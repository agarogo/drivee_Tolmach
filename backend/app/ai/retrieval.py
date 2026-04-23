from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingProviderError, create_embedding_provider
from app.ai.retrieval_cache import pgvector_enabled, vector_literal
from app.ai.types import Interpretation, RetrievalResult
from app.config import get_settings
from app.services.observability import trace_span

settings = get_settings()

TERM_LEXICAL_SQL = text(
    """
    SELECT
        st.term,
        st.aliases,
        st.mapped_entity_type,
        st.mapped_entity_key,
        GREATEST(
            similarity(lower(st.term), :question_lower),
            word_similarity(:question_lower, lower(st.term)),
            similarity(lower(st.mapped_entity_key), :question_lower),
            word_similarity(:question_lower, lower(st.mapped_entity_key)),
            similarity(lower(COALESCE(st.aliases::text, '')), :question_lower),
            word_similarity(:question_lower, lower(COALESCE(st.aliases::text, ''))),
            similarity(
                lower(
                    COALESCE(st.term, '')
                    || ' ' || COALESCE(st.mapped_entity_type, '')
                    || ' ' || COALESCE(st.mapped_entity_key, '')
                    || ' ' || COALESCE(st.aliases::text, '')
                ),
                :question_lower
            ),
            word_similarity(
                :question_lower,
                lower(
                    COALESCE(st.term, '')
                    || ' ' || COALESCE(st.mapped_entity_type, '')
                    || ' ' || COALESCE(st.mapped_entity_key, '')
                    || ' ' || COALESCE(st.aliases::text, '')
                )
            )
        ) AS lexical_score
    FROM app.semantic_terms st
    WHERE st.is_active = TRUE
    ORDER BY lexical_score DESC, st.term ASC
    LIMIT :candidate_limit
    """
)

TERM_VECTOR_SQL = text(
    """
    SELECT
        st.term,
        st.aliases,
        st.mapped_entity_type,
        st.mapped_entity_key,
        GREATEST(0::double precision, 1 - (ec.embedding <=> CAST(:query_vector AS vector))) AS vector_score
    FROM app.embeddings_cache ec
    JOIN app.semantic_terms st
      ON st.term = ec.entity_key
    WHERE ec.is_active = TRUE
      AND st.is_active = TRUE
      AND ec.entity_type = 'semantic_term'
      AND ec.embedding_model = :embedding_model
      AND ec.vector_dims = :vector_dims
      AND ec.embedding IS NOT NULL
    ORDER BY ec.embedding <=> CAST(:query_vector AS vector), st.term ASC
    LIMIT :candidate_limit
    """
)

TEMPLATE_LEXICAL_SQL = text(
    """
    SELECT
        at.template_key,
        at.title,
        at.description,
        at.natural_text,
        at.metric_key,
        at.dimension_keys_json,
        at.filter_keys_json,
        at.chart_type,
        at.category,
        GREATEST(
            similarity(
                lower(
                    COALESCE(at.template_key, '')
                    || ' ' || COALESCE(at.title, '')
                    || ' ' || COALESCE(at.description, '')
                    || ' ' || COALESCE(at.natural_text, '')
                    || ' ' || COALESCE(at.metric_key, '')
                    || ' ' || COALESCE(at.category, '')
                    || ' ' || COALESCE(at.dimension_keys_json::text, '')
                    || ' ' || COALESCE(at.filter_keys_json::text, '')
                ),
                :question_lower
            ),
            word_similarity(
                :question_lower,
                lower(
                    COALESCE(at.template_key, '')
                    || ' ' || COALESCE(at.title, '')
                    || ' ' || COALESCE(at.description, '')
                    || ' ' || COALESCE(at.natural_text, '')
                    || ' ' || COALESCE(at.metric_key, '')
                    || ' ' || COALESCE(at.category, '')
                    || ' ' || COALESCE(at.dimension_keys_json::text, '')
                    || ' ' || COALESCE(at.filter_keys_json::text, '')
                )
            ),
            similarity(lower(at.title), :question_lower),
            similarity(lower(at.natural_text), :question_lower)
        ) AS lexical_score
    FROM app.approved_templates at
    WHERE at.is_active = TRUE
    ORDER BY lexical_score DESC, at.title ASC
    LIMIT :candidate_limit
    """
)

TEMPLATE_VECTOR_SQL = text(
    """
    SELECT
        at.template_key,
        at.title,
        at.description,
        at.natural_text,
        at.metric_key,
        at.dimension_keys_json,
        at.filter_keys_json,
        at.chart_type,
        at.category,
        GREATEST(0::double precision, 1 - (ec.embedding <=> CAST(:query_vector AS vector))) AS vector_score
    FROM app.embeddings_cache ec
    JOIN app.approved_templates at
      ON at.template_key = ec.entity_key
    WHERE ec.is_active = TRUE
      AND at.is_active = TRUE
      AND ec.entity_type = 'approved_template'
      AND ec.embedding_model = :embedding_model
      AND ec.vector_dims = :vector_dims
      AND ec.embedding IS NOT NULL
    ORDER BY ec.embedding <=> CAST(:query_vector AS vector), at.title ASC
    LIMIT :candidate_limit
    """
)

EXAMPLE_LEXICAL_SQL = text(
    """
    SELECT
        se.id::text AS example_id,
        se.title,
        se.natural_text,
        se.metric_key,
        se.dimension_keys_json,
        se.filter_keys_json,
        se.sql_example,
        se.domain_tag,
        GREATEST(
            similarity(
                lower(
                    COALESCE(se.title, '')
                    || ' ' || COALESCE(se.natural_text, '')
                    || ' ' || COALESCE(se.metric_key, '')
                    || ' ' || COALESCE(se.domain_tag, '')
                    || ' ' || COALESCE(se.dimension_keys_json::text, '')
                    || ' ' || COALESCE(se.filter_keys_json::text, '')
                ),
                :question_lower
            ),
            word_similarity(
                :question_lower,
                lower(
                    COALESCE(se.title, '')
                    || ' ' || COALESCE(se.natural_text, '')
                    || ' ' || COALESCE(se.metric_key, '')
                    || ' ' || COALESCE(se.domain_tag, '')
                    || ' ' || COALESCE(se.dimension_keys_json::text, '')
                    || ' ' || COALESCE(se.filter_keys_json::text, '')
                )
            ),
            similarity(lower(se.title), :question_lower),
            similarity(lower(se.natural_text), :question_lower)
        ) AS lexical_score
    FROM app.semantic_examples se
    WHERE se.is_active = TRUE
    ORDER BY lexical_score DESC, se.title ASC
    LIMIT :candidate_limit
    """
)

EXAMPLE_VECTOR_SQL = text(
    """
    SELECT
        se.id::text AS example_id,
        se.title,
        se.natural_text,
        se.metric_key,
        se.dimension_keys_json,
        se.filter_keys_json,
        se.sql_example,
        se.domain_tag,
        GREATEST(0::double precision, 1 - (ec.embedding <=> CAST(:query_vector AS vector))) AS vector_score
    FROM app.embeddings_cache ec
    JOIN app.semantic_examples se
      ON se.id::text = ec.entity_key
    WHERE ec.is_active = TRUE
      AND se.is_active = TRUE
      AND ec.entity_type = 'semantic_example'
      AND ec.embedding_model = :embedding_model
      AND ec.vector_dims = :vector_dims
      AND ec.embedding IS NOT NULL
    ORDER BY ec.embedding <=> CAST(:query_vector AS vector), se.title ASC
    LIMIT :candidate_limit
    """
)


@dataclass
class RetrievalCandidate:
    entity_type: str
    entity_key: str
    title: str
    search_text: str
    payload: dict[str, Any]
    lexical_score: float = 0.0
    vector_score: float = 0.0
    rerank_bonus: float = 0.0
    final_score: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.payload,
            "entity_type": self.entity_type,
            "entity_key": self.entity_key,
            "title": self.title,
            "lexical_score": round(self.lexical_score, 4),
            "vector_score": round(self.vector_score, 4),
            "rerank_bonus": round(self.rerank_bonus, 4),
            "score": round(self.final_score, 4),
            "matched_terms": self.matched_terms,
            "why_selected": self.reasons,
        }


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"\W+", text.lower()) if len(token) > 1}


def _normalize_score(value: float) -> float:
    return max(0.0, min(float(value or 0.0), 1.0))


def _unique_items(items: list[str], *, limit: int = 6) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _fuzzy_phrase_matches(question_lower: str, question_tokens: set[str], phrases: list[str]) -> list[str]:
    matches: list[str] = []
    for phrase in phrases:
        normalized = phrase.strip().lower()
        if not normalized:
            continue
        if normalized in question_lower:
            matches.append(phrase)
            continue
        phrase_tokens = _tokens(normalized)
        for phrase_token in phrase_tokens:
            if len(phrase_token) < 4:
                continue
            stem = phrase_token[: max(4, len(phrase_token) - 2)]
            if any(len(question_token) >= 4 and question_token.startswith(stem) for question_token in question_tokens):
                matches.append(phrase)
                break
    return _unique_items(matches, limit=4)


def _term_search_text(term: str, mapped_entity_type: str, mapped_entity_key: str, aliases: list[str]) -> str:
    return " ".join(part for part in [term, mapped_entity_type, mapped_entity_key, " ".join(aliases)] if part).strip()


def _template_search_text(
    template_key: str,
    title: str,
    description: str,
    natural_text: str,
    metric_key: str,
    category: str,
    dimension_keys: list[str],
    filter_keys: list[str],
) -> str:
    return " ".join(
        part
        for part in [
            template_key,
            title,
            description,
            natural_text,
            metric_key,
            category,
            " ".join(dimension_keys),
            " ".join(filter_keys),
        ]
        if part
    ).strip()


def _example_search_text(
    title: str,
    natural_text: str,
    metric_key: str,
    domain_tag: str,
    dimension_keys: list[str],
    filter_keys: list[str],
) -> str:
    return " ".join(
        part
        for part in [
            title,
            natural_text,
            metric_key,
            domain_tag,
            " ".join(dimension_keys),
            " ".join(filter_keys),
        ]
        if part
    ).strip()


def _candidate_threshold(entity_type: str) -> float:
    if entity_type == "semantic_term":
        return settings.retrieval_term_threshold
    if entity_type == "approved_template":
        return settings.retrieval_template_threshold
    return settings.retrieval_example_threshold


def _candidate_type_bonus(candidate: RetrievalCandidate, interpretation: Interpretation | None) -> tuple[float, list[str]]:
    reasons: list[str] = []
    bonus = 0.0
    metric = interpretation.metric if interpretation else None
    dimensions = set(interpretation.dimensions) if interpretation else set()
    if candidate.entity_type == "semantic_term":
        mapped_key = str(candidate.payload.get("mapped_entity_key", ""))
        mapped_type = str(candidate.payload.get("mapped_entity_type", ""))
        if metric and mapped_key == metric:
            bonus += 0.35
            reasons.append(f"Mapped entity matches the resolved metric `{metric}`.")
        if mapped_type in {"dimension", "filter"} and mapped_key in dimensions:
            bonus += 0.22
            reasons.append(f"Mapped entity matches the resolved dimension `{mapped_key}`.")
    else:
        metric_key = str(candidate.payload.get("metric_key", ""))
        dimension_keys = set(candidate.payload.get("dimension_keys") or [])
        filter_keys = set(candidate.payload.get("filter_keys") or [])
        if metric and metric_key == metric:
            bonus += 0.3
            reasons.append(f"Candidate metric matches the resolved metric `{metric}`.")
        if dimensions & dimension_keys:
            bonus += 0.16
            reasons.append(f"Candidate dimensions overlap with `{', '.join(sorted(dimensions & dimension_keys))}`.")
        if dimensions & filter_keys:
            bonus += 0.1
            reasons.append(f"Candidate filters overlap with `{', '.join(sorted(dimensions & filter_keys))}`.")
    return bonus, reasons


def _rerank_candidate(
    candidate: RetrievalCandidate,
    *,
    question: str,
    question_tokens: set[str],
    interpretation: Interpretation | None,
    use_vector: bool,
) -> RetrievalCandidate:
    question_lower = question.lower()
    candidate_tokens = _tokens(candidate.search_text)
    matched_tokens = sorted(question_tokens & candidate_tokens)
    bonus = 0.0
    reasons: list[str] = []
    matched_terms: list[str] = []

    if candidate.entity_type == "semantic_term":
        term = str(candidate.payload.get("term", ""))
        aliases = [str(item) for item in candidate.payload.get("aliases", [])]
        term_matches = _fuzzy_phrase_matches(question_lower, question_tokens, [term])
        if term_matches:
            bonus += 0.28
            matched_terms.extend(term_matches)
            reasons.append(f"Semantic term match: `{', '.join(term_matches)}`.")
        alias_matches = _fuzzy_phrase_matches(question_lower, question_tokens, aliases)
        if alias_matches:
            bonus += min(0.22, 0.11 * len(alias_matches))
            matched_terms.extend(alias_matches)
            reasons.append(f"Alias match: `{', '.join(alias_matches[:3])}`.")
    else:
        title = candidate.title
        if title and title.lower() in question_lower:
            bonus += 0.18
            matched_terms.append(title)
            reasons.append(f"Exact title match: `{title}`.")

    if matched_tokens:
        bonus += min(0.18, 0.04 * len(matched_tokens))
        matched_terms.extend(matched_tokens)
        reasons.append(f"Token overlap: `{', '.join(matched_tokens[:6])}`.")

    type_bonus, type_reasons = _candidate_type_bonus(candidate, interpretation)
    bonus += type_bonus
    reasons.extend(type_reasons)

    lexical_score = _normalize_score(candidate.lexical_score)
    vector_score = _normalize_score(candidate.vector_score)
    rerank_bonus = min(1.0, bonus)
    if use_vector and vector_score > 0:
        final_score = _normalize_score((0.55 * lexical_score) + (0.3 * vector_score) + (0.15 * rerank_bonus))
        reasons.append(f"Hybrid score used vector similarity {vector_score:.3f}.")
    else:
        final_score = _normalize_score((0.82 * lexical_score) + (0.18 * rerank_bonus))
    if lexical_score > 0:
        reasons.append(f"Lexical pg_trgm score = {lexical_score:.3f}.")

    candidate.rerank_bonus = rerank_bonus
    candidate.final_score = final_score
    candidate.matched_terms = _unique_items(matched_terms)
    candidate.reasons = _unique_items(reasons, limit=8)
    return candidate


def _merge_candidates(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    merged: dict[tuple[str, str], RetrievalCandidate] = {}
    for item in candidates:
        key = (item.entity_type, item.entity_key)
        current = merged.get(key)
        if current is None:
            merged[key] = item
            continue
        current.lexical_score = max(current.lexical_score, item.lexical_score)
        current.vector_score = max(current.vector_score, item.vector_score)
    return list(merged.values())


def _keep_candidates(candidates: list[RetrievalCandidate]) -> list[RetrievalCandidate]:
    kept: list[RetrievalCandidate] = []
    for item in candidates:
        threshold = _candidate_threshold(item.entity_type)
        if max(item.final_score, item.lexical_score, item.vector_score) >= threshold:
            kept.append(item)
    return kept


def _term_candidate_from_row(mapping: dict[str, Any], *, lexical_score: float = 0.0, vector_score: float = 0.0) -> RetrievalCandidate:
    aliases = [str(item) for item in (mapping.get("aliases") or [])]
    term = str(mapping["term"])
    return RetrievalCandidate(
        entity_type="semantic_term",
        entity_key=term,
        title=term,
        search_text=_term_search_text(
            term,
            str(mapping["mapped_entity_type"]),
            str(mapping["mapped_entity_key"]),
            aliases,
        ),
        payload={
            "term": term,
            "aliases": aliases,
            "mapped_entity_type": str(mapping["mapped_entity_type"]),
            "mapped_entity_key": str(mapping["mapped_entity_key"]),
        },
        lexical_score=lexical_score,
        vector_score=vector_score,
    )


def _template_candidate_from_row(
    mapping: dict[str, Any],
    *,
    lexical_score: float = 0.0,
    vector_score: float = 0.0,
) -> RetrievalCandidate:
    dimension_keys = [str(item) for item in (mapping.get("dimension_keys_json") or [])]
    filter_keys = [str(item) for item in (mapping.get("filter_keys_json") or [])]
    title = str(mapping["title"])
    description = str(mapping.get("description") or "")
    natural_text = str(mapping["natural_text"])
    template_key = str(mapping["template_key"])
    metric_key = str(mapping["metric_key"])
    category = str(mapping["category"])
    return RetrievalCandidate(
        entity_type="approved_template",
        entity_key=template_key,
        title=title,
        search_text=_template_search_text(
            template_key,
            title,
            description,
            natural_text,
            metric_key,
            category,
            dimension_keys,
            filter_keys,
        ),
        payload={
            "template_key": template_key,
            "title": title,
            "description": description,
            "natural_text": natural_text,
            "metric_key": metric_key,
            "dimension_keys": dimension_keys,
            "filter_keys": filter_keys,
            "chart_type": str(mapping["chart_type"]),
            "category": category,
        },
        lexical_score=lexical_score,
        vector_score=vector_score,
    )


def _example_candidate_from_row(
    mapping: dict[str, Any],
    *,
    lexical_score: float = 0.0,
    vector_score: float = 0.0,
) -> RetrievalCandidate:
    dimension_keys = [str(item) for item in (mapping.get("dimension_keys_json") or [])]
    filter_keys = [str(item) for item in (mapping.get("filter_keys_json") or [])]
    title = str(mapping["title"])
    natural_text = str(mapping["natural_text"])
    metric_key = str(mapping["metric_key"])
    domain_tag = str(mapping["domain_tag"])
    example_id = str(mapping["example_id"])
    return RetrievalCandidate(
        entity_type="semantic_example",
        entity_key=example_id,
        title=title,
        search_text=_example_search_text(
            title,
            natural_text,
            metric_key,
            domain_tag,
            dimension_keys,
            filter_keys,
        ),
        payload={
            "id": example_id,
            "title": title,
            "natural_text": natural_text,
            "metric_key": metric_key,
            "dimension_keys": dimension_keys,
            "filter_keys": filter_keys,
            "sql_example": str(mapping["sql_example"]),
            "domain_tag": domain_tag,
        },
        lexical_score=lexical_score,
        vector_score=vector_score,
    )


async def _execute_candidate_query(
    db: AsyncSession,
    sql,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = (await db.execute(sql, params)).mappings().all()
    return [dict(row) for row in rows]


async def _fetch_lexical_candidates(db: AsyncSession, question_lower: str) -> list[RetrievalCandidate]:
    params = {
        "question_lower": question_lower,
        "candidate_limit": settings.retrieval_lexical_candidate_pool,
    }
    term_rows = await _execute_candidate_query(db, TERM_LEXICAL_SQL, params)
    template_rows = await _execute_candidate_query(db, TEMPLATE_LEXICAL_SQL, params)
    example_rows = await _execute_candidate_query(db, EXAMPLE_LEXICAL_SQL, params)
    candidates: list[RetrievalCandidate] = []
    for row in term_rows:
        candidates.append(_term_candidate_from_row(row, lexical_score=float(row.get("lexical_score") or 0.0)))
    for row in template_rows:
        candidates.append(_template_candidate_from_row(row, lexical_score=float(row.get("lexical_score") or 0.0)))
    for row in example_rows:
        candidates.append(_example_candidate_from_row(row, lexical_score=float(row.get("lexical_score") or 0.0)))
    return candidates


async def _fetch_vector_candidates(
    db: AsyncSession,
    *,
    embedding_model: str,
    query_vector: list[float],
) -> list[RetrievalCandidate]:
    params = {
        "query_vector": vector_literal(query_vector),
        "embedding_model": embedding_model,
        "vector_dims": len(query_vector),
        "candidate_limit": settings.retrieval_vector_candidate_pool,
    }
    term_rows = await _execute_candidate_query(db, TERM_VECTOR_SQL, params)
    template_rows = await _execute_candidate_query(db, TEMPLATE_VECTOR_SQL, params)
    example_rows = await _execute_candidate_query(db, EXAMPLE_VECTOR_SQL, params)
    candidates: list[RetrievalCandidate] = []
    for row in term_rows:
        candidates.append(_term_candidate_from_row(row, vector_score=float(row.get("vector_score") or 0.0)))
    for row in template_rows:
        candidates.append(_template_candidate_from_row(row, vector_score=float(row.get("vector_score") or 0.0)))
    for row in example_rows:
        candidates.append(_example_candidate_from_row(row, vector_score=float(row.get("vector_score") or 0.0)))
    return candidates


def _select_top(candidates: list[RetrievalCandidate], *, entity_type: str, limit: int) -> list[dict[str, Any]]:
    typed = [item for item in candidates if item.entity_type == entity_type]
    typed.sort(key=lambda item: (item.final_score, item.vector_score, item.lexical_score, item.title), reverse=True)
    return [item.as_dict() for item in typed[:limit]]


def _planner_candidates(candidates: list[RetrievalCandidate]) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: (item.final_score, item.vector_score, item.lexical_score, item.title),
        reverse=True,
    )
    return [item.as_dict() for item in ranked[: settings.retrieval_planner_top_k]]


async def _query_embedding(question: str) -> tuple[list[float] | None, dict[str, Any]]:
    try:
        provider = create_embedding_provider()
    except EmbeddingProviderError as exc:
        return None, {"available": False, "reason": str(exc)}
    if provider is None:
        return None, {"available": False, "reason": "EMBEDDING_PROVIDER is disabled."}
    try:
        response = await provider.embed_many([question])
    except EmbeddingProviderError as exc:
        return None, {
            "available": False,
            "provider": provider.provider_name,
            "model": provider.model_name,
            "reason": str(exc),
        }
    return response.vectors[0], {
        "available": True,
        "provider": response.provider,
        "model": response.model,
        "duration_ms": response.duration_ms,
        "attempts": response.attempts,
    }


async def retrieve_context(
    db: AsyncSession,
    question: str,
    interpretation: Interpretation | None = None,
) -> RetrievalResult:
    question_lower = question.lower().strip()
    question_tokens = _tokens(question)
    lexical_candidates: list[RetrievalCandidate] = []
    vector_candidates: list[RetrievalCandidate] = []
    embedding_meta: dict[str, Any] = {"available": False, "reason": "Not requested."}
    vector_search_used = False
    vector_extension_enabled = False

    with trace_span("tolmach.retrieval", {"question": question[:160]}):
        lexical_candidates = await _fetch_lexical_candidates(db, question_lower)

        vector_extension_enabled = await pgvector_enabled(db)
        if settings.retrieval_enable_vectors and vector_extension_enabled:
            query_vector, embedding_meta = await _query_embedding(question)
            if query_vector:
                vector_candidates = await _fetch_vector_candidates(
                    db,
                    embedding_model=str(embedding_meta.get("model", "")),
                    query_vector=query_vector,
                )
                vector_search_used = bool(vector_candidates)
        else:
            embedding_meta = {
                "available": False,
                "reason": "pgvector is not enabled or retrieval vectors are disabled.",
            }

    merged = _merge_candidates(lexical_candidates + vector_candidates)
    reranked = [
        _rerank_candidate(
            item,
            question=question_lower,
            question_tokens=question_tokens,
            interpretation=interpretation,
            use_vector=vector_search_used,
        )
        for item in merged
    ]
    kept = _keep_candidates(reranked)

    semantic_terms = _select_top(kept, entity_type="semantic_term", limit=settings.retrieval_top_k_terms)
    templates = _select_top(kept, entity_type="approved_template", limit=settings.retrieval_top_k_templates)
    examples = _select_top(kept, entity_type="semantic_example", limit=settings.retrieval_top_k_examples)

    retrieval_mode = "hybrid_pgvector" if vector_search_used else "lexical_pg_trgm"
    return RetrievalResult(
        semantic_terms=semantic_terms,
        templates=templates,
        examples=examples,
        planner_candidates=_planner_candidates(kept),
        retrieval_mode=retrieval_mode,
        retrieval_explainability={
            "mode": retrieval_mode,
            "question_tokens": sorted(question_tokens),
            "pgvector_enabled": vector_extension_enabled,
            "embedding": embedding_meta,
            "vector_search_used": vector_search_used,
            "score_formula": (
                "hybrid = 0.55 * lexical_pg_trgm + 0.30 * vector_similarity + 0.15 * rerank_bonus"
                if vector_search_used
                else "lexical = 0.82 * lexical_pg_trgm + 0.18 * rerank_bonus"
            ),
            "candidate_pool_sizes": {
                "lexical": len(lexical_candidates),
                "vector": len(vector_candidates),
                "merged": len(merged),
                "selected": len(kept),
            },
            "selected_counts": {
                "semantic_terms": len(semantic_terms),
                "templates": len(templates),
                "examples": len(examples),
                "planner_candidates": min(len(kept), settings.retrieval_planner_top_k),
            },
        },
    )
