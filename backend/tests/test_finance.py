from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_management import ORIGIN, login, management_environment  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, EventCharge, Guest, Registration, Wallet, WalletTransaction
from app.seed import bootstrap_admin
from app.services.finance import (
    EffectResult,
    FinanceError,
    append_transaction,
    lock_registration_wallet,
    registration_finance,
    run_idempotent,
)


def test_ledger_debt_reconciliation_and_idempotency(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        guest = Guest(first_name="مینا", last_name="مالی", phone="09123456789")
        session.add(guest)
        session.flush()
        wallet = Wallet(guest_id=guest.id, balance=0)
        event = Event(event_number=30, title="مالی", registration_status="open")
        session.add_all([wallet, event])
        session.flush()
        registration = Registration(event_id=event.id, guest_id=guest.id,
                                    source="admin", attendance="present")
        session.add(registration)
        session.flush()
        session.add(EventCharge(registration_id=registration.id, type="entry",
                                description="ورودی", amount=100, created_by=1))
        guest_id, wallet_id, registration_id = guest.id, wallet.id, registration.id

    def add_credit(session):
        wallet = session.scalar(select(Wallet).where(Wallet.id == wallet_id).with_for_update())
        row = append_transaction(session, wallet=wallet, type="manual_adjust", amount=150,
                                 actor_type="user", actor_id=1, key="credit-ledger-1",
                                 note="اعتبار آزمایشی")
        return EffectResult(201, {"transaction_id": row.id, "balance": wallet.balance},
                            "wallet_transaction", row.id)

    with factory() as session:
        result = run_idempotent(session, actor_type="user", actor_id=1,
                                operation="wallet.adjust", key="request-1",
                                payload={"guest_id": guest_id, "amount": 150}, effect=add_credit)
        assert result.body["balance"] == 150
    with factory() as session:
        repeated = run_idempotent(session, actor_type="user", actor_id=1,
                                  operation="wallet.adjust", key="request-1",
                                  payload={"amount": 150, "guest_id": guest_id},
                                  effect=lambda _: pytest.fail("effect ran twice"))
        assert repeated == result
    with factory() as session, pytest.raises(FinanceError) as conflict:
        run_idempotent(session, actor_type="user", actor_id=1,
                       operation="wallet.adjust", key="request-1",
                       payload={"guest_id": guest_id, "amount": 200}, effect=add_credit)
    assert conflict.value.code == "idempotency_payload_conflict"

    with factory() as session:
        with session.begin():
            event, registration, wallet = lock_registration_wallet(session, registration_id)
            assert event.id == registration.event_id
            assert wallet.guest_id == guest_id
            assert registration_finance(session, registration_id).debt == 100
            settlement = append_transaction(session, wallet=wallet, type="settlement", amount=-80,
                                            registration_id=registration_id, actor_type="user",
                                            actor_id=1, key="settlement-1")
            settlement_id = settlement.id
            assert registration_finance(session, registration_id).debt == 20
        with session.begin():
            _, _, wallet = lock_registration_wallet(session, registration_id)
            append_transaction(session, wallet=wallet, type="refund", amount=30,
                               registration_id=registration_id,
                               original_transaction_id=settlement_id,
                               actor_type="user", actor_id=1, key="refund-1")
            state = registration_finance(session, registration_id)
            assert (state.active_charges, state.active_settlements, state.debt) == (100, 50, 50)
        with pytest.raises(FinanceError) as over_refund:
            with session.begin():
                _, _, wallet = lock_registration_wallet(session, registration_id)
                append_transaction(session, wallet=wallet, type="refund", amount=51,
                                   registration_id=registration_id,
                                   original_transaction_id=settlement_id,
                                   actor_type="user", actor_id=1, key="refund-too-much")
        assert over_refund.value.code == "refund_exceeds_settlement"
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        assert client.get("/api/admin/finance/reconciliation").status_code == 401
        login(client, "boss", "boss-password-123")
        report = client.get(f"/api/admin/finance/reconciliation?guest_id={guest_id}")
        assert report.status_code == 200
        assert report.json()["items"][0]["matches"] is True
        assert report.json()["items"][0]["cached_balance"] == 100
        with factory() as session, session.begin():
            wallet = session.get(Wallet, wallet_id)
            wallet.balance = 101
        mismatch = client.get(f"/api/admin/finance/reconciliation?guest_id={guest_id}").json()
        assert mismatch["mismatch_count_on_page"] == 1
        assert mismatch["items"][0]["difference"] == 1
        with factory() as session, session.begin():
            wallet = session.get(Wallet, wallet_id)
            wallet.balance = 100
    with factory() as session, pytest.raises(DBAPIError):
        with session.begin():
            session.execute(text("UPDATE wallet_transactions SET amount = 999 WHERE id = :id"),
                            {"id": settlement_id})
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 3


def test_idempotent_concurrent_and_rollback(management_environment):  # noqa: F811
    engine, _ = management_environment
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        guest = Guest(first_name="علی", last_name="تست", phone="09123456780")
        session.add(guest)
        session.flush()
        session.add(Wallet(guest_id=guest.id, balance=0))
        guest_id = guest.id

    def submit():
        with factory() as session:
            def effect(current):
                wallet = current.scalar(select(Wallet).where(
                    Wallet.guest_id == guest_id).with_for_update())
                row = append_transaction(current, wallet=wallet, type="manual_adjust", amount=25,
                                         actor_type="user", actor_id=1, key="concurrent-ledger",
                                         note="آزمون هم‌زمان")
                return EffectResult(201, {"id": row.id, "balance": wallet.balance})

            return run_idempotent(session, actor_type="user", actor_id=1,
                                  operation="wallet.adjust", key="concurrent-request",
                                  payload={"guest_id": guest_id, "amount": 25}, effect=effect)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    with factory() as session:
        assert session.scalar(select(Wallet.balance).where(Wallet.guest_id == guest_id)) == 25
        assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 1

    with factory() as session, pytest.raises(RuntimeError):
        def broken(current):
            wallet = current.scalar(select(Wallet).where(
                Wallet.guest_id == guest_id).with_for_update())
            append_transaction(current, wallet=wallet, type="manual_adjust", amount=10,
                               actor_type="user", actor_id=1, key="rolled-back-ledger",
                               note="شکست آزمایشی")
            raise RuntimeError("abort")

        run_idempotent(session, actor_type="user", actor_id=1,
                       operation="wallet.adjust", key="rolled-back-request",
                       payload={"guest_id": guest_id, "amount": 10}, effect=broken)
    with factory() as session:
        assert session.scalar(select(Wallet.balance).where(Wallet.guest_id == guest_id)) == 25
        assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 1
