"""Generated documents: goal-and-scope markdown, quality checks, deliverables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import declaration as d
from .results import LcaResult


def goal_scope_markdown(result: LcaResult) -> str:
    """Render the goal-and-scope document from the declaration."""
    model = result.model
    lines = [
        f"# {d.TITLE}",
        "",
        f"**Version** {d.VERSION}  ·  **Reference period** {d.BASE_YEAR}  ·  "
        f"**Functional unit** 1,000 kg HDPE resin at the gate",
        "",
        "## 1. Goal",
        "",
        f"**Decision the study informs.** {d.DECISION}",
        "",
        f"**Intended audience.** {d.AUDIENCE}",
        "",
        f"**Standards and status.** {d.STANDARDS}",
        "",
        "## 2. Product system and functional unit",
        "",
        f"**Product.** {d.PRODUCT}",
        "",
        f"**Functional unit.** {d.FUNCTIONAL_UNIT}",
        "",
        f"**Declared unit.** {d.DECLARED_UNIT}",
        "",
        f"**Reference flow.** {model.flows.hdpe_t * 1000:,.0f} kg HDPE resin per functional unit.",
        "",
        f"**Geography and technology.** {d.GEOGRAPHY}",
        "",
        f"**Reference period.** {d.REFERENCE_PERIOD}",
        "",
        "## 3. System boundary",
        "",
        "**Boundary: cradle-to-gate.** Raw-material extraction through polymerisation "
        "and pelletising; the gate is the exit of the pelletising unit. No use-phase "
        "or end-of-life stage is modelled, so this study does not claim "
        "cradle-to-grave coverage.",
        "",
        "### Included",
        "",
        "| Module | Treatment |",
        "| --- | --- |",
    ]
    for item, treatment in d.INCLUSIONS:
        lines.append(f"| {item} | {treatment} |")
    lines += [
        "",
        "### Excluded or not inventoried",
        "",
        "| Item | Why | Materiality |",
        "| --- | --- | --- |",
    ]
    for item, why, materiality in d.EXCLUSIONS:
        lines.append(f"| {item} | {why} | {materiality} |")
    lines += [
        "",
        f"**Cut-off.** {d.CUT_OFF}",
        "",
        "## 4. Allocation",
        "",
        d.ALLOCATION,
        "",
        "## 5. Impact assessment method",
        "",
        d.METHOD,
        "",
        "| Category | Indicator | Unit | Treatment |",
        "| --- | --- | --- | --- |",
    ]
    for category, indicator, unit, note in d.IMPACT_CATEGORIES:
        lines.append(f"| {category} | {indicator} | {unit} | {note} |")
    lines += [
        "",
        "## 6. Data quality requirements",
        "",
    ]
    for requirement in d.DATA_QUALITY_REQUIREMENTS:
        lines.append(f"- {requirement}")
    lines += [
        "",
        "## 7. Software and data",
        "",
        d.SOFTWARE,
        "",
        f"**Model result for this declaration.** {model.total_t:.3f} t CO2e per "
        f"functional unit ({model.total_per_kg_resin:.3f} kg CO2e/kg resin), "
        f"with a fossil primary-energy indicator of {result.impact.energy_mj / 1000:,.1f} GJ.",
        "",
        "## 8. Limitations",
        "",
    ]
    for limitation in d.LIMITATIONS:
        lines.append(f"- {limitation}")
    lines += [
        "",
        "---",
        "",
        "This document is generated from `lca/declaration.py`; edit that module and "
        "rebuild with `python -m lca` to keep the study description and the "
        "quantitative deliverables in step.",
    ]
    return "\n".join(lines) + "\n"


def quality_checks(result: LcaResult) -> pd.DataFrame:
    """Acceptance checks from the brief, with the evidence for each status."""
    rows = [
        (
            "Q-01",
            "Functional unit is explicit and consistently applied",
            "Met",
            f"Declaration fixes 1,000 kg resin with density and co-monomer specification; "
            f"all {len(result.flows)} inventory rows are generated per functional unit and "
            "the test suite asserts linear scaling.",
            "",
        ),
        (
            "Q-02",
            "System boundary matches the claims in the report",
            "Met",
            "Every deliverable states cradle-to-gate; gate-to-grave modules are named as "
            "excluded and are not included in any total.",
            "",
        ),
        (
            "Q-03",
            "Inventory quantities have units and sources",
            "Met",
            "LCI sheet carries quantity, unit, source_id (S1-S9), data type, geography, "
            "period and pedigree score for every flow.",
            "",
        ),
        (
            "Q-04",
            "Database version and impact assessment method are recorded",
            "Partial",
            "IA method is recorded (IPCC AR6 GWP100). No background database is licensed "
            "or linked: the factors come from the specification, which states no dataset "
            "identifier or version.",
            "A background database (e.g. ecoinvent 3.x, cut-off) must be linked in openLCA "
            "and its version recorded before the study is externally defensible.",
        ),
        (
            "Q-05",
            "Proxies and allocation choices are explained",
            "Met",
            "Allocation is stated and three bases are quantified. The only proxy (co-monomer "
            "supply) is flagged and excluded from the headline result.",
            "",
        ),
        (
            "Q-06",
            "Sensitivity analysis targets material assumptions",
            "Met",
            "Sensitivity register covers closure-consistent Scope 1 and yields, grid factor, "
            "allocation share, upstream factor, gas yield and polymerisation Scope 1; each "
            "range is labelled evidence, scenario, method or judgement.",
            "",
        ),
        (
            "Q-07",
            "Limitations are prominent and conclusions do not exceed the evidence",
            "Met",
            "Limitations section and category-completeness matrix are in the report; no "
            "result is reported for a category without substance-level data.",
            "",
        ),
        (
            "Q-08",
            "Multiple impact categories are assessed, not a single score",
            "Partial",
            "Climate change is quantified and energy demand is reported as a screening "
            "indicator. Eight further categories are declared but not quantified.",
            "Species-resolved emissions (SO2, NOx, NH3, NMVOC, PM, P, N, water) and a "
            "background database are required for acidification, eutrophication, POCP, "
            "particulate matter, water and land.",
        ),
        (
            "Q-09",
            "Native openLCA model is delivered",
            "Met",
            "Six unit processes are built in openLCA 2.6.2 over its IPC server from the same "
            "foreground exchanges and run on IPCC 2007 climate change - GWP 100a; the result "
            "reproduces the Python total to the reported digits.",
            "Link a licensed background database (e.g. ecoinvent 3.x, cut-off) and re-run "
            "before quoting absolute totals.",
        ),
        (
            "Q-10",
            "Critical review",
            "Not met",
            "No ISO 14044 clause 6 / ISO 14071 critical review has been performed.",
            "Commission an independent review before external publication.",
        ),
    ]
    return pd.DataFrame(
        rows, columns=["id", "check", "status", "evidence", "what_is_needed"]
    )


def deliverables(result: LcaResult) -> pd.DataFrame:
    """The 4.4 deliverable list and where each one is."""
    figures = result.figures
    rows = [
        ("Goal-and-scope document", "LCA_goal_and_scope.md", "Delivered", "Sections 1-8, generated from the declaration."),
        ("Functional-unit and boundary diagram", str(figures.get("boundary", "")), "Delivered", "Included in report and deck."),
        ("Life-cycle inventory workbook", "LCA_inventory.xlsx", "Delivered", "LCI, stage, pedigree, source, parameter, impact, sensitivity and scenario sheets."),
        ("Data-quality and source register", "LCA_data_quality_register.csv", "Delivered", "Pedigree scores and S1-S9 provenance; also a workbook sheet."),
        ("Native openLCA model", "openlca/", "Delivered", "Six unit processes built over IPC in openLCA 2.6.2; IPCC 2007 GWP100 reproduces the Python total (openlca/openlca_run.json)."),
        ("Impact assessment exports", "LCA_impact_assessment.csv / .json", "Delivered", "GWP100 and energy indicator; other categories declared with reasons."),
        ("Hotspot and contribution charts", "figures/contribution_gwp.png", "Delivered", "Climate and energy contribution by stage."),
        ("Sensitivity and uncertainty analysis", "figures/sensitivity.png, figures/uncertainty.png", "Delivered", "Provenance-labelled tornado, reconciliation path, two Monte Carlo runs, scenario envelope."),
        ("Final LCA report", "LCA_report.pdf", "Delivered", "Full study report with quality-check table."),
        ("Presentation", "LCA_presentation.pptx", "Delivered", "Twelve-slide summary for a technical audience."),
    ]
    return pd.DataFrame(rows, columns=["deliverable", "path", "status", "note"])


def write_goal_scope(result: LcaResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(goal_scope_markdown(result), encoding="utf-8")
    return path
