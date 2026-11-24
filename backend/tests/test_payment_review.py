"""H17 receipt-review access, state transitions and wallet effects."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete, func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401
from test_payments import guest, submit

from app.api import payments as payments_api
from app.core.database import build_session_factory
from app.main import create_app
from app.models import (
    AuditLog,
    Event,
    EventCharge,
    EventSecretary,
    PaymentSubmission,
    Registration,
    User,
    Wallet,
    WalletTransaction,
)
from app.seed import bootstrap_admin
from app.services.auth import Actor
from app.services.finance import FinanceError, registration_finance
from app.services.payment_review import review_payment


def setup_admins(engine):
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with factory() as session, session.begin():
        boss_id = session.scalar(select(User.id).where(User.username == "boss"))
        secretary = User(username="sec", full_name="دبیر", role="secretary",
                         password_hash=PasswordHasher().hash("secretary-password-123"))
        session.add(secretary)
        session.flush()
        return boss_id, secretary.id


def mutate(client, path, key, body=None):
    return client.post(path, headers={**write_headers(client), "Idempotency-Key": key},
                       json=body)


def png():
    output = BytesIO()
    Image.new("RGB", (4, 4), "blue").save(output, format="PNG")
    return output.getvalue()


def test_review_queue_access_approval_rejection_and_no_auto_settlement(
    management_environment, monkeypatch, tmp_path,  # noqa: F811
):
    engine, settings = management_environment
    monkeypatch.setattr(payments_api, "RECEIPT_DIR", tmp_path / "receipts")
    boss_id, secretary_id = setup_admins(engine)
    factory = build_session_factory(engine)
    with (TestClient(create_app(settings), base_url=ORIGIN) as boss,
          TestClient(create_app(settings), base_url=ORIGIN) as sec,
          TestClient(create_app(settings), base_url=ORIGIN) as owner):
        login(boss, "boss", "boss-password-123")
        login(sec, "sec", "secretary-password-123")
        guest_id = guest(owner, "09120001101")
        with factory() as session, session.begin():
            event = Event(event_number=201, title="مجاز", registration_status="closed")
            foreign = Event(event_number=202, title="دیگر", registration_status="closed")
            session.add_all([event, foreign])
            session.flush()
            session.add(EventSecretary(event_id=event.id, user_id=secretary_id))
            registration = Registration(event_id=event.id, guest_id=guest_id,
                                        source="admin")
            session.add(registration)
            session.flush()
            session.add(EventCharge(registration_id=registration.id, type="order",
                                    description="سفارش", amount=50, created_by=boss_id))
            event_id, foreign_id, registration_id = event.id, foreign.id, registration.id
        linked = submit(owner, f"/api/me/events/{event_id}/payments", "linked",
                        code="L", image=("receipt.png", png(), "image/png"))
        independent = submit(owner, "/api/me/payments", "independent", code="I")
        with factory() as session, session.begin():
            session.add(PaymentSubmission(guest_id=guest_id, event_id=foreign_id,
                                          amount=70, tracking_code="F",
                                          idempotency_key="foreign-payment"))
        assert linked.status_code == independent.status_code == 201
        linked_id, independent_id = linked.json()["id"], independent.json()["id"]
        sec_items = sec.get("/api/admin/payments?status=pending").json()
        assert sec_items["total"] == 1
        assert [row["id"] for row in sec_items["items"]] == [linked_id]
        assert boss.get("/api/admin/payments?status=pending").json()["total"] == 3
        assert sec.get(f"/api/admin/payments/{independent_id}").status_code == 404
        assert sec.get(f"/api/admin/payments/{independent_id}/receipt").status_code == 404
        assert mutate(sec, f"/api/admin/payments/{independent_id}/approve", "wrong"
                      ).status_code == 404
        assert sec.get(f"/api/admin/payments/{linked_id}/receipt").status_code == 200
        assert boss.get(f"/api/admin/payments/{linked_id}").json()["guest_id"] == guest_id
        assert boss.get(f"/api/admin/payments/{linked_id}").json()["event_title"] == "مجاز"
        approval_path = f"/api/admin/payments/{linked_id}/approve"
        assert sec.post(approval_path, headers={"Origin": ORIGIN}).status_code == 403
        assert sec.post(approval_path, headers=write_headers(sec)).status_code == 422
        approved = mutate(sec, approval_path, "approve-1")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["wallet_balance"] == 100
        assert approved.json()["transaction_id"] is not None
        assert mutate(sec, approval_path, "approve-1").json() == approved.json()
        assert mutate(sec, approval_path, "approve-2").status_code == 409
        assert mutate(boss, f"/api/admin/payments/{linked_id}/reject", "late",
                      {"reason": "دیر"}).status_code == 409
        reject_path = f"/api/admin/payments/{independent_id}/reject"
        assert mutate(sec, reject_path, "unauthorized", {"reason": "نه"}).status_code == 404
        rejected = mutate(boss, reject_path, "reject-1", {"reason": "  نامعتبر  "})
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["reject_reason"] == "نامعتبر"
        assert rejected.json()["transaction_id"] is None
        assert mutate(boss, reject_path, "reject-1", {"reason": "نامعتبر"}
                      ).json() == rejected.json()
        assert mutate(boss, f"/api/admin/payments/{independent_id}/approve", "late"
                      ).status_code == 409
        own_payments = {row["id"]: row for row in owner.get("/api/me/payments").json()}
        assert own_payments[independent_id]["status"] == "rejected"
        assert own_payments[linked_id]["status"] == "approved"
        assert boss.get("/api/admin/payments?status=approved").json()["total"] == 1
        assert boss.get("/api/admin/payments?status=rejected").json()["total"] == 1
        with factory() as session:
            wallet = session.scalar(select(Wallet).where(Wallet.guest_id == guest_id))
            assert wallet.balance == 100
            assert session.get(PaymentSubmission, linked_id).reviewed_by == secretary_id
            assert session.get(PaymentSubmission, independent_id).reviewed_by == boss_id
            assert registration_finance(session, registration_id).debt == 50
            transactions = session.scalars(select(WalletTransaction)).all()
            assert len(transactions) == 1
            assert transactions[0].payment_submission_id == linked_id
            assert transactions[0].registration_id is None
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action.in_(["payment.approve", "payment.reject"]))) == 2
        with factory() as session, session.begin():
            session.execute(delete(EventSecretary).where(
                EventSecretary.event_id == event_id,
                EventSecretary.user_id == secretary_id,
            ))
        assert mutate(sec, approval_path, "approve-1").status_code == 404
        assert sec.get(f"/api/admin/payments/{linked_id}").status_code == 404


def test_two_concurrent_approvals_only_create_one_topup(management_environment):  # noqa: F811
    engine, _ = management_environment
    boss_id, _ = setup_admins(engine)
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        from app.models import Guest  # local fixture data only

        guest_row = Guest(first_name="همزمان", last_name="تست", phone="09120001102")
        session.add(guest_row)
        session.flush()
        session.add(Wallet(guest_id=guest_row.id, balance=0))
        payment = PaymentSubmission(guest_id=guest_row.id, amount=250,
                                    tracking_code="C", idempotency_key="concurrent-payment")
        session.add(payment)
        session.flush()
        payment_id, guest_id = payment.id, guest_row.id
    gate = Barrier(2)
    actor = Actor(type="user", id=boss_id, session_id=1, role="super_admin")

    def approve(key):
        with factory() as session:
            gate.wait()
            try:
                return review_payment(session, payment_id=payment_id, approve=True,
                                      reason=None, actor=actor, key=key).body
            except FinanceError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(approve, "first")
        second = pool.submit(approve, "second")
        outcomes = [first.result(timeout=15), second.result(timeout=15)]
    assert sum(isinstance(result, dict) for result in outcomes) == 1
    assert "payment_already_reviewed" in outcomes
    with factory() as session:
        assert session.scalar(select(Wallet.balance).where(Wallet.guest_id == guest_id)) == 250
        rows = session.scalars(select(WalletTransaction).where(
            WalletTransaction.payment_submission_id == payment_id)).all()
        assert len(rows) == 1 and (rows[0].type, rows[0].amount) == ("topup", 250)
        assert session.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "payment.approve")) == 1


def test_super_admin_can_approve_independent_receipt_and_reject_without_reason(
    management_environment,  # noqa: F811
):
    engine, settings = management_environment
    setup_admins(engine)
    with (TestClient(create_app(settings), base_url=ORIGIN) as boss,
          TestClient(create_app(settings), base_url=ORIGIN) as owner):
        login(boss, "boss", "boss-password-123")
        guest_id = guest(owner, "09120001103")
        approved_receipt = submit(owner, "/api/me/payments", "independent-a", code="A")
        rejected_receipt = submit(owner, "/api/me/payments", "independent-b", code="B")
        approved_id, rejected_id = approved_receipt.json()["id"], rejected_receipt.json()["id"]
        assert mutate(boss, f"/api/admin/payments/{approved_id}/approve", "approve-a"
                      ).status_code == 200
        rejected = mutate(boss, f"/api/admin/payments/{rejected_id}/reject", "reject-b")
        assert rejected.status_code == 200
        assert rejected.json()["reject_reason"] is None
        assert mutate(boss, f"/api/admin/payments/{rejected_id}/approve", "late"
                      ).status_code == 409
        with build_session_factory(engine)() as session:
            assert session.scalar(select(Wallet.balance).where(Wallet.guest_id == guest_id)) == 100
            assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 1
