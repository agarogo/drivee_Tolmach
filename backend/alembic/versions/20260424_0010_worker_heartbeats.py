"""Create scheduler worker heartbeat runtime table.

Revision ID: 20260424_0010
Revises: 20260424_0009
Create Date: 2026-04-24 17:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260424_0010"
down_revision: Union[str, Sequence[str], None] = "20260424_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB
UUID = postgresql.UUID


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("worker_name", sa.String(length=80), nullable=False),
        sa.Column("worker_type", sa.String(length=40), nullable=False, server_default="scheduler"),
        sa.Column("hostname", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("process_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="starting"),
        sa.Column(
            "metadata_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_name"),
        schema="app",
    )
    op.create_index("ix_app_worker_heartbeats_worker_name", "worker_heartbeats", ["worker_name"], unique=False, schema="app")
    op.create_index("ix_app_worker_heartbeats_worker_type", "worker_heartbeats", ["worker_type"], unique=False, schema="app")
    op.create_index("ix_app_worker_heartbeats_status", "worker_heartbeats", ["status"], unique=False, schema="app")
    op.create_index("ix_app_worker_heartbeats_last_seen_at", "worker_heartbeats", ["last_seen_at"], unique=False, schema="app")


def downgrade() -> None:
    op.drop_index("ix_app_worker_heartbeats_last_seen_at", table_name="worker_heartbeats", schema="app")
    op.drop_index("ix_app_worker_heartbeats_status", table_name="worker_heartbeats", schema="app")
    op.drop_index("ix_app_worker_heartbeats_worker_type", table_name="worker_heartbeats", schema="app")
    op.drop_index("ix_app_worker_heartbeats_worker_name", table_name="worker_heartbeats", schema="app")
    op.drop_table("worker_heartbeats", schema="app")
