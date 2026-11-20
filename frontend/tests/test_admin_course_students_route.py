import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TMP_CONFIG_DIR = Path(tempfile.mkdtemp(prefix="pregrader_test_config_"))

import os

os.environ["PREGRADER_CONFIG_DIR"] = str(_TMP_CONFIG_DIR)

sys.path.insert(0, str(Path(__file__).parents[1]))

import auth  # noqa: E402  (import after setting PREGRADER_CONFIG_DIR)
import app as flask_app  # noqa: E402


class AdminCourseStudentsRouteTests(unittest.TestCase):
    """Cubre la ruta de solo lectura GET /admin/api/courses/<id>/students."""

    @classmethod
    def setUpClass(cls):
        auth.init_db()
        auth.create_user("admin_ro_test", "Passw0rd!123", is_admin=True)
        cls.course_id = auth.create_course(
            "Curso Solo Lectura",
            "admin_ro_test",
            [
                {"name": "Perez, Juan", "username": "jperez", "org_id": "111"},
                {"name": "Gomez, Ana", "username": "agomez", "org_id": "222"},
            ],
            course_type="ip",
        )
        cls.client = flask_app.app.test_client()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP_CONFIG_DIR, ignore_errors=True)

    def _admin_client(self):
        with self.client.session_transaction() as sess:
            sess["user"] = "admin_ro_test"
        return self.client

    def test_requires_authentication(self):
        anon_client = flask_app.app.test_client()
        r = anon_client.get(f"/admin/api/courses/{self.course_id}/students")
        self.assertEqual(r.status_code, 401)

    def test_lists_registered_students_readonly(self):
        client = self._admin_client()
        r = client.get(f"/admin/api/courses/{self.course_id}/students")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["course"]["id"], self.course_id)
        names = sorted(s["full_name"] for s in data["students"])
        self.assertEqual(names, ["Gomez, Ana", "Perez, Juan"])
        # GET nunca debe alterar el roster.
        roster_after = auth.get_course_students(self.course_id)
        self.assertEqual(len(roster_after), 2)

    def test_unknown_course_returns_404(self):
        client = self._admin_client()
        r = client.get("/admin/api/courses/999999/students")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])


class HostAccessTests(unittest.TestCase):
    def setUp(self):
        config = patch.dict(
            flask_app.app.config,
            {"TRUSTED_HOSTS": ["pregrader.x7company.com"]},
        )
        config.start()
        self.addCleanup(config.stop)
        self.client = flask_app.app.test_client()

    def test_public_host_serves_login(self):
        response = self.client.get("/login", base_url="https://pregrader.x7company.com")
        self.assertEqual(response.status_code, 200)

    def test_azure_hosts_cannot_access_login_api_or_static_files(self):
        for host in (
            "academic-pregrader-prod.yellowcliff-66c52a32.eastus.azurecontainerapps.io",
            "academic-pregrader-prod--0000054.yellowcliff-66c52a32.eastus.azurecontainerapps.io",
        ):
            for path, method in (
                ("/login", "GET"),
                ("/login", "POST"),
                ("/admin/api/courses/1/students", "GET"),
                ("/static/css/base.css", "GET"),
            ):
                with self.subTest(host=host, path=path, method=method):
                    response = self.client.open(path, method=method, base_url=f"https://{host}")
                    self.assertEqual(response.status_code, 400)

    def test_forwarded_host_does_not_allow_the_old_url(self):
        response = self.client.get(
            "/login",
            base_url="https://academic-pregrader-prod.yellowcliff-66c52a32.eastus.azurecontainerapps.io",
            headers={"X-Forwarded-Host": "pregrader.x7company.com"},
        )
        self.assertEqual(response.status_code, 400)

    def test_local_development_is_available_without_restriction(self):
        with patch.dict(flask_app.app.config, {"TRUSTED_HOSTS": None}):
            response = self.client.get("/login", base_url="http://localhost:5000")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
