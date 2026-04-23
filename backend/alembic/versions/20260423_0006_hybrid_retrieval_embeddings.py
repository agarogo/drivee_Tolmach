"""Add hybrid retrieval indexes and embeddings cache.

Revision ID: 20260423_0006
Revises: 20260423_0005
Create Date: 2026-04-24 01:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0006"
down_revision: Union[str, Sequence[str], None] = "20260423_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        DO $$
        BEGIN
            BEGIN
                CREATE EXTENSION IF NOT EXISTS vector;
            EXCEPTION
                WHEN OTHERS THEN
                    IF SQLSTATE IN ('58P01', '0A000') THEN
                        RAISE NOTICE 'pgvector extension is not installed; lexical retrieval remains available.';
                    ELSE
                        RAISE;
                    END IF;
            END;
        END
        $$;
        """
    )

    op.create_table(
        "embeddings_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_key", sa.String(length=255), nullable=False),
        sa.Column("source_table", sa.String(length=128), nullable=False),
        sa.Column("source_title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_provider", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("vector_dims", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "embedding_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "last_embedded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_key",
            "embedding_provider",
            "embedding_model",
            name="uq_app_embeddings_cache_entity_provider_model",
        ),
        schema="app",
    )
    op.create_index(
        "ix_app_embeddings_cache_entity_lookup",
        "embeddings_cache",
        ["entity_type", "entity_key"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_app_embeddings_cache_model_lookup",
        "embeddings_cache",
        ["embedding_provider", "embedding_model", "vector_dims"],
        unique=False,
        schema="app",
    )
    op.create_index(
        "ix_app_embeddings_cache_active_hash",
        "embeddings_cache",
        ["content_hash"],
        unique=False,
        schema="app",
        postgresql_where=sa.text("is_active = TRUE"),
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                EXECUTE 'ALTER TABLE app.embeddings_cache ADD COLUMN IF NOT EXISTS embedding vector';
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_semantic_terms_document_trgm
        ON app.semantic_terms
        USING gin (
            lower(
                COALESCE(term, '')
                || ' ' || COALESCE(mapped_entity_type, '')
                || ' ' || COALESCE(mapped_entity_key, '')
                || ' ' || COALESCE(aliases::text, '')
            ) gin_trgm_ops
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_approved_templates_document_trgm
        ON app.approved_templates
        USING gin (
            lower(
                COALESCE(template_key, '')
                || ' ' || COALESCE(title, '')
                || ' ' || COALESCE(description, '')
                || ' ' || COALESCE(natural_text, '')
                || ' ' || COALESCE(metric_key, '')
                || ' ' || COALESCE(category, '')
                || ' ' || COALESCE(dimension_keys_json::text, '')
                || ' ' || COALESCE(filter_keys_json::text, '')
            ) gin_trgm_ops
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_app_semantic_examples_document_trgm
        ON app.semantic_examples
        USING gin (
            lower(
                COALESCE(title, '')
                || ' ' || COALESCE(natural_text, '')
                || ' ' || COALESCE(metric_key, '')
                || ' ' || COALESCE(domain_tag, '')
                || ' ' || COALESCE(dimension_keys_json::text, '')
                || ' ' || COALESCE(filter_keys_json::text, '')
            ) gin_trgm_ops
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS app.ix_app_semantic_examples_document_trgm")
    op.execute("DROP INDEX IF EXISTS app.ix_app_approved_templates_document_trgm")
    op.execute("DROP INDEX IF EXISTS app.ix_app_semantic_terms_document_trgm")

    op.drop_index("ix_app_embeddings_cache_active_hash", table_name="embeddings_cache", schema="app")
    op.drop_index("ix_app_embeddings_cache_model_lookup", table_name="embeddings_cache", schema="app")
    op.drop_index("ix_app_embeddings_cache_entity_lookup", table_name="embeddings_cache", schema="app")
    op.drop_table("embeddings_cache", schema="app")
