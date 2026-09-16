#!/usr/bin/env python3
"""Build today's promotion completion snapshot from an ego-browser read."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = PROJECT_ROOT / "docs" / "data" / "snapshot.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "data" / "today.json"
DEFAULT_WORK = PROJECT_ROOT / "work" / "today-submitted.txt"
DEFAULT_READER = (
    Path.home()
    / ".codex"
    / "skills"
    / "tuiguang-tixing"
    / "scripts"
    / "read_submitted.py"
)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class TodaySyncError(RuntimeError):
    """Raised when today's promotion data cannot be refreshed safely."""


def promotion_date_for(value: str) -> str:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    else:
        parsed = parsed.astimezone(SHANGHAI)
    if parsed.hour < 6:
        parsed -= dt.timedelta(days=1)
    return parsed.date().isoformat()


def parse_submitted(text: str) -> list[tuple[str, str]]:
    raw = (text or "").strip()
    if not raw or raw.upper() == "EMPTY":
        return []
    raw = re.sub(r"^\s*N=\d+\s*::\s*", "", raw)
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for segment in re.split(r"[;；]+", raw):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        name, team = (part.strip() for part in segment.split("=", 1))
        key = (name, team)
        if name and team and key not in seen:
            seen.add(key)
            pairs.append(key)
    return pairs


def build_today_snapshot(
    *,
    business_date: str,
    synced_at: str,
    drivers: Iterable[dict[str, Any]],
    submitted: Iterable[tuple[str, str]],
) -> dict[str, Any]:
    submitted_set = set(submitted)
    rows = []
    for person in drivers:
        if person.get("promotionCompleted") is True:
            continue
        name = str(person.get("name") or "").strip()
        team = str(person.get("team") or "").strip()
        rows.append(
            {
                "employeeId": str(person.get("employeeId") or "").strip(),
                "name": name,
                "team": team,
                "completed": (name, team) in submitted_set,
            }
        )
    completed_count = sum(1 for row in rows if row["completed"])
    return {
        "meta": {
            "schemaVersion": 1,
            "businessDate": business_date,
            "syncedAt": synced_at,
            "teamCount": len({row["team"] for row in rows}),
            "driverCount": len(rows),
            "completedCount": completed_count,
            "unfinishedCount": len(rows) - completed_count,
        },
        "drivers": rows,
    }


def status_signature(snapshot: dict[str, Any] | None) -> tuple[str, tuple[str, ...]]:
    snapshot = snapshot or {}
    meta = snapshot.get("meta") or {}
    drivers = sorted(
        (
            f"{row.get('employeeId') or ''}:{int(row.get('completed') is True)}"
            for row in snapshot.get("drivers", [])
        )
    )
    return (
        str(meta.get("businessDate") or ""),
        tuple(drivers),
    )


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        raise TodaySyncError(f"快照读取失败：{path}") from error
    if not isinstance(payload, dict):
        raise TodaySyncError(f"快照格式不正确：{path}")
    return payload


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".today.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def read_submitted_with_ego(reader: Path, business_date: str, output: Path) -> str:
    if not reader.exists():
        raise TodaySyncError(f"缺少 ego-lite 读取脚本：{reader}")
    result = subprocess.run(
        [
            sys.executable,
            str(reader),
            "--date",
            business_date,
            "--out",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise TodaySyncError(detail or "ego-lite 钉钉读取失败")
    try:
        return output.read_text(encoding="utf-8")
    except OSError as error:
        raise TodaySyncError(f"无法读取钉钉提交结果：{output}") from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="", help="推广日 YYYY-MM-DD")
    parser.add_argument("--submitted", type=Path, default=None)
    parser.add_argument("--reader", type=Path, default=DEFAULT_READER)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        now = dt.datetime.now(SHANGHAI)
        business_date = args.date or promotion_date_for(now.isoformat())
        roster_snapshot = load_snapshot(args.snapshot)
        roster = roster_snapshot.get("drivers")
        if not isinstance(roster, list) or not roster:
            raise TodaySyncError("月度快照缺少司机名单")

        if args.submitted is None:
            submitted_text = read_submitted_with_ego(
                args.reader,
                business_date,
                args.work,
            )
        else:
            submitted_text = args.submitted.read_text(encoding="utf-8")

        next_snapshot = build_today_snapshot(
            business_date=business_date,
            synced_at=now.replace(microsecond=0).isoformat(),
            drivers=roster,
            submitted=parse_submitted(submitted_text),
        )
        previous = load_snapshot(args.out)
        changed = args.force or status_signature(previous) != status_signature(next_snapshot)
        if changed:
            write_snapshot(args.out, next_snapshot)
    except (OSError, TodaySyncError) as error:
        print(f"TODAY_SYNC_FAILED: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "changed": changed,
                "businessDate": next_snapshot["meta"]["businessDate"],
                "syncedAt": next_snapshot["meta"]["syncedAt"],
                "completed": next_snapshot["meta"]["completedCount"],
                "unfinished": next_snapshot["meta"]["unfinishedCount"],
                "output": str(args.out),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
