"""Documented conversion factors used by the LCA layer.

Every constant here is an explicit assumption with its derivation, so the
report can state it rather than bury it in code.
"""

from __future__ import annotations

#: Primary energy required per kWh of grid electricity delivered.
#:
#: 1 kWh = 3.6 MJ of delivered energy.  At a 40 % average fossil generating
#: efficiency (the midpoint of a modern CCGT fleet at ~55-58 % and a
#: coal/older-steam fleet at ~33-38 %, plus ~6-8 % transmission losses),
#: primary energy = 3.6 / 0.40 = 9.0 MJ/kWh.  This is a screening conversion,
#: not a database cumulative-energy-demand result; the CED method would
#: integrate the actual supply chain of each generator.
PRIMARY_ENERGY_MJ_PER_KWH = 9.0

#: Range implied by 50 % (best CCGT) and 30 % (older coal) conversion.
PRIMARY_ENERGY_MJ_PER_KWH_RANGE = (7.2, 12.0)

#: Lower heating value of methane, MJ/kg.  Used only to cross-check the
#: specification's declared 29.8 GJ/t methanol energy intensity; it is not
#: added to the indicator, to avoid double counting.
METHANE_LHV_MJ_PER_KG = 50.0

#: Indicative supply-chain factor for 1-butene/1-hexene, kg CO2e/kg.
#:
#: NOT a sourced dataset.  It is used only to size the co-monomer gap in the
#: completeness matrix (0.015 t per functional unit), never in the headline
#: result.  Replace with a licensed olefin dataset before reporting the
#: co-monomer contribution.
COMONOMER_INDICATIVE_KG_CO2E_PER_KG = 2.0

#: Indicative range for the same gap, kg CO2e/kg (analyst judgement).
COMONOMER_INDICATIVE_RANGE = (1.5, 2.5)
