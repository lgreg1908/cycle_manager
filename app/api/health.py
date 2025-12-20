from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from fastapi import Depends

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    # Simple DB ping
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
