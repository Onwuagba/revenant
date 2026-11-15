"""Seed public sample projects (read-only) and an optional viewer account."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import sqlalchemy as sa

from . import models as m

EXAMPLES = Path(__file__).resolve().parents[4] / "examples"

#: Static tool list for the bundled farmer-prices MCP sample (same tools as the sample server).
FARMER_TOOLS = [
    {"name": "get_crop_price", "description": "Get the current price per kg for a crop.",
     "inputSchema": {"type": "object", "required": ["crop"], "properties": {
         "crop": {"type": "string", "enum": ["maize", "rice", "beans", "cassava", "yam"]}}}},
    {"name": "search_market", "description": "Search market listings by free-text query.",
     "inputSchema": {"type": "object", "required": ["query"], "properties": {
         "query": {"type": "string"}}}},
]

SAMPLES = [
    ("clinic-booking", "Clinic booking (OpenAPI)", "openapi", "sample:clinic.openapi.yaml"),
    ("farmer-prices", "Farmer prices (MCP)", "mcp", "registry:farmer-prices"),
    ("unsupported-demo", "Unsupported demo (refusals)", "openapi", "sample:unsupported-demo.openapi.yaml"),
]


def _raw(slug: str) -> str:
    if slug == "farmer-prices":
        return json.dumps(FARMER_TOOLS)
    name = "clinic.openapi.yaml" if slug == "clinic-booking" else "unsupported-demo.openapi.yaml"
    return (EXAMPLES / "specs" / name).read_text()


def seed_samples(engine: sa.Engine, run_compile: Callable[..., None],
                 events: dict[str, list[dict[str, Any]]]) -> None:
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        pw = os.environ.get("REVENANT_VIEWER_PASSWORD")
        if pw and not c.execute(sa.select(m.users.c.id).where(m.users.c.email == "viewer@revenant.local")).first():
            from .app import hash_password

            c.execute(sa.insert(m.users).values(id=str(uuid4()), email="viewer@revenant.local",
                                                role="viewer", pw_hash=hash_password(pw), created_at=now))
    for slug, title, kind, origin in SAMPLES:
        with engine.begin() as c:
            if c.execute(sa.select(m.projects.c.id).where(m.projects.c.slug == slug)).first():
                continue
            pid, sid, rid = str(uuid4()), str(uuid4()), str(uuid4())
            raw = _raw(slug)
            c.execute(sa.insert(m.projects).values(id=pid, owner_id=None, slug=slug, title=title,
                                                   is_public_sample=True, created_at=now))
            c.execute(sa.insert(m.sources).values(id=sid, project_id=pid, kind=kind, origin=origin,
                                                  content_sha256="seed", raw=raw, created_at=now))
            c.execute(sa.insert(m.compile_runs).values(
                id=rid, project_id=pid, source_id=sid, owner_id=None, status="queued", stage="queued",
                annotator="", error="", log="[]", started_at=now))
        events[rid] = []
        # Samples are compiled deterministically at startup: no key, no network.
        run_compile(rid, {"kind": kind, "raw": raw, "origin": origin},
                    {"id": pid, "slug": slug, "title": title}, "deterministic", True)
