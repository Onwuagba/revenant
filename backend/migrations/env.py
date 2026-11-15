"""Alembic env: URL from REVENANT_DATABASE_URL, falling back to alembic.ini."""
import os

from alembic import context
from sqlalchemy import create_engine

from revenant.runtime.store import metadata

config = context.config
url = os.environ.get("REVENANT_DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
