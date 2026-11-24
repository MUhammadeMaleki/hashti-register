"""Explicit wallet settlement, linked refunds and manual adjustments."""

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
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


def settle_registration(
    session: Session, *, registration_id: int, amount: int, actor: Actor, key: str,
) -> EffectResult:
    if amount <= 0:
        raise FinanceError("invalid_amount", 422)

    def effect(current: Session) -> EffectResult:
        event, registration, wallet = lock_registration_wallet(current, registration_id)
        authorize_registration(current, registration_id, actor)
        if event.is_cancelled or registration.status != "active":
            raise FinanceError("settlement_not_allowed")
        state = registration_finance(current, registration_id)
        if amount > state.debt:
            raise FinanceError("settlement_exceeds_debt")
        if amount > wallet.balance:
            raise FinanceError("insufficient_balance")
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
            metadata_json={"idempotency_key": key, "transaction_id": transaction.id,
                           "amount": amount},
        ))
        return EffectResult(200, {"transaction_id": transaction.id,
                                  "registration_id": registration_id, "amount": amount,
                                  "debt": after.debt, "wallet_balance": wallet.balance},
                            "wallet_transaction", transaction.id)

    return run_idempotent(session, actor_type=actor.type, actor_id=actor.id,
                          operation="registration.settle", key=key,
                          payload={"registration_id": registration_id, "amount": amount},
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
