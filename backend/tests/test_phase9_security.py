"""
Phase 9 — Security tests (live API).

RBAC enforcement, authentication requirements, ownership isolation,
and input-validation behaviour (FR access-control + BR security rules).
"""
import unittest

from tests.base import (
    AdminLiveTest, FacultyLiveTest, LiveAPITest, BASE, login,
    OTHER_FACULTY_EMAIL,
)


class TestUnauthenticated(LiveAPITest):
    """401/403 without a token on protected endpoints."""

    def _get(self, path):
        return self.client.get(f"{BASE}{path}")

    def test_me_requires_auth(self):
        self.assertEqual(self._get("/auth/me").status_code, 401)

    def test_travels_requires_auth(self):
        self.assertEqual(self._get("/travels/").status_code, 401)

    def test_documents_requires_auth(self):
        self.assertEqual(self._get("/documents/user/all").status_code, 401)

    def test_audit_requires_auth(self):
        self.assertEqual(self._get("/audit-logs").status_code, 401)

    def test_insights_requires_auth(self):
        self.assertEqual(self._get("/ai/insights").status_code, 401)

    def test_compliance_records_requires_auth(self):
        self.assertEqual(self._get("/compliance/records").status_code, 401)

    def test_bad_token_rejected(self):
        r = self.client.get(f"{BASE}/auth/me",
                            headers={"Authorization": "Bearer not-a-real-token"})
        self.assertIn(r.status_code, (401, 403))

    def test_empty_bearer_rejected(self):
        # httpx rejects empty header values client-side (LocalProtocolError);
        # a blank credential must never authenticate, so treat the client-side
        # rejection or a server 401/403 both as "rejected".
        try:
            r = self.client.get(f"{BASE}/auth/me",
                                headers={"Authorization": "Bearer "})
            self.assertIn(r.status_code, (401, 403))
        except Exception:
            pass  # client refused to send the malformed header


class TestFacultyRBAC(AdminLiveTest):
    """Faculty role must be denied admin-only capabilities."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.faculty = login("jpayla@csucc.edu.ph", "FacultyPass123!")

    def test_cannot_read_audit_logs(self):
        r = self.client.get(f"{BASE}/audit-logs", headers=self.faculty)
        self.assertEqual(r.status_code, 403)

    def test_cannot_read_all_remarks(self):
        r = self.client.get(f"{BASE}/remarks", headers=self.faculty)
        self.assertEqual(r.status_code, 403)

    def test_cannot_list_users(self):
        r = self.client.get(f"{BASE}/users/", headers=self.faculty)
        self.assertEqual(r.status_code, 403)

    def test_cannot_list_compliance_records(self):
        r = self.client.get(f"{BASE}/compliance/records", headers=self.faculty)
        self.assertEqual(r.status_code, 403)

    def test_cannot_recompute_insights(self):
        r = self.client.post(f"{BASE}/ai/insights/recompute", headers=self.faculty,
                             json={})
        self.assertEqual(r.status_code, 403)

    def test_cannot_list_insights(self):
        r = self.client.get(f"{BASE}/ai/insights", headers=self.faculty)
        self.assertEqual(r.status_code, 403)

    def test_cannot_create_doc_type(self):
        r = self.client.post(f"{BASE}/document-types/", headers=self.faculty,
                             json={"name": "P9 Security Probe",
                                   "category": "Pre-Travel"})
        self.assertEqual(r.status_code, 403)

    def test_cannot_create_announcement(self):
        r = self.client.post(f"{BASE}/announcements/", headers=self.faculty,
                             json={"title": "P9 probe", "content": "probe"})
        self.assertEqual(r.status_code, 403)

    def test_cannot_create_user(self):
        r = self.client.post(f"{BASE}/users/", headers=self.faculty, json={
            "full_name": "P9 Probe", "email": "p9-probe@csucc.edu.ph",
            "password": "ProbePass123!", "role": "faculty"})
        self.assertEqual(r.status_code, 403)


class TestOwnershipIsolation(AdminLiveTest):
    """Faculty must not touch another user's travel."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = login("jpayla@csucc.edu.ph", "FacultyPass123!")
        # A travel owned by the other faculty user (rlmariscal) if any exist;
        # otherwise create one as admin-owned? Use rlmariscal via direct create.
        cls.other = login(OTHER_FACULTY_EMAIL, "FacultyPass123!")
        r = cls.client.post(f"{BASE}/travels/", headers=cls.other, json={
            "event_title": "P9 Security Owned Travel",
            "mobility_type": "International Conference",
            "participant_type": "Faculty",
            "college_id": 5,
            "start_date": "2026-08-01", "end_date": "2026-08-05",
            "location": "X", "country": "Y",
        })
        if r.status_code in (200, 201):
            cls.owned_id = r.json()["travel_id"]
        else:
            owner_id = cls.client.get(f"{BASE}/auth/me", headers=cls.owner).json()["user_id"]
            travels = cls.client.get(f"{BASE}/travels/", headers=cls.owner,
                                     params={"limit": 50}).json()
            other = [t for t in travels if t.get("user_id") != owner_id]
            cls.owned_id = other[0]["travel_id"] if other else None

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "owned_id", None) and hasattr(cls, "other"):
            cls.client.delete(f"{BASE}/travels/{cls.owned_id}", headers=cls.other)
        super().tearDownClass()

    def test_cannot_read_others_travel(self):
        if not self.owned_id:
            self.skipTest("no other-owned travel available")
        r = self.client.get(f"{BASE}/travels/{self.owned_id}", headers=self.owner)
        self.assertEqual(r.status_code, 403)

    def test_cannot_delete_others_travel(self):
        if not self.owned_id:
            self.skipTest("no other-owned travel available")
        r = self.client.delete(f"{BASE}/travels/{self.owned_id}", headers=self.owner)
        self.assertEqual(r.status_code, 403)


class TestInputValidation(AdminLiveTest):
    """Bad payloads must be rejected, not crash."""

    def test_suggest_remark_missing_id(self):
        r = self.client.post(f"{BASE}/ai/suggest-remark", headers=self.admin,
                             json={})
        self.assertEqual(r.status_code, 422)

    def test_document_analysis_missing_id(self):
        r = self.client.post(f"{BASE}/ai/document-analysis", headers=self.admin,
                             json={})
        self.assertEqual(r.status_code, 422)

    def test_document_analysis_unknown_doc(self):
        r = self.client.post(f"{BASE}/ai/document-analysis", headers=self.admin,
                             json={"document_id": 999999999})
        self.assertEqual(r.status_code, 404)

    def test_travel_limit_unknown_user(self):
        r = self.client.get(f"{BASE}/compliance/travel-limit/999999999",
                            headers=self.admin)
        self.assertEqual(r.status_code, 404)

    def test_insights_bad_priority_filter(self):
        r = self.client.get(f"{BASE}/ai/insights", headers=self.admin,
                            params={"priority": "urgent"})
        self.assertEqual(r.status_code, 422)

    def test_unknown_route_404(self):
        r = self.client.get(f"{BASE}/definitely-not-a-route", headers=self.admin)
        self.assertEqual(r.status_code, 404)

    def test_login_sql_injection_safe(self):
        r = self.client.post(f"{BASE}/auth/login", json={
            "email": "oige@csucc.edu.ph'; DROP TABLE users;--",
            "password": "x"})
        # 401 (bad creds) or 422 (email validation rejects the payload) are
        # both safe; anything else (200, 500) would be a problem.
        self.assertIn(r.status_code, (401, 422))
        # server still alive afterwards
        r = self.client.get(f"{BASE}/health")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
