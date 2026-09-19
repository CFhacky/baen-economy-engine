"""Admin-network client for the actual pinned OpenTTD product.

OpenTTD explicitly documents the admin TCP protocol as the product boundary for
other applications.  Baen uses that boundary rather than copying DeliverGoods
or other internal C++ economy routines.

Pinned upstream: OpenTTD/OpenTTD
commit 1aca0b60a8024f295e1d0ad2a3407b3dac838099 (GPL-2.0).

The protocol implementation below mirrors the exact pinned packet contract:
uint16 little-endian whole-packet size, uint8 packet type, little-endian numeric
fields, and NUL-terminated strings.  CI builds/boots the exact dedicated server
and probes it through this client.
"""
from __future__ import annotations

from dataclasses import dataclass
import socket
import struct
import time
from typing import Iterable

OPENTTD_COMMIT = "1aca0b60a8024f295e1d0ad2a3407b3dac838099"
OPENTTD_ADMIN_VERSION = 2  # validated against ServerProtocol at runtime, not assumed for parsing
OPENTTD_PATCH_VERSION = 1

# PacketAdminType at the pinned revision.
_ADMIN_JOIN = 0
_ADMIN_QUIT = 1
_ADMIN_POLL = 3
_ADMIN_RCON = 5
_SERVER_ERROR = 102
_SERVER_PROTOCOL = 103
_SERVER_WELCOME = 104
_SERVER_DATE = 107
_SERVER_COMPANY_ECONOMY = 117
_SERVER_RCON = 120
_SERVER_RCON_END = 125

# AdminUpdateType at the pinned revision.
_UPDATE_DATE = 0
_UPDATE_COMPANY_ECONOMY = 3


class OpenTTDProductError(RuntimeError):
    """The OpenTTD product/admin protocol could not satisfy a read request."""


@dataclass(frozen=True, slots=True)
class OpenTTDCompanyEconomy:
    company_id: int
    money: int
    loan: int
    income: int
    delivered_cargo_current_quarter: int
    company_value_last_quarter: int
    performance_last_quarter: int
    delivered_cargo_last_quarter: int
    company_value_previous_quarter: int
    performance_previous_quarter: int
    delivered_cargo_previous_quarter: int


@dataclass(frozen=True, slots=True)
class OpenTTDProductSnapshot:
    upstream: str
    upstream_commit: str
    protocol_version: int
    server_name: str
    revision: str
    dedicated: bool
    generation_seed: int
    landscape: int
    start_date: int
    map_width: int
    map_height: int
    current_date: int
    companies: tuple[OpenTTDCompanyEconomy, ...]
    rcon_output: tuple[str, ...]
    canonical_time_advanced: bool = False


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = memoryview(data)
        self.pos = 0

    def _take(self, count: int) -> bytes:
        if self.pos + count > len(self.data):
            raise OpenTTDProductError("OpenTTD admin packet is truncated")
        value = self.data[self.pos : self.pos + count].tobytes()
        self.pos += count
        return value

    def u8(self) -> int:
        return self._take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self._take(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self._take(8))[0]

    def boolean(self) -> bool:
        return self.u8() != 0

    def string(self) -> str:
        raw = self.data[self.pos :].tobytes()
        end = raw.find(b"\0")
        if end < 0:
            raise OpenTTDProductError("OpenTTD admin string is not NUL terminated")
        self.pos += end + 1
        return raw[:end].decode("utf-8", errors="replace")


class OpenTTDAdminClient:
    """Minimal read-oriented client for OpenTTD's documented admin network."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3977,
        *,
        password: str,
        timeout: float = 5.0,
        name: str = "baen-economy-engine",
        version: str = "0.3.0",
    ) -> None:
        if not isinstance(host, str) or not host:
            raise ValueError("host is required")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be 1..65535")
        if not isinstance(password, str) or not password:
            raise ValueError("OpenTTD admin password is required")
        if type(timeout) not in {int, float} or timeout <= 0:
            raise ValueError("timeout must be positive")
        self.host, self.port, self.password = host, port, password
        self.timeout, self.name, self.version = float(timeout), name, version
        self.sock: socket.socket | None = None

    def __enter__(self) -> "OpenTTDAdminClient":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @staticmethod
    def _cstring(value: str) -> bytes:
        if "\0" in value:
            raise ValueError("OpenTTD admin strings may not contain NUL")
        return value.encode("utf-8") + b"\0"

    @staticmethod
    def _packet(packet_type: int, payload: bytes = b"") -> bytes:
        size = 3 + len(payload)
        if size > 65535:
            raise ValueError("OpenTTD admin packet too large")
        return struct.pack("<HB", size, packet_type) + payload

    def _send(self, packet_type: int, payload: bytes = b"") -> None:
        if self.sock is None:
            raise OpenTTDProductError("OpenTTD admin client is not connected")
        self.sock.sendall(self._packet(packet_type, payload))

    @staticmethod
    def _recv_exact(sock: socket.socket, count: int) -> bytes:
        chunks: list[bytes] = []
        remaining = count
        while remaining:
            chunk = sock.recv(remaining)
            if not chunk:
                raise OpenTTDProductError("OpenTTD admin connection closed unexpectedly")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv(self) -> tuple[int, bytes]:
        if self.sock is None:
            raise OpenTTDProductError("OpenTTD admin client is not connected")
        size = struct.unpack("<H", self._recv_exact(self.sock, 2))[0]
        if size < 3:
            raise OpenTTDProductError("OpenTTD admin packet has invalid size")
        body = self._recv_exact(self.sock, size - 2)
        packet_type = body[0]
        payload = body[1:]
        if packet_type == _SERVER_ERROR:
            code = payload[0] if payload else None
            raise OpenTTDProductError(f"OpenTTD admin server returned error code {code}")
        return packet_type, payload

    def connect(self) -> None:
        if self.sock is not None:
            raise OpenTTDProductError("OpenTTD admin client is already connected")
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            raise OpenTTDProductError(f"cannot connect to OpenTTD admin port: {exc}") from exc
        sock.settimeout(self.timeout)
        self.sock = sock
        self._send(
            _ADMIN_JOIN,
            self._cstring(self.password) + self._cstring(self.name) + self._cstring(self.version),
        )

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            self._send(_ADMIN_QUIT)
        except (OSError, OpenTTDProductError):
            pass
        self.sock.close()
        self.sock = None

    def handshake(self) -> tuple[int, dict[str, object]]:
        protocol_version: int | None = None
        welcome: dict[str, object] | None = None
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline and (protocol_version is None or welcome is None):
            packet_type, payload = self._recv()
            if packet_type == _SERVER_PROTOCOL:
                reader = _Reader(payload)
                protocol_version = reader.u8()
                # Protocol advertises update types/frequency bitsets after version.
                # We do not need to mirror them to parse the subsequent welcome.
            elif packet_type == _SERVER_WELCOME:
                reader = _Reader(payload)
                welcome = {
                    "server_name": reader.string(),
                    "revision": reader.string(),
                    "dedicated": reader.boolean(),
                    "map_name_legacy": reader.string(),
                    "generation_seed": reader.u32(),
                    "landscape": reader.u8(),
                    "start_date": reader.u32(),
                    "map_width": reader.u16(),
                    "map_height": reader.u16(),
                }
        if protocol_version is None or welcome is None:
            raise OpenTTDProductError("OpenTTD admin handshake did not complete")
        return protocol_version, welcome

    def poll_date(self) -> int:
        self._send(_ADMIN_POLL, struct.pack("<BI", _UPDATE_DATE, 0))
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            packet_type, payload = self._recv()
            if packet_type == _SERVER_DATE:
                return _Reader(payload).u32()
        raise OpenTTDProductError("OpenTTD date poll timed out")

    @staticmethod
    def _company_economy(payload: bytes) -> OpenTTDCompanyEconomy:
        reader = _Reader(payload)
        return OpenTTDCompanyEconomy(
            company_id=reader.u8(),
            money=reader.u64(),
            loan=reader.u64(),
            income=reader.i64(),
            delivered_cargo_current_quarter=reader.u16(),
            company_value_last_quarter=reader.u64(),
            performance_last_quarter=reader.u16(),
            delivered_cargo_last_quarter=reader.u16(),
            company_value_previous_quarter=reader.u64(),
            performance_previous_quarter=reader.u16(),
            delivered_cargo_previous_quarter=reader.u16(),
        )

    def poll_company_economy(self, *, quiet_window: float = 0.2) -> tuple[OpenTTDCompanyEconomy, ...]:
        """Poll every existing OpenTTD company economy record.

        The protocol sends one packet per company and no explicit terminator for
        this poll.  We therefore collect until a short socket quiet window.  An
        empty tuple is a valid answer for a fresh server with no companies.
        """

        if quiet_window <= 0:
            raise ValueError("quiet_window must be positive")
        self._send(_ADMIN_POLL, struct.pack("<BI", _UPDATE_COMPANY_ECONOMY, 0))
        if self.sock is None:
            raise OpenTTDProductError("OpenTTD admin client is not connected")
        old_timeout = self.sock.gettimeout()
        self.sock.settimeout(quiet_window)
        companies: list[OpenTTDCompanyEconomy] = []
        try:
            while True:
                try:
                    packet_type, payload = self._recv()
                except socket.timeout:
                    break
                if packet_type == _SERVER_COMPANY_ECONOMY:
                    companies.append(self._company_economy(payload))
        finally:
            self.sock.settimeout(old_timeout)
        return tuple(companies)

    def rcon(self, command: str) -> tuple[str, ...]:
        if not isinstance(command, str) or not command or "\0" in command:
            raise ValueError("rcon command must be non-empty NUL-free text")
        self._send(_ADMIN_RCON, self._cstring(command))
        output: list[str] = []
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            packet_type, payload = self._recv()
            if packet_type == _SERVER_RCON:
                reader = _Reader(payload)
                reader.u16()  # colour; presentation-only for this integration
                output.append(reader.string())
            elif packet_type == _SERVER_RCON_END:
                reader = _Reader(payload)
                if reader.string() != command:
                    raise OpenTTDProductError("OpenTTD rcon completion command mismatch")
                return tuple(output)
        raise OpenTTDProductError("OpenTTD rcon command timed out")

    def transport_income(
        self,
        *,
        cargo_type: int,
        pieces: int,
        distance_tiles: int,
        days_in_transit: int,
    ) -> int:
        """Execute OpenTTD's real GetTransportedGoodsIncome through rcon."""

        values = {
            "cargo_type": cargo_type,
            "pieces": pieces,
            "distance_tiles": distance_tiles,
            "days_in_transit": days_in_transit,
        }
        for name, value in values.items():
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        command = (
            f"baen_transport_income {cargo_type} {pieces} "
            f"{distance_tiles} {days_in_transit}"
        )
        output = self.rcon(command)
        prefix = "BAEN_TRANSPORT_INCOME "
        line = next((item for item in output if item.startswith(prefix)), None)
        if line is None:
            raise OpenTTDProductError(
                "patched OpenTTD product returned no BAEN_TRANSPORT_INCOME result"
            )
        fields: dict[str, str] = {}
        for token in line[len(prefix):].split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            fields[key] = value
        required = {"cargo", "pieces", "distance", "days", "income"}
        if set(fields) != required:
            raise OpenTTDProductError("OpenTTD transport-income result fields changed")
        try:
            parsed = {key: int(value) for key, value in fields.items()}
        except ValueError as exc:
            raise OpenTTDProductError(
                "OpenTTD transport-income result contains invalid integers"
            ) from exc
        expected = {
            "cargo": cargo_type,
            "pieces": pieces,
            "distance": distance_tiles,
            "days": days_in_transit,
        }
        if any(parsed[key] != value for key, value in expected.items()):
            raise OpenTTDProductError("OpenTTD transport-income result identity drifted")
        return parsed["income"]

    def snapshot(self) -> OpenTTDProductSnapshot:
        protocol, welcome = self.handshake()
        current_date = self.poll_date()
        companies = self.poll_company_economy()
        rcon_output = self.rcon("status")
        return OpenTTDProductSnapshot(
            upstream="OpenTTD",
            upstream_commit=OPENTTD_COMMIT,
            protocol_version=protocol,
            server_name=str(welcome["server_name"]),
            revision=str(welcome["revision"]),
            dedicated=bool(welcome["dedicated"]),
            generation_seed=int(welcome["generation_seed"]),
            landscape=int(welcome["landscape"]),
            start_date=int(welcome["start_date"]),
            map_width=int(welcome["map_width"]),
            map_height=int(welcome["map_height"]),
            current_date=current_date,
            companies=companies,
            rcon_output=rcon_output,
            canonical_time_advanced=False,
        )
