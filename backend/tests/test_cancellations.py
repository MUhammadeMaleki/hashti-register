"""H18 cancellation/refund/reactivation invariants on real PostgreSQL."""

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import (
    AuditLog,
    Event,
    EventCharge,
    EventSecretary,
    Guest,
    Registration,
    User,
    Wallet,
    WalletTransaction,
)
from app.seed import bootstrap_admin
from app.services.finance import append_transaction, registration_finance


def action(client, path, key):
    return client.post(path, headers={**write_headers(client), "Idempotency-Key": key})


def seed(engine, *, second=True):
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        boss_id = session.scalar(select(User.id).where(User.username == "boss"))
        secretary = User(username="sec", full_name="دبیر", role="secretary",
                         password_hash=PasswordHasher().hash("secretary-password-123"))
        session.add(secretary)
        session.flush()
        event = Event(event_number=301, title="لغو", entry_fee=100,
                      registration_status="closed")
        session.add(event)
        session.flush()
        session.add(EventSecretary(event_id=event.id, user_id=secretary.id))
        registrations = []
        for number in range(2 if second else 1):
            guest = Guest(first_name="مهمان", last_name=str(number),
                          phone=f"0912000120{number}")
            session.add(guest)
            session.flush()
            session.add(Wallet(guest_id=guest.id, balance=0))
            registration = Registration(event_id=event.id, guest_id=guest.id,
                                        attendance="present", source="admin")
            session.add(registration)
            session.flush()
            session.add(EventCharge(registration_id=registration.id, type="entry",
                                    description="ورودی", amount=100, created_by=boss_id))
            session.add(EventCharge(registration_id=registration.id, type="order",
                                    description="سفارش", amount=20, created_by=boss_id))
            registrations.append(registration.id)
        event_id, secretary_id = event.id, secretary.id
    with factory() as session, session.begin():
        for index, registration_id in enumerate(registrations):
            guest_id = session.get(Registration, registration_id).guest_id
            wallet = session.scalar(select(Wallet).where(
                Wallet.guest_id == guest_id).with_for_update())
            append_transaction(session, wallet=wallet, type="manual_adjust", amount=200,
                               note="آماده‌سازی تست", actor_type="user", actor_id=boss_id,
                               key=f"seed-credit-{index}")
            append_transaction(session, wallet=wallet, type="settlement", amount=-80,
                               registration_id=registration_id, actor_type="user",
                               actor_id=boss_id, key=f"seed-settlement-{index}")
    return event_id, registrations, secretary_id


def test_event_cancel_replay_reactivate_and_explicit_registration_reactivate(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    event_id, registrations, _ = seed(engine)
    factory = build_session_factory(engine)
    with (TestClient(create_app(settings), base_url=ORIGIN) as boss,
          TestClient(create_app(settings), base_url=ORIGIN) as sec):
        login(boss, "boss", "boss-password-123")
        login(sec, "sec", "secretary-password-123")
        cancel_path = f"/api/admin/events/{event_id}/cancel"
        assert sec.post(cancel_path, headers={"Origin": ORIGIN}).status_code == 403
        assert sec.post(cancel_path, headers=write_headers(sec)).status_code == 422
        cancelled = action(sec, cancel_path, "cancel-event")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["registrations"] == 2
        assert cancelled.json()["refunded_total"] == 160
        assert action(sec, cancel_path, "cancel-event").json() == cancelled.json()
        assert action(sec, cancel_path, "cancel-again").json()["changed"] is False
        with factory() as session:
            event = session.get(Event, event_id)
            assert event.is_cancelled and event.registration_status == "closed"
            for registration_id in registrations:
                registration = session.get(Registration, registration_id)
                assert registration.status == "cancelled"
                assert registration.attendance == "present"
                assert registration_finance(session, registration_id).debt == 0
                assert session.scalar(select(func.count()).select_from(EventCharge).where(
                    EventCharge.registration_id == registration_id,
                    EventCharge.is_cancelled.is_(False))) == 0
            assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
                WalletTransaction.type == "refund")) == 2
            assert all(balance == 200 for balance in session.scalars(select(Wallet.balance)))
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "event.cancelled")) == 1
        reactivate_path = f"/api/admin/events/{event_id}/reactivate"
        blocked = action(sec, f"/api/admin/registrations/{registrations[0]}/reactivate",
                         "while-cancelled")
        assert blocked.status_code == 409
        restored = action(sec, reactivate_path, "reactivate-event")
        assert restored.status_code == 200, restored.text
        assert restored.json()["registration_status"] == "closed"
        assert action(sec, reactivate_path, "reactivate-event").json() == restored.json()
        assert action(sec, reactivate_path, "reactivate-again").json()["changed"] is False
        assert action(sec, f"/api/admin/registrations/{registrations[0]}/reactivate",
                      "while-closed").status_code == 409
        with factory() as session:
            assert all(session.get(Registration, rid).status == "cancelled"
                       for rid in registrations)
            assert all(balance == 200 for balance in session.scalars(select(Wallet.balance)))
            assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 6
        opened = boss.patch(f"/api/admin/events/{event_id}", headers=write_headers(boss),
                            json={"registration_status": "open"})
        assert opened.status_code == 200, opened.text
        registration_path = f"/api/admin/registrations/{registrations[0]}/reactivate"
        active = action(sec, registration_path, "reactivate-registration")
        assert active.status_code == 200, active.text
        assert active.json()["attendance"] == "pending"
        assert action(sec, registration_path, "reactivate-registration").json() == active.json()
        assert action(sec, registration_path, "reactivate-again").status_code == 409
        with factory() as session:
            assert session.get(Registration, registrations[0]).status == "active"
            assert session.get(Registration, registrations[1]).status == "cancelled"
            assert registration_finance(session, registrations[0]).active_charges == 0
            assert session.scalar(select(func.count()).select_from(EventCharge).where(
                EventCharge.registration_id == registrations[0])) == 2
        order_path = f"/api/admin/registrations/{registrations[0]}/orders"
        assert boss.post(order_path, headers={**write_headers(boss),
                         "Idempotency-Key": "pending-order"},
                         json={"description": "جدید", "amount": 10}).status_code == 409
        attendance = boss.post(f"/api/admin/registrations/{registrations[0]}/attendance",
                               headers={**write_headers(boss), "Idempotency-Key": "present-again"},
                               json={"attendance": "present"})
        assert attendance.status_code == 200, attendance.text
        with factory() as session:
            charges = session.scalars(select(EventCharge).where(
                EventCharge.registration_id == registrations[0],
                EventCharge.is_cancelled.is_(False))).all()
            assert len(charges) == 1 and charges[0].type == "entry" and charges[0].amount == 100
            assert registration_finance(session, registrations[0]).debt == 100


def test_individual_cancel_and_event_cancel_atomic_rollback(management_environment):  # noqa: F811
    engine, settings = management_environment
    event_id, registrations, _ = seed(engine)
    factory = build_session_factory(engine)
    with TestClient(create_app(settings), base_url=ORIGIN) as boss:
        login(boss, "boss", "boss-password-123")
        path = f"/api/admin/registrations/{registrations[0]}/cancel"
        cancelled = action(boss, path, "cancel-one")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["refunded_total"] == 80
        assert action(boss, path, "cancel-one").json() == cancelled.json()
        assert action(boss, path, "cancel-one-again").json()["changed"] is False
        with factory() as session, session.begin():
            second_guest = session.get(Registration, registrations[1]).guest_id
            wallet = session.scalar(select(Wallet).where(Wallet.guest_id == second_guest))
            wallet.balance += 1  # force a failure after event cancellation has begun
        failed = action(boss, f"/api/admin/events/{event_id}/cancel", "fail-atomic")
        assert failed.status_code == 409, failed.text
        assert failed.json()["detail"] == "wallet_ledger_mismatch"
        with factory() as session:
            assert not session.get(Event, event_id).is_cancelled
            assert session.get(Registration, registrations[1]).status == "active"
            assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
                WalletTransaction.type == "refund")) == 1
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "event.cancelled")) == 0


def test_event_cancel_rolls_back_earlier_guest_when_later_wallet_fails(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    event_id, registrations, _ = seed(engine)
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        second_guest = session.get(Registration, registrations[1]).guest_id
        session.scalar(select(Wallet).where(Wallet.guest_id == second_guest)).balance += 1
    with TestClient(create_app(settings), base_url=ORIGIN) as boss:
        login(boss, "boss", "boss-password-123")
        failed = action(boss, f"/api/admin/events/{event_id}/cancel", "atomic-failure")
        assert failed.status_code == 409
        assert failed.json()["detail"] == "wallet_ledger_mismatch"
    with factory() as session:
        assert not session.get(Event, event_id).is_cancelled
        assert all(session.get(Registration, rid).status == "active" for rid in registrations)
        assert session.scalar(select(func.count()).select_from(EventCharge).where(
            EventCharge.is_cancelled.is_(True))) == 0
        assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.type == "refund")) == 0
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action.in_(["registration.cancelled", "event.cancelled"]))) == 0


def test_free_pending_registration_reactivation_never_creates_zero_entry(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        event = Event(event_number=302, title="رایگان", entry_fee=0,
                      registration_status="open")
        guest = Guest(first_name="مهمان", last_name="رایگان", phone="09120001222")
        session.add_all([event, guest])
        session.flush()
        wallet = Wallet(guest_id=guest.id, balance=0)
        registration = Registration(event_id=event.id, guest_id=guest.id,
                                    attendance="pending", source="admin")
        session.add_all([wallet, registration])
        session.flush()
        registration_id = registration.id
    with TestClient(create_app(settings), base_url=ORIGIN) as boss:
        login(boss, "boss", "boss-password-123")
        path = f"/api/admin/registrations/{registration_id}"
        assert action(boss, path + "/cancel", "free-cancel").json()["refunded_total"] == 0
        assert action(boss, path + "/reactivate", "free-reactivate").status_code == 200
        present = boss.post(path + "/attendance", headers={**write_headers(boss),
                            "Idempotency-Key": "free-present"}, json={"attendance": "present"})
        assert present.status_code == 200, present.text
    with factory() as session:
        assert session.get(Registration, registration_id).attendance == "present"
        assert session.scalar(select(func.count()).select_from(EventCharge).where(
            EventCharge.registration_id == registration_id)) == 0
        assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 0
