from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.core.database import build_engine


@pytest.fixture(scope="session")
def postgres_engine():
    settings = Settings()
    if settings.test_database_url is None:
        pytest.fail("HASHTI_TEST_DATABASE_URL must point to an isolated real PostgreSQL database")
    url = settings.test_database_url.get_secret_value()
    test_url = make_url(url)
    development_url = make_url(settings.database_url.get_secret_value())
    if not test_url.database.endswith("_test") or test_url.database == development_url.database:
        pytest.fail("Refusing to run integration tests against a non-test database")
    engine = build_engine(url)
    configuration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        configuration.attributes["connection"] = connection
        command.upgrade(configuration, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(postgres_engine):
    """Each test gets a real PostgreSQL transaction that is always rolled back."""
    with postgres_engine.connect() as connection:
        outer = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
