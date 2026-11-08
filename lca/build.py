"""Assemble one complete LCA result set."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pcf.model import PCFModel
from pcf.params import ModelParams
from pcf.validation import validate

from . import figures
from .impact import category_frame, compute, contribution_frame, impact_frame
from .inventory import (
    completeness_frame,
    dqi_frame,
    flows_frame,
    source_register,
    stage_frame,
)
from .results import LcaResult
from .uncertainty import (
    monte_carlo,
    reconciliation_curve,
    scenario_envelope,
    sensitivity_frame,
    summarise,
)


def build_result(
    params: Optional[ModelParams] = None,
    draws: int = 20000,
    seed: int = 42,
    figure_dir: Path | str = "outputs/LCA/figures",
    make_figures: bool = True,
) -> LcaResult:
    params = params or ModelParams()
    model = PCFModel(params)
    impact = compute(params)

    evidence = monte_carlo(draws, seed=seed, screening=False, base=params)
    screening = monte_carlo(draws, seed=seed, screening=True, base=params)
    evidence_summary = summarise(evidence, "Evidence-constrained reconciliation")
    screening_summary = summarise(screening, "Screening: evidence + judgement")

    result = LcaResult(
        model=model,
        validation=validate(model),
        impact=impact,
        flows=flows_frame(params),
        stages=stage_frame(params),
        dqi=dqi_frame(params),
        sources=source_register(),
        completeness=completeness_frame(params),
        impact_table=impact_frame(impact),
        categories=category_frame(),
        contribution=contribution_frame(impact),
        sensitivity=sensitivity_frame(params),
        reconciliation=reconciliation_curve(base=params),
        evidence=evidence,
        screening=screening,
        evidence_summary=evidence_summary,
        screening_summary=screening_summary,
        scenarios=scenario_envelope(params),
    )

    if make_figures:
        result.figures = dict(
            figures.build_all(
                model,
                impact,
                Path(figure_dir),
                evidence,
                screening,
                result.sensitivity,
                result.scenarios,
            )
        )
    return result
