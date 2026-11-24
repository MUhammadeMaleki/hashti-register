"""H15 settlement, manual adjustment and linked refund on real PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_charges import mutation, seed
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import AuditLog, Event, Guest, Registration, Setting, Wallet, WalletTransaction
from app.seed import bootstrap_admin
from app.services.auth import Actor
from app.services.finance import FinanceError, registration_finance
from app.services.settlements import settle_registration


def setup_admin(engine):
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")


def make_present(client, registration_id):
    response = mutation(client, "POST",
                        f"/api/admin/registrations/{registration_id}/attendance",
                        f"attendance-{registration_id}", {"attendance": "present"})
    assert response.status_code == 200, response.text


def test_manual_adjustment_settlement_and_debt_ceiling(management_environment):  # noqa: F811
    engine, settings = management_environment
    setup_admin(engine)
    event_id, registration_id, wallet_id = seed(engine, number=51)
    _, _, payer_wallet_id = seed(engine, number=56)
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        session.add(Setting(key="default_debt_ceiling", value=50))
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        make_present(client, registration_id)
        listing = client.get(f"/api/admin/events/{event_id}/registrations").json()
        guest_id = listing["items"][0]["guest_id"]
        profile = client.get(f"/api/admin/guests/{guest_id}").json()
        assert profile["finance_overview"] == {"total_debt": 100, "net_debt": 100,
                                               "debt_ceiling": 50, "over_ceiling": True}
        with factory() as session, session.begin():
            session.get(Guest, guest_id).debt_ceiling = 120
        specific = client.get(f"/api/admin/guests/{guest_id}").json()["finance_overview"]
        assert specific["debt_ceiling"] == 120 and specific["over_ceiling"] is False
        adjustment = f"/api/admin/finance/guests/{guest_id}/adjustments"
        credit = mutation(client, "POST", adjustment, "credit",
                          {"amount": 150, "note": "پرداخت دوست به گیرنده"})
        assert credit.status_code == 200, credit.text
        assert mutation(client, "POST", adjustment, "credit",
                        {"amount": 150, "note": "پرداخت دوست به گیرنده"}).json() == credit.json()
        assert mutation(client, "POST", adjustment, "blank",
                        {"amount": 10, "note": "   "}).status_code == 422
        assert mutation(client, "POST", adjustment, "overdraft",
                        {"amount": -151, "note": "برداشت"}).status_code == 409
        with factory() as session:
            assert session.get(Wallet, wallet_id).balance == 150
            assert session.get(Wallet, payer_wallet_id).balance == 0
            assert registration_finance(session, registration_id).debt == 100
        profile = client.get(f"/api/admin/guests/{guest_id}").json()
        assert profile["finance_overview"]["net_debt"] == -50
        assert profile["finance_overview"]["over_ceiling"] is False
        assert profile["wallet_transactions"][0]["actor_name"] == "مدیر"
        assert mutation(client, "POST", adjustment, "debit",
                        {"amount": -40, "note": "بازپرداخت نقدی"}).status_code == 200
        settlement = f"/api/admin/finance/registrations/{registration_id}/settlements"
        assert mutation(client, "POST", settlement, "over-debt", {"amount": 101}).status_code == 409
        assert mutation(client, "POST", settlement, "over-balance",
                        {"amount": 111}).status_code == 409
        partial = mutation(client, "POST", settlement, "part", {"amount": 60})
        assert partial.status_code == 200 and partial.json()["debt"] == 40
        assert mutation(client, "POST", settlement, "part", {"amount": 60}).json() == partial.json()
        assert mutation(client, "POST", settlement, "too-much", {"amount": 41}).status_code == 409
        full = mutation(client, "POST", settlement, "rest", {"amount": 40})
        assert full.status_code == 200 and full.json()["debt"] == 0
        assert full.json()["wallet_balance"] == 10
        with factory() as session:
            assert session.get(Wallet, wallet_id).balance == 10
            assert session.scalar(select(func.count()).select_from(WalletTransaction).where(
                WalletTransaction.type == "settlement")) == 2
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "wallet.manual_adjusted")) == 2
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "registration.settled")) == 2
        with factory() as session, session.begin():
            other_event = Event(event_number=57, title="رویداد مستقل", entry_fee=25,
                                registration_status="closed")
            session.add(other_event)
            session.flush()
            other_registration = Registration(event_id=other_event.id, guest_id=guest_id,
                                              source="admin")
            session.add(other_registration)
            session.flush()
            other_id = other_registration.id
        make_present(client, other_id)
        with factory() as session:
            assert registration_finance(session, registration_id).debt == 0
            assert registration_finance(session, other_id).debt == 25
        secretary = client.post("/api/admin/users", headers=write_headers(client), json={
            "username": "sec", "full_name": "دبیر", "password": "secretary-password",
        })
        assert secretary.status_code == 201
        with TestClient(create_app(settings), base_url=ORIGIN) as sec_client:
            login(sec_client, "sec", "secretary-password")
            response = mutation(sec_client, "POST", adjustment, "secretary-credit",
                                {"amount": 5, "note": "اصلاح دبیر"})
            assert response.status_code == 200
            assert response.json()["wallet_balance"] == 15


def test_linked_partial_refunds_cannot_exceed_original(management_environment):  # noqa: F811
    engine, settings = management_environment
    setup_admin(engine)
    event_id, registration_id, wallet_id = seed(engine, number=52)
    factory = build_session_factory(engine)
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        make_present(client, registration_id)
        listing = client.get(f"/api/admin/events/{event_id}/registrations").json()
        guest_id = listing["items"][0]["guest_id"]
        assert mutation(client, "POST", f"/api/admin/finance/guests/{guest_id}/adjustments",
                        "credit", {"amount": 100, "note": "واریز"}).status_code == 200
        path = f"/api/admin/finance/registrations/{registration_id}/settlements"
        first = mutation(client, "POST", path, "first", {"amount": 60}).json()["transaction_id"]
        second = mutation(client, "POST", path, "second", {"amount": 40}).json()["transaction_id"]
        refund_path = f"/api/admin/finance/settlements/{second}/refunds"
        one = mutation(client, "POST", refund_path, "refund-one",
                       {"amount": 30, "reason": "اصلاح"})
        assert one.status_code == 200 and one.json()["debt"] == 30
        assert mutation(client, "POST", refund_path, "refund-one",
                        {"amount": 30, "reason": "اصلاح"}).json() == one.json()
        assert mutation(client, "POST", refund_path, "refund-over",
                        {"amount": 11, "reason": "بیش از حد"}).status_code == 409
        assert mutation(client, "POST", refund_path, "refund-rest",
                        {"amount": 10, "reason": "باقی‌مانده"}).status_code == 200
        assert mutation(client, "POST", refund_path, "refund-again",
                        {"amount": 1, "reason": "تکرار"}).status_code == 409
        assert mutation(client, "POST", f"/api/admin/finance/settlements/{first}/refunds",
                        "refund-first", {"amount": 15, "reason": "اصلاح"}).status_code == 200
        listed = client.get(path).json()
        assert [row["active_amount"] for row in listed] == [45, 0]
        with factory() as session:
            assert registration_finance(session, registration_id).debt == 55
            assert session.get(Wallet, wallet_id).balance == 55
            refunds = session.scalars(select(WalletTransaction).where(
                WalletTransaction.type == "refund")).all()
            assert len(refunds) == 3
            assert all(row.original_transaction_id in {first, second} for row in refunds)


def test_guest_ownership_and_settlement_guards(management_environment):  # noqa: F811
    engine, settings = management_environment
    setup_admin(engine)
    event_id, registration_id, _ = seed(engine, number=53)
    _, other_registration_id, _ = seed(engine, number=54)
    factory = build_session_factory(engine)
    with TestClient(create_app(settings), base_url=ORIGIN) as admin:
        login(admin, "boss", "boss-password-123")
        make_present(admin, registration_id)
        guest = admin.get(f"/api/admin/events/{event_id}/registrations").json()["items"][0]
        assert mutation(admin, "POST", f"/api/admin/finance/guests/{guest['guest_id']}/adjustments",
                        "credit", {"amount": 70, "note": "اعتبار"}).status_code == 200
        with TestClient(create_app(settings), base_url=ORIGIN) as client:
            registered = client.post("/api/auth/guest/register", headers={"Origin": ORIGIN},
                                     json={"first_name": "مهمان", "last_name": "مالی",
                                           "phone": guest["phone"],
                                           "password": "guest-password-123"})
            assert registered.status_code == 201, registered.text
            logged = client.post("/api/auth/guest/login", headers={"Origin": ORIGIN},
                                 json={"phone": guest["phone"],
                                       "password": "guest-password-123"})
            assert logged.status_code == 200
            mine = client.get("/api/me/finance")
            assert mine.status_code == 200
            assert mine.json()["wallet_balance"] == 70
            assert mine.json()["registrations"][0]["debt"] == 100
            other = mutation(client, "POST",
                             f"/api/me/registrations/{other_registration_id}/settlements",
                             "other", {"amount": 1})
            assert other.status_code == 404
            path = f"/api/me/registrations/{registration_id}/settlements"
            assert client.post(path, headers={"Origin": ORIGIN,
                               "Idempotency-Key": "no-csrf"},
                               json={"amount": 1}).status_code == 403
            settled = mutation(client, "POST", path, "mine", {"amount": 70})
            assert settled.status_code == 200 and settled.json()["debt"] == 30
            assert mutation(client, "POST", path, "mine", {"amount": 70}).json() == settled.json()
            assert mutation(client, "POST", path, "no-balance", {"amount": 1}).status_code == 409
        with factory() as session, session.begin():
            session.get(Event, event_id).is_cancelled = True
        admin_path = f"/api/admin/finance/registrations/{registration_id}/settlements"
        assert mutation(admin, "POST", admin_path,
                        "cancelled-event", {"amount": 1}).status_code == 409
        with factory() as session, session.begin():
            session.get(Event, event_id).is_cancelled = False
            session.get(Registration, registration_id).status = "cancelled"
        assert mutation(admin, "POST", admin_path,
                        "cancelled-registration", {"amount": 1}).status_code == 409


def test_two_concurrent_settlements_spend_balance_once(management_environment):  # noqa: F811
    engine, settings = management_environment
    setup_admin(engine)
    _, registration_id, wallet_id = seed(engine, number=55)
    factory = build_session_factory(engine)
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        make_present(client, registration_id)
        with factory() as session, session.begin():
            wallet = session.get(Wallet, wallet_id)
            from app.services.finance import append_transaction
            append_transaction(session, wallet=wallet, type="manual_adjust", amount=100,
                               actor_type="user", actor_id=1, key="concurrent-credit",
                               note="تست")
    actor = Actor(type="user", id=1, session_id=1, role="super_admin")
    gate = Barrier(2)

    def attempt(key):
        with factory() as session:
            gate.wait(timeout=10)
            try:
                settle_registration(session, registration_id=registration_id,
                                    amount=80, actor=actor, key=key)
                return "ok"
            except FinanceError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["simultaneous-one", "simultaneous-two"]))
    assert results.count("ok") == 1
    assert sum(result in {"insufficient_balance", "settlement_exceeds_debt"}
               for result in results) == 1
    with factory() as session:
        assert session.get(Wallet, wallet_id).balance == 20
        assert registration_finance(session, registration_id).debt == 20
        rows = session.scalars(select(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet_id)).all()
        assert sum(row.amount for row in rows) == 20
        assert len([row for row in rows if row.type == "settlement"]) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "registration.settled")) == 1
