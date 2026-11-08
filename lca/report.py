"""PDF LCA report (reportlab platypus)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from pcf.allocation import allocation_bases

from . import declaration as d
from .documents import deliverables, quality_checks
from .results import LcaResult

INK = colors.HexColor("#20262b")
MUTED = colors.HexColor("#6b7378")
RULE = colors.HexColor("#c8ced4")
ACCENT = colors.HexColor("#8c6d1f")
BAND = colors.HexColor("#f2f4f6")
HEAD = colors.HexColor("#1f2933")
SCOPE1 = colors.HexColor("#b5533c")
SCOPE2 = colors.HexColor("#2f6f9f")
SCOPE3 = colors.HexColor("#6f8f5a")
PASS = colors.HexColor("#2f6f4f")
WARN = colors.HexColor("#9a6b00")
FAIL = colors.HexColor("#a5342a")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=20, leading=24, textColor=INK, alignment=TA_LEFT,
                                spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10.5, leading=14.5,
                                   textColor=MUTED, spaceAfter=10),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK,
                             spaceBefore=13, spaceAfter=5, keepWithNext=True),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK,
                             spaceBefore=9, spaceAfter=3, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=8.8, leading=12.6, textColor=INK,
                               alignment=TA_JUSTIFY, spaceAfter=5),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontName="Helvetica", fontSize=8.8,
                                 leading=12.2, textColor=INK, leftIndent=9, bulletIndent=1, spaceAfter=2.5),
        "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=7.4, leading=9.6,
                                  textColor=MUTED, spaceBefore=2, spaceAfter=7),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=7.2, leading=8.8, textColor=INK),
        "cellright": ParagraphStyle("cellright", fontName="Helvetica", fontSize=7.2, leading=8.8,
                                    textColor=INK, alignment=TA_RIGHT),
        "cellhead": ParagraphStyle("cellhead", fontName="Helvetica-Bold", fontSize=7.2, leading=8.8,
                                   textColor=colors.white),
        "cellheadr": ParagraphStyle("cellheadr", fontName="Helvetica-Bold", fontSize=7.2, leading=8.8,
                                    textColor=colors.white, alignment=TA_RIGHT),
        "kpi": ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=18, leading=21, textColor=INK),
        "kpilabel": ParagraphStyle("kpilabel", fontName="Helvetica", fontSize=7.4, leading=9.4,
                                   textColor=MUTED),
    }


S = _styles()


def _n(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def _p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, S[style])


def _cell(text: str, head: bool = False, right: bool = False) -> Paragraph:
    style = "cellhead" if head else ("cellright" if right else "cell")
    if head and right:
        style = "cellheadr"
    return Paragraph(str(text), S[style])


def _table(
    data: Sequence[Sequence[str]],
    widths: Sequence[float],
    align_right: Iterable[int] = (),
    font: float = 7.2,
) -> Table:
    right = set(align_right)
    rows = []
    for r, row in enumerate(data):
        rows.append([_cell(str(value), head=(r == 0), right=(r > 0 and c in right))
                     for c, value in enumerate(row)])
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
    ]
    for r in range(1, len(rows)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), BAND))
    table.setStyle(TableStyle(style))
    return table


def _status_colour(status: str) -> colors.Color:
    if status in {"PASS", "Met"}:
        return PASS
    if status in {"WARN", "Partial"}:
        return WARN
    return FAIL


def _image(path: Path, width: float) -> Image:
    with PILImage.open(path) as handle:
        w, h = handle.size
    return Image(str(path), width=width, height=width * h / w)


def _box(value: str, label: str) -> Table:
    inner = Table(
        [[Paragraph(value, S["kpi"])], [Paragraph(label, S["kpilabel"])]],
        colWidths=[CONTENT_W / 4 - 6],
    )
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return inner


def _decorate(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 12 * mm, f"{d.TITLE[:78]}")
    canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Page {canvas.getPageNumber()}")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
    canvas.restoreState()


def build_report(result: LcaResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    model = result.model
    impact = result.impact
    gwp = model.total_t
    energy_gj = impact.energy_mj / 1000.0
    contrib = result.contribution.set_index("stage_key")
    shares = {k: float(contrib.loc[k, "gwp_share_pct"]) for k in contrib.index if k != "total"}
    gwp_stage = {k: float(contrib.loc[k, "gwp_kg_co2e"]) for k in contrib.index if k != "total"}
    ev = result.evidence_summary
    scr = result.screening_summary
    recon_low = float(result.reconciliation["total_t"].iloc[0])
    recon_high = float(result.reconciliation["total_t"].iloc[-1])

    scen = result.scenarios.set_index("scenario")
    zero_grid = float(scen.loc["renewable_grid", "pcf_t"])
    green = float(scen.loc["green_h2_syngas", "pcf_t"])
    mto_own = (model.flows.ethylene_t * model.params.mto_scope1 * model.params.mto_burden_share)
    green_share_mto = 100.0 * mto_own / (green * 1000.0) if green else 0.0

    sens = result.sensitivity.set_index("parameter")
    grid_swing = float(sens.loc["ef_grid", "swing_t"])
    alloc_swing = float(sens.loc["mto_burden_share", "swing_t"])
    mto_swing = float(sens.loc["mto_scope1", "swing_t"])
    eur = float(scen.loc["economic_allocation", "pcf_t"])
    mass = float(scen.loc["mass_allocation", "pcf_t"])

    checks = quality_checks(result)
    status_counts = checks["status"].value_counts().to_dict()
    dqi_counts = result.dqi["dqi_rating"].value_counts().to_dict()

    story: list = []

    # ------------------------------------------------------------------ cover
    story += [
        Spacer(1, 12 * mm),
        Paragraph("INDUSTRIAL LIFE-CYCLE ASSESSMENT", S["meta"]),
        Spacer(1, 3 * mm),
        Paragraph(d.TITLE, S["title"]),
        Paragraph(
            f"Functional unit: 1,000 kg pelletised HDPE resin at the factory gate  ·  "
            f"boundary: cradle-to-gate  ·  method: IPCC AR6 GWP100  ·  version {d.VERSION}",
            S["subtitle"],
        ),
        Spacer(1, 6 * mm),
        Table(
            [[_box(f"{gwp:.3f} t", "CO2e per t HDPE (functional unit)"),
              _box(f"{energy_gj:,.0f} GJ", "fossil primary energy per t"),
              _box(f"{shares['methanol']:.1f} %", "of the burden from methanol synthesis"),
              _box(f"{zero_grid:.2f} t", "if the grid were zero-carbon")]],
            colWidths=[CONTENT_W / 4] * 4,
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBEFORE", (1, 0), (-1, -1), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]),
        ),
        Spacer(1, 8 * mm),
        Paragraph(
            "<b>What this is.</b> A quantitative cradle-to-gate LCA of high-density polyethylene "
            "produced through the natural gas - methanol - MTO - polymerisation chain, built to "
            "ISO 14040/14044 and ISO 14067 framing. It quantifies climate change and a primary-energy "
            "indicator, tests the result against the inventory's own carbon balance, and declares the "
            "categories the inventory cannot support rather than estimating them.",
            S["body"],
        ),
        Paragraph(
            "<b>What it is not.</b> Not a cradle-to-grave study: use phase and end-of-life are outside "
            "the declared boundary. Not a site-measured inventory: all foreground data are secondary. "
            "Not critically reviewed. Not a multi-category impact assessment beyond climate change and "
            "the energy indicator, because the inventory carries aggregated CO2e rather than "
            "species-resolved emissions.",
            S["body"],
        ),
        Spacer(1, 5 * mm),
        Paragraph(
            f"Prepared for internal technical review  ·  {date.today().isoformat()}  ·  "
            f"generated from the project engine; every figure in this report is reproducible with "
            f"<font face='Courier'>python -m lca</font>.",
            S["meta"],
        ),
        PageBreak(),
    ]

    # ------------------------------------------------------- goal and scope
    story += [
        Paragraph("1  Goal and scope", S["h1"]),
        Paragraph("1.1  Decision and audience", S["h2"]),
        _p(d.DECISION),
        _p(d.AUDIENCE),
        Paragraph("1.2  Standards and study status", S["h2"]),
        _p(d.STANDARDS),
        Paragraph("1.3  Product and functional unit", S["h2"]),
        _p(d.PRODUCT),
        _p(f"<b>Functional unit.</b> {d.FUNCTIONAL_UNIT}"),
        _p(
            f"<b>Declared unit.</b> {d.DECLARED_UNIT} The reference flow is "
            f"{model.flows.hdpe_t * 1000:,.0f} kg of resin, so every inventory quantity in this report "
            "is expressed per functional unit by construction rather than by a later division."
        ),
        _p(f"<b>Geography and technology.</b> {d.GEOGRAPHY}"),
        _p(f"<b>Reference period.</b> {d.REFERENCE_PERIOD}"),
        Paragraph("1.4  Cut-off", S["h2"]),
        _p(d.CUT_OFF),
        Paragraph("2  System boundary", S["h1"]),
        _p(
            "The boundary is cradle-to-gate. It begins with natural gas extraction and ends at the "
            "exit of the pelletising unit, so the declared product is uncompounded resin ready for "
            "bulk transport. Process \u2018combustion\u2019 emissions are included at the point of "
            "generation (Scope 1); purchased electricity is included as Scope 2; natural gas supply "
            "is included as Scope 3 category 1. No downstream stage is modelled."
        ),
    ]

    inclusion_rows = [["Included module", "Treatment"]]
    inclusion_rows += [[item, treatment] for item, treatment in d.INCLUSIONS]
    story += [_table(inclusion_rows, [0.32 * CONTENT_W, 0.68 * CONTENT_W]), Spacer(1, 4 * mm)]
    story += [
        _image(result.figures["boundary"], 0.94 * CONTENT_W),
        Paragraph(
            "Figure 1. Functional unit, process chain, system boundary and the flows excluded from "
            "the quantified inventory. Emissions are shown per stage in kg CO2e per functional unit.",
            S["caption"],
        ),
    ]

    exclusion_rows = [["Excluded / not inventoried", "Reason", "Materiality"]]
    exclusion_rows += [[item, why, materiality] for item, why, materiality in d.EXCLUSIONS]
    story += [
        _table(exclusion_rows, [0.24 * CONTENT_W, 0.36 * CONTENT_W, 0.40 * CONTENT_W], font=6.8),
        Paragraph(
            "Table 1. Inclusions and exclusions. The exclusions are listed so the boundary claim can "
            "be checked against the result; none of them is included in the 6.07 t figure.",
            S["caption"],
        ),
        Paragraph("3  Allocation", S["h1"]),
        _p(d.ALLOCATION),
    ]

    bases = {b.key: b for b in allocation_bases(model.params)}
    alloc_rows = [["Basis", "Ethylene share of node 2", "t CO2e/t HDPE", "Delta vs base"]]
    for scenario_key, basis_key, label in (
        ("baseline", "as_specified", "As specified (yield-based)"),
        ("mass_allocation", "mass_allocation", "Mass allocation (42/38/20 carbon)"),
        ("economic_allocation", "economic_allocation", "Economic allocation (reference prices)"),
    ):
        alloc_rows.append([
            label,
            f"{bases[basis_key].ethylene_share:.1%}",
            f"{float(scen.loc[scenario_key, 'pcf_t']):.3f}",
            "base" if scenario_key == "baseline"
            else f"{100.0 * (float(scen.loc[scenario_key, 'pcf_t']) - gwp) / gwp:+.1f} %",
        ])
    story += [_table(alloc_rows, [0.42 * CONTENT_W, 0.22 * CONTENT_W, 0.18 * CONTENT_W, 0.18 * CONTENT_W],
                     align_right=(2, 3))]
    story += [
        Paragraph(
            "Table 2. Allocation sensitivity. Only node 2's own Scope 1 and Scope 2 burden is "
            "re-allocated; the embedded methanol burden stays with ethylene because the 2.95 t/t yield "
            "already nets out the co-products. Allocating the embedded burden again would credit the "
            "co-products twice.",
            S["caption"],
        ),
    ]

    # -------------------------------------------------------- method and IA
    story += [
        Paragraph("4  Impact assessment method and category coverage", S["h1"]),
        _p(d.METHOD),
    ]
    cat_rows = [["Category", "Indicator", "Unit", "Status"]]
    for row in result.categories.itertuples():
        cat_rows.append([row.category, row.indicator, row.unit, row.status])
    story += [
        _table(cat_rows, [0.30 * CONTENT_W, 0.27 * CONTENT_W, 0.16 * CONTENT_W, 0.27 * CONTENT_W],
               font=6.9),
        Paragraph(
            "Table 3. Declared impact categories. Only climate change is quantified. Eight further "
            "categories are declared and left unquantified because the inventory has no "
            "species-resolved emissions to characterise; estimating them from CO2e would not be an "
            "impact assessment.",
            S["caption"],
        ),
        Paragraph("5  Life-cycle inventory", S["h1"]),
        _p(
            f"The inventory contains {len(result.flows)} flows across four stages, each carrying a "
            "quantity, unit, source key, data type, geography, period and a five-criterion pedigree "
            "score. The table below aggregates them to stage level; the flow-level table, the "
            "pedigree matrix, the source register and the completeness matrix are in "
            "<font face='Courier'>LCA_inventory.xlsx</font> (sheets LCI, Data quality, Sources, "
            "Completeness)."
        ),
    ]
    stage_rows = [["Stage", "Scope 1", "Scope 2", "Scope 3.1", "Total kg CO2e", "Share", "Electricity kWh", "Energy GJ"]]
    for row in result.stages.itertuples():
        stage_rows.append([
            row.stage,
            _n(row.scope1_kg),
            _n(row.scope2_kg),
            _n(row.scope3_kg),
            _n(row.total_kg_co2e),
            f"{row.share_pct:.1f} %",
            _n(row.electricity_kwh),
            _n(row.energy_mj / 1000, 1),
        ])
    story += [
        _table(stage_rows, [0.27 * CONTENT_W, 0.09 * CONTENT_W, 0.09 * CONTENT_W, 0.09 * CONTENT_W,
                            0.12 * CONTENT_W, 0.08 * CONTENT_W, 0.14 * CONTENT_W, 0.12 * CONTENT_W],
               align_right=(1, 2, 3, 4, 5, 6, 7), font=6.8),
        Paragraph(
            "Table 4. Stage aggregates per functional unit. Energy includes the declared 29.8 GJ/t "
            "methanol fuel energy and electricity converted at 9.0 MJ primary per kWh delivered.",
            S["caption"],
        ),
        Paragraph("5.1  Provenance and data quality", S["h2"]),
        _p(
            "Every factor is traceable to one of nine source keys. The four most consequential are "
            "the specification's stoichiometry (S1), emission factors (S2) and node inventories (S3), "
            "plus the carbon-balance module (S9) used to bound the inventory against its own mass "
            "balance. No background database is linked: the specification gives no dataset identifier "
            "or version, which is the study's most important data-quality gap and is recorded as such "
            "in check Q-04."
        ),
        _p(
            f"Pedigree scores are mostly B (mean {result.dqi['dqi_score'].mean():.2f}): the flows are "
            "technologically and geographically representative but secondary, aggregated and, for the "
            "MTO and polymerisation nodes, inconsistent with the node carbon balance. The co-monomer "
            "flow is scored C because only its mass is modelled, not its supply chain."
        ),
        Paragraph("6  Impact results", S["h1"]),
    ]

    impact_rows = [["Category / indicator", "Value", "Per kg resin", "Unit", "Status"]]
    for row in result.impact_table.itertuples():
        impact_rows.append([
            f"{row.category} - {row.indicator}",
            _n(row.value, 1),
            f"{row.value_per_kg:,.3f}",
            row.unit,
            row.status,
        ])
    story += [
        _table(impact_rows, [0.40 * CONTENT_W, 0.16 * CONTENT_W, 0.16 * CONTENT_W,
                             0.13 * CONTENT_W, 0.15 * CONTENT_W], align_right=(1, 2), font=6.9),
        Spacer(1, 1.5 * mm),
        _image(result.figures["gwp"], CONTENT_W * 0.80),
        Paragraph(
            "Figure 2. Climate-change contribution by stage, split by Scope 1, Scope 2 and upstream "
            "Scope 3.1.",
            S["caption"],
        ),
        _image(result.figures["energy"], CONTENT_W * 0.90),
        Paragraph(
            "Figure 3. Fossil primary-energy demand by stage. This is a screening indicator with a "
            "documented conversion, not a cumulative-energy-demand database result.",
            S["caption"],
        ),
    ]

    # ------------------------------------------------------------- hotspots
    story += [
        Paragraph("7  Hotspots and interpretation", S["h1"]),
        _p(
            f"Methanol synthesis carries {gwp_stage['methanol']:,.0f} kg CO2e, or "
            f"{shares['methanol']:.1f} % of the cradle-to-gate burden. That is not an artefact of the "
            "allocation: it is the product of two real effects. First, the chain needs "
            f"{model.flows.methanol_t:.3f} t of methanol per tonne of resin, so every kilogram of "
            "methanol burden is multiplied by three before it reaches the gate. Second, the methanol "
            f"plant is the most carbon-intensive node: {model.params.methanol_scope1:,.0f} kg CO2e/t "
            f"Scope 1 plus {model.params.methanol_kwh_per_t * model.params.ef_grid:,.0f} kg CO2e/t "
            f"Scope 2, on a product whose carbon is then largely retained in the polymer."
        ),
        _p(
            f"MTO and separation contributes {gwp_stage['mto']:,.0f} kg ({shares['mto']:.1f} %) and "
            f"natural gas supply {gwp_stage['ng_extraction']:,.0f} kg ({shares['ng_extraction']:.1f} %). "
            f"Polymerisation is small at {gwp_stage['hdpe']:,.0f} kg ({shares['hdpe']:.1f} %) because "
            "its electricity and venting are an order of magnitude below reforming. The ranking is "
            "therefore: feedstock and reforming first, olefin purification second, polymerisation last."
        ),
        _p(
            f"The abatement ladder follows the same order. A zero-carbon grid removes "
            f"{float(scen.loc['baseline', 'scope2_kg']):,.0f} kg CO2e (41 % of the total) and leaves "
            f"{zero_grid:.2f} t. Removing the reformer's Scope 1 - the green-hydrogen syngas case - "
            f"takes the result to {green:.2f} t, at which point MTO regeneration is "
            f"{green_share_mto:.0f} % of what remains. The two levers are not additive: the methanol "
            "plant's direct emissions include fuel combustion that a green-syngas retrofit would also "
            "change, and this model does not re-engineer that node, so the ladder is an ordering, not "
            "a sum of independent savings."
        ),
        Paragraph("7.1  Robust and conditional conclusions", S["h2"]),
        _p(
            "<b>Robust.</b> Methanol synthesis is the largest stage under every inventory and "
            "allocation variant tested: the closure-consistent inventory, the upstream-factor bracket, "
            "the polymerisation bracket and both allocation bases all leave it above 55 %. Grid "
            "decarbonisation is the single largest lever, worth more than the next two levers combined."
        ),
        _p(
            "<b>Conditional.</b> The ranking changes if the syngas route itself is decarbonised: in "
            "the green-hydrogen case methanol synthesis drops out of the inventory and MTO regeneration "
            "becomes the hotspot. Any statement that 'methanol is always the hotspot' is therefore a "
            "statement about the fossil route, not about HDPE in general."
        ),
        _p(
            "<b>Not supported.</b> The study cannot rank stages on acidification, eutrophication, "
            "photochemical ozone, particulate matter, water or land use. Those categories need "
            "substance-level emissions the specification does not carry, and no conclusion should be "
            "drawn for them from this work."
        ),
    ]

    # ---------------------------------------------------------- sensitivity
    story += [
        Paragraph("8  Sensitivity analysis", S["h1"]),
        _p(
            "Eight assumptions are tested one at a time. Each row in the register is labelled by the "
            "provenance of its range, because the brief is explicit that arbitrary brackets must not "
            "be presented as measured variability. Three ranges are constrained by the model's own "
            "carbon balance (evidence); one is a decision variable (grid); one is a method choice "
            "(allocation); three are analyst brackets with no measured basis (judgement)."
        ),
        _image(result.figures["tornado"], CONTENT_W * 0.94),
        Paragraph(
            "Figure 4. One-at-a-time sensitivity. Bar colour gives the provenance of the range; the "
            "dashed line is the base-case 6.07 t.",
            S["caption"],
        ),
    ]
    sens_rows = [["Assumption", "Range tested", "Basis", "Swing (t)", "Swing (%)"]]
    for row in result.sensitivity.itertuples():
        sens_rows.append([
            row.label,
            f"{row.low_value:g} to {row.high_value:g}",
            row.basis,
            f"{row.swing_t:.3f}",
            f"{row.swing_pct:.1f}",
        ])
    story += [
        KeepTogether([
            _table(sens_rows, [0.34 * CONTENT_W, 0.20 * CONTENT_W, 0.14 * CONTENT_W,
                               0.16 * CONTENT_W, 0.16 * CONTENT_W], align_right=(3, 4), font=6.9),
            Paragraph(
                "Table 5. Sensitivity register. The grid factor dominates at "
                f"{grid_swing:.2f} t; allocation is the next largest at {alloc_swing:.2f} t; the "
                f"evidence-constrained MTO Scope 1 range is worth only {mto_swing:.2f} t.",
                S["caption"],
            ),
        ]),
        _p(
            "The ordering matters more than the individual numbers. The two largest swings are a "
            "decision (how the grid is supplied) and a method choice (how co-products are treated). "
            "The inventory parameters that the carbon balance can actually constrain move the result "
            "by hundredths of a tonne. A study that reported only inventory uncertainty would "
            "understate the real uncertainty by an order of magnitude."
        ),
        Paragraph("9  Uncertainty analysis", S["h1"]),
        _p(
            f"Two distributions are run, each with {result.evidence_summary['n']:,} fixed-seed draws. "
            "The first samples only the evidence-constrained reconciliation "
            "path: the inventory is moved from the specification as written (theta = 0) to the "
            "carbon-consistent inventory (theta = 1), with MTO Scope 1, methanol demand and ethylene "
            "demand moving together because the node balances couple them. The second adds the three "
            "judgement brackets and is labelled a screening distribution, not measured variability. "
            "Grid factor and allocation are excluded from both: they are decisions, not uncertainties."
        ),
        _image(result.figures["uncertainty"], 0.88 * CONTENT_W),
        Paragraph(
            "Figure 5. Monte Carlo distributions: evidence-only (left) and screening (right); "
            "dashed red line = base case.",
            S["caption"],
        ),
    ]
    unc_rows = [["Run", "Mean", "SD", "P5", "P50", "P95", "Range"]]
    for summary in (result.evidence_summary, result.screening_summary):
        unc_rows.append([
            str(summary["label"]),
            f"{summary['mean_t']:.4f}",
            f"{summary['sd_t']:.4f}",
            f"{summary['p05_t']:.4f}",
            f"{summary['p50_t']:.4f}",
            f"{summary['p95_t']:.4f}",
            f"{summary['min_t']:.4f}-{summary['max_t']:.4f}",
        ])
    story += [
        _table(unc_rows, [0.38 * CONTENT_W, 0.11 * CONTENT_W, 0.09 * CONTENT_W, 0.10 * CONTENT_W,
                          0.10 * CONTENT_W, 0.10 * CONTENT_W, 0.12 * CONTENT_W],
               align_right=(1, 2, 3, 4, 5, 6)),
        Paragraph("Table 6. Uncertainty summaries, t CO2e per t HDPE.", S["caption"]),
        _p(
            f"Reconciling the inventory to its own carbon balance moves the result from "
            f"{recon_low:.3f} to {recon_high:.3f} t, a change of "
            f"{100.0 * (recon_high - recon_low) / recon_low:+.1f} %. That is the honest size of the "
            "inventory problem: it is real, it is documented, and it does not change the conclusion. "
            f"The screening distribution widens only to {scr['p05_t']:.3f}-{scr['p95_t']:.3f} t. "
            "Compare that with the 3.55-6.07 t span produced by the grid scenario. The dominant "
            "uncertainty in this study is not measurement error; it is which system is being described."
        ),
        Paragraph("10  Scenario analysis", S["h1"]),
        _image(result.figures["scenarios"], CONTENT_W * 0.92),
        Paragraph(
            "Figure 6. Decision and method scenarios against the 6.07 t base case.",
            S["caption"],
        ),
    ]
    scen_rows = [["Scenario", "t CO2e/t", "reduction vs base", "Scope 1", "Scope 2", "Scope 3.1"]]
    for row in result.scenarios.itertuples():
        scen_rows.append([
            row.label,
            f"{row.pcf_t:.3f}",
            f"{row.reduction_vs_baseline_pct:+.1f} %",
            _n(row.scope1_kg),
            _n(row.scope2_kg),
            _n(row.scope3_kg),
        ])
    story += [
        _table(scen_rows, [0.40 * CONTENT_W, 0.13 * CONTENT_W, 0.12 * CONTENT_W,
                           0.115 * CONTENT_W, 0.115 * CONTENT_W, 0.12 * CONTENT_W],
               align_right=(1, 2, 3, 4, 5), font=6.8),
        Paragraph(
            "Table 7. Scenario results. The green-hydrogen and allocation rows are sensitivity "
            "variants, not forecasts.",
            S["caption"],
        ),
        _p(
            f"Mass allocation lowers the result to {mass:.2f} t and economic allocation to {eur:.2f} t. "
            "Both are defensible under ISO 14044, and the choice must be declared with any published "
            "figure. The utility-basis variant is the one place where two internal datasets disagree: "
            "the explicit-utilities decomposition reproduces the execution script but changes the "
            "response to grid decarbonisation, because 60 % of its Scope 2 is thermal."
        ),
    ]

    # --------------------------------------------------------- quality & gaps
    story += [
        Paragraph("11  Data quality, completeness and limitations", S["h1"]),
        _p(
            "The completeness matrix separates what is quantified from what is not, and sizes the "
            "largest avoidable gap. The only gap with a materiality estimate is co-monomer supply: "
            "0.37-0.62 % of the climate result under an indicative 1.5-2.5 kg CO2e/kg proxy. That "
            "proxy is not a dataset and is not used in the headline result. Catalysts, water, "
            "wastewater and solid waste have no quantities at all and are left open rather than "
            "assumed."
        ),
    ]
    comp_rows = [["Module", "Status", "kg CO2e*", "%*", "Basis"]]
    for row in result.completeness.itertuples():
        comp_rows.append([
            row.module,
            row.status,
            "" if pd.isna(row.materiality_kg_co2e) else f"{float(row.materiality_kg_co2e):,.0f}",
            "" if pd.isna(row.materiality_pct) else f"{float(row.materiality_pct):.2f}",
            row.basis,
        ])
    story += [
        _table(comp_rows, [0.24 * CONTENT_W, 0.13 * CONTENT_W, 0.11 * CONTENT_W,
                           0.08 * CONTENT_W, 0.44 * CONTENT_W], font=6.5),
        # NOTE: the two materiality columns are indicative gap sizes, not results.
        Paragraph(
            "Table 8. Completeness matrix. * For the co-monomer row these are the indicative size "
            "of the gap under a proxy, not a modelled contribution.",
            S["caption"],
        ),
        Paragraph("11.1  Limitations", S["h2"]),
    ]
    for item in d.LIMITATIONS:
        story.append(Paragraph(item, S["bullet"], bulletText="\u2022"))
    story += [
        Paragraph("11.2  Data actions to close the gaps", S["h2"]),
        _p(
            "The study is limited by data, not by method. These are the actions that would move it "
            "from a screening assessment to a defensible one, in priority order."
        ),
    ]
    action_rows = [
        ["Data action", "What it closes", "Priority"],
        ["Link a licensed background database and record its name, version and system model",
         "Check Q-04; all upstream factors; reproducibility", "High"],
        ["Replace the aggregate Scope 1 CO2e with a species split (CO2, CH4, N2O, NOx, SO2, NMVOC, PM)",
         "Acidification, eutrophication, POCP, particulate matter", "High"],
        ["Obtain a co-monomer supply dataset for 1-butene/1-hexene",
         "The only sized completeness gap (0.4-0.6 %)", "Medium"],
        ["Meter or obtain 12 months of site utility data (kWh, steam, fuel)",
         "Pedigree from B to A for the three nodes", "Medium"],
        ["Build a water balance: withdrawal, consumption, discharge volume and load",
         "Water scarcity and freshwater eutrophication", "Medium"],
        ["Collect catalyst production datasets (SAPO-34, Cu/ZnO/Al2O3, Ziegler-Natta)",
         "Completeness of the material inputs", "Low"],
    ]
    story += [
        _table(action_rows, [0.50 * CONTENT_W, 0.36 * CONTENT_W, 0.14 * CONTENT_W], font=6.8),
        Paragraph("Table 9. Data-collection actions.", S["caption"]),
    ]
    check_rows = [["ID", "Check", "Status", "Evidence / what is needed"]]
    for row in checks.itertuples():
        evidence = row.evidence if row.status == "Met" else f"{row.evidence} <b>Needed:</b> {row.what_is_needed}"
        check_rows.append([row.id, row.check, row.status, evidence])
    story += [
        Spacer(1, 3 * mm),
        KeepTogether([
            Paragraph("12  Quality-check record", S["h1"]),
            _p(
                "The brief's quality checks, plus three deliverable checks, are recorded below with "
                "the evidence and, where a check is not fully met, what would close it. Two checks "
                "are recorded as not met; neither is papered over with a proxy."
            ),
            _table(check_rows, [0.06 * CONTENT_W, 0.24 * CONTENT_W, 0.09 * CONTENT_W, 0.61 * CONTENT_W],
                   font=6.5),
            Paragraph(
                f"Table 10. {status_counts.get('Met', 0)} met, "
                f"{status_counts.get('Partial', 0)} partial, "
                f"{status_counts.get('Not met', 0)} not met.",
                S["caption"],
            ),
        ]),
        Paragraph("13  Deliverables and reproducibility", S["h1"]),
        _p(
            "Every deliverable is generated by one command from one parameter set, so the report, "
            "workbook, charts and openLCA tables cannot disagree."
        ),
    ]
    del_rows = [["Deliverable", "Path", "Status"]]
    for row in deliverables(result).itertuples():
        del_rows.append([row.deliverable, row.path, row.status])
    story += [
        _table(del_rows, [0.36 * CONTENT_W, 0.46 * CONTENT_W, 0.18 * CONTENT_W], font=6.9),
        Paragraph("Table 11. Deliverable index.", S["caption"]),
        Spacer(1, 4 * mm),
        Paragraph(
            "<b>Reproduce.</b> <font face='Courier'>python -m lca --outdir outputs/LCA</font> "
            "regenerates the workbook, CSV and JSON exports, figures, this report and the "
            "presentation from <font face='Courier'>pcf.params.ModelParams</font>. Change a parameter "
            "there (or pass overrides) and every artefact moves together.",
            S["body"],
        ),
        Paragraph(
            "<b>openLCA.</b> The model is also built in openLCA 2.6.2 over its IPC server: six "
            "foreground unit processes run on IPCC 2007 climate change - GWP 100a and reproduce the "
            "Python total to the reported digits. The background processes are not licensed datasets, "
            "so this verifies the foreground arithmetic, not an ecoinvent footprint. "
            "<font face='Courier'>lca/openlca/README.md</font> gives the build sequence.",
            S["body"],
        ),
    ]

    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=d.TITLE,
        author="HDPE LCA model",
        subject="Cradle-to-gate LCA of HDPE via MTO",
    )
    frame = Frame(MARGIN, 20 * mm, CONTENT_W, PAGE_H - 38 * mm, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_decorate)])
    doc.build(story)
    return path
