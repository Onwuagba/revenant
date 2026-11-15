"""Deterministic heuristic annotator: no network, no key (requirement 2.1)."""

from __future__ import annotations

import re
from typing import Any

from ..gsm7 import transliterate
from ..ir import App, OpKind

_MONEY = re.compile(r"(amount|price|pay|transfer|balance|fee|charge|loan|deposit|withdraw)", re.I)
_IDENTITY = re.compile(r"(nin|bvn|passport|identity|kyc|dob|birth)", re.I)
_VERBS = ("get", "list", "create", "book", "update", "delete", "find", "search", "send", "pay")


def _clean(text: str, limit: int) -> str:
    t = transliterate(re.sub(r"[_\-]+", " ", text)).strip()
    t = re.sub(r"\s+", " ", t)
    if t:
        t = t[0].upper() + t[1:]
    return t[:limit].rstrip() or "Item"


def annotate_deterministic(app: App) -> dict[str, Any]:
    ops: dict[str, Any] = {}
    for op in app.operations:
        blob = " ".join([op.id, op.title] + [p.name for p in op.leaf_params()])
        risk = "low"
        if _IDENTITY.search(blob):
            risk = "identity"
        elif op.kind == OpKind.WRITE and _MONEY.search(blob):
            risk = "money"
        ann: dict[str, Any] = {"label": _clean(op.title or op.id, 24), "risk": risk, "params": {}}
        for p in op.leaf_params():
            ann["params"][p.name] = {"label": _clean(p.name, 20)}
        ops[op.id] = ann
    return {"version": 1, "operations": ops}
