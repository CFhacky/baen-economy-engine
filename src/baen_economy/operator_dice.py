"""Auditable dice receipts for operator previews."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from .operator_codec import canonical_hash


DICE_SCHEMA = "tnp.economy.dice-manifest/1"


def roll_preview_checks(
    *,
    campaign_id: str,
    timeline_id: str,
    period_index: int,
    seed: str | None,
) -> dict[str, object]:
    """Roll two visibly non-binding management checks.

    The results are binding only to the saved preview artifact.  They do not
    resolve Operation Laden Table's seven campaign execution rolls and do not
    change stock flow, finance, or campaign canon.
    """

    if seed is not None and not seed:
        raise ValueError("seed cannot be empty")
    method = "hmac_sha256_seeded_preview" if seed is not None else "system_secure_random"
    seed_fingerprint = (
        hashlib.sha256(seed.encode("utf-8")).hexdigest() if seed is not None else None
    )
    rolls = [
        _three_d6_check(
            roll_key="vara_administration",
            label="Vara administration overview",
            base_target=16,
            target_authority="hybrid-business-ops profile; not the Laden source",
            modifiers=[],
            campaign_id=campaign_id,
            timeline_id=timeline_id,
            period_index=period_index,
            seed=seed,
            method=method,
            seed_fingerprint=seed_fingerprint,
        ),
        _three_d6_check(
            roll_key="vara_merchant",
            label="Vara merchant overview",
            base_target=15,
            target_authority="hybrid-business-ops profile; not the Laden source",
            modifiers=[],
            campaign_id=campaign_id,
            timeline_id=timeline_id,
            period_index=period_index,
            seed=seed,
            method=method,
            seed_fingerprint=seed_fingerprint,
        ),
    ]
    body: dict[str, object] = {
        "schema": DICE_SCHEMA,
        "authority": "illustrative_preview_only",
        "binding_scope": "this persisted preview artifact only",
        "campaign_execution_rolls_resolved": 0,
        "method": method,
        "seed_fingerprint": seed_fingerprint,
        "rolls": rolls,
        "warning": (
            "These checks are not the seven binding Operation Laden Table rolls and "
            "have no effect on stock, money, or campaign canon."
        ),
    }
    body["manifest_hash"] = canonical_hash(body)
    validate_roll_manifest(body)
    return body


def empty_roll_manifest() -> dict[str, object]:
    body: dict[str, object] = {
        "schema": DICE_SCHEMA,
        "authority": "none",
        "binding_scope": "none",
        "campaign_execution_rolls_resolved": 0,
        "method": "none",
        "seed_fingerprint": None,
        "rolls": [],
        "warning": "No dice were rolled; all seven binding execution rolls remain pending.",
    }
    body["manifest_hash"] = canonical_hash(body)
    validate_roll_manifest(body)
    return body


def validate_roll_manifest(manifest: object) -> None:
    """Fail closed unless every stored die and derived field is self-consistent."""

    if not isinstance(manifest, dict):
        raise ValueError("dice manifest must be a concrete object")
    expected_manifest_keys = {
        "schema",
        "authority",
        "binding_scope",
        "campaign_execution_rolls_resolved",
        "method",
        "seed_fingerprint",
        "rolls",
        "warning",
        "manifest_hash",
    }
    if set(manifest) != expected_manifest_keys:
        raise ValueError("dice manifest keys do not match the receipt schema")
    supplied_hash = manifest["manifest_hash"]
    body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if supplied_hash != canonical_hash(body):
        raise ValueError("dice manifest hash does not match")
    if manifest["schema"] != DICE_SCHEMA:
        raise ValueError("dice manifest schema is unsupported")
    if (
        type(manifest["campaign_execution_rolls_resolved"]) is not int
        or manifest["campaign_execution_rolls_resolved"] != 0
    ):
        raise ValueError("preview dice cannot resolve campaign execution rolls")
    rolls = manifest["rolls"]
    if not isinstance(rolls, list):
        raise ValueError("dice manifest rolls must be an array")
    method = manifest["method"]
    fingerprint = manifest["seed_fingerprint"]
    if not rolls:
        if (
            manifest["authority"] != "none"
            or manifest["binding_scope"] != "none"
            or method != "none"
            or fingerprint is not None
        ):
            raise ValueError("empty dice manifest has inconsistent authority or method")
        return
    if (
        manifest["authority"] != "illustrative_preview_only"
        or manifest["binding_scope"] != "this persisted preview artifact only"
        or not isinstance(method, str)
        or method not in {"hmac_sha256_seeded_preview", "system_secure_random"}
    ):
        raise ValueError("preview dice manifest has inconsistent authority or method")
    if method == "hmac_sha256_seeded_preview":
        if not _is_sha256(fingerprint):
            raise ValueError("seeded dice require a full seed fingerprint")
    elif fingerprint is not None:
        raise ValueError("secure random dice cannot claim a seed fingerprint")

    expected_rolls = {
        "vara_administration": ("Vara administration overview", 16),
        "vara_merchant": ("Vara merchant overview", 15),
    }
    if len(rolls) != len(expected_rolls):
        raise ValueError("preview dice receipt must contain exactly two management checks")
    seen: set[str] = set()
    expected_roll_keys = {
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
        if not isinstance(roll, dict) or set(roll) != expected_roll_keys:
            raise ValueError("dice roll keys do not match the receipt schema")
        roll_key = roll["roll_key"]
        if not isinstance(roll_key, str) or roll_key not in expected_rolls or roll_key in seen:
            raise ValueError("dice manifest has an unknown or duplicate roll key")
        seen.add(roll_key)
        expected_label, expected_target = expected_rolls[roll_key]
        if (
            roll["label"] != expected_label
            or type(roll["base_target"]) is not int
            or roll["base_target"] != expected_target
            or roll["target_authority"]
            != "hybrid-business-ops profile; not the Laden source"
        ):
            raise ValueError("dice roll target or authority is inconsistent")
        faces = roll["dice"]
        if (
            not isinstance(faces, list)
            or len(faces) != 3
            or any(type(face) is not int or not 1 <= face <= 6 for face in faces)
        ):
            raise ValueError("3d6 receipt must contain exactly three faces from 1 through 6")
        modifiers = roll["modifiers"]
        if not isinstance(modifiers, list):
            raise ValueError("dice modifiers must be an array")
        modifier_total = 0
        for modifier in modifiers:
            if (
                not isinstance(modifier, dict)
                or set(modifier) != {"label", "value"}
                or not isinstance(modifier["label"], str)
                or not modifier["label"].strip()
                or type(modifier["value"]) is not int
            ):
                raise ValueError("dice modifier receipt is malformed")
            modifier_total += modifier["value"]
        total = sum(faces)
        effective_target = expected_target + modifier_total
        margin = effective_target - total
        if (
            type(roll["total"]) is not int
            or roll["total"] != total
            or type(roll["modifier_total"]) is not int
            or roll["modifier_total"] != modifier_total
            or type(roll["effective_target"]) is not int
            or roll["effective_target"] != effective_target
            or type(roll["margin"]) is not int
            or roll["margin"] != margin
            or roll["outcome"]
            != classify_3d6(total=total, effective_target=effective_target)
        ):
            raise ValueError("dice roll total, margin, or outcome is inconsistent")
        if (
            roll["method"] != method
            or roll["seed_fingerprint"] != fingerprint
            or roll["effect"] != "informational only; no state or financial effect"
        ):
            raise ValueError("dice roll method, fingerprint, or effect is inconsistent")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _three_d6_check(
    *,
    roll_key: str,
    label: str,
    base_target: int,
    target_authority: str,
    modifiers: list[dict[str, object]],
    campaign_id: str,
    timeline_id: str,
    period_index: int,
    seed: str | None,
    method: str,
    seed_fingerprint: str | None,
) -> dict[str, object]:
    faces = [
        _die(
            sides=6,
            seed=seed,
            coordinate=(campaign_id, timeline_id, str(period_index), roll_key, str(index)),
        )
        for index in range(1, 4)
    ]
    modifier_total = sum(int(item["value"]) for item in modifiers)
    effective_target = base_target + modifier_total
    total = sum(faces)
    margin = effective_target - total
    outcome = classify_3d6(total=total, effective_target=effective_target)
    return {
        "roll_key": roll_key,
        "label": label,
        "dice": faces,
        "total": total,
        "base_target": base_target,
        "target_authority": target_authority,
        "modifiers": modifiers,
        "modifier_total": modifier_total,
        "effective_target": effective_target,
        "margin": margin,
        "outcome": outcome,
        "method": method,
        "seed_fingerprint": seed_fingerprint,
        "effect": "informational only; no state or financial effect",
    }


def classify_3d6(*, total: int, effective_target: int) -> str:
    """Classify a GURPS 3d6 result, including skill-dependent criticals."""

    if type(total) is not int or not 3 <= total <= 18:
        raise ValueError("3d6 total must be an integer from 3 through 18")
    if type(effective_target) is not int:
        raise ValueError("effective target must be an integer")
    margin = effective_target - total
    if total <= 4 or (total == 5 and effective_target >= 15) or (
        total == 6 and effective_target >= 16
    ):
        return "critical_success"
    if total == 18 or (total == 17 and effective_target <= 15) or margin <= -10:
        return "critical_failure"
    # A natural 17 is never a success, even at effective skill 17+.
    if total == 17:
        return "failure"
    if margin >= 5:
        return "success_by_5_plus"
    if margin > 0:
        return "success"
    if margin == 0:
        return "exact_target"
    if margin <= -5:
        return "failure_by_5_plus"
    return "failure"


def _die(*, sides: int, seed: str | None, coordinate: tuple[str, ...]) -> int:
    if type(sides) is not int or sides < 2:
        raise ValueError("die must have at least two sides")
    if seed is None:
        return secrets.randbelow(sides) + 1
    # Rejection sampling avoids modulo bias and is stable across Python versions.
    modulus = 1 << 64
    limit = modulus - (modulus % sides)
    message = "\x1f".join(coordinate).encode("utf-8")
    key = hashlib.sha256(seed.encode("utf-8")).digest()
    attempt = 0
    while True:
        digest = hmac.new(
            key,
            message + b"\x1f" + str(attempt).encode("ascii"),
            hashlib.sha256,
        ).digest()
        sample = int.from_bytes(digest[:8], "big")
        if sample < limit:
            return (sample % sides) + 1
        attempt += 1
