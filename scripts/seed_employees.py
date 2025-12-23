from app.db.session import SessionLocal
from app.models.employee import Employee
from app.models.user import User

def upsert_employee(db, employee_number: str, display_name: str, user_email: str | None = None):
    emp = db.query(Employee).filter(Employee.employee_number == employee_number).one_or_none()
    if emp:
        return emp

    user_id = None
    if user_email:
        user = db.query(User).filter(User.email == user_email).one_or_none()
        user_id = user.id if user else None

    emp = Employee(employee_number=employee_number, display_name=display_name, user_id=user_id)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp

def main():
    db = SessionLocal()
    try:
        # Make 3 employees for demo
        e1 = upsert_employee(db, "E100", "Admin Local", "admin@local.test")
        e2 = upsert_employee(db, "E200", "Reviewer One", None)
        e3 = upsert_employee(db, "E300", "Subject One", None)

        print("Seeded employees:")
        for e in [e1, e2, e3]:
            print(e.employee_number, e.display_name, e.id, e.user_id)
    finally:
        db.close()

if __name__ == "__main__":
    main()
