"""annotation cache keyed by (spec_hash, agent_version)"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "annotation_cache",
        sa.Column("spec_hash", sa.String(64), primary_key=True),
        sa.Column("agent_version", sa.String(32), primary_key=True),
        sa.Column("annotations", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("annotation_cache")
