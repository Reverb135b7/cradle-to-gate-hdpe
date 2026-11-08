"""Impact assessment: climate change plus a documented energy indicator.

Only climate change can be quantified from this inventory.  The energy
indicator is reported as a resource indicator with its conversion assumption
stated, and every other category is declared unquantified rather than filled
with an unsupported proxy.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from pcf.model import PCFModel
from pcf.params import ModelParams

from .constants import PRIMARY_ENERGY_MJ_PER_KWH
from .declaration import IMPACT_CATEGORIES
from .inventory import stage_frame


@dataclass(frozen=True)
class ImpactResult:
    """One impact-assessment result set for one parameter set."""

    gwp_kg: float
    gwp_per_kg: float
    energy_mj: float
    energy_per_kg: float
    primary_energy_factor: float
    gwp_by_stage: dict[str, float]
    energy_by_stage: dict[str, float]

    @property
    def gwp_t(self) -> float:
        return self.gwp_kg / 1000.0


def compute(params: ModelParams | None = None) -> ImpactResult:
    p = params or ModelParams()
    model = PCFModel(p)
    stages = stage_frame(p)
    stage_rows = stages[stages["stage_key"] != "total"]
    return ImpactResult(
        gwp_kg=model.total_kg,
        gwp_per_kg=model.total_per_kg_resin,
        energy_mj=float(stage_rows["energy_mj"].sum()),
        energy_per_kg=float(stage_rows["energy_mj"].sum()) / 1000.0,
        primary_energy_factor=PRIMARY_ENERGY_MJ_PER_KWH,
        gwp_by_stage={
            row.stage_key: float(row.total_kg_co2e) for row in stage_rows.itertuples()
        },
        energy_by_stage={row.stage_key: float(row.energy_mj) for row in stage_rows.itertuples()},
    )


def impact_frame(result: ImpactResult) -> pd.DataFrame:
    """The two quantified indicators, with their basis and status."""
    return pd.DataFrame(
        [
            {
                "category": "Climate change",
                "indicator": "GWP100",
                "unit": "kg CO2e",
                "value": result.gwp_kg,
                "value_per_kg": result.gwp_per_kg,
                "method": "IPCC AR6 WG1, 100-year GWP; CO2e as supplied by the inventory",
                "status": "Quantified",
            },
            {
                "category": "Fossil resource use",
                "indicator": "Primary energy demand, LHV",
                "unit": "MJ",
                "value": result.energy_mj,
                "value_per_kg": result.energy_per_kg,
                "method": (
                    "Declared 29.8 GJ/t methanol fuel energy + electricity at "
                    f"{result.primary_energy_factor:.1f} MJ primary per kWh delivered"
                ),
                "status": "Screening indicator",
            },
        ]
    )


def category_frame() -> pd.DataFrame:
    """Every declared category and whether this study can quantify it."""
    rows = []
    for category, indicator, unit, note in IMPACT_CATEGORIES:
        if category == "Climate change":
            status = "Quantified"
        elif category.startswith("Fossil resource"):
            status = "Screening indicator"
        else:
            status = "Not quantified"
        rows.append(
            {
                "category": category,
                "indicator": indicator,
                "unit": unit,
                "status": status,
                "note": note,
            }
        )
    return pd.DataFrame(rows)


def contribution_frame(result: ImpactResult) -> pd.DataFrame:
    """Per-stage contribution to each quantified indicator."""
    labels = {
        "ng_extraction": "Natural gas extraction & transport",
        "methanol": "Methanol synthesis",
        "mto": "MTO & separation",
        "hdpe": "HDPE polymerisation",
    }
    gwp_total = sum(result.gwp_by_stage.values()) or 1.0
    energy_total = sum(result.energy_by_stage.values()) or 1.0
    rows = []
    for key, label in labels.items():
        gwp = result.gwp_by_stage.get(key, 0.0)
        energy = result.energy_by_stage.get(key, 0.0)
        rows.append(
            {
                "stage_key": key,
                "stage": label,
                "gwp_kg_co2e": gwp,
                "gwp_share_pct": 100.0 * gwp / gwp_total,
                "energy_mj": energy,
                "energy_share_pct": 100.0 * energy / energy_total,
            }
        )
    frame = pd.DataFrame(rows)
    frame.loc[len(frame)] = {
        "stage_key": "total",
        "stage": "Total",
        "gwp_kg_co2e": frame["gwp_kg_co2e"].sum(),
        "gwp_share_pct": 100.0,
        "energy_mj": frame["energy_mj"].sum(),
        "energy_share_pct": 100.0,
    }
    return frame
