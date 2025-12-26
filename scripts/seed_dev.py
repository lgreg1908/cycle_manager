# seed_dev.py
import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.employee import Employee
from app.models.rbac import Role, UserRole
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment

from app.models.field_definition import FieldDefinition
from app.models.form_template import FormTemplate
from app.models.form_template_field import FormTemplateField


# ---------- helpers: RBAC ----------

def get_or_create_role(db: Session, name: str) -> Role:
    r = db.query(Role).filter(Role.name == name).one_or_none()
    if r:
        return r
    r = Role(name=name)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def get_or_create_user(db: Session, email: str, full_name: str, is_admin: bool = False) -> User:
    u = db.query(User).filter(User.email == email).one_or_none()
    if u:
        # keep these up to date in dev
        changed = False
        if u.full_name != full_name:
            u.full_name = full_name
            changed = True
        if u.is_admin != is_admin:
            u.is_admin = is_admin
            changed = True
        if not u.is_active:
            u.is_active = True
            changed = True
        if changed:
            db.commit()
            db.refresh(u)
        return u

    u = User(email=email, full_name=full_name, is_active=True, is_admin=is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def ensure_user_role(db: Session, user_id, role_id):
    ur = (
        db.query(UserRole)
        .filter(UserRole.user_id == user_id, UserRole.role_id == role_id)
        .one_or_none()
    )
    if ur:
        return ur
    ur = UserRole(user_id=user_id, role_id=role_id)
    db.add(ur)
    db.commit()
    return ur


def get_or_create_employee(db: Session, employee_number: str, display_name: str, user_id):
    e = db.query(Employee).filter(Employee.employee_number == employee_number).one_or_none()
    if e:
        changed = False
        if e.display_name != display_name:
            e.display_name = display_name
            changed = True
        if e.user_id != user_id:
            e.user_id = user_id
            changed = True
        if changed:
            db.commit()
            db.refresh(e)
        return e

    e = Employee(
        employee_number=employee_number,
        display_name=display_name,
        user_id=user_id,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


# ---------- helpers: Forms ----------

def get_or_create_field_definition(
    db: Session,
    *,
    key: str,
    label: str,
    field_type: str,
    required: bool = False,
    rules: dict | None = None,
) -> FieldDefinition:
    f = db.query(FieldDefinition).filter(FieldDefinition.key == key).one_or_none()
    now = datetime.utcnow()
    if f:
        # keep dev seed "desired state"
        changed = False
        if f.label != label:
            f.label = label
            changed = True
        if f.field_type != field_type:
            f.field_type = field_type
            changed = True
        if f.required != required:
            f.required = required
            changed = True
        if f.rules != rules:
            f.rules = rules
            changed = True
        if changed:
            f.updated_at = now
            db.commit()
            db.refresh(f)
        return f

    f = FieldDefinition(
        key=key,
        label=label,
        field_type=field_type,
        required=required,
        rules=rules,
        created_at=now,
        updated_at=now,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def get_or_create_form_template(
    db: Session,
    *,
    name: str,
    version: int,
    description: str | None = None,
    is_active: bool = True,
) -> FormTemplate:
    form = (
        db.query(FormTemplate)
        .filter(FormTemplate.name == name, FormTemplate.version == version)
        .one_or_none()
    )
    now = datetime.utcnow()
    if form:
        changed = False
        if form.description != description:
            form.description = description
            changed = True
        if form.is_active != is_active:
            form.is_active = is_active
            changed = True
        if changed:
            form.updated_at = now
            db.commit()
            db.refresh(form)
        return form

    form = FormTemplate(
        name=name,
        version=version,
        description=description,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


def upsert_form_field(
    db: Session,
    *,
    form: FormTemplate,
    field: FieldDefinition,
    position: int,
    override_label: str | None = None,
    override_required: bool | None = None,
) -> FormTemplateField:
    row = (
        db.query(FormTemplateField)
        .filter(
            FormTemplateField.form_template_id == form.id,
            FormTemplateField.field_definition_id == field.id,
        )
        .one_or_none()
    )

    now = datetime.utcnow()
    if row:
        changed = False
        if row.position != position:
            row.position = position
            changed = True
        if row.override_label != override_label:
            row.override_label = override_label
            changed = True
        if row.override_required != override_required:
            row.override_required = override_required
            changed = True
        if changed:
            db.commit()
            db.refresh(row)
        return row

    row = FormTemplateField(
        form_template_id=form.id,
        field_definition_id=field.id,
        position=position,
        override_label=override_label,
        override_required=override_required,
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------- helpers: Cycles / assignments ----------

def get_or_create_cycle(
    db: Session,
    *,
    name: str,
    created_by_user_id,
    start_date: date,
    end_date: date,
    status: str = "ACTIVE",
) -> ReviewCycle:
    c = db.query(ReviewCycle).filter(ReviewCycle.name == name).one_or_none()
    now = datetime.utcnow()
    if c:
        changed = False
        if c.start_date != start_date:
            c.start_date = start_date
            changed = True
        if c.end_date != end_date:
            c.end_date = end_date
            changed = True
        if c.status != status:
            c.status = status
            changed = True
        if changed:
            c.updated_at = now
            db.commit()
            db.refresh(c)
        return c

    c = ReviewCycle(
        name=name,
        start_date=start_date,
        end_date=end_date,
        status=status,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def set_cycle_form_template(db: Session, *, cycle: ReviewCycle, form: FormTemplate) -> ReviewCycle:
    now = datetime.utcnow()
    if cycle.form_template_id != form.id:
        cycle.form_template_id = form.id
        cycle.updated_at = now
        db.commit()
        db.refresh(cycle)
    return cycle


def get_or_create_assignment(
    db: Session,
    *,
    cycle_id,
    reviewer_emp_id,
    subject_emp_id,
    approver_emp_id,
    status: str = "ACTIVE",
) -> ReviewAssignment:
    a = (
        db.query(ReviewAssignment)
        .filter(
            ReviewAssignment.cycle_id == cycle_id,
            ReviewAssignment.reviewer_employee_id == reviewer_emp_id,
            ReviewAssignment.subject_employee_id == subject_emp_id,
        )
        .one_or_none()
    )
    if a:
        changed = False
        if a.approver_employee_id != approver_emp_id:
            a.approver_employee_id = approver_emp_id
            changed = True
        if a.status != status:
            a.status = status
            changed = True
        if changed:
            db.commit()
            db.refresh(a)
        return a

    a = ReviewAssignment(
        cycle_id=cycle_id,
        reviewer_employee_id=reviewer_emp_id,
        subject_employee_id=subject_emp_id,
        approver_employee_id=approver_emp_id,
        status=status,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ---------- main ----------

def main():
    db = SessionLocal()
    try:
        # ---- Roles ----
        admin_role = get_or_create_role(db, "ADMIN")
        get_or_create_role(db, "REVIEWER")
        get_or_create_role(db, "APPROVER")

        # ---- Users ----
        admin_user = get_or_create_user(db, "admin@local.test", "Admin Local", is_admin=True)
        reviewer_user = get_or_create_user(db, "reviewer@local.test", "Reviewer Local")
        approver_user = get_or_create_user(db, "approver@local.test", "Approver Local")
        subject_user = get_or_create_user(db, "subject@local.test", "Subject Local")

        ensure_user_role(db, admin_user.id, admin_role.id)

        # ---- Employees (1:1 with users) ----
        admin_emp = get_or_create_employee(db, "E100", "Admin Local", admin_user.id)
        reviewer_emp = get_or_create_employee(db, "E200", "Reviewer Local", reviewer_user.id)
        approver_emp = get_or_create_employee(db, "E300", "Approver Local", approver_user.id)
        subject_emp = get_or_create_employee(db, "E400", "Subject Local", subject_user.id)

        # ---- Form: field defs + template ----
        # Keep it small but representative: comment + rating + manager reference
        fd_comment = get_or_create_field_definition(
            db,
            key="q1",
            label="Overall Comments",
            field_type="text",
            required=False,
            rules={"max_length": 2000},
        )
        fd_rating = get_or_create_field_definition(
            db,
            key="overall_rating",
            label="Overall Rating (1-5)",
            field_type="number",
            required=True,
            rules={"min": 1, "max": 5, "integer": True},
        )
        fd_perf_mgr = get_or_create_field_definition(
            db,
            key="performance_manager",
            label="Performance Manager",
            field_type="employee_reference",
            required=False,  # keep optional for dev
            rules=None,
        )

        form = get_or_create_form_template(
            db,
            name="Demo Evaluation Form",
            version=1,
            description="Dev seed form: q1 + overall_rating + performance_manager",
            is_active=True,
        )

        upsert_form_field(db, form=form, field=fd_comment, position=1)
        upsert_form_field(db, form=form, field=fd_rating, position=2)
        upsert_form_field(db, form=form, field=fd_perf_mgr, position=3)

        # ---- Demo cycle ----
        cycle = get_or_create_cycle(
            db,
            name="Demo Cycle - Q4 2024",
            created_by_user_id=admin_user.id,
            start_date=date(2024, 10, 1),
            end_date=date(2024, 12, 31),
            status="ACTIVE",  # important for evaluation flow
        )

        set_cycle_form_template(db, cycle=cycle, form=form)

        # ---- Assignment ----
        assignment = get_or_create_assignment(
            db,
            cycle_id=cycle.id,
            reviewer_emp_id=reviewer_emp.id,
            subject_emp_id=subject_emp.id,
            approver_emp_id=approver_emp.id,
            status="ACTIVE",
        )

        print("\n=== DEV SEED COMPLETE ===")
        print("Users:")
        print(f"  admin:    {admin_user.email}")
        print(f"  reviewer: {reviewer_user.email}")
        print(f"  approver: {approver_user.email}")
        print(f"  subject:  {subject_user.email}")

        print("\nEmployees:")
        print(f"  admin_employee_id:    {admin_emp.id}")
        print(f"  reviewer_employee_id: {reviewer_emp.id}")
        print(f"  subject_employee_id:  {subject_emp.id}")
        print(f"  approver_employee_id: {approver_emp.id}")

        print("\nForm:")
        print(f"  form_template_id: {form.id} (name={form.name} v{form.version})")
        print("  fields:")
        print("   - q1 (text)")
        print("   - overall_rating (number, required)")
        print("   - performance_manager (employee_reference)")

        print("\nCycle:")
        print(f"  cycle_id: {cycle.id} (status={cycle.status})")
        print(f"  cycle.form_template_id: {cycle.form_template_id}")

        print("\nAssignment:")
        print(f"  assignment_id: {assignment.id}")

        print("\nNext API steps (Postman):")
        print(f"  POST /cycles/{cycle.id}/assignments/{assignment.id}/evaluation  (as reviewer@local.test)")
        print(f"  POST /cycles/{cycle.id}/evaluations/<eval_id>/draft (If-Match: <version>)")
        print(f"  POST /cycles/{cycle.id}/evaluations/<eval_id>/submit (If-Match: <version>)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
