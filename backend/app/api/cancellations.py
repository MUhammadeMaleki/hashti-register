"""Administrative event and registration cancellation endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    require_active_admin,
    require_browser_origin,
    require_csrf,
    require_event_secretary,
)
from app.models import EventSecretary, Registration
from app.services.auth import Actor
from app.services.cancellations import (
    cancel_registration,
    change_event_cancellation,
    reactivate_registration,
)
from app.services.finance import FinanceError

router = APIRouter(prefix="/api/admin", tags=["cancellations"])


def _run(session: Session, call) -> dict:
    session.rollback()
    try:
        return call().body
    except FinanceError as error:
        raise HTTPException(status_code=error.status, detail=error.code) from None


def _registration_access(session: Session, registration_id: int, actor: Actor) -> None:
    event_id = session.scalar(select(Registration.event_id).where(
        Registration.id == registration_id))
    if event_id is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    if actor.role != "super_admin" and session.scalar(select(EventSecretary.user_id).where(
        EventSecretary.event_id == event_id, EventSecretary.user_id == actor.id,
    )) is None:
        raise HTTPException(status_code=403, detail="forbidden")


@router.post("/events/{event_id}/cancel",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def cancel_event(
    event_id: int, key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_event_secretary), session: Session = Depends(get_db),
) -> dict:
    return _run(session, lambda: change_event_cancellation(
        session, event_id=event_id, reactivate=False, actor=actor, key=key))


@router.post("/events/{event_id}/reactivate",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def reactivate_event(
    event_id: int, key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_event_secretary), session: Session = Depends(get_db),
) -> dict:
    return _run(session, lambda: change_event_cancellation(
        session, event_id=event_id, reactivate=True, actor=actor, key=key))


@router.post("/registrations/{registration_id}/cancel",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def cancel_registration_route(
    registration_id: int, key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _registration_access(session, registration_id, actor)
    return _run(session, lambda: cancel_registration(
        session, registration_id=registration_id, actor=actor, key=key))


@router.post("/registrations/{registration_id}/reactivate",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def reactivate_registration_route(
    registration_id: int, key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _registration_access(session, registration_id, actor)
    return _run(session, lambda: reactivate_registration(
        session, registration_id=registration_id, actor=actor, key=key))
