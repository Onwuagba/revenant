"""Platform tables (users, projects, sources, compile runs, bundles, deployments)."""

import sqlalchemy as sa

from ..runtime.store import metadata

users = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("email", sa.String(254), nullable=False, unique=True),
    sa.Column("pw_hash", sa.String(256), nullable=False),
    sa.Column("role", sa.String(16), nullable=False),  # owner | viewer
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sessions_web = sa.Table(
    "sessions_web",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("user_id", sa.String(36), nullable=False),
    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("csrf", sa.String(64), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
)
projects = sa.Table(
    "projects",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("owner_id", sa.String(36), nullable=True),
    sa.Column("slug", sa.String(64), nullable=False, unique=True),
    sa.Column("title", sa.String(120), nullable=False),
    sa.Column("is_public_sample", sa.Boolean, nullable=False, default=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sources = sa.Table(
    "sources",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("project_id", sa.String(36), nullable=False),
    sa.Column("kind", sa.String(16), nullable=False),  # openapi | mcp
    sa.Column("origin", sa.String(512), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("raw", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
compile_runs = sa.Table(
    "compile_runs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("project_id", sa.String(36), nullable=False),
    sa.Column("source_id", sa.String(36), nullable=False),
    sa.Column("owner_id", sa.String(36), nullable=True),
    sa.Column("status", sa.String(16), nullable=False),  # queued|running|verified|failed|refused
    sa.Column("stage", sa.String(16), nullable=False),
    sa.Column("annotator", sa.String(200), nullable=False, default=""),
    sa.Column("error", sa.Text, nullable=False, default=""),
    sa.Column("log", sa.Text, nullable=False, default="[]"),
    sa.Column("bundle_id", sa.String(36), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
)
refusals = sa.Table(
    "refusals",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(36), nullable=False),
    sa.Column("op_id", sa.String(128), nullable=False),
    sa.Column("path", sa.String(256), nullable=False),
    sa.Column("code", sa.String(32), nullable=False),
    sa.Column("message", sa.Text, nullable=False),
)
bundles = sa.Table(
    "bundles",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("project_id", sa.String(36), nullable=False),
    sa.Column("run_id", sa.String(36), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("bundle_hash", sa.String(64), nullable=False),
    sa.Column("bundle", sa.Text, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),  # verified | failed | deployed
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("project_id", "bundle_hash"),
)
deployments = sa.Table(
    "deployments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("bundle_id", sa.String(36), nullable=False),
    sa.Column("slug", sa.String(64), nullable=False),
    sa.Column("channel_code", sa.String(32), nullable=False, default=""),
    sa.Column("callback_token_hash", sa.String(64), nullable=False),
    sa.Column("sms_provider", sa.String(16), nullable=False, default="emulator"),
    sa.Column("upstream_base", sa.String(512), nullable=False, default=""),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
upstream_credentials = sa.Table(
    "upstream_credentials",
    metadata,
    sa.Column("project_id", sa.String(36), primary_key=True),
    sa.Column("ciphertext", sa.Text, nullable=False),  # AES-GCM; write-only via API
)

PLATFORM_TABLES = [
    users,
    sessions_web,
    projects,
    sources,
    compile_runs,
    refusals,
    bundles,
    deployments,
    upstream_credentials,
]
