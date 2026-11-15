"""SMS provider interface and outbox.

SmsProvider: AfricasTalkingSms (sandbox/live), ModemSms (stub), EmulatorSms.
SMS body is GSM-7, split by segment budget (160 single, 153 concatenated).
Compile-time worst case must fit the budget (lossless) or refuse with R_...
"""

from __future__ import annotations

import abc
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..compiler.gsm7 import is_gsm7, septet_count, sanitise_slot, transliterate

logger = logging.getLogger("revenant.runtime.sms")

SINGLE_SEGMENT = 160
CONCAT_SEGMENT = 153


class SmsProvider(abc.ABC):
    """Interface for SMS providers."""

    @abc.abstractmethod
    def send(self, msisdn: str, body: str) -> str:
        """Send an SMS. Returns a provider reference id."""
        ...


class AfricasTalkingSms(SmsProvider):
    """Africa's Talking SMS provider (reads credentials from env only)."""

    def __init__(self) -> None:
        self.username = os.environ.get("AT_USERNAME", "")
        self.api_key = os.environ.get("AT_API_KEY", "")

    def send(self, msisdn: str, body: str) -> str:
        if not self.username or not self.api_key:
            logger.warning("AT credentials not configured")
            return "no-credentials"
        # In a real deployment, this would call the AT API.
        # For the hackathon, we log the intent and return a mock ref.
        logger.info("SMS queued for MSISDN (HMAC prefix hidden)")
        return f"at-{uuid4().hex[:12]}"


class ModemSms(SmsProvider):
    """GSM modem / Android gateway (plan B stub)."""

    def send(self, msisdn: str, body: str) -> str:
        raise NotImplementedError("ModemSms not implemented")


class EmulatorSms(SmsProvider):
    """Writes SMS to an in-memory inbox (shown in the emulator)."""

    def __init__(self) -> None:
        self.inbox: list[dict[str, str]] = []

    def send(self, msisdn: str, body: str) -> str:
        ref = f"emu-{uuid4().hex[:8]}"
        self.inbox.append({"msisdn": msisdn, "body": body, "ref": ref})
        return ref

    def get_inbox(self, msisdn: str) -> list[dict[str, str]]:
        """Return all SMS for a given MSISDN."""
        return [m for m in self.inbox if m["msisdn"] == msisdn]


@dataclass
class SmsOutboxEntry:
    """An SMS queued for sending."""
    id: str = field(default_factory=lambda: str(uuid4()))
    deployment_id: str = ""
    msisdn: str = ""
    body: str = ""
    segments: int = 1
    status: str = "pending"
    attempts: int = 0
    next_attempt_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provider_ref: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def build_sms_body(result: dict[str, Any], values: dict[str, str]) -> str:
    """Build an SMS body from a result template and slot values."""
    template = result.get("sms_template", "") or result.get("template", "")
    if not template:
        fields = result.get("fields", [])
        if fields:
            template = "\n".join(f"{f['label']}: {{{f['path']}}}" for f in fields)
        else:
            template = "Done"

    # Substitute slot values
    body = template
    for name, value in values.items():
        body = body.replace(f"{{{name}}}", sanitise_slot(str(value), 160))

    # Transliterate to GSM-7
    body = transliterate(body)
    return body


def count_segments(body: str) -> int:
    """Count SMS segments: 1 if <= 160 septets, else ceil(septets / 153)."""
    count = septet_count(body)
    if count <= SINGLE_SEGMENT:
        return 1
    return (count + CONCAT_SEGMENT - 1) // CONCAT_SEGMENT


def fits_budget(body: str, max_segments: int) -> bool:
    """Check if an SMS body fits within the segment budget."""
    return count_segments(body) <= max_segments


class SmsOutbox:
    """In-memory SMS outbox for testing."""

    def __init__(self) -> None:
        self._entries: list[SmsOutboxEntry] = []

    def enqueue(self, msisdn: str, body: str, deployment_id: str = "") -> str:
        segments = count_segments(body)
        entry = SmsOutboxEntry(
            deployment_id=deployment_id,
            msisdn=msisdn,
            body=body,
            segments=segments,
            status="pending",
        )
        self._entries.append(entry)
        return entry.id

    def claim_pending(self) -> list[SmsOutboxEntry]:
        """Return pending entries (simulates FOR UPDATE SKIP LOCKED)."""
        return [e for e in self._entries if e.status == "pending"]

    def mark_sent(self, entry_id: str, provider_ref: str) -> None:
        for e in self._entries:
            if e.id == entry_id:
                e.status = "sent"
                e.provider_ref = provider_ref
                break

    def get_all(self) -> list[SmsOutboxEntry]:
        return list(self._entries)

    def get_sent(self) -> list[SmsOutboxEntry]:
        return [e for e in self._entries if e.status == "sent"]
