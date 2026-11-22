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


# ---------------------------------------------------------------------------
# Ingestion requirements 3.3 and 3.4 on the real MCP client path
# ---------------------------------------------------------------------------
import http.server  # noqa: E402
import threading  # noqa: E402


def _allow_all(url, allow_http=False):
    return ResolvedTarget(url, "127.0.0.1", "127.0.0.1", 0)


class _Server:
    """Tiny HTTP server on a thread; records every request path it receives."""

    def __init__(self, handler_body):
        hits = self.hits = []

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _do(self):
                hits.append((self.command, self.path))
                handler_body(self)

            do_GET = do_POST = do_DELETE = _do

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/mcp"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.mark.integration
def test_response_size_cap(farmer_server):
    """3.4: a response larger than the cap fails the ingest instead of being read."""
    with mock.patch.object(ingest_mcp_mod, "check_url", _allow_all):
        with pytest.raises(ingest_mcp_mod.McpFetchError) as exc:
            asyncio.run(ingest_mcp_mod.ingest_mcp(farmer_server, max_bytes=64))
    assert exc.value.code == "TOO_LARGE"


@pytest.mark.integration
def test_total_time_cap():
    """3.4: a server that never answers is abandoned at the time cap."""

    def hang(h):
        time.sleep(5)

    srv = _Server(hang)
    try:
        start = time.monotonic()
        with mock.patch.object(ingest_mcp_mod, "check_url", _allow_all):
            with pytest.raises(ingest_mcp_mod.McpFetchError) as exc:
                asyncio.run(ingest_mcp_mod.ingest_mcp(srv.url, timeout=1.0))
        assert exc.value.code == "TIMEOUT"
        assert time.monotonic() - start < 4
    finally:
        srv.close()


@pytest.mark.integration
def test_guard_runs_on_every_request_not_only_the_first(farmer_server):
    """3.3 / DNS rebinding: if the host later fails the guard, the next request is refused."""
    from revenant.compiler.urlguard import UrlGuardError

    calls = []

    def first_only(url, allow_http=False):
        calls.append(url)
        if len(calls) > 1:  # pre-flight check passes, transport-level re-check fails
            raise UrlGuardError("BLOCKED_ADDRESS", "re-resolved to a private address")
        return _allow_all(url)

    with mock.patch.object(ingest_mcp_mod, "check_url", first_only):
        with pytest.raises(UrlGuardError):
            asyncio.run(ingest_mcp_mod.ingest_mcp(farmer_server))
    assert len(calls) >= 2


@pytest.mark.integration
def test_cross_origin_redirect_is_not_followed():
    """3.3: a redirect to another origin is never followed; the second server sees nothing."""
    target = _Server(lambda h: (h.send_response(200), h.end_headers()))

    def redirect(h):
        h.send_response(307)
        h.send_header("Location", target.url)
        h.send_header("Content-Length", "0")
        h.end_headers()

    origin = _Server(redirect)
    try:
        with mock.patch.object(ingest_mcp_mod, "check_url", _allow_all):
            with pytest.raises(ingest_mcp_mod.McpFetchError) as exc:
                asyncio.run(ingest_mcp_mod.ingest_mcp(origin.url, timeout=5.0))
        assert exc.value.code == "FETCH_FAILED"
        assert origin.hits, "the first server was never contacted"
        assert target.hits == []
    finally:
        origin.close()
        target.close()
