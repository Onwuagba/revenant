"""Single-service deployment: the API serves the built console from the same origin
(REVENANT_CONSOLE_DIR)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from revenant.api.app import create_app

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>console</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("outside the console dir")
    monkeypatch.setenv("REVENANT_CONSOLE_DIR", str(tmp_path))
    return TestClient(create_app(seed=False))


def test_spa_routes_fall_back_to_index(client: TestClient) -> None:
    for path in ("/", "/crypt", "/seance/clinic-booking", "/judges"):
        res = client.get(path)
        assert res.status_code == 200 and "<title>console</title>" in res.text


def test_static_asset_is_served_and_missing_asset_is_404(client: TestClient) -> None:
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/assets/missing.js").status_code == 404


def test_api_and_ussd_keep_priority_and_never_fall_back(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/v1/nope").status_code == 404
    assert client.get("/ussd/nope").status_code == 404


def test_path_traversal_never_leaves_the_console_dir(client: TestClient) -> None:
    for path in ("/..%2fsecret.txt", "/../secret.txt", "/%2e%2e/secret.txt"):
        res = client.get(path)
        assert "outside the console dir" not in res.text


def test_not_registered_without_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVENANT_CONSOLE_DIR", raising=False)
    assert TestClient(create_app(seed=False)).get("/crypt").status_code == 404
