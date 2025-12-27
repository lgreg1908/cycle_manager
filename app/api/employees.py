from typing import Union
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.employee import Employee
from app.models.user import User
from app.schemas.employee import EmployeeOut, EmployeeWithUserOut
from app.schemas.pagination import PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/employees", tags=["employees"])


def employee_to_out(e: Employee, include_user: bool = False) -> EmployeeOut | EmployeeWithUserOut:
    if include_user and e.user:
        return EmployeeWithUserOut(
            id=str(e.id),
            employee_number=e.employee_number,
            display_name=e.display_name,
            user_id=str(e.user_id) if e.user_id else None,
            user_email=e.user.email,
            user_full_name=e.user.full_name,
        )
    return EmployeeOut(
        id=str(e.id),
        employee_number=e.employee_number,
        display_name=e.display_name,
        user_id=str(e.user_id) if e.user_id else None,
    )


@router.get("")
def list_employees(
    search: str | None = Query(default=None, description="Search by employee number or display name"),
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    include_pagination: bool = Query(default=False, description="Include pagination metadata"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    List all employees with optional search and pagination.
    
    Use ?include_pagination=true to get pagination metadata.
    """
    query = db.query(Employee)

    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            (Employee.employee_number.ilike(search_term))
            | (Employee.display_name.ilike(search_term))
        )

    # Get total count before pagination
    total = query.count()
    
    # Apply pagination
    employees = query.order_by(Employee.display_name.asc()).offset(offset).limit(limit).all()
    items = [employee_to_out(e) for e in employees]
    
    if include_pagination:
        return PaginatedResponse(
            items=items,
            pagination=PaginationMeta(
                total=total,
                limit=limit,
                offset=offset,
                has_more=(offset + len(items) < total),
            ),
        )
    return items


@router.get("/{employee_id}", response_model=EmployeeWithUserOut)
def get_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Get employee details by ID, including user information if linked.
    """
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee_to_out(employee, include_user=True)


@router.get("/search/quick", response_model=list[EmployeeOut])
def quick_search_employees(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Quick search endpoint for autocomplete/typeahead functionality.
    Returns top matches ordered by relevance (exact matches first).
    """
    search_term = f"%{q.lower()}%"
    
    # Try exact matches first
    exact_matches = (
        db.query(Employee)
        .filter(
            (Employee.employee_number.ilike(q))
            | (Employee.display_name.ilike(q))
        )
        .limit(limit)
        .all()
    )
    
    if len(exact_matches) >= limit:
        return [employee_to_out(e) for e in exact_matches]
    
    # Then partial matches
    partial_matches = (
        db.query(Employee)
        .filter(
            (Employee.employee_number.ilike(search_term))
            | (Employee.display_name.ilike(search_term))
        )
        .filter(~Employee.id.in_([e.id for e in exact_matches]))
        .limit(limit - len(exact_matches))
        .all()
    )
    
    return [employee_to_out(e) for e in exact_matches + partial_matches]


