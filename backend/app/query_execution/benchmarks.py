from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.semantic_compiler import compile_sql_query_bundle
from app.ai.types import Interpretation, RetrievalResult
from app.query_execution.service import QueryExecutionResult, build_explain_sample, execute_safe_query
from app.semantic.service import load_semantic_catalog
from app.services.guardrails import validate_sql


@dataclass(frozen=True)
class BenchmarkPreset:
    key: str
    title: str
    question: str
    interpretation: Interpretation


BENCHMARK_PRESETS: list[BenchmarkPreset] = [
    BenchmarkPreset(
        key="top_10_cities_revenue_30d",
        title="Top-10 cities revenue 30d",
        question="Покажи топ-10 городов по выручке за последние 30 дней",
        interpretation=Interpretation(
            intent="analytics",
            metric="revenue",
            dimensions=["city"],
            date_range={"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            limit=10,
            sorting={"by": "revenue", "direction": "desc"},
            source="benchmark_suite",
            provider_confidence=1.0,
        ),
    ),
    BenchmarkPreset(
        key="daily_kpi_7d",
        title="Daily KPI 7d",
        question="Покажи ежедневный KPI по завершенным поездкам за 7 дней",
        interpretation=Interpretation(
            intent="analytics",
            metric="completed_trips",
            dimensions=["day"],
            date_range={"kind": "rolling_days", "days": 7, "label": "последние 7 дней"},
            limit=20,
            sorting={"by": "day", "direction": "asc"},
            source="benchmark_suite",
            provider_confidence=1.0,
        ),
    ),
    BenchmarkPreset(
        key="cancellations_by_city",
        title="Cancellations by city",
        question="Покажи отмены клиентом по городам за последние 30 дней",
        interpretation=Interpretation(
            intent="analytics",
            metric="client_cancellations",
            dimensions=["city"],
            date_range={"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            limit=20,
            sorting={"by": "client_cancellations", "direction": "desc"},
            source="benchmark_suite",
            provider_confidence=1.0,
        ),
    ),
    BenchmarkPreset(
        key="active_drivers_by_city",
        title="Active drivers by city",
        question="Покажи активных водителей по городам за последние 30 дней",
        interpretation=Interpretation(
            intent="analytics",
            metric="active_drivers",
            dimensions=["city"],
            date_range={"kind": "rolling_days", "days": 30, "label": "последние 30 дней"},
            limit=20,
            sorting={"by": "active_drivers", "direction": "desc"},
            source="benchmark_suite",
            provider_confidence=1.0,
        ),
    ),
    BenchmarkPreset(
        key="tender_decline_rate",
        title="Tender decline rate",
        question="Покажи долю decline тендеров по городам за последние 7 дней",
        interpretation=Interpretation(
            intent="analytics",
            metric="tender_decline_rate",
            dimensions=["city"],
            date_range={"kind": "rolling_days", "days": 7, "label": "последние 7 дней"},
            limit=20,
            sorting={"by": "tender_decline_rate", "direction": "desc"},
            source="benchmark_suite",
            provider_confidence=1.0,
        ),
    ),
]


def _p95(samples: list[int]) -> int:
    if not samples:
        return 0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
    return ordered[index]


async def _run_single_case(
    db: AsyncSession,
    *,
    preset: BenchmarkPreset,
    iterations: int,
    role: str,
) -> dict[str, Any]:
    catalog = await load_semantic_catalog(db)
    retrieval = RetrievalResult([], [], [], planner_candidates=[])
    compiled = compile_sql_query_bundle(preset.interpretation, retrieval, catalog)
    validation = await validate_sql(db, compiled.rendered_sql, role=role)
    if not validation.ok or validation.validated_sql is None:
        raise RuntimeError(f"Benchmark case {preset.key} failed validation: {validation.message}")

    cold_result = await execute_safe_query(
        validation.validated_sql,
        role=role,
        db=db,
        query_id=None,
        use_cache=False,
    )
    warm_samples: list[QueryExecutionResult] = []
    for _ in range(max(1, iterations - 1)):
        warm_samples.append(
            await execute_safe_query(
                validation.validated_sql,
                role=role,
                db=db,
                query_id=None,
                use_cache=True,
            )
        )

    execution_samples = [cold_result.execution_ms] + [item.execution_ms for item in warm_samples]
    cache_hit_rate = (
        sum(1 for item in warm_samples if item.cached) / len(warm_samples)
        if warm_samples
        else 0.0
    )
    latest_result = warm_samples[-1] if warm_samples else cold_result
    return {
        "key": preset.key,
        "title": preset.title,
        "question": preset.question,
        "fingerprint": latest_result.fingerprint,
        "sql": validation.validated_sql.sql,
        "row_count": latest_result.row_count,
        "cold_execution_ms": cold_result.execution_ms,
        "warm_execution_ms": [item.execution_ms for item in warm_samples],
        "avg_execution_ms": round(mean(execution_samples), 2) if execution_samples else 0.0,
        "p95_execution_ms": _p95(execution_samples),
        "cache_hit_rate": round(cache_hit_rate, 4),
        "explain_cost": float(validation.validated_sql.explain_cost or 0),
        "sample_explain": build_explain_sample(validation.validated_sql.explain_plan),
        "validator_summary": validation.validated_sql.validator_summary,
    }


async def run_benchmark_suite(
    db: AsyncSession,
    *,
    iterations: int,
    role: str = "admin",
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for preset in BENCHMARK_PRESETS:
        results.append(await _run_single_case(db, preset=preset, iterations=iterations, role=role))
    return {
        "iterations": iterations,
        "cases": results,
        "p95_execution_ms": _p95([int(case["p95_execution_ms"]) for case in results]),
    }
