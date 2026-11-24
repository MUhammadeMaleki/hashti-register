from datetime import date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.api import events as event_api
from app.api import public as public_api
from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, Guest, Location, Setting
from app.seed import bootstrap_admin


def test_public_archive_uses_event_start_time_and_excludes_cancelled(
    management_environment, monkeypatch  # noqa: F811
):
    engine, settings = management_environment
    fixed_now = datetime(2026, 11, 24, 16, 0, tzinfo=ZoneInfo("Asia/Tehran"))

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz)

    monkeypatch.setattr(public_api, "datetime", FixedDateTime)
    factory = build_session_factory(engine)
    with factory() as session:
        with session.begin():
            session.add_all([
                Event(id=901, event_number=1, title="امروز گذشته", event_date=date(2026, 11, 24),
                      start_time=time(15, 59)),
                Event(id=902, event_number=2, title="الان", event_date=date(2026, 11, 24),
                      start_time=time(16, 0)),
                Event(id=903, event_number=3, title="امروز آینده", event_date=date(2026, 11, 24),
                      start_time=time(17, 0)),
                Event(id=904, event_number=4, title="زمان نامشخص"),
                Event(id=905, event_number=5, title="واردشده تاریخی",
                      is_historical_import=True),
                Event(id=906, event_number=6, title="لغوشده", event_date=date(2026, 11, 23),
                      is_cancelled=True),
            ])
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        upcoming = client.get("/api/public/events?period=upcoming").json()["items"]
        archive = client.get("/api/public/events?period=archive").json()["items"]
    assert {event["id"] for event in upcoming} == {902, 903, 904}
    assert {event["id"] for event in archive} == {901, 905}


def test_public_catalogue_poster_and_cancelled_access(
    management_environment, monkeypatch, tmp_path  # noqa: F811
):
    engine, settings = management_environment
    monkeypatch.setattr(event_api, "POSTER_DIR", tmp_path)
    monkeypatch.setattr(public_api, "POSTER_DIR", tmp_path)
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
        with session.begin():
            session.add_all([
                Setting(key="telegram_support_link", value="https://t.me/example"),
                Setting(key="card_number", value="1234"),
                Setting(key="private_secret", value="must-not-leak"),
            ])
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        secretary = client.post("/api/admin/users", headers=write_headers(client), json={
            "username": "secretary", "full_name": "دبیر", "password": "secretary-password",
        })
        assert secretary.status_code == 201
        secretary_ids = [secretary.json()["id"]]
        future = client.post("/api/admin/events", headers=write_headers(client), json={
            "event_number": 1, "title": "آینده", "event_date": str(today + timedelta(days=1)),
            "entry_fee": 0, "registration_status": "open", "secretary_ids": secretary_ids,
        })
        assert future.status_code == 201, future.text
        event_id = future.json()["id"]
        past = client.post("/api/admin/events", headers=write_headers(client), json={
            "event_number": 2, "title": "گذشته", "event_date": str(today - timedelta(days=1)),
            "secretary_ids": secretary_ids,
        })
        assert past.status_code == 201, past.text
        past_id = past.json()["id"]

        with factory() as session:
            with session.begin():
                session.add(Guest(first_name="مهمان", last_name="نمونه", phone="09123456789"))
                session.add(Location(title="کافه نمونه", address="تهران"))
        stats = client.get("/api/public/stats")
        assert stats.status_code == 200
        assert stats.json() == {"cafe_count": 1, "guest_count": 1, "event_count": 2}

        upcoming = client.get("/api/public/events?period=upcoming")
        assert upcoming.status_code == 200
        assert [item["id"] for item in upcoming.json()["items"]] == [event_id]
        assert [item["id"] for item in client.get(
            "/api/public/events?period=archive"
        ).json()["items"]] == [past_id]
        detail = client.get(f"/api/public/events/{event_id}").json()
        assert "capacity" not in detail and "secretaries" not in detail
        assert "linked_event_count" not in str(detail)
        assert detail["poster_url"] is None
        assert client.get(f"/api/public/events/{event_id}/poster").status_code == 404

        invalid = client.post(f"/api/admin/events/{event_id}/poster",
                              headers=write_headers(client),
                              files={"poster": ("bad.png", b"not an image", "image/png")})
        assert invalid.status_code == 422
        mismatch = client.post(f"/api/admin/events/{event_id}/poster",
                               headers=write_headers(client),
                               files={"poster": ("bad.jpg", b"\x89PNG\r\n\x1a\n", "image/jpeg")})
        assert mismatch.status_code == 422
        image = BytesIO()
        Image.new("RGB", (32, 48), "blue").save(image, format="PNG")
        uploaded = client.post(f"/api/admin/events/{event_id}/poster",
                               headers=write_headers(client),
                               files={"poster": ("poster.png", image.getvalue(), "image/png")})
        assert uploaded.status_code == 200, uploaded.text
        poster = client.get(f"/api/public/events/{event_id}/poster")
        assert poster.status_code == 200 and poster.headers["content-type"] == "image/jpeg"
        assert poster.content.startswith(b"\xff\xd8")
        heif = BytesIO()
        Image.new("RGB", (32, 48), "red").save(heif, format="HEIF")
        uploaded_heif = client.post(f"/api/admin/events/{event_id}/poster",
                                    headers=write_headers(client),
                                    files={"poster": (
                                        "poster.heif", heif.getvalue(), "image/heif",
                                    )})
        assert uploaded_heif.status_code == 200, uploaded_heif.text
        assert client.get(f"/api/public/events/{event_id}/poster").content.startswith(b"\xff\xd8")

        settings_response = client.get("/api/public/settings/public").json()
        assert settings_response["telegram_support_link"] == "https://t.me/example"
        assert settings_response["card_number"] == "1234"
        assert "private_secret" not in settings_response

        with factory() as session:
            with session.begin():
                event = session.get(Event, event_id)
                event.is_cancelled = True
        assert client.get(f"/api/public/events/{event_id}").status_code == 404
        assert client.get(f"/api/public/events/{event_id}/poster").status_code == 404
        assert client.get("/api/public/events?period=upcoming").json()["items"] == []
        assert client.get("/api/public/stats").json()["event_count"] == 1
