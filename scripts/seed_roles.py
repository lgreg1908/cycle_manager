from app.db.session import SessionLocal
from app.models.rbac import Role

ROLE_NAMES = ["ADMIN", "REVIEWER", "APPROVER"]

def main():
    db = SessionLocal()
    try:
        existing = {r.name for r in db.query(Role).all()}
        to_add = [Role(name=name) for name in ROLE_NAMES if name not in existing]
        if to_add:
            db.add_all(to_add)
            db.commit()
        print("Roles seeded:", ROLE_NAMES)
    finally:
        db.close()

if __name__ == "__main__":
    main()
