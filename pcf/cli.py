"""Command-line interface: ``python -m pcf``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import PCFModel
from .params import SCENARIOS, ModelParams
from .pipeline import run
from .utility_basis import basis_params
from .validation import validate


def _console_summary(model: PCFModel) -> str:
    flows = model.flows
    scopes = model.scope_totals()
    lines = [
        "Integrated cradle-to-gate PCF - NG -> MeOH -> MTO -> HDPE",
        "-" * 66,
        f"Functional unit     : {flows.hdpe_t:.2f} t HDPE resin",
        f"Natural gas demand  : {flows.natural_gas_t:.3f} t",
        f"Methanol demand     : {flows.methanol_t:.3f} t",
        f"Ethylene demand     : {flows.ethylene_t:.3f} t",
        f"Primary energy      : {flows.energy_gj:.1f} GJ",
        "",
        f"Scope 1             : {scopes['scope1']:>10,.1f} kg CO2e",
        f"Scope 2             : {scopes['scope2']:>10,.1f} kg CO2e",
        f"Scope 3 (upstream)  : {scopes['scope3']:>10,.1f} kg CO2e",
        f"TOTAL               : {scopes['total']:>10,.1f} kg CO2e",
        f"                      {model.total_t:>10.3f} t CO2e / t HDPE",
        f"                      {model.total_per_kg_resin:>10.3f} kg CO2e / kg resin",
        "",
        "Stage shares:",
    ]
    for row in model.hotspot_frame().itertuples():
        lines.append(
            f"  {row.stage:<42s} {row.total_kg:>9,.0f} kg  ({row.share_pct:4.1f} %)"
        )
    lines.append("")
    lines.append("Scenarios:")
    for scenario in SCENARIOS:
        value = PCFModel(scenario.params(model.params)).total_t
        reference = (
            f"  spec {scenario.spec_reference_t:.2f}"
            if scenario.spec_reference_t is not None
            else ""
        )
        lines.append(f"  {scenario.key:<18s} {value:>7.3f} t CO2e/t HDPE{reference}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pcf",
        description=(
            "Integrated cradle-to-gate product carbon footprint model for HDPE via "
            "the methanol-to-olefins pathway."
        ),
    )
    parser.add_argument(
        "-o", "--outdir", default="outputs", help="output directory (default: outputs)"
    )
    parser.add_argument(
        "--no-report", action="store_true", help="skip PDF report generation"
    )
    parser.add_argument(
        "--no-figures", action="store_true", help="skip figure generation"
    )
    parser.add_argument(
        "--json", action="store_true", help="print the summary as JSON and exit"
    )
    parser.add_argument(
        "--ef-grid",
        type=float,
        default=None,
        help="override the grid emission factor, kg CO2e/kWh",
    )
    parser.add_argument(
        "--ef-ng-upstream",
        type=float,
        default=None,
        help="override the natural gas upstream factor, kg CO2e/kg",
    )
    parser.add_argument(
        "--utility-basis",
        choices=("grid_equivalent", "explicit_utilities"),
        default="grid_equivalent",
        help=(
            "Scope 2 decomposition basis: grid-electricity equivalent (default) or the "
            "electricity + steam split of the engine execution script"
        ),
    )
    args = parser.parse_args(argv)

    overrides = {
        key: value
        for key, value in (
            ("ef_grid", args.ef_grid),
            ("ef_ng_upstream", args.ef_ng_upstream),
        )
        if value is not None
    }
    params = basis_params(args.utility_basis).with_overrides(**overrides)
    model = PCFModel(params)

    if args.json:
        scopes = model.scope_totals()
        print(
            json.dumps(
                {
                    "functional_unit_t": params.functional_unit_t,
                    "total_t_co2e_per_t_hdpe": round(model.total_t, 4),
                    "total_kg_co2e": round(scopes["total"], 2),
                    "scope1_kg": round(scopes["scope1"], 2),
                    "scope2_kg": round(scopes["scope2"], 2),
                    "scope3_kg": round(scopes["scope3"], 2),
                    "validation_status": validate(model).status,
                    "parameters": {
                        "ef_grid": params.ef_grid,
                        "ef_ng_upstream": params.ef_ng_upstream,
                    },
                },
                indent=2,
            )
        )
        return 0

    print(_console_summary(model))
    if args.utility_basis != "grid_equivalent":
        print(f"\nUtility basis      : {args.utility_basis}")
    result = run(
        outdir=Path(args.outdir),
        params=params,
        make_report=not args.no_report,
        make_figures=not args.no_figures,
    )
    print()
    print(f"Validation status   : {result.validation.status}")
    for finding in result.validation.findings:
        print(f"  [{finding.severity}] {finding.finding_id} {finding.title}")
    print()
    print(f"Outputs written to  : {Path(args.outdir).resolve()}")
    if result.report_path:
        print(f"  report            : {result.report_path}")
    for key, path in result.figures.items():
        print(f"  figure ({key:12s}): {path}")
    for key, path in result.data_paths.items():
        print(f"  data   ({key:19s}): {path}")
    return 0
