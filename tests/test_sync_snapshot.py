import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_snapshot as sync  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_normalize_employee_id_handles_excel_numbers(self):
        self.assertEqual(sync.normalize_employee_id("11281385.0"), "11281385")
        self.assertEqual(sync.normalize_employee_id(11281385.0), "11281385")
        self.assertEqual(sync.normalize_employee_id(" 11281385 "), "11281385")


class RosterTests(unittest.TestCase):
    def test_roster_filters_to_twelve_teams_and_deduplicates(self):
        sources = [
            (
                "dailyA.tsv",
                [
                    "0|司机姓名|司机工号|司机队伍|0|0|0",
                    "1|陈浩|11281385|一大队|0|1|0",
                    "2|王刚|772906|预备大队|0|0|0",
                ],
            ),
            (
                "dailyB.tsv",
                ["2|陈浩|11281385|一大队|0|1|0"],
            ),
        ]
        roster = sync.parse_roster_lines(sources)
        self.assertEqual(
            roster,
            [{"employeeId": "11281385", "name": "陈浩", "team": "一大队"}],
        )


class LedgerTests(unittest.TestCase):
    def test_ledger_counts_unique_out_days_and_miss_days(self):
        rows = [
            ("2026-09-01", "一大队", "陈浩", "11281385", "否"),
            ("2026-09-01", "一大队", "陈浩", "11281385", "否"),
            ("2026-09-02", "一大队", "陈浩", "11281385", "是"),
            ("2026-09-03", "六大队", "黄浩", "747433", "否"),
        ]
        metrics = sync.summarize_ledger_rows(rows, "2026-09", {"11281385"})
        self.assertEqual(metrics["11281385"], {"outDays": 2, "misses": 1})


class DriverMetricTests(unittest.TestCase):
    def test_promotion_delta_can_be_negative(self):
        drivers = sync.build_driver_rows(
            [{"employeeId": "11281385", "name": "陈浩", "team": "一大队"}],
            {"11281385": {"outDays": 3, "misses": 5}},
            {"陈浩": 2},
            {"11281385": 4},
        )
        self.assertEqual(
            drivers[0],
            {
                "employeeId": "11281385",
                "name": "陈浩",
                "team": "一大队",
                "outDays": 3,
                "realTransfers": 4,
                "promotionDelta": -3,
            },
        )


class PromoRowTests(unittest.TestCase):
    def test_orders_match_recommender_and_preserve_flags(self):
        headers = [
            "城市id",
            "城市名称",
            "城市群",
            "大区",
            "城市等级",
            "日期",
            "订单ID",
            "司机ID",
            "司机工号",
            "品类",
            "send_type",
            "推荐司机ID",
            "推荐司机工号",
            "bd_type",
            "djact_id",
            "司服ID",
            "司服名称",
            "是否非线下推广(1非线下0线下)",
            "是否非正常扫码(1非正常0正常)",
            "是否小号(1小号0非小号)",
            "是否熟客订单(1熟客0非熟客)",
            "是否作弊单(1作弊0非作弊)",
        ]
        rows = [
            (
                513400,
                "凉山",
                "四川",
                "西部",
                "C",
                "2026-09-02",
                1,
                2,
                3,
                "didi_driving",
                8,
                4,
                "11281385",
                "传统",
                None,
                3577,
                "公司",
                1,
                0,
                0,
                1,
                0,
            ),
            (
                513400,
                "凉山",
                "四川",
                "西部",
                "C",
                "2026-09-01",
                2,
                2,
                3,
                "didi_driving",
                8,
                4,
                "11281385",
                "dpl",
                None,
                3577,
                "公司",
                0,
                0,
                0,
                0,
                0,
            ),
        ]
        transfer_counts, orders = sync.parse_promo_rows(
            headers, rows, "2026-09-15"
        )
        self.assertEqual(transfer_counts["11281385"], 1)
        self.assertEqual([order["date"] for order in orders], ["2026-09-02", "2026-09-01"])
        self.assertEqual(
            orders[0],
            {
                "employeeId": "11281385",
                "date": "2026-09-02",
                "nonOffline": 1,
                "abnormalScan": 0,
                "burner": 0,
                "regularCustomer": 1,
                "cheating": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()

