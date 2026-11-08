"""Loader for the standalone engine execution script.

The specification ships with ``pcf_engine_execution_script.md``, which contains
a self-contained reference implementation (``HDPE_PCF_Calculator``).  Rather
than re-implementing that arithmetic, this module executes the script straight
from the project file and exposes its output, so the packaged model can be
cross-checked against the reference implementation itself.

The script is executed in its own module namespace with ``__name__`` set to a
non-``__main__`` value, so importing it here never re-runs its demo block.
"""

from __future__ import annotations

import types
from functools import lru_cache
from pathlib import Path

import pandas as pd

#: project-root relative path of the reference script
DEFAULT_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "pcf_engine_execution_script.md"


@lru_cache(maxsize=4)
def load_reference_module(path: str | Path = DEFAULT_SCRIPT_PATH) -> types.ModuleType:
    """Execute the reference script and return it as a module object."""
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType("pcf_engine_execution_script")
    module.__dict__["__name__"] = "pcf_engine_execution_script"
    module.__dict__["__file__"] = str(path)
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def reference_calculator(path: str | Path = DEFAULT_SCRIPT_PATH):
    """Instantiate the reference calculator with its default factors."""
    module = load_reference_module(path)
    return module.HDPE_PCF_Calculator()


def reference_result(
    target_hdpe_ton: float = 1.0,
    path: str | Path = DEFAULT_SCRIPT_PATH,
) -> tuple[float, pd.DataFrame]:
    """Run the reference script's footprint calculation."""
    return reference_calculator(path).calculate_footprint(target_hdpe_ton=target_hdpe_ton)


def reference_node_scope2(path: str | Path = DEFAULT_SCRIPT_PATH) -> dict[str, float]:
    """Scope 2 per node as the reference script computes it, kg CO2e per t product."""
    calc = reference_calculator(path)
    return {
        "methanol": 320.0 * calc.grid_ci + 6.1 * calc.steam_ci,
        "mto": 700.0 * calc.grid_ci + 2.3 * calc.steam_ci,
        "hdpe": 450.0 * calc.grid_ci + 1.5 * calc.steam_ci,
    }


def reference_utilities() -> dict[str, float]:
    """Electricity and steam demand per node, as declared in the script."""
    return {
        "methanol_kwh_per_t": 320.0,
        "methanol_steam_gj_per_t": 6.1,
        "mto_kwh_per_t": 700.0,
        "mto_steam_gj_per_t": 2.3,
        "hdpe_kwh_per_t": 450.0,
        "hdpe_steam_gj_per_t": 1.5,
    }


def main() -> int:
    """Reproduce the reference script's own console output."""
    total, frame = reference_result()
    print("=" * 53)
    print(f"TOTAL CRADLE-TO-GATE HDPE PCF: {total:.2f} kg CO2e / t resin")
    print("=" * 53)
    print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
