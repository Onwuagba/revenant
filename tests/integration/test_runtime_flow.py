"""Integration: full clinic flow through the callback route with a mock upstream.

Covers dedupe, canary PIN (P9), lockout, SMS fallback, worker, retention and
the no-LLM guarantee (spec runtime-sms tasks 6-16).
"""
import logging
import os
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from examples.clinic_api.server import create_app as create_clinic
from revenant.compiler.emit import compile_app
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.subset import classify_app
from revenant.runtime.app import build_router
from revenant.runtime.store import dump_database

pytestmark = pytest.mark.integration

CANARY = "7391"
LLM_VARS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "KIRO_API_KEY", "GOOGLE_API_KEY"]


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    for v in LLM_VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("CLINIC_DEMO_PIN", CANARY)


@pytest.fixture
def bundle():
    raw = Path("examples/specs/clinic.openapi.yaml").read_bytes()
    drafts, _ = ingest_openapi(raw)
    app, _ = classify_app(drafts, slug="clinic", title="Clinic Booking")
    return compile_app(app)


@pytest.fixture
def env(bundle):
    clinic = create_clinic()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=clinic), base_url="http://clinic")
    app = build_router(bundle, "tok", upstream_base="http://clinic", http_client=client)
    return TestClient(app), clinic, app


def ussd(tc, text, session="S1", phone="+2348000000001"):
    r = tc.post("/ussd/clinic/tok", data={"sessionId": session, "serviceCode": "*384#",
                                          "phoneNumber": phone, "text": text})
    assert r.status_code == 200
    return r.text


def test_root_and_prefixes(env):
    tc, _, _ = env
    assert ussd(tc, "").startswith("CON ")
    assert ussd(tc, "1").startswith("CON ")


def test_list_clinics_end(env):
    tc, _, _ = env
    out = ussd(tc, "2")
    assert out.startswith("END ") and "Ikeja Clinic" in out and len(out) <= 182


def test_wrong_token_and_malformed(env):
    tc, _, _ = env
    assert tc.post("/ussd/clinic/nope", data={"sessionId": "a", "phoneNumber": "1", "text": ""}).status_code == 404
    r = tc.post("/ussd/clinic/tok", content=b"\xff\xfe", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.text.startswith("END ")


def test_booking_success(env):
    tc, clinic, _ = env
    ussd(tc, "1")
    ussd(tc, "1*c1")
    ussd(tc, "1*c1*s1")
    ussd(tc, "1*c1*s1*1")
    out = ussd(tc, f"1*c1*s1*1*{CANARY}")
    assert out.startswith("END ") and "code:" in out
    assert clinic.state.calls.count(("POST", "/appointments")) == 1


def test_duplicate_callback_one_upstream_call(env):
    tc, clinic, _ = env
    text = f"1*c1*s1*1*{CANARY}"
    first = ussd(tc, text)
    second = ussd(tc, text)
    assert first == second
    assert clinic.state.calls.count(("POST", "/appointments")) == 1


def test_canary_pin_never_stored_logged_or_returned(env, caplog):
    tc, _, app = env
    caplog.set_level(logging.DEBUG)
    outs = [ussd(tc, t) for t in ["", "1", "1*c1", "1*c1*s1", "1*c1*s1*1", f"1*c1*s1*1*{CANARY}"]]
    assert all(CANARY not in o for o in outs)
    assert CANARY not in caplog.text
    assert CANARY not in dump_database(app.state.engine)


def test_wrong_pin_lockout_identical_message(env):
    tc, clinic, _ = env
    msgs = []
    for i in range(4):
        msgs.append(ussd(tc, "1*c1*s1*1*1111", session=f"L{i}"))
    assert len(set(msgs)) == 1  # lock message identical to bad-PIN message
    # 4th attempt was blocked before reaching upstream
    assert clinic.state.calls.count(("POST", "/appointments")) == 3
    # even the right PIN is refused while locked
    assert ussd(tc, f"1*c1*s1*1*{CANARY}", session="L9") == msgs[0]


def test_slow_upstream_falls_back_to_sms_and_worker_sends(env):
    tc, clinic, app = env
    clinic.state.mode = "async"
    out = ussd(tc, f"1*c1*s1*1*{CANARY}")
    assert out.startswith("END ") and "SMS" in out
    stats = app.state.worker.run_once()
    assert stats["sent"] == 1
    assert app.state.sms_provider.get_inbox("+2348000000001")


def test_upstream_error_generic(env):
    tc, clinic, _ = env
    clinic.state.mode = "error"
    out = ussd(tc, f"1*c1*s1*1*{CANARY}")
    assert out.startswith("END ") and "boom" not in out


def test_too_many_invalid(env):
    tc, _, _ = env
    assert ussd(tc, "9*9*9").startswith("END ")


def test_worker_rate_limit_and_retry(bundle):
    from revenant.runtime.sms import SmsProvider
    from revenant.runtime.store import MsisdnCodec, create_all, make_engine
    from revenant.runtime.worker import SmsWorker, SqlSmsOutbox

    class Flaky(SmsProvider):
        def __init__(self): self.n = 0
        def send(self, msisdn, body):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("down")
            return f"ref{self.n}"

    eng, codec = make_engine(), MsisdnCodec(b"k")
    create_all(eng)
    ob = SqlSmsOutbox(eng, codec)
    ob.enqueue("+2348000000002", "hello", "d")
    w = SmsWorker(eng, codec, Flaky(), per_msisdn_per_hour=1)
    assert w.run_once()["retry"] == 1
    assert ob.all()[0]["status"] == "pending" and ob.all()[0]["attempts"] == 1


def test_purge(env):
    tc, _, app = env
    ussd(tc, "2")
    from revenant.runtime.store import SessionStore
    out = SessionStore(app.state.engine).purge(sent_sms_older_than=timedelta(seconds=0))
    assert set(out) == {"sessions", "options", "sms"}


def test_alembic_migration_matches_models(tmp_path):
    """Migration creates exactly the tables in store.metadata, with no input columns."""
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config

    from revenant.runtime.store import metadata

    db = tmp_path / "m.db"
    os.environ["REVENANT_DATABASE_URL"] = f"sqlite:///{db}"
    try:
        cfg = Config("backend/alembic.ini")
        cfg.set_main_option("script_location", "backend/migrations")
        command.upgrade(cfg, "head")
    finally:
        os.environ.pop("REVENANT_DATABASE_URL", None)
    insp = sa.inspect(sa.create_engine(f"sqlite:///{db}"))
    assert set(insp.get_table_names()) - {"alembic_version"} == set(metadata.tables)
    for t in metadata.tables:
        cols = {c["name"] for c in insp.get_columns(t)}
        assert not cols & {"pin", "text", "params", "input"}
        assert cols == {c.name for c in metadata.tables[t].columns}
