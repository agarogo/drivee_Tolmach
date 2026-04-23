from __future__ import annotations

import argparse
import asyncio

from app.ai.embeddings import EmbeddingProviderError, create_embedding_provider
from app.ai.retrieval_cache import pgvector_enabled, upsert_embedding_cache
from app.ai.retrieval_sources import collect_retrieval_sources
from app.db import AsyncSessionLocal


async def _run(batch_size: int, entity_type: str | None) -> None:
    provider = create_embedding_provider()
    if provider is None:
        raise RuntimeError("EMBEDDING_PROVIDER is disabled. Configure embeddings before running backfill.")

    async with AsyncSessionLocal() as db:
        use_pgvector = await pgvector_enabled(db)
        sources = await collect_retrieval_sources(db)
        if entity_type:
            sources = [item for item in sources if item.entity_type == entity_type]
        total = len(sources)
        processed = 0
        for start in range(0, total, batch_size):
            batch = sources[start : start + batch_size]
            try:
                response = await provider.embed_many([item.search_text for item in batch])
            except EmbeddingProviderError as exc:
                raise RuntimeError(f"Embedding backfill failed for batch starting at {start}: {exc}") from exc
            for source, vector in zip(batch, response.vectors):
                await upsert_embedding_cache(
                    db,
                    source=source,
                    provider_name=response.provider,
                    model_name=response.model,
                    vector=vector,
                    use_pgvector=use_pgvector,
                )
            await db.commit()
            processed += len(batch)
            print(
                f"Backfilled {processed}/{total} retrieval embeddings "
                f"(provider={response.provider}, model={response.model}, pgvector={use_pgvector})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill retrieval embeddings for semantic terms and templates.")
    parser.add_argument("--batch-size", type=int, default=16, help="Number of retrieval entities per embedding batch.")
    parser.add_argument(
        "--entity-type",
        choices=["semantic_term", "approved_template", "semantic_example"],
        default=None,
        help="Optional retrieval entity type to backfill.",
    )
    args = parser.parse_args()
    asyncio.run(_run(batch_size=max(1, args.batch_size), entity_type=args.entity_type))


if __name__ == "__main__":
    main()
