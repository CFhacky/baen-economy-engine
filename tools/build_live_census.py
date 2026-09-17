#!/usr/bin/env python3
"""Compatibility entry point for the canonical live-census publication stage.

Direct Notion acquisition receipts are retained in recovery/acquisition. This
entry point must not rebuild the durable census from an older, partial receipt
set or overwrite a more complete census. All publication and --check behavior
is delegated to the same materializer used by the tested GitHub workflow.
"""
from __future__ import annotations

from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from materialize_live_census import main


if __name__ == "__main__":
    raise SystemExit(main())
