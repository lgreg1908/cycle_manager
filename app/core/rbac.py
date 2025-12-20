from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.rbac import Role, UserRole


def get_user_role_names(db: Session, user: User) -> set[str]:
    rows = (
        db.query(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user.id)
        .all()
    )
    return {r[0] for r in rows}


def require_roles(*required: str):
    """
    Usage:
      Depends(require_roles("ADMIN"))
      Depends(require_roles("ADMIN", "APPROVER"))  # any-of
    """
    required_set = set(required)

    def _dep(
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> User:
        role_names = get_user_role_names(db, user)
        if not (role_names & required_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden. Requires one of: {sorted(required_set)}",
            )
        return user

    return _dep
