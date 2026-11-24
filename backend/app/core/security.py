"""Password, token and cookie primitives for the same-origin auth flow."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Response

from app.core.config import Settings

ACCESS_MINUTES = 15
REFRESH_DAYS = 30
ACCESS_COOKIE = "hashti_access"
REFRESH_COOKIE = "hashti_refresh"
CSRF_COOKIE = "hashti_csrf"


@dataclass(frozen=True)
class AuthTokens:
    access: str
    refresh: str
    csrf: str


def password_hasher(settings: Settings) -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
        type=Type.ID,
    )


def hash_password(password: str, settings: Settings) -> str:
    return password_hasher(settings).hash(password)


def verify_password(stored_hash: str, password: str, settings: Settings) -> bool:
    try:
        return password_hasher(settings).verify(stored_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def random_refresh() -> str:
    return secrets.token_urlsafe(48)


def auth_secret(settings: Settings) -> str:
    if settings.auth_secret is None:
        raise RuntimeError("HASHTI_AUTH_SECRET is required for authentication")
    return settings.auth_secret.get_secret_value()


def make_access_token(
    *, actor_type: str, actor_id: int, session_id: int, settings: Settings
) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": "hashti",
        "aud": "hashti-api",
        "sub": str(actor_id),
        "actor_type": actor_type,
        "sid": session_id,
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_MINUTES),
    }
    return jwt.encode(claims, auth_secret(settings), algorithm="HS256")


def parse_access_token(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token,
        auth_secret(settings),
        algorithms=["HS256"],
        audience="hashti-api",
        issuer="hashti",
        options={"require": ["exp", "iat", "sub", "sid", "actor_type", "jti"]},
    )


def set_auth_cookies(response: Response, tokens: AuthTokens, settings: Settings) -> None:
    secure = settings.environment != "development"
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access,
        max_age=ACCESS_MINUTES * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh,
        max_age=REFRESH_DAYS * 86400,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth",
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf,
        max_age=REFRESH_DAYS * 86400,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    secure = settings.environment != "development"
    response.delete_cookie(ACCESS_COOKIE, path="/", secure=secure, samesite="lax")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", secure=secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
