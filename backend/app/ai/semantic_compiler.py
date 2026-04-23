from __future__ import annotations

from app.ai.types import Interpretation, RetrievalResult, SqlPlan
from app.semantic.compiler import CompiledSemanticQuery, compile_sql_query_artifact
from app.semantic.service import SemanticCatalog, SemanticCompilationError, compile_interpretation_to_sql


def compile_sql_query(
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> tuple[SqlPlan, str]:
    return compile_interpretation_to_sql(interpretation, retrieval, catalog)


def compile_sql_query_bundle(
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> CompiledSemanticQuery:
    return compile_sql_query_artifact(interpretation, retrieval, catalog)


__all__ = ["CompiledSemanticQuery", "SemanticCompilationError", "compile_sql_query", "compile_sql_query_bundle"]
