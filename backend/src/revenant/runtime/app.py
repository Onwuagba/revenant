"""FastAPI router factory for USSD callbacks.

``build_router(bundle, deps)`` creates a router that handles AT-shaped
callbacks: ``POST /ussd/{slug}/{token}`` form-encoded, returns ``text/plain``
starting with ``CON `` or ``END ``.

No LLM in the per-screen path (steering tech.md rule 1). The integration suite
must pass with all LLM env vars unset.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Protocol

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import PlainTextResponse

from .machine import replay, step, render_response, get_screen, END_PREFIX, CON_PREFIX
from .redact import setup_redaction

logger = logging.getLogger("revenant.runtime")


class BundleStore(Protocol):
    """Protocol for looking up bundles by slug and verifying tokens."""

    def get_bundle(self, slug: str) -> dict[str, Any] | None: ...
    def verify_token(self, slug: str, token: str) -> bool: ...


class InMemoryBundleStore:
    """Simple in-memory store for testing."""

    def __init__(self) -> None:
        self._bundles: dict[str, dict[str, Any]] = {}
        self._tokens: dict[str, str] = {}

    def register(self, slug: str, bundle: dict[str, Any], token: str) -> None:
        self._bundles[slug] = bundle
        self._tokens[slug] = hashlib.sha256(token.encode()).hexdigest()

    def get_bundle(self, slug: str) -> dict[str, Any] | None:
        return self._bundles.get(slug)

    def verify_token(self, slug: str, token: str) -> bool:
        expected = self._tokens.get(slug)
        if expected is None:
            return False
        return hmac.compare_digest(expected, hashlib.sha256(token.encode()).hexdigest())


def build_router(
    bundle: dict[str, Any],
    token: str,
    *,
    store: InMemoryBundleStore | None = None,
    engine: Any = None,
    upstream_base: str = "",
    http_client: Any = None,
    deployment_id: str = "dep-1",
    sms_provider: Any = None,
) -> Any:
    """Build a FastAPI app with the USSD callback route.

    ``engine`` is a SQLAlchemy engine (in-memory SQLite if omitted). The app
    exposes ``app.state.service``, ``app.state.engine`` and ``app.state.worker``.
    """
    from .service import Deployment, UssdService, ERROR_MSG
    from .sms import EmulatorSms
    from .store import MsisdnCodec, create_all, make_engine
    from .worker import SmsWorker

    if store is None:
        store = InMemoryBundleStore()
        store.register(bundle.get("ir", {}).get("slug", "app"), bundle, token)
    if engine is None:
        engine = make_engine()
    create_all(engine)
    codec = MsisdnCodec()
    service = UssdService(engine=engine, codec=codec, http_client=http_client)
    provider = sms_provider or EmulatorSms()

    app = FastAPI()
    app.state.service = service
    app.state.engine = engine
    app.state.sms_provider = provider
    app.state.worker = SmsWorker(engine, codec, provider)
    setup_redaction(logger)

    @app.post("/ussd/{slug}/{token}", response_class=PlainTextResponse)
    async def ussd_callback(slug: str, token: str, request: Request) -> Response:
        if not store.verify_token(slug, token):
            return PlainTextResponse("Not found", status_code=404)
        bundle_ = store.get_bundle(slug)
        if bundle_ is None or bundle_.get("machine") is None:
            return PlainTextResponse("Not found", status_code=404)
        try:
            form = await request.form()
            session_id = str(form.get("sessionId", "") or "")
            phone = str(form.get("phoneNumber", "") or "")
            text = form.get("text", "")
            text = text if isinstance(text, str) else ""
            if not session_id or not phone:
                raise ValueError("missing fields")
        except Exception:
            logger.warning("Malformed USSD form for slug=%s", slug)
            return PlainTextResponse("END An error occurred. Try again later.")
        dep = Deployment(id=deployment_id, slug=slug, bundle=bundle_, upstream_base=upstream_base)
        try:
            return PlainTextResponse(await service.handle(dep, session_id, phone, text))
        except Exception as exc:  # no stack trace, no input echoed
            logger.error("Callback failed: %s", type(exc).__name__)
            return PlainTextResponse("END " + ERROR_MSG)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def build_emulator_router(bundle: dict[str, Any]) -> Any:
    """Build a router for the emulator (no token needed)."""
    machine_data = bundle.get("machine", {})
    app = FastAPI()
    setup_redaction(logger)

    @app.post("/emulator/input")
    async def emulator_input(request: Request) -> dict[str, Any]:
        import json
        body = await request.json()
        text = body.get("text", "")
        state_id, invalid_count = replay(machine_data, text)
        max_retries = machine_data.get("max_retries", 3)

        if invalid_count >= max_retries:
            return {"type": "END", "text": "Too many invalid inputs."}

        from ..compiler.planner import TERMINAL_KINDS
        states = machine_data["states"]
        state = states.get(state_id)
        if state is None:
            return {"type": "END", "text": "Session ended."}

        if state["kind"] in (k.value for k in TERMINAL_KINDS):
            return {"type": "END", "text": get_screen(machine_data, state_id)}
        return {"type": "CON", "text": get_screen(machine_data, state_id)}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
