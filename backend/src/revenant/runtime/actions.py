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

    client = http_client or httpx.AsyncClient(timeout=deadline)
    try:
        resp = await client.request(method, url, json=params, headers=headers)
    except Exception as exc:
        logger.warning("Upstream error for %s: %s", url, type(exc).__name__)
        return ActionResult(outcome=ActionOutcome.ERROR, error=str(exc))

    # Check for timeout/async
    if resp.status_code == 202:
        return ActionResult(outcome=ActionOutcome.ASYNC)

    if resp.status_code >= 500:
        return ActionResult(outcome=ActionOutcome.ERROR, error=f"HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception:
        data = {"text": resp.text}

    # Check if result is too long for a screen (simplified)
    result_str = str(data)
    if len(result_str) > 178:  # body budget
        return ActionResult(outcome=ActionOutcome.LONG, data=data,
                            sms_body=str(data)[:1000])

    return ActionResult(outcome=ActionOutcome.OK, data=data)
