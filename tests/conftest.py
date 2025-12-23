import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="session", autouse=True)
def create_test_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    """
    Uses:
      - one outer transaction per test
      - one SAVEPOINT (nested transaction) inside it

    This allows application code to call session.commit() freely without
    breaking the test rollback strategy.
    """
    connection = engine.connect()
    outer_tx = connection.begin()

    session = TestingSessionLocal(bind=connection)

    # Start a SAVEPOINT
    session.begin_nested()

    # If app code commits, the SAVEPOINT ends. This hook recreates it so the test
    # continues running inside a savepoint.
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_tx.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()
