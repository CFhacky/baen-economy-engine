#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

sudo apt-get update -qq
sudo apt-get install -y -qq ant

python -m pip install --upgrade pip
python -m pip install -e '.[mesa]'

mkdir -p .upstream
python tools/prepare_unknown_horizons_product.py --checkout .upstream/unknown-horizons
python tools/prepare_freecol_product.py --checkout .upstream/freecol

echo "Baen mobile app dependencies prepared."
