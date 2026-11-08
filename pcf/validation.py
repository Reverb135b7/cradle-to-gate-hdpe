"""Data-model validation for the integrated PCF model.

Spec section 6.1 requires that mass balance closure is maintained within
+/- 0.1 % across all three unit operations.  This module performs that check
independently of the emission calculation, by balancing *carbon* through each
node (the only element that is conserved in a flowsheet carrying CO2, methanol
and olefins), and it re-checks the specification's published intermediate and
headline results against the implemented model.

Findings are returned as explicit records so the report can explain every
discrepancy with a quantified remediation instead of silently forcing closure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

import pandas as pd

from .model import PCFModel
from .params import (
    C_FRACTION_ETHYLENE,
    C_FRACTION_METHANE,
    C_FRACTION_METHANOL,
    CO2_PER_C,
    KG_PER_TONNE,
    SCENARIO_BY_KEY,
)
from .utility_basis import basis_comparison, steam_share_pct, utility_frame

TOLERANCE_PCT = 0.1  # ISO/technical-specification mass balance closure limit


@dataclass(frozen=True)
class Check:
    """One pass/fail validation check."""

    check_id: str
    description: str
    value: float
    reference: float
    unit: str
    tolerance_pct: float
    note: str = ""

    @property
    def deviation_pct(self) -> float:
        if self.reference == 0:
            return 0.0 if self.value == 0 else float("inf")
        return 100.0 * (self.value - self.reference) / self.reference

    @property
    def status(self) -> str:
        dev = abs(self.deviation_pct)
        if dev <= self.tolerance_pct:
            return "PASS"
        if dev <= 5.0 * self.tolerance_pct:
            return "WARN"
        return "FAIL"


@dataclass(frozen=True)
class CarbonBalance:
    """Carbon bookkeeping for one unit operation, kg C per functional unit."""

    node: str
    basis: str
    carbon_in_kg: float
    carbon_out_kg: float
    makeup_stream: str
    makeup_kg_c: float
    makeup_input_kg: float
    note: str

    @property
    def raw_closure_pct(self) -> float:
        """Closure of the inventory exactly as specified (no make-up stream)."""
        if self.carbon_out_kg == 0:
            return 0.0
        return 100.0 * self.carbon_in_kg / self.carbon_out_kg

    @property
    def closure_pct(self) -> float:
        """Closure once the implied make-up input stream is credited."""
        if self.carbon_out_kg == 0:
            return 0.0
        return 100.0 * (self.carbon_in_kg + self.makeup_kg_c) / self.carbon_out_kg

    @property
    def closure_deviation_pct(self) -> float:
        return self.closure_pct - 100.0


@dataclass(frozen=True)
class Finding:
    """A quantified discrepancy or limitation surfaced by the validation."""

    finding_id: str
    severity: str  # INFO | WARN | FAIL
    title: str
    detail: str
    impact_kg_co2e: float | None = None


@dataclass(frozen=True)
class ValidationReport:
    checks: Sequence[Check]
    carbon: Sequence[CarbonBalance]
    findings: Sequence[Finding]

    @property
    def status(self) -> str:
        if any(c.status == "FAIL" for c in self.checks):
            return "FAIL"
        if any(c.status == "WARN" for c in self.checks):
            return "WARN"
        return "PASS"

    def check_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "id": c.check_id,
                    "check": c.description,
                    "model": c.value,
                    "specified": c.reference,
                    "unit": c.unit,
                    "dev_%": c.deviation_pct,
                    "tol_%": c.tolerance_pct,
                    "status": c.status,
                    "note": c.note,
                }
                for c in self.checks
            ]
        )

    def carbon_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "node": b.node,
                    "basis": b.basis,
                    "C in (kg)": b.carbon_in_kg,
                    "C out (kg)": b.carbon_out_kg,
                    "make-up stream": b.makeup_stream,
                    "make-up (kg C)": b.makeup_kg_c,
                    "raw closure %": b.raw_closure_pct,
                    "closure %": b.closure_pct,
                    "deviation %": b.closure_deviation_pct,
                    "status": "PASS" if abs(b.closure_deviation_pct) <= TOLERANCE_PCT else "FAIL",
                }
                for b in self.carbon
            ]
        )


# --------------------------------------------------------------------- carbon
def carbon_balances(model: PCFModel) -> List[CarbonBalance]:
    """Balance carbon through each node and solve for any make-up input."""
    p = model.params
    f = model.flows

    # --- Node 1: natural gas -> methanol ---------------------------------
    # Carbon supplied by feedstock NG, carbon leaving as methanol and as the
    # process/fuel CO2 of the Scope 1 inventory.  The shortfall is the natural
    # gas fuel stream that the specification's Scope 1 figure implies but does
    # not itemise as an input.
    meoh_c = f.methanol_t * KG_PER_TONNE * C_FRACTION_METHANOL
    ng_feed_c = f.natural_gas_t * KG_PER_TONNE * C_FRACTION_METHANE
    meoh_co2_c = f.methanol_t * p.methanol_scope1 / CO2_PER_C
    node1_makeup = max(0.0, meoh_c + meoh_co2_c - ng_feed_c)
    node1 = CarbonBalance(
        node="Node 1 - Methanol synthesis",
        basis="per functional unit",
        carbon_in_kg=ng_feed_c,
        carbon_out_kg=meoh_c + meoh_co2_c,
        makeup_stream="Natural gas (fuel / reforming heat)",
        makeup_kg_c=node1_makeup,
        makeup_input_kg=node1_makeup / C_FRACTION_METHANE,
        note=(
            "Closes only when the implied reforming fuel gas is itemised as an input "
            f"({node1_makeup / C_FRACTION_METHANE / KG_PER_TONNE / f.methanol_t:.3f} t NG "
            "per t methanol); on feedstock NG alone the inventory closes at "
            f"{100.0 * ng_feed_c / (meoh_c + meoh_co2_c):.1f} %."
        ),
    )

    # --- Node 2: methanol -> ethylene ------------------------------------
    mto_in_c = f.methanol_t * KG_PER_TONNE * C_FRACTION_METHANOL
    et_c = f.ethylene_t * KG_PER_TONNE * C_FRACTION_ETHYLENE
    mto_co2_c = f.ethylene_t * p.mto_scope1 / CO2_PER_C
    node2 = CarbonBalance(
        node="Node 2 - MTO & separation",
        basis="per functional unit",
        carbon_in_kg=mto_in_c,
        carbon_out_kg=et_c + mto_co2_c,
        makeup_stream="none",
        makeup_kg_c=0.0,
        makeup_input_kg=0.0,
        note=(
            "Ethylene carbon plus catalyst-regeneration CO2 exceeds the carbon "
            "delivered by the specified methanol demand; co-product carbon would "
            "widen the gap further."
        ),
    )

    # --- Node 3: ethylene -> HDPE ----------------------------------------
    comonomer_c = f.comonomer_t * KG_PER_TONNE * C_FRACTION_ETHYLENE
    hdpe_in_c = et_c + comonomer_c
    resin_c = f.hdpe_t * KG_PER_TONNE * C_FRACTION_ETHYLENE
    hdpe_co2_c = f.hdpe_t * p.hdpe_scope1 / CO2_PER_C
    node3 = CarbonBalance(
        node="Node 3 - HDPE polymerisation",
        basis="per functional unit",
        carbon_in_kg=hdpe_in_c,
        carbon_out_kg=resin_c + hdpe_co2_c,
        makeup_stream="none",
        makeup_kg_c=0.0,
        makeup_input_kg=0.0,
        note=(
            "Resin carbon plus fugitive monomer / flare CO2 exceeds the carbon in "
            "1.015 t ethylene plus the 1.5 wt% co-monomer."
        ),
    )

    return [node1, node2, node3]


# --------------------------------------------------------------------- checks
def _reproduction_checks(model: PCFModel) -> List[Check]:
    """Compare model internals with the specification's published figures."""
    p = model.params
    pcf = model.node_pcf()
    f = model.flows
    scopes = model.scope_totals()

    meoh_t = pcf["methanol"]["total"] * 1000.0
    et_t = pcf["ethylene"]["total"] * 1000.0
    meoh_cum = f.methanol_t * meoh_t
    et_cum = f.ethylene_t * et_t

    return [
        Check(
            "P-01",
            "Integrated PCF of 1 t HDPE resin",
            model.total_t,
            6.068,
            "t CO2e/t HDPE",
            0.1,
            "Spec section 4, total integrated cradle-to-gate footprint.",
        ),
        Check(
            "P-02",
            "Node 1 PCF per t methanol",
            meoh_t,
            1384.8,
            "kg CO2e/t MeOH",
            0.1,
            "Spec step 2 (upstream NG + Scope 1 + Scope 2).",
        ),
        Check(
            "P-03",
            "Carbon embedded in methanol demand",
            meoh_cum,
            4146.1,
            "kg CO2e",
            0.1,
            "Spec step 2 cumulative burden.",
        ),
        Check(
            "P-04",
            "Cradle-to-gate ethylene monomer footprint",
            et_t,
            5544.8,
            "kg CO2e/t C2H4",
            0.1,
            "Spec step 3.",
        ),
        Check(
            "P-05",
            "Carbon embedded in ethylene demand",
            et_cum,
            5628.0,
            "kg CO2e",
            0.1,
            "Spec step 3 cumulative burden.",
        ),
        Check("P-06", "Scope 1 total", scopes["scope1"], 2940.9, "kg CO2e", 0.1,
              "Spec section 5 column total."),
        Check("P-07", "Scope 2 total", scopes["scope2"], 2513.9, "kg CO2e", 0.1,
              "Spec section 5 column total."),
        Check("P-08", "Scope 3 (upstream NG) total", scopes["scope3"], 613.3,
              "kg CO2e", 0.1, "Spec section 5 column total."),
        Check(
            "P-09",
            "Functional-unit natural gas demand",
            f.natural_gas_t,
            1.614,
            "t NG/t HDPE",
            0.1,
            "Spec step 1.",
        ),
        Check(
            "P-10",
            "Primary energy demand of the chain",
            f.energy_gj,
            89.2,
            "GJ/t HDPE",
            0.5,
            "29.8 GJ/t methanol applied to the methanol demand.",
        ),
    ]


def _reference_checks(model: PCFModel) -> List[Check]:
    """Cross-check the packaged engine against the executed reference script."""
    from .reference_script import reference_calculator, reference_node_scope2

    calc = reference_calculator()
    reference_total, _ = calc.calculate_footprint(target_hdpe_ton=model.params.functional_unit_t)
    explicit = PCFModel(SCENARIO_BY_KEY["explicit_utilities"].params(model.params))
    reference_nodes = reference_node_scope2()
    node_map = {"methanol": "methanol", "ethylene": "mto", "hdpe": "hdpe"}
    worst_node = max(
        abs(explicit.node_pcf()[key]["scope2"] * 1000 - reference_nodes[node])
        for key, node in node_map.items()
    )
    return [
        Check(
            "R-01",
            "Execution-script basis: total footprint",
            explicit.total_kg,
            reference_total,
            "kg CO2e",
            TOLERANCE_PCT,
            "Packaged model vs the executed pcf_engine_execution_script.md.",
        ),
        Check(
            "R-02",
            "Execution-script basis: largest node Scope 2 gap",
            worst_node,
            0.0,
            "kg CO2e",
            TOLERANCE_PCT,
            "Absolute gap between model node Scope 2 and the reference script.",
        ),
    ]


def _scenario_checks(model: PCFModel) -> List[Check]:
    checks: List[Check] = []
    for key, ref in (("baseline", 6.07), ("mid_transition", 4.61)):
        scenario = SCENARIO_BY_KEY[key]
        value = PCFModel(scenario.params(model.params)).total_t
        checks.append(
            Check(
                f"S-{key}",
                f"Scenario '{key}' footprint",
                value,
                ref,
                "t CO2e/t HDPE",
                0.5,
                "Spec section 6.2 quoted scenario value.",
            )
        )

    green = SCENARIO_BY_KEY["green_h2_syngas"]
    green_model = PCFModel(green.params(model.params))
    checks.append(
        Check(
            "S-green_h2_syngas",
            "Scenario 'green_h2_syngas' footprint",
            green_model.total_t,
            1.82,
            "t CO2e/t HDPE",
            0.5,
            "Spec section 6.2 quoted value is not reproducible from the stated "
            "inventory - see finding F-05.",
        )
    )
    return checks


def _mass_balance_checks(model: PCFModel, carbon: Iterable[CarbonBalance]) -> List[Check]:
    """The +/- 0.1 % closure requirement of spec section 6.1."""
    checks: List[Check] = []
    for b in carbon:
        checks.append(
            Check(
                f"M-{b.node.split()[1]}",
                f"Carbon closure, {b.node}",
                b.closure_pct,
                100.0,
                "%",
                TOLERANCE_PCT,
                b.note,
            )
        )
    # gross product mass balance: every node's output equals its stated yield
    f = model.flows
    p = model.params
    checks.append(
        Check(
            "M-gross",
            "Chain mass-multiplication closure (NG -> HDPE)",
            f.ethylene_t / f.hdpe_t * f.methanol_t / f.ethylene_t * f.natural_gas_t / f.methanol_t,
            p.ng_per_hdpe,
            "t NG/t HDPE",
            TOLERANCE_PCT,
            "Yield factors multiply back to the specified natural gas demand.",
        )
    )
    return checks


# ------------------------------------------------------------------- findings
def _findings(model: PCFModel, carbon: Sequence[CarbonBalance]) -> List[Finding]:
    p = model.params
    f = model.flows
    findings: List[Finding] = []

    node1, node2, node3 = carbon

    # F-01 / F-02: closure deficits that the 0.1 % requirement rejects.
    if abs(node2.closure_deviation_pct) > TOLERANCE_PCT:
        required_meoh = (node2.carbon_out_kg / C_FRACTION_METHANOL) / (f.ethylene_t * KG_PER_TONNE)
        max_scope1 = (
            (node2.carbon_in_kg - f.ethylene_t * KG_PER_TONNE * C_FRACTION_ETHYLENE)
            * CO2_PER_C
            / (f.ethylene_t * KG_PER_TONNE)
            * KG_PER_TONNE
        )
        findings.append(
            Finding(
                "F-01",
                "FAIL",
                "MTO node carbon balance does not close",
                (
                    f"Node 2 emits {node2.carbon_out_kg:,.1f} kg C as ethylene + regeneration "
                    f"CO2 against {node2.carbon_in_kg:,.1f} kg C supplied by "
                    f"{f.methanol_t:.3f} t methanol (closure {node2.raw_closure_pct:.2f} %, "
                    f"{node2.closure_deviation_pct:+.2f} %). Closure within the 0.1 % "
                    f"requirement needs either {required_meoh:.3f} t CH3OH per t C2H4 "
                    f"(vs {p.methanol_per_ethylene:.2f}) with zero co-product carbon, or a "
                    f"Scope 1 inventory at or below {max_scope1:,.0f} kg CO2e/t C2H4 "
                    f"(vs {p.mto_scope1:,.0f}). The specification's 2.95 t/t yield and "
                    f"975 kg/t regeneration figure cannot both hold."
                ),
                impact_kg_co2e=0.0,
            )
        )
    if abs(node3.closure_deviation_pct) > TOLERANCE_PCT:
        required_ethylene = (node3.carbon_out_kg / C_FRACTION_ETHYLENE) / (
            f.hdpe_t * KG_PER_TONNE
        ) - p.comonomer_wt_fraction
        findings.append(
            Finding(
                "F-02",
                "FAIL",
                "Polymerisation node carbon balance does not close",
                (
                    f"Node 3 closes at {node3.raw_closure_pct:.2f} % "
                    f"({node3.closure_deviation_pct:+.2f} %). The 1.015 t ethylene per t "
                    f"HDPE yield cannot supply both the resin carbon and "
                    f"{p.hdpe_scope1:,.0f} kg CO2e/t of fugitive monomer and flare "
                    f"emissions; a carbon-consistent monomer demand is "
                    f"{required_ethylene:.3f} t C2H4/t HDPE."
                ),
                impact_kg_co2e=0.0,
            )
        )

    # F-03: the node 1 make-up fuel stream is not priced upstream.
    if node1.makeup_input_kg > 0:
        fuel_ng_per_fu = node1.makeup_input_kg / KG_PER_TONNE
        fuel_ng_per_meoh = fuel_ng_per_fu / f.methanol_t
        unbilled = fuel_ng_per_fu * KG_PER_TONNE * p.ef_ng_upstream
        findings.append(
            Finding(
                "F-03",
                "WARN",
                "Reformer fuel gas carries unbilled upstream emissions",
                (
                    f"Reforming the specified natural gas requires a make-up fuel stream of "
                    f"{fuel_ng_per_meoh:.3f} t NG per t methanol ({fuel_ng_per_fu:.3f} t per t "
                    f"HDPE) to close the node 1 carbon balance. The specification applies the "
                    f"{p.ef_ng_upstream:.3f} kg CO2e/kg upstream factor only to the "
                    f"{f.natural_gas_t:.3f} t feedstock stream, so roughly {unbilled:,.0f} kg "
                    f"CO2e per t HDPE of Scope 3.1 burden is missing. Including it raises the "
                    f"baseline footprint from {model.total_t:.2f} to about "
                    f"{(model.total_kg + unbilled) / KG_PER_TONNE:.2f} t CO2e/t HDPE."
                ),
                impact_kg_co2e=unbilled,
            )
        )

    # F-04: 42/38/20 carbon split versus the 2.95 t/t methanol demand.
    et_carbon_share = (
        p.ethylene_per_hdpe * p.functional_unit_t * C_FRACTION_ETHYLENE
        / (p.methanol_per_hdpe * C_FRACTION_METHANOL)
        * 100.0
    )
    if et_carbon_share > 100.0 * p.carbon_split_ethylene:
        implied_ethylene = (
            p.carbon_split_ethylene * p.methanol_per_hdpe * C_FRACTION_METHANOL
            / C_FRACTION_ETHYLENE
        )
        findings.append(
            Finding(
                "F-04",
                "WARN",
                "Carbon-selectivity split is inconsistent with the methanol yield",
                (
                    f"The specification reports 42 % carbon selectivity to ethylene, but the "
                    f"stated 2.95 t methanol per t ethylene route already fixes ethylene at "
                    f"{et_carbon_share:.1f} % of the methanol carbon before any propylene or "
                    f"C4+ is formed. A 42 % selectivity would deliver only "
                    f"{implied_ethylene:.3f} t ethylene per t HDPE. Mass allocation in the "
                    f"model therefore uses the 2.95 t/t yield directly; the 42/38/20 split "
                    f"is retained only for the allocation sensitivity variant."
                ),
                impact_kg_co2e=0.0,
            )
        )

    # F-05: the quoted green scenario.
    green = SCENARIO_BY_KEY["green_h2_syngas"]
    green_model = PCFModel(green.params(model.params))
    renewable = PCFModel(SCENARIO_BY_KEY["renewable_grid"].params(model.params))
    if green.spec_reference_t is not None:
        grid_linked = model.scope_totals()["scope2"]
        abatement_shortfall = model.total_kg - green.spec_reference_t * KG_PER_TONNE
        if p.ef_grid > 0:
            equivalent_kwh = abatement_shortfall / p.ef_grid
            inventoried_kwh = grid_linked / p.ef_grid
            shortfall_text = (
                f"{abatement_shortfall:,.0f} kg CO2e, which corresponds to "
                f"{equivalent_kwh:,.0f} kWh/t HDPE of grid-linked load at the base factor "
                f"versus the {inventoried_kwh:,.0f} kWh/t actually inventoried, "
                f"i.e. {equivalent_kwh / inventoried_kwh - 1:.0%} more "
                f"electricity-linked burden than the process consumes"
                if inventoried_kwh
                else f"{abatement_shortfall:,.0f} kg CO2e against a zero grid factor, so no "
                f"grid-linked equivalence can be defined"
            )
        else:
            equivalent_kwh = 0.0
            shortfall_text = (
                f"{abatement_shortfall:,.0f} kg CO2e, but the grid factor is zero, so no "
                f"further grid abatement is available and the target is unreachable by "
                f"decarbonising electricity alone"
            )
        findings.append(
            Finding(
                "F-05",
                "WARN",
                "Quoted 1.82 t green scenario is not reproducible from the inventory",
                (
                    f"The full green-hydrogen route models at {green_model.total_t:.2f} t "
                    f"CO2e/t HDPE and grid decarbonisation alone at {renewable.total_t:.2f} t. "
                    f"Reaching the quoted {green.spec_reference_t:.2f} t requires shedding "
                    f"{shortfall_text}. The quoted value is treated as an indicative "
                    f"target, not a model result."
                ),
                impact_kg_co2e=abatement_shortfall,
            )
        )

    # F-07: the execution script's utility split changes the scenario response.
    comparison = basis_comparison(p).set_index("basis")
    utility = utility_frame(p)
    explicit_checks_calc = comparison.loc["explicit_utilities"]
    grid_calc = comparison.loc["grid_equivalent"]
    steam_pct = steam_share_pct(p)
    mid_spec = SCENARIO_BY_KEY["mid_transition"].spec_reference_t
    findings.append(
        Finding(
            "F-07",
            "WARN",
            "Execution-script utility split does not reproduce the quoted grid scenarios",
            (
                f"The engine execution script decomposes Scope 2 into electricity and "
                f"steam: {explicit_checks_calc['pcf_baseline']:.3f} t CO2e/t HDPE, "
                f"{(explicit_checks_calc['pcf_baseline'] / model.total_t - 1):+.2%} versus the "
                f"grid-equivalent basis, with {steam_pct:.1f} % of Scope 2 carried as "
                f"{utility.iloc[-1]['steam_kg']:,.0f} kg CO2e of steam. Because most of the "
                f"burden is thermal rather than grid-linked, the quoted mid-transition "
                f"scenario becomes {explicit_checks_calc['pcf_mid_transition']:.2f} t "
                f"(spec {mid_spec:.2f}, "
                f"{100.0 * (explicit_checks_calc['pcf_mid_transition'] - mid_spec) / mid_spec:+.0f} %) "
                f"and a zero-carbon grid stops at "
                f"{explicit_checks_calc['pcf_zero_carbon_grid']:.2f} t, not "
                f"{grid_calc['pcf_zero_carbon_grid']:.2f} t. The two decompositions sit on "
                f"different sides of the specification's own numbers: the grid-equivalent "
                f"basis reproduces section 6.2, the explicit basis reproduces the execution "
                f"script. Only one can be the declared basis, and the choice must be stated "
                f"with the result."
            ),
            impact_kg_co2e=explicit_checks_calc["pcf_baseline"] * KG_PER_TONNE - model.total_kg,
        )
    )

    # F-08: the reference decomposition does not reconcile to the Scope 2 inventory.
    worst = utility.iloc[:-1].reindex(
        utility.iloc[:-1]["delta_kg"].abs().sort_values(ascending=False).index
    ).iloc[0]
    findings.append(
        Finding(
            "F-08",
            "INFO",
            "Execution-script Scope 2 does not reconcile to the specified inventory",
            (
                f"At the base grid factor the explicit decomposition gives "
                f"{utility.iloc[-1]['explicit_scope2_kg']:,.1f} kg CO2e of Scope 2 against "
                f"{utility.iloc[-1]['grid_equivalent_kg']:,.1f} kg in the specification. The "
                f"largest node gap is {worst['node']}: "
                f"{worst['explicit_scope2_kg']:,.2f} kg versus {worst['grid_equivalent_kg']:,.2f} kg "
                f"({worst['delta_kg']:+.2f} kg, {worst['delta_pct']:+.2f} %). Either the script's "
                f"utility demands or its scope 2 totals need reconciling before the two "
                f"interpretations can be mixed."
            ),
            impact_kg_co2e=utility.iloc[-1]["delta_kg"],
        )
    )

    # F-09: steam factor is not exercised by the grid-equivalent Scope 2 inventory.
    scope2_kg = model.scope_totals()["scope2"]
    electricity_only = scope2_kg / p.ef_grid if p.ef_grid else 0.0
    load_text = (
        f"equals {electricity_only:,.0f} kWh/t HDPE at the {p.ef_grid:.3f} kg CO2e/kWh factor"
        if p.ef_grid
        else "is zero with a zero-carbon grid, so the factor cannot be inferred"
    )
    findings.append(
        Finding(                "F-09",
                "INFO",
                "Scope 2 inventory reconciles to grid electricity, not steam",
            (                    f"The default Scope 2 inventory ({scope2_kg:,.1f} kg CO2e) "
                    f"{load_text}, with "
                    f"no thermal remainder. The 68.5 kg CO2e/GJ steam factor in section 3 is "
                    f"therefore not exercised by the default basis (it is by the explicit_utilities "
                    f"basis, see F-07); treating reported Scope 2 as grid-electricity-equivalent is "
                    f"what reproduces the quoted mid-transition scenario."
            ),
        )
    )
    return findings


# ------------------------------------------------------------------ public API
def validate(model: PCFModel | None = None) -> ValidationReport:
    model = model or PCFModel()
    carbon = carbon_balances(model)
    checks = (
        _reproduction_checks(model)
        + _scenario_checks(model)
        + _reference_checks(model)
        + _mass_balance_checks(model, carbon)
    )
    return ValidationReport(
        checks=tuple(checks),
        carbon=tuple(carbon),
        findings=tuple(_findings(model, carbon)),
    )
