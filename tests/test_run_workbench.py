import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_workbench as runner  # noqa: E402


class MonthlyWindowTests(unittest.TestCase):
    def test_window_contains_1830_through_1839(self):
        timezone = ZoneInfo("Asia/Shanghai")
        self.assertTrue(
            runner.is_monthly_window(dt.datetime(2026, 9, 16, 18, 30, tzinfo=timezone))
        )
        self.assertTrue(
            runner.is_monthly_window(
                dt.datetime(2026, 9, 16, 18, 39, 59, tzinfo=timezone)
            )
        )

    def test_window_excludes_adjacent_minutes(self):
        timezone = ZoneInfo("Asia/Shanghai")
        self.assertFalse(
            runner.is_monthly_window(dt.datetime(2026, 9, 16, 18, 29, tzinfo=timezone))
        )
        self.assertFalse(
            runner.is_monthly_window(dt.datetime(2026, 9, 16, 18, 40, tzinfo=timezone))
        )


class PendingTests(unittest.TestCase):
    def test_pending_covers_today_and_snapshot(self):
        self.assertTrue(runner.has_pending_publish({"pendingToday": True}))
        self.assertTrue(runner.has_pending_publish({"pendingSnapshot": True}))
        self.assertFalse(runner.has_pending_publish({}))


class CommandTests(unittest.TestCase):
    def test_full_mode_forces_today_sync(self):
        self.assertEqual(
            runner.sync_today_arguments(force=True),
            ["scripts/sync_today.py", "--force"],
        )

    def test_default_mode_does_not_force_today_sync(self):
        self.assertEqual(
            runner.sync_today_arguments(force=False),
            ["scripts/sync_today.py"],
        )


if __name__ == "__main__":
    unittest.main()
