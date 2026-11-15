"""Merge annotations onto the draft IR.

Whitelisted effects only: labels, risk, secret=pin, date-window size,
options-from links, hide, sms-only. The merge can never add operations,
transitions or call targets: unknown operation/param ids are ignored, and the
output has exactly the draft's operations. Idempotent (P12).
"""

from __future__ import annotations

from typing import Any

from ..ir import App, OptionsFrom, ParamType, Risk, SecretType
from .schema import validate_annotations


def apply_annotations(app: App, annotations: dict[str, Any]) -> tuple[App, set[str]]:
    """Return (annotated copy of app, hidden operation ids)."""
    validate_annotations(annotations)
    out = app.model_copy(deep=True)
    known = {op.id for op in out.operations}
    hidden: set[str] = set()

    for op in out.operations:
        ann = annotations["operations"].get(op.id)
        if not ann:
            continue
        if "label" in ann:
            op.title = ann["label"]
        if "risk" in ann:
            op.risk = Risk(ann["risk"])
        if ann.get("hide"):
            hidden.add(op.id)
        if ann.get("sms-only"):
            op.async_ = True
        leaves = {p.name: p for p in op.leaf_params()}
        for name, pann in ann.get("params", {}).items():
            p = leaves.get(name)
            if p is None:
                continue
            if "label" in pann:
                p.label = pann["label"]
            if pann.get("secret") == "pin":
                p.secret = SecretType.PIN
            if "date-window" in pann and p.type == ParamType.DATE_WINDOW:
                p.constraints.window = pann["date-window"]
            of = pann.get("options-from")
            if of and of["op_id"] in known and of["op_id"] != op.id:
                p.options_from = OptionsFrom(**of)
    return out, hidden
