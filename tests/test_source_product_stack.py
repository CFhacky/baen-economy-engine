from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baen_economy.product_stack import prepare_source_products, source_product_environment


class SourceProductStackTests(unittest.TestCase):
    @patch("baen_economy.product_stack._ensure_freecol")
    @patch("baen_economy.product_stack._ensure_unknown_horizons")
    @patch("baen_economy.product_stack._ensure_mesa")
    def test_prepare_source_products_only_prepares_admissible_products(
        self, ensure_mesa, ensure_unknown, ensure_freecol
    ):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ensure_unknown.return_value = root / "unknown-horizons"
            ensure_freecol.return_value = root / "freecol"
            paths = prepare_source_products(root)
        ensure_mesa.assert_called_once_with()
        ensure_unknown.assert_called_once()
        ensure_freecol.assert_called_once()
        self.assertEqual(
            set(paths),
            {"unknown_horizons", "freecol"},
        )

    @patch("baen_economy.product_stack._ensure_freecol")
    @patch("baen_economy.product_stack._ensure_unknown_horizons")
    @patch("baen_economy.product_stack._ensure_mesa")
    def test_source_environment_sets_and_restores_only_actual_product_checkouts(
        self, ensure_mesa, ensure_unknown, ensure_freecol
    ):
        previous_unknown = os.environ.get("UNKNOWN_HORIZONS_CHECKOUT")
        previous_freecol = os.environ.get("FREECOL_CHECKOUT")
        previous_openttd = os.environ.get("OPENTTD_ADMIN_HOST")
        os.environ["UNKNOWN_HORIZONS_CHECKOUT"] = "before-unknown"
        os.environ["FREECOL_CHECKOUT"] = "before-freecol"
        os.environ["OPENTTD_ADMIN_HOST"] = "do-not-touch"
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                ensure_unknown.return_value = root / "unknown-horizons"
                ensure_freecol.return_value = root / "freecol"
                with source_product_environment(root):
                    self.assertEqual(
                        os.environ["UNKNOWN_HORIZONS_CHECKOUT"],
                        str(root / "unknown-horizons"),
                    )
                    self.assertEqual(
                        os.environ["FREECOL_CHECKOUT"],
                        str(root / "freecol"),
                    )
                    self.assertEqual(os.environ["OPENTTD_ADMIN_HOST"], "do-not-touch")
                self.assertEqual(os.environ["UNKNOWN_HORIZONS_CHECKOUT"], "before-unknown")
                self.assertEqual(os.environ["FREECOL_CHECKOUT"], "before-freecol")
                self.assertEqual(os.environ["OPENTTD_ADMIN_HOST"], "do-not-touch")
        finally:
            if previous_unknown is None:
                os.environ.pop("UNKNOWN_HORIZONS_CHECKOUT", None)
            else:
                os.environ["UNKNOWN_HORIZONS_CHECKOUT"] = previous_unknown
            if previous_freecol is None:
                os.environ.pop("FREECOL_CHECKOUT", None)
            else:
                os.environ["FREECOL_CHECKOUT"] = previous_freecol
            if previous_openttd is None:
                os.environ.pop("OPENTTD_ADMIN_HOST", None)
            else:
                os.environ["OPENTTD_ADMIN_HOST"] = previous_openttd


if __name__ == "__main__":
    unittest.main()
