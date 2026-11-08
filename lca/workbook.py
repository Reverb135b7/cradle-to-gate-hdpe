"""Excel LCI workbook and data-quality register."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from pcf.params import ModelParams

from . import declaration as d
from .documents import deliverables, quality_checks
from .results import LcaResult

HEADER_FILL = PatternFill("solid", fgColor="1F2933")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=9)
TITLE_FONT = Font(bold=True, size=13, color="1F2933")
MUTED_FONT = Font(size=9, color="5A6670")
THIN = Side(style="thin", color="D5DADE")
BORDER = Border(bottom=THIN)


def _write_frame(ws, frame: pd.DataFrame) -> None:
    ws.append(list(frame.columns))
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in frame.itertuples(index=False):
        ws.append([None if pd.isna(value) else value for value in row])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for idx, column in enumerate(frame.columns, start=1):
        longest = max(
            [len(str(column))] + [len(str(value)) for value in frame[column].head(80)]
        )
        ws.column_dimensions[get_column_letter(idx)].width = min(max(11, longest + 2), 62)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def _add_sheet(wb: Workbook, name: str, frame: pd.DataFrame):
    ws = wb.create_sheet(name[:31])
    _write_frame(ws, frame)
    return ws


def build_workbook(result: LcaResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)

    # ---------------------------------------------------------------- read me
    ws = wb.create_sheet("Read me")
    ws["A1"] = d.TITLE
    ws["A1"].font = TITLE_FONT
    rows = [
        ("Version", d.VERSION),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Functional unit", d.FUNCTIONAL_UNIT),
        ("Boundary", "Cradle-to-gate; gate at pelletising exit. No use phase or end-of-life."),
        ("Impact method", "IPCC AR6 GWP100 (kg CO2e); fossil primary energy as a screening indicator."),
        ("Allocation", "Yield-based base case; mass and economic allocation as sensitivity."),
        ("Result", f"{result.model.total_t:.4f} t CO2e per t HDPE ({result.model.total_per_kg_resin:.4f} kg CO2e/kg)"),
        ("Validation", f"{result.validation.status}: {sum(1 for c in result.validation.checks if c.status == 'PASS')} of "
                        f"{len(result.validation.checks)} checks pass"),
        ("Data status", "Secondary data only; no site measurements; no background database linked."),
        ("Licence note", "All factors are traceable to the project's technical specification (source keys S1-S9)."),
    ]
    for i, (key, value) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=key).font = Font(bold=True, size=9)
        ws.cell(row=i, column=2, value=value).font = MUTED_FONT
        ws.cell(row=i, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 105

    # ------------------------------------------------------------- goal/scope
    goal = pd.DataFrame(
        [
            ("Goal", d.DECISION),
            ("Audience", d.AUDIENCE),
            ("Product", d.PRODUCT),
            ("Functional unit", d.FUNCTIONAL_UNIT),
            ("Declared unit", d.DECLARED_UNIT),
            ("Boundary", "Cradle-to-gate; raw material extraction through pelletising. Gate = pelletising exit."),
            ("Allocation", d.ALLOCATION),
            ("Method", d.METHOD),
            ("Geography", d.GEOGRAPHY),
            ("Period", d.REFERENCE_PERIOD),
            ("Cut-off", d.CUT_OFF),
            ("Software", d.SOFTWARE),
            ("Standards", d.STANDARDS),
        ],
        columns=["item", "statement"],
    )
    _add_sheet(wb, "Goal and scope", goal)

    # -------------------------------------------------------------------- LCI
    _add_sheet(wb, "LCI", result.flows)
    _add_sheet(wb, "Stages", result.stages)
    _add_sheet(wb, "Data quality", result.dqi)
    _add_sheet(wb, "Sources", result.sources)
    _add_sheet(wb, "Completeness", result.completeness)

    params = pd.DataFrame(
        [(f.name, getattr(result.model.params, f.name)) for f in fields(ModelParams)],
        columns=["parameter", "value"],
    )
    _add_sheet(wb, "Parameters", params)

    # ----------------------------------------------------------------- impact
    _add_sheet(wb, "Impact", result.impact_table)
    _add_sheet(wb, "Categories", result.categories)
    _add_sheet(wb, "Contribution", result.contribution)

    # ------------------------------------------------------------- sensitivity
    _add_sheet(wb, "Sensitivity", result.sensitivity)
    _add_sheet(wb, "Reconciliation", result.reconciliation)

    summary = pd.DataFrame([result.evidence_summary, result.screening_summary])
    _add_sheet(wb, "Uncertainty", summary)
    _add_sheet(wb, "Scenarios", result.scenarios)

    # --------------------------------------------------------- checks & index
    _add_sheet(wb, "Quality checks", quality_checks(result))
    _add_sheet(wb, "Deliverables", deliverables(result))

    wb.save(path)
    return path


def write_data_quality_register(result: LcaResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    register = result.dqi.merge(
        result.flows[["flow_id", "quantity", "unit", "source_id", "data_type", "period"]],
        on="flow_id",
        how="left",
    )
    register.to_csv(path, index=False)
    return path
