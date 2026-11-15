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
) -> Any:
    """Build a FastAPI app with the USSD callback route.

    Args:
        bundle: the compiled bundle (machine + screens).
        token: the expected callback token (stored hashed).
        store: optional shared store (for multiple bundles). If None, a
            single-bundle store is created.

    Returns a FastAPI app instance.
    """
    if store is None:
        store = InMemoryBundleStore()
        slug = bundle.get("ir", {}).get("slug", "app")
        store.register(slug, bundle, token)
    # Find the slug
    slug = bundle.get("ir", {}).get("slug", "app")

    app = FastAPI()
    setup_redaction(logger)

    @app.post("/ussd/{slug}/{token}", response_class=PlainTextResponse)
    async def ussd_callback(
        slug: str,
        token: str,
        request: Request,
    ) -> Response:
        # Token check
        if not store.verify_token(slug, token):
            return PlainTextResponse("Not found", status_code=404)

        bundle = store.get_bundle(slug)
        if bundle is None:
            return PlainTextResponse("Not found", status_code=404)

        machine_data = bundle.get("machine")
        if machine_data is None:
            return PlainTextResponse("END Service unavailable")

        # Parse form (handle malformed gracefully)
        try:
            form = await request.form()
            session_id = form.get("sessionId", "")
            phone_number = form.get("phoneNumber", "")
            text = form.get("text", "")
        except Exception:
            logger.warning("Malformed USSD form for slug=%s", slug)
            return PlainTextResponse("END An error occurred. Try again later.")

        # Ensure text is a string
        if not isinstance(text, str):
            text = str(text) if text else ""

        # Replay from text to get current state
        state_id, invalid_count = replay(machine_data, text)

        # Check retry limit
        max_retries = machine_data.get("max_retries", 3)
        if invalid_count >= max_retries:
            return PlainTextResponse("END Too many invalid inputs. Try again later.")

        # Determine response
        from ..compiler.planner import TERMINAL_KINDS
        states = machine_data["states"]
        state = states.get(state_id)
        if state is None:
            return PlainTextResponse("END Session ended.")

        if state["kind"] in (k.value for k in TERMINAL_KINDS):
            prefix = END_PREFIX
        else:
            prefix = CON_PREFIX

        response_text = render_response(machine_data, state_id, prefix)
        return PlainTextResponse(response_text)

    # Health check
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
