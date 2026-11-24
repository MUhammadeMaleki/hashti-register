"""H24: one complete daily workflow through the public and admin APIs."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_events import event_body, secretary
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401
from test_payments import guest, submit

from app.core.database import build_session_factory
from app.main import create_app
from app.models import (
    EventCharge,
    Guest,
    PaymentSubmission,
    Registration,
    Wallet,
    WalletTransaction,
)
from app.seed import bootstrap_admin
from app.services.finance import registration_finance


def mutation(client, path, key, body=None):
    return client.post(path, headers={**write_headers(client), "Idempotency-Key": key}, json=body)


def test_full_event_to_cancellation_journey(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with (TestClient(create_app(settings), base_url=ORIGIN) as admin,
          TestClient(create_app(settings), base_url=ORIGIN) as visitor):
        login(admin, "boss", "boss-password-123")
        secretary_id = secretary(admin, "daily-secretary")
        created = admin.post("/api/admin/events", headers=write_headers(admin),
                             json=event_body(901, entry_fee=100, capacity=3,
                                             event_date="2030-01-01",
                                             secretary_ids=[secretary_id]))
        assert created.status_code == 201, created.text
        event_id = created.json()["id"]
        assert visitor.get("/api/public/events?period=upcoming").json()["total"] == 1

        registered = visitor.post(f"/api/public/events/{event_id}/register",
                                  headers={"Origin": ORIGIN}, json={"members": [{
                                      "first_name": "مینا", "last_name": "نمونه",
                                      "phone": "09120001501",
                                  }]})
        assert registered.status_code == 200, registered.text
        assert registered.json()["results"][0]["status"] == "created"
        guest(visitor, "09120001501")  # Existing contact gains a login, not a second profile.
        listing = admin.get(f"/api/admin/events/{event_id}/registrations").json()
        registration_id = listing["items"][0]["id"]
        guest_id = listing["items"][0]["guest_id"]
        order_path = f"/api/admin/registrations/{registration_id}/orders"
        assert mutation(admin, order_path, "pending-order", {
            "description": "چای", "amount": 40,
        }).status_code == 409

        attended = mutation(admin, f"/api/admin/registrations/{registration_id}/attendance",
                            "present", {"attendance": "present"})
        assert attended.status_code == 200, attended.text
        order = mutation(admin, order_path, "tea", {"description": "چای", "amount": 40})
        assert order.status_code == 200, order.text
        receipt = submit(visitor, f"/api/me/events/{event_id}/payments", "receipt-1",
                         amount="200", code="H24-RECEIPT")
        assert receipt.status_code == 201, receipt.text
        approved = mutation(admin, f"/api/admin/payments/{receipt.json()['id']}/approve",
                            "approve-receipt")
        assert approved.status_code == 200, approved.text
        assert approved.json()["wallet_balance"] == 200
        settled = mutation(admin,
                           f"/api/admin/finance/registrations/{registration_id}/settlements",
                           "settle-140", {"amount": 140})
        assert settled.status_code == 200, settled.text
        assert (settled.json()["debt"], settled.json()["wallet_balance"]) == (0, 60)
        assert visitor.get("/api/me/wallet").status_code == 200

        cancelled = mutation(admin, f"/api/admin/events/{event_id}/cancel", "cancel-event")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["refunded_total"] == 140
        assert visitor.get("/api/public/events?period=upcoming").json()["total"] == 0
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Guest)) == 1
            assert session.get(Registration, registration_id).status == "cancelled"
            assert registration_finance(session, registration_id).debt == 0
            assert session.scalar(select(Wallet.balance).where(Wallet.guest_id == guest_id)) == 200
            assert session.scalar(select(func.count()).select_from(EventCharge).where(
                EventCharge.registration_id == registration_id,
                EventCharge.is_cancelled.is_(False))) == 0
            assert session.scalar(select(func.count()).select_from(PaymentSubmission)) == 1
            assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
                WalletTransaction.type == "refund")) == 1
