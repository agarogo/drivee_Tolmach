from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import RefreshToken, User

settings = get_settings()
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class SessionBundle:
    session_token: str
    csrf_token: str
    expires_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 180_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64url(salt)}${_b64url(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_raw)
        expected = _b64url_decode(digest_raw)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_session_bundle(
    db: AsyncSession,
    *,
    user: User,
    device_hint: str = "",
) -> SessionBundle:
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(hours=max(1, settings.session_ttl_hours))
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_session_token(session_token),
            device_hint=device_hint[:255],
            expires_at=expires_at,
        )
    )
    await db.flush()
    return SessionBundle(
        session_token=session_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )


def apply_session_cookies(response: Response, bundle: SessionBundle) -> None:
    max_age = max(0, int((bundle.expires_at - _utcnow()).total_seconds()))
    cookie_common = {
        "path": "/",
        "secure": settings.session_cookie_secure_effective,
        "samesite": settings.session_cookie_samesite,
        "max_age": max_age,
    }
    response.set_cookie(
        key=settings.session_cookie_name,
        value=bundle.session_token,
        httponly=True,
        **cookie_common,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=bundle.csrf_token,
        httponly=False,
        **cookie_common,
    )


def clear_session_cookies(response: Response) -> None:
    cookie_common = {
        "path": "/",
        "secure": settings.session_cookie_secure_effective,
        "samesite": settings.session_cookie_samesite,
    }
    response.delete_cookie(settings.session_cookie_name, **cookie_common)
    response.delete_cookie(settings.csrf_cookie_name, **cookie_common)


async def resolve_session_user(db: AsyncSession, session_token: str) -> User | None:
    session_hash = hash_session_token(session_token)
    session = await db.scalar(
        select(RefreshToken)
        .where(
            RefreshToken.token_hash == session_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .order_by(RefreshToken.created_at.desc())
    )
    if not session:
        return None
    if session.expires_at and session.expires_at <= _utcnow():
        session.revoked_at = _utcnow()
        await db.flush()
        return None

    user = await db.get(User, session.user_id)
    if not user or not user.is_active:
        return None
    return user


async def revoke_session(db: AsyncSession, session_token: str | None) -> bool:
    if not session_token:
        return False
    session_hash = hash_session_token(session_token)
    session = await db.scalar(
        select(RefreshToken)
        .where(
            RefreshToken.token_hash == session_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .order_by(RefreshToken.created_at.desc())
    )
    if not session:
        return False
    session.revoked_at = _utcnow()
    await db.flush()
    return True


def _csrf_header_value(request: Request) -> str | None:
    return request.headers.get(settings.csrf_header_name)


def require_csrf(request: Request) -> None:
    if request.method.upper() in SAFE_HTTP_METHODS:
        return

    csrf_cookie = request.cookies.get(settings.csrf_cookie_name) or ""
    csrf_header = _csrf_header_value(request) or ""
    if not csrf_cookie or not csrf_header or not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    require_csrf(request)
    user = await resolve_session_user(db, session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or is no longer valid.",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )
    return user
