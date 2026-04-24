from datetime import datetime

from fastapi import APIRouter, Depends, Query as ApiQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.db import get_db
from app.models import Query, User
from app.query_execution.benchmarks import BENCHMARK_PRESETS
from app.schemas import BenchmarkPresetOut, LogOut, QueryExecutionAuditOut, QueryExecutionCacheStatsOut, QueryExecutionSummaryOut

router = APIRouter()


@router.get("/admin/logs", response_model=list[LogOut])
async def admin_logs(
    user_email: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[LogOut]:
    stmt = select(Query, User.email).outerjoin(User, User.id == Query.user_id)
    if user_email:
        stmt = stmt.where(User.email.ilike(f"%{user_email}%"))
    if date_from:
        stmt = stmt.where(Query.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Query.created_at <= datetime.fromisoformat(date_to))
    rows = (await db.execute(stmt.order_by(Query.created_at.desc()).limit(300))).all()
    return [
        LogOut(
            id=query.id,
            created_at=query.created_at,
            user_email=email,
            question=query.natural_text,
            generated_sql=query.corrected_sql or query.generated_sql,
            status=query.status,
            duration_ms=query.execution_ms,
            prompt=str(query.interpretation_json),
            raw_response=str(query.sql_plan_json),
            error=query.error_message or query.block_reason,
        )
        for query, email in rows
    ]


@router.get("/admin/query-execution/cache", response_model=QueryExecutionCacheStatsOut)
async def admin_query_execution_cache_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> QueryExecutionCacheStatsOut:
    import app.api as api_pkg

    return QueryExecutionCacheStatsOut.model_validate(await api_pkg.get_query_cache_stats(db))


@router.get("/admin/query-execution/summary", response_model=QueryExecutionSummaryOut)
async def admin_query_execution_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> QueryExecutionSummaryOut:
    import app.api as api_pkg

    return QueryExecutionSummaryOut.model_validate(await api_pkg.get_query_execution_summary(db))


@router.get("/admin/query-execution/audits", response_model=list[QueryExecutionAuditOut])
async def admin_query_execution_audits(
    limit: int = ApiQuery(default=50, ge=1, le=200),
    cache_hit: bool | None = None,
    status_filter: str | None = None,
    fingerprint: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[QueryExecutionAuditOut]:
    import app.api as api_pkg

    rows = await api_pkg.list_query_execution_audits(
        db,
        limit=limit,
        cache_hit=cache_hit,
        status=status_filter,
        fingerprint=fingerprint,
    )
    return [QueryExecutionAuditOut.model_validate(row) for row in rows]


@router.get("/admin/query-execution/benchmarks/presets", response_model=list[BenchmarkPresetOut])
async def admin_query_execution_benchmark_presets(
    _: User = Depends(require_admin),
) -> list[BenchmarkPresetOut]:
    return [BenchmarkPresetOut(key=item.key, title=item.title, question=item.question) for item in BENCHMARK_PRESETS]
