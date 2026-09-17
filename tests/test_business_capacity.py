from dataclasses import FrozenInstanceError
from decimal import Decimal
import hashlib
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.business_capacity import (  # noqa: E402
    BRICKWORKS_CAPACITY_PER_MONTH,
    BRICKWORKS_SOURCE_RECORD_ID,
    CAPACITY_BLOCKERS,
    CLAY_QUARRY_CAPACITY_PER_MONTH,
    CLAY_QUARRY_SOURCE_RECORD_ID,
    CapacityProfileError,
    build_brickworks_partial_capacity,
)
from baen_economy.operator_codec import canonical_hash  # noqa: E402


def digest(label):
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class RegistrySnapshotStub:
    def __init__(self):
        self.snapshot_hash = digest("snapshot")
        self.rows = {
            BRICKWORKS_SOURCE_RECORD_ID: {
                "Date Operational": "Ches 1494",
                "Employees": "30",
                "Entity": "Baen Brickworks",
                "Last Updated": "Eleint 20, 1494",
                "Monthly Cost": "2233",
                "Monthly Revenue": "3333",
                "Notes": "75k bricks/month. Fed by Neverwinter Clay Quarries.",
                "Parent Entity": "—",
                "Status": "Operational",
            },
            CLAY_QUARRY_SOURCE_RECORD_ID: {
                "Date Operational": "Ches 1494",
                "Employees": "12",
                "Entity": "Neverwinter Clay Quarries",
                "Last Updated": "Eleint 20, 1494",
                "Monthly Cost": "1500",
                "Monthly Revenue": "0",
                "Notes": "2k tons/mo. Internal transfer.",
                "Parent Entity": "Feeds Brickworks",
                "Status": "Operational",
            },
        }
        self.row_hashes = {
            source_id: canonical_hash(row) for source_id, row in self.rows.items()
        }

    def row(self, source_record_id):
        return self.rows[source_record_id]

    def property_hash(self, source_record_id, property_name):
        return canonical_hash(
            {
                "snapshot_hash": self.snapshot_hash,
                "source_record_id": source_record_id,
                "row_hash": self.row_hashes[source_record_id],
                "property_name": property_name,
                "source_value": self.rows[source_record_id][property_name],
            }
        )


class BusinessCapacityTests(unittest.TestCase):
    def test_profile_binds_exact_source_capacities_and_hash_receipts(self):
        snapshot = RegistrySnapshotStub()
        profile = build_brickworks_partial_capacity(snapshot)

        self.assertEqual(profile.snapshot_hash, snapshot.snapshot_hash)
        self.assertEqual(
            profile.brickworks.source.source_record_id,
            BRICKWORKS_SOURCE_RECORD_ID,
        )
        self.assertEqual(
            profile.clay_quarry.source.source_record_id,
            CLAY_QUARRY_SOURCE_RECORD_ID,
        )
        self.assertEqual(
            profile.brickworks.capacity_per_month,
            BRICKWORKS_CAPACITY_PER_MONTH,
        )
        self.assertEqual(
            profile.clay_quarry.capacity_per_month,
            CLAY_QUARRY_CAPACITY_PER_MONTH,
        )
        self.assertEqual(BRICKWORKS_CAPACITY_PER_MONTH, Decimal("75000"))
        self.assertEqual(CLAY_QUARRY_CAPACITY_PER_MONTH, Decimal("2000"))
        self.assertEqual(
            profile.brickworks.source.row_hash,
            snapshot.row_hashes[BRICKWORKS_SOURCE_RECORD_ID],
        )
        self.assertEqual(
            profile.clay_quarry.source.property_hash("Notes"),
            snapshot.property_hash(CLAY_QUARRY_SOURCE_RECORD_ID, "Notes"),
        )

    def test_profile_is_explicitly_non_executing_and_unknowns_are_null(self):
        profile = build_brickworks_partial_capacity(RegistrySnapshotStub())
        payload = profile.to_dict()

        self.assertEqual(payload["mode"], "partial_capacity_only")
        self.assertEqual(
            payload["capacity_claims"]["brickworks"]["capacity_per_month"],
            "75000",
        )
        self.assertEqual(
            payload["capacity_claims"]["clay_quarry"]["capacity_per_month"],
            "2000",
        )
        self.assertTrue(all(value is None for value in payload["unknowns"].values()))
        self.assertIsNone(
            payload["capacity_claims"]["brickworks"]["realized_quantity"]
        )
        self.assertIsNone(
            payload["capacity_claims"]["clay_quarry"]["realized_quantity"]
        )
        self.assertEqual(
            payload["claims"],
            {
                "actual_production": False,
                "conservation": False,
                "execution_authorized": False,
            },
        )
        expected_codes = {
            "missing_clay_to_brick_ratio",
            "missing_opening_inventory",
            "unresolved_cost_consolidation",
            "unruled_surface_economy_date",
        }
        self.assertEqual(
            {blocker["code"] for blocker in payload["blockers"]}, expected_codes
        )
        self.assertEqual(tuple(CAPACITY_BLOCKERS), profile.blockers)
        body = dict(payload)
        supplied_hash = body.pop("profile_hash")
        self.assertEqual(supplied_hash, canonical_hash(body))

    def test_capacity_notes_or_source_identity_cannot_drift(self):
        snapshot = RegistrySnapshotStub()
        snapshot.rows[BRICKWORKS_SOURCE_RECORD_ID]["Notes"] = "75k-ish"
        with self.assertRaisesRegex(CapacityProfileError, "Notes have drifted"):
            build_brickworks_partial_capacity(snapshot)

        snapshot = RegistrySnapshotStub()
        snapshot.rows[CLAY_QUARRY_SOURCE_RECORD_ID]["Entity"] = "Another Quarry"
        with self.assertRaisesRegex(CapacityProfileError, "identity"):
            build_brickworks_partial_capacity(snapshot)

    def test_missing_or_malformed_hash_receipts_fail_closed(self):
        snapshot = RegistrySnapshotStub()
        del snapshot.row_hashes[BRICKWORKS_SOURCE_RECORD_ID]
        with self.assertRaisesRegex(CapacityProfileError, "no supplied row hash"):
            build_brickworks_partial_capacity(snapshot)

        snapshot = RegistrySnapshotStub()
        snapshot.snapshot_hash = "short"
        with self.assertRaisesRegex(CapacityProfileError, "snapshot hash"):
            build_brickworks_partial_capacity(snapshot)

        snapshot = RegistrySnapshotStub()
        snapshot.property_hash = lambda source_id, name: "0" * 63
        with self.assertRaisesRegex(CapacityProfileError, "property hash"):
            build_brickworks_partial_capacity(snapshot)

    def test_profile_and_source_bindings_are_immutable(self):
        profile = build_brickworks_partial_capacity(RegistrySnapshotStub())
        with self.assertRaises(FrozenInstanceError):
            profile.realized_brick_production = Decimal("1")
        with self.assertRaises(FrozenInstanceError):
            profile.brickworks.capacity_per_month = Decimal("1")


if __name__ == "__main__":
    unittest.main()
