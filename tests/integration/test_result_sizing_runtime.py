"""Runtime result sizing through the real callback route and SMS worker (runtime 3.2, 5.4)."""

import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from revenant.compiler.emit import compile_app
from revenant.compiler.gsm7 import is_gsm7
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.results import segment_count
from revenant.compiler.subset import classify_app
from revenant.runtime.app import build_router

pytestmark = pytest.mark.integration

PHONE = "+2348000000002"


def _bundle(schema):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/items": {
                "get": {
                    "operationId": "list_items",
                    "summary": "List items",
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"schema": schema}},
                        }
                    },
                }
            }
        },
    }
    drafts, _ = ingest_openapi(json.dumps(spec))
    app, _ = classify_app(drafts, slug="items", title="Items")
    bundle = compile_app(app)
    assert bundle["report"]["all_passed"], bundle["report"]
    return bundle


def _env(bundle, payload):
    up = FastAPI()

    @up.get("/items")
    def items():
        return payload

    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=up), base_url="http://up")
    app = build_router(bundle, "tok", upstream_base="http://up", http_client=client)
    return TestClient(app), app


def _call(tc, text):
    r = tc.post(
        "/ussd/items/tok",
        data={"sessionId": "S9", "serviceCode": "*1#", "phoneNumber": PHONE, "text": text},
    )
    assert r.status_code == 200
    return r.text


LIST = {
    "type": "array",
    "maxItems": 4,
    "items": {"type": "object", "properties": {"name": {"type": "string", "maxLength": 20}}},
}


def test_short_list_is_shown_on_screen():
    tc, _ = _env(_bundle(LIST), [{"name": "Ada"}, {"name": "Bo"}])
    out = _call(tc, "1")
    assert out == "END name: Ada\nname: Bo"


LONG_LIST = {**LIST, "maxItems": 8}


def test_long_list_goes_by_sms_lossless_within_budget():
    names = [{"name": f"Clinic number {i:02d} ok"} for i in range(8)]
    tc, app = _env(_bundle(LONG_LIST), names)
    out = _call(tc, "1")
    assert out.startswith("END ") and "SMS" in out
    assert app.state.worker.run_once()["sent"] == 1
    body = app.state.sms_provider.get_inbox(PHONE)[-1]["body"]
    assert is_gsm7(body) and segment_count(body) <= 3
    for n in names:
        assert n["name"][:20] in body  # every item, each field within its declared width


def test_upstream_exceeding_max_items_is_capped_to_the_contract(caplog):
    names = [{"name": f"n{i}"} for i in range(9)]
    tc, _ = _env(_bundle(LIST), names)
    out = _call(tc, "1")
    assert out.count("name: ") == 4
    assert "more than the declared maxItems" in caplog.text


def test_long_text_result_is_cut_to_the_budget_with_a_marker():
    tc, app = _env(_bundle({"type": "string"}), "word " * 400)
    out = _call(tc, "1")
    assert "SMS" in out
    app.state.worker.run_once()
    body = app.state.sms_provider.get_inbox(PHONE)[-1]["body"]
    assert segment_count(body) <= 3 and body.endswith("...")


def test_list_of_scalars_renders_one_per_line():
    tc, _ = _env(_bundle({"type": "array", "items": {"type": "string"}}), ["a", "b"])
    assert _call(tc, "1") == "END a\nb"
