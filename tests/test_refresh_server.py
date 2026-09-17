import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh_server  # noqa: E402


class OriginTests(unittest.TestCase):
    def test_allows_workbench_and_local_development_origins(self):
        self.assertTrue(
            refresh_server.allowed_origin(
                "https://fbmv76z724-eng.github.io"
            )
        )
        self.assertTrue(refresh_server.allowed_origin("http://127.0.0.1:4173"))
        self.assertTrue(refresh_server.allowed_origin("http://localhost:4173"))
        self.assertFalse(refresh_server.allowed_origin("https://example.com"))


class RefreshJobTests(unittest.TestCase):
    def test_runs_job_and_records_success(self):
        finished = threading.Event()

        def runner():
            finished.set()
            return subprocess.CompletedProcess(
                args=["refresh"],
                returncode=0,
                stdout='{"ok": true}\n',
                stderr="",
            )

        job = refresh_server.RefreshJob(runner=runner)
        state = job.start()
        self.assertIn(state["status"], {"running", "success"})
        self.assertTrue(finished.wait(timeout=2))

        deadline = time.monotonic() + 2
        while job.snapshot()["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
        state = job.snapshot()
        self.assertEqual(state["status"], "success")
        self.assertIn('"ok": true', state["message"])

    def test_running_job_is_not_started_twice(self):
        release = threading.Event()

        def runner():
            release.wait(timeout=2)
            return subprocess.CompletedProcess(
                args=["refresh"],
                returncode=0,
                stdout="",
                stderr="",
            )

        job = refresh_server.RefreshJob(runner=runner)
        first = job.start()
        second = job.start()
        self.assertEqual(first["status"], "running")
        self.assertEqual(second["status"], "running")
        self.assertEqual(first["startedAt"], second["startedAt"])
        release.set()

    def test_recovery_alert_counts_as_success(self):
        result = subprocess.CompletedProcess(
            args=["refresh"],
            returncode=1,
            stdout="",
            stderr="ALERT: 推广工作台已恢复（此前失败：today_sync）",
        )
        self.assertTrue(refresh_server.refresh_result_succeeded(result))


if __name__ == "__main__":
    unittest.main()
