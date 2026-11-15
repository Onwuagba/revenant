"""Runtime persistence (SQLAlchemy Core; SQLite in tests, PostgreSQL in prod).

Tables follow ``docs/ARCHITECTURE.md`` section 6. No column may hold a PIN,
free-text input or any user-entered value: sessions keep only the state id,
step index and the last *response* (which is a rendered screen, never input).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa

metadata = sa.MetaData()

ussd_sessions = sa.Table(
    "ussd_sessions", metadata,
    sa.Column("session_id", sa.String(128), primary_key=True),
    sa.Column("deployment_id", sa.String(64), nullable=False),
    sa.Column("msisdn_hmac", sa.String(64), nullable=False),
    sa.Column("state_id", sa.String(128), nullable=False),
    sa.Column("step_index", sa.Integer, nullable=False),
    sa.Column("last_response", sa.Text, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
)

session_events = sa.Table(
    "session_events", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("session_id", sa.String(128), nullable=False),
    sa.Column("step_index", sa.Integer, nullable=False),
    sa.Column("state_id", sa.String(128), nullable=False),
    sa.Column("kind", sa.String(32), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
)

option_cache = sa.Table(
    "option_cache", metadata,
    sa.Column("key", sa.String(128), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
)

pin_attempts = sa.Table(
    "pin_attempts", metadata,
    sa.Column("msisdn_hmac", sa.String(64), primary_key=True),
    sa.Column("deployment_id", sa.String(64), primary_key=True),
    sa.Column("failures", sa.Integer, nullable=False, default=0),
    sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
)

sms_outbox = sa.Table(
    "sms_outbox", metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("deployment_id", sa.String(64), nullable=False),
    sa.Column("msisdn_enc", sa.Text, nullable=False),
    sa.Column("msisdn_hmac", sa.String(64), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("segments", sa.Integer, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False, default=0),
    sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("provider_ref", sa.String(64), nullable=False, default=""),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

#: Tables whose rows are dumped by the canary test.
ALL_TABLES = [ussd_sessions, session_events, option_cache, pin_attempts, sms_outbox]


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(url: str = "sqlite+pysqlite:///:memory:") -> sa.Engine:
    kwargs: dict[str, Any] = {}
    if url.startswith("sqlite") and ":memory:" in url:
        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": sa.pool.StaticPool}
    engine = sa.create_engine(url, **kwargs)
    return engine


def create_all(engine: sa.Engine) -> None:
    metadata.create_all(engine)


def dump_database(engine: sa.Engine) -> str:
    """Text dump of every runtime table (used by the canary PIN test)."""
    out: list[str] = []
    with engine.connect() as conn:
        for table in ALL_TABLES:
            for row in conn.execute(sa.select(table)):
                out.append(f"{table.name}: {tuple(row)}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# MSISDN protection
# ---------------------------------------------------------------------------
class MsisdnCodec:
    """HMAC for lookups/lockouts; AES-GCM for the stored, recoverable form."""

    def __init__(self, key: bytes | None = None) -> None:
        raw = key or os.environ.get("REVENANT_MSISDN_KEY", "").encode() or os.urandom(32)
        self._key = hashlib.sha256(raw).digest()

    def hmac(self, msisdn: str) -> str:
        return hmac.new(self._key, msisdn.encode(), hashlib.sha256).hexdigest()

    def encrypt(self, msisdn: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        ct = AESGCM(self._key).encrypt(nonce, msisdn.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt(self, blob: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = base64.b64decode(blob)
        return AESGCM(self._key).decrypt(raw[:12], raw[12:], None).decode()


# ---------------------------------------------------------------------------
# Session cache + events
# ---------------------------------------------------------------------------
SESSION_TTL = timedelta(minutes=5)


class SessionStore:
    def __init__(self, engine: sa.Engine) -> None:
        self.engine = engine

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(ussd_sessions).where(ussd_sessions.c.session_id == session_id)
            ).mappings().first()
        if row is None:
            return None
        exp = row["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now():
            return None
        return dict(row)

    def put(self, *, session_id: str, deployment_id: str, msisdn_hmac: str,
            state_id: str, step_index: int, last_response: str) -> None:
        values = dict(
            session_id=session_id, deployment_id=deployment_id, msisdn_hmac=msisdn_hmac,
            state_id=state_id, step_index=step_index, last_response=last_response,
            expires_at=now() + SESSION_TTL,
        )
        with self.engine.begin() as conn:
            res = conn.execute(
                sa.update(ussd_sessions)
                .where(ussd_sessions.c.session_id == session_id).values(**values)
            )
            if res.rowcount == 0:
                conn.execute(sa.insert(ussd_sessions).values(**values))

    def event(self, session_id: str, step_index: int, state_id: str, kind: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(sa.insert(session_events).values(
                session_id=session_id, step_index=step_index,
                state_id=state_id, kind=kind, at=now()))

    def events(self, session_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(session_events).where(session_events.c.session_id == session_id)
            ).mappings().all()
        return [dict(r) for r in rows]

    def purge(self, *, sent_sms_older_than: timedelta = timedelta(hours=24)) -> dict[str, int]:
        """Retention: drop expired sessions/option-cache and old sent SMS rows."""
        cutoff = now() - sent_sms_older_than
        with self.engine.begin() as conn:
            s = conn.execute(sa.delete(ussd_sessions).where(ussd_sessions.c.expires_at < now()))
            c = conn.execute(sa.delete(option_cache).where(option_cache.c.expires_at < now()))
            m = conn.execute(sa.delete(sms_outbox).where(
                sa.and_(sms_outbox.c.status == "sent", sms_outbox.c.created_at < cutoff)))
        return {"sessions": s.rowcount, "options": c.rowcount, "sms": m.rowcount}


class OptionCache:
    """TTL cache for fetched upstream lists (default 60 s)."""

    def __init__(self, engine: sa.Engine, ttl: timedelta = timedelta(seconds=60)) -> None:
        self.engine = engine
        self.ttl = ttl

    def get(self, key: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(option_cache).where(option_cache.c.key == key)).mappings().first()
        if row is None:
            return None
        exp = row["expires_at"]
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return row["value"] if exp >= now() else None

    def put(self, key: str, value: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(sa.delete(option_cache).where(option_cache.c.key == key))
            conn.execute(sa.insert(option_cache).values(
                key=key, value=value, expires_at=now() + self.ttl))


# ---------------------------------------------------------------------------
# PIN lockout
# ---------------------------------------------------------------------------
MAX_PIN_FAILURES = 3
LOCK_DURATION = timedelta(minutes=15)


class PinGuard:
    """3 failures per (MSISDN HMAC, deployment) -> 15 minute lock."""

    def __init__(self, engine: sa.Engine) -> None:
        self.engine = engine

    def _row(self, conn: sa.Connection, h: str, dep: str) -> dict[str, Any] | None:
        r = conn.execute(sa.select(pin_attempts).where(sa.and_(
            pin_attempts.c.msisdn_hmac == h, pin_attempts.c.deployment_id == dep))).mappings().first()
        return dict(r) if r else None

    def is_locked(self, h: str, dep: str) -> bool:
        with self.engine.connect() as conn:
            r = self._row(conn, h, dep)
        if not r or not r["locked_until"]:
            return False
        lu = r["locked_until"]
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=timezone.utc)
        return lu > now()

    def record_failure(self, h: str, dep: str) -> bool:
        """Record a failure; returns True if the MSISDN is now locked."""
        with self.engine.begin() as conn:
            r = self._row(conn, h, dep)
            if r is None:
                conn.execute(sa.insert(pin_attempts).values(
                    msisdn_hmac=h, deployment_id=dep, failures=1, locked_until=None))
                failures = 1
            else:
                failures = r["failures"] + 1
                locked = now() + LOCK_DURATION if failures >= MAX_PIN_FAILURES else None
                conn.execute(sa.update(pin_attempts).where(sa.and_(
                    pin_attempts.c.msisdn_hmac == h, pin_attempts.c.deployment_id == dep
                )).values(failures=failures, locked_until=locked))
        return failures >= MAX_PIN_FAILURES

    def record_success(self, h: str, dep: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(sa.delete(pin_attempts).where(sa.and_(
                pin_attempts.c.msisdn_hmac == h, pin_attempts.c.deployment_id == dep)))
