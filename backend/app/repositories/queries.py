from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Query, User


async def require_owned_query(db: AsyncSession, query_id: UUID, user: User) -> Query:
    item = await db.get(Query, query_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return item
