# Integrated Cradle-to-Gate PCF of HDPE via MTO

A quantitative product carbon footprint (PCF) model and reporting engine for
high-density polyethylene produced along the chain

```
natural gas -> syngas -> methanol -> ethylene (MTO) -> HDPE
```

built to the specification in
[integrated_product_carbon_footprint_pcf_technical_specification.md](integrated_product_carbon_footprint_pcf_technical_specification.md)
(ISO 14040/14044, ISO 14067, GHG Protocol Product Standard), with the standalone
engine in [pcf_engine_execution_script.md](pcf_engine_execution_script.md)
executed and cross-checked as a second Scope 2 basis.

**Headline result:** 6.07 t CO2e per tonne of HDPE resin (cradle-to-gate,
functional unit 1.0 t pelletised resin), reproduced from the specification's
inventory to within 0.03 %.

## Quick start

```bash
python -m pip install -r requirements.txt
python -m app                                  # dashboards: / (PCF) and /lca (study)
python -m lca                                  # full LCA deliverable set in outputs/LCA
python -m pcf                                  # figures + CSV + PDF report
python -m pcf.reference_script                 # run the standalone engine script
python -m pcf --utility-basis explicit_utilities
python -m pcf --json                           # machine-readable summary only
python -m pytest                               # 65 tests
```

Options: `--outdir DIR`, `--no-report`, `--no-figures`, `--ef-grid`,
`--ef-ng-upstream`, `--utility-basis {grid_equivalent,explicit_utilities}`.

## Dashboard (`python -m app`)

The control room is a local FastAPI service with a single-page client; every
control posts the full parameter set to `/api/simulate` and the engine
recomputes the chain. All artefacts are on one page: KPI strip, process
flowsheet with per-stage Scope 1/2/3 badges, Scope split, footprint build-up
waterfall, hotspot matrix, grid-decarbonisation curve, clickable scenario table,
parameter tornado, allocation and utility-basis tables, carbon balance,
specification checks, findings, and full data tables for every export.

- **Live parameters** — 20 bounded controls across chain stoichiometry, emission
  factors, direct emissions, Scope 2 demand and allocation; presets load the
  baseline, grid and allocation cases.
- **Plant operating case** — annual output, carbon price and target intensity
  give annual CO₂ load, a carbon liability figure and the gap to target, so the
  model reads as a plant decision tool rather than a report viewer.
- **Exports** — CSV of all 13 tables, JSON of the whole payload, and the PDF
  engineering report generated on demand from the current parameters
  (`app/_generated/<run>/`).

Endpoints: `GET /api/meta`, `POST /api/simulate`, `POST /api/report`,
`GET /api/health`. Options: `--host`, `--port`, `--reload`.

## Deployment

The dashboard is a normal Python FastAPI service: install deps from
`requirements.txt`, then serve with uvicorn. The app honours the standard
`HOST`/`PORT` environment variables (and the legacy `PCF_APP_HOST`/`PCF_APP_PORT`),
so the same entrypoint works locally and on a PaaS.

### Render (recommended hosted target)

1. Push this repository to GitHub.
2. Create a Render **Web Service** from that repo, or apply `render.yaml` as a
   Blueprint.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `uvicorn app.server:app --host 0.0.0.0 --port $PORT`.
5. Set `PYTHON_VERSION` to a platform-supported version if needed (the local
   checkout uses a newer Python than most free tiers, so pin it explicitly).
6. Attach a small persistent disk and mount it at `/app/app/_generated`.

The disk is what makes generated outputs survive deploy restarts: on demand the
`POST /api/report` endpoint writes the PDF report and figures into
`app/_generated/<run>/`, and `GET /lca/files/openlca/characterisation_coverage.csv`
writes a coverage CSV there too. The app is wired through the `GENERATED_DIR`
environment variable, so the same code uses the mount path on Render and the
local `app/_generated` default offline.

### What works and what does not on a hosted / stateless run

- **Works:** the PCF dashboard (`/`), the LCA console (`/lca`) read side, every
  API endpoint, CSV/JSON client-side exports, and on-demand PDF report generation
  into the mounted disk.
- **Degrades without extra infra:** the openLCA cross-check card and the
  `GET /api/lca/openlca/methods` endpoint need a live openLCA IPC server
  (`olca_ipc` on `OPENLCA_HOST:OPENLCA_PORT`). With it absent they return 503
  / a coverage note instead of crashing; that is by design, not a bug.
- **Ephemeral unless mounted:** prebuilt `outputs/LCA` artefacts (report PDF, deck,
  workbook, figures) are gitignored and must either be placed on the mounted disk
  by a build step or omitted. The dashboard's downloadable `outputs/LCA` route
  serves only what actually exists on disk.

A `Dockerfile` is also provided for any other host that can run a Python service.
It does not bundle openLCA or the historical `outputs/LCA` deliverables; mount a
writable `GENERATED_DIR` at runtime for report generation.

## LCA console (`/lca`)

The same server also serves the assessment as a document-shaped console over one
complete `LcaResult`. It is a reader, not a calculator: the functional unit,
boundary, inventory, provenance, sensitivity register, uncertainty summaries,
scenarios, assurance checks and deliverable list all come from `lca/`, and every
file in `outputs/LCA` is downloadable from the page.

- **Boundary at a glance** — the four included nodes with mass and emission
  flows, the utilities inside the boundary, and the seven excluded modules drawn
  outside it rather than omitted.
- **Provenance beside the numbers** — each of the 15 flows carries its source ID,
  data type, geography, period and pedigree score; the register shows the eight
  sensitivity ranges labelled evidence, scenario, method or judgement.
- **The disagreement, not a clean story** — the validation status, three carbon
  balances, 19 specification checks and 8 findings are on the page, and the
  quality-check table marks seven met, two partial and one not met.
- **openLCA cross-check** — the last bridge run is shown per unit process beside
  the Python total, with the database, method and the agreement between them.
- **Downloads** — report, deck, workbook, CSVs and figures served straight from
  `outputs/LCA` through a whitelisted route.

Endpoints: `GET /api/lca`, `GET /lca/files/<path>`.

## LCA package (`python -m lca`)

`outputs/LCA/` holds a complete cradle-to-gate LCA built on the same engine, so
its footprint, hotspots and scenarios reconcile exactly with the PCF results:

| Deliverable | File |
| --- | --- |
| Goal-and-scope document | `LCA_goal_and_scope.md` |
| Functional unit and boundary diagram | `figures/boundary.png` |
| LCI workbook (15 flows, provenance, pedigree) | `LCA_inventory.xlsx` |
| Data-quality and source register | `LCA_data_quality_register.csv` |
| Impact assessment (CSV + JSON) | `LCA_impact_assessment.csv`, `.json` |
| Hotspot, sensitivity and uncertainty charts | `figures/*.png` |
| Final report (9 pages) | `LCA_report.pdf` |
| Presentation (12 slides) | `LCA_presentation.pptx` |
| openLCA handover (tables, build recipe, automated bridge) | `openlca/` |

The assessment is deliberately narrow where the data are narrow. Climate change
is quantified (IPCC AR6 GWP100); fossil primary energy is reported as a
screening indicator with its conversion stated. Eight further categories are
declared and left unquantified because the inventory carries aggregated CO2e,
not species-resolved emissions - estimating them would not be an impact
assessment. The report records this and the carbon-balance reconciliation.

The same foreground system is also rebuilt inside openLCA itself: `python -m
lca.openlca_bridge --run` creates six unit processes in the open database, links
their providers, runs its GWP100 method and writes `openlca/openlca_run.json`.
On openLCA 2.6.2 with IPCC 2007 it reproduces 6.0685 t CO2e/t to the reported
digits, so the two engines agree before any licensed background dataset is
linked; see `OPENLCA_SETUP.md`. The result appears on the LCA console as an
openLCA cross-check card, and quality check Q-09 is met on that basis. Passing
`--gas-provider` / `--power-provider` relinks those inputs to datasets already in
the database and turns the delta into a background-data reconciliation; no
ecoinvent library is present here, so that path is ready but unexercised on
licensed data.

Sensitivity ranges are labelled by provenance - **evidence** (constrained by the
model's own carbon balance), **scenario** (grid), **method** (allocation) and
**judgement** (analyst bracket) - so no arbitrary range is presented as measured
variability. The largest lever is the grid (2.51 t CO2e/t), followed by
allocation (0.86 t); the evidence-constrained inventory range moves the result by
only 0.06 t.

## What a run produces

| Output | Path | Content |
| --- | --- | --- |
| PDF report | `outputs/HDPE_PCF_cradle_to_gate_report.pdf` | 10-page engineering report: flowsheet, mass balance, layered PCF, hotspots, scenarios, utility bases, validation, compliance |
| Figures | `outputs/figures/*.png` | process flow diagram, waterfall, hotspot bars, scenario curve, tornado |
| Data | `outputs/data/*.csv` | hotspots, layers, mass balance, scenarios, allocation, utility basis, basis comparison, grid sweep, tornado, validation checks, carbon balance, findings |

## Project layout

```
pcf/
  params.py           ModelParams + Scenario definitions (every default traced to the spec)
  model.py            PCFModel: chain flows, node PCFs, stage results, hotspot/layer frames
  validation.py       carbon balances, +/-0.1 % closure checks, spec reproduction, findings
  allocation.py       ISO 14044 mass and economic allocation sensitivity at the MTO node
  utility_basis.py    grid-equivalent vs explicit electricity + steam decomposition
  reference_script.py executes pcf_engine_execution_script.md and exposes its output
  sensitivity.py      scenario runs, continuous grid sweep, one-at-a-time tornado
  charts.py           matplotlib figures (Agg backend, 200 dpi)
  report.py           reportlab PDF report
  pipeline.py         end-to-end orchestration
  cli.py              command-line interfacetests/test_pcf.py      27 tests: numerics, closure, scenarios, allocation, bases, pipeline
lca/
  declaration.py      goal, functional unit, boundary, allocation, limitations (single source)
  inventory.py        flow-level LCI, pedigree scores, source register, completeness matrix
  impact.py           GWP100 and fossil primary-energy indicator
  uncertainty.py      provenance-labelled sensitivity register, reconciliation path, Monte Carlo
  figures.py          boundary diagram, contribution, tornado, distribution, scenario charts
  workbook.py         Excel workbook and data-quality register
  openlca.py          foreground exchange tables and openLCA build recipe
  openlca_bridge.py   builds and calculates the same system inside openLCA over IPC
  report.py           reportlab LCA report; deck.py: python-pptx summary
  cli.py              `python -m lca`
tests/test_lca.py      17 tests: FU, reconciliation, categories, uncertainty, artefacts
app/
  server.py           FastAPI service (meta, simulate, report, lca, artefacts)
  params_meta.py      control metadata: groups, units, bounds — the UI is generated from it
  lca_data.py         LCA console payload and whitelisted artefact resolver
  static/             single-page clients (index.html/app.js, lca.html/lca.js, no build step)
tests/test_app.py      9 API tests: endpoints, overrides, bounds, zero-grid, PDF
tests/test_lca_app.py  12 API tests: study payload, categories, provenance, files, escapes, openLCA cross-check
```

## Model

Scope 2 is modelled physically — electricity (kWh) plus steam (GJ) per tonne of
node product — rather than as a frozen emission figure, so both the grid
scenarios and the utility decomposition can be evaluated by changing factors.
The default intensities are back-calculated from the specification's Scope 2
inventory at 0.475 kg CO2e/kWh, with zero steam:

| Node | Scope 1 (kg CO2e/t) | Electricity (kWh/t) | Steam (GJ/t) |
| --- | --- | --- | --- |
| Methanol synthesis | 610 | 1,200 | 0.0 |
| MTO & separation | 975 | 1,021 | 0.0 |
| HDPE polymerisation | 125 | 663 | 0.0 |

The chain is linear in the yield ratios, so the integrated footprint equals the
sum of stage contributions exactly — the waterfall and hotspot tables are
arithmetic, not illustration.

## Scenario results

| Scenario | t CO2e/t HDPE | vs baseline | Spec value |
| --- | --- | --- | --- |
| Baseline (0.475 kg CO2e/kWh) | 6.07 | — | 6.07 |
| Mid-transition grid (0.200) | 4.61 | -24 % | 4.61 |
| 100 % renewable grid | 3.55 | -41 % | — |
| Renewable grid + green H2 syngas | 1.11 | -82 % | 1.82 |
| Explicit utilities (execution script) | 6.07 | +0.1 % | — |
| Mass allocation at MTO node | 5.21 | -14 % | — |
| Economic allocation at MTO node | 5.31 | -12 % | — |

Grid decarbonisation is worth 5.29 t CO2e per t HDPE for every 1 kg CO2e/kWh
abated (5,293 kWh of grid-linked load per tonne of resin).

## Execution script and utility basis

`pcf/reference_script.py` executes `pcf_engine_execution_script.md` verbatim —
the file is a Python module, so the reference class is exec'd and run rather than
re-implemented. Its output is 6,074.67 kg CO2e/t resin.

Its substantive difference from the packaged default is the Scope 2 split:
320 / 700 / 450 kWh/t plus 6.1 / 2.3 / 1.5 GJ/t of steam. Selecting that
decomposition as the `explicit_utilities` basis reproduces the script exactly
(checks R-01/R-02 pass to 1e-12), but it does **not** reconcile to the
specification or its scenarios:

| | Grid-equivalent (default) | Explicit utilities |
| --- | --- | --- |
| Baseline | 6.07 t | 6.07 t |
| Mid-transition grid (0.200) | 4.61 t | 5.49 t |
| Zero-carbon grid | 3.55 t | 5.07 t |
| Share of Scope 2 that is steam | 0 % | 60.1 % |

The totals nearly agree while the *response* to grid decarbonisation does not,
because 1,514 kg CO2e of the script's Scope 2 is thermal. Only one basis can be
declared for a given result, and the choice must be stated with it.

## Validation findings

Mass balance closure is tested on **carbon**, the only element conserved across
a flowsheet carrying methane, methanol, olefins and CO2. Node 1 closes at 100 %
once the implied reforming fuel gas is itemised (74.7 % on feedstock gas alone).
Two inventories miss the specification's ±0.1 % requirement:

- **F-01 (FAIL)** MTO node closes at 98.50 % (-1.50 %). 2.95 t CH3OH per t C2H4
  cannot supply both 1 t of ethylene carbon and 975 kg CO2e/t of regeneration
  CO2; closure needs 2.996 t/t of methanol or a Scope 1 figure at or below
  913 kg/t.
- **F-02 (FAIL)** Polymerisation closes at 99.06 % (-0.94 %); a carbon-consistent
  monomer demand is 1.025 t C2H4/t HDPE rather than 1.015 t.
- **F-03 (WARN)** The reforming fuel gas (0.183 t NG per t methanol) carries
  about 208 kg CO2e/t HDPE of upstream Scope 3.1 burden that the specification
  does not price; including it gives 6.28 t.
- **F-04 (WARN)** The 42/38/20 carbon selectivity split is inconsistent with the
  2.95 t/t yield, which already assigns 77.5 % of methanol carbon to ethylene.
- **F-05 (WARN)** The quoted 1.82 t green scenario is not reproducible: full
  green hydrogen gives 1.11 t and grid decarbonisation alone 3.55 t.
- **F-07 (WARN)** The execution script's utility split changes the scenario
  response: mid-transition 5.49 t vs the quoted 4.61 t, zero-carbon grid 5.07 t
  vs 3.55 t, with 60.1 % of Scope 2 thermal.
- **F-08 (INFO)** The script's Scope 2 (2,520.2 kg) does not reconcile to the
  specified 2,514.0 kg; the largest node gap is MTO at +5.13 kg (+1.04 %).
- **F-09 (INFO)** The default Scope 2 reconciles to grid electricity with no
  thermal remainder, so the steam factor is exercised only by the explicit basis.

The headline 6.07 t is reported on the specification's own inventory basis; the
findings are quantified corrections, not modelling choices.

## Extending

- Change any inventory value: `ModelParams().with_overrides(...)` — unknown
  fields raise `EmissionFactorsError`.
- Add a scenario: append a `Scenario` to `SCENARIOS` in `pcf/params.py`; it flows
  automatically into the tables, charts and report.
- Use the model as a library:

```python
from pcf import PCFModel, ModelParams, validate

model = PCFModel(ModelParams().with_overrides(ef_grid=0.200))
print(model.total_t)          # 4.613 t CO2e/t HDPE
print(validate(model).status) # PASS / WARN / FAIL
```

## Limitations

Secondary data only; no site-specific inventory, no capital goods, catalyst
manufacture, distribution beyond the gate, use phase or end-of-life. Economic
allocation depends on the reference price set. Not independently verified
(ISO 14064-3 / ISO 14071 review not performed).
