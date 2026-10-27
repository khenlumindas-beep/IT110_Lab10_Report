"""
Pre-Travel requirements gate (boss directive, 2026-10-20):

- New travels start at workflow_status = 'Pending Requirements'.
- POST /travels/{id}/submit-for-approval is owner-only; blocked (422) until
  every required Pre-Travel item has a submitted document; then -> Submitted.
- PATCH /travels/{id}/workflow to 'Approved' is blocked (422) while the same
  checklist is incomplete.
"""
import io
import os
import unittest

BASE = os.environ.get("SMARTTRACK_API", "http://127.0.0.1:5000/api")

from tests.base import (  # noqa: E402
    AdminLiveTest, FacultyLiveTest, login,
    FACULTY_EMAIL, FACULTY_PASSWORD, OTHER_FACULTY_EMAIL, FACULTY_PASSWORD as OTHER_PW,
)

# Required Faculty Pre-Travel parents (master list, phase Pre-Travel).
FACULTY_PRE_REQUIRED = [
    "Letter of Intent",
    "Endorsement Letter (Immediate Supervisor)",
    "Invitation Letter",
    "CHED IAS Assessment",
    "Itinerary of Travel",
    "Travel Order",
    "Re-Entry Action Plan",
    "Certificate of Employment",
]

PDF = b"%PDF-1.4 pretravel gate test"


class TestPreTravelGate(AdminLiveTest):
    """Full gate flow: create -> blocked -> upload -> submit -> approve."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fh = login(FACULTY_EMAIL, FACULTY_PASSWORD)

    def setUp(self):
        r = self.client.post(f"{BASE}/travels/", headers=self.fh, json={
            "event_title": "P29 Gate Test Travel",
            "mobility_type": "International Conference",
            "participant_type": "Faculty",
            "college_id": 5,
            "start_date": "2026-11-01", "end_date": "2026-11-05",
            "location": "Testland", "country": "Testland",
        })
        self.assertEqual(r.status_code in (200, 201), True, r.text)
        self.travel = r.json()
        self.tid = self.travel["travel_id"]
        self._docs = []

    def tearDown(self):
        for did in self._docs:
            try:
                self.client.delete(f"{BASE}/documents/{did}", headers=self.fh)
            except Exception:
                pass
        self.client.delete(f"{BASE}/travels/{self.tid}", headers=self.fh)

    def _upload(self, doc_type: str) -> int:
        files = {"file": ("gate_test_doc.pdf", io.BytesIO(PDF), "application/pdf")}
        r = self.client.post(f"{BASE}/documents/upload", headers=self.fh,
                             params={"travel_id": self.tid, "doc_type": doc_type},
                             files=files)
        self.assertIn(r.status_code, (200, 201), r.text)
        did = r.json()["document_id"]
        self._docs.append(did)
        return did

    def _upload_all_required(self):
        for name in FACULTY_PRE_REQUIRED:
            self._upload(name)

    # ---- tests (ordered by method name) ----

    def test_a_new_travel_starts_pending_requirements(self):
        self.assertEqual(self.travel["workflow_status"], "Pending Requirements")

    def test_b_submit_blocked_when_incomplete(self):
        r = self.client.post(f"{BASE}/travels/{self.tid}/submit-for-approval",
                             headers=self.fh)
        self.assertEqual(r.status_code, 422, r.text)
        detail = r.json()["detail"]
        self.assertIn("missing", detail)
        self.assertEqual(len(detail["missing"]), len(FACULTY_PRE_REQUIRED))
        self.assertEqual(detail["missing"][0], "Letter of Intent")
        # still pending
        r2 = self.client.get(f"{BASE}/travels/{self.tid}", headers=self.fh)
        self.assertEqual(r2.json()["workflow_status"], "Pending Requirements")

    def test_c_non_owner_cannot_submit(self):
        other = login(OTHER_FACULTY_EMAIL, OTHER_PW)
        r = self.client.post(f"{BASE}/travels/{self.tid}/submit-for-approval",
                             headers=other)
        self.assertEqual(r.status_code, 403, r.text)

    def test_d_admin_approve_blocked_while_incomplete(self):
        # advance to Under Review via the (gate-free) transitions
        for target in ("Submitted", "Under Review"):
            r = self.client.patch(f"{BASE}/travels/{self.tid}/workflow",
                                  headers=self.admin,
                                  json={"workflow_status": target})
            self.assertEqual(r.status_code, 200, r.text)
        r = self.client.patch(f"{BASE}/travels/{self.tid}/workflow",
                              headers=self.admin,
                              json={"workflow_status": "Approved"})
        self.assertEqual(r.status_code, 422, r.text)
        detail = r.json()["detail"]
        self.assertIn("missing", detail)
        self.assertEqual(len(detail["missing"]), len(FACULTY_PRE_REQUIRED))

    def test_e_direct_pending_to_approved_rejected(self):
        r = self.client.patch(f"{BASE}/travels/{self.tid}/workflow",
                              headers=self.admin,
                              json={"workflow_status": "Approved"})
        self.assertEqual(r.status_code, 400, r.text)

    def test_f_full_flow_upload_submit_approve(self):
        # submit while incomplete still blocked (sanity inside full flow)
        r = self.client.post(f"{BASE}/travels/{self.tid}/submit-for-approval",
                             headers=self.fh)
        self.assertEqual(r.status_code, 422, r.text)

        self._upload_all_required()

        r = self.client.post(f"{BASE}/travels/{self.tid}/submit-for-approval",
                             headers=self.fh)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["workflow_status"], "Submitted")
        self.assertEqual(body["pre_travel_status"], "Complete Documents")

        r = self.client.patch(f"{BASE}/travels/{self.tid}/workflow",
                              headers=self.admin,
                              json={"workflow_status": "Under Review"})
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.patch(f"{BASE}/travels/{self.tid}/workflow",
                              headers=self.admin,
                              json={"workflow_status": "Approved"})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.get(f"{BASE}/travels/{self.tid}", headers=self.admin)
        self.assertEqual(r.json()["workflow_status"], "Approved")

    def test_g_rejected_doc_does_not_satisfy_gate(self):
        did = self._upload("Letter of Intent")
        # admin rejects the document
        r = self.client.patch(f"{BASE}/documents/{did}/status",
                              headers=self.admin,
                              json={"status": "Rejected", "remarks": "test"})
        self.assertEqual(r.status_code, 200, r.text)

        r = self.client.post(f"{BASE}/travels/{self.tid}/submit-for-approval",
                             headers=self.fh)
        self.assertEqual(r.status_code, 422, r.text)
        self.assertIn("Letter of Intent", r.json()["detail"]["missing"])


if __name__ == "__main__":
    unittest.main()
