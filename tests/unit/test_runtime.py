"""Tests for runtime: redaction, step/replay, FastAPI callback, SMS (spec 4 tasks 1-4, 10-15)."""

import logging
from pathlib import Path

import pytest
from revenant.compiler.emit import compile_app
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.subset import classify_app
from revenant.runtime.actions import make_idempotency_key
from revenant.runtime.machine import replay, step
from revenant.runtime.redact import (
    RedactFilter,
    redact_dict,
    redact_text,
)
from revenant.runtime.sms import (
    AfricasTalkingSms,
    EmulatorSms,
    ModemSms,
    SmsOutbox,
    build_sms_body,
    count_segments,
    fits_budget,
)


def _compile_clinic():
    raw = Path("examples/specs/clinic.openapi.yaml").read_bytes()
    drafts, _ = ingest_openapi(raw)
    app, report = classify_app(drafts, slug="clinic", title="Clinic Booking")
    return compile_app(app)


# ---------------------------------------------------------------------------
# Task 1: Redaction filter
# ---------------------------------------------------------------------------
class TestRedaction:
    def test_redact_dict(self):
        d = {"text": "1*2*1234", "name": "Alice", "pin": "1234"}
        r = redact_dict(d)
        assert r["text"] == "[REDACTED]"
        assert r["pin"] == "[REDACTED]"
        assert r["name"] == "Alice"

    def test_redact_text(self):
        s = "pin=1234 text=hello"
        r = redact_text(s)
        assert "1234" not in r
        assert "hello" not in r

    def test_logging_filter(self):
        logger = logging.getLogger("test_redact")
        logger.handlers.clear()
        records = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        logger.addHandler(CaptureHandler())
        logger.addFilter(RedactFilter())
        logger.warning("text=secret_data pin=1234")
        msg = records[-1]
        assert "secret_data" not in msg
        assert "1234" not in msg


# ---------------------------------------------------------------------------
# Task 2: Machine step and replay
# ---------------------------------------------------------------------------
class TestMachineStep:
    def test_empty_text_returns_root(self):
        bundle = _compile_clinic()
        machine = bundle["machine"]
        state_id, invalid = replay(machine, "")
        assert state_id == machine["root"]
        assert invalid == 0

    def test_select_first_item(self):
        bundle = _compile_clinic()
        machine = bundle["machine"]
        state_id, _ = replay(machine, "1")
        # First item in root menu
        assert state_id != machine["root"]

    def test_back_navigation(self):
        bundle = _compile_clinic()
        machine = bundle["machine"]
        # Navigate: 1 -> 0 (back to root)
        state_id, _ = replay(machine, "1*0")
        assert state_id == machine["root"]

    def test_home_navigation(self):
        bundle = _compile_clinic()
        machine = bundle["machine"]
        # Navigate: 1 -> 00 (home)
        state_id, _ = replay(machine, "1*00")
        assert state_id == machine["root"]

    def test_invalid_input_stays(self):
        bundle = _compile_clinic()
        machine = bundle["machine"]
        state_id, invalid = replay(machine, "99")
        assert invalid >= 1
        # Stays on root or gets to error after 3
        if invalid < 3:
            assert state_id == machine["root"]

    def test_step_function(self):
        bundle = _compile_clinic()
        machine = bundle["machine"]
        root = machine["root"]
        next_id, prefix = step(machine, root, "1")
        assert next_id != root
        assert prefix in ("CON ", "END ")


# ---------------------------------------------------------------------------
# Task 4: FastAPI callback route
# ---------------------------------------------------------------------------
class TestCallbackRoute:
    def test_root_screen(self):
        import asyncio

        from httpx import ASGITransport, AsyncClient
        from revenant.runtime.app import InMemoryBundleStore, build_router

        bundle = _compile_clinic()
        store = InMemoryBundleStore()
        slug = bundle["ir"]["slug"]
        store.register(slug, bundle, "test-token")
        app = build_router(bundle, "test-token", store=store)

        async def run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/ussd/{slug}/test-token",
                    data={
                        "sessionId": "s1",
                        "serviceCode": "*384#",
                        "phoneNumber": "+2348000000000",
                        "text": "",
                    },
                )
                assert resp.status_code == 200
                assert resp.text.startswith("CON ")

        asyncio.run(run())

    def test_wrong_token_404(self):
        import asyncio

        from httpx import ASGITransport, AsyncClient
        from revenant.runtime.app import InMemoryBundleStore, build_router

        bundle = _compile_clinic()
        store = InMemoryBundleStore()
        slug = bundle["ir"]["slug"]
        store.register(slug, bundle, "correct-token")
        app = build_router(bundle, "correct-token", store=store)

        async def run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/ussd/{slug}/wrong-token",
                    data={"sessionId": "s1", "text": ""},
                )
                assert resp.status_code == 404

        asyncio.run(run())

    def test_malformed_form(self):
        import asyncio

        from httpx import ASGITransport, AsyncClient
        from revenant.runtime.app import InMemoryBundleStore, build_router

        bundle = _compile_clinic()
        store = InMemoryBundleStore()
        slug = bundle["ir"]["slug"]
        store.register(slug, bundle, "test-token")
        app = build_router(bundle, "test-token", store=store)

        async def run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Send malformed content — must get 200, never a stack trace
                resp = await client.post(
                    f"/ussd/{slug}/test-token",
                    content=b"\x00\x01invalid",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                assert resp.status_code == 200
                assert resp.text.startswith("CON ") or resp.text.startswith("END ")

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Tasks 12-15: SMS provider, outbox, segments
# ---------------------------------------------------------------------------
class TestSms:
    def test_emulator_sms(self):
        emu = EmulatorSms()
        ref = emu.send("+2348000000000", "Hello from Revenant")
        assert ref.startswith("emu-")
        inbox = emu.get_inbox("+2348000000000")
        assert len(inbox) == 1
        assert inbox[0]["body"] == "Hello from Revenant"

    def test_modem_sms_raises(self):
        modem = ModemSms()
        with pytest.raises(NotImplementedError):
            modem.send("+234", "test")

    def test_at_sms_no_credentials(self):
        at = AfricasTalkingSms()
        ref = at.send("+234", "test")
        assert ref == "no-credentials"

    def test_count_segments(self):
        assert count_segments("hello") == 1
        assert count_segments("x" * 160) == 1
        assert count_segments("x" * 161) == 2

    def test_fits_budget(self):
        assert fits_budget("hello", 3) is True
        assert fits_budget("x" * 500, 1) is False

    def test_outbox_enqueue(self):
        ob = SmsOutbox()
        entry_id = ob.enqueue("+234", "Test SMS")
        assert entry_id
        pending = ob.claim_pending()
        assert len(pending) == 1
        assert pending[0].msisdn == "+234"

    def test_outbox_mark_sent(self):
        ob = SmsOutbox()
        entry_id = ob.enqueue("+234", "Test SMS")
        ob.mark_sent(entry_id, "ref-123")
        sent = ob.get_sent()
        assert len(sent) == 1
        assert sent[0].provider_ref == "ref-123"

    def test_build_sms_body(self):
        result = {
            "fields": [
                {"path": "code", "label": "Code", "max_len": 8},
                {"path": "time", "label": "Time", "max_len": 20},
            ],
            "template": "Booked {code} {time}",
        }
        body = build_sms_body(result, {"code": "KX42", "time": "Sat 14:30"})
        assert "KX42" in body
        assert "Sat 14:30" in body

    def test_sms_body_gsm7(self):
        result = {"template": "Booked {code}", "fields": []}
        body = build_sms_body(result, {"code": "KX42"})
        from revenant.compiler.gsm7 import is_gsm7

        assert is_gsm7(body), f"SMS body not GSM-7: {body!r}"


# ---------------------------------------------------------------------------
# Task 7: Actions and Idempotency-Key
# ---------------------------------------------------------------------------
class TestActions:
    def test_idempotency_key_deterministic(self):
        key1 = make_idempotency_key("s1", "state1", {"a": 1})
        key2 = make_idempotency_key("s1", "state1", {"a": 1})
        assert key1 == key2

    def test_idempotency_key_differs_by_session(self):
        key1 = make_idempotency_key("s1", "state1", {"a": 1})
        key2 = make_idempotency_key("s2", "state1", {"a": 1})
        assert key1 != key2
