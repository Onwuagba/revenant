"""Ingestion requirement 4.4: a user can never make the server launch a stdio command."""

import pytest
from fastapi.testclient import TestClient
from revenant.api.app import create_app
from revenant.runtime.store import make_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv("REVENANT_INSECURE_COOKIES", "1")
    monkeypatch.delenv("KIRO_API_KEY", raising=False)
    c = TestClient(create_app(make_engine()), base_url="http://testserver")
    r = c.post("/api/v1/auth/register", json={"email": "s@x.io", "password": "password123"})
    h = {"x-csrf-token": r.json()["csrf"]}
    pid = c.post("/api/v1/projects", json={"title": "S", "slug": "ss"}, headers=h).json()["id"]
    return c, h, pid


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "stdio", "command": "python -m evil"},
        {"kind": "mcp", "url": "stdio:python -m evil"},
        {"kind": "mcp", "url": "file:///etc/passwd"},
        {"kind": "mcp", "url": "python -m examples.farmer_prices_mcp.server"},
        {"kind": "mcp", "url": "http://example.com/mcp"},  # https only
    ],
)
def test_stdio_or_non_https_source_rejected(owner, body):
    c, h, pid = owner
    r = c.post(f"/api/v1/projects/{pid}/sources", json=body, headers=h)
    assert r.status_code == 422
