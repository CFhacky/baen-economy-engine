from decimal import Decimal, getcontext, setcontext
from dataclasses import replace
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.domain import Authority, TemporalState  # noqa: E402
from baen_economy.events import (  # noqa: E402
    CampaignDate, EventEnvelope, EventPhase, EventStore, ResolutionStatus,
    canonical_json,
)


def event(**overrides):
    values = {
        "source_event_key": "fixture:harvest",
        "event_revision": 1,
        "timeline_id": "actual",
        "model_version": "0.1",
        "campaign_date": CampaignDate(1, "Synthetic 1"),
        "phase": "production",
        "sequence": 1,
        "authority": Authority.CAMPAIGN_RESOLUTION,
        "temporal_state": TemporalState.CURRENT,
        "resolution_status": ResolutionStatus.RESOLVED,
        "source_ref": "fixture:source",
        "event_type": "stock.produced",
        "payload": {"quantity": Decimal("10"), "commodity": "grain"},
    }
    values.update(overrides)
    return EventEnvelope.create(**values)


class EventTests(unittest.TestCase):
    def test_json_key_order_does_not_change_hash_or_id(self):
        first = event(payload={"quantity": Decimal("10"), "commodity": "grain"})
        second = event(payload={"commodity": "grain", "quantity": Decimal("10")})
        self.assertEqual(first.payload_hash, second.payload_hash)
        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(canonical_json({"b": 2, "a": 1}), '{"a":1,"b":2}')

    def test_decimal_event_serialization_ignores_ambient_capitals(self):
        original = getcontext().copy()
        try:
            getcontext().capitals = 0
            lower_context = event(payload={"quantity": Decimal("1E+20")})
            getcontext().capitals = 1
            upper_context = event(payload={"quantity": Decimal("1E+20")})
        finally:
            setcontext(original)
        self.assertEqual(lower_context.payload_json, upper_context.payload_json)
        self.assertEqual(lower_context.payload_hash, upper_context.payload_hash)
        self.assertEqual(lower_context.integrity_hash, upper_context.integrity_hash)
        self.assertIn("1E+20", lower_context.payload_json)

    def test_only_resolved_current_actual_event_may_mutate_actual(self):
        self.assertTrue(event().may_mutate_actual)
        self.assertFalse(event(timeline_id="forecast:x").may_mutate_actual)
        self.assertFalse(event(temporal_state=TemporalState.FORWARD_RESOLVED).may_mutate_actual)
        self.assertFalse(event(resolution_status=ResolutionStatus.PENDING).may_mutate_actual)
        self.assertFalse(event(authority=Authority.SCENARIO_ASSUMPTION).may_mutate_actual)

    def test_unknown_phase_is_rejected_and_known_phases_sort_by_rank(self):
        with self.assertRaisesRegex(ValueError, "unknown event phase"):
            event(phase="anything")
        store = EventStore()
        store.append(event(source_event_key="fixture:finance", phase=EventPhase.FINANCE, sequence=1))
        store.append(event(source_event_key="fixture:arrival", phase=EventPhase.ARRIVAL, sequence=2))
        self.assertEqual([item.phase for item in store.events], ["arrival", "finance"])

    def test_duplicate_event_is_rejected(self):
        store = EventStore()
        first = event()
        store.append(first)
        with self.assertRaisesRegex(ValueError, "duplicate event"):
            store.append(first)

    def test_duck_typed_event_cannot_enter_store(self):
        fake = type(
            "FakeEvent",
            (),
            {
                "event_id": "event:fake",
                "timeline_id": "actual",
                "model_version": "economy-0.1",
                "source_event_key": "fake",
                "event_revision": 1,
                "reverses_event_id": None,
                "validate_integrity": lambda self: None,
            },
        )()
        with self.assertRaisesRegex(ValueError, "concrete EventEnvelope"):
            EventStore().append(fake)

    def test_changed_payload_under_same_source_revision_is_rejected(self):
        store = EventStore()
        store.append(event())
        changed = event(payload={"quantity": Decimal("11"), "commodity": "grain"})
        with self.assertRaisesRegex(ValueError, "collision"):
            store.append(changed)

    def test_correction_requires_explicit_reversal(self):
        store = EventStore()
        first = event()
        store.append(first)
        with self.assertRaisesRegex(ValueError, "reverse"):
            store.append(event(event_revision=2, payload={"quantity": Decimal("11")}))
        correction = event(
            event_revision=2,
            payload={"quantity": Decimal("11")},
            reverses_event_id=first.event_id,
        )
        store.append(correction)
        self.assertEqual(len(store.events), 2)
        self.assertFalse(store.contains_active(first))
        self.assertTrue(store.contains_active(correction))
        self.assertFalse(correction.may_mutate_actual)

    def test_unsupported_schema_and_changed_provenance_fail_closed(self):
        original = event()
        for invalid_schema in (999, True, 1.0):
            with self.assertRaisesRegex(ValueError, "schema version"):
                EventStore().append(replace(original, schema_version=invalid_schema))
        changed = event(source_ref="fixture:other", authority=Authority.USER_RULING)
        self.assertEqual(original.event_id, changed.event_id)
        self.assertEqual(original.payload_hash, changed.payload_hash)
        self.assertNotEqual(original.integrity_hash, changed.integrity_hash)

    def test_identity_delimiters_cannot_collide(self):
        first = event(source_event_key="a|1|x", event_type="y")
        second = event(source_event_key="a", event_type="x|1|y")
        self.assertNotEqual(first.event_id, second.event_id)

    def test_control_metadata_and_invalid_campaign_precision_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "control"):
            event(source_event_key="fixture:safe\n  injected")
        with self.assertRaisesRegex(ValueError, "precision"):
            CampaignDate(1, "Synthetic", precision="day\n  injected")
        with self.assertRaisesRegex(ValueError, "precision"):
            CampaignDate(1, "Synthetic", precision=1)

    def test_revision_lineage_cannot_cross_timelines(self):
        store = EventStore()
        original = event()
        store.append(original)
        cross_timeline = event(
            event_revision=2,
            timeline_id="forecast:other",
            reverses_event_id=original.event_id,
        )
        with self.assertRaisesRegex(ValueError, "preceding"):
            store.append(cross_timeline)

    def test_nonauthoritative_revision_cannot_reverse_actual_history(self):
        original = event(source_event_key="fixture:authority-revision")
        store = EventStore()
        store.append(original)
        correction = event(
            source_event_key="fixture:authority-revision",
            event_revision=2,
            reverses_event_id=original.event_id,
            authority=Authority.SCENARIO_ASSUMPTION,
            temporal_state=TemporalState.PROJECTED,
            resolution_status=ResolutionStatus.PENDING,
        )
        with self.assertRaisesRegex(ValueError, "current, resolved, and authoritative"):
            store.append(correction)
        self.assertTrue(store.contains_active(original))


if __name__ == "__main__":
    unittest.main()
