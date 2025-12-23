from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

# expire_on_commit=False prevents SQLAlchemy from expiring objects after commit,
# which avoids "ObjectDeletedError / Detached" surprises when you access attrs.
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False,)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
