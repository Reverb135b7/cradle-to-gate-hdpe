"""Life-cycle inventory: flows, provenance, pedigree and completeness.

The inventory is generated from the same parameter set as the PCF engine, so a
quantity can never disagree with the footprint.  Each flow carries its source,
geography, period, data type and a five-criterion pedigree score.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

import pandas as pd

from pcf.params import KG_PER_TONNE, ModelParams
from pcf.model import PCFModel

from .constants import (
    COMONOMER_INDICATIVE_KG_CO2E_PER_KG,
    COMONOMER_INDICATIVE_RANGE,
    PRIMARY_ENERGY_MJ_PER_KWH,
)

#: pedigree criteria, 1 = best, 5 = worst (Weidema & Wesnaes style)
DQI_CRITERIA = {
    "dq_reliability": "Reliability of the source data",
    "dq_completeness": "Completeness of the flow set for the node",
    "dq_temporal": "Temporal correlation to the reference period",
    "dq_geographical": "Geographical correlation",
    "dq_technological": "Technological correlation",
}


def _row(
    flow_id: str,
    stage_key: str,
    stage: str,
    flow: str,
    direction: str,
    kind: str,
    quantity: float,
    unit: str,
    source_id: str,
    data_type: str,
    dqi: Sequence[int],
    note: str = "",
    internal: bool = False,
    proxy: bool = False,
) -> Dict[str, Any]:
    reliability, completeness, temporal, geographical, technological = dqi
    score = (reliability + completeness + temporal + geographical + technological) / 5.0
    return {
        "flow_id": flow_id,
        "stage_key": stage_key,
        "stage": stage,
        "flow": flow,
        "direction": direction,
        "kind": kind,
        "quantity": quantity,
        "unit": unit,
        "internal": internal,
        "source_id": source_id,
        "data_type": data_type,
        "geography": "Global average" if stage_key != "ng_extraction" else "Global average supply",
        "period": "2024-2025",
        "dq_reliability": reliability,
        "dq_completeness": completeness,
        "dq_temporal": temporal,
        "dq_geographical": geographical,
        "dq_technological": technological,
        "dqi_score": round(score, 2),
        "dqi_rating": dqi_rating(score),
        "proxy": "yes" if proxy else "no",
        "note": note,
    }


def dqi_rating(score: float) -> str:
    if score <= 1.4:
        return "A"
    if score <= 2.2:
        return "B"
    if score <= 3.0:
        return "C"
    if score <= 3.8:
        return "D"
    return "E"


def flows_frame(params: ModelParams | None = None) -> pd.DataFrame:
    """One row per inventory flow, per functional unit."""
    p = params or ModelParams()
    model = PCFModel(p)
    f = model.flows
    share = p.mto_burden_share

    meoh_kwh = p.methanol_kwh_per_t * f.methanol_t
    mto_kwh = p.mto_kwh_per_t * f.ethylene_t * share
    hdpe_kwh = p.hdpe_kwh_per_t * f.hdpe_t
    meoh_steam = p.methanol_steam_gj_per_t * f.methanol_t
    mto_steam = p.mto_steam_gj_per_t * f.ethylene_t * share
    hdpe_steam = p.hdpe_steam_gj_per_t * f.hdpe_t

    rows = [
        _row(
            "NG-01", "ng_extraction", "Natural gas extraction & transport",
            "Natural gas, feedstock", "input", "feedstock",
            f.natural_gas_t * KG_PER_TONNE, "kg", "S1/S3", "derived",
            (2, 3, 2, 2, 2),
            "Derived from the chain ratios: 2.994 t MeOH / 1.855 t MeOH per t NG. "
            "The reforming fuel gas is not separately itemised in the specification (finding F-03).",
        ),
        _row(
            "ELE-01", "methanol", "Methanol synthesis (SMR/ATR + synthesis)",
            "Electricity, grid", "input", "energy",
            meoh_kwh, "kWh", "S2/S3", "derived",
            (3, 2, 2, 2, 2),
            "Back-calculated from the specified 570 kg CO2e/t Scope 2 at 0.475 kg CO2e/kWh.",
        ),
        _row(
            "ELE-02", "mto", "Methanol-to-olefins & separation",
            "Electricity, grid", "input", "energy",
            mto_kwh, "kWh", "S2/S3", "derived",
            (3, 2, 2, 2, 2),
            "Back-calculated from 485 kg CO2e/t C2H4 at 0.475 kg CO2e/kWh; scaled by the "
            "allocated node share when an allocation variant is selected.",
        ),
        _row(
            "ELE-03", "hdpe", "HDPE polymerisation & finishing",
            "Electricity, grid", "input", "energy",
            hdpe_kwh, "kWh", "S2/S3", "derived",
            (3, 2, 2, 2, 2),
            "Back-calculated from 315 kg CO2e/t HDPE at 0.475 kg CO2e/kWh.",
        ),
        _row(
            "STM-01", "methanol", "Methanol synthesis (SMR/ATR + synthesis)",
            "Steam, high pressure", "input", "energy",
            meoh_steam, "GJ", "S4", "secondary",
            (3, 2, 2, 2, 2),
            "Zero in the grid-equivalent base case; 6.1 GJ/t MeOH under the explicit-utilities basis.",
        ),
        _row(
            "STM-02", "mto", "Methanol-to-olefins & separation",
            "Steam, high pressure", "input", "energy",
            mto_steam, "GJ", "S4", "secondary",
            (3, 2, 2, 2, 2),
            "Zero in the grid-equivalent base case; 2.3 GJ/t C2H4 under the explicit-utilities basis.",
        ),
        _row(
            "STM-03", "hdpe", "HDPE polymerisation & finishing",
            "Steam, high pressure", "input", "energy",
            hdpe_steam, "GJ", "S4", "secondary",
            (3, 2, 2, 2, 2),
            "Zero in the grid-equivalent base case; 1.5 GJ/t HDPE under the explicit-utilities basis.",
        ),
        _row(
            "CH3OH-01", "methanol", "Methanol synthesis (SMR/ATR + synthesis)",
            "Methanol, intermediate", "output", "intermediate",
            f.methanol_t * KG_PER_TONNE, "kg", "S1", "derived",
            (3, 3, 2, 2, 2),
            "Internal flow: consumed at the MTO node, not a boundary output. Excluded from "
            "mass totals to avoid double counting.", internal=True,
        ),
        _row(
            "C2H4-01", "mto", "Methanol-to-olefins & separation",
            "Ethylene, polymer grade", "output", "intermediate",
            f.ethylene_t * KG_PER_TONNE, "kg", "S1", "derived",
            (3, 3, 2, 2, 2),
            "Internal flow: consumed at the polymerisation node. Co-products are netted out "
            "through the 2.95 t/t yield.", internal=True,
        ),
        _row(
            "COM-01", "hdpe", "HDPE polymerisation & finishing",
            "1-butene / 1-hexene co-monomer", "input", "material",
            f.comonomer_t * KG_PER_TONNE, "kg", "S2", "secondary (mass only)",
            (5, 1, 3, 3, 3),
            "Mass included at 1.5 wt%; no supply-chain burden is modelled. Proxy flag: "
            "gap sized separately in the completeness matrix, not in the headline result.",
            proxy=True,
        ),
        _row(
            "EM-01", "ng_extraction", "Natural gas extraction & transport",
            "Upstream CO2e (extraction, processing, transport)", "output", "emission",
            f.natural_gas_t * KG_PER_TONNE * p.ef_ng_upstream, "kg CO2e", "S2", "calculated",
            (2, 2, 2, 2, 2),
            "0.380 kg CO2e/kg NG, including 1.2 % fugitive methane on an AR6 GWP100 basis.",
        ),
        _row(
            "EM-02", "methanol", "Methanol synthesis (SMR/ATR + synthesis)",
            "Direct CO2e (reforming + synthesis)", "output", "emission",
            f.methanol_t * p.methanol_scope1, "kg CO2e", "S3", "secondary",
            (3, 2, 2, 2, 2),
            "Aggregated Scope 1 CO2e/t MeOH; not species-resolved. Carbon closure of node 1 "
            "is 100 % once the implied fuel gas is itemised (finding F-03).",
        ),
        _row(
            "EM-03", "mto", "Methanol-to-olefins & separation",
            "Direct CO2e (catalyst regeneration)", "output", "emission",
            f.ethylene_t * p.mto_scope1 * share, "kg CO2e", "S3", "secondary",
            (4, 2, 2, 2, 2),
            "Aggregated Scope 1 CO2e/t C2H4. Node carbon closure is 98.50 % (finding F-01); "
            "closure-consistent value is <= 913 kg CO2e/t.",
        ),
        _row(
            "EM-04", "hdpe", "HDPE polymerisation & finishing",
            "Direct CO2e (venting + flaring)", "output", "emission",
            f.hdpe_t * p.hdpe_scope1, "kg CO2e", "S3", "secondary",
            (4, 2, 2, 2, 2),
            "Aggregated Scope 1 CO2e/t HDPE. Node carbon closure is 99.06 % (finding F-02).",
        ),
        _row(
            "PRD-01", "hdpe", "HDPE polymerisation & finishing",
            "HDPE resin, reference product", "output", "product",
            f.hdpe_t * KG_PER_TONNE, "kg", "-", "reference",
            (1, 1, 1, 1, 1),
            "Reference flow. All quantities in this table are per this amount.",
        ),
    ]
    return pd.DataFrame(rows)


def stage_frame(params: ModelParams | None = None) -> pd.DataFrame:
    """Aggregated inventory and burden by life-cycle stage."""
    p = params or ModelParams()
    flows = flows_frame(p)
    stages = {s.key: s for s in PCFModel(p).stages()}
    total = sum(s.total for s in stages.values()) or 1.0

    rows = []
    for key, label in (
        ("ng_extraction", "Natural gas extraction & transport"),
        ("methanol", "Methanol synthesis (SMR/ATR + synthesis)"),
        ("mto", "Methanol-to-olefins & separation"),
        ("hdpe", "HDPE polymerisation & finishing"),
    ):
        sub = flows[flows["stage_key"] == key]
        electricity = float(sub.loc[sub["flow_id"].str.startswith("ELE"), "quantity"].sum())
        steam = float(sub.loc[sub["flow_id"].str.startswith("STM"), "quantity"].sum())
        declared_energy = 0.0
        if key == "methanol":
            declared_energy = p.methanol_energy_gj_per_t * PCFModel(p).flows.methanol_t * 1000.0
        energy_mj = declared_energy + electricity * PRIMARY_ENERGY_MJ_PER_KWH + steam * 1000.0
        stage = stages[key]
        rows.append(
            {
                "stage_key": key,
                "stage": label,
                "scope1_kg": stage.scope1,
                "scope2_kg": stage.scope2,
                "scope3_kg": stage.scope3,
                "total_kg_co2e": stage.total,
                "share_pct": 100.0 * stage.total / total,
                "electricity_kwh": electricity,
                "steam_gj": steam,
                "declared_fuel_gj": declared_energy / 1000.0,
                "energy_mj": energy_mj,
                "gwp_intensity_per_kg": stage.total / 1000.0,
            }
        )
    frame = pd.DataFrame(rows)
    frame.loc[len(frame)] = {
        "stage_key": "total",
        "stage": "Total",
        "scope1_kg": frame["scope1_kg"].sum(),
        "scope2_kg": frame["scope2_kg"].sum(),
        "scope3_kg": frame["scope3_kg"].sum(),
        "total_kg_co2e": frame["total_kg_co2e"].sum(),
        "share_pct": 100.0,
        "electricity_kwh": frame["electricity_kwh"].sum(),
        "steam_gj": frame["steam_gj"].sum(),
        "declared_fuel_gj": frame["declared_fuel_gj"].sum(),
        "energy_mj": frame["energy_mj"].sum(),
        "gwp_intensity_per_kg": frame["total_kg_co2e"].sum() / 1000.0,
    }
    return frame


def dqi_frame(params: ModelParams | None = None) -> pd.DataFrame:
    """Pedigree summary for the source register and workbook."""
    flows = flows_frame(params)
    return flows[
        [
            "flow_id",
            "flow",
            "stage",
            "dq_reliability",
            "dq_completeness",
            "dq_temporal",
            "dq_geographical",
            "dq_technological",
            "dqi_score",
            "dqi_rating",
            "proxy",
            "note",
        ]
    ].copy()


def source_register() -> pd.DataFrame:
    """Provenance for every factor and dataset the model relies on."""
    rows = [
        {
            "source_id": "S1",
            "source": "Integrated PCF technical specification, section 2",
            "type": "Engineering specification",
            "supplies": "Chain stoichiometry: 1.855 t MeOH/t NG, 2.95 t MeOH/t C2H4, 1.015 t C2H4/t HDPE, 1.5 wt% co-monomer",
            "geography": "n/a",
            "period": "2024-2025",
            "version": "1.0 (repository file)",
            "note": "Nameplate / design basis, not metered. No uncertainty stated.",
        },
        {
            "source_id": "S2",
            "source": "Integrated PCF technical specification, section 3",
            "type": "Emission factors",
            "supplies": "0.380 kg CO2e/kg NG upstream (Scope 3.1); 0.475 kg CO2e/kWh grid; 68.5 kg CO2e/GJ steam",
            "geography": "Global average",
            "period": "2024-2025",
            "version": "1.0 (repository file)",
            "note": "Stated as global average industrial factors; no dataset identifier or database version is given, which is a documented gap.",
        },
        {
            "source_id": "S3",
            "source": "Integrated PCF technical specification, section 4",
            "type": "Node inventories",
            "supplies": "Scope 1 610/975/125 kg CO2e per t MeOH/C2H4/HDPE; Scope 2 570/485/315 kg CO2e per t node product",
            "geography": "Global average",
            "period": "2024-2025",
            "version": "1.0 (repository file)",
            "note": "Aggregated CO2e, not species-resolved; two nodes fail the specification's own carbon closure test.",
        },
        {
            "source_id": "S4",
            "source": "PCF engine execution script",
            "type": "Engineering script",
            "supplies": "Alternative utility decomposition: 320/700/450 kWh/t and 6.1/2.3/1.5 GJ steam/t",
            "geography": "Global average",
            "period": "2024-2025",
            "version": "1.0 (repository file)",
            "note": "Second Scope 2 basis. Does not reconcile to the specification's scenario response.",
        },
        {
            "source_id": "S5",
            "source": "IPCC AR6 WG1, chapter 7 (radiative forcing / GWP100)",
            "type": "Impact method",
            "supplies": "100-year global warming potentials; CO2e basis",
            "geography": "n/a",
            "period": "2021",
            "version": "AR6",
            "note": "Method reference only. This study inherits the CO2e aggregation from the specification and does not re-characterise individual species.",
        },
        {
            "source_id": "S6",
            "source": "ISO 14040:2006, ISO 14044:2006, ISO 14067:2018; GHG Protocol Product Standard",
            "type": "Method standard",
            "supplies": "Goal and scope, inventory, allocation hierarchy, interpretation, reporting",
            "geography": "n/a",
            "period": "2006-2018",
            "version": "as cited",
            "note": "Framework compliance claimed, not certified.",
        },
        {
            "source_id": "S7",
            "source": "Indicative 2024-2025 contract prices (ethylene 1,150; propylene 950; heavies 700 USD/t)",
            "type": "Economic parameter",
            "supplies": "Economic allocation sensitivity only",
            "geography": "Global",
            "period": "2024-2025",
            "version": "analysis assumption",
            "note": "Not part of the inventory; used only to compute the economic allocation share.",
        },
        {
            "source_id": "S8",
            "source": "Derived conversion: 3.6 MJ/kWh / 0.40 generating efficiency",
            "type": "Derived assumption",
            "supplies": "Primary energy indicator, 9.0 MJ per kWh delivered (range 7.2-12.0)",
            "geography": "Global average",
            "period": "n/a",
            "version": "analysis assumption",
            "note": "Screening conversion, not a cumulative-energy-demand database result.",
        },
        {
            "source_id": "S9",
            "source": "Carbon-balance module of this repository (pcf.validation)",
            "type": "Internal consistency check",
            "supplies": "Closure-consistent bounds: MTO <= 913 kg CO2e/t; C2H4 1.015-1.025 t/t HDPE; MeOH 2.95-2.996 t/t",
            "geography": "n/a",
            "period": "2025",
            "version": "1.0",
            "note": "The only quantitative uncertainty ranges in the study that are constrained by the data themselves.",
        },
    ]
    return pd.DataFrame(rows)


def flows_frame_openlca(result: Any) -> pd.DataFrame:
    """openLCA-flavoured foreground flow table exported alongside exchanges/mapping.

    This is the legacy helper the CLI and the old openLCA handover rely on.  It is
    populated from the same foreground inventory used elsewhere in the study, so it
    stays consistent with the workbook and the impact layer.
    """
    params = result.model.params if hasattr(result, "model") else None
    return flows_frame(params)


def completeness_frame(params: ModelParams | None = None) -> pd.DataFrame:
    """Every module, its status, and the materiality of what is missing."""
    p = params or ModelParams()
    model = PCFModel(p)
    stages = {s.key: s for s in model.stages()}
    total = model.total_kg or 1.0
    comonomer_kg = model.flows.comonomer_t * KG_PER_TONNE
    low = comonomer_kg * COMONOMER_INDICATIVE_RANGE[0]
    high = comonomer_kg * COMONOMER_INDICATIVE_RANGE[1]
    mid = comonomer_kg * COMONOMER_INDICATIVE_KG_CO2E_PER_KG

    def _stage(key: str) -> tuple[float, float]:
        value = stages[key].total
        return value, 100.0 * value / total

    rows = [
        ("Natural gas extraction & transport", "Upstream supply", "Quantified", *_stage("ng_extraction"),
         "Specification factor 0.380 kg CO2e/kg; coverage of feedstock gas only."),
        ("Methanol synthesis", "Foreground process", "Quantified", *_stage("methanol"),
         "Scope 1 + Scope 2 + embedded upstream gas."),
        ("MTO & separation", "Foreground process", "Quantified", *_stage("mto"),
         "Scope 1 + Scope 2; node carbon balance fails at 98.50 %."),
        ("HDPE polymerisation & finishing", "Foreground process", "Quantified", *_stage("hdpe"),
         "Scope 1 + Scope 2; node carbon balance fails at 99.06 %."),
        ("Co-monomer supply", "Material input", "Not quantified", mid, 100.0 * mid / total,
         f"Mass {comonomer_kg:.0f} kg modelled; burden 0. {low:.0f}-{high:.0f} kg CO2e "
         f"({100.0 * low / total:.2f}-{100.0 * high / total:.2f} %) if a 1.5-2.5 kg CO2e/kg "
         "proxy were used. Proxy is indicative only and is excluded from the headline result."),
        ("Catalyst & adsorbent manufacture", "Material input", "Not quantified", None, None,
         "SAPO-34, Cu/ZnO/Al2O3, Ziegler-Natta/metallocene. No quantities in the source; "
         "obtain catalyst production datasets before claiming coverage."),
        ("Water supply", "Utility", "Not quantified", None, None,
         "No withdrawal or consumption inventory. Blocks a water-scarcity result."),
        ("Wastewater treatment", "Emission control", "Not quantified", None, None,
         "No volume or load data; treatment route undefined."),
        ("Solid / hazardous waste", "Waste", "Not quantified", None, None,
         "No waste quantities or routes; spent catalyst and sludge are the material streams."),
        ("Packaging", "Downstream of gate", "Excluded", None, None,
         "Gate is defined at pelletising exit; packaging is a separate module."),
        ("Outbound transport", "Downstream of gate", "Excluded", None, None,
         "No destination, mode or distance defined."),
        ("Use phase", "Downstream of gate", "Excluded", None, None,
         "Product applications are open-ended; outside the declared boundary."),
        ("End-of-life / recycling", "Downstream of gate", "Excluded", None, None,
         "No waste-scenario data; a separate gate-to-grave module is required."),
        ("Acidification, eutrophication, POCP, PM, water, land", "Impact assessment", "Blocked", None, None,
         "Requires species-resolved emissions (SO2, NOx, NH3, NMVOC, PM, P, N, water). The "
         "inventory carries aggregated CO2e only, so these categories are declared, not estimated."),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "module",
            "life_cycle_stage",
            "status",
            "materiality_kg_co2e",
            "materiality_pct",
            "basis",
        ],
    )
    frame["materiality_kg_co2e"] = frame["materiality_kg_co2e"].astype("Float64")
    frame["materiality_pct"] = frame["materiality_pct"].astype("Float64")
    return frame
