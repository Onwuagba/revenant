"""runtime tables: sessions, events, option cache, pin attempts, sms outbox

No column holds a PIN or any user-entered value (spec runtime-sms task 5).
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "ussd_sessions",
        sa.Column("session_id", sa.String(128), primary_key=True),
        sa.Column("deployment_id", sa.String(64), nullable=False),
        sa.Column("msisdn_hmac", sa.String(64), nullable=False),
        sa.Column("state_id", sa.String(128), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("last_response", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "session_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("state_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "option_cache",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pin_attempts",
        sa.Column("msisdn_hmac", sa.String(64), primary_key=True),
        sa.Column("deployment_id", sa.String(64), primary_key=True),
        sa.Column("failures", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "sms_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deployment_id", sa.String(64), nullable=False),
        sa.Column("msisdn_enc", sa.Text, nullable=False),
        sa.Column("msisdn_hmac", sa.String(64), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("segments", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_ref", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for t in ("sms_outbox", "pin_attempts", "option_cache", "session_events", "ussd_sessions"):
        op.drop_table(t)
