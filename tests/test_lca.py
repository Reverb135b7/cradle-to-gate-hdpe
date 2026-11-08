"""Tests for the LCA layer (:mod:`lca`)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from lca import build_result
from lca.deck import build_deck
from lca.documents import quality_checks
from lca.impact import compute
from lca.inventory import flows_frame, stage_frame
from lca.openlca import exchanges_frame
from lca.report import build_report
from lca.uncertainty import (
    monte_carlo,
    reconciled_params,
    reconciliation_curve,
    sensitivity_frame,
)
from lca.workbook import build_workbook
from pcf.model import PCFModel
from pcf.params import ModelParams


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    outdir = tmp_path_factory.mktemp("lca_figures")
    return build_result(draws=300, figure_dir=outdir)


# ------------------------------------------------------------------ functional unit
def test_functional_unit_is_applied_from_the_engine() -> None:
    flows = flows_frame()
    product = flows.loc[flows["flow_id"] == "PRD-01"].iloc[0]
    assert product["quantity"] == pytest.approx(1000.0)
    assert product["unit"] == "kg"
    assert product["data_type"] == "reference"


def test_doubling_the_functional_unit_doubles_the_mass_flow() -> None:
    single = PCFModel(ModelParams()).flows
    double = PCFModel(ModelParams().with_overrides(functional_unit_t=2.0)).flows
    assert double.hdpe_t == pytest.approx(2 * single.hdpe_t)
    assert double.natural_gas_t == pytest.approx(2 * single.natural_gas_t)
    # intensity is invariant
    assert PCFModel(ModelParams().with_overrides(functional_unit_t=2.0)).total_t == pytest.approx(
        PCFModel().total_t
    )


# ----------------------------------------------------------------------- results
def test_gwp_reconciles_with_the_pcf_engine(result) -> None:
    assert result.model.total_kg == pytest.approx(PCFModel().total_kg)
    assert result.impact.gwp_kg == pytest.approx(result.model.total_kg)
    assert result.impact.gwp_per_kg == pytest.approx(6.0685, abs=5e-4)


def test_energy_indicator_is_internally_consistent(result) -> None:
    assert result.impact.energy_mj > 0
    stage_rows = result.stages[result.stages["stage_key"] != "total"]
    assert result.impact.energy_mj == pytest.approx(float(stage_rows["energy_mj"].sum()))
    assert result.impact.energy_mj / 1000 == pytest.approx(136.86, abs=0.05)
    stages = stage_frame()
    row = stages[stages["stage_key"] == "methanol"].iloc[0]
    assert row["energy_mj"] > 100_000


def test_emission_flows_sum_to_the_footprint(result) -> None:
    flows = result.flows
    direct = flows[flows["kind"] == "emission"]["quantity"].sum()
    electricity = flows[flows["flow_id"].str.startswith("ELE")]["quantity"].sum()
    steam = flows[flows["flow_id"].str.startswith("STM")]["quantity"].sum()
    params = result.model.params
    scope2 = electricity * params.ef_grid + steam * params.ef_steam
    assert direct + scope2 == pytest.approx(result.model.total_kg, rel=1e-12)


def test_inventory_provenance_is_complete(result) -> None:
    required = [
        "flow_id", "flow", "quantity", "unit", "source_id", "data_type",
        "geography", "period", "dqi_score", "dqi_rating", "proxy",
    ]
    assert not result.flows[required].isna().any().any()
    for column in ("dq_reliability", "dq_completeness", "dq_temporal",
                   "dq_geographical", "dq_technological"):
        assert result.flows[column].between(1, 5).all()
    assert set(result.flows["dqi_rating"]) <= {"A", "B", "C", "D", "E"}
    assert set(result.flows["source_id"]) <= {"S1", "S2", "S3", "S4", "S1/S3", "S2/S3", "-"}


def test_sources_cover_every_referenced_key(result) -> None:
    keys = set(result.sources["source_id"])
    referenced = set()
    for value in result.flows["source_id"]:
        referenced.update(part.strip() for part in str(value).split("/"))
    assert referenced - {"-"} <= keys


def test_categories_are_declared_not_invented(result) -> None:
    frame = result.categories
    quantified = frame[frame["status"] == "Quantified"]
    assert list(quantified["category"]) == ["Climate change"]
    assert len(frame) >= 8
    assert (frame["status"] == "Not quantified").sum() >= 6


# ------------------------------------------------------------------ sensitivity
def test_sensitivity_register_is_labelled(result) -> None:
    frame = result.sensitivity
    assert set(frame["basis"]) <= {"evidence", "scenario", "method", "judgement"}
    assert (frame["low_value"] <= frame["high_value"]).all()
    assert (frame["swing_t"] >= 0).all()
    assert frame.iloc[0]["parameter"] == "ef_grid"  # largest swing first


def test_reconciliation_path_moves_between_the_two_inventories() -> None:
    curve = reconciliation_curve(steps=11)
    assert len(curve) == 11
    assert curve["total_t"].is_monotonic_increasing
    assert curve["total_t"].iloc[0] == pytest.approx(6.0685, abs=5e-4)
    assert curve["total_t"].iloc[-1] == pytest.approx(6.1257, abs=5e-4)
    assert reconciled_params(1.0).mto_scope1 == pytest.approx(913.0)
    assert reconciled_params(1.0).ethylene_per_hdpe == pytest.approx(1.025)


def test_monte_carlo_is_seeded_and_ordered() -> None:
    a = monte_carlo(300, seed=7)
    b = monte_carlo(300, seed=7)
    assert np.allclose(a["total_t"], b["total_t"])
    evidence = monte_carlo(400, seed=11, screening=False)
    screening = monte_carlo(400, seed=11, screening=True)
    assert evidence["total_t"].std() < screening["total_t"].std()
    assert evidence["total_t"].min() >= 6.06
    assert screening["total_t"].min() < evidence["total_t"].min()


# --------------------------------------------------------------------- scenarios
def test_scenario_values_match_the_pcf_pipeline(result) -> None:
    scen = result.scenarios.set_index("scenario")
    assert scen.loc["baseline", "pcf_t"] == pytest.approx(6.0685, abs=5e-4)
    assert scen.loc["mid_transition", "pcf_t"] == pytest.approx(4.613, abs=1e-3)
    assert scen.loc["renewable_grid", "pcf_t"] == pytest.approx(3.5545, abs=5e-4)
    assert scen.loc["mass_allocation", "pcf_t"] == pytest.approx(5.209, abs=1e-3)
    assert scen.loc["economic_allocation", "pcf_t"] == pytest.approx(5.314, abs=1e-3)


# -------------------------------------------------------------------- artefacts
def test_openlca_tables_have_a_reference_flow_per_process() -> None:
    frame = exchanges_frame()
    assert set(frame["process"]) == {
        "P1 Methanol synthesis", "P2 MTO and separation", "P3 HDPE polymerisation"
    }
    for process, group in frame.groupby("process"):
        outputs = group[(group["exchange_type"] == "output") & (group["flow_type"] == "technosphere")]
        assert (outputs["amount"] == 1000.0).any(), process
    assert (frame["amount"] > 0).all()


def test_workbook_contains_the_deliverable_sheets(result, tmp_path: Path) -> None:
    path = build_workbook(result, tmp_path / "LCA_inventory.xlsx")
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True)
    for sheet in ("LCI", "Data quality", "Sources", "Completeness", "Impact",
                  "Sensitivity", "Uncertainty", "Quality checks"):
        assert sheet in wb.sheetnames
    assert wb["LCI"].max_row >= 15


def test_report_and_deck_build(result, tmp_path: Path) -> None:
    pdf = build_report(result, tmp_path / "LCA_report.pdf")
    assert pdf.stat().st_size > 100_000
    assert pdf.read_bytes()[:4] == b"%PDF"

    pptx = build_deck(result, tmp_path / "LCA_presentation.pptx")
    assert pptx.stat().st_size > 100_000
    from pptx import Presentation

    assert len(Presentation(pptx).slides) == 12


def test_quality_checks_record_partial_and_unmet_items(result) -> None:
    frame = quality_checks(result)
    assert len(frame) >= 10
    statuses = set(frame["status"])
    assert {"Met", "Partial", "Not met"} <= statuses
    assert (frame["what_is_needed"] != "").sum() >= 2


def test_cli_builds_the_expected_files(tmp_path: Path) -> None:
    from lca.cli import build_all

    result = build_all(outdir=tmp_path, draws=60, make_report=False, make_deck=False)
    for name in (
        "LCA_goal_and_scope.md",
        "LCA_inventory.xlsx",
        "LCA_data_quality_register.csv",
        "LCA_impact_assessment.csv",
        "LCA_impact_assessment.json",
        "LCA_deliverables.md",
        "openlca/README.md",
        "openlca/exchanges.csv",
    ):
        assert (tmp_path / name).exists(), name
    payload = json.loads((tmp_path / "LCA_impact_assessment.json").read_text())
    assert payload["result"]["gwp_t_co2e_per_t"] == pytest.approx(6.0685, abs=5e-4)
    assert payload["validation"]["status"] == result.validation.status
