# IT 110 — Laboratory Activity No. 10
## FastAPI Backend Health Check and REST API Testing

**System:** SmartTrack — AI-Based International Travel Monitoring System (CSUCC OIGE)
**Backend:** FastAPI + Uvicorn + PostgreSQL (`smarttrack_db`, schema `system_core`)
**Repository checkpoint:** `c987580` (security fixes) — this report commit follows.

---

## 1. Backend startup

Project layout: `backend/main.py` (app object `main:app`).

```bash
cd backend
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8001
```

The project normally runs on port **5000** for the Flutter client. Port **8001** was used for this activity because port 8000 was already in use. Startup output ended with:

```
Database initialized successfully
Application startup complete.
Uvicorn running on http://127.0.0.1:8001
```

Interactive docs: `http://127.0.0.1:8001/api/docs`
OpenAPI schema: `http://127.0.0.1:8001/api/openapi.json`

---

## 2. S01 — Health check evidence

| Item | Result |
|---|---|
| URL | `http://127.0.0.1:8001/health` |
| Status | **200 OK** |
| Body | `{"status":"ok"}` |
| Screenshot | `docs/activity10/S01_health.png` |

`GET /api/health` also returns the extended health object:

```json
{"status":"healthy","timestamp":"2026-10-27T04:11:21.433575","version":"1.0.0"}
```

**Correction made:** the application originally exposed only `/api/health`. A root `GET /health` route returning exactly `{"status":"ok"}` was added in `main.py` for the Activity 10 contract.

---

## 3. S02 — Swagger UI and endpoint inventory

Screenshots: `S02_docs.png` (top: authentication, users, travels), `S02b_docs.png` (middle: documents, compliance, analytics), `S02c_docs.png` (bottom: notifications, announcements, audit, requirements).

Swagger UI loaded **115 API operations** across these feature groups:

| Feature group | Ops | Representative routes |
|---|---|---|
| Authentication | 5 | `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me`, `POST /api/auth/logout`, `POST /api/auth/register` |
| User management | 10 | `GET/POST /api/users/`, `GET/PUT/DELETE /api/users/{id}`, `POST /api/users/{id}/role`, `POST /api/users/{id}/reactivate`, `POST /api/users/change-password` |
| Travel records | 25 | `GET/POST /api/travels/`, `GET/PUT/DELETE /api/travels/{id}`, `PATCH /api/travels/{id}/workflow`, submit-for-approval, statistics |
| Documents | 12 | `POST /api/documents/upload`, `GET /api/documents/`, verify/reject/resubmit, stats |
| Compliance | 3 | `GET /api/compliance/records`, recompute, travel limits |
| Analytics / AI | 13 | system & college summaries, risk, trends, AI insights, document analysis, suggested remarks |
| Notifications / announcements | 9 | `GET /api/notifications/`, unread count, read-all, announcements CRUD |
| SIAP / Mobility plans / Re-entry / Post-travel | 24 | internships, faculty mobility plan, re-entry activities, post-travel requirements |
| Reference data | 14 | colleges, departments, document types, requirement items |
| Audit / remarks | 3 | `GET /api/audit-logs`, `GET /api/remarks`, `GET /api/remarks/mine` |
| System | 3 | `/`, `/health`, `/api/health` |

A machine-generated appendix listing all 115 method+path pairs follows at the end of this report.

---

## 4. Part A — Feature-to-endpoint inventory (tested operations)

| ID | Feature / user action | Method and path | Role / test data | Expected | Actual | Proof |
|---|---|---|---|---|---|---|
| F01 | Log in | `POST /api/auth/login` | super_admin `oige@csucc.edu.ph` | 200 + JWT | **200**, access/refresh token (redacted) | `F01_login_200.png` |
| F02 | List user accounts | `GET /api/users/?skip=0&limit=100` | super_admin bearer token | 200 + list | **200**, 27 accounts | `F02_users_list_200.png` |
| F03 | Create user account | `POST /api/users/` | super_admin; `Lab Test User` / `labtest_act10@csucc.edu.ph` / role `faculty` | 200 + created record | **200**, returns `user_id`; test record deleted after test | `F03_user_create.png` |
| F04 | List travel records | `GET /api/travels/` | super_admin token | 200 + list | **200**, 67 travels | `F04_travels_200.png` |
| F05 | System analytics summary | `GET /api/analytics/system/summary` | super_admin token | 200 + aggregates | **200** | `F05_analytics_200.png` |
| F06 | List notifications | `GET /api/notifications/` | super_admin token | 200 + list | **200** | `F06_notifications_200.png` |
| F07 | Read audit trail | `GET /api/audit-logs` | super_admin token | 200 + log rows | **200**, audit entries | `F07_audit_200.png` |

Remaining feature groups were inventoried through `/docs` and `/api/openapi.json`; write/delete operations were exercised only with safe test records (F03), which were cleaned up afterwards.

---

## 5. Error-to-success evidence (E01)

| Phase | Detail |
|---|---|
| **A — Before** | `POST /api/auth/login` with `{"email":"oige@csucc.edu.ph","password":"WrongPass!"}` → **401 Unauthorized**; body `{"detail":"Invalid email or password"}`. Screenshot: `E01_before_login_401.png` |
| **B — Diagnosis** | Status 401 is the documented authentication failure, i.e. an expected negative test — not a backend defect. The endpoint correctly rejects a bad credential and does not reveal whether the email exists. |
| **C — After** | Same endpoint with the valid test credential → **200 OK** with token payload (`expires_in: 1800`). Screenshot: `F01_login_200.png` |
| **D — Record** | Endpoint is covered by the backend test suite; security fixes committed in `c987580`. |

**Additional correction (pre-test):** the root `/health` path returned 404 because only `/api/health` existed. `GET /health → {"status":"ok"}` was implemented in `main.py`; after state is `S01_health.png`. (The 404 was observed in the terminal before the route existed; no before screenshot is claimed.)

---

## 6. Evidence authenticity and secret handling

- All screenshots come from the running backend at `127.0.0.1:8001`.
- Bearer tokens and passwords were masked (DOM-level redaction) before capture: `"access_token": "REDACTED"`, `"password": "********"`. Status codes, paths and response shapes are unmodified.
- `backend/.env` is not tracked by Git; `.env.example` contains placeholders only.
- Hard-coded mock credentials were removed from `routes/auth.py` as part of this activity.

---

## 7. Post-laboratory reflection

1. **First issue preventing `/health`?** The app only had `/api/health`; `/health` returned 404. Added a root health route returning exactly `{"status":"ok"}`.
2. **Hardest endpoint to test?** `POST /api/users/` — it requires a valid super-admin bearer token, a whitelisted role (`super_admin`/`faculty`), and it enforces the max-2-super-admin rule, so test data had to be chosen carefully.
3. **What did a failed response reveal?** A 401 from wrong credentials is correct client-input handling, not a backend defect. Defects are 500s or successful-but-wrong responses; negative 4xx responses prove validation works.
4. **How was success proven beyond the status code?** The create response returned the new `user_id` and echoed the stored fields, and a follow-up list call showed the record persisted. (The test record was then deleted.)
5. **Ready for Flutter integration?** Auth, user management, travel records, analytics, and notifications all returned valid 200 responses and are ready. No blocking backend issue remains; AI/insight endpoints are functional but recommended for additional edge-case testing.

---

## Appendix — Full endpoint inventory (115 operations)

Total: **115** operations

- `GET /` - Root
- `POST /api/ai/document-analysis` - Analyze Document
- `GET /api/ai/document-analysis/{document_id}` - Get Document Analysis
- `GET /api/ai/insights` - List Insights
- `POST /api/ai/insights/recompute` - Recompute Insights
- `POST /api/ai/insights/{insight_id}/accept` - Accept Insight
- `POST /api/ai/suggest-remark` - Suggest Remark
- `GET /api/analytics/college/{college_id}/summary` - Get College Analytics
- `GET /api/analytics/system/summary` - Get System Analytics
- `GET /api/analytics/travel/{travel_id}/compliance` - Get Travel Compliance
- `GET /api/analytics/travel/{travel_id}/risk` - Get Travel Risk Prediction
- `GET /api/analytics/trends/mobility-types` - Get Mobility Type Distribution
- `GET /api/analytics/trends/top-countries` - Get Top Travel Countries
- `GET /api/analytics/user/summary` - Get User Analytics
- `GET /api/announcements/` - Get Announcements
- `POST /api/announcements/` - Create Announcement
- `PUT /api/announcements/{announcement_id}` - Update Announcement
- `PATCH /api/announcements/{announcement_id}/deactivate` - Deactivate Announcement
- `GET /api/audit-logs` - List Audit Logs
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Get Current User Info
- `POST /api/auth/refresh` - Refresh Token
- `POST /api/auth/register` - Register
- `GET /api/colleges/` - List Colleges
- `POST /api/colleges/` - Create College
- `GET /api/colleges/{college_id}` - Get College
- `PUT /api/colleges/{college_id}` - Update College
- `GET /api/colleges/{college_id}/departments` - List College Departments
- `POST /api/colleges/{college_id}/departments` - Create Department
- `GET /api/colleges/{college_id}/stats` - Get College Stats
- `GET /api/compliance/records` - List Compliance
- `GET /api/compliance/travel-limit/{faculty_user_id}` - Check Travel Limit
- `GET /api/compliance/travel-limits` - List Travel Limits
- `GET /api/document-types/` - List Document Types
- `POST /api/document-types/` - Create Document Type
- `PUT /api/document-types/{doc_type_id}` - Update Document Type
- `DELETE /api/document-types/{doc_type_id}` - Delete Document Type
- `GET /api/documents/` - List All Documents
- `GET /api/documents/stats/summary` - Get Document Statistics
- `GET /api/documents/travel/{travel_id}` - Get Travel Documents
- `POST /api/documents/upload` - Upload Document
- `GET /api/documents/user/all` - Get User Documents
- `GET /api/documents/{document_id}` - Get Document
- `DELETE /api/documents/{document_id}` - Delete Document
- `GET /api/documents/{document_id}/file` - Download Document File
- `PATCH /api/documents/{document_id}/reject` - Reject Document
- `POST /api/documents/{document_id}/resubmit` - Resubmit Document
- `PATCH /api/documents/{document_id}/status` - Update Document Status
- `PATCH /api/documents/{document_id}/verify` - Verify Document
- `GET /api/download/apk` - Download Apk
- `GET /api/health` - Health Check
- `GET /api/mobility-plans/` - List Plans
- `POST /api/mobility-plans/` - Create Or Update My Plan
- `GET /api/mobility-plans/distribution` - Get Distribution
- `GET /api/mobility-plans/my-plan` - Get My Plan
- `PUT /api/mobility-plans/{plan_id}` - Update Plan
- `DELETE /api/mobility-plans/{plan_id}` - Delete Plan
- `GET /api/notifications/` - Get Notifications
- `PATCH /api/notifications/read-all` - Mark All As Read
- `GET /api/notifications/unread/count` - Get Unread Count
- `DELETE /api/notifications/{notification_id}` - Delete Notification
- `PATCH /api/notifications/{notification_id}/read` - Mark Notification As Read
- `GET /api/remarks` - List Remarks
- `GET /api/remarks/mine` - List My Remarks
- `GET /api/requirements/` - List Requirement Items
- `GET /api/requirements/ai-check/{travel_id}` - Ai Check Travel
- `GET /api/requirements/checklist-files` - Checklist Files
- `GET /api/requirements/report` - Requirements Report
- `GET /api/requirements/report/export` - Requirements Report Export
- `GET /api/requirements/templates/{template_key}` - Download Template
- `GET /api/requirements/travel/{travel_id}` - Travel Requirements
- `GET /api/siap/` - List Internships
- `POST /api/siap/` - Create Internship
- `GET /api/siap/stats/by-college` - Internships By College
- `GET /api/siap/{internship_id}` - Get Internship
- `PUT /api/siap/{internship_id}` - Update Internship
- `DELETE /api/siap/{internship_id}` - Delete Internship
- `PATCH /api/siap/{internship_id}/status` - Update Internship Status
- `POST /api/travels/` - Create Travel
- `GET /api/travels/` - List Travels
- `GET /api/travels/college/{college_id}` - Get College Travels
- `GET /api/travels/college/{college_id}/statistics` - Get College Statistics
- `GET /api/travels/statistics/` - Get Travel Statistics
- `GET /api/travels/user/{user_id}` - Get User Travels
- `GET /api/travels/{travel_id}` - Get Travel
- `PUT /api/travels/{travel_id}` - Update Travel
- `DELETE /api/travels/{travel_id}` - Delete Travel
- `PATCH /api/travels/{travel_id}/compliance` - Update Compliance Status
- `GET /api/travels/{travel_id}/compliance` - Get Compliance
- `POST /api/travels/{travel_id}/compliance/recompute` - Recompute Compliance
- `GET /api/travels/{travel_id}/post-travel/` - List Post Travel
- `POST /api/travels/{travel_id}/post-travel/` - Create Post Travel
- `PATCH /api/travels/{travel_id}/post-travel/{requirement_id}` - Update Post Travel
- `DELETE /api/travels/{travel_id}/post-travel/{requirement_id}` - Delete Post Travel
- `POST /api/travels/{travel_id}/post-travel/{requirement_id}/evidence` - Upload Post Travel Evidence
- `GET /api/travels/{travel_id}/re-entry/` - List Reentry
- `POST /api/travels/{travel_id}/re-entry/` - Create Reentry
- `PATCH /api/travels/{travel_id}/re-entry/{activity_id}` - Update Reentry
- `DELETE /api/travels/{travel_id}/re-entry/{activity_id}` - Delete Reentry
- `POST /api/travels/{travel_id}/re-entry/{activity_id}/evidence` - Upload Reentry Evidence
- `PATCH /api/travels/{travel_id}/status` - Update Travel Status
- `POST /api/travels/{travel_id}/submit-for-approval` - Submit Travel For Approval
- `PATCH /api/travels/{travel_id}/workflow` - Update Travel Workflow
- `GET /api/users/` - List Users
- `POST /api/users/` - Create User
- `POST /api/users/change-password` - Change Password
- `GET /api/users/profile` - Get User Profile
- `PUT /api/users/profile` - Update User Profile
- `GET /api/users/{user_id}` - Get User By Id
- `PUT /api/users/{user_id}` - Update User
- `DELETE /api/users/{user_id}` - Deactivate User
- `POST /api/users/{user_id}/reactivate` - Reactivate User
- `POST /api/users/{user_id}/role` - Change User Role
- `GET /health` - Health
