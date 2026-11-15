"""OpenAPI ingestion: safe load, own $ref resolver, operation extraction.

Produces draft IR (DraftOperation list) that feeds into the classifier
(``subset.classify_app``). Source: ingestion requirements 1–2, 5.

Security: 2 MB raw cap, YAML safe loader with depth/alias limits, local $ref
resolution only (remote refs -> R_REF_UNRESOLVED, no network call), pattern
never executed.
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from .ir import DraftOperation, DraftParam, OpKind, Risk
from .refusals import Refusal, RefusalCode

#: Max raw content size (requirement 1.5).
MAX_RAW_SIZE = 2 * 1024 * 1024  # 2 MB

#: Max nesting depth after load (anti deep-nesting / alias bomb).
MAX_DOC_DEPTH = 50

#: Max total keys/elements in the loaded document.
MAX_DOC_ELEMENTS = 10_000


# ---------------------------------------------------------------------------
# Safe loader with depth and element limits
# ---------------------------------------------------------------------------
class IngestError(Exception):
    """Typed ingestion error (never a raw stack trace to users)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def safe_load(raw: bytes | str, *, max_size: int = MAX_RAW_SIZE) -> Any:
    """Load JSON or YAML with size, depth and element caps.

    Requirement 1.5: rejects >2MB before parsing.
    Requirement 2.1: safe loader with alias and depth limits.
    Requirement 5.1: alias bombs and deep nesting rejected.
    """
    if isinstance(raw, str):
        raw_bytes = raw.encode("utf-8")
    else:
        raw_bytes = raw

    if len(raw_bytes) > max_size:
        raise IngestError("TOO_LARGE", f"Content exceeds {max_size} bytes")

    text = raw_bytes.decode("utf-8")
    stripped = text.lstrip()

    # Detect JSON vs YAML by first character
    if stripped and stripped[0] in "{[":
        return _load_json(text)
    return _load_yaml(text)


def _load_json(text: str) -> Any:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestError("PARSE_ERROR", f"Invalid JSON: {exc}") from exc
    _check_depth_and_size(doc)
    return doc


def _load_yaml(text: str) -> Any:
    """Safe YAML load with alias and depth limits."""
    # Use a custom loader that limits alias references
    loader = yaml.SafeLoader(text)

    # Patch construct_object to count nodes (anti alias-bomb)
    node_count = [0]

    original_construct_object = loader.construct_object

    def counting_construct_object(node, deep=False):  # type: ignore[no-untyped-def]
        node_count[0] += 1
        if node_count[0] > MAX_DOC_ELEMENTS:
            raise IngestError("TOO_MANY_NODES",
                               f"YAML document has more than {MAX_DOC_ELEMENTS} nodes (alias bomb?)")
        return original_construct_object(node, deep)

    loader.construct_object = counting_construct_object

    try:
        doc = loader.get_single_data()
    except yaml.YAMLError as exc:
        raise IngestError("PARSE_ERROR", f"Invalid YAML: {exc}") from exc
    finally:
        loader.dispose()

    _check_depth_and_size(doc)
    return doc


def _check_depth_and_size(obj: Any, depth: int = 0, count: list[int] | None = None) -> None:
    """Recursively check depth and element count."""
    if count is None:
        count = [0]
    count[0] += 1
    if count[0] > MAX_DOC_ELEMENTS:
        raise IngestError("TOO_MANY_ELEMENTS",
                          f"Document exceeds {MAX_DOC_ELEMENTS} elements")
    if depth > MAX_DOC_DEPTH:
        raise IngestError("TOO_DEEP",
                          f"Document exceeds depth limit of {MAX_DOC_DEPTH}")
    if isinstance(obj, dict):
        for v in obj.values():
            _check_depth_and_size(v, depth + 1, count)
    elif isinstance(obj, list):
        for item in obj:
            _check_depth_and_size(item, depth + 1, count)


# ---------------------------------------------------------------------------
# Local $ref resolver
# ---------------------------------------------------------------------------
class RefResolver:
    """Resolve local JSON pointers (``#/...``) within an OpenAPI document.

    - Local refs: resolved via JSON pointer traversal.
    - Remote refs: returned as R_REF_UNRESOLVED (no network call).
    - Cycles: detected via a seen-set, returned as R_RECURSIVE.
    - Depth: capped to prevent runaway recursion.
    """

    def __init__(self, doc: dict[str, Any], *, max_depth: int = 20) -> None:
        self._doc = doc
        self._max_depth = max_depth

    def resolve(
        self,
        ref: str,
        *,
        seen: frozenset[str] | None = None,
        depth: int = 0,
    ) -> tuple[dict[str, Any] | None, Refusal | None]:
        """Resolve a $ref. Returns (resolved_schema, refusal_or_None)."""
        if seen is None:
            seen = frozenset()

        if depth >= self._max_depth:
            return None, Refusal.make("", ref, RefusalCode.R_RECURSIVE)

        if not ref.startswith("#"):
            # Remote ref — block without network call
            return None, Refusal.make("", ref, RefusalCode.R_REF_UNRESOLVED)

        if ref in seen:
            return None, Refusal.make("", ref, RefusalCode.R_RECURSIVE)

        # JSON pointer: #/components/schemas/Foo
        parts = ref[2:].split("/") if ref.startswith("#/") else [ref[1:]]
        current: Any = self._doc
        for part in parts:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None, Refusal.make("", ref, RefusalCode.R_REF_UNRESOLVED)
            else:
                return None, Refusal.make("", ref, RefusalCode.R_REF_UNRESOLVED)

        if not isinstance(current, dict):
            return None, Refusal.make("", ref, RefusalCode.R_REF_UNRESOLVED)

        # If the resolved schema itself has a $ref, follow it
        new_seen = seen | {ref}
        if "$ref" in current:
            inner_ref = current["$ref"]
            return self.resolve(inner_ref, seen=new_seen, depth=depth + 1)

        return current, None

    def resolve_schema(self, schema: dict[str, Any], *, depth: int = 0) -> dict[str, Any] | Refusal:
        """Resolve $ref at the top of *schema*, returning the target or a Refusal."""
        if "$ref" not in schema:
            return schema
        ref = schema["$ref"]
        resolved, refusal = self.resolve(ref, depth=depth)
        if refusal is not None:
            return refusal
        assert resolved is not None
        return resolved


# ---------------------------------------------------------------------------
# OpenAPI operation extraction
# ---------------------------------------------------------------------------
def _generate_op_id(method: str, path: str) -> str:
    """Generate an operation id from method and path (requirement 1.3)."""
    clean = path.replace("/", "_").replace("{", "").replace("}", "").strip("_")
    return f"{method.lower()}_{clean}"


def _extract_params(
    parameters: list[dict[str, Any]],
    body_schema: dict[str, Any] | None,
    resolver: RefResolver,
    op_id: str,
) -> tuple[list[DraftParam], list[Refusal]]:
    """Extract DraftParams from OpenAPI parameters and request body."""
    draft_params: list[DraftParam] = []
    refusals: list[Refusal] = []

    for param in parameters:
        name = param.get("name", "")
        if not name:
            continue
        in_loc = param.get("in", "")
        required = param.get("required", False)
        schema = param.get("schema", {})

        # Resolve $ref in schema
        if isinstance(schema, dict) and "$ref" in schema:
            resolved = resolver.resolve_schema(schema)
            if isinstance(resolved, Refusal):
                refusals.append(
                    Refusal.make(op_id, f"#/params/{name}", resolved.code)
                )
                continue
            schema = resolved

        draft_params.append(DraftParam(
            name=name,
            schema=schema if isinstance(schema, dict) else {},
            required=required,
            in_location=in_loc,
        ))

    # Request body (usually a flat object schema)
    if body_schema is not None:
        # Resolve $ref if present
        if "$ref" in body_schema:
            resolved = resolver.resolve_schema(body_schema)
            if isinstance(resolved, Refusal):
                refusals.append(resolved)
                return draft_params, refusals
            body_schema = resolved
        draft_params.append(DraftParam(
            name="body",
            schema=body_schema,
            required=True,
            in_location="body",
        ))

    return draft_params, refusals


def _get_body_schema(op_obj: dict[str, Any], resolver: RefResolver) -> dict[str, Any] | None:
    """Extract the request body JSON schema from an OpenAPI operation."""
    body = op_obj.get("requestBody", {})
    if not body:
        return None
    # Resolve $ref on body itself
    if "$ref" in body:
        resolved = resolver.resolve_schema(body)
        if isinstance(resolved, Refusal):
            return None
        body = resolved

    content = body.get("content", {})
    # Prefer application/json
    for media_type in ("application/json", "application/yaml"):
        if media_type in content:
            schema = content[media_type].get("schema", {})
            if isinstance(schema, dict):
                return schema
    return None


def _get_response_schema(op_obj: dict[str, Any], resolver: RefResolver) -> dict[str, Any] | None:
    """Extract the success response schema for result classification."""
    responses = op_obj.get("responses", {})
    # Look for 200, 201, or default
    for code in ("200", "201", "default", "2XX"):
        resp = responses.get(code)
        if not resp:
            continue
        if isinstance(resp, dict) and "$ref" in resp:
            resolved = resolver.resolve_schema(resp)
            if isinstance(resolved, Refusal):
                continue
            resp = resolved
        if not isinstance(resp, dict):
            continue
        content = resp.get("content", {})
        for media_type in ("application/json", "application/yaml"):
            if media_type in content:
                schema = content[media_type].get("schema", {})
                if isinstance(schema, dict):
                    return schema
    return None


def ingest_openapi(raw: bytes | str, *, slug: str = "app") -> tuple[list[DraftOperation], list[Refusal]]:
    """Ingest an OpenAPI document into draft operations.

    Returns (draft_operations, ingest_refusals). The caller passes
    draft_operations to ``subset.classify_app`` for classification.
    """
    doc = safe_load(raw)
    if not isinstance(doc, dict):
        raise IngestError("NOT_OPENAPI", "Document is not a valid OpenAPI object")

    # Check OpenAPI version
    version = doc.get("openapi") or doc.get("swagger")
    if not version:
        raise IngestError("NOT_OPENAPI", "Document has no openapi or swagger version")

    resolver = RefResolver(doc)
    draft_ops: list[DraftOperation] = []
    ingest_refusals: list[Refusal] = []

    paths = doc.get("paths", {})
    if not isinstance(paths, dict):
        return draft_ops, ingest_refusals

    # Collect all operations deterministically (sorted by path then method)
    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict):
            continue
        # Resolve path-level $ref
        if "$ref" in path_item:
            resolved = resolver.resolve_schema(path_item)
            if isinstance(resolved, Refusal):
                continue
            path_item = resolved

        path_params = path_item.get("parameters", [])
        if not isinstance(path_params, list):
            path_params = []

        for method in sorted(k for k in path_item if k.lower() in
                             ("get", "post", "put", "patch", "delete")):
            op_obj = path_item[method]
            if not isinstance(op_obj, dict):
                continue

            # Operation id
            op_id = op_obj.get("operationId")
            generated = False
            if not op_id:
                op_id = _generate_op_id(method, path)
                generated = True

            # Title from summary or operationId
            title = op_obj.get("summary", op_id)[:24]

            # Kind from method
            kind = OpKind.READ if method.lower() == "get" else OpKind.WRITE

            # Params: combine path-level and operation-level parameters
            op_params = op_obj.get("parameters", [])
            if not isinstance(op_params, list):
                op_params = []
            all_params = path_params + op_params

            body_schema = _get_body_schema(op_obj, resolver)
            result_schema = _get_response_schema(op_obj, resolver)

            draft_params, param_refusals = _extract_params(
                all_params, body_schema, resolver, op_id
            )

            if param_refusals:
                ingest_refusals.extend(param_refusals)

            # Risk: money/identity hint from tags or summary keywords
            risk = Risk.LOW
            summary_lower = (op_obj.get("summary", "") + " " + op_id).lower()
            if any(w in summary_lower for w in ("pay", "transfer", "send", "money")):
                risk = Risk.MONEY
            elif any(w in summary_lower for w in ("login", "pin", "auth", "password")):
                risk = Risk.IDENTITY

            draft_ops.append(DraftOperation(
                id=op_id,
                source_ref=f"{method.upper()} {path}",
                kind=kind,
                title=title,
                params=draft_params,
                result_schema=result_schema,
                risk=risk,
            ))

    return draft_ops, ingest_refusals
