"""Authentication operations. Services own transactions and never expose raw tokens in DB."""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    REFRESH_DAYS,
    AuthTokens,
    hash_password,
    make_access_token,
    random_refresh,
    refresh_hash,
    verify_password,
)
from app.models import AuditLog, AuthSession, Guest, GuestAccount, User, Wallet
from app.services.guests import normalize_phone

DUMMY_HASH = PasswordHasher().hash("not-an-account-password")


class AuthError(Exception):
    def __init__(self, code: str, status: int = 401):
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Actor:
    type: str
    id: int
    session_id: int
    role: str | None = None
    must_change_password: bool = False


def audit(
    session: Session,
    action: str,
    entity_type: str,
    entity_id: int,
    *,
    actor_type: str = "system",
    actor_id: int | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def register_guest(
    session: Session,
    *,
    first_name: str,
    last_name: str,
    phone: str,
    password: str,
    settings: Settings,
) -> tuple[int, int]:
    normalized = normalize_phone(phone)
    first_name, last_name = first_name.strip(), last_name.strip()
    if not first_name or not last_name or len(password) < 12:
        raise AuthError("invalid_registration", 422)
    password_digest = hash_password(password, settings)
    for attempt in range(2):
        try:
            with session.begin():
                if session.scalar(select(GuestAccount.id).where(GuestAccount.phone == normalized)):
                    raise AuthError("account_exists", 409)
                guest = session.scalar(
                    select(Guest).where(Guest.phone == normalized).with_for_update()
                )
                if guest is None:
                    guest = Guest(first_name=first_name, last_name=last_name, phone=normalized)
                    session.add(guest)
                    session.flush()
                    session.add(Wallet(guest_id=guest.id, balance=0))
                    session.flush()
                elif session.scalar(select(Wallet.id).where(Wallet.guest_id == guest.id)) is None:
                    raise AuthError("profile_incomplete", 409)
                account = GuestAccount(
                    guest_id=guest.id,
                    phone=normalized,
                    password_hash=password_digest,
                )
                session.add(account)
                session.flush()
                audit(session, "auth.guest_registered", "guest_account", account.id)
                return guest.id, account.id
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(GuestAccount.id).where(GuestAccount.phone == normalized)
            )
            session.rollback()
            if existing is not None or attempt == 1:
                raise AuthError("account_exists", 409) from None
    raise AuthError("account_exists", 409)


def _create_session(
    session: Session,
    *,
    actor_type: str,
    actor_id: int,
    settings: Settings,
) -> AuthTokens:
    token = random_refresh()
    record = AuthSession(
        actor_type=actor_type,
        actor_id=actor_id,
        refresh_token_hash=refresh_hash(token),
        expires_at=datetime.now(UTC) + timedelta(days=REFRESH_DAYS),
    )
    session.add(record)
    session.flush()
    return AuthTokens(
        access=make_access_token(
            actor_type=actor_type, actor_id=actor_id, session_id=record.id, settings=settings
        ),
        refresh=token,
        csrf=secrets.token_urlsafe(32),
    )


def login(
    session: Session,
    *,
    actor_type: str,
    identifier: str,
    password: str,
    settings: Settings,
) -> tuple[AuthTokens, bool]:
    model = User if actor_type == "user" else GuestAccount
    field = User.username if actor_type == "user" else GuestAccount.phone
    if actor_type == "guest":
        try:
            identifier = normalize_phone(identifier)
        except ValueError:
            identifier = ""
    failed = False
    tokens = None
    must_change = False
    with session.begin():
        account = session.scalar(select(model).where(field == identifier).with_for_update())
        now = datetime.now(UTC)
        if account is None or not account.is_active:
            verify_password(DUMMY_HASH, password, settings)
            failed = True
        elif account.locked_until is not None and account.locked_until > now:
            failed = True
        elif (
            actor_type == "guest"
            and account.must_change_password
            and account.temp_password_expires_at is None
        ):
            failed = True
        elif (
            actor_type == "guest"
            and account.must_change_password
            and account.temp_password_expires_at <= now
        ):
            failed = True
        elif not verify_password(account.password_hash, password, settings):
            account.failed_login_count += 1
            if account.failed_login_count >= settings.login_max_failures:
                account.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                account.failed_login_count = 0
            failed = True
        else:
            account.failed_login_count = 0
            account.locked_until = None
            must_change = actor_type == "guest" and account.must_change_password
            if must_change:
                account.temp_password_expires_at = None  # one successful login consumes it
            if actor_type == "guest":
                account.last_login_at = now
            tokens = _create_session(
                session, actor_type=actor_type, actor_id=account.id, settings=settings
            )
        audit(
            session,
            "auth.login_failed" if failed else "auth.login_succeeded",
            actor_type,
            account.id if account else 0,
        )
    if failed or tokens is None:
        raise AuthError("invalid_credentials")
    return tokens, must_change


def rotate_refresh(session: Session, *, token: str, settings: Settings) -> AuthTokens:
    result = None
    failed = False
    with session.begin():
        record = session.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == refresh_hash(token))
            .with_for_update()
        )
        now = datetime.now(UTC)
        if record is None:
            failed = True
        elif record.revoked_at is not None:
            if record.replaced_by_session_id is not None:
                session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.actor_type == record.actor_type,
                        AuthSession.actor_id == record.actor_id,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                audit(session, "auth.refresh_reuse", record.actor_type, record.actor_id)
            failed = True
        elif record.expires_at <= now:
            record.revoked_at = now
            failed = True
        else:
            model = User if record.actor_type == "user" else GuestAccount
            actor = session.get(model, record.actor_id)
            if actor is None or not actor.is_active:
                record.revoked_at = now
                failed = True
            else:
                record.revoked_at = now
                record.last_used_at = now
                result = _create_session(
                    session,
                    actor_type=record.actor_type,
                    actor_id=record.actor_id,
                    settings=settings,
                )
                record.replaced_by_session_id = session.scalar(
                    select(AuthSession.id).where(
                        AuthSession.refresh_token_hash == refresh_hash(result.refresh)
                    )
                )
                audit(session, "auth.refresh", record.actor_type, record.actor_id)
    if failed or result is None:
        raise AuthError("invalid_session")
    return result


def revoke_session(session: Session, *, token: str | None) -> None:
    if not token:
        return
    with session.begin():
        record = session.scalar(
            select(AuthSession)
            .where(AuthSession.refresh_token_hash == refresh_hash(token))
            .with_for_update()
        )
        if record and record.revoked_at is None:
            record.revoked_at = datetime.now(UTC)
            audit(session, "auth.logout", record.actor_type, record.actor_id)


def revoke_actor_sessions(session: Session, *, actor_type: str, actor_id: int) -> None:
    session.execute(
        update(AuthSession)
        .where(
            AuthSession.actor_type == actor_type,
            AuthSession.actor_id == actor_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )


def issue_guest_temp_password(
    session: Session, *, guest_id: int, issued_by: Actor, settings: Settings
) -> str:
    password = secrets.token_urlsafe(18)
    with session.begin():
        account = session.scalar(
            select(GuestAccount).where(GuestAccount.guest_id == guest_id).with_for_update()
        )
        if account is None or not account.is_active:
            raise AuthError("guest_account_not_found", 404)
        account.password_hash = hash_password(password, settings)
        account.must_change_password = True
        account.temp_password_expires_at = datetime.now(UTC) + timedelta(hours=24)
        account.failed_login_count = 0
        account.locked_until = None
        revoke_actor_sessions(session, actor_type="guest", actor_id=account.id)
        audit(
            session,
            "auth.temp_password_issued",
            "guest",
            account.id,
            actor_type="user",
            actor_id=issued_by.id,
        )
    return password


def change_password(
    session: Session,
    *,
    actor: Actor,
    new_password: str,
    current_password: str | None,
    settings: Settings,
) -> None:
    if len(new_password) < 12:
        raise AuthError("weak_password", 422)
    model = User if actor.type == "user" else GuestAccount
    with session.begin():
        account = session.scalar(select(model).where(model.id == actor.id).with_for_update())
        if account is None or not account.is_active:
            raise AuthError("invalid_session")
        if actor.type == "guest":
            if not account.must_change_password or account.temp_password_expires_at is not None:
                raise AuthError("password_change_not_available", 403)
        elif not current_password or not verify_password(
            account.password_hash, current_password, settings
        ):
            raise AuthError("invalid_credentials")
        account.password_hash = hash_password(new_password, settings)
        if actor.type == "guest":
            account.must_change_password = False
            account.temp_password_expires_at = None
        revoke_actor_sessions(session, actor_type=actor.type, actor_id=actor.id)
        audit(session, "auth.password_changed", actor.type, actor.id)
