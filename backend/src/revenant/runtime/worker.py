"""SMS outbox (SQL) and worker.

Claims pending rows with ``FOR UPDATE SKIP LOCKED`` (PostgreSQL; ignored by
SQLite), retries with exponential backoff up to ``MAX_ATTEMPTS``, sends only to
the session's own MSISDN (stored encrypted at enqueue time), and enforces
per-MSISDN, per-deployment and daily caps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import sqlalchemy as sa

from .sms import SmsProvider, count_segments
from .store import MsisdnCodec, now, sms_outbox

logger = logging.getLogger("revenant.runtime.worker")

MAX_ATTEMPTS = 5
BACKOFF_BASE = timedelta(seconds=10)
PER_MSISDN_PER_HOUR = 5
PER_DEPLOYMENT_PER_HOUR = 200
DAILY_CAP = 1000


class SqlSmsOutbox:
    def __init__(self, engine: sa.Engine, codec: MsisdnCodec) -> None:
        self.engine = engine
        self.codec = codec

    def enqueue(self, msisdn: str, body: str, deployment_id: str = "") -> str:
        eid = str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                sa.insert(sms_outbox).values(
                    id=eid,
                    deployment_id=deployment_id,
                    msisdn_enc=self.codec.encrypt(msisdn),
                    msisdn_hmac=self.codec.hmac(msisdn),
                    body=body,
                    segments=count_segments(body),
                    status="pending",
                    attempts=0,
                    next_attempt_at=now(),
                    provider_ref="",
                    created_at=now(),
                )
            )
        return eid

    def all(self) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(sa.select(sms_outbox)).mappings()]


class SmsWorker:
    def __init__(
        self,
        engine: sa.Engine,
        codec: MsisdnCodec,
        provider: SmsProvider,
        *,
        per_msisdn_per_hour: int = PER_MSISDN_PER_HOUR,
        per_deployment_per_hour: int = PER_DEPLOYMENT_PER_HOUR,
        daily_cap: int = DAILY_CAP,
    ) -> None:
        self.engine, self.codec, self.provider = engine, codec, provider
        self.per_msisdn = per_msisdn_per_hour
        self.per_dep = per_deployment_per_hour
        self.daily_cap = daily_cap

    def _sent_since(self, conn: sa.Connection, since: datetime, **where: Any) -> int:
        q = (
            sa.select(sa.func.count())
            .select_from(sms_outbox)
            .where(sms_outbox.c.status == "sent", sms_outbox.c.created_at >= since)
        )
        for k, v in where.items():
            q = q.where(sms_outbox.c[k] == v)
        return conn.execute(q).scalar_one()

    def run_once(self, batch: int = 20) -> dict[str, int]:
        stats = {"sent": 0, "retry": 0, "failed": 0, "deferred": 0}
        with self.engine.begin() as conn:
            rows = (
                conn.execute(
                    sa.select(sms_outbox)
                    .where(sms_outbox.c.status == "pending", sms_outbox.c.next_attempt_at <= now())
                    .limit(batch)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for row in rows:
                hour_ago, day_ago = now() - timedelta(hours=1), now() - timedelta(days=1)
                over = (
                    self._sent_since(conn, hour_ago, msisdn_hmac=row["msisdn_hmac"])
                    >= self.per_msisdn
                    or self._sent_since(conn, hour_ago, deployment_id=row["deployment_id"])
                    >= self.per_dep
                    or self._sent_since(conn, day_ago) >= self.daily_cap
                )
                if over:
                    conn.execute(
                        sa.update(sms_outbox)
                        .where(sms_outbox.c.id == row["id"])
                        .values(next_attempt_at=now() + timedelta(minutes=10))
                    )
                    stats["deferred"] += 1
                    continue
                attempts = row["attempts"] + 1
                try:
                    # Own MSISDN only: the number comes from the row written
                    # for this session, never from request input.
                    ref = self.provider.send(self.codec.decrypt(row["msisdn_enc"]), row["body"])
                    conn.execute(
                        sa.update(sms_outbox)
                        .where(sms_outbox.c.id == row["id"])
                        .values(status="sent", attempts=attempts, provider_ref=ref)
                    )
                    stats["sent"] += 1
                except Exception as exc:
                    logger.warning("SMS send failed: %s", type(exc).__name__)
                    if attempts >= MAX_ATTEMPTS:
                        conn.execute(
                            sa.update(sms_outbox)
                            .where(sms_outbox.c.id == row["id"])
                            .values(status="failed", attempts=attempts)
                        )
                        stats["failed"] += 1
                    else:
                        conn.execute(
                            sa.update(sms_outbox)
                            .where(sms_outbox.c.id == row["id"])
                            .values(
                                attempts=attempts,
                                next_attempt_at=now() + BACKOFF_BASE * (2 ** (attempts - 1)),
                            )
                        )
                        stats["retry"] += 1
        return stats
