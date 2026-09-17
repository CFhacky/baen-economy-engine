"""Read-only client for the actual pinned Brunnfeld Agentic World product.

Brunnfeld exposes a Node HTTP server (`npm run server`) with economy, market,
trade, price, state, village, and SSE endpoints.  Baen therefore treats it as an
external simulation sidecar instead of copying its TypeScript economy classes.

Pinned upstream: marcopatzelt/brunnfeld-agentic-world
commit e0656ca01630333e26c622ffd4ba4c973b79eebe (MIT).

This client is deliberately read-only.  It does not call Brunnfeld's mutating
`/api/start`, `/api/generate-world`, event, meeting, or whisper endpoints, and it
cannot advance Baen's canonical campaign clock.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BRUNNFELD_COMMIT = "e0656ca01630333e26c622ffd4ba4c973b79eebe"
BRUNNFELD_DEFAULT_URL = "http://127.0.0.1:3333"


class BrunnfeldSidecarError(RuntimeError):
    """The pinned Brunnfeld sidecar is unavailable or returned invalid data."""


@dataclass(frozen=True, slots=True)
class BrunnfeldSnapshot:
    """One read-only cross-section of the running Brunnfeld product."""

    upstream: str
    upstream_commit: str
    state: dict[str, Any]
    economy: list[Any]
    marketplace: dict[str, Any]
    trades: list[Any]
    prices: dict[str, Any]
    villages: list[Any]
    canonical_time_advanced: bool = False


class BrunnfeldServiceClient:
    """Consume Brunnfeld's actual HTTP product boundary without reimplementation."""

    def __init__(self, base_url: str = BRUNNFELD_DEFAULT_URL, *, timeout: float = 5.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Brunnfeld base_url must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("Brunnfeld base_url may not contain query or fragment components")
        if type(timeout) not in {int, float} or timeout <= 0:
            raise ValueError("Brunnfeld timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def _get_json(self, path: str) -> Any:
        if not path.startswith("/api/"):
            raise ValueError("Brunnfeld reads must use an /api/ endpoint")
        request = Request(
            self.base_url + path,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": "baen-economy-engine"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise BrunnfeldSidecarError(
                        f"Brunnfeld {path} returned HTTP {response.status}"
                    )
                raw = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise BrunnfeldSidecarError(f"Brunnfeld {path} is unavailable: {exc}") from exc
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BrunnfeldSidecarError(f"Brunnfeld {path} returned non-JSON data") from exc

    @staticmethod
    def _expect(value: Any, expected: type, endpoint: str) -> Any:
        if not isinstance(value, expected):
            raise BrunnfeldSidecarError(
                f"Brunnfeld {endpoint} returned {type(value).__name__}; expected {expected.__name__}"
            )
        return value

    def state(self) -> dict[str, Any]:
        return self._expect(self._get_json("/api/state"), dict, "/api/state")

    def economy(self) -> list[Any]:
        return self._expect(self._get_json("/api/economy"), list, "/api/economy")

    def marketplace(self) -> dict[str, Any]:
        return self._expect(self._get_json("/api/marketplace"), dict, "/api/marketplace")

    def trades(self) -> list[Any]:
        return self._expect(self._get_json("/api/trades"), list, "/api/trades")

    def prices(self) -> dict[str, Any]:
        return self._expect(self._get_json("/api/prices"), dict, "/api/prices")

    def villages(self) -> list[Any]:
        return self._expect(self._get_json("/api/villages"), list, "/api/villages")

    def snapshot(self) -> BrunnfeldSnapshot:
        """Read the product's published economic/state views without mutating it."""

        return BrunnfeldSnapshot(
            upstream="Brunnfeld Agentic World",
            upstream_commit=BRUNNFELD_COMMIT,
            state=self.state(),
            economy=self.economy(),
            marketplace=self.marketplace(),
            trades=self.trades(),
            prices=self.prices(),
            villages=self.villages(),
            canonical_time_advanced=False,
        )
