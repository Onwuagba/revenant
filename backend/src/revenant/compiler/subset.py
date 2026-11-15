"""Type classifier: maps JSON Schema to a supported Param or a typed Refusal.

A *total* function: any input yields a supported Param or a Refusal with a
known code — never raises (P7). Patterns are never executed at compile time
(requirement 3.6). Source of truth: ``architecture/IR_AND_TYPE_SUBSET.md``
section 3–4.
"""

from __future__ import annotations

from typing import Any, TypedDict

from .gsm7 import is_gsm7
from .ir import (
    App,
    DraftOperation,
    DraftParam,
    OpKind,
    Operation,
    OptionsFrom,
    Param,
    ParamConstraints,
    ParamType,
    Result,
    ResultField,
    ResultShape,
    Risk,
    SecretType,
)
from .refusals import Refusal, RefusalCode

#: Max required leaf params per operation (step cap leaves room for menu/confirm/PIN).
MAX_REQUIRED_PARAMS = 5

#: Max properties in a flat object.
MAX_FLAT_OBJECT_PROPS = 6

#: Max enum values for a paginated menu.
MAX_ENUM_VALUES = 36

#: Max digits in a bounded number.
MAX_NUMBER_DIGITS = 9

#: Default recursion depth cap.
DEFAULT_DEPTH_LIMIT = 20


def _make_param(
    name: str,
    ptype: ParamType,
    *,
    label: str | None = None,
    required: bool = True,
    constraints: ParamConstraints | None = None,
    secret: SecretType = SecretType.NONE,
    options_from: OptionsFrom | None = None,
    default_from: str | None = None,
    params: list[Param] | None = None,
) -> Param:
    """Build a Param, deriving a safe label from the name if none given."""
    lbl = label if label is not None else name[:20]
    return Param(
        name=name,
        label=lbl,
        type=ptype,
        required=required,
        constraints=constraints or ParamConstraints(),
        secret=secret,
        options_from=options_from,
        default_from=default_from,
        params=params,
    )


def classify_schema(
    schema: Any,
    *,
    op_id: str,
    path: str,
    name: str = "",
    depth_limit: int = DEFAULT_DEPTH_LIMIT,
    seen_refs: frozenset[str] | None = None,
) -> Param | Refusal:
    """Classify a JSON Schema into a supported Param or a typed Refusal.

    Never raises (P7). Handles cyclic, deeply nested, and malformed schemas
    gracefully.
    """
    if seen_refs is None:
        seen_refs = frozenset()
    try:
        return _classify(
            schema,
            op_id=op_id,
            path=path,
            name=name,
            depth=depth_limit,
            seen=seen_refs,
        )
    except Exception:  # noqa: BLE001 — total function, never raises (P7)
        return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)


def _classify(
    schema: Any,
    *,
    op_id: str,
    path: str,
    name: str,
    depth: int,
    seen: frozenset[str],
) -> Param | Refusal:
    # --- Depth cap -------------------------------------------------------
    if depth <= 0:
        return Refusal.make(op_id, path, RefusalCode.R_RECURSIVE)

    # --- Non-dict schemas (None, bool, list, malformed) ------------------
    if schema is None or isinstance(schema, bool):
        # OpenAPI boolean schema: True = any type, False = no type.
        # Neither is a constrained input we can render.
        return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)
    if not isinstance(schema, dict):
        return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)

    # --- $ref handling ----------------------------------------------------
    ref = schema.get("$ref")
    if ref is not None:
        if ref in seen:
            return Refusal.make(op_id, path, RefusalCode.R_RECURSIVE)
        if not ref.startswith("#"):
            return Refusal.make(op_id, path, RefusalCode.R_REF_UNRESOLVED)
        # Local ref should have been resolved by the resolver. If still
        # present, it is unresolved (cycle or missing target).
        return Refusal.make(op_id, path, RefusalCode.R_REF_UNRESOLVED)

    # --- Polymorphism ----------------------------------------------------
    for key in ("oneOf", "anyOf", "allOf"):
        if key in schema:
            return Refusal.make(op_id, path, RefusalCode.R_POLYMORPHIC)
    if "discriminator" in schema:
        return Refusal.make(op_id, path, RefusalCode.R_POLYMORPHIC)

    # --- Callbacks / webhooks (OpenAPI) -----------------------------------
    if "callbacks" in schema:
        return Refusal.make(op_id, path, RefusalCode.R_CALLBACK)

    # --- Vendor extensions -----------------------------------------------
    x_secret = schema.get("x-revenant-secret")
    x_options_from = schema.get("x-revenant-options-from")
    x_date_window = schema.get("x-revenant-date-window")

    # PIN must be checked early (it's a string with a secret annotation).
    if x_secret == "pin":
        return _make_param(
            name, ParamType.PIN,
            secret=SecretType.PIN,
            constraints=ParamConstraints(
                min=schema.get("minLength"),
                max=schema.get("maxLength"),
            ),
        )

    # Dynamic choice (options-from).
    if x_options_from is not None and isinstance(x_options_from, dict):
        of = OptionsFrom(
            op_id=x_options_from.get("op_id", ""),
            value_path=x_options_from.get("value_path", ""),
            label_path=x_options_from.get("label_path", ""),
        )
        return _make_param(name, ParamType.DYNAMIC_CHOICE, options_from=of)

    # --- Type dispatch ---------------------------------------------------
    type_ = schema.get("type")
    fmt = schema.get("format", "")

    # Boolean --------------------------------------------------------------
    if type_ == "boolean":
        return _make_param(name, ParamType.BOOLEAN)

    # Integer / number -----------------------------------------------------
    if type_ in ("integer", "number"):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is None or maximum is None:
            return Refusal.make(op_id, path, RefusalCode.R_UNBOUNDED_NUMBER)
        try:
            max_val = float(maximum)
        except (TypeError, ValueError):
            return Refusal.make(op_id, path, RefusalCode.R_UNBOUNDED_NUMBER)
        if abs(max_val) >= 10**MAX_NUMBER_DIGITS:
            return Refusal.make(op_id, path, RefusalCode.R_UNBOUNDED_NUMBER)
        return _make_param(
            name, ParamType.NUMERIC,
            constraints=ParamConstraints(min=minimum, max=maximum),
        )

    # String ---------------------------------------------------------------
    if type_ == "string":
        # Binary / byte
        if fmt in ("binary", "byte"):
            return Refusal.make(op_id, path, RefusalCode.R_BINARY)

        # date-time / time / duration -> R_DATETIME
        if fmt in ("date-time", "time", "duration"):
            return Refusal.make(op_id, path, RefusalCode.R_DATETIME)

        # date with window -> day picker
        if fmt == "date":
            if isinstance(x_date_window, int) and 1 <= x_date_window <= 7:
                return _make_param(
                    name, ParamType.DATE_WINDOW,
                    constraints=ParamConstraints(window=x_date_window),
                )
            return Refusal.make(op_id, path, RefusalCode.R_DATETIME)

        # phone -> prefilled
        if fmt == "phone":
            return _make_param(name, ParamType.PHONE, default_from="caller_msisdn")

        # enum -> paginated menu
        enum = schema.get("enum")
        if enum is not None:
            enum_vals = [str(v) for v in enum]
            if len(enum_vals) > MAX_ENUM_VALUES:
                return Refusal.make(op_id, path, RefusalCode.R_TOO_MANY_PARAMS)
            if not all(is_gsm7(v) for v in enum_vals):
                return Refusal.make(op_id, path, RefusalCode.R_NON_GSM7)
            return _make_param(
                name, ParamType.ENUM_MENU,
                constraints=ParamConstraints(enum=enum_vals),
            )

        # pattern or maxLength<=20 -> typed token (never execute pattern)
        pattern = schema.get("pattern")
        max_len = schema.get("maxLength")
        if pattern is not None:
            return _make_param(
                name, ParamType.TOKEN,
                constraints=ParamConstraints(pattern=str(pattern)),
            )
        if max_len is not None:
            try:
                ml = int(max_len)
            except (TypeError, ValueError):
                ml = 0
            if ml <= 20:
                return _make_param(
                    name, ParamType.TOKEN,
                    constraints=ParamConstraints(max_len=ml),
                )
            # maxLength > 20 -> too long for a token
            return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)

        # Unconstrained string -> free text
        return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)

    # Object ---------------------------------------------------------------
    if type_ == "object" or "properties" in schema:
        return _classify_object(schema, op_id=op_id, path=path, name=name,
                                 depth=depth, seen=seen)

    # Array ----------------------------------------------------------------
    if type_ == "array":
        items = schema.get("items", {})
        if isinstance(items, dict):
            item_type = items.get("type")
            if item_type == "object" or "properties" in items or "$ref" in items:
                return Refusal.make(op_id, path, RefusalCode.R_NESTED_OBJECT)
            # Array of scalars is not a supported input type.
        return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)

    # No type and no recognised shape -> free text
    return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)


def _classify_object(
    schema: dict[str, Any],
    *,
    op_id: str,
    path: str,
    name: str,
    depth: int,
    seen: frozenset[str],
) -> Param | Refusal:
    """Classify an object schema: flat objects are flattened, nested refused."""
    properties: dict[str, Any] = schema.get("properties", {})
    if not properties:
        return Refusal.make(op_id, path, RefusalCode.R_FREE_TEXT)

    if len(properties) > MAX_FLAT_OBJECT_PROPS:
        return Refusal.make(op_id, path, RefusalCode.R_TOO_MANY_PARAMS)

    required_set: set[str] = set(schema.get("required", []))
    sub_params: list[Param] = []
    new_seen = seen

    for prop_name, prop_schema in properties.items():
        # A property that is itself an object means nested object -> refuse.
        if isinstance(prop_schema, dict) and (
            prop_schema.get("type") == "object" or "properties" in prop_schema
        ):
            return Refusal.make(op_id, path, RefusalCode.R_NESTED_OBJECT)
        result = _classify(
            prop_schema,
            op_id=op_id,
            path=f"{path}/properties/{prop_name}",
            name=prop_name,
            depth=depth - 1,
            seen=new_seen,
        )
        if isinstance(result, Refusal):
            # Nested object inside this object -> R_NESTED_OBJECT
            if result.code in (RefusalCode.R_NESTED_OBJECT, RefusalCode.R_RECURSIVE):
                return Refusal.make(op_id, path, RefusalCode.R_NESTED_OBJECT)
            # Other refusal (free text, datetime, etc.) -> propagate
            return result
        # If the sub-param is itself flattened, the object is nested.
        if result.type == ParamType.FLATTENED:
            return Refusal.make(op_id, path, RefusalCode.R_NESTED_OBJECT)
        result = result.model_copy(update={"required": prop_name in required_set})
        sub_params.append(result)

    return _make_param(
        name, ParamType.FLATTENED,
        required=True,
        params=sub_params,
    )


# ---------------------------------------------------------------------------
# Result classification (basic — templates filled by render.py in spec 3)
# ---------------------------------------------------------------------------
def _classify_result(result_schema: dict[str, Any] | None) -> Result:
    """Map a result schema to a Result model (templates left empty for now)."""
    if result_schema is None:
        return Result(shape=ResultShape.TEXT)
    try:
        type_ = result_schema.get("type")
        if type_ == "array":
            items = result_schema.get("items", {})
            if isinstance(items, dict) and items.get("type") == "object":
                props = items.get("properties", {})
                fields = [
                    ResultField(path=k, label=k)
                    for k in props
                ]
                return Result(shape=ResultShape.LIST, fields=fields)
            return Result(shape=ResultShape.LIST)
        if type_ == "object":
            props = result_schema.get("properties", {})
            fields = [ResultField(path=k, label=k) for k in props]
            return Result(shape=ResultShape.RECORD, fields=fields)
        if type_ in ("string", "integer", "number", "boolean"):
            return Result(shape=ResultShape.SCALAR)
        return Result(shape=ResultShape.TEXT)
    except Exception:  # noqa: BLE001
        return Result(shape=ResultShape.TEXT)


# ---------------------------------------------------------------------------
# Operation-level classification
# ---------------------------------------------------------------------------
def classify_operation(
    draft: DraftOperation,
    *,
    depth_limit: int = DEFAULT_DEPTH_LIMIT,
) -> Operation | list[Refusal]:
    """Classify a draft operation into an Operation or a list of Refusals.

    If any parameter is refused, the whole operation is excluded and every
    Refusal is returned (requirement 3.4).
    """
    seen_refs: frozenset[str] = frozenset()
    refusals: list[Refusal] = []
    leaf_params: list[Param] = []

    for dp in draft.params:
        result = classify_schema(
            dp.schema,
            op_id=draft.id,
            path=f"#/params/{dp.name}",
            name=dp.name,
            depth_limit=depth_limit,
            seen_refs=seen_refs,
        )
        if isinstance(result, Refusal):
            refusals.append(result)
            continue
        # Expand flattened params into leaf params
        expanded = result.expand()
        for p in expanded:
            p = p.model_copy(update={"required": dp.required and p.required})
            leaf_params.append(p)

    # Check required param count against step cap
    required_count = sum(1 for p in leaf_params if p.required)
    if required_count > MAX_REQUIRED_PARAMS:
        refusals.append(
            Refusal.make(
                draft.id,
                f"#/params",
                RefusalCode.R_TOO_MANY_PARAMS,
                message=f"{required_count} required params exceed the max of {MAX_REQUIRED_PARAMS}.",
            )
        )

    if refusals:
        return refusals

    result = _classify_result(draft.result_schema)
    return Operation(
        id=draft.id,
        source_ref=draft.source_ref,
        kind=draft.kind,
        title=draft.title,
        params=leaf_params,
        result=result,
        async_=draft.async_,
        risk=draft.risk,
    )


# ---------------------------------------------------------------------------
# Refusal report
# ---------------------------------------------------------------------------
class RefusalReport(TypedDict):
    """Refusal report with per-code table (requirement 4.1, 4.2).

    Never presents a single coverage percentage without the per-code table.
    """

    refusals: list[dict[str, str]]
    compiled_count: int
    refused_count: int
    per_code: dict[str, int]


def classify_app(
    drafts: list[DraftOperation],
    *,
    slug: str = "app",
    title: str = "App",
    depth_limit: int = DEFAULT_DEPTH_LIMIT,
) -> tuple[App, RefusalReport]:
    """Classify all draft operations into an App and a refusal report.

    Returns (App with compiled operations, RefusalReport). If every operation
    is refused, App.operations is empty (caller checks for exit-code-2 signal).
    """
    operations: list[Operation] = []
    all_refusals: list[Refusal] = []

    for draft in drafts:
        result = classify_operation(draft, depth_limit=depth_limit)
        if isinstance(result, list):
            all_refusals.extend(result)
        else:
            operations.append(result)

    app = App(slug=slug, title=title, operations=operations)
    report = _build_report(operations, all_refusals)
    return app, report


def _build_report(
    operations: list[Operation],
    refusals: list[Refusal],
) -> RefusalReport:
    """Build the refusal report with accurate counts and per-code table."""
    per_code: dict[str, int] = {}
    for r in refusals:
        per_code[r.code.value] = per_code.get(r.code.value, 0) + 1
    # Count refused operations (unique op_ids that had refusals)
    refused_op_ids: set[str] = set()
    for r in refusals:
        refused_op_ids.add(r.op_id)
    return RefusalReport(
        refusals=[
            {
                "op_id": r.op_id,
                "path": r.path,
                "code": r.code.value,
                "message": r.message,
                "hint": r.hint,
            }
            for r in refusals
        ],
        compiled_count=len(operations),
        refused_count=len(refused_op_ids),
        per_code=per_code,
    )
