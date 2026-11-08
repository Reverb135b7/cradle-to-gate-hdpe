"""Allocation sensitivity for the multi-output MTO node (ISO 14044 4.3.4.2).

The specification applies mass allocation at the MTO node and asks for an
economic-allocation variant.  Because the stated 2.95 t CH3OH per t C2H4 yield
already nets out the propylene / C4+ co-products, allocating the *embedded
methanol* burden as well would credit the co-products twice.  The sensitivity
therefore allocates only the node's own Scope 1 and Scope 2 burden, using the
carbon-selectivity split from spec section 2 and a transparent reference price
set, and leaves the yield-based feedstock burden on ethylene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import pandas as pd

from .model import PCFModel
from .params import C_FRACTION_ETHYLENE, ModelParams, Scenario

#: Indicative 2024-2025 contract reference prices, USD per tonne.  Used only for
#: the economic-allocation sensitivity; they are not part of the inventory.
REFERENCE_PRICES_USD_PER_T: Dict[str, float] = {
    "ethylene": 1150.0,
    "propylene": 950.0,
    "heavies": 700.0,
}


@dataclass(frozen=True)
class AllocationBasis:
    """One allocation basis for the MTO node."""

    key: str
    label: str
    ethylene_share: float
    rationale: str


def allocation_bases(params: ModelParams) -> Tuple[AllocationBasis, ...]:
    """Mass and economic ethylene shares of the MTO node burden."""
    carbon = {
        "ethylene": params.carbon_split_ethylene,
        "propylene": params.carbon_split_propylene,
        "heavies": params.carbon_split_heavies,
    }
    # convert carbon shares to mass shares at the common olefin carbon fraction
    mass = {k: v / C_FRACTION_ETHYLENE for k, v in carbon.items()}
    revenue = {k: mass[k] * REFERENCE_PRICES_USD_PER_T[k] for k in mass}
    total_revenue = sum(revenue.values())
    econ_share = revenue["ethylene"] / total_revenue

    return (
        AllocationBasis(
            key="as_specified",
            label="As specified (yield-based, no allocation)",
            ethylene_share=1.0,
            rationale=(
                "The 2.95 t CH3OH/t C2H4 demand already accounts for co-products; "
                "the full node burden is carried by ethylene."
            ),
        ),
        AllocationBasis(
            key="mass_allocation",
            label="Mass allocation (42 / 38 / 20 carbon split)",
            ethylene_share=carbon["ethylene"],
            rationale="Ethylene receives 42 % of node 2 Scope 1 and Scope 2 emissions.",
        ),
        AllocationBasis(
            key="economic_allocation",
            label="Economic allocation (reference prices)",
            ethylene_share=econ_share,
            rationale=(
                f"Ethylene revenue share of {econ_share:.1%} using "
                f"{REFERENCE_PRICES_USD_PER_T['ethylene']:.0f}/"
                f"{REFERENCE_PRICES_USD_PER_T['propylene']:.0f}/"
                f"{REFERENCE_PRICES_USD_PER_T['heavies']:.0f} USD/t."
            ),
        ),
    )


def allocation_scenarios(params: ModelParams) -> Tuple[Scenario, ...]:
    """Scenarios for the allocation sensitivity, excluding the default basis."""
    scenarios = []
    for basis in allocation_bases(params)[1:]:
        scenarios.append(
            Scenario(
                key=basis.key,
                label=basis.label,
                description=basis.rationale,
                overrides={"mto_burden_share": basis.ethylene_share},
            )
        )
    return tuple(scenarios)


def allocation_frame(params: ModelParams) -> pd.DataFrame:
    """Footprint under each allocation basis, t CO2e/t HDPE."""
    baseline = PCFModel(params).total_t
    rows = []
    for basis in allocation_bases(params):
        model = PCFModel(params.with_overrides(mto_burden_share=basis.ethylene_share))
        rows.append(
            {
                "basis": basis.key,
                "label": basis.label,
                "ethylene share of node 2": basis.ethylene_share,
                "pcf_t": model.total_t,
                "delta_t": model.total_t - baseline,
                "delta_pct": 100.0 * (model.total_t - baseline) / baseline,
                "rationale": basis.rationale,
            }
        )
    return pd.DataFrame(rows)
