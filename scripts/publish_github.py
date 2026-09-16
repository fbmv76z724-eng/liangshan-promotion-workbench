#!/usr/bin/env python3
"""Publish the local static site through the GitHub API."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY = "fbmv76z724-eng/liangshan-promotion-workbench"


class PublishError(RuntimeError):
    """Raised when GitHub cannot publish the site."""


def run_gh(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_not_found: bool = False,
) -> Any:
    command = ["gh", "api", "--method", method, endpoint]
    if payload is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if allow_not_found and (
            "HTTP 404" in result.stderr or "Not Found" in result.stderr
        ):
            return None
        raise PublishError(result.stderr.strip() or "GitHub API 调用失败")
    return json.loads(result.stdout) if result.stdout.strip() else None


def tracked_files(root: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-s"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PublishError(result.stderr.strip() or "无法读取 Git 文件列表")

    files = []
    for line in result.stdout.splitlines():
        metadata, path = line.split("\t", 1)
        mode, _object_id, _stage = metadata.split()
        files.append({"mode": mode, "path": path, "content": (root / path).read_bytes()})
    if not files:
        raise PublishError("当前仓库没有可发布的文件")
    return files


def create_blobs(repository: str, files: list[dict[str, Any]]) -> list[dict[str, str]]:
    entries = []
    for file in files:
        blob = run_gh(
            "POST",
            f"repos/{repository}/git/blobs",
            {
                "content": base64.b64encode(file["content"]).decode("ascii"),
                "encoding": "base64",
            },
        )
        entries.append(
            {
                "path": file["path"],
                "mode": file["mode"],
                "type": "blob",
                "sha": blob["sha"],
            }
        )
    return entries


def current_ref(repository: str, branch: str) -> dict[str, Any] | None:
    try:
        return run_gh("GET", f"repos/{repository}/git/ref/heads/{branch}")
    except PublishError as error:
        if "HTTP 404" in str(error) or "Git Repository is empty" in str(error):
            return None
        raise


def bootstrap_repository(repository: str, branch: str, root: Path) -> None:
    readme = (root / "README.md").read_text(encoding="utf-8")
    run_gh(
        "PUT",
        f"repos/{repository}/contents/README.md",
        {
            "message": "chore: initialize repository",
            "content": base64.b64encode(readme.encode("utf-8")).decode("ascii"),
            "branch": branch,
        },
    )


def publish_commit(
    *,
    repository: str,
    branch: str,
    root: Path,
    message: str,
) -> dict[str, Any]:
    ref = current_ref(repository, branch)
    if ref is None:
        bootstrap_repository(repository, branch, root)
        ref = current_ref(repository, branch)
    parent_sha = ref["object"]["sha"] if ref else None
    parent_tree = None
    if parent_sha:
        parent_commit = run_gh(
            "GET", f"repos/{repository}/git/commits/{parent_sha}"
        )
        parent_tree = parent_commit["tree"]["sha"]

    entries = create_blobs(repository, tracked_files(root))
    tree = run_gh(
        "POST",
        f"repos/{repository}/git/trees",
        {"tree": entries},
    )
    if parent_tree and tree["sha"] == parent_tree:
        return {"ok": True, "changed": False, "commit": parent_sha}

    commit = run_gh(
        "POST",
        f"repos/{repository}/git/commits",
        {
            "message": message,
            "tree": tree["sha"],
            "parents": [parent_sha] if parent_sha else [],
        },
    )

    if ref:
        run_gh(
            "PATCH",
            f"repos/{repository}/git/refs/heads/{branch}",
            {"sha": commit["sha"], "force": True},
        )
    else:
        run_gh(
            "POST",
            f"repos/{repository}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": commit["sha"]},
        )
    return {"ok": True, "changed": True, "commit": commit["sha"]}


def ensure_pages(repository: str, branch: str) -> dict[str, Any]:
    source = {"branch": branch, "path": "/docs"}
    existing = run_gh(
        "GET", f"repos/{repository}/pages", allow_not_found=True
    )
    if existing is None:
        return run_gh(
            "POST",
            f"repos/{repository}/pages",
            {"source": source},
        )
    return run_gh(
        "PUT",
        f"repos/{repository}/pages",
        {"source": source},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--message", default="chore: update workbench data")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        commit = publish_commit(
            repository=args.repository,
            branch=args.branch,
            root=args.root,
            message=args.message,
        )
        pages = ensure_pages(args.repository, args.branch)
    except PublishError as error:
        print(f"发布失败：{error}")
        return 1

    print(
        json.dumps(
            {
                **commit,
                "pagesUrl": pages.get("html_url"),
                "repository": args.repository,
                "branch": args.branch,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
