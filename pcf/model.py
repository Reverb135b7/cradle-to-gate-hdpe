"""Mass/energy balance and layered PCF engine for the NG -> MeOH -> MTO -> HDPE chain.

The model walks the chain backwards from the functional unit (1 t of
pelletised HDPE resin at the factory gate), accumulates the emissions of each
unit operation and keeps the cumulative cradle-to-gate burden, so that both
the per-node PCF (t CO2e per t of node product) and the integrated footprint
of the functional unit can be reported from a single parameter set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import pandas as pd

from .params import KG_PER_TONNE, ModelParams

#: ordered life-cycle stages of the modelled system
STAGE_KEYS = ("ng_extraction", "methanol", "mto", "hdpe")

STAGE_LABELS = {
    "ng_extraction": "Natural gas extraction & transport",
    "methanol": "Methanol synthesis (SMR/ATR + synthesis)",
    "mto": "Methanol-to-olefins & separation",
    "hdpe": "HDPE polymerisation & finishing",
}


@dataclass(frozen=True)
class Flows:
    """Chain mass flows that satisfy one functional unit."""

    hdpe_t: float
    ethylene_t: float
    methanol_t: float
    natural_gas_t: float
    comonomer_t: float
    energy_gj: float

    def as_dict(self) -> dict:
        return {
            "HDPE resin (functional unit), t": self.hdpe_t,
            "Ethylene feedstock, t": self.ethylene_t,
            "Methanol feedstock, t": self.methanol_t,
            "Natural gas feedstock, t": self.natural_gas_t,
            "1-butene/1-hexene co-monomer, t": self.comonomer_t,
            "Primary energy demand, GJ": self.energy_gj,
        }


@dataclass(frozen=True)
class StageResult:
    """Emissions contributed by one life-cycle stage, kg CO2e per functional unit."""

    key: str
    label: str
    scope1: float
    scope2: float
    scope3: float
    cumulative: float

    @property
    def total(self) -> float:
        return self.scope1 + self.scope2 + self.scope3


class PCFModel:
    """Cradle-to-gate PCF model for HDPE produced via the MTO pathway."""

    def __init__(self, params: ModelParams | None = None) -> None:
        self.params = params or ModelParams()

    # ------------------------------------------------------------------ flows
    @property
    def flows(self) -> Flows:
        p = self.params
        hdpe = p.functional_unit_t
        ethylene = hdpe * p.ethylene_per_hdpe
        methanol = ethylene * p.methanol_per_ethylene
        ng = methanol / p.methanol_per_ng
        return Flows(
            hdpe_t=hdpe,
            ethylene_t=ethylene,
            methanol_t=methanol,
            natural_gas_t=ng,
            comonomer_t=hdpe * p.comonomer_wt_fraction,
            energy_gj=methanol * p.methanol_energy_gj_per_t,
        )

    # ----------------------------------------------------------- node results
    def _scope2_per_t(self, kwh_per_t: float, steam_gj_per_t: float) -> float:
        """Scope 2 intensity for one node, t CO2e per t of node product."""
        p = self.params
        return (kwh_per_t * p.ef_grid + steam_gj_per_t * p.ef_steam) / KG_PER_TONNE

    def node_pcf(self) -> dict[str, dict[str, float]]:
        """Per-node PCF expressed per tonne of that node's product (t CO2e/t)."""
        p = self.params
        # Node 1, per tonne of methanol produced
        meoh_upstream = p.ng_per_tonne_methanol * p.ef_ng_upstream
        meoh_s1 = p.methanol_scope1 / KG_PER_TONNE
        meoh_s2 = self._scope2_per_t(
            p.methanol_kwh_per_t, p.methanol_steam_gj_per_t
        )
        meoh_total = meoh_upstream + meoh_s1 + meoh_s2

        # Node 2, per tonne of ethylene: the methanol burden enters at the
        # 2.95 t CH3OH / t C2H4 demand ratio.
        et_s1 = p.mto_scope1 * p.mto_burden_share / KG_PER_TONNE
        et_s2 = (
            self._scope2_per_t(p.mto_kwh_per_t, p.mto_steam_gj_per_t)
            * p.mto_burden_share
        )
        et_embedded = p.methanol_per_ethylene * meoh_total

        # Node 3, per tonne of HDPE resin: ethylene enters at 1.015 t/t.
        hdpe_s1 = p.hdpe_scope1 / KG_PER_TONNE
        hdpe_s2 = self._scope2_per_t(p.hdpe_kwh_per_t, p.hdpe_steam_gj_per_t)

        ethylene_pcf = et_embedded + et_s1 + et_s2
        return {
            "methanol": {
                "scope3_upstream": meoh_upstream,
                "scope1": meoh_s1,
                "scope2": meoh_s2,
                "total": meoh_total,
            },
            "ethylene": {
                "embedded_methanol": et_embedded,
                "scope1": et_s1,
                "scope2": et_s2,
                "total": ethylene_pcf,
            },
            "hdpe": {
                "embedded_ethylene": p.ethylene_per_hdpe * ethylene_pcf,
                "scope1": hdpe_s1,
                "scope2": hdpe_s2,
                "total": p.ethylene_per_hdpe * ethylene_pcf + hdpe_s1 + hdpe_s2,
            },
        }

    def stages(self) -> Sequence[StageResult]:
        """Stage-level emission contributions, kg CO2e per functional unit."""
        p = self.params
        f = self.flows

        ng_s3 = f.natural_gas_t * KG_PER_TONNE * p.ef_ng_upstream
        meoh_s1 = f.methanol_t * p.methanol_scope1
        meoh_s2 = (
            f.methanol_t
            * (p.methanol_kwh_per_t * p.ef_grid + p.methanol_steam_gj_per_t * p.ef_steam)
        )
        mto_s1 = f.ethylene_t * p.mto_scope1 * p.mto_burden_share
        mto_s2 = (
            f.ethylene_t
            * (p.mto_kwh_per_t * p.ef_grid + p.mto_steam_gj_per_t * p.ef_steam)
            * p.mto_burden_share
        )
        hdpe_s1 = f.hdpe_t * p.hdpe_scope1
        hdpe_s2 = f.hdpe_t * (
            p.hdpe_kwh_per_t * p.ef_grid + p.hdpe_steam_gj_per_t * p.ef_steam
        )

        raw = (
            ("ng_extraction", 0.0, 0.0, ng_s3),
            ("methanol", meoh_s1, meoh_s2, 0.0),
            ("mto", mto_s1, mto_s2, 0.0),
            ("hdpe", hdpe_s1, hdpe_s2, 0.0),
        )

        out: List[StageResult] = []
        cumulative = 0.0
        for key, s1, s2, s3 in raw:
            cumulative += s1 + s2 + s3
            out.append(
                StageResult(
                    key=key,
                    label=STAGE_LABELS[key],
                    scope1=s1,
                    scope2=s2,
                    scope3=s3,
                    cumulative=cumulative,
                )
            )
        return out

    # -------------------------------------------------------------- aggregates
    @property
    def total_kg(self) -> float:
        """Integrated cradle-to-gate PCF, kg CO2e per functional unit."""
        return self.stages()[-1].cumulative

    @property
    def total_t(self) -> float:
        """Integrated cradle-to-gate PCF, t CO2e per t HDPE."""
        return self.total_kg / (self.params.functional_unit_t * KG_PER_TONNE)

    @property
    def total_per_kg_resin(self) -> float:
        """kg CO2e per kg HDPE resin (ISO 14067 declared unit form)."""
        return self.total_t

    def scope_totals(self) -> dict[str, float]:
        stages = self.stages()
        return {
            "scope1": sum(s.scope1 for s in stages),
            "scope2": sum(s.scope2 for s in stages),
            "scope3": sum(s.scope3 for s in stages),
            "total": sum(s.total for s in stages),
        }

    # --------------------------------------------------------------- reporting
    def hotspot_frame(self) -> pd.DataFrame:
        """Hotspot matrix equivalent to spec section 5."""
        stages = self.stages()
        total = sum(s.total for s in stages)
        return pd.DataFrame(
            [
                {
                    "stage": s.label,
                    "stage_key": s.key,
                    "scope1_kg": s.scope1,
                    "scope2_kg": s.scope2,
                    "scope3_kg": s.scope3,
                    "total_kg": s.total,
                    "share_pct": 100.0 * s.total / total if total else 0.0,
                }
                for s in stages
            ]
        )

    def layer_frame(self) -> pd.DataFrame:
        """Layer-by-layer breakdown equivalent to spec section 4 (per t product)."""
        pcf = self.node_pcf()
        return pd.DataFrame(
            [
                {
                    "layer": "Node 1 - Methanol synthesis",
                    "basis": "t MeOH",
                    "embedded_upstream_t": pcf["methanol"]["scope3_upstream"],
                    "scope1_t": pcf["methanol"]["scope1"],
                    "scope2_t": pcf["methanol"]["scope2"],
                    "total_t": pcf["methanol"]["total"],
                },
                {
                    "layer": "Node 2 - MTO ethylene",
                    "basis": "t C2H4",
                    "embedded_upstream_t": pcf["ethylene"]["embedded_methanol"],
                    "scope1_t": pcf["ethylene"]["scope1"],
                    "scope2_t": pcf["ethylene"]["scope2"],
                    "total_t": pcf["ethylene"]["total"],
                },
                {
                    "layer": "Node 3 - HDPE polymerisation",
                    "basis": "t HDPE",
                    "embedded_upstream_t": pcf["hdpe"]["embedded_ethylene"],
                    "scope1_t": pcf["hdpe"]["scope1"],
                    "scope2_t": pcf["hdpe"]["scope2"],
                    "total_t": pcf["hdpe"]["total"],
                },
            ]
        )

    def mass_flow_frame(self) -> pd.DataFrame:
        """Mass and energy balance table for the functional unit."""

        p = self.params
        f = self.flows
        rows = [
            (
                "Node 3 - Polymerisation",
                "Ethylene",
                f.ethylene_t,
                f.hdpe_t,
                "HDPE resin",
            ),
            (
                "Node 2 - MTO",
                "Methanol",
                f.methanol_t,
                f.ethylene_t,
                "Polymer-grade ethylene",
            ),
            (
                "Node 1 - Methanol synthesis",
                "Natural gas",
                f.natural_gas_t,
                f.methanol_t,
                "Methanol",
            ),
        ]
        frame = pd.DataFrame(
            rows,
            columns=["node", "input", "input_t", "output_t", "output"],
        )
        frame["yield_t_per_t"] = frame["output_t"] / frame["input_t"]
        frame["spec_yield"] = [
            1.0 / p.ethylene_per_hdpe,
            1.0 / p.methanol_per_ethylene,
            p.methanol_per_ng,
        ]
        return frame
