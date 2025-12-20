from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from fastapi import Depends


def get_current_user(
    x_user_email: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    DEV AUTH: pass X-User-Email header to simulate logged-in user.
    Example: X-User-Email: admin@local.test
    """
    if not x_user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Email header (dev auth)",
        )

    user = db.query(User).filter(User.email == x_user_email).one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user
