"""Validator MCP server: ``python -m revenant.mcp_validator``.

Exposes exactly three tools: ``validate_draft``, ``explain_violation`` and
``list_limits``. No shell, file-write or network tools. Reads ``ir.draft.json``
from the working directory (the run dir).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from ..compiler.annotate.merge import apply_annotations
from ..compiler.annotate.schema import AnnotationError, schema_errors
from ..compiler.emit import compile_app
from ..compiler.ir import App

DRAFT_FILE = "ir.draft.json"

EXPLANATIONS = {
    "reachability": "Every state must be reachable from root. Shorten the root menu or "
    "remove hidden dependencies.",
    "exits": "Every state needs a way out (back, home or terminal).",
    "back": "Global keys: 0 is back, 00 is home on every non-root screen.",
    "steps": "A flow may take at most max_steps (8) inputs; hide or simplify the operation.",
    "length": "Screens must fit 182 characters including CON/END and use GSM-7 only. "
    "Shorten labels.",
    "pin": "PIN must be the last input before the action and is never echoed.",
    "sms": "SMS bodies must be GSM-7 and fit the segment budget (160 single, 153 concatenated).",
    "refusal_soundness": "Refused operations must not appear in the machine.",
}

LIMITS = {
    "max_chars": 182,
    "max_steps": 8,
    "op_title_max": 24,
    "param_label_max": 20,
    "root_menu_max": 7,
    "sms_segments": 3,
    "charset": "gsm7",
}


def validate_draft_impl(
    annotations: dict[str, Any], draft_path: str = DRAFT_FILE
) -> dict[str, Any]:
    errs = schema_errors(annotations)
    if errs:
        return {"ok": False, "stage": "schema", "violations": errs[:10]}
    app = App.model_validate(json.loads(Path(draft_path).read_text()))
    try:
        annotated, hidden = apply_annotations(app, annotations)
        bundle = compile_app(annotated, hidden)
    except (AnnotationError, ValueError) as exc:
        return {"ok": False, "stage": "merge", "violations": [str(exc)[:300]]}
    violations = [
        {"validator": r["validator"], **v}
        for r in bundle["report"]["validators"]
        if not r["passed"]
        for v in r["violations"]
    ]
    return {"ok": not violations, "stage": "validators", "violations": violations[:20]}


def build_server() -> MCPServer:
    server = MCPServer(
        name="revenant-validator",
        version="1.0.0",
        description="Run the real Revenant validators on a draft with annotations.",
    )

    @server.tool(description="Validate annotations against the schema and the real validators.")
    def validate_draft(annotations: dict[str, Any]) -> dict[str, Any]:
        return validate_draft_impl(annotations)

    @server.tool(description="Explain what a validator checks and how to fix it.")
    def explain_violation(validator: str) -> str:
        return EXPLANATIONS.get(
            validator, "Unknown validator. Known: " + ", ".join(sorted(EXPLANATIONS))
        )

    @server.tool(description="List carrier and label limits.")
    def list_limits() -> dict[str, Any]:
        return LIMITS

    return server


def main() -> None:
    build_server().run(transport="stdio")
