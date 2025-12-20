from app.db.session import SessionLocal
from app.models.user import User
from app.models.rbac import Role, UserRole


def main():
    db = SessionLocal()
    try:
        # Ensure user exists
        user = db.query(User).filter(User.email == "admin@local.test").one_or_none()
        if not user:
            user = User(email="admin@local.test", full_name="Admin Local", is_admin=True)
            db.add(user)
            db.commit()
            db.refresh(user)

        # Ensure role exists
        admin_role = db.query(Role).filter(Role.name == "ADMIN").one()

        # Ensure mapping exists
        exists = (
            db.query(UserRole)
            .filter(UserRole.user_id == user.id, UserRole.role_id == admin_role.id)
            .one_or_none()
        )
        if not exists:
            db.add(UserRole(user_id=user.id, role_id=admin_role.id))
            db.commit()

        print("Admin user:", user.email, user.id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
