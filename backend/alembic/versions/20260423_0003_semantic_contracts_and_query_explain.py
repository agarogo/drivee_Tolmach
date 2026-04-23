"""Add semantic contracts and SQL explainability fields.

Revision ID: 20260423_0003
Revises: 20260423_0002
Create Date: 2026-04-23 18:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0003"
down_revision: Union[str, Sequence[str], None] = "20260423_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.add_column(
        "semantic_layer",
        sa.Column("semantic_key", sa.String(length=128), nullable=False, server_default=""),
        schema="tolmach",
    )
    op.add_column(
        "semantic_layer",
        sa.Column("item_kind", sa.String(length=32), nullable=False, server_default="legacy"),
        schema="tolmach",
    )
    op.add_column(
        "semantic_layer",
        sa.Column(
            "semantic_config_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="tolmach",
    )
    op.execute(
        """
        UPDATE tolmach.semantic_layer
        SET semantic_key = CASE term
            WHEN 'выручка' THEN 'revenue'
            WHEN 'заказы' THEN 'orders_count'
            WHEN 'завершённые поездки' THEN 'completed_trips'
            WHEN 'отмены клиентом' THEN 'client_cancellations'
            WHEN 'отмены водителем' THEN 'driver_cancellations'
            WHEN 'decline тендеров' THEN 'tender_decline_rate'
            WHEN 'средний чек' THEN 'avg_check'
            WHEN 'город' THEN 'city'
            WHEN 'день' THEN 'day'
            WHEN 'водители' THEN 'active_drivers'
            ELSE term
        END
        """
    )
    op.execute(
        """
        UPDATE tolmach.semantic_layer
        SET item_kind = CASE
            WHEN COALESCE(dimension_type, '') <> '' THEN 'dimension'
            ELSE 'metric'
        END
        """
    )
    op.alter_column("semantic_layer", "semantic_key", server_default=None, schema="tolmach")
    op.alter_column("semantic_layer", "item_kind", server_default=None, schema="tolmach")
    op.alter_column("semantic_layer", "semantic_config_json", server_default=None, schema="tolmach")
    op.create_index("ix_semantic_layer_semantic_key", "semantic_layer", ["semantic_key"], unique=True, schema="tolmach")
    op.create_index("ix_semantic_layer_item_kind", "semantic_layer", ["item_kind"], schema="tolmach")

    op.add_column(
        "queries",
        sa.Column(
            "resolved_request_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="tolmach",
    )
    op.add_column(
        "queries",
        sa.Column(
            "sql_explain_plan_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="tolmach",
    )
    op.add_column(
        "queries",
        sa.Column("sql_explain_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        schema="tolmach",
    )
    op.alter_column("queries", "resolved_request_json", server_default=None, schema="tolmach")
    op.alter_column("queries", "sql_explain_plan_json", server_default=None, schema="tolmach")
    op.alter_column("queries", "sql_explain_cost", server_default=None, schema="tolmach")


def downgrade() -> None:
    op.drop_column("queries", "sql_explain_cost", schema="tolmach")
    op.drop_column("queries", "sql_explain_plan_json", schema="tolmach")
    op.drop_column("queries", "resolved_request_json", schema="tolmach")

    op.drop_index("ix_semantic_layer_item_kind", table_name="semantic_layer", schema="tolmach")
    op.drop_index("ix_semantic_layer_semantic_key", table_name="semantic_layer", schema="tolmach")
    op.drop_column("semantic_layer", "semantic_config_json", schema="tolmach")
    op.drop_column("semantic_layer", "item_kind", schema="tolmach")
    op.drop_column("semantic_layer", "semantic_key", schema="tolmach")
