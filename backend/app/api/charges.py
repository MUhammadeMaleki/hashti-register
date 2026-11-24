"""Administrative orders and event-wide entry-fee mutation."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_active_admin, require_browser_origin, require_csrf
from app.models import Event, EventCharge, EventSecretary, Registration
from app.services.auth import Actor
from app.services.charges import change_entry_fee, change_order
from app.services.finance import FinanceError

router = APIRouter(prefix="/api/admin", tags=["charges"])


class OrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    description: str = Field(min_length=1)
    amount: int = Field(gt=0)

    @field_validator("description")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class FeeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    amount: int = Field(ge=0)


def _authorize(session: Session, event_id: int, actor: Actor) -> None:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    if actor.role != "super_admin" and session.scalar(select(EventSecretary.user_id).where(
        EventSecretary.event_id == event_id, EventSecretary.user_id == actor.id
    )) is None:
        raise HTTPException(status_code=403, detail="forbidden")


def _registration_event(session: Session, registration_id: int, actor: Actor) -> None:
    event_id = session.scalar(select(Registration.event_id).where(
        Registration.id == registration_id))
    if event_id is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    _authorize(session, event_id, actor)


def _run(session: Session, call):
    session.rollback()
    try:
        return call().body
    except FinanceError as error:
        raise HTTPException(status_code=error.status, detail=error.code) from None


@router.get("/registrations/{registration_id}/charges")
def list_charges(
    registration_id: int, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> list[dict]:
    _registration_event(session, registration_id, actor)
    rows = session.scalars(select(EventCharge).where(
        EventCharge.registration_id == registration_id
    ).order_by(EventCharge.id)).all()
    return [{"id": row.id, "type": row.type, "description": row.description,
             "amount": row.amount, "is_cancelled": row.is_cancelled} for row in rows]


@router.post("/registrations/{registration_id}/orders",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def create_order(
    registration_id: int, body: OrderBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _registration_event(session, registration_id, actor)
    return _run(session, lambda: change_order(
        session, registration_id=registration_id, charge_id=None,
        description=body.description, amount=body.amount, cancel=False,
        actor=actor, key=idempotency_key))


@router.patch("/registrations/{registration_id}/orders/{charge_id}",
              dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def update_order(
    registration_id: int, charge_id: int, body: OrderBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _registration_event(session, registration_id, actor)
    return _run(session, lambda: change_order(
        session, registration_id=registration_id, charge_id=charge_id,
        description=body.description, amount=body.amount, cancel=False,
        actor=actor, key=idempotency_key))


@router.delete("/registrations/{registration_id}/orders/{charge_id}",
               dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def cancel_order(
    registration_id: int, charge_id: int,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _registration_event(session, registration_id, actor)
    return _run(session, lambda: change_order(
        session, registration_id=registration_id, charge_id=charge_id,
        description=None, amount=None, cancel=True,
        actor=actor, key=idempotency_key))


@router.patch("/events/{event_id}/entry-fee",
              dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def update_entry_fee(
    event_id: int, body: FeeBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _authorize(session, event_id, actor)
    return _run(session, lambda: change_entry_fee(
        session, event_id=event_id, amount=body.amount, actor=actor,
        key=idempotency_key))
