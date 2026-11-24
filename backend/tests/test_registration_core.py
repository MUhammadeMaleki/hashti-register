"""H12: transaction boundaries and uniqueness on isolated real PostgreSQL schemas."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sa_event
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.api.registrations import Member, register_one
from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, EventSecretary, Guest, GuestAccount, Registration, Wallet
from app.seed import bootstrap_admin


def counts(session) -> tuple[int, int, int, int]:
    return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
        Guest, Wallet, Registration, GuestAccount,
    ))


def test_registration_rolls_back_guest_and_wallet_on_late_failure(
    management_environment,  # noqa: F811
):
    engine, _ = management_environment
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        event = Event(event_number=41, title="Rollback", registration_status="open")
        session.add(event)
        session.flush()
        event_id = event.id

    def fail_registration(_mapper, _connection, _target):
        raise RuntimeError("simulated late registration failure")

    sa_event.listen(Registration, "before_insert", fail_registration)
    try:
        with factory() as session, pytest.raises(RuntimeError):
            register_one(session, event_id, member=Member(
                first_name="آزمایشی", last_name="برگشت", phone="۰۹۱۲۳۴۵۶۷۸۹",
            ))
    finally:
        sa_event.remove(Registration, "before_insert", fail_registration)
    with factory() as session:
        assert counts(session) == (0, 0, 0, 0)


def test_group_partial_failure_account_reuse_and_cancelled_duplicate(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        event = Event(event_number=42, title="گروه", registration_status="open")
        session.add(event)
        session.flush()
        event_id = event.id
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        response = client.post(f"/api/public/events/{event_id}/register",
                               headers={"Origin": ORIGIN}, json={"members": [
                                   {"first_name": "مریم", "last_name": "الف",
                                    "phone": "۰۹۱۲۳۴۵۶۷۸۹"},
                                   {"first_name": "نام", "last_name": "دوم",
                                    "phone": "+989123456789"},
                                   {"first_name": "", "last_name": "نامعتبر",
                                    "phone": "09123456780"},
                                   {"first_name": "رضا", "last_name": "درست",
                                    "phone": "٠٩١٢٣٤٥٦٧٧٧"},
                                   {"first_name": "بی‌موبایل", "last_name": "نامعتبر"},
                               ]})
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        assert [row["status"] for row in results] == [
            "created", "error", "error", "created", "error",
        ]
        assert [results[1]["code"], results[2]["code"]] == [
            "already_registered", "invalid_registration",
        ]
        assert results[4]["code"] == "invalid_phone"
        with factory() as session:
            assert counts(session) == (2, 2, 2, 0)
            guest_id = session.scalar(select(Guest.id).where(Guest.phone == "09123456789"))
            registration_id = session.scalar(select(Registration.id).where(
                Registration.guest_id == guest_id))
        account = client.post("/api/auth/guest/register", headers={"Origin": ORIGIN}, json={
            "first_name": "مریم", "last_name": "الف", "phone": "09123456789",
            "password": "guest-password-123",
        })
        assert account.status_code == 201, account.text
        assert account.json()["guest_id"] == guest_id
        assert client.post("/api/auth/guest/register", headers={"Origin": ORIGIN}, json={
            "first_name": "دیگر", "last_name": "نام", "phone": "+989123456789",
            "password": "guest-password-123",
        }).status_code == 409
        with factory() as session, session.begin():
            registration = session.get(Registration, registration_id)
            registration.status = "cancelled"
        duplicate = client.post(f"/api/public/events/{event_id}/register",
                                headers={"Origin": ORIGIN}, json={"members": [
                                    {"first_name": "مریم", "last_name": "الف",
                                     "phone": "09123456789"},
                                ]})
        assert duplicate.json()["results"][0]["code"] == "already_registered"
        with factory() as session:
            assert counts(session) == (2, 2, 2, 1)
            assert session.get(Registration, registration_id).status == "cancelled"


def test_same_phone_concurrent_different_events_reuses_one_profile(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        first = Event(event_number=43, title="اول", registration_status="open")
        second = Event(event_number=44, title="دوم", registration_status="open")
        session.add_all([first, second])
        session.flush()
        event_ids = [first.id, second.id]
    app = create_app(settings)

    def submit(event_id):
        with TestClient(app, base_url=ORIGIN) as client:
            response = client.post(f"/api/public/events/{event_id}/register",
                                   headers={"Origin": ORIGIN}, json={"members": [
                                       {"first_name": "لیلا", "last_name": "مشترک",
                                        "phone": "۰۹۱۲۳۴۵۶۷۸۹"},
                                   ]})
            assert response.status_code == 200, response.text
            return response.json()["results"][0]["status"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(submit, event_ids)) == ["created", "created"]
    with factory() as session:
        assert counts(session) == (1, 1, 2, 0)
        guest_ids = set(session.scalars(select(Registration.guest_id)))
        assert len(guest_ids) == 1


def test_database_unique_guards_for_registration_and_account(
    management_environment,  # noqa: F811
):
    engine, _ = management_environment
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        guest = Guest(first_name="یک", last_name="نفر", phone="09123456789")
        event = Event(event_number=45, title="یکتا", registration_status="open")
        session.add_all([guest, event])
        session.flush()
        guest_id, event_id = guest.id, event.id
        session.add_all([
            Wallet(guest_id=guest_id, balance=0),
            Registration(guest_id=guest_id, event_id=event_id, source="public"),
            GuestAccount(guest_id=guest_id, phone="09123456789", password_hash="test"),
        ])
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(Registration(guest_id=guest_id, event_id=event_id, source="admin"))
            session.flush()
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(GuestAccount(guest_id=guest_id, phone="09123456789",
                                     password_hash="test-two"))
            session.flush()
    with factory() as session:
        assert counts(session) == (1, 1, 1, 1)


def test_assigned_secretary_and_closed_cancelled_guards(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as boss:
        login(boss, "boss", "boss-password-123")
        assigned = boss.post("/api/admin/users", headers=write_headers(boss), json={
            "username": "assigned", "full_name": "دبیر رویداد", "password": "secretary-password",
        })
        assert assigned.status_code == 201
        outsider = boss.post("/api/admin/users", headers=write_headers(boss), json={
            "username": "outsider", "full_name": "دبیر دیگر", "password": "secretary-password",
        })
        assert outsider.status_code == 201
        with factory() as session, session.begin():
            event = Event(event_number=46, title="مجوز", registration_status="open")
            session.add(event)
            session.flush()
            event_id = event.id
            session.add(EventSecretary(event_id=event_id, user_id=assigned.json()["id"]))
        admin_path = f"/api/admin/events/{event_id}/registrations"
        public_path = f"/api/public/events/{event_id}/register"
        with TestClient(create_app(settings), base_url=ORIGIN) as secretary:
            login(secretary, "assigned", "secretary-password")
            assert secretary.post(admin_path, headers={"Origin": ORIGIN}, json={
                "first_name": "ناامن", "last_name": "بدون CSRF", "phone": "09123456789",
            }).status_code == 403
            added = secretary.post(admin_path, headers=write_headers(secretary), json={
                "first_name": "مینا", "last_name": "درست", "phone": "۰۹۱۲۳۴۵۶۷۸۹",
            })
            assert added.status_code == 201, added.text
        with TestClient(create_app(settings), base_url=ORIGIN) as other:
            login(other, "outsider", "secretary-password")
            assert other.post(admin_path, headers=write_headers(other), json={
                "first_name": "رد", "last_name": "مجوز", "phone": "09123456780",
            }).status_code == 403
        with factory() as session, session.begin():
            session.get(Event, event_id).registration_status = "closed"
        with TestClient(create_app(settings), base_url=ORIGIN) as secretary:
            login(secretary, "assigned", "secretary-password")
            payload = {"first_name": "نفر", "last_name": "بسته", "phone": "09123456780"}
            assert secretary.post(admin_path, headers=write_headers(secretary),
                                  json=payload).status_code == 409
            assert secretary.post(public_path, headers={"Origin": ORIGIN},
                                  json={"members": [payload]}).status_code == 409
            with factory() as session, session.begin():
                event = session.get(Event, event_id)
                event.registration_status = "open"
                event.is_cancelled = True
            assert secretary.post(admin_path, headers=write_headers(secretary),
                                  json=payload).status_code == 409
            assert secretary.post(public_path, headers={"Origin": ORIGIN},
                                  json={"members": [payload]}).status_code == 404
        with factory() as session:
            assert counts(session) == (1, 1, 1, 0)
