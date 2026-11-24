"""Reusable session, origin, CSRF and actor guards."""

import secrets
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, parse_access_token
from app.models import (
    AuthSession,
    Event,
    EventSecretary,
    GuestAccount,
    PaymentSubmission,
    Registration,
    User,
    Wallet,
)
from app.services.auth import Actor


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


def require_browser_origin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    origin = request.headers.get("origin")
    allowed_origins = {settings.public_origin}
    if settings.environment == "development":
        configured = urlsplit(settings.public_origin)
        if configured.hostname in {"localhost", "127.0.0.1"}:
            alternate_host = (
                "localhost" if configured.hostname == "127.0.0.1" else "127.0.0.1"
            )
            port = f":{configured.port}" if configured.port is not None else ""
            allowed_origins.add(f"{configured.scheme}://{alternate_host}{port}")
    if origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="invalid_origin")
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site not in {None, "same-origin"}:
        raise HTTPException(status_code=403, detail="invalid_origin")


def require_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="invalid_csrf")


def current_actor(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Actor:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="invalid_session")
    try:
        claims = parse_access_token(token, settings)
        actor_type = claims["actor_type"]
        actor_id = int(claims["sub"])
        session_id = int(claims["sid"])
        if actor_type not in {"user", "guest"} or actor_id <= 0 or session_id <= 0:
            raise ValueError("Invalid token claims")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(status_code=401, detail="invalid_session") from None
    record = session.get(AuthSession, session_id)
    model = User if actor_type == "user" else GuestAccount
    account = session.get(model, actor_id)
    now = datetime.now(UTC)
    if (
        record is None
        or record.actor_type != actor_type
        or record.actor_id != actor_id
        or record.revoked_at is not None
        or record.expires_at <= now
        or account is None
        or not account.is_active
    ):
        raise HTTPException(status_code=401, detail="invalid_session")
    actor = Actor(
        type=actor_type,
        id=actor_id,
        session_id=session_id,
        role=account.role if actor_type == "user" else None,
        must_change_password=account.must_change_password if actor_type == "guest" else False,
    )
    session.rollback()  # services can start their own transaction
    return actor


def require_active_admin(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.type != "user":
        raise HTTPException(status_code=403, detail="forbidden")
    return actor


def require_super_admin(actor: Actor = Depends(require_active_admin)) -> Actor:
    if actor.role != "super_admin":
        raise HTTPException(status_code=403, detail="forbidden")
    return actor


def require_event_secretary(
    event_id: int,
    actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> Actor:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    assigned = actor.role == "super_admin" or session.scalar(
        select(EventSecretary.user_id).where(
            EventSecretary.event_id == event_id, EventSecretary.user_id == actor.id
        )
    ) is not None
    session.rollback()
    if not assigned:
        raise HTTPException(status_code=403, detail="forbidden")
    return actor


def require_active_guest(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.type != "guest" or actor.must_change_password:
        raise HTTPException(status_code=403, detail="forbidden")
    return actor


GUEST_OWNED_MODELS = {
    "registration": Registration,
    "payment": PaymentSubmission,
    "wallet": Wallet,
}


def require_guest_ownership(
    session: Session, *, actor: Actor, resource_type: str, resource_id: int
) -> int:
    """Return the guest profile ID, hiding other guests' resources as not found."""
    if actor.type != "guest" or actor.must_change_password:
        raise HTTPException(status_code=403, detail="forbidden")
    account = session.get(GuestAccount, actor.id)
    model = GUEST_OWNED_MODELS.get(resource_type)
    if account is None or not account.is_active or model is None:
        raise HTTPException(status_code=403, detail="forbidden")
    resource = session.get(model, resource_id)
    if resource is None or resource.guest_id != account.guest_id:
        raise HTTPException(status_code=404, detail="resource_not_found")
    return account.guest_id
