from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, EventCharge, Guest, GuestAccount, Registration, Wallet
from app.seed import bootstrap_admin


def test_public_group_and_admin_registration(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        with factory() as session, session.begin():
            event = Event(event_number=20, title="هشتی ثبت‌نام", registration_status="open")
            session.add(event)
            session.flush()
            event_id = event.id
        path = f"/api/public/events/{event_id}/register"
        group = {"members": [
            {"first_name": "مینا", "last_name": "الف", "phone": "۰۹۱۲۳۴۵۶۷۸۹"},
            {"first_name": "رضا", "last_name": "ب", "phone": "09123456780"},
            {"first_name": "غلط", "last_name": "شماره", "phone": "123"},
        ]}
        assert client.post(path, json=group).status_code == 403
        response = client.post(path, headers={"Origin": ORIGIN}, json=group)
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        assert [item["status"] for item in results] == ["created", "created", "error"]
        assert results[2]["code"] == "invalid_phone"
        with factory() as session:
            guests = session.scalars(select(Guest).order_by(Guest.id)).all()
            assert len(guests) == 2
            assert guests[0].phone == "09123456789"
            assert session.query(Wallet).count() == 2
            assert session.query(GuestAccount).count() == 0
            assert session.query(EventCharge).count() == 0
            registrations = session.scalars(select(Registration).order_by(Registration.id)).all()
            assert len(registrations) == 2
            assert all(row.status == "active" and row.attendance == "pending"
                       and row.source == "public" for row in registrations)
            first_id = guests[0].id
        repeated = client.post(path, headers={"Origin": ORIGIN}, json={"members": [
            {"first_name": "نام دیگر", "last_name": "الف", "phone": "+989123456789"},
        ]})
        assert repeated.json()["results"][0]["code"] == "already_registered"
        with factory() as session, session.begin():
            event = session.get(Event, event_id)
            event.registration_status = "closed"
        assert client.post(path, headers={"Origin": ORIGIN}, json=group).status_code == 409
        denied = client.post(f"/api/admin/events/{event_id}/registrations",
                             headers=write_headers(client), json={"guest_id": first_id})
        assert denied.status_code == 409
        with factory() as session, session.begin():
            event = session.get(Event, event_id)
            event.registration_status = "open"
            event.is_cancelled = True
        assert client.post(path, headers={"Origin": ORIGIN}, json=group).status_code == 404
        denied = client.post(f"/api/admin/events/{event_id}/registrations",
                             headers=write_headers(client), json={"guest_id": first_id})
        assert denied.status_code == 409
        with factory() as session, session.begin():
            event = session.get(Event, event_id)
            event.is_cancelled = False
        with factory() as session, session.begin():
            new_event = Event(event_number=21, title="دوم", registration_status="open")
            session.add(new_event)
            session.flush()
            next_id = new_event.id
        linked = client.post(f"/api/admin/events/{next_id}/registrations",
                             headers=write_headers(client), json={"guest_id": first_id})
        assert linked.status_code == 201, linked.text
        assert linked.json()["attendance"] == "pending"
        duplicate = client.post(f"/api/admin/events/{next_id}/registrations",
                                headers=write_headers(client), json={"guest_id": first_id})
        assert duplicate.status_code == 409
        created = client.post(f"/api/admin/events/{next_id}/registrations",
                              headers=write_headers(client), json={
                                  "first_name": "سارا", "last_name": "ج", "phone": "09123456770",
                              })
        assert created.status_code == 201, created.text
        outsider = client.post("/api/admin/users", headers=write_headers(client), json={
            "username": "outsider", "full_name": "دبیر دیگر", "password": "secretary-password",
        })
        assert outsider.status_code == 201
        with TestClient(create_app(settings), base_url=ORIGIN) as secretary:
            login(secretary, "outsider", "secretary-password")
            forbidden = secretary.post(f"/api/admin/events/{next_id}/registrations",
                                       headers=write_headers(secretary),
                                       json={"guest_id": first_id})
            assert forbidden.status_code == 403
        with factory() as session:
            assert session.query(Guest).count() == 3
            assert session.query(Wallet).count() == 3
            assert session.query(EventCharge).count() == 0


def test_concurrent_registration_stays_unique(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        event = Event(event_number=22, title="رقابت", registration_status="open")
        session.add(event)
        session.flush()
        event_id = event.id
    app = create_app(settings)
    member = {"first_name": "لیلا", "last_name": "آزمون", "phone": "۰۹۱۲۳۴۵۶۷۸۹"}

    def submit():
        with TestClient(app, base_url=ORIGIN) as client:
            response = client.post(f"/api/public/events/{event_id}/register",
                                   headers={"Origin": ORIGIN}, json={"members": [member]})
            assert response.status_code == 200, response.text
            return response.json()["results"][0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(result["status"] for result in results) == ["created", "error"]
    assert next(result for result in results if result["status"] == "error")["code"] == \
        "already_registered"
    with factory() as session:
        assert session.query(Guest).count() == 1
        assert session.query(Wallet).count() == 1
        assert session.query(Registration).count() == 1
