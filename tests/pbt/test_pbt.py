"""Property-based tests for the compiler core.

P7 (totality) and P13 (refusal soundness) from docs/TESTING.md.
Run with: pytest -m pbt --hypothesis-profile=dev -x
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from revenant.compiler.ir import ParamType
from revenant.compiler.refusals import RefusalCode
from revenant.compiler.subset import classify_app, classify_schema

from .strategies import (
    st_any_schema,
    st_app,
    st_deep_nested_schema,
)


# ---------------------------------------------------------------------------
# P7: Totality — any JSON Schema either maps to a supported Param or yields a
# Refusal with a known code; never raises.
# ---------------------------------------------------------------------------
@pytest.mark.pbt
class TestP7Totality:
    """P7: Totality: any JSON Schema either maps to a supported Param or yields
    a Refusal with a known code; never raises."""

    @given(schema=st_any_schema)
    @settings(max_examples=50)
    def test_any_schema_returns_param_or_refusal(self, schema):
        result = classify_schema(schema, op_id="pbt", path="#/test", name="test")
        # Must be either a Param (has .type) or a Refusal (has .code)
        if hasattr(result, "code"):
            assert isinstance(result.code, RefusalCode)
        else:
            assert hasattr(result, "type")
            assert isinstance(result.type, ParamType)

    @given(schema=st_deep_nested_schema())
    @settings(max_examples=20)
    def test_deep_nesting_never_raises(self, schema):
        result = classify_schema(schema, op_id="pbt", path="#/test", name="test")
        assert hasattr(result, "type") or hasattr(result, "code")

    def test_empty_schema_does_not_raise(self):
        result = classify_schema({}, op_id="pbt", path="#/test", name="test")
        assert hasattr(result, "type") or hasattr(result, "code")

    def test_none_schema_does_not_raise(self):
        result = classify_schema(None, op_id="pbt", path="#/test", name="test")
        assert hasattr(result, "code")

    def test_malformed_schema_does_not_raise(self):
        for bad in [
            None,
            True,
            False,
            [],
            {"type": "unknown"},
            {"type": "string", "enum": "not_a_list"},
            {"$ref": 42},
        ]:
            result = classify_schema(bad, op_id="pbt", path="#/test", name="test")
            assert hasattr(result, "type") or hasattr(result, "code")


# ---------------------------------------------------------------------------
# P13: Refusal soundness — refused ops never appear in IR operations
# (stub at the IR layer; extended to machine/screens in state-machine-validators
# task 12).
# ---------------------------------------------------------------------------
@pytest.mark.pbt
class TestP13RefusalSoundness:
    """P13: Refusal soundness: refused ops never appear in machine or screens.

    This stub checks the IR layer: refused op ids are absent from
    App.operations. Extended to machine/screens when the planner exists.
    """

    @given(drafts=st_app())
    @settings(max_examples=50)
    def test_refused_ops_absent_from_ir(self, drafts):
        app, report = classify_app(drafts)
        compiled_ids = {op.id for op in app.operations}
        # Every op that had a refusal must NOT be in the compiled set
        for refusal_entry in report["refusals"]:
            assert refusal_entry["op_id"] not in compiled_ids, (
                f"Refused op {refusal_entry['op_id']} appeared in compiled operations"
            )
        # Consistency: compiled_count matches actual operations
        assert report["compiled_count"] == len(app.operations)

    def test_known_refused_code_stubs(self):
        """P13 stub: a single refused op is absent from IR."""
        from revenant.compiler.ir import DraftOperation, DraftParam

        drafts = [
            DraftOperation(
                id="good_op",
                title="Good Op",
                kind="read",
                params=[DraftParam(name="flag", json_schema={"type": "boolean"})],
            ),
            DraftOperation(
                id="bad_op",
                title="Bad Op",
                kind="read",
                params=[DraftParam(name="text", json_schema={"type": "string"})],
            ),
        ]
        app, report = classify_app(drafts)
        compiled_ids = {op.id for op in app.operations}
        assert "good_op" in compiled_ids
        assert "bad_op" not in compiled_ids
