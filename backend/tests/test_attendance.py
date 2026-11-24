"""H13 attendance state machine on isolated PostgreSQL, with and without entry fees."""

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
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
    Wallet,
    WalletTransaction,
)
from app.seed import bootstrap_admin
from app.services.finance import append_transaction, lock_registration_wallet, registration_finance

SOURCES = ("pending", "present", "absent_kept", "absent_forfeited")
TARGETS = ("present", "absent_kept", "absent_forfeited")


def change(client, registration_id: int, target: str, key: str):
    return client.post(f"/api/admin/registrations/{registration_id}/attendance",
                       headers={**write_headers(client), "Idempotency-Key": key},
                       json={"attendance": target})


def test_all_attendance_transitions_paid_and_free(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        counter = 0
        for fee in (0, 100):
            with factory() as session, session.begin():
                event = Event(event_number=100 + fee, title="حضور", entry_fee=fee,
                              registration_status="closed")
                session.add(event)
                session.flush()
                event_id = event.id
            for source in SOURCES:
                for target in TARGETS:
                    counter += 1
                    with factory() as session, session.begin():
                        guest = Guest(first_name="مهمان", last_name="آزمون",
                                      phone=f"0912{counter:07d}")
                        session.add(guest)
                        session.flush()
                        session.add(Wallet(guest_id=guest.id, balance=0))
                        registration = Registration(event_id=event_id, guest_id=guest.id,
                                                    source="admin", attendance="pending")
                        session.add(registration)
                        session.flush()
                        registration_id = registration.id
                    if source != "pending":
                        prepared = change(client, registration_id, source,
                                          f"prepare-{fee}-{counter}")
                        assert prepared.status_code == 200, prepared.text
                    else:
                        unchanged = change(client, registration_id, "pending",
                                           f"pending-self-{fee}-{counter}")
                        assert unchanged.status_code == 200
                        assert unchanged.json()["changed"] is False
                    transition_key = f"transition-{fee}-{counter}"
                    response = change(client, registration_id, target, transition_key)
                    assert response.status_code == 200, response.text
                    assert response.json()["changed"] is (source != target)
                    assert change(client, registration_id, target,
                                  transition_key).json() == response.json()
                    with factory() as session:
                        registration = session.get(Registration, registration_id)
                        assert registration.attendance == target
                        charges = session.scalars(select(EventCharge).where(
                            EventCharge.registration_id == registration_id)).all()
                        active_entries = [charge for charge in charges
                                          if charge.type == "entry" and not charge.is_cancelled]
                        assert len(active_entries) == (1 if fee and target != "absent_kept" else 0)
                        assert all(charge.amount > 0 for charge in charges)
                        state = registration_finance(session, registration_id)
                        expected = fee if target != "absent_kept" else 0
                        assert (state.active_charges, state.debt) == (expected, expected)
                    if target != "pending":
                        rejected = change(client, registration_id, "pending",
                                          f"invalid-{fee}-{counter}")
                        assert rejected.status_code == 409
                        assert rejected.json()["detail"] == "attendance_back_to_pending"
        assert counter == 24


def test_attendance_refunds_only_excess_and_is_atomic(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        with factory() as session, session.begin():
            event = Event(event_number=201, title="برگشت", entry_fee=100,
                          registration_status="closed")
            session.add(event)
            session.flush()
            event_id = event.id
        for index, (settled, target, expected_refund) in enumerate((
            (0, "absent_forfeited", 0),
            (60, "absent_forfeited", 0),
            (140, "absent_forfeited", 40),
            (60, "absent_kept", 60),
            (140, "absent_kept", 140),
        ), start=1):
            with factory() as session, session.begin():
                guest = Guest(first_name="مهمان", last_name="مالی", phone=f"0913{index:07d}")
                session.add(guest)
                session.flush()
                wallet = Wallet(guest_id=guest.id, balance=0)
                registration = Registration(event_id=event_id, guest_id=guest.id, source="admin")
                session.add_all([wallet, registration])
                session.flush()
                registration_id, wallet_id = registration.id, wallet.id
            assert change(client, registration_id, "present", f"present-{index}").status_code == 200
            with factory() as session, session.begin():
                _, _, wallet = lock_registration_wallet(session, registration_id)
                session.add(EventCharge(registration_id=registration_id, type="order",
                                        description="خوراک", amount=40, created_by=1))
                append_transaction(session, wallet=wallet, type="manual_adjust", amount=200,
                                   actor_type="user", actor_id=1, key=f"credit-{index}",
                                   note="اعتبار تست")
                if settled:
                    append_transaction(session, wallet=wallet, type="settlement", amount=-settled,
                                       registration_id=registration_id, actor_type="user",
                                       actor_id=1, key=f"settle-{index}")
            key = f"absence-{index}"
            if index == 3:
                with factory() as session, session.begin():
                    session.get(Wallet, wallet_id).balance += 1
                failed = change(client, registration_id, target, key)
                assert failed.status_code == 409
                assert failed.json()["detail"] == "wallet_ledger_mismatch"
                with factory() as session:
                    assert session.get(Registration, registration_id).attendance == "present"
                    assert session.scalar(select(EventCharge.is_cancelled).where(
                        EventCharge.registration_id == registration_id,
                        EventCharge.type == "order")) is False
                    assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
                        WalletTransaction.registration_id == registration_id,
                        WalletTransaction.type == "refund")) == 0
                with factory() as session, session.begin():
                    session.get(Wallet, wallet_id).balance -= 1
            response = change(client, registration_id, target, key)
            assert response.status_code == 200, response.text
            body = response.json()
            assert sum(item["amount"] for item in body["refunds"]) == expected_refund
            assert body["wallet_balance"] == 200 - settled + expected_refund
            assert body["debt"] == (100 if target == "absent_forfeited" else 0) - \
                (settled - expected_refund)
            assert change(client, registration_id, target, key).json() == body
            assert change(client, registration_id, target,
                          f"self-{index}").json()["changed"] is False
            if target != "absent_kept":
                assert change(client, registration_id, "absent_kept", key).status_code == 409
            with factory() as session:
                assert session.get(Wallet, wallet_id).balance == 200 - settled + expected_refund
                orders = session.scalars(select(EventCharge).where(
                    EventCharge.registration_id == registration_id,
                    EventCharge.type == "order")).all()
                assert len(orders) == 1 and orders[0].is_cancelled
                state = registration_finance(session, registration_id)
                assert state.debt >= 0
                refunds = session.scalars(select(WalletTransaction).where(
                    WalletTransaction.registration_id == registration_id,
                    WalletTransaction.type == "refund")).all()
                assert sum(row.amount for row in refunds) == expected_refund
                assert all(row.original_transaction_id is not None for row in refunds)
                audit = session.scalar(select(AuditLog).where(
                    AuditLog.entity_type == "registration", AuditLog.entity_id == registration_id,
                    AuditLog.action == "registration.attendance_changed",
                ).order_by(AuditLog.id.desc()))
                assert audit.metadata_json["idempotency_key"] == key
                assert audit.metadata_json["refunded_total"] == expected_refund
            if index == 4:
                restored = change(client, registration_id, "present", "restore-entry")
                assert restored.status_code == 200
                assert restored.json()["debt"] == 100
                assert restored.json()["refunds"] == []


def test_free_event_order_refund_and_cancelled_guard(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        event = Event(event_number=202, title="رایگان", entry_fee=0,
                      registration_status="closed")
        guest = Guest(first_name="رایگان", last_name="مهمان", phone="09123456789")
        session.add_all([event, guest])
        session.flush()
        wallet = Wallet(guest_id=guest.id, balance=0)
        registration = Registration(event_id=event.id, guest_id=guest.id, source="admin")
        session.add_all([wallet, registration])
        session.flush()
        registration_id, event_id = registration.id, event.id
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        assert change(client, registration_id, "present", "free-present").status_code == 200
        with factory() as session, session.begin():
            _, _, wallet = lock_registration_wallet(session, registration_id)
            session.add(EventCharge(registration_id=registration_id, type="order",
                                    description="سفارش", amount=40, created_by=1))
            append_transaction(session, wallet=wallet, type="manual_adjust", amount=40,
                               actor_type="user", actor_id=1, key="free-credit", note="تست")
            append_transaction(session, wallet=wallet, type="settlement", amount=-40,
                               registration_id=registration_id, actor_type="user", actor_id=1,
                               key="free-settlement")
        absent = change(client, registration_id, "absent_forfeited", "free-absent")
        assert absent.status_code == 200, absent.text
        assert sum(row["amount"] for row in absent.json()["refunds"]) == 40
        assert absent.json()["debt"] == 0
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(EventCharge).where(
                EventCharge.registration_id == registration_id,
                EventCharge.type == "entry")) == 0
            assert session.get(Wallet, wallet.id).balance == 40
        with factory() as session, session.begin():
            session.get(Event, event_id).is_cancelled = True
        assert change(client, registration_id, "present", "cancelled-event").status_code == 409
        with factory() as session, session.begin():
            session.get(Event, event_id).is_cancelled = False
            session.get(Registration, registration_id).status = "cancelled"
        blocked = change(client, registration_id, "present", "cancelled-registration")
        assert blocked.status_code == 409


def test_removed_secretary_cannot_replay_attendance_change(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as boss:
        login(boss, "boss", "boss-password-123")
        secretary = boss.post("/api/admin/users", headers=write_headers(boss), json={
            "username": "sec", "full_name": "دبیر", "password": "secretary-password",
        })
        assert secretary.status_code == 201
        secretary_id = secretary.json()["id"]
        with factory() as session, session.begin():
            event = Event(event_number=203, title="مجوز حضور", entry_fee=10,
                          registration_status="closed")
            guest = Guest(first_name="مهمان", last_name="مجوز", phone="09123456789")
            session.add_all([event, guest])
            session.flush()
            session.add_all([Wallet(guest_id=guest.id, balance=0),
                             EventSecretary(event_id=event.id, user_id=secretary_id)])
            registration = Registration(event_id=event.id, guest_id=guest.id, source="admin")
            session.add(registration)
            session.flush()
            registration_id, event_id = registration.id, event.id
        with TestClient(create_app(settings), base_url=ORIGIN) as assigned:
            login(assigned, "sec", "secretary-password")
            first = change(assigned, registration_id, "present", "assigned-change")
            assert first.status_code == 200
            listing = assigned.get(f"/api/admin/events/{event_id}/registrations")
            assert listing.status_code == 200
            assert listing.json()["total"] == 1
            assert listing.json()["items"][0]["attendance"] == "present"
            assert listing.json()["items"][0]["active_charge_total"] == 10
            with factory() as session, session.begin():
                session.execute(delete(EventSecretary).where(
                    EventSecretary.event_id == event_id,
                    EventSecretary.user_id == secretary_id))
            replay = change(assigned, registration_id, "present", "assigned-change")
            assert replay.status_code == 403
            assert assigned.get(f"/api/admin/events/{event_id}/registrations").status_code == 403
