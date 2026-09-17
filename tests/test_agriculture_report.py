from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from html import unescape
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.agriculture_cli import (  # noqa: E402
    DEFAULT_SOURCE,
    load_agriculture_canon,
    main as agriculture_main,
)
from baen_economy.agriculture_report import (  # noqa: E402
    render_agriculture_workbench_html,
)


class AgricultureWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_agriculture_canon()
        cls.html = render_agriculture_workbench_html(cls.payload)

    def test_current_actual_freeze_is_prominent_and_not_advanced(self) -> None:
        self.assertIn("CURRENT ACTUAL: Day 7 Hammer 1495 DR, midday Hell-cycle", self.html)
        self.assertIn("LIVE FREEZE · NO CAMPAIGN ADVANCE", self.html)
        self.assertIn("Notion writes <strong>0</strong>", self.html)
        self.assertIn("Canonical ledger postings <strong>0</strong>", self.html)

    def test_four_authority_layers_are_separate_accessible_tabs(self) -> None:
        for tab in (
            "Current Actual",
            "Forward Kythorn 1495",
            "Later References",
            "Technical Design",
        ):
            self.assertIn(f">{tab}</button>", self.html)
        self.assertEqual(self.html.count('<section id="panel-'), 4)
        self.assertIn("RATIFIED FORWARD SCENARIO — NOT CURRENT ACTUAL", self.html)
        self.assertIn("TECHNICAL DESIGN — NOT CANON EXECUTION", self.html)

    def test_every_species_and_crop_is_rendered_with_source_links(self) -> None:
        for species in self.payload["species"]:
            self.assertIn(species["name"], self.html)
            self.assertIn(species["scientific_name"], self.html)
        for crop in self.payload["crop_program"]["crops"]:
            self.assertIn(crop["name"], self.html)
        self.assertIn("Aquaculture Technical Specifications", self.html)
        self.assertIn("https://app.notion.com/p/32be821484b0810f8830e08af7982ae8", self.html)
        self.assertEqual(len(self.payload["species"]), 15)
        self.assertEqual(len(self.payload["crop_program"]["crops"]), 12)
        wheat_start = self.html.index("<strong>Wheat</strong>")
        wheat_end = self.html.index("</tr>", wheat_start)
        wheat_row = self.html[wheat_start:wheat_end]
        self.assertIn("Aquaculture Technical Specifications", wheat_row)
        self.assertNotIn("Agricultural Shelter Zones", wheat_row)
        tomato_start = self.html.index("<strong>Tomatoes</strong>")
        tomato_end = self.html.index("</tr>", tomato_start)
        self.assertIn("Agricultural Shelter Zones", self.html[tomato_start:tomato_end])

    def test_businesses_conflicts_and_blockers_are_not_omitted(self) -> None:
        for entity in self.payload["registry_entities"]:
            self.assertIn(entity["name"], self.html)
        for conflict in self.payload["known_conflicts"]:
            self.assertIn(conflict["description"], self.html)
        readable_html = unescape(self.html)
        for blocker in self.payload["unresolved_inputs"]:
            self.assertIn(blocker, readable_html)
        self.assertIn("never zero", self.html)

    def test_dated_systems_logistics_and_faction_query_are_visible(self) -> None:
        for system in self.payload["dated_agricultural_systems"]:
            self.assertIn(system["name"], self.html)
        self.assertIn("Hunding Canal", self.html)
        self.assertIn("Neverwinter Ice House", self.html)
        self.assertIn("Faction Beliefs cross-reference", self.html)
        self.assertIn("None returned by the live Active+ query", self.html)
        self.assertIn("not converted into an invented production loss", self.html)

    def test_calculators_are_explicitly_non_canon_and_self_contained(self) -> None:
        self.assertIn("Aquaculture capacity + feed", self.html)
        self.assertIn("Crop yield uplift", self.html)
        self.assertIn("Monthly inventory flow", self.html)
        self.assertIn("ALL VALUES USER ASSUMPTIONS · NOT CANON", self.html)
        self.assertIn("No campaign state is changed", self.html)
        self.assertNotIn("fetch(", self.html)
        self.assertNotIn("https://cdn", self.html)
        self.assertIn('type="application/json"', self.html)
        self.assertIn("Assumption fields begin empty", self.html)
        for input_id in (
            "aqua-capacity",
            "aqua-utilization",
            "crop-baseline",
            "inventory-opening",
            "inventory-production",
            "inventory-receipts",
            "inventory-demand",
            "inventory-loss",
            "inventory-months",
        ):
            marker = f'id="{input_id}"'
            element = self.html[self.html.index(marker) : self.html.index(">", self.html.index(marker))]
            self.assertNotIn(" value=", element)
            self.assertIn("placeholder=", element)

    def test_source_coverage_counts_are_visible(self) -> None:
        self.assertIn(f"<strong>{len(self.payload['sources'])}</strong><span>linked Notion authorities", self.html)
        self.assertIn("<strong>15</strong><span>named aquaculture species", self.html)
        self.assertIn("<strong>12</strong><span>named crop entries", self.html)

    def test_responsive_css_reflows_tables_without_page_clipping(self) -> None:
        self.assertIn("overflow-x: hidden", self.html)
        self.assertIn("@media (max-width: 760px)", self.html)
        self.assertIn("table, tbody, tr, td { display: block", self.html)
        self.assertIn("content: attr(data-label)", self.html)

    def test_build_cli_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "agriculture.html"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = agriculture_main(["build", "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("Baen Agriculture Workbench", rendered)
            self.assertIn(str(output.resolve()), stdout.getvalue())

    def test_open_cli_rebuilds_and_opens_file_uri(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "agriculture.html"
            with patch("baen_economy.agriculture_cli.webbrowser.open", return_value=True) as opener:
                code = agriculture_main(["open", "--output", str(output)])
            self.assertEqual(code, 0)
            opener.assert_called_once_with(output.resolve().as_uri(), new=2)
            self.assertTrue(output.is_file())

    def test_windows_launcher_is_one_click_and_repo_relative(self) -> None:
        launcher = (PROJECT / "OPEN-BAEN-AGRICULTURE.cmd").read_text(encoding="utf-8")
        self.assertIn('cd /d "%~dp0"', launcher)
        self.assertIn("OPEN-BAEN-FOOD-OPERATOR.cmd", launcher)
        self.assertNotIn("git ", launcher.lower())
        self.assertNotIn("pip install", launcher.lower())

    def test_invalid_fixture_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
        del payload["species"]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "broken.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = agriculture_main(["build", "--source", str(source)])
            self.assertEqual(code, 2)
            self.assertIn("missing required fields: species", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
