# Test Suite Documentation

## Overview

This test suite provides comprehensive coverage of the Cycle Manager API, replacing the need for Postman collection testing. All Postman workflows are now covered by automated unit and integration tests.

## Test Organization

The test suite is organized into domain-specific files for unit tests and a dedicated file for comprehensive workflow integration tests.

### Domain-Specific Test Files

#### `test_health.py`
Tests for basic health and root endpoints:
- `test_health_ok()` - Health check endpoint
- `test_root_endpoint()` - Root API endpoint

#### `test_me.py`
Tests for user-specific endpoints (`/me/*`):
- Current user information
- User assignments (with role filtering)
- User evaluations (with role and status filtering)
- User statistics

#### `test_cycles.py`
Tests for review cycle management:
- Cycle creation and lifecycle (DRAFT → ACTIVE → CLOSED)
- Cycle updates (only allowed in DRAFT status)
- Cycle readiness checks
- Cycle statistics
- Form template assignment
- Cycle activation and closing
- Error scenarios (activate without form, update active cycle)

#### `test_forms.py`
Tests for form templates and field definitions:
- Field definition creation and listing
- Form template creation and listing
- Attaching fields to forms
- Form retrieval with fields
- Duplicate key validation

#### `test_assignments.py`
Tests for review assignment management:
- Bulk assignment creation
- Assignment listing
- RBAC enforcement (admin-only)
- Error scenarios (create in ACTIVE cycle)
- Duplicate assignment prevention

#### `test_evaluations.py`
Tests for evaluation workflows:
- Evaluation creation and retrieval
- Draft saving with optimistic locking
- Evaluation validation
- Evaluation submission
- Evaluation approval and return
- Access control (reviewer/approver only)
- Idempotency handling
- Error scenarios (submit invalid, missing If-Match header)

#### `test_employees.py`
Tests for employee management:
- Employee listing and pagination
- Employee search (by name or number)
- Quick search for autocomplete
- Bulk employee lookup
- Get employee by ID
- Employee-user relationship handling

#### `test_audit.py`
Tests for audit and admin functionality:
- Admin ping endpoint
- Audit event listing
- Audit event filtering by entity type/ID
- RBAC enforcement (admin-only)

#### `test_rbac.py`
Tests for role-based access control:
- Role enforcement on various endpoints
- Admin-only operations
- User role assignments

#### `test_pagination_and_expand.py`
Tests for pagination and field expansion features:
- Pagination metadata
- Field expansion (e.g., employee names in assignments)

### Workflow Integration Tests

#### `test_postman_workflows.py`
Comprehensive end-to-end workflow tests that cover complete user journeys:

**`TestCompleteAdminWorkflow`**
- Complete cycle setup from scratch
- Create field definitions
- Create form template
- Attach fields to form
- Assign form to cycle
- Create assignments
- Check cycle readiness
- Activate cycle

**`TestCompleteReviewerWorkflow`**
- Get reviewer assignments
- Create or get evaluation (with idempotency)
- Save draft with responses
- Validate draft
- Submit evaluation

**`TestCompleteApproverWorkflow`**
- Get approver assignments
- List pending evaluations
- Get evaluation for review
- Approve evaluation
- Return evaluation (alternative workflow)

**`TestCompleteEndToEndWorkflow`**
- Full workflow from setup to close:
  1. Health check
  2. Admin setup (cycle, form, assignments)
  3. Cycle activation
  4. Reviewer workflow (create, draft, submit)
  5. Approver workflow (approve)
  6. Statistics retrieval
  7. Cycle closure

## Test Configuration

### Environment Setup

Tests automatically use `.env.test` configuration:
- Database: `hr_platform_test` on port `5433`
- Automatically configured in `conftest.py`
- No manual `ENV_FILE` setting required

### Test Database

- Each test runs in a transaction that is rolled back
- Database schema is created/dropped per test session
- Tests are isolated and can run in any order

### Fixtures

**`client`** - FastAPI TestClient instance
**`db_session`** - SQLAlchemy session for test data setup
**`db_connection`** - Database connection (one per test)

## Running Tests

### Run All Tests
```bash
pytest
```

### Run Specific Test File
```bash
pytest tests/test_cycles.py
```

### Run Specific Test Class
```bash
pytest tests/test_postman_workflows.py::TestCompleteAdminWorkflow
```

### Run Specific Test
```bash
pytest tests/test_cycles.py::test_cycle_lifecycle
```

### Run with Verbose Output
```bash
pytest -v
```

### Run with Coverage
```bash
pytest --cov=app --cov-report=html
```

### Run Only Workflow Tests
```bash
pytest tests/test_postman_workflows.py -v
```

## Test Coverage

### API Endpoints Covered

✅ **Health & Root**
- `GET /health`
- `GET /`

✅ **User Endpoints**
- `GET /me`
- `GET /me/assignments`
- `GET /me/evaluations`
- `GET /me/stats`

✅ **Cycle Management**
- `POST /cycles` - Create cycle
- `GET /cycles` - List cycles
- `GET /cycles/{id}` - Get cycle details
- `PATCH /cycles/{id}` - Update cycle
- `POST /cycles/{id}/activate` - Activate cycle
- `POST /cycles/{id}/close` - Close cycle
- `GET /cycles/{id}/readiness` - Check readiness
- `GET /cycles/{id}/stats` - Get statistics
- `POST /cycles/{id}/set-form/{form_id}` - Assign form

✅ **Form Management**
- `POST /forms/fields` - Create field definition
- `GET /forms/fields` - List field definitions
- `POST /forms` - Create form template
- `GET /forms` - List form templates
- `GET /forms/{id}` - Get form with fields
- `POST /forms/{id}/fields` - Attach fields to form

✅ **Assignment Management**
- `POST /cycles/{id}/assignments/bulk` - Bulk create assignments
- `GET /cycles/{id}/assignments` - List assignments

✅ **Evaluation Management**
- `POST /cycles/{id}/assignments/{id}/evaluation` - Create/get evaluation
- `GET /cycles/{id}/evaluations/{id}` - Get evaluation
- `GET /cycles/{id}/evaluations` - List evaluations
- `POST /cycles/{id}/evaluations/{id}/draft` - Save draft
- `POST /cycles/{id}/evaluations/{id}/validate` - Validate draft
- `POST /cycles/{id}/evaluations/{id}/submit` - Submit evaluation
- `POST /cycles/{id}/evaluations/{id}/approve` - Approve evaluation
- `POST /cycles/{id}/evaluations/{id}/return` - Return evaluation

✅ **Employee Management**
- `GET /employees` - List employees
- `GET /employees/{id}` - Get employee by ID
- `GET /employees/search/quick` - Quick search
- `POST /employees/bulk-lookup` - Bulk lookup

✅ **Audit & Admin**
- `GET /admin/ping` - Admin ping
- `GET /audit` - List audit events

### Workflow Coverage

✅ **Complete Admin Workflow**
- Cycle creation → Field definitions → Form creation → Form assignment → Assignment creation → Activation

✅ **Complete Reviewer Workflow**
- Get assignments → Create evaluation → Save draft → Validate → Submit

✅ **Complete Approver Workflow**
- Get assignments → List evaluations → Get evaluation → Approve/Return

✅ **Complete End-to-End Workflow**
- Setup → Review → Approve → Close

### Error Scenario Coverage

✅ **Cycle Errors**
- Activate cycle without form
- Update ACTIVE cycle
- Create assignment in ACTIVE cycle

✅ **Evaluation Errors**
- Submit invalid evaluation (missing required fields)
- Save draft without If-Match header
- Access evaluation without proper role

✅ **Validation Errors**
- Invalid UUID formats
- Missing required fields
- Duplicate key violations

## Test Helpers

Located in `tests/helpers.py`:

- `create_user()` - Create a user
- `grant_role()` - Grant role to user
- `create_employee()` - Create an employee
- `create_cycle()` - Create a review cycle
- `create_assignment()` - Create a review assignment
- `create_field_definition()` - Create a field definition
- `create_form_template()` - Create a form template
- `attach_field_to_form()` - Attach field to form
- `set_cycle_form_template()` - Assign form to cycle
- `create_form_for_cycle_with_fields()` - Complete form setup helper

## Best Practices

### Writing New Tests

1. **Use domain-specific files** for unit tests
2. **Use `test_postman_workflows.py`** only for comprehensive workflow tests
3. **Use test helpers** from `tests/helpers.py` for data setup
4. **Test error scenarios** in domain-specific files
5. **Keep tests independent** - no test should depend on another

### Test Naming

- Unit tests: `test_<functionality>_<scenario>`
- Workflow tests: `test_<workflow_name>_workflow`
- Error tests: `test_<action>_<error_condition>_fails`

### Test Structure

```python
def test_feature_scenario(db_session, client: TestClient):
    """Test description"""
    # 1. Setup test data
    # 2. Make API call
    # 3. Assert response
    # 4. Assert side effects
```

## Replacing Postman Collection

This test suite **completely replaces** the Postman collection for testing:

- ✅ All Postman workflows are covered
- ✅ All error scenarios are tested
- ✅ All edge cases are handled
- ✅ Tests run automatically in CI/CD
- ✅ Tests are version controlled
- ✅ Tests are easier to maintain

### Migration from Postman

If you were using the Postman collection:
1. **Run the test suite** instead: `pytest tests/test_postman_workflows.py -v`
2. **Individual endpoint tests** are in domain-specific files
3. **No manual variable management** - tests handle state automatically
4. **No manual setup** - fixtures handle database state

## Continuous Integration

The test suite is designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pytest --cov=app --cov-report=xml
```

## Troubleshooting

### Tests Fail with Database Errors

- Ensure test database is running on port 5433
- Check `.env.test` configuration
- Verify database connection string

### Tests Fail with Import Errors

- Ensure virtual environment is activated
- Install dependencies: `pip install -r requirements.txt`
- Check Python path includes project root

### Tests Are Slow

- Tests use transactions that rollback (fast)
- If slow, check for database connection issues
- Consider running tests in parallel: `pytest -n auto`

## Test Statistics

- **Total Test Files**: 12
- **Workflow Test Classes**: 4
- **Domain Test Files**: 8
- **Coverage**: All API endpoints and workflows

## Future Enhancements

Potential additions to the test suite:
- Performance/load tests
- Contract tests (API schema validation)
- Integration tests with external services
- End-to-end browser tests (if UI is added)

