from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import RefreshToken, User

settings = get_settings()
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}
SESSION_SIGNING_SALT = "tolmach-session-v1"


@dataclass(frozen=True)
class SessionBundle:
    session_token: str
    csrf_token: str
    expires_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache(maxsize=1)
def _password_hasher() -> PasswordHasher:
    # Argon2id parameters are intentionally explicit so hashes remain stable
    # across dependency updates while still being much safer than hand-written PBKDF2.
    return PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)


@lru_cache(maxsize=1)
def _session_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.session_secret_key_effective, salt=SESSION_SIGNING_SALT)


def hash_password(password: str) -> str:
    return _password_hasher().hash(password)


def _verify_legacy_pbkdf2(password: str, encoded: str) -> bool:
    """Read-only compatibility with old hashes created before the auth refactor."""
    import base64

    def b64url_decode(data: str) -> bytes:
        padding = "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)

    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        salt = b64url_decode(salt_raw)
        expected = b64url_decode(digest_raw)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def verify_password(password: str, encoded: str) -> bool:
    if not encoded:
        return False
    if encoded.startswith("pbkdf2_sha256$"):
        return _verify_legacy_pbkdf2(password, encoded)
    try:
        return _password_hasher().verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError, ValueError):
        return False


def needs_password_rehash(encoded: str) -> bool:
    if not encoded or encoded.startswith("pbkdf2_sha256$"):
        return True
    try:
        return _password_hasher().check_needs_rehash(encoded)
    except (InvalidHashError, VerificationError, ValueError):
        return True


def _sign_session_token(raw_token: str) -> str:
    return _session_serializer().dumps({"token": raw_token})


def _unsign_session_token(signed_token: str | None) -> str | None:
    if not signed_token:
        return None
    try:
        payload = _session_serializer().loads(signed_token)
    except BadSignature:
        return None
    if not isinstance(payload, dict):
        return None
    token = payload.get("token")
    return token if isinstance(token, str) and token else None


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def create_session_bundle(
    db: AsyncSession,
    *,
    user: User,
    device_hint: str = "",
) -> SessionBundle:
    import secrets

    raw_session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(hours=max(1, settings.session_ttl_hours))
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_session_token(raw_session_token),
            device_hint=device_hint[:255],
            expires_at=expires_at,
        )
    )
    await db.flush()
    return SessionBundle(
        session_token=_sign_session_token(raw_session_token),
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


async def resolve_session_user(db: AsyncSession, signed_session_token: str) -> User | None:
    raw_session_token = _unsign_session_token(signed_session_token)
    if not raw_session_token:
        return None

    session_hash = hash_session_token(raw_session_token)
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


async def revoke_session(db: AsyncSession, signed_session_token: str | None) -> bool:
    raw_session_token = _unsign_session_token(signed_session_token)
    if not raw_session_token:
        return False
    session_hash = hash_session_token(raw_session_token)
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
    signed_session_token = request.cookies.get(settings.session_cookie_name)
    if not signed_session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    require_csrf(request)
    user = await resolve_session_user(db, signed_session_token)
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
