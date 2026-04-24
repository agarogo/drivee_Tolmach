from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query as ApiQuery
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.utils import query_to_out
from app.models import Query, User
from app.repositories.queries import require_owned_query
from app.schemas import QueryClarifyRequest, QueryOut, QueryRunRequest
from app.services.export import rows_to_csv
from app.services.query_flow import clarify_query_for_user, run_query_for_user

router = APIRouter(prefix="/queries", tags=["Queries"])


@router.post("/run", response_model=QueryOut)
async def run_query(
    payload: QueryRunRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    return await run_query_for_user(db, user, payload)


@router.post("/{query_id}/clarify", response_model=QueryOut)
async def clarify_query(
    query_id: UUID,
    payload: QueryClarifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    return await clarify_query_for_user(db, user, query_id, payload)


@router.get("/history", response_model=list[QueryOut])
async def query_history(
    limit: int = ApiQuery(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[QueryOut]:
    rows = list(
        (
            await db.scalars(
                select(Query).where(Query.user_id == user.id).order_by(Query.created_at.desc()).limit(limit)
            )
        ).all()
    )
    return [await query_to_out(db, row) for row in rows]


@router.get("/{query_id}", response_model=QueryOut)
async def get_query(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QueryOut:
    return await query_to_out(db, await require_owned_query(db, query_id, user))


@router.get("/{query_id}/export.csv", response_class=Response)
async def export_query_csv(
    query_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    item = await require_owned_query(db, query_id, user)
    csv_body = rows_to_csv(item.result_snapshot or [])
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="query-{query_id}.csv"'},
    )
