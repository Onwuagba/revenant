"""Unit tests for subset.py — classifier (tasks 5-8).

One test per supported row and per refusal code.
"""

import pytest
from revenant.compiler.ir import (
    DraftOperation,
    DraftParam,
    OpKind,
    ParamType,
    SecretType,
)
from revenant.compiler.refusals import RefusalCode
from revenant.compiler.subset import (
    classify_app,
    classify_operation,
    classify_schema,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def classify(schema, name="p", op_id="op", path="#/p", **kwargs):
    return classify_schema(schema, op_id=op_id, path=path, name=name, **kwargs)


def is_param(result):
    return hasattr(result, "type") and not hasattr(result, "code")


def is_refusal(result):
    return hasattr(result, "code")


# ---------------------------------------------------------------------------
# Task 5: scalar types
# ---------------------------------------------------------------------------
class TestScalarSupported:
    def test_boolean(self):
        r = classify({"type": "boolean"})
        assert is_param(r)
        assert r.type == ParamType.BOOLEAN

    def test_bounded_integer(self):
        r = classify({"type": "integer", "minimum": 0, "maximum": 100})
        assert is_param(r)
        assert r.type == ParamType.NUMERIC
        assert r.constraints.min == 0
        assert r.constraints.max == 100

    def test_bounded_number(self):
        r = classify({"type": "number", "minimum": 0.0, "maximum": 99.99})
        assert is_param(r)
        assert r.type == ParamType.NUMERIC

    def test_enum_string(self):
        r = classify({"type": "string", "enum": ["a", "b", "c"]})
        assert is_param(r)
        assert r.type == ParamType.ENUM_MENU
        assert r.constraints.enum == ["a", "b", "c"]

    def test_enum_at_limit_36(self):
        r = classify({"type": "string", "enum": [str(i) for i in range(36)]})
        assert is_param(r)
        assert r.type == ParamType.ENUM_MENU

    def test_token_with_pattern(self):
        r = classify({"type": "string", "pattern": "^[A-Z0-9]+$"})
        assert is_param(r)
        assert r.type == ParamType.TOKEN
        assert r.constraints.pattern == "^[A-Z0-9]+$"

    def test_token_with_maxlength(self):
        r = classify({"type": "string", "maxLength": 10})
        assert is_param(r)
        assert r.type == ParamType.TOKEN
        assert r.constraints.max_len == 10

    def test_token_maxlength_at_20(self):
        r = classify({"type": "string", "maxLength": 20})
        assert is_param(r)
        assert r.type == ParamType.TOKEN


class TestScalarRefusals:
    def test_unbounded_integer(self):
        r = classify({"type": "integer"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_UNBOUNDED_NUMBER

    def test_integer_with_only_min(self):
        r = classify({"type": "integer", "minimum": 0})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_UNBOUNDED_NUMBER

    def test_integer_with_only_max(self):
        r = classify({"type": "integer", "maximum": 100})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_UNBOUNDED_NUMBER

    def test_free_text_string(self):
        r = classify({"type": "string"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_FREE_TEXT

    def test_free_text_string_maxlen_over_20(self):
        r = classify({"type": "string", "maxLength": 21})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_FREE_TEXT

    def test_number_too_many_digits(self):
        r = classify({"type": "integer", "minimum": 0, "maximum": 10**9})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_UNBOUNDED_NUMBER

    def test_enum_over_36(self):
        r = classify({"type": "string", "enum": [str(i) for i in range(37)]})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_TOO_MANY_PARAMS


# ---------------------------------------------------------------------------
# Task 6: PIN, date window, options-from
# ---------------------------------------------------------------------------
class TestPinDateOptions:
    def test_pin(self):
        r = classify({"type": "string", "x-revenant-secret": "pin", "minLength": 4, "maxLength": 6})
        assert is_param(r)
        assert r.type == ParamType.PIN
        assert r.secret == SecretType.PIN

    def test_date_window(self):
        r = classify({"type": "string", "format": "date", "x-revenant-date-window": 5})
        assert is_param(r)
        assert r.type == ParamType.DATE_WINDOW
        assert r.constraints.window == 5

    def test_date_window_at_limit_7(self):
        r = classify({"type": "string", "format": "date", "x-revenant-date-window": 7})
        assert is_param(r)
        assert r.type == ParamType.DATE_WINDOW

    def test_phone_format(self):
        r = classify({"type": "string", "format": "phone"})
        assert is_param(r)
        assert r.type == ParamType.PHONE
        assert r.default_from == "caller_msisdn"

    def test_options_from(self):
        of = {"op_id": "list_clinics", "value_path": "id", "label_path": "name"}
        r = classify({"type": "string", "x-revenant-options-from": of})
        assert is_param(r)
        assert r.type == ParamType.DYNAMIC_CHOICE
        assert r.options_from is not None
        assert r.options_from.op_id == "list_clinics"


class TestDateRefusals:
    def test_date_without_window(self):
        r = classify({"type": "string", "format": "date"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_DATETIME

    def test_date_window_over_7(self):
        r = classify({"type": "string", "format": "date", "x-revenant-date-window": 8})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_DATETIME

    def test_date_time(self):
        r = classify({"type": "string", "format": "date-time"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_DATETIME

    def test_time_format(self):
        r = classify({"type": "string", "format": "time"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_DATETIME

    def test_duration(self):
        r = classify({"type": "string", "format": "duration"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_DATETIME


# ---------------------------------------------------------------------------
# Task 7: objects, polymorphism, binary, recursion
# ---------------------------------------------------------------------------
class TestObjects:
    def test_flat_object_flattened(self):
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 10},
                "age": {"type": "integer", "minimum": 0, "maximum": 120},
            },
            "required": ["name"],
        }
        r = classify(schema, name="body")
        assert is_param(r)
        assert r.type == ParamType.FLATTENED
        assert r.params is not None
        assert len(r.params) == 2
        assert r.params[0].name == "name"
        assert r.params[0].required is True
        assert r.params[1].name == "age"
        assert r.params[1].required is False

    def test_flat_object_at_6_props(self):
        schema = {
            "type": "object",
            "properties": {f"p{i}": {"type": "boolean"} for i in range(6)},
        }
        r = classify(schema)
        assert is_param(r)
        assert r.type == ParamType.FLATTENED

    def test_nested_object_refused(self):
        schema = {
            "type": "object",
            "properties": {
                "outer": {
                    "type": "object",
                    "properties": {"inner": {"type": "string"}},
                },
            },
        }
        r = classify(schema)
        assert is_refusal(r)
        assert r.code == RefusalCode.R_NESTED_OBJECT

    def test_too_many_object_props(self):
        schema = {
            "type": "object",
            "properties": {f"p{i}": {"type": "boolean"} for i in range(7)},
        }
        r = classify(schema)
        assert is_refusal(r)
        assert r.code == RefusalCode.R_TOO_MANY_PARAMS

    def test_array_of_objects_refused(self):
        r = classify(
            {"type": "array", "items": {"type": "object", "properties": {"x": {"type": "string"}}}}
        )
        assert is_refusal(r)
        assert r.code == RefusalCode.R_NESTED_OBJECT


class TestPolymorphism:
    def test_one_of(self):
        r = classify({"oneOf": [{"type": "string"}, {"type": "integer"}]})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_POLYMORPHIC

    def test_any_of(self):
        r = classify({"anyOf": [{"type": "string"}, {"type": "boolean"}]})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_POLYMORPHIC

    def test_all_of(self):
        r = classify({"allOf": [{"type": "string"}]})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_POLYMORPHIC

    def test_discriminator(self):
        r = classify({"type": "object", "discriminator": {"propertyName": "type"}})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_POLYMORPHIC


class TestBinaryAndCallbacks:
    def test_binary_format(self):
        r = classify({"type": "string", "format": "binary"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_BINARY

    def test_byte_format(self):
        r = classify({"type": "string", "format": "byte"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_BINARY

    def test_callbacks(self):
        r = classify({"callbacks": {"myCallback": {"$ref": "#/components/callbacks/x"}}})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_CALLBACK


class TestRefAndRecursion:
    def test_remote_ref_unresolved(self):
        r = classify({"$ref": "https://example.com/schema.json"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_REF_UNRESOLVED

    def test_local_ref_unresolved(self):
        r = classify({"$ref": "#/components/schemas/Missing"})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_REF_UNRESOLVED

    def test_cyclic_ref(self):
        r = classify({"$ref": "#/a"}, seen_refs=frozenset({"#/a"}))
        assert is_refusal(r)
        assert r.code == RefusalCode.R_RECURSIVE


class TestTotalityNeverRaises:
    """Requirement 3.3: classifier never raises for any input."""

    @pytest.mark.parametrize(
        "schema",
        [
            None,
            True,
            False,
            [],
            {},
            {"type": "unknown"},
            {"type": "string", "enum": "not_a_list"},
            {"type": "object", "properties": None},
            {"type": "integer", "minimum": "abc", "maximum": "xyz"},
            {"$ref": 42},
            {"oneOf": "not_a_list"},
            {"type": "string", "pattern": 123},
            {"type": "string", "enum": ["ok", "\u2764"]},  # non-GSM7 enum value
            {"type": "object", "properties": {f"p{i}": {"type": "string"} for i in range(100)}},
        ],
    )
    def test_never_raises(self, schema):
        result = classify(schema)
        # Must return either a Param or a Refusal, never raise
        assert is_param(result) or is_refusal(result)

    def test_non_gsm7_enum_refused(self):
        r = classify({"type": "string", "enum": ["ok", "\u2764"]})
        assert is_refusal(r)
        assert r.code == RefusalCode.R_NON_GSM7

    def test_deep_nesting_does_not_raise(self):
        schema = {"type": "boolean"}
        for _ in range(100):
            schema = {"type": "object", "properties": {"x": schema}}
        result = classify(schema)
        assert is_refusal(result) or is_param(result)

    def test_pattern_not_executed(self):
        """Requirement 3.6: pattern is never executed at compile time."""
        # A catastrophic-backtracking pattern must not hang
        import time

        start = time.monotonic()
        r = classify({"type": "string", "pattern": "^(a+)+$"})
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, "pattern execution would hang"
        assert is_param(r)
        assert r.type == ParamType.TOKEN


# ---------------------------------------------------------------------------
# Task 8: operation-level classification and refusal report
# ---------------------------------------------------------------------------
class TestClassifyOperation:
    def _draft(self, params=None, id="op1", kind="read", title="Op One", result_schema=None):
        return DraftOperation(
            id=id,
            title=title,
            kind=kind,
            params=params or [],
            result_schema=result_schema,
        )

    def test_all_params_supported(self):
        draft = self._draft(
            params=[
                DraftParam(name="flag", json_schema={"type": "boolean"}),
                DraftParam(
                    name="num", json_schema={"type": "integer", "minimum": 0, "maximum": 10}
                ),
            ]
        )
        result = classify_operation(draft)
        assert not isinstance(result, list)
        assert result.id == "op1"
        assert len(result.params) == 2
        assert result.params[0].type == ParamType.BOOLEAN
        assert result.params[1].type == ParamType.NUMERIC

    def test_one_refused_excludes_whole_operation(self):
        draft = self._draft(
            params=[
                DraftParam(name="ok", json_schema={"type": "boolean"}),
                DraftParam(name="bad", json_schema={"type": "string"}),  # free text
            ]
        )
        result = classify_operation(draft)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].code == RefusalCode.R_FREE_TEXT
        assert result[0].op_id == "op1"

    def test_too_many_required_params_refused(self):
        draft = self._draft(
            params=[
                DraftParam(name=f"p{i}", json_schema={"type": "boolean"}, required=True)
                for i in range(6)
            ]
        )
        result = classify_operation(draft)
        assert isinstance(result, list)
        codes = [r.code for r in result]
        assert RefusalCode.R_TOO_MANY_PARAMS in codes

    def test_flat_object_flattened_in_operation(self):
        draft = self._draft(
            params=[
                DraftParam(
                    name="body",
                    json_schema={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "maxLength": 10},
                            "flag": {"type": "boolean"},
                        },
                        "required": ["name"],
                    },
                ),
            ]
        )
        result = classify_operation(draft)
        assert not isinstance(result, list)
        assert len(result.params) == 2
        assert result.params[0].name == "name"
        assert result.params[1].name == "flag"

    def test_write_kind(self):
        draft = self._draft(
            params=[DraftParam(name="flag", json_schema={"type": "boolean"})],
            kind="write",
        )
        result = classify_operation(draft)
        assert not isinstance(result, list)
        assert result.kind == OpKind.WRITE


class TestClassifyApp:
    def test_mixed_compiled_and_refused(self):
        drafts = [
            DraftOperation(
                id="list_clinics",
                title="List clinics",
                kind="read",
                params=[DraftParam(name="flag", json_schema={"type": "boolean"})],
            ),
            DraftOperation(
                id="broken",
                title="Broken",
                kind="read",
                params=[DraftParam(name="text", json_schema={"type": "string"})],
            ),
        ]
        app, report = classify_app(drafts)
        assert len(app.operations) == 1
        assert app.operations[0].id == "list_clinics"
        assert report["compiled_count"] == 1
        assert report["refused_count"] == 1
        assert "R_FREE_TEXT" in report["per_code"]

    def test_all_refused(self):
        drafts = [
            DraftOperation(
                id="broken",
                title="Broken",
                kind="read",
                params=[DraftParam(name="text", json_schema={"type": "string"})],
            ),
        ]
        app, report = classify_app(drafts)
        assert len(app.operations) == 0
        assert report["compiled_count"] == 0
        assert report["refused_count"] == 1

    def test_report_has_per_code_table(self):
        """Requirement 4.2: report must have per-code table, not just a percentage."""
        drafts = [
            DraftOperation(
                id="free",
                title="Free",
                kind="read",
                params=[DraftParam(name="t", json_schema={"type": "string"})],
            ),
            DraftOperation(
                id="nested",
                title="Nested",
                kind="read",
                params=[
                    DraftParam(
                        name="o",
                        json_schema={
                            "type": "object",
                            "properties": {
                                "inner": {"type": "object", "properties": {"x": {"type": "string"}}}
                            },
                        },
                    )
                ],
            ),
        ]
        _, report = classify_app(drafts)
        assert "per_code" in report
        assert report["per_code"]["R_FREE_TEXT"] == 1
        assert report["per_code"]["R_NESTED_OBJECT"] == 1
        # No single coverage percentage without the table
        assert "coverage" not in report

    def test_refused_op_absent_from_ir(self):
        """Requirement 3.4 / P13: refused op ids absent from IR operations."""
        drafts = [
            DraftOperation(
                id="good",
                title="Good",
                kind="read",
                params=[DraftParam(name="flag", json_schema={"type": "boolean"})],
            ),
            DraftOperation(
                id="bad",
                title="Bad",
                kind="read",
                params=[DraftParam(name="t", json_schema={"type": "string"})],
            ),
        ]
        app, _ = classify_app(drafts)
        op_ids = [op.id for op in app.operations]
        assert "good" in op_ids
        assert "bad" not in op_ids
