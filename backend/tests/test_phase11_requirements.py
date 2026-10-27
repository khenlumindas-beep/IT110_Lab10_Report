"""
Phase 11: Requirement checklists — official OIGE PDFs as master data,
per-travel completeness tracking, downloadable templates (incl. Re-Entry Plan).
"""
import os
import unittest

from tests.base import (
    BASE, AdminLiveTest, FacultyLiveTest, LiveAPITest, login,
    OTHER_FACULTY_EMAIL, FACULTY_PASSWORD,
)


class TestRequirementMaster(AdminLiveTest):
    def test_master_list_seeded_from_checklists(self):
        r = self.client.get(f"{BASE}/requirements/", headers=self.admin)
        self.assertEqual(r.status_code, 200)
        items = r.json()
        self.assertGreaterEqual(len(items), 70, "migration_011 should seed ~78 items")
        names = {i["name"] for i in items}
        self.assertIn("Re-Entry Action Plan", names)
        self.assertIn("CHED IAS Assessment", names)
        self.assertIn("IZN Student Screening Committee Referendum", names)
        fac_pre = [i for i in items
                   if i["applies_to"] == "Faculty" and i["phase"] == "Pre-Travel"]
        children = [i for i in fac_pre if i["parent_id"] is not None]
        self.assertGreaterEqual(len(children), 10, "CHED IAS a-j sub-items")
        self.assertEqual(len(fac_pre), 26)

    def test_requires_auth(self):
        r = self.client.get(f"{BASE}/requirements/")
        self.assertEqual(r.status_code, 401)

    def test_faculty_post_document_display(self):
        """Migration 012: PDF-verbatim display_text + CHED IAS a-j children."""
        r = self.client.get(
            f"{BASE}/requirements/?applies_to=Faculty&phase=Post-Travel",
            headers=self.admin)
        self.assertEqual(r.status_code, 200)
        items = r.json()
        parents = [i for i in items if i["parent_id"] is None]
        children = [i for i in items if i["parent_id"] is not None]
        self.assertEqual(len(parents), 23, "official PDF has 23 numbered items")
        self.assertGreaterEqual(len(children), 10, "CHED IAS a-j sub-items")
        self.assertTrue(all(i["display_text"] for i in parents),
                        "every numbered item needs PDF-verbatim display_text")
        loi = next(i for i in parents if i["name"] == "Letter of Intent")
        self.assertEqual(loi["display_text"], "Approved Letter of Intent")
        ched = next(i for i in parents if i["name"] == "CHED IAS Assessment")
        ched_kids = [i for i in children
                     if i["parent_id"] == ched["requirement_id"]]
        self.assertEqual(len(ched_kids), 10, "CHED IAS children a-j")
        self.assertTrue(all(i["display_text"] for i in ched_kids))


class TestTravelRequirements(FacultyLiveTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        r = cls.client.get(f"{BASE}/travels/", headers=cls.faculty)
        r.raise_for_status()
        cls.travels = r.json()
        assert cls.travels, "faculty fixture needs at least one travel"

    def test_status_shape_and_template_flag(self):
        tid = self.travels[0]["travel_id"]
        r = self.client.get(f"{BASE}/requirements/travel/{tid}",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["participant_type"], "Faculty")
        self.assertGreater(len(d["items"]), 40)  # 26 pre + 33 post
        names = {i["name"] for i in d["items"]}
        self.assertIn("Re-Entry Action Plan", names)
        self.assertIn("faculty_pre_checklist", d["checklist_files"])
        post = [i for i in d["items"] if i["phase"] == "Post-Travel"]
        post_parents = [i for i in post if i["parent_id"] is None]
        self.assertEqual(len(post_parents), 23)
        self.assertTrue(all(i["display_text"] for i in post_parents),
                        "travel payload must carry display_text for doc format")
        ra = [i for i in d["items"] if i["name"] == "Re-Entry Action Plan"]
        self.assertTrue(all(i["has_template"] and i["template_key"] == "reentry_plan"
                            for i in ra))
        # summary math: verified + still-open == required_total
        required = [i for i in d["items"]
                    if i["is_required"] and i["parent_id"] is None]
        self.assertEqual(len(required), d["required_total"])
        verified = len([i for i in required if i["status"] == "Verified"])
        self.assertEqual(verified, d["verified_required"])

    def test_matching_document_flips_status(self):
        """A Verified doc whose doc_type equals the requirement name counts."""
        tid = self.travels[0]["travel_id"]
        # upload under a checklist name, then check it appears as Submitted
        files = {"file": ("req_match.pdf", b"%PDF-1.4 test", "application/pdf")}
        r = self.client.post(
            f"{BASE}/documents/upload?travel_id={tid}"
            f"&doc_type=Certificate%20of%20Employment&doc_category=Pre-Travel",
            files=files, headers=self.faculty)
        self.assertEqual(r.status_code, 200, r.text)
        r2 = self.client.get(f"{BASE}/requirements/travel/{tid}",
                             headers=self.faculty)
        item = next(i for i in r2.json()["items"]
                    if i["name"] == "Certificate of Employment"
                    and i["phase"] == "Pre-Travel")
        self.assertEqual(item["status"], "Submitted")
        self.assertIsNotNone(item["document_id"])

    def test_other_faculty_forbidden(self):
        tid = self.travels[0]["travel_id"]
        other = login(OTHER_FACULTY_EMAIL, FACULTY_PASSWORD)
        r = self.client.get(f"{BASE}/requirements/travel/{tid}", headers=other)
        self.assertEqual(r.status_code, 403)

    def test_unknown_travel_404(self):
        r = self.client.get(f"{BASE}/requirements/travel/999999",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 404)


class TestTemplates(LiveAPITest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.faculty = login("jpayla@csucc.edu.ph", "FacultyPass123!")

    def test_download_reentry_template(self):
        r = self.client.get(f"{BASE}/requirements/templates/reentry_plan",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 1000)
        self.assertIn("pdf", r.headers.get("content-type", ""))

    def test_download_all_checklist_pdfs(self):
        for key in ("faculty_pre_checklist", "faculty_post_checklist",
                    "student_post_checklist"):
            r = self.client.get(f"{BASE}/requirements/templates/{key}",
                                headers=self.faculty)
            self.assertEqual(r.status_code, 200, key)
            self.assertGreater(len(r.content), 1000, key)

    def test_query_token_download(self):
        tok = self.faculty["Authorization"].split(" ", 1)[1]
        r = self.client.get(
            f"{BASE}/requirements/templates/faculty_pre_checklist?token={tok}")
        self.assertEqual(r.status_code, 200)

    def test_unknown_template_404(self):
        r = self.client.get(f"{BASE}/requirements/templates/not_a_key",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 404)

    def test_no_auth_401(self):
        r = self.client.get(f"{BASE}/requirements/templates/reentry_plan")
        self.assertEqual(r.status_code, 401)


class TestRequirementsReport(AdminLiveTest):
    """Post-Travel requirements compliance report (admin Reports tab)."""

    def test_report_shape(self):
        r = self.client.get(
            f"{BASE}/requirements/report?applies_to=Faculty&phase=Post-Travel",
            headers=self.admin)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["applies_to"], "Faculty")
        self.assertEqual(d["phase"], "Post-Travel")
        s = d["summary"]
        for k in ("total", "complete", "incomplete", "not_started",
                  "in_progress", "avg_percent"):
            self.assertIn(k, s)
        self.assertEqual(s["total"], len(d["rows"]))
        self.assertGreaterEqual(s["total"], 1, "fixture needs a faculty travel")
        for row in d["rows"]:
            for k in ("travel_id", "event_title", "faculty_name",
                      "required_total", "verified_required", "percent",
                      "complete", "missing"):
                self.assertIn(k, row)
            self.assertEqual(
                row["verified_required"] + len(row["missing"]),
                row["required_total"])
            self.assertEqual(row["complete"],
                             row["verified_required"] == row["required_total"])
            if row["missing"]:
                self.assertTrue(all(row["missing"]),
                                "missing entries use display_text wording")

    def test_faculty_report_scoped_to_own_travels(self):
        fac = login("jpayla@csucc.edu.ph", "FacultyPass123!")
        r = self.client.get(f"{BASE}/requirements/report", headers=fac)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["summary"]["total"], len(d["rows"]))
        # compare against the faculty's own travel ids
        mine = self.client.get(f"{BASE}/travels/", headers=fac).json()
        my_ids = {t["travel_id"] for t in mine}
        row_ids = {row["travel_id"] for row in d["rows"]}
        self.assertTrue(row_ids.issubset(my_ids),
                        "faculty must only see own rows")
        for row in d["rows"]:
            self.assertEqual(row["faculty_name"], "Julieto Q. Payla")

    def test_no_auth_401(self):
        r = self.client.get(f"{BASE}/requirements/report")
        self.assertEqual(r.status_code, 401)

    def test_invalid_params_400(self):
        r = self.client.get(f"{BASE}/requirements/report?applies_to=Alien",
                            headers=self.admin)
        self.assertEqual(r.status_code, 400)

    def test_export_csv_query_token(self):
        tok = self.admin["Authorization"].split(" ", 1)[1]
        r = self.client.get(
            f"{BASE}/requirements/report/export?format=csv&token={tok}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("csv", r.headers.get("content-type", ""))
        self.assertIn("attachment",
                      r.headers.get("content-disposition", ""))
        self.assertIn("Faculty/Participant", r.text)
        self.assertIn("Missing Requirements", r.text)

    def test_export_html_printable(self):
        tok = self.admin["Authorization"].split(" ", 1)[1]
        r = self.client.get(
            f"{BASE}/requirements/report/export?format=html&token={tok}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("text/html", r.headers.get("content-type", ""))
        self.assertIn("Print / Save as PDF", r.text)
        self.assertIn("Requirements Compliance Report", r.text)

    def test_export_faculty_scoped(self):
        fac = login("jpayla@csucc.edu.ph", "FacultyPass123!")
        tok = fac["Authorization"].split(" ", 1)[1]
        r = self.client.get(
            f"{BASE}/requirements/report/export?format=csv&token={tok}")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("Faculty/Participant", r.text)
        # scoped: only the faculty's own event titles appear as data rows
        mine = self.client.get(f"{BASE}/travels/", headers=fac).json()
        self.assertTrue(any(t["event_title"] in r.text for t in mine),
                        "own travel rows must be in the CSV")

    def test_export_bad_format_400(self):
        r = self.client.get(f"{BASE}/requirements/report/export?format=xls",
                            headers=self.admin)
        self.assertEqual(r.status_code, 400)


class TestAiCheck(FacultyLiveTest):
    """AI (heuristic) requirements check: completeness + submission correctness."""

    def setUp(self):
        r = self.client.post(f"{BASE}/travels/", headers=self.faculty, json={
            "event_title": f"P14 AI Check {os.urandom(3).hex()}",
            "mobility_type": "International Conference",
            "participant_type": "Faculty",
            "college_id": 5,
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
            "location": "Test City",
            "country": "Testland",
        })
        self.assertIn(r.status_code, (200, 201), r.text)
        self.travel = r.json()
        self.doc_id = None

    def tearDown(self):
        if self.doc_id:
            self.client.delete(f"{BASE}/documents/{self.doc_id}",
                               headers=self.faculty)
        self.client.delete(f"{BASE}/travels/{self.travel['travel_id']}",
                           headers=self.faculty)

    def test_fresh_travel_incomplete_all_missing(self):
        tid = self.travel["travel_id"]
        r = self.client.get(f"{BASE}/requirements/ai-check/{tid}",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["travel_id"], tid)
        self.assertEqual(d["phase"], "Post-Travel")
        items = d["items"]
        self.assertEqual(len(items), 23, "parents only: 23 numbered items")
        s = d["summary"]
        required = [i for i in items if i["is_required"]]
        self.assertEqual(s["required_total"], len(required))
        self.assertEqual(s["missing"], s["required_total"])
        self.assertEqual(s["verdict"], "INCOMPLETE")
        self.assertEqual(s["percent"], 0.0)
        self.assertTrue(all(i["verdict"] == "missing" for i in required))
        self.assertTrue(all(i["reasons"] for i in required))
        optional = [i for i in items if not i["is_required"]]
        self.assertTrue(all(i["verdict"] == "optional_missing" for i in optional))

    def test_bad_submission_flagged_for_review(self):
        """Tiny + wrong-category file must come back needs_review with reasons."""
        tid = self.travel["travel_id"]
        files = {"file": ("scan.pdf", b"%PDF-1.4 tiny", "application/pdf")}
        r = self.client.post(
            f"{BASE}/documents/upload?travel_id={tid}"
            f"&doc_type=Certificate%20of%20Employment&doc_category=Pre-Travel",
            files=files, headers=self.faculty)
        self.assertEqual(r.status_code, 200, r.text)
        self.doc_id = r.json()["document_id"]

        r2 = self.client.get(f"{BASE}/requirements/ai-check/{tid}",
                             headers=self.faculty)
        self.assertEqual(r2.status_code, 200, r2.text)
        d = r2.json()
        coe = next(i for i in d["items"]
                   if i["name"] == "Certificate of Employment")
        self.assertEqual(coe["verdict"], "needs_review", d["summary"])
        joined = " ".join(coe["reasons"])
        self.assertIn("under 1KB", joined)
        self.assertIn("Pre-Travel", joined, "wrong phase must be flagged")
        self.assertEqual(d["summary"]["needs_review"], 1)
        self.assertEqual(d["summary"]["verdict"], "INCOMPLETE")

    def test_other_faculty_forbidden(self):
        other = login(OTHER_FACULTY_EMAIL, FACULTY_PASSWORD)
        r = self.client.get(
            f"{BASE}/requirements/ai-check/{self.travel['travel_id']}",
            headers=other)
        self.assertEqual(r.status_code, 403)

    def test_unknown_travel_404(self):
        r = self.client.get(f"{BASE}/requirements/ai-check/999999",
                            headers=self.faculty)
        self.assertEqual(r.status_code, 404)


class TestAiCheckAccess(LiveAPITest):
    def test_requires_auth(self):
        r = self.client.get(f"{BASE}/requirements/ai-check/1")
        self.assertEqual(r.status_code, 401)

    def test_admin_can_check_any_travel(self):
        admin = login("oige@csucc.edu.ph", "AdminPass123!")
        travels = self.client.get(f"{BASE}/travels/", headers=admin).json()
        self.assertTrue(travels, "seeded travels required")
        tid = travels[0]["travel_id"]
        r = self.client.get(f"{BASE}/requirements/ai-check/{tid}",
                            headers=admin)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["travel_id"], tid)
        self.assertIn(d["summary"]["verdict"],
                      ("COMPLETE", "NEEDS REVIEW", "INCOMPLETE"))


if __name__ == "__main__":
    unittest.main()
