"""
Product Carbon Footprint (PCF) Calculation Engine: Natural Gas -> Methanol -> MTO -> HDPE
Standard: ISO 14067 & GHG Protocol Product Life Cycle Standard
"""

import numpy as np
import pandas as pd


class HDPE_PCF_Calculator:
    def __init__(
        self, grid_ci=0.475, ng_upstream_ci=0.380, steam_ci=68.5
    ):
        """
        Initialize Carbon Intensity (CI) factors.
        grid_ci: kg CO2e / kWh
        ng_upstream_ci: kg CO2e / kg Natural Gas
        steam_ci: kg CO2e / GJ steam
        """
        self.grid_ci = grid_ci
        self.ng_upstream_ci = ng_upstream_ci
        self.steam_ci = steam_ci

    def calculate_footprint(self, target_hdpe_ton=1.0):
        # -------------------------------------------------------------
        # STAGE 3: HDPE Polymerization Node
        # -------------------------------------------------------------
        ethylene_req_per_ton_hdpe = 1.015  # tons ethylene / ton HDPE
        hdpe_scope1 = 125.0 * target_hdpe_ton  # kg CO2e
        hdpe_electricity_kwh = 450.0 * target_hdpe_ton  # kWh
        hdpe_steam_gj = 1.5 * target_hdpe_ton  # GJ
        hdpe_scope2 = (
            hdpe_electricity_kwh * self.grid_ci
        ) + (hdpe_steam_gj * self.steam_ci)

        # -------------------------------------------------------------
        # STAGE 2: MTO & Ethylene Purification Node
        # -------------------------------------------------------------
        total_ethylene_needed = target_hdpe_ton * ethylene_req_per_ton_hdpe
        methanol_req_per_ton_ethylene = (
            2.95  # tons methanol / ton ethylene
        )
        total_methanol_needed = (
            total_ethylene_needed * methanol_req_per_ton_ethylene
        )

        mto_scope1 = (
            975.0 * total_ethylene_needed
        )  # kg CO2e (Coke regen & vent)
        mto_elec_kwh = 700.0 * total_ethylene_needed  # kWh
        mto_steam_gj = 2.3 * total_ethylene_needed  # GJ
        mto_scope2 = (mto_elec_kwh * self.grid_ci) + (
            mto_steam_gj * self.steam_ci
        )

        # -------------------------------------------------------------
        # STAGE 1: Methanol Synthesis Node
        # -------------------------------------------------------------
        ng_req_per_ton_methanol = (
            1.0 / 1.855
        )  # tons NG / ton methanol
        total_ng_needed = total_methanol_needed * ng_req_per_ton_methanol

        meth_scope1 = 610.0 * total_methanol_needed  # kg CO2e
        meth_elec_kwh = 320.0 * total_methanol_needed  # kWh
        meth_steam_gj = 6.1 * total_methanol_needed  # GJ
        meth_scope2 = (meth_elec_kwh * self.grid_ci) + (
            meth_steam_gj * self.steam_ci
        )

        # -------------------------------------------------------------
        # STAGE 0: Natural Gas Upstream Extraction (Scope 3)
        # -------------------------------------------------------------
        ng_upstream_scope3 = (
            total_ng_needed * 1000.0 * self.ng_upstream_ci
        )  # kg CO2e

        # -------------------------------------------------------------
        # AGGREGATION & SUMMARY MATRIX
        # -------------------------------------------------------------
        total_scope1 = hdpe_scope1 + mto_scope1 + meth_scope1
        total_scope2 = hdpe_scope2 + mto_scope2 + meth_scope2
        total_scope3 = ng_upstream_scope3
        total_pcf = total_scope1 + total_scope2 + total_scope3

        summary_df = pd.DataFrame(
            [
                {
                    "Node": "Natural Gas Extraction",
                    "Scope 1 (kg CO2e)": 0.0,
                    "Scope 2 (kg CO2e)": 0.0,
                    "Scope 3 (kg CO2e)": ng_upstream_scope3,
                    "Subtotal (kg CO2e)": ng_upstream_scope3,
                    "Percentage": (ng_upstream_scope3 / total_pcf) * 100,
                },
                {
                    "Node": "Methanol Synthesis",
                    "Scope 1 (kg CO2e)": meth_scope1,
                    "Scope 2 (kg CO2e)": meth_scope2,
                    "Scope 3 (kg CO2e)": 0.0,
                    "Subtotal (kg CO2e)": meth_scope1 + meth_scope2,
                    "Percentage": (
                        (meth_scope1 + meth_scope2) / total_pcf
                    )
                    * 100,
                },
                {
                    "Node": "MTO & Separation",
                    "Scope 1 (kg CO2e)": mto_scope1,
                    "Scope 2 (kg CO2e)": mto_scope2,
                    "Scope 3 (kg CO2e)": 0.0,
                    "Subtotal (kg CO2e)": mto_scope1 + mto_scope2,
                    "Percentage": (
                        (mto_scope1 + mto_scope2) / total_pcf
                    )
                    * 100,
                },
                {
                    "Node": "HDPE Polymerization",
                    "Scope 1 (kg CO2e)": hdpe_scope1,
                    "Scope 2 (kg CO2e)": hdpe_scope2,
                    "Scope 3 (kg CO2e)": 0.0,
                    "Subtotal (kg CO2e)": hdpe_scope1 + hdpe_scope2,
                    "Percentage": (
                        (hdpe_scope1 + hdpe_scope2) / total_pcf
                    )
                    * 100,
                },
            ]
        )

        return total_pcf, summary_df


if __name__ == "__main__":
    calc = HDPE_PCF_Calculator()
    pcf_val, df = calc.calculate_footprint(target_hdpe_ton=1.0)
    print(f"=====================================================")
    print(
        f"TOTAL CRADLE-TO-GATE HDPE PCF: {pcf_val:.2f} kg CO2e / t resin"
    )
    print(f"=====================================================")
    print(df.to_string(index=False))