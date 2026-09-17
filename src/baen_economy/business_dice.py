"""Auditable 3d6 receipts for non-canonical registry business previews."""

from __future__ import annotations

import hashlib
from typing import Mapping

from .operator_codec import canonical_hash
from .operator_dice import _die, classify_3d6


BUSINESS_DICE_SCHEMA = "tnp.business.dice-manifest/1"


def roll_business_checks(
    *,
    snapshot_hash: str,
    source_record_id: str,
    month_label: str,
    seed: str,
    revenue_modifiers: list[dict[str, object]],
    expense_modifiers: list[dict[str, object]],
) -> dict[str, object]:
    if not isinstance(seed, str) or not seed:
        raise ValueError("business preview seed must be non-empty text")
    method = "hmac_sha256_seeded_preview"
    fingerprint = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    rolls = [
        _roll(
            roll_key="revenue",
            label="Sector revenue check",
            base_target=15,
            target_authority="hybrid-business-ops Merchant-15 sector revenue table",
            modifiers=revenue_modifiers,
            snapshot_hash=snapshot_hash,
            source_record_id=source_record_id,
            month_label=month_label,
            sampling_key=fingerprint,
            method=method,
            fingerprint=fingerprint,
        ),
        _roll(
            roll_key="expense",
            label="Entity expense-control check",
            base_target=16,
            target_authority="hybrid-business-ops Administration-16 expense table",
            modifiers=expense_modifiers,
            snapshot_hash=snapshot_hash,
            source_record_id=source_record_id,
            month_label=month_label,
            sampling_key=fingerprint,
            method=method,
            fingerprint=fingerprint,
        ),
    ]
    body: dict[str, object] = {
        "schema": BUSINESS_DICE_SCHEMA,
        "authority": "scenario_assumption",
        "binding_scope": "this persisted non-canonical registry preview only",
        "campaign_state_rolls_resolved": 0,
        "method": method,
        "seed_fingerprint": fingerprint,
        "rolls": rolls,
        "warning": (
            "These rolls determine only this preview. They do not advance campaign canon, "
            "alter the Business Registry, or authorize ledger postings."
        ),
    }
    body["manifest_hash"] = canonical_hash(body)
    validate_business_manifest(
        body,
        revenue_modifiers=revenue_modifiers,
        expense_modifiers=expense_modifiers,
        snapshot_hash=snapshot_hash,
        source_record_id=source_record_id,
        month_label=month_label,
    )
    return body


def validate_business_manifest(
    manifest: object,
    *,
    revenue_modifiers: list[dict[str, object]],
    expense_modifiers: list[dict[str, object]],
    snapshot_hash: str | None = None,
    source_record_id: str | None = None,
    month_label: str | None = None,
) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("business dice manifest must be a concrete object")
    expected_keys = {
        "schema",
        "authority",
        "binding_scope",
        "campaign_state_rolls_resolved",
        "method",
        "seed_fingerprint",
        "rolls",
        "warning",
        "manifest_hash",
    }
    if set(manifest) != expected_keys:
        raise ValueError("business dice manifest keys do not match the schema")
    supplied_hash = manifest["manifest_hash"]
    body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if supplied_hash != canonical_hash(body):
        raise ValueError("business dice manifest hash does not match")
    if (
        manifest["schema"] != BUSINESS_DICE_SCHEMA
        or manifest["authority"] != "scenario_assumption"
        or manifest["binding_scope"]
        != "this persisted non-canonical registry preview only"
        or type(manifest["campaign_state_rolls_resolved"]) is not int
        or manifest["campaign_state_rolls_resolved"] != 0
    ):
        raise ValueError("business dice authority receipt is inconsistent")
    method = manifest["method"]
    fingerprint = manifest["seed_fingerprint"]
    if method != "hmac_sha256_seeded_preview":
        raise ValueError("business dice method is unsupported")
    if not _is_sha256(fingerprint):
        raise ValueError("seeded business dice require a full fingerprint")
    rolls = manifest["rolls"]
    if not isinstance(rolls, list) or len(rolls) != 2:
        raise ValueError("business dice receipt must contain exactly two checks")
    if [
        roll.get("roll_key") if isinstance(roll, dict) else None for roll in rolls
    ] != ["revenue", "expense"]:
        raise ValueError("business dice checks are not in their canonical order")
    expected = {
        "revenue": (
            "Sector revenue check",
            15,
            "hybrid-business-ops Merchant-15 sector revenue table",
            revenue_modifiers,
        ),
        "expense": (
            "Entity expense-control check",
            16,
            "hybrid-business-ops Administration-16 expense table",
            expense_modifiers,
        ),
    }
    seen: set[str] = set()
    roll_keys = {
        "roll_key",
        "label",
        "dice",
        "total",
        "base_target",
        "target_authority",
        "modifiers",
        "modifier_total",
        "effective_target",
        "margin",
        "outcome",
        "method",
        "seed_fingerprint",
        "effect",
    }
    for roll in rolls:
        if not isinstance(roll, dict) or set(roll) != roll_keys:
            raise ValueError("business dice roll keys do not match the schema")
        key = roll["roll_key"]
        if not isinstance(key, str) or key not in expected or key in seen:
            raise ValueError("business dice has an unknown or duplicate roll")
        seen.add(key)
        label, base_target, authority, modifiers = expected[key]
        if (
            roll["label"] != label
            or roll["base_target"] != base_target
            or roll["target_authority"] != authority
            or roll["modifiers"] != modifiers
        ):
            raise ValueError("business dice target, authority, or modifiers drifted")
        _validate_modifiers(modifiers)
        faces = roll["dice"]
        if (
            not isinstance(faces, list)
            or len(faces) != 3
            or any(type(face) is not int or not 1 <= face <= 6 for face in faces)
        ):
            raise ValueError("business 3d6 receipt must contain three valid faces")
        total = sum(faces)
        modifier_total = sum(item["value"] for item in modifiers)
        target = base_target + modifier_total
        margin = target - total
        if (
            any(
                type(roll[name]) is not int
                for name in (
                    "total",
                    "base_target",
                    "modifier_total",
                    "effective_target",
                    "margin",
                )
            )
            or roll["total"] != total
            or roll["modifier_total"] != modifier_total
            or roll["effective_target"] != target
            or roll["margin"] != margin
            or roll["outcome"] != classify_3d6(total=total, effective_target=target)
            or roll["method"] != method
            or roll["seed_fingerprint"] != fingerprint
            or roll["effect"] != "drives only the stored non-canonical preview"
        ):
            raise ValueError("business dice arithmetic or effect is inconsistent")
        binding_parts = (snapshot_hash, source_record_id, month_label)
        if any(item is not None for item in binding_parts):
            if not all(isinstance(item, str) and item for item in binding_parts):
                raise ValueError("business dice replay binding must be complete")
            if method != "hmac_sha256_seeded_preview" or not isinstance(
                fingerprint, str
            ):
                raise ValueError("source-bound business dice must be deterministically seeded")
            replay_faces = [
                _die(
                    sides=6,
                    seed=fingerprint,
                    coordinate=(
                        "business-month",
                        str(snapshot_hash),
                        str(source_record_id),
                        str(month_label),
                        key,
                        str(index),
                    ),
                )
                for index in range(1, 4)
            ]
            if faces != replay_faces:
                raise ValueError("business dice faces do not match their source binding")


def _roll(
    *,
    roll_key: str,
    label: str,
    base_target: int,
    target_authority: str,
    modifiers: list[dict[str, object]],
    snapshot_hash: str,
    source_record_id: str,
    month_label: str,
    sampling_key: str | None,
    method: str,
    fingerprint: str | None,
) -> dict[str, object]:
    _validate_modifiers(modifiers)
    faces = [
        _die(
            sides=6,
            seed=sampling_key,
            coordinate=(
                "business-month",
                snapshot_hash,
                source_record_id,
                month_label,
                roll_key,
                str(index),
            ),
        )
        for index in range(1, 4)
    ]
    modifier_total = sum(item["value"] for item in modifiers)
    total = sum(faces)
    target = base_target + modifier_total
    return {
        "roll_key": roll_key,
        "label": label,
        "dice": faces,
        "total": total,
        "base_target": base_target,
        "target_authority": target_authority,
        "modifiers": modifiers,
        "modifier_total": modifier_total,
        "effective_target": target,
        "margin": target - total,
        "outcome": classify_3d6(total=total, effective_target=target),
        "method": method,
        "seed_fingerprint": fingerprint,
        "effect": "drives only the stored non-canonical preview",
    }


def _validate_modifiers(modifiers: object) -> None:
    if not isinstance(modifiers, list):
        raise ValueError("business dice modifiers must be an array")
    for modifier in modifiers:
        if (
            not isinstance(modifier, dict)
            or set(modifier) != {"label", "value"}
            or not isinstance(modifier["label"], str)
            or not modifier["label"].strip()
            or type(modifier["value"]) is not int
        ):
            raise ValueError("business dice modifier is malformed")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
