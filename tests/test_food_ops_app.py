from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_ops_app import (  # noqa: E402
    render_food_ops_app,
    write_food_ops_app,
)


class FoodOpsAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = render_food_ops_app()

    def test_render_returns_complete_operator_document(self) -> None:
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn("<title>Baen Food-Sector Operator</title>", self.html)
        self.assertIn("<main>", self.html)
        self.assertIn("</html>", self.html)
        self.assertIn("Decisions first. Sources remain attached.", self.html)

    def test_write_creates_parent_directories_and_exact_rendered_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "nested" / "Baen-Food-Operator.html"
            written = write_food_ops_app(destination)

            self.assertEqual(written, destination)
            self.assertTrue(destination.is_file())
            self.assertEqual(destination.read_text(encoding="utf-8"), self.html)

    def test_required_navigation_and_primary_operator_controls_are_present(self) -> None:
        for view, label in (
            ("dashboard", "Dashboard"),
            ("longsaddle", "Plan Longsaddle"),
            ("production", "Plan Fish &amp; Crops"),
            ("month", "Preview Food Month"),
            ("rulings", "Open Rulings"),
            ("evidence", "Evidence"),
        ):
            self.assertIn(f'data-view="{view}"', self.html)
            self.assertIn(f">{label}</button>", self.html)
            self.assertIn(f'id="view-{view}"', self.html)

        for control_id in (
            "longsaddle-form",
            "load-low",
            "longsaddle-result",
            "aquaculture-form",
            "crop-form",
            "production-result",
            "month-form",
            "generate-seed",
            "month-result",
            "refresh-saved",
            "saved-list",
            "compare-result",
        ):
            self.assertIn(f'id="{control_id}"', self.html)

        for label in (
            "Load illustrative low case",
            "Run plan",
            "Run aquaculture plan",
            "Run crop plan",
            "Generate replay seed",
            "Run non-canon preview",
            "Save locally",
            "Print",
            "Compare selected",
            "Export",
        ):
            self.assertIn(label, self.html)

    def test_operator_calls_only_the_expected_local_api_routes(self) -> None:
        for endpoint in (
            "/api/bootstrap",
            "/api/longsaddle/preview",
            "/api/production/aquaculture/preview",
            "/api/production/crop/preview",
            "/api/food-sector/preview",
            "/api/scenarios",
            "/api/scenarios/${encodeURIComponent(id)}",
            "/api/scenarios/${encodeURIComponent(id)}/export?format=html",
        ):
            self.assertIn(endpoint, self.html)

        literal_api_routes = set(re.findall(r"['\"](/api/[^'\"]*)['\"]", self.html))
        self.assertEqual(
            literal_api_routes,
            {
                "/api/bootstrap",
                "/api/food-sector/preview",
                "/api/longsaddle/preview",
                "/api/production/aquaculture/preview",
                "/api/production/crop/preview",
                "/api/scenarios",
            },
        )

    def test_provenance_and_campaign_safety_boundaries_are_visible(self) -> None:
        for provenance_class in ("Source", "Assumption", "Derived", "Unknown"):
            self.assertIn(f"['{provenance_class}'", self.html)

        for safety_text in (
            "Read-only · no Notion or ledger writes",
            "A preview never advances time.",
            "non-canon until accepted",
            "It is not a binding campaign roll.",
            "Notion writes 0",
            "ledger postings 0",
            "campaign time advanced no",
            "Blank means unresolved; it never becomes zero.",
        ):
            self.assertIn(safety_text, self.html)

    def test_document_has_no_external_asset_dependencies(self) -> None:
        self.assertIsNone(re.search(r"<script\b[^>]*\bsrc\s*=", self.html, re.IGNORECASE))
        self.assertIsNone(re.search(r"<link\b[^>]*\bhref\s*=", self.html, re.IGNORECASE))
        self.assertIsNone(re.search(r"<(?:img|iframe|video|audio|source)\b[^>]*\bsrc\s*=", self.html, re.IGNORECASE))
        self.assertIsNone(re.search(r"@import\s+", self.html, re.IGNORECASE))
        self.assertIsNone(re.search(r"url\(\s*['\"]?https?://", self.html, re.IGNORECASE))
        self.assertNotIn("https://cdn", self.html.lower())

    def test_inline_javascript_has_valid_syntax_when_node_is_available(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")

        matches = re.findall(r"<script>(.*?)</script>", self.html, re.DOTALL | re.IGNORECASE)
        self.assertEqual(len(matches), 1, "expected exactly one inline application script")
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "food-ops-app.js"
            script.write_text(matches[0], encoding="utf-8")
            checked = subprocess.run(
                [node, "--check", str(script)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(checked.returncode, 0, checked.stderr or checked.stdout)

    def test_windows_launcher_is_repo_relative_and_uses_persistent_local_store(self) -> None:
        launcher = (PROJECT / "OPEN-BAEN-FOOD-OPERATOR.cmd").read_text(
            encoding="utf-8"
        )
        self.assertIn('cd /d "%~dp0"', launcher)
        self.assertIn("baen_economy.food_ops_server", launcher)
        self.assertIn("%USERPROFILE%\\Documents\\Baen Economy", launcher)
        self.assertIn("--open", launcher)
        self.assertNotIn("git ", launcher.lower())
        self.assertNotIn("pip install", launcher.lower())


if __name__ == "__main__":
    unittest.main()
