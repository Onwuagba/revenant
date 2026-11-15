"""platform tables"""
from alembic import op

from revenant.api.models import PLATFORM_TABLES

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    bind = op.get_bind()
    for t in PLATFORM_TABLES:
        t.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for t in reversed(PLATFORM_TABLES):
        t.drop(bind, checkfirst=True)
