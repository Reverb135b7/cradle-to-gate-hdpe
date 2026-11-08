"""Sensitivity and uncertainty analysis with explicit range provenance.

Ranges are classified as:

* **evidence**  - constrained by the model's own carbon balance or by the
  specification's stated stoichiometry;
* **scenario**  - a decision variable (grid mix), not an uncertainty;
* **method**    - an allocation or utility-basis choice;
* **judgement** - no measured range exists; the bracket is an analyst
  assumption and is labelled as such everywhere it appears.

The Monte Carlo is run twice: once over the evidence-constrained reconciliation
path only, and once with the judgement brackets added.  The second is a
screening distribution, not measured variability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from pcf.allocation import allocation_scenarios
from pcf.model import PCFModel
from pcf.params import SCENARIOS, ModelParams
from pcf.sensitivity import run_scenarios

#: Specification value and carbon-closure-consistent value for the three
#: coupled inventory parameters.  The reconciliation path interpolates
#: linearly between them; see pcf/validation.py findings F-01 and F-02.
RECONCILIATION: Dict[str, Tuple[float, float]] = {
    "mto_scope1": (975.0, 913.0),
    "methanol_per_ethylene": (2.95, 2.996),
    "ethylene_per_hdpe": (1.015, 1.025),
}


@dataclass(frozen=True)
class Range:
    parameter: str
    label: str
    low: float
    high: float
    basis: str
    rationale: str


def sensitivity_ranges(base: ModelParams | None = None) -> Tuple[Range, ...]:
    """The sensitivity register: every assumption tested, with its provenance."""
    base = base or ModelParams()
    return (
        Range(
            "mto_scope1", "MTO Scope 1 (catalyst regeneration)",
            RECONCILIATION["mto_scope1"][1], RECONCILIATION["mto_scope1"][0],
            "evidence",
            "Node 2 carbon closure requires <= 913 kg CO2e/t C2H4 against the "
            "specified 975 (finding F-01). Coupled to the methanol demand.",
        ),
        Range(
            "methanol_per_ethylene", "Methanol demand per t ethylene",
            RECONCILIATION["methanol_per_ethylene"][0],
            RECONCILIATION["methanol_per_ethylene"][1],
            "evidence",
            "Carbon closure of node 2 needs 2.996 t/t against the specified 2.95 (F-01).",
        ),
        Range(
            "ethylene_per_hdpe", "Ethylene demand per t HDPE",
            RECONCILIATION["ethylene_per_hdpe"][0],
            RECONCILIATION["ethylene_per_hdpe"][1],
            "evidence",
            "Carbon closure of node 3 needs 1.025 t/t against the specified 1.015 (F-02).",
        ),
        Range(
            "ef_grid", "Grid emission factor",
            0.0, base.ef_grid,
            "scenario",
            "Decision variable, not uncertainty: 0.000-0.475 kg CO2e/kWh spans the "
            "renewable and fossil-dominant cases in the specification.",
        ),
        Range(
            "mto_burden_share", "Ethylene share of node 2 burden",
            0.42, 1.0,
            "method",
            "ISO 14044 mass allocation at the 42/38/20 carbon split versus the "
            "yield-based base case; economic allocation lies inside this bracket.",
        ),
        Range(
            "ef_ng_upstream", "Natural gas upstream factor",
            0.30, 0.46,
            "judgement",
            "No range is stated in the specification. +/-20 % bracket around 0.38 "
            "kg CO2e/kg; an analyst assumption, not measured variability.",
        ),
        Range(
            "methanol_per_ng", "Methanol yield per t natural gas",
            1.80, 1.90,
            "judgement",
            "No tolerance is stated. +/-2.7 % bracket around 1.855 t/t; analyst assumption.",
        ),
        Range(
            "hdpe_scope1", "Polymerisation Scope 1",
            112.5, 137.5,
            "judgement",
            "No range is stated. +/-10 % screening bracket around 125 kg CO2e/t; "
            "analyst assumption.",
        ),
    )


# --------------------------------------------------------------- reconciliation
def reconciled_params(theta: float, base: ModelParams | None = None) -> ModelParams:
    """Interpolate the inventory between the specification and carbon closure.

    ``theta = 0`` is the specification as written; ``theta = 1`` is the
    carbon-consistent inventory.  The three parameters move together because
    the node balances couple them.
    """
    base = base or ModelParams()
    theta = float(np.clip(theta, 0.0, 1.0))
    updates = {}
    for field, (start, end) in RECONCILIATION.items():
        updates[field] = start + theta * (end - start)
    return base.with_overrides(**updates)


def reconciliation_curve(
    steps: int = 41, base: ModelParams | None = None
) -> pd.DataFrame:
    """Footprint along the evidence-constrained reconciliation path."""
    base = base or ModelParams()
    rows = []
    for theta in np.linspace(0.0, 1.0, steps):
        model = PCFModel(reconciled_params(float(theta), base))
        rows.append(
            {
                "theta": float(theta),
                "total_t": model.total_t,
                "scope1_kg": model.scope_totals()["scope1"],
                "scope2_kg": model.scope_totals()["scope2"],
                "scope3_kg": model.scope_totals()["scope3"],
            }
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- sensitivity
def sensitivity_frame(base: ModelParams | None = None) -> pd.DataFrame:
    """One-at-a-time swing for every assumption in the register."""
    base = base or ModelParams()
    central = PCFModel(base).total_t
    rows = []
    for r in sensitivity_ranges(base):
        low = PCFModel(base.with_overrides(**{r.parameter: r.low})).total_t
        high = PCFModel(base.with_overrides(**{r.parameter: r.high})).total_t
        rows.append(
            {
                "parameter": r.parameter,
                "label": r.label,
                "base_value": getattr(base, r.parameter),
                "low_value": r.low,
                "high_value": r.high,
                "basis": r.basis,
                "pcf_low_t": low,
                "pcf_high_t": high,
                "swing_t": abs(high - low),
                "swing_pct": 100.0 * abs(high - low) / central,
                "delta_low_pct": 100.0 * (low - central) / central,
                "delta_high_pct": 100.0 * (high - central) / central,
                "rationale": r.rationale,
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("swing_t", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------ monte carlo
def monte_carlo(
    n: int = 20000,
    seed: int = 42,
    screening: bool = False,
    base: ModelParams | None = None,
) -> pd.DataFrame:
    """Sample the parameter space and return the footprint distribution.

    With ``screening=False`` only the evidence-constrained reconciliation
    parameter theta is sampled.  With ``screening=True`` the judgement brackets
    for upstream gas, methanol yield and polymerisation Scope 1 are added, and
    the result is labelled a screening distribution.
    """
    base = base or ModelParams()
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0.0, 1.0, n)
    upstream = (
        rng.triangular(0.30, 0.38, 0.46, n) if screening else np.full(n, base.ef_ng_upstream)
    )
    meoh_ng = (
        rng.triangular(1.80, 1.855, 1.90, n) if screening else np.full(n, base.methanol_per_ng)
    )
    hdpe_s1 = (
        rng.triangular(112.5, 125.0, 137.5, n) if screening else np.full(n, base.hdpe_scope1)
    )

    totals = np.empty(n)
    for i in range(n):
        params = reconciled_params(float(theta[i]), base).with_overrides(
            ef_ng_upstream=float(upstream[i]),
            methanol_per_ng=float(meoh_ng[i]),
            hdpe_scope1=float(hdpe_s1[i]),
        )
        totals[i] = PCFModel(params).total_t

    return pd.DataFrame(
        {
            "theta": theta,
            "ef_ng_upstream": upstream,
            "methanol_per_ng": meoh_ng,
            "hdpe_scope1": hdpe_s1,
            "total_t": totals,
        }
    )


def summarise(samples: pd.DataFrame, label: str = "") -> Dict[str, float | str]:
    """Distribution summary used by the report and workbook."""
    values = samples["total_t"].to_numpy()
    return {
        "label": label,
        "n": int(values.size),
        "mean_t": float(values.mean()),
        "sd_t": float(values.std(ddof=1)),
        "p05_t": float(np.percentile(values, 5)),
        "p50_t": float(np.percentile(values, 50)),
        "p95_t": float(np.percentile(values, 95)),
        "min_t": float(values.min()),
        "max_t": float(values.max()),
    }


# -------------------------------------------------------------------- scenarios
def scenario_envelope(base: ModelParams | None = None) -> pd.DataFrame:
    """Decision and method scenarios, separated from inventory uncertainty."""
    base = base or ModelParams()
    scenarios = SCENARIOS + allocation_scenarios(base)
    frame = run_scenarios(base, scenarios)
    labels = {
        "baseline": "Grid & technology",
        "mid_transition": "Grid & technology",
        "renewable_grid": "Grid & technology",
        "green_h2_syngas": "Grid & technology",
        "explicit_utilities": "Utility basis",
        "mass_allocation": "Allocation",
        "economic_allocation": "Allocation",
    }
    frame["kind"] = frame["scenario"].map(labels).fillna("Other")
    return frame
