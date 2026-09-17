"""Deterministic, source-bound medieval regional-economy vertical slice.

This module is intentionally standalone (Python 3.11 stdlib only).  It accepts
JSON-shaped mappings, rejects binary floats, performs all arithmetic with
``Decimal``, and returns JSON-safe exact decimal strings.

Public API
==========

``load_scenario(path)``
    Load and validate a scenario JSON document.
``initial_state(scenario)``
    Build the hash-sealed month-zero state from the scenario's source-bound
    opening records.
``run_month(scenario, state, seed)``
    Resolve one non-canonical month and return ``{"result", "next_state"}``.
``canonical_json(value)`` / ``state_hash(value)``
    Stable persistence and replay helpers.
``render_report(result)``
    Render the causal events, checks, and available decisions as Markdown.

The scenario contract is documented by :func:`validate_scenario`.  This is a
mechanical vertical slice, never permission to write campaign canon or Notion.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


STATE_SCHEMA = "baen.whole-economy-state/1"
RESULT_SCHEMA = "baen.whole-economy-month/1"
SCENARIO_SCHEMA = "baen.whole-economy-scenario/1"
PLAYED_CONTEXT_SCHEMA = "baen.played-canonical-context/1"
ZERO = Decimal("0")
ONE = Decimal("1")
DAYS_PER_MONTH = Decimal("20")
MONEY = Decimal("0.01")
CONSERVATION_TOLERANCE = Decimal("1e-24")
SHOCK_TYPES = {
    "weather",
    "harvest",
    "war",
    "monster",
    "political",
    "infrastructure",
    "policy",
}


class EconomyError(ValueError):
    """Raised when a scenario/state is ambiguous or violates conservation."""


def _context() -> Context:
    return Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _decimal(value: object, label: str, *, minimum: Decimal | None = ZERO) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise EconomyError(f"{label} must use exact decimal text, Decimal, or integer")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str) and value and value == value.strip():
        try:
            result = Decimal(value)
        except Exception as exc:
            raise EconomyError(f"{label} is not exact decimal text") from exc
    else:
        raise EconomyError(f"{label} must use exact decimal text, Decimal, or integer")
    if not result.is_finite():
        raise EconomyError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise EconomyError(f"{label} cannot be below {minimum}")
    return result


def _available_quantity(inventory: Mapping[str, object], label: str) -> Decimal:
    """Return unpledged stock available to promise.

    This is the whole-economy use of the project's Brunnfeld Agentic World
    available-to-promise adaptation: ``max(0, on_hand - reserved)``.  The
    upstream method is MIT licensed and pinned in ``docs/THIRD_PARTY_SOURCES.md``;
    its full notice is retained in ``THIRD_PARTY_NOTICES.md``.  Here,
    ``pledged_quantity`` is the reservation field, so pledged collateral cannot
    also be consumed, used as a recipe input, sold locally, or dispatched.
    """

    quantity = _decimal(inventory.get("quantity"), f"{label} quantity")
    pledged = _decimal(
        inventory.get("pledged_quantity", ZERO), f"{label} pledged quantity"
    )
    if pledged > quantity:
        raise EconomyError(f"{label} pledges exceed on-hand quantity")
    return max(ZERO, quantity - pledged)


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    number = _decimal(value, label, minimum=Decimal(minimum))
    if number != number.to_integral_value():
        raise EconomyError(f"{label} must be an integer")
    return int(number)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EconomyError(f"{label} must be non-empty trimmed text")
    return value


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise EconomyError(f"{label} must be an object with text keys")
    return value


def _records(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(v, Mapping) for v in value):
        raise EconomyError(f"{label} must be a JSON array of objects")
    return list(value)


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise EconomyError("non-finite Decimal cannot be serialized")
    if value == ZERO:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, float):
        raise EconomyError("binary floating-point values are forbidden")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise EconomyError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Return stable compact JSON with every Decimal encoded as exact text."""

    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def state_hash(value: object) -> str:
    """Hash a value, excluding a top-level self-referential hash field."""

    body = value
    if isinstance(value, Mapping):
        schema = value.get("schema")
        self_field = (
            "state_hash"
            if schema == STATE_SCHEMA
            else "result_hash"
            if schema == RESULT_SCHEMA
            else None
        )
        body = {
            key: item
            for key, item in value.items()
            if self_field is None or key != self_field
        }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _sample(seed: str, coordinate: str) -> Decimal:
    digest = hashlib.sha256(f"{seed}\0{coordinate}".encode("utf-8")).digest()
    numerator = Decimal(int.from_bytes(digest, "big"))
    return numerator / Decimal(1 << (8 * len(digest)))


def _unique(records: Iterable[Mapping[str, object]], key: str, label: str) -> None:
    values = [_text(item.get(key), f"{label} {key}") for item in records]
    if len(values) != len(set(values)):
        raise EconomyError(f"duplicate {label} {key}")


def _rate(value: object, label: str) -> Decimal:
    result = _decimal(value, label)
    if result > ONE:
        raise EconomyError(f"{label} must be in [0, 1]")
    return result


def load_scenario(path: str | Path) -> dict[str, object]:
    """Load a JSON scenario without allowing binary floating-point values."""

    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=lambda value: (_ for _ in ()).throw(
                EconomyError(f"non-finite JSON number is forbidden: {value}")
            ),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise EconomyError(f"could not load scenario {source}: {exc}") from exc
    scenario = dict(_mapping(payload, "scenario"))
    validate_scenario(scenario)
    return scenario


def load_played_context(path: str | Path) -> dict[str, object]:
    """Load structured played-canon evidence used only to evaluate operation gates.

    The engine never infers arrival from prose.  A campaign integration must
    provide an event explicitly marked both ``canonical`` and ``played`` with
    the structured subject, event type, and location required by the sealed
    operation gate.
    """

    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=lambda value: (_ for _ in ()).throw(
                EconomyError(f"non-finite JSON number is forbidden: {value}")
            ),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise EconomyError(f"could not load played-canon context {source}: {exc}") from exc
    context = dict(_mapping(payload, "played-canon context"))
    validate_played_context(context)
    return context


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EconomyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def validate_played_context(context: Mapping[str, object]) -> None:
    """Validate explicit evidence without treating unplayed text as canon."""

    if context.get("schema") != PLAYED_CONTEXT_SCHEMA:
        raise EconomyError(f"played-canon context schema must be {PLAYED_CONTEXT_SCHEMA}")
    events = _records(context.get("events"), "played-canon events")
    _unique(events, "event_id", "played-canon event")
    for event in events:
        for field in (
            "subject_id",
            "event_type",
            "location_id",
            "source_ref",
            "source_text",
        ):
            _text(event.get(field), f"played-canon event {field}")
        for field in ("canonical", "played"):
            if not isinstance(event.get(field), bool):
                raise EconomyError(f"played-canon event {field} must be boolean")


def surface_pending_operations(
    operations: Sequence[Mapping[str, object]],
    played_context: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    """Return each operation once, and only after its sealed evidence gate matches.

    The returned activation is a read-only view.  It does not execute the
    operation, resolve a fact request, make a decision, advance campaign time,
    or alter the sealed state.  Repeated or duplicate matching evidence cannot
    duplicate an operation because output is keyed by ``operation_id``.
    """

    if played_context is not None:
        validate_played_context(played_context)
        events = _records(played_context.get("events"), "played-canon events")
    else:
        events = []
    surfaced: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw_operation in operations:
        operation = _mapping(raw_operation, "pending operation")
        operation_id = _text(operation.get("operation_id"), "pending operation ID")
        if operation_id in seen:
            continue
        gate = _mapping(operation.get("activation_gate"), "operation activation gate")
        matches = _matching_gate_events(gate, events)
        if matches is None:
            continue
        active = deepcopy(dict(operation))
        active["activation"] = {
            "activation_id": f"activation:{operation_id}",
            "state": "active",
            "policy": gate.get("activation_policy"),
            "matched_event_ids": [event.get("event_id") for event in matches],
            "source_refs": [event.get("source_ref") for event in matches],
            "automatic_execution": False,
            "automatic_resolution": False,
        }
        surfaced.append(active)
        seen.add(operation_id)
    return sorted(surfaced, key=lambda row: str(row.get("operation_id", "")))


def _matching_gate_events(
    gate: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]] | None:
    required = _records(gate.get("required_events"), "operation required events")
    matched: list[Mapping[str, object]] = []
    for requirement in required:
        candidates = [
            event
            for event in events
            if event.get("canonical") is True
            and event.get("played") is True
            and all(
                event.get(field) == requirement.get(field)
                for field in ("subject_id", "event_type", "location_id")
            )
        ]
        if not candidates:
            return None
        matched.append(sorted(candidates, key=lambda row: str(row.get("event_id", "")))[0])
    return matched


def validate_scenario(scenario: Mapping[str, object]) -> None:
    """Validate the whole-economy scenario contract.

    Required top-level fields are ``schema``, ``scenario_id``, ``canonical``
    (which must be false), ``source_refs``, ``settlements``, ``commodities``,
    ``recipes``, ``routes``, ``tenures``, ``shocks``, ``migration_links``,
    ``credit_requests``, ``pending_operations``, and ``opening_state``.

    Settlements contain ``classes`` with population, a household account,
    per-person monthly ``basket``, and optional substitution mappings.  Opening
    state contains account, inventory, labour, bank, loan, price, transit, and
    arrears arrays.  Every invented executable number therefore remains visible
    in the scenario rather than becoming a hidden engine default.
    """

    required = {
        "schema",
        "scenario_id",
        "canonical",
        "source_refs",
        "settlements",
        "commodities",
        "recipes",
        "routes",
        "tenures",
        "shocks",
        "migration_links",
        "credit_requests",
        "pending_operations",
        "opening_state",
    }
    missing = required - set(scenario)
    if missing:
        raise EconomyError(f"scenario missing required fields: {sorted(missing)}")
    if scenario.get("schema") != SCENARIO_SCHEMA:
        raise EconomyError(f"scenario schema must be {SCENARIO_SCHEMA}")
    _text(scenario.get("scenario_id"), "scenario ID")
    if scenario.get("canonical") is not False:
        raise EconomyError("whole-economy vertical slice must be explicitly non-canonical")
    refs = scenario.get("source_refs")
    if not isinstance(refs, list) or not refs or any(not isinstance(v, str) or not v for v in refs):
        raise EconomyError("scenario requires at least one source reference")

    settlements = _records(scenario.get("settlements"), "settlements")
    commodities = _records(scenario.get("commodities"), "commodities")
    recipes = _records(scenario.get("recipes"), "recipes")
    routes = _records(scenario.get("routes"), "routes")
    tenures = _records(scenario.get("tenures"), "tenures")
    _unique(settlements, "id", "settlement")
    _unique(commodities, "id", "commodity")
    _unique(recipes, "id", "recipe")
    _unique(routes, "id", "route")
    _unique(tenures, "id", "tenure")
    settlement_ids = {_text(v.get("id"), "settlement ID") for v in settlements}
    commodity_ids = {_text(v.get("id"), "commodity ID") for v in commodities}
    entity_ids: set[str] = set()

    for settlement in settlements:
        classes = _records(settlement.get("classes"), "settlement classes")
        _unique(classes, "id", "social class")
        for social_class in classes:
            _decimal(social_class.get("population"), "class population")
            entity_ids.add(_text(social_class.get("household_account_id"), "household account"))
            basket = _mapping(social_class.get("basket"), "class consumption basket")
            if not basket:
                raise EconomyError("every social class requires a non-empty basket")
            for commodity_id, quantity in sorted(basket.items()):
                if commodity_id not in commodity_ids:
                    raise EconomyError(f"basket references unknown commodity {commodity_id}")
                _decimal(quantity, "per-person basket quantity")
            substitutions = _mapping(
                social_class.get("substitutions", {}), "class substitutions"
            )
            for primary, choices in sorted(substitutions.items()):
                if primary not in basket or not isinstance(choices, list):
                    raise EconomyError("substitution primary must be in the class basket")
                for choice in choices:
                    item = _mapping(choice, "substitution choice")
                    if item.get("commodity_id") not in commodity_ids:
                        raise EconomyError("substitution references an unknown commodity")
                    if _decimal(item.get("ratio"), "substitution ratio") <= ZERO:
                        raise EconomyError("substitution ratio must be positive")

    for commodity in commodities:
        for field in ("base_price", "min_price", "max_price", "spoilage_rate", "price_elasticity"):
            _decimal(commodity.get(field), f"commodity {field}")
        if _rate(commodity.get("spoilage_rate"), "commodity spoilage rate") >= ONE:
            raise EconomyError("commodity spoilage rate must be below one")

    for recipe in recipes:
        entity_ids.add(_text(recipe.get("entity_id"), "recipe entity"))
        if recipe.get("settlement_id") not in settlement_ids:
            raise EconomyError("recipe references an unknown settlement")
        _text(recipe.get("kind"), "recipe kind")
        _decimal(recipe.get("max_batches"), "recipe maximum batches")
        _decimal(recipe.get("desired_batches"), "recipe desired batches")
        for field in ("inputs", "outputs"):
            amounts = _mapping(recipe.get(field), f"recipe {field}")
            for commodity_id, amount in sorted(amounts.items()):
                if commodity_id not in commodity_ids:
                    raise EconomyError(f"recipe references unknown commodity {commodity_id}")
                _decimal(amount, f"recipe {field} amount")
        labor = _mapping(recipe.get("labor"), "recipe labor")
        for occupation, days in sorted(labor.items()):
            _text(occupation, "recipe occupation")
            _decimal(days, "recipe labor days")

    for route in routes:
        if route.get("origin") not in settlement_ids or route.get("destination") not in settlement_ids:
            raise EconomyError("route references an unknown settlement")
        entity_ids.add(_text(route.get("carrier_id"), "route carrier"))
        entity_ids.add(_text(route.get("toll_recipient_id"), "route toll recipient"))
        allowed = route.get("commodities")
        if not isinstance(allowed, list) or not allowed or any(v not in commodity_ids for v in allowed):
            raise EconomyError("route commodities must be known and non-empty")
        _decimal(route.get("capacity"), "route capacity")
        _integer(route.get("travel_months"), "route travel months")
        if _rate(route.get("spoilage_rate"), "route spoilage rate") >= ONE:
            raise EconomyError("route spoilage rate must be below one")
        _decimal(route.get("carrier_cost_per_unit"), "route carrier cost")
        _decimal(route.get("toll_per_unit"), "route toll")

    for tenure in tenures:
        if tenure.get("settlement_id") not in settlement_ids:
            raise EconomyError("tenure references an unknown settlement")
        for field in ("tenant_id", "landlord_id", "church_id", "treasury_id"):
            entity_ids.add(_text(tenure.get(field), f"tenure {field}"))
        for field in ("acres", "rent_per_acre"):
            _decimal(tenure.get(field), f"tenure {field}")
        for field in ("feudal_due_rate", "tithe_rate", "tax_rate"):
            _rate(tenure.get(field), f"tenure {field}")

    credit_requests = _records(scenario.get("credit_requests"), "credit requests")
    _unique(credit_requests, "loan_id", "credit request")
    requested_bank_ids: set[str] = set()
    for request in credit_requests:
        requested_bank_ids.add(_text(request.get("bank_id"), "credit-request bank"))
        entity_ids.add(_text(request.get("borrower_id"), "credit-request borrower"))
        entity_ids.add(
            _text(
                request.get("collateral_owner_id", request.get("borrower_id")),
                "credit-request collateral owner",
            )
        )

    shocks = _records(scenario.get("shocks"), "shocks")
    _unique(shocks, "id", "shock")
    seen_shock_types: set[str] = set()
    for shock in shocks:
        shock_type = _text(shock.get("type"), "shock type")
        if shock_type not in SHOCK_TYPES:
            raise EconomyError(f"unsupported shock type: {shock_type}")
        seen_shock_types.add(shock_type)
        _rate(shock.get("probability"), "shock probability")
        _mapping(shock.get("effects"), "shock effects")
        if "months" in shock:
            months = shock.get("months")
            if not isinstance(months, list) or not months:
                raise EconomyError("shock months must be a non-empty array of positive integers")
            parsed_months = [
                _integer(value, "shock scheduled month", minimum=1) for value in months
            ]
            if len(parsed_months) != len(set(parsed_months)):
                raise EconomyError("shock months cannot contain duplicates")

    pending_operations = _records(
        scenario.get("pending_operations"), "pending operations"
    )
    _unique(pending_operations, "operation_id", "pending operation")
    for operation in pending_operations:
        for field in (
            "kind",
            "title",
            "status",
            "boot_trigger",
            "play_trigger",
            "current_boundary",
        ):
            _text(operation.get(field), f"pending operation {field}")
        if operation.get("status") != "pending":
            raise EconomyError("bundled campaign operations must begin pending")
        if operation.get("canonical") is not False:
            raise EconomyError("pending operation must remain explicitly non-canonical")
        gate = _mapping(
            operation.get("activation_gate"),
            "pending operation activation gate",
        )
        if gate.get("visibility") != "silent_until_matched":
            raise EconomyError("pending operation must remain silent until its gate matches")
        if gate.get("evidence_authority") != "played_canonical_text":
            raise EconomyError("pending operation requires played canonical text evidence")
        if gate.get("activation_policy") != "once_per_operation_id":
            raise EconomyError("pending operation must activate once per operation ID")
        if gate.get("activate_once") is not True:
            raise EconomyError("pending operation activate_once must be true")
        for field in ("auto_execute", "auto_resolve"):
            if gate.get(field) is not False:
                raise EconomyError(f"pending operation {field} must be false")
        required_events = _records(
            gate.get("required_events"), "pending operation required events"
        )
        if not required_events:
            raise EconomyError("pending operation requires an activation event")
        required_event_keys: set[tuple[str, str, str]] = set()
        for event in required_events:
            key = tuple(
                _text(event.get(field), f"required activation event {field}")
                for field in ("subject_id", "event_type", "location_id")
            )
            if key in required_event_keys:
                raise EconomyError("pending operation required events cannot duplicate")
            required_event_keys.add(key)
        suppressed = gate.get("suppressed_contexts")
        if (
            not isinstance(suppressed, list)
            or not suppressed
            or any(not isinstance(value, str) or not value.strip() for value in suppressed)
        ):
            raise EconomyError("pending operation requires explicit suppressed contexts")
        operation_refs = operation.get("source_refs")
        if (
            not isinstance(operation_refs, list)
            or not operation_refs
            or any(not isinstance(value, str) or not value.strip() for value in operation_refs)
        ):
            raise EconomyError("pending operation requires source references")
        guards = operation.get("activation_guards")
        if (
            not isinstance(guards, list)
            or not guards
            or any(not isinstance(value, str) or not value.strip() for value in guards)
        ):
            raise EconomyError("pending operation requires activation guards")
        authority = _mapping(
            operation.get("decision_authority"),
            "pending operation decision authority",
        )
        if authority.get("holder") != "player":
            raise EconomyError("pending operation authority holder must be player")
        for field in (
            "may_execute_without_approval",
            "may_advance_campaign_time",
            "may_write_notion",
        ):
            if authority.get(field) is not False:
                raise EconomyError(f"pending operation {field} must be false")
        delegation = authority.get("delegation")
        if (
            not isinstance(delegation, list)
            or not delegation
            or any(not isinstance(value, str) or not value.strip() for value in delegation)
        ):
            raise EconomyError("pending operation requires explicit delegation rules")
        requests = _records(
            operation.get("required_fact_requests"),
            "pending operation fact requests",
        )
        _unique(requests, "request_id", "fact request")
        _unique(requests, "fact_key", "fact request")
        if not requests:
            raise EconomyError("pending operation requires at least one fact request")
        for request in requests:
            for field in ("location", "owner", "due", "question", "evidence", "resolves"):
                _text(request.get(field), f"fact request {field}")
            if request.get("status") != "unresolved":
                raise EconomyError("fact request must begin unresolved")
        gates = _records(operation.get("decision_gates"), "pending operation decision gates")
        _unique(gates, "decision_id", "decision gate")
        if not gates:
            raise EconomyError("pending operation requires at least one decision gate")
        for gate in gates:
            for field in ("authority", "when", "decision"):
                _text(gate.get(field), f"decision gate {field}")
            options = gate.get("options")
            if (
                not isinstance(options, list)
                or len(options) < 2
                or any(not isinstance(value, str) or not value.strip() for value in options)
            ):
                raise EconomyError("decision gate requires at least two explicit options")

    opening = _mapping(scenario.get("opening_state"), "opening state")
    opening_rows = {
        field: _records(opening.get(field, []), f"opening {field}")
        for field in (
            "accounts",
            "inventories",
            "labor",
            "banks",
            "loans",
            "prices",
            "in_transit",
            "arrears",
        )
    }
    _unique(opening_rows["accounts"], "entity_id", "opening account")
    _unique(opening_rows["banks"], "bank_id", "opening bank")
    _unique(opening_rows["loans"], "loan_id", "opening loan")
    bank_ids = {_text(row.get("bank_id"), "opening bank ID") for row in opening_rows["banks"]}
    if requested_bank_ids - bank_ids:
        raise EconomyError(
            f"credit requests reference missing banks: {sorted(requested_bank_ids - bank_ids)}"
        )
    for bank in opening_rows["banks"]:
        for field in ("other_assets", "other_liabilities"):
            if field not in bank:
                raise EconomyError(f"opening bank {_text(bank.get('bank_id'), 'bank ID')} must explicitly state {field}")
            _decimal(bank.get(field), f"opening bank {field}")
        entity_ids.add(_text(bank.get("bank_id"), "bank account entity"))
    for inventory in opening_rows["inventories"]:
        entity_ids.add(_text(inventory.get("owner_id"), "inventory owner account"))
    for labor in opening_rows["labor"]:
        entity_ids.add(_text(labor.get("household_account_id"), "labor household account"))
    for loan in opening_rows["loans"]:
        loan_bank_id = _text(loan.get("bank_id"), "opening loan bank")
        if loan_bank_id not in bank_ids:
            raise EconomyError(f"opening loan references missing bank {loan_bank_id}")
        entity_ids.add(_text(loan.get("borrower_id"), "opening loan borrower"))
        entity_ids.add(_text(loan.get("collateral_owner_id"), "opening collateral owner"))
    for lot in opening_rows["in_transit"]:
        for field in ("buyer_id", "seller_id", "carrier_id", "toll_recipient_id"):
            entity_ids.add(_text(lot.get(field), f"opening shipment {field}"))

    account_ids = {
        _text(row.get("entity_id"), "opening account entity")
        for row in opening_rows["accounts"]
    }
    missing_accounts = entity_ids - account_ids
    if missing_accounts:
        raise EconomyError(
            f"opening state lacks explicit accounts for transactional roles: {sorted(missing_accounts)}"
        )
    for account in opening_rows["accounts"]:
        account_bank_id = account.get("bank_id")
        if account_bank_id is not None and _text(account_bank_id, "account bank") not in bank_ids:
            raise EconomyError(
                f"account {_text(account.get('entity_id'), 'account entity')} references a missing bank"
            )


def initial_state(scenario: Mapping[str, object]) -> dict[str, object]:
    """Build and seal the exact month-zero state for a validated scenario."""

    validate_scenario(scenario)
    opening = _mapping(scenario["opening_state"], "opening state")
    populations: list[dict[str, object]] = []
    for settlement in _records(scenario["settlements"], "settlements"):
        for social_class in _records(settlement["classes"], "social classes"):
            populations.append(
                {
                    "settlement_id": settlement["id"],
                    "class_id": social_class["id"],
                    "population": _decimal(social_class["population"], "population"),
                }
            )
    prices = deepcopy(opening.get("prices", []))
    present = {
        (row.get("settlement_id"), row.get("commodity_id"))
        for row in _records(prices, "opening prices")
    }
    for settlement in _records(scenario["settlements"], "settlements"):
        for commodity in _records(scenario["commodities"], "commodities"):
            key = (settlement["id"], commodity["id"])
            if key not in present:
                prices.append(
                    {
                        "settlement_id": key[0],
                        "commodity_id": key[1],
                        "price": commodity["base_price"],
                    }
                )
    state: dict[str, object] = {
        "schema": STATE_SCHEMA,
        "scenario_id": scenario["scenario_id"],
        "scenario_hash": state_hash(scenario),
        "canonical": False,
        "month": 0,
        "source_refs": list(scenario["source_refs"]),
        "populations": populations,
        "accounts": deepcopy(opening.get("accounts", [])),
        "inventories": deepcopy(opening.get("inventories", [])),
        "labor": deepcopy(opening.get("labor", [])),
        "banks": deepcopy(opening.get("banks", [])),
        "loans": deepcopy(opening.get("loans", [])),
        "prices": prices,
        "in_transit": deepcopy(opening.get("in_transit", [])),
        "arrears": deepcopy(opening.get("arrears", [])),
        "pending_operations": deepcopy(scenario.get("pending_operations", [])),
    }
    normalized = _normalize_state(state, scenario, require_hash=False)
    inventory_index = _index(normalized["inventories"], ("owner_id", "settlement_id", "commodity_id"))
    for inventory in normalized["inventories"]:
        inventory["pledged_quantity"] = ZERO
    for loan in normalized["loans"]:
        if loan.get("status") not in {"performing", "delinquent"}:
            continue
        collateral_key = (
            _text(loan.get("collateral_owner_id"), "collateral owner"),
            _text(loan.get("collateral_settlement_id"), "collateral settlement"),
            _text(loan.get("collateral_commodity_id"), "collateral commodity"),
        )
        if collateral_key not in inventory_index:
            raise EconomyError(f"opening loan collateral inventory is missing: {collateral_key}")
        collateral = inventory_index[collateral_key]
        collateral["pledged_quantity"] = _decimal(
            collateral.get("pledged_quantity", ZERO), "opening pledged quantity"
        ) + _decimal(loan.get("collateral_quantity"), "opening collateral quantity")
        if _decimal(collateral.get("pledged_quantity"), "opening pledged quantity") > _decimal(
            collateral.get("quantity"), "opening collateral inventory"
        ):
            raise EconomyError("opening loans pledge more collateral than exists")
    for bank in normalized["banks"]:
        bank_id = _text(bank.get("bank_id"), "opening bank ID")
        active_principal = sum(
            (
                _decimal(loan.get("principal"), "opening loan principal")
                for loan in normalized["loans"]
                if loan.get("bank_id") == bank_id
                and loan.get("status") in {"performing", "delinquent"}
            ),
            ZERO,
        )
        assets = (
            _decimal(bank.get("reserves"), "opening bank reserves")
            + active_principal
            + _decimal(bank.get("interest_receivable", ZERO), "opening interest receivable")
            + _decimal(bank.get("collateral_assets", ZERO), "opening collateral assets")
            + _decimal(bank.get("other_assets"), "opening other assets")
        )
        liabilities = _decimal(
            bank.get("deposit_liability"), "opening deposit liability"
        ) + _decimal(bank.get("other_liabilities"), "opening other liabilities")
        equity = _decimal(bank.get("equity"), "opening bank equity", minimum=None)
        residual = assets - liabilities - equity
        if abs(residual) > CONSERVATION_TOLERANCE:
            raise EconomyError(
                f"opening bank {bank_id} balance sheet residual is {_decimal_text(residual)}"
            )
    safe = dict(_json_safe(normalized))
    safe["state_hash"] = state_hash(safe)
    return safe


def _normalize_state(
    state: Mapping[str, object],
    scenario: Mapping[str, object],
    *,
    require_hash: bool = True,
) -> dict[str, object]:
    if state.get("schema") != STATE_SCHEMA:
        raise EconomyError(f"state schema must be {STATE_SCHEMA}")
    if state.get("scenario_id") != scenario.get("scenario_id"):
        raise EconomyError("state belongs to a different scenario")
    if state.get("scenario_hash") != state_hash(scenario):
        raise EconomyError("state is not bound to this exact scenario payload")
    if state.get("canonical") is not False:
        raise EconomyError("vertical-slice state must remain non-canonical")
    if "result_hash" in state:
        raise EconomyError("state contains an unexpected result hash")
    provided_hash = state.get("state_hash")
    if require_hash and provided_hash is None:
        raise EconomyError("state must carry a state hash seal")
    if provided_hash is not None:
        if not isinstance(provided_hash, str) or len(provided_hash) != 64:
            raise EconomyError("state hash must be a SHA-256 hexadecimal seal")
        try:
            int(provided_hash, 16)
        except ValueError as exc:
            raise EconomyError("state hash must be a SHA-256 hexadecimal seal") from exc
        if state_hash(state) != provided_hash:
            raise EconomyError("state hash does not match state payload")
    result = deepcopy(dict(state))
    result.pop("state_hash", None)
    result["month"] = _integer(result.get("month"), "state month")
    for field in ("populations", "accounts", "inventories", "labor", "banks", "loans", "prices", "in_transit", "arrears", "pending_operations"):
        result[field] = [dict(row) for row in _records(result.get(field, []), f"state {field}")]
    if canonical_json(result["pending_operations"]) != canonical_json(
        scenario.get("pending_operations", [])
    ):
        raise EconomyError("state pending operations do not match the sealed scenario")
    decimal_fields = {
        "populations": ("population",),
        "accounts": ("cash", "deposit"),
        "inventories": ("quantity", "pledged_quantity", "collateral_carrying_value"),
        "labor": ("workers", "wage", "employed_worker_days", "employed_workers"),
        "banks": (
            "reserves",
            "reserve_ratio",
            "equity",
            "deposit_liability",
            "interest_receivable",
            "collateral_assets",
            "other_assets",
            "other_liabilities",
        ),
        "loans": ("principal", "annual_rate", "scheduled_principal", "collateral_quantity", "collateral_haircut", "accrued_interest"),
        "prices": ("price",),
        "in_transit": ("quantity", "dispatched_quantity", "route_loss", "goods_value", "carrier_fee", "toll"),
        "arrears": ("amount",),
    }
    for group, fields in decimal_fields.items():
        for row in result[group]:
            if group == "loans":
                row.setdefault("accrued_interest", ZERO)
            if group == "inventories":
                row.setdefault("pledged_quantity", ZERO)
                row.setdefault("collateral_carrying_value", ZERO)
            if group == "banks":
                row.setdefault("collateral_assets", ZERO)
            for field in fields:
                if field in row:
                    minimum = None if group == "banks" and field == "equity" else ZERO
                    row[field] = _decimal(row[field], f"{group} {field}", minimum=minimum)
    for inventory in result["inventories"]:
        quantity = _decimal(inventory.get("quantity"), "inventory quantity")
        pledged = _decimal(inventory.get("pledged_quantity", ZERO), "pledged inventory")
        if pledged > quantity:
            raise EconomyError("inventory pledged quantity cannot exceed physical quantity")
    account_rows = result["accounts"]
    for bank in result["banks"]:
        bank_id = _text(bank.get("bank_id"), "bank ID")
        computed = sum(
            (
                _decimal(account.get("deposit", ZERO), "opening account deposit")
                for account in account_rows
                if account.get("bank_id") == bank_id
            ),
            ZERO,
        )
        if "deposit_liability" in bank and _decimal(
            bank.get("deposit_liability"), "recorded deposit liability"
        ) != computed:
            raise EconomyError(f"bank {bank_id} deposit liability does not match depositor balances")
        bank.setdefault("deposit_liability", computed)
        accrued = sum(
            (
                _decimal(loan.get("accrued_interest", ZERO), "loan accrued interest")
                for loan in result["loans"]
                if loan.get("bank_id") == bank_id
                and loan.get("status") in {"performing", "delinquent"}
            ),
            ZERO,
        )
        if "interest_receivable" in bank and _decimal(
            bank.get("interest_receivable"), "bank interest receivable"
        ) != accrued:
            raise EconomyError(f"bank {bank_id} interest receivable does not match active loans")
        bank.setdefault("interest_receivable", accrued)
        for field in ("other_assets", "other_liabilities"):
            if field not in bank:
                raise EconomyError(f"state bank {bank_id} is missing explicit {field}")
        collateral_inventory_value = sum(
            (
                _decimal(
                    inventory.get("collateral_carrying_value", ZERO),
                    "bank collateral inventory carrying value",
                )
                for inventory in result["inventories"]
                if inventory.get("owner_id") == bank_id
            ),
            ZERO,
        )
        if _decimal(
            bank.get("collateral_assets", ZERO), "bank collateral assets"
        ) != collateral_inventory_value:
            raise EconomyError(
                f"bank {bank_id} collateral asset does not match tagged collateral inventory"
            )
    return result


def _index(records: Sequence[MutableMapping[str, object]], keys: Sequence[str]) -> dict[tuple[str, ...], MutableMapping[str, object]]:
    result: dict[tuple[str, ...], MutableMapping[str, object]] = {}
    for record in records:
        key = tuple(_text(record.get(part), f"record {part}") for part in keys)
        if key in result:
            raise EconomyError(f"duplicate state key: {key}")
        result[key] = record
    return result


class _Month:
    def __init__(self, scenario: Mapping[str, object], state: dict[str, object], seed: str):
        self.scenario = scenario
        self.state = state
        self.seed = seed
        self.month = int(state["month"]) + 1
        self.events: list[dict[str, object]] = []
        self.decisions: list[dict[str, object]] = []
        self.ledger: list[dict[str, object]] = []
        self.production: list[dict[str, object]] = []
        self.labor_receipts: list[dict[str, object]] = []
        self.market: list[dict[str, object]] = []
        self.trades: list[dict[str, object]] = []
        self.route_usage: dict[str, Decimal] = {}
        self.obligations: list[dict[str, object]] = []
        self.migrations: list[dict[str, object]] = []
        self.bank_receipts: list[dict[str, object]] = []
        self.shocks: list[dict[str, object]] = []
        self.physical: dict[str, dict[str, Decimal]] = {}
        self.accounts = _index(self.state["accounts"], ("entity_id",))
        self.inventories = _index(
            self.state["inventories"], ("owner_id", "settlement_id", "commodity_id")
        )
        self.labor = _index(self.state["labor"], ("settlement_id", "occupation"))
        self.banks = _index(self.state["banks"], ("bank_id",))
        self.prices = _index(self.state["prices"], ("settlement_id", "commodity_id"))
        self.populations = _index(self.state["populations"], ("settlement_id", "class_id"))
        self.commodities = {
            _text(row.get("id"), "commodity ID"): row
            for row in _records(scenario["commodities"], "commodities")
        }
        self.active_effects: list[Mapping[str, object]] = []
        self.opening_physical = self._physical_totals()

    def event(self, phase: str, kind: str, summary: str, causes: Sequence[str], effects: Sequence[str]) -> None:
        self.events.append(
            {
                "event_id": f"event:{self.month}:{len(self.events)+1:04d}",
                "phase": phase,
                "kind": kind,
                "summary": summary,
                "causes": list(causes),
                "effects": list(effects),
            }
        )

    def decision(self, decision_id: str, summary: str, reason: str, options: Sequence[str]) -> None:
        if any(item["decision_id"] == decision_id for item in self.decisions):
            return
        self.decisions.append(
            {
                "decision_id": decision_id,
                "summary": summary,
                "reason": reason,
                "options": list(options),
            }
        )

    def book(self, kind: str, summary: str, postings: Sequence[tuple[str, Decimal, Decimal]]) -> None:
        debits = sum((item[1] for item in postings), ZERO)
        credits = sum((item[2] for item in postings), ZERO)
        if debits != credits:
            raise EconomyError(f"unbalanced transaction {kind}: {debits} != {credits}")
        self.ledger.append(
            {
                "transaction_id": f"txn:{self.month}:{len(self.ledger)+1:04d}",
                "kind": kind,
                "summary": summary,
                "postings": [
                    {"account": account, "debit": debit, "credit": credit}
                    for account, debit, credit in postings
                ],
                "debits": debits,
                "credits": credits,
            }
        )

    def inventory(self, owner: str, settlement: str, commodity: str) -> MutableMapping[str, object]:
        key = (owner, settlement, commodity)
        if key not in self.inventories:
            row: MutableMapping[str, object] = {
                "owner_id": owner,
                "settlement_id": settlement,
                "commodity_id": commodity,
                "quantity": ZERO,
                "pledged_quantity": ZERO,
                "collateral_carrying_value": ZERO,
            }
            self.state["inventories"].append(row)
            self.inventories[key] = row
        return self.inventories[key]

    def account(self, entity: str) -> MutableMapping[str, object]:
        key = (entity,)
        if key not in self.accounts:
            raise EconomyError(f"missing explicit account for transactional entity {entity}")
        return self.accounts[key]

    def funds(self, entity: str) -> Decimal:
        account = self.account(entity)
        return _decimal(account.get("cash", ZERO), "account cash") + _decimal(
            account.get("deposit", ZERO), "account deposit"
        )

    def _physical_totals(self) -> dict[str, Decimal]:
        totals = {commodity_id: ZERO for commodity_id in self.commodities}
        for row in self.state["inventories"]:
            totals[_text(row.get("commodity_id"), "inventory commodity")] += _decimal(
                row.get("quantity"), "inventory quantity"
            )
        for row in self.state["in_transit"]:
            totals[_text(row.get("commodity_id"), "transit commodity")] += _decimal(
                row.get("quantity"), "transit quantity"
            )
        return totals

    def physical_add(self, commodity: str, field: str, amount: Decimal) -> None:
        self.physical.setdefault(commodity, {}).setdefault(field, ZERO)
        self.physical[commodity][field] += amount

    def transfer(self, payer: str, payee: str, amount: Decimal, kind: str, summary: str) -> Decimal:
        amount = amount.quantize(MONEY)
        if amount <= ZERO:
            return ZERO
        if payer == payee:
            return amount
        payer_account = self.account(payer)
        payee_account = self.account(payee)
        paid = min(amount, self.funds(payer))
        if paid <= ZERO:
            return ZERO
        remaining = paid
        rail_postings: list[tuple[str, Decimal, Decimal]] = []
        cash = min(_decimal(payer_account.get("cash", ZERO), "payer cash"), remaining)
        payer_account["cash"] = _decimal(payer_account.get("cash", ZERO), "payer cash") - cash
        payee_bank = payee_account.get("bank_id")
        if payee_bank:
            payee_bank_id = _text(payee_bank, "payee bank")
            payee_bank_row = self.banks[(payee_bank_id,)]
            payee_account["deposit"] = _decimal(payee_account.get("deposit", ZERO), "payee deposit") + cash
            payee_bank_row["reserves"] = _decimal(payee_bank_row.get("reserves"), "bank reserves") + cash
            payee_bank_row["deposit_liability"] = _decimal(
                payee_bank_row.get("deposit_liability", ZERO), "deposit liability"
            ) + cash
            if cash:
                rail_postings.extend(
                    (
                        (f"Assets:{payee_bank_id}:Reserves", cash, ZERO),
                        (f"Liabilities:{payee_bank_id}:CustomerDeposits", ZERO, cash),
                    )
                )
        else:
            payee_account["cash"] = _decimal(payee_account.get("cash", ZERO), "payee cash") + cash
        remaining -= cash
        if remaining > ZERO:
            payer_bank_id = _text(payer_account.get("bank_id"), "payer bank")
            payer_bank = self.banks[(payer_bank_id,)]
            payee_bank_id = payee_account.get("bank_id")
            reserve_limit = remaining
            if payee_bank_id != payer_bank_id:
                reserve_limit = min(
                    reserve_limit,
                    _decimal(payer_bank.get("reserves"), "payer bank reserves"),
                )
            deposit_paid = min(
                remaining,
                reserve_limit,
                _decimal(payer_account.get("deposit", ZERO), "payer deposit"),
            )
            payer_account["deposit"] = _decimal(payer_account.get("deposit", ZERO), "payer deposit") - deposit_paid
            payer_bank["deposit_liability"] = _decimal(
                payer_bank.get("deposit_liability", ZERO), "payer deposit liability"
            ) - deposit_paid
            if payee_bank_id:
                payee_bank_id = _text(payee_bank_id, "payee bank")
                payee_account["deposit"] = _decimal(payee_account.get("deposit", ZERO), "payee deposit") + deposit_paid
                if payee_bank_id != payer_bank_id:
                    payer_bank["reserves"] = _decimal(payer_bank.get("reserves"), "payer reserves") - deposit_paid
                    other = self.banks[(payee_bank_id,)]
                    other["reserves"] = _decimal(other.get("reserves"), "payee reserves") + deposit_paid
                    other["deposit_liability"] = _decimal(
                        other.get("deposit_liability", ZERO), "payee deposit liability"
                    ) + deposit_paid
                    rail_postings.extend(
                        (
                            (f"Liabilities:{payer_bank_id}:CustomerDeposits", deposit_paid, ZERO),
                            (f"Assets:{payer_bank_id}:Reserves", ZERO, deposit_paid),
                            (f"Assets:{payee_bank_id}:Reserves", deposit_paid, ZERO),
                            (f"Liabilities:{payee_bank_id}:CustomerDeposits", ZERO, deposit_paid),
                        )
                    )
                else:
                    other = self.banks[(payee_bank_id,)]
                    other["deposit_liability"] = _decimal(
                        other.get("deposit_liability", ZERO), "payee deposit liability"
                    ) + deposit_paid
            else:
                payer_bank["reserves"] = _decimal(payer_bank.get("reserves"), "payer reserves") - deposit_paid
                payee_account["cash"] = _decimal(payee_account.get("cash", ZERO), "payee cash") + deposit_paid
                rail_postings.extend(
                    (
                        (f"Liabilities:{payer_bank_id}:CustomerDeposits", deposit_paid, ZERO),
                        (f"Assets:{payer_bank_id}:Reserves", ZERO, deposit_paid),
                    )
                )
            remaining -= deposit_paid
        actual = paid - remaining
        if actual > ZERO:
            self.book(
                kind,
                summary,
                [
                    (f"Assets:{payee}:Funds", actual, ZERO),
                    (f"Assets:{payer}:Funds", ZERO, actual),
                    *rail_postings,
                ],
            )
        return actual

    def effect(self, name: str, *, settlement: str | None = None, sector: str | None = None) -> Decimal:
        multiplicative = name.endswith("_multiplier")
        value = ONE if multiplicative else ZERO
        for shock in self.active_effects:
            if shock.get("settlement_id") not in {None, settlement}:
                continue
            if shock.get("sector") not in {None, sector}:
                continue
            effects = _mapping(shock.get("effects"), "shock effects")
            if name not in effects:
                continue
            amount = _decimal(effects[name], f"shock {name}", minimum=None)
            value = value * amount if multiplicative else value + amount
        return max(ZERO, value) if multiplicative else value


def _apply_shocks(month: _Month) -> None:
    for shock in sorted(
        _records(month.scenario["shocks"], "shocks"),
        key=lambda item: _text(item.get("id"), "shock ID"),
    ):
        shock_id = _text(shock.get("id"), "shock ID")
        probability = _rate(shock.get("probability"), "shock probability")
        draw = _sample(month.seed, f"month:{month.month}:shock:{shock_id}")
        scheduled_months = (
            [
                _integer(value, "shock scheduled month", minimum=1)
                for value in shock.get("months", [])
            ]
            if "months" in shock
            else None
        )
        eligible = scheduled_months is None or month.month in scheduled_months
        active = eligible and draw < probability
        receipt = {
            "shock_id": shock_id,
            "type": _text(shock.get("type"), "shock type"),
            "eligible": eligible,
            "months": scheduled_months,
            "active": active,
            "probability": probability,
            "draw": draw,
            "settlement_id": shock.get("settlement_id"),
            "sector": shock.get("sector"),
            "effects": dict(_mapping(shock.get("effects"), "shock effects")),
            "source_ref": _text(shock.get("source_ref"), "shock source reference"),
        }
        month.shocks.append(receipt)
        if active:
            month.active_effects.append(receipt)
            effect_text = [f"{key}={value}" for key, value in sorted(receipt["effects"].items())]
            month.event(
                "shocks",
                f"shock:{receipt['type']}",
                f"{shock_id} occurred.",
                [f"deterministic draw {_decimal_text(draw)} below probability {_decimal_text(probability)}"],
                effect_text,
            )
            month.decision(
                f"respond:{shock_id}",
                f"Respond to {receipt['type']} shock",
                f"{shock_id} changed this month's operating constraints.",
                ["absorb the loss", "redirect reserves", "change production or route priorities"],
            )


def _process_arrivals(month: _Month) -> None:
    remaining: list[MutableMapping[str, object]] = []
    for lot in sorted(month.state["in_transit"], key=lambda row: str(row.get("shipment_id"))):
        arrival = _integer(lot.get("arrival_month"), "shipment arrival month")
        if arrival > month.month:
            remaining.append(lot)
            continue
        buyer = _text(lot.get("buyer_id"), "shipment buyer")
        payments = [
            (_text(lot.get("seller_id"), "shipment seller"), _decimal(lot.get("goods_value", ZERO), "shipment goods value").quantize(MONEY), "trade-goods"),
            (_text(lot.get("carrier_id"), "shipment carrier"), _decimal(lot.get("carrier_fee", ZERO), "shipment carrier fee").quantize(MONEY), "carrier-fee"),
            (_text(lot.get("toll_recipient_id"), "shipment toll recipient"), _decimal(lot.get("toll", ZERO), "shipment toll").quantize(MONEY), "route-toll"),
        ]
        total_due = sum((item[1] for item in payments), ZERO)
        prepaid = lot.get("settlement_status") == "prepaid"
        if not prepaid and not _bundle_is_payable(month, buyer, payments):
            lot["status"] = "held_at_destination_unpaid"
            remaining.append(lot)
            month.event(
                "arrivals",
                "shipment-held",
                f"{lot.get('shipment_id')} reached its destination but could not settle.",
                [f"buyer funds {_decimal_text(month.funds(buyer))} below {_decimal_text(total_due)} due"],
                ["cargo remains in carrier custody", "household or business demand remains uncovered"],
            )
            month.decision(
                f"settle:{lot.get('shipment_id')}",
                "Settle held shipment",
                "Arrived cargo is unpaid and unavailable to consume.",
                ["fund the buyer", "renegotiate the sale", "release the cargo to another buyer"],
            )
            continue
        if not prepaid:
            _settle_bundle(month, buyer, payments, f"Settlement of {lot.get('shipment_id')}")
        inventory = month.inventory(
            buyer,
            _text(lot.get("destination"), "shipment destination"),
            _text(lot.get("commodity_id"), "shipment commodity"),
        )
        inventory["quantity"] = _decimal(inventory.get("quantity"), "arrival inventory") + _decimal(
            lot.get("quantity"), "arrival quantity"
        )
        month.event(
            "arrivals",
            "shipment-arrival",
            f"{lot.get('shipment_id')} delivered {_decimal_text(_decimal(lot.get('quantity'), 'arrival'))} {lot.get('commodity_id')} to {buyer}.",
            [f"dispatched in month {lot.get('departure_month')}", f"route {lot.get('route_id')} travel completed"],
            [
                "buyer inventory increased",
                "seller, carrier, and toll accounts were prepaid at dispatch"
                if prepaid
                else "seller, carrier, and toll accounts settled at arrival",
            ],
        )
    month.state["in_transit"] = remaining


def _bundle_is_payable(
    month: _Month,
    payer: str,
    payments: Sequence[tuple[str, Decimal, str]],
) -> bool:
    """Preflight a payment bundle conservatively, including reserve settlement."""

    account = month.account(payer)
    cash = _decimal(account.get("cash", ZERO), "payer cash")
    deposit = _decimal(account.get("deposit", ZERO), "payer deposit")
    total = sum((amount for payee, amount, _ in payments if payee != payer), ZERO)
    if cash + deposit < total:
        return False
    payer_bank_id = account.get("bank_id")
    if not payer_bank_id:
        return cash >= total
    payer_bank_id = _text(payer_bank_id, "payer bank")
    external = sum(
        (
            amount
            for payee, amount, _ in payments
            if payee != payer and month.account(payee).get("bank_id") != payer_bank_id
        ),
        ZERO,
    )
    reserves = _decimal(month.banks[(payer_bank_id,)].get("reserves"), "payer-bank reserves")
    return external <= cash + min(deposit, reserves)


def _settle_bundle(
    month: _Month,
    payer: str,
    payments: Sequence[tuple[str, Decimal, str]],
    summary: str,
) -> None:
    if not _bundle_is_payable(month, payer, payments):
        raise EconomyError("attempted to settle an unaffordable payment bundle")
    payer_bank_id = month.account(payer).get("bank_id")
    ordered = sorted(
        payments,
        key=lambda item: (
            month.account(item[0]).get("bank_id") == payer_bank_id,
            item[0],
            item[2],
        ),
    )
    for payee, due, kind in ordered:
        if due and month.transfer(payer, payee, due, kind, summary) != due:
            raise EconomyError("payment-bundle preflight and settlement diverged")


def _bank_deposits(month: _Month, bank_id: str) -> Decimal:
    return sum(
        (
            _decimal(row.get("deposit", ZERO), "account deposit")
            for row in month.state["accounts"]
            if row.get("bank_id") == bank_id
        ),
        ZERO,
    )


def _originate_credit(month: _Month) -> None:
    existing = {_text(row.get("loan_id"), "loan ID") for row in month.state["loans"]}
    for request in sorted(
        _records(month.scenario["credit_requests"], "credit requests"),
        key=lambda item: _text(item.get("loan_id"), "credit-request loan ID"),
    ):
        if _integer(request.get("month", month.month), "credit request month") != month.month:
            continue
        loan_id = _text(request.get("loan_id"), "credit-request loan ID")
        if loan_id in existing:
            continue
        bank_id = _text(request.get("bank_id"), "credit-request bank")
        borrower = _text(request.get("borrower_id"), "credit-request borrower")
        amount = _decimal(request.get("amount"), "credit amount")
        bank = month.banks.get((bank_id,))
        if bank is None:
            raise EconomyError(f"credit request references unknown bank {bank_id}")
        borrower_account = month.account(borrower)
        if borrower_account.get("bank_id") != bank_id:
            month.decision(
                f"credit:{loan_id}",
                "Choose a settlement bank",
                f"{borrower} does not hold its deposit at {bank_id}.",
                ["open a deposit account", "request another bank", "fund operations without credit"],
            )
            continue
        settlement = _text(request.get("collateral_settlement_id"), "collateral settlement")
        commodity = _text(request.get("collateral_commodity_id"), "collateral commodity")
        collateral_quantity = _decimal(request.get("collateral_quantity"), "collateral quantity")
        collateral_owner = _text(request.get("collateral_owner_id", borrower), "collateral owner")
        collateral_inventory = month.inventory(collateral_owner, settlement, commodity)
        available = _available_quantity(collateral_inventory, "collateral inventory")
        collateral_price = _decimal(month.prices[(settlement, commodity)].get("price"), "collateral price")
        haircut = _rate(request.get("collateral_haircut", "0.25"), "collateral haircut")
        collateral_value = available if available < collateral_quantity else collateral_quantity
        collateral_value *= collateral_price * (ONE - haircut)
        ratio = _decimal(request.get("minimum_collateral_ratio", "1.25"), "minimum collateral ratio")
        reserve_ratio = _rate(bank.get("reserve_ratio"), "bank reserve ratio")
        deposits_after = _bank_deposits(month, bank_id) + amount
        reserve_ok = _decimal(bank.get("reserves"), "bank reserves") >= deposits_after * reserve_ratio
        collateral_ok = collateral_quantity <= available and collateral_value >= amount * ratio
        if not reserve_ok or not collateral_ok:
            causes = []
            if not reserve_ok:
                causes.append("post-loan deposits would breach the reserve requirement")
            if not collateral_ok:
                causes.append("haircut collateral value is below the required coverage")
            month.event("banking", "loan-denied", f"{bank_id} denied {loan_id}.", causes, ["no deposit was created"])
            month.decision(
                f"credit:{loan_id}",
                "Repair denied credit",
                "; ".join(causes),
                ["add collateral", "reduce the request", "increase bank reserves"],
            )
            continue
        borrower_account["deposit"] = _decimal(borrower_account.get("deposit", ZERO), "borrower deposit") + amount
        bank["deposit_liability"] = _decimal(
            bank.get("deposit_liability", ZERO), "bank deposit liability"
        ) + amount
        loan = {
            "loan_id": loan_id,
            "bank_id": bank_id,
            "borrower_id": borrower,
            "principal": amount,
            "annual_rate": _rate(request.get("annual_rate"), "loan annual rate"),
            "accrued_interest": ZERO,
            "scheduled_principal": amount / Decimal(_integer(request.get("term_months"), "loan term", minimum=1)),
            "remaining_months": _integer(request.get("term_months"), "loan term", minimum=1),
            "origin_month": month.month,
            "missed_payments": 0,
            "default_after_missed": _integer(request.get("default_after_missed", 2), "default threshold", minimum=1),
            "status": "performing",
            "collateral_owner_id": collateral_owner,
            "collateral_settlement_id": settlement,
            "collateral_commodity_id": commodity,
            "collateral_quantity": collateral_quantity,
            "collateral_haircut": haircut,
        }
        month.state["loans"].append(loan)
        collateral_inventory["pledged_quantity"] = _decimal(
            collateral_inventory.get("pledged_quantity", ZERO), "pledged collateral"
        ) + collateral_quantity
        existing.add(loan_id)
        month.book(
            "loan-origination",
            f"{bank_id} originated {loan_id} to {borrower}",
            (
                (f"Assets:{bank_id}:Loans:{loan_id}", amount, ZERO),
                (f"Liabilities:{bank_id}:Deposits", ZERO, amount),
                (f"Assets:{borrower}:Deposit:{bank_id}", amount, ZERO),
                (f"Liabilities:{borrower}:Loan:{loan_id}", ZERO, amount),
            ),
        )
        month.bank_receipts.append({"loan_id": loan_id, "action": "originated", "amount": amount, "collateral_value": collateral_value})
        month.event(
            "banking",
            "loan-originated",
            f"{bank_id} created a {_decimal_text(amount)} gp working-capital deposit for {borrower}.",
            [f"collateral value after haircut {_decimal_text(collateral_value)}", "reserve requirement passed"],
            ["bank loan asset and deposit liability increased equally", "collateral remains pledged"],
        )


def _produce(month: _Month) -> None:
    labor_used: dict[tuple[str, str], Decimal] = {key: ZERO for key in month.labor}
    for recipe in sorted(
        _records(month.scenario["recipes"], "recipes"),
        key=lambda item: (_integer(item.get("priority", 100), "recipe priority"), _text(item.get("id"), "recipe ID")),
    ):
        recipe_id = _text(recipe.get("id"), "recipe ID")
        entity = _text(recipe.get("entity_id"), "recipe entity")
        settlement = _text(recipe.get("settlement_id"), "recipe settlement")
        kind = _text(recipe.get("kind"), "recipe kind")
        sector = _text(recipe.get("sector", kind), "recipe sector")
        multiplier = month.effect("production_multiplier", settlement=settlement, sector=sector)
        feasible = min(
            _decimal(recipe.get("desired_batches"), "desired batches"),
            _decimal(recipe.get("max_batches"), "maximum batches") * multiplier,
        )
        limits: list[str] = []
        for commodity, per_batch_raw in sorted(
            _mapping(recipe.get("inputs"), "recipe inputs").items()
        ):
            per_batch = _decimal(per_batch_raw, "input per batch")
            if per_batch > ZERO:
                input_inventory = month.inventory(entity, settlement, commodity)
                available = _available_quantity(input_inventory, "input inventory")
                candidate = available / per_batch
                if candidate < feasible:
                    feasible = candidate
                    limits = [f"{commodity} inventory"]
        wage_per_batch = ZERO
        for occupation, days_raw in sorted(
            _mapping(recipe.get("labor"), "recipe labor").items()
        ):
            days = _decimal(days_raw, "labor days per batch")
            pool = month.labor.get((settlement, occupation))
            if pool is None:
                raise EconomyError(f"recipe {recipe_id} lacks {occupation} labor at {settlement}")
            labor_multiplier = month.effect("labor_multiplier", settlement=settlement, sector=sector)
            available_days = _decimal(pool.get("workers"), "labor workers") * DAYS_PER_MONTH * labor_multiplier - labor_used[(settlement, occupation)]
            if days > ZERO and available_days / days < feasible:
                feasible = max(ZERO, available_days / days)
                limits = [f"{occupation} worker-days"]
            wage_per_batch += days * _decimal(pool.get("wage"), "labor wage")
        if wage_per_batch > ZERO and month.funds(entity) / wage_per_batch < feasible:
            feasible = month.funds(entity) / wage_per_batch
            limits = ["payroll liquidity"]
        batches = max(ZERO, feasible)
        inputs: dict[str, Decimal] = {}
        outputs: dict[str, Decimal] = {}
        for commodity, amount_raw in sorted(
            _mapping(recipe.get("inputs"), "recipe inputs").items()
        ):
            amount = _decimal(amount_raw, "input amount") * batches
            inventory = month.inventory(entity, settlement, commodity)
            inventory["quantity"] = _decimal(inventory.get("quantity"), "input inventory") - amount
            inputs[commodity] = amount
            month.physical_add(commodity, "production_inputs", amount)
        for commodity, amount_raw in sorted(
            _mapping(recipe.get("outputs"), "recipe outputs").items()
        ):
            amount = _decimal(amount_raw, "output amount") * batches
            inventory = month.inventory(entity, settlement, commodity)
            inventory["quantity"] = _decimal(inventory.get("quantity"), "output inventory") + amount
            outputs[commodity] = amount
            month.physical_add(commodity, "produced", amount)
        payroll = ZERO
        labor_lines: list[dict[str, object]] = []
        for occupation, days_raw in sorted(
            _mapping(recipe.get("labor"), "recipe labor").items()
        ):
            days = _decimal(days_raw, "labor days") * batches
            pool = month.labor[(settlement, occupation)]
            labor_used[(settlement, occupation)] += days
            due = (days * _decimal(pool.get("wage"), "labor wage")).quantize(MONEY)
            household = _text(pool.get("household_account_id"), "labor household account")
            paid = month.transfer(entity, household, due, "payroll", f"{recipe_id} {occupation} payroll")
            if paid != due:
                raise EconomyError(f"recipe {recipe_id} produced output without fully paying labor")
            payroll += paid
            labor_lines.append({"occupation": occupation, "worker_days": days, "wage": pool["wage"], "payroll": paid})
        receipt = {
            "recipe_id": recipe_id,
            "entity_id": entity,
            "settlement_id": settlement,
            "kind": kind,
            "sector": sector,
            "batches": batches,
            "inputs": inputs,
            "outputs": outputs,
            "payroll": payroll,
            "labor": labor_lines,
            "limiting_factors": limits,
            "shock_multiplier": multiplier,
            "source_ref": _text(recipe.get("source_ref"), "recipe source reference"),
        }
        month.production.append(receipt)
        month.event(
            "production",
            f"production:{kind}",
            f"{entity} completed {_decimal_text(batches)} batches of {recipe_id}.",
            limits or ["requested volume fit material, labour, capacity, and payroll limits"],
            [f"outputs: {', '.join(f'{key}={_decimal_text(value)}' for key, value in sorted(outputs.items())) or 'none'}", f"payroll {_decimal_text(payroll)} gp"],
        )

    for key, pool in sorted(month.labor.items()):
        used = labor_used[key]
        workers = _decimal(pool.get("workers"), "labor workers")
        capacity = workers * DAYS_PER_MONTH
        utilization = ZERO if capacity == ZERO else min(ONE, used / capacity)
        old_wage = _decimal(pool.get("wage"), "labor wage")
        wage_change = (utilization - Decimal("0.80")) * Decimal("0.05")
        new_wage = max(Decimal("0.01"), old_wage * (ONE + wage_change))
        pool["employed_worker_days"] = used
        pool["employed_workers"] = used / DAYS_PER_MONTH
        pool["wage"] = new_wage
        receipt = {
            "settlement_id": key[0],
            "occupation": key[1],
            "class_id": pool.get("class_id"),
            "workers": workers,
            "employed_workers": pool["employed_workers"],
            "worker_days": used,
            "utilization": utilization,
            "wage_before": old_wage,
            "wage_after": new_wage,
        }
        month.labor_receipts.append(receipt)
        if workers > ZERO and utilization < Decimal("0.50"):
            month.decision(
                f"employment:{key[0]}:{key[1]}",
                f"Address low {key[1]} employment",
                f"Only {_decimal_text(utilization * Decimal(100))}% of available worker-days were used.",
                ["commission public work", "retrain workers", "permit migration"],
            )


def _apply_storage_spoilage(month: _Month) -> None:
    for key, inventory in sorted(month.inventories.items()):
        quantity = _decimal(inventory.get("quantity"), "inventory quantity")
        rate = _rate(month.commodities[key[2]].get("spoilage_rate"), "commodity spoilage rate")
        shock_extra = month.effect("spoilage_rate_delta", settlement=key[1])
        effective_rate = min(Decimal("0.999999"), max(ZERO, rate + shock_extra))
        loss = quantity * effective_rate
        if loss <= ZERO:
            continue
        inventory["quantity"] = quantity - loss
        inventory["pledged_quantity"] = min(
            _decimal(inventory.get("pledged_quantity", ZERO), "pledged inventory"),
            quantity - loss,
        )
        if (key[0],) in month.banks:
            carrying_value = _decimal(
                inventory.get("collateral_carrying_value", ZERO),
                "collateral carrying value",
            )
            if carrying_value:
                impairment = (
                    carrying_value
                    if loss == quantity
                    else min(carrying_value, (carrying_value * loss / quantity).quantize(MONEY))
                )
                inventory["collateral_carrying_value"] = carrying_value - impairment
                bank = month.banks[(key[0],)]
                bank["collateral_assets"] = _decimal(
                    bank.get("collateral_assets", ZERO), "bank collateral assets"
                ) - impairment
                bank["equity"] = _decimal(
                    bank.get("equity", ZERO), "bank equity", minimum=None
                ) - impairment
                if impairment:
                    month.book(
                        "collateral-impairment",
                        f"Storage spoilage impaired seized {key[2]} held by {key[0]}",
                        (
                            (f"Expense:{key[0]}:CollateralImpairment", impairment, ZERO),
                            (f"Assets:{key[0]}:CollateralInventory", ZERO, impairment),
                        ),
                    )
        month.physical_add(key[2], "storage_spoilage", loss)
        month.event(
            "storage",
            "spoilage",
            f"{_decimal_text(loss)} {key[2]} spoiled at {key[1]}.",
            [f"base/effective storage loss rate {_decimal_text(effective_rate)}"],
            [f"{key[0]} inventory fell to {_decimal_text(quantity-loss)}"],
        )


def _local_consumption(
    month: _Month,
    *,
    buyer: str,
    settlement: str,
    commodity: str,
    requested: Decimal,
    stats: MutableMapping[tuple[str, str], dict[str, Decimal]],
    purpose: str,
) -> tuple[Decimal, list[dict[str, object]]]:
    """Consume owned stock, then clear deterministic local cash trades."""

    if requested <= ZERO:
        return ZERO, []
    key = (settlement, commodity)
    stats.setdefault(key, {"requested": ZERO, "consumed": ZERO, "opening_supply": ZERO})
    stats[key]["requested"] += requested
    consumed = ZERO
    trade_lines: list[dict[str, object]] = []
    own = month.inventory(buyer, settlement, commodity)
    own_use = min(
        requested,
        ZERO
        if (buyer,) in month.banks
        else _available_quantity(own, "buyer inventory"),
    )
    if own_use:
        own["quantity"] = _decimal(own.get("quantity"), "buyer inventory") - own_use
        consumed += own_use
        month.physical_add(commodity, "consumed", own_use)
        trade_lines.append({"seller_id": buyer, "quantity": own_use, "kind": "own-stock"})
    price = _decimal(month.prices[(settlement, commodity)].get("price"), "local price")
    for inventory_key, inventory in sorted(month.inventories.items()):
        if consumed >= requested:
            break
        seller, site, offered_commodity = inventory_key
        if (
            site != settlement
            or offered_commodity != commodity
            or seller == buyer
            or (seller,) in month.banks
        ):
            continue
        available = _available_quantity(inventory, "seller inventory")
        if available <= ZERO or price <= ZERO:
            continue
        units = min(requested - consumed, available, month.funds(buyer) / price)
        cost = (units * price).quantize(MONEY)
        if cost <= ZERO:
            continue
        paid = month.transfer(
            buyer,
            seller,
            cost,
            "local-trade",
            f"{buyer} bought {commodity} from {seller} at {settlement}",
        )
        units = min(units, paid / price)
        if units <= ZERO:
            continue
        inventory["quantity"] = _decimal(inventory.get("quantity"), "seller inventory") - units
        consumed += units
        month.physical_add(commodity, "consumed", units)
        trade = {
            "trade_id": f"trade:{month.month}:{len(month.trades)+1:04d}",
            "seller_id": seller,
            "buyer_id": buyer,
            "carrier_id": None,
            "origin": settlement,
            "destination": settlement,
            "commodity_id": commodity,
            "dispatched_quantity": units,
            "delivered_quantity": units,
            "route_loss": ZERO,
            "goods_value": paid,
            "carrier_fee": ZERO,
            "toll": ZERO,
            "departure_month": month.month,
            "arrival_month": month.month,
            "status": "delivered-and-settled",
            "purpose": purpose,
        }
        month.trades.append(trade)
        trade_lines.append({"seller_id": seller, "quantity": units, "kind": "local-purchase", "trade_id": trade["trade_id"]})
    stats[key]["consumed"] += consumed
    return consumed, trade_lines


def _dispatch_routes(
    month: _Month,
    *,
    buyer: str,
    destination: str,
    commodity: str,
    quantity_needed: Decimal,
    purpose: str,
    stats: MutableMapping[tuple[str, str], dict[str, Decimal]],
) -> tuple[Decimal, Decimal, list[dict[str, object]]]:
    """Dispatch imports; only zero-travel routes satisfy this month's need."""

    consumed_now = ZERO
    future_delivery = ZERO
    receipts: list[dict[str, object]] = []
    routes = [
        route
        for route in _records(month.scenario["routes"], "routes")
        if route.get("destination") == destination and commodity in route.get("commodities", [])
    ]
    def landed_cost(route: Mapping[str, object]) -> Decimal:
        origin = _text(route.get("origin"), "route origin")
        delivered_fraction = ONE - _rate(route.get("spoilage_rate"), "route spoilage rate")
        return _decimal(
            month.prices[(origin, commodity)].get("price"), "origin price"
        ) + (
            _decimal(route.get("carrier_cost_per_unit"), "carrier cost")
            + _decimal(route.get("toll_per_unit"), "route toll")
        ) / delivered_fraction

    routes.sort(key=lambda route: (landed_cost(route), _text(route.get("id"), "route ID")))
    remaining = quantity_needed
    for route in routes:
        if remaining <= ZERO:
            break
        route_id = _text(route.get("id"), "route ID")
        origin = _text(route.get("origin"), "route origin")
        loss_rate = _rate(route.get("spoilage_rate"), "route spoilage rate")
        delivered_fraction = ONE - loss_rate
        capacity = _decimal(route.get("capacity"), "route capacity") * month.effect(
            "route_capacity_multiplier", settlement=origin
        )
        used = month.route_usage.get(route_id, ZERO)
        route_remaining = max(ZERO, capacity - used)
        if route_remaining <= ZERO:
            continue
        origin_price = _decimal(month.prices[(origin, commodity)].get("price"), "origin price")
        carrier_unit = _decimal(route.get("carrier_cost_per_unit"), "carrier unit cost")
        toll_unit = _decimal(route.get("toll_per_unit"), "toll per unit")
        landed_per_delivered = origin_price + (carrier_unit + toll_unit) / delivered_fraction
        affordable_delivery = ZERO if landed_per_delivered <= ZERO else month.funds(buyer) / landed_per_delivered
        desired_dispatch = remaining / delivered_fraction
        for inventory_key, inventory in sorted(month.inventories.items()):
            if desired_dispatch <= ZERO or route_remaining <= ZERO:
                break
            seller, site, offered_commodity = inventory_key
            if (
                site != origin
                or offered_commodity != commodity
                or seller == buyer
                or (seller,) in month.banks
            ):
                continue
            available = _available_quantity(inventory, "route seller inventory")
            dispatched = min(available, desired_dispatch, route_remaining, affordable_delivery / delivered_fraction)
            if dispatched <= ZERO:
                continue
            delivered = dispatched * delivered_fraction
            loss = dispatched - delivered
            goods_value = (delivered * origin_price).quantize(MONEY)
            carrier_fee = (dispatched * carrier_unit).quantize(MONEY)
            toll = (dispatched * toll_unit).quantize(MONEY)
            total_due = goods_value + carrier_fee + toll
            if month.funds(buyer) < total_due:
                continue
            travel = _integer(route.get("travel_months"), "route travel months")
            payments = [
                (seller, goods_value, "route-goods"),
                (_text(route.get("carrier_id"), "route carrier"), carrier_fee, "carrier-fee"),
                (_text(route.get("toll_recipient_id"), "toll recipient"), toll, "route-toll"),
            ]
            if not _bundle_is_payable(month, buyer, payments):
                continue
            _settle_bundle(month, buyer, payments, f"Prepayment of {route_id} shipment")
            inventory["quantity"] = _decimal(inventory.get("quantity"), "route seller inventory") - dispatched
            month.route_usage[route_id] = month.route_usage.get(route_id, ZERO) + dispatched
            month.physical_add(commodity, "route_spoilage", loss)
            trade = {
                "trade_id": f"trade:{month.month}:{len(month.trades)+1:04d}",
                "shipment_id": f"shipment:{month.month}:{len(month.trades)+1:04d}",
                "route_id": route_id,
                "seller_id": seller,
                "buyer_id": buyer,
                "carrier_id": _text(route.get("carrier_id"), "route carrier"),
                "toll_recipient_id": _text(route.get("toll_recipient_id"), "toll recipient"),
                "origin": origin,
                "destination": destination,
                "commodity_id": commodity,
                "dispatched_quantity": dispatched,
                "delivered_quantity": delivered,
                "quantity": delivered,
                "route_loss": loss,
                "goods_value": goods_value,
                "carrier_fee": carrier_fee,
                "toll": toll,
                "departure_month": month.month,
                "arrival_month": month.month + travel,
                "status": "in-transit-prepaid" if travel else "delivered-and-settled",
                "settlement_status": "prepaid",
                "purpose": purpose,
            }
            if travel:
                month.state["in_transit"].append(dict(trade))
                future_delivery += delivered
            else:
                consumed_now += delivered
                month.physical_add(commodity, "consumed", delivered)
                stats.setdefault((destination, commodity), {"requested": ZERO, "consumed": ZERO, "opening_supply": ZERO})
                stats[(destination, commodity)]["consumed"] += delivered
            month.trades.append(trade)
            receipts.append(trade)
            month.event(
                "trade",
                "route-dispatch",
                f"{trade['shipment_id']} dispatched {_decimal_text(dispatched)} {commodity} on {route_id}.",
                [f"unmet demand at {destination}", f"route capacity remaining {_decimal_text(route_remaining)}"],
                [f"expected delivery {_decimal_text(delivered)}", f"route spoilage {_decimal_text(loss)}", f"carrier fee {_decimal_text(carrier_fee)} gp", f"toll {_decimal_text(toll)} gp"],
            )
            remaining -= delivered
            desired_dispatch = max(ZERO, remaining) / delivered_fraction
            route_remaining -= dispatched
            affordable_delivery -= delivered
    return consumed_now, future_delivery, receipts


def _clear_markets(month: _Month) -> None:
    stats: dict[tuple[str, str], dict[str, Decimal]] = {}
    for settlement in _records(month.scenario["settlements"], "settlements"):
        settlement_id = _text(settlement.get("id"), "settlement ID")
        for commodity_id in month.commodities:
            stats[(settlement_id, commodity_id)] = {
                "requested": ZERO,
                "consumed": ZERO,
                "opening_supply": sum(
                    (
                        _available_quantity(row, "market opening inventory")
                        for key, row in month.inventories.items()
                        if key[1] == settlement_id and key[2] == commodity_id
                        and (key[0],) not in month.banks
                    ),
                    ZERO,
                ),
            }
        for social_class in sorted(
            _records(settlement.get("classes"), "social classes"),
            key=lambda row: (_integer(row.get("priority", 100), "class priority"), _text(row.get("id"), "class ID")),
        ):
            class_id = _text(social_class.get("id"), "class ID")
            buyer = _text(social_class.get("household_account_id"), "household account")
            population = _decimal(month.populations[(settlement_id, class_id)].get("population"), "class population")
            for primary, per_person_raw in sorted(_mapping(social_class.get("basket"), "class basket").items()):
                requested = population * _decimal(per_person_raw, "basket quantity")
                primary_used, lines = _local_consumption(
                    month,
                    buyer=buyer,
                    settlement=settlement_id,
                    commodity=primary,
                    requested=requested,
                    stats=stats,
                    purpose=f"{class_id} household consumption",
                )
                equivalent = primary_used
                substitutions: list[dict[str, object]] = []
                for choice in _mapping(social_class.get("substitutions", {}), "substitutions").get(primary, []):
                    if equivalent >= requested:
                        break
                    option = _mapping(choice, "substitution choice")
                    alternative = _text(option.get("commodity_id"), "substitute commodity")
                    ratio = _decimal(option.get("ratio"), "substitution ratio")
                    alternative_needed = (requested - equivalent) * ratio
                    alternative_used, alternative_lines = _local_consumption(
                        month,
                        buyer=buyer,
                        settlement=settlement_id,
                        commodity=alternative,
                        requested=alternative_needed,
                        stats=stats,
                        purpose=f"substitute for {primary}",
                    )
                    equivalent += alternative_used / ratio
                    substitutions.append(
                        {
                            "commodity_id": alternative,
                            "ratio": ratio,
                            "quantity_consumed": alternative_used,
                            "primary_equivalent": alternative_used / ratio,
                            "sources": alternative_lines,
                        }
                    )
                current_shortage = max(ZERO, requested - equivalent)
                delivered_now, future, route_lines = _dispatch_routes(
                    month,
                    buyer=buyer,
                    destination=settlement_id,
                    commodity=primary,
                    quantity_needed=current_shortage,
                    purpose=f"{class_id} household consumption",
                    stats=stats,
                )
                equivalent += delivered_now
                shortage = max(ZERO, requested - equivalent)
                receipt = {
                    "demand_id": f"demand:{month.month}:{settlement_id}:{class_id}:{primary}",
                    "settlement_id": settlement_id,
                    "class_id": class_id,
                    "buyer_id": buyer,
                    "commodity_id": primary,
                    "population": population,
                    "per_person_quantity": _decimal(per_person_raw, "basket quantity"),
                    "requested_primary_equivalent": requested,
                    "consumed_primary_equivalent": equivalent,
                    "shortage_primary_equivalent": shortage,
                    "future_delivery": future,
                    "substitutions": substitutions,
                    "local_sources": lines,
                    "route_trades": [item["trade_id"] for item in route_lines],
                }
                month.market.append(receipt)
                month.event(
                    "consumption",
                    "class-consumption",
                    f"{class_id} households in {settlement_id} consumed {_decimal_text(equivalent)} of {_decimal_text(requested)} {primary}-equivalent.",
                    [f"population {_decimal_text(population)}", "class basket and substitution rules"],
                    [f"shortage {_decimal_text(shortage)}", f"future imports {_decimal_text(future)}"],
                )
                if shortage > ZERO:
                    month.decision(
                        f"shortage:{settlement_id}:{class_id}:{primary}",
                        f"Relieve {class_id} {primary} shortage",
                        f"{_decimal_text(shortage)} primary-equivalent went unmet after substitution.",
                        ["release reserves", "subsidize imports", "expand production", "change the class basket"],
                    )

    for demand in sorted(
        _records(month.scenario.get("market_demands", []), "business market demands"),
        key=lambda row: _text(row.get("id"), "market demand ID"),
    ):
        buyer = _text(demand.get("buyer_id"), "market buyer")
        settlement = _text(demand.get("settlement_id"), "market settlement")
        commodity = _text(demand.get("commodity_id"), "market commodity")
        requested = _decimal(demand.get("quantity"), "market demand quantity")
        used, sources = _local_consumption(
            month,
            buyer=buyer,
            settlement=settlement,
            commodity=commodity,
            requested=requested,
            stats=stats,
            purpose=_text(demand.get("purpose"), "market demand purpose"),
        )
        route_now, future, routes = _dispatch_routes(
            month,
            buyer=buyer,
            destination=settlement,
            commodity=commodity,
            quantity_needed=max(ZERO, requested - used),
            purpose=_text(demand.get("purpose"), "market demand purpose"),
            stats=stats,
        )
        month.market.append(
            {
                "demand_id": demand["id"],
                "settlement_id": settlement,
                "class_id": None,
                "buyer_id": buyer,
                "commodity_id": commodity,
                "requested_primary_equivalent": requested,
                "consumed_primary_equivalent": used + route_now,
                "shortage_primary_equivalent": max(ZERO, requested - used - route_now),
                "future_delivery": future,
                "substitutions": [],
                "local_sources": sources,
                "route_trades": [item["trade_id"] for item in routes],
            }
        )

    for key, row in sorted(month.prices.items()):
        settlement, commodity_id = key
        commodity = month.commodities[commodity_id]
        before = _decimal(row.get("price"), "price before")
        market_stats = stats[key]
        requested = market_stats["requested"]
        consumed = market_stats["consumed"]
        shortage_pressure = ZERO if requested == ZERO else max(ZERO, requested - consumed) / requested
        surplus = max(ZERO, market_stats["opening_supply"] - requested)
        surplus_pressure = ZERO if market_stats["opening_supply"] == ZERO else surplus / market_stats["opening_supply"]
        elasticity = _decimal(commodity.get("price_elasticity"), "price elasticity")
        factor = ONE + elasticity * shortage_pressure - elasticity * Decimal("0.25") * surplus_pressure
        factor += month.effect("price_pressure", settlement=settlement)
        after = before * max(Decimal("0.10"), factor)
        after = min(
            _decimal(commodity.get("max_price"), "maximum price"),
            max(_decimal(commodity.get("min_price"), "minimum price"), after),
        )
        row["price"] = after
        if after != before:
            month.event(
                "prices",
                "price-change",
                f"{commodity_id} at {settlement} moved from {_decimal_text(before)} to {_decimal_text(after)} gp/unit.",
                [f"requested {_decimal_text(requested)}", f"consumed {_decimal_text(consumed)}", f"opening supply {_decimal_text(market_stats['opening_supply'])}"],
                ["the new local price persists into the next state"],
            )


def _collect_obligations(month: _Month) -> None:
    agricultural_value: dict[tuple[str, str], Decimal] = {}
    for receipt in month.production:
        if receipt["kind"] != "agriculture":
            continue
        key = (str(receipt["entity_id"]), str(receipt["settlement_id"]))
        value = ZERO
        for commodity, quantity in sorted(
            _mapping(receipt["outputs"], "agricultural outputs").items()
        ):
            value += _decimal(quantity, "agricultural quantity") * _decimal(
                month.prices[(key[1], commodity)].get("price"), "agricultural price"
            )
        agricultural_value[key] = agricultural_value.get(key, ZERO) + value

    tenures = _records(month.scenario["tenures"], "tenures")
    total_acres: dict[tuple[str, str], Decimal] = {}
    for tenure in tenures:
        key = (
            _text(tenure.get("tenant_id"), "tenant"),
            _text(tenure.get("settlement_id"), "tenure settlement"),
        )
        total_acres[key] = total_acres.get(key, ZERO) + _decimal(
            tenure.get("acres"), "tenure acres"
        )

    for tenure in sorted(
        tenures,
        key=lambda row: _text(row.get("id"), "tenure ID"),
    ):
        tenure_id = _text(tenure.get("id"), "tenure ID")
        settlement = _text(tenure.get("settlement_id"), "tenure settlement")
        tenant = _text(tenure.get("tenant_id"), "tenant")
        gross_total = agricultural_value.get((tenant, settlement), ZERO)
        acres = _decimal(tenure.get("acres"), "tenure acres")
        tenant_acres = total_acres[(tenant, settlement)]
        gross = ZERO if tenant_acres == ZERO else gross_total * acres / tenant_acres
        tax_delta = month.effect("tax_rate_delta", settlement=settlement)
        charges = (
            ("rent", acres * _decimal(tenure.get("rent_per_acre"), "rent per acre"), _text(tenure.get("landlord_id"), "landlord")),
            ("feudal_due", gross * _rate(tenure.get("feudal_due_rate"), "feudal due rate"), _text(tenure.get("landlord_id"), "landlord")),
            ("tithe", gross * _rate(tenure.get("tithe_rate"), "tithe rate"), _text(tenure.get("church_id"), "church")),
            ("tax", gross * min(ONE, max(ZERO, _rate(tenure.get("tax_rate"), "tax rate") + tax_delta)), _text(tenure.get("treasury_id"), "treasury")),
        )
        for charge, raw_due, recipient in charges:
            due = raw_due.quantize(MONEY)
            paid = month.transfer(
                tenant,
                recipient,
                due,
                charge,
                f"{tenure_id} {charge} paid by {tenant}",
            )
            arrears = due - paid
            receipt = {
                "tenure_id": tenure_id,
                "settlement_id": settlement,
                "tenant_id": tenant,
                "recipient_id": recipient,
                "kind": charge,
                "assessment_base": gross,
                "due": due,
                "paid": paid,
                "arrears": arrears,
            }
            month.obligations.append(receipt)
            if arrears > ZERO:
                month.state["arrears"].append(
                    {
                        "arrears_id": f"arrears:{month.month}:{tenure_id}:{charge}",
                        "debtor_id": tenant,
                        "creditor_id": recipient,
                        "kind": charge,
                        "amount": arrears,
                        "origin_month": month.month,
                    }
                )
                month.decision(
                    f"arrears:{tenure_id}:{charge}",
                    f"Resolve {charge} arrears",
                    f"{tenant} could not pay {_decimal_text(arrears)} gp due under {tenure_id}.",
                    ["grant relief", "extend credit", "accept in-kind payment", "enforce the claim"],
                )
            month.event(
                "obligations",
                charge,
                f"{tenant} paid {_decimal_text(paid)} of {_decimal_text(due)} gp {charge}.",
                [
                    f"tenure {tenure_id}",
                    f"allocated agricultural assessment base {_decimal_text(gross)} gp of {_decimal_text(gross_total)} gp tenant output",
                ],
                [f"{recipient} received {_decimal_text(paid)} gp", f"arrears {_decimal_text(arrears)} gp"],
            )


def _withdraw_to_bank(
    month: _Month, borrower: str, bank_id: str, requested: Decimal
) -> dict[str, object]:
    """Move borrower funds to a creditor bank and expose the exact payment rail."""

    account = month.account(borrower)
    bank = month.banks[(bank_id,)]
    remaining = min(requested.quantize(MONEY), month.funds(borrower))
    cash = min(_decimal(account.get("cash", ZERO), "borrower cash"), remaining)
    account["cash"] = _decimal(account.get("cash", ZERO), "borrower cash") - cash
    bank["reserves"] = _decimal(bank.get("reserves"), "bank reserves") + cash
    remaining -= cash

    same_bank_deposit = ZERO
    external_deposit = ZERO
    source_bank_id: str | None = None
    if remaining > ZERO and _decimal(account.get("deposit", ZERO), "borrower deposit") > ZERO:
        source_bank_id = _text(account.get("bank_id"), "borrower bank")
        source_bank = month.banks[(source_bank_id,)]
        reserve_limit = remaining if source_bank_id == bank_id else min(
            remaining, _decimal(source_bank.get("reserves"), "source bank reserves")
        )
        deposit_paid = min(
            remaining,
            reserve_limit,
            _decimal(account.get("deposit", ZERO), "borrower deposit"),
        )
        account["deposit"] = _decimal(account.get("deposit", ZERO), "borrower deposit") - deposit_paid
        source_bank["deposit_liability"] = _decimal(
            source_bank.get("deposit_liability", ZERO), "source-bank deposit liability"
        ) - deposit_paid
        if source_bank_id == bank_id:
            same_bank_deposit = deposit_paid
        else:
            external_deposit = deposit_paid
            source_bank["reserves"] = _decimal(source_bank.get("reserves"), "source reserves") - deposit_paid
            bank["reserves"] = _decimal(bank.get("reserves"), "target reserves") + deposit_paid
        remaining -= deposit_paid
    return {
        "amount": cash + same_bank_deposit + external_deposit,
        "cash": cash,
        "same_bank_deposit": same_bank_deposit,
        "external_deposit": external_deposit,
        "source_bank_id": source_bank_id,
    }


def _loan_payment_postings(
    borrower: str,
    bank_id: str,
    receipt: Mapping[str, object],
    *,
    borrower_liability: str,
    bank_asset: str,
) -> list[tuple[str, Decimal, Decimal]]:
    amount = _decimal(receipt.get("amount"), "loan payment amount")
    cash = _decimal(receipt.get("cash"), "loan cash payment")
    same_bank = _decimal(receipt.get("same_bank_deposit"), "same-bank loan payment")
    external = _decimal(receipt.get("external_deposit"), "external-bank loan payment")
    postings: list[tuple[str, Decimal, Decimal]] = [
        (borrower_liability, amount, ZERO),
        (bank_asset, ZERO, amount),
    ]
    if cash:
        postings.extend(
            (
                (f"Assets:{bank_id}:Reserves", cash, ZERO),
                (f"Assets:{borrower}:Cash", ZERO, cash),
            )
        )
    if same_bank:
        postings.extend(
            (
                (f"Liabilities:{bank_id}:CustomerDeposits", same_bank, ZERO),
                (f"Assets:{borrower}:Deposit:{bank_id}", ZERO, same_bank),
            )
        )
    if external:
        source_bank_id = _text(receipt.get("source_bank_id"), "source bank")
        postings.extend(
            (
                (f"Assets:{bank_id}:Reserves", external, ZERO),
                (f"Liabilities:{source_bank_id}:CustomerDeposits", external, ZERO),
                (f"Assets:{source_bank_id}:Reserves", ZERO, external),
                (f"Assets:{borrower}:Deposit:{source_bank_id}", ZERO, external),
            )
        )
    return postings


def _release_pledge(month: _Month, loan: MutableMapping[str, object]) -> Decimal:
    """Release this loan's surviving collateral claim exactly once."""

    if loan.get("collateral_released") is True:
        return ZERO
    owner = _text(loan.get("collateral_owner_id"), "collateral owner")
    settlement = _text(loan.get("collateral_settlement_id"), "collateral settlement")
    commodity = _text(loan.get("collateral_commodity_id"), "collateral commodity")
    promised = _decimal(loan.get("collateral_quantity"), "collateral quantity")
    inventory = month.inventory(owner, settlement, commodity)
    pledged = _decimal(inventory.get("pledged_quantity", ZERO), "pledged collateral")
    released = min(promised, pledged)
    inventory["pledged_quantity"] = pledged - released
    loan["collateral_released"] = True
    loan["collateral_released_quantity"] = released
    if released < promised:
        shortfall = promised - released
        month.event(
            "banking",
            "collateral-impairment",
            f"Collateral available for {loan.get('loan_id')} was {_decimal_text(shortfall)} {commodity} below its original pledge.",
            ["pledged inventory spoiled or was otherwise impaired"],
            ["the creditor's realizable collateral claim fell"],
        )
        month.decision(
            f"collateral:{loan.get('loan_id')}",
            "Resolve impaired collateral",
            f"Only {_decimal_text(released)} of {_decimal_text(promised)} pledged {commodity} remains.",
            ["add replacement collateral", "restructure the exposure", "recognize the impairment"],
        )
    return released


def _service_loans(month: _Month) -> None:
    for loan in sorted(month.state["loans"], key=lambda row: _text(row.get("loan_id"), "loan ID")):
        if loan.get("status") not in {"performing", "delinquent"}:
            continue
        if _integer(loan.get("origin_month"), "loan origin month") >= month.month:
            continue
        loan_id = _text(loan.get("loan_id"), "loan ID")
        bank_id = _text(loan.get("bank_id"), "loan bank")
        borrower = _text(loan.get("borrower_id"), "loan borrower")
        bank = month.banks[(bank_id,)]
        principal_before = _decimal(loan.get("principal"), "loan principal")
        prior_interest = _decimal(loan.get("accrued_interest", ZERO), "loan accrued interest")
        new_interest = (
            principal_before
            * _rate(loan.get("annual_rate"), "loan annual rate")
            / Decimal(12)
        ).quantize(MONEY)
        if new_interest:
            loan["accrued_interest"] = prior_interest + new_interest
            bank["interest_receivable"] = _decimal(
                bank.get("interest_receivable", ZERO), "bank interest receivable"
            ) + new_interest
            bank["equity"] = _decimal(
                bank.get("equity", ZERO), "bank equity", minimum=None
            ) + new_interest
            month.book(
                "interest-accrual",
                f"Monthly interest on {loan_id}",
                (
                    (f"Assets:{bank_id}:InterestReceivable:{loan_id}", new_interest, ZERO),
                    (f"Income:{bank_id}:Interest", ZERO, new_interest),
                    (f"Expense:{borrower}:Interest", new_interest, ZERO),
                    (f"Liabilities:{borrower}:InterestPayable:{loan_id}", ZERO, new_interest),
                ),
            )
        interest_due = prior_interest + new_interest
        remaining_months = _integer(
            loan.get("remaining_months"), "remaining loan months"
        )
        principal_due = (
            principal_before
            if remaining_months <= 1
            else min(
                principal_before,
                _decimal(loan.get("scheduled_principal"), "scheduled principal"),
            )
        ).quantize(MONEY)
        interest_payment = _withdraw_to_bank(month, borrower, bank_id, interest_due)
        interest_paid = _decimal(interest_payment.get("amount"), "interest paid")
        if interest_paid:
            loan["accrued_interest"] = interest_due - interest_paid
            bank["interest_receivable"] = _decimal(
                bank.get("interest_receivable", ZERO), "bank interest receivable"
            ) - interest_paid
            month.book(
                "interest-payment",
                f"Interest payment on {loan_id}",
                _loan_payment_postings(
                    borrower,
                    bank_id,
                    interest_payment,
                    borrower_liability=f"Liabilities:{borrower}:InterestPayable:{loan_id}",
                    bank_asset=f"Assets:{bank_id}:InterestReceivable:{loan_id}",
                ),
            )
        else:
            loan["accrued_interest"] = interest_due
        principal_payment = _withdraw_to_bank(month, borrower, bank_id, principal_due)
        principal_paid = _decimal(principal_payment.get("amount"), "principal paid")
        if principal_paid:
            loan["principal"] = principal_before - principal_paid
            month.book(
                "principal-repayment",
                f"Principal repayment on {loan_id}",
                _loan_payment_postings(
                    borrower,
                    bank_id,
                    principal_payment,
                    borrower_liability=f"Liabilities:{borrower}:Loan:{loan_id}",
                    bank_asset=f"Assets:{bank_id}:Loans:{loan_id}",
                ),
            )
        shortfall = _decimal(loan.get("accrued_interest", ZERO), "unpaid interest") + (
            principal_due - principal_paid
        )
        ending_exposure = _decimal(loan.get("principal"), "ending principal") + _decimal(
            loan.get("accrued_interest", ZERO), "ending accrued interest"
        )
        shock_risk = min(ONE, max(ZERO, month.effect("default_risk_delta")))
        # A repaid exposure cannot be defaulted retroactively by a monthly
        # shock.  This guard also prevents zero-value collateral seizures and
        # contradictory repaid/defaulted receipts.
        shock_default = ending_exposure > ZERO and (
            _sample(month.seed, f"month:{month.month}:default:{loan_id}") < shock_risk
        )
        if shortfall > ZERO or shock_default:
            loan["missed_payments"] = _integer(loan.get("missed_payments", 0), "missed payments") + 1
            loan["status"] = "delinquent"
        else:
            loan["missed_payments"] = 0
            loan["remaining_months"] = max(0, _integer(loan.get("remaining_months"), "remaining loan months") - 1)
            loan["status"] = "performing"
            if (
                _decimal(loan.get("principal"), "ending principal") == ZERO
                and _decimal(loan.get("accrued_interest", ZERO), "ending accrued interest") == ZERO
            ):
                loan["status"] = "repaid"
                _release_pledge(month, loan)
        defaulted = _integer(loan.get("missed_payments", 0), "missed payments") >= _integer(
            loan.get("default_after_missed"), "default threshold", minimum=1
        )
        if defaulted:
            settlement = _text(loan.get("collateral_settlement_id"), "collateral settlement")
            commodity = _text(loan.get("collateral_commodity_id"), "collateral commodity")
            owner = _text(loan.get("collateral_owner_id"), "collateral owner")
            pledged = _release_pledge(month, loan)
            source = month.inventory(owner, settlement, commodity)
            principal_exposure = _decimal(loan.get("principal"), "default principal")
            interest_exposure = _decimal(
                loan.get("accrued_interest", ZERO), "default accrued interest"
            )
            exposure = principal_exposure + interest_exposure
            price = _decimal(month.prices[(settlement, commodity)].get("price"), "collateral price")
            haircut = _rate(loan.get("collateral_haircut"), "collateral haircut")
            net_unit_value = price * (ONE - haircut)
            quantity_needed = ZERO if net_unit_value == ZERO else exposure / net_unit_value
            seized = min(
                pledged,
                _decimal(source.get("quantity"), "collateral inventory"),
                quantity_needed,
            )
            source["quantity"] = _decimal(source.get("quantity"), "collateral inventory") - seized
            target = month.inventory(bank_id, settlement, commodity)
            target["quantity"] = _decimal(target.get("quantity"), "bank collateral inventory") + seized
            recovery = min(
                exposure,
                (seized * net_unit_value).quantize(MONEY),
            )
            target["collateral_carrying_value"] = _decimal(
                target.get("collateral_carrying_value", ZERO),
                "bank collateral inventory carrying value",
            ) + recovery
            loss = exposure - recovery
            loan["principal"] = ZERO
            loan["accrued_interest"] = ZERO
            loan["status"] = "defaulted"
            bank["collateral_assets"] = _decimal(
                bank.get("collateral_assets", ZERO), "bank collateral assets"
            ) + recovery
            bank["interest_receivable"] = _decimal(
                bank.get("interest_receivable", ZERO), "bank interest receivable"
            ) - interest_exposure
            bank["equity"] = _decimal(bank.get("equity", ZERO), "bank equity", minimum=None) - loss
            month.book(
                "loan-default",
                f"Default and collateral seizure on {loan_id}",
                (
                    (f"Assets:{bank_id}:Collateral:{loan_id}", recovery, ZERO),
                    (f"Expense:{bank_id}:CreditLoss", loss, ZERO),
                    (f"Assets:{bank_id}:Loans:{loan_id}", ZERO, principal_exposure),
                    (f"Assets:{bank_id}:InterestReceivable:{loan_id}", ZERO, interest_exposure),
                    (f"Liabilities:{borrower}:Loan:{loan_id}", principal_exposure, ZERO),
                    (f"Liabilities:{borrower}:InterestPayable:{loan_id}", interest_exposure, ZERO),
                    (
                        f"Income:{borrower}:DebtRelief:{loan_id}",
                        ZERO,
                        principal_exposure + interest_exposure,
                    ),
                ),
            )
            month.decision(
                f"default:{loan_id}",
                "Resolve loan default",
                f"{loan_id} defaulted; collateral recovered {_decimal_text(recovery)} gp against {_decimal_text(recovery+loss)} gp exposure.",
                ["restructure residual claims", "sell seized collateral", "recapitalize the bank", "pursue guarantors"],
            )
            month.event(
                "banking",
                "loan-default",
                f"{borrower} defaulted on {loan_id}; {bank_id} seized {_decimal_text(seized)} {commodity}.",
                [f"missed-payment threshold reached", f"shock default={shock_default}"],
                [f"collateral recovery {_decimal_text(recovery)} gp", f"credit loss {_decimal_text(loss)} gp"],
            )
        month.bank_receipts.append(
            {
                "loan_id": loan_id,
                "action": "serviced",
                "interest_brought_forward": prior_interest,
                "interest_accrued": new_interest,
                "interest_due": interest_due,
                "interest_paid": interest_paid,
                "interest_carried_forward": loan.get("accrued_interest", ZERO),
                "principal_due": principal_due,
                "principal_paid": principal_paid,
                "shortfall": shortfall,
                "status": loan.get("status"),
            }
        )


def _migrate(month: _Month) -> None:
    shortages: dict[tuple[str, str], Decimal] = {}
    for receipt in month.market:
        class_id = receipt.get("class_id")
        if class_id is None:
            continue
        requested = _decimal(receipt.get("requested_primary_equivalent"), "migration demand")
        shortage = _decimal(receipt.get("shortage_primary_equivalent"), "migration shortage")
        key = (str(receipt["settlement_id"]), str(class_id))
        ratio = ZERO if requested == ZERO else shortage / requested
        shortages[key] = max(shortages.get(key, ZERO), ratio)
    wages: dict[tuple[str, str], Decimal] = {}
    for receipt in month.labor_receipts:
        key = (str(receipt["settlement_id"]), str(receipt.get("class_id")))
        wages[key] = max(wages.get(key, ZERO), _decimal(receipt.get("wage_after"), "migration wage"))
    for link in sorted(
        _records(month.scenario["migration_links"], "migration links"),
        key=lambda row: _text(row.get("id"), "migration-link ID"),
    ):
        source = _text(link.get("origin"), "migration origin")
        destination = _text(link.get("destination"), "migration destination")
        class_id = _text(link.get("class_id"), "migrant class")
        source_key = (source, class_id)
        destination_key = (destination, class_id)
        if source_key not in month.populations or destination_key not in month.populations:
            raise EconomyError("migration link references an unknown settlement class")
        source_wage = wages.get(source_key, ZERO)
        destination_wage = wages.get(destination_key, ZERO)
        wage_pull = ZERO
        if destination_wage > source_wage:
            wage_pull = (destination_wage - source_wage) / max(Decimal("0.01"), source_wage)
        pressure = shortages.get(source_key, ZERO) * _decimal(link.get("shortage_weight"), "migration shortage weight")
        pressure += wage_pull * _decimal(link.get("wage_weight"), "migration wage weight")
        pressure += month.effect("migration_push", settlement=source)
        pressure -= _decimal(link.get("friction"), "migration friction")
        rate = min(_rate(link.get("max_rate"), "maximum migration rate"), max(ZERO, pressure))
        source_population = _decimal(month.populations[source_key].get("population"), "source population")
        migrants = source_population * rate
        if migrants <= ZERO:
            continue
        month.populations[source_key]["population"] = source_population - migrants
        month.populations[destination_key]["population"] = _decimal(
            month.populations[destination_key].get("population"), "destination population"
        ) + migrants
        occupation = _text(link.get("occupation"), "migrant occupation")
        source_pool = month.labor.get((source, occupation))
        destination_pool = month.labor.get((destination, occupation))
        if source_pool is not None and destination_pool is not None:
            worker_share = ZERO if source_population == ZERO else migrants / source_population
            source_workers = _decimal(source_pool.get("workers"), "source workers")
            workers_moving = source_workers * worker_share
            source_pool["workers"] = source_workers - workers_moving
            destination_pool["workers"] = _decimal(destination_pool.get("workers"), "destination workers") + workers_moving
            retained_share = ONE - worker_share
            source_pool["employed_worker_days"] = min(
                _decimal(
                    source_pool.get("employed_worker_days", ZERO),
                    "source employed worker-days",
                )
                * retained_share,
                _decimal(source_pool.get("workers"), "remaining source workers")
                * DAYS_PER_MONTH,
            )
            source_pool["employed_workers"] = min(
                _decimal(
                    source_pool.get("employed_workers", ZERO),
                    "source employed workers",
                )
                * retained_share,
                _decimal(source_pool.get("workers"), "remaining source workers"),
            )
        receipt = {
            "migration_id": _text(link.get("id"), "migration ID"),
            "origin": source,
            "destination": destination,
            "class_id": class_id,
            "occupation": occupation,
            "migrants": migrants,
            "rate": rate,
            "shortage_pressure": shortages.get(source_key, ZERO),
            "wage_pull": wage_pull,
        }
        month.migrations.append(receipt)
        month.event(
            "migration",
            "class-migration",
            f"{_decimal_text(migrants)} {class_id} people moved from {source} to {destination}.",
            [f"shortage pressure {_decimal_text(shortages.get(source_key, ZERO))}", f"wage pull {_decimal_text(wage_pull)}", f"migration rate {_decimal_text(rate)}"],
            ["settlement populations changed", f"{occupation} labour supply moved proportionally"],
        )


def _checks(month: _Month) -> dict[str, object]:
    closing = month._physical_totals()
    conservation: list[dict[str, object]] = []
    physical_ok = True
    for commodity in sorted(month.commodities):
        flows = month.physical.get(commodity, {})
        left = month.opening_physical.get(commodity, ZERO) + flows.get("produced", ZERO)
        right = closing.get(commodity, ZERO) + flows.get("production_inputs", ZERO)
        right += flows.get("consumed", ZERO) + flows.get("storage_spoilage", ZERO)
        right += flows.get("route_spoilage", ZERO)
        residual = left - right
        within_tolerance = abs(residual) <= CONSERVATION_TOLERANCE
        physical_ok = physical_ok and within_tolerance
        conservation.append(
            {
                "commodity_id": commodity,
                "opening_plus_produced": left,
                "closing_plus_uses_and_losses": right,
                "residual": residual,
                "tolerance": CONSERVATION_TOLERANCE,
                "within_tolerance": within_tolerance,
            }
        )
    inventory_invariants = all(
        ZERO
        <= _decimal(row.get("pledged_quantity", ZERO), "closing pledged inventory")
        <= _decimal(row.get("quantity"), "closing inventory")
        and _decimal(
            row.get("collateral_carrying_value", ZERO),
            "closing collateral carrying value",
        )
        >= ZERO
        for row in month.state["inventories"]
    )
    labor_invariants = all(
        _decimal(row.get("workers"), "closing workers") >= ZERO
        and ZERO
        <= _decimal(row.get("employed_workers", ZERO), "closing employed workers")
        <= _decimal(row.get("workers"), "closing workers")
        and ZERO
        <= _decimal(row.get("employed_worker_days", ZERO), "closing employed worker-days")
        <= _decimal(row.get("workers"), "closing workers") * DAYS_PER_MONTH
        for row in month.state["labor"]
    )
    nonnegative = inventory_invariants and labor_invariants and all(
        _decimal(row.get("cash", ZERO), "closing cash") >= ZERO
        and _decimal(row.get("deposit", ZERO), "closing deposit") >= ZERO
        for row in month.state["accounts"]
    ) and all(
        _decimal(row.get("reserves"), "closing bank reserves") >= ZERO
        and _decimal(row.get("deposit_liability", ZERO), "closing deposit liability") >= ZERO
        and _decimal(row.get("interest_receivable", ZERO), "closing interest receivable") >= ZERO
        for row in month.state["banks"]
    ) and all(
        _decimal(row.get("principal"), "closing loan principal") >= ZERO
        and _decimal(row.get("accrued_interest", ZERO), "closing accrued interest") >= ZERO
        for row in month.state["loans"]
    )
    total_debits = sum((_decimal(txn["debits"], "transaction debits") for txn in month.ledger), ZERO)
    total_credits = sum((_decimal(txn["credits"], "transaction credits") for txn in month.ledger), ZERO)
    deposit_checks = []
    reserve_ok = True
    deposits_reconcile = True
    interest_reconciles = True
    collateral_reconciles = True
    balance_sheets_balance = True
    banks_solvent = True
    for key, bank in sorted(month.banks.items()):
        bank_id = key[0]
        deposits = _bank_deposits(month, bank_id)
        recorded_deposits = _decimal(
            bank.get("deposit_liability", ZERO), "recorded deposit liability"
        )
        deposit_reconciles = recorded_deposits == deposits
        deposits_reconcile = deposits_reconcile and deposit_reconciles
        reserves = _decimal(bank.get("reserves"), "bank reserves")
        requirement = deposits * _rate(bank.get("reserve_ratio"), "bank reserve ratio")
        compliant = reserves >= requirement
        reserve_ok = reserve_ok and compliant
        active_principal = sum(
            (
                _decimal(loan.get("principal"), "active loan principal")
                for loan in month.state["loans"]
                if loan.get("bank_id") == bank_id
                and loan.get("status") in {"performing", "delinquent"}
            ),
            ZERO,
        )
        accrued_interest = sum(
            (
                _decimal(loan.get("accrued_interest", ZERO), "active accrued interest")
                for loan in month.state["loans"]
                if loan.get("bank_id") == bank_id
                and loan.get("status") in {"performing", "delinquent"}
            ),
            ZERO,
        )
        interest_receivable = _decimal(
            bank.get("interest_receivable", ZERO), "bank interest receivable"
        )
        interest_reconciles_for_bank = interest_receivable == accrued_interest
        interest_reconciles = interest_reconciles and interest_reconciles_for_bank
        collateral_assets = _decimal(
            bank.get("collateral_assets", ZERO), "bank collateral assets"
        )
        tagged_collateral = sum(
            (
                _decimal(
                    inventory.get("collateral_carrying_value", ZERO),
                    "tagged collateral inventory",
                )
                for inventory in month.state["inventories"]
                if inventory.get("owner_id") == bank_id
            ),
            ZERO,
        )
        collateral_reconciles_for_bank = collateral_assets == tagged_collateral
        collateral_reconciles = collateral_reconciles and collateral_reconciles_for_bank
        other_assets = _decimal(bank.get("other_assets", ZERO), "bank other assets")
        other_liabilities = _decimal(
            bank.get("other_liabilities", ZERO), "bank other liabilities"
        )
        equity = _decimal(bank.get("equity", ZERO), "bank equity", minimum=None)
        assets = reserves + active_principal + interest_receivable + collateral_assets + other_assets
        liabilities = recorded_deposits + other_liabilities
        balance_residual = assets - liabilities - equity
        balanced = abs(balance_residual) <= CONSERVATION_TOLERANCE
        balance_sheets_balance = balance_sheets_balance and balanced
        solvent = equity >= ZERO
        banks_solvent = banks_solvent and solvent
        deposit_checks.append(
            {
                "bank_id": bank_id,
                "depositor_balances": deposits,
                "deposit_liability": recorded_deposits,
                "deposit_liability_reconciles": deposit_reconciles,
                "reserves": reserves,
                "required_reserves": requirement,
                "reserve_compliant": compliant,
                "active_loan_principal": active_principal,
                "accrued_interest_on_loans": accrued_interest,
                "interest_receivable": interest_receivable,
                "interest_receivable_reconciles": interest_reconciles_for_bank,
                "collateral_assets": collateral_assets,
                "tagged_collateral_inventory": tagged_collateral,
                "collateral_assets_reconcile": collateral_reconciles_for_bank,
                "other_assets": other_assets,
                "other_liabilities": other_liabilities,
                "assets": assets,
                "liabilities": liabilities,
                "equity": equity,
                "balance_sheet_residual": balance_residual,
                "balance_sheet_balanced": balanced,
                "solvent": solvent,
            }
        )
        if not compliant:
            month.decision(
                f"reserves:{bank_id}",
                "Restore bank reserves",
                f"{bank_id} holds {_decimal_text(reserves)} against {_decimal_text(requirement)} required.",
                ["call loans", "raise capital", "borrow reserves", "restrict withdrawals"],
            )
        if not solvent:
            month.decision(
                f"solvency:{bank_id}",
                "Recapitalize insolvent bank",
                f"{bank_id} has negative equity of {_decimal_text(-equity)} gp.",
                ["inject capital", "write down liabilities", "restructure or resolve the bank"],
            )
    ledger_ok = total_debits == total_credits and all(
        _decimal(txn["debits"], "transaction debits") == _decimal(txn["credits"], "transaction credits")
        for txn in month.ledger
    )
    return {
        "physical_conservation": physical_ok,
        "physical_receipts": conservation,
        "nonnegative_balances": nonnegative,
        "inventory_pledges_valid": inventory_invariants,
        "labor_employment_valid": labor_invariants,
        "ledger_balanced": ledger_ok,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "deposit_liabilities_reconcile": deposits_reconcile,
        "interest_receivables_reconcile": interest_reconciles,
        "collateral_assets_reconcile": collateral_reconciles,
        "bank_balance_sheets_balance": balance_sheets_balance,
        "banks_solvent": banks_solvent,
        "bank_reserves_compliant": reserve_ok,
        "bank_checks": deposit_checks,
        "notion_writes": 0,
        "canonical_ledger_postings": 0,
        "campaign_advanced": False,
    }


LIMITATIONS = (
    "The scenario remains explicitly non-canonical and cannot advance campaign time.",
    "Population is aggregated by settlement and social class, not simulated as individuals.",
    "Production recipes use fixed coefficients; capital depreciation and firm entry are not modeled.",
    "Markets clear deterministically by priority and landed cost rather than strategic bidding.",
    "Credit uses one collateral pledge per loan and no secondary securities market.",
    "Seized bank collateral is held and impaired in this slice; liquidation requires an explicit future phase.",
    "Migration is an aggregate pressure response, not household-level pathfinding.",
)


def run_month(
    scenario: Mapping[str, object],
    state: Mapping[str, object],
    seed: str,
) -> dict[str, object]:
    """Run one complete deterministic, non-canonical regional month.

    The exact same scenario, sealed state, and seed produce byte-identical
    canonical JSON.  The returned result and state contain only JSON-safe values.
    """

    validate_scenario(scenario)
    _text(seed, "deterministic seed")
    with localcontext(_context()):
        normalized = _normalize_state(state, scenario)
        opening_hash = state_hash(state)
        month = _Month(scenario, normalized, seed)
        _apply_shocks(month)
        _process_arrivals(month)
        _originate_credit(month)
        _produce(month)
        _apply_storage_spoilage(month)
        _clear_markets(month)
        _collect_obligations(month)
        _service_loans(month)
        _migrate(month)
        checks = _checks(month)
        required_checks = (
            "physical_conservation",
            "nonnegative_balances",
            "ledger_balanced",
            "deposit_liabilities_reconcile",
            "interest_receivables_reconcile",
            "collateral_assets_reconcile",
            "bank_balance_sheets_balance",
        )
        failed_checks = [name for name in required_checks if not checks[name]]
        if failed_checks:
            residuals = [
                f"{row['commodity_id']}={_decimal_text(_decimal(row['residual'], 'physical residual', minimum=None))}"
                for row in checks["physical_receipts"]
                if not row["within_tolerance"]
            ]
            detail = f"; physical residuals: {', '.join(residuals)}" if residuals else ""
            raise EconomyError(f"month failed checks: {', '.join(failed_checks)}{detail}")
        month.state["month"] = month.month
        for field, keys in (
            ("populations", ("settlement_id", "class_id")),
            ("accounts", ("entity_id",)),
            ("inventories", ("owner_id", "settlement_id", "commodity_id")),
            ("labor", ("settlement_id", "occupation")),
            ("banks", ("bank_id",)),
            ("loans", ("loan_id",)),
            ("prices", ("settlement_id", "commodity_id")),
            ("in_transit", ("shipment_id",)),
            ("arrears", ("arrears_id",)),
            ("pending_operations", ("operation_id",)),
        ):
            month.state[field] = sorted(
                month.state[field], key=lambda row, sort_keys=keys: tuple(str(row.get(key, "")) for key in sort_keys)
            )
        next_state = dict(_json_safe(month.state))
        next_state["state_hash"] = state_hash(next_state)
        result: dict[str, object] = {
            "schema": RESULT_SCHEMA,
            "scenario_id": scenario["scenario_id"],
            "scenario_hash": state_hash(scenario),
            "canonical": False,
            "month": month.month,
            "source_refs": list(scenario["source_refs"]),
            "input_state_hash": opening_hash,
            "next_state_hash": next_state["state_hash"],
            "seed_fingerprint": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "shocks": month.shocks,
            "production": month.production,
            "labor": month.labor_receipts,
            "market": month.market,
            "trade": month.trades,
            "route_usage": [
                {"route_id": route_id, "dispatched_quantity": quantity}
                for route_id, quantity in sorted(month.route_usage.items())
            ],
            "land_and_fiscal_obligations": month.obligations,
            "banking": month.bank_receipts,
            "migration": month.migrations,
            "ledger": month.ledger,
            "events": month.events,
            "available_decisions": month.decisions,
            # Monthly simulation has no authority to assert played canon.  The
            # sealed dormant templates remain in next_state, while the public
            # result exposes only operations whose explicit context gate was
            # matched by the caller.  With no context, this must be empty.
            "pending_operations": surface_pending_operations(
                month.state["pending_operations"], None
            ),
            "checks": checks,
            "limitations": list(LIMITATIONS),
        }
        result["report_markdown"] = render_report(_json_safe(result))
        safe_result = dict(_json_safe(result))
        safe_result["result_hash"] = state_hash(safe_result)
        return {"result": safe_result, "next_state": next_state}


def render_report(result: Mapping[str, object]) -> str:
    """Render a self-contained, campaign-readable Markdown month report."""

    title = f"# Regional Economy — Month {result.get('month')} (PREVIEW — NOT CANON)"
    lines = [
        title,
        "",
        "This source-bound preview made **zero Notion writes**, posted **zero canonical ledger entries**, and did **not** advance campaign time.",
        "",
        "## What changed, where, and why",
        "",
    ]
    events = result.get("events", [])
    if isinstance(events, list) and events:
        for event in events:
            if not isinstance(event, Mapping):
                continue
            causes = "; ".join(str(value) for value in event.get("causes", []))
            effects = "; ".join(str(value) for value in event.get("effects", []))
            lines.append(f"- **{event.get('phase')} — {event.get('summary')}** Cause: {causes}. Effect: {effects}.")
    else:
        lines.append("- No economic event was resolved.")
    operations = result.get("pending_operations", [])
    if isinstance(operations, list) and operations:
        lines.extend(["", "## Pending campaign operations", ""])
        for operation in operations:
            if not isinstance(operation, Mapping):
                continue
            lines.append(
                f"- **{operation.get('title')}** — {operation.get('status')}. "
                f"Boot: {operation.get('boot_trigger')}. Play: {operation.get('play_trigger')}."
            )
            authority = operation.get("decision_authority", {})
            if isinstance(authority, Mapping):
                lines.append(
                    f"- **Authority lock:** {authority.get('holder')}; automatic execution, "
                    f"campaign advancement, and Notion writing are all disabled."
                )
            for request in operation.get("required_fact_requests", []):
                if not isinstance(request, Mapping):
                    continue
                lines.append(
                    f"- **Fact required — {request.get('location')}:** "
                    f"{request.get('question')} Owner: {request.get('owner')}; "
                    f"due: {request.get('due')}; status: {request.get('status')}."
                )
            for gate in operation.get("decision_gates", []):
                if not isinstance(gate, Mapping):
                    continue
                options = "; ".join(str(value) for value in gate.get("options", []))
                lines.append(
                    f"- **Decision gate:** {gate.get('decision')} Authority: "
                    f"{gate.get('authority')}; when: {gate.get('when')}. Options: {options}."
                )
    lines.extend(["", "## Available decisions", ""])
    decisions = result.get("available_decisions", [])
    if isinstance(decisions, list) and decisions:
        for decision in decisions:
            if not isinstance(decision, Mapping):
                continue
            options = "; ".join(str(value) for value in decision.get("options", []))
            lines.append(f"- **{decision.get('summary')}** — {decision.get('reason')} Options: {options}.")
    else:
        lines.append("- No intervention threshold fired this month.")
    checks = _mapping(result.get("checks", {}), "report checks")
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Physical conservation: **{'PASS' if checks.get('physical_conservation') else 'FAIL'}**",
            f"- Balanced economic ledger: **{'PASS' if checks.get('ledger_balanced') else 'FAIL'}**",
            f"- Nonnegative balances: **{'PASS' if checks.get('nonnegative_balances') else 'FAIL'}**",
            f"- Deposit reconciliation: **{'PASS' if checks.get('deposit_liabilities_reconcile') else 'FAIL'}**",
            f"- Collateral-asset reconciliation: **{'PASS' if checks.get('collateral_assets_reconcile') else 'FAIL'}**",
            f"- Bank balance sheets: **{'PASS' if checks.get('bank_balance_sheets_balance') else 'FAIL'}**",
            f"- Bank solvency: **{'PASS' if checks.get('banks_solvent') else 'ACTION REQUIRED'}**",
            f"- Bank reserve compliance: **{'PASS' if checks.get('bank_reserves_compliant') else 'ACTION REQUIRED'}**",
            "",
            "## Limits",
            "",
        ]
    )
    for limitation in result.get("limitations", LIMITATIONS):
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


__all__ = [
    "EconomyError",
    "LIMITATIONS",
    "PLAYED_CONTEXT_SCHEMA",
    "canonical_json",
    "initial_state",
    "load_played_context",
    "load_scenario",
    "render_report",
    "run_month",
    "state_hash",
    "surface_pending_operations",
    "validate_played_context",
    "validate_scenario",
]
