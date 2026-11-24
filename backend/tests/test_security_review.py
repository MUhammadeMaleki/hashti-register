"""H26: private files, cross-role access, revocation and secret-free logs."""

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_management import ORIGIN, login, management_environment, write_headers  # noqa: F401
from test_payments import guest, image_bytes, submit

from app.api import payments as payments_api
from app.core.database import build_session_factory
from app.core.security import refresh_hash
from app.main import create_app
from app.models import AuditLog, AuthSession, Event, GuestAccount, PaymentSubmission
from app.seed import bootstrap_admin


def test_all_sensitive_routes_have_auth_and_mutation_guards():
    application = create_app()
    routes = [candidate for included in application.routes
              if hasattr(included, "effective_candidates")
              for candidate in included.effective_candidates()
              if hasattr(candidate, "path") and (
                  candidate.path.startswith("/api/admin") or
                  candidate.path.startswith("/api/me"))]
    assert len(routes) >= 77
    auth_guards = {"require_active_admin", "require_super_admin",
                   "require_event_secretary", "require_active_guest", "current_actor"}
    for route in routes:
        dependencies = {item.call.__name__ for item in route.dependant.dependencies}
        assert dependencies & auth_guards, route.path
        if route.methods & {"POST", "PATCH", "PUT", "DELETE"}:
            assert {"require_browser_origin", "require_csrf"} <= dependencies, route.path


def test_private_receipt_and_revoked_staff_session(
    management_environment, monkeypatch, tmp_path,  # noqa: F811
):
    engine, settings = management_environment
    monkeypatch.setattr(payments_api, "RECEIPT_DIR", tmp_path / "receipts")
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with (TestClient(create_app(settings), base_url=ORIGIN) as admin,
          TestClient(create_app(settings), base_url=ORIGIN) as secretary,
          TestClient(create_app(settings), base_url=ORIGIN) as owner,
          TestClient(create_app(settings), base_url=ORIGIN) as stranger,
          TestClient(create_app(settings), base_url=ORIGIN) as anonymous):
        login(admin, "boss", "boss-password-123")
        created = admin.post("/api/admin/users", headers=write_headers(admin), json={
            "username": "sec", "full_name": "دبیر", "password": "secretary-password-123",
        })
        assert created.status_code == 201
        secretary_id = created.json()["id"]
        login(secretary, "sec", "secretary-password-123")
        old_refresh = secretary.cookies.get("hashti_refresh")
        old_csrf = secretary.cookies.get("hashti_csrf")
        assert secretary.get("/api/admin/users").status_code == 403
        assert secretary.get("/api/admin/import/events/template").status_code == 403

        guest(owner, "09120001926")
        guest(stranger, "09120001927")
        image = image_bytes()
        assert owner.post("/api/me/payments", headers={
            "Origin": ORIGIN, "Idempotency-Key": "missing-csrf",
        }, data={"amount": "100", "tracking_code": "X"},
            files={"receipt": ("receipt.png", image, "image/png")}).status_code == 403
        assert submit(owner, "/api/me/payments", "bad-heif", code="X",
                      image=("receipt.heif", b"\x00\x00\x00\x18ftypheifbad",
                             "image/heif")).status_code == 422
        assert submit(owner, "/api/me/payments", "valid-image", code="X",
                      image=("receipt.png", image, "image/png")).status_code == 201
        payment_id = owner.get("/api/me/payments").json()[0]["id"]
        with factory() as session:
            stored = session.get(PaymentSubmission, payment_id)
            name = stored.display_receipt_path
            assert name and (tmp_path / "receipts" / name).is_file()
        own = owner.get(f"/api/me/payments/{payment_id}/receipt")
        assert own.status_code == 200 and own.headers["cache-control"] == "private, no-store"
        assert own.headers["x-content-type-options"] == "nosniff"
        assert stranger.get(f"/api/me/payments/{payment_id}/receipt").status_code == 404
        assert secretary.get(f"/api/admin/payments/{payment_id}/receipt").status_code == 404
        assert admin.get(f"/api/admin/payments/{payment_id}/receipt").status_code == 200
        assert anonymous.get(f"/api/me/payments/{payment_id}/receipt").status_code == 401
        assert anonymous.get(f"/api/admin/payments/{payment_id}/receipt").status_code == 401
        assert anonymous.get(f"/.local/uploads/receipts/{name}").status_code == 404
        assert anonymous.get(f"/api/public/receipts/{name}").status_code == 404

        with factory() as session, session.begin():
            event = Event(event_number=926, title="محرمانه")
            session.add(event)
            session.flush()
            event_id = event.id
        assert secretary.get(f"/api/admin/events/{event_id}/registrations").status_code == 403
        assert secretary.post("/api/admin/events", headers={"Origin": ORIGIN},
                              json={"event_number": 927, "title": "بدون CSRF"}).status_code == 403
        assert secretary.post("/api/admin/events", headers={
            **write_headers(secretary), "Origin": "https://evil.example",
        }, json={"event_number": 927, "title": "مبدأ بد"}).status_code == 403
        assert owner.get("/api/admin/users").status_code == 403
        assert admin.patch(f"/api/admin/users/{secretary_id}",
                           headers=write_headers(admin),
                           json={"is_active": False}).status_code == 200
        assert secretary.get("/api/auth/session").status_code == 401
        assert secretary.get("/api/admin/events").status_code == 401
        assert secretary.post("/api/auth/refresh", headers={
            "Origin": ORIGIN, "X-CSRF-Token": old_csrf,
        }).status_code == 401
        with factory() as session:
            old = session.scalar(select(AuthSession).where(
                AuthSession.refresh_token_hash == refresh_hash(old_refresh)))
            assert old.revoked_at is not None
            assert session.scalar(select(func.count()).select_from(PaymentSubmission)) == 1


def test_auth_audit_and_error_log_exclude_secrets(management_environment, caplog):  # noqa: F811
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with (TestClient(create_app(settings), base_url=ORIGIN) as admin,
          TestClient(create_app(settings), base_url=ORIGIN) as visitor):
        login(admin, "boss", "boss-password-123")
        refresh = admin.cookies.get("hashti_refresh")
        csrf = admin.cookies.get("hashti_csrf")
        account_id = guest(visitor, "09120001928")
        issued = admin.post(f"/api/admin/guests/{account_id}/temp-password",
                            headers=write_headers(admin))
        assert issued.status_code == 200
        temporary = issued.json()["temporary_password"]
        with factory() as session, session.begin():
            account = session.scalar(select(GuestAccount).where(
                GuestAccount.guest_id == account_id))
            account.temp_password_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        denied = visitor.post("/api/auth/guest/login", headers={"Origin": ORIGIN}, json={
            "phone": "09120001928", "password": temporary,
        })
        assert denied.status_code == 401
        assert temporary not in denied.text
        with factory() as session:
            audit = session.scalars(select(AuditLog)).all()
            serialized = json.dumps([{
                "action": row.action, "before": row.before_json,
                "after": row.after_json, "metadata": row.metadata_json,
            } for row in audit], ensure_ascii=False)
            assert any(row.action == "auth.temp_password_issued" for row in audit)
            assert any(row.action == "auth.login_failed" for row in audit)
        for secret in ("boss-password-123", "guest-password-123", temporary, refresh, csrf):
            assert secret not in serialized
            assert secret not in caplog.text
