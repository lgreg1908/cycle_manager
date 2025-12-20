from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# Import models so Alembic can discover them
from app.models import *  # noqa
