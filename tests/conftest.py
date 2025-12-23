import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.config import settings


@pytest.fixture(scope="session")
def engine():
    # Create engine AFTER settings is loaded with ENV_FILE=.env.test
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


@pytest.fixture(scope="session", autouse=True)
def create_test_schema(engine):
    # One-time schema setup for the test database
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session(engine):
    """
    Provides a SQLAlchemy Session inside a transaction that is rolled back
    after each test, so tests don't leak data into each other.
    """
    connection = engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()
