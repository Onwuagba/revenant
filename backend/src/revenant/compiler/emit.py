"""Emit: assembles the bundle (canonical JSON) and computes bundle_hash.

The bundle contains the IR, machine, screens and validation report.
``bundle_hash = sha256(canonical_json(bundle))`` is deterministic (P6).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .ir import App, canonical_json
from .planner import Machine, plan
from .render import render
from .validators import run_all


def compile_app(app: App, refused_op_ids: set[str] | None = None) -> dict[str, Any]:
    """Full compile pipeline: plan -> render -> validate -> bundle.

    Returns the bundle dict with ``bundle_hash``.
    """
    refused = refused_op_ids or set()
    machine = plan_and_render(app, refused)
    results = run_all(machine, app.operations, refused)

    # Sort operations and flows in the IR dump for canonical determinism (P6)
    ir_dict = app.model_dump(mode="json", by_alias=True)
    ir_dict["operations"] = [
        op.model_dump(mode="json", by_alias=True) for op in app.sorted_operations()
    ]
    ir_dict["flows"] = [
        fl.model_dump(mode="json", by_alias=True) for fl in app.sorted_flows()
    ]

    bundle = {
        "ir": ir_dict,
        "machine": machine.canonical_dict(),
        "screens": _screens_dict(machine),
        "report": {
            "validators": [r.to_dict() for r in results],
            "all_passed": all(r.passed for r in results),
        },
    }
    bundle_bytes = canonical_json(bundle)
    bundle["bundle_hash"] = hashlib.sha256(bundle_bytes).hexdigest()
    return bundle


def plan_and_render(app: App, refused_op_ids: set[str] | None = None) -> Machine:
    """Plan and render an app into a machine with screen details."""
    machine = plan(app, refused_op_ids)
    render(machine, app)
    return machine


def _screens_dict(machine: Machine) -> dict[str, Any]:
    """Extract screen records (states with templates) from the machine."""
    from .planner import SCREEN_KINDS
    screens = {}
    for sid in sorted(machine.states):
        state = machine.states[sid]
        if state.kind in SCREEN_KINDS:
            screens[sid] = {
                "state_id": sid,
                "kind": state.kind.value,
                "template": state.template,
                "slots": [{"name": s.name, "max_len": s.max_len} for s in state.slots],
                "static_len": state.static_len,
                "worst_case_len": state.worst_case_len,
                "transitions": dict(state.transitions),
            }
    return screens


def bundle_hash(bundle: dict[str, Any]) -> str:
    """Compute the sha256 hash of the canonical JSON of a bundle."""
    bundle_copy = {k: v for k, v in bundle.items() if k != "bundle_hash"}
    return hashlib.sha256(canonical_json(bundle_copy)).hexdigest()
