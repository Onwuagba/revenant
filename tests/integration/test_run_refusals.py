"""A run that refused every operation has no bundle; its refusals must still be returned with
the run."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from revenant.api.app import create_app
from revenant.runtime.store import make_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("REVENANT_INSECURE_COOKIES", "1")
    monkeypatch.delenv("KIRO_API_KEY", raising=False)
    return TestClient(create_app(make_engine()), base_url="http://testserver")


def _latest_run(client: TestClient, slug: str) -> dict:
    project = client.get(f"/api/v1/projects/{slug}").json()
    return client.get(f"/api/v1/compile-runs/{project['runs'][0]['id']}").json()


def test_fully_refused_sample_returns_each_refusal_with_code_and_reason(client: TestClient) -> None:
    run = _latest_run(client, "unsupported-demo")
    assert run["status"] == "refused" and run["bundle_id"] is None
    codes = {r["code"] for r in run["refusals"]}
    assert codes == {"R_DATETIME", "R_NESTED_OBJECT", "R_FREE_TEXT", "R_BINARY", "R_POLYMORPHIC"}
    for r in run["refusals"]:
        assert r["op_id"] and r["path"] and r["message"]


def test_clean_sample_has_no_refusals(client: TestClient) -> None:
    assert _latest_run(client, "clinic-booking")["refusals"] == []
