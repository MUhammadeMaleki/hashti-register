"""H14 order and event entry-fee accounting on real PostgreSQL."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.core.database import build_session_factory
from app.main import create_app
from app.models import AuditLog, Event, EventCharge, Guest, Registration, Wallet, WalletTransaction
from app.seed import bootstrap_admin
from app.services.finance import append_transaction, lock_registration_wallet, registration_finance


def mutation(client, method, path, key, body=None):
    return client.request(method, path, headers={**write_headers(client),
                          "Idempotency-Key": key}, json=body)


def seed(engine, *, fee=100, attendance="pending", number=1):
    factory = build_session_factory(engine)
    with factory() as session, session.begin():
        event = Event(event_number=number, title="هزینه", entry_fee=fee,
                      registration_status="closed")
        session.add(event)
        session.flush()
        guest = Guest(first_name="مهمان", last_name="مالی", phone=f"0912{number:07d}")
        session.add(guest)
        session.flush()
        wallet = Wallet(guest_id=guest.id, balance=0)
        registration = Registration(event_id=event.id, guest_id=guest.id,
                                    attendance=attendance, source="admin")
        session.add_all([wallet, registration])
        session.flush()
        return event.id, registration.id, wallet.id


def test_orders_pending_multiple_edit_cancel_refund_and_replay(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    event_id, registration_id, wallet_id = seed(engine)
    path = f"/api/admin/registrations/{registration_id}/orders"
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        denied = mutation(client, "POST", path, "pending", {"description": "چای", "amount": 40})
        assert denied.status_code == 409
        assert denied.json()["detail"] == "order_attendance_not_allowed"
        assert client.get(f"/api/admin/registrations/{registration_id}/charges").json() == []
        attendance = mutation(client, "POST",
                              f"/api/admin/registrations/{registration_id}/attendance",
                              "present", {"attendance": "present"})
        assert attendance.status_code == 200
        first = mutation(client, "POST", path, "first", {"description": "چای", "amount": 40})
        second = mutation(client, "POST", path, "second", {"description": "کیک", "amount": 20})
        assert first.status_code == second.status_code == 200
        assert mutation(client, "POST", path, "first",
                        {"description": "چای", "amount": 40}).json() == first.json()
        assert mutation(client, "POST", path, "first",
                        {"description": "قهوه", "amount": 40}).status_code == 409
        assert len(client.get(f"/api/admin/registrations/{registration_id}/charges").json()) == 3
        with factory() as session, session.begin():
            _, _, wallet = lock_registration_wallet(session, registration_id)
            append_transaction(session, wallet=wallet, type="manual_adjust", amount=160,
                               actor_type="user", actor_id=1, key="credit", note="تست")
            append_transaction(session, wallet=wallet, type="settlement", amount=-100,
                               registration_id=registration_id, actor_type="user",
                               actor_id=1, key="settlement-1")
            append_transaction(session, wallet=wallet, type="settlement", amount=-60,
                               registration_id=registration_id, actor_type="user",
                               actor_id=1, key="settlement-2")
        updated = mutation(client, "PATCH", f"{path}/{first.json()['id']}", "reduce",
                           {"description": "چای کوچک", "amount": 10})
        assert updated.status_code == 200, updated.text
        assert sum(row["amount"] for row in updated.json()["refunds"]) == 30
        assert updated.json()["debt"] == 0
        cancelled = mutation(client, "DELETE", f"{path}/{second.json()['id']}", "cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert sum(row["amount"] for row in cancelled.json()["refunds"]) == 20
        assert mutation(client, "DELETE", f"{path}/{second.json()['id']}",
                        "cancel").json() == cancelled.json()
        assert mutation(client, "PATCH", f"{path}/{second.json()['id']}", "revive",
                        {"description": "کیک", "amount": 20}).status_code == 409
        assert mutation(client, "DELETE", f"{path}/{first.json()['id']}", "cancel-first"
                        ).status_code == 200
        with factory() as session:
            state = registration_finance(session, registration_id)
            assert (state.active_charges, state.active_settlements, state.debt) == (100, 100, 0)
            assert session.get(Wallet, wallet_id).balance == 60
            refunds = session.scalars(select(WalletTransaction).where(
                WalletTransaction.registration_id == registration_id,
                WalletTransaction.type == "refund").order_by(WalletTransaction.id)).all()
            assert [row.amount for row in refunds] == [30, 20, 10]
            assert all(row.original_transaction_id for row in refunds)
            assert refunds[0].original_transaction_id == refunds[1].original_transaction_id
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action.in_(["order.create", "order.update", "order.cancel"]))) == 5


def test_entry_fee_bulk_positive_zero_positive_and_rollback(management_environment):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    event_id, present_id, wallet_id = seed(engine, number=2)
    with factory() as session, session.begin():
        guest = Guest(first_name="دیگر", last_name="مهمان", phone="09120000003")
        session.add(guest)
        session.flush()
        session.add(Wallet(guest_id=guest.id, balance=0))
        forfeited = Registration(event_id=event_id, guest_id=guest.id, source="admin",
                                 attendance="absent_forfeited")
        session.add(forfeited)
        session.flush()
        forfeited_id = forfeited.id
        guest2 = Guest(first_name="منتظر", last_name="مهمان", phone="09120000004")
        session.add(guest2)
        session.flush()
        session.add_all([Wallet(guest_id=guest2.id, balance=0),
                         Registration(event_id=event_id, guest_id=guest2.id, source="admin")])
    fee_path = f"/api/admin/events/{event_id}/entry-fee"
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        assert mutation(client, "POST",
                        f"/api/admin/registrations/{present_id}/attendance",
                        "present", {"attendance": "present"}).status_code == 200
        with factory() as session, session.begin():
            _, _, wallet = lock_registration_wallet(session, present_id)
            append_transaction(session, wallet=wallet, type="manual_adjust", amount=100,
                               actor_type="user", actor_id=1, key="fee-credit", note="تست")
            append_transaction(session, wallet=wallet, type="settlement", amount=-100,
                               registration_id=present_id, actor_type="user", actor_id=1,
                               key="fee-settlement")
        down = mutation(client, "PATCH", fee_path, "fee-down", {"amount": 60})
        assert down.status_code == 200, down.text
        assert down.json()["registrations"] == 2
        assert down.json()["refunds"] == 40
        assert mutation(client, "PATCH", fee_path, "fee-down",
                        {"amount": 60}).json() == down.json()
        assert mutation(client, "PATCH", fee_path, "fee-down",
                        {"amount": 50}).status_code == 409
        with factory() as session:
            assert session.get(Wallet, wallet_id).balance == 40
            assert registration_finance(session, present_id).debt == 0
            assert registration_finance(session, forfeited_id).debt == 60
        increase = mutation(client, "PATCH", fee_path, "fee-increase", {"amount": 120})
        assert increase.status_code == 200 and increase.json()["refunds"] == 0
        with factory() as session:
            assert registration_finance(session, present_id).debt == 60
            assert session.get(Wallet, wallet_id).balance == 40
        decrease = mutation(client, "PATCH", fee_path, "fee-decrease", {"amount": 60})
        assert decrease.status_code == 200 and decrease.json()["refunds"] == 0
        zero = mutation(client, "PATCH", fee_path, "fee-zero", {"amount": 0})
        assert zero.status_code == 200, zero.text
        assert zero.json()["refunds"] == 60
        with factory() as session:
            entries = session.scalars(select(EventCharge).where(
                EventCharge.registration_id.in_([present_id, forfeited_id]),
                EventCharge.type == "entry")).all()
            assert len(entries) == 2 and all(row.is_cancelled and row.amount > 0
                                             for row in entries)
            assert session.get(Wallet, wallet_id).balance == 100
        up = mutation(client, "PATCH", fee_path, "fee-up", {"amount": 80})
        assert up.status_code == 200, up.text
        with factory() as session:
            entries = session.scalars(select(EventCharge).where(
                EventCharge.registration_id.in_([present_id, forfeited_id]),
                EventCharge.type == "entry")).all()
            assert len(entries) == 4
            assert len([row for row in entries if not row.is_cancelled]) == 2
            assert all(row.amount > 0 for row in entries)
            assert registration_finance(session, present_id).debt == 80
            assert session.scalar(select(func.count()).select_from(EventCharge).where(
                EventCharge.registration_id.not_in([present_id, forfeited_id]))) == 0
        with factory() as session, session.begin():
            _, _, wallet = lock_registration_wallet(session, present_id)
            append_transaction(session, wallet=wallet, type="settlement", amount=-80,
                               registration_id=present_id, actor_type="user", actor_id=1,
                               key="fee-settlement-new")
            session.get(Wallet, wallet_id).balance += 1
        failed = mutation(client, "PATCH", fee_path, "fee-fail", {"amount": 0})
        assert failed.status_code == 409
        with factory() as session:
            assert session.get(Event, event_id).entry_fee == 80
            assert len(session.scalars(select(EventCharge).where(
                EventCharge.registration_id == present_id,
                EventCharge.is_cancelled.is_(False))).all()) == 1
        with factory() as session, session.begin():
            session.get(Wallet, wallet_id).balance -= 1
        assert mutation(client, "PATCH", fee_path, "fee-fail", {"amount": 0}).status_code == 200
        unchanged = mutation(client, "PATCH", fee_path, "fee-unchanged", {"amount": 0})
        assert unchanged.status_code == 200 and unchanged.json()["changed"] is False
        with factory() as session, session.begin():
            session.get(Event, event_id).is_cancelled = True
        assert mutation(client, "PATCH", fee_path, "fee-cancelled",
                        {"amount": 50}).status_code == 409
        assert mutation(client, "POST", f"/api/admin/registrations/{present_id}/orders",
                        "order-cancelled-event", {"description": "چای", "amount": 10}
                        ).status_code == 409
