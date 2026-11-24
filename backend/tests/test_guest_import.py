"""Excel contact import is previewed and committed without duplicate profiles."""

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Guest, GuestAccount, Registration, Wallet
from app.seed import bootstrap_admin


def file_bytes(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    result = BytesIO()
    book.save(result)
    return result.getvalue()


def test_preview_confirm_errors_and_retry(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    content = file_bytes([
        ["نام", "نام خانوادگی", "شماره موبایل", "سن", "جنسیت", "تحصیلات", "یادداشت"],
        ["علی", "نمونه", "۰۹۱۲۳۴۵۶۷۸۹", 24, "مرد", "کارشناسی", "یادداشت"],
        ["تکراری", "نمونه", "09123456789"],
        ["بدون", "موبایل", "invalid"],
        ["مینا", "نمونه", "+989123456790", 31],
    ])
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        assert client.get("/api/admin/import/template").status_code == 401
        login(client, "boss", "boss-password-123")
        template = client.get("/api/admin/import/template")
        assert load_workbook(BytesIO(template.content), read_only=True).active["C1"].value == (
            "شماره موبایل")
        assert client.post("/api/admin/import/preview", files={"file": (
            "guests.xlsx", content)}).status_code == 403
        preview = client.post("/api/admin/import/preview", headers=write_headers(client),
                              files={"file": ("guests.xlsx", content)})
        assert preview.status_code == 200, preview.text
        data = preview.json()
        assert (data["total"], data["valid_count"], data["error_count"]) == (4, 2, 2)
        assert [item["row"] for item in data["errors"]] == [3, 4]
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Guest)) == 0
        changed = file_bytes([["نام", "نام خانوادگی", "شماره موبایل"]])
        bad = client.post("/api/admin/import/confirm", headers=write_headers(client),
                          data={"preview_token": data["preview_token"]},
                          files={"file": ("guests.xlsx", changed)})
        assert bad.status_code == 422
        confirmed = client.post("/api/admin/import/confirm", headers=write_headers(client),
                                data={"preview_token": data["preview_token"]},
                                files={"file": ("guests.xlsx", content)})
        assert confirmed.status_code == 200, confirmed.text
        assert (confirmed.json()["imported_count"], confirmed.json()["error_count"]) == (2, 2)
        retry = client.post("/api/admin/import/confirm", headers=write_headers(client),
                            data={"preview_token": data["preview_token"]},
                            files={"file": ("guests.xlsx", content)})
        assert retry.status_code == 200
        assert (retry.json()["imported_count"], retry.json()["error_count"]) == (0, 4)
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Guest)) == 2
            assert session.scalar(select(func.count()).select_from(Wallet)) == 2
            assert session.scalar(select(func.count()).select_from(GuestAccount)) == 0
            assert session.scalar(select(func.count()).select_from(Registration)) == 0
            assert set(session.scalars(select(Wallet.balance))) == {0}
            assert set(session.scalars(select(Guest.phone))) == {
                "09123456789", "09123456790"}


def test_invalid_columns_and_formula_are_rejected(management_environment):  # noqa: F811
    engine, settings = management_environment
    with build_session_factory(engine)() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        missing = file_bytes([["نام", "شماره موبایل"], ["علی", "09123456789"]])
        assert client.post("/api/admin/import/preview", headers=write_headers(client),
                           files={"file": ("missing.xlsx", missing)}).status_code == 422
        assert client.post("/api/admin/import/preview", headers=write_headers(client),
                           files={"file": ("broken.xlsx", b"not an xlsx")}).status_code == 422
        formula = file_bytes([["نام", "نام خانوادگی", "شماره موبایل"],
                              ["=1+1", "نمونه", "09123456789"]])
        result = client.post("/api/admin/import/preview", headers=write_headers(client),
                             files={"file": ("formula.xlsx", formula)})
        assert result.status_code == 200
        assert result.json()["errors"] == [{"row": 2, "reason": "فرمول در فایل ورودی مجاز نیست"}]


def test_thousand_contacts_import_without_accounts(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    content = file_bytes([["نام", "نام خانوادگی", "شماره موبایل"]] + [
        ["مهمان", str(number), f"0912{number:07d}"] for number in range(1000)
    ])
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        preview = client.post("/api/admin/import/preview", headers=write_headers(client),
                              files={"file": ("guests.xlsx", content)})
        assert preview.status_code == 200, preview.text
        assert preview.json()["valid_count"] == 1000
        confirmed = client.post("/api/admin/import/confirm", headers=write_headers(client),
                                data={"preview_token": preview.json()["preview_token"]},
                                files={"file": ("guests.xlsx", content)})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["imported_count"] == 1000
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Guest)) == 1000
        assert session.scalar(select(func.count()).select_from(Wallet)) == 1000
        assert session.scalar(select(func.count()).select_from(GuestAccount)) == 0
