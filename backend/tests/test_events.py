from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_management import HEADERS, ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, EventSecretary, Registration
from app.seed import bootstrap_admin
from app.services.guests import create_guest_with_wallet


def secretary(client, username):
    response = client.post(
        "/api/admin/users", headers=write_headers(client),
        json={"username": username, "full_name": username, "password": "secretary-password"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def event_body(number, location_id=None, **extra):
    return {
        "event_number": number,
        "title": f"هشتی {number}",
        "event_date": "2020-01-01",
        "start_time": "18:00:00",
        "time_mode": "exact" if location_id else "tba",
        "location_mode": "exact" if location_id else "tba",
        "location_id": location_id,
        "entry_fee": 10000,
        "capacity": 1,
        "registration_status": "open",
        "hosts": "میزبان یک، میزبان دو",
        **extra,
    }


def test_event_list_search_filters_and_pagination(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        session.add_all([
            Event(event_number=81, title="گفت‌وگوی آینده", event_date=today + timedelta(days=1),
                  registration_status="open", hosts="مریم"),
            Event(event_number=82, title="هشتی بی‌تاریخ", time_mode="approximate",
                  time_text="در حال هماهنگی", registration_status="open"),
            Event(event_number=83, title="هشتی گذشته", event_date=today - timedelta(days=1)),
            Event(event_number=84, title="هشتی لغوشده", is_cancelled=True),
        ])
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        upcoming = client.get("/api/admin/events?period=upcoming&registration_status=open")
        assert upcoming.status_code == 200
        assert upcoming.json()["total"] == 2
        assert {item["event_number"] for item in upcoming.json()["items"]} == {81, 82}
        assert client.get("/api/admin/events?period=archive").json()["total"] == 1
        assert client.get("/api/admin/events?period=cancelled").json()["total"] == 1
        assert client.get("/api/admin/events?q=مریم").json()["items"][0]["event_number"] == 81
        assert client.get("/api/admin/events?q=۸۲").json()["items"][0]["event_number"] == 82
        page = client.get("/api/admin/events?period=upcoming&limit=1&offset=1").json()
        assert page["total"] == 2 and len(page["items"]) == 1


def test_time_and_location_modes_are_independent(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        secretary_id = secretary(client, "sec")
        place = client.post("/api/admin/locations", headers=write_headers(client),
                            json={"title": "کافه", "address": "نشانی", "map_link": None})
        assert place.status_code == 201, place.text
        location_id = place.json()["id"]
        base = {"title": "رویداد", "secretary_ids": [secretary_id]}
        cases = [
            ({"time_mode": "exact", "event_date": "2026-12-01",
              "start_time": "18:00:00", "location_mode": "tba"}, 201),
            ({"time_mode": "approximate", "time_text": "جمعه، ساعت در حال هماهنگی",
              "location_mode": "exact", "location_id": location_id}, 201),
            ({"time_mode": "tba", "location_mode": "approximate",
              "location_text": "مرکز شهر"}, 201),
            ({"time_mode": "exact", "event_date": "2026-12-01",
              "location_mode": "tba"}, 422),
            ({"time_mode": "approximate", "time_text": "  ",
              "location_mode": "tba"}, 422),
            ({"time_mode": "tba", "location_mode": "exact"}, 422),
            ({"time_mode": "tba", "location_mode": "approximate",
              "location_text": "  "}, 422),
        ]
        for number, (fields, status) in enumerate(cases, start=1):
            result = client.post("/api/admin/events", headers=write_headers(client),
                                 json={**base, **fields, "event_number": number})
            assert result.status_code == status, result.text
            if status == 201:
                public = client.get(f"/api/public/events/{result.json()['id']}")
                assert public.status_code == 200
                assert public.json()["time_mode"] == fields["time_mode"]
                assert public.json()["location_mode"] == fields["location_mode"]


def test_event_assignment_shared_location_and_history(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    app = create_app(settings)
    with (
        TestClient(app, base_url=ORIGIN) as boss,
        TestClient(app, base_url=ORIGIN) as first_client,
        TestClient(app, base_url=ORIGIN) as second_client,
    ):
        login(boss, "boss", "boss-password-123")
        first_id = secretary(boss, "first")
        second_id = secretary(boss, "second")
        login(first_client, "first", "secretary-password")
        login(second_client, "second", "secretary-password")
        location_response = boss.post(
            "/api/admin/locations", headers=write_headers(boss),
            json={"title": "کافه", "address": "نشانی قدیم", "map_link": None},
        )
        assert location_response.status_code == 201, location_response.text
        location_id = location_response.json()["id"]
        assert first_client.post(
            "/api/admin/events", headers=write_headers(first_client),
            json=event_body(1, location_id, start_time=None),
        ).status_code == 422
        created = first_client.post(
            "/api/admin/events", headers=write_headers(first_client),
            json=event_body(1, location_id),
        )
        assert created.status_code == 201, created.text
        first_event = created.json()["id"]
        assert created.json()["secretaries"][0]["id"] == first_id
        assert created.json()["event_date"] == "2020-01-01"  # Past dates are allowed.
        assert boss.get("/api/admin/events/next-number").json()["suggested_number"] == 2
        created = second_client.post(
            "/api/admin/events", headers=write_headers(second_client),
            json=event_body(2, location_id),
        )
        assert created.status_code == 201, created.text
        second_event = created.json()["id"]
        assert second_client.patch(
            f"/api/admin/events/{first_event}", headers=write_headers(second_client),
            json={"title": "غیرمجاز"},
        ).status_code == 403
        assert first_client.patch(
            f"/api/admin/events/{first_event}", headers=write_headers(first_client),
            json={"title": "عنوان تازه", "registration_status": "closed"},
        ).status_code == 200
        assert first_client.patch(
            f"/api/admin/locations/{location_id}", headers=write_headers(first_client),
            json={"title": "کافه", "address": "نشانی تازه", "map_link": None},
        ).status_code == 403
        changed = boss.patch(
            f"/api/admin/locations/{location_id}", headers=write_headers(boss),
            json={"title": "کافه جدید", "address": "نشانی تازه", "map_link": None},
        )
        assert changed.status_code == 200, changed.text
        first_location = boss.get(f"/api/admin/events/{first_event}").json()["location"]
        second_location = boss.get(f"/api/admin/events/{second_event}").json()["location"]
        assert first_location["address"] == "نشانی تازه"
        assert second_location["title"] == "کافه جدید"
        assert boss.delete(
            f"/api/admin/locations/{location_id}", headers=write_headers(boss)
        ).status_code == 409
        assert boss.post(
            "/api/admin/events", headers=write_headers(boss),
            json=event_body(1, secretary_ids=[second_id]),
        ).status_code == 409
        with factory() as session:
            guest_a = create_guest_with_wallet(
                session, first_name="الف", last_name="مهمان", phone="09120000121"
            )
            guest_b = create_guest_with_wallet(
                session, first_name="ب", last_name="مهمان", phone="09120000122"
            )
        with factory() as session, session.begin():
            session.add_all([
                Registration(event_id=first_event, guest_id=guest_a.guest_id, source="admin"),
                Registration(event_id=first_event, guest_id=guest_b.guest_id, source="admin"),
            ])
        assert boss.get(f"/api/admin/events/{first_event}").json()["capacity"] == 1
        assert first_client.patch(
            f"/api/admin/events/{first_event}", headers=write_headers(first_client),
            json={"entry_fee": 15000},
        ).status_code == 409
        assert first_client.delete(
            f"/api/admin/events/{first_event}", headers=write_headers(first_client)
        ).status_code == 409
        assert boss.patch(
            f"/api/admin/users/{first_id}", headers=write_headers(boss),
            json={"is_active": False},
        ).status_code == 200
        reassigned = boss.put(
            f"/api/admin/events/{first_event}/secretaries", headers=write_headers(boss),
            json={"user_ids": [second_id]},
        )
        assert reassigned.status_code == 200, reassigned.text
        assert {person["id"] for person in reassigned.json()["secretaries"]} == {
            first_id, second_id
        }
        secretaries = boss.get(f"/api/admin/events/{first_event}").json()["secretaries"]
        assert secretaries[0]["is_active"] is False
        with factory() as session:
            assert session.get(EventSecretary, (first_event, first_id)) is not None
            assert session.scalar(select(Event.event_number).where(Event.id == first_event)) == 1


def test_concurrent_number_collision_and_safe_deletes(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    app = create_app(settings)
    with TestClient(app, base_url=ORIGIN) as admin:
        login(admin, "boss", "boss-password-123")
        secretary_id = secretary(admin, "first")
        empty = admin.post(
            "/api/admin/events", headers=write_headers(admin),
            json=event_body(8, secretary_ids=[secretary_id]),
        )
        assert empty.status_code == 201, empty.text
        assert admin.delete(
            f"/api/admin/events/{empty.json()['id']}", headers=write_headers(admin)
        ).status_code == 204
        location = admin.post(
            "/api/admin/locations", headers=write_headers(admin),
            json={"title": "مکان موقت", "address": "نشانی", "map_link": None},
        )
        assert admin.delete(
            f"/api/admin/locations/{location.json()['id']}", headers=write_headers(admin)
        ).status_code == 204

    def create_once():
        with TestClient(app, base_url=ORIGIN) as client:
            login(client, "boss", "boss-password-123")
            return client.post(
                "/api/admin/events", headers=write_headers(client),
                json=event_body(9, secretary_ids=[secretary_id]),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_once(), range(2)))
    assert sorted(results) == [201, 409]
    with factory() as session:
        assert session.scalar(select(Event.event_number).where(Event.event_number == 9)) == 9


def test_cancel_compacts_future_numbers_and_reactivation_gets_next_free(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        events = [Event(event_number=number, title=f"هشتی {number}",
                        event_date=today - timedelta(days=1) if number == 1
                        else today + timedelta(days=1)) for number in range(1, 5)]
        session.add_all(events)
        session.flush()
        ids = [event.id for event in events]
    with TestClient(create_app(settings), base_url=ORIGIN) as admin:
        login(admin, "boss", "boss-password-123")
        cancel = admin.post(f"/api/admin/events/{ids[1]}/cancel", headers={
            **write_headers(admin), "Idempotency-Key": "cancel-second"})
        assert cancel.status_code == 200, cancel.text
        with factory() as session:
            rows = [session.get(Event, event_id) for event_id in ids]
            assert [row.event_number for row in rows] == [1, 2, 2, 3]
            assert rows[1].number_released is True
            assert rows[0].event_number == 1
        assert admin.get("/api/admin/events/next-number").json()["suggested_number"] == 4
        secretary_id = secretary(admin, "numbers-secretary")
        created = admin.post("/api/admin/events", headers=write_headers(admin),
                             json=event_body(4, event_date=str(today + timedelta(days=2)),
                                             start_time=None,
                                             secretary_ids=[secretary_id]))
        assert created.status_code == 201, created.text
        restored = admin.post(f"/api/admin/events/{ids[1]}/reactivate", headers={
            **write_headers(admin), "Idempotency-Key": "restore-second"})
        assert restored.status_code == 200, restored.text
        assert restored.json()["event_number"] == 5
        with factory() as session:
            assert session.get(Event, ids[1]).number_released is False
            assert session.get(Event, ids[1]).event_number == 5
        archived = admin.patch(f"/api/admin/events/{ids[0]}",
                               headers=write_headers(admin), json={"event_number": 9})
        assert archived.status_code == 409
        assert archived.json()["detail"] == "event_number_archived"
        archived_cancel = admin.post(f"/api/admin/events/{ids[0]}/cancel", headers={
            **write_headers(admin), "Idempotency-Key": "cancel-archived"})
        assert archived_cancel.status_code == 200, archived_cancel.text
        with factory() as session:
            past = session.get(Event, ids[0])
            assert past.event_number == 1
            assert past.number_released is False
