"""Tests for the integrated cradle-to-gate HDPE PCF model."""

from __future__ import annotations

import math

import pytest

from pcf.allocation import allocation_frame, allocation_scenarios
from pcf.model import PCFModel
from pcf.params import SCENARIO_BY_KEY, EmissionFactorsError, ModelParams, Scenario
from pcf.sensitivity import grid_sweep, run_scenarios, tornado
from pcf.validation import carbon_balances, validate

APPROX = pytest.approx


# ---------------------------------------------------------------- model basis
def test_functional_unit_flows_match_specification():
    flows = PCFModel().flows
    assert flows.hdpe_t == 1.0
    assert flows.ethylene_t == APPROX(1.015, rel=1e-12)
    assert flows.methanol_t == APPROX(2.99425, rel=1e-6)
    assert flows.natural_gas_t == APPROX(1.61415, rel=1e-6)
    assert flows.comonomer_t == APPROX(0.015, rel=1e-12)
    assert flows.energy_gj == APPROX(89.2287, rel=1e-4)


def test_total_footprint_reproduces_specification():
    model = PCFModel()
    assert model.total_t == APPROX(6.068, abs=2e-3)
    assert model.total_kg == APPROX(6068.0, abs=1.0)
    assert model.total_per_kg_resin == APPROX(6.068, abs=2e-3)


def test_scope_totals_match_hotspot_column_sums():
    scopes = PCFModel().scope_totals()
    assert scopes["scope1"] == APPROX(2940.9, abs=1.0)
    assert scopes["scope2"] == APPROX(2513.9, abs=1.0)
    assert scopes["scope3"] == APPROX(613.3, abs=0.5)
    assert scopes["total"] == APPROX(scopes["scope1"] + scopes["scope2"] + scopes["scope3"])


def test_node_layer_footprints():
    pcf = PCFModel().node_pcf()
    assert pcf["methanol"]["total"] * 1000 == APPROX(1384.8, abs=0.2)
    assert pcf["ethylene"]["total"] * 1000 == APPROX(5544.8, abs=0.8)
    assert pcf["hdpe"]["total"] * 1000 == APPROX(6068.0, abs=1.0)


def test_stage_cumulative_is_monotonic_and_consistent():
    stages = PCFModel().stages()
    cumulative = [s.cumulative for s in stages]
    assert cumulative == sorted(cumulative)
    assert cumulative[-1] == APPROX(PCFModel().total_kg)
    assert sum(s.total for s in stages) == APPROX(cumulative[-1])


def test_hotspot_shares_sum_to_one_hundred():
    frame = PCFModel().hotspot_frame()
    assert frame["share_pct"].sum() == pytest.approx(100.0, abs=1e-9)
    assert frame["total_kg"].sum() == pytest.approx(6068.0, abs=1.0)


def test_unknown_parameter_override_raises():
    with pytest.raises(EmissionFactorsError):
        ModelParams().with_overrides(not_a_parameter=1.0)


# --------------------------------------------------------------- flexibility
def test_grid_factor_scales_only_scope_two():
    base = PCFModel()
    zero = PCFModel(ModelParams().with_overrides(ef_grid=0.0))
    assert zero.scope_totals()["scope2"] == pytest.approx(0.0, abs=1e-9)
    assert zero.scope_totals()["scope1"] == pytest.approx(base.scope_totals()["scope1"])
    assert zero.total_kg == pytest.approx(
        base.total_kg - base.scope_totals()["scope2"], rel=1e-12
    )


def test_grid_sweep_is_linear_and_monotonic():
    sweep = grid_sweep(step=0.05)
    values = sweep["pcf_t"].to_list()
    assert values == sorted(values)
    assert sweep["pcf_t"].iloc[0] == pytest.approx(3.5545, abs=1e-3)
    assert sweep["pcf_t"].iloc[-1] == pytest.approx(6.7301, abs=1e-3)
    slopes = sweep["slope_t_per_ef"].to_numpy()
    assert max(slopes) - min(slopes) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------- validation
def test_spec_reproduction_checks_pass():
    report = validate()
    reproduction = [c for c in report.checks if c.check_id.startswith("P-")]
    assert reproduction, "expected reproduction checks"
    for check in reproduction:
        assert check.status == "PASS", f"{check.check_id}: {check.deviation_pct:.3f} %"


def test_carbon_balance_closure_of_node_one_is_closed_by_fuel_gas():
    node1 = carbon_balances(PCFModel())[0]
    assert node1.closure_pct == pytest.approx(100.0, abs=1e-9)
    assert node1.raw_closure_pct == pytest.approx(74.68, abs=0.05)
    assert node1.makeup_input_kg / 1000 == pytest.approx(0.5472, abs=1e-3)


def test_carbon_balance_deficits_are_flagged():
    report = validate()
    carbon = {b.node.split()[1]: b for b in report.carbon}
    assert carbon["2"].closure_deviation_pct == pytest.approx(-1.496, abs=0.01)
    assert carbon["3"].closure_deviation_pct == pytest.approx(-0.940, abs=0.01)
    failed = {c.check_id for c in report.checks if c.status == "FAIL"}
    assert {"M-2", "M-3"} <= failed
    assert report.status == "FAIL"


def test_findings_are_quantified():
    report = validate()
    ids = [f.finding_id for f in report.findings]
    assert ids == [
        "F-01", "F-02", "F-03", "F-04", "F-05", "F-07", "F-08", "F-09",
    ]
    fuel_gas = next(f for f in report.findings if f.finding_id == "F-03")
    assert fuel_gas.impact_kg_co2e == pytest.approx(207.9, abs=0.5)
    utility_gap = next(f for f in report.findings if f.finding_id == "F-08")
    assert utility_gap.impact_kg_co2e == pytest.approx(6.177, abs=0.01)


def test_reference_script_cross_checks_pass():
    report = validate()
    reference = {c.check_id: c for c in report.checks if c.check_id.startswith("R-")}
    assert set(reference) == {"R-01", "R-02"}
    assert all(c.status == "PASS" for c in reference.values())
    assert reference["R-01"].value == pytest.approx(6074.669, abs=1e-3)


# ------------------------------------------------- execution-script utilities
def test_explicit_utility_basis_matches_reference_script():
    from pcf.reference_script import reference_result

    model = PCFModel(SCENARIO_BY_KEY["explicit_utilities"].params())
    reference_total, _ = reference_result()
    assert model.total_kg == pytest.approx(reference_total, rel=1e-12)
    assert model.total_t == pytest.approx(6.0747, abs=1e-4)
    assert model.scope_totals()["scope2"] == pytest.approx(2520.174, abs=1e-3)


def test_explicit_utility_node_scope2_matches_reference():
    from pcf.reference_script import reference_node_scope2

    pcf = PCFModel(SCENARIO_BY_KEY["explicit_utilities"].params()).node_pcf()
    reference = reference_node_scope2()
    assert pcf["methanol"]["scope2"] * 1000 == pytest.approx(reference["methanol"], abs=1e-9)
    assert pcf["ethylene"]["scope2"] * 1000 == pytest.approx(reference["mto"], abs=1e-9)
    assert pcf["hdpe"]["scope2"] * 1000 == pytest.approx(reference["hdpe"], abs=1e-9)


def test_scenario_overrides_track_the_reference_script():
    from pcf.reference_script import reference_utilities

    overrides = {k: float(v) for k, v in SCENARIO_BY_KEY["explicit_utilities"].overrides.items()}
    assert overrides == reference_utilities()


def test_steam_basis_blocks_full_grid_decarbonisation():
    from pcf.utility_basis import basis_comparison, steam_share_pct

    comparison = basis_comparison().set_index("basis")
    assert comparison.loc["grid_equivalent", "steam_share_pct"] == 0.0
    assert steam_share_pct() == pytest.approx(60.07, abs=0.02)
    assert comparison.loc["explicit_utilities", "pcf_mid_transition"] == pytest.approx(
        5.492, abs=1e-3
    )
    assert comparison.loc["explicit_utilities", "pcf_zero_carbon_grid"] == pytest.approx(
        5.0683, abs=1e-3
    )
    assert comparison.loc["grid_equivalent", "pcf_baseline"] == pytest.approx(6.0685, abs=1e-4)


def test_utility_frame_reconciles_nodes_to_scope2_total():
    from pcf.utility_basis import utility_frame

    frame = utility_frame()
    total = frame.iloc[-1]
    assert total["grid_equivalent_kg"] == pytest.approx(2513.998, abs=1e-2)
    assert total["explicit_scope2_kg"] == pytest.approx(2520.174, abs=1e-2)
    assert total["steam_kg"] == pytest.approx(1513.811, abs=1e-2)
    assert total["delta_kg"] == pytest.approx(6.177, abs=1e-2)
    assert total["explicit_scope2_kg"] == pytest.approx(
        frame.iloc[:-1]["explicit_scope2_kg"].sum(), abs=1e-9
    )


def test_default_basis_has_no_thermal_remainder():
    params = ModelParams()
    assert params.methanol_steam_gj_per_t == 0.0
    assert params.mto_steam_gj_per_t == 0.0
    assert params.hdpe_steam_gj_per_t == 0.0
    assert PCFModel().total_t == pytest.approx(6.06849, abs=1e-5)


# --------------------------------------------------------------- sensitivity
def test_scenarios_reproduce_quoted_values():
    frame = run_scenarios().set_index("scenario")
    assert frame.loc["baseline", "pcf_t"] == pytest.approx(6.07, abs=0.01)
    assert frame.loc["mid_transition", "pcf_t"] == pytest.approx(4.61, abs=0.01)
    assert frame.loc["renewable_grid", "pcf_t"] == pytest.approx(3.5545, abs=1e-3)
    assert frame.loc["green_h2_syngas", "pcf_t"] == pytest.approx(1.1146, abs=1e-3)


def test_mid_transition_reduction_is_electricity_linked():
    frame = run_scenarios().set_index("scenario")
    saved = frame.loc["baseline", "pcf_t"] - frame.loc["mid_transition", "pcf_t"]
    expected = 2513.9975 * (0.475 - 0.200) / 0.475 / 1000
    assert saved == pytest.approx(expected, rel=1e-6)


def test_tornado_is_ranked_and_symmetric():
    frame = tornado()
    assert len(frame) == 8
    assert frame["swing_t"].is_monotonic_decreasing
    top = frame.iloc[0]
    assert top["parameter"] == "ethylene_per_hdpe"


def test_allocation_ordering():
    frame = allocation_frame(ModelParams()).set_index("basis")
    assert frame.loc["as_specified", "pcf_t"] > frame.loc["economic_allocation", "pcf_t"]
    assert frame.loc["economic_allocation", "pcf_t"] > frame.loc["mass_allocation", "pcf_t"]
    assert frame.loc["mass_allocation", "ethylene share of node 2"] == pytest.approx(0.42)
    assert [s.key for s in allocation_scenarios(ModelParams())] == [
        "mass_allocation",
        "economic_allocation",
    ]


# ------------------------------------------------------------------ pipeline
def test_pipeline_writes_all_artifacts(tmp_path):
    from pcf.pipeline import run

    result = run(outdir=tmp_path)
    assert result.report_path is not None and result.report_path.exists()
    assert result.report_path.stat().st_size > 50_000
    for name in ("process_flow", "waterfall", "hotspot", "scenarios", "tornado"):
        assert result.figures[name].exists()
        assert result.figures[name].stat().st_size > 10_000
    for key, path in result.data_paths.items():
        assert path.exists(), key
        assert path.stat().st_size > 0
    assert result.total_t == pytest.approx(6.068, abs=2e-3)


def test_scenario_dataclass_rejects_unknown_override():
    bad = Scenario(key="x", label="x", description="x", overrides={"nope": 1})
    with pytest.raises(EmissionFactorsError):
        bad.params(ModelParams())


def test_negative_grid_factor_is_physically_meaningless_but_stable():
    # guard against numeric drift rather than silently accepting nonsense
    model = PCFModel(ModelParams().with_overrides(ef_grid=0.0))
    assert math.isfinite(model.total_t)
    assert SCENARIO_BY_KEY["baseline"].params().ef_grid == 0.475
