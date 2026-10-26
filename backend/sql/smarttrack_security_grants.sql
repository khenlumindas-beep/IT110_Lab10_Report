-- ============================================================================
-- SMARTTRACK POSTGRESQL SECURITY
-- GRANT and REVOKE Statements for Role-Based Access Control
-- 
-- Database: smarttrack_db
-- Schema: system_core
-- Roles: app_admin, app_faculty
-- ============================================================================

-- ============================================================================
-- BLOCK 1: CREATE APPLICATION ROLES
-- ============================================================================

CREATE ROLE app_admin NOLOGIN;
CREATE ROLE app_faculty NOLOGIN;

-- ============================================================================
-- BLOCK 2: GRANT SCHEMA USAGE
-- ============================================================================

GRANT USAGE ON SCHEMA system_core TO app_admin;
GRANT USAGE ON SCHEMA system_core TO app_faculty;

-- ============================================================================
-- BLOCK 3: USERS TABLE - GRANT/REVOKE
-- ============================================================================

-- Admin: full control on users table
GRANT SELECT, INSERT, UPDATE, DELETE ON system_core.users TO app_admin;

-- Faculty: NO access to users table (user management is admin-only)
REVOKE ALL ON system_core.users FROM app_faculty;

-- ============================================================================
-- BLOCK 4: TRAVELS TABLE - GRANT/REVOKE
-- ============================================================================

-- Admin: full control on travels (all operations)
GRANT SELECT, INSERT, UPDATE, DELETE ON system_core.travels TO app_admin;

-- Faculty: can create and manage own travels (SELECT, INSERT, UPDATE but NOT DELETE)
GRANT SELECT, INSERT, UPDATE ON system_core.travels TO app_faculty;

-- Faculty: CANNOT delete travels (maintain audit trail)
REVOKE DELETE ON system_core.travels FROM app_faculty;

-- ============================================================================
-- BLOCK 5: DOCUMENTS TABLE - GRANT/REVOKE
-- ============================================================================

-- Admin: full control on documents
GRANT SELECT, INSERT, UPDATE, DELETE ON system_core.documents TO app_admin;

-- Faculty: can upload and update documents for own travels (SELECT, INSERT, UPDATE but NOT DELETE)
GRANT SELECT, INSERT, UPDATE ON system_core.documents TO app_faculty;

-- Faculty: CANNOT delete documents (maintain audit trail)
REVOKE DELETE ON system_core.documents FROM app_faculty;

-- ============================================================================
-- BLOCK 6: COMPLIANCE_RECORDS TABLE - GRANT/REVOKE
-- ============================================================================

-- Admin: SELECT and UPDATE (can view and modify compliance status)
GRANT SELECT, UPDATE ON system_core.compliance_records TO app_admin;

-- Faculty: SELECT only (can view but NOT modify their compliance status - computed by system)
GRANT SELECT ON system_core.compliance_records TO app_faculty;

-- Faculty: explicitly revoke other operations
REVOKE INSERT, UPDATE, DELETE ON system_core.compliance_records FROM app_faculty;

-- ============================================================================
-- BLOCK 7: AUDIT_LOGS TABLE - IMMUTABLE (APPEND ONLY)
-- ============================================================================

-- Admin: SELECT only (read audit trail for security review)
GRANT SELECT ON system_core.audit_logs TO app_admin;

-- Admin: CANNOT modify audit logs (immutable - even admin cannot INSERT, UPDATE, DELETE)
REVOKE INSERT, UPDATE, DELETE ON system_core.audit_logs FROM app_admin;

-- Faculty: NO access to audit logs (security-sensitive)
REVOKE ALL ON system_core.audit_logs FROM app_faculty;

-- ============================================================================
-- BLOCK 8: REMARK_HISTORY TABLE - APPEND ONLY
-- ============================================================================

-- Admin: SELECT and INSERT only (can read remarks and add new ones, but NOT modify existing)
GRANT SELECT, INSERT ON system_core.remark_history TO app_admin;

-- Admin: CANNOT modify or delete existing remarks (audit trail)
REVOKE UPDATE, DELETE ON system_core.remark_history FROM app_admin;

-- Faculty: SELECT only (can view remarks on own travels)
GRANT SELECT ON system_core.remark_history TO app_faculty;

-- Faculty: CANNOT add remarks (only admin can)
REVOKE INSERT, UPDATE, DELETE ON system_core.remark_history FROM app_faculty;

-- ============================================================================
-- BLOCK 9: SUPPORTING TABLES (READ-ONLY REFERENCE DATA)
-- ============================================================================

-- COLLEGES table: SELECT only
GRANT SELECT ON system_core.colleges TO app_admin;
GRANT SELECT ON system_core.colleges TO app_faculty;

-- DEPARTMENTS table: SELECT only
GRANT SELECT ON system_core.departments TO app_admin;
GRANT SELECT ON system_core.departments TO app_faculty;

-- DOCUMENT_TYPES table: SELECT only
GRANT SELECT ON system_core.document_types TO app_admin;
GRANT SELECT ON system_core.document_types TO app_faculty;

-- REQUIREMENT_ITEMS table: SELECT only
GRANT SELECT ON system_core.requirement_items TO app_admin;
GRANT SELECT ON system_core.requirement_items TO app_faculty;

-- ANNOUNCEMENTS table: SELECT only
GRANT SELECT ON system_core.announcements TO app_admin;
GRANT SELECT ON system_core.announcements TO app_faculty;

-- ============================================================================
-- BLOCK 10: SEQUENCE PERMISSIONS (for auto-increment IDs)
-- ============================================================================

-- Allow roles to use sequences for INSERT operations
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA system_core TO app_admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA system_core TO app_faculty;

-- ============================================================================
-- TEST CASES (Optional - uncomment to run tests)
-- ============================================================================

-- TEST 1: Admin can INSERT travels (should SUCCEED)
-- SET ROLE app_admin;
-- INSERT INTO system_core.travels 
--   (user_id, college_id, participant_type, event_title, mobility_type, 
--    start_date, end_date, workflow_status) 
-- VALUES 
--   (3, 1, 'Faculty', 'Test Travel - Admin', 'Faculty Exchange', 
--    '2026-11-01', '2026-11-30', 'Pending Requirements');
-- RESET ROLE;

-- TEST 2: Faculty can INSERT travels (should SUCCEED)
-- SET ROLE app_faculty;
-- INSERT INTO system_core.travels 
--   (user_id, college_id, participant_type, event_title, mobility_type, 
--    start_date, end_date, workflow_status) 
-- VALUES 
--   (5, 1, 'Faculty', 'Test Travel - Faculty', 'Faculty Exchange', 
--    '2026-12-01', '2026-12-30', 'Pending Requirements');
-- RESET ROLE;

-- TEST 3: Faculty CANNOT DELETE travels (should FAIL with permission denied)
-- SET ROLE app_faculty;
-- DELETE FROM system_core.travels WHERE travel_id = 1;
-- RESET ROLE;

-- TEST 4: Faculty CANNOT access users table (should FAIL with permission denied)
-- SET ROLE app_faculty;
-- SELECT * FROM system_core.users LIMIT 1;
-- RESET ROLE;

-- TEST 5: Admin CANNOT DELETE audit_logs (immutable - should FAIL with permission denied)
-- SET ROLE app_admin;
-- DELETE FROM system_core.audit_logs WHERE audit_id = 1;
-- RESET ROLE;

-- ============================================================================
-- END OF SMARTTRACK SECURITY SETUP
-- ============================================================================


-- ============================================================================
-- PART 2: ROW-LEVEL SECURITY (RLS) POLICIES
-- ============================================================================

-- ============================================================================
-- Enable RLS on Tables
-- ============================================================================

ALTER TABLE system_core.travels ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_core.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_core.compliance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_core.post_travel_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_core.remark_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_core.notifications ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- TRAVELS TABLE - RLS POLICIES
-- ============================================================================

-- Policy: Faculty can only SELECT their own travels
CREATE POLICY travels_faculty_select ON system_core.travels
  FOR SELECT
  USING (
    user_id = COALESCE(
      NULLIF(current_setting('app.current_user_id', true), '')::int,
      0
    )
    OR
    COALESCE(current_setting('app.current_user_role', true), '') = 'super_admin'
  );

-- Policy: Faculty can only INSERT travels as owner (user_id must match)
CREATE POLICY travels_faculty_insert ON system_core.travels
  FOR INSERT
  WITH CHECK (
    user_id = COALESCE(
      NULLIF(current_setting('app.current_user_id', true), '')::int,
      0
    )
  );

-- Policy: Faculty can only UPDATE their own travels
CREATE POLICY travels_faculty_update ON system_core.travels
  FOR UPDATE
  USING (
    user_id = COALESCE(
      NULLIF(current_setting('app.current_user_id', true), '')::int,
      0
    )
  );

-- Policy: Super admin can do everything on travels
CREATE POLICY travels_admin_all ON system_core.travels
  FOR ALL
  TO app_admin
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- DOCUMENTS TABLE - RLS POLICIES
-- ============================================================================

-- Policy: Faculty can only see documents in their own travels
CREATE POLICY documents_faculty_select ON system_core.documents
  FOR SELECT
  USING (
    travel_id IN (
      SELECT travel_id FROM system_core.travels 
      WHERE user_id = COALESCE(
        NULLIF(current_setting('app.current_user_id', true), '')::int,
        0
      )
    )
    OR
    COALESCE(current_setting('app.current_user_role', true), '') = 'super_admin'
  );

-- Policy: Faculty can only INSERT documents into their own travels
CREATE POLICY documents_faculty_insert ON system_core.documents
  FOR INSERT
  WITH CHECK (
    travel_id IN (
      SELECT travel_id FROM system_core.travels 
      WHERE user_id = COALESCE(
        NULLIF(current_setting('app.current_user_id', true), '')::int,
        0
      )
    )
  );

-- Policy: Super admin can do everything on documents
CREATE POLICY documents_admin_all ON system_core.documents
  FOR ALL
  TO app_admin
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- COMPLIANCE_RECORDS TABLE - RLS POLICIES
-- ============================================================================

-- Policy: Faculty can only see their own compliance records
CREATE POLICY compliance_faculty_select ON system_core.compliance_records
  FOR SELECT
  USING (
    travel_id IN (
      SELECT travel_id FROM system_core.travels 
      WHERE user_id = COALESCE(
        NULLIF(current_setting('app.current_user_id', true), '')::int,
        0
      )
    )
    OR
    COALESCE(current_setting('app.current_user_role', true), '') = 'super_admin'
  );

-- Policy: Super admin can do everything on compliance records
CREATE POLICY compliance_admin_all ON system_core.compliance_records
  FOR ALL
  TO app_admin
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- POST_TRAVEL_REQUIREMENTS TABLE - RLS POLICIES
-- ============================================================================

-- Policy: Faculty can only see requirements for their own travels
CREATE POLICY requirements_faculty_select ON system_core.post_travel_requirements
  FOR SELECT
  USING (
    travel_id IN (
      SELECT travel_id FROM system_core.travels 
      WHERE user_id = COALESCE(
        NULLIF(current_setting('app.current_user_id', true), '')::int,
        0
      )
    )
    OR
    COALESCE(current_setting('app.current_user_role', true), '') = 'super_admin'
  );

-- Policy: Super admin can do everything
CREATE POLICY requirements_admin_all ON system_core.post_travel_requirements
  FOR ALL
  TO app_admin
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- REMARK_HISTORY TABLE - RLS POLICIES
-- ============================================================================

-- Policy: Faculty can only see remarks for their own travels
CREATE POLICY remarks_faculty_select ON system_core.remark_history
  FOR SELECT
  USING (
    travel_id IN (
      SELECT travel_id FROM system_core.travels 
      WHERE user_id = COALESCE(
        NULLIF(current_setting('app.current_user_id', true), '')::int,
        0
      )
    )
    OR
    COALESCE(current_setting('app.current_user_role', true), '') = 'super_admin'
  );

-- Policy: Super admin can do everything
CREATE POLICY remarks_admin_all ON system_core.remark_history
  FOR ALL
  TO app_admin
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- NOTIFICATIONS TABLE - RLS POLICIES
-- ============================================================================

-- Policy: Users can only see their own notifications
CREATE POLICY notifications_user_own ON system_core.notifications
  FOR SELECT
  USING (
    user_id = COALESCE(
      NULLIF(current_setting('app.current_user_id', true), '')::int,
      0
    )
    OR
    COALESCE(current_setting('app.current_user_role', true), '') = 'super_admin'
  );

-- Policy: Super admin can see all notifications
CREATE POLICY notifications_admin_all ON system_core.notifications
  FOR ALL
  TO app_admin
  USING (true)
  WITH CHECK (true);

-- ============================================================================
-- END OF ROW-LEVEL SECURITY SETUP
-- ============================================================================
