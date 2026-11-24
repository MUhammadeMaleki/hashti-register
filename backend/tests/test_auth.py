from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select

from alembic import command
from app.core.config import Settings
from app.core.database import build_session_factory
from app.core.security import refresh_hash
from app.main import create_app
from app.models import AuditLog, AuthSession, Guest, GuestAccount, Registration, User, Wallet
from app.seed import bootstrap_admin
from app.services.auth import AuthError, register_guest
from app.services.guests import create_guest_with_wallet

ORIGIN = "http://testserver"
HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def auth_environment(postgres_engine):
    schema = "h04_" + uuid4().hex[:12]
    with postgres_engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    scoped_url = postgres_engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(scoped_url, pool_pre_ping=True)
    try:
        configuration = Config("alembic.ini")
        with engine.begin() as connection:
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "head")
        settings = Settings(
            database_url=SecretStr(scoped_url.render_as_string(hide_password=False)),
            auth_secret=SecretStr("a" * 64),
            public_origin=ORIGIN,
            environment="development",
            argon2_memory_cost=8192,
            argon2_time_cost=1,
            argon2_parallelism=1,
        )
        yield engine, settings
    finally:
        engine.dispose()
        with postgres_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')


def test_guest_registration_existing_and_new_profile(auth_environment):
    engine, settings = auth_environment
    factory = build_session_factory(engine)
    with factory() as session:
        existing = create_guest_with_wallet(
            session, first_name="موجود", last_name="مهمان", phone="09120000010"
        )
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        response = client.post(
            "/api/auth/guest/register",
            headers=HEADERS,
            json={
                "first_name": "نام تازه",
                "last_name": "تکراری",
                "phone": "+۹۸۹۱۲۰۰۰۰۰۱۰",
                "password": "guest-password-123",
            },
        )
        assert response.status_code == 201
        assert response.json()["guest_id"] == existing.guest_id
        assert (
            client.post(
                "/api/auth/guest/register",
                headers=HEADERS,
                json={
                    "first_name": "نام",
                    "last_name": "تکراری",
                    "phone": "09120000010",
                    "password": "guest-password-123",
                },
            ).status_code
            == 409
        )
        new = client.post(
            "/api/auth/guest/register",
            headers=HEADERS,
            json={
                "first_name": "جدید",
                "last_name": "مهمان",
                "phone": "09120000011",
                "password": "guest-password-123",
            },
        )
        assert new.status_code == 201
        assert (
            client.post(
                "/api/auth/guest/register",
                json={
                    "first_name": "bad",
                    "last_name": "origin",
                    "phone": "09120000012",
                    "password": "guest-password-123",
                },
            ).status_code
            == 403
        )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Guest)) == 2
        assert session.scalar(select(func.count()).select_from(Wallet)) == 2
        assert session.scalar(select(func.count()).select_from(GuestAccount)) == 2
        assert session.scalar(select(func.count()).select_from(Registration)) == 0


def test_concurrent_registration_creates_one_profile_wallet_and_account(auth_environment):
    engine, settings = auth_environment
    factory = build_session_factory(engine)

    def register_once():
        with factory() as session:
            try:
                return register_guest(
                    session,
                    first_name="هم‌زمان",
                    last_name="مهمان",
                    phone="09120000014",
                    password="guest-password-123",
                    settings=settings,
                )
            except AuthError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: register_once(), range(2)))
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert results.count("account_exists") == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Guest)) == 1
        assert session.scalar(select(func.count()).select_from(Wallet)) == 1
        assert session.scalar(select(func.count()).select_from(GuestAccount)) == 1


def test_login_refresh_replay_csrf_and_logout(auth_environment):
    engine, settings = auth_environment
    factory = build_session_factory(engine)
    with factory() as session:
        assert bootstrap_admin(
            session, username="admin", full_name="مدیر", password="admin-password-123"
        )
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        denied = client.post(
            "/api/auth/admin/login",
            headers=HEADERS,
            json={
                "username": "missing",
                "password": "bad",
            },
        )
        assert denied.status_code == 401
        response = client.post(
            "/api/auth/admin/login",
            headers=HEADERS,
            json={
                "username": "admin",
                "password": "admin-password-123",
            },
        )
        assert response.status_code == 200
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=lax" in response.headers["set-cookie"].lower()
        assert "access" not in response.json()
        assert client.get("/api/auth/session").json()["role"] == "super_admin"
        old_refresh = client.cookies.get("hashti_refresh")
        old_csrf = client.cookies.get("hashti_csrf")
        assert client.post("/api/auth/refresh", headers=HEADERS).status_code == 403
        assert (
            client.post(
                "/api/auth/refresh", headers={**HEADERS, "X-CSRF-Token": old_csrf}
            ).status_code
            == 200
        )
        assert client.cookies.get("hashti_refresh") != old_refresh
        with factory() as session:
            old = session.scalar(
                select(AuthSession).where(
                    AuthSession.refresh_token_hash == refresh_hash(old_refresh)
                )
            )
            assert old.revoked_at is not None
            assert old.replaced_by_session_id is not None
        with TestClient(create_app(settings), base_url=ORIGIN) as replay_client:
            replay_client.cookies.set("hashti_refresh", old_refresh, path="/api/auth")
            replay_client.cookies.set("hashti_csrf", old_csrf, path="/")
            replay = replay_client.post(
                "/api/auth/refresh", headers={**HEADERS, "X-CSRF-Token": old_csrf}
            )
        assert replay.status_code == 401
        assert client.get("/api/auth/session").status_code == 401
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(AuthSession).where(
                AuthSession.actor_type == "user", AuthSession.revoked_at.is_(None))) == 0
            assert session.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "auth.refresh_reuse")) == 1
        response = client.post(
            "/api/auth/admin/login",
            headers=HEADERS,
            json={
                "username": "admin",
                "password": "admin-password-123",
            },
        )
        assert response.status_code == 200
        csrf = client.cookies.get("hashti_csrf")
        assert (
            client.post("/api/auth/logout", headers={**HEADERS, "X-CSRF-Token": csrf}).status_code
            == 200
        )
        assert client.get("/api/auth/session").status_code == 401


def test_lockout_and_disabled_admin(auth_environment):
    engine, settings = auth_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="admin", full_name="مدیر", password="admin-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        for _ in range(settings.login_max_failures):
            assert (
                client.post(
                    "/api/auth/admin/login",
                    headers=HEADERS,
                    json={
                        "username": "admin",
                        "password": "wrong",
                    },
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/api/auth/admin/login",
                headers=HEADERS,
                json={
                    "username": "admin",
                    "password": "admin-password-123",
                },
            ).status_code
            == 401
        )
        with factory() as session:
            user = session.scalar(select(User).where(User.username == "admin"))
            assert user.locked_until is not None
            user.locked_until = None
            session.commit()
        assert (
            client.post(
                "/api/auth/admin/login",
                headers=HEADERS,
                json={
                    "username": "admin",
                    "password": "admin-password-123",
                },
            ).status_code
            == 200
        )
        with factory() as session:
            user = session.scalar(select(User).where(User.username == "admin"))
            user.is_active = False
            session.commit()
        assert client.get("/api/auth/session").status_code == 401


def test_temp_password_one_time_and_admin_change(auth_environment):
    engine, settings = auth_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="admin", full_name="مدیر", password="admin-password-123")
        profile = create_guest_with_wallet(
            session, first_name="مهمان", last_name="رمز", phone="09120000013"
        )
    with TestClient(create_app(settings), base_url=ORIGIN) as guest_client:
        assert (
            guest_client.post(
                "/api/auth/guest/register",
                headers=HEADERS,
                json={
                    "first_name": "مهمان",
                    "last_name": "رمز",
                    "phone": "09120000013",
                    "password": "initial-password-123",
                },
            ).status_code
            == 201
        )
        with TestClient(create_app(settings), base_url=ORIGIN) as admin_client:
            assert (
                admin_client.post(
                    "/api/auth/admin/login",
                    headers=HEADERS,
                    json={
                        "username": "admin",
                        "password": "admin-password-123",
                    },
                ).status_code
                == 200
            )
            csrf = admin_client.cookies.get("hashti_csrf")
            issued = admin_client.post(
                f"/api/admin/guests/{profile.guest_id}/temp-password",
                headers={**HEADERS, "X-CSRF-Token": csrf},
            )
            assert issued.status_code == 200
            temporary = issued.json()["temporary_password"]
            assert issued.headers["cache-control"] == "no-store"
            with factory() as session:
                account = session.scalar(
                    select(GuestAccount).where(GuestAccount.guest_id == profile.guest_id)
                )
                assert account.password_hash != temporary
                assert account.must_change_password
                account.temp_password_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                session.commit()
            assert (
                guest_client.post(
                    "/api/auth/guest/login",
                    headers=HEADERS,
                    json={
                        "phone": "09120000013",
                        "password": temporary,
                    },
                ).status_code
                == 401
            )
            issued = admin_client.post(
                f"/api/admin/guests/{profile.guest_id}/temp-password",
                headers={**HEADERS, "X-CSRF-Token": csrf},
            )
            assert issued.status_code == 200
            temporary = issued.json()["temporary_password"]
            logged_in = guest_client.post(
                "/api/auth/guest/login",
                headers=HEADERS,
                json={
                    "phone": "09120000013",
                    "password": temporary,
                },
            )
            assert logged_in.status_code == 200
            assert logged_in.json()["must_change_password"]
            assert (
                guest_client.post(
                    "/api/auth/guest/login",
                    headers=HEADERS,
                    json={
                        "phone": "09120000013",
                        "password": temporary,
                    },
                ).status_code
                == 401
            )
            csrf = guest_client.cookies.get("hashti_csrf")
            changed = guest_client.post(
                "/api/auth/guest/change-password",
                headers={
                    **HEADERS,
                    "X-CSRF-Token": csrf,
                },
                json={"new_password": "new-guest-password-123"},
            )
            assert changed.status_code == 200
            assert guest_client.get("/api/auth/session").status_code == 401
            assert (
                guest_client.post(
                    "/api/auth/guest/login",
                    headers=HEADERS,
                    json={
                        "phone": "09120000013",
                        "password": "new-guest-password-123",
                    },
                ).status_code
                == 200
            )
            csrf = admin_client.cookies.get("hashti_csrf")
            assert (
                admin_client.post(
                    "/api/auth/admin/change-password",
                    headers={
                        **HEADERS,
                        "X-CSRF-Token": csrf,
                    },
                    json={
                        "current_password": "admin-password-123",
                        "new_password": "new-admin-password-123",
                    },
                ).status_code
                == 200
            )
            assert admin_client.get("/api/auth/session").status_code == 401
            assert (
                admin_client.post(
                    "/api/auth/admin/login",
                    headers=HEADERS,
                    json={
                        "username": "admin",
                        "password": "new-admin-password-123",
                    },
                ).status_code
                == 200
            )
