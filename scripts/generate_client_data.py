#!/usr/bin/env python3
"""
Generate realistic client datasets for 100 reviewable employees.

This simulates what a client would provide:
- Employee roster with organizational structure
- User accounts
- Role assignments
- Review assignments for a cycle
- Form field definitions
"""

import csv
import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
import random

# Set seed for reproducibility
random.seed(42)

# Departments and structure
DEPARTMENTS = [
    "Engineering",
    "Product",
    "Sales",
    "Marketing",
    "Customer Success",
    "Operations",
    "Finance",
    "HR",
    "Legal",
    "Executive"
]

# Generate realistic names
FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Jason", "Rebecca", "Edward", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia", "Jacob", "Kathleen", "Gary", "Amy",
    "Nicholas", "Angela", "Eric", "Shirley", "Jonathan", "Anna", "Stephen", "Brenda",
    "Larry", "Pamela", "Justin", "Emma", "Scott", "Nicole", "Brandon", "Helen",
    "Benjamin", "Samantha", "Samuel", "Katherine", "Frank", "Christine", "Gregory", "Debra",
    "Raymond", "Rachel", "Alexander", "Carolyn", "Patrick", "Janet", "Jack", "Virginia",
    "Dennis", "Maria", "Jerry", "Heather", "Tyler", "Diane", "Aaron", "Julie"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor",
    "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Sanchez",
    "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "King", "Wright",
    "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green", "Adams", "Nelson",
    "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts", "Gomez",
    "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz", "Edwards", "Collins",
    "Reyes", "Stewart", "Morris", "Morales", "Murphy", "Cook", "Rogers", "Gutierrez",
    "Ortiz", "Morgan", "Cooper", "Peterson", "Bailey", "Reed", "Kelly", "Howard",
    "Ramos", "Kim", "Cox", "Ward", "Richardson", "Watson", "Brooks", "Chavez",
    "Wood", "James", "Bennett", "Gray", "Mendoza", "Ruiz", "Hughes", "Price",
    "Alvarez", "Castillo", "Sanders", "Patel", "Myers", "Long", "Ross", "Foster"
]

def generate_employee_number(index: int) -> str:
    """Generate employee number like E001, E002, etc."""
    return f"E{index:04d}"

def generate_email(first_name: str, last_name: str, domain: str = "clientcorp.com") -> str:
    """Generate email address."""
    return f"{first_name.lower()}.{last_name.lower()}@{domain}"

def generate_employees(num_employees: int = 100) -> list[dict]:
    """Generate employee roster with organizational structure."""
    employees = []
    
    # Create executive team first (top of hierarchy)
    exec_count = 3
    exec_dept = "Executive"
    exec_employees = []
    
    for i in range(exec_count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        emp_num = generate_employee_number(i + 1)
        exec_employees.append({
            "employee_number": emp_num,
            "display_name": f"{first} {last}",
            "department": exec_dept,
            "manager_employee_number": None,  # Top level
            "start_date": (date.today() - timedelta(days=random.randint(365, 1825))).isoformat(),
            "status": "active"
        })
    
    employees.extend(exec_employees)
    
    # Distribute remaining employees across departments
    remaining = num_employees - exec_count
    employees_per_dept = remaining // (len(DEPARTMENTS) - 1)  # Exclude Executive
    
    dept_index = 0
    emp_index = exec_count + 1
    
    for dept in DEPARTMENTS:
        if dept == "Executive":
            continue
            
        # Assign a manager from executive or previous department
        if dept_index == 0:
            manager = random.choice(exec_employees)["employee_number"]
        else:
            # Manager from same department or previous
            potential_managers = [e for e in employees if e["department"] in [dept, DEPARTMENTS[dept_index - 1]]]
            if potential_managers:
                manager = random.choice(potential_managers)["employee_number"]
            else:
                manager = random.choice(exec_employees)["employee_number"]
        
        # Create department head
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        dept_head_num = generate_employee_number(emp_index)
        dept_head = {
            "employee_number": dept_head_num,
            "display_name": f"{first} {last}",
            "department": dept,
            "manager_employee_number": manager,
            "start_date": (date.today() - timedelta(days=random.randint(180, 1095))).isoformat(),
            "status": "active"
        }
        employees.append(dept_head)
        emp_index += 1
        
        # Create team members
        for j in range(employees_per_dept - 1):
            if emp_index > num_employees:
                break
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            emp_num = generate_employee_number(emp_index)
            employees.append({
                "employee_number": emp_num,
                "display_name": f"{first} {last}",
                "department": dept,
                "manager_employee_number": dept_head_num,  # Report to dept head
                "start_date": (date.today() - timedelta(days=random.randint(30, 730))).isoformat(),
                "status": "active"
            })
            emp_index += 1
        
        dept_index += 1
    
    # Fill remaining slots
    while len(employees) < num_employees:
        dept = random.choice([d for d in DEPARTMENTS if d != "Executive"])
        potential_managers = [e for e in employees if e["department"] == dept]
        manager = random.choice(potential_managers)["employee_number"] if potential_managers else None
        
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        emp_num = generate_employee_number(len(employees) + 1)
        employees.append({
            "employee_number": emp_num,
            "display_name": f"{first} {last}",
            "department": dept,
            "manager_employee_number": manager,
            "start_date": (date.today() - timedelta(days=random.randint(30, 730))).isoformat(),
            "status": "active"
        })
    
    return employees[:num_employees]

def generate_users(employees: list[dict]) -> list[dict]:
    """Generate user accounts for employees."""
    users = []
    admin_count = 3  # First 3 users are admins
    
    for i, emp in enumerate(employees):
        name_parts = emp["display_name"].split()
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
        email = generate_email(first_name, last_name)
        
        users.append({
            "email": email,
            "full_name": emp["display_name"],
            "employee_number": emp["employee_number"],
            "is_admin": i < admin_count,
            "is_active": True
        })
    
    return users

def generate_user_roles(users: list[dict], employees: list[dict]) -> list[dict]:
    """Generate role assignments."""
    roles = []
    
    for user in users:
        # All users get at least one role
        if user["is_admin"]:
            roles.append({
                "user_email": user["email"],
                "role_name": "ADMIN"
            })
        
        # Assign reviewer/approver roles based on hierarchy
        # Managers and above are approvers
        emp = next((e for e in employees if e["employee_number"] == user["employee_number"]), None)
        if emp:
            # If they have direct reports, they're approvers
            has_reports = any(e["manager_employee_number"] == emp["employee_number"] for e in employees)
            if has_reports:
                roles.append({
                    "user_email": user["email"],
                    "role_name": "APPROVER"
                })
            
            # Most employees are reviewers
            if random.random() > 0.2:  # 80% are reviewers
                roles.append({
                    "user_email": user["email"],
                    "role_name": "REVIEWER"
                })
    
    return roles

def generate_assignments(employees: list[dict], cycle_name: str = "Q4 2024 Performance Reviews") -> list[dict]:
    """Generate review assignments."""
    assignments = []
    
    # Filter to active employees
    active_employees = [e for e in employees if e["status"] == "active"]
    
    # Create assignments: each employee gets reviewed by their manager
    # Approver is manager's manager (or executive if no manager's manager)
    for emp in active_employees:
        if emp["manager_employee_number"]:
            reviewer = emp["manager_employee_number"]
            subject = emp["employee_number"]
            
            # Find approver (manager's manager)
            manager = next((e for e in employees if e["employee_number"] == reviewer), None)
            if manager and manager["manager_employee_number"]:
                approver = manager["manager_employee_number"]
            else:
                # Fallback to executive
                exec_emps = [e for e in employees if e["department"] == "Executive"]
                approver = random.choice(exec_emps)["employee_number"] if exec_emps else reviewer
            
            assignments.append({
                "cycle_name": cycle_name,
                "reviewer_employee_number": reviewer,
                "subject_employee_number": subject,
                "approver_employee_number": approver,
                "status": "ACTIVE"
            })
    
    return assignments

def generate_field_definitions() -> list[dict]:
    """Generate form field definitions."""
    return [
        {
            "key": "overall_rating",
            "label": "Overall Performance Rating",
            "field_type": "number",
            "required": True,
            "rules": {
                "min": 1,
                "max": 5,
                "integer": True
            }
        },
        {
            "key": "q1",
            "label": "Overall Comments",
            "field_type": "text",
            "required": False,
            "rules": {
                "max_length": 2000
            }
        },
        {
            "key": "technical_skills",
            "label": "Technical Skills Rating",
            "field_type": "number",
            "required": True,
            "rules": {
                "min": 1,
                "max": 5,
                "integer": True
            }
        },
        {
            "key": "communication",
            "label": "Communication Skills Rating",
            "field_type": "number",
            "required": True,
            "rules": {
                "min": 1,
                "max": 5,
                "integer": True
            }
        },
        {
            "key": "collaboration",
            "label": "Collaboration Rating",
            "field_type": "number",
            "required": False,
            "rules": {
                "min": 1,
                "max": 5,
                "integer": True
            }
        },
        {
            "key": "goals_achievement",
            "label": "Goals Achievement Comments",
            "field_type": "text",
            "required": False,
            "rules": {
                "max_length": 1000
            }
        },
        {
            "key": "development_areas",
            "label": "Development Areas",
            "field_type": "text",
            "required": False,
            "rules": {
                "max_length": 1500
            }
        }
    ]

def generate_form_templates() -> list[dict]:
    """Generate form template definitions."""
    return [
        {
            "name": "Standard Performance Review Form",
            "version": 1,
            "description": "Standard performance review form for annual reviews",
            "is_active": True,
            "fields": [
                {"field_key": "overall_rating", "position": 1, "override_label": None, "override_required": None},
                {"field_key": "q1", "position": 2, "override_label": None, "override_required": None},
                {"field_key": "technical_skills", "position": 3, "override_label": None, "override_required": None},
                {"field_key": "communication", "position": 4, "override_label": None, "override_required": None},
                {"field_key": "collaboration", "position": 5, "override_label": None, "override_required": None},
                {"field_key": "goals_achievement", "position": 6, "override_label": None, "override_required": None},
                {"field_key": "development_areas", "position": 7, "override_label": None, "override_required": None}
            ]
        }
    ]

def write_csv(filename: str, data: list[dict], fieldnames: list[str]):
    """Write data to CSV file."""
    output_dir = Path("client_data")
    output_dir.mkdir(exist_ok=True)
    
    filepath = output_dir / filename
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    
    print(f"✅ Generated {filepath} ({len(data)} rows)")

def write_json(filename: str, data: list[dict] | dict):
    """Write data to JSON file."""
    output_dir = Path("client_data")
    output_dir.mkdir(exist_ok=True)
    
    filepath = output_dir / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    count = len(data) if isinstance(data, list) else 1
    print(f"✅ Generated {filepath} ({count} items)")

def main():
    print("=" * 60)
    print("Generating Client Datasets for 100 Employees")
    print("=" * 60)
    print()
    
    # Generate data
    print("📊 Generating employees...")
    employees = generate_employees(100)
    
    print("👤 Generating users...")
    users = generate_users(employees)
    
    print("🔐 Generating role assignments...")
    roles = generate_user_roles(users, employees)
    
    print("📋 Generating review assignments...")
    assignments = generate_assignments(employees)
    
    print("📝 Generating field definitions...")
    field_definitions = generate_field_definitions()
    
    print("📄 Generating form templates...")
    form_templates = generate_form_templates()
    
    print()
    print("💾 Writing files...")
    print()
    
    # Write CSV files
    write_csv("employees.csv", employees, [
        "employee_number", "display_name", "department", 
        "manager_employee_number", "start_date", "status"
    ])
    
    write_csv("users.csv", users, [
        "email", "full_name", "employee_number", "is_admin", "is_active"
    ])
    
    write_csv("user_roles.csv", roles, [
        "user_email", "role_name"
    ])
    
    write_csv("assignments.csv", assignments, [
        "cycle_name", "reviewer_employee_number", "subject_employee_number",
        "approver_employee_number", "status"
    ])
    
    # Write JSON files
    write_json("field_definitions.json", field_definitions)
    write_json("form_templates.json", form_templates)
    
    # Generate summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Employees: {len(employees)}")
    print(f"Users: {len(users)}")
    print(f"Admins: {sum(1 for u in users if u['is_admin'])}")
    print(f"Role assignments: {len(roles)}")
    print(f"Review assignments: {len(assignments)}")
    print(f"Field definitions: {len(field_definitions)}")
    print(f"Form templates: {len(form_templates)}")
    print()
    print(f"📁 All files written to: client_data/")
    print()

if __name__ == "__main__":
    main()



