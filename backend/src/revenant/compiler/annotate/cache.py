"""Annotation cache keyed by (spec_hash, agent_version)."""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from ...runtime.store import annotation_cache
from .schema import schema_errors


class AnnotationCache:
    def __init__(self, engine: sa.Engine) -> None:
        self.engine = engine
        annotation_cache.create(engine, checkfirst=True)

    def get(self, spec_hash: str, agent_version: str) -> dict[str, Any] | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(annotation_cache.c.annotations).where(
                    sa.and_(
                        annotation_cache.c.spec_hash == spec_hash,
                        annotation_cache.c.agent_version == agent_version,
                    )
                )
            ).first()
        if row is None:
            return None
        ann = json.loads(row[0])
        return ann if not schema_errors(ann) else None

    def put(self, spec_hash: str, agent_version: str, annotations: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                sa.delete(annotation_cache).where(
                    sa.and_(
                        annotation_cache.c.spec_hash == spec_hash,
                        annotation_cache.c.agent_version == agent_version,
                    )
                )
            )
            conn.execute(
                sa.insert(annotation_cache).values(
                    spec_hash=spec_hash,
                    agent_version=agent_version,
                    annotations=json.dumps(annotations, sort_keys=True),
                )
            )
