"""Container for one complete LCA run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from pcf.model import PCFModel
from pcf.validation import ValidationReport

from .impact import ImpactResult


@dataclass
class LcaResult:
    model: PCFModel
    validation: ValidationReport
    impact: ImpactResult
    flows: pd.DataFrame
    stages: pd.DataFrame
    dqi: pd.DataFrame
    sources: pd.DataFrame
    completeness: pd.DataFrame
    impact_table: pd.DataFrame
    categories: pd.DataFrame
    contribution: pd.DataFrame
    sensitivity: pd.DataFrame
    reconciliation: pd.DataFrame
    evidence: pd.DataFrame
    screening: pd.DataFrame
    evidence_summary: Dict[str, Any]
    screening_summary: Dict[str, Any]
    scenarios: pd.DataFrame
    figures: Dict[str, Path] = field(default_factory=dict)
    paths: Dict[str, Path] = field(default_factory=dict)
