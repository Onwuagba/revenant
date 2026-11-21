"""Platform API: auth, authz, samples, compile + SSE, emulator, deployments."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from revenant.api.app import create_app
from revenant.runtime.store import make_engine

pytestmark = pytest.mark.integration
CLINIC = Path("examples/specs/clinic.openapi.yaml").read_text()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("REVENANT_INSECURE_COOKIES", "1")
    monkeypatch.setenv("REVENANT_VIEWER_PASSWORD", "viewerpass1")
    monkeypatch.delenv("KIRO_API_KEY", raising=False)
    return TestClient(create_app(make_engine()), base_url="http://testserver")


def signup(c, email="a@x.io"):
    r = c.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201
    return {"x-csrf-token": r.json()["csrf"]}


def test_samples_public_and_compiled(client):
    ps = {p["slug"]: p for p in client.get("/api/v1/projects").json()}
    assert {"clinic-booking", "farmer-prices", "unsupported-demo"} <= set(ps)
    clinic = client.get(f"/api/v1/projects/{ps['clinic-booking']['id']}").json()
    assert clinic["bundles"] and clinic["runs"][0]["annotator"] == "deterministic"
    unsupported = client.get(f"/api/v1/projects/{ps['unsupported-demo']['id']}").json()
    assert unsupported["runs"][0]["status"] in ("refused", "verified")
    run = client.get(f"/api/v1/compile-runs/{unsupported['runs'][0]['id']}").json()
    assert any("per_code" in e["data"] for e in run["log"])


def test_auth_required_and_csrf(client):
    assert client.post("/api/v1/projects", json={"title": "T", "slug": "tt"}).status_code == 401
    h = signup(client)
    assert (
        client.post("/api/v1/projects", json={"title": "T", "slug": "tt"}).status_code == 403
    )  # no CSRF
    r = client.post("/api/v1/projects", json={"title": "T", "slug": "tt"}, headers=h)
    assert r.status_code == 201
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "a@x.io", "password": "wrongwrong"}
        ).status_code
        == 401
    )


def test_viewer_is_read_only(client):
    r = client.post(
        "/api/v1/auth/login", json={"email": "viewer@revenant.local", "password": "viewerpass1"}
    )
    assert r.status_code == 200
    h = {"x-csrf-token": r.json()["csrf"]}
    assert (
        client.post("/api/v1/projects", json={"title": "T", "slug": "vv"}, headers=h).status_code
        == 403
    )


def test_cross_project_isolation(client):
    h1 = signup(client, "one@x.io")
    pid = client.post(
        "/api/v1/projects", json={"title": "Mine", "slug": "mine"}, headers=h1
    ).json()["id"]
    client.cookies.clear()
    h2 = signup(client, "two@x.io")
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/compile", json={}, headers=h2).status_code == 404


def test_compile_flow_sse_deploy_and_ussd(client):
    h = signup(client)
    pid = client.post("/api/v1/projects", json={"title": "Mine", "slug": "mine"}, headers=h).json()[
        "id"
    ]
    assert (
        client.post(f"/api/v1/projects/{pid}/compile", json={}, headers=h).status_code == 422
    )  # no source
    assert (
        client.post(
            f"/api/v1/projects/{pid}/sources",
            json={"kind": "mcp", "url": "http://127.0.0.1/mcp"},
            headers=h,
        ).status_code
        == 422
    )  # SSRF guard
    assert (
        client.post(
            f"/api/v1/projects/{pid}/sources",
            json={"kind": "openapi", "content": CLINIC},
            headers=h,
        ).status_code
        == 201
    )
    rid = client.post(
        f"/api/v1/projects/{pid}/compile", json={"annotator": "deterministic"}, headers=h
    ).json()["id"]
    with client.stream("GET", f"/api/v1/compile-runs/{rid}/events") as s:
        body = "".join(s.iter_text())
    for ev in ("event: stage", "event: validator", "event: kiro_event", "event: done"):
        assert ev in body
    run = client.get(f"/api/v1/compile-runs/{rid}").json()
    assert run["status"] == "verified"
    bid = run["bundle_id"]
    assert client.get(f"/api/v1/bundles/{bid}").json()["machine"]["root"]
    rep = client.get(f"/api/v1/bundles/{bid}/report").json()
    assert rep["annotation"]["annotator"] == "deterministic" and rep["all_passed"]
    assert client.get(f"/api/v1/bundles/{bid}/download").status_code == 200

    dep = client.post(f"/api/v1/bundles/{bid}/deployments", json={}, headers=h).json()
    url = dep["callback_url"].replace("http://testserver", "")
    r = client.post(url, data={"sessionId": "s", "phoneNumber": "+2348000000001", "text": ""})
    assert r.text.startswith("CON ")
    assert (
        client.post(url + "x", data={"sessionId": "s", "phoneNumber": "1", "text": ""}).status_code
        == 404
    )


def test_emulator_clinic_booking_and_sms_inbox(client, monkeypatch):
    monkeypatch.setenv("CLINIC_DEMO_PIN", "2468")
    ps = {p["slug"]: p for p in client.get("/api/v1/projects").json()}
    bid = client.get(f"/api/v1/projects/{ps['clinic-booking']['id']}").json()["bundles"][0]["id"]
    sid = client.post("/api/v1/emulator/sessions", json={"bundle_id": bid}).json()["session_id"]

    def inp(t):
        return client.post(f"/api/v1/emulator/sessions/{sid}/input", json={"text": t}).json()

    assert inp("")["type"] == "CON"
    out = inp("1*c1*s1*1*2468")
    assert out["type"] == "END" and "code:" in out["text"]
    out = inp("2")  # list clinics
    assert "Ikeja Clinic" in out["text"]


def test_emulator_farmer_mcp(client):
    ps = {p["slug"]: p for p in client.get("/api/v1/projects").json()}
    bid = client.get(f"/api/v1/projects/{ps['farmer-prices']['id']}").json()["bundles"][0]["id"]
    sid = client.post("/api/v1/emulator/sessions", json={"bundle_id": bid}).json()["session_id"]
    out = client.post(f"/api/v1/emulator/sessions/{sid}/input", json={"text": "1*2"}).json()
    assert out["type"] == "END" and "350" in out["text"]
