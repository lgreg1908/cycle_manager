import os
import pytest
from pathlib import Path

# Set ENV_FILE to .env.test before importing settings
# This ensures tests always use the test database configuration
BASE_DIR = Path(__file__).resolve().parents[1]  # project root
if "ENV_FILE" not in os.environ:
    os.environ["ENV_FILE"] = str(BASE_DIR / ".env.test")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.config import settings


def _assert_test_db(url: str):
    if "hr_platform_test" not in url and "_test" not in url:
        raise RuntimeError(f"Refusing to run tests on non-test database: {url}")


_assert_test_db(settings.DATABASE_URL)

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

TestingSessionLocal = sessionmaker(
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
def create_test_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_connection():
    """
    One connection + one outer transaction per test.
    Everything runs inside this transaction and gets rolled back at the end.
    """
    connection = engine.connect()
    outer_tx = connection.begin()
    try:
        yield connection
    finally:
        outer_tx.rollback()
        connection.close()


@pytest.fixture()
def db_session(db_connection):
    """
    Session for seeding inside the test (not used by the API requests).
    """
    session = TestingSessionLocal(
        bind=db_connection,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def override_get_db(db_connection):
    """
    FastAPI dependency override: create a NEW Session per request
    (still bound to the same per-test connection/outer transaction).

    IMPORTANT: commit on success so the test session can see rows.
    """
    def _get_db_override():
        db = TestingSessionLocal(
            bind=db_connection,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    return TestClient(app)
