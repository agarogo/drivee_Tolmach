from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import to_user_out
from app.auth import authenticate_user, get_current_user, issue_token_pair, hash_password, revoke_refresh_token, rotate_refresh_token
from app.db import get_db
from app.models import User
from app.schemas import AuthResponse, LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, StatusResponse, UserOut

router = APIRouter()


@router.post("/auth/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    user_agent: str | None = Header(default=None),
) -> AuthResponse:
    email = payload.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=400, detail="Введите корректный email")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Пользователь уже существует")

    user = User(
        email=email,
        full_name=(payload.full_name or email.split("@", 1)[0]).strip(),
        password_hash=hash_password(payload.password),
        role="user",
        preferences={"theme": "dark"},
    )
    db.add(user)
    await db.flush()
    tokens = await issue_token_pair(db, user, device_hint=user_agent or "")
    await db.commit()
    await db.refresh(user)
    return AuthResponse(**tokens, user=to_user_out(user))


@router.post("/auth/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
    user_agent: str | None = Header(default=None),
) -> AuthResponse:
    user = await authenticate_user(db, payload.email, payload.password)
    tokens = await issue_token_pair(db, user, device_hint=user_agent or "")
    await db.commit()
    return AuthResponse(**tokens, user=to_user_out(user))


@router.post("/auth/refresh", response_model=AuthResponse)
async def refresh_tokens(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    user_agent: str | None = Header(default=None),
) -> AuthResponse:
    user, tokens = await rotate_refresh_token(db, payload.refresh_token, device_hint=user_agent or "")
    await db.commit()
    return AuthResponse(**tokens, user=to_user_out(user))


@router.post("/auth/logout", response_model=StatusResponse)
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)) -> StatusResponse:
    await revoke_refresh_token(db, payload.refresh_token)
    await db.commit()
    return StatusResponse(message="logged_out")


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)
