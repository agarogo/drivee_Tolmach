from __future__ import annotations

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retrieval_sources import RetrievalSource


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


async def extension_enabled(db: AsyncSession, extension_name: str) -> bool:
    result = await db.scalar(
        text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = :extension_name)"),
        {"extension_name": extension_name},
    )
    return bool(result)


async def pgvector_enabled(db: AsyncSession) -> bool:
    return await extension_enabled(db, "vector")


async def upsert_embedding_cache(
    db: AsyncSession,
    *,
    source: RetrievalSource,
    provider_name: str,
    model_name: str,
    vector: list[float],
    use_pgvector: bool,
) -> None:
    params: dict[str, Any] = {
        "id": str(uuid5(NAMESPACE_URL, f"{source.entity_type}:{source.entity_key}:{provider_name}:{model_name}")),
        "entity_type": source.entity_type,
        "entity_key": source.entity_key,
        "source_table": source.source_table,
        "source_title": source.title,
        "source_text": source.search_text,
        "content_hash": source.content_hash,
        "embedding_provider": provider_name,
        "embedding_model": model_name,
        "vector_dims": len(vector),
        "embedding_json": json.dumps(vector),
    }
    if use_pgvector:
        params["embedding_literal"] = vector_literal(vector)
        await db.execute(
            text(
                """
                INSERT INTO app.embeddings_cache (
                    id,
                    entity_type,
                    entity_key,
                    source_table,
                    source_title,
                    source_text,
                    content_hash,
                    embedding_provider,
                    embedding_model,
                    vector_dims,
                    embedding_json,
                    embedding,
                    is_active,
                    last_error,
                    last_embedded_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :entity_type,
                    :entity_key,
                    :source_table,
                    :source_title,
                    :source_text,
                    :content_hash,
                    :embedding_provider,
                    :embedding_model,
                    :vector_dims,
                    CAST(:embedding_json AS jsonb),
                    CAST(:embedding_literal AS vector),
                    TRUE,
                    '',
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (entity_type, entity_key, embedding_provider, embedding_model)
                DO UPDATE SET
                    source_table = EXCLUDED.source_table,
                    source_title = EXCLUDED.source_title,
                    source_text = EXCLUDED.source_text,
                    content_hash = EXCLUDED.content_hash,
                    vector_dims = EXCLUDED.vector_dims,
                    embedding_json = EXCLUDED.embedding_json,
                    embedding = EXCLUDED.embedding,
                    is_active = TRUE,
                    last_error = '',
                    last_embedded_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            params,
        )
        return

    await db.execute(
        text(
            """
            INSERT INTO app.embeddings_cache (
                id,
                entity_type,
                entity_key,
                source_table,
                source_title,
                source_text,
                content_hash,
                embedding_provider,
                embedding_model,
                vector_dims,
                embedding_json,
                is_active,
                last_error,
                last_embedded_at,
                created_at,
                updated_at
            )
            VALUES (
                :id,
                :entity_type,
                :entity_key,
                :source_table,
                :source_title,
                :source_text,
                :content_hash,
                :embedding_provider,
                :embedding_model,
                :vector_dims,
                CAST(:embedding_json AS jsonb),
                TRUE,
                '',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (entity_type, entity_key, embedding_provider, embedding_model)
            DO UPDATE SET
                source_table = EXCLUDED.source_table,
                source_title = EXCLUDED.source_title,
                source_text = EXCLUDED.source_text,
                content_hash = EXCLUDED.content_hash,
                vector_dims = EXCLUDED.vector_dims,
                embedding_json = EXCLUDED.embedding_json,
                is_active = TRUE,
                last_error = '',
                last_embedded_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        params,
    )
