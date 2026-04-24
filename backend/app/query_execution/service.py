from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import analytics_engine, platform_engine
from app.models import QueryExecutionAudit, QueryResultCache
from app.query_execution.fingerprint import build_query_fingerprint
from app.services.charts import serialize_rows
from app.services.guardrails import ValidatedSQL
from app.services.observability import trace_span

settings = get_settings()


@dataclass(frozen=True)
class QueryExecutionResult:
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: int
    cached: bool
    fingerprint: str
    explain_plan: dict[str, Any]
    explain_cost: float
    execution_mode: str
    cache_expires_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "execution_ms": self.execution_ms,
            "cached": self.cached,
            "fingerprint": self.fingerprint,
            "explain_cost": self.explain_cost,
            "execution_mode": self.execution_mode,
            "cache_expires_at": self.cache_expires_at.isoformat() if self.cache_expires_at else None,
            "sample_explain": build_explain_sample(self.explain_plan),
        }


def build_explain_sample(plan: dict[str, Any]) -> dict[str, Any]:
    root = dict(plan.get("Plan", {}))
    return {
        "node_type": root.get("Node Type", ""),
        "relation_name": root.get("Relation Name", ""),
        "strategy": root.get("Strategy", ""),
        "plan_rows": int(root.get("Plan Rows", 0) or 0),
        "total_cost": float(root.get("Total Cost", 0) or 0),
        "plans": [
            {
                "node_type": child.get("Node Type", ""),
                "relation_name": child.get("Relation Name", ""),
                "plan_rows": int(child.get("Plan Rows", 0) or 0),
                "total_cost": float(child.get("Total Cost", 0) or 0),
            }
            for child in list(root.get("Plans", []))[:3]
            if isinstance(child, dict)
        ],
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cache_enabled_for(validated_sql: ValidatedSQL, use_cache: bool) -> bool:
    if not use_cache or not settings.query_cache_enabled:
        return False
    if validated_sql.row_limit > settings.query_cache_max_rows:
        return False
    return True


async def _get_cache_entry(db: AsyncSession, fingerprint: str) -> QueryResultCache | None:
    stmt = select(QueryResultCache).where(QueryResultCache.fingerprint == fingerprint)
    return await db.scalar(stmt)


async def _prune_expired_cache(db: AsyncSession) -> int:
    now = _utcnow()
    rows = list(
        (
            await db.scalars(
                select(QueryResultCache).where(QueryResultCache.expires_at < now).limit(100)
            )
        ).all()
    )
    for row in rows:
        await db.delete(row)
    if rows:
        await db.flush()
    return len(rows)


async def _touch_cache_hit(db: AsyncSession, entry: QueryResultCache) -> None:
    entry.hit_count += 1
    entry.last_accessed_at = _utcnow()
    await db.flush()


async def _upsert_cache_entry(
    db: AsyncSession,
    *,
    fingerprint: str,
    role: str,
    validated_sql: ValidatedSQL,
    rows: list[dict[str, Any]],
) -> QueryResultCache:
    now = _utcnow()
    entry = await _get_cache_entry(db, fingerprint)
    expires_at = now + timedelta(seconds=settings.query_cache_ttl_seconds)
    if entry is None:
        entry = QueryResultCache(
            fingerprint=fingerprint,
            role=role,
            sql_text=validated_sql.sql,
            row_limit=validated_sql.row_limit,
            explain_cost=validated_sql.explain_cost,
            explain_plan_json=validated_sql.explain_plan,
            result_rows_json=rows,
            row_count=len(rows),
            hit_count=0,
            expires_at=expires_at,
            last_accessed_at=now,
        )
        db.add(entry)
    else:
        entry.role = role
        entry.sql_text = validated_sql.sql
        entry.row_limit = validated_sql.row_limit
        entry.explain_cost = validated_sql.explain_cost
        entry.explain_plan_json = validated_sql.explain_plan
        entry.result_rows_json = rows
        entry.row_count = len(rows)
        entry.expires_at = expires_at
        entry.updated_at = now
        entry.last_accessed_at = now
    await db.flush()
    return entry


async def _record_execution_audit(
    db: AsyncSession | None,
    *,
    query_id: UUID | None,
    fingerprint: str,
    role: str,
    sql_text: str,
    cache_hit: bool,
    execution_mode: str,
    row_count: int,
    execution_ms: int,
    explain_cost: float,
    status: str,
    error_message: str = "",
    details: dict[str, Any] | None = None,
    explain_plan: dict[str, Any] | None = None,
) -> None:
    if db is None:
        return
    db.add(
        QueryExecutionAudit(
            query_id=query_id,
            fingerprint=fingerprint,
            role=role,
            sql_text=sql_text,
            cache_hit=cache_hit,
            execution_mode=execution_mode,
            row_count=row_count,
            execution_ms=execution_ms,
            explain_cost=explain_cost,
            status=status,
            error_message=error_message,
            details_json=details or {},
            explain_plan_json=explain_plan or {},
        )
    )
    await db.flush()


async def _execute_database_query(validated_sql: ValidatedSQL) -> tuple[list[dict[str, Any]], int]:
    started = _utcnow()
    async with analytics_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text(f"SET LOCAL statement_timeout = {settings.query_timeout_ms}"))
            await conn.execute(text(f"SET LOCAL lock_timeout = {settings.sql_lock_timeout_ms}"))
            await conn.execute(
                text(
                    f"SET LOCAL idle_in_transaction_session_timeout = {settings.sql_idle_in_transaction_timeout_ms}"
                )
            )
            result = await conn.execute(text(validated_sql.sql))
            rows = [dict(row._mapping) for row in result.fetchall()]
    duration_ms = int((_utcnow() - started).total_seconds() * 1000)
    serialized = serialize_rows(rows[: validated_sql.row_limit])
    return serialized, duration_ms


async def execute_safe_query(
    validated_sql: ValidatedSQL,
    *,
    role: str,
    db: AsyncSession | None = None,
    query_id: UUID | None = None,
    use_cache: bool = True,
) -> QueryExecutionResult:
    fingerprint = build_query_fingerprint(validated_sql.sql, role)
    cache_allowed = _cache_enabled_for(validated_sql, use_cache)

    with trace_span(
        "tolmach.query_execution",
        {
            "fingerprint": fingerprint,
            "role": role,
            "cache_enabled": cache_allowed,
        },
    ):
        if cache_allowed and db is not None:
            await _prune_expired_cache(db)
            cache_entry = await _get_cache_entry(db, fingerprint)
            if cache_entry is not None and cache_entry.expires_at >= _utcnow():
                await _touch_cache_hit(db, cache_entry)
                await _record_execution_audit(
                    db,
                    query_id=query_id,
                    fingerprint=fingerprint,
                    role=role,
                    sql_text=validated_sql.sql,
                    cache_hit=True,
                    execution_mode="cache",
                    row_count=cache_entry.row_count,
                    execution_ms=0,
                    explain_cost=float(cache_entry.explain_cost or 0),
                    status="ok",
                    details={"source": "query_result_cache"},
                    explain_plan=dict(cache_entry.explain_plan_json or {}),
                )
                return QueryExecutionResult(
                    rows=list(cache_entry.result_rows_json or []),
                    row_count=int(cache_entry.row_count or 0),
                    execution_ms=0,
                    cached=True,
                    fingerprint=fingerprint,
                    explain_plan=dict(cache_entry.explain_plan_json or {}),
                    explain_cost=float(cache_entry.explain_cost or 0),
                    execution_mode="cache",
                    cache_expires_at=cache_entry.expires_at,
                )

        try:
            rows, execution_ms = await _execute_database_query(validated_sql)
        except Exception as exc:
            await _record_execution_audit(
                db,
                query_id=query_id,
                fingerprint=fingerprint,
                role=role,
                sql_text=validated_sql.sql,
                cache_hit=False,
                execution_mode="database",
                row_count=0,
                execution_ms=0,
                explain_cost=float(validated_sql.explain_cost or 0),
                status="error",
                error_message=str(exc),
                details={"validator_summary": validated_sql.validator_summary},
                explain_plan=validated_sql.explain_plan,
            )
            raise

        cache_expires_at = None
        if cache_allowed and db is not None:
            entry = await _upsert_cache_entry(
                db,
                fingerprint=fingerprint,
                role=role,
                validated_sql=validated_sql,
                rows=rows,
            )
            cache_expires_at = entry.expires_at

        await _record_execution_audit(
            db,
            query_id=query_id,
            fingerprint=fingerprint,
            role=role,
            sql_text=validated_sql.sql,
            cache_hit=False,
            execution_mode="database",
            row_count=len(rows),
            execution_ms=execution_ms,
            explain_cost=float(validated_sql.explain_cost or 0),
            status="ok",
            details={"validator_summary": validated_sql.validator_summary},
            explain_plan=validated_sql.explain_plan,
        )
        return QueryExecutionResult(
            rows=rows,
            row_count=len(rows),
            execution_ms=execution_ms,
            cached=False,
            fingerprint=fingerprint,
            explain_plan=validated_sql.explain_plan,
            explain_cost=float(validated_sql.explain_cost or 0),
            execution_mode="database",
            cache_expires_at=cache_expires_at,
        )


async def get_query_cache_stats(db: AsyncSession) -> dict[str, Any]:
    now = _utcnow()
    total_entries = int(await db.scalar(select(func.count(QueryResultCache.id))) or 0)
    active_entries = int(
        await db.scalar(select(func.count(QueryResultCache.id)).where(QueryResultCache.expires_at >= now))
        or 0
    )
    expired_entries = total_entries - active_entries
    total_hit_count = int(await db.scalar(select(func.coalesce(func.sum(QueryResultCache.hit_count), 0))) or 0)
    avg_row_count = float(await db.scalar(select(func.coalesce(func.avg(QueryResultCache.row_count), 0))) or 0)
    recent_entries = list(
        (
            await db.scalars(
                select(QueryResultCache).order_by(QueryResultCache.updated_at.desc()).limit(10)
            )
        ).all()
    )
    return {
        "cache_enabled": settings.query_cache_enabled,
        "ttl_seconds": settings.query_cache_ttl_seconds,
        "total_entries": total_entries,
        "active_entries": active_entries,
        "expired_entries": expired_entries,
        "total_hit_count": total_hit_count,
        "avg_row_count": round(avg_row_count, 2),
        "recent_entries": [
            {
                "fingerprint": row.fingerprint,
                "role": row.role,
                "row_count": row.row_count,
                "hit_count": row.hit_count,
                "expires_at": row.expires_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
                "sample_explain": build_explain_sample(dict(row.explain_plan_json or {})),
            }
            for row in recent_entries
        ],
    }


async def list_query_execution_audits(
    db: AsyncSession,
    *,
    limit: int = 50,
    cache_hit: bool | None = None,
    status: str | None = None,
    fingerprint: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(QueryExecutionAudit).order_by(QueryExecutionAudit.created_at.desc()).limit(
        max(1, min(limit, settings.query_observability_limit))
    )
    if cache_hit is not None:
        stmt = stmt.where(QueryExecutionAudit.cache_hit.is_(cache_hit))
    if status:
        stmt = stmt.where(QueryExecutionAudit.status == status)
    if fingerprint:
        stmt = stmt.where(QueryExecutionAudit.fingerprint == fingerprint)
    rows = list((await db.scalars(stmt)).all())
    return [
        {
            "id": row.id,
            "query_id": row.query_id,
            "fingerprint": row.fingerprint,
            "role": row.role,
            "cache_hit": row.cache_hit,
            "execution_mode": row.execution_mode,
            "row_count": row.row_count,
            "execution_ms": row.execution_ms,
            "explain_cost": float(row.explain_cost or 0),
            "status": row.status,
            "error_message": row.error_message,
            "details": dict(row.details_json or {}),
            "sample_explain": build_explain_sample(dict(row.explain_plan_json or {})),
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def get_query_execution_summary(db: AsyncSession) -> dict[str, Any]:
    rows = list(
        (
            await db.scalars(
                select(QueryExecutionAudit)
                .where(QueryExecutionAudit.status == "ok")
                .order_by(QueryExecutionAudit.created_at.desc())
                .limit(settings.query_observability_limit)
            )
        ).all()
    )
    execution_samples = [row.execution_ms for row in rows if not row.cache_hit and row.execution_ms >= 0]
    cache_hits = sum(1 for row in rows if row.cache_hit)
    total_rows = len(rows)
    return {
        "sample_size": total_rows,
        "cache_hit_rate": round((cache_hits / total_rows), 4) if total_rows else 0.0,
        "avg_execution_ms": round(mean(execution_samples), 2) if execution_samples else 0.0,
        "p95_target_ms": settings.benchmark_p95_target_ms,
    }
