"""API tests for the HDPE PCF dashboard (:mod:`app.server`)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server import app
from pcf.params import ModelParams


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_index_and_assets(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "HDPE Carbon Control Room" in page.text
    for asset in ("styles.css", "app.js"):
        assert client.get(f"/static/{asset}").status_code == 200


def test_meta_exposes_every_parameter(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    defaults = body["defaults"]
    keys = {f.name for f in __import__("dataclasses").fields(ModelParams)}
    assert set(defaults) <= keys
    assert defaults["ef_grid"] == pytest.approx(0.475)
    assert any(p["key"] == "baseline" for p in body["presets"])
    assert any(p["key"] == "renewable_grid" for p in body["presets"])


def test_simulate_reproduces_specification(client: TestClient) -> None:
    body = client.post("/api/simulate", json={"params": {}}).json()
    assert body["kpis"]["total_t"] == pytest.approx(6.0685, abs=5e-4)
    assert body["kpis"]["scope1_kg"] == pytest.approx(2941.1, abs=1.0)
    assert len(body["stages"]) == 4
    assert len(body["validation"]["checks"]) == 19
    for key in ("scenarios", "sweep", "tornado", "allocation", "mass_balance", "layers"):
        assert body[key], key
    assert body["validation"]["status"] in {"PASS", "WARN", "FAIL"}


def test_parameter_override_moves_the_result(client: TestClient) -> None:
    base = client.post("/api/simulate", json={"params": {}}).json()
    mid = client.post("/api/simulate", json={"params": {"ef_grid": 0.3}}).json()
    assert mid["kpis"]["total_t"] < base["kpis"]["total_t"]
    assert mid["params"]["ef_grid"] == pytest.approx(0.3)
    # Scope 2 is proportional to the grid factor for a fixed workload
    per_kwh = base["kpis"]["scope2_kg"] / base["params"]["ef_grid"]
    assert mid["kpis"]["scope2_kg"] == pytest.approx(0.3 * per_kwh, rel=1e-9)


def test_zero_carbon_grid_is_supported(client: TestClient) -> None:
    body = client.post("/api/simulate", json={"params": {"ef_grid": 0.0}}).json()
    assert body["kpis"]["total_t"] == pytest.approx(3.5545, abs=5e-4)
    assert body["kpis"]["scope2_kg"] == pytest.approx(0.0)


def test_batch_size_leaves_intensity_unchanged(client: TestClient) -> None:
    one = client.post("/api/simulate", json={"params": {}}).json()["kpis"]
    many = client.post("/api/simulate", json={"params": {"functional_unit_t": 500}}).json()["kpis"]
    assert many["total_t"] == pytest.approx(one["total_t"])
    assert many["total_kg"] == pytest.approx(500 * one["total_kg"])


def test_rejects_unknown_and_out_of_range(client: TestClient) -> None:
    unknown = client.post("/api/simulate", json={"params": {"not_a_parameter": 1}})
    assert unknown.status_code == 422
    out_of_range = client.post("/api/simulate", json={"params": {"ef_grid": 5.0}})
    assert out_of_range.status_code == 422
    assert "ef_grid" in out_of_range.json()["detail"]
    not_numeric = client.post("/api/simulate", json={"params": {"ef_grid": "abc"}})
    assert not_numeric.status_code == 422


def test_report_endpoint_serves_pdf(client: TestClient) -> None:
    body = client.post("/api/report", json={"params": {}}).json()
    assert body["total_t"] == pytest.approx(6.0685, abs=5e-4)
    pdf = client.get(body["url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"
    for url in body["figures"].values():
        assert client.get(url).status_code == 200
