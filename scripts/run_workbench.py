#!/usr/bin/env python3
"""Run the promotion workbench synchronization and publish workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(
    "/Users/fifidei/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)
STATE_PATH = PROJECT_ROOT / "work" / "workbench-state.json"
PAGES_URL = "https://fbmv76z724-eng.github.io/liangshan-promotion-workbench/"
REPOSITORY = "fbmv76z724-eng/liangshan-promotion-workbench"
TODAY_MESSAGE = "chore: sync today's promotion status"
SNAPSHOT_MESSAGE = "chore: sync monthly promotion snapshot"
SHANGHAI = ZoneInfo("Asia/Shanghai")

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sync_snapshot  # noqa: E402


class WorkbenchError(RuntimeError):
    """A user-actionable workflow failure."""

    def __init__(self, phase: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase
        self.message = " ".join(str(message).split())[:240] or "未知错误"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="立即同步月度与今日数据，并强制发布今日更新时间",
    )
    parser.add_argument(
        "--now",
        default="",
        help="用于测试的上海时间 ISO 时间戳",
    )
    return parser.parse_args()


def now_in_shanghai(value: str = "") -> dt.datetime:
    now = dt.datetime.fromisoformat(value) if value else dt.datetime.now(SHANGHAI)
    if now.tzinfo is None:
        return now.replace(tzinfo=SHANGHAI)
    return now.astimezone(SHANGHAI)


def is_monthly_window(now: dt.datetime) -> bool:
    return (18, 30) <= (now.hour, now.minute) < (18, 40)


def has_pending_publish(state: dict[str, Any]) -> bool:
    return bool(state.get("pendingToday") or state.get("pendingSnapshot"))


def load_json(path: Path, *, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise WorkbenchError("local_data", f"无法读取 {path}") from error


def load_state() -> dict[str, Any]:
    state = load_json(STATE_PATH, default={})
    return state if isinstance(state, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=STATE_PATH.parent,
        prefix=".workbench-state.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(payload)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, STATE_PATH)


def command_detail(result: subprocess.CompletedProcess[str]) -> str:
    output = (result.stderr or result.stdout or "").strip()
    return " | ".join(line.strip() for line in output.splitlines()[-3:] if line.strip())


def run_command(
    command: list[str],
    *,
    phase: str,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise WorkbenchError(phase, str(error)) from error
    if result.returncode != 0:
        raise WorkbenchError(phase, command_detail(result))
    return result


def run_json_script(
    arguments: list[str],
    *,
    phase: str,
    timeout: int = 300,
) -> dict[str, Any]:
    result = run_command(
        [str(PYTHON), *arguments],
        phase=phase,
        timeout=timeout,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise WorkbenchError(phase, "脚本没有返回有效 JSON") from error
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise WorkbenchError(phase, "脚本返回了失败的 JSON")
    return payload


def run_tests() -> None:
    run_command(
        [
            str(PYTHON),
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ],
        phase="python_tests",
        timeout=300,
    )
    run_command(
        ["sh", "scripts/test_logic.sh"],
        phase="frontend_tests",
        timeout=180,
    )


def publish(message: str) -> str:
    result = run_json_script(
        ["scripts/publish_github.py", "--message", message],
        phase="publish",
        timeout=600,
    )
    commit = str(result.get("commit") or "")
    if not commit:
        raise WorkbenchError("publish", "发布结果缺少 commit")
    return commit


def wait_for_pages(commit: str, timeout: int = 240) -> None:
    deadline = time.monotonic() + timeout
    endpoint = f"repos/{REPOSITORY}/pages/builds/latest"
    while time.monotonic() < deadline:
        result = run_command(
            ["gh", "api", endpoint],
            phase="pages_build",
            timeout=60,
        )
        try:
            build = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise WorkbenchError("pages_build", "GitHub Pages 返回无效 JSON") from error
        status = str(build.get("status") or "")
        if status == "errored":
            detail = (build.get("error") or {}).get("message") or "构建失败"
            raise WorkbenchError("pages_build", detail)
        if str(build.get("commit") or "") == commit and status == "built":
            return
        time.sleep(5)
    raise WorkbenchError("pages_build", f"等待构建超时：{commit[:12]}")


def fetch_live(path: str, cache_key: str) -> str:
    separator = "&" if "?" in path else "?"
    url = f"{PAGES_URL}{path}{separator}v={cache_key}"
    request = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "liangshan-promotion-workbench-sync",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise WorkbenchError("online_verify", f"{path} 返回 {response.status}")
            return response.read().decode("utf-8")
    except (OSError, urllib.error.URLError) as error:
        raise WorkbenchError("online_verify", f"{path} 不可访问：{error}") from error


def verify_homepage(commit: str) -> str:
    wait_for_pages(commit)
    homepage = fetch_live("", commit)
    if "<title>推广工作台</title>" not in homepage:
        raise WorkbenchError("online_verify", "线上首页标题不正确")
    return homepage


def verify_today(commit: str) -> None:
    homepage = verify_homepage(commit)
    app_js = fetch_live("app.js", commit)
    for marker in ('id="today-only-completed"', 'id="today-refresh"'):
        if marker not in homepage:
            raise WorkbenchError("online_verify", f"线上今日板块缺少控件：{marker}")
    if "todayOnlyCompleted" not in app_js or "refreshTodayManually" not in app_js:
        raise WorkbenchError("online_verify", "线上今日板块缺少筛除逻辑")
    expected = load_json(PROJECT_ROOT / "docs" / "data" / "today.json")
    try:
        actual = json.loads(fetch_live("data/today.json", commit))
    except json.JSONDecodeError as error:
        raise WorkbenchError("online_verify", "线上 today.json 不是有效 JSON") from error
    if actual != expected:
        raise WorkbenchError("online_verify", "线上 today.json 与本地数据不一致")


def verify_snapshot(commit: str) -> None:
    homepage = verify_homepage(commit)
    expected = load_json(PROJECT_ROOT / "docs" / "data" / "snapshot.json")
    try:
        actual = json.loads(fetch_live("data/snapshot.json", commit))
        app_js = fetch_live("app.js", commit)
    except json.JSONDecodeError as error:
        raise WorkbenchError("online_verify", "线上 snapshot.json 不是有效 JSON") from error
    if actual != expected:
        raise WorkbenchError("online_verify", "线上 snapshot.json 与本地数据不一致")

    teams = {str(row.get("team") or "") for row in actual.get("drivers", [])}
    if len(teams) != 12 or actual.get("meta", {}).get("teamCount") != 12:
        raise WorkbenchError("online_verify", "线上快照不是 12 个队伍")
    if "teamCompletionFilter" not in app_js:
        raise WorkbenchError("online_verify", "线上推广完成筛选逻辑缺失")
    for marker in (
        'id="team-completion-filter"',
        'value="completed"',
        'value="unfinished"',
    ):
        if marker not in homepage:
            raise WorkbenchError("online_verify", "线上推广完成筛选控件缺失")
    synced_at = str(actual.get("meta", {}).get("syncedAt") or "")
    source_date = str(actual.get("meta", {}).get("sourceDate") or "")
    if not synced_at or not source_date:
        raise WorkbenchError("online_verify", "线上快照缺少最新同步日期")


def sync_today_arguments(*, force: bool = False) -> list[str]:
    arguments = ["scripts/sync_today.py"]
    if force:
        arguments.append("--force")
    return arguments


def sync_today(state: dict[str, Any], *, force: bool = False) -> bool:
    payload = run_json_script(
        sync_today_arguments(force=force),
        phase="today_sync",
        timeout=300,
    )
    changed = payload.get("changed") is True
    if changed:
        state["pendingToday"] = True
        save_state(state)
    return changed


def check_snapshot(state: dict[str, Any], *, monthly_due: bool) -> bool:
    if not monthly_due and not state.get("pendingSnapshot"):
        return False

    current = load_json(PROJECT_ROOT / "docs" / "data" / "snapshot.json")
    current_date = str(current.get("meta", {}).get("sourceDate") or "")
    daily_dir = sync_snapshot.discover_latest_daily_dir(
        sync_snapshot.DEFAULT_DAILY_ROOT
    )
    sent = sync_snapshot.read_latest_sent(daily_dir)
    source_date = str(sent.get("sourceDate") or "")
    if not current_date or not source_date:
        raise WorkbenchError("snapshot_check", "快照缺少 sourceDate")
    if source_date <= current_date:
        return False

    run_json_script(
        ["scripts/sync_snapshot.py", "--daily-dir", str(daily_dir)],
        phase="snapshot_sync",
        timeout=600,
    )
    state["pendingSnapshot"] = True
    save_state(state)
    return True


def failure_key(errors: list[WorkbenchError]) -> str:
    return "\n".join(f"{error.phase}: {error.message}" for error in errors)


def print_alert(message: str) -> None:
    print(f"ALERT: {message}", file=sys.stderr)


def finish(
    *,
    state: dict[str, Any],
    errors: list[WorkbenchError],
    changed_today: bool,
    changed_snapshot: bool,
    published: list[str],
) -> int:
    if errors:
        key = failure_key(errors)
        previous = state.get("failure") or {}
        state["failure"] = {
            "key": key,
            "phase": errors[0].phase,
            "message": errors[0].message,
            "since": previous.get("since") or dt.datetime.now(SHANGHAI).isoformat(),
        }
        save_state(state)
        if previous.get("key") != key:
            print_alert(
                f"推广工作台同步失败（{errors[0].phase}）：{errors[0].message}"
            )
            return 1
        print(
            json.dumps(
                {
                    "ok": True,
                    "notify": False,
                    "status": "unchanged_failure",
                    "phase": errors[0].phase,
                },
                ensure_ascii=False,
            )
        )
        return 0

    previous = state.get("failure")
    if previous:
        state["failure"] = None
        save_state(state)
        print_alert(
            f"推广工作台已恢复（此前失败：{previous.get('phase') or '未知'}）"
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "notify": False,
                "changedToday": changed_today,
                "changedSnapshot": changed_snapshot,
                "published": published,
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    args = parse_args()
    now = now_in_shanghai(args.now)
    state = load_state()
    errors: list[WorkbenchError] = []
    changed_today = False
    changed_snapshot = False
    published: list[str] = []

    if not PYTHON.is_file():
        return finish(
            state=state,
            errors=[WorkbenchError("runtime", f"Python 不存在：{PYTHON}")],
            changed_today=False,
            changed_snapshot=False,
            published=[],
        )

    try:
        changed_today = sync_today(state, force=args.full)
    except WorkbenchError as error:
        errors.append(error)

    try:
        changed_snapshot = check_snapshot(
            state,
            monthly_due=args.full or is_monthly_window(now),
        )
    except WorkbenchError as error:
        errors.append(error)

    tests_passed = False
    if has_pending_publish(state):
        try:
            run_tests()
            tests_passed = True
        except WorkbenchError as error:
            errors.append(error)

    if tests_passed and state.get("pendingToday"):
        try:
            published.append(publish(TODAY_MESSAGE))
            verify_today(published[-1])
            state["pendingToday"] = False
            save_state(state)
        except WorkbenchError as error:
            errors.append(error)

    if tests_passed and state.get("pendingSnapshot"):
        try:
            published.append(publish(SNAPSHOT_MESSAGE))
            verify_snapshot(published[-1])
            state["pendingSnapshot"] = False
            save_state(state)
        except WorkbenchError as error:
            errors.append(error)

    return finish(
        state=state,
        errors=errors,
        changed_today=changed_today,
        changed_snapshot=changed_snapshot,
        published=published,
    )


if __name__ == "__main__":
    raise SystemExit(main())
