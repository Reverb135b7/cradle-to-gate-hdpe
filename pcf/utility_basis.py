"""Scope 2 decomposition bases: grid-equivalent vs explicit utilities.

Two readings of the specification's Scope 2 inventory are supported:

``grid_equivalent``
    The default basis.  Scope 2 is treated as grid electricity only, at the
    intensities that reproduce the specified 570 / 485 / 315 kg CO2e per tonne
    of node product.  This is the reading under which the specification's own
    mid-transition scenario (4.61 t) reproduces.

``explicit_utilities``
    The decomposition declared in ``pcf_engine_execution_script.md``:
    electricity of 320 / 700 / 450 kWh per tonne plus steam of 6.1 / 2.3 / 1.5
    GJ per tonne, valued at 0.475 kg CO2e/kWh and 68.5 kg CO2e/GJ.  This
    exercises the steam factor and is cross-checked against the executed
    reference script.

The two bases are not interchangeable: under the explicit basis 60 % of Scope 2
is thermal, so grid decarbonisation alone no longer reaches the quoted
scenario values.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .model import PCFModel
from .params import KG_PER_TONNE, SCENARIO_BY_KEY, ModelParams

NODES: tuple[tuple[str, str], ...] = (
    ("methanol", "Methanol synthesis"),
    ("ethylene", "MTO & separation"),
    ("hdpe", "HDPE polymerisation"),
)


@dataclass(frozen=True)
class UtilityBasis:
    """One Scope 2 decomposition basis."""

    key: str
    label: str
    description: str
    params: ModelParams


def basis_params(key: str, base: ModelParams | None = None) -> ModelParams:
    """Resolve a named basis to a parameter set."""
    base = base or ModelParams()
    if key == "grid_equivalent":
        return base
    if key == "explicit_utilities":
        return SCENARIO_BY_KEY["explicit_utilities"].params(base)
    raise KeyError(f"unknown utility basis: {key!r}")


def bases(base: ModelParams | None = None) -> tuple[UtilityBasis, ...]:
    """Both supported bases, resolved against ``base``."""
    base = base or ModelParams()
    return (
        UtilityBasis(
            key="grid_equivalent",
            label="Grid-equivalent (default)",
            description=(
                "Scope 2 modelled as grid electricity only; reproduces the specified "
                "Scope 2 inventory and the quoted grid scenarios."
            ),
            params=base,
        ),
        UtilityBasis(
            key="explicit_utilities",
            label="Explicit electricity + steam (execution script)",
            description=(
                "Scope 2 split as 320/700/450 kWh/t and 6.1/2.3/1.5 GJ/t; exercises the "
                "68.5 kg CO2e/GJ steam factor."
            ),
            params=basis_params("explicit_utilities", base),
        ),
    )


def _scope2_components(model: PCFModel, node: str) -> tuple[float, float, float]:
    """(electricity kg, steam kg, total kg) of Scope 2 for one node."""
    p = model.params
    f = model.flows
    if node == "methanol":
        mass, kwh, gj = f.methanol_t, p.methanol_kwh_per_t, p.methanol_steam_gj_per_t
    elif node == "ethylene":
        mass, kwh, gj = f.ethylene_t, p.mto_kwh_per_t, p.mto_steam_gj_per_t
    else:
        mass, kwh, gj = f.hdpe_t, p.hdpe_kwh_per_t, p.hdpe_steam_gj_per_t
    electricity = mass * kwh * p.ef_grid
    steam = mass * gj * p.ef_steam
    return electricity, steam, electricity + steam


def utility_frame(base: ModelParams | None = None) -> pd.DataFrame:
    """Node-by-node comparison of the two decompositions, kg CO2e per FU."""
    base = base or ModelParams()
    grid_model = PCFModel(basis_params("grid_equivalent", base))
    explicit_model = PCFModel(basis_params("explicit_utilities", base))

    rows = []
    for node, label in NODES:
        spec_kg = _scope2_components(grid_model, node)[2]
        elec, steam, total = _scope2_components(explicit_model, node)
        rows.append(
            {
                "node": label,
                "electricity_kg": elec,
                "steam_kg": steam,
                "explicit_scope2_kg": total,
                "grid_equivalent_kg": spec_kg,
                "delta_kg": total - spec_kg,
                "delta_pct": 100.0 * (total - spec_kg) / spec_kg if spec_kg else 0.0,
            }
        )
    frame = pd.DataFrame(rows)
    total_row = {
        "node": "Total",
        "electricity_kg": frame["electricity_kg"].sum(),
        "steam_kg": frame["steam_kg"].sum(),
        "explicit_scope2_kg": frame["explicit_scope2_kg"].sum(),
        "grid_equivalent_kg": frame["grid_equivalent_kg"].sum(),
        "delta_kg": frame["delta_kg"].sum(),
        "delta_pct": 0.0,
    }
    total_row["delta_pct"] = (
        100.0
        * total_row["delta_kg"]
        / total_row["grid_equivalent_kg"]
        if total_row["grid_equivalent_kg"]
        else 0.0
    )
    return pd.concat([frame, pd.DataFrame([total_row])], ignore_index=True)


def steam_share_pct(base: ModelParams | None = None, key: str = "explicit_utilities") -> float:
    """Share of Scope 2 that is thermal under the given basis, percent."""
    model = PCFModel(basis_params(key, base))
    steam = sum(_scope2_components(model, node)[1] for node, _ in NODES)
    total = sum(_scope2_components(model, node)[2] for node, _ in NODES)
    return 100.0 * steam / total if total else 0.0


def basis_comparison(base: ModelParams | None = None) -> pd.DataFrame:
    """Footprint under each basis at baseline, mid-transition and zero-carbon grid."""
    base = base or ModelParams()
    rows = []
    for basis in bases(base):
        row = {
            "basis": basis.key,
            "label": basis.label,
            "steam_share_pct": steam_share_pct(base, basis.key),
        }
        for label, ef in (("baseline", 0.475), ("mid_transition", 0.200), ("zero_carbon_grid", 0.0)):
            model = PCFModel(basis.params.with_overrides(ef_grid=ef))
            row[f"pcf_{label}"] = model.total_t
        rows.append(row)
    return pd.DataFrame(rows)
