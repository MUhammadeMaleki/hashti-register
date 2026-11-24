"""H16 receipt creation, image validation and private delivery."""

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pillow_heif import register_heif_opener
from sqlalchemy import func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401

from app.api import payments as payments_api
from app.core.database import build_session_factory
from app.main import create_app
from app.models import Event, PaymentSubmission, Registration, Wallet, WalletTransaction
from app.seed import bootstrap_admin


def guest(client, phone):
    response = client.post("/api/auth/guest/register", headers={"Origin": ORIGIN}, json={
        "first_name": "مهمان", "last_name": "رسید", "phone": phone,
        "password": "guest-password-123",
    })
    assert response.status_code == 201, response.text
    logged_in = client.post("/api/auth/guest/login", headers={"Origin": ORIGIN}, json={
        "phone": phone, "password": "guest-password-123",
    })
    assert logged_in.status_code == 200, logged_in.text
    return response.json()["guest_id"]


def image_bytes():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


def heic_bytes():
    register_heif_opener()
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="HEIF")
    return buffer.getvalue()


def submit(client, path, key, *, amount="100", code=None, image=None, extra=None):
    data = {"amount": amount, **(extra or {})}
    if code is not None:
        data["tracking_code"] = code
    files = {"receipt": image} if image is not None else None
    return client.post(path, headers={**write_headers(client), "Idempotency-Key": key},
                       data=data, files=files)


def test_code_only_image_only_replay_and_private_access(
    management_environment, monkeypatch, tmp_path,  # noqa: F811
):
    engine, settings = management_environment
    monkeypatch.setattr(payments_api, "RECEIPT_DIR", tmp_path / "receipts")
    with (TestClient(create_app(settings), base_url=ORIGIN) as owner,
          TestClient(create_app(settings), base_url=ORIGIN) as other):
        guest_id = guest(owner, "09120001001")
        guest(other, "09120001002")
        path = "/api/me/payments"
        assert submit(owner, path, "empty").status_code == 422
        assert submit(owner, path, "blank", code="   ").status_code == 422
        code = submit(owner, path, "code", code="  ABC  ")
        assert code.status_code == 201, code.text
        assert code.json()["tracking_code"] == "ABC"
        assert not code.json()["has_image"]
        assert submit(owner, path, "code", code="ABC").json() == code.json()
        assert submit(owner, path, "code", code="different").status_code == 409
        assert owner.get(f"{path}/{code.json()['id']}/receipt").status_code == 404
        raw = image_bytes()
        uploaded = submit(owner, path, "image", image=("receipt.png", raw, "image/png"))
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["has_image"]
        assert uploaded.json()["tracking_code"] is None
        both = submit(owner, path, "both", code="HEIC-1",
                      image=("receipt.heic", heic_bytes(), "image/heic"))
        assert both.status_code == 201, both.text
        assert both.json()["has_image"] and both.json()["tracking_code"] == "HEIC-1"
        receipt_url = f"{path}/{uploaded.json()['id']}/receipt"
        own_image = owner.get(receipt_url)
        assert own_image.status_code == 200
        assert own_image.headers["content-type"] == "image/jpeg"
        assert own_image.headers["cache-control"] == "private, no-store"
        assert other.get(receipt_url).status_code == 404
        assert other.get("/api/admin/payments/1/receipt").status_code == 403
        with build_session_factory(engine)() as session:
            rows = session.scalars(select(PaymentSubmission).order_by(PaymentSubmission.id)).all()
            assert len(rows) == 3
            assert rows[0].guest_id == guest_id
            assert rows[0].original_receipt_path is None
            assert rows[0].display_receipt_path is None
            assert rows[1].original_receipt_path is not None
            assert rows[1].display_receipt_path is not None
            assert session.scalar(select(func.count()).select_from(WalletTransaction)) == 0
            assert session.scalar(select(Wallet.balance).where(Wallet.guest_id == guest_id)) == 0


def test_image_validation_and_event_ownership(
    management_environment, monkeypatch, tmp_path,  # noqa: F811
):
    engine, settings = management_environment
    monkeypatch.setattr(payments_api, "RECEIPT_DIR", tmp_path / "receipts")
    with (TestClient(create_app(settings), base_url=ORIGIN) as owner,
          TestClient(create_app(settings), base_url=ORIGIN) as other):
        guest_id = guest(owner, "09120001003")
        guest(other, "09120001004")
        with build_session_factory(engine)() as session, session.begin():
            event = Event(event_number=190, title="رویداد", registration_status="closed")
            session.add(event)
            session.flush()
            session.add(Registration(event_id=event.id, guest_id=guest_id, source="admin"))
            event_id = event.id
        path = f"/api/me/events/{event_id}/payments"
        assert submit(other, path, "foreign", code="X").status_code == 403
        assert submit(owner, path, "body", code="X", extra={"event_id": "999"}
                      ).status_code == 422
        valid = submit(owner, path, "linked", code="X")
        assert valid.status_code == 201, valid.text
        assert valid.json()["event_id"] == event_id
        assert submit(owner, "/api/me/payments", "mismatch",
                      image=("receipt.png", image_bytes(), "image/jpeg")).status_code == 422
        assert submit(owner, "/api/me/payments", "broken",
                      image=("receipt.png", b"\x89PNG\r\n\x1a\ncorrupt", "image/png")
                      ).status_code == 422
        assert submit(owner, "/api/me/payments", "unsupported",
                      image=("receipt.gif", b"GIF89a", "image/gif")
                      ).status_code == 422
        assert submit(owner, "/api/me/payments", "large",
                      image=("receipt.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")
                      ).status_code == 422
        assert not (tmp_path / "receipts").exists()
        with build_session_factory(engine)() as session, session.begin():
            session.get(Event, event_id).is_cancelled = True
        assert submit(owner, path, "cancelled", code="Y").status_code == 409


def test_failed_preview_write_cleans_original(management_environment, monkeypatch, tmp_path):  # noqa: F811
    engine, settings = management_environment
    receipt_dir = tmp_path / "receipts"
    monkeypatch.setattr(payments_api, "RECEIPT_DIR", receipt_dir)
    original_write = Path.write_bytes

    def fail_preview(path, data):
        if path.suffix == ".jpg" and path.parent == receipt_dir:
            raise OSError("preview write failed")
        return original_write(path, data)

    monkeypatch.setattr(Path, "write_bytes", fail_preview)
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        guest(client, "09120001005")
        with pytest.raises(OSError, match="preview write failed"):
            submit(client, "/api/me/payments", "write-failure",
                   image=("receipt.png", image_bytes(), "image/png"))
    assert list(receipt_dir.iterdir()) == []
    with build_session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(PaymentSubmission)) == 0


def test_event_attendance_reports_only_linked_receipts(management_environment):  # noqa: F811
    engine, settings = management_environment
    with build_session_factory(engine)() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with (TestClient(create_app(settings), base_url=ORIGIN) as owner,
          TestClient(create_app(settings), base_url=ORIGIN) as admin):
        guest_id = guest(owner, "09120001006")
        with build_session_factory(engine)() as session, session.begin():
            event = Event(event_number=191, title="رویداد", registration_status="closed")
            session.add(event)
            session.flush()
            session.add(Registration(event_id=event.id, guest_id=guest_id, source="admin"))
            event_id = event.id
        linked = submit(owner, f"/api/me/events/{event_id}/payments", "linked-summary",
                        amount="200000", code="A")
        assert linked.status_code == 201, linked.text
        assert submit(owner, "/api/me/payments", "independent-summary",
                      amount="100000", code="B").status_code == 201
        login(admin, "boss", "boss-password-123")
        response = admin.get(f"/api/admin/events/{event_id}/registrations")
        assert response.status_code == 200, response.text
        row = response.json()["items"][0]
        assert row["guest_id"] == guest_id
        assert row["event_payments"] == [{
            "id": linked.json()["id"], "amount": 200000, "status": "pending",
            "created_at": linked.json()["created_at"],
        }]
