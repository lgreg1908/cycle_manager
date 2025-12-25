from datetime import datetime
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.employee import Employee
from app.models.rbac import Role, UserRole
from app.models.review_cycle import ReviewCycle
from app.models.review_assignment import ReviewAssignment
from app.models.field_definition import FieldDefinition
from app.models.form_template import FormTemplate
from app.models.form_template_field import FormTemplateField

def ensure_role(db, name: str) -> Role:
    r = db.query(Role).filter(Role.name == name).one_or_none()
    if r:
        return r
    r = Role(name=name)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r

def create_user(db, email: str, full_name="User", is_admin=False) -> User:
    u = User(email=email, full_name=full_name, is_active=True, is_admin=is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

def grant_role(db, user: User, role_name: str):
    role = ensure_role(db, role_name)
    exists = db.query(UserRole).filter(UserRole.user_id == user.id, UserRole.role_id == role.id).one_or_none()
    if not exists:
        db.add(UserRole(user_id=user.id, role_id=role.id))
        db.commit()

def create_employee(db, employee_number: str, display_name: str, user: User | None = None) -> Employee:
    e = Employee(employee_number=employee_number, display_name=display_name, user_id=(user.id if user else None))
    db.add(e)
    db.commit()
    db.refresh(e)
    return e

def create_cycle(db, created_by: User, status="DRAFT") -> ReviewCycle:
    c = ReviewCycle(name="Q4 Reviews", status=status, created_by_user_id=created_by.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

def create_assignment(db, cycle: ReviewCycle, reviewer: Employee, subject: Employee, approver: Employee, status="ACTIVE") -> ReviewAssignment:
    a = ReviewAssignment(
        cycle_id=cycle.id,
        reviewer_employee_id=reviewer.id,
        subject_employee_id=subject.id,
        approver_employee_id=approver.id,
        status=status,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a



def create_field_definition(
    db: Session,
    *,
    key: str,
    label: str = "Question",
    field_type: str = "text",
    required: bool = False,
    rules: dict | None = None,
) -> FieldDefinition:
    f = db.query(FieldDefinition).filter(FieldDefinition.key == key).one_or_none()
    if f:
        return f

    f = FieldDefinition(
        key=key,
        label=label,
        field_type=field_type,
        required=required,
        rules=rules,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def create_form_template(
    db: Session,
    *,
    name: str = "Test Form",
    version: int = 1,
    description: str | None = None,
) -> FormTemplate:
    form = (
        db.query(FormTemplate)
        .filter(FormTemplate.name == name, FormTemplate.version == version)
        .one_or_none()
    )
    if form:
        return form

    form = FormTemplate(
        name=name,
        version=version,
        description=description,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return form


def attach_field_to_form(
    db: Session,
    *,
    form: FormTemplate,
    field: FieldDefinition,
    position: int = 1,
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
    if row:
        row.position = position
        row.override_label = override_label
        row.override_required = override_required
        db.commit()
        db.refresh(row)
        return row

    row = FormTemplateField(
        form_template_id=form.id,
        field_definition_id=field.id,
        position=position,
        override_label=override_label,
        override_required=override_required,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_cycle_form_template(db: Session, *, cycle: ReviewCycle, form: FormTemplate) -> ReviewCycle:
    cycle.form_template_id = form.id
    cycle.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cycle)
    return cycle


def create_form_for_cycle_with_fields(
    db: Session,
    *,
    cycle,
    fields: list[dict],
    form_name: str = "Cycle Form",
    form_version: int = 1,
) -> FormTemplate:
    """
    fields example:
      [{"key":"q1","field_type":"text","required":False},
       {"key":"rating","field_type":"number","required":True,"rules":{"min":1,"max":5,"integer":True}}]
    """
    # ✅ remove is_active=True (your helper doesn't accept it)
    form = create_form_template(db, name=form_name, version=form_version)

    for idx, f in enumerate(fields, start=1):
        fd = create_field_definition(
            db,
            key=f["key"],
            label=f.get("label", f["key"]),
            field_type=f.get("field_type", "text"),
            required=f.get("required", False),
            rules=f.get("rules"),
        )
        attach_field_to_form(db, form=form, field=fd, position=idx)

    set_cycle_form_template(db, cycle=cycle, form=form)
    return form
