"""Add query execution cache and audit tables.

Revision ID: 20260423_0007
Revises: 20260423_0006
Create Date: 2026-04-24 03:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0007"
down_revision: Union[str, Sequence[str], None] = "20260423_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "query_result_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("row_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("explain_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("explain_plan_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_rows_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_app_query_result_cache_fingerprint"),
        schema="app",
    )
    op.create_index("ix_app_query_result_cache_role", "query_result_cache", ["role"], unique=False, schema="app")
    op.create_index("ix_app_query_result_cache_expires_at", "query_result_cache", ["expires_at"], unique=False, schema="app")

    op.create_table(
        "query_execution_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_mode", sa.String(length=20), nullable=False, server_default="database"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("explain_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("details_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("explain_plan_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["query_id"], ["app.queries.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index("ix_app_query_execution_audit_query_id", "query_execution_audit", ["query_id"], unique=False, schema="app")
    op.create_index("ix_app_query_execution_audit_fingerprint", "query_execution_audit", ["fingerprint"], unique=False, schema="app")
    op.create_index("ix_app_query_execution_audit_role", "query_execution_audit", ["role"], unique=False, schema="app")
    op.create_index("ix_app_query_execution_audit_cache_hit", "query_execution_audit", ["cache_hit"], unique=False, schema="app")
    op.create_index("ix_app_query_execution_audit_status", "query_execution_audit", ["status"], unique=False, schema="app")
    op.create_index("ix_app_query_execution_audit_created_at", "query_execution_audit", ["created_at"], unique=False, schema="app")


def downgrade() -> None:
    op.drop_index("ix_app_query_execution_audit_created_at", table_name="query_execution_audit", schema="app")
    op.drop_index("ix_app_query_execution_audit_status", table_name="query_execution_audit", schema="app")
    op.drop_index("ix_app_query_execution_audit_cache_hit", table_name="query_execution_audit", schema="app")
    op.drop_index("ix_app_query_execution_audit_role", table_name="query_execution_audit", schema="app")
    op.drop_index("ix_app_query_execution_audit_fingerprint", table_name="query_execution_audit", schema="app")
    op.drop_index("ix_app_query_execution_audit_query_id", table_name="query_execution_audit", schema="app")
    op.drop_table("query_execution_audit", schema="app")

    op.drop_index("ix_app_query_result_cache_expires_at", table_name="query_result_cache", schema="app")
    op.drop_index("ix_app_query_result_cache_role", table_name="query_result_cache", schema="app")
    op.drop_table("query_result_cache", schema="app")
