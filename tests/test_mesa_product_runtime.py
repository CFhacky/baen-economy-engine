from __future__ import annotations

import sys
import unittest

from baen_economy.mesa_runtime import (
    MESA_COMMIT,
    MESA_VERSION,
    MesaProductEvent,
    MesaRuntimeUnavailable,
    mesa_available,
    run_mesa_preview,
)


class MesaProductRuntimeTests(unittest.TestCase):
    def test_exact_upstream_pin_is_visible(self):
        self.assertEqual(MESA_COMMIT, "20841b12559ef920dd4c8263a09fe75ceac7250c")
        self.assertEqual(MESA_VERSION, "4.0.0a0")

    def test_product_runtime_or_explicit_unavailable_boundary(self):
        events = (
            MesaProductEvent(1, "LOW", "low", {"kind": "audit"}),
            MesaProductEvent(1, "DEFAULT", "default", {"kind": "trade"}),
            MesaProductEvent(1, "HIGH", "high", {"kind": "need"}),
            MesaProductEvent(2, "DEFAULT", "later", {"kind": "delivery"}),
        )
        if sys.version_info < (3, 12):
            # The inspected Mesa revision itself requires >=3.12.  Python 3.11
            # remains a supported Baen base runtime rather than silently using a
            # home-grown substitute under the Mesa name.
            if not mesa_available():
                with self.assertRaises(MesaRuntimeUnavailable):
                    run_mesa_preview(events, until_tick=2, seed=17)
                return
        self.assertTrue(mesa_available(), "Python 3.12 CI must install the pinned Mesa product")
        result = run_mesa_preview(events, until_tick=2, seed=17)
        self.assertEqual(result.upstream, "Mesa")
        self.assertEqual(result.upstream_commit, MESA_COMMIT)
        self.assertEqual(result.upstream_version, MESA_VERSION)
        self.assertEqual(result.final_time, 2)
        self.assertFalse(result.canonical_time_advanced)
        # Mesa's own priority queue executes HIGH before DEFAULT before LOW.
        self.assertEqual(
            [event["event_id"] for event in result.executed_events],
            ["high", "default", "low", "later"],
        )
        # Mesa DataCollector records the state after each actual event callback.
        self.assertEqual(result.collected_event_counts, (1, 2, 3, 4))

    def test_duplicate_ids_are_rejected_before_product_mutation(self):
        duplicate = (
            MesaProductEvent(1, "DEFAULT", "same", {}),
            MesaProductEvent(2, "DEFAULT", "same", {}),
        )
        with self.assertRaisesRegex(ValueError, "duplicate Mesa event_id"):
            run_mesa_preview(duplicate, until_tick=2)

    def test_event_outside_preview_horizon_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "beyond requested preview horizon"):
            run_mesa_preview(
                (MesaProductEvent(3, "DEFAULT", "future", {}),),
                until_tick=2,
            )


if __name__ == "__main__":
    unittest.main()
