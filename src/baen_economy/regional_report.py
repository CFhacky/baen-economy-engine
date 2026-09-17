"""Human-readable, self-contained report for a committed regional month.

The SQLite database and JSON artifacts are durable machine state.  This module
turns that state into the part an operator can actually read: one static HTML
file with no scripts, remote assets, Notion access, or canonical-ledger access.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from html import escape
from pathlib import Path
from typing import Mapping, Sequence


REPORT_SCHEMA = "tnp.economy.regional-html-report/1"


def default_report_path(database: Path, period: int) -> Path:
    """Return the obvious, double-clickable report path beside the database."""

    return database.resolve().with_name(
        f"{database.stem}-Month-{period}-Report.html"
    )


def render_month_html(payload: Mapping[str, object]) -> str:
    """Render a complete monthly report from a CLI run/report envelope."""

    result = _mapping(
        payload.get("latest_result", payload.get("result")), "monthly result"
    )
    scenario = _optional_mapping(payload.get("scenario"))
    state = _optional_mapping(payload.get("state"))
    period = int(payload.get("period", result.get("period", 0)))

    business_names = _name_lookup(scenario, "businesses", "entity_id")
    site_names = _name_lookup(scenario, "sites", "site_id")
    commodity_names = _name_lookup(scenario, "commodities", "commodity_id")

    production = _optional_mapping(result.get("production"))
    labor = _optional_mapping(result.get("labor"))
    transport = _optional_mapping(result.get("transport"))
    market = _optional_mapping(result.get("market"))
    banking = _optional_mapping(result.get("banking"))
    treasury = _optional_mapping(result.get("treasury"))
    journal = _optional_mapping(result.get("journal"))

    production_runs = _records(production.get("runs"))
    labor_rows = _records(labor.get("details"))
    route_rows = _records(transport.get("route_usage"))
    demand_rows = _records(market.get("demand_receipts"))
    loss_rows = _records(market.get("storage_loss_receipts"))

    active_businesses = sum(
        1 for row in production_runs if _decimal(row.get("output_produced")) > 0
    )
    shortages = [row for row in demand_rows if _decimal(row.get("shortage_quantity")) > 0]
    shortage_markets = len(shortages)
    journal_balanced = journal.get("balanced") is True

    finance_state = _optional_mapping(_optional_mapping(state.get("finance")).get("finance_state"))
    finance_reports = _optional_mapping(_optional_mapping(state.get("finance")).get("reports"))
    entity_reports = _records(finance_reports.get("entities"))
    balance_sheet = _optional_mapping(finance_reports.get("balance_sheet"))
    cash_flow = _optional_mapping(finance_reports.get("cash_flow"))

    title = f"Baen Regional Economy — Month {period}"
    warning = str(
        scenario.get(
            "warning",
            "This is a noncanonical preview. It does not advance campaign state.",
        )
    )

    highlights = _highlights(
        production_runs,
        demand_rows,
        route_rows,
        business_names,
        site_names,
        commodity_names,
        banking,
        treasury,
    )

    production_table = _table(
        ("Business", "Operation", "Completed / planned", "Inputs", "Outputs", "Workers", "Payroll", "Constraint"),
        [
            (
                _label(row.get("entity_id"), business_names),
                _human_id(row.get("recipe_id")),
                f"{_qty(row.get('actual_batches'))} / {_qty(row.get('requested_batches'))}",
                _amount_list(row.get("inputs"), commodity_names),
                _amount_list(row.get("outputs"), commodity_names),
                _qty(row.get("workers")),
                _money(row.get("payroll")),
                _constraints(row.get("limiting_factors")),
            )
            for row in production_runs
        ],
        "No production receipts were stored for this month.",
    )

    labor_table = _table(
        ("Business", "Work", "Workers", "Worker-days", "Daily wage", "Payroll"),
        [
            (
                _label(row.get("entity_id"), business_names),
                _title(str(row.get("labor_class", "—"))),
                _qty(row.get("workers")),
                _qty(row.get("worker_days")),
                _money(row.get("wage_gp_per_day")),
                _money(row.get("payroll")),
            )
            for row in labor_rows
        ],
        "No labour receipts were stored for this month.",
    )

    route_table = _table(
        ("Route", "Commodity", "From → to", "Dispatched", "Delivered", "Lost", "Capacity used", "Cost", "Arrival"),
        [
            (
                _human_id(row.get("route_id")),
                _label(row.get("commodity_id"), commodity_names),
                f"{_label(row.get('origin_site_id'), site_names)} → {_label(row.get('destination_site_id'), site_names)}",
                _qty_with_unit(row.get("quantity_moved"), row.get("commodity_id"), scenario),
                _qty_with_unit(row.get("expected_delivered_quantity"), row.get("commodity_id"), scenario),
                _qty_with_unit(row.get("expected_loss_quantity"), row.get("commodity_id"), scenario),
                _capacity(row.get("quantity_moved"), row.get("capacity")),
                _money(row.get("transport_cost_gp")),
                _arrival(row, period),
            )
            for row in route_rows
        ],
        "No route receipts were stored for this month.",
    )

    market_table = _table(
        ("Buyer", "Market", "Commodity", "Demand", "Supplied", "Shortfall", "Price before → after", "Result"),
        [
            (
                _label(row.get("buyer_entity_id"), business_names),
                _label(row.get("site_id"), site_names),
                _label(row.get("commodity_id"), commodity_names),
                _qty_with_unit(row.get("requested_quantity"), row.get("commodity_id"), scenario),
                _qty_with_unit(row.get("consumed_quantity"), row.get("commodity_id"), scenario),
                _qty_with_unit(row.get("shortage_quantity"), row.get("commodity_id"), scenario),
                f"{_price(row.get('price_before_gp_per_unit'))} → {_price(row.get('price_after_gp_per_unit'))}",
                _title(str(row.get("disposition", "—"))),
            )
            for row in demand_rows
        ],
        "No market-demand receipts were stored for this month.",
    )

    storage_table = _table(
        ("Owner", "Site", "Commodity", "Opening", "Loss rate", "Lost", "After storage"),
        [
            (
                _label(row.get("owner_id"), business_names),
                _label(row.get("site_id"), site_names),
                _label(row.get("commodity_id"), commodity_names),
                _qty_with_unit(row.get("opening_quantity"), row.get("commodity_id"), scenario),
                _percent(row.get("storage_loss_rate")),
                _qty_with_unit(row.get("storage_loss_quantity"), row.get("commodity_id"), scenario),
                _qty_with_unit(row.get("closing_before_trade_quantity"), row.get("commodity_id"), scenario),
            )
            for row in loss_rows
        ],
        "No perishable storage losses were recorded.",
    )

    entity_table = _table(
        ("Entity", "Type", "Income", "Expenses", "Net result", "Assets", "Liabilities"),
        [
            (
                _label(row.get("entity_id"), business_names),
                _title(str(row.get("entity_type", "—"))),
                _money(row.get("income")),
                _money(row.get("expenses")),
                _money(row.get("net_income")),
                _money(row.get("assets")),
                _money(row.get("liabilities")),
            )
            for row in entity_reports
        ],
        "Entity-level financial statements were not available.",
    )

    balance_table = _table(
        ("Measure", "Amount"),
        [
            ("Assets", _money(balance_sheet.get("assets"))),
            ("Liabilities", _money(balance_sheet.get("liabilities"))),
            ("Equity", _money(balance_sheet.get("equity"))),
            ("Income", _money(balance_sheet.get("income"))),
            ("Expenses", _money(balance_sheet.get("expenses"))),
            ("Net income", _money(balance_sheet.get("net_income"))),
            ("Accounting imbalance", _money(balance_sheet.get("equation_imbalance"))),
        ] if balance_sheet else [],
        "A regional balance sheet was not available.",
    )

    cashflow_table = _table(
        ("Measure", "Amount"),
        [
            ("Opening settlement cash", _money(cash_flow.get("opening_settlement_cash"))),
            ("Operating cash flow", _money(cash_flow.get("operating"))),
            ("Financing cash flow", _money(cash_flow.get("financing"))),
            ("Treasury cash flow", _money(cash_flow.get("treasury"))),
            ("Net change", _money(cash_flow.get("net_change"))),
            ("Ending settlement cash", _money(cash_flow.get("ending_settlement_cash"))),
            ("Reconciles", "Yes" if cash_flow.get("reconciles") is True else "No"),
        ] if cash_flow else [],
        "A regional cash-flow statement was not available.",
    )

    source_hash = str(payload.get("state_hash", payload.get("next_state_hash", "—")))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="{REPORT_SCHEMA}">
  <title>{escape(title)}</title>
  <style>
    :root {{ --ink:#211b16; --muted:#6d6258; --paper:#f5efe3; --panel:#fffaf0; --line:#d6c6a9; --red:#8f2d2d; --green:#2f684b; --gold:#9b6a1b; --blue:#315c72; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font:15px/1.5 Georgia, "Times New Roman", serif; }}
    header {{ padding:38px max(24px, calc((100vw - 1240px)/2)); background:#211b16; color:#fffaf0; border-bottom:5px solid var(--gold); }}
    h1 {{ margin:0 0 8px; font-size:clamp(30px, 5vw, 54px); line-height:1.05; font-weight:600; }}
    h2 {{ margin:34px 0 12px; padding-bottom:8px; border-bottom:2px solid var(--line); font-size:27px; }}
    h3 {{ margin:22px 0 8px; font-size:20px; }}
    p {{ max-width:82ch; }}
    main {{ max-width:1240px; margin:auto; padding:28px 24px 60px; }}
    .eyebrow {{ margin:0 0 8px; color:#d9b56f; letter-spacing:.14em; text-transform:uppercase; font:700 12px/1.2 Arial, sans-serif; }}
    .subtitle {{ margin:0; color:#ded3c1; font-size:17px; }}
    .badges {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }}
    .badge {{ padding:6px 10px; border:1px solid #8d7d68; border-radius:999px; font:700 12px/1 Arial, sans-serif; }}
    .badge.warn {{ background:var(--red); border-color:#c16a62; }}
    .badge.good {{ background:var(--green); border-color:#6ea184; }}
    .notice {{ margin:0 0 24px; padding:16px 18px; background:#fff4d7; border-left:5px solid var(--gold); box-shadow:0 1px 3px #0001; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:18px 0 28px; }}
    .card {{ min-height:112px; padding:16px; background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 2px 8px #3323120d; }}
    .card .label {{ color:var(--muted); font:700 11px/1.2 Arial, sans-serif; letter-spacing:.08em; text-transform:uppercase; }}
    .card .value {{ display:block; margin-top:8px; font-size:25px; line-height:1.1; font-variant-numeric:tabular-nums; }}
    .card .detail {{ display:block; margin-top:6px; color:var(--muted); font-size:13px; }}
    .highlights {{ margin:0; padding:0; list-style:none; display:grid; gap:8px; }}
    .highlights li {{ padding:11px 14px 11px 38px; position:relative; background:#fffaf0; border:1px solid var(--line); border-radius:6px; }}
    .highlights li::before {{ content:"◆"; position:absolute; left:14px; color:var(--gold); }}
    .table-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:7px; background:var(--panel); }}
    table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
    th {{ background:#3a3027; color:#fffaf0; text-align:left; font:700 12px/1.25 Arial,sans-serif; letter-spacing:.03em; }}
    th, td {{ padding:10px 11px; border-bottom:1px solid #e4d8c3; vertical-align:top; }}
    tbody tr:nth-child(even) {{ background:#fbf4e7; }}
    tbody tr:last-child td {{ border-bottom:0; }}
    .empty {{ padding:18px; color:var(--muted); font-style:italic; }}
    .split {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:18px; }}
    .integrity {{ padding:18px; border:2px solid {var_color(journal_balanced)}; border-radius:8px; background:{var_background(journal_balanced)}; }}
    code {{ font:12px/1.4 Consolas, monospace; overflow-wrap:anywhere; }}
    footer {{ margin-top:40px; padding-top:18px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    @media print {{ body {{ background:white; }} header {{ padding:24px; }} main {{ padding:20px 0; }} .card,.table-wrap,.notice {{ box-shadow:none; }} h2 {{ break-after:avoid; }} table {{ break-inside:auto; }} tr {{ break-inside:avoid; }} }}
  </style>
</head>
<body>
  <header>
    <p class="eyebrow">The New Path · Regional Economy Preview</p>
    <h1>{escape(title)}</h1>
    <p class="subtitle">A readable operating report generated from the committed simulation state.</p>
    <div class="badges">
      <span class="badge warn">PREVIEW — NOT CANON</span>
      <span class="badge">Notion writes: 0</span>
      <span class="badge">Canonical ledger postings: 0</span>
      <span class="badge {'good' if journal_balanced else 'warn'}">Journal {'balanced' if journal_balanced else 'not balanced'}</span>
    </div>
  </header>
  <main>
    <div class="notice"><strong>Authority boundary.</strong> {escape(warning)} Opening money, recipes, quantities, routes, prices, loss rates, and banking rules shown here remain preview assumptions unless separately accepted into campaign canon.</div>

    <section aria-labelledby="overview">
      <h2 id="overview">Month at a glance</h2>
      <div class="cards">
        {_card("Active producers", str(active_businesses), f"of {len(production_runs)} operating receipts")}
        {_card("Workforce used", _qty(labor.get("workers")), f"Payroll {_money(labor.get('payroll'))}")}
        {_card("Routes used", str(len(route_rows)), "Same-month and in-transit movements")}
        {_card("Markets short", str(shortage_markets), f"of {len(demand_rows)} demand receipts")}
        {_card("Bank deposits", _money(banking.get("ending_customer_deposits")), f"Change {_money(banking.get('deposit_change'))}")}
        {_card("Treasury cash", _money(treasury.get("ending_cash")), f"Receipts {_money(treasury.get('receipts_total'))}")}
      </div>
      <h3>What happened</h3>
      <ul class="highlights">{''.join(f'<li>{escape(item)}</li>' for item in highlights)}</ul>
    </section>

    <section aria-labelledby="production"><h2 id="production">Production and labour</h2>{production_table}<h3>Labour detail</h3>{labor_table}</section>
    <section aria-labelledby="transport"><h2 id="transport">Transport and losses</h2>{route_table}<h3>Storage loss</h3>{storage_table}</section>
    <section aria-labelledby="markets"><h2 id="markets">Demand, shortages, and prices</h2>{market_table}</section>

    <section aria-labelledby="finance">
      <h2 id="finance">Business, banking, and treasury</h2>
      <div class="cards">
        {_card("Loans originated", _money(banking.get("loan_originations")), f"Outstanding {_money(banking.get('ending_gross_loans'))}")}
        {_card("Interest accrued", _money(banking.get("interest_accrued")), f"Principal repaid {_money(banking.get('principal_repaid'))}")}
        {_card("Tax assessed", _money(treasury.get("tax_assessed")), f"Received {_money(treasury.get('tax_receipts'))}")}
        {_card("Default exposure", _money(banking.get("default_exposure")), "Preview loan portfolio")}
      </div>
      <p><strong>Interpretation:</strong> deposits are bank liabilities; loan principal is not revenue; principal repayment is separate from interest; tax assessment and receipt remain separately traceable.</p>
      <h3>Entity statements</h3>{entity_table}
      <div class="split"><div><h3>Regional balance sheet</h3>{balance_table}</div><div><h3>Regional cash flow</h3>{cashflow_table}</div></div>
    </section>

    <section aria-labelledby="integrity">
      <h2 id="integrity">Accounting and safety check</h2>
      <div class="integrity">
        <strong>{'PASS — journal balances exactly.' if journal_balanced else 'FAIL — journal does not balance.'}</strong>
        <p>{_qty(journal.get('transaction_count'))} transactions · {_qty(journal.get('posting_count'))} postings · debits {_money(journal.get('total_debits'))} · credits {_money(journal.get('total_credits'))} · imbalance {_money(journal.get('imbalance'))}</p>
        <p>Notion writes: <strong>{escape(str(result.get('notion_writes', 0)))}</strong>. Canonical campaign-ledger postings: <strong>{escape(str(result.get('canonical_ledger_postings', 0)))}</strong>.</p>
      </div>
    </section>

    <footer>
      <p>Scenario: <code>{escape(str(payload.get('scenario_id', result.get('scenario_id', '—'))))}</code><br>Period: {period}<br>State hash: <code>{escape(source_hash)}</code><br>Report schema: <code>{REPORT_SCHEMA}</code></p>
      <p>The SQLite database remains the machine-readable audit trail. This HTML file is the human-readable operating view.</p>
    </footer>
  </main>
</body>
</html>
"""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _optional_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _records(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _name_lookup(
    scenario: Mapping[str, object], collection: str, id_key: str
) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in _records(scenario.get(collection)):
        identifier = row.get(id_key)
        name = row.get("name")
        if isinstance(identifier, str) and isinstance(name, str) and name.strip():
            result[identifier] = name
    return result


def _commodity_unit(scenario: Mapping[str, object], commodity_id: object) -> str:
    for row in _records(scenario.get("commodities")):
        if row.get("commodity_id") == commodity_id:
            return str(row.get("unit", "unit"))
    return "unit"


def _label(identifier: object, names: Mapping[str, str]) -> str:
    if isinstance(identifier, str) and identifier in names:
        return names[identifier]
    return _human_id(identifier)


def _human_id(value: object) -> str:
    if value is None:
        return "—"
    text = str(value)
    tail = text.split(":")[-1].replace("-", " ").replace("_", " ")
    words = [word.upper() if word.lower() in {"hq", "ncf", "gp"} else word.capitalize() for word in tail.split()]
    return " ".join(words) or "—"


def _title(value: str) -> str:
    return " ".join(word.upper() if word.lower() in {"hq", "ncf", "gp"} else word.capitalize() for word in value.replace("_", " ").split())


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)
    return result if result.is_finite() else Decimal(0)


def _formatted(value: object, places: int, *, suffix: str = "") -> str:
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        return "—"
    quantum = Decimal(1).scaleb(-places)
    number = number.quantize(quantum, rounding=ROUND_HALF_EVEN)
    rendered = f"{number:,.{places}f}"
    if places:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered == "-0":
        rendered = "0"
    return rendered + suffix


def _qty(value: object) -> str:
    return _formatted(value, 4)


def _money(value: object) -> str:
    rendered = _formatted(value, 2)
    return "—" if rendered == "—" else f"{rendered} GP"


def _price(value: object) -> str:
    rendered = _formatted(value, 4)
    return "—" if rendered == "—" else f"{rendered} GP/unit"


def _percent(value: object) -> str:
    return _formatted(_decimal(value) * 100, 2, suffix="%")


def _qty_with_unit(
    value: object, commodity_id: object, scenario: Mapping[str, object]
) -> str:
    return f"{_qty(value)} {_commodity_unit(scenario, commodity_id)}"


def _capacity(moved: object, capacity: object) -> str:
    cap = _decimal(capacity)
    if cap <= 0:
        return "—"
    return f"{_qty(moved)} / {_qty(capacity)} ({_formatted(_decimal(moved) / cap * 100, 1, suffix='%')})"


def _arrival(row: Mapping[str, object], period: int) -> str:
    arrival = int(_decimal(row.get("arrival_period_index")))
    if row.get("movement_kind") == "same_month_handling" or arrival <= period:
        return f"Month {period} — delivered"
    return f"Month {arrival} — in transit"


def _amount_list(value: object, commodity_names: Mapping[str, str]) -> str:
    rows = _records(value)
    if not rows:
        return "None"
    return "; ".join(
        f"{_qty(row.get('quantity'))} {_label(row.get('commodity_id'), commodity_names)}"
        for row in rows
    )


def _constraints(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return "None"
    items = [_human_id(item) for item in value]
    return ", ".join(items) if items else "None"


def _highlights(
    production: Sequence[Mapping[str, object]],
    demands: Sequence[Mapping[str, object]],
    routes: Sequence[Mapping[str, object]],
    businesses: Mapping[str, str],
    sites: Mapping[str, str],
    commodities: Mapping[str, str],
    banking: Mapping[str, object],
    treasury: Mapping[str, object],
) -> list[str]:
    lines: list[str] = []
    for row in production:
        outputs = _records(row.get("outputs"))
        if not outputs:
            continue
        produced = ", ".join(
            f"{_qty(item.get('quantity'))} {_label(item.get('commodity_id'), commodities)}"
            for item in outputs
        )
        lines.append(
            f"{_label(row.get('entity_id'), businesses)} produced {produced} in {_qty(row.get('actual_batches'))} completed batches."
        )
    for row in demands:
        shortage = _decimal(row.get("shortage_quantity"))
        if shortage <= 0:
            continue
        lines.append(
            f"{_label(row.get('site_id'), sites)} lacked {_qty(shortage)} {_label(row.get('commodity_id'), commodities)}; its preview price moved from {_price(row.get('price_before_gp_per_unit'))} to {_price(row.get('price_after_gp_per_unit'))}."
        )
    in_transit = sum(
        1
        for row in routes
        if row.get("movement_kind") != "same_month_handling"
        and _decimal(row.get("arrival_period_index")) > 1
    )
    if in_transit:
        lines.append(
            f"{in_transit} shipment{'s are' if in_transit != 1 else ' is'} still in transit and not treated as delivered this month."
        )
    lines.append(
        f"The preview bank originated {_money(banking.get('loan_originations'))}, ended with {_money(banking.get('ending_customer_deposits'))} in customer deposits, and recorded {_money(banking.get('interest_accrued'))} of accrued interest."
    )
    lines.append(
        f"The preview treasury received {_money(treasury.get('receipts_total'))}; no amount was posted to the canonical campaign ledger."
    )
    return lines


def _table(
    headers: Sequence[str], rows: Sequence[Sequence[object]], empty: str
) -> str:
    if not rows:
        return f'<div class="table-wrap"><p class="empty">{escape(empty)}</p></div>'
    head = "".join(f"<th scope=\"col\">{escape(str(item))}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _card(label: str, value: str, detail: str) -> str:
    return (
        '<div class="card">'
        f'<span class="label">{escape(label)}</span>'
        f'<span class="value">{escape(value)}</span>'
        f'<span class="detail">{escape(detail)}</span>'
        "</div>"
    )


def var_color(passed: bool) -> str:
    return "#2f684b" if passed else "#8f2d2d"


def var_background(passed: bool) -> str:
    return "#eef8f1" if passed else "#fff0ee"
