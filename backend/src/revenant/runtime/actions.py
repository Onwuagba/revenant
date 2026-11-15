"""Actions: upstream REST calls with deadline, Idempotency-Key, outcomes.

Outcomes: ok (result fits screen), slow (timeout), long (result too big),
error (upstream failure). Slow/long/202 -> SMS outbox + END.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger("revenant.runtime.actions")

#: Upstream call deadline (3 s — our budget, not a platform fact).
UPSTREAM_DEADLINE = 3.0


class ActionOutcome(str, Enum):
    OK = "ok"
    SLOW = "slow"
    LONG = "long"
    ERROR = "error"
    ASYNC = "async"
    AUTH_FAILED = "auth_failed"


@dataclass
class ActionResult:
    outcome: ActionOutcome
    data: dict[str, Any] | None = None
    error: str = ""
    sms_body: str = ""


def make_idempotency_key(session_id: str, state_id: str, params: dict[str, Any]) -> str:
    """Derive an Idempotency-Key from hash(session, state, params)."""
    raw = f"{session_id}:{state_id}:{sorted(params.items())}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def call_upstream(
    url: str,
    method: str,
    params: dict[str, Any],
    *,
    session_id: str = "",
    state_id: str = "",
    deadline: float = UPSTREAM_DEADLINE,
    http_client: Any = None,
) -> ActionResult:
    """Call an upstream API with a deadline and Idempotency-Key.

    Uses httpx if no client is provided. Returns an ActionResult.
    For testing, pass a mock http_client with a .request method.
    """
    import httpx

    key = make_idempotency_key(session_id, state_id, params)
    headers = {"Idempotency-Key": key, "Content-Type": "application/json"}

    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=deadline)
    try:
        if method.upper() == "GET":
            resp = await client.request(method, url, params=params, headers=headers)
        else:
            resp = await client.request(method, url, json=params, headers=headers)
    except httpx.TimeoutException:
        logger.warning("Upstream timeout for %s", url)
        return ActionResult(outcome=ActionOutcome.SLOW)
    except Exception as exc:
        # Never include str(exc): httpx messages can echo request details.
        logger.warning("Upstream error for %s: %s", url, type(exc).__name__)
        return ActionResult(outcome=ActionOutcome.ERROR, error=type(exc).__name__)

    if own_client:
        await client.aclose()

    # Check for timeout/async
    if resp.status_code == 202:
        return ActionResult(outcome=ActionOutcome.ASYNC)

    if resp.status_code in (401, 403):
        return ActionResult(outcome=ActionOutcome.AUTH_FAILED)

    if resp.status_code >= 500:
        return ActionResult(outcome=ActionOutcome.ERROR, error=f"HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception:
        data = {"text": resp.text}

    # Screen-budget (LONG) decisions are made by the service on the *rendered*
    # text, not on the raw upstream payload.
    return ActionResult(outcome=ActionOutcome.OK, data=data)
