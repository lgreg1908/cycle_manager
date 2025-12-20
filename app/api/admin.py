from fastapi import APIRouter, Depends

from app.core.rbac import require_roles
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping")
def admin_ping(current_user: User = Depends(require_roles("ADMIN"))):
    return {"status": "ok", "admin": current_user.email}
