"""Reports reconcile with ledger data without granting edit permissions."""

from datetime import date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from test_management import HEADERS, ORIGIN, login, management_environment  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import (
    Event,
    EventCharge,
    Guest,
    GuestInterestTag,
    InterestTag,
    PaymentSubmission,
    Registration,
    User,
    Wallet,
)
from app.seed import bootstrap_admin
from app.services.finance import append_transaction
from app.services.report_exports import workbook_bytes
from app.services.reports import dashboard


def test_dashboard_includes_approximate_and_unannounced_upcoming_events(db_session):
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    events = [
        Event(event_number=501, title="دقیق", event_date=today + timedelta(days=1),
              time_mode="exact"),
        Event(event_number=502, title="تقریبی", time_mode="approximate",
              time_text="در حال هماهنگی"),
        Event(event_number=503, title="اعلام بعدی", time_mode="tba"),
        Event(event_number=504, title="گذشته", event_date=today - timedelta(days=1)),
        Event(event_number=505, title="لغوشده", is_cancelled=True),
        Event(event_number=506, title="آرشیوی", is_historical_import=True),
        Event(event_number=507, title="امروز برگزارشده", event_date=today,
              start_time=time.min),
    ]
    db_session.add_all(events)
    db_session.flush()
    rows = [{"event_id": event.id, "guest_id": index, "debt": 0, "status": "active"}
            for index, event in enumerate(events)]
    result = dashboard(db_session, rows)
    assert result["upcoming_event_count"] == 3
    assert result["upcoming_registration_count"] == 3
    assert result["held_event_count"] == 3


def test_reports_totals_filters_permissions_and_reconciliation(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        admin_id = session.scalar(select(User.id).where(User.username == "boss"))
        secretary = User(username="reader", full_name="دبیر گزارش", role="secretary",
                         password_hash=PasswordHasher().hash("reader-password-123"))
        guests = [Guest(first_name=name, last_name="نمونه", phone=f"0912000003{index}")
                  for index, name in enumerate(["اول", "دوم", "سوم"])]
        upcoming = Event(event_number=41, title="آینده", event_date=date.today() + timedelta(1),
                         registration_status="open")
        held = Event(event_number=42, title="گذشته", event_date=date.today() - timedelta(1),
                     registration_status="closed")
        tag = InterestTag(name="موسیقی")
        session.add_all([secretary, *guests, upcoming, held, tag])
        session.flush()
        session.add(GuestInterestTag(guest_id=guests[0].id, tag_id=tag.id))
        wallets = [Wallet(guest_id=guest.id, balance=0) for guest in guests]
        session.add_all(wallets)
        first = Registration(event_id=upcoming.id, guest_id=guests[0].id,
                             source="admin", attendance="present")
        second = Registration(event_id=upcoming.id, guest_id=guests[1].id,
                              source="admin", attendance="present")
        cancelled = Registration(event_id=upcoming.id, guest_id=guests[2].id,
                                 source="admin", status="cancelled", attendance="pending")
        previous = Registration(event_id=held.id, guest_id=guests[1].id,
                                source="admin", attendance="present")
        session.add_all([first, second, cancelled, previous])
        session.flush()
        session.add_all([
            EventCharge(registration_id=first.id, type="entry", description="ورودی",
                        amount=100, created_by=admin_id),
            EventCharge(registration_id=first.id, type="order", description="سفارش",
                        amount=50, created_by=admin_id),
            EventCharge(registration_id=second.id, type="entry", description="ورودی",
                        amount=100, created_by=admin_id),
            EventCharge(registration_id=previous.id, type="entry", description="ورودی",
                        amount=80, created_by=admin_id),
        ])
        session.flush()
        append_transaction(session, wallet=wallets[0], type="manual_adjust", amount=100,
                           actor_type="user", actor_id=admin_id, key="report-credit-1", note="شارژ")
        append_transaction(session, wallet=wallets[0], type="settlement", amount=-50,
                           registration_id=first.id, actor_type="user", actor_id=admin_id,
                           key="report-settle-1")
        append_transaction(session, wallet=wallets[1], type="manual_adjust", amount=200,
                           actor_type="user", actor_id=admin_id, key="report-credit-2", note="شارژ")
        original = append_transaction(session, wallet=wallets[1], type="settlement", amount=-80,
                                      registration_id=previous.id, actor_type="user",
                                      actor_id=admin_id, key="report-settle-2")
        append_transaction(session, wallet=wallets[1], type="refund", amount=20,
                           registration_id=previous.id, original_transaction_id=original.id,
                           actor_type="user", actor_id=admin_id, key="report-refund-2")
        session.add(PaymentSubmission(guest_id=guests[2].id, amount=25,
                                      tracking_code="report-pending", status="pending",
                                      idempotency_key="report-pending"))
        event_id, first_guest_id, tag_id = upcoming.id, guests[0].id, tag.id
        wallet_id = wallets[0].id

    app = create_app(settings)
    with (TestClient(app, base_url=ORIGIN) as reader,
          TestClient(app, base_url=ORIGIN) as boss):
        assert reader.get("/api/admin/reports/dashboard").status_code == 401
        assert reader.get("/api/admin/reports/export/guests").status_code == 401
        login(reader, "reader", "reader-password-123")
        login(boss, "boss", "boss-password-123")
        report = reader.get(f"/api/admin/reports/events/{event_id}")
        assert report.status_code == 200
        event = report.json()
        assert (event["present_count"], event["entry_total"], event["orders_total"]) == (2, 200, 50)
        assert (event["charges_total"], event["settled_total"], event["debt_total"]) == (
            250, 50, 200)
        assert event["unsettled_count"] == 2
        assert len(event["debtors"]) == 2
        assert reader.put(f"/api/admin/events/{event_id}/secretaries",
                          headers={**HEADERS, "X-CSRF-Token": reader.cookies.get("hashti_csrf")},
                          json={"user_ids": []}).status_code == 403

        dashboard = reader.get("/api/admin/reports/dashboard").json()
        assert dashboard == {"guest_count": 3, "upcoming_event_count": 1,
                             "upcoming_registration_count": 2, "pending_receipt_count": 1,
                             "debtor_count": 2, "total_debt": 220, "held_event_count": 1}
        finance = reader.get("/api/admin/reports/finance?debtors_only=true").json()
        assert finance["total"] == 1
        assert finance["items"][0]["guest_id"] == first_guest_id
        assert finance["items"][0]["net_debt"] == 50
        assert reader.get("/api/admin/reports/guests?interest_tag_id=" + str(tag_id)).json()[
            "total"] == 1
        assert reader.get("/api/admin/reports/guests?guest_kind=returning").json()[
            "items"][0]["name"] == "دوم نمونه"
        assert reader.get("/api/admin/reports/guests?attendance=present").json()[
            "total"] == 2
        export = reader.get(f"/api/admin/reports/export/guests?interest_tag_id={tag_id}")
        assert export.status_code == 200
        assert export.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        assert export.headers["cache-control"] == "private, no-store"
        sheet = load_workbook(BytesIO(export.content), read_only=True).active
        assert sheet["B4"].value == 1
        assert sheet["A3"].value == "اول نمونه"
        assert sheet["F3"].value == 50
        assert sheet["F4"].value == 50
        finance_export = reader.get("/api/admin/reports/export/finance?debtors_only=true")
        finance_sheet = load_workbook(BytesIO(finance_export.content), read_only=True).active
        assert finance_sheet["B4"].value == finance["total"]
        assert finance_sheet["E3"].value == finance["items"][0]["net_debt"]
        event_export = reader.get(f"/api/admin/reports/export/events/{event_id}?q=اول")
        event_sheet = load_workbook(BytesIO(event_export.content), read_only=True).active
        assert event_sheet["B4"].value == 1
        assert event_sheet["D3"].value == 0  # discount
        assert event_sheet["F3"].value == 100  # remaining debt
        assert reader.get("/api/admin/reports/export/guests?date_from=2030-01-02"
                          "&date_to=2029-01-01").status_code == 422
        assert reader.get("/api/admin/reports/guests?date_from=2030-01-02&date_to=2029-01-01"
                          ).status_code == 422
        charts = reader.get("/api/admin/reports/charts").json()
        assert charts["attendance_ratio"] == {"present": 3, "absent": 0}
        assert charts["new_vs_returning"] == {"new": 1, "returning": 1}
        assert charts["attendance_buckets"]["1-2"] == 2
        assert charts["interests"][0] == {"name": "موسیقی", "count": 1}
        filtered_charts = reader.get(
            f"/api/admin/reports/charts?event_id={event_id}&interest_tag_id={tag_id}"
        ).json()
        assert filtered_charts["attendance_ratio"] == {"present": 1, "absent": 0}
        assert filtered_charts["new_vs_returning"] == {"new": 1, "returning": 0}
        assert reader.get("/api/admin/finance/reconciliation").status_code == 403
        with factory() as session, session.begin():
            session.get(Wallet, wallet_id).balance += 1
        mismatch = boss.get(f"/api/admin/finance/reconciliation?guest_id={first_guest_id}").json()
        assert mismatch["items"][0]["difference"] == 1
        with factory() as session:
            assert session.get(Wallet, wallet_id).balance == 51


def test_excel_user_text_is_not_a_formula():
    data = workbook_bytes("گزارش", [("مهمان", "name"), ("مبلغ", "debt")],
                          [{"name": " =HYPERLINK(\"https://bad.example\")", "debt": 12}],
                          total_keys=("debt",))
    sheet = load_workbook(BytesIO(data), read_only=True).active
    assert sheet["A3"].data_type == "s"
    assert sheet["A3"].value.startswith("' =HYPERLINK")
    assert sheet["B3"].value == 12
