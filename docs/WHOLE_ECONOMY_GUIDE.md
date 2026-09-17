# Baen Whole-Economy Preview

This is a local, non-canonical medieval regional-economy simulation. It advances one month at a time, preserves every committed month, verifies the saved history by deterministic replay, and opens a readable HTML report.

It makes **zero Notion writes** and **zero canonical campaign-ledger postings**.

## Use it without a terminal

The launcher must remain in the project root beside `pyproject.toml`. Do not move it away from the repository, because it resolves the simulator and scenario through repository-relative paths.

1. Double-click `OPEN-BAEN-WHOLE-ECONOMY.cmd`.
2. On the first launch, it creates and seals a durable workspace at `Documents\Baen Economy\whole-economy-preview-v3`. The new path is deliberate: older v1/v2 workspaces remain immutable and cannot retain the superseded always-visible operation gate.
3. It silently checks sealed campaign-operation gates without changing them, then verifies all existing history, commits exactly one next month, verifies the newly saved history, and opens that month's `report.html` in the default browser. With no played-canon evidence supplied, the Forgedeep operation remains completely absent from boot output and reports.
4. Double-click the same launcher again whenever you want to advance exactly one more month. It reuses the same workspace; it does not restart Month 1.

Python 3.11 or newer must already be installed and available as `py.exe` or `python.exe`. The launcher does not install or update software. If anything fails, the window remains open with the error. The append-only CLI refuses to overwrite a committed month.

The launcher invokes no Git command, package installer, Notion integration, or canonical writer. Its only durable runtime output is the preview workspace under Documents.

## What the report contains

Each committed month includes:

- settlement and social-class population changes;
- class consumption, shortages, and substitutions;
- land tenure, rents, feudal dues, tithes, and taxes;
- agricultural, extraction, workshop, construction, and service production;
- labour allocation, wages, unemployment, and migration;
- local market clearing and persistent settlement prices;
- routed trade, carriers, travel time, tolls, spoilage, and arrivals;
- entity cash, treasuries, bank deposits and reserves, loans, collateral, interest, repayment, and default;
- applied weather, harvest, war, monster, political, infrastructure, and policy shocks;
- a causal account of what changed, where it changed, why it changed, and the decisions currently available.
- any campaign operation whose exact played-canon activation gate has matched, together with its still-unresolved evidence requests and player-held decision gates. Dormant operations are omitted completely.

The HTML is a report, not an interactive control panel. “Available decisions” are visible recommendations; clicking them does not alter the simulation.

## Source and assumption boundary

The bundled scenario is explicitly `canonical: false`.

The source-backed boundary is narrow and auditable: the Registry snapshot supplies the copied fields in `entities[].registry_facts`—entity name, city, sector, status, employees, monthly revenue, monthly cost, and capital where present. Those records remain tagged with their source record IDs.

Every executable number outside `entities[].registry_facts` is an explicit scenario assumption for this vertical slice. That includes settlement populations and class mix, land and tenure quantities, production coefficients, inventories, wages, prices, household baskets, substitution rules, route capacity and losses, tax and tithe rates, bank terms, credit requests, migration response, and shock timing or severity. Simulation output is therefore a model result, not a recovered campaign fact or forecast.

The launcher reads only the bundled, sealed JSON scenario. It does not read live Notion data. Initialization copies that scenario into the workspace; later repository edits do not silently change an existing run.

## Command-line fallback

Run these commands from the project root in Command Prompt. Set `BAEN_WORKSPACE` to the same Documents location used by the launcher (substitute the actual path if Windows redirects Documents):

```bat
set "BAEN_WORKSPACE=%USERPROFILE%\Documents\Baen Economy\whole-economy-preview-v3"

py -3 src\baen_economy\whole_economy_cli.py init "%BAEN_WORKSPACE%" --scenario "fixtures\regional-scenarios\baen-north-whole-economy-v1.json" --seed "baen-north-whole-economy-preview-v3"

py -3 src\baen_economy\whole_economy_cli.py run-month "%BAEN_WORKSPACE%" --commit

py -3 src\baen_economy\whole_economy_cli.py verify "%BAEN_WORKSPACE%"
```

Run `init` only when creating a new workspace. Run `run-month --commit` once for each month you intend to add. Omitting `--commit` performs a preview calculation without saving it.

To print the path of the latest stored report:

```bat
py -3 src\baen_economy\whole_economy_cli.py report "%BAEN_WORKSPACE%"
```

To gate-check sealed campaign operations without running or saving a month:

```bat
py -3 src\baen_economy\whole_economy_cli.py boot "%BAEN_WORKSPACE%"
```

`boot` is read-only and deliberately prints nothing while every operation is dormant. It verifies the complete workspace but does not reveal a dormant operation's title, ID, facts, or decisions.

The Forgedeep return can surface only when a campaign integration supplies a structured `baen.played-canonical-context/1` file containing an event explicitly marked `canonical: true` and `played: true` with `subject_id: "arik"`, `event_type: "physical_arrival"`, and `location_id: "forgedeep"`:

```bat
py -3 src\baen_economy\whole_economy_cli.py boot "%BAEN_WORKSPACE%" --played-context "C:\path\to\played-context.json"
```

Free text, an intended destination, a Forgedeep mention, Avernus, the Black Sluice, Tethford, portal transit, approach, or travel does not satisfy the structured gate. Matching evidence returns exactly one stable activation identity for the operation. It surfaces the unanswered fact requests and decisions but cannot execute or resolve them.

The local launcher does not read Notion and therefore cannot discover a landing by itself. The live campaign Runtime Control must supply or apply the same played-canon event gate. This prevents the local preview from interfering with the current Avernus and Black Sluice path.

To export an exact copy outside the sealed workspace, choose a new `.html` path that does not already exist:

```bat
py -3 src\baen_economy\whole_economy_cli.py report "%BAEN_WORKSPACE%" --period 1 --output "%USERPROFILE%\Desktop\baen-economy-month-1.html"
```

## Operational limits

- This is a source-bound vertical slice, not a completed canonical model of every settlement, household, firm, commodity, institution, or campaign event.
- The bundled fixture currently covers three settlements, sixteen Registry-identified entities, sixteen commodities, seventeen production recipes, six routes, three tenures, and seven typed shock categories.
- Resolution is monthly. Within-month sequencing is an explicit model rule, not day-by-day simulation.
- Results are deterministic for the sealed scenario, prior state, and stored seed fingerprint. They are not probabilistic confidence intervals or historical forecasts.
- The accounting layer is a balanced simulation transaction journal and account state, not an approved canonical campaign balance sheet.
- Committed history is append-only. Manual edits, missing files, gaps, or changed reports cause verification to fail instead of being silently accepted.
- There is no automatic workspace migration. A materially revised scenario or model should use a new workspace rather than rewriting an old run.
- Supported committed months are `0001` through `9999`.
- The one-click launcher targets Windows `cmd.exe`. It uses PowerShell only to locate a redirected Documents folder and falls back to `%USERPROFILE%\Documents` if that lookup is unavailable.

The safe interpretation is: use the report to inspect and compare simulated regional consequences; do not treat it as a canonical posting until its assumptions and outcomes are explicitly approved.
