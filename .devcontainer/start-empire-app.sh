#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

mkdir -p "$HOME/.local/share/baen-economy"
export PYTHONPATH="$ROOT/src"
export UNKNOWN_HORIZONS_CHECKOUT="$ROOT/.upstream/unknown-horizons"
export FREECOL_CHECKOUT="$ROOT/.upstream/freecol"

# Stop only a prior copy of this application owned by the current Codespace user.
if [ -f "$HOME/.local/share/baen-economy/app.pid" ]; then
  OLD_PID="$(cat "$HOME/.local/share/baen-economy/app.pid" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" || true
  fi
fi

nohup python -m baen_economy.empire_ops_server   --host 0.0.0.0   --port 8765   --database "$HOME/.local/share/baen-economy/baen-empire-operator.sqlite"   > "$HOME/.local/share/baen-economy/app.log" 2>&1 &

echo $! > "$HOME/.local/share/baen-economy/app.pid"
echo "Baen Economy Engine: http://127.0.0.1:8765"
