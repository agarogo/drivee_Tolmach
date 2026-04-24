import unittest
from unittest.mock import AsyncMock, patch

from app.ai.retrieval import RetrievalCandidate, retrieve_context
from app.ai.types import Interpretation


def semantic_term_candidate(*, lexical: float = 0.7, vector: float = 0.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        entity_type="semantic_term",
        entity_key="выручка",
        title="выручка",
        search_text="выручка revenue metric finance gmv",
        payload={
            "term": "выручка",
            "aliases": ["gmv"],
            "mapped_entity_type": "metric",
            "mapped_entity_key": "revenue",
        },
        lexical_score=lexical,
        vector_score=vector,
    )


def template_candidate(*, lexical: float = 0.4, vector: float = 0.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        entity_type="approved_template",
        entity_key="revenue_by_city",
        title="Revenue by city",
        search_text="revenue by city template выручка город revenue city",
        payload={
            "template_key": "revenue_by_city",
            "title": "Revenue by city",
            "description": "Revenue split by city",
            "natural_text": "Покажи выручку по городам",
            "metric_key": "revenue",
            "dimension_keys": ["city"],
            "filter_keys": ["day"],
            "chart_type": "bar",
            "category": "ops",
        },
        lexical_score=lexical,
        vector_score=vector,
    )


def example_candidate(*, lexical: float = 0.35, vector: float = 0.0) -> RetrievalCandidate:
    return RetrievalCandidate(
        entity_type="semantic_example",
        entity_key="example-1",
        title="Completed trips by day",
        search_text="completed trips by day orders trend example",
        payload={
            "id": "example-1",
            "title": "Completed trips by day",
            "natural_text": "Покажи завершённые поездки по дням",
            "metric_key": "completed_trips",
            "dimension_keys": ["day"],
            "filter_keys": ["city"],
            "sql_example": "SELECT ...",
            "domain_tag": "ops",
        },
        lexical_score=lexical,
        vector_score=vector,
    )


class HybridRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieval_falls_back_to_lexical_mode_without_pgvector(self) -> None:
        interpretation = Interpretation(intent="analytics", metric="revenue", dimensions=["city"])
        with patch(
            "app.ai.retrieval._fetch_lexical_candidates",
            new=AsyncMock(return_value=[semantic_term_candidate(), template_candidate(), example_candidate()]),
        ):
            with patch("app.ai.retrieval.pgvector_enabled", new=AsyncMock(return_value=False)):
                result = await retrieve_context(AsyncMock(), "Покажи выручку по городам", interpretation)

        self.assertEqual(result.retrieval_mode, "lexical_pg_trgm")
        self.assertFalse(result.retrieval_explainability["vector_search_used"])
        self.assertEqual(result.semantic_terms[0]["mapped_entity_key"], "revenue")
        self.assertIn("выручка", [item.lower() for item in result.semantic_terms[0]["matched_terms"]])
        self.assertTrue(result.planner_candidates)

    async def test_hybrid_retrieval_promotes_vector_relevant_template(self) -> None:
        interpretation = Interpretation(intent="analytics", metric="revenue", dimensions=["city"])
        lexical_pool = [
            semantic_term_candidate(lexical=0.18),
            template_candidate(lexical=0.12),
            example_candidate(lexical=0.11),
        ]
        vector_pool = [
            template_candidate(lexical=0.0, vector=0.91),
        ]
        with patch("app.ai.retrieval._fetch_lexical_candidates", new=AsyncMock(return_value=lexical_pool)):
            with patch("app.ai.retrieval.pgvector_enabled", new=AsyncMock(return_value=True)):
                with patch(
                    "app.ai.retrieval._query_embedding",
                    new=AsyncMock(
                        return_value=(
                            [0.1, 0.2, 0.3],
                            {"available": True, "provider": "production", "model": "text-embedding-3-small"},
                        )
                    ),
                ):
                    with patch("app.ai.retrieval._fetch_vector_candidates", new=AsyncMock(return_value=vector_pool)):
                        result = await retrieve_context(AsyncMock(), "Покажи выручку по городам", interpretation)

        self.assertEqual(result.retrieval_mode, "hybrid_pgvector")
        self.assertTrue(result.retrieval_explainability["vector_search_used"])
        self.assertEqual(result.templates[0]["template_key"], "revenue_by_city")
        self.assertGreater(result.templates[0]["vector_score"], 0.8)
        self.assertTrue(
            any("vector similarity" in reason.lower() for reason in result.templates[0]["why_selected"]),
            result.templates[0]["why_selected"],
        )

    async def test_retrieval_keeps_lexical_mode_when_embeddings_fail(self) -> None:
        interpretation = Interpretation(intent="analytics", metric="revenue", dimensions=["city"])
        with patch(
            "app.ai.retrieval._fetch_lexical_candidates",
            new=AsyncMock(return_value=[semantic_term_candidate(lexical=0.5)]),
        ):
            with patch("app.ai.retrieval.pgvector_enabled", new=AsyncMock(return_value=True)):
                with patch(
                    "app.ai.retrieval._query_embedding",
                    new=AsyncMock(return_value=(None, {"available": False, "reason": "provider timeout"})),
                ):
                    result = await retrieve_context(AsyncMock(), "Покажи выручку", interpretation)

        self.assertEqual(result.retrieval_mode, "lexical_pg_trgm")
        self.assertEqual(result.retrieval_explainability["embedding"]["reason"], "provider timeout")
        self.assertFalse(result.retrieval_explainability["vector_search_used"])


if __name__ == "__main__":
    unittest.main()
