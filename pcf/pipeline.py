"""End-to-end pipeline: model -> validation -> sensitivity -> figures -> report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

import pandas as pd

from . import charts
from .allocation import allocation_frame
from .model import PCFModel
from .params import ModelParams
from .report import PCFReport
from .sensitivity import grid_sweep, run_all_scenarios, run_scenarios, tornado
from .utility_basis import basis_comparison, utility_frame
from .validation import ValidationReport, validate


@dataclass
class PipelineResult:
    """Everything one run of the model produces."""

    model: PCFModel
    validation: ValidationReport
    scenarios: pd.DataFrame
    allocation: pd.DataFrame
    sweep: pd.DataFrame
    tornado: pd.DataFrame
    figures: Dict[str, Path] = field(default_factory=dict)
    report_path: Path | None = None
    data_paths: Dict[str, Path] = field(default_factory=dict)

    @property
    def total_t(self) -> float:
        return self.model.total_t


def run(
    outdir: Path | str = "outputs",
    params: ModelParams | None = None,
    make_report: bool = True,
    make_figures: bool = True,
) -> PipelineResult:
    """Run the full analysis and write figures, CSV data and the PDF report."""
    outdir = Path(outdir)
    figure_dir = outdir / "figures"
    data_dir = outdir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    model = PCFModel(params)
    validation = validate(model)
    scenarios = run_all_scenarios(model.params)
    allocation = allocation_frame(model.params)
    sweep = grid_sweep(model.params)
    tornado_frame = tornado(model.params)

    figures: Dict[str, Path] = {}
    if make_figures:
        figures = charts.build_all(model, figure_dir, sweep, run_scenarios(model.params), tornado_frame)

    data_paths = {
        "hotspots": _write(model.hotspot_frame(), data_dir / "hotspots.csv"),
        "layers": _write(model.layer_frame(), data_dir / "layers.csv"),
        "mass_balance": _write(model.mass_flow_frame(), data_dir / "mass_balance.csv"),
        "scenarios": _write(scenarios, data_dir / "scenarios.csv"),
        "allocation": _write(allocation, data_dir / "allocation.csv"),
        "grid_sweep": _write(sweep, data_dir / "grid_sweep.csv"),
        "tornado": _write(tornado_frame, data_dir / "tornado.csv"),
        "utility_basis": _write(utility_frame(model.params), data_dir / "utility_basis.csv"),
        "basis_comparison": _write(
            basis_comparison(model.params), data_dir / "basis_comparison.csv"
        ),
        "validation_checks": _write(validation.check_frame(), data_dir / "validation_checks.csv"),
        "carbon_balance": _write(validation.carbon_frame(), data_dir / "carbon_balance.csv"),
        "findings": _write(
            pd.DataFrame(
                [
                    {
                        "id": f.finding_id,
                        "severity": f.severity,
                        "title": f.title,
                        "detail": f.detail,
                        "impact_kg_co2e": f.impact_kg_co2e,
                    }
                    for f in validation.findings
                ]
            ),
            data_dir / "findings.csv",
        ),
    }

    report_path = None
    if make_report:
        if not figures:
            figures = charts.build_all(
                model, figure_dir, sweep, run_scenarios(model.params), tornado_frame
            )
        report = PCFReport(
            model=model,
            validation=validation,
            figures=figures,
            scenarios=scenarios,
            sweep=sweep,
            tornado_frame=tornado_frame,
            allocation=allocation,
        )
        report_path = report.build(outdir / "HDPE_PCF_cradle_to_gate_report.pdf")

    return PipelineResult(
        model=model,
        validation=validation,
        scenarios=scenarios,
        allocation=allocation,
        sweep=sweep,
        tornado=tornado_frame,
        figures=figures,
        report_path=report_path,
        data_paths=data_paths,
    )


def _write(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path
