"""Goal-and-scope declaration for the HDPE cradle-to-gate LCA.

This module is the single source of truth for the qualitative framing of the
study.  The goal-and-scope document, the PDF report, the workbook and the
presentation all render the values defined here, so the functional unit,
boundary and method cannot drift between deliverables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

TITLE = "Cradle-to-gate life-cycle assessment of HDPE resin produced via methanol-to-olefins"
VERSION = "1.0"
BASE_YEAR = "2024-2025"

PRODUCT = (
    "Uncompounded, pelletised, polymer-grade high-density polyethylene (HDPE) "
    "resin, copolymer grade with 1.5 wt% 1-butene/1-hexene, density "
    "0.941-0.965 g/cm3, produced in an integrated natural gas -> methanol -> "
    "ethylene (MTO) -> HDPE complex."
)

FUNCTIONAL_UNIT = (
    "1,000 kg (1 tonne) of HDPE resin meeting the specification above, at the "
    "factory gate (exit of the pelletising unit), ex-works, ready for bulk "
    "transport."
)

DECLARED_UNIT = "1 kg of the same resin, used only where a per-kilogram figure is quoted."

DECISION = (
    "Which life-cycle stage and which physical lever dominates the cradle-to-gate "
    "environmental burden of MTO-route HDPE; how far that conclusion survives the "
    "inventory's own carbon-balance inconsistencies, grid decarbonisation, "
    "allocation choice and the utility basis; and therefore where abatement effort "
    "and data-collection effort should go first."
)

AUDIENCE = (
    "Process and energy engineers at the integrated site, the polymer business's "
    "sustainability and procurement functions, and an internal technical reviewer "
    "checking the study against ISO 14040/14044, ISO 14067 and the GHG Protocol "
    "Product Life Cycle Standard."
)

STANDARDS = (
    "ISO 14040:2006 and ISO 14044:2006 (LCA principles, framework and "
    "requirements); ISO 14067:2018 (product carbon footprint); GHG Protocol "
    "Product Life Cycle Accounting and Reporting Standard. The study is a "
    "screening, secondary-data LCA: it is built to those frameworks but is not "
    "a certified or critically reviewed study."
)

METHOD = (
    "Climate change is quantified as 100-year global warming potential (GWP100) "
    "on IPCC AR6 WG1 values, in kg CO2e. A fossil primary-energy-demand indicator "
    "(MJ, lower heating value) is reported alongside it as a resource indicator, "
    "not as a midpoint impact category. No normalisation, weighting or single "
    "aggregate score is applied."
)

SOFTWARE = (
    "Python 3.14 model (this repository) for the foreground inventory, impact "
    "calculation, sensitivity and uncertainty. openLCA 2.6.2 is used as an "
    "independent calculation engine: the same foreground exchanges are rebuilt as "
    "six unit processes over its IPC server and run on IPCC 2007 GWP100, "
    "reproducing the total to the reported digits. No licensed background "
    "database is linked, so openLCA verifies the foreground arithmetic rather "
    "than supplying upstream data."
)

ALLOCATION = (
    "The MTO node is multi-output (ethylene, propylene, C4+ heavies). The base "
    "case follows the specification: the 2.95 t CH3OH per t C2H4 demand already "
    "nets out co-products, so the yield-based burden is attributed entirely to "
    "ethylene and no further allocation is applied. ISO 14044 4.3.4.2 mass "
    "allocation (42/38/20 carbon split) and economic allocation at reference "
    "prices are run as sensitivity variants on the node's own Scope 1 and Scope 2 "
    "burden. No allocation is applied to electricity, steam or upstream gas, "
    "which are single-purpose flows."
)

GEOGRAPHY = (
    "Global average industrial energy supply: grid factor 0.475 kg CO2e/kWh and "
    "natural gas upstream factor 0.380 kg CO2e/kg. The technology is a modern "
    "integrated SMR/ATR + methanol + SAPO-34 MTO + slurry/gas-phase polymerisation "
    "complex, not a specific named plant."
)

REFERENCE_PERIOD = (
    "2024-2025 engineering basis as stated in the technical specification; no "
    "site measurement campaign. The grid factor is a single annual average and "
    "is not time-resolved."
)

CUT_OFF = (
    "No formal cut-off criterion was applied. Every flow present in the source "
    "specification is modelled. Flows absent from the specification are not "
    "estimated into the headline result; they are listed in the completeness "
    "matrix with an assessed materiality and the data needed to close them."
)

INCLUSIONS: Tuple[Tuple[str, str], ...] = (
    ("Natural gas extraction, processing and transport", "Scope 3.1, 0.380 kg CO2e/kg NG, 1.614 t per functional unit"),
    ("Methanol synthesis (reforming, compression, distillation)", "Scope 1 610 kg CO2e/t MeOH; 1,200 kWh/t electricity"),
    ("Methanol-to-olefins and olefin separation", "Scope 1 975 kg CO2e/t C2H4; 1,021 kWh/t electricity"),
    ("HDPE polymerisation, devolatilisation, drying and pelletising", "Scope 1 125 kg CO2e/t HDPE; 663 kWh/t electricity"),
    ("Grid electricity supply to all three nodes", "Scope 2 at 0.475 kg CO2e/kWh; 5,293 kWh per functional unit"),
    ("Steam supply", "Declared as 0 GJ in the grid-equivalent base case; 22.1 GJ under the explicit-utilities basis"),
    ("Co-monomer mass input", "1.5 wt% 1-butene/1-hexene; mass included, supply-chain burden not modelled (see gaps)"),
)

EXCLUSIONS: Tuple[Tuple[str, str, str], ...] = (
    (
        "Packaging (bags, octabins, pallets, film)",
        "Not in the source inventory; gate is defined at pelletising exit.",
        "Not quantified. Would be reported as a separate packaging module with its own material and mass data.",
    ),
    (
        "Outbound transport and distribution",
        "Boundary stops at the gate; no destination or mode is defined.",
        "Not quantified. Would be reported as a separate gate-to-customer module.",
    ),
    (
        "Use phase",
        "HDPE applications are open-ended (pipe, film, containers); no use profile is defined.",
        "Outside the declared boundary; must not be inferred from this result.",
    ),
    (
        "End-of-life treatment and recycling",
        "No waste-scenario data; the project folder's 'cradle to grave' name is a project label, not a boundary claim.",
        "Outside the declared boundary. Mechanical recycling or energy recovery would be a separate module.",
    ),
    (
        "Water supply and wastewater treatment",
        "No water inventory in the source specification.",
        "Not quantified; no water-scarcity result can be reported.",
    ),
    (
        "Catalyst and adsorbent manufacture",
        "SAPO-34, Cu/ZnO/Al2O3 and Ziegler-Natta/metallocene catalysts are not in the inventory.",
        "Not quantified; typically small per tonne but not verified here.",
    ),
    (
        "Capital goods and infrastructure",
        "No asset inventory or lifetime throughput.",
        "Excluded by convention for a screening study.",
    ),
    (
        "Direct emissions other than CO2e aggregates",
        "The specification gives Scope 1 as CO2e totals, not species-resolved NOx/SO2/CH4/N2O/NMVOC/PM.",
        "Blocks acidification, eutrophication, photochemical ozone and particulate-matter categories.",
    ),
)

IMPACT_CATEGORIES: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "Climate change",
        "GWP100",
        "kg CO2e",
        "Quantified. IPCC AR6 WG1 100-year factors applied to the inventory's CO2e flows; CO2e aggregation inherited from the specification.",
    ),
    (
        "Fossil resource use (energy)",
        "Primary energy demand, LHV",
        "MJ",
        "Screening indicator, not a midpoint category. Natural gas energy as declared plus electricity converted at 9.0 MJ primary per kWh delivered.",
    ),
    (
        "Acidification",
        "Accumulated exceedance",
        "mol H+ eq",
        "Not quantified: inventory has no SO2, NOx or NH3 flows.",
    ),
    (
        "Eutrophication",
        "Freshwater / marine",
        "kg P eq / kg N eq",
        "Not quantified: inventory has no phosphorus or nitrogen species.",
    ),
    (
        "Photochemical ozone formation",
        "NMVOC-equivalent",
        "kg NMVOC eq",
        "Not quantified: inventory has no NMVOC or NOx speciation.",
    ),
    (
        "Particulate matter",
        "PM2.5 formation",
        "kg PM2.5 eq",
        "Not quantified: inventory has no PM or precursor speciation.",
    ),
    (
        "Water scarcity",
        "Consumptive water use",
        "m3 world eq",
        "Not quantified: no water withdrawal or consumption inventory.",
    ),
    (
        "Land use",
        "Soil organic carbon / biodiversity",
        "dimensionless",
        "Not quantified: no land occupation or transformation flows.",
    ),
)

DATA_QUALITY_REQUIREMENTS: Tuple[str, ...] = (
    "Every flow carries a quantity, a unit, a source identifier, a geography, a reference period and a pedigree score.",
    "Every non-measured flow is flagged as secondary or derived, and every proxy is flagged with its justification.",
    "The functional unit is applied by construction: flows are generated from the chain ratios, never scaled by hand.",
    "Carbon closure is tested per node at +/-0.1 % (ISO 14044 mass-balance expectation) and failures are reported, not smoothed.",
    "Sensitivity ranges are labelled by basis: 'evidence' where the model's own balance constrains them, 'scenario' where they are decision variables, and 'judgement' where no measured range exists.",
    "Conclusions are stated only for categories that are quantified; gaps are reported as gaps.",
)

LIMITATIONS: Tuple[str, ...] = (
    "Secondary data only. No site measurements, no metered utility data, no supplier-specific factors.",
    "The source specification's MTO and polymerisation carbon balances do not close within their own +/-0.1 % requirement; the headline result is reported on the specification's inventory as given, and the closure-consistent variant is quantified separately.",
    "Scope 1 is an aggregated CO2e figure per node. Without species-level emissions the study cannot support acidification, eutrophication, photochemical ozone or particulate-matter results, and does not attempt them.",
    "Electricity is a single annual-average grid factor; no marginal, hourly or supplier-specific factor is used, and grid decarbonisation is explored as a scenario rather than a forecast.",
    "The primary-energy conversion for electricity (9.0 MJ/kWh) is a documented screening assumption, not a database CED result.",
    "The co-monomer supply chain, catalysts, water, wastewater, packaging, outbound transport, use phase and end-of-life are outside the quantified inventory.",
    "Economic allocation depends on an indicative 2024-2025 price set, which is not part of the inventory and is varied only as a sensitivity.",
    "No critical review under ISO 14044 6 or ISO 14071 has been performed.",
)
