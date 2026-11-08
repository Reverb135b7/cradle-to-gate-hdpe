"""Twelve-slide presentation summary (python-pptx)."""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from . import declaration as d
from .documents import quality_checks
from .results import LcaResult

INK = RGBColor(0x20, 0x26, 0x2B)
MUTED = RGBColor(0x6B, 0x73, 0x78)
ACCENT = RGBColor(0x8C, 0x6D, 0x1F)
BAND = RGBColor(0xF2, 0xF4, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RULE = RGBColor(0xC8, 0xCE, 0xD4)

W, H = 13.333, 7.5


def _text(slide, x, y, w, h, text, size=14, bold=False, colour=INK, align=PP_ALIGN.LEFT,
          italic=False, spacing=1.0):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        run = p.add_run()
        run.text = line
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = colour
        run.font.name = "Segoe UI"
    return box


def _bullets(slide, x, y, w, h, items, size=13, colour=INK):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(7)
        p.line_spacing = 1.05
        run = p.add_run()
        run.text = "\u2022  " + item
        run.font.size = Pt(size)
        run.font.color.rgb = colour
        run.font.name = "Segoe UI"
    return box


def _card(slide, x, y, w, h, value, label):
    shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = BAND
    shape.line.color.rgb = RULE
    shape.line.width = Pt(0.75)
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.16)
    tf.margin_top = Inches(0.12)
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = value
    run.font.size = Pt(24)
    run.font.bold = True
    run.font.color.rgb = INK
    run.font.name = "Segoe UI"
    p2 = tf.add_paragraph()
    run2 = p2.add_run()
    run2.text = label
    run2.font.size = Pt(9)
    run2.font.color.rgb = MUTED
    run2.font.name = "Segoe UI"


def _header(slide, kicker, title):
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(W), Inches(0.09))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    _text(slide, 0.7, 0.42, 11.8, 0.3, kicker.upper(), size=10, bold=True, colour=MUTED)
    _text(slide, 0.7, 0.72, 11.9, 0.7, title, size=26, bold=True, colour=INK)


def build_deck(result: LcaResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)
    blank = prs.slide_layouts[6]

    model = result.model
    impact = result.impact
    gwp = model.total_t
    contrib = result.contribution.set_index("stage_key")
    shares = {k: float(contrib.loc[k, "gwp_share_pct"]) for k in contrib.index if k != "total"}
    gwp_stage = {k: float(contrib.loc[k, "gwp_kg_co2e"]) for k in contrib.index if k != "total"}
    scen = result.scenarios.set_index("scenario")
    zero = float(scen.loc["renewable_grid", "pcf_t"])
    green = float(scen.loc["green_h2_syngas", "pcf_t"])
    mto_own = model.flows.ethylene_t * model.params.mto_scope1 * model.params.mto_burden_share
    checks = quality_checks(result)
    met = int((checks["status"] == "Met").sum())
    partial = int((checks["status"] == "Partial").sum())
    unmet = int((checks["status"] == "Not met").sum())

    # 1 cover
    s = prs.slides.add_slide(blank)
    spine = s.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.22), Inches(H))
    spine.fill.solid()
    spine.fill.fore_color.rgb = ACCENT
    spine.line.fill.background()
    _text(s, 0.9, 0.9, 11.5, 0.4, "INDUSTRIAL LIFE-CYCLE ASSESSMENT", size=11, bold=True, colour=MUTED)
    _text(s, 0.9, 1.45, 11.6, 1.9, "HDPE via methanol-to-olefins\ncradle-to-gate LCA", size=40, bold=True)
    _text(s, 0.9, 3.35, 11.4, 1.0,
          "Functional unit 1,000 kg resin at the gate  ·  IPCC AR6 GWP100  ·  secondary-data screening study",
          size=15, colour=MUTED)
    _card(s, 0.9, 4.45, 2.85, 1.35, f"{gwp:.2f} t", "CO2e per t HDPE")
    _card(s, 3.95, 4.45, 2.85, 1.35, f"{impact.energy_mj / 1000:,.0f} GJ", "fossil primary energy")
    _card(s, 7.0, 4.45, 2.85, 1.35, f"{shares['methanol']:.0f} %", "from methanol synthesis")
    _card(s, 10.05, 4.45, 2.4, 1.35, f"{zero:.2f} t", "zero-carbon grid")
    _text(s, 0.9, 6.35, 11.5, 0.4, f"Version {d.VERSION}  ·  internal technical review  ·  not critically reviewed",
          size=10, colour=MUTED)

    # 2 goal
    s = prs.slides.add_slide(blank)
    _header(s, "01  Goal and scope", "The decision this study informs")
    _text(s, 0.7, 1.65, 5.6, 0.35, "DECISION", size=11, bold=True, colour=ACCENT)
    _text(s, 0.7, 2.0, 5.9, 2.1, d.DECISION, size=14)
    _text(s, 0.7, 4.25, 5.6, 0.35, "AUDIENCE", size=11, bold=True, colour=ACCENT)
    _text(s, 0.7, 4.6, 5.9, 1.5, d.AUDIENCE, size=13, colour=MUTED)
    _text(s, 6.95, 1.65, 5.6, 0.35, "BOUNDARY", size=11, bold=True, colour=ACCENT)
    _bullets(s, 6.95, 2.0, 5.7, 2.0, [
        "Cradle-to-gate: gas extraction through pelletising",
        "Scope 1 direct, Scope 2 grid, Scope 3.1 upstream gas",
        "Gate at pelletising exit; ex-works resin",
        "Use phase and end-of-life are outside the claim",
    ], size=13)
    _text(s, 6.95, 4.25, 5.6, 0.35, "WHAT IT IS NOT", size=11, bold=True, colour=ACCENT)
    _bullets(s, 6.95, 4.6, 5.7, 1.6, [
        "Not cradle-to-grave",
        "Not site-measured - secondary data only",
        "Not multi-category beyond climate change",
    ], size=13, colour=MUTED)

    # 3 boundary diagram
    s = prs.slides.add_slide(blank)
    _header(s, "02  System boundary", "Functional unit and process chain")
    s.shapes.add_picture(str(result.figures["boundary"]), Inches(1.35), Inches(1.5), width=Inches(10.6))
    _text(s, 0.7, 6.65, 11.8, 0.4,
          "Excluded modules are shown outside the boundary and are not part of the 6.07 t result.",
          size=10, colour=MUTED, italic=True)

    # 4 method
    s = prs.slides.add_slide(blank)
    _header(s, "03  Method", "One category quantified, the rest declared")
    _bullets(s, 0.7, 1.7, 6.0, 3.4, [
        "GWP100 on IPCC AR6, kg CO2e - quantified",
        "Fossil primary energy - screening indicator, 9.0 MJ/kWh",
        "No normalisation, weighting or single score",
        "Eight further categories declared but not quantified",
        "Reason: inventory carries aggregated CO2e, not species",
    ], size=14)
    rows = [
        ("Climate change", "Quantified", "6.07 t CO2e"),
        ("Acidification", "Not quantified", "no SO2 / NOx / NH3"),
        ("Eutrophication", "Not quantified", "no P / N species"),
        ("Photochemical ozone", "Not quantified", "no NMVOC / NOx"),
        ("Particulate matter", "Not quantified", "no PM speciation"),
        ("Water scarcity", "Not quantified", "no water inventory"),
    ]
    top = 1.85
    for i, (cat, status, note) in enumerate(rows):
        y = top + i * 0.72
        _text(s, 7.0, y, 2.5, 0.3, cat, size=12, bold=True)
        colour = ACCENT if status == "Quantified" else MUTED
        _text(s, 9.35, y, 1.65, 0.3, status, size=10, bold=True, colour=colour)
        _text(s, 10.95, y, 2.0, 0.3, note, size=9.5, colour=MUTED)

    # 5 result
    s = prs.slides.add_slide(blank)
    _header(s, "04  Result", "Methanol synthesis dominates the cradle-to-gate burden")
    s.shapes.add_picture(str(result.figures["gwp"]), Inches(0.55), Inches(1.7), width=Inches(8.4))
    _text(s, 9.25, 1.9, 3.6, 0.35, "BY STAGE", size=11, bold=True, colour=ACCENT)
    for i, key in enumerate(("methanol", "mto", "ng_extraction", "hdpe")):
        label = {
            "methanol": "Methanol synthesis",
            "mto": "MTO & separation",
            "ng_extraction": "NG extraction",
            "hdpe": "Polymerisation",
        }[key]
        y = 2.35 + i * 0.86
        _text(s, 9.25, y, 2.3, 0.3, label, size=12)
        _text(s, 11.6, y, 1.0, 0.3, f"{shares[key]:.1f} %", size=13, bold=True, align=PP_ALIGN.RIGHT)
        _text(s, 9.25, y + 0.28, 2.2, 0.3, f"{gwp_stage[key]:,.0f} kg CO2e", size=9.5, colour=MUTED)
    _text(s, 9.25, 5.95, 3.4, 0.8,
          "Methanol carries three times its own burden because 2.99 t of it are needed per t of resin.",
          size=10.5, colour=MUTED, italic=True)

    # 6 why
    s = prs.slides.add_slide(blank)
    _header(s, "05  Interpretation", "Why the hotspot sits where it does")
    _bullets(s, 0.7, 1.8, 6.1, 4.0, [
        "2.99 t methanol per t resin - a 3x mass multiplier",
        "Reforming is the most carbon-intensive node: 610 kg/t direct",
        "Its Scope 2 adds another 570 kg/t at the base grid",
        "MTO adds 975 kg/t on 1.02 t of ethylene",
        "Polymerisation is small: 125 kg/t direct plus 315 kg/t power",
    ], size=14)
    _text(s, 7.1, 1.85, 5.5, 0.35, "ROBUST VS CONDITIONAL", size=11, bold=True, colour=ACCENT)
    _text(s, 7.1, 2.25, 5.4, 1.5,
          "Robust: methanol is the largest stage under every inventory, allocation and factor variant tested, "
          "never below 55 %.", size=12.5)
    _text(s, 7.1, 3.85, 5.4, 1.5,
          "Conditional: with green hydrogen syngas the methanol stage disappears and MTO regeneration "
          f"becomes {100 * mto_own / (green * 1000):.0f} % of what remains.", size=12.5, colour=MUTED)
    _text(s, 7.1, 5.5, 5.4, 0.9,
          "Not supported: any ranking on acidification, eutrophication, ozone, PM, water or land.",
          size=12.5, colour=MUTED, italic=True)

    # 7 abatement
    s = prs.slides.add_slide(blank)
    _header(s, "06  Abatement", "Grid first, then the reformer")
    _card(s, 0.8, 1.85, 2.7, 1.35, "6.07 t", "base case")
    _card(s, 3.75, 1.85, 2.7, 1.35, "3.55 t", "zero-carbon grid (-41 %)")
    _card(s, 6.7, 1.85, 2.7, 1.35, "1.11 t", "green H2 syngas (-82 %)")
    _card(s, 9.65, 1.85, 2.7, 1.35, "5.21 t", "mass allocation (-14 %)")
    _text(s, 0.8, 3.6, 11.8, 0.35, "THE LADDER IS AN ORDERING, NOT A SUM", size=11, bold=True, colour=ACCENT)
    _bullets(s, 0.8, 3.95, 11.4, 2.4, [
        "Grid decarbonisation is the single largest lever: 2,514 kg CO2e, 41 % of the total.",
        "Removing reformer Scope 1 is the second: 1,826 kg CO2e.",
        "MTO regeneration is the third: 990 kg CO2e, and it becomes the residual hotspot under green syngas.",
        "The levers interact: a green-syngas retrofit also changes the methanol plant's fuel use, which this model does not re-engineer.",
    ], size=13)
    _text(s, 0.8, 6.45, 11.4, 0.4,
          "Economic allocation gives 5.31 t; the utility-basis variant changes the response to grid decarbonisation, not the base total.",
          size=10, colour=MUTED, italic=True)

    # 8 sensitivity
    s = prs.slides.add_slide(blank)
    _header(s, "07  Sensitivity", "Decisions move the result; inventory noise does not")
    s.shapes.add_picture(str(result.figures["tornado"]), Inches(0.55), Inches(1.65), width=Inches(9.3))
    _text(s, 10.15, 1.95, 2.8, 0.35, "RANGE PROVENANCE", size=9.5, bold=True, colour=ACCENT)
    for i, (label, text) in enumerate((
        ("Evidence", "constrained by carbon balance"),
        ("Scenario", "grid decision variable"),
        ("Method", "allocation choice"),
        ("Judgement", "analyst bracket, not measured"),
    )):
        _text(s, 10.15, 2.35 + i * 0.9, 2.8, 0.3, label, size=11, bold=True)
        _text(s, 10.15, 2.63 + i * 0.9, 2.8, 0.5, text, size=9, colour=MUTED)

    # 9 uncertainty
    s = prs.slides.add_slide(blank)
    _header(s, "08  Uncertainty", "Reconciling the inventory changes it by 1 %")
    s.shapes.add_picture(str(result.figures["uncertainty"]), Inches(0.55), Inches(1.7), width=Inches(9.6))
    ev = result.evidence_summary
    _text(s, 10.4, 1.95, 2.6, 0.35, "EVIDENCE-ONLY", size=9.5, bold=True, colour=ACCENT)
    _text(s, 10.4, 2.3, 2.6, 1.3,
          f"P5 {ev['p05_t']:.3f}\nP50 {ev['p50_t']:.3f}\nP95 {ev['p95_t']:.3f}\nSD {ev['sd_t']:.3f}",
          size=12)
    _text(s, 10.4, 3.95, 2.6, 0.35, "SCREENING", size=9.5, bold=True, colour=ACCENT)
    _text(s, 10.4, 4.3, 2.6, 1.3,
          f"P5 {result.screening_summary['p05_t']:.3f}\nP50 {result.screening_summary['p50_t']:.3f}\n"
          f"P95 {result.screening_summary['p95_t']:.3f}", size=12)
    _text(s, 10.4, 5.8, 2.7, 1.0,
          "Compare with 3.55-6.07 t from the grid scenario.", size=10, colour=MUTED, italic=True)

    # 10 scenarios
    s = prs.slides.add_slide(blank)
    _header(s, "09  Scenarios", "Grid and technology choices dominate the envelope")
    s.shapes.add_picture(str(result.figures["scenarios"]), Inches(0.55), Inches(1.65), width=Inches(9.2))
    _text(s, 9.95, 2.0, 3.0, 0.35, "THE SPREAD", size=9.5, bold=True, colour=ACCENT)
    _text(s, 9.95, 2.4, 3.0, 0.6, "3.55 - 6.07 t", size=24, bold=True)
    _text(s, 9.95, 3.05, 3.0, 1.0, "for grid decarbonisation alone, with the process chain unchanged.",
          size=10.5, colour=MUTED)
    _text(s, 9.95, 4.3, 3.0, 0.35, "ALLOCATION", size=9.5, bold=True, colour=ACCENT)
    _text(s, 9.95, 4.65, 3.0, 1.2, "Mass 5.21 t\nEconomic 5.31 t\nBase 6.07 t", size=11)

    # 11 quality
    s = prs.slides.add_slide(blank)
    _header(s, "10  Quality and gaps", "What the evidence cannot support")
    _text(s, 0.7, 1.7, 5.8, 0.35, "COMPLETENESS", size=11, bold=True, colour=ACCENT)
    _bullets(s, 0.7, 2.05, 5.9, 3.6, [
        "Co-monomer supply: 0.4-0.6 % if proxied - proxy flagged, not used",
        "Catalysts, water, wastewater, waste: no quantities at all",
        "Packaging, transport, use, end-of-life: outside the boundary",
        "Non-GWP categories: blocked by aggregated CO2e inventory",
    ], size=12.5)
    _text(s, 7.0, 1.7, 5.6, 0.35, "ACCEPTANCE CHECKS", size=11, bold=True, colour=ACCENT)
    _text(s, 7.0, 2.05, 5.6, 0.7, f"{met} met  ·  {partial} partial  ·  {unmet} not met", size=20, bold=True)
    _bullets(s, 7.0, 2.95, 5.7, 3.0, [
        "Functional unit, boundary, units and sources: met",
        "Database version and multi-category coverage: partial",
        "openLCA model rebuilt: total matched; critical review: not met",
    ], size=12.5, colour=MUTED)

    # 12 close
    s = prs.slides.add_slide(blank)
    _header(s, "11  Conclusions", "What to do with this result")
    _bullets(s, 0.7, 1.8, 7.2, 4.2, [
        "Treat methanol synthesis and reforming as the primary abatement target.",
        "Decarbonise electricity first: it is the largest single lever, worth 41 %.",
        "Do not quote a single footprint without its grid, allocation and utility basis.",
        "Close the carbon-balance inconsistency before external publication: it is worth +0.9 %, not nothing.",
        "Collect species-level emissions and water data before claiming a multi-category LCA.",
    ], size=14)
    _text(s, 8.2, 1.85, 4.4, 0.35, "DELIVERABLES", size=11, bold=True, colour=ACCENT)
    _text(s, 8.2, 2.25, 4.4, 3.6,
          "LCA_report.pdf\nLCA_inventory.xlsx\nLCA_goal_and_scope.md\nLCA_data_quality_register.csv\n"
          "LCA_impact_assessment.csv / .json\nfigures/ (6)\nopenLCA model and run\nthis deck",
          size=11, colour=MUTED, spacing=1.35)
    _text(s, 8.2, 6.1, 4.4, 0.6, "Reproduce: python -m lca", size=11, bold=True)

    prs.save(path)
    return path
