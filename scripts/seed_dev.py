from app.db.session import SessionLocal
from app.models.user import User

def main():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@local.test").one_or_none()
        if not admin:
            admin = User(email="admin@local.test", full_name="Admin Local", is_admin=True)
            db.add(admin)
            db.commit()
            db.refresh(admin)
        print("Admin:", admin.id, admin.email)
    finally:
        db.close()
        
if __name__ == "__main__":
    main()
