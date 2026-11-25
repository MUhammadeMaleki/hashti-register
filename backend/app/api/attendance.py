"""Administrative attendance table and guarded transitions."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    require_active_admin,
    require_browser_origin,
    require_csrf,
    require_event_secretary,
)
from app.models import EventSecretary, Guest, PaymentSubmission, Registration, Wallet
from app.services.attendance import change_attendance
from app.services.auth import Actor
from app.services.finance import FinanceError, registration_finance

router = APIRouter(prefix="/api/admin", tags=["attendance"])


class AttendanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    attendance: Literal["pending", "present", "absent_kept", "absent_forfeited"]


@router.get("/events/{event_id}/registrations")
def list_event_registrations(
    event_id: int, limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: Actor = Depends(require_event_secretary), session: Session = Depends(get_db),
) -> dict:
    total = session.scalar(select(func.count()).select_from(Registration).where(
        Registration.event_id == event_id)) or 0
    rows = session.execute(select(Registration, Guest, Wallet).join(
        Guest, Guest.id == Registration.guest_id
    ).join(Wallet, Wallet.guest_id == Guest.id).where(
        Registration.event_id == event_id
    ).order_by(Registration.id).limit(limit).offset(offset)).all()
    guest_ids = [guest.id for _, guest, _ in rows]
    payments_by_guest: dict[int, list[dict]] = {guest_id: [] for guest_id in guest_ids}
    if guest_ids:
        payments = session.scalars(select(PaymentSubmission).where(
            PaymentSubmission.event_id == event_id,
            PaymentSubmission.guest_id.in_(guest_ids),
        ).order_by(PaymentSubmission.id.desc())).all()
        for payment in payments:
            payments_by_guest[payment.guest_id].append({
                "id": payment.id, "amount": payment.amount, "status": payment.status,
                "created_at": payment.created_at.isoformat(),
            })
    items = []
    for registration, guest, wallet in rows:
        state = registration_finance(session, registration.id)
        items.append({"id": registration.id, "guest_id": guest.id,
                      "first_name": guest.first_name, "last_name": guest.last_name,
                      "phone": guest.phone, "status": registration.status,
                      "attendance": registration.attendance,
                      "active_charge_total": state.active_charges,
                      "active_settlements": state.active_settlements,
                      "active_discounts": state.active_discounts,
                      "debt": state.debt, "wallet_balance": wallet.balance,
                      "event_payments": payments_by_guest[guest.id]})
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/registrations/{registration_id}/attendance",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def set_attendance(
    registration_id: int, body: AttendanceBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    event_id = session.scalar(select(Registration.event_id).where(
        Registration.id == registration_id))
    if event_id is None:
        raise HTTPException(status_code=404, detail="registration_not_found")
    if actor.role != "super_admin" and session.scalar(select(EventSecretary.user_id).where(
        EventSecretary.event_id == event_id, EventSecretary.user_id == actor.id
    )) is None:
        raise HTTPException(status_code=403, detail="forbidden")
    session.rollback()
    try:
        return change_attendance(session, registration_id=registration_id,
                                 target=body.attendance, actor=actor,
                                 key=idempotency_key).body
    except FinanceError as error:
        raise HTTPException(status_code=error.status, detail=error.code) from None
