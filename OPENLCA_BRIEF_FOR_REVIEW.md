# Briefing: openLCA cross-check of the HDPE cradle-to-gate LCA

**Audience:** another AI agent reviewing the project for correctness, reproducibility, and honest claims.
**Purpose of this brief:** let you re-verify the openLCA part of the HDPE study without re-deriving it from the report.

---

## What "the projection" is

Cradle-to-gate LCA of **1,000 kg HDPE resin at the gate**, quantified in two independent
implementations over the **same foreground inventory**:

1. `pcf/` — the source of record. Declares functional unit, boundary, exchanges, allocations,
   data origins, and all uncertainty. This is the declaration.
2. `lca/openlca_bridge.py` — an independent calculation engine that rebuilds the same six
   foreground unit processes in openLCA and runs the database's GWP100 method.

openLCA is a **cross-check**, not a second design of the study. The claims live in the Python
model and the report; openLCA checks that the same exchanges, linked and scaled through a product
system, return the same impact.

**Verified result:** `6.0685 t CO2e / t HDPE` in both engines. Delta `0.000%` (floating point
rounding). The raw JSON total is `6068.492358490566 kg CO2e/t`, i.e. `6068.49 kg`; the card shows
rounded `6.0685 t`. Per process (kg CO2e/t HDPE, as on the card): electricity 2514.0, methanol 1826.5,
MTO 989.6, gas 613.4, polymerisation 125.0, co-monomer 0.0.

**Correction appended from a re-verification pass on this session:** the brief originally said
`python_gwp_kg = 6068.5` and `6068.5 kg per functional unit`. The actual stored JSON field is
`total_kg_co2e = 6068.492358490566`; `python_kg_co2e` is not a field in `openlca_run.json`.
The dashboard carries the Python total itself in `kpis.gwp_kg`, and `build_result()`/`impact.compute()`
derive it from the model. So the reconciliation is: openLCA JSON `total_kg_co2e` vs the Python model
`gwp_kg`, both ~6068.49 kg; the "6068.5" figure was a rounded display shorthand, not what is stored.

Scope split (same as the report): Scope 1 = 2941.1, Scope 2 = 2514.0, Scope 3 = 613.4.

---

## What to verify

- `outputs/LCA/openlca/openlca_run.json` is the authoritative openLCA output.
  Fields to trust: `total_kg_co2e`, `total_t`, `python_t`, `delta_pct`, `per_process`, `background`.
- `outputs/LCA/openlca/README.md` documents the manual handover route (build by hand) and what
  changes when a real database is linked.
- `OPENLCA_SETUP.md` is the setup doc; the long section "HDPE study projection — features,
  capabilities, mechanism, limitations" is the descriptive note I added for this purpose.
- `app/lca_data.py` — function `_openlca()` reads `openlca_run.json` and surfaces it as the
  `openlca` card on `/lca`. The console is read-only; it never drives openLCA.
- `app/static/lca.html` + `app/static/lca.js` — the card is `#openlca-card`, summary
  `#openlca-summary`, note `#openlca-note`, table `#openlca tbody tr`.
- `tests/test_lca_app.py` — includes an `openlca` reconciliation test that parses the JSON and
  checks `total_t`, delta, 6 rows, breakdown sums.

---

## Honest state (this is the part other agents should react to)

- **No licensed ecoinvent process database is present in this install.** The openLCA workspace
  `~/openLCA-data-1.4/databases.json` lists exactly one local database,
  `ecoinvent2_2_lcia_methods`, and that database contains no ecoinvent **process** dataset:
  it holds ecoinvent LCIA **methods** (37 impact methods confirmed present, including
  `IPCC 2007` and `Carbon dioxide, fossil`), plus 20 processes that are 14 from an unrelated
  Prosopis juliflora / biochar study and 6 HDPE study processes I created.
- So **there is no shift to report against 6.0685 t right now.** The background-linking path is
  implemented and verified on synthetic providers, but it is **unexercised on real ecoinvent data**.
- "Linking ecoinvent" therefore means: import a licensed ecoinvent database into this workspace,
  then pass the exact process names with `--gas-provider` and `--power-provider`.
- The study explicitly models Scope 1 as aggregated CO2e → `Carbon dioxide, fossil`, GWP100 factor
  1. That is exact for a CO2-only aggregate, but the model cannot support acidification, eutrophication,
  POCP or particulate-matter categories until the emissions are split into CO2, CH4 and N2O. Those
  categories stay unquantified by design. (This is not new; it is stated plainly because it is the
  kind of overclaim another agent should catch.)

---

## How linking is done (mechanism, so you can judge whether it is real or hand-waved)

- A dataset can only supply its own product flow. So to link gas/electricity, the bridge re-expresses
  the study's consumer inputs in **the provider's own flow and unit**, drops the study's proxy unit
  process for that input, and lets openLCA's builder link the provider. openLCA's builder ignores
  default-provider hints on a process, so setting those does not work.
- Validation order: resolve provider names against the open database **before** purge, so a typo cannot
  delete the existing study; after the system is built, confirm each requested provider is present in
  `system.processes`, failing loudly rather than reporting a silent zero.
- `--run --purge` deletes only entities whose name starts with `HDPE study / ` plus that product system.
  Without `--purge` a run is additive and would duplicate the study; the bridge refuses that.
- IPC quirk handled: `get_all()`/entity sub-lists can include `None` entries and by-name `get` can miss
  existing entities; all scans tolerate nulls.

---

## What would let this become a fully linked result

1. Import a licensed ecoinvent database into `~/openLCA-data-1.4`.
2. Identify the exact openLCA process names for market electricity and natural gas (or the specific
   datasets the suppliers actually use).
3. Run:
   ```
   python -m lca.openlca_bridge --run --purge \
       --gas-provider "<exact name>" --power-provider "<exact name>"
   ```
4. Read the reconciliation delta from the console's `openlca` card; record the provider's geography,
   technology, reference year and cut-offs so the shift is explained, not just stated.
5. Update the report page on background data and the quality record accordingly.

---

## Development artifact, explicitly not a deliverable

Earlier, to prove the linking path, a synthetic test ran with two dummy providers:
0.9 kg CO2e/kWh for power and 0.5 kg CO2/kg for gas. That returned 8.511557 t against an analytically
expected 8.511556 t (delta +0.000002%), provider rows 4763.4 and 807.1 kg, both providers confirmed
inside the product system. **Those dummy providers were deleted.** That number is **not** in any
deliverable. It is a mechanism test only.

---

## Where another agent is most likely to disagree, and my answer

1. **"openLCA found an ecoinvent database, so it is ecoinvent-based."**
   It is not. `ecoinvent2_2_lcia_methods` is a methods database, not a process library. No ecoinvent
   process is loaded. The current number is not an ecoinvent footprint.
2. **"Reconciling two engines that use the same foreground is not a real cross-check."**
   Agreed, within scope. It verifies reproducibility of the arithmetic (a useful property and an
   explicit deliverable), not independence of the inventory. The brief says this plainly.
3. **"The number should move once ecoinvent is linked."**
   Yes, mainly through the grid factor, which is the single largest lever. That difference is the
   reconciliation to report, not an error to hide. But it is not available until ecoinvent is imported.
4. **"Why is Scope 1 a single CO2e line?"**
   Because the source gave an aggregate CO2e figure, not a species split. The mapping enters it as
   fossil CO2 and flags the proxy. Splitting it is the next real modeling step; it also unlocks other
   impact categories. The handover README says this.

---

## Re-scoped execution plan for the next agent (Step 3 + Step 4)

### Re-scoping note for the plan you pasted

The plan you supplied is directionally right but over-specifies implementation before checking what the
project already does and what it can actually do with the installed data. The corrections below are what
I would write before executing it.

1. **The DQI engine already exists.** This project is not starting from blank on Task 4.1.
   `lca/inventory.py` implements a five-criterion pedigree matrix (reliability, completeness, temporal,
   geographical, technological), scores each flow, and derives a `dqi_rating` A–E. `lca/build.py`
   includes `dqi`, `dqi_frame`, `source_register`, `completeness_frame`, and `validation`.
   `lca/documents.py` exposes a 10-check acceptance grid (`Q-01`…`Q-10`) whose evidence already
   cites the DQI register, pedi gree mean, proxy flags and the co-monomer gap. So Task 4.1 should be
   scoped as: **extend or harden the existing pedigree/DQI machinery**, not reimplement it. If the plan
   wants extra, it should say what current scoring does not capture — e.g. per-flow data gap flags that
   the dashboard surfaces, uncertainty propagation into the DQI, or a background-database DQI that is
   currently absent because no database is linked.

2. **The multi-category claim already exists, as "declared but not quantified".** Task 3 is not going to
   magically quantify acidification/eutrophication/POCP/PM/water by wiring a method flag. The foreground
   inventory is still **aggregated CO2e per node** (`methanol_scope1`, `mto_scope1`, `hdpe_scope1` in
   `pcf/params.py`; `EM-01`…`EM-04` in `lca/inventory.py`; mapping to `Carbon dioxide, fossil` in
   `lca/openlca.py` mapping_frame). `lca/declaration.py` already lists 8 impact categories, 1 quantified
   (climate change), 1 screening (primary energy), 6 declared-not-quantified because the inventory has no
   species. `lca/impact.py` implements climate + primary energy only.
   So the honest scope for Step 3 is:
   - **3.1 species disaggregation** is blocked on **source data**, not on code. Before rewriting the
     inventory into CO2/CH4/N2O/SO2/NOx/NMVOC, the agent needs the actual species figures for each node
     (or a defensible way to obtain or bound them). If they do not exist in the source specification, the
     right move is to **keep the aggregated CO2e line and add an explicit species-resolve gap with the
     data needed to close it**, rather than inventing fluxes.
   - **3.2 multi-method LCIA** should be checked against the real openLCA IPC API surface of the
     `olca-ipc` version installed here, and against the fact that the only background DB present holds
     methods but no processes. The useful deliverable is: *which methods are available in the open
     database, what elementary flows they cover, and what would be needed to characterise the existing
     foreground inventory against them*. If the foreground stays aggregated CO2e, most methods will still
     not quantify because the foreground has no SO2/NOx/NH3/NMVOC/PM/P/N/water.
   - **3.3 output schema** should be compared against what `lca_data.py` already serialises:
     `categories`, `impact_table`, `dqi`, `sources`, `completeness`, `reconciliation`, `sensitivity`,
     `scenarios`, `uncertainty`. Depending on what the plan wants, it may be extending those frames rather
     than inventing a new `indicators` blob. Keep provenance with the numbers: category, indicator, unit,
     method, status, basis, gap.

3. **The forensic-blocker carry-over from the linked-data work is real for Step 3 too.**
   There is no licensed ecoinvent process database installed, so any multi-impact result that needs a
   background database (e.g. acidification/eutrophication/water via market processes) cannot be completed
   here until one is imported. The plan should record that as a dependency, not assume it away.

4. **Step 4.2 provenance ledger** should record what is actually obtainable, not pretend to fields the
   install does not furnish. From this project's state:
   - commit hash: available from git.
   - openLCA IPC server version: available from the running openLCA instance.
   - database name: `ecoinvent2_2_lcia_methods` is real and verifiable from `databases.json`.
   - database UUID/version/provider names: only if a real database is loaded. Today there are no
     ecoinvent provider names to log, because there are no ecoinvent processes in the open DB.
   So the ledger is fine as a per-run provenance record, but its "exact provider names used" field should
   be populated only when background linking is actually done.

5. **Step 4.3 ISO 14044 critical review generator** should be framed as an **audit-package and
   checklist generator**, not as "signed-off compliance document". An automated generator can produce a
   reviewable package — goal/scope, boundary, inventory provenance, DQI, completeness gaps, sensitivity
   provenance, category coverage, openLCA reconciliation, allocation basis, data gaps — and a checklist
   mapped to the study's existing Q-01…Q-10. It cannot sign off or perform the independent critical review
   that the study itself marks as Q-10 "Not met". That distinction matters.

### Concrete corrected sequence

**Step 3, corrected:**
- 3.1 only after the foreground inventory can be species-resolved from real data; otherwise extend the
  completeness matrix and mapping to make the species gap explicit and auditable.
- 3.2 inspect real openLCA IPC method enumeration and characterisation coverage in this install; report
  what is available and what the current foreground can and cannot characterise.
- 3.3 align the output schema with the existing `lca_data.py` serialisation so the dashboard and
  artefacts stay consistent; add multi-category fields only if the foreground and a method can actually
  support them.

**Step 4, corrected:**
- 4.1 work on the existing `lca/inventory.py` pedigree/DQI + `documents.py` acceptance checks; add
  whatever is genuinely missing (likely: per-flow gap surfacing, background-DQI slot, uncertainty-propagated
  DQI, clearer warning thresholds on the dashboard).
- 4.2 provenance ledger: commit hash + IPC server version + database name + method + provider names when
  linked + allocation basis; expose as `/audit/export` only after the ledger is real.
- 4.3 produce an ISO-mapped audit package and critical-review checklist from the existing goal/scope,
  declaration, DQI, completeness, sensitivity and openLCA reconciliation; label it as a review input, not a
  signed review.

**Hard dependencies to record before promising Step 3 results:**
- species-resolved foreground emissions data, or an explicit gap with the data required;
- a licensed background database with the elementary flows the chosen methods need;
- confirmation of the real `olca-ipc` method/characterisation API surface in this install.

---

## Files an agent should open first

- `outputs/LCA/openlca/openlca_run.json` — the result.
- `outputs/LCA/openlca/README.md` — manual build + what changes on linking.
- `OPENLCA_SETUP.md` — setup + the projection note.
- `lca/openlca_bridge.py` — the bridge (check and run helpers, `--gas-provider`/`--power-provider`).
- `app/lca_data.py` — `_openlca(); built payload frames: categories, impact_table, dqi, sources, completeness, reconciliation, sensitivity, scenarios, uncertainty`.
- `pcf/params.py` + `pcf/model.py` + `lca/inventory.py` + `lca/impact.py` + `lca/openlca.py` mapping_frame — the real foreground inventory and its species gap.
- `lca/documents.py` — existing quality checks Q-01…Q-10 and deliverables list.
- `tests/test_lca_app.py` — especially `test_openlca_cross_check_reconciles_with_the_python_model` and `test_quality_checks_expose_partial_and_unmet_items`.

---

## A concrete ask for the reviewing agent

Please check, and tell me where you find a mismatch:

1. Does `openlca_run.json` reconcile with the Python model to the digits claimed, using the actual stored
   field `total_kg_co2e` against `kpis.gwp_kg`, not a made-up `python_kg_co2e` field?
2. Are the 6 per-process rows present, and do they sum to `total_kg_co2e`?
3. Is the "no ecoinvent process dataset loaded" statement verifiable from `databases.json` and the
   open database's process list?
4. Does the bridge refuse the unsafe additive re-run and validate providers before purge?
5. Are the Scope 1/2/3 split and the species-resolution limitation stated honestly and consistently
   between the JSON, the report, the workbook, the deck and the handover README?
6. Is the existing DQI/pedigree + acceptance-check machinery correctly described as already present, so
   Step 4.1 is framed as extension/hardening rather than reimplementation?
7. Is anything in this brief or the re-scoped plan that I have not actually verified?

## Verification status

Verified before writing this:
- `pytest` → 65 passed.
- `python -m lca.openlca_bridge --run --purge` rebuilds the six-process study at 6.0685 t.
- `openlca_run.json` present; `total_kg_co2e` = 6068.492358490566; `python_kg_co2e` is not a JSON field.
- `databases.json` confirms exactly one local database, `ecoinvent2_2_lcia_methods`, with no ecoinvent
  processes loaded (verified: 1 local DB, 20 processes, 6 HDPE-study, 0 market-like).
- The dashboard at `http://127.0.0.1:8099/lca` renders `#openlca-card` with 6 rows, no overflow, and
  the note "No background dataset is linked...".
- Output tree under `outputs/LCA` checked: report PDF, presentation PPTX, workbook XLSX, goal/scope MD,
  impact JSON/CSV, DQI CSV, flows CSV, inventory XLSX/CSV, scenarios, sensitivity, uncertainty, completeness,
  deliverables index, plus the openlca folder with exchanges/flows/mapping CSVs, the JSON, and the README.

Not verified in this session: a fresh visual screenshot of the page; the exact `olca-ipc` method-enumeration
API surface against a running openLCA instance with an added method database.

## Limitations of what this brief does not yet cover

- It does not yet answer Step 3.2's "which impact methods are actually available and characterisable in this
  install" — that requires a live openLCA IPC call or a documented `olca-ipc` API check.
- It does not yet contain species-resolved foreground data, because neither the specification nor the current
  repository provides it; that is the real blocker for anything beyond "declare the gap".
