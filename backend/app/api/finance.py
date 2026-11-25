"""Read-only reconciliation of cached wallet balances against the ledger."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_db,
    require_active_admin,
    require_active_guest,
    require_browser_origin,
    require_csrf,
    require_super_admin,
)
from app.models import Event, Guest, GuestAccount, Location, Registration, Wallet, WalletTransaction
from app.services.auth import Actor
from app.services.finance import FinanceError, active_settlement, registration_finance
from app.services.settlements import (
    adjust_wallet,
    authorize_registration,
    refund_settlement,
    settle_registration,
)

router = APIRouter(prefix="/api/admin/finance", tags=["finance"])
guest_router = APIRouter(prefix="/api/me", tags=["finance"])


class AmountBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    amount: int = Field(gt=0)


class AdminSettlementBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    amount: int = Field(ge=0)
    discount_amount: int = Field(default=0, ge=0)
    discount_reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def valid_combination(self):
        self.discount_reason = self.discount_reason.strip()
        if self.amount + self.discount_amount <= 0:
            raise ValueError("payment or discount is required")
        if self.discount_amount > 0 and not self.discount_reason:
            raise ValueError("discount reason is required")
        return self


class RefundBody(AmountBody):
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class AdjustmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    amount: int
    note: str = Field(min_length=1)

    @field_validator("note")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


def _result(session: Session, action):
    session.rollback()
    try:
        return action().body
    except FinanceError as error:
        raise HTTPException(status_code=error.status, detail=error.code) from None


def _authorize(session: Session, registration_id: int, actor: Actor) -> None:
    try:
        authorize_registration(session, registration_id, actor)
    except FinanceError as error:
        raise HTTPException(status_code=error.status, detail=error.code) from None


@router.post("/registrations/{registration_id}/settlements",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def admin_settle(
    registration_id: int, body: AdminSettlementBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    _authorize(session, registration_id, actor)
    return _result(session, lambda: settle_registration(
        session, registration_id=registration_id, amount=body.amount,
        actor=actor, key=idempotency_key, discount_amount=body.discount_amount,
        discount_reason=body.discount_reason))


@router.get("/registrations/{registration_id}/settlements")
def list_settlements(
    registration_id: int, actor: Actor = Depends(require_active_admin),
    session: Session = Depends(get_db),
) -> list[dict]:
    _authorize(session, registration_id, actor)
    rows = session.scalars(select(WalletTransaction).where(
        WalletTransaction.registration_id == registration_id,
        WalletTransaction.type == "settlement",
    ).order_by(WalletTransaction.id)).all()
    return [{"id": row.id, "amount": -row.amount,
             "active_amount": active_settlement(session, row.id),
             "created_at": row.created_at} for row in rows]


@router.post("/settlements/{settlement_id}/refunds",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def admin_refund(
    settlement_id: int, body: RefundBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    registration_id = session.scalar(select(WalletTransaction.registration_id).where(
        WalletTransaction.id == settlement_id,
        WalletTransaction.type == "settlement"))
    if registration_id is None:
        raise HTTPException(status_code=404, detail="settlement_not_found")
    _authorize(session, registration_id, actor)
    return _result(session, lambda: refund_settlement(
        session, settlement_id=settlement_id, amount=body.amount,
        reason=body.reason, actor=actor, key=idempotency_key))


@router.post("/guests/{guest_id}/adjustments",
             dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def admin_adjust(
    guest_id: int, body: AdjustmentBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_admin), session: Session = Depends(get_db),
) -> dict:
    return _result(session, lambda: adjust_wallet(
        session, guest_id=guest_id, amount=body.amount, note=body.note,
        actor=actor, key=idempotency_key))


def _guest_id(session: Session, actor: Actor) -> int:
    return session.get(GuestAccount, actor.id).guest_id


def _my_registrations(session: Session, guest_id: int) -> list[dict]:
    rows = session.execute(select(Registration, Event, Location.title).join(
        Event, Event.id == Registration.event_id
    ).outerjoin(
        Location, Location.id == Event.location_id
    ).where(Registration.guest_id == guest_id,
            Registration.status == "active").order_by(Registration.id.desc())).all()
    registrations = []
    for registration, event, location_title in rows:
        state = registration_finance(session, registration.id)
        registrations.append({"id": registration.id, "event_id": event.id,
                              "event_number": event.event_number, "title": event.title,
                              "poster_url": (f"/api/public/events/{event.id}/poster"
                                             if event.poster_path else None),
                              "event_date": event.event_date, "start_time": event.start_time,
                              "time_mode": event.time_mode, "time_text": event.time_text,
                              "location_mode": event.location_mode,
                              "location_text": event.location_text,
                              "location_title": (location_title if event.location_mode == "exact"
                                                 else None),
                              "entry_fee": event.entry_fee,
                              "attendance": registration.attendance,
                              "is_cancelled": event.is_cancelled,
                              "active_charges": state.active_charges,
                              "active_settlements": state.active_settlements,
                              "active_discounts": state.active_discounts,
                              "debt": state.debt})
    return registrations


@guest_router.get("/profile")
def my_profile(
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> dict:
    guest = session.get(Guest, _guest_id(session, actor))
    return {"id": guest.id, "first_name": guest.first_name,
            "last_name": guest.last_name, "phone": guest.phone,
            "age": guest.age, "gender": guest.gender, "education": guest.education}


@guest_router.get("/registrations")
def my_registrations(
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> list[dict]:
    return _my_registrations(session, _guest_id(session, actor))


@guest_router.get("/wallet")
def my_wallet(
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> dict:
    guest_id = _guest_id(session, actor)
    wallet = session.scalar(select(Wallet).where(Wallet.guest_id == guest_id))
    registrations = _my_registrations(session, guest_id)
    return {"balance": wallet.balance,
            "event_debts": [{"registration_id": row["id"], "event_id": row["event_id"],
                             "event_number": row["event_number"], "title": row["title"],
                             "debt": row["debt"]} for row in registrations]}


@guest_router.get("/wallet/transactions")
def my_transactions(
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> list[dict]:
    wallet = session.scalar(select(Wallet).where(Wallet.guest_id == _guest_id(session, actor)))
    rows = session.scalars(select(WalletTransaction).where(
        WalletTransaction.wallet_id == wallet.id
    ).order_by(WalletTransaction.id.desc())).all()
    return [{"id": row.id, "type": row.type, "amount": row.amount,
             "registration_id": row.registration_id, "note": row.note,
             "created_at": row.created_at} for row in rows]


@guest_router.get("/finance")
def my_finance(
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> dict:
    account = session.get(GuestAccount, actor.id)
    wallet = session.scalar(select(Wallet).where(Wallet.guest_id == account.guest_id))
    registrations = _my_registrations(session, account.guest_id)
    transactions = session.scalars(select(WalletTransaction).where(
        WalletTransaction.wallet_id == wallet.id
    ).order_by(WalletTransaction.id.desc()).limit(50)).all()
    return {"wallet_balance": wallet.balance, "registrations": registrations,
            "transactions": [{"id": row.id, "type": row.type, "amount": row.amount,
                              "registration_id": row.registration_id,
                              "note": row.note, "created_at": row.created_at}
                             for row in transactions]}


@guest_router.post("/registrations/{registration_id}/settlements",
                   dependencies=[Depends(require_browser_origin), Depends(require_csrf)])
def guest_settle(
    registration_id: int, body: AmountBody,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    actor: Actor = Depends(require_active_guest), session: Session = Depends(get_db),
) -> dict:
    _authorize(session, registration_id, actor)
    return _result(session, lambda: settle_registration(
        session, registration_id=registration_id, amount=body.amount,
        actor=actor, key=idempotency_key))


@router.get("/reconciliation")
def reconcile_wallets(
    guest_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: Actor = Depends(require_super_admin), session: Session = Depends(get_db),
) -> dict:
    totals = select(
        WalletTransaction.wallet_id.label("wallet_id"),
        func.sum(WalletTransaction.amount).label("ledger_balance"),
    ).group_by(WalletTransaction.wallet_id).subquery()
    filters = [Wallet.guest_id == guest_id] if guest_id is not None else []
    total = session.scalar(select(func.count()).select_from(Wallet).where(*filters)) or 0
    rows = session.execute(select(
        Wallet.id, Wallet.guest_id, Wallet.balance, Guest.first_name, Guest.last_name,
        func.coalesce(totals.c.ledger_balance, 0),
    ).join(Guest, Guest.id == Wallet.guest_id).outerjoin(
        totals, totals.c.wallet_id == Wallet.id,
    ).where(*filters).order_by(Wallet.id).limit(limit).offset(offset)).all()
    items = [{"wallet_id": wallet_id, "guest_id": owner_id,
              "guest_name": f"{first_name} {last_name}",
              "cached_balance": cached, "ledger_balance": int(ledger),
              "difference": cached - int(ledger), "matches": cached == ledger}
             for wallet_id, owner_id, cached, first_name, last_name, ledger in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "mismatch_count_on_page": sum(not item["matches"] for item in items)}
