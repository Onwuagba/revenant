"""Canonical IR models and serialisation.

Source-independent typed IR. Pydantic v2 models with length limits
(Operation title <= 24, Param label <= 20). ``canonical_json`` emits
sorted-key JSON with operations ordered by id so two IRs differing only
in order serialise to identical bytes (P6).

Source of truth: ``architecture/IR_AND_TYPE_SUBSET.md`` section 2.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .refusals import Refusal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ParamType(str, Enum):
    BOOLEAN = "boolean"
    ENUM_MENU = "enum_menu"
    NUMERIC = "numeric"
    TOKEN = "token"
    PHONE = "phone"
    DATE_WINDOW = "date_window"
    PIN = "pin"
    DYNAMIC_CHOICE = "dynamic_choice"
    FLATTENED = "flattened"


class SecretType(str, Enum):
    NONE = "none"
    PIN = "pin"


class OpKind(str, Enum):
    READ = "read"
    WRITE = "write"


class Risk(str, Enum):
    LOW = "low"
    MONEY = "money"
    IDENTITY = "identity"


class ResultShape(str, Enum):
    SCALAR = "scalar"
    RECORD = "record"
    LIST = "list"
    TEXT = "text"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------
class ParamConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enum: list[str] | None = None
    min: float | int | None = None
    max: float | int | None = None
    max_len: int | None = None
    pattern: str | None = None
    window: int | None = None  # for date_window params


class OptionsFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op_id: str
    value_path: str
    label_path: str


class Param(BaseModel):
    """A single input parameter (or flattened group)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str
    type: ParamType
    required: bool = True
    constraints: ParamConstraints = Field(default_factory=ParamConstraints)
    secret: SecretType = SecretType.NONE
    options_from: OptionsFrom | None = None
    default_from: str | None = None
    # Sub-params for flattened objects (type == FLATTENED).
    params: list[Param] | None = None

    @field_validator("label")
    @classmethod
    def label_length(cls, v: str) -> str:
        if len(v) > 20:
            raise ValueError(f"Param label exceeds 20 chars ({len(v)}): {v[:20]!r}...")
        return v

    def expand(self) -> list[Param]:
        """Return a flat list of leaf params (expands flattened groups)."""
        if self.type == ParamType.FLATTENED and self.params:
            result: list[Param] = []
            for sub in self.params:
                result.extend(sub.expand())
            return result
        return [self]


class ResultField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    label: str
    max_len: int = 40


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shape: ResultShape = ResultShape.TEXT
    fields: list[ResultField] = Field(default_factory=list)
    template: str = ""
    sms_template: str = ""


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    source_ref: str = ""
    kind: OpKind = OpKind.READ
    title: str
    params: list[Param] = Field(default_factory=list)
    result: Result = Field(default_factory=Result)
    async_: bool = Field(default=False, alias="async")
    risk: Risk = Risk.LOW

    @field_validator("title")
    @classmethod
    def title_length(cls, v: str) -> str:
        if len(v) > 24:
            raise ValueError(f"Operation title exceeds 24 chars ({len(v)}): {v[:24]!r}...")
        return v

    def leaf_params(self) -> list[Param]:
        """Return expanded leaf params (flattening any FLATTENED groups)."""
        result: list[Param] = []
        for p in self.params:
            result.extend(p.expand())
        return result


class Flow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    entry_op: str
    steps: list[str] = Field(default_factory=list)
    confirm: bool = False


class CarrierProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_chars: int = 182
    max_steps: int = 8
    sms_segments: int = 3
    charset: str = "gsm7"


class App(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    locale: str = "en"
    carrier_profile: CarrierProfile = Field(default_factory=CarrierProfile)
    operations: list[Operation] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)

    def sorted_operations(self) -> list[Operation]:
        """Operations ordered by id for canonical serialisation."""
        return sorted(self.operations, key=lambda op: op.id)

    def sorted_flows(self) -> list[Flow]:
        """Flows ordered by id for canonical serialisation."""
        return sorted(self.flows, key=lambda fl: fl.id)


# ---------------------------------------------------------------------------
# Draft models (pre-classification, produced by ingest)
# ---------------------------------------------------------------------------
class DraftParam(BaseModel):
    """A parameter before classification (from OpenAPI/MCP ingest)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    json_schema: dict[str, Any] = Field(default_factory=dict)
    required: bool = True
    in_location: str = ""  # path, query, header, body


class DraftOperation(BaseModel):
    """An operation before classification (from OpenAPI/MCP ingest)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_ref: str = ""
    kind: OpKind = OpKind.READ
    title: str
    params: list[DraftParam] = Field(default_factory=list)
    result_schema: dict[str, Any] | None = None
    risk: Risk = Risk.LOW
    async_: bool = False
    #: True when the id was generated from method+path (spec had no operationId).
    id_generated: bool = False
    #: Refusals found while ingesting this operation; the classifier excludes the operation.
    refusals: list[Refusal] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------
def _prepare_for_canonical(obj: Any) -> Any:
    """Recursively prepare an object for canonical JSON dump."""
    if isinstance(obj, BaseModel):
        data = obj.model_dump(mode="json", by_alias=True)
        if isinstance(obj, App):
            data["operations"] = [_prepare_for_canonical(op) for op in obj.sorted_operations()]
            data["flows"] = [_prepare_for_canonical(fl) for fl in obj.sorted_flows()]
        else:
            data = _prepare_for_canonical(data)
        return data
    if isinstance(obj, dict):
        return {k: _prepare_for_canonical(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_prepare_for_canonical(v) for v in obj]
    return obj


def canonical_json(obj: Any) -> bytes:
    """Serialise to canonical JSON: sorted keys, operations ordered by id.

    Two IRs that differ only in operation order or key order produce
    identical bytes (requirement 1.2, 1.3; PBT P6).
    """
    prepared = _prepare_for_canonical(obj)
    return json.dumps(
        prepared,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
