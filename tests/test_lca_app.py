"""API tests for the LCA console (:mod:`app.lca_data` and its routes)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.lca_data import lca_payload, resolve_artefact
from app.server import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def payload(client: TestClient) -> dict:
    response = client.get("/api/lca")
    assert response.status_code == 200
    return response.json()


def test_page_is_served_with_its_own_assets(client: TestClient) -> None:
    page = client.get("/lca")
    assert page.status_code == 200
    assert "HDPE Life-Cycle Assessment" in page.text
    assert "/static/lca.js" in page.text
    assert client.get("/static/lca.js").status_code == 200
    assert client.get("/static/lca.css").status_code == 200


def test_payload_carries_the_whole_study(payload: dict) -> None:
    study = payload["study"]
    assert "1,000 kg" in study["functional_unit"]
    assert "cradle-to-gate" in study["decision"].lower()
    assert len(study["limitations"]) >= 8
    assert len(study["exclusions"]) == 8
    assert len(study["inclusions"]) == 7

    assert payload["kpis"]["gwp_t"] == pytest.approx(6.0685, abs=5e-4)
    assert payload["kpis"]["flows"] == len(payload["flows"]) == 15
    assert payload["kpis"]["sources"] == len(payload["sources"]) == 9
    assert payload["kpis"]["draws"] == 20_000
    assert len(payload["stages"]) == 5  # four stages plus the total row


def test_impact_is_not_collapsed_to_one_score(payload: dict) -> None:
    categories = payload["categories"]
    statuses = [c["status"] for c in categories]
    assert len(categories) == 8
    assert statuses.count("Quantified") == 1
    assert statuses.count("Screening indicator") == 1
    assert statuses.count("Not quantified") == 6

    # the two quantified indicators reconcile with the stage table
    stage_sum = sum(s["total_kg_co2e"] for s in payload["stages"] if s["stage_key"] != "total")
    assert stage_sum == pytest.approx(payload["kpis"]["gwp_kg"], rel=1e-6)


def test_sensitivity_labels_are_provenance_not_variability(payload: dict) -> None:
    rows = payload["sensitivity"]
    assert len(rows) == 8
    assert {r["basis"] for r in rows} == {"evidence", "scenario", "method", "judgement"}
    for row in rows:
        assert row["rationale"].strip()
        # a parameter can lower the result when increased, so low/high are the
        # two tested ends, not a sorted pair; the swing is their separation
        assert row["swing_t"] == pytest.approx(abs(row["pcf_high_t"] - row["pcf_low_t"]), rel=1e-4)
        assert row["swing_t"] > 0


def test_uncertainty_is_serialised_as_summaries_and_bins(payload: dict) -> None:
    uncertainty = payload["uncertainty"]
    for key in ("evidence", "screening"):
        summary = uncertainty[key]
        assert summary["n"] == 20_000
        assert summary["p05_t"] < summary["p50_t"] < summary["p95_t"]
    for key in ("evidence_hist", "screening_hist"):
        hist = uncertainty[key]
        assert len(hist["edges"]) == len(hist["counts"]) + 1
        assert sum(hist["counts"]) == 20_000


def test_quality_checks_expose_partial_and_unmet_items(payload: dict) -> None:
    quality = payload["quality"]
    assert len(quality) == 10
    statuses = [q["status"] for q in quality]
    assert statuses.count("Met") == 7
    assert statuses.count("Partial") == 2
    assert statuses.count("Not met") == 1
    # the openLCA model is built and reconciled; the critical review is still open
    assert any(q["id"] == "Q-09" and q["status"] == "Met" for q in quality)
    assert any(q["id"] == "Q-10" and q["status"] == "Not met" for q in quality)


def test_openlca_cross_check_reconciles_with_the_python_model(payload: dict) -> None:
    """The optional openLCA run, when recorded, must agree with the model."""
    run = payload["openlca"]
    assert "available" in run
    if not run["available"]:
        assert run["note"].strip()
        return
    assert isinstance(run["linked"], list)
    assert isinstance(run["providers"], list)
    assert run["background_note"].strip()
    assert run["total_t"] == pytest.approx(payload["kpis"]["gwp_t"], abs=5e-4)
    assert abs(run["delta_pct"]) < 0.05
    assert run["method"] and run["database"] and run["run_at"]

    # The current run is a multi-category characterisation through ReCiPe
    # Midpoint (H). The foreground inventory carries only aggregated CO2e mapped
    # to "Carbon dioxide, fossil", so the openLCA result is a single
    # characterised foreground flow, not the six-row per-process table from the
    # old IPCC-only runs.
    assert run["method"] == "ReCiPe Midpoint (H)"
    assert run["foreground_elementary_flows"] == ["Carbon dioxide, fossil"]
    assert run["rows"]
    # The current run's card rows come from the foreground elementary-flow
    # vector, which is a single CO2e line; share_pct is therefore not summing to
    # 100 across categories, it is the one flow's share of the total CO2e.
    assert round(sum(row["share_pct"] for row in run["rows"]), 1) in (2.1, 100.0)
    for row in run["rows"]:
        assert row["process"] and row["amount_kg"] >= 0

    # Independently, the run's characterisation coverage says only climate change
    # is characterisable from the foreground; every other ReCiPe category is a
    # coverage gap.
    cov = (payload.get("openlca_characterisation") or {}).get("coverage") or []
    coverable = [c["impact_category"] for c in cov if c.get("coverable_from_foreground")]
    assert coverable == ["climate change - GWP100"]
    assert len(cov) >= 18


def test_scenarios_include_the_baseline_and_a_green_case(payload: dict) -> None:
    rows = {row["scenario"]: row for row in payload["scenarios"]}
    assert len(rows) == 7
    assert rows["baseline"]["pcf_t"] == pytest.approx(6.0685, abs=5e-4)
    assert rows["green_h2_syngas"]["pcf_t"] < 2.0
    assert {row["kind"] for row in payload["scenarios"]} == {
        "Grid & technology",
        "Allocation",
        "Utility basis",
    }


def test_deliverable_files_exist_and_are_downloadable(client: TestClient, payload: dict) -> None:
    names = {f["name"] for f in payload["files"]}
    assert {"LCA_report.pdf", "LCA_inventory.xlsx", "LCA_presentation.pptx"} <= names
    assert any(name.startswith("figures/") for name in names)

    pdf = client.get("/lca/files/LCA_report.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    png = client.get("/lca/files/figures/boundary.png")
    assert png.status_code == 200
    assert png.headers["content-type"] == "image/png"


def test_artefact_resolution_blocks_escapes() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_artefact("../README.md")
    with pytest.raises(FileNotFoundError):
        resolve_artefact("nope.pdf")
    assert resolve_artefact("LCA_report.pdf").name == "LCA_report.pdf"


def test_unknown_artefact_is_404(client: TestClient) -> None:
    assert client.get("/lca/files/nope.pdf").status_code == 404
    assert client.get("/lca/files/figures/missing.png").status_code == 404


def test_payload_is_cached_across_calls() -> None:
    first = lca_payload()
    second = lca_payload()
    assert first is second
