from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select

from alembic import command
from app.api.dependencies import require_event_secretary, require_guest_ownership
from app.core.config import Settings
from app.core.database import build_session_factory
from app.core.security import CSRF_COOKIE
from app.main import create_app
from app.models import (
    AuditLog,
    Event,
    EventSecretary,
    PaymentSubmission,
    Registration,
    Setting,
    User,
    Wallet,
)
from app.seed import bootstrap_admin
from app.services.auth import Actor, register_guest

ORIGIN = "http://testserver"
HEADERS = {"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def management_environment(postgres_engine):
    schema = "h05_" + uuid4().hex[:12]
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


def login(client, username, password):
    response = client.post(
        "/api/auth/admin/login",
        headers=HEADERS,
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def write_headers(client):
    return {**HEADERS, "X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}


def test_super_admin_manages_secretaries_and_settings(management_environment):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    app = create_app(settings)
    with (
        TestClient(app, base_url=ORIGIN) as super_client,
        TestClient(app, base_url=ORIGIN) as secretary_client,
    ):
        login(super_client, "boss", "boss-password-123")
        assert super_client.post(
            "/api/admin/users", headers=HEADERS,
            json={"username": "sec", "full_name": "دبیر", "password": "secretary-password"},
        ).status_code == 403
        created = super_client.post(
            "/api/admin/users", headers=write_headers(super_client),
            json={"username": "sec", "full_name": "دبیر", "password": "secretary-password"},
        )
        assert created.status_code == 201, created.text
        user_id = created.json()["id"]
        assert "password_hash" not in created.json()
        assert len(super_client.get("/api/admin/users").json()) == 2
        login(secretary_client, "sec", "secretary-password")
        assert secretary_client.get("/api/admin/users").status_code == 403
        assert secretary_client.patch(
            "/api/admin/settings", headers=write_headers(secretary_client),
            json={"default_debt_ceiling": 1000},
        ).status_code == 403
        assert super_client.patch(
            "/api/admin/settings", headers=write_headers(super_client),
            json={"default_debt_ceiling": -1},
        ).status_code == 422
        changed = super_client.patch(
            "/api/admin/settings", headers=write_headers(super_client),
            json={"organization_name": "هشتی", "default_debt_ceiling": 500000,
                  "telegram_support_link": "https://t.me/hashti"},
        )
        assert changed.status_code == 200, changed.text
        assert super_client.get("/api/admin/settings").json()["default_debt_ceiling"] == 500000
        assert super_client.patch(
            f"/api/admin/users/{user_id}", headers=write_headers(super_client),
            json={"is_active": False},
        ).status_code == 200
        assert secretary_client.get("/api/auth/session").status_code == 401
        assert secretary_client.post(
            "/api/auth/admin/login", headers=HEADERS,
            json={"username": "sec", "password": "secretary-password"},
        ).status_code == 401
        assert super_client.get(f"/api/admin/users/{user_id}").json()["is_active"] is False
        assert super_client.patch(
            f"/api/admin/users/{user_id}", headers=write_headers(super_client),
            json={"is_active": True, "new_password": "changed-password-123"},
        ).status_code == 200
        login(secretary_client, "sec", "changed-password-123")
        assert secretary_client.get("/api/auth/session").status_code == 200
    with factory() as session:
        assert session.get(User, user_id) is not None
        assert session.get(Setting, "default_debt_ceiling").value == 500000
        assert session.scalar(select(func.count()).select_from(AuditLog)) >= 3


def test_event_assignment_and_guest_resource_ownership(management_environment):
    engine, settings = management_environment
    factory = build_session_factory(engine)
    with factory() as session:
        bootstrap_admin(session, username="boss", full_name="مدیر", password="boss-password-123")
    with TestClient(create_app(settings), base_url=ORIGIN) as client:
        login(client, "boss", "boss-password-123")
        first = client.post(
            "/api/admin/users", headers=write_headers(client),
            json={"username": "first", "full_name": "اول", "password": "secretary-password"},
        ).json()["id"]
        second = client.post(
            "/api/admin/users", headers=write_headers(client),
            json={"username": "second", "full_name": "دوم", "password": "secretary-password"},
        ).json()["id"]
        with factory() as session, session.begin():
            event = Event(event_number=1, title="رویداد", entry_fee=0)
            session.add(event)
            session.flush()
            event_id = event.id
            session.add(EventSecretary(event_id=event_id, user_id=first))
        with factory() as session:
            assert require_event_secretary(event_id, Actor("user", first, 1, "secretary"), session)
            assert require_event_secretary(event_id, Actor("user", 1, 1, "super_admin"), session)
            with pytest.raises(HTTPException) as denied:
                require_event_secretary(event_id, Actor("user", second, 1, "secretary"), session)
            assert denied.value.status_code == 403
        assert client.patch(
            f"/api/admin/users/{first}", headers=write_headers(client),
            json={"is_active": False},
        ).status_code == 200
        with factory() as session:
            assert session.get(EventSecretary, (event_id, first)) is not None
    with factory() as session:
        guest_one, account_one = register_guest(
            session, first_name="یک", last_name="مهمان", phone="09120000031",
            password="guest-password-123", settings=settings,
        )
        guest_two, account_two = register_guest(
            session, first_name="دو", last_name="مهمان", phone="09120000032",
            password="guest-password-123", settings=settings,
        )
    with factory() as session, session.begin():
        registration = Registration(event_id=event_id, guest_id=guest_one, source="admin")
        payment = PaymentSubmission(
            guest_id=guest_one, amount=1000, tracking_code="test-code",
            idempotency_key="h05-payment-test",
        )
        session.add_all([registration, payment])
        session.flush()
        registration_id = registration.id
        payment_id = payment.id
        wallet_id = session.scalar(select(Wallet.id).where(Wallet.guest_id == guest_one))
    with factory() as session:
        actor_one = Actor("guest", account_one, 1)
        actor_two = Actor("guest", account_two, 1)
        assert require_guest_ownership(
            session, actor=actor_one, resource_type="registration", resource_id=registration_id
        ) == guest_one
        with pytest.raises(HTTPException) as denied:
            require_guest_ownership(
                session, actor=actor_two, resource_type="registration", resource_id=registration_id
            )
        assert denied.value.status_code == 404
        for resource_type, resource_id in (("payment", payment_id), ("wallet", wallet_id)):
            assert require_guest_ownership(
                session, actor=actor_one, resource_type=resource_type, resource_id=resource_id
            ) == guest_one
            with pytest.raises(HTTPException) as denied:
                require_guest_ownership(
                    session, actor=actor_two, resource_type=resource_type,
                    resource_id=resource_id,
                )
            assert denied.value.status_code == 404
        assert guest_two != guest_one
