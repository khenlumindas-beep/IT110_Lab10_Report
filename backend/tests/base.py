"""
SmartTrack Phase 9 — shared helpers for the live-API test suite.

Run from the backend/ directory:

    python -m unittest discover -s tests -t . -v

Tests exercise the running server (default http://127.0.0.1:5000). If the
server is down the live-API test classes are skipped; pure-function tests
(engine evaluations) still run.
"""
import os
import unittest

import httpx

BASE = os.environ.get("SMARTTRACK_API", "http://127.0.0.1:5000/api")

ADMIN_EMAIL = os.environ.get("SMARTTRACK_ADMIN_EMAIL", "oige@csucc.edu.ph")
ADMIN_PASSWORD = os.environ.get("SMARTTRACK_ADMIN_PASSWORD", "AdminPass123!")
FACULTY_EMAIL = os.environ.get("SMARTTRACK_FACULTY_EMAIL", "jpayla@csucc.edu.ph")
FACULTY_PASSWORD = os.environ.get("SMARTTRACK_FACULTY_PASSWORD", "FacultyPass123!")
OTHER_FACULTY_EMAIL = os.environ.get("SMARTTRACK_OTHER_FACULTY_EMAIL", "rlmariscal@csucc.edu.ph")


def server_up() -> bool:
    try:
        r = httpx.get(f"{BASE}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def login(email: str, password: str) -> dict:
    r = httpx.post(f"{BASE}/auth/login", json={"email": email, "password": password},
                   timeout=15)
    r.raise_for_status()
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class LiveAPITest(unittest.TestCase):
    """Base class: skips the whole class when the API server is not running."""

    @classmethod
    def setUpClass(cls):
        if not server_up():
            raise unittest.SkipTest(
                f"API server not reachable at {BASE} — start uvicorn to run live tests")
        cls.client = httpx.Client(timeout=30)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "client"):
            cls.client.close()


class AdminLiveTest(LiveAPITest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = login(ADMIN_EMAIL, ADMIN_PASSWORD)


class FacultyLiveTest(LiveAPITest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.faculty = login(FACULTY_EMAIL, FACULTY_PASSWORD)
