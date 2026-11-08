"""Data layer for the LCA console (:mod:`app` served at ``/lca``).

The console is a reader over one complete :class:`lca.results.LcaResult`, built
from the same package that writes ``outputs/LCA``.  Nothing is transcribed: the
functional unit comes from :mod:`lca.declaration`, the inventory from
:mod:`lca.inventory`, the uncertainty summaries from :mod:`lca.uncertainty`, and
the acceptance checks from :mod:`lca.documents`.

Serialisation is deliberately lossy where volume would be: the 20,000-draw
Monte Carlo runs are reduced to summaries plus a histogram, because the browser
never needs the raw draws.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from lca import declaration as d
from lca.build import build_result
from lca.documents import deliverables, quality_checks
from lca.ledger import read_ledger
from lca.results import LcaResult
from lca.openlca import characterisation_coverage, elementary_flows_frame
from pcf.params import ModelParams, _FIELDS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LCA_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "LCA"
OPENLCA_RESULT = LCA_OUTPUT_DIR / "openlca" / "openlca_run.json"

#: draws used for the console; matches the study report
CONSOLE_DRAWS = 20000

_CACHE: Dict[str, Any] = {}


# --------------------------------------------------------------------- helpers
def _json(frame: pd.DataFrame) -> List[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records"))


def _f(value: Any, digits: int = 6) -> float:
    """JSON-safe rounded float."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not np.isfinite(number):
        return 0.0
    return round(number, digits)


def _histogram(draws: pd.DataFrame, bins: int = 34) -> dict[str, list[float]]:
    values = draws["total_t"].to_numpy(dtype=float)
    counts, edges = np.histogram(values, bins=bins)
    return {
        "edges": [_f(edge, 5) for edge in edges],
        "counts": [int(count) for count in counts],
    }


def _summary(summary: dict[str, Any]) -> dict[str, Any]:
    keep = ("label", "n", "mean_t", "sd_t", "p05_t", "p50_t", "p95_t", "min_t", "max_t")
    return {key: (_f(summary[key], 5) if key != "label" else summary[key]) for key in keep if key in summary}


def _mass_balances(result: LcaResult) -> dict[str, float]:
    flows = result.model.flows
    return {
        "ng_t": _f(flows.natural_gas_t),
        "methanol_t": _f(flows.methanol_t),
        "ethylene_t": _f(flows.ethylene_t),
        "hdpe_t": _f(flows.hdpe_t),
        "comonomer_t": _f(flows.comonomer_t),
        "electricity_kwh": _f(sum(result.stages["electricity_kwh"])),
        "declared_fuel_gj": _f(sum(result.stages["declared_fuel_gj"])),
    }


ALLOWED_PRIMARY_OVERRIDES = frozenset({
    # functional unit and chain stoichiometry
    "functional_unit_t",
    "ethylene_per_hdpe",
    "methanol_per_ethylene",
    "methanol_per_ng",
    "comonomer_wt_fraction",
    # primary emission factors
    "ef_ng_upstream",
    "ef_grid",
    "ef_steam",
    # scope 1 direct emissions, kg CO2e per t node product
    "methanol_scope1",
    "mto_scope1",
    "hdpe_scope1",
    # scope 2 demand: electricity + steam per t node product
    "methanol_kwh_per_t",
    "methanol_steam_gj_per_t",
    "mto_kwh_per_t",
    "mto_steam_gj_per_t",
    "hdpe_kwh_per_t",
    "hdpe_steam_gj_per_t",
    # energy and allocation descriptors
    "methanol_energy_gj_per_t",
    "carbon_split_ethylene",
    "carbon_split_propylene",
    "carbon_split_heavies",
    "mto_burden_share",
})


def _canonicalise_overrides(values: dict[str, Any] | None) -> dict[str, float]:
    if not values:
        return {}
    raw = {str(k).strip(): v for k, v in values.items() if k is not None}
    out: dict[str, float] = {}
    for k, v in raw.items():
        if k.startswith("_") or k in {"self", "params", "base", "overrides"}:
            continue
        if k not in ALLOWED_PRIMARY_OVERRIDES:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def primary_data_payload(overrides: dict[str, Any], draws: int = CONSOLE_DRAWS) -> dict[str, Any]:
    """Recompute the affected LCA KPIs from user-supplied primary inventory data.

    Only the model parameters listed in ``ALLOWED_PRIMARY_OVERRIDES`` are
    accepted; everything else is ignored, so the endpoint cannot be used to
    inject arbitrary model fields.  The returned payload is intentionally a
    subset of ``lca_payload``: it is enough to refresh the KPI cards, the
    stage table, the impact table and the contribution chart, plus the
    primary-data coverage note that keeps the dashboard honest.
    """
    params = ModelParams().with_overrides(**_canonicalise_overrides(overrides))
    result = build_result(params=params, draws=draws, make_figures=False)
    model = result.model
    scopes = model.scope_totals()
    total_kg = scopes["total"] or 1.0

    return {
        "params": _json(model_flows_frame(model)),
        "mass": _mass_balances(result),
        "kpis": {
            "gwp_t": _f(result.impact.gwp_per_kg, 4),
            "gwp_kg": _f(result.impact.gwp_kg, 3),
            "energy_gj": _f(result.impact.energy_mj / 1000.0, 2),
            "energy_mj": _f(result.impact.energy_mj, 1),
            "pe_factor": _f(result.impact.primary_energy_factor, 2),
            "scope1_kg": _f(scopes["scope1"], 2),
            "scope2_kg": _f(scopes["scope2"], 2),
            "scope3_kg": _f(scopes["scope3"], 2),
            "scope1_share": _f(100.0 * scopes["scope1"] / total_kg, 2),
            "scope2_share": _f(100.0 * scopes["scope2"] / total_kg, 2),
            "scope3_share": _f(100.0 * scopes["scope3"] / total_kg, 2),
            "flows": int(len(result.flows)),
            "dqi_mean": _f(result.dqi["dqi_score"].mean(), 2),
            "validation": result.validation.status,
            "findings": int(len(result.validation.findings)),
        },
        "stages": _json(result.stages),
        "impact_table": _json(result.impact_table),
        "contribution": _json(result.contribution),
        "categories": _json(result.categories),
        "coverage_note": (
            "With only the primary data supplied here, the model can still quantify "
            "climate change (GWP100) and the fossil primary-energy indicator. All other "
            "declared impact categories remain unquantified unless the corresponding "
            "elementary flows are also supplied as primary data; those gaps stay reported "
            "as gaps."
        ),
        "validation": {
            "status": result.validation.status,
            "findings": [
                {
                    "id": finding.finding_id,
                    "severity": finding.severity,
                    "title": finding.title,
                    "detail": finding.detail,
                    "impact_kg_co2e": _f(finding.impact_kg_co2e or 0.0, 2),
                }
                for finding in result.validation.findings
            ],
        },
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
    }


def model_flows_frame(model: PCFModel) -> pd.DataFrame:
    """Primary-data summary: one row per chain mass/energy flow."""
    f = model.flows
    rows = [
        {"flow": "HDPE resin (functional unit)", "quantity": f.hdpe_t, "unit": "t"},
        {"flow": "Ethylene feedstock", "quantity": f.ethylene_t, "unit": "t"},
        {"flow": "Methanol feedstock", "quantity": f.methanol_t, "unit": "t"},
        {"flow": "Natural gas feedstock", "quantity": f.natural_gas_t, "unit": "t"},
        {"flow": "1-butene/1-hexene co-monomer", "quantity": f.comonomer_t, "unit": "t"},
        {"flow": "Primary energy demand", "quantity": f.energy_gj, "unit": "GJ"},
    ]
    return pd.DataFrame(rows)


def _study() -> dict[str, Any]:
    return {
        "title": d.TITLE,
        "version": d.VERSION,
        "reference_period": d.REFERENCE_PERIOD,
        "base_year": d.BASE_YEAR,
        "product": d.PRODUCT,
        "functional_unit": d.FUNCTIONAL_UNIT,
        "declared_unit": d.DECLARED_UNIT,
        "decision": d.DECISION,
        "audience": d.AUDIENCE,
        "standards": d.STANDARDS,
        "method": d.METHOD,
        "software": d.SOFTWARE,
        "allocation": d.ALLOCATION,
        "geography": d.GEOGRAPHY,
        "cut_off": d.CUT_OFF,
        "inclusions": [{"item": item, "detail": detail} for item, detail in d.INCLUSIONS],
        "exclusions": [
            {"item": item, "why": why, "consequence": consequence}
            for item, why, consequence in d.EXCLUSIONS
        ],
        "limitations": list(d.LIMITATIONS),
        "dq_requirements": list(d.DATA_QUALITY_REQUIREMENTS),
        "impact_categories": [
            {"category": category, "indicator": indicator, "unit": unit, "note": note}
            for category, indicator, unit, note in d.IMPACT_CATEGORIES
        ],
    }


def _openlca() -> dict[str, Any]:
    """The openLCA cross-check, read from the bridge's result file.

    The console stays read-only: it reports the last run and never drives openLCA.
    A missing or unreadable file is a normal state (the bridge is optional), so it
    degrades to a note instead of failing the payload.
    """
    if not OPENLCA_RESULT.exists():
        return {
            "available": False,
            "note": (
                "No openLCA run recorded. With openLCA open and its IPC server started, "
                "run python -m lca.openlca_bridge --run to fill this card."
            ),
        }
    try:
        data = json.loads(OPENLCA_RESULT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "available": False,
            "note": "openlca_run.json could not be parsed, so the last run is not shown.",
        }

    total = float(data.get("total_kg_co2e") or 0.0)
    rows: List[dict[str, Any]] = []
    for item in data.get("per_process") or []:
        amount = float(item.get("amount_kg") or 0.0)
        rows.append(
            {
                "process": str(item.get("process", "")).replace("HDPE study / ", ""),
                "amount_kg": _f(amount, 2),
                "share_pct": _f(100.0 * amount / total if total else 0.0, 1),
            }
        )
    rows.sort(key=lambda row: -float(row["amount_kg"]))

    background = data.get("background") or {}
    providers = background.get("providers") or {}

    rows = rows or []

    # Old GWP runs wrote a six-row per-process table in `rows`. Multi-category
    # runs keep `rows = []` and report the foreground characterisation basis
    # separately; rebuild card rows from the foreground elementary-flow vector so
    # the card still shows the one category the current foreground can support.
    if not rows:
        fg_kg = data.get("foreground_elementary_flows_kg") or {}
        total = float(data.get("total_kg_co2e") or 0.0)
        if fg_kg and total:
            rows = [
                {
                    "process": str(fname),
                    "amount_kg": _f(float(qty), 2),
                    "share_pct": _f(100.0 * float(qty) / total, 1),
                }
                for fname, qty in fg_kg.items()
            ]
            rows.sort(key=lambda row: -float(row["amount_kg"]))

    return {
        "available": True,
        "linked": list(background.get("linked") or []),
        "providers": [
            {"flow": str(key), "name": str(value.get("name", ""))}
            for key, value in providers.items()
        ],
        "background_note": str(background.get("note", "")),
        "database": str(data.get("database", "")),
        "port": data.get("port"),
        "method": str(data.get("method", "")),
        "method_note": str(data.get("method_note", "")),
        "functional_unit": str(data.get("functional_unit", "")),
        "target_amount_kg": _f(data.get("target_amount_kg"), 1),
        "total_t": _f(data.get("total_t"), 4) if data.get("total_t") is not None else None,
        "python_t": _f(data.get("python_t"), 4) if data.get("python_t") is not None else None,
        "delta_pct": _f(data.get("delta_pct"), 4) if data.get("delta_pct") is not None else None,
        "run_at": str(data.get("run_at", "")),
        "rows": rows,
        "foreground_elementary_flows": data.get("foreground_elementary_flows"),
        "foreground_elementary_flows_kg": data.get("foreground_elementary_flows_kg"),
        "method_characterisation": data.get("method_characterisation"),
    }


# ---------------------------------------------------------------------- public
def lca_payload(draws: int = CONSOLE_DRAWS) -> dict[str, Any]:
    """The complete console payload, cached per draw count."""
    cached = _CACHE.get("payload")
    if cached is not None and cached["kpis"]["draws"] == draws:
        return cached

    result = build_result(draws=draws, make_figures=False)
    model = result.model
    scopes = model.scope_totals()
    total_kg = scopes["total"] or 1.0
    checks = quality_checks(result)
    status_counts = checks["status"].value_counts().to_dict()
    dqi_counts = result.dqi["dqi_rating"].value_counts().to_dict()

    payload: dict[str, Any] = {
        "study": _study(),
        "kpis": {
            "gwp_t": _f(result.impact.gwp_per_kg, 4),
            "gwp_kg": _f(result.impact.gwp_kg, 3),
            "energy_gj": _f(result.impact.energy_mj / 1000.0, 2),
            "energy_mj": _f(result.impact.energy_mj, 1),
            "pe_factor": _f(result.impact.primary_energy_factor, 2),
            "scope1_kg": _f(scopes["scope1"], 2),
            "scope2_kg": _f(scopes["scope2"], 2),
            "scope3_kg": _f(scopes["scope3"], 2),
            "scope1_share": _f(100.0 * scopes["scope1"] / total_kg, 2),
            "scope2_share": _f(100.0 * scopes["scope2"] / total_kg, 2),
            "scope3_share": _f(100.0 * scopes["scope3"] / total_kg, 2),
            "flows": int(len(result.flows)),
            "sources": int(len(result.sources)),
            "dqi_mean": _f(result.dqi["dqi_score"].mean(), 2),
            "dqi_counts": {str(k): int(v) for k, v in dqi_counts.items()},
            "draws": int(draws),
            "checks": {
                "met": int(status_counts.get("Met", 0)),
                "partial": int(status_counts.get("Partial", 0)),
                "not_met": int(status_counts.get("Not met", 0)),
                "total": int(len(checks)),
            },
            "validation": result.validation.status,
            "findings": int(len(result.validation.findings)),
            "categories_quantified": int(
                (result.categories["status"] == "Quantified").sum()
            ),
            "categories_declared": int(len(result.categories)),
        },
        "mass": _mass_balances(result),
        "stages": _json(result.stages),
        "flows": _json(result.flows),
        "dqi": _json(result.dqi),
        "sources": _json(result.sources),
        "completeness": _json(result.completeness),
        "impact_table": _json(result.impact_table),
        "categories": _json(result.categories),
        "contribution": _json(result.contribution),
        "sensitivity": _json(result.sensitivity),
        "reconciliation": _json(result.reconciliation),
        "uncertainty": {
            "evidence": _summary(result.evidence_summary),
            "screening": _summary(result.screening_summary),
            "evidence_hist": _histogram(result.evidence),
            "screening_hist": _histogram(result.screening),
        },
        "scenarios": _json(result.scenarios),
        "validation": {
            "status": result.validation.status,
            "checks": _json(result.validation.check_frame()),
            "carbon": _json(result.validation.carbon_frame()),
            "findings": [
                {
                    "id": finding.finding_id,
                    "severity": finding.severity,
                    "title": finding.title,
                    "detail": finding.detail,
                    "impact_kg_co2e": _f(finding.impact_kg_co2e or 0.0, 2),
                }
                for finding in result.validation.findings
            ],
        },
        "quality": _json(checks),
        "openlca": _openlca(),
        "deliverables": _json(deliverables(result)),
        "files": list_files(),
        "openlca_ledger": read_ledger(),
        "openlca_characterisation": {
            "note": (
                "Multi-category characterisation is available from the open database's "
                "impact methods, but the current foreground inventory carries only "
                "aggregated CO2e mapped to 'Carbon dioxide, fossil', so only climate "
                "change is characterisable from the foreground. All other categories "
                "are recorded as coverage gaps, not estimated. Run with "
                "--method 'ReCiPe Midpoint (H)' (or another installed method) to write "
                "a characterisation coverage artefact and a multi-category run JSON."
            ),
            "coverage": _json(characterisation_coverage(result.model.params)) if result else None,
        },
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
    }
    _CACHE["payload"] = payload
    return payload


# ------------------------------------------------------------------- artefacts
KIND_BY_SUFFIX = {
    ".pdf": "pdf",
    ".pptx": "deck",
    ".xlsx": "workbook",
    ".md": "doc",
    ".csv": "csv",
    ".json": "json",
    ".png": "figure",
}

LABELS = {
    "LCA_report.pdf": "LCA report",
    "LCA_presentation.pptx": "Presentation",
    "LCA_inventory.xlsx": "LCI workbook",
    "LCA_goal_and_scope.md": "Goal and scope",
    "LCA_impact_assessment.csv": "Impact assessment",
    "LCA_impact_assessment.json": "Impact assessment (JSON)",
    "LCA_data_quality_register.csv": "Data-quality register",
    "LCA_inventory_flows.csv": "LCI flows",
    "LCA_scenarios.csv": "Scenarios",
    "LCA_sensitivity.csv": "Sensitivity register",
    "LCA_uncertainty.csv": "Uncertainty draws summary",
    "LCA_completeness.csv": "Completeness matrix",
    "LCA_deliverables.md": "Deliverables index",
}


def list_files() -> List[dict[str, Any]]:
    """Every downloadable artefact that actually exists in outputs/LCA."""
    if not LCA_OUTPUT_DIR.exists():
        return []
    out: List[dict[str, Any]] = []
    for path in sorted(LCA_OUTPUT_DIR.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(LCA_OUTPUT_DIR).as_posix()
        label = LABELS.get(path.name, path.stem.replace("_", " ").title())
        if path.parent.name == "figures":
            label = f"Figure: {path.stem.replace('_', ' ')}"
        elif path.parent.name == "openlca":
            label = f"openLCA: {path.name}"
        out.append(
            {
                "name": rel,
                "label": label,
                "kind": KIND_BY_SUFFIX.get(path.suffix.lower(), "file"),
                "bytes": path.stat().st_size,
                "folder": path.parent.name if path.parent != LCA_OUTPUT_DIR else "",
                "url": f"/lca/files/{rel}",
            }
        )
    return out


def resolve_artefact(name: str) -> Path:
    """Resolve a requested artefact, refusing anything outside outputs/LCA."""
    root = LCA_OUTPUT_DIR.resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate
