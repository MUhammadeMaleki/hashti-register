"""H25: cross-operation races on separate real PostgreSQL sessions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select
from test_management import management_environment  # noqa: F401

from app.core.database import build_session_factory
from app.models import (
    AuditLog,
    Event,
    EventCharge,
    Guest,
    Registration,
    User,
    Wallet,
    WalletTransaction,
)
from app.seed import bootstrap_admin
from app.services.attendance import change_attendance
from app.services.auth import Actor
from app.services.charges import change_order
from app.services.finance import FinanceError, append_transaction, registration_finance
from app.services.settlements import adjust_wallet, refund_settlement, settle_registration


def setup(engine, *, credit=100, order=0):
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        actor_id = session.scalar(select(User.id).where(User.username == "boss"))
        event = Event(event_number=925, title="رقابت مالی", entry_fee=100)
        guest = Guest(first_name="مینا", last_name="رقابت", phone="09120001925")
        session.add_all([event, guest])
        session.flush()
        wallet = Wallet(guest_id=guest.id, balance=0)
        registration = Registration(event_id=event.id, guest_id=guest.id,
                                    attendance="present", source="admin")
        session.add_all([wallet, registration])
        session.flush()
        session.add(EventCharge(registration_id=registration.id, type="entry",
                                description="ورودی", amount=100, created_by=actor_id))
        order_row = None
        if order:
            order_row = EventCharge(registration_id=registration.id, type="order",
                                    description="چای", amount=order, created_by=actor_id)
            session.add(order_row)
        append_transaction(session, wallet=wallet, type="manual_adjust", amount=credit,
                           actor_type="user", actor_id=actor_id, key="seed-credit",
                           note="آماده‌سازی آزمون")
        session.flush()
        ids = guest.id, wallet.id, registration.id, order_row.id if order_row else None
    return factory, Actor(type="user", id=actor_id, session_id=1, role="super_admin"), ids


def race(factory, first, second):
    gate = Barrier(2)

    def run(operation):
        with factory() as session:
            gate.wait(timeout=10)
            try:
                return operation(session)
            except FinanceError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, operation) for operation in (first, second)]
        return [future.result(timeout=20) for future in futures]


def ledger(session, wallet_id):
    balance = session.scalar(select(Wallet.balance).where(Wallet.id == wallet_id))
    total = session.scalar(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
        WalletTransaction.wallet_id == wallet_id))
    assert balance == total and balance >= 0
    return balance


def test_settlement_and_debit_spend_wallet_once(management_environment):  # noqa: F811
    engine, _ = management_environment
    factory, actor, (guest_id, wallet_id, registration_id, _) = setup(engine)
    outcomes = race(factory,
                    lambda session: settle_registration(session, registration_id=registration_id,
                                                        amount=80, actor=actor, key="settle").body,
                    lambda session: adjust_wallet(session, guest_id=guest_id, amount=-80,
                                                  note="برداشت", actor=actor, key="debit").body)
    assert sum(isinstance(value, dict) for value in outcomes) == 1
    assert "insufficient_balance" in outcomes
    with factory() as session:
        assert ledger(session, wallet_id) == 20
        state = registration_finance(session, registration_id)
        assert state.debt in {20, 100} and state.debt >= 0
        assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 2
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action.in_(["registration.settled", "wallet.manual_adjusted"]))) == 1
        assert session.scalar(select(AuditLog.actor_id).where(
            AuditLog.action.in_(["registration.settled", "wallet.manual_adjusted"]))) == actor.id


def test_attendance_and_settlement_leave_consistent_debt(management_environment):  # noqa: F811
    engine, _ = management_environment
    factory, actor, (_, wallet_id, registration_id, _) = setup(engine)
    outcomes = race(factory,
                    lambda session: change_attendance(session, registration_id=registration_id,
                                                      target="absent_kept", actor=actor,
                                                      key="kept").body,
                    lambda session: settle_registration(session, registration_id=registration_id,
                                                        amount=80, actor=actor,
                                                        key="settle-kept").body)
    assert isinstance(outcomes[0], dict) and outcomes[0]["attendance"] == "absent_kept"
    assert isinstance(outcomes[1], dict) or outcomes[1] == "settlement_exceeds_debt"
    with factory() as session:
        assert ledger(session, wallet_id) == 100
        state = registration_finance(session, registration_id)
        assert (state.active_charges, state.active_settlements, state.debt) == (0, 0, 0)
        refunds = session.scalars(select(WalletTransaction).where(
            WalletTransaction.type == "refund")).all()
        settlements = session.scalars(select(WalletTransaction).where(
            WalletTransaction.type == "settlement")).all()
        assert len(refunds) == len(settlements) == (1 if isinstance(outcomes[1], dict) else 0)
        if refunds:
            assert (refunds[0].amount, refunds[0].original_transaction_id) == (
                80, settlements[0].id)
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "registration.attendance_changed")) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "registration.settled")) == len(settlements)
        assert all(row.actor_id == actor.id for row in session.scalars(select(AuditLog).where(
            AuditLog.action.in_(["registration.attendance_changed", "registration.settled"]))))


def test_order_reduction_and_refund_never_over_refund(management_environment):  # noqa: F811
    engine, _ = management_environment
    factory, actor, (_, wallet_id, registration_id, order_id) = setup(
        engine, credit=200, order=40)
    with factory() as session:
        settlement = settle_registration(session, registration_id=registration_id,
                                         amount=140, actor=actor, key="pre-settle")
        settlement_id = settlement.body["transaction_id"]
    outcomes = race(factory,
                    lambda session: change_order(session, registration_id=registration_id,
                                                 charge_id=order_id, description="چای کوچک",
                                                 amount=10, cancel=False, actor=actor,
                                                 key="reduce").body,
                    lambda session: refund_settlement(session, settlement_id=settlement_id,
                                                      amount=140, reason="برگشت کامل",
                                                      actor=actor, key="manual-refund").body)
    assert isinstance(outcomes[0], dict)
    assert isinstance(outcomes[1], dict) or outcomes[1] == "refund_exceeds_settlement"
    with factory() as session:
        balance = ledger(session, wallet_id)
        state = registration_finance(session, registration_id)
        assert state.active_charges == 110 and state.debt >= 0
        refunds = session.scalars(select(WalletTransaction).where(
            WalletTransaction.type == "refund")).all()
        assert sum(row.amount for row in refunds) <= 140
        assert all(row.original_transaction_id == settlement_id for row in refunds)
        assert balance == 60 + sum(row.amount for row in refunds)
        assert state.active_settlements == 140 - sum(row.amount for row in refunds)
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "order.update")) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "registration.refunded")) == (
                1 if isinstance(outcomes[1], dict) else 0)
        assert all(row.actor_id == actor.id for row in session.scalars(select(AuditLog).where(
            AuditLog.action.in_(["order.update", "registration.refunded"]))))


def test_same_key_concurrent_settlement_has_one_effect(management_environment):  # noqa: F811
    engine, _ = management_environment
    factory, actor, (_, wallet_id, registration_id, _) = setup(engine)
    operation = lambda session: settle_registration(  # noqa: E731
        session, registration_id=registration_id, amount=80, actor=actor, key="same-key").body
    outcomes = race(factory, operation, operation)
    assert outcomes[0] == outcomes[1]
    with factory() as session:
        assert ledger(session, wallet_id) == 20
        assert registration_finance(session, registration_id).debt == 20
        assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.type == "settlement")) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "registration.settled")) == 1
        assert session.scalar(select(AuditLog.actor_id).where(
            AuditLog.action == "registration.settled")) == actor.id
