"""Refusal codes and Refusal model.

Exactly 12 refusal codes. A Refusal is a typed result for unsupported shapes;
the compiler never raises on weird input (P7). Source of truth:
``architecture/IR_AND_TYPE_SUBSET.md`` section 4.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class RefusalCode(str, Enum):
    """The 12 refusal codes — never extended without updating IR_AND_TYPE_SUBSET.md."""

    R_NESTED_OBJECT = "R_NESTED_OBJECT"
    R_POLYMORPHIC = "R_POLYMORPHIC"
    R_FREE_TEXT = "R_FREE_TEXT"
    R_DATETIME = "R_DATETIME"
    R_UNBOUNDED_NUMBER = "R_UNBOUNDED_NUMBER"
    R_TOO_MANY_PARAMS = "R_TOO_MANY_PARAMS"
    R_BINARY = "R_BINARY"
    R_AUTH_SCHEME = "R_AUTH_SCHEME"
    R_CALLBACK = "R_CALLBACK"
    R_NON_GSM7 = "R_NON_GSM7"
    R_REF_UNRESOLVED = "R_REF_UNRESOLVED"
    R_RECURSIVE = "R_RECURSIVE"


#: Human-readable hints for each code.
HINTS: dict[RefusalCode, str] = {
    RefusalCode.R_NESTED_OBJECT: "Flatten nested objects into separate parameters or use a list endpoint.",
    RefusalCode.R_POLYMORPHIC: "Provide separate operations for each variant instead of oneOf/anyOf/allOf.",
    RefusalCode.R_FREE_TEXT: "Add an enum, pattern, or maxLength<=20 to constrain free-text input.",
    RefusalCode.R_DATETIME: "Use format 'date' with x-revenant-date-window N (N<=7) for a day picker.",
    RefusalCode.R_UNBOUNDED_NUMBER: "Add both minimum and maximum (at most 9 digits) to bound the number.",
    RefusalCode.R_TOO_MANY_PARAMS: "Reduce required parameters to at most 5 per flow.",
    RefusalCode.R_BINARY: "Binary/byte/multipart inputs are not supported on feature phones.",
    RefusalCode.R_AUTH_SCHEME: "Use a server-held API key or bearer token, not per-user OAuth/OIDC.",
    RefusalCode.R_CALLBACK: "Webhooks, callbacks and streaming are not supported over USSD.",
    RefusalCode.R_NON_GSM7: "Transliterate to GSM-7 safe characters or shorten the label/value.",
    RefusalCode.R_REF_UNRESOLVED: "Inline the schema or add the host to the ref allowlist.",
    RefusalCode.R_RECURSIVE: "Remove the cycle or cap recursion depth in the schema.",
}

#: Messages describing each code.
MESSAGES: dict[RefusalCode, str] = {
    RefusalCode.R_NESTED_OBJECT: "Nested object or array of objects in input.",
    RefusalCode.R_POLYMORPHIC: "Polymorphic schema (oneOf/anyOf/allOf/discriminator).",
    RefusalCode.R_FREE_TEXT: "Unconstrained string without enum, pattern, or maxLength<=20.",
    RefusalCode.R_DATETIME: "date-time, time, duration, or date without a window annotation.",
    RefusalCode.R_UNBOUNDED_NUMBER: "Number or integer without both minimum and maximum.",
    RefusalCode.R_TOO_MANY_PARAMS: "Operation would exceed the step cap (max 5 required params).",
    RefusalCode.R_BINARY: "Binary, byte, or multipart input.",
    RefusalCode.R_AUTH_SCHEME: "Per-user OAuth/OIDC auth scheme.",
    RefusalCode.R_CALLBACK: "Webhook, callback, or streaming endpoint.",
    RefusalCode.R_NON_GSM7: "Label or enum value cannot be transliterated to GSM-7.",
    RefusalCode.R_REF_UNRESOLVED: "Remote or missing $ref.",
    RefusalCode.R_RECURSIVE: "Cyclic or excessively deep schema.",
}


class Refusal(BaseModel):
    """A typed refusal for an unsupported schema shape."""

    model_config = ConfigDict(extra="forbid")

    op_id: str
    path: str
    code: RefusalCode
    message: str
    hint: str

    @classmethod
    def make(
        cls,
        op_id: str,
        path: str,
        code: RefusalCode,
        *,
        message: str = "",
        hint: str = "",
    ) -> Refusal:
        """Create a Refusal with default message and hint for the code."""
        return cls(
            op_id=op_id,
            path=path,
            code=code,
            message=message or MESSAGES[code],
            hint=hint or HINTS[code],
        )
