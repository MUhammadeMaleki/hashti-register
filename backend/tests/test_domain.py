from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic.config import Config
from argon2 import PasswordHasher
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import (
    Event,
    EventCharge,
    Guest,
    PaymentSubmission,
    Registration,
    Setting,
    User,
    Wallet,
    WalletTransaction,
)
from app.seed import bootstrap_admin, seed_demo
from app.services.guests import create_guest_with_wallet, normalize_phone


def expect_rejected(session, item):
    with pytest.raises(IntegrityError), session.begin_nested():
        session.add(item)
        session.flush()


def test_empty_schema_upgrades_to_head(postgres_engine):
    schema = "h03_" + uuid4().hex[:12]
    with postgres_engine.connect() as connection:
        outer = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            configuration = Config("alembic.ini")
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "head")
            names = set(inspect(connection).get_table_names(schema=schema))
            assert len(names) == 20  # 19 domain tables plus Alembic version
            assert "event_discounts" in names
            assert "wallet_transactions" in names
            assert "alembic_version" in names
        finally:
            outer.rollback()


def test_guest_wallet_atomicity_and_phone_uniqueness(db_session):
    profile = create_guest_with_wallet(
        db_session, first_name="آراد", last_name="نمونه", phone="+۹۸ ۹۱۲-۰۰۰-۰۰۰۰"
    )
    assert normalize_phone("۰۹۱۲ ۰۰۰ ۰۰۰۰") == "09120000000"
    assert db_session.get(Wallet, profile.wallet_id).balance == 0
    assert db_session.get(Guest, profile.guest_id).phone == "09120000000"
    db_session.rollback()
    with pytest.raises(IntegrityError):
        create_guest_with_wallet(
            db_session, first_name="تکراری", last_name="نمونه", phone="09120000000"
        )
    assert db_session.scalar(select(func.count()).select_from(Wallet)) == 1
    db_session.rollback()

    real_flush = db_session.flush
    calls = 0

    def fail_wallet_flush(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated wallet insert failure")
        return real_flush(*args, **kwargs)

    with patch.object(db_session, "flush", side_effect=fail_wallet_flush):
        with pytest.raises(RuntimeError, match="wallet insert"):
            create_guest_with_wallet(
                db_session, first_name="ناتمام", last_name="نمونه", phone="09120000001"
            )
    assert db_session.scalar(select(Guest.id).where(Guest.phone == "09120000001")) is None
    db_session.rollback()


def test_database_rejects_invalid_amounts_states_and_receipts(db_session):
    user = User(username="admin-h03", full_name="مدیر", password_hash="hash", role="super_admin")
    guest = Guest(first_name="الف", last_name="ب", phone="09120000002")
    db_session.add_all([user, guest])
    db_session.flush()
    wallet = Wallet(guest_id=guest.id)
    db_session.add(wallet)
    db_session.flush()
    event = Event(event_number=311, title="تست", entry_fee=0)
    db_session.add(event)
    db_session.flush()
    registration = Registration(event_id=event.id, guest_id=guest.id, source="admin")
    db_session.add(registration)
    db_session.flush()

    expect_rejected(db_session, Wallet(guest_id=guest.id, balance=0))
    expect_rejected(db_session, Guest(first_name="x", last_name="y", phone="08120000002"))
    expect_rejected(db_session, Event(event_number=312, title="bad", entry_fee=-1))
    expect_rejected(db_session, Registration(event_id=event.id, guest_id=guest.id, source="admin"))
    expect_rejected(
        db_session,
        EventCharge(
            registration_id=registration.id,
            type="order",
            description="bad",
            amount=0,
            created_by=user.id,
        ),
    )
    expect_rejected(
        db_session,
        WalletTransaction(
            wallet_id=wallet.id,
            type="settlement",
            amount=100,
            registration_id=registration.id,
            actor_type="user",
            actor_id=user.id,
            idempotency_key="bad-sign",
        ),
    )
    expect_rejected(
        db_session,
        PaymentSubmission(
            guest_id=guest.id,
            amount=100,
            idempotency_key="no-evidence",
        ),
    )
    expect_rejected(db_session, Setting(key="default_debt_ceiling", value=-1))


def test_historical_foreign_keys_restrict_deletion(db_session):
    profile = create_guest_with_wallet(
        db_session, first_name="مهمان", last_name="تاریخی", phone="09120000003"
    )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(Guest.__table__.delete().where(Guest.id == profile.guest_id))


def test_financial_type_and_receipt_constraints(db_session):
    profile = create_guest_with_wallet(
        db_session, first_name="مهمان", last_name="مالی", phone="09120000004"
    )
    submission = PaymentSubmission(
        guest_id=profile.guest_id,
        amount=200,
        tracking_code="AB-123",
        idempotency_key="receipt-1",
    )
    db_session.add(submission)
    db_session.flush()
    expect_rejected(
        db_session,
        PaymentSubmission(
            guest_id=profile.guest_id,
            amount=100,
            original_receipt_path="original.jpg",
            idempotency_key="receipt-bad-image",
        ),
    )
    topup = WalletTransaction(
        wallet_id=profile.wallet_id,
        type="topup",
        amount=200,
        payment_submission_id=submission.id,
        actor_type="user",
        actor_id=1,
        idempotency_key="topup-1",
    )
    db_session.add(topup)
    db_session.flush()
    expect_rejected(
        db_session,
        WalletTransaction(
            wallet_id=profile.wallet_id,
            type="topup",
            amount=200,
            payment_submission_id=submission.id,
            actor_type="user",
            actor_id=1,
            idempotency_key="topup-2",
        ),
    )
    expect_rejected(
        db_session,
        WalletTransaction(
            wallet_id=profile.wallet_id,
            type="refund",
            amount=10,
            actor_type="user",
            actor_id=1,
            idempotency_key="refund-no-original",
        ),
    )


def test_super_admin_and_demo_seed_are_explicit_and_idempotent(db_session):
    assert bootstrap_admin(
        db_session, username="h03-admin", full_name="مدیر نمونه", password="long-test-secret"
    )
    user = db_session.scalar(select(User).where(User.username == "h03-admin"))
    assert user.role == "super_admin"
    assert user.password_hash != "long-test-secret"
    assert PasswordHasher().verify(user.password_hash, "long-test-secret")
    admin_id = user.id
    db_session.rollback()
    assert not bootstrap_admin(
        db_session, username="h03-admin", full_name="مدیر نمونه", password="long-test-secret"
    )
    seed_demo(db_session, admin_id=admin_id)
    seed_demo(db_session, admin_id=admin_id)
    assert (
        db_session.scalar(select(func.count()).select_from(Event).where(Event.event_number == 1))
        == 1
    )
    assert (
        db_session.scalar(
            select(func.count()).select_from(Guest).where(Guest.phone == "09000000000")
        )
        == 1
    )
