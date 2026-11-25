"""Explicit wallet settlement, linked refunds and manual adjustments."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    EventDiscount,
    EventSecretary,
    GuestAccount,
    Registration,
    Wallet,
    WalletTransaction,
)
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


def _ledger_key(operation: str, actor: Actor, key: str) -> str:
    return operation + ":" + hashlib.sha256(
        f"{actor.type}:{actor.id}:{key}".encode()).hexdigest()


def authorize_registration(session: Session, registration_id: int, actor: Actor) -> int:
    registration = session.get(Registration, registration_id)
    if registration is None:
        raise FinanceError("registration_not_found", 404)
    if actor.type == "guest":
        account = session.get(GuestAccount, actor.id)
        if account is None or account.guest_id != registration.guest_id:
            raise FinanceError("registration_not_found", 404)
    elif actor.role != "super_admin" and session.scalar(select(EventSecretary.user_id).where(
        EventSecretary.event_id == registration.event_id,
        EventSecretary.user_id == actor.id,
    )) is None:
        raise FinanceError("forbidden", 403)
    return registration.event_id


def settlement_operations(session: Session, registration_id: int) -> list[dict]:
    """Project each recorded settlement attempt, including discount-only operations."""
    logs = session.scalars(select(AuditLog).where(
        AuditLog.entity_type == "registration", AuditLog.entity_id == registration_id,
        AuditLog.action == "registration.settled",
    ).order_by(AuditLog.id.desc())).all()
    result = []
    for log in logs:
        metadata = log.metadata_json or {}
        transaction_id = metadata.get("transaction_id")
        discount_id = metadata.get("discount_id")
        transaction = session.get(WalletTransaction, transaction_id) if transaction_id else None
        discount = session.get(EventDiscount, discount_id) if discount_id else None
        if not transaction and not discount:
            continue
        if (transaction and (transaction.type != "settlement" or
                             transaction.registration_id != registration_id)) or (
                discount and (discount.registration_id != registration_id or
                              discount.amount <= 0)):
            raise FinanceError("finance_invariant_broken")
        active_payment = active_settlement(session, transaction.id) if transaction else 0
        active_discount = 0
        if discount:
            reversed_amount = session.scalar(select(func.coalesce(
                func.sum(EventDiscount.amount), 0)).where(
                    EventDiscount.original_discount_id == discount.id)) or 0
            active_discount = discount.amount + int(reversed_amount)
            if active_discount < 0:
                raise FinanceError("finance_invariant_broken")
        result.append({"id": log.id, "registration_id": registration_id,
                       "amount": -transaction.amount if transaction else 0,
                       "discount_amount": discount.amount if discount else 0,
                       "active_amount": active_payment,
                       "active_discount_amount": active_discount,
                       "created_at": log.created_at})
    return result


def settle_registration(
    session: Session, *, registration_id: int, amount: int, actor: Actor, key: str,
    discount_amount: int = 0, discount_reason: str = "",
) -> EffectResult:
    discount_reason = discount_reason.strip()
    if (isinstance(amount, bool) or not isinstance(amount, int) or amount < 0 or
            isinstance(discount_amount, bool) or not isinstance(discount_amount, int) or
            discount_amount < 0 or amount + discount_amount <= 0):
        raise FinanceError("invalid_amount", 422)
    if discount_amount and (actor.type != "user" or not discount_reason):
        raise FinanceError("invalid_discount", 422)

    def effect(current: Session) -> EffectResult:
        event, registration, wallet = lock_registration_wallet(current, registration_id)
        authorize_registration(current, registration_id, actor)
        if event.is_cancelled or registration.status != "active":
            raise FinanceError("settlement_not_allowed")
        state = registration_finance(current, registration_id)
        if amount + discount_amount > state.debt:
            raise FinanceError("settlement_exceeds_debt")
        if amount > wallet.balance:
            raise FinanceError("insufficient_balance")
        discount = None
        if discount_amount:
            discount = EventDiscount(
                registration_id=registration_id, amount=discount_amount,
                reason=discount_reason, actor_id=actor.id,
                idempotency_key=_ledger_key("discount", actor, key),
            )
            current.add(discount)
            current.flush()
        transaction = None
        if amount:
            transaction = append_transaction(
                current, wallet=wallet, type="settlement", amount=-amount,
                registration_id=registration_id, actor_type=actor.type, actor_id=actor.id,
                key=_ledger_key("settlement", actor, key),
            )
        after = registration_finance(current, registration_id)
        current.add(AuditLog(
            actor_type=actor.type, actor_id=actor.id, action="registration.settled",
            entity_type="registration", entity_id=registration_id,
            before_json={"debt": state.debt, "wallet_balance": wallet.balance + amount},
            after_json={"debt": after.debt, "wallet_balance": wallet.balance},
            metadata_json={"idempotency_key": key,
                           "transaction_id": transaction.id if transaction else None,
                           "discount_id": discount.id if discount else None,
                           "amount": amount, "discount_amount": discount_amount,
                           "discount_reason": discount_reason if discount else None},
        ))
        return EffectResult(200, {"transaction_id": transaction.id if transaction else None,
                                  "discount_id": discount.id if discount else None,
                                  "registration_id": registration_id, "amount": amount,
                                  "discount_amount": discount_amount,
                                  "debt": after.debt, "wallet_balance": wallet.balance},
                            "wallet_transaction" if transaction else "event_discount",
                            transaction.id if transaction else discount.id)

    payload = {"registration_id": registration_id, "amount": amount}
    if discount_amount:
        payload.update({"discount_amount": discount_amount,
                        "discount_reason": discount_reason})
    return run_idempotent(session, actor_type=actor.type, actor_id=actor.id,
                          operation="registration.settle", key=key,
                          payload=payload, effect=effect)


def cancel_settlement_operation(
    session: Session, *, operation_id: int, reason: str, actor: Actor, key: str,
) -> EffectResult:
    reason = reason.strip()
    if not reason:
        raise FinanceError("invalid_cancellation_reason", 422)

    def effect(current: Session) -> EffectResult:
        log = current.scalar(select(AuditLog).where(
            AuditLog.id == operation_id, AuditLog.entity_type == "registration",
            AuditLog.action == "registration.settled",
        ))
        if log is None:
            raise FinanceError("settlement_operation_not_found", 404)
        event, registration, wallet = lock_registration_wallet(current, log.entity_id)
        authorize_registration(current, registration.id, actor)
        if event.is_cancelled or registration.status != "active":
            raise FinanceError("settlement_cancellation_not_allowed")
        metadata = log.metadata_json or {}
        transaction_id = metadata.get("transaction_id")
        discount_id = metadata.get("discount_id")
        transaction = current.scalar(select(WalletTransaction).where(
            WalletTransaction.id == transaction_id).with_for_update()) if transaction_id else None
        discount = current.scalar(select(EventDiscount).where(
            EventDiscount.id == discount_id).with_for_update()) if discount_id else None
        if ((not transaction and not discount) or
                (transaction_id and (transaction is None or transaction.type != "settlement" or
                                     transaction.registration_id != registration.id or
                                     transaction.wallet_id != wallet.id)) or
                (discount_id and (discount is None or discount.amount <= 0 or
                                  discount.registration_id != registration.id))):
            raise FinanceError("invalid_settlement_operation")
        payment = active_settlement(current, transaction.id) if transaction else 0
        discount_amount = 0
        if discount:
            reversed_amount = current.scalar(select(func.coalesce(
                func.sum(EventDiscount.amount), 0)).where(
                    EventDiscount.original_discount_id == discount.id)) or 0
            discount_amount = discount.amount + int(reversed_amount)
            if discount_amount < 0:
                raise FinanceError("finance_invariant_broken")
        if not payment and not discount_amount:
            raise FinanceError("settlement_already_cancelled")
        before = registration_finance(current, registration.id)
        reversal = None
        if discount_amount:
            reversal = EventDiscount(
                registration_id=registration.id, original_discount_id=discount.id,
                amount=-discount_amount, reason=reason, actor_id=actor.id,
                idempotency_key=_ledger_key("discount-cancel", actor, key),
            )
            current.add(reversal)
            current.flush()
        refund = None
        if payment:
            refund = append_transaction(
                current, wallet=wallet, type="refund", amount=payment,
                registration_id=registration.id, original_transaction_id=transaction.id,
                actor_type="user", actor_id=actor.id,
                key=_ledger_key("settlement-cancel", actor, key), reason=reason,
            )
        after = registration_finance(current, registration.id)
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action="registration.settlement_cancelled",
            entity_type="registration", entity_id=registration.id,
            before_json={"debt": before.debt, "wallet_balance": wallet.balance - payment},
            after_json={"debt": after.debt, "wallet_balance": wallet.balance},
            metadata_json={"idempotency_key": key, "operation_id": operation_id,
                           "settlement_id": transaction_id, "discount_id": discount_id,
                           "refund_id": refund.id if refund else None,
                           "discount_reversal_id": reversal.id if reversal else None,
                           "amount": payment, "discount_amount": discount_amount,
                           "reason": reason},
        ))
        return EffectResult(200, {"operation_id": operation_id,
                                  "registration_id": registration.id,
                                  "refunded_amount": payment,
                                  "cancelled_discount_amount": discount_amount,
                                  "debt": after.debt, "wallet_balance": wallet.balance},
                            "registration", registration.id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation="registration.settlement_cancel", key=key,
                          payload={"operation_id": operation_id, "reason": reason},
                          effect=effect)


def refund_settlement(
    session: Session, *, settlement_id: int, amount: int, reason: str,
    actor: Actor, key: str,
) -> EffectResult:
    if amount <= 0 or not reason.strip():
        raise FinanceError("invalid_refund", 422)
    reason = reason.strip()

    def effect(current: Session) -> EffectResult:
        original_id = current.scalar(select(WalletTransaction.registration_id).where(
            WalletTransaction.id == settlement_id,
            WalletTransaction.type == "settlement"))
        if original_id is None:
            raise FinanceError("settlement_not_found", 404)
        _, registration, wallet = lock_registration_wallet(current, original_id)
        authorize_registration(current, original_id, actor)
        original = current.scalar(select(WalletTransaction).where(
            WalletTransaction.id == settlement_id).with_for_update())
        if original is None or original.type != "settlement":
            raise FinanceError("settlement_not_found", 404)
        if original.registration_id != registration.id or original.wallet_id != wallet.id:
            raise FinanceError("invalid_settlement")
        if amount > active_settlement(current, settlement_id):
            raise FinanceError("refund_exceeds_settlement")
        before = registration_finance(current, registration.id)
        refund = append_transaction(
            current, wallet=wallet, type="refund", amount=amount,
            registration_id=registration.id, original_transaction_id=settlement_id,
            actor_type=actor.type, actor_id=actor.id,
            key=_ledger_key("refund", actor, key), reason=reason,
        )
        after = registration_finance(current, registration.id)
        current.add(AuditLog(
            actor_type=actor.type, actor_id=actor.id, action="registration.refunded",
            entity_type="registration", entity_id=registration.id,
            before_json={"debt": before.debt}, after_json={"debt": after.debt},
            metadata_json={"idempotency_key": key, "settlement_id": settlement_id,
                           "refund_id": refund.id, "amount": amount, "reason": reason},
        ))
        return EffectResult(200, {"transaction_id": refund.id,
                                  "settlement_id": settlement_id,
                                  "registration_id": registration.id, "amount": amount,
                                  "debt": after.debt, "wallet_balance": wallet.balance},
                            "wallet_transaction", refund.id)

    return run_idempotent(session, actor_type=actor.type, actor_id=actor.id,
                          operation="registration.refund", key=key,
                          payload={"settlement_id": settlement_id, "amount": amount,
                                   "reason": reason}, effect=effect)


def adjust_wallet(
    session: Session, *, guest_id: int, amount: int, note: str,
    actor: Actor, key: str,
) -> EffectResult:
    if amount == 0 or not note.strip():
        raise FinanceError("invalid_adjustment", 422)
    note = note.strip()

    def effect(current: Session) -> EffectResult:
        wallet = current.scalar(select(Wallet).where(
            Wallet.guest_id == guest_id).with_for_update())
        if wallet is None:
            raise FinanceError("guest_not_found", 404)
        before = wallet.balance
        transaction = append_transaction(
            current, wallet=wallet, type="manual_adjust", amount=amount,
            actor_type="user", actor_id=actor.id,
            key=_ledger_key("manual_adjust", actor, key), note=note,
        )
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action="wallet.manual_adjusted",
            entity_type="wallet", entity_id=wallet.id,
            before_json={"balance": before}, after_json={"balance": wallet.balance},
            metadata_json={"idempotency_key": key, "transaction_id": transaction.id,
                           "amount": amount, "note": note},
        ))
        return EffectResult(200, {"transaction_id": transaction.id, "guest_id": guest_id,
                                  "amount": amount, "wallet_balance": wallet.balance},
                            "wallet_transaction", transaction.id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation="wallet.manual_adjust", key=key,
                          payload={"guest_id": guest_id, "amount": amount, "note": note},
                          effect=effect)
