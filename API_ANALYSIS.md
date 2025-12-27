# API Analysis: Requirements for Smooth, Secure, and Accurate UI

## 🔴 Critical Security Issues

### 1. **CORS Configuration**
- **Current**: `allow_origins=["*"]` - allows all origins
- **Risk**: CSRF attacks, unauthorized access
- **Fix**: Restrict to specific frontend origins in production
- **Location**: `app/main.py:20`

### 2. **Authentication Method**
- **Current**: Dev-only `X-User-Email` header authentication
- **Risk**: No real authentication, anyone can impersonate users
- **Fix**: Implement proper JWT/OAuth2 authentication
- **Location**: `app/core/security.py:9-26`

### 3. **No Rate Limiting**
- **Risk**: API abuse, DoS attacks
- **Fix**: Add rate limiting middleware (e.g., slowapi)

### 4. **Input Sanitization**
- **Current**: Basic validation exists, but no XSS protection
- **Risk**: Stored XSS in text fields
- **Fix**: Sanitize text inputs before storing

---

## 🟡 Missing Data in Responses (N+1 Query Problems)

### 1. **Assignments Return Only Employee IDs**
- **Problem**: UI must make N+1 calls to resolve employee names
- **Current**: `AssignmentOut` has `reviewer_employee_id`, `subject_employee_id`, `approver_employee_id` (UUIDs only)
- **Impact**: Slow UI, poor UX
- **Fix**: Add `?expand=employees` parameter or always include names
- **Endpoints Affected**:
  - `GET /cycles/{cycle_id}/assignments`
  - `GET /me/assignments`
  - `POST /cycles/{cycle_id}/assignments/bulk` (response)

### 2. **Evaluations Missing Assignment Context**
- **Problem**: UI can't show "Reviewing: John Doe" without extra calls
- **Current**: `EvaluationOut` has `assignment_id` but no employee names
- **Fix**: Include assignment context with employee names
- **Endpoints Affected**:
  - `GET /cycles/{cycle_id}/evaluations`
  - `GET /me/evaluations`
  - `GET /cycles/{cycle_id}/evaluations/{evaluation_id}`

### 3. **No Pagination Metadata**
- **Problem**: UI can't show "Page 1 of 5" or "Showing 1-20 of 100"
- **Current**: All list endpoints return arrays only
- **Fix**: Wrap in `PaginatedResponse` with `total`, `limit`, `offset`, `has_more`
- **Endpoints Affected**: All `GET` endpoints returning lists

### 4. **/me Endpoint Missing Employee ID**
- **Problem**: UI must query employees separately to link user to employee
- **Current**: Returns user info but not `employee_id`
- **Fix**: Include `employee_id` in `/me` response
- **Location**: `app/api/me.py:16-24`

---

## 🟠 Missing Endpoints for Smooth UX

### 1. **Cycle Readiness Check**
- **Need**: `GET /cycles/{cycle_id}/readiness`
- **Returns**: `{ready: bool, can_activate: bool, checks: {...}, warnings: [], errors: []}`
- **Use Case**: Wizard validation before activation

### 2. **Statistics/Dashboard Endpoints**
- **Need**: 
  - `GET /me/stats` - User's evaluation/assignment counts
  - `GET /cycles/{cycle_id}/stats` - Cycle completion rates, status breakdowns
- **Use Case**: Dashboard widgets, progress indicators

### 3. **Bulk Employee Lookup**
- **Need**: `POST /employees/bulk-lookup` with `{employee_ids: [...]}`
- **Returns**: Employee names for multiple IDs in one call
- **Use Case**: Resolve employee names for assignment/evaluation lists

### 4. **Validation Preview**
- **Need**: `POST /cycles/{cycle_id}/evaluations/{evaluation_id}/validate`
- **Returns**: `{valid: bool, errors: [...], warnings: [...]}`
- **Use Case**: Show validation errors before submit attempt

### 5. **Form Preview**
- **Need**: `GET /cycles/{cycle_id}/form-preview`
- **Returns**: Form structure without loading full evaluation
- **Use Case**: Wizard shows form fields before creating evaluation

### 6. **Evaluation Progress**
- **Need**: `GET /cycles/{cycle_id}/evaluations/{evaluation_id}/progress`
- **Returns**: `{total_fields: 5, filled: 4, progress: 0.8, completion_status: "ready_to_submit"}`
- **Use Case**: Progress bars, completion indicators

### 7. **Quick Actions**
- **Need**: `GET /me/quick-actions`
- **Returns**: Prioritized list of actions user can take
- **Use Case**: Dashboard "What's next" suggestions

### 8. **Cycle Summary (All-in-One)**
- **Need**: `GET /cycles/{cycle_id}/summary`
- **Returns**: Cycle + form + assignments + stats in one call
- **Use Case**: Wizard needs all data upfront

---

## 🟢 Error Handling Improvements

### Current State
- ✅ Validation errors are structured: `{message: "...", errors: [{field, code, message}]}`
- ❌ Generic errors are strings: `detail="Cycle not found"`
- ❌ No suggestions on how to fix errors
- ❌ No links to relevant docs/endpoints

### Recommended Format
```python
class ErrorResponse(BaseModel):
    error: str  # "VALIDATION_ERROR", "NOT_FOUND", etc.
    message: str
    code: str  # "CYCLE_NOT_FOUND", "INVALID_EMPLOYEE_REFERENCE"
    field: str | None  # if field-specific
    suggestions: list[str]  # ["Check cycle ID", "Verify cycle exists"]
    links: dict[str, str]  # {"cycles": "/cycles", "help": "/docs"}
```

### Endpoints Needing Better Errors
- All 404 errors should include suggestions
- All 403 errors should explain why access denied
- All 409 errors should explain conflict and resolution

---

## 🔵 Data Consistency & Validation

### 1. **Cycle Activation Pre-flight**
- **Need**: `GET /cycles/{cycle_id}/can-activate`
- **Returns**: `{can_activate: bool, reasons: [], blockers: []}`
- **Use Case**: Prevent activation attempts that will fail

### 2. **Assignment Validation Before Bulk Create**
- **Need**: `POST /cycles/{cycle_id}/assignments/validate`
- **Returns**: `{valid: bool, errors: [{index, field, message}], warnings: []}`
- **Use Case**: Validate CSV imports, prevent bulk failures

### 3. **Employee Reference Validation**
- **Current**: Validates UUID format and existence
- **Good**: ✅ Already implemented
- **Enhancement**: Return employee name in error for better UX

---

## 🟣 Performance Optimizations

### 1. **Eager Loading for Related Data**
- **Problem**: N+1 queries when loading evaluations with assignments
- **Fix**: Use SQLAlchemy `joinedload()` or `selectinload()`
- **Affected**: 
  - `GET /cycles/{cycle_id}/evaluations`
  - `GET /me/evaluations`

### 2. **Response Caching Hints**
- **Need**: Add `Cache-Control` headers for read-only endpoints
- **Endpoints**: 
  - `GET /forms/{id}` (form templates rarely change)
  - `GET /employees` (employee list changes infrequently)

### 3. **Pagination Defaults**
- **Current**: Some endpoints default to 100, others to 20
- **Fix**: Standardize defaults (20 for lists, 100 for admin views)

---

## 🟤 Missing Business Logic Endpoints

### 1. **Bulk Status Updates**
- **Need**: `POST /cycles/{cycle_id}/evaluations/bulk-approve`
- **Use Case**: Approve multiple evaluations at once

### 2. **Form Template Clone**
- **Need**: `POST /forms/{form_id}/clone`
- **Use Case**: Create similar forms without starting from scratch

### 3. **Cycle Archive**
- **Current**: Only DRAFT → ACTIVE → CLOSED
- **Need**: `POST /cycles/{cycle_id}/archive`
- **Use Case**: Move old cycles out of active view

### 4. **Evaluation Return with Comment**
- **Current**: `POST /evaluations/{id}/return` exists
- **Enhancement**: Add optional comment field for why it was returned

---

## 📊 Summary: Priority Ranking

### **P0 - Critical (Security & Core Functionality)**
1. ✅ Fix CORS configuration (production)
2. ✅ Implement real authentication
3. ✅ Add rate limiting
4. ✅ Include employee names in assignment/evaluation responses
5. ✅ Add pagination metadata to all list endpoints
6. ✅ Include employee_id in /me response

### **P1 - High Priority (UX Blockers)**
7. ✅ Cycle readiness check endpoint
8. ✅ Statistics endpoints (dashboard data)
9. ✅ Bulk employee lookup
10. ✅ Validation preview endpoint
11. ✅ Form preview endpoint
12. ✅ Evaluation progress calculation

### **P2 - Medium Priority (Nice to Have)**
13. ✅ Quick actions endpoint
14. ✅ Cycle summary (all-in-one)
15. ✅ Better error responses with suggestions
16. ✅ Assignment validation endpoint
17. ✅ Eager loading optimizations

### **P3 - Low Priority (Future Enhancements)**
18. ✅ Bulk status updates
19. ✅ Form template clone
20. ✅ Response caching hints
21. ✅ Cycle archive endpoint

---

## ✅ What's Already Good

1. **Validation**: Comprehensive two-tier validation (draft vs submit)
2. **Optimistic Locking**: ETags prevent lost updates
3. **Idempotency**: Safe retries for critical operations
4. **Audit Logging**: Full audit trail
5. **Access Control**: Proper RBAC and role-based filtering
6. **Error Structure**: Validation errors are well-structured
7. **Database Constraints**: Strong data integrity (unique keys, check constraints)

---

## 🎯 Recommended Implementation Order

**Week 1 (Security & Core)**
- Fix CORS
- Add employee names to responses (expand parameter)
- Add pagination metadata
- Include employee_id in /me

**Week 2 (UX Essentials)**
- Cycle readiness check
- Statistics endpoints
- Bulk employee lookup
- Validation preview

**Week 3 (Polish)**
- Form preview
- Progress calculation
- Better error responses
- Quick actions

**Week 4 (Optimization)**
- Eager loading
- Response caching
- Performance tuning

