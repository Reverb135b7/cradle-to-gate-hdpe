"""Provenance ledger for openLCA runs.

One JSON line per run, written to outputs/LCA/openlca/ledger.jsonl.  It records
what is actually available at run time: git commit, openLCA IPC server, database
name, method, provider names when linked, and allocation basis.  It does not
pretend to fields the install does not furnish - in particular, provider names are
recorded only when a real background database is linked.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

LEDGER_PATH = Path("outputs/LCA/openlca/ledger.jsonl")

# The bridge writes the run JSON to RESULT_PATH, then records provenance in this
# separate ledger so the run file stays a single clean JSON document.

#: primary run JSON path used by the dashboard.  If the bridge is called with a
#: custom result_path that differs from this, the ledger records that path.
RESULT_PATH = Path("outputs/LCA/openlca/openlca_run.json")


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def _openlca_descriptor(desc: Optional[Any]) -> Dict[str, Any]:
    if desc is None:
        return {}
    return {
        "version": getattr(desc, "version", None),
        "build": getattr(desc, "build", None),
        "java_version": getattr(desc, "java_version", None),
    }


def record(
    port: int,
    database: str,
    method: str,
    provider_names: Optional[Dict[str, str]] = None,
    allocation_basis: Optional[str] = None,
    amount_kg: float = 1000.0,
    openlca_descriptor: Optional[Any] = None,
    result_path: Optional[Path] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "openlca_ipc_port": port,
        "openlca_descriptor": _openlca_descriptor(openlca_descriptor),
        "database_name": database,
        "method": method,
        "allocation_basis": allocation_basis or "use default allocation",
        "functional_unit_kg": amount_kg,
        "providers_linked": provider_names or {},
        "result_path": str(result_path or RESULT_PATH),
    }
    ledger = Path(result_path).with_name("ledger.jsonl") if result_path else LEDGER_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if not ledger.exists():
        ledger.write_text("", encoding="utf-8")
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_ledger(path: Path = LEDGER_PATH) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
