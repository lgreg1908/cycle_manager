# Postman Collection - Cycle Manager API

## Overview

This Postman collection provides comprehensive end-to-end workflows for testing the Cycle Manager application. It covers all major user roles and scenarios.

## Setup Instructions

1. **Import the Collection**
   - Open Postman
   - Click "Import" → Select `postman_collection.json`
   - The collection will be imported with all workflows

2. **Configure Variables**
   - Open the collection settings (click on collection name → Variables tab)
   - Update these variables:
     - `base_url`: Your API base URL (default: `http://localhost:8000`)
     - `admin_email`: Admin user email (default: `admin@local.test`)
     - `reviewer_email`: Reviewer user email (default: `reviewer@local.test`)
     - `approver_email`: Approver user email (default: `approver@local.test`)

3. **Prerequisites**
   - Ensure your API server is running
   - Ensure test users exist in the database with appropriate roles
   - Ensure employees exist in the database

## Workflow Structure

### 1. Setup & Health
- Health check endpoint
- Root endpoint
- Get current user info

### 2. Admin Workflow - Cycle Setup
Complete cycle setup process:
1. Create review cycle
2. Get cycle details
3. Check cycle readiness (before setup)
4. Create field definitions (rating, comments)
5. List field definitions
6. Create form template
7. Attach fields to form
8. Get form with fields
9. Assign form to cycle
10. Get employees (for assignments)
11. Bulk create assignments
12. List assignments
13. Check cycle readiness (after setup)
14. Activate cycle

### 3. Reviewer Workflow - Complete Evaluation
Reviewer completes an evaluation:
1. Get my assignments
2. Create or get evaluation
3. Get evaluation details
4. Validate draft (before saving)
5. Save draft
6. Get evaluation after draft save
7. Submit evaluation

### 4. Approver Workflow - Review & Approve
Approver reviews and approves evaluations:
1. Get my assignments (as approver)
2. List evaluations (pending approval)
3. Get evaluation for approval
4. Approve evaluation
5. Return evaluation (alternative)

### 5. Statistics & Reports
View statistics and reports:
1. Get user stats
2. Get cycle statistics
3. List all cycles
4. List evaluations with filters

### 6. Employee Management
Employee-related operations:
1. List employees
2. Quick search employees
3. Bulk employee lookup
4. Get employee by ID

### 7. Audit & Admin
Admin-only operations:
1. Admin ping
2. List audit events
3. Get audit events for cycle

### 8. Error Scenarios & Edge Cases
Test error handling:
1. Try to activate cycle without form
2. Try to update ACTIVE cycle
3. Try to create assignment in ACTIVE cycle
4. Try to submit invalid evaluation
5. Try to access without If-Match header

### 9. Close Cycle
Final step:
1. Close cycle

## Key Features

### Automatic Variable Management
The collection automatically captures and stores:
- `cycle_id` - From cycle creation
- `form_template_id` - From form creation
- `field_definition_id_1` and `field_definition_id_2` - From field creation
- `assignment_id` - From assignment creation
- `evaluation_id` - From evaluation creation
- `evaluation_version` - From ETag headers (for optimistic locking)
- Employee IDs - From employee listing

### Optimistic Locking
The collection handles optimistic locking automatically:
- Extracts version from `ETag` header
- Includes `If-Match` header in subsequent requests
- Updates version after each modification

### Idempotency
Many requests include `Idempotency-Key` headers to ensure safe retries.

### Test Scripts
Each request includes test scripts that:
- Verify status codes
- Extract and store variables
- Validate response structure

## Running Workflows

### Run Complete Workflow
1. Select the collection
2. Click "Run" button
3. Select all folders
4. Click "Run Cycle Manager API..."

### Run Individual Workflows
- Run folders 1-4 in sequence for a complete end-to-end test
- Run folder 8 to test error scenarios
- Run folder 5-7 for reporting and admin tasks

### Run Individual Requests
- Click on any request to run it individually
- Variables will be populated from previous requests

## Expected Results

### Successful Workflow
1. **Setup**: Health check returns 200
2. **Admin**: Cycle created, form attached, assignments created, cycle activated
3. **Reviewer**: Evaluation created, draft saved, evaluation submitted
4. **Approver**: Evaluation approved
5. **Statistics**: All stats endpoints return data
6. **Close**: Cycle closed successfully

### Error Scenarios
- Folder 8 requests should return appropriate error codes (409, 422, 428, etc.)
- Error messages should be descriptive

## Troubleshooting

### Variables Not Populating
- Ensure you run requests in order
- Check that test scripts are executing (View → Show Postman Console)
- Manually set variables if needed

### 404 Errors
- Verify `base_url` is correct
- Ensure server is running
- Check that resources exist (cycle_id, evaluation_id, etc.)

### 401/403 Errors
- Verify user emails are correct
- Ensure users exist in database
- Check user roles are properly assigned

### 428 Errors (Precondition Required)
- Ensure `If-Match` header is included
- Get the evaluation first to obtain the ETag
- Use the version from the ETag header

## Notes

- All dates should be in ISO format (YYYY-MM-DD)
- Employee IDs must be valid UUIDs
- The collection assumes at least 3 employees exist in the database
- Some requests require previous requests to have completed successfully




