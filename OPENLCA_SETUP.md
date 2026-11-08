# Quantifying the HDPE study in openLCA

The Python model in `pcf/` remains the declaration of the study. openLCA is used
as an **independent calculation engine** over the same foreground inventory, so
the numbers are checked by a second implementation rather than re-typed.

`lca/openlca_bridge.py` builds six unit processes in the open database, links
them into a product system, runs the database's GWP100 method and writes the
result to `outputs/LCA/openlca/openlca_run.json`. The LCA console (`/lca`) reads
that file and shows it as the *openLCA cross-check* card in the Assurance
section.

## What you need

- openLCA 2.x (verified on 2.6.2), running.
- A database open in the desktop app that contains the `IPCC 2007` impact method
  and the elementary flow `Carbon dioxide, fossil`. The verified run used
  `ecoinvent2_2_lcia_methods`.
- `olca-ipc` in the same Python environment: `python -m pip install olca-ipc`
  (installs `olca_schema` as well).

## Start the IPC server

In openLCA: **Tools → Developer tools → IPC Server → Start**. The default port
is 8080 and it must be running before any command below.

## Run it

```
python -m lca.openlca_bridge --check          # connects, reports method/flow/model counts
python -m lca.openlca_bridge --run            # build the six processes and calculate
python -m lca.openlca_bridge --run --purge    # delete a previous run first, then rebuild
python -m lca.openlca_bridge --port 8081 ...  # if the IPC server is on another port
```

`--check` prints the database name, how many impact methods and processes it
sees, and whether `IPCC 2007` and `Carbon dioxide, fossil` are present. If any
of that is false, the bridge stops with a specific message instead of building a
model it cannot calculate.

The run creates six flows, six unit processes and one product system, all named
`HDPE study / ...` (the system is `HDPE study / Product system (1 t HDPE)`), so
the study is easy to find and to remove in the openLCA navigator.

`--purge` deletes only entities whose name starts with `HDPE study / ` plus the
product system built from them, then rebuilds. Without `--purge` a run is
additive: openLCA will hold two copies of the same processes and the product
system will keep whichever provider it linked first, so use `--purge` for a
clean rebuild.

## What the run produced

| Field | Value |
| --- | --- |
| Database | `ecoinvent2_2_lcia_methods` |
| Method | `IPCC 2007 / climate change - GWP 100a` |
| Functional unit | 1,000 kg HDPE resin at the gate |
| openLCA total | 6.0685 t CO2e / t HDPE |
| Python total | 6.0685 t CO2e / t HDPE |
| Difference | 0.000 % (floating-point rounding) |

Per unit process (kg CO2e per t HDPE): electricity supply 2,514.0, methanol
synthesis 1,826.5, methanol-to-olefins 989.6, natural gas supply 613.4,
polymerisation 125.0, co-monomer supply 0.0. The first three plus
polymerisation are Scope 1 (2,941.1), electricity supply is Scope 2 (2,514.0)
and natural gas supply is Scope 3 (613.4) - the same split the report gives.

## Linking a licensed background dataset

The bridge can replace its own upstream gas and electricity proxies with datasets
that already exist in the open database:

```
python -m lca.openlca_bridge --run --purge \
    --gas-provider "<exact process name>" \
    --power-provider "<exact process name>"
```

Both options take the exact process name as it appears in the openLCA navigator
(a licensed ecoinvent database must be imported into this workspace first; the
database currently open holds no ecoinvent processes). What happens then:

- the study's input exchanges for gas and electricity are re-expressed in the
  **provider's own flow** and unit, because a dataset can only supply its own
  product — this is the step that makes the link possible at all;
- the study's proxy unit processes for those two inputs are not created;
- openLCA's product-system builder then links the provider and pulls in its
  upstream chain, so the provider's own burdens are included;
- the run fails loudly if the provider does not end up inside the product
  system, rather than reporting a link openLCA ignored.

The run writes `background.linked` and `background.providers` into
`openlca_run.json`, and the console shows the linked datasets beside the delta.

**Reading the result.** With no provider linked the two engines agree by
construction (6.0685 t) because they carry the same foreground amounts. As soon
as a provider is linked, the difference against 6.0685 t stops being a rounding
check and becomes the reconciliation: it is the effect of the background
dataset's own factors, and it is reported per unit process. That number is only
meaningful when the dataset's geography, technology and reference year are
recorded — which is why providers are named explicitly rather than matched.

A run without `--purge` is refused when study entities already exist: it would
duplicate them and leave the product system linked to the wrong copy.

## HDPE study projection — features, capabilities, mechanism, limitations

### What this projection is

The projection is a **cradle-to-gate LCA of 1 tonne of HDPE resin at the gate**,
quantified in two independent implementations over the same foreground inventory:

- `pcf/` declares the study in Python and is the source of record for the
  functional unit, boundary and exchange list;
- `lca/openlca_bridge.py` rebuilds the same six foreground unit processes in
  openLCA, runs the ecoinvent2-based impact method and reconciles the total
  against the Python model (6.0685 t CO2e / t HDPE).

openLCA therefore is a **cross-check of the projection**, not a second design of
it. The projection's claims (functional unit, system boundary, quantities,
allocations, data origins) live in the Python model and the report; openLCA
checks that the same exchanges, linked and scaled through a product system,
return the same impact.

### Features

- **Same foreground, two engines.** The bridge writes the same six processes and
  their six flows into openLCA that the Python model declares: grid electricity,
  natural gas, methanol, ethylene, co-monomer and the resin itself, each with
  quantity and unit.
- **One documented impact method.** GWP100a from `IPCC 2007 / climate change -
  GWP 100a` over the method database `ecoinvent2_2_lcia_methods`.
- **Per-process breakdown.** The result is given by unit process, not only as a
  single score: electricity supply, methanol synthesis, methanol-to-olefins,
  natural gas supply, polymerisation and pelletising, co-monomer supply.
- **Scope grouping preserved.** Scope 1 = the first four (aggregated CO2e as
  `Carbon dioxide, fossil`), Scope 2 = electricity, Scope 3 = natural gas —
  the same split the report uses.
- **Background linking, optional and explicit.** Passing `--gas-provider` and/or
  `--power-provider` swaps the study's own proxy for a named dataset already in
  the database and turns the delta from a rounding check into a reconciliation.
- **Safe rebuild.** `--run --purge` deletes only the study's own prefix-named
  entities and rebuilds; the bridge refuses an unsafe re-run that would
  duplicate the study.
- **Verified presence checks.** `--check` confirms the database, method and the
  `Carbon dioxide, fossil` flow before any build.
- **Reconciliation in the console.** The `/lca` dashboard reads
  `openlca_run.json` and shows the openLCA total, the Python total, the
  difference, and (when a provider is linked) which datasets were used.

### How it is done

1. **OpenLCA runs an IPC server.** Start it from *Tools → Developer tools → IPC
   Server* on port 8080.
2. **`--check` confirms the calculation environment** has the method and flow.
3. **`build()` creates the six foreground unit processes and their flows** under
   the prefix `HDPE study / `, each with exchanges that carry the study's
exchange amounts.
4. **A product system is built from the foreground processes**; openLCA's own
   provider resolution links upstream providers using the flows, not the study's
   named default-provider hints.
5. **The method is run** and the impact is read back per process, then written to
   `outputs/LCA/openlca/openlca_run.json` alongside a `background` block.
6. **The LCA console reads that JSON** and renders the openLCA card.

The part that is easy to get wrong — and was wrong several times during setup —
is linking a background dataset. The reason is that a dataset supplies only its
own product flow, so the study's linkables must be expressed in the provider's
flow and unit, the study's proxy process for that input is dropped, and
openLCA's builder then links the provider and pulls in its upstream chain. The
bridge does exactly that, and verifies the provider ended up inside the product
system. Trying to force the link by setting default providers on a process or by
retargeting an exchange does not work: openLCA's builder ignores both. The
exact mechanism is described under `Linking a licensed background dataset`.

Two validation passes make the result dependable:

- Before purge, the requested provider names are resolved against the database,
  so a typo cannot delete the existing study.
- After the system is built, the bridge confirms each requested provider is
  present in `system.processes`; if not, it raises rather than reporting a silent
  0.

### Capability boundary (what it can do and what it is explicitly not)

- **It can** reproduce the foreground arithmetic and report a delta against the
  Python model.
- **It can** incorporate a licensed background dataset once one exists in the
  database, and report the shift.
- **It cannot**, with the current database, produce a licensed-e
coinvent-based footprint. The database open now (`ecoinvent2_2_lcia_methods`)
holds ecoinvent LCIA **methods** but no ecoinvent **process** dataset: the
`databases.json` list contains only that database, and its 20 processes are 14
from an unrelated Prosopis juliflora / biochar study plus the 6 HDPE study
processes. Linking ecoinvent means importing a licensed database into this
workspace first.
- **It cannot resolve species.** Scope 1 is an aggregated CO2e figure modelled
  as `Carbon dioxide, fossil` with a GWP100 factor of 1. The model therefore
  supports GWP100 and the carbon categories that follow from it, but it cannot
  support acidification, eutrophication, POCP or particulate-matter categories
  until the Scope 1 emissions are split into CO2, CH4 and N2O.
- **It does not model human toxicity, ecotoxicity, resource depletion, land use,
  water use, or the other categories outside GWP100** unless a complete
  characterisation happens to be available in the method database and the
  foreground flows are declared for them.
- **It links only the inputs that have a proxy process it can replace.** With
  this study that is electricity and natural gas. Every other upstream flow stays
  a study proxy; linking a provider does not change the rest of the inventory.

### Honest result status

- **Without a linked provider**, the two engines agree by construction at
  6.0685 t and the run is **not** an ecoinvent footprint.
- **With a provider linked**, the delta against 6.0685 t is the reconciliation:
  the product of the background dataset's factors on the foreground quantities.
  That shift is reported per unit process and is meaningful only when the
  dataset's geography, technology and reference year are recorded. **No such
  shift is currently available** because no licensed dataset is installed.

During development a synthetic test ran against two dummy providers (0.9 kg CO2
e/kWh for power and 0.5 kg CO2/kg for gas), written and deleted immediately.
That test returned 8.511557 t against an analytically expected 8.511556 t
(0.000002%), with the provider rows at 4,763.4 and 807.1 kg and both providers
confirmed inside the product system. This confirms the linking and reconciliation
path works; it is not an environmental result and is not present in any
deliverable.

### Limitations and open items

- **No licensed ecoinvent database is present in this install**, so the
  background-linking path is implemented and verified on synthetic providers but
  is unexercised on real ecoinvent data. The next step to get a real shift is to
  import a licensed ecoinvent database and pass the exact process names.
- **Provider matching is exact and by name only.** No fuzzy search; no
  technology-class matching. The user must supply the exact openLCA process name.
- **Quality of the reconciliation depends on the background dataset's
  metadata.** Geography, technology, reference year and cut-off must be recorded
  before the shift is quoted; the bridge cannot recover them from a bare
  process name.
- **Overlap with the Python model.** Because openLCA re-runs the same foreground,
  the card does not provide an entirely independent footprint; it confirms the
  arithmetic. Conclusions should not be strengthened beyond what both the
  foreground inventory and the chosen impact method support.
- **Method coverage is GWP100 only in practice** for this study, with the
  species-resolution caveat noted above.
- **IPC interaction quirks.** openLCA's IPC `get` and entity lists can return
  `None` entries or miss existing entities by name, so scans must tolerate nulls.
  This is an environmental quirk of the IPC layer, not of the study, and is
  handled in the bridge's helpers.

### What would turn this into a fully linked projection

1. Import a licensed ecoinvent database into this openLCA workspace.
2. Identify the exact process names for market electricity and for natural gas in
   that database (or the electricity and gas datasets the study's suppliers in
   fact use).
3. Run `--run --purge --gas-provider "..." --power-provider "..."`.
4. Read the reconciliation delta from the console, and record the provider's
   geography, technology, reference year and cut-offs so the shift can be
   explained rather than merely stated.
5. Update the report's page referring to background data and the quality record
   accordingly.

## What the agreement does and does not prove

- **It proves** the foreground arithmetic is reproducible in a second engine:
  the same exchange amounts, linked and scaled through a product system, return
  the same impact.
- **It does not prove** an ecoinvent-based footprint. No licensed background
  dataset is linked, so upstream gas and electricity carry the study's own
  factors, not provider datasets.
- **It does not resolve species.** Scope 1 is an aggregated CO2e figure entered
  as `Carbon dioxide, fossil` with a GWP100 factor of 1. That is exact for a
  CO2-only aggregate, but the model cannot support acidification,
  eutrophication, POCP or particulate-matter categories until the emissions are
  split into CO2, CH4 and N2O - which is why those categories stay unquantified.
- Linking a real background database will move the total, mainly through the
  grid factor. That difference is a reconciliation to report, not an error to
  hide. `outputs/LCA/openlca/README.md` gives the manual build sequence for that
  case.

## Taking it out of the database

`python -m lca.openlca_bridge --purge` on its own (without `--run`) is not
supported; run `--run --purge` to replace the study, or delete entities named
`HDPE study / ...` and the product system they belong to in the openLCA
navigator. Nothing else in the database is touched.
