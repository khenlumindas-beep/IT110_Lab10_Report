"""
Phase 9 — AI evaluation tests.

Evaluates the Phase 7/8 heuristic engines against expected outcomes:
classification accuracy, extraction correctness, issue-detection flags,
remark quality and insight generation (FR-AI01..AI06). Pure-function tests
run without a server; live-API tests are skipped when the server is down.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_engine
import ai_monitor

from tests.base import AdminLiveTest, BASE

_TYPES = [
    "Invitation Letter", "Travel Authority", "Passport Copy",
    "Proof of Funding", "Program/Conference Information",
    "Certificate of Participation", "Travel Report", "Proof of Attendance",
    "Re-entry Activity Report", "Re-entry Evidence/MOV",
]


class TestClassification(unittest.TestCase):
    """FR-AI01: document type suggestions from filename signals."""

    def test_matching_filename_high_confidence(self):
        r = ai_engine.analyze("invitation_letter.pdf", 50_000,
                              "Invitation Letter", _TYPES)
        self.assertEqual(r["suggested_type"], "Invitation Letter")
        self.assertGreaterEqual(r["confidence"], 0.7)
        self.assertNotIn("type_mismatch", r["issue_flags"] or "")

    def test_mismatch_detected(self):
        r = ai_engine.analyze("travel_authority_signed.pdf", 200_000,
                              "Invitation Letter", _TYPES)
        self.assertEqual(r["suggested_type"], "Travel Authority")
        self.assertIn("type_mismatch", r["issue_flags"] or "")

    def test_certificate_recognized(self):
        r = ai_engine.analyze("certificate_of_participation_scan.jpg", 90_000,
                              "Certificate of Participation", _TYPES)
        self.assertEqual(r["suggested_type"], "Certificate of Participation")

    def test_passport_recognized(self):
        r = ai_engine.analyze("my_passport_copy.png", 300_000,
                              "Passport Copy", _TYPES)
        self.assertEqual(r["suggested_type"], "Passport Copy")

    def test_travel_report_recognized(self):
        r = ai_engine.analyze("final_travel_report_2026.pdf", 120_000,
                              "Travel Report", _TYPES)
        self.assertEqual(r["suggested_type"], "Travel Report")

    def test_confidence_bounded(self):
        r = ai_engine.analyze("x.pdf", 100, "Invitation Letter", _TYPES)
        self.assertGreaterEqual(r["confidence"], 0.0)
        self.assertLessEqual(r["confidence"], 0.99)
        self.assertEqual(r["status"], "complete")


class TestExtraction(unittest.TestCase):
    """FR-AI02: field extraction from filename/file attributes."""

    def test_date_extracted(self):
        f = ai_engine.extract_fields("travel_report_2026-03-15.pdf", 100_000)
        self.assertEqual(f["date"], "2026-03-15")

    def test_compact_date_extracted(self):
        f = ai_engine.extract_fields("scan_20260315_report.pdf", 50_000)
        self.assertEqual(f["date"], "2026-03-15")

    def test_size_class(self):
        self.assertEqual(ai_engine.extract_fields("a.pdf", 500)["size_class"],
                         "very_small")
        self.assertEqual(ai_engine.extract_fields("a.pdf", 20_000)["size_class"],
                         "small")
        self.assertEqual(ai_engine.extract_fields("a.pdf", 200_000)["size_class"],
                         "medium")
        self.assertEqual(ai_engine.extract_fields("a.pdf", 9_000_000)["size_class"],
                         "large")

    def test_extension_extracted(self):
        f = ai_engine.extract_fields("doc.PDF", 100)
        self.assertEqual(f["extension"], "pdf")


class TestIssueDetection(unittest.TestCase):
    """FR-AI03: potential issue flags."""

    def _flags(self, name, size, declared="Travel Report"):
        return ai_engine.analyze(name, size, declared, _TYPES)["issue_flags"] or ""

    def test_placeholder_flagged(self):
        self.assertIn("placeholder_file", self._flags("report.pdf", 500))

    def test_generic_filename_flagged(self):
        self.assertIn("filename_generic", self._flags("IMG_0001.png", 200_000))

    def test_unsupported_extension_flagged(self):
        self.assertIn("unsupported_extension", self._flags("report.txt", 200_000))

    def test_draft_flagged(self):
        self.assertIn("possibly_unsigned", self._flags("draft_report.pdf", 200_000))

    def test_clean_file_no_flags(self):
        flags = self._flags("final_travel_report_2026-03-15.pdf", 200_000)
        for bad in ("placeholder_file", "filename_generic", "unsupported_extension"):
            self.assertNotIn(bad, flags)

    def test_oversized_flagged(self):
        self.assertIn("oversized", self._flags("report.pdf", 6_000_000))


class TestRemarkHeuristics(unittest.TestCase):
    """FR-AI06 quality: remarks are structured and reference real issues."""

    def test_engine_functions_exist(self):
        self.assertTrue(callable(ai_monitor.build_remark))
        self.assertTrue(callable(ai_monitor.build_insights))
        self.assertTrue(callable(ai_monitor.refresh_insights))

    def test_insight_dict_shape(self):
        class _Row:
            insight_id = 1
            travel_id = 2
            insight_type = "compliance_summary"
            summary = "s"
            priority = "medium"
            suggested_remark = "r"
            is_accepted = None
            created_at = None
        d = ai_monitor.insight_dict(_Row)
        for key in ("insight_id", "travel_id", "insight_type", "summary",
                    "priority", "suggested_remark", "is_accepted", "created_at"):
            self.assertIn(key, d)


class TestLiveAIEvaluation(AdminLiveTest):
    """Live checks: insights/remarks produced for real data stay well-formed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from tests.base import login, FACULTY_EMAIL, FACULTY_PASSWORD
        cls.fh = login(FACULTY_EMAIL, FACULTY_PASSWORD)

    def test_insights_have_valid_enums(self):
        r = self.client.get(f"{BASE}/ai/insights", headers=self.admin,
                            params={"limit": 50})
        self.assertEqual(r.status_code, 200)
        for ins in r.json():
            self.assertIn(ins["priority"], (None, "low", "medium", "high"))
            self.assertIn(ins["insight_type"],
                          ("compliance_summary", "priority", "document_issue",
                           "suggested_remark"))

    def test_suggest_remark_quality(self):
        travels = self.client.get(f"{BASE}/travels/", headers=self.fh,
                                  params={"limit": 1}).json()
        self.assertTrue(travels)
        r = self.client.post(f"{BASE}/ai/suggest-remark", headers=self.fh,
                             json={"travel_id": travels[0]["travel_id"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn(body["priority"], ("low", "medium", "high"))
        if body["remark"] is not None:
            # remarks must be structured and actionable
            self.assertTrue(body["remark"].startswith("[AI suggested]"))
            self.assertIn("Please address", body["remark"])
            self.assertIsInstance(body["issues"], list)

    def test_document_analysis_end_to_end(self):
        docs = self.client.get(f"{BASE}/documents/user/all", headers=self.fh).json()
        self.assertTrue(docs)
        r = self.client.post(f"{BASE}/ai/document-analysis", headers=self.fh,
                             json={"document_id": docs[0]["document_id"]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "complete")
        self.assertIsNotNone(body["suggested_type"])
        # extracted_text is a semicolon-joined field summary
        self.assertIn("extension=", body["extracted_text"])


if __name__ == "__main__":
    unittest.main()
