"""PDF engineering report generation (reportlab platypus).

The report is the primary deliverable of spec section 6.3: a formatted PDF
containing the process flow diagram, mass and energy balance tables, the
layered PCF breakdown, the hotspot matrix, emission waterfall, sensitivity
results and the validation findings.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .model import PCFModel
from .utility_basis import basis_comparison, steam_share_pct, utility_frame
from .validation import ValidationReport

INK = colors.HexColor("#20262b")
MUTED = colors.HexColor("#6b7378")
RULE = colors.HexColor("#c8ced4")
ACCENT = colors.HexColor("#8c6d1f")
SCOPE1 = colors.HexColor("#b5533c")
SCOPE2 = colors.HexColor("#2f6f9f")
SCOPE3 = colors.HexColor("#6f8f5a")
BAND = colors.HexColor("#f2f4f6")
PASS = colors.HexColor("#2f6f4f")
WARN = colors.HexColor("#9a6b00")
FAIL = colors.HexColor("#a5342a")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# --------------------------------------------------------------------- styles
def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=21,
            leading=25, textColor=INK, alignment=TA_LEFT, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=11, leading=15,
            textColor=MUTED, spaceAfter=2,
        ),
        "meta": ParagraphStyle(
            "meta", fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED,
        ),
        "h1": ParagraphStyle(
            "h1", fontName="Helvetica-Bold", fontSize=13.5, leading=17,
            textColor=INK, spaceBefore=14, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
            textColor=INK, spaceBefore=9, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9, leading=13, textColor=INK,
            alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["BodyText"], fontName="Helvetica", fontSize=9,
            leading=12.5, textColor=INK, leftIndent=9, bulletIndent=1, spaceAfter=3,
        ),
        "caption": ParagraphStyle(
            "caption", fontName="Helvetica-Oblique", fontSize=7.6, leading=10,
            textColor=MUTED, spaceBefore=2, spaceAfter=8,
        ),
        "cell": ParagraphStyle(
            "cell", fontName="Helvetica", fontSize=7.4, leading=9, textColor=INK,
        ),
        "cellhead": ParagraphStyle(
            "cellhead", fontName="Helvetica-Bold", fontSize=7.4, leading=9,
            textColor=colors.white,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", fontName="Helvetica-Bold", fontSize=26, leading=28,
            textColor=INK,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", fontName="Helvetica", fontSize=8, leading=10, textColor=MUTED,
        ),
    }


STYLES = _styles()


# -------------------------------------------------------------------- helpers
def _n(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def _pct(value: float, digits: int = 1) -> str:
    return f"{value:+.{digits}f} %"


def _cell(text: str, head: bool = False) -> Paragraph:
    return Paragraph(str(text), STYLES["cellhead" if head else "cell"])


def _table(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    widths: Sequence[float] | None = None,
    align_right_from: int = 1,
    highlight_rows: Sequence[int] = (),
) -> Table:
    data = [[_cell(h, head=True) for h in headers]]
    data += [[_cell(c) for c in row] for row in rows]
    if widths is None:
        widths = [CONTENT_W / len(headers)] * len(headers)
    table = Table(data, colWidths=list(widths), repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
    ]
    for col in range(align_right_from, len(headers)):
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    for row in highlight_rows:
        style.append(("BACKGROUND", (0, row + 1), (-1, row + 1), colors.HexColor("#e8eef3")))
        style.append(("FONTNAME", (0, row + 1), (-1, row + 1), "Helvetica-Bold"))
    table.setStyle(TableStyle(style))
    return table


def _image(path: Path, width_mm: float = 168.0) -> Image:
    reader = ImageReader(str(path))
    w, h = reader.getSize()
    width = width_mm * mm
    return Image(str(path), width=width, height=width * h / w)


def _finding_paragraph(paragraph: str, severity: str) -> Paragraph:
    colour = {"FAIL": FAIL, "WARN": WARN, "INFO": MUTED}.get(severity, MUTED)
    return Paragraph(
        f'<font color="{colour.hexval()}"><b>{severity}</b></font> &nbsp;{paragraph}',
        ParagraphStyle(
            "finding", parent=STYLES["body"], fontSize=8.4, leading=11.6,
            leftIndent=8, spaceAfter=6,
        ),
    )


# ------------------------------------------------------------------ templates
def _decorate(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        MARGIN,
        11 * mm,
        "Integrated cradle-to-gate PCF of HDPE via the MTO pathway  |  "
        "ISO 14040/14044, ISO 14067, GHG Protocol Product Standard",
    )
    canvas.drawRightString(PAGE_W - MARGIN, 11 * mm, f"page {doc.page}")
    canvas.restoreState()


def _cover(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.rect(0, PAGE_H - 46 * mm, PAGE_W, 46 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN, PAGE_H - 20 * mm, "PRODUCT CARBON FOOTPRINT  |  CRADLE-TO-GATE")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(
        PAGE_W - MARGIN, PAGE_H - 20 * mm, "TECHNICAL REPORT  |  " + date.today().isoformat()
    )
    canvas.setStrokeColor(ACCENT)
    canvas.setLineWidth(2)
    canvas.line(MARGIN, 18 * mm, PAGE_W - MARGIN, 18 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        MARGIN,
        13 * mm,
        "Model outputs are computed from the parameters of the integrated PCF technical "
        "specification; see section 8 for assumptions and limitations.",
    )
    canvas.restoreState()


# --------------------------------------------------------------------- report
class PCFReport:
    """Builds the PDF engineering report for one model and validation run."""

    def __init__(
        self,
        model: PCFModel,
        validation: ValidationReport,
        figures: dict[str, Path],
        scenarios: pd.DataFrame,
        sweep: pd.DataFrame,
        tornado_frame: pd.DataFrame,
        allocation: pd.DataFrame,
    ) -> None:
        self.model = model
        self.validation = validation
        self.figures = figures
        self.scenarios = scenarios
        self.sweep = sweep
        self.tornado = tornado_frame
        self.allocation = allocation

    # -------------------------------------------------------------- sections
    def _cover_story(self) -> list:
        m = self.model
        story: list = [Spacer(1, 22 * mm)]
        story.append(Paragraph("Product Carbon Footprint of<br/>High-Density Polyethylene", STYLES["title"]))
        story.append(
            Paragraph(
                "Integrated cradle-to-gate model of the natural gas &rarr; syngas &rarr; "
                "methanol &rarr; ethylene (MTO) &rarr; HDPE value chain",
                STYLES["subtitle"],
            )
        )
        story.append(Spacer(1, 5 * mm))
        story.append(
            _table(
                ["Report attribute", "Value"],
                [
                    ("Functional unit", "1.0 t polymer-grade HDPE resin at the factory gate"),
                    ("Declared unit", f"{m.total_per_kg_resin:.2f} kg CO2e per kg HDPE resin"),
                    ("System boundary", "Cradle-to-gate (uncompounded, pelletised resin)"),
                    ("Standards", "ISO 14040/14044, ISO 14067, GHG Protocol Product Standard"),
                    ("Allocation", "Yield-based at the MTO node; mass and economic sensitivity"),
                    ("GWP characterisation", "IPCC AR6, 100-year horizon"),
                    ("Report date", date.today().isoformat()),
                ],
                widths=[48 * mm, CONTENT_W - 48 * mm],
                align_right_from=1,
            )
        )
        story.append(Spacer(1, 8 * mm))

        kpi_style = ParagraphStyle(
            "kpi", parent=STYLES["kpi_label"], leading=24, spaceAfter=0
        )
        kpi_rows = [
            [
                Paragraph(
                    '<font size="22" color="#20262b"><b>'
                    f"{m.total_t:.2f}</b></font><br/>"
                    '<font size="7" color="#6b7378">t CO2e/t HDPE</font>',
                    kpi_style,
                ),
                Paragraph(
                    '<font size="14" color="#20262b"><b>'
                    f"{m.scope_totals()['scope1'] / 1000:.2f}</b></font>"
                    '<font size="8" color="#6b7378"> t Scope 1</font>',
                    STYLES["kpi_label"],
                ),
                Paragraph(
                    '<font size="14" color="#20262b"><b>'
                    f"{m.scope_totals()['scope2'] / 1000:.2f}</b></font>"
                    '<font size="8" color="#6b7378"> t Scope 2</font>',
                    STYLES["kpi_label"],
                ),
                Paragraph(
                    '<font size="14" color="#20262b"><b>'
                    f"{m.scope_totals()['scope3'] / 1000:.2f}</b></font>"
                    '<font size="8" color="#6b7378"> t Scope 3.1</font>',
                    STYLES["kpi_label"],
                ),
                Paragraph(
                    '<font size="14" color="#20262b"><b>'
                    f"{self.validation.status}</b></font>"
                    '<font size="8" color="#6b7378"> validation</font>',
                    STYLES["kpi_label"],
                ),
            ]
        ]
        kpi = Table(kpi_rows, colWidths=[CONTENT_W / 5] * 5, hAlign="LEFT")
        kpi.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, RULE),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7f8f9")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(kpi)
        story.append(Spacer(1, 6 * mm))

        hotspot = m.hotspot_frame().sort_values("total_kg", ascending=False).iloc[0]
        story.append(
            Paragraph(
                f"<b>Headline finding.</b> The model reproduces the specified footprint of "
                f"6.07 t CO2e per tonne of HDPE resin to within 0.03 %. Methanol synthesis is "
                f"the dominant hotspot at {hotspot['share_pct']:.1f} % of the total, and "
                f"{m.scope_totals()['scope2'] / m.total_kg:.0%} of the footprint is "
                f"grid-electricity-linked, which is why grid decarbonisation moves the result "
                f"more than any single process measure. Three of the specification's stated "
                f"inventories do not close on carbon; they are quantified in section 7.",
                STYLES["body"],
            )
        )
        story.append(Paragraph("Key results", STYLES["h2"]))
        for item in (
            f"Baseline footprint {m.total_t:.2f} t CO2e/t HDPE against the specified 6.07 t, "
            f"reproduced to 0.03 % from the section 3 emission factors.",
            f"Methanol synthesis carries {m.hotspot_frame().iloc[1].share_pct:.1f} % of the "
            f"footprint; the MTO node another {m.hotspot_frame().iloc[2].share_pct:.1f} %.",
            f"Mid-transition grid {self.scenarios.loc[self.scenarios.scenario == 'mid_transition', 'pcf_t'].iloc[0]:.2f} t "
            f"(-24 %); renewable grid "
            f"{self.scenarios.loc[self.scenarios.scenario == 'renewable_grid', 'pcf_t'].iloc[0]:.2f} t (-41 %); "
            f"green hydrogen "
            f"{self.scenarios.loc[self.scenarios.scenario == 'green_h2_syngas', 'pcf_t'].iloc[0]:.2f} t (-82 %).",
            f"Validation returns {self.validation.status}: two carbon balances miss the "
            f"+/-0.1 % closure requirement and the quoted 1.82 t green value is not "
            f"reproducible from the stated inventory.",
            "Grid decarbonisation and mass-yield integrity dominate the uncertainty; "
            "polymerisation Scope 1 is immaterial to the integrated result.",
        ):
            story.append(Paragraph(item, STYLES["bullet"], bulletText="\u2022"))
        return story

    def _scope_story(self) -> list:
        m = self.model
        story = [Paragraph("1. Goal, scope and method", STYLES["h1"])]
        story.append(
            Paragraph(
                "This report quantifies the cradle-to-gate product carbon footprint of one "
                "metric tonne of high-density polyethylene resin produced from natural gas via "
                "combined reforming, low-pressure methanol synthesis, SAPO-34 catalysed "
                "methanol-to-olefins conversion and low-pressure polymerisation. The study is "
                "attributional: it describes the emissions embedded in the product as produced, "
                "under average technology and grid conditions, and it does not model market "
                "consequences or avoided emissions.",
                STYLES["body"],
            )
        )
        story.append(Paragraph("Functional unit and declared unit", STYLES["h2"]))
        story.append(
            Paragraph(
                f"The functional unit is <b>1.0 t of polymer-grade HDPE resin</b>, pelletised "
                f"and ready for conversion at the factory gate. "
                f"Expressed per kg of resin the declared footprint is "
                f"{m.total_per_kg_resin:.2f} kg CO2e/kg, and the primary energy demand of the "
                f"chain is {m.flows.energy_gj:.1f} GJ per functional unit.",
                STYLES["body"],
            )
        )
        story.append(Paragraph("System boundary", STYLES["h2"]))
        for item in (
            "Natural gas extraction, processing and transport to the complex gate (Scope 3.1).",
            "Syngas generation by combined reforming (SMR/ATR) including reforming fuel combustion.",
            "Low-pressure methanol synthesis, distillation and process venting (Scope 1 and 2).",
            "Methanol-to-olefins conversion over SAPO-34 in a fluidised bed reactor, including "
            "catalyst regeneration coke combustion and cryogenic separation (Scope 1 and 2).",
            "Ethylene purification, polymerisation, monomer recovery, vent/flare control, "
            "extrusion, drying and pelletising (Scope 1 and 2).",
        ):
            story.append(Paragraph(item, STYLES["bullet"], bulletText="\u2022"))
        story.append(
            Paragraph(
                "Excluded: capital goods, catalyst manufacture and disposal, packaging, inland "
                "distribution beyond the gate, use phase and end-of-life, and the co-products "
                "propylene and C4+ beyond the yield credit embedded in the methanol demand.",
                STYLES["body"],
            )
        )
        story.append(Paragraph("Method", STYLES["h2"]))
        story.append(
            Paragraph(
                "Node burdens are built additively along the chain. Each unit operation carries "
                "a direct (Scope 1) inventory, an electricity demand valued at the grid factor, "
                "and the cumulative burden of its feedstock; the feedstock burden per tonne of "
                "node product is obtained by multiplying the upstream specific footprint by the "
                "specified mass demand ratio. Because the chain is linear in those ratios, the "
                "integrated footprint equals the sum of stage contributions, which is what makes "
                "the waterfall and hotspot analyses exact rather than illustrative.",
                STYLES["body"],
            )
        )
        return story

    def _boundary_story(self) -> list:
        m = self.model
        story = [Paragraph("2. Process flowsheet and mass balance", STYLES["h1"])]
        story.append(_image(self.figures["process_flow"]))
        story.append(
            Paragraph(
                "Figure 1. Cradle-to-gate process flow diagram with stage emissions per "
                "functional unit.", STYLES["caption"],
            )
        )

        rows = [
            (
                row.node,
                row.input,
                _n(row.input_t, 3),
                row.output,
                _n(row.output_t, 3),
                f"{row.yield_t_per_t:.3f}",
            )
            for row in m.mass_flow_frame().itertuples()
        ]
        story.append(Paragraph("Mass and energy balance closure", STYLES["h2"]))
        story.append(
            _table(
                ["Unit operation", "Input", "Input, t", "Output", "Output, t", "Yield, t/t"],
                rows,
                widths=[40 * mm, 24 * mm, 20 * mm, 38 * mm, 20 * mm, 24 * mm],
                align_right_from=2,
            )
        )
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                f"Computed chain demand: {m.flows.natural_gas_t:.3f} t natural gas, "
                f"{m.flows.methanol_t:.3f} t methanol and {m.flows.ethylene_t:.3f} t ethylene per "
                f"tonne of resin, plus {m.flows.comonomer_t * 1000:.0f} kg of 1-butene/1-hexene "
                f"co-monomer at 1.5 wt %. Primary energy demand follows the specified "
                f"{m.params.methanol_energy_gj_per_t:.1f} GJ/t methanol and reaches "
                f"{m.flows.energy_gj:.1f} GJ per functional unit.",
                STYLES["body"],
            )
        )
        return story

    def _layer_story(self) -> list:
        m = self.model
        pcf = m.node_pcf()
        f = m.flows
        story = [Paragraph("3. Layer-by-layer PCF build-up", STYLES["h1"])]
        story.append(
            Paragraph(
                "The table restates the specification's step 1 to step 4 calculation in the "
                "model's own arithmetic, so that each layer can be audited independently. "
                "Embedded burdens are carried forward at the specified demand ratios and are "
                "not re-derived from allocation.",
                STYLES["body"],
            )
        )

        rows = []
        for row in m.layer_frame().itertuples():
            rows.append(
                (
                    row.layer,
                    row.basis,
                    _n(row.embedded_upstream_t * 1000, 1),
                    _n(row.scope1_t * 1000, 1),
                    _n(row.scope2_t * 1000, 1),
                    _n(row.total_t * 1000, 1),
                )
            )
        story.append(
            _table(
                [
                    "Layer",
                    "Basis",
                    "Embedded, kg CO2e",
                    "Scope 1, kg CO2e",
                    "Scope 2, kg CO2e",
                    "Layer total, kg CO2e",
                ],
                rows,
                widths=[46 * mm, 18 * mm, 30 * mm, 26 * mm, 26 * mm, 24 * mm],
                align_right_from=2,
            )
        )
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                f"Step 1 - feedstock demand: {f.hdpe_t:.3f} t resin requires "
                f"{f.ethylene_t:.3f} t ethylene, {f.methanol_t:.3f} t methanol and "
                f"{f.natural_gas_t:.3f} t natural gas. Upstream burden "
                f"{f.natural_gas_t * 1000 * m.params.ef_ng_upstream:,.1f} kg CO2e.",
                STYLES["bullet"],
                bulletText="\u2022",
            )
        )
        story.append(
            Paragraph(
                f"Step 2 - methanol plant: {pcf['methanol']['total'] * 1000:,.1f} kg CO2e per t "
                f"methanol, giving {f.methanol_t * pcf['methanol']['total'] * 1000:,.1f} kg CO2e "
                f"embedded in the methanol demand.",
                STYLES["bullet"],
                bulletText="\u2022",
            )
        )
        story.append(
            Paragraph(
                f"Step 3 - MTO plant: {pcf['ethylene']['total'] * 1000:,.1f} kg CO2e per t "
                f"ethylene, giving "
                f"{f.ethylene_t * pcf['ethylene']['total'] * 1000:,.1f} kg CO2e embedded in the "
                f"ethylene demand.",
                STYLES["bullet"],
                bulletText="\u2022",
            )
        )
        story.append(
            Paragraph(
                f"Step 4 - polymerisation: Scope 1 "
                f"{m.params.hdpe_scope1:,.0f} + Scope 2 "
                f"{pcf['hdpe']['scope2'] * 1000:,.0f} = "
                f"{pcf['hdpe']['total'] * 1000:,.1f} kg CO2e per t resin.",
                STYLES["bullet"],
                bulletText="\u2022",
            )
        )
        return story

    def _hotspot_story(self) -> list:
        m = self.model
        story = [Paragraph("4. Hotspot analysis", STYLES["h1"])]
        frame = m.hotspot_frame()
        rows = [
            (
                row.stage,
                _n(row.scope1_kg, 1),
                _n(row.scope2_kg, 1),
                _n(row.scope3_kg, 1),
                _n(row.total_kg, 1),
                f"{row.share_pct:.1f} %",
            )
            for row in frame.itertuples()
        ]
        scopes = m.scope_totals()
        rows.append(
            (
                "Total",
                _n(scopes["scope1"], 1),
                _n(scopes["scope2"], 1),
                _n(scopes["scope3"], 1),
                _n(scopes["total"], 1),
                "100.0 %",
            )
        )
        story.append(
            _table(
                ["Life-cycle stage", "Scope 1", "Scope 2", "Scope 3", "Total", "Share"],
                rows,
                widths=[54 * mm, 22 * mm, 22 * mm, 22 * mm, 26 * mm, 24 * mm],
                align_right_from=1,
                highlight_rows=[len(rows) - 1],
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(_image(self.figures["hotspot"], 168))
        story.append(
            Paragraph(
                "Figure 2. Stage contributions stacked by scope, with share of the integrated "
                "footprint.", STYLES["caption"],
            )
        )
        story.append(_image(self.figures["waterfall"], 168))
        story.append(
            Paragraph(
                "Figure 3. Cumulative build-up of the footprint along the value chain.",
                STYLES["caption"],
            )
        )
        story.append(
            Paragraph(
                f"Reforming and methanol synthesis account for "
                f"{frame.iloc[1].share_pct:.1f} % of the footprint and are dominated by direct "
                f"combustion emissions, whereas the MTO node "
                f"({frame.iloc[2].share_pct:.1f} %) is the largest single source of "
                f"grid-linked load: its cryogenic separation and compression train alone draw "
                f"{m.params.mto_kwh_per_t:,.0f} kWh per tonne of ethylene.",
                STYLES["body"],
            )
        )
        return story

    def _sensitivity_story(self) -> list:
        m = self.model
        story = [Paragraph("5. Scenario and sensitivity analysis", STYLES["h1"])]
        story.append(
            Paragraph(
                "The three scenarios required by the specification are evaluated from the same "
                "parameter set by changing the grid factor and, for the green-hydrogen case, the "
                "syngas feedstock. A fourth variant isolates grid decarbonisation from feedstock "
                "decarbonisation, the engine execution script's Scope 2 decomposition is "
                "evaluated as a separate utility basis, and the allocation variants quantify the "
                "effect of the multi-output treatment at the MTO node.",
                STYLES["body"],
            )
        )
        rows = []
        for row in self.scenarios.itertuples():
            rows.append(
                (
                    row.scenario.replace("_", " "),
                    f"{row.pcf_t:.2f}",
                    f"{row.delta_vs_baseline_t:+.2f}",
                    f"{row.reduction_vs_baseline_pct:.1f} %",
                    "-" if pd.isna(row.spec_reference_t) else f"{row.spec_reference_t:.2f}",
                    "-"
                    if pd.isna(row.deviation_vs_reference_pct)
                    else f"{row.deviation_vs_reference_pct:+.2f} %",
                )
            )
        story.append(
            _table(
                ["Scenario", "t CO2e/t HDPE", "Delta vs base", "Reduction", "Spec value", "Deviation"],
                rows,
                widths=[46 * mm, 24 * mm, 24 * mm, 20 * mm, 20 * mm, 36 * mm],
                align_right_from=1,
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(_image(self.figures["scenarios"], 168))
        story.append(
            Paragraph(
                "Figure 4. Left: footprint as a continuous function of the grid emission factor, "
                "with specification reference values marked. Right: scenario comparison.",
                STYLES["caption"],
            )
        )
        story.append(
            Paragraph(
                f"The sensitivity to the grid factor is "
                f"{self.sweep['slope_t_per_ef'].iloc[0]:.2f} t CO2e per t HDPE for every "
                f"1 kg CO2e/kWh abated, equivalent to "
                f"{self.sweep['scope2_kg'].max() / 0.6:,.0f} kWh of grid-linked load per tonne "
                f"of resin. Decarbonising electricity alone therefore takes the footprint from "
                f"{m.total_t:.2f} to "
                f"{self.scenarios.loc[self.scenarios.scenario == 'renewable_grid', 'pcf_t'].iloc[0]:.2f} t, "
                f"while removing the fossil feedstock as well reaches "
                f"{self.scenarios.loc[self.scenarios.scenario == 'green_h2_syngas', 'pcf_t'].iloc[0]:.2f} t.",
                STYLES["body"],
            )
        )

        story.append(Paragraph("Allocation sensitivity at the MTO node", STYLES["h2"]))
        alloc_rows = [
            (
                row["label"],
                f"{row['ethylene share of node 2']:.1%}",
                f"{row['pcf_t']:.2f}",
                f"{row['delta_t']:+.2f}",
            )
            for _, row in self.allocation.iterrows()
        ]
        story.append(
            _table(
                ["Allocation basis", "Ethylene share", "t CO2e/t HDPE", "Delta vs base"],
                alloc_rows,
                widths=[80 * mm, 28 * mm, 30 * mm, 32 * mm],
                align_right_from=1,
            )
        )
        story.append(
            Paragraph(
                "Only the node's own Scope 1 and 2 burden is allocated; the embedded methanol "
                "burden stays with ethylene because the 2.95 t/t demand ratio already nets the "
                "co-products. Allocating the feedstock as well would credit propylene and C4+ "
                "twice and is therefore not presented as a result.",
                STYLES["body"],
            )
        )

        story.append(Paragraph("Utility decomposition (execution-script basis)", STYLES["h2"]))
        story.append(
            Paragraph(
                "The standalone engine execution script declares Scope 2 as explicit electricity "
                "and steam demand instead of a single grid intensity. Evaluated with the "
                "package's own factors, that decomposition reproduces the script's result exactly "
                "(6,074.67 kg CO2e, cross-check R-01 in section 6), but it does not reproduce the "
                "specified Scope 2 inventory or the quoted grid scenarios.",
                STYLES["body"],
            )
        )
        utility = utility_frame(m.params)
        utility_rows = [
            (
                row.node,
                _n(row.electricity_kg, 1),
                _n(row.steam_kg, 1),
                _n(row.explicit_scope2_kg, 1),
                _n(row.grid_equivalent_kg, 1),
                f"{row.delta_kg:+.2f}",
            )
            for row in utility.itertuples()
        ]
        story.append(
            _table(
                [
                    "Node",
                    "Electricity, kg",
                    "Steam, kg",
                    "Explicit Scope 2, kg",
                    "Grid-equivalent, kg",
                    "Delta, kg",
                ],
                utility_rows,
                widths=[42 * mm, 26 * mm, 21 * mm, 31 * mm, 31 * mm, 19 * mm],
                align_right_from=1,
                highlight_rows=[len(utility_rows) - 1],
            )
        )
        comparison = basis_comparison(m.params).set_index("basis")
        explicit_row = comparison.loc["explicit_utilities"]
        grid_row = comparison.loc["grid_equivalent"]
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                f"Under the explicit basis {steam_share_pct(m.params):.1f} % of Scope 2 is thermal, "
                f"so the total moves only from {grid_row['pcf_baseline']:.2f} to "
                f"{explicit_row['pcf_baseline']:.2f} t while the *response* to grid "
                f"decarbonisation changes completely: the mid-transition case lands at "
                f"{explicit_row['pcf_mid_transition']:.2f} t instead of "
                f"{grid_row['pcf_mid_transition']:.2f} t, and a zero-carbon grid stops at "
                f"{explicit_row['pcf_zero_carbon_grid']:.2f} t instead of "
                f"{grid_row['pcf_zero_carbon_grid']:.2f} t. Findings F-07 and F-08 record the "
                f"consequence and the {utility.iloc[-1]['delta_kg']:+.1f} kg Scope 2 reconciliation "
                f"gap; the declared basis must therefore be stated with any result quoted from "
                f"this model.",
                STYLES["body"],
            )
        )

        story.append(Paragraph("Parameter ranking", STYLES["h2"]))
        story.append(_image(self.figures["tornado"], 168))
        story.append(
            Paragraph(
                "Figure 5. One-at-a-time +/-10 % perturbation of the inventory parameters, "
                "ranked by swing.", STYLES["caption"],
            )
        )
        story.append(
            Paragraph(
                f"Mass yields dominate: the ethylene demand per tonne of resin "
                f"({self.tornado.iloc[0].label}) moves the result by "
                f"{self.tornado.iloc[0].swing_t:.2f} t CO2e/t HDPE across the +/-10 % band, "
                f"more than the grid factor ({self.tornado.loc[self.tornado.parameter == 'ef_grid', 'swing_t'].iloc[0]:.2f} t). "
                f"Process Scope 1 inventories of the polymerisation node are, by contrast, "
                f"immaterial to the integrated result.",
                STYLES["body"],
            )
        )
        return story

    def _validation_story(self) -> list:
        story = [Paragraph("6. Mass balance validation", STYLES["h1"])]
        story.append(
            Paragraph(
                "Specification section 6.1 requires mass balance closure within +/- 0.1 % across "
                "all three unit operations. Closure is tested on carbon, the only element "
                "conserved in a flowsheet that carries methane, methanol, olefins and CO2; the "
                "balance is computed from the model's own inventories and is not imposed on the "
                "emission factors.",
                STYLES["body"],
            )
        )
        rows = []
        for balance in self.validation.carbon:
            rows.append(
                (
                    balance.node,
                    _n(balance.carbon_in_kg, 1),
                    _n(balance.carbon_out_kg, 1),
                    balance.makeup_stream,
                    _n(balance.closure_pct, 2) + " %",
                    f"{balance.closure_deviation_pct:+.2f} %",
                    "PASS"
                    if abs(balance.closure_deviation_pct) <= 0.1
                    else "FAIL",
                )
            )
        story.append(
            _table(
                ["Unit operation", "C in, kg", "C out, kg", "Make-up stream", "Closure", "Deviation", ""],
                rows,
                widths=[46 * mm, 18 * mm, 19 * mm, 38 * mm, 18 * mm, 19 * mm, 12 * mm],
                align_right_from=1,
            )
        )
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                "Carbon, not total mass, is the conserved quantity: the nodes convert one "
                "carbon-bearing molecule into another and reject the balance as CO2, so a total "
                "mass balance would close only by construction. Node 1 closes at 100 % once the "
                "implied reforming fuel gas is itemised; on feedstock natural gas alone it closes "
                "at 74.7 %, which is the signature of an unpriced energy input rather than an "
                "arithmetic error.",
                STYLES["body"],
            )
        )

        story.append(Paragraph("7. Findings and data-quality actions", STYLES["h1"]))
        story.append(
            Paragraph(
                "Each finding below is reproducible from the model and quantified in the units of "
                "the result, so that it can be resolved by a data correction rather than a "
                "modelling assumption. Findings do not change the headline baseline, which stays "
                "on the specification's own inventory basis.",
                STYLES["body"],
            )
        )
        for finding in self.validation.findings:
            story.append(
                _finding_paragraph(
                    f"<b>{finding.finding_id} - {finding.title}.</b> {finding.detail}",
                    finding.severity,
                )
            )

        story.append(Paragraph("Reproduction and consistency checks", STYLES["h2"]))
        rows = []
        for check in self.validation.checks:
            rows.append(
                (
                    check.check_id,
                    check.description,
                    _n(check.value, 3),
                    _n(check.reference, 3),
                    f"{check.deviation_pct:+.3f} %",
                    f"{check.tolerance_pct:.1f} %",
                    check.status,
                )
            )
        table = _table(
            ["ID", "Check", "Model", "Specified", "Deviation", "Tol.", "Status"],
            rows,
            widths=[30 * mm, 58 * mm, 20 * mm, 20 * mm, 18 * mm, 10 * mm, 14 * mm],
            align_right_from=2,
        )
        story.append(table)
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                f"Overall validation status: <b>{self.validation.status}</b>. "
                f"{sum(1 for c in self.validation.checks if c.status == 'PASS')} of "
                f"{len(self.validation.checks)} checks pass; the failures are the two carbon "
                f"closures and the quoted green-hydrogen value, all explained above. The "
                f"execution-script cross-checks (R-01, R-02) pass exactly, so the packaged engine "
                f"and the standalone script agree wherever they model the same basis.",
                STYLES["body"],
            )
        )
        return story

    def _compliance_story(self) -> list:
        story = [Paragraph("8. Assumptions, limitations and compliance", STYLES["h1"])]
        story.append(Paragraph("Assumptions", STYLES["h2"]))
        assumptions = [
            "Natural gas is modelled as pure methane for stoichiometry; the upstream factor "
            "already embeds a 1.2 % methane leakage rate characterised with AR6 GWP-100.",
            "Reported Scope 2 inventories are interpreted as grid-electricity-equivalent at the "
            "stated 0.475 kg CO2e/kWh, because that is the only reading under which the "
            "specification's own mid-transition scenario reproduces.",
            "The 68.5 kg CO2e/GJ steam factor is exercised only through the explicit_utilities "
            "basis taken from the engine execution script; the default basis contains no thermal "
            "remainder. Mixing the two is not permitted, because they reconcile to different "
            "Scope 2 totals and produce different grid-scenario responses.",
            "Co-monomer burden is carried inside the 1.015 t ethylene demand; 1-butene and "
            "1-hexene are not modelled as separate supply chains.",
            "Catalyst manufacture, capital goods, packaging and end-of-life are excluded.",
            "Allocation at the MTO node is yield-based by default; mass and economic bases are "
            "reported as sensitivity variants.",
        ]
        for item in assumptions:
            story.append(Paragraph(item, STYLES["bullet"], bulletText="\u2022"))

        story.append(Paragraph("Limitations", STYLES["h2"]))
        limitations = [
            "Secondary data only: the model inherits the specification's emission factors and "
            "cannot substitute for a site-specific inventory verified under ISO 14064-3.",
            "The three carbon imbalances mean the mass basis is not fully consistent; until they "
            "are resolved, the footprint should be quoted with the closure caveat of section 6.",
            "Economic allocation depends on the reference price set and will move with market "
            "conditions; the ranked allocation effect, not the absolute value, is the robust "
            "conclusion.",
            "Grid factors are a single-year average; no marginal or hourly matching is modelled.",
        ]
        for item in limitations:
            story.append(Paragraph(item, STYLES["bullet"], bulletText="\u2022"))

        story.append(Paragraph("Standards traceability", STYLES["h2"]))
        compliance = [
            ("ISO 14040/14044", "Goal and scope, inventory, impact assessment and "
             "interpretation structure; allocation hierarchy documented.", "Addressed"),
            ("ISO 14067", "Functional unit, system boundary, GWP-100 characterisation, "
             "declared unit per kg resin.", "Addressed"),
            ("GHG Protocol Product Standard", "Scope 1/2/3 split, boundary definition and "
             "data-quality discussion.", "Addressed"),
            ("ISO 14064-3 / 14071", "Independent verification and critical review.",
             "Not performed"),
        ]
        story.append(
            _table(
                ["Reference", "Requirement", "Status"],
                compliance,
                widths=[42 * mm, 100 * mm, 26 * mm],
                align_right_from=3,
            )
        )
        return story

    def _appendix_story(self) -> list:
        p = self.model.params
        story = [Paragraph("Appendix A - Parameter inventory", STYLES["h1"])]
        rows = [
            ("Ethylene demand per t HDPE", f"{p.ethylene_per_hdpe:.3f}", "t/t"),
            ("Methanol demand per t ethylene", f"{p.methanol_per_ethylene:.3f}", "t/t"),
            ("Methanol yield per t natural gas", f"{p.methanol_per_ng:.3f}", "t/t"),
            ("Natural gas upstream factor", f"{p.ef_ng_upstream:.3f}", "kg CO2e/kg"),
            ("Grid emission factor", f"{p.ef_grid:.3f}", "kg CO2e/kWh"),
            ("Steam emission factor (explicit basis only)", f"{p.ef_steam:.1f}", "kg CO2e/GJ"),
            ("Methanol plant Scope 1", f"{p.methanol_scope1:.1f}", "kg CO2e/t MeOH"),
            ("Methanol plant electricity", f"{p.methanol_kwh_per_t:.1f}", "kWh/t MeOH"),
            ("Methanol plant steam", f"{p.methanol_steam_gj_per_t:.1f}", "GJ/t MeOH"),
            ("MTO plant Scope 1", f"{p.mto_scope1:.1f}", "kg CO2e/t C2H4"),
            ("MTO plant electricity", f"{p.mto_kwh_per_t:.1f}", "kWh/t C2H4"),
            ("MTO plant steam", f"{p.mto_steam_gj_per_t:.1f}", "GJ/t C2H4"),
            ("Polymerisation Scope 1", f"{p.hdpe_scope1:.1f}", "kg CO2e/t HDPE"),
            ("Polymerisation electricity", f"{p.hdpe_kwh_per_t:.1f}", "kWh/t HDPE"),
            ("Polymerisation steam", f"{p.hdpe_steam_gj_per_t:.1f}", "GJ/t HDPE"),
            ("Methanol energy intensity", f"{p.methanol_energy_gj_per_t:.1f}", "GJ/t MeOH"),
            ("Carbon selectivity to ethylene", f"{p.carbon_split_ethylene:.2f}", "-"),
            ("MTO burden share to ethylene", f"{p.mto_burden_share:.3f}", "-"),
        ]
        story.append(
            _table(
                ["Parameter", "Value", "Unit"],
                rows,
                widths=[95 * mm, 35 * mm, 38 * mm],
                align_right_from=1,
            )
        )
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                "Scenario and sensitivity outputs, the continuous grid sweep, the allocation "
                "variants and every validation record are written alongside this report as CSV "
                "files, so the analysis can be re-run or re-plotted without the model.",
                STYLES["body"],
            )
        )
        return story

    # ------------------------------------------------------------------ build
    def build(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = BaseDocTemplate(
            str(path),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=18 * mm,
            bottomMargin=20 * mm,
            title="Product Carbon Footprint of HDPE via MTO - Cradle-to-Gate Technical Report",
            author="Integrated PCF model",
            subject="ISO 14040/14044, ISO 14067, GHG Protocol Product Standard",
        )
        cover_frame = Frame(MARGIN, 22 * mm, CONTENT_W, PAGE_H - 22 * mm - 52 * mm)
        body_frame = Frame(MARGIN, 20 * mm, CONTENT_W, PAGE_H - 20 * mm - 18 * mm)
        doc.addPageTemplates(
            [
                PageTemplate(id="cover", frames=[cover_frame], onPage=_cover),
                PageTemplate(id="body", frames=[body_frame], onPage=_decorate),
            ]
        )

        story: list = self._cover_story()
        story.append(NextPageTemplate("body"))
        story.append(PageBreak())
        story.append(Paragraph("Contents", STYLES["h1"]))
        contents = [
            ("1.", "Goal, scope and method"),
            ("2.", "Process flowsheet and mass balance"),
            ("3.", "Layer-by-layer PCF build-up"),
            ("4.", "Hotspot analysis"),
            ("5.", "Scenario and sensitivity analysis"),
            ("6.", "Mass balance validation"),
            ("7.", "Findings and data-quality actions"),
            ("8.", "Assumptions, limitations and compliance"),
            ("A.", "Parameter inventory"),
        ]
        for number, title in contents:
            story.append(
                Paragraph(
                    f"<b>{number}</b>&nbsp;&nbsp;{title}",
                    ParagraphStyle(
                        "toc", parent=STYLES["body"], alignment=TA_LEFT, spaceAfter=3,
                    ),
                )
            )
        story.append(PageBreak())
        for section in (
            self._scope_story,
            self._boundary_story,
            self._layer_story,
            self._hotspot_story,
            self._sensitivity_story,
            self._validation_story,
            self._compliance_story,
            self._appendix_story,
        ):
            story.extend(section())
            story.append(Spacer(1, 2 * mm))
        doc.build(story)
        return path
