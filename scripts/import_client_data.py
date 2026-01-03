#!/usr/bin/env python3
"""
Import client data into the Cycle Manager database.

This script reads client data from CSV/JSON files and imports them into the database
in the correct dependency order. All operations are idempotent and can be safely re-run.

Usage:
    python scripts/import_client_data.py
    python scripts/import_client_data.py --data-dir /path/to/data
    python scripts/import_client_data.py --dry-run
    python scripts/import_client_data.py --verbose
"""

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Load environment variables
load_dotenv()

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.employee import Employee
from app.models.field_definition import FieldDefinition
from app.models.form_template import FormTemplate
from app.models.form_template_field import FormTemplateField
from app.models.rbac import Role, UserRole
from app.models.review_assignment import ReviewAssignment
from app.models.review_cycle import ReviewCycle
from app.models.user import User


# ============================================================================
# Helper Functions (reused from seed_dev.py pattern)
# ============================================================================

def get_or_create_role(db: Session, name: str) -> tuple[Role, bool]:
    """Get or create a role. Returns (role, created)."""
    r = db.query(Role).filter(Role.name == name).one_or_none()
    if r:
        return r, False
    r = Role(name=name)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r, True


def get_or_create_user(
    db: Session, email: str, full_name: str, is_admin: bool = False, is_active: bool = True
) -> tuple[User, bool]:
    """Get or create a user. Returns (user, created)."""
    u = db.query(User).filter(User.email == email).one_or_none()
    if u:
        changed = False
        if u.full_name != full_name:
            u.full_name = full_name
            changed = True
        if u.is_admin != is_admin:
            u.is_admin = is_admin
            changed = True
        if u.is_active != is_active:
            u.is_active = is_active
            changed = True
        if changed:
            db.commit()
            db.refresh(u)
        return u, False
    u = User(email=email, full_name=full_name, is_active=is_active, is_admin=is_admin)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u, True


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email."""
    return db.query(User).filter(User.email == email).one_or_none()


def get_or_create_employee(
    db: Session, employee_number: str, display_name: str, user_id: Optional[str] = None
) -> tuple[Employee, bool]:
    """Get or create an employee. Returns (employee, created)."""
    e = db.query(Employee).filter(Employee.employee_number == employee_number).one_or_none()
    if e:
        changed = False
        if e.display_name != display_name:
            e.display_name = display_name
            changed = True
        if user_id and e.user_id != user_id:
            e.user_id = user_id
            changed = True
        if changed:
            db.commit()
            db.refresh(e)
        return e, False
    e = Employee(employee_number=employee_number, display_name=display_name, user_id=user_id)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e, True


def get_employee_by_number(db: Session, employee_number: str) -> Optional[Employee]:
    """Get employee by employee number."""
    return db.query(Employee).filter(Employee.employee_number == employee_number).one_or_none()


def get_role_by_name(db: Session, role_name: str) -> Optional[Role]:
    """Get role by name."""
    return db.query(Role).filter(Role.name == role_name).one_or_none()


def ensure_user_role(db: Session, user_id: str, role_id: str) -> tuple[UserRole, bool]:
    """Ensure user has role. Returns (user_role, created)."""
    ur = db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.role_id == role_id).one_or_none()
    if ur:
        return ur, False
    ur = UserRole(user_id=user_id, role_id=role_id)
    db.add(ur)
    db.commit()
    return ur, True


def get_or_create_field_definition(
    db: Session,
    *,
    key: str,
    label: str,
    field_type: str,
    required: bool = False,
    rules: dict | None = None,
) -> tuple[FieldDefinition, bool]:
    """Get or create a field definition. Returns (field, created)."""
    f = db.query(FieldDefinition).filter(FieldDefinition.key == key).one_or_none()
    now = datetime.utcnow()
    if f:
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
        return f, False
    f = FieldDefinition(
        key=key, label=label, field_type=field_type, required=required, rules=rules, created_at=now, updated_at=now
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f, True


def get_or_create_form_template(
    db: Session,
    *,
    name: str,
    version: int,
    description: str | None = None,
    is_active: bool = True,
) -> tuple[FormTemplate, bool]:
    """Get or create a form template. Returns (form, created)."""
    form = db.query(FormTemplate).filter(FormTemplate.name == name, FormTemplate.version == version).one_or_none()
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
        return form, False
    form = FormTemplate(
        name=name, version=version, description=description, is_active=is_active, created_at=now, updated_at=now
    )
    db.add(form)
    db.commit()
    db.refresh(form)
    return form, True


def upsert_form_field(
    db: Session,
    *,
    form: FormTemplate,
    field: FieldDefinition,
    position: int,
    override_label: str | None = None,
    override_required: bool | None = None,
) -> tuple[FormTemplateField, bool]:
    """Upsert a form field. Returns (form_field, created)."""
    row = (
        db.query(FormTemplateField)
        .filter(FormTemplateField.form_template_id == form.id, FormTemplateField.field_definition_id == field.id)
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
        return row, False
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
    return row, True


def get_or_create_cycle(
    db: Session,
    *,
    name: str,
    created_by_user_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str = "DRAFT",
) -> tuple[ReviewCycle, bool]:
    """Get or create a review cycle. Returns (cycle, created)."""
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
        return c, False
    c = ReviewCycle(
        name=name, start_date=start_date, end_date=end_date, status=status, created_by_user_id=created_by_user_id, created_at=now, updated_at=now
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c, True


def get_or_create_assignment(
    db: Session,
    *,
    cycle_id: str,
    reviewer_emp_id: str,
    subject_emp_id: str,
    approver_emp_id: str,
    status: str = "ACTIVE",
) -> tuple[ReviewAssignment, bool]:
    """Get or create a review assignment. Returns (assignment, created)."""
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
        return a, False
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
    return a, True


# ============================================================================
# Data Loading Functions
# ============================================================================

def load_csv(file_path: Path) -> List[Dict[str, Any]]:
    """Load CSV file and return list of dictionaries."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_json(file_path: Path) -> List[Dict[str, Any]]:
    """Load JSON file and return list of dictionaries."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# Validation Functions
# ============================================================================

class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def validate_files(data_dir: Path) -> None:
    """Validate that all required files exist."""
    required_files = [
        "employees.csv",
        "users.csv",
        "user_roles.csv",
        "assignments.csv",
        "field_definitions.json",
        "form_templates.json",
    ]
    missing = []
    for file_name in required_files:
        if not (data_dir / file_name).exists():
            missing.append(file_name)
    if missing:
        raise ValidationError(f"Missing required files: {', '.join(missing)}")


def validate_data(data_dir: Path, verbose: bool = False) -> None:
    """Validate data integrity before import."""
    errors = []

    # Load data
    try:
        employees = load_csv(data_dir / "employees.csv")
        users = load_csv(data_dir / "users.csv")
        user_roles = load_csv(data_dir / "user_roles.csv")
        assignments = load_csv(data_dir / "assignments.csv")
        field_definitions = load_json(data_dir / "field_definitions.json")
        form_templates = load_json(data_dir / "form_templates.json")
    except Exception as e:
        errors.append(f"Failed to load data files: {e}")
        raise ValidationError("\n".join(errors))

    # Build lookup sets
    employee_numbers = {row["employee_number"] for row in employees}
    user_emails = {row["email"] for row in users}
    field_keys = {field["key"] for field in field_definitions}

    # Validate employees
    for i, emp in enumerate(employees, start=2):  # Start at 2 (header is row 1)
        if not emp.get("employee_number"):
            errors.append(f"employees.csv:{i}: Missing employee_number")
        if not emp.get("display_name"):
            errors.append(f"employees.csv:{i}: Missing display_name")
        manager_num = emp.get("manager_employee_number", "").strip()
        if manager_num and manager_num not in employee_numbers:
            errors.append(f"employees.csv:{i}: manager_employee_number '{manager_num}' not found")

    # Validate users
    for i, user in enumerate(users, start=2):
        if not user.get("email"):
            errors.append(f"users.csv:{i}: Missing email")
        if not user.get("full_name"):
            errors.append(f"users.csv:{i}: Missing full_name")
        emp_num = user.get("employee_number", "").strip()
        if emp_num and emp_num not in employee_numbers:
            errors.append(f"users.csv:{i}: employee_number '{emp_num}' not found in employees.csv")

    # Validate user_roles
    for i, ur in enumerate(user_roles, start=2):
        email = ur.get("user_email", "").strip() or ur.get("email", "").strip()
        if not email:
            errors.append(f"user_roles.csv:{i}: Missing email")
        elif email not in user_emails:
            errors.append(f"user_roles.csv:{i}: email '{email}' not found in users.csv")
        role_name = ur.get("role_name", "").strip()
        if role_name not in ["ADMIN", "REVIEWER", "APPROVER"]:
            errors.append(f"user_roles.csv:{i}: Invalid role_name '{role_name}' (must be ADMIN, REVIEWER, or APPROVER)")

    # Validate assignments
    for i, assign in enumerate(assignments, start=2):
        if not assign.get("cycle_name"):
            errors.append(f"assignments.csv:{i}: Missing cycle_name")
        reviewer_num = assign.get("reviewer_employee_number", "").strip()
        if reviewer_num and reviewer_num not in employee_numbers:
            errors.append(f"assignments.csv:{i}: reviewer_employee_number '{reviewer_num}' not found")
        subject_num = assign.get("subject_employee_number", "").strip()
        if subject_num and subject_num not in employee_numbers:
            errors.append(f"assignments.csv:{i}: subject_employee_number '{subject_num}' not found")
        approver_num = assign.get("approver_employee_number", "").strip()
        if approver_num and approver_num not in employee_numbers:
            errors.append(f"assignments.csv:{i}: approver_employee_number '{approver_num}' not found")

    # Validate form_templates
    for i, form in enumerate(form_templates, start=1):
        if not form.get("name"):
            errors.append(f"form_templates.json:[{i}]: Missing name")
        if "fields" not in form:
            errors.append(f"form_templates.json:[{i}]: Missing fields array")
        else:
            for j, field_ref in enumerate(form["fields"], start=1):
                field_key = field_ref.get("field_key", "").strip()
                if not field_key:
                    errors.append(f"form_templates.json:[{i}].fields[{j}]: Missing field_key")
                elif field_key not in field_keys:
                    errors.append(f"form_templates.json:[{i}].fields[{j}]: field_key '{field_key}' not found in field_definitions.json")

    if errors:
        if verbose:
            print("\nValidation errors:")
            for error in errors:
                print(f"  ❌ {error}")
        raise ValidationError(f"Validation failed with {len(errors)} error(s)")

    if verbose:
        print(f"✓ Validation passed: {len(employees)} employees, {len(users)} users, {len(assignments)} assignments")


# ============================================================================
# Import Functions
# ============================================================================

def import_roles(db: Session, verbose: bool = False) -> Dict[str, int]:
    """Import roles (ADMIN, REVIEWER, APPROVER). Returns stats."""
    stats = {"created": 0, "updated": 0}
    role_names = ["ADMIN", "REVIEWER", "APPROVER"]
    for name in role_names:
        _, created = get_or_create_role(db, name)
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1
    if verbose:
        print(f"  Roles: {stats['created']} created, {stats['updated']} already exist")
    return stats


def import_field_definitions(db: Session, data_dir: Path, verbose: bool = False) -> Dict[str, int]:
    """Import field definitions from JSON. Returns stats."""
    stats = {"created": 0, "updated": 0}
    fields = load_json(data_dir / "field_definitions.json")
    for field_data in fields:
        _, created = get_or_create_field_definition(
            db,
            key=field_data["key"],
            label=field_data["label"],
            field_type=field_data["field_type"],
            required=field_data.get("required", False),
            rules=field_data.get("rules"),
        )
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1
    if verbose:
        print(f"  Field Definitions: {stats['created']} created, {stats['updated']} updated")
    return stats


def import_form_templates(db: Session, data_dir: Path, verbose: bool = False) -> Dict[str, int]:
    """Import form templates from JSON. Returns stats."""
    stats = {"created": 0, "updated": 0, "fields_attached": 0}
    forms = load_json(data_dir / "form_templates.json")
    for form_data in forms:
        form, created = get_or_create_form_template(
            db,
            name=form_data["name"],
            version=form_data.get("version", 1),
            description=form_data.get("description"),
            is_active=form_data.get("is_active", True),
        )
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1

        # Attach fields
        for field_ref in form_data.get("fields", []):
            field_key = field_ref["field_key"]
            field = db.query(FieldDefinition).filter(FieldDefinition.key == field_key).one()
            _, field_created = upsert_form_field(
                db,
                form=form,
                field=field,
                position=field_ref.get("position", 0),
                override_label=field_ref.get("override_label"),
                override_required=field_ref.get("override_required"),
            )
            if field_created:
                stats["fields_attached"] += 1
    if verbose:
        print(f"  Form Templates: {stats['created']} created, {stats['updated']} updated, {stats['fields_attached']} fields attached")
    return stats


def import_users(db: Session, data_dir: Path, verbose: bool = False) -> Dict[str, int]:
    """Import users from CSV. Returns stats."""
    stats = {"created": 0, "updated": 0}
    users = load_csv(data_dir / "users.csv")
    for user_data in users:
        is_admin = user_data.get("is_admin", "").lower() in ["true", "1", "yes"]
        is_active = user_data.get("is_active", "true").lower() not in ["false", "0", "no"]
        _, created = get_or_create_user(
            db,
            email=user_data["email"],
            full_name=user_data["full_name"],
            is_admin=is_admin,
            is_active=is_active,
        )
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1
    if verbose:
        print(f"  Users: {stats['created']} created, {stats['updated']} updated")
    return stats


def import_employees(db: Session, data_dir: Path, verbose: bool = False) -> Dict[str, int]:
    """Import employees from CSV. Returns stats."""
    stats = {"created": 0, "updated": 0}
    employees = load_csv(data_dir / "employees.csv")
    users = load_csv(data_dir / "users.csv")

    # Build email -> user_id mapping
    email_to_user_id = {}
    for user_data in users:
        user = get_user_by_email(db, user_data["email"])
        if user:
            email_to_user_id[user_data["email"]] = user.id

    # Build employee_number -> user_id mapping from users.csv
    emp_num_to_user_id = {}
    for user_data in users:
        emp_num = user_data.get("employee_number", "").strip()
        if emp_num and emp_num in email_to_user_id:
            emp_num_to_user_id[emp_num] = email_to_user_id[user_data["email"]]

    for emp_data in employees:
        emp_num = emp_data["employee_number"]
        user_id = emp_num_to_user_id.get(emp_num)
        _, created = get_or_create_employee(
            db, employee_number=emp_num, display_name=emp_data["display_name"], user_id=user_id
        )
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1
    if verbose:
        print(f"  Employees: {stats['created']} created, {stats['updated']} updated")
    return stats


def import_user_roles(db: Session, data_dir: Path, verbose: bool = False) -> Dict[str, int]:
    """Import user roles from CSV. Returns stats."""
    stats = {"created": 0, "skipped": 0}
    user_roles = load_csv(data_dir / "user_roles.csv")
    for ur_data in user_roles:
        # Handle both 'email' and 'user_email' column names
        email = ur_data.get("user_email", "").strip() or ur_data.get("email", "").strip()
        role_name = ur_data["role_name"].strip()
        user = get_user_by_email(db, email)
        if not user:
            if verbose:
                print(f"  Warning: User '{email}' not found, skipping role assignment")
            stats["skipped"] += 1
            continue
        role = get_role_by_name(db, role_name)
        if not role:
            if verbose:
                print(f"  Warning: Role '{role_name}' not found, skipping")
            stats["skipped"] += 1
            continue
        _, created = ensure_user_role(db, user.id, role.id)
        if created:
            stats["created"] += 1
        else:
            stats["skipped"] += 1
    if verbose:
        print(f"  User Roles: {stats['created']} created, {stats['skipped']} skipped (already exist)")
    return stats


def import_cycles(db: Session, data_dir: Path, verbose: bool = False) -> Dict[str, Any]:
    """Import review cycles from assignments CSV. Returns stats and cycle mapping."""
    stats = {"created": 0, "updated": 0}
    assignments = load_csv(data_dir / "assignments.csv")
    cycles_data = {}

    # Group assignments by cycle_name to extract unique cycles
    for assign in assignments:
        cycle_name = assign["cycle_name"]
        if cycle_name not in cycles_data:
            # Try to get dates from assignment row, or use defaults
            start_date_str = assign.get("cycle_start_date", "").strip()
            end_date_str = assign.get("cycle_end_date", "").strip()
            start_date = None
            end_date = None
            if start_date_str:
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            if end_date_str:
                try:
                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            cycles_data[cycle_name] = {
                "name": cycle_name,
                "start_date": start_date,
                "end_date": end_date,
                "status": "DRAFT",  # Default to DRAFT, can be activated later
            }

    # Get first admin user as created_by
    admin_user = db.query(User).filter(User.is_admin == True).first()
    if not admin_user:
        raise ValidationError("No admin user found. Cannot create cycles without an admin user.")

    cycle_mapping = {}
    for cycle_data in cycles_data.values():
        cycle, created = get_or_create_cycle(
            db,
            name=cycle_data["name"],
            created_by_user_id=admin_user.id,
            start_date=cycle_data["start_date"],
            end_date=cycle_data["end_date"],
            status=cycle_data["status"],
        )
        cycle_mapping[cycle_data["name"]] = cycle
        if created:
            stats["created"] += 1
        else:
            stats["updated"] += 1

    if verbose:
        print(f"  Review Cycles: {stats['created']} created, {stats['updated']} updated")
    return {"stats": stats, "cycle_mapping": cycle_mapping}


def import_assignments(
    db: Session, data_dir: Path, cycle_mapping: Dict[str, ReviewCycle], verbose: bool = False
) -> Dict[str, int]:
    """Import review assignments from CSV. Returns stats."""
    stats = {"created": 0, "skipped": 0}
    assignments = load_csv(data_dir / "assignments.csv")

    for assign_data in assignments:
        cycle_name = assign_data["cycle_name"]
        cycle = cycle_mapping.get(cycle_name)
        if not cycle:
            if verbose:
                print(f"  Warning: Cycle '{cycle_name}' not found, skipping assignment")
            stats["skipped"] += 1
            continue

        reviewer_num = assign_data["reviewer_employee_number"].strip()
        subject_num = assign_data["subject_employee_number"].strip()
        approver_num = assign_data["approver_employee_number"].strip()
        status = assign_data.get("status", "ACTIVE").strip()

        reviewer_emp = get_employee_by_number(db, reviewer_num)
        subject_emp = get_employee_by_number(db, subject_num)
        approver_emp = get_employee_by_number(db, approver_num)

        if not reviewer_emp or not subject_emp or not approver_emp:
            if verbose:
                missing = []
                if not reviewer_emp:
                    missing.append(f"reviewer '{reviewer_num}'")
                if not subject_emp:
                    missing.append(f"subject '{subject_num}'")
                if not approver_emp:
                    missing.append(f"approver '{approver_num}'")
                print(f"  Warning: Missing employees ({', '.join(missing)}), skipping assignment")
            stats["skipped"] += 1
            continue

        try:
            _, created = get_or_create_assignment(
                db,
                cycle_id=cycle.id,
                reviewer_emp_id=reviewer_emp.id,
                subject_emp_id=subject_emp.id,
                approver_emp_id=approver_emp.id,
                status=status,
            )
            if created:
                stats["created"] += 1
            else:
                stats["skipped"] += 1
        except IntegrityError:
            stats["skipped"] += 1
            if verbose:
                print(f"  Warning: Duplicate assignment (cycle={cycle_name}, reviewer={reviewer_num}, subject={subject_num}), skipping")

    if verbose:
        print(f"  Assignments: {stats['created']} created, {stats['skipped']} skipped (already exist)")
    return stats


# ============================================================================
# Main Import Function
# ============================================================================

def run_import(data_dir: Path, dry_run: bool = False, verbose: bool = False) -> Dict[str, Any]:
    """Run the complete import process."""
    start_time = time.time()
    summary = {}

    print("Importing client data...")
    if dry_run:
        print("  [DRY RUN MODE - No changes will be made]")

    # Validate files
    print("  ✓ Validating files...", end="", flush=True)
    validate_files(data_dir)
    print(" OK")

    # Validate data
    print("  ✓ Validating data...", end="", flush=True)
    validate_data(data_dir, verbose=verbose)
    print(" OK")

    if dry_run:
        print("\n✓ Dry-run complete - validation passed. No data imported.")
        return {"dry_run": True, "validation_passed": True}

    # Start database session
    db = SessionLocal()
    try:
        # Import in dependency order
        print("\n  Importing roles...", end="", flush=True)
        summary["roles"] = import_roles(db, verbose=verbose)

        print("  Importing field definitions...", end="", flush=True)
        summary["field_definitions"] = import_field_definitions(db, data_dir, verbose=verbose)

        print("  Importing form templates...", end="", flush=True)
        summary["form_templates"] = import_form_templates(db, data_dir, verbose=verbose)

        print("  Importing users...", end="", flush=True)
        summary["users"] = import_users(db, data_dir, verbose=verbose)

        print("  Importing employees...", end="", flush=True)
        summary["employees"] = import_employees(db, data_dir, verbose=verbose)

        print("  Importing user roles...", end="", flush=True)
        summary["user_roles"] = import_user_roles(db, data_dir, verbose=verbose)

        print("  Importing review cycles...", end="", flush=True)
        cycles_result = import_cycles(db, data_dir, verbose=verbose)
        summary["cycles"] = cycles_result["stats"]
        cycle_mapping = cycles_result["cycle_mapping"]

        print("  Importing assignments...", end="", flush=True)
        summary["assignments"] = import_assignments(db, data_dir, cycle_mapping, verbose=verbose)

        elapsed = time.time() - start_time
        summary["elapsed_time"] = elapsed

        print(f"\n✓ Import complete! ({elapsed:.1f}s)")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Import failed: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        raise
    finally:
        db.close()

    return summary


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Import client data into Cycle Manager database")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "client_data",
        help="Directory containing client data files (default: client_data/)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate data without importing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    if not data_dir.exists():
        print(f"❌ Error: Data directory not found: {data_dir}")
        sys.exit(1)

    try:
        summary = run_import(data_dir, dry_run=args.dry_run, verbose=args.verbose)

        if not args.dry_run:
            print("\n=== Import Summary ===")
            print(f"Roles:           {summary['roles']['created']} created, {summary['roles'].get('updated', 0)} already exist")
            print(f"Field Definitions: {summary['field_definitions']['created']} created, {summary['field_definitions']['updated']} updated")
            print(f"Form Templates:    {summary['form_templates']['created']} created, {summary['form_templates']['updated']} updated")
            print(f"Users:            {summary['users']['created']} created, {summary['users']['updated']} updated")
            print(f"Employees:        {summary['employees']['created']} created, {summary['employees']['updated']} updated")
            print(f"User Roles:       {summary['user_roles']['created']} created, {summary['user_roles']['skipped']} skipped")
            print(f"Review Cycles:     {summary['cycles']['created']} created, {summary['cycles']['updated']} updated")
            print(f"Assignments:       {summary['assignments']['created']} created, {summary['assignments']['skipped']} skipped")
            print(f"\nTotal time: {summary['elapsed_time']:.1f}s")

    except ValidationError as e:
        print(f"\n❌ Validation Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

