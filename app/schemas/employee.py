from pydantic import BaseModel


class EmployeeOut(BaseModel):
    id: str
    employee_number: str
    display_name: str
    user_id: str | None

    class Config:
        from_attributes = True


class EmployeeWithUserOut(EmployeeOut):
    user_email: str | None = None
    user_full_name: str | None = None

