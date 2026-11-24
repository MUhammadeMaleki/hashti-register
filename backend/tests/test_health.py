from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import health as health_api
from app.core.config import Settings
from app.main import create_app


def test_liveness_does_not_require_database():
    settings = Settings(database_url="postgresql+psycopg://unused@127.0.0.1:1/unused")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json() == {"status": "ok", "service": "hashti-api"}


def test_readiness_does_not_expose_connection_errors():
    class UnavailableEngine:
        def connect(self):
            raise OperationalError("secret connection", {}, Exception("private credential"))

    settings = Settings(database_url="postgresql+psycopg://unused@127.0.0.1:1/unused")
    with TestClient(create_app(settings)) as client, patch.object(
        health_api.logger, "warning"
    ) as warning:
        client.app.state.engine = UnavailableEngine()
        response = client.get("/api/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        warning.assert_called_once_with("database_readiness_failed")


def test_real_postgresql_and_migration(postgres_engine):
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT current_database()")).scalar_one().endswith("_test")
        assert connection.execute(text("SELECT version()")).scalar_one().startswith("PostgreSQL")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "e53b72f6a0c4"
        )


def test_real_readiness(postgres_engine):
    url = postgres_engine.url.render_as_string(hide_password=False)
    with TestClient(create_app(Settings(database_url=url))) as client:
        response = client.get("/api/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "postgresql"}
