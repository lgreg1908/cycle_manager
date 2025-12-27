from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.models.form_template import FormTemplate
from app.models.form_template_field import FormTemplateField
from app.models.field_definition import FieldDefinition


def _load_form_for_cycle_or_409(db: Session, cycle) -> FormTemplate:
    if not getattr(cycle, "form_template_id", None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cycle has no form template assigned",
        )

    form = db.get(FormTemplate, cycle.form_template_id)
    if not form or not form.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Form template not found or inactive",
        )
    return form


def _load_form_fields_map(db: Session, form: FormTemplate) -> dict[str, dict]:
    """
    Returns map keyed by field key (question_key):
      {
        "overall_rating": {"type": "...", "required": bool, "rules": {...}}
      }
    """
    rows = (
        db.query(FormTemplateField)
        .filter(FormTemplateField.form_template_id == form.id)
        .all()
    )

    out: dict[str, dict] = {}
    for r in rows:
        f: FieldDefinition = r.field
        key = f.key
        required = r.override_required if r.override_required is not None else f.required
        rules = f.rules or {}
        ftype = f.field_type

        out[key] = {
            "key": key,
            "type": ftype,
            "required": bool(required),
            "rules": rules,
        }
    return out


def _type_sanity(ftype: str, value_text: str) -> None:
    """
    Draft-level: validate "this could be valid" for the declared type.
    """
    if value_text is None:
        return

    s = value_text.strip()

    if ftype == "text":
        return

    if ftype == "number":
        # allow ints or floats; rules will constrain on submit
        try:
            float(s)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Type validation failed", "field_type": "number"})

    elif ftype == "select":
        # draft: any string is fine
        return

    elif ftype == "employee_reference":
        try:
            UUID(s)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Type validation failed", "field_type": "employee_reference"})

    elif ftype == "date":
        try:
            date.fromisoformat(s)
        except ValueError:
            raise HTTPException(status_code=400, detail={"message": "Type validation failed", "field_type": "date"})

    else:
        raise HTTPException(status_code=400, detail={"message": f"Unknown field type: {ftype}"})


def _full_validate_one(db: Session, spec: dict, value_text: str | None) -> list[dict]:
    """
    Submit-level: required + rules + references.
    Returns list of error dicts (empty if ok).
    """
    errors: list[dict] = []
    key = spec["key"]
    ftype = spec["type"]
    rules = spec.get("rules") or {}
    required = bool(spec.get("required"))

    if value_text is None or value_text.strip() == "":
        if required:
            errors.append({"field": key, "code": "required", "message": "Required"})
        return errors

    s = value_text.strip()

    # type + rule checks
    if ftype == "text":
        max_len = rules.get("max_length")
        if isinstance(max_len, int) and len(s) > max_len:
            errors.append({"field": key, "code": "max_length", "message": f"Must be <= {max_len} chars"})

    elif ftype == "number":
        try:
            x = float(s)
        except ValueError:
            errors.append({"field": key, "code": "type", "message": "Must be a number"})
            return errors

        if rules.get("integer") is True and not float(x).is_integer():
            errors.append({"field": key, "code": "integer", "message": "Must be an integer"})

        mn = rules.get("min")
        mx = rules.get("max")
        if mn is not None and x < mn:
            errors.append({"field": key, "code": "min", "message": f"Must be >= {mn}"})
        if mx is not None and x > mx:
            errors.append({"field": key, "code": "max", "message": f"Must be <= {mx}"})

    elif ftype == "select":
        choices = rules.get("choices")
        if isinstance(choices, list) and choices and s not in choices:
            errors.append({"field": key, "code": "choice", "message": "Must be one of allowed choices"})

    elif ftype == "employee_reference":
        try:
            emp_id = UUID(s)
        except ValueError:
            errors.append({"field": key, "code": "type", "message": "Must be a UUID"})
            return errors

        exists = db.query(Employee.id).filter(Employee.id == emp_id).one_or_none()
        if not exists:
            errors.append({"field": key, "code": "not_found", "message": "Employee not found"})

    elif ftype == "date":
        try:
            date.fromisoformat(s)
        except ValueError:
            errors.append({"field": key, "code": "type", "message": "Must be ISO date YYYY-MM-DD"})

    else:
        errors.append({"field": key, "code": "unknown_type", "message": f"Unknown type: {ftype}"})

    return errors


def validate_draft_payload(
    *,
    db: Session,
    cycle,
    responses: list[dict],  # [{"question_key": "...", "value_text": "..."}]
) -> None:
    """
    draft: validate keys exist + type sanity only
    """
    form = _load_form_for_cycle_or_409(db, cycle)
    spec_map = _load_form_fields_map(db, form)

    errors: list[dict] = []
    for r in responses:
        key = r["question_key"]
        if key not in spec_map:
            errors.append({"field": key, "code": "unknown_key", "message": "Not in form"})
            continue

        try:
            _type_sanity(spec_map[key]["type"], r.get("value_text") or "")
        except HTTPException as e:
            # normalize into our errors list
            errors.append({"field": key, "code": "type", "message": "Type validation failed"})

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Draft validation failed", "errors": errors},
        )


def validate_submit_from_db(
    *,
    db: Session,
    cycle,
    stored_responses: dict[str, str | None],  # {question_key: value_text}
) -> None:
    """
    submit: full required + rules + references
    """
    form = _load_form_for_cycle_or_409(db, cycle)
    spec_map = _load_form_fields_map(db, form)

    errors: list[dict] = []

    # unknown keys saved in DB
    for key in stored_responses.keys():
        if key not in spec_map:
            errors.append({"field": key, "code": "unknown_key", "message": "Not in form"})

    # required + rule checks for all keys in form
    for key, spec in spec_map.items():
        value = stored_responses.get(key)
        errors.extend(_full_validate_one(db, spec, value))

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Submit validation failed", "errors": errors},
        )
