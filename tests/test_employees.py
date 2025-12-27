from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import create_user, create_employee


def test_list_employees_requires_auth(db_session):
    """Test that listing employees requires authentication"""
    client = TestClient(app)
    r = client.get("/employees")
    assert r.status_code == 401


def test_list_employees_empty(db_session):
    """Test listing employees when none exist"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.get("/employees", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_employees_basic(db_session):
    """Test listing employees returns all employees"""
    user = create_user(db_session, "user@test.com")
    emp1 = create_employee(db_session, "E100", "Alice Smith")
    emp2 = create_employee(db_session, "E200", "Bob Jones")
    emp3 = create_employee(db_session, "E300", "Charlie Brown")

    client = TestClient(app)
    r = client.get("/employees", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 3
    # Should be ordered by display_name
    assert employees[0]["display_name"] == "Alice Smith"
    assert employees[1]["display_name"] == "Bob Jones"
    assert employees[2]["display_name"] == "Charlie Brown"


def test_list_employees_with_search(db_session):
    """Test searching employees by name or number"""
    user = create_user(db_session, "user@test.com")
    create_employee(db_session, "E100", "Alice Smith")
    create_employee(db_session, "E200", "Bob Jones")
    create_employee(db_session, "E300", "Alice Wonder")

    client = TestClient(app)
    # Search by name
    r = client.get("/employees?search=Alice", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 2
    assert all("Alice" in emp["display_name"] for emp in employees)

    # Search by employee number
    r = client.get("/employees?search=E200", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 1
    assert employees[0]["employee_number"] == "E200"


def test_list_employees_pagination(db_session):
    """Test pagination for employee list"""
    user = create_user(db_session, "user@test.com")
    # Create 5 employees
    for i in range(5):
        create_employee(db_session, f"E{i+1:03d}", f"Employee {i+1}")

    client = TestClient(app)
    # First page
    r = client.get("/employees?limit=2&offset=0", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 2

    # Second page
    r = client.get("/employees?limit=2&offset=2", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 2

    # Last page
    r = client.get("/employees?limit=2&offset=4", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 1


def test_get_employee_by_id(db_session):
    """Test getting a single employee by ID"""
    user = create_user(db_session, "user@test.com")
    emp = create_employee(db_session, "E100", "Alice Smith", user=user)

    client = TestClient(app)
    r = client.get(f"/employees/{emp.id}", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employee = r.json()
    assert employee["id"] == str(emp.id)
    assert employee["employee_number"] == "E100"
    assert employee["display_name"] == "Alice Smith"
    assert employee["user_id"] == str(user.id)
    assert employee["user_email"] == "user@test.com"
    assert employee["user_full_name"] == "User"


def test_get_employee_by_id_not_found(db_session):
    """Test getting non-existent employee returns 404"""
    user = create_user(db_session, "user@test.com")
    import uuid
    fake_id = str(uuid.uuid4())

    client = TestClient(app)
    r = client.get(f"/employees/{fake_id}", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 404


def test_get_employee_without_user(db_session):
    """Test getting employee without linked user"""
    user = create_user(db_session, "user@test.com")
    emp = create_employee(db_session, "E100", "Alice Smith", user=None)

    client = TestClient(app)
    r = client.get(f"/employees/{emp.id}", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employee = r.json()
    assert employee["user_id"] is None
    assert employee["user_email"] is None
    assert employee["user_full_name"] is None


def test_quick_search_employees(db_session):
    """Test quick search endpoint for autocomplete"""
    user = create_user(db_session, "user@test.com")
    create_employee(db_session, "E100", "Alice Smith")
    create_employee(db_session, "E200", "Bob Jones")
    create_employee(db_session, "E300", "Alice Wonder")

    client = TestClient(app)
    # Search should return exact matches first
    r = client.get("/employees/search/quick?q=Alice", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 2
    assert all("Alice" in emp["display_name"] for emp in employees)


def test_quick_search_employees_by_number(db_session):
    """Test quick search by employee number"""
    user = create_user(db_session, "user@test.com")
    emp = create_employee(db_session, "E100", "Alice Smith")
    create_employee(db_session, "E200", "Bob Jones")

    client = TestClient(app)
    r = client.get("/employees/search/quick?q=E100", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 1
    assert employees[0]["employee_number"] == "E100"


def test_quick_search_employees_limit(db_session):
    """Test quick search respects limit parameter"""
    user = create_user(db_session, "user@test.com")
    # Create many employees
    for i in range(10):
        create_employee(db_session, f"E{i+1:03d}", f"Employee {i+1}")

    client = TestClient(app)
    r = client.get("/employees/search/quick?q=Employee&limit=5", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 200
    employees = r.json()
    assert len(employees) == 5


def test_quick_search_employees_requires_query(db_session):
    """Test quick search requires query parameter"""
    user = create_user(db_session, "user@test.com")
    client = TestClient(app)
    r = client.get("/employees/search/quick", headers={"X-User-Email": "user@test.com"})
    assert r.status_code == 422  # Validation error for missing required parameter

