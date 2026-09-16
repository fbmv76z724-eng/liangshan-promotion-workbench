import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_today as today  # noqa: E402


class PromotionDateTests(unittest.TestCase):
    def test_before_six_uses_previous_promotion_date(self):
        value = today.promotion_date_for("2026-09-16T05:59:00+08:00")
        self.assertEqual(value, "2026-09-15")

    def test_at_six_uses_current_promotion_date(self):
        value = today.promotion_date_for("2026-09-16T06:00:00+08:00")
        self.assertEqual(value, "2026-09-16")


class SubmittedTests(unittest.TestCase):
    def test_parses_compact_ego_browser_output(self):
        value = today.parse_submitted(
            "N=2 :: 宾二龙=二大队 ;; 黄子仁=五大队"
        )
        self.assertEqual(
            value,
            [("宾二龙", "二大队"), ("黄子仁", "五大队")],
        )


class TodaySnapshotTests(unittest.TestCase):
    def test_marks_matching_name_and_team_completed(self):
        snapshot = today.build_today_snapshot(
            business_date="2026-09-16",
            synced_at="2026-09-16T19:00:00+08:00",
            drivers=[
                {
                    "employeeId": "1",
                    "name": "宾二龙",
                    "team": "二大队",
                    "promotionCompleted": False,
                },
                {
                    "employeeId": "2",
                    "name": "黄子仁",
                    "team": "五大队",
                    "promotionCompleted": False,
                },
                {
                    "employeeId": "3",
                    "name": "黄子仁",
                    "team": "一大队",
                    "promotionCompleted": False,
                },
            ],
            submitted=[("宾二龙", "二大队")],
        )
        self.assertEqual(
            [(driver["employeeId"], driver["completed"]) for driver in snapshot["drivers"]],
            [("1", True), ("2", False), ("3", False)],
        )
        self.assertEqual(snapshot["meta"]["completedCount"], 1)
        self.assertEqual(snapshot["meta"]["unfinishedCount"], 2)

    def test_duplicate_names_in_same_team_are_both_completed(self):
        snapshot = today.build_today_snapshot(
            business_date="2026-09-16",
            synced_at="2026-09-16T19:00:00+08:00",
            drivers=[
                {
                    "employeeId": "1",
                    "name": "刘鹏",
                    "team": "二大队",
                    "promotionCompleted": False,
                },
                {
                    "employeeId": "2",
                    "name": "刘鹏",
                    "team": "二大队",
                    "promotionCompleted": False,
                },
            ],
            submitted=[("刘鹏", "二大队")],
        )
        self.assertTrue(all(driver["completed"] for driver in snapshot["drivers"]))

    def test_excludes_drivers_who_reached_two_real_transfers(self):
        snapshot = today.build_today_snapshot(
            business_date="2026-09-16",
            synced_at="2026-09-16T19:00:00+08:00",
            drivers=[
                {
                    "employeeId": "1",
                    "name": "未完成",
                    "team": "一大队",
                    "promotionCompleted": False,
                },
                {
                    "employeeId": "2",
                    "name": "已完成",
                    "team": "一大队",
                    "promotionCompleted": True,
                },
            ],
            submitted=[("已完成", "一大队")],
        )
        self.assertEqual(
            [driver["employeeId"] for driver in snapshot["drivers"]],
            ["1"],
        )
        self.assertEqual(snapshot["meta"]["driverCount"], 1)
        self.assertEqual(snapshot["meta"]["completedCount"], 0)

    def test_status_signature_ignores_sync_time(self):
        before = {
            "meta": {"businessDate": "2026-09-16", "syncedAt": "10:00"},
            "drivers": [
                {"employeeId": "1", "completed": False},
                {"employeeId": "2", "completed": True},
            ],
        }
        after = {
            "meta": {"businessDate": "2026-09-16", "syncedAt": "10:05"},
            "drivers": [
                {"employeeId": "2", "completed": True},
                {"employeeId": "1", "completed": False},
            ],
        }
        self.assertEqual(
            today.status_signature(before),
            today.status_signature(after),
        )

    def test_status_signature_changes_when_included_driver_set_changes(self):
        before = {
            "meta": {"businessDate": "2026-09-16"},
            "drivers": [{"employeeId": "1", "completed": False}],
        }
        after = {
            "meta": {"businessDate": "2026-09-16"},
            "drivers": [
                {"employeeId": "1", "completed": False},
                {"employeeId": "2", "completed": False},
            ],
        }
        self.assertNotEqual(
            today.status_signature(before),
            today.status_signature(after),
        )


if __name__ == "__main__":
    unittest.main()
