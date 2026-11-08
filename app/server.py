"""FastAPI backend for the HDPE PCF control room.

The API is a thin, stateless wrapper around the :mod:`pcf` engine: the client
posts a parameter set, the engine recomputes the whole chain, and the response
carries every artifact the dashboard renders (KPIs, flowsheet, hotspots,
scenario comparison, sensitivity, validation and findings).
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pcf.allocation import allocation_frame, allocation_scenarios
from pcf.model import PCFModel
from pcf.params import SCENARIOS, EmissionFactorsError, ModelParams
from pcf.pipeline import run as run_pipeline
from pcf.sensitivity import grid_sweep, run_scenarios, tornado
from pcf.utility_basis import basis_comparison, utility_frame
from pcf.validation import validate

from . import lca_data, params_meta

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
def _generated_dir() -> Path:
    env = os.environ.get("GENERATED_DIR")
    if env:
        return Path(env).resolve()
    return APP_DIR / "_generated"


GENERATED_DIR = _generated_dir()

#: headline values from the technical specification, for the comparison column
SPEC_REFERENCE = {
    "pcf_t": 6.068,
    "scope1_kg": 2940.9,
    "scope2_kg": 2513.9,
    "scope3_kg": 613.3,
    "methanol_pcf_kg": 1384.8,
    "ethylene_pcf_kg": 5544.8,
    "ng_t": 1.614,
}

app = FastAPI(
    title="HDPE PCF Control Room",
    description=(
        "Cradle-to-gate product carbon footprint of high-density polyethylene via the "
        "methanol-to-olefins pathway (ISO 14040/14044, ISO 14067)."
    ),
    version="1.0.0",
)

GENERATED_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------- helpers
def _json(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records"))


def _params_from(raw: dict[str, Any] | None) -> ModelParams:
    """Validate a client parameter set into a :class:`ModelParams`."""
    raw = raw or {}
    known = set(params_meta.field_keys())
    clean: dict[str, float] = {}
    for key, value in raw.items():
        if key not in known:
            raise HTTPException(status_code=422, detail=f"unknown parameter: {key}")
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"parameter {key} is not numeric"
            ) from exc
        if not math.isfinite(number):
            raise HTTPException(status_code=422, detail=f"parameter {key} is not finite")
        bounds = params_meta.bounds()[key]
        if number < bounds["min"] or number > bounds["max"]:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"parameter {key} = {number} outside supported range "
                    f"[{bounds['min']}, {bounds['max']}]"
                ),
            )
        clean[key] = number

    try:
        params = ModelParams().with_overrides(**clean)
    except EmissionFactorsError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # guard the divisors so the chain stays finite
    if params.methanol_per_ng <= 0 or params.methanol_per_ethylene <= 0:
        raise HTTPException(status_code=422, detail="yield factors must be positive")
    if params.ethylene_per_hdpe <= 0 or params.functional_unit_t <= 0:
        raise HTTPException(status_code=422, detail="demand ratios must be positive")
    return params


def _kpis(model: PCFModel) -> dict[str, float]:
    scopes = model.scope_totals()
    flows = model.flows
    pcf = model.node_pcf()
    return {
        "total_t": model.total_t,
        "total_kg": scopes["total"],
        "per_kg": model.total_per_kg_resin,
        "scope1_kg": scopes["scope1"],
        "scope2_kg": scopes["scope2"],
        "scope3_kg": scopes["scope3"],
        "scope1_share": 100.0 * scopes["scope1"] / scopes["total"] if scopes["total"] else 0.0,
        "scope2_share": 100.0 * scopes["scope2"] / scopes["total"] if scopes["total"] else 0.0,
        "scope3_share": 100.0 * scopes["scope3"] / scopes["total"] if scopes["total"] else 0.0,
        "ng_t": flows.natural_gas_t,
        "methanol_t": flows.methanol_t,
        "ethylene_t": flows.ethylene_t,
        "hdpe_t": flows.hdpe_t,
        "comonomer_t": flows.comonomer_t,
        "energy_gj": flows.energy_gj,
        "energy_per_t": flows.energy_gj / flows.hdpe_t if flows.hdpe_t else 0.0,
        "methanol_pcf_kg": pcf["methanol"]["total"] * 1000.0,
        "ethylene_pcf_kg": pcf["ethylene"]["total"] * 1000.0,
        "delta_vs_spec_pct": 100.0
        * (model.total_t - SPEC_REFERENCE["pcf_t"])
        / SPEC_REFERENCE["pcf_t"],
    }


def _payload(params: ModelParams) -> dict[str, Any]:
    model = PCFModel(params)
    report = validate(model)
    stages = model.stages()
    total_kg = model.total_kg or 1.0

    scenarios = run_scenarios(
        params,
        tuple(SCENARIOS) + tuple(allocation_scenarios(params)),
    )
    sweep = grid_sweep(params)
    tornado_frame = tornado(params)

    return {
        "params": {f.name: getattr(params, f.name) for f in dataclasses.fields(params)},
        "kpis": _kpis(model),
        "stages": [
            {
                "key": s.key,
                "label": s.label,
                "scope1": s.scope1,
                "scope2": s.scope2,
                "scope3": s.scope3,
                "total": s.total,
                "cumulative": s.cumulative,
                "share_pct": 100.0 * s.total / total_kg,
            }
            for s in stages
        ],
        "layers": _json(model.layer_frame()),
        "mass_balance": _json(model.mass_flow_frame()),
        "scenarios": _json(scenarios),
        "sweep": _json(sweep),
        "tornado": _json(tornado_frame),
        "allocation": _json(allocation_frame(params)),
        "utility": {
            "nodes": _json(utility_frame(params)),
            "comparison": _json(basis_comparison(params)),
        },
        "validation": {
            "status": report.status,
            "checks": _json(report.check_frame()),
            "carbon": _json(report.carbon_frame()),
            "findings": [
                {
                    "id": f.finding_id,
                    "severity": f.severity,
                    "title": f.title,
                    "detail": f.detail,
                    "impact_kg_co2e": f.impact_kg_co2e,
                }
                for f in report.findings
            ],
        },
        "spec_reference": SPEC_REFERENCE,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# -------------------------------------------------------------------- routes
@app.get("/api/meta")
def meta() -> dict[str, Any]:
    """Parameter description, defaults and the available presets."""
    presets = [
        {
            "key": s.key,
            "label": s.label,
            "description": s.description,
            "overrides": {k: float(v) for k, v in s.overrides.items()},
            "spec_reference_t": s.spec_reference_t,
        }
        for s in SCENARIOS
    ]
    presets += [
        {
            "key": s.key,
            "label": s.label,
            "description": s.description,
            "overrides": {k: float(v) for k, v in s.overrides.items()},
            "spec_reference_t": s.spec_reference_t,
        }
        for s in allocation_scenarios(ModelParams())
    ]
    return {
        "groups": params_meta.PARAM_GROUPS,
        "defaults": params_meta.defaults(),
        "presets": presets,
        "spec_reference": SPEC_REFERENCE,
        "standards": ["ISO 14040/14044", "ISO 14067", "GHG Protocol Product Standard"],
    }


@app.post("/api/simulate")
def simulate(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Recompute the full chain for a parameter set and return every artifact."""
    params = _params_from(body.get("params") if "params" in body else body)
    try:
        return _payload(params)
    except (ZeroDivisionError, ValueError) as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/report")
def generate_report(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Build the PDF engineering report for the supplied parameter set."""
    params = _params_from(body.get("params") if "params" in body else body)
    run_id = uuid.uuid4().hex[:12]
    outdir = GENERATED_DIR / run_id
    result = run_pipeline(outdir=outdir, params=params, make_report=True)
    if result.report_path is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="report generation failed")
    return {
        "id": run_id,
        "url": f"/generated/{run_id}/{result.report_path.name}",
        "figures": {
            name: f"/generated/{run_id}/figures/{path.name}"
            for name, path in result.figures.items()
        },
        "total_t": result.total_t,
        "validation_status": result.validation.status,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/lca")
def lca() -> dict[str, Any]:
    """The complete LCA console payload, built from the study package."""
    return lca_data.lca_payload()


@app.post("/api/lca/compute")
def lca_compute(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Recompute the affected LCA KPIs from user-supplied primary data.

    Only the inventory fields listed in ``lca_data.ALLOWED_PRIMARY_OVERRIDES``
    are accepted; unrecognised keys are ignored and invalid numerics are rejected
    with 422.  The response is a focused subset of the console payload: it is
    enough to refresh the KPI cards, the primary-data flows, the stage table, the
    impact table, the contribution chart and the openLCA characterisation coverage
    note, without rebuilding the full Monte Carlo payloads.
    """
    try:
        return lca_data.primary_data_payload(body.get("params") if isinstance(body, dict) else body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/lca")
def lca_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "lca.html")


@app.get("/lca/files/{name:path}")
def lca_file(name: str) -> FileResponse:
    """Serve a delivered artefact from outputs/LCA, refusing anything outside it."""
    try:
        path = lca_data.resolve_artefact(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"no such artefact: {name}") from exc
    return FileResponse(path, filename=path.name)


@app.get("/lca/files/openlca/characterisation_coverage.csv")
def openlca_characterisation_coverage() -> FileResponse:
    """Characterisation coverage exported from the open database's impact methods."""
    from lca.openlca import characterisation_coverage
    frame = characterisation_coverage()
    path = GENERATED_DIR / "openlca_characterisation_coverage.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return FileResponse(path, filename="openlca_characterisation_coverage.csv")


@app.get("/api/lca/openlca/methods")
def openlca_methods() -> JSONResponse:
    """Impact methods available in the open database, from the IPC server."""
    try:
        import olca_ipc as ipc
        import olca_schema as o
        from lca.matrix import all_methods
        client = ipc.Client()
        methods = all_methods(client)
        return JSONResponse(content={"methods": methods})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"openLCA not reachable: {exc}") from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.exception_handler(HTTPException)
def http_error(request, exc: HTTPException) -> JSONResponse:  # type: ignore[no-untyped-def]
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/generated", StaticFiles(directory=GENERATED_DIR), name="generated")
