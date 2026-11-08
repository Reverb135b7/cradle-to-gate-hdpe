"""Parameter set for the cradle-to-gate HDPE product carbon footprint (PCF) model.

Every default value in :class:`ModelParams` is traceable to
``integrated_product_carbon_footprint_pcf_technical_specification.md``:

* chain stoichiometry  -> spec section 2 (mass balance conversion factors)
* emission factors     -> spec section 3 (primary emission factors)
* scope 1 inventories  -> spec section 4, steps 2-4
* scope 2 inventories  -> spec section 4, steps 2-4

Scope 2 is modelled physically as an electricity demand (kWh per tonne of
node product) rather than as a frozen emission figure, so that grid
decarbonisation scenarios can be evaluated by changing ``ef_grid`` only.
The default kWh intensities are back-calculated from the spec's scope 2
inventory at the stated base grid factor (0.475 kg CO2e/kWh).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Mapping

KG_PER_TONNE = 1000.0

#: kg CO2 per kg carbon
CO2_PER_C = 44.0 / 12.0

#: carbon mass fraction of methane, CH4
C_FRACTION_METHANE = 12.0 / 16.0

#: carbon mass fraction of methanol, CH3OH
C_FRACTION_METHANOL = 12.0 / 32.0

#: carbon mass fraction of ethylene / polyethylene repeat unit, C2H4
C_FRACTION_ETHYLENE = 24.0 / 28.0


class EmissionFactorsError(ValueError):
    """Raised when a parameter override does not exist in the model."""


@dataclass(frozen=True)
class ModelParams:
    """Complete inventory parameter set for one model run."""

    # --- functional unit and chain stoichiometry (spec section 2) ---------
    functional_unit_t: float = 1.0
    ethylene_per_hdpe: float = 1.015
    methanol_per_ethylene: float = 2.95
    methanol_per_ng: float = 1.855
    comonomer_wt_fraction: float = 0.015

    # --- primary emission factors (spec section 3) ------------------------
    ef_ng_upstream: float = 0.380  # kg CO2e / kg NG      (Scope 3.1)
    ef_grid: float = 0.475  # kg CO2e / kWh        (Scope 2)
    ef_steam: float = 68.5  # kg CO2e / GJ steam   (utility reference)

    # --- scope 1 direct emissions, kg CO2e per tonne node product ---------
    methanol_scope1: float = 610.0
    mto_scope1: float = 975.0
    hdpe_scope1: float = 125.0

    # --- scope 2 demand: electricity (kWh) + steam (GJ) per t node product -
    # Defaults reproduce the specified Scope 2 inventory as grid-electricity
    # equivalent: 570 / 0.475 ; 485 / 0.475 ; 315 / 0.475, with no thermal
    # remainder.  The engine execution script instead declares an explicit
    # split of 320/700/450 kWh/t and 6.1/2.3/1.5 GJ/t; selecting those values
    # exercises ``ef_steam`` and is exposed as the ``explicit_utilities``
    # scenario below.
    methanol_kwh_per_t: float = 1200.0
    methanol_steam_gj_per_t: float = 0.0
    mto_kwh_per_t: float = 485.0 / 0.475
    mto_steam_gj_per_t: float = 0.0
    hdpe_kwh_per_t: float = 315.0 / 0.475
    hdpe_steam_gj_per_t: float = 0.0

    # --- energy and allocation descriptors --------------------------------
    methanol_energy_gj_per_t: float = 29.8
    carbon_split_ethylene: float = 0.42
    carbon_split_propylene: float = 0.38
    carbon_split_heavies: float = 0.20

    #: share of the MTO node's *own* Scope 1/2 burden attributed to ethylene.
    #: 1.0 = as-specified (the 2.95 t/t methanol yield already nets co-products).
    #: Lower values emulate ISO 14044 mass / economic allocation of node 2.
    mto_burden_share: float = 1.0

    # --- derived helpers --------------------------------------------------
    @property
    def ng_per_tonne_methanol(self) -> float:
        """t natural gas required per t methanol."""
        return 1.0 / self.methanol_per_ng

    @property
    def methanol_per_hdpe(self) -> float:
        """t methanol required per t HDPE resin."""
        return self.ethylene_per_hdpe * self.methanol_per_ethylene

    @property
    def ng_per_hdpe(self) -> float:
        """t natural gas feedstock required per t HDPE resin."""
        return self.methanol_per_hdpe * self.ng_per_tonne_methanol

    def with_overrides(self, **overrides: Any) -> "ModelParams":
        """Return a copy of this parameter set with the given fields replaced."""
        unknown = set(overrides) - {f.name for f in _FIELDS}
        if unknown:
            raise EmissionFactorsError(f"unknown model parameter(s): {sorted(unknown)}")
        return replace(self, **overrides)


_FIELDS = tuple(f for f in ModelParams.__dataclass_fields__.values())  # type: ignore[attr-defined]


@dataclass(frozen=True)
class Scenario:
    """A named parameter variant of the baseline model."""

    key: str
    label: str
    description: str
    overrides: Mapping[str, Any] = field(default_factory=dict)
    #: headline value quoted in the technical specification, t CO2e/t HDPE
    spec_reference_t: float | None = None

    def params(self, base: ModelParams | None = None) -> ModelParams:
        base = base or ModelParams()
        return base.with_overrides(**dict(self.overrides))


#: Scenario set required by spec section 6.2 plus the physically motivated
#: "full green-hydrogen syngas" variant used to bracket the spec's 1.82 value.
SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="baseline",
        label="Baseline (fossil-dominant grid)",
        description=(
            "SMR/ATR natural gas route, base grid factor 0.475 kg CO2e/kWh. "
            "Reproduces the specification's headline footprint."
        ),
        overrides={},
        spec_reference_t=6.07,
    ),
    Scenario(
        key="mid_transition",
        label="Mid-transition grid",
        description="Same process chain, grid factor reduced to 0.200 kg CO2e/kWh.",
        overrides={"ef_grid": 0.200},
        spec_reference_t=4.61,
    ),
    Scenario(
        key="renewable_grid",
        label="100% renewable grid",
        description=(
            "Grid factor 0.000 kg CO2e/kWh with fossil natural gas retained as "
            "the carbon feedstock (process Scope 1 unchanged)."
        ),
        overrides={"ef_grid": 0.000},
    ),
    Scenario(
        key="green_h2_syngas",
        label="Renewable grid + green hydrogen syngas",
        description=(
            "Renewable electricity, syngas from green H2 + captured CO2 "
            "(no natural gas extraction, no reformer Scope 1). MTO catalyst "
            "regeneration and polymerisation venting are retained."
        ),
        overrides={
            "ef_grid": 0.000,
            "ef_ng_upstream": 0.0,
            "methanol_scope1": 0.0,
        },
        spec_reference_t=1.82,
    ),
    Scenario(
        key="explicit_utilities",
        label="Explicit utility decomposition (engine execution script)",
        description=(
            "Scope 2 split into electricity and steam demand exactly as declared in "
            "the engine execution script (320/700/450 kWh/t and 6.1/2.3/1.5 GJ/t), "
            "which exercises the 68.5 kg CO2e/GJ steam factor."
        ),
        overrides={
            "methanol_kwh_per_t": 320.0,
            "methanol_steam_gj_per_t": 6.1,
            "mto_kwh_per_t": 700.0,
            "mto_steam_gj_per_t": 2.3,
            "hdpe_kwh_per_t": 450.0,
            "hdpe_steam_gj_per_t": 1.5,
        },
    ),
)

SCENARIO_BY_KEY: Dict[str, Scenario] = {s.key: s for s in SCENARIOS}
