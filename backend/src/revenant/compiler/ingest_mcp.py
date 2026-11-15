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

from typing import Any

from .ir import DraftOperation, DraftParam, OpKind, Risk
from .refusals import Refusal, RefusalCode
from .urlguard import check_url

#: Static registry of bundled stdio sample servers (no user-supplied commands).
STDIO_REGISTRY: dict[str, list[str]] = {
    "farmer-prices": ["python", "-m", "examples.farmer_prices_mcp.server"],
}


def map_tool_to_draft(
    tool_name: str,
    tool: dict[str, Any] | Any,
) -> DraftOperation:
    """Map an MCP tool definition (dict or Tool object) to a DraftOperation.

    Pure function — no network, no I/O. Tested in isolation.
    """
    # Normalise to dict for uniform access
    if isinstance(tool, dict):
        td = tool
    else:
        td = {
            "name": getattr(tool, "name", tool_name),
            "description": getattr(tool, "description", ""),
            "inputSchema": getattr(tool, "inputSchema", None),
            "outputSchema": getattr(tool, "outputSchema", None),
            "annotations": getattr(tool, "annotations", None),
        }

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
            params.append(DraftParam(
                name=prop_name,
                schema=prop_schema if isinstance(prop_schema, dict) else {},
                required=prop_name in required_set,
                in_location="body",
            ))

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
            refusals.append(Refusal.make(
                "unknown", "#/tools", RefusalCode.R_FREE_TEXT,
                message="Tool without a name.",
            ))
            continue
        draft_ops.append(map_tool_to_draft(name, tool))

    return draft_ops, refusals


async def ingest_mcp(
    url: str,
    *,
    allow_http: bool = False,
) -> tuple[list[DraftOperation], list[Refusal]]:
    """Connect to a streamable-HTTP MCP server and ingest its tools.

    Requirement 4.1: calls initialize and tools/list.
    Requirement 4.4: only streamable HTTP from users; stdio from registry.
    Requirement 3.1: URL guarded by SSRF policy.
    """
    from mcp.client.streamable_http import streamable_http_client
    from mcp.client.session import ClientSession

    # Guard the URL (SSRF policy)
    target = check_url(url, allow_http=allow_http)

    async with streamable_http_client(target.url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else None,
                    "outputSchema": getattr(t, "outputSchema", None),
                    "annotations": getattr(t, "annotations", None),
                }
                for t in result.tools
            ]
            return ingest_mcp_tools(tools)


def is_allowed_stdio(name: str) -> bool:
    """Return True if *name* is in the static stdio registry (requirement 4.4)."""
    return name in STDIO_REGISTRY
