# IT 108 — Laboratory Activity No. 7
## Securing the PostgreSQL Database of SmartTrack

**Database:** `smarttrack_db` (PostgreSQL 16), all application tables in schema **`system_core`**
**Application roles (actual, from `models.py` check constraint):** `super_admin`, `faculty`
**Backend:** FastAPI, SQLAlchemy ORM, JWT authentication

---

## Part A — System roles

| System role | Main responsibilities | Data / actions that require access | Security concern |
|---|---|---|---|
| `super_admin` | OIGE director/admin: manage user accounts, verify documents, approve/return travel workflows, read audit trail and analytics | SELECT/INSERT/UPDATE on users, travels, documents, compliance; SELECT on audit_logs | Must not read plaintext passwords, must not modify audit logs, cannot delete travel history |
| `faculty` | Own international mobility records: create/edit own travels, upload own documents, view own compliance and remarks | SELECT/INSERT/UPDATE on own travels and documents; SELECT own compliance/remarks | Must never read other faculty's travels, documents or remarks; cannot manage users; cannot delete records |
| `student participant` | Appears in travel records as a participant; **no login account** (managed by admin/faculty) | No direct database access | PII inside travel rows; must be visible only to owner/admin |

The application authenticates with JWT; the role claim is one of `super_admin` / `faculty`.

---

## Part B — Important tables (5)

| Table | Purpose / sensitive data | Roles that use it | Why access must be controlled |
|---|---|---|---|
| `system_core.users` | Accounts: full_name, email, `password_hash` (bcrypt), role, is_active | super_admin | PII + authentication data; password hashes must never leak |
| `system_core.travels` | Faculty/student mobility records: destination, dates, workflow status, owner `user_id` | super_admin, faculty | Personal travel data; owner-only rows; audit trail |
| `system_core.documents` | Passport/visa/insurance uploads linked to `travel_id` and `user_id` | super_admin, faculty | Sensitive personal documents |
| `system_core.compliance_records` | Computed compliance status per travel | super_admin, faculty (read) | Must not be edited by faculty; drives approvals |
| `system_core.audit_logs` | Security/administrative activity history | super_admin (read only) | Must be immutable/append-only for forensics |

### Access-control matrix

| Table | Role | SELECT | INSERT | UPDATE | DELETE | Restriction / reason |
|---|---|---|---|---|---|---|
| users | super_admin | Y | Y | Y (not password_hash directly) | N | No hard delete; deactivate via `is_active` |
| users | faculty | Own row only | N | Own profile fields only | N | Cannot browse user accounts |
| travels | super_admin | Y (all) | Y | Y | N | Soft workflow states instead of delete |
| travels | faculty | **Own rows only** | Y (own) | Own rows only | N | Audit trail; no delete |
| documents | super_admin | Y (all) | Y | Y (verify/reject) | N | Evidence retention |
| documents | faculty | Own rows only | Y (own) | Own rows only | N | Cannot delete submitted evidence |
| compliance_records | super_admin | Y | Y (recompute) | Y | N | System-computed |
| compliance_records | faculty | Own rows only | N | N | N | Read-only |
| audit_logs | super_admin | Y | N | N | N | Immutable |
| audit_logs | faculty | N | N | N | N | No access |

---

## Part C — GRANT and REVOKE (project-specific)

```sql
-- Application DB roles (mapped from JWT roles super_admin / faculty)
CREATE ROLE smarttrack_super_admin NOLOGIN;
CREATE ROLE smarttrack_faculty NOLOGIN;

GRANT USAGE ON SCHEMA system_core TO smarttrack_super_admin, smarttrack_faculty;

-- 1) User management is admin-only
GRANT SELECT, INSERT, UPDATE ON system_core.users TO smarttrack_super_admin;
REVOKE ALL ON system_core.users FROM smarttrack_faculty;

-- 2) Travels: admin full read/write; faculty create/edit own, never delete
GRANT SELECT, INSERT, UPDATE ON system_core.travels TO smarttrack_super_admin;
GRANT SELECT, INSERT, UPDATE ON system_core.travels TO smarttrack_faculty;
REVOKE DELETE ON system_core.travels FROM smarttrack_faculty;

-- 3) Documents: faculty upload/update own, no delete
GRANT SELECT, INSERT, UPDATE ON system_core.documents TO smarttrack_super_admin;
GRANT SELECT, INSERT, UPDATE ON system_core.documents TO smarttrack_faculty;
REVOKE DELETE ON system_core.documents FROM smarttrack_faculty;

-- 4) Compliance: faculty read-only
GRANT SELECT ON system_core.compliance_records TO smarttrack_faculty;
REVOKE INSERT, UPDATE, DELETE ON system_core.compliance_records FROM smarttrack_faculty;

-- 5) Audit logs: immutable, admin read-only
GRANT SELECT ON system_core.audit_logs TO smarttrack_super_admin;
REVOKE INSERT, UPDATE, DELETE ON system_core.audit_logs FROM smarttrack_super_admin;
REVOKE ALL ON system_core.audit_logs FROM smarttrack_faculty;

-- 6) Sequences for INSERTs
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA system_core TO smarttrack_faculty;
```

Prepared full script: `backend/sql/smarttrack_security_grants.sql`.

### Test execution (temporary roles `st_test_admin`, `st_test_faculty`, created and dropped after the test)

| ID | Role + table | Test | Actual result |
|---|---|---|---|
| T1 | faculty → travels | `SELECT count(*)` | **SUCCESS — 67 rows** |
| T2 | faculty → travels | `DELETE` | **DENIED — 42501 permission denied for table travels** |
| T3 | faculty → users | `SELECT count(*)` | **DENIED — 42501 permission denied for table users** |
| T4 | admin → audit_logs | `INSERT` | **DENIED — 42501 permission denied for table audit_logs** |
| T5 | admin → audit_logs | `SELECT count(*)` | **SUCCESS — 1499 rows** |

Conclusion: least-privilege GRANT/REVOKE behaves as designed: faculty can read travels but cannot delete them or see accounts; admin can read the audit trail but cannot write to it.

---

## Part D — Row-Level Security decision

| Question | Answer |
|---|---|
| Do multiple users/roles access the same table? | **YES** — all faculty share `travels`, `documents`, `compliance_records`, `remark_history` |
| Should a user see only rows belonging to that user? | **YES** — a faculty member may only see their own mobility records and documents |
| Which tables need row filtering? | `travels`, `documents`, `compliance_records`, `post_travel_requirements`, `remark_history`, `notifications` |
| Does the project need PostgreSQL RLS? | **YES** (defense-in-depth) |
| Justification | SmartTrack's core screens are "My Travels" and "My Documents". Today the FastAPI layer enforces ownership (`WHERE user_id = current_user.user_id`), but a single forgotten filter would expose every faculty member's international travel and passport/visa files. RLS makes the database enforce `user_id = current_setting('app.current_user_id')::int`, so even a backend bug cannot return another user's rows. Policies are prepared in `backend/sql/smarttrack_security_grants.sql`; enabling them requires the backend to issue `SET LOCAL app.current_user_id = ...` per request (currently not yet wired, so RLS is **designed but not enabled** in the live database — API-level filtering is the active control). |

Policy pattern (prepared):

```sql
ALTER TABLE system_core.travels ENABLE ROW LEVEL SECURITY;

CREATE POLICY travels_owner_select ON system_core.travels
  FOR SELECT USING (
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::int
  );

CREATE POLICY travels_admin_all ON system_core.travels
  FOR ALL TO smarttrack_super_admin USING (true) WITH CHECK (true);
```

---

## Part E — Credential protection

| Check | Evidence |
|---|---|
| No hard-coded credentials in committed source | `backend/config.py` loads `DATABASE_URL`, `SECRET_KEY`, SMTP secrets from environment via `os.getenv` / pydantic-settings; `.env.example` has placeholders only |
| `.env` excluded from Git | Root `.gitignore` contains `.env` and `backend/.env`; `git ls-files backend/.env` returns nothing |
| No secrets in repo | `.env` is untracked; committed sample file uses `YOUR_PASSWORD_HERE` |
| Hard-coded mock login removed | `routes/auth.py` previously contained plaintext mock passwords; removed in commit `c987580` — login now fails closed against the database |
| Least-privilege DB account | **Gap identified:** the development `DATABASE_URL` connects as `postgres` (superuser). Recommended production setting: `postgresql://smarttrack_app:•••@127.0.0.1:5432/smarttrack_db` with only the grants in Part C. This is documented as the next hardening step. |

---

## Part F — SQL injection review (real code)

**Feature / file / function:** Travel list filter — `backend/routes/travels.py`, `get_travels()` (`GET /api/travels/?country=...`)

```python
query = db.query(Travel)
if country:
    query = query.filter(Travel.country.ilike(f"%{country}%"))
```

**User input:** `country` query parameter (also `status`, `mobility_type`, `participant_type`, `year`, `skip`, `limit`).

**Parameterized / ORM binding:** **YES** — SQLAlchemy Core/ORM builds the statement and sends the value as a bound parameter.

Generated SQL:

```sql
SELECT ... FROM system_core.travels WHERE travels.country ILIKE %(country_1)s;
-- parameter: country_1 = '%Japan%'
```

**Why it is safe:** the `f"%{country}%"` only builds the *value* passed to `ilike()`; SQLAlchemy never concatenates it into SQL text. PostgreSQL receives the SQL structure and the data separately, so input such as `'; DROP TABLE travels; --` is searched as a literal string and matches nothing. `limit`/`skip` are typed integers validated by FastAPI, and all inserts/updates go through ORM model attributes, never string-built SQL.

Unsafe pattern avoided:

```python
db.execute(text(f"SELECT * FROM travels WHERE country ILIKE '%{country}%'"))  # VULNERABLE
```

---

## Post-laboratory reflection

1. **Greatest DB access:** `smarttrack_super_admin` (read/write users, travels, documents). `DELETE` is not necessary — soft-delete/workflow status is enough; audit logs must stay read-only.
2. **Most sensitive table:** `users` (password hashes + PII) — faculty has no access, admin cannot read/write hashes through the API, and passwords are bcrypt-hashed.
3. **RLS:** yes for defense-in-depth on owner-scoped tables; policies are prepared, enforcement currently at API layer, with `SET LOCAL app.current_user_id` as the next step.
4. **If credentials leaked:** anyone could connect directly as `postgres` and bypass the API; prevented by ignoring `.env`, committing only `.env.example`, and (recommended) switching to a least-privilege DB role.
5. **Query reviewed:** travels country filter — SQLAlchemy binds `%country%` as a parameter (`$1`), keeping user input separate from SQL syntax.

---

**Repository:** `C:\xampp\htdocs\SmartTrack` — security fixes committed as `c987580`.
