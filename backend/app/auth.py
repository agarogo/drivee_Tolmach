from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import RefreshToken, User

settings = get_settings()
http_bearer = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _json_dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sign(signing_input: str) -> str:
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64url(signature)


def _token_ttl_seconds(token_type: str) -> int:
    if token_type == "refresh":
        days = int(getattr(settings, "refresh_token_ttl_days", 30) or 30)
        return days * 24 * 60 * 60
    minutes = int(getattr(settings, "jwt_ttl_minutes", 60) or 60)
    return minutes * 60


def _token_issuer() -> str:
    return str(getattr(settings, "jwt_issuer", "tolmach"))


def _hash_token_value(token: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    n = 2**14
    r = 8
    p = 1
    dklen = 32
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
    )
    return f"scrypt${n}${r}${p}${dklen}${_b64url(salt)}${_b64url(digest)}"


def _verify_scrypt_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_raw, r_raw, p_raw, dklen_raw, salt_raw, digest_raw = encoded.split("$", 6)
        if algorithm != "scrypt":
            return False
        n = int(n_raw)
        r = int(r_raw)
        p = int(p_raw)
        dklen = int(dklen_raw)
        salt = _b64url_decode(salt_raw)
        expected = _b64url_decode(digest_raw)
    except Exception:
        return False

    actual = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
    )
    return hmac.compare_digest(actual, expected)


def _verify_legacy_pbkdf2_password(password: str, encoded: str) -> bool:
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


def verify_password(password: str, encoded: str) -> bool:
    if not encoded:
        return False
    if encoded.startswith("scrypt$"):
        return _verify_scrypt_password(password, encoded)
    if encoded.startswith("pbkdf2_sha256$"):
        return _verify_legacy_pbkdf2_password(password, encoded)
    return False


def password_needs_rehash(encoded: str) -> bool:
    return not encoded.startswith("scrypt$")


def create_signed_token(payload: dict[str, Any], token_type: str = "access") -> str:
    now = utcnow()
    claims = {
        **payload,
        "typ": token_type,
        "iss": _token_issuer(),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=_token_ttl_seconds(token_type))).timestamp()),
        "jti": secrets.token_urlsafe(18),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64url(_json_dumps(header))}.{_b64url(_json_dumps(claims))}"
    return f"{signing_input}.{_sign(signing_input)}"


def create_access_token(payload: dict[str, Any]) -> str:
    return create_signed_token(payload, token_type="access")


def create_refresh_token(payload: dict[str, Any]) -> str:
    return create_signed_token(payload, token_type="refresh")


def decode_signed_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        ) from exc

    signing_input = f"{header_raw}.{payload_raw}"
    expected_signature = _sign(signing_input)
    if not hmac.compare_digest(expected_signature, signature_raw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        )

    try:
        header = json.loads(_b64url_decode(header_raw))
        payload = json.loads(_b64url_decode(payload_raw))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        ) from exc

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    if payload.get("iss") != _token_issuer():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    now = int(utcnow().timestamp())
    if int(payload.get("nbf", 0)) > now or int(payload.get("exp", 0)) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Срок токена истёк")
    if expected_type and payload.get("typ") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_signed_token(token, expected_type="access")


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    await db.flush()
    return user


async def issue_token_pair(db: AsyncSession, user: User, device_hint: str = "") -> dict[str, str]:
    base_payload = {"sub": str(user.id), "email": user.email, "role": user.role}
    access_token = create_access_token(base_payload)
    refresh_token = create_refresh_token(base_payload)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=_hash_token_value(refresh_token),
            device_hint=device_hint[:255],
            expires_at=utcnow() + timedelta(seconds=_token_ttl_seconds("refresh")),
        )
    )
    await db.flush()
    return {"access_token": access_token, "refresh_token": refresh_token}


async def rotate_refresh_token(db: AsyncSession, refresh_token: str, device_hint: str = "") -> tuple[User, dict[str, str]]:
    payload = decode_signed_token(refresh_token, expected_type="refresh")
    refresh_row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token_value(refresh_token))
    )
    if not refresh_row or refresh_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token недействителен")
    if refresh_row.expires_at and refresh_row.expires_at <= utcnow().replace(tzinfo=None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token истёк")

    user_id = payload.get("sub")
    try:
        parsed_user_id = UUID(str(user_id)) if user_id is not None else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен") from exc

    user = await db.get(User, parsed_user_id) if parsed_user_id else None
    if not user or not user.is_active or user.id != refresh_row.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")

    refresh_row.revoked_at = utcnow()
    await db.flush()
    token_pair = await issue_token_pair(db, user, device_hint=device_hint or refresh_row.device_hint)
    user.last_login_at = utcnow()
    await db.flush()
    return user, token_pair


async def revoke_refresh_token(db: AsyncSession, refresh_token: str) -> None:
    try:
        decode_signed_token(refresh_token, expected_type="refresh")
    except HTTPException:
        return
    refresh_row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash_token_value(refresh_token))
    )
    if refresh_row and refresh_row.revoked_at is None:
        refresh_row.revoked_at = utcnow()
        await db.flush()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нужна авторизация",
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    try:
        parsed_user_id = UUID(str(user_id)) if user_id is not None else None
    except ValueError:
        parsed_user_id = None
    user = await db.get(User, parsed_user_id) if parsed_user_id is not None else None
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только администратору",
        )
    return user
