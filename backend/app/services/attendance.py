"""Atomic attendance transitions and entry-charge/refund accounting."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, EventCharge, EventSecretary, WalletTransaction
from app.services.auth import Actor
from app.services.finance import (
    EffectResult,
    FinanceError,
    active_settlement,
    append_transaction,
    lock_registration_wallet,
    registration_finance,
    run_idempotent,
)

ATTENDANCE = {"pending", "present", "absent_kept", "absent_forfeited"}


def change_attendance(
    session: Session, *, registration_id: int, target: str, actor: Actor, key: str,
) -> EffectResult:
    if target not in ATTENDANCE:
        raise FinanceError("invalid_attendance", 422)

    def effect(current: Session) -> EffectResult:
        event, registration, wallet = lock_registration_wallet(current, registration_id)
        if actor.role != "super_admin" and current.scalar(select(EventSecretary.user_id).where(
            EventSecretary.event_id == event.id, EventSecretary.user_id == actor.id
        )) is None:
            raise FinanceError("forbidden", 403)
        if event.is_cancelled:
            raise FinanceError("event_cancelled")
        if registration.status != "active":
            raise FinanceError("registration_cancelled")
        before = registration.attendance
        if before == target:
            state = registration_finance(current, registration_id)
            return EffectResult(200, {"registration_id": registration_id,
                                      "attendance": target, "changed": False,
                                      "debt": state.debt, "wallet_balance": wallet.balance},
                                "registration", registration_id)
        if target == "pending":
            raise FinanceError("attendance_back_to_pending")
        charges = current.scalars(select(EventCharge).where(
            EventCharge.registration_id == registration_id
        ).order_by(EventCharge.id).with_for_update()).all()
        before_total = sum(charge.amount for charge in charges if not charge.is_cancelled)
        created_ids: list[int] = []
        cancelled_ids: list[int] = []
        now = datetime.now(UTC)
        if target == "absent_kept":
            to_cancel = [charge for charge in charges if not charge.is_cancelled]
        elif target == "absent_forfeited":
            to_cancel = [charge for charge in charges if not charge.is_cancelled
                         and charge.type == "order"]
        else:
            to_cancel = []
        for charge in to_cancel:
            charge.is_cancelled = True
            charge.cancelled_at = now
            charge.cancel_reason = "attendance_changed"
            cancelled_ids.append(charge.id)
        active_entry = any(charge.type == "entry" and not charge.is_cancelled
                           for charge in charges)
        if target in {"present", "absent_forfeited"} and event.entry_fee > 0 and not active_entry:
            entry = EventCharge(registration_id=registration_id, type="entry",
                                description="ورودی رویداد", amount=event.entry_fee,
                                created_by=actor.id)
            current.add(entry)
            current.flush()
            created_ids.append(entry.id)
        current.flush()
        after_total = current.scalar(select(func.coalesce(func.sum(EventCharge.amount), 0)).where(
            EventCharge.registration_id == registration_id,
            EventCharge.is_cancelled.is_(False))) or 0
        after_total = int(after_total)
        net_settled = -int(current.scalar(select(func.coalesce(
            func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.registration_id == registration_id,
                WalletTransaction.type.in_(["settlement", "refund"]))) or 0)
        refund_needed = max(0, net_settled - after_total)
        refunds: list[dict] = []
        if refund_needed:
            settlements = current.scalars(select(WalletTransaction).where(
                WalletTransaction.registration_id == registration_id,
                WalletTransaction.type == "settlement",
            ).order_by(WalletTransaction.id).with_for_update()).all()
            for settlement in reversed(settlements):
                available = active_settlement(current, settlement.id)
                amount = min(refund_needed, available)
                if amount == 0:
                    continue
                refund_key = "attendance:" + hashlib.sha256(
                    f"{key}:{settlement.id}".encode()).hexdigest()
                refund = append_transaction(
                    current, wallet=wallet, type="refund", amount=amount,
                    registration_id=registration_id, original_transaction_id=settlement.id,
                    actor_type="user", actor_id=actor.id, key=refund_key,
                    reason="attendance_changed",
                )
                refunds.append({"id": refund.id, "amount": amount,
                                "settlement_id": settlement.id})
                refund_needed -= amount
                if refund_needed == 0:
                    break
            if refund_needed:
                raise FinanceError("finance_invariant_broken")
        registration.attendance = target
        current.flush()
        state = registration_finance(current, registration_id)
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action="registration.attendance_changed",
            entity_type="registration", entity_id=registration_id,
            before_json={"status": registration.status, "attendance": before,
                         "active_charge_total": before_total},
            after_json={"status": registration.status, "attendance": target,
                        "active_charge_total": state.active_charges,
                        "active_settlements": state.active_settlements, "debt": state.debt},
            metadata_json={"idempotency_key": key, "created_charge_ids": created_ids,
                           "cancelled_charge_ids": cancelled_ids, "refunds": refunds,
                           "refunded_total": sum(item["amount"] for item in refunds)},
        ))
        return EffectResult(200, {"registration_id": registration_id,
                                  "attendance": target, "changed": True,
                                  "created_charge_ids": created_ids,
                                  "cancelled_charge_ids": cancelled_ids,
                                  "refunds": refunds, "debt": state.debt,
                                  "wallet_balance": wallet.balance},
                            "registration", registration_id)

    return run_idempotent(
        session, actor_type="user", actor_id=actor.id, operation="attendance.change",
        key=key, payload={"registration_id": registration_id, "target": target}, effect=effect,
    )
