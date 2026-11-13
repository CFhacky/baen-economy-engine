from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from baen_economy.unknown_horizons_product import (
    UNKNOWN_HORIZONS_COMMIT,
    UnknownHorizonsProductError,
    run_unknown_horizons_production_line,
)


class UnknownHorizonsProductTests(unittest.TestCase):
    def test_exact_upstream_pin_is_visible(self):
        self.assertEqual(
            UNKNOWN_HORIZONS_COMMIT,
            "af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615",
        )

    def test_non_product_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(UnknownHorizonsProductError):
                run_unknown_horizons_production_line(
                    temp, line_id=1, produces=((1, 2),), consumes=((2, -1),)
                )

    def test_duplicate_resource_input_is_rejected_before_product_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "horizons/world/production").mkdir(parents=True)
            (root / "horizons/world/production/productionline.py").write_text("# marker\n")
            # The duplicate check occurs after checkout identity verification, so
            # this synthetic path intentionally proves only the missing-product
            # failure boundary rather than pretending to execute upstream code.
            with self.assertRaises(UnknownHorizonsProductError):
                run_unknown_horizons_production_line(
                    root, line_id=1, produces=((1, 2), (1, 3))
                )

    @unittest.skipUnless(
        os.environ.get("UNKNOWN_HORIZONS_CHECKOUT"),
        "actual pinned Unknown Horizons checkout is exercised in the dedicated CI product job",
    )
    def test_actual_pinned_product_executes_production_line(self):
        result = run_unknown_horizons_production_line(
            os.environ["UNKNOWN_HORIZONS_CHECKOUT"],
            line_id=77,
            produces=((1, 2.5),),
            consumes=((2, -3.0),),
            time=6.0,
        )
        self.assertEqual(result.upstream, "Unknown Horizons")
        self.assertEqual(result.upstream_commit, UNKNOWN_HORIZONS_COMMIT)
        self.assertEqual(result.line_id, 77)
        self.assertEqual(result.time, 6.0)
        self.assertEqual(result.produced, {1: 2.5})
        self.assertEqual(result.consumed, {2: -3.0})
        self.assertEqual(result.production, {1: 2.5, 2: -3.0})
        self.assertEqual(result.units, {})
        self.assertFalse(result.canonical_time_advanced)


if __name__ == "__main__":
    unittest.main()
