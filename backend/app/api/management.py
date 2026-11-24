"""Super-admin secretary accounts and system settings."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    get_settings,
    require_browser_origin,
    require_csrf,
    require_super_admin,
)
from app.core.config import Settings
from app.core.security import hash_password
from app.models import AuditLog, Setting, User
from app.services.auth import Actor, audit, revoke_actor_sessions

router = APIRouter(prefix="/api/admin", tags=["management"])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class CreateSecretary(StrictBody):
    username: str = Field(min_length=1, max_length=100)
    full_name: str = Field(min_length=1, max_length=200)
    password: SecretStr

    @field_validator("username", "full_name")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class UpdateSecretary(StrictBody):
    username: str | None = Field(default=None, min_length=1, max_length=100)
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    new_password: SecretStr | None = None

    @field_validator("username", "full_name")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SettingsPatch(StrictBody):
    organization_name: str | None = Field(default=None, max_length=200)
    card_number: str | None = Field(default=None, max_length=32)
    account_holder: str | None = Field(default=None, max_length=200)
    telegram_support_id: str | None = Field(default=None, max_length=200)
    telegram_support_link: str | None = Field(default=None, max_length=500)
    bale_support_id: str | None = Field(default=None, max_length=200)
    bale_support_link: str | None = Field(default=None, max_length=500)
    support_phone: str | None = Field(default=None, max_length=32)
    default_debt_ceiling: int | None = Field(default=None, ge=0)
    event_display_settings: dict | None = None


def user_view(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("/users")
def list_users(
    _: Actor = Depends(require_super_admin), session: Session = Depends(get_db)
) -> list[dict]:
    return [user_view(user) for user in session.scalars(select(User).order_by(User.id))]


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    _: Actor = Depends(require_super_admin),
    session: Session = Depends(get_db),
) -> dict:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found")
    return user_view(user)


@router.post(
    "/users", status_code=201,
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def create_secretary(
    body: CreateSecretary,
    actor: Actor = Depends(require_super_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    password = body.password.get_secret_value()
    if len(password) < 12:
        raise HTTPException(status_code=422, detail="password_too_short")
    digest = hash_password(password, settings)
    try:
        with session.begin():
            user = User(
                username=body.username, full_name=body.full_name,
                password_hash=digest, role="secretary",
            )
            session.add(user)
            session.flush()
            audit(session, "user.created", "user", user.id, actor_type="user", actor_id=actor.id)
            result = user_view(user)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="username_exists") from None
    return result


@router.patch(
    "/users/{user_id}",
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def update_secretary(
    user_id: int,
    body: UpdateSecretary,
    actor: Actor = Depends(require_super_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="invalid_update")
    new_password = changes.pop("new_password", None)
    if new_password is not None and len(new_password.get_secret_value()) < 12:
        raise HTTPException(status_code=422, detail="password_too_short")
    digest = hash_password(new_password.get_secret_value(), settings) if new_password else None
    try:
        with session.begin():
            user = session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise HTTPException(status_code=404, detail="user_not_found")
            if user.role != "secretary":
                raise HTTPException(status_code=403, detail="cannot_modify_super_admin")
            for key, value in changes.items():
                setattr(user, key, value)
            if digest is not None:
                user.password_hash = digest
            if changes.get("is_active") is False or digest is not None:
                revoke_actor_sessions(session, actor_type="user", actor_id=user.id)
            audit(session, "user.updated", "user", user.id, actor_type="user", actor_id=actor.id)
            session.flush()
            result = user_view(user)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="username_exists") from None
    return result


@router.get("/settings")
def get_settings_values(
    _: Actor = Depends(require_super_admin), session: Session = Depends(get_db)
) -> dict:
    return {record.key: record.value for record in session.scalars(select(Setting))}


@router.patch(
    "/settings", dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def update_settings_values(
    body: SettingsPatch,
    actor: Actor = Depends(require_super_admin),
    session: Session = Depends(get_db),
) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="invalid_settings")
    with session.begin():
        for key, value in changes.items():
            record = session.get(Setting, key)
            if record is None:
                session.add(Setting(key=key, value=value))
            else:
                record.value = value
            session.add(AuditLog(
                actor_type="user", actor_id=actor.id, action="setting.updated",
                entity_type="setting", entity_id=0, metadata_json={"key": key},
            ))
    return changes
