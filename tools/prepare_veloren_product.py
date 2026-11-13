#!/usr/bin/env python3
"""Acquire pinned Veloren and build the minimal GPL-side Baen economy bridge.

The upstream economy implementation remains Veloren's. The only patch exposes
state injection that Veloren's own economy tests currently perform from inside
the module because the relevant fields are private. The bridge then calls the
existing public ``Economy::tick`` and reads the existing public information and
price APIs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

REPO = "https://github.com/veloren/veloren.git"
COMMIT = "e633eb8ca15ae97bb5ef5a039fcf6844e96ad704"
PATCH_VERSION = 1

METHOD_MARKER = "    pub fn population(&self) -> f32 { self.pop }\n"
METHOD_INSERT = r'''    /// Baen GPL-side adapter seam: seed externally sourced scenario state
    /// without reimplementing Veloren's economy algorithms outside this crate.
    pub fn baen_import_state(&mut self, population: f32, stocks: &[(Good, f32)]) {
        self.pop = population.max(0.0);
        self.stocks = GoodMap::default();
        self.surplus = Default::default();
        self.marginal_surplus = Default::default();
        self.unconsumed_stock = Default::default();
        self.last_exports = Default::default();
        self.active_exports = Default::default();
        self.orders.clear();
        self.deliveries.clear();
        for (good, amount) in stocks.iter().copied() {
            if let Ok(index) = GoodIndex::try_from(good) {
                self.stocks[index] = amount.max(0.0);
            }
        }
    }

'''

EXAMPLE = r'''use common::{store::Store, trade::Good};
use std::env;
use veloren_world::site::Site;

fn number(args: &[String], index: usize, name: &str) -> f32 {
    args.get(index)
        .unwrap_or_else(|| panic!("missing {name}"))
        .parse::<f32>()
        .unwrap_or_else(|_| panic!("invalid {name}"))
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let population = number(&args, 1, "population");
    let food = number(&args, 2, "food_stock");
    let coin = number(&args, 3, "coin_stock");
    let days = number(&args, 4, "days");
    if days <= 0.0 {
        panic!("days must be positive");
    }

    let mut sites: Store<Site> = Store::default();
    let mut site = Site::default();
    site.economy_mut().baen_import_state(
        population,
        &[(Good::Food, food), (Good::Coin, coin)],
    );
    let id = sites.insert(site);
    sites.get_mut(id).economy_mut().tick(id, days);

    let economy = sites.get(id).economy.as_ref().expect("economy");
    let info = economy.get_information(id);
    let prices = economy.get_site_prices();
    let food_after = info.stock.get(&Good::Food).copied().unwrap_or(0.0);
    let coin_after = info.stock.get(&Good::Coin).copied().unwrap_or(0.0);
    let food_price = prices.values.get(&Good::Food).copied().unwrap_or(0.0);
    println!(
        "population={};food={};coin={};food_price={};days={}",
        info.population, food_after, coin_after, food_price, days
    );
}
'''


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def output(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(".upstream/veloren"))
    parser.add_argument("--toolchain", default="nightly")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if not shutil.which("git"):
        raise SystemExit("git is required")
    if not shutil.which("cargo"):
        raise SystemExit("cargo/rustup are required")
    checkout = args.checkout.resolve()
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
        run(["git", "clone", REPO, str(checkout)], env=env)
    if not (checkout / ".git").is_dir():
        raise SystemExit(f"{checkout} is not a git checkout")
    run(["git", "fetch", "origin", COMMIT], cwd=checkout)
    run(["git", "checkout", "--detach", "--force", COMMIT], cwd=checkout)
    run(["git", "clean", "-fdx"], cwd=checkout)
    actual = output(["git", "rev-parse", "HEAD"], cwd=checkout)
    if actual != COMMIT:
        raise SystemExit(f"Veloren checkout mismatch: expected {COMMIT}, got {actual}")

    economy = checkout / "world/src/site/economy/mod.rs"
    text = economy.read_text(encoding="utf-8")
    if METHOD_MARKER not in text:
        raise SystemExit("Veloren economy patch marker changed; refusing fuzzy patch")
    text = text.replace(METHOD_MARKER, METHOD_INSERT + METHOD_MARKER, 1)
    economy.write_text(text, encoding="utf-8")

    example = checkout / "world/examples/baen_economy_bridge.rs"
    example.write_text(EXAMPLE, encoding="utf-8")
    marker = checkout / ".baen-economy-product-patch.json"
    marker.write_text(
        json.dumps({"upstream_commit": COMMIT, "patch_version": PATCH_VERSION}, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if not args.skip_build:
        env = dict(
            os.environ,
            VELOREN_ASSETS=str(checkout / "assets"),
            DISABLE_GIT_LFS_CHECK="true",
            CARGO_INCREMENTAL="0",
        )
        run(
            ["cargo", f"+{args.toolchain}", "build", "-p", "veloren-world",
             "--example", "baen_economy_bridge", "--no-default-features"],
            cwd=checkout,
            env=env,
        )
    binary = checkout / "target/debug/examples/baen_economy_bridge"
    if not args.skip_build and not binary.is_file():
        raise SystemExit("Veloren Baen product bridge binary was not produced")
    print(f"Veloren {COMMIT} GPL-side bridge ready at {checkout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
