from __future__ import annotations

import socket
import struct
from threading import Thread
import time
import unittest

from baen_economy.openttd_product import (
    OPENTTD_COMMIT,
    OpenTTDAdminClient,
)


def packet(kind: int, payload: bytes = b"") -> bytes:
    return struct.pack("<HB", len(payload) + 3, kind) + payload


def cstring(value: str) -> bytes:
    return value.encode() + b"\0"


def recv_packet(conn: socket.socket) -> tuple[int, bytes]:
    header = conn.recv(2)
    if len(header) != 2:
        raise RuntimeError("short header")
    size = struct.unpack("<H", header)[0]
    body = b""
    while len(body) < size - 2:
        chunk = conn.recv(size - 2 - len(body))
        if not chunk:
            raise RuntimeError("short packet")
        body += chunk
    return body[0], body[1:]


class _FakeAdmin:
    def __init__(self) -> None:
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.error: BaseException | None = None
        self.thread = Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self) -> None:
        try:
            conn, _ = self.listener.accept()
            with conn:
                kind, payload = recv_packet(conn)
                assert kind == 0
                assert b"secret\0baen-economy-engine\00.3.0\0" == payload
                conn.sendall(packet(103, b"\x02\x00"))
                welcome = (
                    cstring("Fake OpenTTD") + cstring("1aca-test") + b"\x01" + cstring("")
                    + struct.pack("<IBIHH", 424242, 0, 0, 256, 256)
                )
                conn.sendall(packet(104, welcome))

                kind, payload = recv_packet(conn)
                assert kind == 3 and payload == struct.pack("<BI", 0, 0)
                conn.sendall(packet(107, struct.pack("<I", 12345)))

                kind, payload = recv_packet(conn)
                assert kind == 3 and payload == struct.pack("<BI", 3, 0)
                company = (
                    struct.pack("<BQQqH", 2, 50000, 10000, 1234, 77)
                    + struct.pack("<QHH", 60000, 500, 66)
                    + struct.pack("<QHH", 55000, 480, 61)
                )
                conn.sendall(packet(117, company))
                # Let the client's documented quiet-window collection terminate.
                time.sleep(0.08)

                kind, payload = recv_packet(conn)
                assert kind == 5 and payload == cstring("status")
                conn.sendall(packet(120, struct.pack("<H", 1) + cstring("Server is running")))
                conn.sendall(packet(125, cstring("status")))
                try:
                    recv_packet(conn)  # optional AdminQuit
                except Exception:
                    pass
        except BaseException as exc:
            self.error = exc
        finally:
            self.listener.close()

    def close(self) -> None:
        self.thread.join(timeout=3)
        if self.error is not None:
            raise self.error


class OpenTTDProductTests(unittest.TestCase):
    def test_exact_upstream_pin(self):
        self.assertEqual(OPENTTD_COMMIT, "1aca0b60a8024f295e1d0ad2a3407b3dac838099")

    def test_actual_admin_wire_contract_and_company_economy_parser(self):
        server = _FakeAdmin()
        try:
            with OpenTTDAdminClient(
                "127.0.0.1", server.port, password="secret", timeout=1.0
            ) as client:
                snapshot = client.snapshot()
            self.assertEqual(snapshot.protocol_version, 2)
            self.assertEqual(snapshot.server_name, "Fake OpenTTD")
            self.assertTrue(snapshot.dedicated)
            self.assertEqual(snapshot.current_date, 12345)
            self.assertEqual(snapshot.rcon_output, ("Server is running",))
            self.assertEqual(len(snapshot.companies), 1)
            economy = snapshot.companies[0]
            self.assertEqual(economy.company_id, 2)
            self.assertEqual(economy.money, 50000)
            self.assertEqual(economy.loan, 10000)
            self.assertEqual(economy.income, 1234)
            self.assertEqual(economy.delivered_cargo_current_quarter, 77)
            self.assertEqual(economy.company_value_last_quarter, 60000)
            self.assertEqual(economy.delivered_cargo_previous_quarter, 61)
            self.assertFalse(snapshot.canonical_time_advanced)
        finally:
            server.close()

    def test_admin_password_required(self):
        with self.assertRaises(ValueError):
            OpenTTDAdminClient(password="")


if __name__ == "__main__":
    unittest.main()
