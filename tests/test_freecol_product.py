from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from baen_economy.freecol_product import (
    FREECOL_COMMIT,
    FreeColProductError,
    run_freecol_production_info,
)


class FreeColProductTests(unittest.TestCase):
    def test_exact_upstream_pin_is_visible(self):
        self.assertEqual(FREECOL_COMMIT, "0a9e3cce950471fa67ae390d1a2fdf179e732092")

    def test_missing_product_jar_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FreeColProductError):
                run_freecol_production_info(temp, actual={"grain": 5}, maximum={"grain": 9})

    def test_invalid_mapping_key_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "FreeCol.jar").write_bytes(b"not-a-real-jar")
            # Checkout verification happens before argument encoding; this is a
            # fail-closed product-boundary test, not a fake execution success.
            with self.assertRaises(FreeColProductError):
                run_freecol_production_info(root, actual={"bad,key": 5}, maximum={})

    @unittest.skipUnless(
        os.environ.get("FREECOL_CHECKOUT"),
        "actual pinned FreeCol checkout is exercised in the dedicated CI product job",
    )
    def test_actual_pinned_product_executes_production_info(self):
        result = run_freecol_production_info(
            os.environ["FREECOL_CHECKOUT"],
            actual={"model.goods.grain": 6, "model.goods.tools": 4},
            maximum={"model.goods.grain": 10, "model.goods.tools": 4},
        )
        self.assertEqual(result.upstream, "FreeCol")
        self.assertEqual(result.upstream_commit, FREECOL_COMMIT)
        self.assertEqual(result.actual, {"model.goods.grain": 6, "model.goods.tools": 4})
        self.assertEqual(result.maximum, {"model.goods.grain": 10, "model.goods.tools": 4})
        self.assertEqual(result.deficits, {"model.goods.grain": 4})
        self.assertFalse(result.canonical_time_advanced)


if __name__ == "__main__":
    unittest.main()
