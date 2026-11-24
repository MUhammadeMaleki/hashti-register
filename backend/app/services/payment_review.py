"""Atomic review of guest receipts without automatic event settlement."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, EventSecretary, PaymentSubmission, Wallet
from app.services.auth import Actor
from app.services.finance import EffectResult, FinanceError, append_transaction, run_idempotent


def review_payment(
    session: Session, *, payment_id: int, approve: bool, reason: str | None,
    actor: Actor, key: str,
) -> EffectResult:
    if actor.type != "user":
        raise FinanceError("forbidden", 403)
    operation = "payment.approve" if approve else "payment.reject"
    reason = reason.strip() if reason is not None else None
    reason = reason or None
    if reason is not None and len(reason) > 2000:
        raise FinanceError("invalid_reject_reason", 422)
    if approve and reason is not None:
        raise FinanceError("invalid_payment_review", 422)
    payload = {"payment_id": payment_id, "reason": reason}

    def effect(current: Session) -> EffectResult:
        payment = current.scalar(select(PaymentSubmission).where(
            PaymentSubmission.id == payment_id).with_for_update())
        if payment is None:
            raise FinanceError("payment_not_found", 404)
        if actor.role != "super_admin" and (payment.event_id is None or current.scalar(
            select(EventSecretary.user_id).where(
                EventSecretary.event_id == payment.event_id,
                EventSecretary.user_id == actor.id,
            )
        ) is None):
            raise FinanceError("payment_not_found", 404)
        if payment.status != "pending":
            raise FinanceError("payment_already_reviewed")
        before = {"status": payment.status}
        payment.status = "approved" if approve else "rejected"
        payment.reviewed_by = actor.id
        payment.reviewed_at = datetime.now(UTC)
        payment.reject_reason = None if approve else reason
        transaction_id = None
        wallet_balance = None
        if approve:
            wallet = current.scalar(select(Wallet).where(
                Wallet.guest_id == payment.guest_id).with_for_update())
            if wallet is None:
                raise FinanceError("wallet_not_found", 404)
            current.flush()
            transaction = append_transaction(
                current, wallet=wallet, type="topup", amount=payment.amount,
                payment_submission_id=payment.id, actor_type="user", actor_id=actor.id,
                key=operation + ":" + hashlib.sha256(
                    f"{actor.id}:{key}".encode()).hexdigest(),
            )
            transaction_id = transaction.id
            wallet_balance = wallet.balance
        current.add(AuditLog(
            actor_type="user", actor_id=actor.id, action=operation,
            entity_type="payment_submission", entity_id=payment.id,
            before_json=before,
            after_json={"status": payment.status, "reject_reason": payment.reject_reason},
            metadata_json={"idempotency_key": key, "transaction_id": transaction_id,
                           "amount": payment.amount, "event_id": payment.event_id},
        ))
        body = {"id": payment.id, "status": payment.status,
                "reject_reason": payment.reject_reason, "reviewed_by": actor.id,
                "reviewed_at": payment.reviewed_at.isoformat(),
                "transaction_id": transaction_id, "wallet_balance": wallet_balance}
        return EffectResult(200, body, "payment_submission", payment.id)

    return run_idempotent(session, actor_type="user", actor_id=actor.id,
                          operation=operation, key=key, payload=payload, effect=effect)
