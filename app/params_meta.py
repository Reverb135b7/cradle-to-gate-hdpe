"""Editable-parameter metadata for the dashboard.

The UI is generated from this description, so a new model parameter only has to
be added here (and to :class:`pcf.params.ModelParams`) to appear as a control.
"""

from __future__ import annotations

from typing import Any

from pcf.params import ModelParams

PARAM_GROUPS: list[dict[str, Any]] = [
    {
        "id": "chain",
        "label": "Chain stoichiometry",
        "fields": [
            {
                "key": "functional_unit_t",
                "label": "Batch size",
                "unit": "t HDPE",
                "min": 1,
                "max": 10000,
                "step": 1,
                "decimals": 0,
                "hint": "Functional unit size; the footprint per tonne is unchanged.",
            },
            {
                "key": "ethylene_per_hdpe",
                "label": "Ethylene per t HDPE",
                "unit": "t/t",
                "min": 0.95,
                "max": 1.10,
                "step": 0.001,
                "decimals": 3,
                "hint": "Monomer demand incl. recovery and purge losses.",
            },
            {
                "key": "methanol_per_ethylene",
                "label": "Methanol per t ethylene",
                "unit": "t/t",
                "min": 2.60,
                "max": 3.40,
                "step": 0.01,
                "decimals": 3,
                "hint": "MTO yield; nets propylene and C4+ co-products.",
            },
            {
                "key": "methanol_per_ng",
                "label": "Methanol per t natural gas",
                "unit": "t/t",
                "min": 1.40,
                "max": 2.20,
                "step": 0.005,
                "decimals": 3,
                "hint": "Reforming + synthesis yield on a methane basis.",
            },
            {
                "key": "comonomer_wt_fraction",
                "label": "Co-monomer fraction",
                "unit": "wt",
                "min": 0.0,
                "max": 0.05,
                "step": 0.001,
                "decimals": 3,
                "hint": "1-butene / 1-hexene added for density control.",
            },
        ],
    },
    {
        "id": "factors",
        "label": "Emission factors",
        "fields": [
            {
                "key": "ef_grid",
                "label": "Grid factor",
                "unit": "kg CO2e/kWh",
                "min": 0.0,
                "max": 1.2,
                "step": 0.005,
                "decimals": 3,
                "hint": "Scope 2 electricity factor.",
            },
            {
                "key": "ef_ng_upstream",
                "label": "Natural gas upstream",
                "unit": "kg CO2e/kg",
                "min": 0.0,
                "max": 1.0,
                "step": 0.005,
                "decimals": 3,
                "hint": "Scope 3.1 extraction, processing and transport.",
            },
            {
                "key": "ef_steam",
                "label": "Steam supply",
                "unit": "kg CO2e/GJ",
                "min": 0.0,
                "max": 150.0,
                "step": 0.5,
                "decimals": 1,
                "hint": "Exercised only where steam demand is non-zero.",
            },
        ],
    },
    {
        "id": "scope1",
        "label": "Direct emissions",
        "fields": [
            {
                "key": "methanol_scope1",
                "label": "Methanol plant",
                "unit": "kg CO2e/t MeOH",
                "min": 0,
                "max": 1200,
                "step": 5,
                "decimals": 0,
                "hint": "Reformer flue gas, purge and venting.",
            },
            {
                "key": "mto_scope1",
                "label": "MTO regeneration",
                "unit": "kg CO2e/t C2H4",
                "min": 0,
                "max": 2000,
                "step": 5,
                "decimals": 0,
                "hint": "SAPO-34 coke burn plus process vents.",
            },
            {
                "key": "hdpe_scope1",
                "label": "Polymerisation venting",
                "unit": "kg CO2e/t HDPE",
                "min": 0,
                "max": 400,
                "step": 1,
                "decimals": 0,
                "hint": "Fugitive monomer and flare operations.",
            },
        ],
    },
    {
        "id": "utilities",
        "label": "Scope 2 demand",
        "fields": [
            {
                "key": "methanol_kwh_per_t",
                "label": "Methanol electricity",
                "unit": "kWh/t MeOH",
                "min": 0,
                "max": 2000,
                "step": 10,
                "decimals": 0,
            },
            {
                "key": "methanol_steam_gj_per_t",
                "label": "Methanol steam",
                "unit": "GJ/t MeOH",
                "min": 0,
                "max": 10,
                "step": 0.1,
                "decimals": 2,
            },
            {
                "key": "mto_kwh_per_t",
                "label": "MTO electricity",
                "unit": "kWh/t C2H4",
                "min": 0,
                "max": 2000,
                "step": 10,
                "decimals": 0,
            },
            {
                "key": "mto_steam_gj_per_t",
                "label": "MTO steam",
                "unit": "GJ/t C2H4",
                "min": 0,
                "max": 10,
                "step": 0.1,
                "decimals": 2,
            },
            {
                "key": "hdpe_kwh_per_t",
                "label": "Polymerisation electricity",
                "unit": "kWh/t HDPE",
                "min": 0,
                "max": 1500,
                "step": 10,
                "decimals": 0,
            },
            {
                "key": "hdpe_steam_gj_per_t",
                "label": "Polymerisation steam",
                "unit": "GJ/t HDPE",
                "min": 0,
                "max": 6,
                "step": 0.1,
                "decimals": 2,
            },
        ],
    },
    {
        "id": "energy",
        "label": "Energy & allocation",
        "fields": [
            {
                "key": "methanol_energy_gj_per_t",
                "label": "Methanol energy intensity",
                "unit": "GJ LHV/t",
                "min": 20,
                "max": 45,
                "step": 0.1,
                "decimals": 1,
            },
            {
                "key": "mto_burden_share",
                "label": "MTO burden to ethylene",
                "unit": "share",
                "min": 0.2,
                "max": 1.0,
                "step": 0.01,
                "decimals": 2,
                "hint": "1.0 = as specified; lower values emulate allocation.",
            },
        ],
    },
]


def field_keys() -> list[str]:
    return [field["key"] for group in PARAM_GROUPS for field in group["fields"]]


def defaults() -> dict[str, float]:
    params = ModelParams()
    return {key: float(getattr(params, key)) for key in field_keys()}


def bounds() -> dict[str, dict[str, float]]:
    return {
        field["key"]: {"min": field["min"], "max": field["max"]}
        for group in PARAM_GROUPS
        for field in group["fields"]
    }
