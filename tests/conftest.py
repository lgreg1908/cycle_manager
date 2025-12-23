import pytest

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

# Note: do NOT bind this to the engine here; we'll bind to a per-test connection.
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
def db_session():
    """
    SQLAlchemy 2.0 best practice for tests:

    - Start ONE outer transaction per test (never committed).
    - Use join_transaction_mode="create_savepoint" so any app/session.commit()
      becomes a SAVEPOINT release, not a real commit of the outer transaction.
    - At the end of the test, we rollback the outer transaction -> clean DB.
    """
    connection = engine.connect()
    outer_tx = connection.begin()

    session = TestingSessionLocal(
        bind=connection,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        # Outer transaction is always safe to rollback here
        outer_tx.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def client():
    return TestClient(app)
