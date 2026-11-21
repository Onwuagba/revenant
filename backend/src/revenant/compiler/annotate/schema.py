"""Annotation contract: load and validate ``annotations.schema.json``.

Annotations are untrusted data. Nothing touches them before this check.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import jsonschema

SCHEMA_PATH = Path(__file__).with_name("annotations.schema.json")

#: Whitelisted keys (requirement 1.1).
ALLOWED_KEYS = frozenset(
    {"label", "secret", "date-window", "options-from", "interpret", "risk", "hide", "sms-only"}
)


class AnnotationError(ValueError):
    """Annotations failed the schema."""


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
    return schema


def schema_errors(annotations: Any) -> list[str]:
    validator = jsonschema.Draft202012Validator(load_schema())
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(annotations), key=lambda e: list(e.absolute_path))
    ]


def validate_annotations(annotations: Any) -> dict[str, Any]:
    errs = schema_errors(annotations)
    if errs:
        raise AnnotationError("; ".join(errs[:5]))
    return cast(dict[str, Any], annotations)
