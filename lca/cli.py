"""Command line: ``python -m lca`` builds the full deliverable set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from pcf.params import ModelParams

from . import declaration as d
from .build import build_result
from .deck import build_deck
from .documents import deliverables, quality_checks, write_goal_scope
from .openlca import write_openlca
from .report import build_report
from .results import LcaResult
from .workbook import build_workbook, write_data_quality_register


def _json_payload(result: LcaResult) -> dict[str, Any]:
    return {
        "study": {
            "title": d.TITLE,
            "version": d.VERSION,
            "functional_unit": d.FUNCTIONAL_UNIT,
            "boundary": "cradle-to-gate",
            "method": "IPCC AR6 GWP100; fossil primary energy screening indicator",
            "allocation": "yield-based base case; mass and economic allocation sensitivity",
        },
        "result": {
            "gwp_kg_co2e": result.model.total_kg,
            "gwp_t_co2e_per_t": result.model.total_t,
            "gwp_kg_co2e_per_kg": result.model.total_per_kg_resin,
            "primary_energy_mj": result.impact.energy_mj,
            "primary_energy_gj_per_t": result.impact.energy_mj / 1000.0,
        },
        "contribution": result.contribution.to_dict(orient="records"),
        "impact_categories": result.categories.to_dict(orient="records"),
        "sensitivity": result.sensitivity.to_dict(orient="records"),
        "uncertainty": {
            "evidence": result.evidence_summary,
            "screening": result.screening_summary,
        },
        "scenarios": result.scenarios.to_dict(orient="records"),
        "validation": {
            "status": result.validation.status,
            "checks": len(result.validation.checks),
            "failed": [
                c.description for c in result.validation.checks if c.status == "FAIL"
            ],
            "findings": len(result.validation.findings),
        },
        "quality_checks": quality_checks(result).to_dict(orient="records"),
    }


def _write(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def build_all(
    outdir: Path | str = "outputs/LCA",
    draws: int = 20000,
    seed: int = 42,
    make_report: bool = True,
    make_deck: bool = True,
) -> LcaResult:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    result = build_result(params=ModelParams(), draws=draws, seed=seed,
                          figure_dir=outdir / "figures")

    paths = result.paths
    paths["goal_scope"] = write_goal_scope(result, outdir / "LCA_goal_and_scope.md")
    paths["impact_csv"] = _write(result.impact_table, outdir / "LCA_impact_assessment.csv")
    paths["flows_csv"] = _write(result.flows, outdir / "LCA_inventory_flows.csv")
    paths["completeness_csv"] = _write(result.completeness, outdir / "LCA_completeness.csv")
    paths["sensitivity_csv"] = _write(result.sensitivity, outdir / "LCA_sensitivity.csv")
    paths["scenarios_csv"] = _write(result.scenarios, outdir / "LCA_scenarios.csv")
    paths["register_csv"] = write_data_quality_register(
        result, outdir / "LCA_data_quality_register.csv"
    )
    paths["uncertainty_csv"] = _write(
        pd.DataFrame([result.evidence_summary, result.screening_summary]),
        outdir / "LCA_uncertainty.csv",
    )

    payload = _json_payload(result)
    paths["impact_json"] = outdir / "LCA_impact_assessment.json"
    paths["impact_json"].write_text(json.dumps(payload, indent=2, default=float), encoding="utf-8")

    paths["workbook"] = build_workbook(result, outdir / "LCA_inventory.xlsx")
    paths["openlca"] = write_openlca(result, outdir / "openlca")["readme"]

    if make_report:
        paths["report"] = build_report(result, outdir / "LCA_report.pdf")
    if make_deck:
        paths["deck"] = build_deck(result, outdir / "LCA_presentation.pptx")

    # deliverables index written last so it can list what exists
    rows = deliverables(result)
    lines = [
        f"# {d.TITLE}",
        "",
        f"Generated {pd.Timestamp.now():%Y-%m-%d %H:%M}  ·  version {d.VERSION}",
        "",
        f"**Result:** {result.model.total_t:.3f} t CO2e per t HDPE, "
        f"{result.impact.energy_mj / 1000:,.0f} GJ fossil primary energy per t.",
        "",
        "| Deliverable | Path | Status | Note |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows.itertuples():
        lines.append(f"| {row.deliverable} | `{row.path}` | {row.status} | {row.note} |")
    lines += [
        "",
        "Regenerate with `python -m lca`.",
    ]
    paths["index"] = outdir / "LCA_deliverables.md"
    paths["index"].write_text("\n".join(lines) + "\n", encoding="utf-8")

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lca", description="Build the cradle-to-gate HDPE LCA deliverable set"
    )
    parser.add_argument("--outdir", default="outputs/LCA", help="output directory")
    parser.add_argument("--draws", type=int, default=20000, help="Monte Carlo draws per run")
    parser.add_argument("--seed", type=int, default=42, help="Monte Carlo seed")
    parser.add_argument("--no-report", action="store_true", help="skip the PDF report")
    parser.add_argument("--no-deck", action="store_true", help="skip the presentation")
    args = parser.parse_args(argv)

    result = build_all(
        outdir=args.outdir,
        draws=args.draws,
        seed=args.seed,
        make_report=not args.no_report,
        make_deck=not args.no_deck,
    )
    outdir = Path(args.outdir)
    print(f"LCA built in {outdir}")
    print(f"  {result.model.total_t:.4f} t CO2e / t HDPE  |  "
          f"{result.impact.energy_mj / 1000:,.1f} GJ / t  |  "
          f"validation {result.validation.status}")
    for key in (
        "report", "workbook", "goal_scope", "register_csv", "impact_csv",
        "impact_json", "index",
    ):
        if key in result.paths:
            print(f"  {result.paths[key]}")
    return 0
