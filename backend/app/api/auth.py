"""Same-origin cookie authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.api.dependencies import (
    current_actor,
    get_db,
    get_settings,
    require_active_admin,
    require_browser_origin,
    require_csrf,
)
from app.core.config import Settings
from app.core.security import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.services.auth import (
    Actor,
    AuthError,
    change_password,
    issue_guest_temp_password,
    login,
    register_guest,
    revoke_session,
    rotate_refresh,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/admin", tags=["admin-auth"])


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class AdminLogin(StrictBody):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr


class GuestLogin(StrictBody):
    phone: str = Field(min_length=10, max_length=32)
    password: SecretStr


class GuestRegister(GuestLogin):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)


class ChangePassword(StrictBody):
    new_password: SecretStr
    current_password: SecretStr | None = None


def auth_failure(error: AuthError) -> HTTPException:
    return HTTPException(status_code=error.status, detail=error.code)


@router.post("/guest/register", status_code=201, dependencies=[Depends(require_browser_origin)])
def guest_register(
    body: GuestRegister,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        guest_id, account_id = register_guest(
            session,
            first_name=body.first_name,
            last_name=body.last_name,
            phone=body.phone,
            password=body.password.get_secret_value(),
            settings=settings,
        )
    except (AuthError, ValueError) as error:
        if isinstance(error, AuthError):
            raise auth_failure(error) from None
        raise HTTPException(status_code=422, detail="invalid_registration") from None
    return {"guest_id": guest_id, "account_id": account_id}


@router.post("/admin/login", dependencies=[Depends(require_browser_origin)])
def admin_login(
    body: AdminLogin,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        tokens, _ = login(
            session,
            actor_type="user",
            identifier=body.username,
            password=body.password.get_secret_value(),
            settings=settings,
        )
    except AuthError as error:
        raise auth_failure(error) from None
    set_auth_cookies(response, tokens, settings)
    return {"actor_type": "user"}


@router.post("/guest/login", dependencies=[Depends(require_browser_origin)])
def guest_login(
    body: GuestLogin,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        tokens, must_change = login(
            session,
            actor_type="guest",
            identifier=body.phone,
            password=body.password.get_secret_value(),
            settings=settings,
        )
    except AuthError as error:
        raise auth_failure(error) from None
    set_auth_cookies(response, tokens, settings)
    return {"actor_type": "guest", "must_change_password": must_change}


@router.post(
    "/refresh", response_model=None,
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict | Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="invalid_session")
    try:
        tokens = rotate_refresh(session, token=token, settings=settings)
    except AuthError as error:
        rejected = JSONResponse(status_code=error.status, content={"detail": error.code})
        clear_auth_cookies(rejected, settings)
        return rejected
    set_auth_cookies(response, tokens, settings)
    return {"status": "ok"}


@router.post("/logout", dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    revoke_session(session, token=request.cookies.get(REFRESH_COOKIE))
    clear_auth_cookies(response, settings)
    return {"status": "ok"}


@router.get("/session")
def session_info(actor: Actor = Depends(current_actor)) -> dict:
    return {
        "actor_type": actor.type,
        "actor_id": actor.id,
        "role": actor.role,
        "must_change_password": actor.must_change_password,
    }


@router.post(
    "/guest/change-password", dependencies=[Depends(require_browser_origin), Depends(require_csrf)]
)
def guest_change_password(
    body: ChangePassword,
    response: Response,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if actor.type != "guest":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        change_password(
            session,
            actor=actor,
            new_password=body.new_password.get_secret_value(),
            current_password=None,
            settings=settings,
        )
    except AuthError as error:
        raise auth_failure(error) from None
    clear_auth_cookies(response, settings)
    return {"status": "password_changed"}


@router.post(
    "/admin/change-password", dependencies=[Depends(require_browser_origin), Depends(require_csrf)]
)
def admin_change_password(
    body: ChangePassword,
    response: Response,
    actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        change_password(
            session,
            actor=actor,
            new_password=body.new_password.get_secret_value(),
            current_password=body.current_password.get_secret_value()
            if body.current_password
            else None,
            settings=settings,
        )
    except AuthError as error:
        raise auth_failure(error) from None
    clear_auth_cookies(response, settings)
    return {"status": "password_changed"}


@admin_router.post(
    "/guests/{guest_id}/temp-password",
    dependencies=[Depends(require_browser_origin), Depends(require_csrf)],
)
def create_temp_password(
    guest_id: int,
    response: Response,
    actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        password = issue_guest_temp_password(
            session, guest_id=guest_id, issued_by=actor, settings=settings
        )
    except AuthError as error:
        raise auth_failure(error) from None
    response.headers["Cache-Control"] = "no-store"
    return {"temporary_password": password, "expires_in_hours": 24}
