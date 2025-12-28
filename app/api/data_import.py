"""
API endpoints for client data import.
"""

import csv
import json
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.rbac import require_roles
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.import_job import ImportJob
from app.services.import_service import ImportService

router = APIRouter(prefix="/admin/import", tags=["import"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def import_client_data(
    employees_file: UploadFile = File(None),
    users_file: UploadFile = File(None),
    roles_file: UploadFile = File(None),
    assignments_file: UploadFile = File(None),
    field_definitions_file: UploadFile = File(None),
    form_templates_file: UploadFile = File(None),
    cycle_name: str = Form(None),
    cycle_start_date: str = Form(None),
    cycle_end_date: str = Form(None),
    form_template_name: str = Form(None),
    form_template_version: int = Form(1),
    dry_run: bool = Form(False),
    mode: str = Form("upsert"),  # "insert" | "upsert" | "update"
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """
    Import client data from CSV and JSON files.

    Supports:
    - employees.csv: Employee roster
    - users.csv: User accounts
    - user_roles.csv: Role assignments
    - assignments.csv: Review assignments
    - field_definitions.json: Form field definitions
    - form_templates.json: Form template definitions
    """
    # Create import job
    import_job = ImportJob(
        created_by_user_id=current_user.id,
        status="PROCESSING",
        phase="validating",
        import_options={
            "dry_run": dry_run,
            "mode": mode,
            "cycle_name": cycle_name,
        },
        started_at=datetime.utcnow(),
    )
    db.add(import_job)
    db.commit()
    db.refresh(import_job)

    try:
        # Parse files
        files_data = {}

        if employees_file:
            content = employees_file.file.read().decode("utf-8")
            files_data["employees"] = ImportService._parse_csv(content)

        if users_file:
            content = users_file.file.read().decode("utf-8")
            files_data["users"] = ImportService._parse_csv(content)

        if roles_file:
            content = roles_file.file.read().decode("utf-8")
            files_data["roles"] = ImportService._parse_csv(content)

        if assignments_file:
            content = assignments_file.file.read().decode("utf-8")
            files_data["assignments"] = ImportService._parse_csv(content)

        if field_definitions_file:
            content = field_definitions_file.file.read().decode("utf-8")
            files_data["field_definitions"] = ImportService._parse_json(content)

        if form_templates_file:
            content = form_templates_file.file.read().decode("utf-8")
            files_data["form_templates"] = ImportService._parse_json(content)

        # Calculate total records
        total_records = sum(len(data) if isinstance(data, list) else 1 for data in files_data.values())
        import_job.total_records = total_records
        db.commit()

        # Initialize import service
        service = ImportService(db, import_job)

        # Phase 1: Field Definitions
        if "field_definitions" in files_data:
            field_defs = files_data["field_definitions"]
            if isinstance(field_defs, list):
                service.import_field_definitions(field_defs, dry_run=dry_run)
            elif isinstance(field_defs, dict):
                # Handle single field definition
                service.import_field_definitions([field_defs], dry_run=dry_run)

        # Phase 2: Form Templates
        if "form_templates" in files_data:
            form_templates = files_data["form_templates"]
            if isinstance(form_templates, list):
                service.import_form_templates(form_templates, dry_run=dry_run)
            elif isinstance(form_templates, dict):
                # Handle single form template
                service.import_form_templates([form_templates], dry_run=dry_run)

        # Phase 3: Users
        if "users" in files_data:
            service.import_users(files_data["users"], dry_run=dry_run)

        # Phase 4: Employees
        if "employees" in files_data and "users" in files_data:
            service.import_employees(files_data["employees"], files_data["users"], dry_run=dry_run)

        # Phase 5: Roles
        if "roles" in files_data:
            service.import_user_roles(files_data["roles"], dry_run=dry_run)

        # Phase 6: Review Cycle
        if cycle_name:
            start_date = None
            end_date = None
            if cycle_start_date:
                try:
                    start_date = datetime.fromisoformat(cycle_start_date.replace("Z", "+00:00")).date()
                except ValueError:
                    pass
            if cycle_end_date:
                try:
                    end_date = datetime.fromisoformat(cycle_end_date.replace("Z", "+00:00")).date()
                except ValueError:
                    pass

            service.import_cycle(
                cycle_name=cycle_name,
                start_date=start_date,
                end_date=end_date,
                form_template_name=form_template_name,
                form_template_version=form_template_version,
                created_by_user_id=current_user.id,
                dry_run=dry_run,
            )

        # Phase 7: Assignments
        if "assignments" in files_data and cycle_name:
            service.import_assignments(files_data["assignments"], cycle_name, dry_run=dry_run)

        # Finalize
        if dry_run:
            import_job.status = "COMPLETED"
            import_job.completed_at = datetime.utcnow()
        else:
            service.finalize()

        return {
            "import_id": str(import_job.id),
            "status": import_job.status,
            "phase": import_job.phase,
            "message": "Import completed successfully" if not dry_run else "Dry run completed",
            "summary": service.summary,
        }

    except Exception as e:
        import_job.status = "FAILED"
        import_job.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}",
        )


@router.get("/{import_id}")
def get_import_status(
    import_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Get import job status and progress."""
    import_job = db.get(ImportJob, import_id)
    if not import_job:
        raise HTTPException(status_code=404, detail="Import job not found")

    return {
        "import_id": str(import_job.id),
        "status": import_job.status,
        "phase": import_job.phase,
        "progress": import_job.progress,
        "total_records": import_job.total_records,
        "processed_records": import_job.processed_records,
        "errors": import_job.errors or [],
        "warnings": import_job.warnings or [],
        "started_at": import_job.started_at.isoformat() if import_job.started_at else None,
        "completed_at": import_job.completed_at.isoformat() if import_job.completed_at else None,
        "estimated_completion": None,  # Could calculate based on progress
    }


@router.get("/{import_id}/results")
def get_import_results(
    import_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """Get final import results and summary."""
    import_job = db.get(ImportJob, import_id)
    if not import_job:
        raise HTTPException(status_code=404, detail="Import job not found")

    duration = None
    if import_job.started_at and import_job.completed_at:
        duration = (import_job.completed_at - import_job.started_at).total_seconds()

    return {
        "import_id": str(import_job.id),
        "status": import_job.status,
        "summary": import_job.result_summary or {},
        "errors": import_job.errors or [],
        "warnings": import_job.warnings or [],
        "started_at": import_job.started_at.isoformat() if import_job.started_at else None,
        "completed_at": import_job.completed_at.isoformat() if import_job.completed_at else None,
        "duration_seconds": duration,
    }


@router.get("")
def list_import_jobs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("ADMIN")),
):
    """List all import jobs."""
    jobs = (
        db.query(ImportJob)
        .order_by(ImportJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total = db.query(ImportJob).count()

    return {
        "items": [
            {
                "import_id": str(job.id),
                "status": job.status,
                "phase": job.phase,
                "progress": job.progress,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in jobs
        ],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(jobs) < total,
        },
    }



