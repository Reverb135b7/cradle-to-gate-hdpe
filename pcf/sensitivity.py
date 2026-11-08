"""Scenario, grid-decarbonisation and one-at-a-time sensitivity analysis.

Spec section 6.2 requires a dynamic recalculation of the footprint under three
grid / technology scenarios.  The module generalises that requirement:
``run_scenarios`` evaluates any set of :class:`~pcf.params.Scenario` objects,
``grid_sweep`` produces the continuous decarbonisation curve and
``tornado`` ranks the inventory parameters by their influence on the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from .allocation import allocation_scenarios
from .model import PCFModel
from .params import SCENARIOS, ModelParams, Scenario


@dataclass(frozen=True)
class ScenarioResult:
    """Result of one scenario evaluation."""

    key: str
    label: str
    description: str
    pcf_t: float
    scope1_kg: float
    scope2_kg: float
    scope3_kg: float
    spec_reference_t: float | None

    @property
    def delta_vs_reference(self) -> float | None:
        if self.spec_reference_t is None:
            return None
        return self.pcf_t - self.spec_reference_t

    @property
    def deviation_vs_reference_pct(self) -> float | None:
        if not self.spec_reference_t:
            return None
        return 100.0 * (self.pcf_t - self.spec_reference_t) / self.spec_reference_t


def evaluate(scenario: Scenario, base: ModelParams | None = None) -> ScenarioResult:
    model = PCFModel(scenario.params(base))
    scopes = model.scope_totals()
    return ScenarioResult(
        key=scenario.key,
        label=scenario.label,
        description=scenario.description,
        pcf_t=model.total_t,
        scope1_kg=scopes["scope1"],
        scope2_kg=scopes["scope2"],
        scope3_kg=scopes["scope3"],
        spec_reference_t=scenario.spec_reference_t,
    )


def run_scenarios(
    base: ModelParams | None = None,
    scenarios: Iterable[Scenario] | None = None,
) -> pd.DataFrame:
    """Evaluate the scenario set and return a comparison table."""
    base = base or ModelParams()
    scenarios = tuple(scenarios) if scenarios is not None else SCENARIOS
    baseline_pcf = PCFModel(base).total_t
    rows = []
    for scenario in scenarios:
        result = evaluate(scenario, base)
        rows.append(
            {
                "scenario": result.key,
                "label": result.label,
                "description": result.description,
                "pcf_t": result.pcf_t,
                "delta_vs_baseline_t": result.pcf_t - baseline_pcf,
                "reduction_vs_baseline_pct": 100.0
                * (baseline_pcf - result.pcf_t)
                / baseline_pcf,
                "scope1_kg": result.scope1_kg,
                "scope2_kg": result.scope2_kg,
                "scope3_kg": result.scope3_kg,
                "spec_reference_t": result.spec_reference_t,
                "deviation_vs_reference_pct": result.deviation_vs_reference_pct,
            }
        )
    return pd.DataFrame(rows)


def run_all_scenarios(base: ModelParams | None = None) -> pd.DataFrame:
    """Grid / technology scenarios plus the allocation sensitivity variants."""
    base = base or ModelParams()
    return run_scenarios(base, SCENARIOS + allocation_scenarios(base))


def grid_sweep(
    base: ModelParams | None = None,
    start: float = 0.0,
    stop: float = 0.6,
    step: float = 0.025,
) -> pd.DataFrame:
    """Footprint as a function of the grid emission factor, kg CO2e/kWh."""
    base = base or ModelParams()
    factors = np.round(np.arange(start, stop + step / 2.0, step), 4)
    rows = []
    for ef in factors:
        model = PCFModel(base.with_overrides(ef_grid=float(ef)))
        scopes = model.scope_totals()
        rows.append(
            {
                "ef_grid": float(ef),
                "pcf_t": model.total_t,
                "scope1_kg": scopes["scope1"],
                "scope2_kg": scopes["scope2"],
                "scope3_kg": scopes["scope3"],
            }
        )
    frame = pd.DataFrame(rows)
    # local gradient: t CO2e per t HDPE saved per 0.1 kg CO2e/kWh abated
    frame["slope_t_per_ef"] = np.gradient(frame["pcf_t"], frame["ef_grid"])
    return frame


#: parameters perturbed in the tornado analysis
TORNADO_PARAMETERS: tuple[tuple[str, str], ...] = (
    ("ef_grid", "Grid emission factor"),
    ("ef_ng_upstream", "Natural gas upstream factor (Scope 3.1)"),
    ("methanol_scope1", "Methanol plant Scope 1"),
    ("mto_scope1", "MTO Scope 1 (catalyst regeneration)"),
    ("methanol_per_ethylene", "Methanol demand per t ethylene"),
    ("methanol_per_ng", "Methanol yield per t natural gas"),
    ("ethylene_per_hdpe", "Ethylene demand per t HDPE"),
    ("hdpe_scope1", "Polymerisation Scope 1"),
)


def tornado(
    base: ModelParams | None = None,
    delta: float = 0.10,
    parameters: Sequence[tuple[str, str]] = TORNADO_PARAMETERS,
) -> pd.DataFrame:
    """One-at-a-time +/- ``delta`` perturbation ranking, t CO2e/t HDPE."""
    base = base or ModelParams()
    central = PCFModel(base).total_t
    rows = []
    for field, label in parameters:
        current = getattr(base, field)
        low_model = PCFModel(base.with_overrides(**{field: current * (1 - delta)}))
        high_model = PCFModel(base.with_overrides(**{field: current * (1 + delta)}))
        low, high = low_model.total_t, high_model.total_t
        rows.append(
            {
                "parameter": field,
                "label": label,
                "base_value": current,
                "pcf_low_t": low,
                "pcf_high_t": high,
                "swing_t": abs(high - low),
                "swing_pct": 100.0 * abs(high - low) / central,
                "sensitivity": (high - low) / (2 * delta * current) if current else 0.0,
            }
        )
    frame = pd.DataFrame(rows).sort_values("swing_t", ascending=False)
    return frame.reset_index(drop=True)
