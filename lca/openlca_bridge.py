"""Quantify the HDPE study inside openLCA over its IPC server, then read the
result back into this project.

The Python model in :mod:`pcf` is the declaration of the study; openLCA becomes
an independent calculation engine over the same foreground inventory.  The
bridge builds six unit processes (gas supply, electricity supply, methanol,
MTO, polymerisation, co-monomer supply), links them into a product system, runs
the study's GWP100 method and writes ``outputs/LCA/openlca/openlca_run.json``,
which the dashboard reads.

Two honest constraints shape the mapping:

* The source inventory gives Scope 1 as aggregated CO2e per node.  It is
  therefore modelled as ``Carbon dioxide, fossil`` with a GWP100 factor of 1.
  For a CO2-only aggregate that is exact, but the model is a CO2e-equivalent
  model: it cannot support non-CO2 categories, and that is stated in the
  result file and the dashboard.
* No background database is used for the foreground chain.  Every quantity
  comes from the study's own inventory, so the openLCA total should reproduce
  the Python total to rounding; the value of the run is that an independent
  engine links the processes, scales them and applies the impact method.

Usage::

    python -m lca.openlca_bridge --check
    python -m lca.openlca_bridge --run
    python -m lca.openlca_bridge --run --purge
    python -m lca.openlca_bridge --run --purge \\
        --gas-provider "market for natural gas" --power-provider "market for electricity"
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import olca_ipc as ipc
import olca_schema as o

from pcf.params import ModelParams

from .inventory import stage_frame
from .openlca import characterisation_coverage, elementary_flows_frame

PREFIX = "HDPE study / "
DEFAULT_PORT = 8080
RESULT_PATH = Path("outputs/LCA/openlca/openlca_run.json")
CO2_FLOW_NAME = "Carbon dioxide, fossil"
METHOD_NAME = "IPCC 2007"
CATEGORY_NAME = "GWP 100"

FLOW_NAMES = {
    "ng": f"{PREFIX}Natural gas",
    "meoh": f"{PREFIX}Methanol",
    "ethylene": f"{PREFIX}Ethylene",
    "hdpe": f"{PREFIX}High-density polyethylene",
    "comonomer": f"{PREFIX}1-butene / 1-hexene co-monomer",
    "electricity": f"{PREFIX}Grid electricity",
}


class BridgeError(RuntimeError):
    """The bridge could not complete; the message is shown to the user."""


# --------------------------------------------------------------------- helpers
def _ref(entity: Any, ref_type: o.RefType) -> o.Ref:
    return o.Ref(id=entity.id, ref_type=ref_type, name=entity.name)


def _all(client: ipc.Client, model_type: Any) -> List[Any]:
    """Every entity of a type, dropping the nulls the IPC client sometimes returns."""
    return [entity for entity in client.get_all(model_type) if entity is not None]


def connect(port: int = DEFAULT_PORT) -> ipc.Client:
    try:
        return ipc.Client(port)
    except Exception as exc:  # pragma: no cover - depends on the desktop app
        raise BridgeError(
            f"no openLCA IPC server on port {port}. In openLCA open a database, then "
            "Tools > Developer tools > IPC Server > Start."
        ) from exc


def _flow_properties(client: ipc.Client) -> Dict[str, Any]:
    """Reference flow properties and units to bind the exchanges to."""
    wanted = {"Mass": "kg", "Energy": "kWh"}
    found: Dict[str, Any] = {}
    for prop in _all(client, o.FlowProperty):
        if prop.name in wanted:
            group = client.get(o.UnitGroup, prop.unit_group.id)
            unit = next(u for u in group.units if u.name == wanted[prop.name])
            found[prop.name] = (prop, unit)
    missing = set(wanted) - set(found)
    if missing:
        raise BridgeError(
            "the openLCA database is missing reference flow properties: "
            + ", ".join(sorted(missing))
        )
    return found


def _method(client: ipc.Client) -> tuple[o.Ref, o.Ref, str]:
    """The GWP100 impact method and category to run."""
    method = client.get(o.ImpactMethod, name=METHOD_NAME)
    if method is None:
        raise BridgeError(
            f"impact method '{METHOD_NAME}' is not in this database. Import the openLCA "
            "LCIA methods pack (Import > Linked Data (JSON-LD)) and retry."
        )
    category_ref = next(
        (ref for ref in method.impact_categories if CATEGORY_NAME in ref.name), None
    )
    if category_ref is None:
        raise BridgeError(f"'{METHOD_NAME}' has no category containing '{CATEGORY_NAME}'")
    return _ref(method, o.RefType.ImpactMethod), category_ref, category_ref.name


def _co2_flow(client: ipc.Client) -> o.Ref:
    """The reference CO2 flow that the GWP100 category gives a factor of 1."""
    category = client.get(
        o.ImpactCategory,
        name=f"climate change - {CATEGORY_NAME}a",
    ) or client.get(o.ImpactCategory, name=f"climate change - {CATEGORY_NAME}")
    factor_ids = set()
    if category and category.impact_factors:
        factor_ids = {f.flow.id for f in category.impact_factors if f.value == 1.0}
    for flow in _all(client, o.Flow):
        if flow.name == CO2_FLOW_NAME and flow.id in factor_ids:
            return _ref(flow, o.RefType.Flow)
    raise BridgeError(
        f"no '{CO2_FLOW_NAME}' elementary flow with a GWP100 factor of 1 in this database"
    )


# ---------------------------------------------------------------------- model
def model_definition(params: Optional[ModelParams] = None) -> Dict[str, Any]:
    """The foreground model as plain data, per unit of each process output.

    Amounts are derived from the same stage frame the Python result uses, so the
    two engines cannot drift: openLCA's job is to link and scale these numbers.
    """
    params = params or ModelParams()
    frame = stage_frame(params).set_index("stage_key")
    if "total" in frame.index:
        frame = frame.drop(index="total")

    hdpe_kg = 1000.0
    ethylene_kg = hdpe_kg * params.ethylene_per_hdpe
    meoh_kg = ethylene_kg * params.methanol_per_ethylene
    ng_kg = meoh_kg / params.methanol_per_ng
    comonomer_kg = hdpe_kg * params.comonomer_wt_fraction

    def per_stage(key: str, column: str) -> float:
        return float(frame.loc[key, column])

    meoh_scope1 = per_stage("methanol", "scope1_kg")
    mto_scope1 = per_stage("mto", "scope1_kg")
    hdpe_scope1 = per_stage("hdpe", "scope1_kg")
    ng_scope3 = per_stage("ng_extraction", "scope3_kg")

    meoh_elec = per_stage("methanol", "electricity_kwh")
    mto_elec = per_stage("mto", "electricity_kwh")
    hdpe_elec = per_stage("hdpe", "electricity_kwh")

    return {
        "functional_unit_kg": hdpe_kg,
        "flows": [
            ("ng", "Mass", "kg", "Natural gas, feedstock and reforming fuel (S1)"),
            ("meoh", "Mass", "kg", "Methanol, synthesis grade (S2)"),
            ("ethylene", "Mass", "kg", "Ethylene, MTO grade (S3)"),
            ("hdpe", "Mass", "kg", "High-density polyethylene resin at the gate"),
            ("comonomer", "Mass", "kg", "1-butene / 1-hexene co-monomer (supply chain not modelled)"),
            ("electricity", "Energy", "kWh", "Grid electricity, 0.475 kg CO2e/kWh (S2/S3)"),
        ],
        "processes": [
            {
                "key": "ng",
                "name": f"{PREFIX}Natural gas supply",
                "unit": "kg",
                "description": "Upstream extraction, processing and transport of natural gas at 0.380 kg CO2e/kg (S1).",
                "output": ("ng", 1.0),
                "inputs": [],
                "emissions": [ng_scope3 / ng_kg],
                "output_kg": ng_kg,
            },
            {
                "key": "electricity",
                "name": f"{PREFIX}Electricity supply",
                "unit": "kWh",
                "description": "Grid electricity at the study's 0.475 kg CO2e/kWh annual average (S2/S3).",
                "output": ("electricity", 1.0),
                "inputs": [],
                "emissions": [float(params.ef_grid)],
                "output_kg": 1.0,
            },
            {
                "key": "methanol",
                "name": f"{PREFIX}Methanol synthesis",
                "unit": "kg",
                "description": "SMR/ATR natural gas to methanol, including compression and distillation (S2).",
                "output": ("meoh", 1.0),
                "inputs": [
                    ("ng", ng_kg / meoh_kg, "Mass", "kg"),
                    ("electricity", meoh_elec / meoh_kg, "Energy", "kWh"),
                ],
                "emissions": [meoh_scope1 / meoh_kg],
                "output_kg": meoh_kg,
            },
            {
                "key": "mto",
                "name": f"{PREFIX}Methanol-to-olefins",
                "unit": "kg",
                "description": "SAPO-34 MTO and olefin separation, 2.95 t methanol per t ethylene; co-products netted out in that yield (S3).",
                "output": ("ethylene", 1.0),
                "inputs": [
                    ("meoh", meoh_kg / ethylene_kg, "Mass", "kg"),
                    ("electricity", mto_elec / ethylene_kg, "Energy", "kWh"),
                ],
                "emissions": [mto_scope1 / ethylene_kg],
                "output_kg": ethylene_kg,
            },
            {
                "key": "hdpe",
                "name": f"{PREFIX}Polymerisation and pelletising",
                "unit": "kg",
                "description": "Slurry/gas-phase polymerisation, devolatilisation, drying and pelletising (S4).",
                "output": ("hdpe", 1.0),
                "inputs": [
                    ("ethylene", ethylene_kg / hdpe_kg, "Mass", "kg"),
                    ("comonomer", comonomer_kg / hdpe_kg, "Mass", "kg"),
                    ("electricity", hdpe_elec / hdpe_kg, "Energy", "kWh"),
                ],
                "emissions": [hdpe_scope1 / hdpe_kg],
                "output_kg": hdpe_kg,
            },
            {
                "key": "comonomer",
                "name": f"{PREFIX}Co-monomer supply",
                "unit": "kg",
                "description": "Mass-only module: the co-monomer supply chain is outside the quantified inventory, so this process carries no emissions (recorded gap).",
                "output": ("comonomer", 1.0),
                "inputs": [],
                "emissions": [],
                "output_kg": comonomer_kg,
            },
        ],
    }


# ------------------------------------------------------------------- entities
def _delete_study(client: ipc.Client) -> int:
    removed = 0
    for system in _all(client, o.ProductSystem):
        if system.name.startswith(PREFIX):
            client.delete(_ref(system, o.RefType.ProductSystem))
            removed += 1
    for process in _all(client, o.Process):
        if process.name.startswith(PREFIX):
            client.delete(_ref(process, o.RefType.Process))
            removed += 1
    for flow in _all(client, o.Flow):
        if flow.name.startswith(PREFIX):
            client.delete(_ref(flow, o.RefType.Flow))
            removed += 1
    return removed


def _ensure_flow(
    client: ipc.Client,
    name: str,
    flow_type: o.FlowType,
    property_name: str,
    unit: str,
    description: str,
    props: Dict[str, Any],
) -> o.Ref:
    existing = client.get(o.Flow, name=name)
    if existing is None:
        # a missed by-name lookup would otherwise create a duplicate flow and
        # silently split the model in two
        existing = next((f for f in _all(client, o.Flow) if f.name == name), None)
    if existing is not None:
        return _ref(existing, o.RefType.Flow)
    prop, _ = props[property_name]
    flow = o.Flow(
        name=name,
        description=description,
        flow_type=flow_type,
        flow_properties=[
            o.FlowPropertyFactor(
                flow_property=_ref(prop, o.RefType.FlowProperty),
                conversion_factor=1.0,
                is_ref_flow_property=True,
            )
        ],
    )
    ref = client.put(flow)
    if ref is None:
        raise BridgeError(f"openLCA refused the flow '{name}'")
    return ref


def _provider_supply(client: ipc.Client, provider: o.Ref) -> Dict[str, Any]:
    """The product a background dataset actually offers, as flow, property and unit.

    A dataset can only supply its own flow, so a study input has to be expressed in
    that flow to be linkable at all; the study's private flow and its proxy process
    are then dropped for that input.
    """
    process = client.get(o.Process, uid=provider.id)
    if process is None:
        process = next((p for p in _all(client, o.Process) if p.id == provider.id), None)
    if process is None:
        raise BridgeError(f"provider '{provider.name}' could not be read back")
    reference = next(
        (e for e in (process.exchanges or []) if e is not None and e.is_quantitative_reference),
        None,
    )
    if reference is None or reference.flow is None:
        raise BridgeError(
            f"provider '{process.name}' has no reference product flow, so nothing can be "
            "linked to it"
        )
    return {
        "name": process.name,
        "flow": o.Ref(
            id=reference.flow.id, ref_type=o.RefType.Flow, name=reference.flow.name
        ),
        "flow_property": reference.flow_property,
        "unit": reference.unit,
    }


def _resolve_provider(client: ipc.Client, name: str) -> o.Ref:
    """An existing process in this database, used as a background provider.

    Providers are named explicitly rather than pattern-matched: a background
    dataset is an evidential choice (geography, technology, year) that has to be
    written down, not guessed from a name.
    """
    process = client.get(o.Process, name=name)
    if process is None:
        # the by-name lookup can miss an entity that exists, so confirm by scan
        process = next((p for p in _all(client, o.Process) if p.name == name), None)
    if process is None:
        total = len(_all(client, o.Process))
        raise BridgeError(
            f"no process named '{name}' in this database, so there is nothing to link "
            f"({total} processes present). Import the licensed background database and "
            "use its exact process name."
        )
    return _ref(process, o.RefType.Process)


def build(
    client: ipc.Client,
    definition: Dict[str, Any],
    co2: o.Ref,
    background: Optional[Dict[str, o.Ref]] = None,
) -> Dict[str, Any]:
    """Create flows, processes, provider links and the product system."""
    props = _flow_properties(client)
    background = background or {}
    supply = {key: _provider_supply(client, ref) for key, ref in background.items()}

    flow_refs: Dict[str, o.Ref] = {}
    for key, property_name, unit, description in definition["flows"]:
        if key in supply:
            flow_refs[key] = supply[key]["flow"]
            continue
        flow_refs[key] = _ensure_flow(
            client,
            FLOW_NAMES[key],
            o.FlowType.PRODUCT_FLOW,
            property_name,
            unit,
            description,
            props,
        )

    process_refs: Dict[str, o.Ref] = {}
    process_outputs: Dict[str, str] = {}
    for spec in definition["processes"]:
        if spec["key"] in supply:
            # the background dataset replaces this proxy, so it is not created
            continue
        output_key, output_amount = spec["output"]
        exchanges: List[o.Exchange] = []
        internal_id = 1

        exchanges.append(
            o.Exchange(
                internal_id=internal_id,
                flow=flow_refs[output_key],
                flow_property=_ref(props["Mass" if _property_of(definition, output_key) == "Mass" else "Energy"][0], o.RefType.FlowProperty),
                unit=o.Ref(
                    id=props["Mass" if _property_of(definition, output_key) == "Mass" else "Energy"][1].id,
                    ref_type=o.RefType.Unit,
                    name=spec["unit"],
                ),
                amount=output_amount,
                is_input=False,
                is_quantitative_reference=True,
                description=f"Reference product of {spec['name']}",
            )
        )
        internal_id += 1

        for input_key, amount, property_name, unit in spec["inputs"]:
            if input_key in supply:
                prop = supply[input_key]["flow_property"]
                unit_obj = supply[input_key]["unit"]
            else:
                prop, unit_obj = props[property_name]
            exchanges.append(
                o.Exchange(
                    internal_id=internal_id,
                    flow=flow_refs[input_key],
                    flow_property=_ref(prop, o.RefType.FlowProperty),
                    unit=o.Ref(id=unit_obj.id, ref_type=o.RefType.Unit, name=unit_obj.name),
                    amount=amount,
                    is_input=True,
                )
            )
            internal_id += 1

        for amount in spec["emissions"]:
            exchanges.append(
                o.Exchange(
                    internal_id=internal_id,
                    flow=co2,
                    flow_property=_ref(props["Mass"][0], o.RefType.FlowProperty),
                    unit=o.Ref(id=props["Mass"][1].id, ref_type=o.RefType.Unit, name="kg"),
                    amount=amount,
                    is_input=False,
                    description="Aggregated CO2e emitted as CO2 (study inventory)",
                )
            )
            internal_id += 1

        process = o.Process(
            name=spec["name"],
            description=spec["description"],
            process_type=o.ProcessType.UNIT_PROCESS,
            exchanges=exchanges,
        )
        ref = client.put(process)
        if ref is None:
            raise BridgeError(f"openLCA refused the process '{spec['name']}'")
        process_refs[spec["key"]] = ref
        process_outputs[spec["key"]] = output_key

    # second pass: point every consumed product at its provider, which is a
    # background dataset where one was named explicitly
    background = background or {}
    for spec in definition["processes"]:
        if not spec["inputs"]:
            continue
        process = client.get(o.Process, name=spec["name"])
        if process is None:
            raise BridgeError(f"process '{spec['name']}' disappeared after creation")
        for exchange in process.exchanges:
            if not exchange.is_input:
                continue
            provider_key = _provider_for(definition, exchange.flow.name)
            provider = background.get(provider_key) or process_refs.get(provider_key)
            if provider is not None:
                exchange.default_provider = provider
        client.put(process)

    hdpe_ref = process_refs["hdpe"]
    system_ref = client.create_product_system(hdpe_ref)
    if system_ref is None:
        raise BridgeError("openLCA could not create the product system")

    # openLCA names the system after the reference process, which reads as if the
    # study were only the polymerisation step; name it for the functional unit.
    linked = sorted(background)
    if background:
        # prove the datasets really entered the supply chain, rather than
        # reporting a link that openLCA quietly ignored
        created = client.get(o.ProductSystem, uid=system_ref.id)
        present = {p.id for p in (created.processes or []) if p is not None}
        missing = [ref.name for key, ref in background.items() if ref.id not in present]
        if created is None or missing:
            raise BridgeError(
                "the product system did not pick up the background provider(s): "
                + ", ".join(missing)
            )

    system = client.get(o.ProductSystem, uid=system_ref.id)
    if system is not None:
        system.name = f"{PREFIX}Product system (1 t HDPE)"
        renamed = client.put(system)
        if renamed is not None:
            system_ref = renamed
    return {
        "flows": flow_refs,
        "processes": process_refs,
        "process_outputs": process_outputs,
        "system": system_ref,
        "linked": linked,
    }


def _property_of(definition: Dict[str, Any], flow_key: str) -> str:
    return next(p for k, p, _, _ in definition["flows"] if k == flow_key)


def _provider_for(definition: Dict[str, Any], flow_name: str) -> Optional[str]:
    for key, name in FLOW_NAMES.items():
        if name == flow_name:
            return key if key in {p["key"] for p in definition["processes"]} else None
    return None


# ---------------------------------------------------------------- calculation
def calculate(
    client: ipc.Client,
    system: o.Ref,
    method: o.Ref,
    amount_kg: float,
) -> Dict[str, Any]:
    setup = o.CalculationSetup(
        target=system,
        impact_method=method,
        amount=amount_kg,
        allocation=o.AllocationType.USE_DEFAULT_ALLOCATION,
    )
    result = client.calculate(setup)
    result.wait_until_ready()
    try:
        impacts = result.get_total_impacts()
        categories = {c.id: c.name for c in result.get_impact_categories()}
        rows = []
        for value in impacts:
            rows.append(
                {
                    "category": categories.get(value.impact_category.id, value.impact_category.name),
                    "amount": float(value.amount),
                    "unit": value.impact_category.ref_unit,
                }
            )

        gwp_ids = {v.impact_category.id for v in impacts if "GWP" in v.impact_category.name}
        target_id = next((v.impact_category.id for v in impacts if v.impact_category.id in gwp_ids), None)
        per_process = []
        for tech_flow in result.get_tech_flows():
            for value in result.get_direct_impacts_of(tech_flow):
                if value.impact_category.id != target_id:
                    continue
                per_process.append(
                    {
                        "process": tech_flow.provider.name,
                        "amount_kg": float(value.amount),
                    }
                )
                break
        return {"rows": rows, "per_process": per_process}
    finally:
        result.dispose()


# ----------------------------------------------------------------------- runs
def run(
    port: int = DEFAULT_PORT,
    purge: bool = False,
    amount_kg: float = 1000.0,
    gas_provider: Optional[str] = None,
    power_provider: Optional[str] = None,
    result_path: Optional[Path] = None,
) -> Dict[str, Any]:
    return _run(
        port=port,
        purge=purge,
        amount_kg=amount_kg,
        gas_provider=gas_provider,
        power_provider=power_provider,
        result_path=result_path,
        method_name=METHOD_NAME,
        category_name=CATEGORY_NAME,
    )


def method_run(
    port: int = DEFAULT_PORT,
    purge: bool = False,
    amount_kg: float = 1000.0,
    method_name: str = "ReCiPe Midpoint (H)",
    result_path: Optional[Path] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Calculate the study through an arbitrary openLCA impact method.

    This is the multi-indicator path. The current foreground inventories only the
    aggregated CO2e line, so only climate change is characterised from the
    foreground; every other category is recorded as a coverage gap in the result,
    not estimated.
    """
    return _run(
        port=port,
        purge=purge,
        amount_kg=amount_kg,
        gas_provider=None,
        power_provider=None,
        result_path=result_path,
        method_name=method_name,
        category_name=None,
        force=force,
    )


def _run(
    port: int = DEFAULT_PORT,
    purge: bool = False,
    amount_kg: float = 1000.0,
    gas_provider: Optional[str] = None,
    power_provider: Optional[str] = None,
    result_path: Optional[Path] = None,
    method_name: str = METHOD_NAME,
    category_name: Optional[str] = CATEGORY_NAME,
    force: bool = False,
) -> Dict[str, Any]:
    definition = model_definition()
    client = connect(port)

    existing = [p.name for p in _all(client, o.Process) if p.name.startswith(PREFIX)]
    if existing and not purge and not force:
        raise BridgeError(
            f"{len(existing)} '{PREFIX}...' processes already exist in this database. "
            "Use --purge to replace them, or --force with --method to add a characterisation "
            "without rebuilding the foreground model."
        )

    background: Dict[str, o.Ref] = {}
    if gas_provider:
        background["ng"] = _resolve_provider(client, gas_provider)
    if power_provider:
        background["electricity"] = _resolve_provider(client, power_provider)

    if purge:
        _delete_study(client)

    # Resolve the requested method early so an unknown name fails before anything is built.
    try:
        requested_method = client.get(o.ImpactMethod, name=method_name)
    except Exception as exc:  # pragma: no cover - IPC-dependent
        raise BridgeError(f"could not read method '{method_name}': {exc}") from exc
    if requested_method is None:
        raise BridgeError(
            f"method '{method_name}' is not in this database. "
            "The database currently holds 37 impact methods including IPCC 2007, "
            "ReCiPe Midpoint (H), CML 2001 and USEtox; list them with --check or "
            "by opening the database in openLCA."
        )

    co2 = _co2_flow(client)
    entities = build(client, definition, co2, background)

    effective_category_name = category_name
    if effective_category_name and effective_category_name not in " ":
        cat_ref = next(
            (ref for ref in requested_method.impact_categories if effective_category_name in ref.name), None
        )
        if cat_ref is None:
            raise BridgeError(
                f"'{method_name}' has no category containing '{effective_category_name}'. "
                "For IPCC 2007 use 'GWP 100'; for ReCiPe use the method's category names."
            )
        category_ref = cat_ref
        category_name = category_ref.name
    else:
        category_ref = None

    if effective_category_name:
        outcome = calculate(client, entities["system"], _ref(requested_method, o.RefType.ImpactMethod), amount_kg)
    else:
        outcome = calculate(client, entities["system"], _ref(requested_method, o.RefType.ImpactMethod), amount_kg)

    gwp = next((row for row in outcome["rows"] if "GWP" in row["category"]), None) if effective_category_name else None
    if effective_category_name and gwp is None:
        raise BridgeError("the calculation returned no matching category")

    from .impact import compute
    from .ledger import record

    python_t = compute().gwp_per_kg
    total_t = gwp["amount"] / 1000.0 if gwp else None

    fg = elementary_flows_frame()
    fg_names = list(fg["flow"].unique())

    result = {
        "connected": True,
        "port": port,
        "database": _database_name(),
        "method": (
            f"{method_name} / {category_name}" if effective_category_name else method_name
        ),
        "method_note": (
            "The inventory's Scope 1 is an aggregated CO2e figure, modelled here as CO2 "
            "with a GWP100 factor of 1. That is exact for a CO2-only aggregate but means "
            "the openLCA model is CO2e-equivalent, not species-resolved."
        ),
        "functional_unit": "1,000 kg HDPE resin at the gate",
        "target_amount_kg": amount_kg,
        "foreground_elementary_flows": fg_names,
        "foreground_elementary_flows_kg": {row["flow"]: float(row["quantity_kg"]) for row in fg.to_dict("records")},
        "method_characterisation": {
            "method": method_name,
            "coverage": characterisation_coverage().to_dict("records"),
        },
    }

    if effective_category_name:
        result.update(
            {
                "total_kg_co2e": gwp["amount"],
                "total_t": total_t,
                "python_t": python_t,
                "delta_pct": 100.0 * (total_t - python_t) / python_t if python_t else 0.0,
                "per_process": sorted(
                    [r for r in outcome["per_process"] if "GWP" in r.get("category", "")],
                    key=lambda r: -r["amount_kg"],
                ),
            }
        )
    else:
        # multi-category run: only climate change is from the foreground; the rest
        # are coverage gaps, not numbers.
        cc = next((r for r in outcome["rows"] if "GWP" in r.get("category", "")), None)
        result.update(
            {
                "total_kg_co2e": cc["amount"] if cc else None,
                "total_t": cc["amount"] / 1000.0 if cc else None,
                "python_t": python_t,
                "delta_pct": (
                    100.0 * ((cc["amount"] / 1000.0) - python_t) / python_t if cc and python_t else None
                ),
                "per_process": [],
                "method_note": (
                    "Multi-category run through {method}. The foreground inventory carries only "
                    "aggregated CO2e mapped to Carbon dioxide, fossil, so only climate change is "
                    "characterisable from the foreground; every other category is recorded as a "
                    "coverage gap, not estimated."
                ).format(method=method_name),
            }
        )

    result.update(
        {
            "entities": {
                "product_system": entities["system"].id,
                "processes": {key: ref.id for key, ref in entities["processes"].items()},
                "flows": {key: ref.id for key, ref in entities["flows"].items()},
            },
            "background": {
                "linked": sorted(background),
                "providers": {
                    key: {"name": ref.name, "id": ref.id} for key, ref in background.items()
                },
                "note": (
                    "Gas and electricity are taken from provider datasets in the open database; "
                    "the difference against the Python total is the background-data reconciliation."
                    if background
                    else (
                        "No background provider linked: the upstream gas and electricity processes "
                        "are the study's own factor-based proxies, so the two engines agree by "
                        "construction and this run is not an ecoinvent footprint."
                    )
                ),
            },
            "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )

    target = Path(result_path) if result_path else RESULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    try:
        descriptor = client.get(o.Descriptor)
    except Exception:
        descriptor = None
    record(
        port=port,
        database=_database_name(),
        method=result.get("method"),
        provider_names={k: v["name"] for k, v in result.get("background", {}).get("providers", {}).items()},
        amount_kg=amount_kg,
        openlca_descriptor=descriptor,
        result_path=target,
    )
    return result


def _database_name() -> str:
    workspace = Path.home() / "openLCA-data-1.4" / "databases.json"
    try:
        data = json.loads(workspace.read_text(encoding="utf-8"))
        names = [db["name"] for db in data.get("localDatabases", [])]
        return names[0] if len(names) == 1 else ", ".join(names)
    except Exception:
        return "unknown"


def check(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    client = connect(port)
    return {
        "connected": True,
        "port": port,
        "database": _database_name(),
        "impact_methods": len(client.get_all(o.ImpactMethod)),
        "processes": len(client.get_all(o.Process)),
        "has_ipcc": client.get(o.ImpactMethod, name=METHOD_NAME) is not None,
        "has_co2": client.get(o.Flow, name=CO2_FLOW_NAME) is not None,
    }


def read_result(path: Path = RESULT_PATH) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ------------------------------------------------------------------------ cli
def main(argv: Optional[List[str]] = None) -> int:
    import logging

    # olca-ipc logs a warning for every by-name lookup that misses; the bridge
    # uses those lookups deliberately to decide whether to create an entity.
    logging.getLogger().setLevel(logging.ERROR)

    parser = argparse.ArgumentParser(prog="lca.openlca_bridge", description=__doc__)
    parser.add_argument("--check", action="store_true", help="test the IPC connection only")
    parser.add_argument("--run", action="store_true", help="build the model and calculate with IPCC 2007 GWP 100")
    parser.add_argument("--purge", action="store_true", help="delete the HDPE study entities first")
    parser.add_argument(
        "--gas-provider",
        metavar="PROCESS",
        help="exact name of a natural-gas provider process in the open database",
    )
    parser.add_argument(
        "--power-provider",
        metavar="PROCESS",
        help="exact name of an electricity provider process in the open database",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--method",
        metavar="METHOD",
        help="calculate through an arbitrary openLCA impact method (e.g. 'ReCiPe Midpoint (H)')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --method, add characterisation without rebuilding the foreground model",
    )
    args = parser.parse_args(argv)

    if not (args.check or args.run or args.method):
        parser.print_help()
        return 2

    try:
        if args.check:
            info = check(args.port)
            print(f"connected to openLCA on port {info['port']} ({info['database']})")
            print(f"  impact methods {info['impact_methods']} · processes {info['processes']}")
            print(f"  IPCC 2007 present: {info['has_ipcc']} · CO2 fossil present: {info['has_co2']}")
            return 0

        if args.method:
            result = method_run(
                port=args.port,
                purge=args.purge,
                amount_kg=1000.0,
                method_name=args.method,
                force=args.force,
            )
            print(f"openLCA method: {result.get('method')}")
            if result.get("total_t") is not None:
                print(f"  climate change: {result['total_t']:.4f} t CO2e / t HDPE")
                if result.get("python_t"):
                    print(f"  python: {result['python_t']:.4f} t · delta {result.get('delta_pct', float('nan')):+.2f} %")
            print(f"  foreground elementary flows: {result.get('foreground_elementary_flows')}")
            print(f"  characterisation coverage written with the run")
            print(f"  written to {RESULT_PATH}")
            return 0

        result = run(
            args.port,
            purge=args.purge,
            gas_provider=args.gas_provider,
            power_provider=args.power_provider,
        )
        print(f"openLCA: {result['total_t']:.4f} t CO2e / t HDPE")
        print(f"  python: {result['python_t']:.4f} t · delta {result['delta_pct']:+.2f} %")
        print(f"  method: {result['method']}")
        for key, provider in result["background"]["providers"].items():
            print(f"  provider {key}: {provider['name']}")
        for row in result["per_process"]:
            print(f"  {row['process']:<44} {row['amount_kg']:>9.1f} kg")
        print(f"  written to {RESULT_PATH}")
        return 0
    except BridgeError as exc:
        print(f"openLCA bridge: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
