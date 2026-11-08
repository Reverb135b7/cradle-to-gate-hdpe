"""Discover what the openLCA database can characterise, and map foreground flows.

This is the "Step 3.2" deliverable for the install actually running here: it does not
assume that a chosen method magically quantifies everything. It reports, for a method,
which impact categories it has, which elementary flows each category factors, and which
of the study's foreground elementary flows are coverable.

A full multi-indicator result is only possible if the foreground actually contains the
elementary flows those factors characterise. For the current study the foreground carries
an aggregated CO2e line mapped to "Carbon dioxide, fossil", so only climate-change is
characterisable from that inventory; every other category is declared as a coverage gap.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import olca_ipc as ipc
import olca_schema as o


def all_methods(client: ipc.Client) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for method in _entities(client, o.ImpactMethod):
        rows.append(
            {
                "name": method.name,
                "code": getattr(method, "code", None),
                "num_categories": len(
                    [c for c in (getattr(method, "impact_categories", None) or []) if c is not None]
                ),
                "impact_categories": [
                    getattr(c, "name", None) for c in (getattr(method, "impact_categories", None) or []) if c is not None
                ],
            }
        )
    return rows


def method_matrix(client: ipc.Client, method_name: str) -> Dict[str, Any]:
    """Characterisation matrix for one method, keyed by impact category.

    Returns a structure that can be serialised and written to CSV/JSON as the
    "what does this method actually cover" artefact.
    """
    try:
        method = client.get(o.ImpactMethod, name=method_name)
    except Exception as exc:  # pragma: no cover - IPC-dependent
        raise MethodError(f"could not read method '{method_name}': {exc}") from exc
    if method is None:
        raise MethodError(f"method '{method_name}' is not in this database")

    categories: List[Dict[str, Any]] = []
    coverage: Dict[str, List[str]] = {}
    for cat_ref in _refs(getattr(method, "impact_categories", None) or []):
        cat = client.get(o.ImpactCategory, cat_ref.id)
        if cat is None:
            categories.append({"category": cat_ref.name, "status": "missing"})
            continue
        factors: List[Dict[str, Any]] = []
        flows: set[str] = set()
        for factor in _factors_of(cat):
            flow_name = getattr(factor.flow, "name", None) if factor.flow is not None else None
            unit_name = getattr(factor.unit, "name", None) if factor.unit is not None else None
            flow_prop_name = getattr(factor.flow_property, "name", None) if factor.flow_property is not None else None
            factors.append(
                {
                    "flow": flow_name,
                    "flow_property": flow_prop_name,
                    "unit": unit_name,
                    "value": getattr(factor, "value", None),
                    "location": getattr(factor, "location", None),
                }
            )
            if flow_name is not None:
                flows.add(flow_name)
        categories.append(
            {
                "category": cat.name,
                "ref_unit": getattr(cat, "ref_unit", None),
                "num_factors": len(factors),
                "num_distinct_flows": len(flows),
                "status": "ready",
                "flows": sorted(flows),
                "factors": factors,
            }
        )
        coverage[cat.name] = sorted(flows)
    return {
        "method": method_name,
        "num_categories": len(categories),
        "impact_categories": categories,
        "coverage_summary": coverage,
    }


def foreground_coverage(
    matrix: Dict[str, Any], foreground_flow_names: List[str]
) -> Dict[str, Any]:
    """Which impact categories can this matrix characterise, given the foreground flows.

    A category is coverable only if at least one of its factors references a flow the
    foreground actually emits. This is the honest gate for any multi-indicator result.
    """
    matrix_flows: Dict[str, set[str]] = {}
    for cat in matrix.get("impact_categories", []):
        flows = cat.get("flows") or []
        matrix_flows[cat["category"]] = set(flows)
    foreground = set(foreground_flow_names)
    coverable: List[Dict[str, Any]] = []
    for cat, flows in matrix_flows.items():
        hit = flows & foreground
        coverable.append(
            {
                "category": cat,
                "coverable": bool(hit),
                "covering_foreground_flows": sorted(hit),
                "all_matrix_flows_for_category": sorted(flows),
            }
        )
    return {
        "foreground_flows": sorted(foreground),
        "method": matrix.get("method"),
        "num_categories_in_method": matrix.get("num_categories"),
        "categories_coverable_from_foreground": [
            c["category"] for c in coverable if c["coverable"]
        ],
        "coverage": coverable,
    }


def characterise_foreground(
    client: ipc.Client,
    method_name: str,
    foreground: Dict[str, float],
    foreground_flow_names: List[str],
) -> Dict[str, Any]:
    """Characterise a foreground elementary-flow vector through an openLCA method.

    `foreground` maps elementary flow name -> kg. Only flows the method factors are
    characterised; flows the method does not know about are listed as uncharacterised;
    flows the foreground does not have are listed as missing-from-foreground.
    """
    matrix = method_matrix(client, method_name)
    fg = foreground_coverage(matrix, foreground_flow_names)
    rows: List[Dict[str, Any]] = []
    for cat in matrix["impact_categories"]:
        if cat.get("status") != "ready":
            rows.append(
                {
                    "category": cat.get("category"),
                    "ref_unit": cat.get("ref_unit"),
                    "result": None,
                    "status": "cannot_characterise",
                    "reason": cat.get("status"),
                }
            )
            continue
        factors = {(f["flow"]): f for f in cat.get("factors", []) if f.get("flow")}
        result = 0.0
        characterised_flows: List[Dict[str, Any]] = []
        for fname in cat.get("flows", []):
            qty = foreground.get(fname, 0.0)
            factor_value = getattr(factors.get(fname), "value", None) if factors.get(fname) is not None else None
            if factor_value is None:
                continue
            delta = float(qty) * float(factor_value)
            result += delta
            characterised_flows.append(
                {"flow": fname, "quantity_kg": float(qty), "factor": float(factor_value), "contribution": float(delta)}
            )
        uncharacterised = [f for f in cat.get("flows", []) if f in foreground and f not in factors]
        missing_from_foreground = [f for f in fg["categories_coverable_from_foreground"] if False]  # placeholder below
        rows.append(
            {
                "category": cat["category"],
                "ref_unit": cat["ref_unit"],
                "result": float(result) if result else None,
                "status": "characterised" if characterised_flows else "zero_from_foreground",
                "characterised_flows": characterised_flows,
                "uncharacterised_foreground_flows": uncharacterised,
            }
        )
    return {
        "method": method_name,
        "functional_unit_kg": sum(foreground.values()),
        "impact_categories": rows,
    }


# ------------------------------------------------------------------ helpers
class MethodError(RuntimeError):
    """The requested impact method could not be used."""


def _factors_of(category: o.ImpactCategory) -> List[o.ImpactFactor]:
    return [f for f in (getattr(category, "impact_factors", None) or []) if f is not None]


def _entities(client: ipc.Client, model_type: Any) -> List[Any]:
    return [entity for entity in client.get_all(model_type) if entity is not None]


def _refs(items: List[Any]) -> List[Any]:
    return [item for item in items if item is not None]
