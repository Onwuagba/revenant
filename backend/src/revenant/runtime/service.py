"""USSD callback service: replay, dedupe, actions, PIN safety, SMS fallback.

No LLM anywhere on this path (steering rule 1). The PIN is read from the
replayed ``text`` into memory, passed upstream, and dropped; it is never
logged, stored, or rendered. Sessions store only the state id, step index and
the rendered response.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa

from ..compiler.gsm7 import sanitise_slot
from ..compiler.planner import TERMINAL_KINDS
from .actions import ActionOutcome, ActionResult, call_upstream
from .machine import CON_PREFIX, END_PREFIX, Trace, get_screen, replay_full
from .redact import setup_redaction
from .sms import OutboxLike, build_sms_body
from .store import MsisdnCodec, OptionCache, PinGuard, SessionStore

logger = logging.getLogger("revenant.runtime")
setup_redaction(logger)

#: Screen budget including the CON/END prefix (carrier profile default).
SCREEN_BUDGET = 182

BAD_PIN_MSG = "Could not complete the request. Check your PIN and try again later."
ERROR_MSG = "Service is unavailable. Try again later."
SMS_MSG = "Details will be sent to you by SMS."
TOO_MANY_MSG = "Too many invalid inputs. Try again later."


@dataclass
class Deployment:
    id: str
    slug: str
    bundle: dict[str, Any]
    upstream_base: str = ""
    sms_budget_segments: int = 3
    http_client: Any = None  # per-deployment upstream client (tests/demo use ASGI mocks)
    mcp_call: Any = None  # async (tool, args) -> Any for MCP-sourced operations


@dataclass
class UssdService:
    engine: sa.Engine
    codec: MsisdnCodec = field(default_factory=MsisdnCodec)
    http_client: Any = None
    outbox: OutboxLike | None = None  # in-memory fallback; DB outbox via SqlSmsOutbox

    def __post_init__(self) -> None:
        self.sessions = SessionStore(self.engine)
        self.pins = PinGuard(self.engine)
        self.options = OptionCache(self.engine)
        if self.outbox is None:
            from .worker import SqlSmsOutbox

            self.outbox = SqlSmsOutbox(self.engine, self.codec)

    # -- public ---------------------------------------------------------
    async def handle(self, dep: Deployment, session_id: str, msisdn: str, text: str) -> str:
        """Return the full ``CON ...`` / ``END ...`` response for one callback."""
        step_index = len([s for s in text.split("*") if s != ""]) if text else 0
        mh = self.codec.hmac(msisdn)

        cached = self.sessions.get(session_id)
        if cached and cached["deployment_id"] == dep.id and cached["step_index"] == step_index:
            if cached["msisdn_hmac"] == mh:
                return str(cached["last_response"])  # duplicate callback: no re-execution

        trace = replay_full(dep.bundle, text)
        machine = dep.bundle["machine"]
        states = machine["states"]

        if trace.invalid_count >= machine.get("max_retries", 3):
            response = END_PREFIX + TOO_MANY_MSG
            kind = "too_many_invalid"
        else:
            state = states.get(trace.state_id)
            if state is None:
                response, kind = END_PREFIX + ERROR_MSG, "error"
            elif state["kind"] == "ACTION":
                response, kind = await self._run_action(dep, session_id, msisdn, mh, trace)
            elif state["kind"] in (k.value for k in TERMINAL_KINDS):
                response, kind = END_PREFIX + get_screen(machine, trace.state_id), "terminal"
            else:
                response, kind = CON_PREFIX + get_screen(machine, trace.state_id), "screen"

        self.sessions.put(
            session_id=session_id,
            deployment_id=dep.id,
            msisdn_hmac=mh,
            state_id=trace.state_id,
            step_index=step_index,
            last_response=response,
        )
        self.sessions.event(session_id, step_index, trace.state_id, kind)
        # `trace` (params, pin) goes out of scope here; nothing above stored it.
        return response

    # -- actions --------------------------------------------------------
    async def _run_action(
        self, dep: Deployment, session_id: str, msisdn: str, mh: str, trace: Trace
    ) -> tuple[str, str]:
        op = next((o for o in dep.bundle["ir"]["operations"] if o["id"] == trace.op_id), None)
        if op is None:
            return END_PREFIX + ERROR_MSG, "error"

        has_pin = any(p.get("secret") == "pin" for p in op["params"])
        if has_pin and self.pins.is_locked(mh, dep.id):
            # Identical to the bad-PIN message so lockout is not observable.
            return END_PREFIX + BAD_PIN_MSG, "pin_locked"

        params = dict(trace.params)
        if op["source_ref"].startswith("mcp:"):
            return await self._run_mcp(dep, op, params, msisdn, mh)
        method, _, path = op["source_ref"].partition(" ")
        url = dep.upstream_base.rstrip("/") + path
        if has_pin and trace.pin is not None:
            params["pin"] = trace.pin

        cache_key = ""
        if method == "GET" and not has_pin:
            cache_key = hashlib.sha256(
                f"{dep.id}:{url}:{sorted(params.items())}".encode()
            ).hexdigest()
            hit = self.options.get(cache_key)
            if hit is not None:
                return self._render_result(
                    dep, op, ActionResult(ActionOutcome.OK, json.loads(hit)), msisdn, mh
                )

        result = await call_upstream(
            url,
            method,
            params,
            session_id=session_id,
            state_id=trace.state_id,
            http_client=dep.http_client or self.http_client,
        )
        params.clear()

        if has_pin and result.outcome == ActionOutcome.AUTH_FAILED:
            self.pins.record_failure(mh, dep.id)
            return END_PREFIX + BAD_PIN_MSG, "pin_failed"
        if has_pin and result.outcome == ActionOutcome.OK:
            self.pins.record_success(mh, dep.id)

        if result.outcome == ActionOutcome.OK and cache_key:
            self.options.put(cache_key, json.dumps(result.data))
        return self._render_result(dep, op, result, msisdn, mh)

    async def _run_mcp(
        self, dep: Deployment, op: dict[str, Any], params: dict[str, Any], msisdn: str, mh: str
    ) -> tuple[str, str]:
        if dep.mcp_call is None:
            return END_PREFIX + ERROR_MSG, "upstream_error"
        try:
            raw = await dep.mcp_call(op["source_ref"][4:], params)
        except Exception as exc:
            logger.warning("MCP call failed: %s", type(exc).__name__)
            return END_PREFIX + ERROR_MSG, "upstream_error"
        finally:
            params.clear()
        data = raw if isinstance(raw, (dict, list)) else {"text": str(raw)}
        return self._render_result(dep, op, ActionResult(ActionOutcome.OK, data), msisdn, mh)

    def _render_result(
        self, dep: Deployment, op: dict[str, Any], result: ActionResult, msisdn: str, mh: str
    ) -> tuple[str, str]:
        if result.outcome == ActionOutcome.ERROR:
            return END_PREFIX + ERROR_MSG, "upstream_error"
        if result.outcome in (ActionOutcome.SLOW, ActionOutcome.ASYNC):
            self._queue_sms(dep, msisdn, mh, "Your request is being processed. We will update you.")
            return END_PREFIX + SMS_MSG, "sms_slow"

        fields = op["result"]["fields"]
        data = result.data
        if not fields:  # text-shaped result (e.g. MCP tool without outputSchema)
            txt = sanitise_slot(_dig(data, "text") if isinstance(data, dict) else str(data), 400)
            fields = []
            data = {"_t": txt}
            lines = [txt]
            screen = END_PREFIX + txt
            if len(screen) <= SCREEN_BUDGET:
                return screen, "result"
            self._queue_sms(dep, msisdn, mh, txt)
            return END_PREFIX + SMS_MSG, "sms_long"
        items = data if isinstance(data, list) else [data if isinstance(data, dict) else {}]
        lines = []
        for item in items:
            row = [
                f"{f['label']}: {sanitise_slot(_dig(item, f['path']), f.get('max_len', 40))}"
                for f in fields
            ]
            lines.append("\n".join(row))
        screen = END_PREFIX + "\n".join(lines)
        if len(screen) <= SCREEN_BUDGET and result.outcome != ActionOutcome.LONG:
            return screen, "result"

        body = "\n".join(lines)
        self._queue_sms(dep, msisdn, mh, body)
        return END_PREFIX + SMS_MSG, "sms_long"

    def _queue_sms(self, dep: Deployment, msisdn: str, mh: str, body: str) -> None:
        body = build_sms_body({"template": body.replace("{", "(").replace("}", ")")}, {})
        assert self.outbox is not None  # set in __post_init__
        self.outbox.enqueue(msisdn, body, dep.id)


def _dig(item: Any, path: str) -> str:
    cur = item
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return ""
    return "" if cur is None else str(cur)
