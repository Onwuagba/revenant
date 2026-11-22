"""MCP (Model Context Protocol) ingestion.

Connects to a streamable-HTTP MCP server, calls ``initialize`` and
``tools/list``, and maps each tool to a draft Operation that feeds the
classifier. Tool descriptions and server responses are data, never
instructions (requirement 4.5).

Security: stdio transports accepted only from a server-side registry of
bundled samples — no user-supplied commands (requirement 4.4). URLs are
guarded by the SSRF policy.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .ir import DraftOperation, DraftParam, OpKind, Risk
from .refusals import Refusal, RefusalCode
from .urlguard import DEFAULT_MAX_SIZE, DEFAULT_TIMEOUT, UrlGuardError, check_url

#: Static registry of bundled stdio sample servers (no user-supplied commands).
STDIO_REGISTRY: dict[str, list[str]] = {
    "farmer-prices": ["python", "-m", "examples.farmer_prices_mcp.server"],
}


def tool_to_dict(tool: dict[str, Any] | Any, default_name: str = "") -> dict[str, Any]:
    """Normalise a tool (dict or SDK model) to camelCase MCP keys.

    mcp 1.x models expose ``inputSchema``; mcp 2.x exposes ``input_schema`` with the camelCase
    alias. ``model_dump(by_alias=True)`` yields the wire names for both, so a tool is never
    silently read as having no parameters.
    """
    if isinstance(tool, dict):
        return tool
    if hasattr(tool, "model_dump"):
        dumped: dict[str, Any] = tool.model_dump(by_alias=True)
        dumped.setdefault("name", default_name)
        return dumped
    return {
        "name": getattr(tool, "name", default_name),
        "description": getattr(tool, "description", ""),
        "inputSchema": getattr(tool, "inputSchema", None),
        "outputSchema": getattr(tool, "outputSchema", None),
        "annotations": getattr(tool, "annotations", None),
    }


def map_tool_to_draft(
    tool_name: str,
    tool: dict[str, Any] | Any,
) -> DraftOperation:
    """Map an MCP tool definition (dict or Tool object) to a DraftOperation.

    Pure function — no network, no I/O. Tested in isolation.
    """
    td = tool_to_dict(tool, tool_name)

    name = td.get("name", tool_name)
    description = td.get("description", "") or ""

    # inputSchema -> DraftParams
    input_schema = td.get("inputSchema") or {}
    if not isinstance(input_schema, dict):
        input_schema = {}

    params: list[DraftParam] = []
    properties = input_schema.get("properties", {})
    if isinstance(properties, dict):
        required_list = input_schema.get("required", [])
        required_set: set[str] = set(required_list) if isinstance(required_list, list) else set()
        for prop_name, prop_schema in properties.items():
            params.append(
                DraftParam(
                    name=prop_name,
                    json_schema=prop_schema if isinstance(prop_schema, dict) else {},
                    required=prop_name in required_set,
                    in_location="body",
                )
            )

    # outputSchema -> result_schema (None = text shape)
    output_schema = td.get("outputSchema")
    result_schema = output_schema if isinstance(output_schema, dict) else None

    # Annotations as untrusted seeds for kind/risk (requirement 4.3)
    kind = OpKind.READ
    risk = Risk.LOW
    annotations = td.get("annotations")
    if annotations is not None:
        if isinstance(annotations, dict):
            if annotations.get("readOnlyHint") is True:
                kind = OpKind.READ
            elif annotations.get("readOnlyHint") is False:
                kind = OpKind.WRITE
            if annotations.get("destructiveHint") is True:
                risk = Risk.IDENTITY
            elif annotations.get("openWorldHint") is False:
                kind = OpKind.READ
        else:
            # Object with attributes (pydantic model)
            if getattr(annotations, "readOnlyHint", None) is False:
                kind = OpKind.WRITE
            if getattr(annotations, "destructiveHint", None) is True:
                risk = Risk.IDENTITY

    # Title from description (truncated) or tool name
    title = (description.split("\n")[0] if description else name)[:24]

    return DraftOperation(
        id=name,
        source_ref=f"mcp:{name}",
        kind=kind,
        title=title,
        params=params,
        result_schema=result_schema,
        risk=risk,
    )


def ingest_mcp_tools(
    tools: list[dict[str, Any] | Any],
) -> tuple[list[DraftOperation], list[Refusal]]:
    """Map a list of MCP tool definitions to draft operations.

    Pure mapping — no network. The caller fetches the tool list from the
    server via :func:`ingest_mcp` or provides them directly for testing.
    """
    draft_ops: list[DraftOperation] = []
    refusals: list[Refusal] = []

    for tool in tools:
        name = tool.get("name", "") if isinstance(tool, dict) else getattr(tool, "name", "")
        if not name:
            refusals.append(
                Refusal.make(
                    "unknown",
                    "#/tools",
                    RefusalCode.R_FREE_TEXT,
                    message="Tool without a name.",
                )
            )
            continue
        draft_ops.append(map_tool_to_draft(name, tool))

    return draft_ops, refusals


class McpFetchError(Exception):
    """A guarded MCP fetch failed its size or time cap (requirement 3.4)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def _guarded_client(
    *, allow_http: bool, max_bytes: int, timeout: float, failures: list[Exception]
) -> Any:
    """An httpx2 client for the MCP SDK that re-runs the URL guard and caps response size.

    - Every request is guarded, not only the first: this covers same-origin redirects (the
      SDK follows no other kind) and narrows DNS rebinding to the gap between our resolution
      and the connection. The connection is not pinned to the checked IP; doing that over TLS
      needs SNI control we have not verified, so a small window remains.
    - Responses are capped on Content-Length and on the bytes actually read.
    - Proxy settings from the environment are ignored so the guard checks the real peer.

    The SDK swallows errors raised while it reads a stream and reports a generic one, so the
    first guard or cap failure is also appended to *failures* for the caller to report.
    """
    import httpx2

    class _CappedStream(httpx2.AsyncByteStream):
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self._seen = 0

        async def __aiter__(self) -> Any:
            async for chunk in self._inner:
                self._seen += len(chunk)
                if self._seen > max_bytes:
                    err = McpFetchError("TOO_LARGE", f"MCP response exceeds {max_bytes} bytes")
                    failures.append(err)
                    raise err
                yield chunk

        async def aclose(self) -> None:
            await self._inner.aclose()

    class _GuardedTransport(httpx2.AsyncBaseTransport):
        def __init__(self) -> None:
            self._inner = httpx2.AsyncHTTPTransport(trust_env=False)

        async def handle_async_request(self, request: Any) -> Any:
            try:
                check_url(str(request.url), allow_http=allow_http)
            except UrlGuardError as guard_err:
                failures.append(guard_err)
                raise
            resp = await self._inner.handle_async_request(request)
            length = resp.headers.get("content-length", "")
            if length.isdigit() and int(length) > max_bytes:
                await resp.aclose()
                err = McpFetchError("TOO_LARGE", f"MCP response exceeds {max_bytes} bytes")
                failures.append(err)
                raise err
            return httpx2.Response(
                status_code=resp.status_code,
                headers=resp.headers,
                stream=_CappedStream(resp.stream),
                extensions=resp.extensions,
            )

        async def aclose(self) -> None:
            await self._inner.aclose()

    return httpx2.AsyncClient(
        transport=_GuardedTransport(), timeout=httpx2.Timeout(timeout), trust_env=False
    )


def _first_cause(exc: BaseException) -> BaseException:
    """Unwrap anyio task-group exception groups to the first real error."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


async def ingest_mcp(
    url: str,
    *,
    allow_http: bool = False,
    max_bytes: int = DEFAULT_MAX_SIZE,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[list[DraftOperation], list[Refusal]]:
    """Connect to a streamable-HTTP MCP server and ingest its tools.

    Requirement 4.1: calls initialize and tools/list.
    Requirement 4.4: only streamable HTTP from users; stdio from registry.
    Requirements 3.1-3.4: URL guarded on every request; size and total-time caps.
    Raises UrlGuardError or McpFetchError; never returns partial results.
    """
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    target = check_url(url, allow_http=allow_http)  # fail fast before any connection

    failures: list[Exception] = []

    async def _run() -> tuple[list[DraftOperation], list[Refusal]]:
        async with _guarded_client(
            allow_http=allow_http, max_bytes=max_bytes, timeout=timeout, failures=failures
        ) as client:
            # mcp 1.x yields (read, write, get_session_id); mcp 2.x yields (read, write).
            async with streamable_http_client(
                target.url, http_client=client, max_sse_event_size=max_bytes
            ) as streams:
                read, write = streams[0], streams[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return ingest_mcp_tools([tool_to_dict(t) for t in result.tools])

    try:
        return await asyncio.wait_for(_run(), timeout)
    except TimeoutError as exc:
        if failures:
            raise failures[0] from exc
        raise McpFetchError("TIMEOUT", f"MCP ingest exceeded {timeout:g} s") from exc
    except Exception as exc:
        if failures:  # our guard or cap tripped; the SDK may have reported something generic
            raise failures[0] from exc
        cause = _first_cause(exc)
        if isinstance(cause, (UrlGuardError, McpFetchError)):
            raise cause from exc
        raise McpFetchError("FETCH_FAILED", type(cause).__name__) from exc


def is_allowed_stdio(name: str) -> bool:
    """Return True if *name* is in the static stdio registry (requirement 4.4)."""
    return name in STDIO_REGISTRY
