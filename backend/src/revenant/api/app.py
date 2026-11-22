"""Platform API: ``create_app()`` serves ``/api/v1`` plus the AT-facing runtime route.

Auth: email + password (scrypt), server-side session, HttpOnly SameSite=Lax
cookie, CSRF double-submit header on state-changing owner calls. Roles:
``owner`` (own projects) and ``viewer`` (read-only; samples + emulator).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..compiler.annotate.cache import AnnotationCache
from ..compiler.annotate.pipeline import compile_with_annotation
from ..compiler.ingest_mcp import ingest_mcp, ingest_mcp_tools
from ..compiler.ingest_openapi import IngestError, ingest_openapi
from ..compiler.subset import classify_app
from ..runtime.service import ERROR_MSG, Deployment, UssdService
from ..runtime.sms import EmulatorSms
from ..runtime.store import MsisdnCodec, create_all, make_engine
from ..runtime.worker import SmsWorker
from . import models as m

MAX_SOURCE_BYTES = 2 * 1024 * 1024
SESSION_COOKIE = "rv_session"
CSRF_HEADER = "x-csrf-token"


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        cand = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(cand.hex(), dk)
    except Exception:
        return False


def problem(status: int, title: str, detail: str = "") -> HTTPException:
    """RFC 7807 problem details."""
    return HTTPException(
        status_code=status,
        detail={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )


class Creds(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")


class SourceIn(BaseModel):
    kind: str = Field(pattern="^(openapi|mcp)$")
    content: str | None = None
    url: str | None = None


class CompileIn(BaseModel):
    annotator: str = Field(default="auto", pattern="^(kiro|deterministic|auto)$")
    fresh: bool = False


class DeployIn(BaseModel):
    upstream_base: str = ""
    sms_provider: str = Field(default="emulator", pattern="^(emulator|africastalking)$")


class EmuStart(BaseModel):
    bundle_id: str | None = None
    deployment_id: str | None = None
    msisdn: str = Field(default="+2348000000000", pattern=r"^\+?[0-9]{7,15}$")


class EmuInput(BaseModel):
    text: str = Field(default="", max_length=200)


class CredIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


def create_app(
    engine: sa.Engine | None = None, *, seed: bool = True, runs_root: Path = Path("runs")
) -> FastAPI:
    engine = engine or make_engine(
        os.environ.get("REVENANT_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    )
    create_all(engine)
    codec = MsisdnCodec()
    sms = EmulatorSms()
    service = UssdService(engine=engine, codec=codec)
    worker = SmsWorker(engine, codec, sms)
    events: dict[str, list[dict[str, Any]]] = {}
    emu_sessions: dict[str, dict[str, Any]] = {}
    login_attempts: dict[str, list[float]] = {}

    app = FastAPI(title="Revenant platform API")
    app.state.engine, app.state.service, app.state.worker, app.state.sms = (
        engine,
        service,
        worker,
        sms,
    )

    @app.exception_handler(HTTPException)
    async def _http_exc(_: Request, exc: HTTPException) -> JSONResponse:
        body = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"type": "about:blank", "title": str(exc.detail), "status": exc.status_code}
        )
        return JSONResponse(
            body, status_code=exc.status_code, media_type="application/problem+json"
        )

    # ------------------------------------------------------------------ auth
    def current_user(request: Request) -> dict[str, Any] | None:
        tok = request.cookies.get(SESSION_COOKIE)
        if not tok:
            return None
        with engine.connect() as c:
            row = (
                c.execute(
                    sa.select(m.sessions_web, m.users.c.email, m.users.c.role)
                    .join(m.users, m.users.c.id == m.sessions_web.c.user_id)
                    .where(m.sessions_web.c.token_hash == _sha(tok))
                )
                .mappings()
                .first()
            )
        if not row or _aware(row["expires_at"]) < _now():
            return None
        return {
            "id": row["user_id"],
            "email": row["email"],
            "role": row["role"],
            "csrf": row["csrf"],
        }

    def require_user(request: Request, user: dict | None = Depends(current_user)) -> dict[str, Any]:
        if user is None:
            raise problem(401, "Not signed in")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get(CSRF_HEADER, ""), user["csrf"]):
                raise problem(403, "CSRF token missing or invalid")
        return user

    def require_owner(user: dict = Depends(require_user)) -> dict[str, Any]:
        if user["role"] != "owner":
            raise problem(403, "Read-only account")
        return user

    def _new_session(c: sa.Connection, user_id: str, response: Response) -> str:
        tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        c.execute(
            sa.insert(m.sessions_web).values(
                id=str(uuid4()),
                user_id=user_id,
                token_hash=_sha(tok),
                csrf=csrf,
                expires_at=_now() + timedelta(days=7),
            )
        )
        response.set_cookie(
            SESSION_COOKIE,
            tok,
            httponly=True,
            samesite="lax",
            secure=os.environ.get("REVENANT_INSECURE_COOKIES") != "1",
            max_age=7 * 86400,
        )
        return csrf

    @app.post("/api/v1/auth/register", status_code=201)
    def register(body: Creds, response: Response) -> dict[str, Any]:
        email = body.email.strip().lower()
        with engine.begin() as c:
            if c.execute(sa.select(m.users.c.id).where(m.users.c.email == email)).first():
                raise problem(409, "Email already registered")
            uid = str(uuid4())
            c.execute(
                sa.insert(m.users).values(
                    id=uid,
                    email=email,
                    role="owner",
                    pw_hash=hash_password(body.password),
                    created_at=_now(),
                )
            )
            csrf = _new_session(c, uid, response)
        return {"id": uid, "email": email, "role": "owner", "csrf": csrf}

    @app.post("/api/v1/auth/login")
    def login(body: Creds, response: Response) -> dict[str, Any]:
        email = body.email.strip().lower()
        recent = [t for t in login_attempts.get(email, []) if time.time() - t < 300]
        if len(recent) >= 5:
            raise problem(429, "Too many attempts. Try again later.")
        with engine.begin() as c:
            row = c.execute(sa.select(m.users).where(m.users.c.email == email)).mappings().first()
            if not row or not verify_password(body.password, row["pw_hash"]):
                login_attempts[email] = recent + [time.time()]
                raise problem(401, "Invalid email or password")
            csrf = _new_session(c, row["id"], response)
        login_attempts.pop(email, None)
        return {"id": row["id"], "email": email, "role": row["role"], "csrf": csrf}

    @app.post("/api/v1/auth/logout")
    def logout(response: Response, user: dict = Depends(require_user)) -> dict[str, bool]:
        with engine.begin() as c:
            c.execute(sa.delete(m.sessions_web).where(m.sessions_web.c.user_id == user["id"]))
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/v1/me")
    def me(user: dict | None = Depends(current_user)) -> dict[str, Any]:
        if user is None:
            raise problem(401, "Not signed in")
        return {
            "id": user["id"],
            "email": user["email"],
            "role": user["role"],
            "csrf": user["csrf"],
        }

    # -------------------------------------------------------------- projects
    def _project(pid: str) -> dict[str, Any]:
        with engine.connect() as c:
            row = (
                c.execute(
                    sa.select(m.projects).where(
                        sa.or_(m.projects.c.id == pid, m.projects.c.slug == pid)
                    )
                )
                .mappings()
                .first()
            )
        if not row:
            raise problem(404, "Project not found")
        return dict(row)

    def _can_read(p: dict, user: dict | None) -> bool:
        return bool(p["is_public_sample"] or (user and p["owner_id"] == user["id"]))

    def _readable_project(pid: str, user: dict | None) -> dict[str, Any]:
        p = _project(pid)
        if not _can_read(p, user):
            raise problem(404, "Project not found")  # no existence leak across projects
        return p

    def _owned_project(pid: str, user: dict) -> dict[str, Any]:
        p = _project(pid)
        if p["owner_id"] != user["id"]:
            raise problem(404, "Project not found")
        return p

    def _pub(p: dict) -> dict[str, Any]:
        return {
            "id": p["id"],
            "slug": p["slug"],
            "title": p["title"],
            "is_public_sample": p["is_public_sample"],
        }

    @app.get("/api/v1/projects")
    def list_projects(user: dict | None = Depends(current_user)) -> list[dict[str, Any]]:
        cond = m.projects.c.is_public_sample == True  # noqa: E712
        if user:
            cond = sa.or_(cond, m.projects.c.owner_id == user["id"])
        with engine.connect() as c:
            rows = c.execute(
                sa.select(m.projects).where(cond).order_by(m.projects.c.created_at)
            ).mappings()
            return [_pub(dict(r)) for r in rows]

    @app.post("/api/v1/projects", status_code=201)
    def create_project(body: ProjectIn, user: dict = Depends(require_owner)) -> dict[str, Any]:
        with engine.begin() as c:
            if c.execute(sa.select(m.projects.c.id).where(m.projects.c.slug == body.slug)).first():
                raise problem(409, "Slug already used")
            pid = str(uuid4())
            c.execute(
                sa.insert(m.projects).values(
                    id=pid,
                    owner_id=user["id"],
                    slug=body.slug,
                    title=body.title,
                    is_public_sample=False,
                    created_at=_now(),
                )
            )
        return _pub(_project(pid))

    @app.get("/api/v1/projects/{pid}")
    def get_project(pid: str, user: dict | None = Depends(current_user)) -> dict[str, Any]:
        p = _readable_project(pid, user)
        with engine.connect() as c:
            runs = (
                c.execute(
                    sa.select(m.compile_runs)
                    .where(m.compile_runs.c.project_id == p["id"])
                    .order_by(m.compile_runs.c.started_at.desc())
                )
                .mappings()
                .all()
            )
            bnd = (
                c.execute(
                    sa.select(
                        m.bundles.c.id,
                        m.bundles.c.version,
                        m.bundles.c.status,
                        m.bundles.c.bundle_hash,
                    )
                    .where(m.bundles.c.project_id == p["id"])
                    .order_by(m.bundles.c.version.desc())
                )
                .mappings()
                .all()
            )
        return {
            **_pub(p),
            "runs": [
                {
                    "id": r["id"],
                    "status": r["status"],
                    "stage": r["stage"],
                    "annotator": r["annotator"],
                    "bundle_id": r["bundle_id"],
                }
                for r in runs
            ],
            "bundles": [dict(b) for b in bnd],
        }

    @app.post("/api/v1/projects/{pid}/sources", status_code=201)
    async def add_source(
        pid: str, body: SourceIn, user: dict = Depends(require_owner)
    ) -> dict[str, Any]:
        p = _owned_project(pid, user)
        if body.kind == "openapi":
            if not body.content:
                raise problem(422, "OpenAPI content required")
            raw, origin = body.content, "upload"
            if len(raw.encode()) > MAX_SOURCE_BYTES:
                raise problem(413, "Spec exceeds 2 MB")
        else:
            if not body.url:
                raise problem(422, "MCP url required")
            from ..compiler.urlguard import UrlGuardError, check_url

            try:
                check_url(body.url)  # SSRF guard before anything is stored or fetched
            except UrlGuardError as exc:
                raise problem(422, "URL refused", str(exc)[:200]) from exc
            except Exception as exc:
                raise problem(422, "URL refused") from exc
            raw, origin = "", body.url
        sid = str(uuid4())
        with engine.begin() as c:
            c.execute(
                sa.insert(m.sources).values(
                    id=sid,
                    project_id=p["id"],
                    kind=body.kind,
                    origin=origin[:512],
                    content_sha256=_sha(raw or origin),
                    raw=raw,
                    created_at=_now(),
                )
            )
        return {"id": sid, "kind": body.kind, "origin": origin}

    @app.put("/api/v1/projects/{pid}/credentials")
    def put_credentials(
        pid: str, body: CredIn, user: dict = Depends(require_owner)
    ) -> dict[str, bool]:
        p = _owned_project(pid, user)
        blob = codec.encrypt(body.api_key)
        with engine.begin() as c:
            c.execute(
                sa.delete(m.upstream_credentials).where(
                    m.upstream_credentials.c.project_id == p["id"]
                )
            )
            c.execute(sa.insert(m.upstream_credentials).values(project_id=p["id"], ciphertext=blob))
        return {"stored": True}  # write-only: never returned

    # --------------------------------------------------------------- compile
    def _emit(run_id: str, kind: str, **data: Any) -> None:
        ev = {"event": kind, "data": data, "t": round(time.time(), 3)}
        events.setdefault(run_id, []).append(ev)
        with engine.begin() as c:
            c.execute(
                sa.update(m.compile_runs)
                .where(m.compile_runs.c.id == run_id)
                .values(log=json.dumps(events[run_id]))
            )

    def _set_run(run_id: str, **vals: Any) -> None:
        with engine.begin() as c:
            c.execute(sa.update(m.compile_runs).where(m.compile_runs.c.id == run_id).values(**vals))

    def run_compile(
        run_id: str, source: dict[str, Any], project: dict[str, Any], mode: str, fresh: bool
    ) -> None:
        try:
            _set_run(run_id, status="running", stage="exhume")
            _emit(run_id, "stage", name="exhume", label="Exhume")
            if source["kind"] == "openapi":
                drafts, ing_ref = ingest_openapi(source["raw"])
            elif source["raw"]:
                drafts, ing_ref = ingest_mcp_tools(json.loads(source["raw"]))
            else:
                drafts, ing_ref = asyncio.run(ingest_mcp(source["origin"]))
            _emit(run_id, "log", message=f"Ingested {len(drafts)} operation(s)")
            app_ir, report = classify_app(drafts, slug=project["slug"], title=project["title"])
            refusals = report["refusals"] + [
                {
                    "op_id": r.op_id,
                    "path": r.path,
                    "code": r.code.value,
                    "message": r.message,
                    "hint": r.hint,
                }
                for r in ing_ref
            ]
            with engine.begin() as c:
                for r in refusals:
                    c.execute(
                        sa.insert(m.refusals).values(
                            run_id=run_id,
                            op_id=r["op_id"][:128],
                            path=r["path"][:256],
                            code=r["code"],
                            message=r.get("message", ""),
                        )
                    )
            _emit(
                run_id,
                "log",
                message=f"Compiled {report['compiled_count']}, refused {report['refused_count']}",
                per_code=report["per_code"],
            )
            if not app_ir.operations:
                _set_run(run_id, status="refused", stage="done", finished_at=_now())
                _emit(run_id, "done", status="refused", bundle_id=None)
                return

            _set_run(run_id, stage="reanimate")
            _emit(run_id, "stage", name="reanimate", label="Reanimate")
            kiro_on = mode == "kiro" or (mode == "auto" and bool(os.environ.get("KIRO_API_KEY")))
            bundle = compile_with_annotation(
                app_ir,
                refusals,
                kiro_enabled=kiro_on,
                cache=None if fresh else AnnotationCache(engine),
                runs_root=runs_root,
            )
            ann = bundle["report"]["annotation"]
            _emit(
                run_id,
                "kiro_event",
                annotator=ann["annotator"],
                cached=ann["cached"],
                kiro_model=ann["kiro_model"],
                exit_code=ann["exit_code"],
            )
            _set_run(run_id, annotator=ann["annotator"], stage="last_rites")
            _emit(run_id, "stage", name="last_rites", label="Last Rites")
            for v in bundle["report"]["validators"]:
                _emit(
                    run_id,
                    "validator",
                    validator=v["validator"],
                    passed=v["passed"],
                    violations=len(v["violations"]),
                )
            bundle["report"]["refusals"] = refusals
            status = "verified" if bundle["report"]["all_passed"] else "failed"
            bid = str(uuid4())
            with engine.begin() as c:
                dup = c.execute(
                    sa.select(m.bundles.c.id).where(
                        sa.and_(
                            m.bundles.c.project_id == project["id"],
                            m.bundles.c.bundle_hash == bundle["bundle_hash"],
                        )
                    )
                ).scalar()
                if dup:
                    bid = dup
                else:
                    ver = (
                        c.execute(
                            sa.select(sa.func.max(m.bundles.c.version)).where(
                                m.bundles.c.project_id == project["id"]
                            )
                        ).scalar()
                        or 0
                    ) + 1
                    c.execute(
                        sa.insert(m.bundles).values(
                            id=bid,
                            project_id=project["id"],
                            run_id=run_id,
                            version=ver,
                            bundle_hash=bundle["bundle_hash"],
                            bundle=json.dumps(bundle),
                            status=status,
                            created_at=_now(),
                        )
                    )
            _set_run(run_id, status=status, stage="done", bundle_id=bid, finished_at=_now())
            _emit(run_id, "done", status=status, bundle_id=bid)
        except IngestError as exc:
            _fail(run_id, f"{exc.code}: input could not be read")
        except Exception as exc:  # no internals leaked to the client
            _fail(run_id, f"Compile failed ({type(exc).__name__})")

    def _fail(run_id: str, msg: str) -> None:
        _set_run(run_id, status="failed", stage="done", error=msg, finished_at=_now())
        _emit(run_id, "done", status="failed", bundle_id=None, error=msg)

    @app.post("/api/v1/projects/{pid}/compile", status_code=202)
    def compile_project(
        pid: str, body: CompileIn, user: dict = Depends(require_owner)
    ) -> dict[str, Any]:
        p = _owned_project(pid, user)
        with engine.begin() as c:
            src = (
                c.execute(
                    sa.select(m.sources)
                    .where(m.sources.c.project_id == p["id"])
                    .order_by(m.sources.c.created_at.desc())
                )
                .mappings()
                .first()
            )
            if not src:
                raise problem(422, "Add a source first")
            busy = c.execute(
                sa.select(m.compile_runs.c.id).where(
                    sa.and_(
                        m.compile_runs.c.owner_id == user["id"],
                        m.compile_runs.c.status.in_(["queued", "running"]),
                    )
                )
            ).first()
            if busy:
                raise problem(429, "A compile is already running")
            rid = str(uuid4())
            c.execute(
                sa.insert(m.compile_runs).values(
                    id=rid,
                    project_id=p["id"],
                    source_id=src["id"],
                    owner_id=user["id"],
                    status="queued",
                    stage="queued",
                    annotator="",
                    error="",
                    log="[]",
                    started_at=_now(),
                )
            )
        events[rid] = []
        threading.Thread(
            target=run_compile, args=(rid, dict(src), p, body.annotator, body.fresh), daemon=True
        ).start()
        return {"id": rid, "status": "queued"}

    def _run_for(rid: str, user: dict | None) -> dict[str, Any]:
        with engine.connect() as c:
            r = (
                c.execute(sa.select(m.compile_runs).where(m.compile_runs.c.id == rid))
                .mappings()
                .first()
            )
        if not r:
            raise problem(404, "Run not found")
        _readable_project(r["project_id"], user)
        return dict(r)

    @app.get("/api/v1/compile-runs/{rid}")
    def get_run(rid: str, user: dict | None = Depends(current_user)) -> dict[str, Any]:
        r = _run_for(rid, user)
        return {
            "id": r["id"],
            "status": r["status"],
            "stage": r["stage"],
            "annotator": r["annotator"],
            "error": r["error"],
            "bundle_id": r["bundle_id"],
            "log": json.loads(r["log"]),
        }

    @app.get("/api/v1/compile-runs/{rid}/events")
    async def run_events(
        rid: str, user: dict | None = Depends(current_user)
    ) -> EventSourceResponse:
        _run_for(rid, user)

        async def gen():
            sent = 0
            while True:
                log = events.get(rid)
                if log is None:  # finished before this process (or restarted): replay from DB
                    log = json.loads(_run_for(rid, user)["log"])
                while sent < len(log):
                    ev = log[sent]
                    sent += 1
                    yield {"event": ev["event"], "data": json.dumps(ev["data"])}
                    if ev["event"] == "done":
                        return
                await asyncio.sleep(0.1)

        return EventSourceResponse(gen())

    # --------------------------------------------------------------- bundles
    def _bundle(bid: str, user: dict | None) -> tuple[dict[str, Any], dict[str, Any]]:
        with engine.connect() as c:
            row = c.execute(sa.select(m.bundles).where(m.bundles.c.id == bid)).mappings().first()
        if not row:
            raise problem(404, "Bundle not found")
        _readable_project(row["project_id"], user)
        return dict(row), json.loads(row["bundle"])

    @app.get("/api/v1/bundles/{bid}")
    def get_bundle(bid: str, user: dict | None = Depends(current_user)) -> dict[str, Any]:
        row, b = _bundle(bid, user)
        return {
            "id": bid,
            "status": row["status"],
            "version": row["version"],
            "bundle_hash": row["bundle_hash"],
            "ir": b["ir"],
            "machine": b["machine"],
            "screens": b["screens"],
        }

    @app.get("/api/v1/bundles/{bid}/report")
    def get_report(bid: str, user: dict | None = Depends(current_user)) -> dict[str, Any]:
        _, b = _bundle(bid, user)
        return b["report"]

    @app.get("/api/v1/bundles/{bid}/download")
    def download(bid: str, user: dict | None = Depends(current_user)) -> Response:
        row, b = _bundle(bid, user)
        return Response(
            json.dumps(b, indent=2, sort_keys=True),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="bundle-{row["bundle_hash"][:8]}.json"'
                )
            },
        )

    # ----------------------------------------------------------- deployments
    @app.post("/api/v1/bundles/{bid}/deployments", status_code=201)
    def create_deployment(
        bid: str, body: DeployIn, request: Request, user: dict = Depends(require_owner)
    ) -> dict[str, Any]:
        row, b = _bundle(bid, user)
        p = _owned_project(row["project_id"], user)
        if row["status"] != "verified":
            raise problem(422, "Only verified bundles can be deployed")
        token = secrets.token_urlsafe(24)
        did = str(uuid4())
        with engine.begin() as c:
            c.execute(
                sa.insert(m.deployments).values(
                    id=did,
                    bundle_id=bid,
                    slug=p["slug"],
                    channel_code="",
                    callback_token_hash=_sha(token),
                    sms_provider=body.sms_provider,
                    upstream_base=body.upstream_base,
                    status="active",
                    created_at=_now(),
                )
            )
            c.execute(sa.update(m.bundles).where(m.bundles.c.id == bid).values(status="deployed"))
        base = str(request.base_url).rstrip("/")
        # The token is shown exactly once; only its hash is stored.
        return {"id": did, "callback_url": f"{base}/ussd/{p['slug']}/{token}", "shown_once": True}

    @app.get("/api/v1/deployments/{did}/sessions")
    def deployment_sessions(did: str, user: dict = Depends(require_owner)) -> list[dict[str, Any]]:
        with engine.connect() as c:
            d = (
                c.execute(sa.select(m.deployments).where(m.deployments.c.id == did))
                .mappings()
                .first()
            )
            if not d:
                raise problem(404, "Deployment not found")
            b = c.execute(
                sa.select(m.bundles.c.project_id).where(m.bundles.c.id == d["bundle_id"])
            ).scalar()
        _owned_project(b, user)
        from ..runtime.store import session_events

        with engine.connect() as c:  # redacted by construction: no input values are stored
            rows = c.execute(
                sa.select(session_events).order_by(session_events.c.id.desc()).limit(100)
            ).mappings()
            return [
                {
                    "session_id": r["session_id"][:6] + "…",
                    "step_index": r["step_index"],
                    "state_id": r["state_id"],
                    "kind": r["kind"],
                    "at": r["at"].isoformat(),
                }
                for r in rows
            ]

    # ----------------------------------------------------- runtime (AT-facing)
    def _runtime_deployment(slug: str, token: str) -> Deployment | None:
        with engine.connect() as c:
            d = (
                c.execute(
                    sa.select(m.deployments).where(
                        sa.and_(
                            m.deployments.c.slug == slug,
                            m.deployments.c.status == "active",
                            m.deployments.c.callback_token_hash == _sha(token),
                        )
                    )
                )
                .mappings()
                .first()
            )
            if not d:
                return None
            row = c.execute(
                sa.select(m.bundles.c.bundle).where(m.bundles.c.id == d["bundle_id"])
            ).scalar()
        return _make_deployment(d["id"], slug, json.loads(row), d["upstream_base"])

    @app.post("/ussd/{slug}/{token}", response_class=PlainTextResponse)
    async def ussd(slug: str, token: str, request: Request) -> Response:
        dep = _runtime_deployment(slug, token)
        if dep is None:
            return PlainTextResponse("Not found", status_code=404)
        try:
            form = await request.form()
            sid, phone = (
                str(form.get("sessionId", "") or ""),
                str(form.get("phoneNumber", "") or ""),
            )
            text = form.get("text", "")
            text = text if isinstance(text, str) else ""
            if not sid or not phone:
                raise ValueError
        except Exception:
            return PlainTextResponse("END An error occurred. Try again later.")
        try:
            return PlainTextResponse(await service.handle(dep, sid, phone, text))
        except Exception:
            return PlainTextResponse("END " + ERROR_MSG)

    # -------------------------------------------------------------- emulator
    def _make_deployment(
        dep_id: str, slug: str, bundle: dict[str, Any], upstream: str
    ) -> Deployment:
        dep = Deployment(id=dep_id, slug=slug, bundle=bundle, upstream_base=upstream)
        if slug == "clinic-booking" or upstream.startswith("mock://clinic"):
            import httpx

            from examples.clinic_api.server import app as clinic

            dep.upstream_base = "http://clinic"
            dep.http_client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=clinic), base_url="http://clinic"
            )
        elif slug == "farmer-prices":
            from examples.farmer_prices_mcp import server as farmer

            async def call(tool: str, args: dict[str, Any]) -> Any:
                fn = getattr(farmer, tool, None)
                if tool not in ("get_crop_price",) or fn is None:
                    raise ValueError("unknown tool")
                return fn(**args)

            dep.mcp_call = call
        return dep

    @app.post("/api/v1/emulator/sessions", status_code=201)
    def emu_start(body: EmuStart, user: dict | None = Depends(current_user)) -> dict[str, Any]:
        if body.bundle_id:
            row, b = _bundle(body.bundle_id, user)
            p = _project(row["project_id"])
            dep = _make_deployment(f"emu-{row['id']}", p["slug"], b, "")
        elif body.deployment_id:
            raise problem(422, "Use bundle_id for the emulator")
        else:
            raise problem(422, "bundle_id required")
        sid = "emu-" + secrets.token_hex(8)
        emu_sessions[sid] = {"dep": dep, "msisdn": body.msisdn}
        return {"session_id": sid, "label": "simulated handset", "max_chars": 182}

    @app.post("/api/v1/emulator/sessions/{sid}/input")
    async def emu_input(sid: str, body: EmuInput) -> dict[str, str]:
        s = emu_sessions.get(sid)
        if not s:
            raise problem(404, "Session not found")
        out = await service.handle(
            s["dep"], sid, s["msisdn"], body.text
        )  # same path as AT callback
        worker.run_once()
        return {"type": out[:3], "text": out[4:]}

    @app.get("/api/v1/emulator/inbox/{msisdn}")
    def emu_inbox(msisdn: str) -> list[dict[str, str]]:
        worker.run_once()
        return [{"body": x["body"]} for x in sms.get_inbox(msisdn)]

    @app.get("/api/v1/healthz")
    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    if seed:
        from .seed import seed_samples

        seed_samples(engine, run_compile, events)

    # Single-service deployment (e.g. Render): serve the built console from the same origin.
    # Registered last so /api, /ussd and /healthz keep priority. Unset locally (Vite serves it).
    console_dir = os.environ.get("REVENANT_CONSOLE_DIR")
    if console_dir and Path(console_dir, "index.html").is_file():
        root = Path(console_dir).resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def console(path: str) -> FileResponse:
            if path.startswith(("api/", "ussd/")):
                raise problem(404, "Not found")
            candidate = (root / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            if path.startswith("assets/"):
                raise problem(404, "Not found")  # a missing asset must not be served as HTML
            return FileResponse(root / "index.html")  # SPA fallback

    return app
