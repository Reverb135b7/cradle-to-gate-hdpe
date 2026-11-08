"""Cradle-to-gate LCA layer over the HDPE PCF engine.

The LCA package consumes :mod:`pcf` rather than re-implementing it, so the
footprint, hotspots and scenario results are identical to the PCF deliverables.
"""

from __future__ import annotations

from .build import build_result
from .impact import ImpactResult, compute
from .results import LcaResult

__all__ = ["LcaResult", "ImpactResult", "build_result", "compute"]
__version__ = "1.0"
