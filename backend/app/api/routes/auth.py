from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.utils import device_hint, to_user_out
from app.auth import apply_session_cookies, clear_session_cookies, create_session_bundle, hash_password, needs_password_rehash, revoke_session, verify_password
from app.config import get_settings
from app.models import User
from app.schemas import AuthResponse, LoginRequest, LogoutResponse, RegisterRequest, UserOut

settings = get_settings()


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Введите корректный email")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Пользователь уже существует")
    user = User(
        email=email,
        full_name=payload.full_name or email.split("@", 1)[0],
        password_hash=hash_password(payload.password),
        role="user",
        preferences={"theme": "dark"},
    )
    db.add(user)
    await db.flush()
    bundle = await create_session_bundle(db, user=user, device_hint=device_hint(request))
    apply_session_cookies(response, bundle)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=to_user_out(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if needs_password_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = datetime.utcnow()
    bundle = await create_session_bundle(db, user=user, device_hint=device_hint(request))
    apply_session_cookies(response, bundle)
    await db.commit()
    return AuthResponse(user=to_user_out(user))


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> LogoutResponse:
    await revoke_session(db, request.cookies.get(settings.session_cookie_name))
    await db.commit()
    clear_session_cookies(response)
    return LogoutResponse(ok=True)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(user)
