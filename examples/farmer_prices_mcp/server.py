"""Farmer-prices MCP sample server (streamable HTTP).

Two tools: one in-subset (crop price with enum), one deliberately
out-of-subset (free-text market search). Used for the live compile demo
and MCP ingestion tests.

Run: python -m examples.farmer_prices_mcp.server
"""

from __future__ import annotations

import asyncio
from typing import Literal

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="farmer-prices",
    version="1.0.0",
    description="Sample MCP server for Revenant: crop prices over MCP.",
)


@server.tool(description="Get the current price per kg for a crop.")
def get_crop_price(crop: Literal["maize", "rice", "beans", "cassava", "yam"]) -> str:
    """Get the current market price for a specific crop."""
    prices = {
        "maize": "NGN 120/kg",
        "rice": "NGN 350/kg",
        "beans": "NGN 280/kg",
        "cassava": "NGN 90/kg",
        "yam": "NGN 200/kg",
    }
    return prices.get(crop, "Price not available")


@server.tool(description="Search market listings by free-text query.")
def search_market(query: str) -> str:
    """Search all market listings matching a free-text query.

    This tool is deliberately out-of-subset: the query parameter is an
    unconstrained string (free text) that cannot be rendered as a USSD
    input. It should be refused by the classifier with R_FREE_TEXT.
    """
    return f"Search results for '{query}': (demo — no listings configured)"


async def main() -> None:
    await server.run_streamable_http_async()


if __name__ == "__main__":
    asyncio.run(main())
