"""Guest portal exposes only the signed-in guest's profile and finances."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_auth import HEADERS, ORIGIN, auth_environment  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, EventCharge, Guest, Registration, User, Wallet
from app.seed import bootstrap_admin
from app.services.auth import register_guest
from app.services.finance import append_transaction


def test_guest_portal_profile_history_wallet_and_ownership(auth_environment):  # noqa: F811
    engine, settings = auth_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
        first_id, _ = register_guest(session, first_name="اول", last_name="مهمان",
                                     phone="09120000021", password="guest-password-123",
                                     settings=settings)
        second_id, _ = register_guest(session, first_name="دوم", last_name="مهمان",
                                      phone="09120000022", password="guest-password-123",
                                      settings=settings)
    with factory() as session, session.begin():
        admin_id = session.scalar(select(User.id).where(User.username == "boss"))
        session.get(Guest, first_id).internal_note = "فقط برای دبیر"
        first_event = Event(event_number=91, title="رویداد اول", registration_status="open")
        cancelled_event = Event(event_number=92, title="لغوشده", registration_status="open")
        second_event = Event(event_number=93, title="رویداد دوم", registration_status="open")
        session.add_all([first_event, cancelled_event, second_event])
        session.flush()
        active = Registration(event_id=first_event.id, guest_id=first_id,
                              source="admin", attendance="present")
        cancelled = Registration(event_id=cancelled_event.id, guest_id=first_id,
                                 source="admin", status="cancelled", attendance="pending")
        other = Registration(event_id=second_event.id, guest_id=second_id,
                             source="admin", attendance="present")
        session.add_all([active, cancelled, other])
        session.flush()
        session.add(EventCharge(registration_id=active.id, type="entry",
                                description="ورودی", amount=100, created_by=admin_id))
        first_registration_id = active.id
        first_event_id = first_event.id
        for guest_id, credit in [(first_id, 200), (second_id, 400)]:
            wallet = session.scalar(select(Wallet).where(Wallet.guest_id == guest_id))
            append_transaction(session, wallet=wallet, type="manual_adjust", amount=credit,
                               actor_type="user", actor_id=admin_id,
                               key=f"portal-credit-{guest_id}", note="اعتبار آزمایشی")

    with TestClient(create_app(settings), base_url=ORIGIN) as first:
        assert first.get("/api/me/profile").status_code == 401
        login = first.post("/api/auth/guest/login", headers=HEADERS,
                           json={"phone": "09120000021", "password": "guest-password-123"})
        assert login.status_code == 200
        profile = first.get("/api/me/profile").json()
        assert profile["id"] == first_id
        assert profile["phone"] == "09120000021"
        assert "internal_note" not in profile
        registrations = first.get("/api/me/registrations").json()
        assert [row["id"] for row in registrations] == [first_registration_id]
        assert registrations[0]["debt"] == 100
        assert registrations[0]["time_mode"] == "tba"
        assert registrations[0]["location_title"] is None
        assert registrations[0]["poster_url"] is None
        assert registrations[0]["entry_fee"] == 0
        assert first.get("/api/me/finance").json()["registrations"][0]["event_number"] == 91
        wallet = first.get("/api/me/wallet").json()
        assert wallet["balance"] == 200
        assert wallet["event_debts"][0]["debt"] == 100
        assert [row["amount"] for row in first.get("/api/me/wallet/transactions").json()] == [200]

        receipt = first.post("/api/me/payments", headers={**HEADERS,
                             "X-CSRF-Token": first.cookies.get("hashti_csrf"),
                             "Idempotency-Key": "portal-receipt-1"},
                             data={"amount": "50", "tracking_code": "tracking-1"})
        assert receipt.status_code == 201
        assert receipt.json()["event_id"] is None
        assert [row["id"] for row in first.get("/api/me/payments").json()] == [receipt.json()["id"]]

        settled = first.post(f"/api/me/registrations/{first_registration_id}/settlements",
                             headers={**HEADERS, "X-CSRF-Token": first.cookies.get("hashti_csrf"),
                                      "Idempotency-Key": "portal-settle-1"},
                             json={"amount": 100})
        assert settled.status_code == 200
        assert first.get("/api/me/wallet").json()["balance"] == 100
        assert first.get("/api/me/registrations").json()[0]["debt"] == 0
        assert len(first.get("/api/me/wallet/transactions").json()) == 2

    with TestClient(create_app(settings), base_url=ORIGIN) as second:
        second.post("/api/auth/guest/login", headers=HEADERS,
                    json={"phone": "09120000022", "password": "guest-password-123"})
        assert second.get("/api/me/profile").json()["id"] == second_id
        assert second.get("/api/me/wallet").json()["balance"] == 400
        assert second.get("/api/me/registrations").json()[0]["event_number"] == 93
        assert [row["amount"] for row in second.get("/api/me/wallet/transactions").json()] == [400]
        assert second.get("/api/me/payments").json() == []
        denied = second.post(f"/api/me/registrations/{first_registration_id}/settlements",
                             headers={**HEADERS, "X-CSRF-Token": second.cookies.get("hashti_csrf"),
                                      "Idempotency-Key": "portal-other-settle"},
                             json={"amount": 1})
        assert denied.status_code in {403, 404}
        other_receipt = second.post(
            f"/api/me/events/{first_event_id}/payments",
            headers={**HEADERS, "X-CSRF-Token": second.cookies.get("hashti_csrf"),
                     "Idempotency-Key": "portal-other-receipt"},
            data={"amount": "50", "tracking_code": "tracking-2"},
        )
        assert other_receipt.status_code in {403, 404}
