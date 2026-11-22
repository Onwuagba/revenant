"""Shared pytest configuration: register the ``pbt`` marker and Hypothesis profiles.

Profiles (from steering testing.md / docs/TESTING.md):
  - dev:  50 examples, fast, used by the on-save hook
  - ci:   200 examples, derandomised seed printed
  - deep: nightly/manual, higher example count

The marker is registered programmatically so no separate ini file is needed.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, settings


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "pbt: property-based tests using Hypothesis")
    config.addinivalue_line("markers", "integration: integration tests using in-process mocks")
    config.addinivalue_line("markers", "e2e: end-to-end tests")


# ---------------------------------------------------------------------------
# Hypothesis profiles
# ---------------------------------------------------------------------------
settings.register_profile(
    "dev",
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "ci",
    max_examples=200,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    print_blob=True,
)
settings.register_profile(
    "deep",
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# Load the profile from --hypothesis-profile=<name>, default to dev.
settings.load_profile("dev")


# ---------------------------------------------------------------------------
# Optional: run the same suite against PostgreSQL 16 (steering tech.md, testing.md)
#
#   REVENANT_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:5432/postgres pytest tests
#
# Every default in-memory engine becomes a fresh, empty Postgres database (dropped at the end),
# so tests stay isolated. Explicit SQLite file URLs (the Alembic test) are left alone.
# ---------------------------------------------------------------------------
_PG_URL = __import__("os").environ.get("REVENANT_TEST_PG_URL", "")
_PG_DATABASES: list[str] = []

if _PG_URL:
    from uuid import uuid4

    import revenant.runtime.store as _store
    import sqlalchemy as sa

    _admin = sa.create_engine(_PG_URL, isolation_level="AUTOCOMMIT")
    _original_make_engine = _store.make_engine

    def _pg_make_engine(url: str = "sqlite+pysqlite:///:memory:") -> sa.Engine:
        if not (url.startswith("sqlite") and ":memory:" in url):
            return _original_make_engine(url)
        name = f"revenant_t_{uuid4().hex[:12]}"
        with _admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{name}"'))
        _PG_DATABASES.append(name)
        return _original_make_engine(str(sa.make_url(_PG_URL).set(database=name)))

    _store.make_engine = _pg_make_engine


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not _PG_URL:
        return
    with _admin.connect() as conn:
        for name in _PG_DATABASES:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def pytest_report_header(config: pytest.Config) -> str:
    return f"database: {'PostgreSQL (' + _PG_URL.split('@')[-1] + ')' if _PG_URL else 'SQLite'}"
