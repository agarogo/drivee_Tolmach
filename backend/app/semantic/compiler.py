from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot import expressions as exp

from app.ai.types import Interpretation, RetrievalResult, SqlPlan
from app.semantic.errors import (
    SemanticCompilationError,
    SemanticErrorCode,
    build_block_reason,
)
from app.semantic.planner import QueryPlannerResult, plan_sql_query
from app.semantic.service import SemanticCatalog


def _render_sql(expression: exp.Expression) -> str:
    try:
        return expression.sql(dialect="postgres")
    except TypeError:
        return expression.sql()


def _serialize_ast(expression: exp.Expression) -> dict[str, Any]:
    if hasattr(expression, "dump"):
        dumped = expression.dump()
        if isinstance(dumped, dict):
            return dumped
        return {"dump": dumped}
    return {"sql": _render_sql(expression), "repr": repr(expression)}


def _table_identifier(table: exp.Table) -> str:
    schema = str(table.db or "").strip().lower()
    name = str(table.name or "").strip().lower()
    return f"{schema}.{name}" if schema else name


def _build_compiler_sql(plan: QueryPlannerResult) -> str:
    select_parts = [
        f"{item.select_sql} AS {item.definition.dimension_key}"
        for item in plan.dimensions
    ]
    metric_alias = plan.metric.metric_key
    select_parts.append(f"{plan.metric_expression_sql} AS {metric_alias}")
    group_by = [item.group_by_sql for item in plan.dimensions]
    filter_clauses = [item.clause_sql for item in plan.filters]
    all_where_parts = [*filter_clauses, *plan.period_clauses]

    joins_sql = "\n".join(plan.joins)
    where_sql = f"WHERE {' AND '.join(all_where_parts)}" if all_where_parts else ""
    group_by_sql = f"GROUP BY {', '.join(group_by)}" if group_by else ""
    order_by_sql = f"ORDER BY {plan.order_by_sql}" if plan.order_by_sql else ""

    return f"""
SELECT
  {', '.join(select_parts)}
FROM {plan.grain.source_table} {plan.grain.base_alias}
{joins_sql}
{where_sql}
{group_by_sql}
{order_by_sql}
LIMIT {plan.limit}
""".strip()


@dataclass(frozen=True)
class CompiledSemanticQuery:
    planner_result: QueryPlannerResult
    sql_plan: SqlPlan
    ast: exp.Expression
    rendered_sql: str
    source_tables: set[str]
    column_references: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "planner_result": self.planner_result.as_dict(),
            "sql_plan": self.sql_plan.as_dict(),
            "rendered_sql": self.rendered_sql,
            "source_tables": sorted(self.source_tables),
            "column_references": self.column_references,
        }


def compile_planned_query(plan: QueryPlannerResult) -> CompiledSemanticQuery:
    compiler_sql = _build_compiler_sql(plan)
    try:
        ast = sqlglot.parse_one(compiler_sql, read="postgres")
    except Exception as exc:
        raise SemanticCompilationError(
            build_block_reason(
                SemanticErrorCode.SQL_PARSE_ERROR,
                f"Compiled SQL could not be parsed into AST: {exc}",
                details={"sql": compiler_sql},
            )
        ) from exc

    rendered_sql = _render_sql(ast).strip().rstrip(";")
    source_tables = {_table_identifier(table) for table in ast.find_all(exp.Table)}
    column_references = []
    for column in ast.find_all(exp.Column):
        column_references.append(
            {
                "table_alias": str(column.table or ""),
                "column_name": column.name.lower(),
            }
        )

    dimension_labels = {
        item.definition.dimension_key: item.definition.business_name
        for item in plan.dimensions
    }
    sql_plan = SqlPlan(
        metric=plan.metric.metric_key,
        metric_label=plan.metric.business_name,
        metric_expression=plan.metric_expression_sql,
        source_table=f"{plan.grain.source_table} {plan.grain.base_alias}",
        dimensions=[item.definition.dimension_key for item in plan.dimensions],
        dimension_labels=dimension_labels,
        joins=plan.joins,
        filters=[item.clause_sql for item in plan.filters] + list(plan.period_clauses),
        group_by=[item.group_by_sql for item in plan.dimensions],
        order_by=plan.order_by_sql,
        limit=plan.limit,
        chart_type=plan.chart_type,
        explanation=plan.explanation,
        ast_json=_serialize_ast(ast),
        planner_notes=plan.planner_notes,
        clarification_reasons=[item.as_dict() for item in plan.clarification_reasons],
    )
    return CompiledSemanticQuery(
        planner_result=plan,
        sql_plan=sql_plan,
        ast=ast,
        rendered_sql=rendered_sql,
        source_tables=source_tables,
        column_references=column_references,
    )


def compile_sql_query_artifact(
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> CompiledSemanticQuery:
    planner_result = plan_sql_query(interpretation, retrieval, catalog)
    return compile_planned_query(planner_result)


def compile_interpretation_to_sql(
    interpretation: Interpretation,
    retrieval: RetrievalResult,
    catalog: SemanticCatalog,
) -> tuple[SqlPlan, str]:
    artifact = compile_sql_query_artifact(interpretation, retrieval, catalog)
    return artifact.sql_plan, artifact.rendered_sql
