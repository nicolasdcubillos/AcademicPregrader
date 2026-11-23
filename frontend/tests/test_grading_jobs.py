import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch


_CONFIG = tempfile.TemporaryDirectory(prefix="pregrader_job_tests_")
os.environ["PREGRADER_CONFIG_DIR"] = _CONFIG.name
sys.path.insert(0, str(Path(__file__).parents[1]))
import app as flask_app


class GradingJobTests(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.app.test_client()
        with self.client.session_transaction() as session:
            session["user"] = "grading_job_test"
        user = patch.object(flask_app.auth, "get_user", return_value={
            "must_change_password": False, "is_blocked": False,
        })
        user.start()
        self.addCleanup(user.stop)
        events = patch.object(flask_app.auth, "log_event")
        events.start()
        self.addCleanup(events.stop)
        activity = patch.object(flask_app.auth, "touch_last_seen")
        activity.start()
        self.addCleanup(activity.stop)
        self.addCleanup(flask_app._active_jobs.clear)

    def test_second_request_is_rejected_even_before_process_start(self):
        with patch.object(flask_app, "_start_pregrader", return_value=flask_app.app.response_class(
            '{"job_id":"reserved"}', mimetype="application/json",
        )) as start:
            first = self.client.post("/run")
            second = self.client.post("/run")
        self.assertEqual(200, first.status_code)
        self.assertEqual(409, second.status_code)
        start.assert_called_once()
        self.assertIn("evaluación en curso", second.get_json()["error"])

    def test_failed_upload_and_setup_release_reservation(self):
        self.assertEqual(400, self.client.post("/run").status_code)
        self.assertEqual({}, flask_app._active_jobs)
        with patch.object(flask_app, "_start_pregrader", side_effect=RuntimeError("setup failed")), \
             patch.dict(flask_app.app.config, {"TESTING": True}):
            with self.assertRaisesRegex(RuntimeError, "setup failed"):
                self.client.post("/run")
        self.assertEqual({}, flask_app._active_jobs)

    def run_worker(self, lines, returncode):
        finished = Event()
        processes = []

        class FakeProcess:
            def __init__(self, *args, **kwargs):
                self.stdout = io.StringIO("\n".join(lines) + "\n")
                processes.append(self)

            def wait(self):
                return returncode

        class ImmediateThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()
                finished.set()

        job_config = tempfile.mkdtemp(prefix="pregrader_job_config_test_")
        with patch.object(flask_app.subprocess, "Popen", FakeProcess), \
             patch.object(flask_app.threading, "Thread", ImmediateThread), \
             patch.object(flask_app, "PdfReader"), \
             patch.object(flask_app, "build_job_config_dir", return_value=job_config), \
             patch.object(flask_app.auth, "save_grading_history"):
            response = self.client.post("/run", data={
                "zip_file": (io.BytesIO(b"zip"), "submissions.zip"),
                "enunciado_text": "Assignment",
            })
        self.assertTrue(finished.is_set())
        self.assertEqual(200, response.status_code)
        job_id = response.get_json()["job_id"]
        queue = flask_app._queues.pop(job_id)
        messages = []
        while not queue.empty():
            message = queue.get_nowait()
            if message is not None:
                messages.append(message)
        flask_app._results.pop(job_id, None)
        flask_app._job_statements.pop(job_id, None)
        self.assertFalse(Path(job_config).exists())
        self.assertEqual({}, flask_app._active_jobs)
        return messages

    def test_failed_or_incomplete_process_never_reports_success(self):
        for lines, code in (
            (["Traceback: process failed"], 1),
            (["Early return"], 0),
            (['##STUDENTS## ["student"]', '##DONE## {"count": 0}'], 0),
        ):
            with self.subTest(lines=lines):
                messages = self.run_worker(lines, code)
                self.assertIn("error", [m["type"] for m in messages])
                self.assertNotIn("done", [m["type"] for m in messages])

    def test_done_event_preserves_error_counts_and_blank_grade(self):
        error = {
            "estudiante": "student", "estado": "error", "nota": "",
            "compila": "N/A", "plagio": "", "comentario": "Unsupported PNG", "codigo": "",
        }
        messages = self.run_worker([
            '##STUDENTS## ["student"]',
            "##RESULT## " + json.dumps(error),
            '##DONE## {"count": 1, "total": 1, "failed": 1}',
        ], 0)
        done = next(m for m in messages if m["type"] == "done")
        self.assertEqual(1, done["failed"])
        self.assertEqual(1, done["total"])
        result = next(m["data"] for m in messages if m["type"] == "student_result")
        self.assertEqual("", result["nota"])


if __name__ == "__main__":
    unittest.main()
