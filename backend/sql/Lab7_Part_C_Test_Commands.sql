-- ============================================================================
-- IT 108 LAB 7 - PART C: TEST EXECUTION COMMANDS
-- ============================================================================
-- Copy each block below and paste into pgAdmin Query Tool
-- Execute each one separately and take a screenshot of the Results panel
--
-- Database: smarttrack_db
-- Schema: system_core
-- ============================================================================

-- ============================================================================
-- TEST 1: SKIPPED - Roles already exist (app_admin, app_faculty)
-- ============================================================================
-- If you got "ERROR: role 'app_admin' already exists", 
-- this means TEST 1 was already run. Skip to TEST 2.


-- ============================================================================
-- TEST 2a: GRANT Schema Usage
-- ============================================================================
-- Screenshot: Figure C-1a
-- Expected: GRANT x2

GRANT USAGE ON SCHEMA system_core TO app_admin;
GRANT USAGE ON SCHEMA system_core TO app_faculty;

-- Result should show:
-- GRANT
-- GRANT
-- Query returned successfully


-- ============================================================================
-- TEST 2b: REVOKE DELETE from app_faculty on travels (Security Test)
-- ============================================================================
-- Screenshot: Figure C-1b
-- Expected: REVOKE (Success)

REVOKE DELETE ON system_core.travels FROM app_faculty;

-- Result should show:
-- REVOKE
-- Query returned successfully in XX msec.
-- ✅ PASS: Successfully removed DELETE permission from faculty


-- ============================================================================
-- TEST 2c: REVOKE ALL from app_faculty on users (Security Test)
-- ============================================================================
-- Screenshot: Figure C-1c
-- Expected: REVOKE (Success)

REVOKE ALL ON system_core.users FROM app_faculty;

-- Result should show:
-- REVOKE
-- Query returned successfully in XX msec.
-- ✅ PASS: Successfully removed ALL permissions on users from faculty


-- ============================================================================
-- TEST 2d: REVOKE INSERT, UPDATE, DELETE from app_admin on audit_logs (Immutable)
-- ============================================================================
-- Screenshot: Figure C-1d
-- Expected: REVOKE (Success)

REVOKE INSERT, UPDATE, DELETE ON system_core.audit_logs FROM app_admin;

-- Result should show:
-- REVOKE
-- Query returned successfully in XX msec.
-- ✅ PASS: Audit logs are now immutable - admin cannot modify


-- ============================================================================
-- TEST 3: First, check existing user IDs (find a valid user_id to use)
-- ============================================================================
-- Screenshot: Figure C-2 (optional - just for reference)
-- This shows what user IDs exist

SELECT user_id, email FROM system_core.users LIMIT 3;

-- Then use one of these user_ids in TEST 3b below
-- For example, if you see user_id = 1, use that instead of 106


-- ============================================================================
-- TEST 3b: app_faculty CAN INSERT into travels (ALLOWED)
-- ============================================================================
-- Screenshot: Figure C-2 (ACTUAL SCREENSHOT)
-- Expected: INSERT 0 1 (Success)
-- 
-- ⚠️ IMPORTANT: Replace the user_id below with a VALID user_id from your database
--   If no valid user exists, create a test user first:
--   INSERT INTO system_core.users (email, full_name, role, hashed_password) 
--   VALUES ('test_faculty@csu.edu', 'Test Faculty', 'faculty', 'hashed_pwd');

SET ROLE app_faculty;
INSERT INTO system_core.travels 
  (user_id, college_id, participant_type, event_title, mobility_type, 
   start_date, end_date, workflow_status) 
VALUES 
  (1, 1, 'Faculty', 'Test Travel - Faculty Insert', 'Faculty Exchange', 
   '2026-11-15', '2026-11-22', 'Pending Requirements');
RESET ROLE;

-- Result should show:
-- INSERT 0 1
-- Query returned successfully in XX msec.
-- ✅ PASS: Faculty can create travels


-- ============================================================================
-- TEST 4: app_faculty CANNOT DELETE travels (DENIED)
-- ============================================================================
-- Screenshot: Figure C-3
-- Expected: ERROR: permission denied

SET ROLE app_faculty;
DELETE FROM system_core.travels WHERE travel_id = 1;
RESET ROLE;

-- Result should show:
-- ERROR: permission denied for table travels
-- SQL state: 42501
-- ❌ EXPECTED DENIAL: Faculty cannot delete


-- ============================================================================
-- TEST 5: app_admin CAN DELETE travels (ALLOWED - for cleanup)
-- ============================================================================
-- Screenshot: Figure C-4
-- Expected: DELETE 1

SET ROLE app_admin;
DELETE FROM system_core.travels 
WHERE travel_id IN (
  SELECT travel_id FROM system_core.travels 
  WHERE event_title = 'Test Travel - Faculty Insert' 
  LIMIT 1
);
RESET ROLE;

-- Result should show:
-- DELETE 1
-- Query returned successfully in XX msec.
-- ✅ PASS: Admin can delete


-- ============================================================================
-- TEST 6: app_faculty CANNOT ACCESS users table (DENIED)
-- ============================================================================
-- Screenshot: Figure C-5
-- Expected: ERROR: permission denied

SET ROLE app_faculty;
SELECT COUNT(*) FROM system_core.users;
RESET ROLE;

-- Result should show:
-- ERROR: permission denied for table users
-- SQL state: 42501
-- ❌ EXPECTED DENIAL: Faculty cannot see user accounts


-- ============================================================================
-- TEST 7: app_admin CANNOT DELETE audit_logs (IMMUTABLE - DENIED)
-- ============================================================================
-- Screenshot: Figure C-6
-- Expected: ERROR: permission denied

SET ROLE app_admin;
DELETE FROM system_core.audit_logs WHERE audit_id = 1;
RESET ROLE;

-- Result should show:
-- ERROR: permission denied for table audit_logs
-- SQL state: 42501
-- ✅ IMMUTABLE: Even admin cannot modify audit trail


-- ============================================================================
-- TEST 8: app_faculty CANNOT SELECT compliance_records (DENIED)
-- ============================================================================
-- Screenshot: Figure C-7
-- Expected: ERROR: permission denied

SET ROLE app_faculty;
SELECT COUNT(*) FROM system_core.compliance_records;
RESET ROLE;

-- Result should show:
-- ERROR: permission denied for table compliance_records
-- SQL state: 42501
-- ❌ EXPECTED DENIAL: Faculty cannot access compliance records


-- ============================================================================
-- TEST 9: app_admin CAN SELECT remark_history (ALLOWED)
-- ============================================================================
-- Screenshot: Figure C-8
-- Expected: Shows rows or 0 rows (no error)

SET ROLE app_admin;
SELECT COUNT(*) FROM system_core.remark_history;
RESET ROLE;

-- Result should show:
-- count
-- -------
--   N (some number)
-- (1 row)
-- ✅ PASS: Admin can read remarks


-- ============================================================================
-- TEST 10: app_faculty CAN SELECT remark_history (ALLOWED - read-only)
-- ============================================================================
-- Screenshot: Figure C-9
-- Expected: Shows rows or 0 rows (no error)

SET ROLE app_faculty;
SELECT COUNT(*) FROM system_core.remark_history;
RESET ROLE;

-- Result should show:
-- count
-- -------
--   N (some number)
-- (1 row)
-- ✅ PASS: Faculty can READ remarks (if RLS filters own travels)


-- ============================================================================
-- TEST 11: app_faculty CAN SELECT documents (ALLOWED - own travel)
-- ============================================================================
-- Screenshot: Figure C-10
-- Expected: Shows rows or 0 rows (no error)

SET ROLE app_faculty;
SELECT COUNT(*) FROM system_core.documents;
RESET ROLE;

-- Result should show:
-- count
-- -------
--   N (some number)
-- (1 row)
-- ✅ PASS: Faculty can view documents (filtered by RLS)


-- ============================================================================
-- TEST 12: app_faculty CANNOT DELETE documents (DENIED - immutable audit)
-- ============================================================================
-- Screenshot: Figure C-11
-- Expected: ERROR: permission denied

SET ROLE app_faculty;
DELETE FROM system_core.documents WHERE document_id = 1;
RESET ROLE;

-- Result should show:
-- ERROR: permission denied for table documents
-- SQL state: 42501
-- ❌ EXPECTED DENIAL: Documents cannot be deleted (audit trail)


-- ============================================================================
-- TEST 13: app_admin CAN SELECT all documents (ALLOWED)
-- ============================================================================
-- Screenshot: Figure C-12
-- Expected: Shows total documents count

SET ROLE app_admin;
SELECT COUNT(*) as total_documents FROM system_core.documents;
RESET ROLE;

-- Result should show something like:
-- total_documents
-- ----------------
--       150
-- (1 row)
-- ✅ PASS: Admin can view all faculty documents


-- ============================================================================
-- CLEANUP: Delete test records (optional - run as admin)
-- ============================================================================

-- DELETE FROM system_core.documents WHERE file_name = 'test_passport.pdf';
-- DELETE FROM system_core.remark_history WHERE remark_text LIKE 'Test%';

-- ============================================================================
-- END OF TEST COMMANDS
-- ============================================================================
