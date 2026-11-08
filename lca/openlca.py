
"""openLCA handover: foreground exchange tables, elementary-flow mapping and characterisation coverage.

A native .zolca cannot be produced here (openLCA is a desktop application with
a licensed background database).  These tables are the foreground system, at
the same quantitative references as the Python model, so the product system can
be rebuilt and checked against 6.068 t.

The characterisation exports (`characterisation_coverage.csv`, `characterisation_factors.csv`)
come from the open database's impact methods and describe what the database *can*
characterise, not what the foreground *does* emit.  With the current foreground
inventory (aggregated CO2e mapped to "Carbon dioxide, fossil") only climate change
is characterisable from the foreground; every other category is recorded as a
coverage gap.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pcf.model import PCFModel
from pcf.params import ModelParams

from .inventory import flows_frame, flows_frame_openlca
from .results import LcaResult


# Global elementary-flow names the current foreground can supply.
# In this study those are the aggregated CO2e flows mapped to "Carbon dioxide, fossil".
FOREGROUND_ELEMENTARY_FLOWS = ["Carbon dioxide, fossil"]



def exchanges_frame(params: ModelParams | None = None) -> pd.DataFrame:
    p = params or ModelParams()
    model = PCFModel(p)
    f = model.flows
    rows = [
        # node 1
        ("P1 Methanol synthesis", "Methanol", "input", "Natural gas, feedstock", "technosphere",
         f.natural_gas_t * 1000 / f.methanol_t, "kg", "market for natural gas, high pressure",
         "S1/S2", "Provider must include extraction, processing and transport."),
        ("P1 Methanol synthesis", "Methanol", "input", "Electricity, grid", "technosphere",
         p.methanol_kwh_per_t, "kWh", "market for electricity, industrial",
         "S2", "Grid factor 0.475 kg CO2e/kWh in the specification basis."),
        ("P1 Methanol synthesis", "Methanol", "output", "Methanol", "technosphere",
         1000.0, "kg", "", "S1", "Quantitative reference."),
        ("P1 Methanol synthesis", "Methanol", "output", "Carbon dioxide, fossil (as CO2e)", "elementary",
         p.methanol_scope1, "kg", "", "S3", "Aggregate Scope 1 CO2e; species split not supplied."),
        # node 2
        ("P2 MTO and separation", "Ethylene", "input", "Methanol", "technosphere",
         p.methanol_per_ethylene * 1000, "kg", "P1 Methanol synthesis", "S1", "Internal link."),
        ("P2 MTO and separation", "Ethylene", "input", "Electricity, grid", "technosphere",
         p.mto_kwh_per_t, "kWh", "market for electricity, industrial", "S2", ""),
        ("P2 MTO and separation", "Ethylene", "output", "Ethylene, polymer grade", "technosphere",
         1000.0, "kg", "", "S1", "Quantitative reference."),
        ("P2 MTO and separation", "Ethylene", "output", "Carbon dioxide, fossil (as CO2e)", "elementary",
         p.mto_scope1, "kg", "", "S3", "Catalyst regeneration; aggregate CO2e."),
        # node 3
        ("P3 HDPE polymerisation", "HDPE", "input", "Ethylene, polymer grade", "technosphere",
         p.ethylene_per_hdpe * 1000, "kg", "P2 MTO and separation", "S1", "Internal link."),
        ("P3 HDPE polymerisation", "HDPE", "input", "Electricity, grid", "technosphere",
         p.hdpe_kwh_per_t, "kWh", "market for electricity, industrial", "S2", ""),
        ("P3 HDPE polymerisation", "HDPE", "input", "1-butene / 1-hexene", "technosphere",
         p.comonomer_wt_fraction * 1000, "kg", "market for 1-butene", "S2",
         "No burden modelled in the specification; linking a provider will add 0.4-0.6 %."),
        ("P3 HDPE polymerisation", "HDPE", "output", "HDPE resin", "technosphere",
         1000.0, "kg", "", "-", "Quantitative reference."),
        ("P3 HDPE polymerisation", "HDPE", "output", "Carbon dioxide, fossil (as CO2e)", "elementary",
         p.hdpe_scope1, "kg", "", "S3", "Venting and flaring; aggregate CO2e."),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "process",
            "process_reference_product",
            "exchange_type",
            "flow",
            "flow_type",
            "amount",
            "unit",
            "provider",
            "source_id",
            "note",
        ],
    )



def elementary_flows_frame(params: ModelParams | None = None) -> pd.DataFrame:
    """Elementary flows the foreground actually emits for characterisation.

    In this study the Scope 1 emissions are supplied as aggregated CO2e and mapped
    to "Carbon dioxide, fossil".  This frame is the truthful foreground vector for
    any multi-category characterisation: it is a single flow, not a species split.
    """
    p = params or ModelParams()
    model = PCFModel(p)
    rows = []
    for stage_key, label, flow_name, basis, qty_kg in [
        ("methanol", "Methanol synthesis (SMR/ATR + synthesis)", "Carbon dioxide, fossil", "Scope 1 aggregate CO2e", model.flows.methanol_t * p.methanol_scope1),
        ("mto", "Methanol-to-olefins & separation", "Carbon dioxide, fossil", "Scope 1 aggregate CO2e", model.flows.ethylene_t * p.mto_scope1 * p.mto_burden_share),
        ("hdpe", "HDPE polymerisation & finishing", "Carbon dioxide, fossil", "Scope 1 aggregate CO2e", model.flows.hdpe_t * p.hdpe_scope1),
    ]:
        rows.append(
            {
                "flow": flow_name,
                "flow_type": "Elementary flow",
                "compartment": "air / unspecified",
                "stage": label,
                "stage_key": stage_key,
                "quantity_kg": qty_kg,
                "unit": "kg",
                "data_type": basis,
                "note": "Aggregated CO2e mapped to Carbon dioxide, fossil; not species-resolved.",
            }
        )
    return pd.DataFrame(rows)


def characterisation_coverage(params: ModelParams | None = None) -> pd.DataFrame:
    """What the open database's methods can characterise, vs what the foreground emits.

    This is read-only discovery. It does not fabricate numbers for categories the
    foreground cannot supply.
    """
    import olca_ipc as ipc
    import olca_schema as o
    from .matrix import all_methods, foreground_coverage, method_matrix

    client = ipc.Client()
    matrix = method_matrix(client, "ReCiPe Midpoint (H)")
    cov = foreground_coverage(matrix, FOREGROUND_ELEMENTARY_FLOWS)
    rows = []
    for c in cov["coverage"]:
        rows.append(
            {
                "impact_category": c["category"],
                "method": cov["method"],
                "coverable_from_foreground": c["coverable"],
                "covering_foreground_flows": ", ".join(c["covering_foreground_flows"]),
                "all_matrix_flows_for_category": ", ".join(c["all_matrix_flows_for_category"]),
            }
        )
    return pd.DataFrame(rows)


def characterisation_factors(method_name: str, params: ModelParams | None = None) -> pd.DataFrame:
    """Every factor for one method, written as a reference table.

    One row per impact factor: impact category, elementary flow, unit, value.
    """
    import olca_ipc as ipc
    import olca_schema as o
    from .matrix import method_matrix

    client = ipc.Client()
    matrix = method_matrix(client, method_name)
    rows = []
    for cat in matrix.get("impact_categories", []):
        for f in cat.get("factors", []):
            rows.append(
                {
                    "method": method_name,
                    "impact_category": cat.get("category"),
                    "impact_category_ref_unit": cat.get("ref_unit"),
                    "elementary_flow": f.get("flow"),
                    "flow_property": f.get("flow_property"),
                    "factor_unit": f.get("unit"),
                    "value": f.get("value"),
                    "location": f.get("location"),
                }
            )
    return pd.DataFrame(rows)


def write_openlca(result: LcaResult, directory: Path) -> dict[str, Path]:
    flows = flows_frame(result.model.params)
    mapping = {
        "NG-01": ("Technosphere flow", "Fuel / natural gas", "market for natural gas"),
        "ELE-01": ("Technosphere flow", "Electricity / grid", "market for electricity, industrial"),
        "ELE-02": ("Technosphere flow", "Electricity / grid", "market for electricity, industrial"),
        "ELE-03": ("Technosphere flow", "Electricity / grid", "market for electricity, industrial"),
        "STM-01": ("Technosphere flow", "Heat / steam", "market for steam"),
        "STM-02": ("Technosphere flow", "Heat / steam", "market for steam"),
        "STM-03": ("Technosphere flow", "Heat / steam", "market for steam"),
        "CH3OH-01": ("Technosphere flow", "Chemical / methanol", "internal"),
        "C2H4-01": ("Technosphere flow", "Chemical / ethylene", "internal"),
        "COM-01": ("Technosphere flow", "Chemical / olefin", "market for 1-butene"),
        "EM-01": ("Elementary flow", "Emission to air / unspecified", "n/a"),
        "EM-02": ("Elementary flow", "Emission to air / unspecified", "n/a"),
        "EM-03": ("Elementary flow", "Emission to air / unspecified", "n/a"),
        "EM-04": ("Elementary flow", "Emission to air / unspecified", "n/a"),
        "PRD-01": ("Technosphere flow", "Polymer / HDPE", "n/a"),
    }
    rows = []
    for flow in flows.itertuples():
        flow_type, category, provider = mapping.get(
            flow.flow_id, ("Technosphere flow", "unspecified", "unspecified")
        )
        rows.append(
            {
                "flow_id": flow.flow_id,
                "flow": flow.flow,
                "flow_type": flow_type,
                "openlca_category": category,
                "unit": flow.unit,
                "amount_per_fu": flow.quantity,
                "provider_hint": provider,
                "is_elementary": "yes" if flow_type == "Elementary flow" else "no",
                "note": flow.note,
            }
        )
    return pd.DataFrame(rows)


def mapping_frame(result: LcaResult) -> pd.DataFrame:
    flows = flows_frame(result.model.params)
    rows = []
    for flow in flows.itertuples():
        if flow.flow_id.startswith("EM"):
            rows.append(
                {
                    "flow_id": flow.flow_id,
                    "our_flow": flow.flow,
                    "openlca_flow": "Carbon dioxide, fossil",
                    "compartment": "air / unspecified",
                    "basis": "aggregate CO2e entered as CO2 - proxy",
                    "warning": "Overstates CO2 mass if methane or N2O are present; "
                               "replace with a species split for a compliant inventory.",
                }
            )
        else:
            rows.append(
                {
                    "flow_id": flow.flow_id,
                    "our_flow": flow.flow,
                    "openlca_flow": flow.flow.split(",")[0],
                    "compartment": "technosphere",
                    "basis": "physical flow",
                    "warning": "",
                }
            )
    return pd.DataFrame(rows)


_README = """# openLCA handover

## Status

Two things are handed over. First, the complete foreground system as tables:
every process, exchange, amount and provider requirement, at the same
quantitative references as the Python model. Second, an automated bridge that
builds that system inside a running openLCA and calculates it, so the model does
not have to be entered by hand.

The bridge (`python -m lca.openlca_bridge --run`, see `OPENLCA_SETUP.md`) creates
six namespaced unit processes, links their providers, runs the database's GWP100
method and writes `openlca_run.json`. On openLCA 2.6.2 with IPCC 2007 it
reproduces the Python total to the reported digits, because it carries the same
foreground amounts: it verifies the arithmetic, not a licensed background
dataset. Entering the model by hand from these tables remains the route when a
real background database is linked, and should take roughly 30-60 minutes.

## Prerequisites

- openLCA 2.x
- A licensed background database. The specification's factors are generic
  ("global average"), so no exact dataset is named in the source. Choose a
  database whose geography, technology and reference year you can defend, and
  record its name and version in the study report.
- The IPCC 2021 GWP100 method (available in openLCA's built-in methods), or
  IPCC AR6 if present.

## Automated build

With a database open in openLCA and Tools -> Developer tools -> IPC Server
started on port 8080:

```
python -m lca.openlca_bridge --check          # connect, method and CO2 flow
python -m lca.openlca_bridge --run --purge    # rebuild and calculate
```

The bridge writes into the database that is currently open, under the process
prefix `HDPE study / `. `--purge` deletes any previous run of that prefix first;
without it the run is additive. Nothing else in the database is touched.

## Process structure

| ID | Process | Quantitative reference | Direct Scope 1 (kg CO2e) |
| --- | --- | --- | --- |
| P1 | Methanol synthesis | 1,000 kg methanol | 610 |
| P2 | MTO and separation | 1,000 kg ethylene | 975 |
| P3 | HDPE polymerisation | 1,000 kg HDPE resin | 125 |

Electricity demand: 1,200 / 1,021.05 / 663.16 kWh per 1,000 kg of node product.
The grid-equivalent base case has no separate steam input; the explicit-utility
variant (6.1 / 2.3 / 1.5 GJ/t) is a scenario, not the base case.

## Build sequence

1. **Create the flows.** Use `flows.csv` and `mapping.csv`. For the four
   emission flows the specification gives an aggregate CO2e figure, not a
   species split; the mapping enters it as fossil CO2 and flags the proxy. A
   compliant model needs the species split (CO2, CH4, N2O) before the result can
   be called an inventory.
2. **Create the three processes** with the quantitative references above.
3. **Enter the exchanges** from `exchanges.csv`. Amounts are per the process
   reference, not per functional unit.
4. **Link providers.** Electricity and natural gas should come from the
   background database, not from the emission factors in the specification.
   Linking a real grid dataset will change the result; that is expected and
   should be recorded as a reconciliation, not hidden.
5. **Build the product system** P1 -> P2 -> P3 and set the reference flow to
   1,000 kg HDPE.
6. **Set allocation.** Base case: no allocation at P2 (the 2.95 t/t methanol
   demand already nets the co-products). Sensitivity: mass allocation at the
   42/38/20 carbon split, or economic allocation at the reference prices.
7. **Run IPCC 2021 GWP100.** Record the method version.
8. **Check the result** against the specification basis: 6,068 kg CO2e per
   functional unit. A database-linked result will differ; report the difference
   and its cause.
9. **Export** the product system (`.zolca`), the process table, the LCIA result
   and the method version. Add them to the deliverables folder.

## What changes when a real database is linked

- The upstream natural gas factor (0.380 kg CO2e/kg) is replaced by the
  provider dataset, including its own methane leakage assumptions.
- The grid factor (0.475 kg CO2e/kWh) is replaced by the chosen geography and
  year - the single largest source of difference.
- Co-monomer supply, currently a mass-only flow, acquires a burden (0.4-0.6 %
  of the climate result at an indicative 2 kg CO2e/kg).
- The aggregate Scope 1 CO2e is split into species, which is what makes
  acidification, eutrophication and photochemical-ozone categories possible at
  all.

## Verification checklist

- [ ] Product system reference flow is 1,000 kg HDPE.
- [ ] Mass balance closes at each process within the database's own tolerance.
- [ ] Electricity and gas are provider-linked, not entered as emission factors.
- [ ] Database name and version are recorded in the report.
- [ ] Method and version (IPCC 2021 GWP100) are recorded.
- [ ] Result is reconciled to 6,068 kg CO2e/t and the delta explained.
- [ ] Allocation basis is stated.
- [ ] Native project exported and archived.
"""


def write_openlca(result: LcaResult, directory: Path) -> dict[str, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    paths["exchanges"] = directory / "exchanges.csv"
    exchanges_frame(result.model.params).to_csv(paths["exchanges"], index=False)
    paths["flows"] = directory / "flows.csv"
    flows_frame_openlca(result).to_csv(paths["flows"], index=False)
    paths["mapping"] = directory / "mapping.csv"
    mapping_frame(result).to_csv(paths["mapping"], index=False)
    paths["readme"] = directory / "README.md"
    paths["readme"].write_text(_README, encoding="utf-8")
    paths["elementary_flows"] = directory / "elementary_flows.csv"
    elementary_flows_frame(result.model.params).to_csv(paths["elementary_flows"], index=False)
    paths["characterisation_coverage"] = directory / "characterisation_coverage.csv"
    characterisation_coverage(result.model.params).to_csv(paths["characterisation_coverage"], index=False)
    return paths
