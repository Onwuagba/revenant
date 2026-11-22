"""Mock clinic upstream used by the demo and the runtime tests.

Matches ``examples/specs/clinic.openapi.yaml``. The PIN is checked against
``CLINIC_DEMO_PIN`` (default ``2468``); wrong PIN -> 401. Slow and error modes
are switchable for failure tests via ``app.state.mode``.
"""
from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

CLINICS = [{"id": "c1", "name": "Ikeja Clinic"}, {"id": "c2", "name": "Yaba Clinic"}]
SLOTS = [{"id": "s1", "label": "09:00"}, {"id": "s2", "label": "10:30"}]


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.mode = "ok"  # ok | slow | error | async
    app.state.calls = []

    @app.get("/clinics")
    async def clinics(request: Request):
        app.state.calls.append(("GET", "/clinics"))
        return CLINICS

    @app.get("/slots")
    async def slots(request: Request):
        app.state.calls.append(("GET", "/slots"))
        return SLOTS

    @app.post("/appointments")
    async def appointments(request: Request):
        body = await request.json()
        app.state.calls.append(("POST", "/appointments"))
        if app.state.mode == "slow":
            await asyncio.sleep(5)
        if app.state.mode == "error":
            return JSONResponse({"error": "boom"}, status_code=500)
        if app.state.mode == "async":
            return JSONResponse({"status": "queued"}, status_code=202)
        if body.get("pin") != (os.environ.get("CLINIC_DEMO_PIN") or "2468"):
            return JSONResponse({"error": "bad pin"}, status_code=401)
        return JSONResponse({"code": "BK" + str(len(app.state.calls)), "time": "09:00"}, status_code=201)

    return app


app = create_app()
