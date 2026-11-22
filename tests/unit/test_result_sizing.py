"""V7 and result sizing (state-machine-validators 3.7, runtime 5.4)."""

import json

from revenant.compiler.emit import compile_app
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.results import (
    format_items,
    segment_count,
    septet_budget,
    truncate_to_septets,
    worst_case_body,
)
from revenant.compiler.subset import classify_app


def _spec(result_schema):
    return json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/r": {
                    "get": {
                        "operationId": "get_r",
                        "summary": "Get",
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {"application/json": {"schema": result_schema}},
                            }
                        },
                    }
                }
            },
        }
    )


def _compile(result_schema):
    drafts, _ = ingest_openapi(_spec(result_schema))
    app, _ = classify_app(drafts)
    return app, compile_app(app)


def _v7(bundle):
    return next(v for v in bundle["report"]["validators"] if v["validator"] == "V7_sms")


def _list(n_items, width, fields=("a", "b")):
    props = {f: {"type": "string", "maxLength": width} for f in fields}
    schema = {"type": "array", "items": {"type": "object", "properties": props}}
    if n_items is not None:
        schema["maxItems"] = n_items
    return schema


class TestClassifierReadsBounds:
    def test_field_widths_from_schema(self):
        schema = {
            "type": "object",
            "properties": {
                "s": {"type": "string", "maxLength": 7},
                "e": {"type": "string", "enum": ["ok", "failed"]},
                "n": {"type": "integer"},
                "b": {"type": "boolean"},
                "d": {"type": "string", "format": "date"},
                "free": {"type": "string"},
            },
        }
        app, _ = _compile(schema)
        widths = {f.path: f.max_len for f in app.operations[0].result.fields}
        assert widths == {"s": 7, "e": 6, "n": 24, "b": 5, "d": 10, "free": None}

    def test_list_max_items(self):
        app, _ = _compile(_list(4, 8))
        assert app.operations[0].result.max_items == 4


class TestV7:
    def test_bounded_list_within_budget_passes(self):
        _, b = _compile(_list(3, 10))
        assert _v7(b)["passed"]

    def test_list_without_max_items_is_flagged(self):
        _, b = _compile(_list(None, 10))
        v = _v7(b)
        assert not v["passed"]
        assert any("maxItems" in x["message"] for x in v["violations"])

    def test_field_without_max_length_is_flagged(self):
        schema = {"type": "object", "properties": {"note": {"type": "string"}}}
        _, b = _compile(schema)
        v = _v7(b)
        assert not v["passed"]
        assert any("'note'" in x["message"] for x in v["violations"])

    def test_worst_case_over_segment_budget_is_flagged_with_measured_segments(self):
        _, b = _compile(_list(20, 20))
        v = _v7(b)
        assert not v["passed"]
        over = [x for x in v["violations"] if x["measured"]]
        assert over and over[0]["measured"] > 3

    def test_text_result_is_not_a_violation(self):
        _, b = _compile({"type": "string"})
        assert _v7(b)["passed"]


class TestFormatter:
    def test_worst_case_body_is_the_longest_real_output(self):
        app, _ = _compile(_list(3, 6))
        result = app.operations[0].result
        worst = worst_case_body(result)
        real = format_items(
            [f.model_dump() for f in result.fields],
            [{"a": "€" * 50, "b": "x" * 50}] * 3,  # over-long values are cut to the field width
        )
        assert len(real) <= len(worst)

    def test_truncate_to_septets_marks_the_cut(self):
        out = truncate_to_septets("x" * 500, septet_budget(1))
        assert out.endswith("...") and segment_count(out) == 1
        assert truncate_to_septets("short", 160) == "short"

    def test_septet_budget(self):
        assert [septet_budget(n) for n in (1, 2, 3)] == [160, 306, 459]
