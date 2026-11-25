"""Historical event import preserves incomplete archive records without attendance."""

from datetime import date, time
from io import BytesIO

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, Location, Registration, User
from app.seed import bootstrap_admin
from app.services.event_import import parse_workbook


def file_bytes(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    result = BytesIO()
    book.save(result)
    return result.getvalue()


def test_archive_preview_accepts_jalali_and_gregorian_dates():
    content = file_bytes([
        ["شماره رویداد", "عنوان", "تاریخ"],
        [1, "شمسی با رقم لاتین", "1402/12/10"],
        [2, "شمسی با رقم فارسی", "۱۴۰۳/۰۱/۰۱"],
        [3, "شمسی با رقم عربی", "١٤٠٣-٠١-٠١"],
        [4, "میلادی متنی", "2024-02-29"],
        [5, "تاریخ اکسل", date(2024, 2, 29)],
        [6, "تاریخ شمسی نامعتبر", "1402/12/30"],
    ])
    valid, errors, total = parse_workbook(content)
    assert (total, len(valid), len(errors)) == (6, 5, 1)
    assert [item["event_date"] for item in valid] == [
        date(2024, 2, 29), date(2024, 3, 20), date(2024, 3, 20),
        date(2024, 2, 29), date(2024, 2, 29),
    ]
    assert errors[0]["row"] == 7
    assert "تاریخ نامعتبر" in errors[0]["reason"]


def test_archive_preview_confirm_and_retry(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        session.add(User(username="sec", full_name="دبیر", role="secretary",
                         password_hash=PasswordHasher().hash("secretary-password-123")))
    content = file_bytes([
        ["شماره رویداد", "عنوان", "تاریخ", "ساعت", "توضیحات", "نام مکان",
         "آدرس مکان", "هزینه ورودی", "یادداشت عمومی", "وضعیت ثبت‌نام"],
        [42, "رویداد قدیمی", date(2022, 4, 1), time(18, 30), "شرح", "خانه فرهنگ",
         "خیابان نمونه", 120000, "یادداشت", "بسته"],
        [42, "تکرار"],
        [43],
        [0, "نامعتبر"],
        [44, "مکان ناقص", date(2020, 1, 1), None, None, "نام مکان"],
    ])
    app = create_app(settings)
    with (TestClient(app, base_url=ORIGIN) as client,
          TestClient(app, base_url=ORIGIN) as secretary):
        assert client.get("/api/admin/import/events/template").status_code == 401
        login(client, "boss", "boss-password-123")
        login(secretary, "sec", "secretary-password-123")
        assert secretary.get("/api/admin/import/events/template").status_code == 403
        template = client.get("/api/admin/import/events/template")
        assert load_workbook(BytesIO(template.content), read_only=True).active["A1"].value == (
            "شماره رویداد")
        assert client.post("/api/admin/import/events/preview", files={"file": (
            "archive.xlsx", content)}).status_code == 403
        preview = client.post("/api/admin/import/events/preview", headers=write_headers(client),
                              files={"file": ("archive.xlsx", content)})
        assert preview.status_code == 200, preview.text
        data = preview.json()
        assert (data["total"], data["valid_count"], data["error_count"]) == (5, 3, 2)
        assert [item["row"] for item in data["errors"]] == [3, 5]
        assert data["preview_rows"][1]["title"] == "هشتی 43"
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Event)) == 0
        changed = file_bytes([["شماره رویداد"], [99]])
        assert client.post("/api/admin/import/events/confirm", headers=write_headers(client),
                           data={"preview_token": data["preview_token"]},
                           files={"file": ("archive.xlsx", changed)}).status_code == 422
        confirmed = client.post("/api/admin/import/events/confirm", headers=write_headers(client),
                                data={"preview_token": data["preview_token"]},
                                files={"file": ("archive.xlsx", content)})
        assert confirmed.status_code == 200, confirmed.text
        assert (confirmed.json()["imported_count"], confirmed.json()["error_count"]) == (3, 2)
        archive = client.get("/api/public/events?period=archive")
        assert archive.status_code == 200
        assert {item["event_number"] for item in archive.json()["items"]} == {42, 43, 44}
        upcoming = client.get("/api/public/events?period=upcoming")
        assert upcoming.status_code == 200
        assert upcoming.json()["total"] == 0
        retry = client.post("/api/admin/import/events/confirm", headers=write_headers(client),
                            data={"preview_token": data["preview_token"]},
                            files={"file": ("archive.xlsx", content)})
        assert retry.status_code == 200
        assert (retry.json()["imported_count"], retry.json()["error_count"]) == (0, 5)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 3
        assert session.scalar(select(func.count()).select_from(Location)) == 1
        assert session.scalar(select(func.count()).select_from(Registration)) == 0
        full = session.scalar(select(Event).where(Event.event_number == 42))
        assert full.poster_path is None
        assert (full.location_mode, full.entry_fee, full.registration_status) == (
            "exact", 120000, "closed")
        minimal = session.scalar(select(Event).where(Event.event_number == 43))
        assert (minimal.title, minimal.event_date, minimal.location_mode) == (
            "هشتی 43", None, "tba")
        assert minimal.is_historical_import is True
        partial = session.scalar(select(Event).where(Event.event_number == 44))
        assert partial.location_mode == "approximate"
        assert partial.location_text == "نام مکان"


def test_archive_existing_number_and_180_rows(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        session.add(Event(event_number=7, title="موجود"))
    content = file_bytes([["شماره رویداد", "عنوان", "تاریخ"]] + [
        [number, f"هشتی {number}", date(2020, 1, 1)] for number in range(1, 181)
    ])
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        preview = client.post("/api/admin/import/events/preview", headers=write_headers(client),
                              files={"file": ("archive.xlsx", content)})
        assert preview.status_code == 200, preview.text
        assert (preview.json()["valid_count"], preview.json()["error_count"]) == (179, 1)
        confirmed = client.post("/api/admin/import/events/confirm", headers=write_headers(client),
                                data={"preview_token": preview.json()["preview_token"]},
                                files={"file": ("archive.xlsx", content)})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["imported_count"] == 179
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Event)) == 180
        assert session.scalar(select(func.count()).select_from(Registration)) == 0
