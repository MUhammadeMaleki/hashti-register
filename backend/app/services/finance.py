"""Transactional primitives for the append-only wallet ledger and retry control."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Event,
    EventCharge,
    IdempotencyRequest,
    PaymentSubmission,
    Registration,
    Wallet,
    WalletTransaction,
)


class FinanceError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class EffectResult:
    status: int
    body: dict
    resource_type: str | None = None
    resource_id: int | None = None


@dataclass(frozen=True)
class FinanceState:
    active_charges: int
    active_settlements: int
    debt: int


def run_idempotent(
    session: Session, *, actor_type: str, actor_id: int, operation: str,
    key: str, payload: dict, effect: Callable[[Session], EffectResult],
) -> EffectResult:
    """Claim key, execute effect and persist response in one database transaction."""
    if not key or len(key) > 100 or not operation or len(operation) > 100:
        raise FinanceError("invalid_idempotency_key", 422)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode()).hexdigest()
    with session.begin():
        created = session.scalar(insert(IdempotencyRequest).values(
            actor_type=actor_type, actor_id=actor_id, operation=operation,
            key=key, request_hash=digest,
        ).on_conflict_do_nothing(index_elements=[
            "actor_type", "actor_id", "operation", "key",
        ]).returning(IdempotencyRequest.id))
        request = session.scalar(select(IdempotencyRequest).where(
            IdempotencyRequest.actor_type == actor_type,
            IdempotencyRequest.actor_id == actor_id,
            IdempotencyRequest.operation == operation,
            IdempotencyRequest.key == key,
        ).with_for_update())
        if request.request_hash != digest:
            raise FinanceError("idempotency_payload_conflict")
        if created is None:
            if request.completed_at is None or request.response_json is None:
                raise FinanceError("idempotency_in_progress")
            return EffectResult(request.response_status, request.response_json,
                                request.resource_type, request.resource_id)
        result = effect(session)
        request.response_status = result.status
        request.response_json = result.body
        request.resource_type = result.resource_type
        request.resource_id = result.resource_id
        request.completed_at = datetime.now(UTC)
        session.flush()
        return result


def lock_registration_wallet(
    session: Session, registration_id: int,
) -> tuple[Event, Registration, Wallet]:
    """Acquire event → registration → wallet in the documented order."""
    event_id = session.scalar(select(Registration.event_id).where(
        Registration.id == registration_id))
    if event_id is None:
        raise FinanceError("registration_not_found", 404)
    event = session.scalar(select(Event).where(Event.id == event_id).with_for_update())
    registration = session.scalar(select(Registration).where(
        Registration.id == registration_id).with_for_update())
    wallet = session.scalar(select(Wallet).where(
        Wallet.guest_id == registration.guest_id).with_for_update())
    if wallet is None:
        raise FinanceError("wallet_not_found", 404)
    return event, registration, wallet


def registration_finance(session: Session, registration_id: int) -> FinanceState:
    charges = session.scalar(select(func.coalesce(func.sum(EventCharge.amount), 0)).where(
        EventCharge.registration_id == registration_id, EventCharge.is_cancelled.is_(False))) or 0
    net_settlements = session.scalar(select(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .where(WalletTransaction.registration_id == registration_id,
               WalletTransaction.type.in_(["settlement", "refund"]))) or 0
    charges = int(charges)
    active_settlements = -int(net_settlements)
    debt = charges - active_settlements
    if active_settlements < 0 or debt < 0:
        raise FinanceError("finance_invariant_broken")
    return FinanceState(charges, active_settlements, debt)


def active_settlement(session: Session, settlement_id: int) -> int:
    original = session.scalar(select(WalletTransaction).where(
        WalletTransaction.id == settlement_id).with_for_update())
    if original is None or original.type != "settlement":
        raise FinanceError("settlement_not_found", 404)
    refunded = session.scalar(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
        WalletTransaction.original_transaction_id == settlement_id,
        WalletTransaction.type == "refund")) or 0
    active = -original.amount - int(refunded)
    if active < 0:
        raise FinanceError("finance_invariant_broken")
    return active


def refund_excess(
    session: Session, *, registration_id: int, wallet: Wallet,
    actor_id: int, key: str, reason: str,
) -> list[dict]:
    """Refund only settlement above active charges, newest original first."""
    charges = session.scalar(select(func.coalesce(func.sum(EventCharge.amount), 0)).where(
        EventCharge.registration_id == registration_id,
        EventCharge.is_cancelled.is_(False))) or 0
    net = session.scalar(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
        WalletTransaction.registration_id == registration_id,
        WalletTransaction.type.in_(["settlement", "refund"]))) or 0
    remaining = max(0, -int(net) - int(charges))
    if not remaining:
        return []
    settlements = session.scalars(select(WalletTransaction).where(
        WalletTransaction.registration_id == registration_id,
        WalletTransaction.type == "settlement",
    ).order_by(WalletTransaction.id).with_for_update()).all()
    refunds = []
    for original in reversed(settlements):
        amount = min(remaining, active_settlement(session, original.id))
        if not amount:
            continue
        refund_key = reason + ":" + hashlib.sha256(
            f"{key}:{registration_id}:{original.id}".encode()).hexdigest()
        refund = append_transaction(
            session, wallet=wallet, type="refund", amount=amount,
            registration_id=registration_id, original_transaction_id=original.id,
            actor_type="user", actor_id=actor_id, key=refund_key, reason=reason,
        )
        refunds.append({"id": refund.id, "amount": amount,
                        "settlement_id": original.id})
        remaining -= amount
        if not remaining:
            break
    if remaining:
        raise FinanceError("finance_invariant_broken")
    return refunds


def append_transaction(
    session: Session, *, wallet: Wallet, type: str, amount: int,
    actor_type: str, actor_id: int, key: str, registration_id: int | None = None,
    payment_submission_id: int | None = None, original_transaction_id: int | None = None,
    note: str = "", reason: str | None = None,
) -> WalletTransaction:
    """Append one ledger row and update the already-locked wallet in the same transaction."""
    if not isinstance(amount, int) or isinstance(amount, bool) or amount == 0:
        raise FinanceError("invalid_amount", 422)
    if type not in {"topup", "settlement", "refund", "manual_adjust"}:
        raise FinanceError("invalid_transaction_type", 422)
    if not key or len(key) > 100:
        raise FinanceError("invalid_idempotency_key", 422)
    if type == "topup":
        valid = (amount > 0 and payment_submission_id is not None
                 and registration_id is None and original_transaction_id is None)
    elif type == "settlement":
        valid = (amount < 0 and registration_id is not None
                 and payment_submission_id is None and original_transaction_id is None)
    elif type == "refund":
        valid = (amount > 0 and registration_id is not None
                 and original_transaction_id is not None and payment_submission_id is None)
    else:
        valid = (bool(note.strip()) and registration_id is None
                 and payment_submission_id is None and original_transaction_id is None)
    if not valid:
        raise FinanceError("invalid_transaction", 422)
    if type == "topup":
        payment = session.get(PaymentSubmission, payment_submission_id)
        if payment is None or payment.guest_id != wallet.guest_id or payment.status != "approved":
            raise FinanceError("invalid_payment_submission")
    if type in {"settlement", "refund"}:
        registration = session.get(Registration, registration_id)
        if registration is None or registration.guest_id != wallet.guest_id:
            raise FinanceError("invalid_registration_wallet")
        if type == "settlement":
            event = session.get(Event, registration.event_id)
            if registration.status != "active" or event is None or event.is_cancelled:
                raise FinanceError("settlement_not_allowed")
    if type == "refund":
        original = session.get(WalletTransaction, original_transaction_id)
        if (original is None or original.wallet_id != wallet.id
                or original.registration_id != registration_id
                or amount > active_settlement(session, original_transaction_id)):
            raise FinanceError("refund_exceeds_settlement")
    if type == "settlement":
        state = registration_finance(session, registration_id)
        if -amount > state.debt:
            raise FinanceError("settlement_exceeds_debt")
    ledger_balance = session.scalar(select(func.coalesce(func.sum(WalletTransaction.amount), 0))
        .where(WalletTransaction.wallet_id == wallet.id)) or 0
    if ledger_balance != wallet.balance:
        raise FinanceError("wallet_ledger_mismatch")
    if wallet.balance + amount < 0:
        raise FinanceError("insufficient_balance")
    transaction = WalletTransaction(
        wallet_id=wallet.id, type=type, amount=amount,
        registration_id=registration_id, payment_submission_id=payment_submission_id,
        original_transaction_id=original_transaction_id, note=note, reason=reason,
        actor_type=actor_type, actor_id=actor_id, idempotency_key=key,
    )
    session.add(transaction)
    wallet.balance += amount
    session.flush()
    return transaction
