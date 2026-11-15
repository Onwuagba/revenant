"""Redaction filter: drops sensitive keys from logs (PIN safety, P9).

The USSD callback field ``text`` (may contain a PIN) MUST NEVER appear in
any log line, exception message, or DB row. This filter drops keys:
text, pin, password, token, authorization.
"""

from __future__ import annotations

import logging
import re
from typing import Any

#: Keys that must never appear in logs.
REDACTED_KEYS = frozenset({"text", "pin", "password", "token", "authorization"})

#: Patterns to redact in string messages.
_REDACT_PATTERNS = [
    re.compile(r"(?i)(pin|password|token|authorization|text)\s*[=:]\s*\S+"),
]

REDACTED = "[REDACTED]"


class RedactFilter(logging.Filter):
    """Logging filter that redacts sensitive keys from records."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact structured extra fields
        for key in list(record.__dict__):
            if key.lower() in REDACTED_KEYS:
                setattr(record, key, REDACTED)

        # Redact the message string
        msg = record.getMessage()
        for pattern in _REDACT_PATTERNS:
            msg = pattern.sub(r"\1=" + REDACTED, msg)
        record.msg = msg
        record.args = ()
        return True


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *data* with sensitive keys replaced by [REDACTED]."""
    return {k: (REDACTED if k.lower() in REDACTED_KEYS else v) for k, v in data.items()}


def redact_text(s: str) -> str:
    """Redact sensitive patterns from a string."""
    for pattern in _REDACT_PATTERNS:
        s = pattern.sub(r"\1=" + REDACTED, s)
    return s


def setup_redaction(logger: logging.Logger | None = None) -> None:
    """Attach the redact filter to a logger (or the root logger)."""
    if logger is None:
        logger = logging.getLogger()
    logger.addFilter(RedactFilter())
