"""
Phase 9 — Functional tests (live API).

Covers core happy-path workflows end to end: auth, travels, documents,
document types, notifications, compliance, lifecycle, audit, AI.
Writes are cleaned up where the API supports deletion.
"""
import io
import uuid
import unittest

from tests.base import AdminLiveTest, FacultyLiveTest, BASE


def _unique(prefix="P9"):
    return f"{prefix} {uuid.uuid4().hex[:8]}"


class TestFunctionalAuth(AdminLiveTest):
    def test_health(self):
        r = self.client.get(f"{BASE}/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "healthy")

    def test_login_returns_token(self):
        r = self.client.post(f"{BASE}/auth/login",
                             json={"email": "oige@csucc.edu.ph", "password": "AdminPass123!"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access_token", r.json())

    def test_me_returns_profile(self):
        r = self.client.get(f"{BASE}/auth/me", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["email"], "oige@csucc.edu.ph")
        self.assertEqual(body["role"], "super_admin")

    def test_wrong_password_rejected(self):
        r = self.client.post(f"{BASE}/auth/login",
                             json={"email": "oige@csucc.edu.ph", "password": "nope"})
        self.assertEqual(r.status_code, 401)


class TestFunctionalTravelLifecycle(FacultyLiveTest):
    """Create -> read -> update -> delete a travel (FR-F02, UC-F02)."""

    def setUp(self):
        r = self.client.post(f"{BASE}/travels/", headers=self.faculty, json={
            "event_title": _unique("P9 Travel"),
            "mobility_type": "International Conference",
            "participant_type": "Faculty",
            "college_id": 5,
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "location": "Test City",
            "country": "Testland",
        })
        self.assertIn(r.status_code, (200, 201), r.text)
        self.travel = r.json()

    def tearDown(self):
        self.client.delete(f"{BASE}/travels/{self.travel['travel_id']}",
                           headers=self.faculty)

    def test_travel_created(self):
        self.assertTrue(self.travel["travel_id"] > 0)
        self.assertTrue(self.travel["event_title"].startswith("P9 Travel"))

    def test_travel_read(self):
        r = self.client.get(f"{BASE}/travels/{self.travel['travel_id']}",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["travel_id"], self.travel["travel_id"])

    def test_travel_update(self):
        r = self.client.put(f"{BASE}/travels/{self.travel['travel_id']}",
                            headers=self.faculty,
                            json={"event_title": _unique("P9 Edited")})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["event_title"].startswith("P9 Edited"))

    def test_travel_in_list(self):
        r = self.client.get(f"{BASE}/travels/", headers=self.faculty,
                            params={"limit": 100})
        self.assertEqual(r.status_code, 200)
        ids = [t["travel_id"] for t in r.json()]
        self.assertIn(self.travel["travel_id"], ids)

    def test_workflow_submit(self):
        # Workflow transitions are admin-only; faculty must be denied.
        r = self.client.patch(f"{BASE}/travels/{self.travel['travel_id']}/workflow",
                              headers=self.faculty, json={"workflow_status": "Submitted"})
        self.assertEqual(r.status_code, 403, r.text)


class TestFunctionalWorkflowAdmin(AdminLiveTest):
    """Admin can advance a travel through the workflow (8-state lifecycle)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests.base import login, FACULTY_EMAIL, FACULTY_PASSWORD
        cls.fh = login(FACULTY_EMAIL, FACULTY_PASSWORD)

    def test_admin_workflow_transition(self):
        r = self.client.post(f"{BASE}/travels/", headers=self.fh, json={
            "event_title": _unique("P9 Workflow"),
            "mobility_type": "International Conference",
            "participant_type": "Faculty",
            "college_id": 5,
            "start_date": "2026-10-01", "end_date": "2026-10-05",
            "location": "W", "country": "W",
        })
        self.assertIn(r.status_code, (200, 201), r.text)
        tid = r.json()["travel_id"]
        try:
            r2 = self.client.patch(f"{BASE}/travels/{tid}/workflow",
                                   headers=self.admin,
                                   json={"workflow_status": "Approved"})
            self.assertIn(r2.status_code, (200, 400), r2.text)
        finally:
            self.client.delete(f"{BASE}/travels/{tid}", headers=self.fh)


class TestFunctionalDocumentRoundtrip(FacultyLiveTest):
    """Upload -> fetch -> download -> delete a document (FR-F03, UC-F03)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        r = cls.client.post(f"{BASE}/travels/", headers=cls.faculty, json={
            "event_title": _unique("P9 DocTravel"),
            "mobility_type": "International Training",
            "participant_type": "Faculty",
            "college_id": 5,
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "location": "Test City",
            "country": "Testland",
        })
        assert r.status_code in (200, 201), r.text
        cls.travel_id = r.json()["travel_id"]

    @classmethod
    def tearDownClass(cls):
        cls.client.delete(f"{BASE}/travels/{cls.travel_id}", headers=cls.faculty)
        super().tearDownClass()

    def setUp(self):
        payload = b"%PDF-1.4 phase9 functional test document"
        files = {"file": ("phase9_test_document.pdf", io.BytesIO(payload),
                          "application/pdf")}
        r = self.client.post(f"{BASE}/documents/upload", headers=self.faculty,
                             params={"travel_id": self.travel_id,
                                     "doc_type": "Travel Report"},
                             files=files)
        self.assertEqual(r.status_code in (200, 201), True, r.text)
        self.doc = r.json()

    def tearDown(self):
        self.client.delete(f"{BASE}/documents/{self.doc['document_id']}",
                           headers=self.faculty)

    def test_upload(self):
        self.assertGreater(self.doc["document_id"], 0)
        self.assertEqual(self.doc["status"], "Submitted")
        self.assertEqual(self.doc["doc_type"], "Travel Report")

    def test_fetch(self):
        r = self.client.get(f"{BASE}/documents/{self.doc['document_id']}",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200)

    def test_download(self):
        r = self.client.get(f"{BASE}/documents/{self.doc['document_id']}/file",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200)

    def test_list_by_travel(self):
        r = self.client.get(f"{BASE}/documents/travel/{self.travel_id}",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200)
        ids = [d["document_id"] for d in r.json()]
        self.assertIn(self.doc["document_id"], ids)

    def test_auto_analysis_created(self):
        r = self.client.get(
            f"{BASE}/ai/document-analysis/{self.doc['document_id']}",
            headers=self.faculty)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "complete")


class TestFunctionalDocTypes(AdminLiveTest):
    """Admin CRUD on document types (FR-A13-adjacent configuration)."""

    def setUp(self):
        r = self.client.post(f"{BASE}/document-types/", headers=self.admin,
                             json={"name": _unique("P9 DocType"),
                                   "category": "Pre-Travel",
                                   "is_required": False})
        self.assertEqual(r.status_code in (200, 201), True, r.text)
        self.doc_type = r.json()

    def tearDown(self):
        self.client.delete(f"{BASE}/document-types/{self.doc_type['doc_type_id']}",
                           headers=self.admin)

    def test_created(self):
        self.assertTrue(self.doc_type["name"].startswith("P9 DocType"))

    def test_update(self):
        new_name = _unique("P9 DocTypeRenamed")
        r = self.client.put(f"{BASE}/document-types/{self.doc_type['doc_type_id']}",
                            headers=self.admin, json={"name": new_name})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["name"], new_name)

    def test_listed(self):
        r = self.client.get(f"{BASE}/document-types/", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        names = [t["name"] for t in r.json()]
        self.assertIn(self.doc_type["name"], names)


class TestFunctionalReads(AdminLiveTest):
    """Read-side smoke of the admin monitoring surface (FR-A01..A08, A15)."""

    def test_system_summary(self):
        r = self.client.get(f"{BASE}/analytics/system/summary", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertIn("total_travels", r.json())

    def test_compliance_records(self):
        r = self.client.get(f"{BASE}/compliance/records", headers=self.admin,
                            params={"limit": 20})
        self.assertEqual(r.status_code, 200)

    def test_travel_limits(self):
        r = self.client.get(f"{BASE}/compliance/travel-limits", headers=self.admin)
        self.assertEqual(r.status_code, 200)

    def test_audit_logs(self):
        r = self.client.get(f"{BASE}/audit-logs", headers=self.admin,
                            params={"limit": 10})
        self.assertEqual(r.status_code, 200)

    def test_remarks(self):
        r = self.client.get(f"{BASE}/remarks", headers=self.admin,
                            params={"limit": 10})
        self.assertEqual(r.status_code, 200)

    def test_users_list(self):
        r = self.client.get(f"{BASE}/users/", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()), 0)

    def test_announcements_list(self):
        r = self.client.get(f"{BASE}/announcements/", headers=self.admin)
        self.assertEqual(r.status_code, 200)

    def test_notifications_list(self):
        r = self.client.get(f"{BASE}/notifications/", headers=self.admin,
                            params={"limit": 5})
        self.assertEqual(r.status_code, 200)

    def test_ai_insights_list(self):
        r = self.client.get(f"{BASE}/ai/insights", headers=self.admin,
                            params={"limit": 5})
        self.assertEqual(r.status_code, 200)

    def test_mobility_plans(self):
        r = self.client.get(f"{BASE}/mobility-plans/", headers=self.admin)
        self.assertEqual(r.status_code, 200)

    def test_siap_list(self):
        r = self.client.get(f"{BASE}/siap/", headers=self.admin)
        self.assertEqual(r.status_code, 200)

    def test_colleges_list(self):
        r = self.client.get(f"{BASE}/colleges/", headers=self.admin)
        self.assertEqual(r.status_code, 200)


class TestFunctionalFacultyReads(FacultyLiveTest):
    """Read-side smoke of the faculty surface (FR-F01, F07, F10)."""

    def test_my_travels(self):
        r = self.client.get(f"{BASE}/travels/", headers=self.faculty,
                            params={"limit": 20})
        self.assertEqual(r.status_code, 200)

    def test_my_documents(self):
        r = self.client.get(f"{BASE}/documents/user/all", headers=self.faculty)
        self.assertEqual(r.status_code, 200)

    def test_my_remarks(self):
        r = self.client.get(f"{BASE}/remarks/mine", headers=self.faculty,
                            params={"limit": 10})
        self.assertEqual(r.status_code, 200)

    def test_my_plan(self):
        r = self.client.get(f"{BASE}/mobility-plans/my-plan", headers=self.faculty)
        self.assertIn(r.status_code, (200, 404))

    def test_announcements_visible(self):
        r = self.client.get(f"{BASE}/announcements/", headers=self.faculty)
        self.assertEqual(r.status_code, 200)

    def test_user_summary(self):
        r = self.client.get(f"{BASE}/analytics/user/summary", headers=self.faculty)
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
