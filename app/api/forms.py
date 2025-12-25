from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.rbac import require_roles
from app.db.session import get_db
from app.models.field_definition import FieldDefinition
from app.models.form_template import FormTemplate
from app.models.form_template_field import FormTemplateField
from app.schemas.forms import (
    FieldDefinitionCreate,
    FieldDefinitionOut,
    FormTemplateCreate,
    FormTemplateOut,
    FormTemplateFieldAttach,
    FormTemplateWithFieldsOut,
)
from app.core.audit import log_event
from app.models.user import User

router = APIRouter(prefix="/forms", tags=["forms"])


def _field_out(f: FieldDefinition) -> FieldDefinitionOut:
    return FieldDefinitionOut(
        id=str(f.id),
        key=f.key,
        label=f.label,
        field_type=f.field_type,
        required=f.required,
        rules=f.rules,
        created_at=f.created_at,
        updated_at=f.updated_at,
    )


def _form_out(form: FormTemplate) -> FormTemplateOut:
    return FormTemplateOut(
        id=str(form.id),
        name=form.name,
        version=form.version,
        description=form.description,
        is_active=form.is_active,
        created_at=form.created_at,
        updated_at=form.updated_at,
    )


@router.post("/fields", response_model=FieldDefinitionOut, status_code=status.HTTP_201_CREATED)
def create_field_definition(
    payload: FieldDefinitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    f = FieldDefinition(
        key=payload.key,
        label=payload.label,
        field_type=payload.field_type,
        required=payload.required,
        rules=payload.rules,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(f)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Field key already exists")

    log_event(
        db=db,
        actor=current_user,
        action="FIELD_DEFINITION_CREATED",
        entity_type="field_definition",
        entity_id=f.id,
        metadata={"key": f.key, "field_type": f.field_type, "required": f.required},
    )

    db.commit()
    db.refresh(f)
    return _field_out(f)


@router.get("/fields", response_model=list[FieldDefinitionOut])
def list_field_definitions(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
):
    rows = db.query(FieldDefinition).order_by(FieldDefinition.created_at.desc()).all()
    return [_field_out(r) for r in rows]


@router.post("", response_model=FormTemplateOut, status_code=status.HTTP_201_CREATED)
def create_form_template(
    payload: FormTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    form = FormTemplate(
        name=payload.name,
        version=payload.version,
        description=payload.description,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(form)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Form name+version already exists")

    log_event(
        db=db,
        actor=current_user,
        action="FORM_TEMPLATE_CREATED",
        entity_type="form_template",
        entity_id=form.id,
        metadata={"name": form.name, "version": form.version},
    )

    db.commit()
    db.refresh(form)
    return _form_out(form)


@router.post("/{form_id}/fields", response_model=FormTemplateWithFieldsOut, status_code=200)
def attach_fields_to_form(
    form_id: str,
    payload: list[FormTemplateFieldAttach],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    form = db.get(FormTemplate, form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    # add/update rows
    for item in payload:
        fdef = db.get(FieldDefinition, item.field_definition_id)
        if not fdef:
            raise HTTPException(status_code=400, detail={"missing_field_definition_id": item.field_definition_id})

        existing = (
            db.query(FormTemplateField)
            .filter(
                FormTemplateField.form_template_id == form.id,
                FormTemplateField.field_definition_id == fdef.id,
            )
            .one_or_none()
        )
        if existing:
            existing.position = item.position
            existing.override_label = item.override_label
            existing.override_required = item.override_required
        else:
            db.add(
                FormTemplateField(
                    form_template_id=form.id,
                    field_definition_id=fdef.id,
                    position=item.position,
                    override_label=item.override_label,
                    override_required=item.override_required,
                )
            )

    form.updated_at = datetime.utcnow()
    db.flush()

    log_event(
        db=db,
        actor=current_user,
        action="FORM_TEMPLATE_FIELDS_UPDATED",
        entity_type="form_template",
        entity_id=form.id,
        metadata={"field_count": len(payload)},
    )

    db.commit()
    db.refresh(form)

    # output
    rows = (
        db.query(FormTemplateField)
        .filter(FormTemplateField.form_template_id == form.id)
        .order_by(FormTemplateField.position.asc())
        .all()
    )

    fields_out = []
    for r in rows:
        f = r.field
        fields_out.append(
            {
                "position": r.position,
                "field_definition_id": str(f.id),
                "key": f.key,
                "label": r.override_label or f.label,
                "field_type": f.field_type,
                "required": (r.override_required if r.override_required is not None else f.required),
                "rules": f.rules,
            }
        )

    return FormTemplateWithFieldsOut(
        id=str(form.id),
        name=form.name,
        version=form.version,
        description=form.description,
        is_active=form.is_active,
        fields=fields_out,
    )


@router.get("/{form_id}", response_model=FormTemplateWithFieldsOut)
def get_form_template(
    form_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
):
    form = db.get(FormTemplate, form_id)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    rows = (
        db.query(FormTemplateField)
        .filter(FormTemplateField.form_template_id == form.id)
        .order_by(FormTemplateField.position.asc())
        .all()
    )

    fields_out = []
    for r in rows:
        f = r.field
        fields_out.append(
            {
                "position": r.position,
                "field_definition_id": str(f.id),
                "key": f.key,
                "label": r.override_label or f.label,
                "field_type": f.field_type,
                "required": (r.override_required if r.override_required is not None else f.required),
                "rules": f.rules,
            }
        )

    return FormTemplateWithFieldsOut(
        id=str(form.id),
        name=form.name,
        version=form.version,
        description=form.description,
        is_active=form.is_active,
        fields=fields_out,
    )
