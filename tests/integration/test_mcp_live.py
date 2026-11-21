"""Live MCP ingest against the real farmer-prices sample server (streamable HTTP).

The SSRF guard blocks loopback by design (covered in test_urlguard.py), so this test replaces
only the guard call to reach the local server; everything else is the real client path.
"""

import asyncio
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest
import revenant.compiler.ingest_mcp as ingest_mcp_mod
from revenant.compiler.refusals import RefusalCode
from revenant.compiler.subset import classify_app
from revenant.compiler.urlguard import ResolvedTarget

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def farmer_server():
    port = _free_port()
    code = (
        "import asyncio\n"
        "from examples.farmer_prices_mcp.server import server\n"
        f"asyncio.run(server.run_streamable_http_async(port={port}))\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("farmer-prices MCP server did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.mark.integration
def test_ingest_mcp_from_live_server_then_classify(farmer_server):
    def allow(url, allow_http=False):
        return ResolvedTarget(url, "127.0.0.1", "127.0.0.1", 0)

    with mock.patch.object(ingest_mcp_mod, "check_url", allow):
        drafts, refusals = asyncio.run(ingest_mcp_mod.ingest_mcp(farmer_server))
    assert {d.id for d in drafts} == {"get_crop_price", "search_market"}
    app, report = classify_app(drafts, slug="farmer-prices", title="Farmer Prices")
    assert {o.id for o in app.operations} == {"get_crop_price"}
    assert RefusalCode.R_FREE_TEXT.value in report["per_code"]


@pytest.mark.integration
def test_ingest_mcp_blocks_loopback_without_patch(farmer_server):
    from revenant.compiler.urlguard import UrlGuardError

    with pytest.raises(UrlGuardError):
        asyncio.run(ingest_mcp_mod.ingest_mcp(farmer_server, allow_http=True))
