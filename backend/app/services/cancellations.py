"""Atomic cancellation and explicit reactivation of events and registrations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Event,
    EventCharge,
    EventSecretary,
    Registration,
    Wallet,
    WalletTransaction,
)
from app.services.auth import Actor
from app.services.finance import (
    EffectResult,
    FinanceError,
    lock_registration_wallet,
    refund_excess,
    registration_finance,
    run_idempotent,
)


def _authorize(session: Session, event_id: int, actor: Actor) -> None:
    if actor.type != "user" or (actor.role != "super_admin" and session.scalar(
        select(EventSecretary.user_id).where(
            EventSecretary.event_id == event_id, EventSecretary.user_id == actor.id,
        )
    ) is None):
        raise FinanceError("forbidden", 403)


def _cancel_locked_registration(
    session: Session, registration: Registration, *, actor: Actor, key: str, reason: str,
) -> dict:
    wallet = session.scalar(select(Wallet).where(
        Wallet.guest_id == registration.guest_id).with_for_update())
    if wallet is None:
        raise FinanceError("wallet_not_found", 404)
    before = registration_finance(session, registration.id)
    charges = session.scalars(select(EventCharge).where(
        EventCharge.registration_id == registration.id,
        EventCharge.is_cancelled.is_(False),
    ).order_by(EventCharge.id).with_for_update()).all()
    cancelled_ids = [charge.id for charge in charges]
    now = datetime.now(UTC)
    for charge in charges:
        charge.is_cancelled = True
        charge.cancelled_at = now
        charge.cancel_reason = reason
    session.flush()
    settlements = session.scalars(select(WalletTransaction.id).where(
        WalletTransaction.registration_id == registration.id,
        WalletTransaction.type == "settlement",
    ).order_by(WalletTransaction.id)).all()
    refunds = refund_excess(session, registration_id=registration.id, wallet=wallet,
                            actor_id=actor.id, key=key, reason=reason)
    registration.status = "cancelled"
    session.flush()
    after = registration_finance(session, registration.id)
    if after.active_charges or after.active_settlements or after.debt:
        raise FinanceError("finance_invariant_broken")
    refunded_total = sum(item["amount"] for item in refunds)
    session.add(AuditLog(
        actor_type="user", actor_id=actor.id, action="registration.cancelled",
        entity_type="registration", entity_id=registration.id,
        before_json={"status": "active", "attendance": registration.attendance,
                     "active_charge_total": before.active_charges,
                     "active_settlements": before.active_settlements, "debt": before.debt},
        after_json={"status": "cancelled", "attendance": registration.attendance,
                    "active_charge_total": 0, "active_settlements": 0, "debt": 0},
        metadata_json={"idempotency_key": key, "reason": reason,
                       "event_id": registration.event_id, "created_charge_ids": [],
                       "cancelled_charge_ids": cancelled_ids,
                       "settlement_ids": settlements, "refunds": refunds,
                       "refunded_total": refunded_total},
    ))
    return {"registration_id": registration.id, "status": "cancelled",
            "attendance": registration.attendance, "changed": True,
            "cancelled_charge_ids": cancelled_ids, "refunds": refunds,
            "refunded_total": refunded_total, "debt": 0,
            "wallet_balance": wallet.balance}


def cancel_registration(
    session: Session, *, registration_id: int, actor: Actor, key: str,
) -> EffectResult:
    def effect(current: Session) -> EffectResult:
        event, registration, wallet = lock_registration_wallet(current, registration_id)
        _authorize(current, event.id, actor)
        if event.is_cancelled:
            raise FinanceError("event_cancelled")
        if registration.status == "cancelled":
            return EffectResult(200, {"registration_id": registration.id,
                                      "status": "cancelled", "changed": False,
                                      "wallet_balance": wallet.balance},
                                "registration", registration.id)
        body = _cancel_locked_registration(current, registration, actor=actor,
                                           key=key, reason="registration_cancelled")
        return EffectResult(200, body, "registration", registration.id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation="registration.cancel", key=key,
                          payload={"registration_id": registration_id}, effect=effect)


def reactivate_registration(
    session: Session, *, registration_id: int, actor: Actor, key: str,
) -> EffectResult:
    def effect(current: Session) -> EffectResult:
        event, registration, wallet = lock_registration_wallet(current, registration_id)
        _authorize(current, event.id, actor)
        if event.is_cancelled:
            raise FinanceError("event_cancelled")
        if event.registration_status != "open":
            raise FinanceError("registration_closed")
        if registration.status != "cancelled":
            raise FinanceError("registration_not_cancelled")
        previous_attendance = registration.attendance
        before = registration_finance(current, registration.id)
        if before.active_charges or before.active_settlements:
            raise FinanceError("finance_invariant_broken")
        registration.status = "active"
        registration.attendance = "pending"
        current.flush()
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action="registration.reactivated",
            entity_type="registration", entity_id=registration.id,
            before_json={"status": "cancelled", "attendance": previous_attendance,
                         "active_charge_total": 0, "active_settlements": 0},
            after_json={"status": "active", "attendance": "pending",
                        "active_charge_total": 0, "active_settlements": 0},
            metadata_json={"idempotency_key": key, "event_id": event.id,
                           "created_charge_ids": [], "cancelled_charge_ids": [],
                           "settlement_ids": [], "refunds": [], "refunded_total": 0},
        ))
        return EffectResult(200, {"registration_id": registration.id,
                                  "status": "active", "attendance": "pending",
                                  "changed": True, "debt": 0,
                                  "wallet_balance": wallet.balance},
                            "registration", registration.id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation="registration.reactivate", key=key,
                          payload={"registration_id": registration_id}, effect=effect)


def change_event_cancellation(
    session: Session, *, event_id: int, reactivate: bool, actor: Actor, key: str,
) -> EffectResult:
    operation = "event.reactivate" if reactivate else "event.cancel"

    def effect(current: Session) -> EffectResult:
        event = current.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if event is None:
            raise FinanceError("event_not_found", 404)
        _authorize(current, event_id, actor)
        if event.is_cancelled == (not reactivate):
            return EffectResult(200, {"event_id": event_id,
                                      "is_cancelled": event.is_cancelled,
                                      "registration_status": event.registration_status,
                                      "changed": False, "registrations": 0,
                                      "refunded_total": 0}, "event", event_id)
        if reactivate:
            event.is_cancelled = False
            current.add(AuditLog(
                actor_type="user", actor_id=actor.id, action="event.reactivated",
                entity_type="event", entity_id=event_id,
                before_json={"is_cancelled": True},
                after_json={"is_cancelled": False,
                            "registration_status": event.registration_status},
                metadata_json={"idempotency_key": key, "registrations": 0,
                               "refunded_total": 0},
            ))
            count, refunded_total = 0, 0
        else:
            registrations = current.scalars(select(Registration).where(
                Registration.event_id == event_id, Registration.status == "active",
            ).order_by(Registration.id).with_for_update()).all()
            results = [_cancel_locked_registration(
                current, row, actor=actor, key=key, reason="event_cancelled",
            ) for row in registrations]
            count = len(results)
            refunded_total = sum(row["refunded_total"] for row in results)
            event.is_cancelled = True
            current.add(AuditLog(
                actor_type="user", actor_id=actor.id, action="event.cancelled",
                entity_type="event", entity_id=event_id,
                before_json={"is_cancelled": False,
                             "registration_status": event.registration_status},
                after_json={"is_cancelled": True,
                            "registration_status": event.registration_status},
                metadata_json={"idempotency_key": key, "registrations": count,
                               "refunded_total": refunded_total,
                               "registration_ids": [row["registration_id"] for row in results]},
            ))
        return EffectResult(200, {"event_id": event_id,
                                  "is_cancelled": event.is_cancelled,
                                  "registration_status": event.registration_status,
                                  "changed": True, "registrations": count,
                                  "refunded_total": refunded_total}, "event", event_id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation=operation, key=key, payload={"event_id": event_id},
                          effect=effect)
