"""Persist answer contract fields on queries.

Revision ID: 20260424_0009
Revises: 20260424_0008
Create Date: 2026-04-24 18:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260424_0009"
down_revision: Union[str, Sequence[str], None] = "20260424_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.add_column("queries", sa.Column("answer_type_code", sa.Integer(), nullable=False, server_default="5"), schema="app")
    op.add_column(
        "queries",
        sa.Column("answer_type_key", sa.String(length=32), nullable=False, server_default="table"),
        schema="app",
    )
    op.add_column(
        "queries",
        sa.Column("primary_view_mode", sa.String(length=32), nullable=False, server_default="table"),
        schema="app",
    )
    op.add_column(
        "queries",
        sa.Column("answer_envelope_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.create_index("ix_app_queries_answer_type_code", "queries", ["answer_type_code"], unique=False, schema="app")
    op.create_index("ix_app_queries_answer_type_key", "queries", ["answer_type_key"], unique=False, schema="app")

    op.execute(
        """
        UPDATE app.queries
        SET primary_view_mode = CASE
            WHEN chart_type IN ('bar', 'line', 'grouped_bar') THEN 'chart'
            ELSE 'table'
        END
        """
    )

    op.alter_column("queries", "answer_type_code", server_default=None, schema="app")
    op.alter_column("queries", "answer_type_key", server_default=None, schema="app")
    op.alter_column("queries", "primary_view_mode", server_default=None, schema="app")
    op.alter_column("queries", "answer_envelope_json", server_default=None, schema="app")


def downgrade() -> None:
    op.drop_index("ix_app_queries_answer_type_key", table_name="queries", schema="app")
    op.drop_index("ix_app_queries_answer_type_code", table_name="queries", schema="app")
    op.drop_column("queries", "answer_envelope_json", schema="app")
    op.drop_column("queries", "primary_view_mode", schema="app")
    op.drop_column("queries", "answer_type_key", schema="app")
    op.drop_column("queries", "answer_type_code", schema="app")
