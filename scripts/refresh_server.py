#!/usr/bin/env python3
"""Expose a loopback-only refresh endpoint for the static workbench."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(
    "/Users/fifidei/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/python/bin/python3"
)
DEFAULT_PORT = 18765
SHANGHAI = ZoneInfo("Asia/Shanghai")
ALLOWED_ORIGINS = {
    "https://fbmv76z724-eng.github.io",
}


class RefreshJob:
    """Run one full workbench refresh at a time."""

    def __init__(
        self,
        runner: Callable[[], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._runner = runner or self._run_workbench
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {"status": "idle"}

    @staticmethod
    def _run_workbench() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PYTHON), "scripts/run_workbench.py", "--full"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=900,
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._state.get("status") == "running":
                return dict(self._state)
            self._state = {
                "status": "running",
                "startedAt": dt.datetime.now(SHANGHAI).replace(microsecond=0).isoformat(),
            }
        threading.Thread(target=self._run, daemon=True).start()
        return self.snapshot()

    def _run(self) -> None:
        try:
            result = self._runner()
        except Exception as error:  # noqa: BLE001
            state = {
                "status": "failure",
                "finishedAt": dt.datetime.now(SHANGHAI)
                .replace(microsecond=0)
                .isoformat(),
                "message": " ".join(str(error).split())[:300],
            }
        else:
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            detail = " | ".join(
                line.strip() for line in output.splitlines()[-3:] if line.strip()
            )
            state = {
                "status": (
                    "success"
                    if refresh_result_succeeded(result)
                    else "failure"
                ),
                "finishedAt": dt.datetime.now(SHANGHAI)
                .replace(microsecond=0)
                .isoformat(),
                "message": detail[:500],
            }
        with self._lock:
            self._state = state


def allowed_origin(origin: str) -> bool:
    return (
        origin in ALLOWED_ORIGINS
        or origin.startswith("http://127.0.0.1:")
        or origin.startswith("http://localhost:")
    )


def refresh_result_succeeded(result: subprocess.CompletedProcess[str]) -> bool:
    if result.returncode == 0:
        return True
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    return '"ok": true' in output or "已恢复（此前失败" in output


def make_handler(job: RefreshJob) -> type[BaseHTTPRequestHandler]:
    class RefreshHandler(BaseHTTPRequestHandler):
        server_version = "WorkbenchRefresh/1.0"

        def log_message(self, format_string: str, *args: Any) -> None:
            super().log_message(format_string, *args)

        def _origin(self) -> str:
            return str(self.headers.get("Origin") or "").rstrip("/")

        def _cors_headers(self) -> dict[str, str]:
            origin = self._origin()
            if not origin or not allowed_origin(origin):
                return {}
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "X-Workbench-Refresh, Content-Type",
                "Vary": "Origin",
            }

        def _send_json(
            self,
            status_code: int,
            payload: dict[str, Any],
            *,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in self._cors_headers().items():
                self.send_header(key, value)
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            origin = self._origin()
            if not origin or not allowed_origin(origin):
                self._send_json(403, {"ok": False, "error": "origin_not_allowed"})
                return
            headers = {}
            if self.headers.get("Access-Control-Request-Private-Network") == "true":
                headers["Access-Control-Allow-Private-Network"] = "true"
            self._send_json(204, {}, extra_headers=headers)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send_json(200, {"ok": True, "status": "ready"})
                return
            if self.path == "/status":
                self._send_json(200, {"ok": True, **job.snapshot()})
                return
            self._send_json(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/refresh":
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            if self.headers.get("X-Workbench-Refresh") != "1":
                self._send_json(400, {"ok": False, "error": "missing_refresh_header"})
                return
            origin = self._origin()
            if origin and not allowed_origin(origin):
                self._send_json(403, {"ok": False, "error": "origin_not_allowed"})
                return
            state = job.start()
            status_code = 202 if state.get("status") == "running" else 200
            self._send_json(status_code, {"ok": True, **state})

    return RefreshHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(RefreshJob()),
    )
    print(
        json.dumps(
            {"ok": True, "port": args.port, "project": str(PROJECT_ROOT)},
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
