"""Introduce governed semantic catalog tables and admin contracts.

Revision ID: 20260423_0005
Revises: 20260423_0004
Create Date: 2026-04-23 23:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0005"
down_revision: Union[str, Sequence[str], None] = "20260423_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "metric_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_key", sa.String(length=128), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sql_expression_template", sa.Text(), nullable=False),
        sa.Column("grain", sa.String(length=64), nullable=False),
        sa.Column(
            "allowed_dimensions_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "allowed_filters_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("default_chart", sa.String(length=32), nullable=False, server_default="table_only"),
        sa.Column(
            "safety_tags_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["app.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index("ix_app_metric_catalog_metric_key", "metric_catalog", ["metric_key"], unique=True, schema="app")
    op.create_index("ix_app_metric_catalog_grain", "metric_catalog", ["grain"], unique=False, schema="app")

    op.create_table(
        "dimension_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension_key", sa.String(length=128), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False),
        sa.Column("join_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("data_type", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["app.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_app_dimension_catalog_dimension_key",
        "dimension_catalog",
        ["dimension_key"],
        unique=True,
        schema="app",
    )
    op.create_index("ix_app_dimension_catalog_table_name", "dimension_catalog", ["table_name"], schema="app")

    op.create_table(
        "semantic_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term", sa.String(length=128), nullable=False),
        sa.Column(
            "aliases",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("mapped_entity_type", sa.String(length=32), nullable=False),
        sa.Column("mapped_entity_key", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["app.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index("ix_app_semantic_terms_term", "semantic_terms", ["term"], unique=True, schema="app")
    op.create_index(
        "ix_app_semantic_terms_entity",
        "semantic_terms",
        ["mapped_entity_type", "mapped_entity_key"],
        unique=False,
        schema="app",
    )

    op.create_table(
        "approved_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("natural_text", sa.Text(), nullable=False),
        sa.Column("metric_key", sa.String(length=128), nullable=False),
        sa.Column(
            "dimension_keys_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "filter_keys_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "canonical_intent_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("chart_type", sa.String(length=32), nullable=False, server_default="table_only"),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="general"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["app.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index(
        "ix_app_approved_templates_template_key",
        "approved_templates",
        ["template_key"],
        unique=True,
        schema="app",
    )
    op.create_index(
        "ix_app_approved_templates_metric_key",
        "approved_templates",
        ["metric_key"],
        unique=False,
        schema="app",
    )

    op.add_column("semantic_examples", sa.Column("metric_key", sa.String(length=128), nullable=True), schema="app")
    op.add_column(
        "semantic_examples",
        sa.Column(
            "dimension_keys_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="app",
    )
    op.add_column(
        "semantic_examples",
        sa.Column(
            "filter_keys_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="app",
    )
    op.add_column(
        "semantic_examples",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema="app",
    )
    op.add_column(
        "semantic_examples",
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        schema="app",
    )
    op.create_index(
        "ix_app_semantic_examples_metric_key",
        "semantic_examples",
        ["metric_key"],
        unique=False,
        schema="app",
    )
    op.create_foreign_key(
        "fk_app_semantic_examples_updated_by",
        "semantic_examples",
        "users",
        ["updated_by"],
        ["id"],
        source_schema="app",
        referent_schema="app",
    )

    _backfill_catalogs()


def downgrade() -> None:
    op.drop_constraint("fk_app_semantic_examples_updated_by", "semantic_examples", schema="app", type_="foreignkey")
    op.drop_index("ix_app_semantic_examples_metric_key", table_name="semantic_examples", schema="app")
    op.drop_column("semantic_examples", "updated_by", schema="app")
    op.drop_column("semantic_examples", "is_active", schema="app")
    op.drop_column("semantic_examples", "filter_keys_json", schema="app")
    op.drop_column("semantic_examples", "dimension_keys_json", schema="app")
    op.drop_column("semantic_examples", "metric_key", schema="app")

    op.drop_index("ix_app_approved_templates_metric_key", table_name="approved_templates", schema="app")
    op.drop_index("ix_app_approved_templates_template_key", table_name="approved_templates", schema="app")
    op.drop_table("approved_templates", schema="app")

    op.drop_index("ix_app_semantic_terms_entity", table_name="semantic_terms", schema="app")
    op.drop_index("ix_app_semantic_terms_term", table_name="semantic_terms", schema="app")
    op.drop_table("semantic_terms", schema="app")

    op.drop_index("ix_app_dimension_catalog_table_name", table_name="dimension_catalog", schema="app")
    op.drop_index("ix_app_dimension_catalog_dimension_key", table_name="dimension_catalog", schema="app")
    op.drop_table("dimension_catalog", schema="app")

    op.drop_index("ix_app_metric_catalog_grain", table_name="metric_catalog", schema="app")
    op.drop_index("ix_app_metric_catalog_metric_key", table_name="metric_catalog", schema="app")
    op.drop_table("metric_catalog", schema="app")


def _uuid_sql(seed: str) -> str:
    return f"""(
        substr(md5({seed}), 1, 8)
        || '-'
        || substr(md5({seed}), 9, 4)
        || '-'
        || substr(md5({seed}), 13, 4)
        || '-'
        || substr(md5({seed}), 17, 4)
        || '-'
        || substr(md5({seed}), 21, 12)
    )::uuid"""


def _backfill_catalogs() -> None:
    op.execute(
        f"""
        INSERT INTO app.metric_catalog (
            id,
            metric_key,
            business_name,
            description,
            sql_expression_template,
            grain,
            allowed_dimensions_json,
            allowed_filters_json,
            default_chart,
            safety_tags_json,
            is_active,
            updated_by,
            created_at,
            updated_at
        )
        SELECT
            {_uuid_sql("'metric:' || sl.semantic_key")},
            sl.semantic_key,
            sl.term,
            COALESCE(sl.description, ''),
            COALESCE(
                replace(
                    replace(
                        sl.semantic_config_json -> 'expression_by_base' ->> (sl.semantic_config_json ->> 'base_table'),
                        'fo.',
                        '{{base_alias}}.'
                    ),
                    'ft.',
                    '{{base_alias}}.'
                ),
                replace(
                    replace(sl.sql_expression, 'fact.orders.', '{{base_alias}}.'),
                    'fact.tenders.',
                    '{{base_alias}}.'
                )
            ),
            CASE
                WHEN COALESCE(sl.semantic_config_json ->> 'base_table', sl.table_name) LIKE 'fact.tenders%' THEN 'tender'
                ELSE 'order'
            END,
            COALESCE(sl.semantic_config_json -> 'supported_dimensions', '[]'::jsonb),
            COALESCE(sl.semantic_config_json -> 'supported_dimensions', '[]'::jsonb),
            COALESCE(sl.semantic_config_json ->> 'default_chart_type', 'table_only'),
            CASE
                WHEN COALESCE(sl.metric_type, '') = '' THEN '[]'::jsonb
                ELSE jsonb_build_array(sl.metric_type)
            END,
            TRUE,
            sl.updated_by,
            COALESCE(sl.updated_at, CURRENT_TIMESTAMP),
            COALESCE(sl.updated_at, CURRENT_TIMESTAMP)
        FROM app.semantic_layer sl
        WHERE COALESCE(sl.item_kind, 'metric') = 'metric'
          AND NOT EXISTS (
              SELECT 1
              FROM app.metric_catalog existing
              WHERE existing.metric_key = sl.semantic_key
          )
        """
    )

    op.execute(
        f"""
        INSERT INTO app.dimension_catalog (
            id,
            dimension_key,
            business_name,
            table_name,
            column_name,
            join_path,
            data_type,
            is_active,
            updated_by,
            created_at,
            updated_at
        )
        SELECT
            {_uuid_sql("'dimension:' || sl.semantic_key")},
            sl.semantic_key,
            sl.term,
            CASE
                WHEN sl.semantic_key = 'day' THEN '__grain__'
                ELSE COALESCE(sl.table_name, '__grain__')
            END,
            CASE
                WHEN sl.semantic_key = 'city' THEN 'city_name'
                WHEN sl.semantic_key = 'day' THEN '{{time_dimension_column}}'
                ELSE regexp_replace(COALESCE(sl.sql_expression, ''), '^.*\\.', '')
            END,
            CASE
                WHEN sl.semantic_key = 'city' THEN 'JOIN dim.cities {{dimension_alias}} ON {{dimension_alias}}.city_id = {{base_alias}}.city_id'
                ELSE ''
            END,
            CASE
                WHEN COALESCE(sl.semantic_config_json ->> 'value_type', '') IN ('date', 'timestamp', 'integer', 'numeric', 'boolean', 'string')
                    THEN sl.semantic_config_json ->> 'value_type'
                WHEN sl.semantic_key = 'day' THEN 'date'
                ELSE 'string'
            END,
            TRUE,
            sl.updated_by,
            COALESCE(sl.updated_at, CURRENT_TIMESTAMP),
            COALESCE(sl.updated_at, CURRENT_TIMESTAMP)
        FROM app.semantic_layer sl
        WHERE COALESCE(sl.item_kind, '') IN ('dimension', 'filter')
          AND NOT EXISTS (
              SELECT 1
              FROM app.dimension_catalog existing
              WHERE existing.dimension_key = sl.semantic_key
          )
        """
    )

    op.execute(
        f"""
        INSERT INTO app.semantic_terms (
            id,
            term,
            aliases,
            mapped_entity_type,
            mapped_entity_key,
            is_active,
            updated_by,
            created_at,
            updated_at
        )
        SELECT
            {_uuid_sql("'term:' || lower(sl.term)")},
            lower(sl.term),
            COALESCE(sl.aliases, '[]'::jsonb),
            CASE
                WHEN COALESCE(sl.item_kind, '') = 'filter' THEN 'filter'
                WHEN COALESCE(sl.item_kind, '') = 'dimension' THEN 'dimension'
                ELSE 'metric'
            END,
            sl.semantic_key,
            TRUE,
            sl.updated_by,
            COALESCE(sl.updated_at, CURRENT_TIMESTAMP),
            COALESCE(sl.updated_at, CURRENT_TIMESTAMP)
        FROM app.semantic_layer sl
        WHERE NOT EXISTS (
            SELECT 1
            FROM app.semantic_terms existing
            WHERE existing.term = lower(sl.term)
        )
        """
    )

    op.execute(
        """
        UPDATE app.semantic_examples
        SET metric_key = COALESCE(
                NULLIF(metric_key, ''),
                canonical_intent_json ->> 'metric_key',
                canonical_intent_json ->> 'metric',
                ''
            ),
            dimension_keys_json = CASE
                WHEN jsonb_typeof(canonical_intent_json -> 'dimension_keys') = 'array' THEN canonical_intent_json -> 'dimension_keys'
                WHEN jsonb_typeof(canonical_intent_json -> 'dimensions') = 'array' THEN canonical_intent_json -> 'dimensions'
                ELSE '[]'::jsonb
            END,
            filter_keys_json = CASE
                WHEN jsonb_typeof(canonical_intent_json -> 'filter_keys') = 'array' THEN canonical_intent_json -> 'filter_keys'
                ELSE '[]'::jsonb
            END,
            is_active = TRUE
        """
    )

    op.execute(
        f"""
        INSERT INTO app.approved_templates (
            id,
            template_key,
            title,
            description,
            natural_text,
            metric_key,
            dimension_keys_json,
            filter_keys_json,
            canonical_intent_json,
            chart_type,
            category,
            is_active,
            approved_by,
            created_at,
            updated_at
        )
        SELECT
            {_uuid_sql("'approved_template:' || t.id::text")},
            'template_' || substr(md5(t.id::text), 1, 12),
            t.title,
            COALESCE(t.description, ''),
            t.natural_text,
            COALESCE(t.canonical_intent_json ->> 'metric_key', t.canonical_intent_json ->> 'metric', ''),
            CASE
                WHEN jsonb_typeof(t.canonical_intent_json -> 'dimension_keys') = 'array' THEN t.canonical_intent_json -> 'dimension_keys'
                WHEN jsonb_typeof(t.canonical_intent_json -> 'dimensions') = 'array' THEN t.canonical_intent_json -> 'dimensions'
                ELSE '[]'::jsonb
            END,
            CASE
                WHEN jsonb_typeof(t.canonical_intent_json -> 'filter_keys') = 'array' THEN t.canonical_intent_json -> 'filter_keys'
                ELSE '[]'::jsonb
            END,
            COALESCE(t.canonical_intent_json, '{{}}'::jsonb),
            COALESCE(t.chart_type, 'table_only'),
            COALESCE(t.category, 'general'),
            TRUE,
            t.created_by,
            COALESCE(t.created_at, CURRENT_TIMESTAMP),
            COALESCE(t.updated_at, CURRENT_TIMESTAMP)
        FROM app.templates t
        WHERE t.is_public = TRUE
          AND NOT EXISTS (
              SELECT 1
              FROM app.approved_templates existing
              WHERE existing.template_key = 'template_' || substr(md5(t.id::text), 1, 12)
          )
        """
    )

    op.alter_column("semantic_examples", "metric_key", schema="app", existing_type=sa.String(length=128), nullable=False)
