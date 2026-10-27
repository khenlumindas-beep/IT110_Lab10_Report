"""
Super-admin guard tests (UbeDelights-style) — live API.

Covers: role whitelist on create, max-2 active super admin cap, update
field whitelist, no self-deactivation, guarded role change with
transfer-blocking, reactivation cap, and forced logout of deactivated
accounts.
"""
import unittest
import uuid

from tests.base import AdminLiveTest, BASE, login


def _unique(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestSuperAdminGuards(AdminLiveTest):
    """UbeDelights-derived super admin rules on user management."""

    # ---------- create ----------

    def test_create_rejects_invalid_role(self):
        r = self.client.post(
            f"{BASE}/users/",
            headers=self.admin,
            json={
                "full_name": "Guard Test",
                "email": f"{_unique('guard')}@csucc.edu.ph",
                "password": "TestPass123!",
                "role": "hacker",
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn("Invalid role", r.json()["detail"])

    def test_create_super_admin_respects_cap(self):
        users = self.client.get(f"{BASE}/users/", headers=self.admin).json()
        active_sa = [u for u in users
                     if u["role"] == "super_admin" and u["is_active"]]
        email = f"{_unique('guard_sa')}@csucc.edu.ph"
        r = self.client.post(
            f"{BASE}/users/",
            headers=self.admin,
            json={
                "full_name": "Guard SA",
                "email": email,
                "password": "TestPass123!",
                "role": "super_admin",
            })
        if len(active_sa) >= 2:
            self.assertEqual(r.status_code, 400)
            self.assertIn("Maximum of 2", r.json()["detail"])
        else:
            self.assertEqual(r.status_code, 200)
            # cleanup: deactivate the created super admin again
            created_id = r.json()["user_id"]
            self.client.delete(f"{BASE}/users/{created_id}", headers=self.admin)

    # ---------- update whitelist ----------

    def test_update_cannot_change_role_or_active(self):
        r = self.client.post(
            f"{BASE}/users/",
            headers=self.admin,
            json={
                "full_name": "Guard Update",
                "email": f"{_unique('guard_up')}@csucc.edu.ph",
                "password": "TestPass123!",
                "role": "faculty",
            })
        self.assertEqual(r.status_code, 200)
        uid = r.json()["user_id"]
        try:
            r2 = self.client.put(
                f"{BASE}/users/{uid}",
                headers=self.admin,
                json={"full_name": "Guard Update Renamed",
                      "role": "super_admin",
                      "is_active": False,
                      "password_hash": "pwned"})
            self.assertEqual(r2.status_code, 200)
            after = self.client.get(f"{BASE}/users/{uid}",
                                    headers=self.admin).json()
            self.assertEqual(after["full_name"], "Guard Update Renamed")
            self.assertEqual(after["role"], "faculty")      # unchanged
            self.assertTrue(after["is_active"])             # unchanged
            self.assertNotEqual(after.get("password_hash", ""), "pwned")
        finally:
            self.client.delete(f"{BASE}/users/{uid}", headers=self.admin)

    # ---------- deactivate ----------

    def test_cannot_deactivate_self(self):
        users = self.client.get(f"{BASE}/users/", headers=self.admin).json()
        me = next(u for u in users if u["email"].lower() == "oige@csucc.edu.ph")
        r = self.client.delete(f"{BASE}/users/{me['user_id']}",
                               headers=self.admin)
        self.assertEqual(r.status_code, 400)
        self.assertIn("your own account", r.json()["detail"])

    def test_deactivated_user_is_logged_out(self):
        r = self.client.post(
            f"{BASE}/users/",
            headers=self.admin,
            json={
                "full_name": "Guard Logout",
                "email": f"{_unique('guard_lo')}@csucc.edu.ph",
                "password": "TestPass123!",
                "role": "faculty",
            })
        self.assertEqual(r.status_code, 200)
        uid = r.json()["user_id"]
        email = r.json()["email"]
        victim = login(email, "TestPass123!")
        # token works while active
        me = self.client.get(f"{BASE}/auth/me", headers=victim)
        self.assertEqual(me.status_code, 200)
        # deactivate -> same token must be rejected immediately
        d = self.client.delete(f"{BASE}/users/{uid}", headers=self.admin)
        self.assertEqual(d.status_code, 200)
        me2 = self.client.get(f"{BASE}/auth/me", headers=victim)
        self.assertEqual(me2.status_code, 401)
        # cleanup: purge is not exposed; account stays deactivated

    # ---------- role change ----------

    def test_cannot_change_own_role(self):
        users = self.client.get(f"{BASE}/users/", headers=self.admin).json()
        me = next(u for u in users if u["email"].lower() == "oige@csucc.edu.ph")
        r = self.client.post(f"{BASE}/users/{me['user_id']}/role",
                             headers=self.admin, json={"role": "faculty"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("your own role", r.json()["detail"])

    def test_role_change_blocks_account(self):
        r = self.client.post(
            f"{BASE}/users/",
            headers=self.admin,
            json={
                "full_name": "Guard Role",
                "email": f"{_unique('guard_rl')}@csucc.edu.ph",
                "password": "TestPass123!",
                "role": "faculty",
            })
        self.assertEqual(r.status_code, 200)
        uid = r.json()["user_id"]
        # demote-style change: faculty -> faculty is a no-op message
        same = self.client.post(f"{BASE}/users/{uid}/role",
                                headers=self.admin, json={"role": "faculty"})
        self.assertEqual(same.status_code, 200)
        # invalid role rejected
        bad = self.client.post(f"{BASE}/users/{uid}/role",
                               headers=self.admin, json={"role": "root"})
        self.assertEqual(bad.status_code, 400)
        # promote (may hit the max-2 cap)
        users = self.client.get(f"{BASE}/users/", headers=self.admin).json()
        active_sa = [u for u in users
                     if u["role"] == "super_admin" and u["is_active"]]
        promo = self.client.post(f"{BASE}/users/{uid}/role",
                                 headers=self.admin,
                                 json={"role": "super_admin"})
        if len(active_sa) >= 2:
            self.assertEqual(promo.status_code, 400)
            self.assertIn("Maximum of 2", promo.json()["detail"])
        else:
            self.assertEqual(promo.status_code, 200)
            after = self.client.get(f"{BASE}/users/{uid}",
                                    headers=self.admin).json()
            self.assertEqual(after["role"], "super_admin")
            self.assertFalse(after["is_active"])  # blocked pending reactivation
            # With only one active SA (us), reactivating this second SA is
            # allowed and fills the cap of 2. A third active SA would then be
            # refused (covered by the create/promote cap tests).
            re1 = self.client.post(f"{BASE}/users/{uid}/reactivate",
                                   headers=self.admin)
            self.assertEqual(re1.status_code, 200)
            # demote first, then reactivate as faculty — allowed
            demote = self.client.post(f"{BASE}/users/{uid}/role",
                                      headers=self.admin,
                                      json={"role": "faculty"})
            self.assertEqual(demote.status_code, 200)
            re2 = self.client.post(f"{BASE}/users/{uid}/reactivate",
                                   headers=self.admin)
            self.assertEqual(re2.status_code, 200)
        # cleanup
        self.client.delete(f"{BASE}/users/{uid}", headers=self.admin)

    def test_reactivate_missing_user_404(self):
        r = self.client.post(f"{BASE}/users/999999/reactivate",
                             headers=self.admin)
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
