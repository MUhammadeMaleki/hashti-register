"""Atomic order mutations and event-wide entry-fee changes."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Event, EventCharge, EventSecretary, Registration, Wallet
from app.services.auth import Actor
from app.services.finance import (
    EffectResult,
    FinanceError,
    lock_registration_wallet,
    refund_excess,
    registration_finance,
    run_idempotent,
)


def _authorized(session: Session, event_id: int, actor: Actor) -> None:
    if actor.role != "super_admin" and session.scalar(select(EventSecretary.user_id).where(
        EventSecretary.event_id == event_id, EventSecretary.user_id == actor.id
    )) is None:
        raise FinanceError("forbidden", 403)


def change_order(
    session: Session, *, registration_id: int, charge_id: int | None,
    description: str | None, amount: int | None, cancel: bool, actor: Actor, key: str,
) -> EffectResult:
    operation = "order.cancel" if cancel else ("order.update" if charge_id else "order.create")
    payload = {"registration_id": registration_id, "charge_id": charge_id,
               "description": description, "amount": amount, "cancel": cancel}

    def effect(current: Session) -> EffectResult:
        event, registration, wallet = lock_registration_wallet(current, registration_id)
        _authorized(current, event.id, actor)
        if event.is_cancelled:
            raise FinanceError("event_cancelled")
        if registration.status != "active":
            raise FinanceError("registration_cancelled")
        if charge_id is None and registration.attendance in {"pending", "absent_kept"}:
            raise FinanceError("order_attendance_not_allowed")
        charge = None
        if charge_id is not None:
            charge = current.scalar(select(EventCharge).where(
                EventCharge.id == charge_id,
                EventCharge.registration_id == registration_id,
            ).with_for_update())
            if charge is None or charge.type != "order":
                raise FinanceError("order_not_found", 404)
            if charge.is_cancelled:
                raise FinanceError("order_cancelled")
        before = None if charge is None else {"description": charge.description,
                                              "amount": charge.amount, "is_cancelled": False}
        if cancel:
            charge.is_cancelled = True
            charge.cancelled_at = datetime.now(UTC)
            charge.cancel_reason = "order_cancelled"
        elif charge is None:
            charge = EventCharge(registration_id=registration_id, type="order",
                                 description=description, amount=amount, created_by=actor.id)
            current.add(charge)
        else:
            charge.description = description
            charge.amount = amount
        current.flush()
        refunds = refund_excess(current, registration_id=registration_id, wallet=wallet,
                                actor_id=actor.id, key=key, reason=operation)
        state = registration_finance(current, registration_id)
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action=operation,
            entity_type="event_charge", entity_id=charge.id,
            before_json=before,
            after_json={"description": charge.description, "amount": charge.amount,
                        "is_cancelled": charge.is_cancelled, "debt": state.debt},
            metadata_json={"idempotency_key": key, "registration_id": registration_id,
                           "refunds": refunds},
        ))
        return EffectResult(200, {"id": charge.id, "registration_id": registration_id,
                                  "description": charge.description, "amount": charge.amount,
                                  "is_cancelled": charge.is_cancelled, "refunds": refunds,
                                  "debt": state.debt, "wallet_balance": wallet.balance},
                            "event_charge", charge.id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation=operation, key=key, payload=payload, effect=effect)


def change_entry_fee(
    session: Session, *, event_id: int, amount: int, actor: Actor, key: str,
) -> EffectResult:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise FinanceError("invalid_amount", 422)

    def effect(current: Session) -> EffectResult:
        event = current.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if event is None:
            raise FinanceError("event_not_found", 404)
        _authorized(current, event_id, actor)
        if event.is_cancelled:
            raise FinanceError("event_cancelled")
        old = event.entry_fee
        if old == amount:
            return EffectResult(200, {"event_id": event_id, "entry_fee": amount,
                                      "changed": False, "registrations": 0, "refunds": 0},
                                "event", event_id)
        registrations = current.scalars(select(Registration).where(
            Registration.event_id == event_id, Registration.status == "active",
            Registration.attendance.in_(["present", "absent_forfeited"]),
        ).order_by(Registration.id).with_for_update()).all()
        wallets = current.scalars(select(Wallet).where(
            Wallet.guest_id.in_([row.guest_id for row in registrations])
        ).order_by(Wallet.id).with_for_update()).all() if registrations else []
        by_guest = {wallet.guest_id: wallet for wallet in wallets}
        created, cancelled, updated, refund_total = [], [], [], 0
        for registration in registrations:
            entries = current.scalars(select(EventCharge).where(
                EventCharge.registration_id == registration.id,
                EventCharge.type == "entry", EventCharge.is_cancelled.is_(False),
            ).order_by(EventCharge.id).with_for_update()).all()
            if len(entries) > 1:
                raise FinanceError("finance_invariant_broken")
            entry = entries[0] if entries else None
            if amount == 0 and entry:
                entry.is_cancelled = True
                entry.cancelled_at = datetime.now(UTC)
                entry.cancel_reason = "entry_fee_zero"
                cancelled.append(entry.id)
            elif amount > 0 and entry:
                entry.amount = amount
                updated.append(entry.id)
            elif amount > 0:
                entry = EventCharge(registration_id=registration.id, type="entry",
                                    description="ورودی رویداد", amount=amount,
                                    created_by=actor.id)
                current.add(entry)
                current.flush()
                created.append(entry.id)
            current.flush()
            refunds = refund_excess(current, registration_id=registration.id,
                                    wallet=by_guest[registration.guest_id], actor_id=actor.id,
                                    key=key, reason="entry_fee.change")
            refund_total += sum(row["amount"] for row in refunds)
            registration_finance(current, registration.id)
        event.entry_fee = amount
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action="event.entry_fee_changed",
            entity_type="event", entity_id=event_id,
            before_json={"entry_fee": old}, after_json={"entry_fee": amount},
            metadata_json={"idempotency_key": key, "created_charge_ids": created,
                           "cancelled_charge_ids": cancelled, "updated_charge_ids": updated,
                           "refunded_total": refund_total},
        ))
        return EffectResult(200, {"event_id": event_id, "entry_fee": amount,
                                  "changed": True, "registrations": len(registrations),
                                  "refunds": refund_total}, "event", event_id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation="event.entry_fee.change", key=key,
                          payload={"event_id": event_id, "amount": amount}, effect=effect)
