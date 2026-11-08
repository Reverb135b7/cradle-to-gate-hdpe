"""Integrated cradle-to-gate product carbon footprint model for HDPE via MTO.

Public API::

    from pcf import PCFModel, ModelParams, validate, run

    model = PCFModel()
    model.total_t            # 6.068 t CO2e / t HDPE
    validate(model).status   # PASS / WARN / FAIL
"""

from .allocation import allocation_frame, allocation_scenarios
from .model import PCFModel, StageResult
from .params import SCENARIOS, EmissionFactorsError, ModelParams, Scenario
from .pipeline import PipelineResult, run
from .reference_script import reference_result
from .sensitivity import grid_sweep, run_all_scenarios, run_scenarios, tornado
from .utility_basis import basis_comparison, basis_params, steam_share_pct, utility_frame
from .validation import Check, Finding, ValidationReport, validate

__version__ = "1.0.0"

__all__ = [
    "PCFModel",
    "StageResult",
    "ModelParams",
    "Scenario",
    "SCENARIOS",
    "EmissionFactorsError",
    "validate",
    "ValidationReport",
    "Check",
    "Finding",
    "run",
    "PipelineResult",
    "run_scenarios",
    "run_all_scenarios",
    "grid_sweep",
    "tornado",
    "allocation_frame",
    "allocation_scenarios",
    "utility_frame",
    "basis_comparison",
    "basis_params",
    "steam_share_pct",
    "reference_result",
    "__version__",
]
