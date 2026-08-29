#!/usr/bin/env python3
"""Acquire pinned public-validation metadata and opt-in large assets."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from dataset_lock import load_json, validate_lock


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)


def clone_pinned(item: dict, root: Path, materialize: bool) -> None:
    dest = root / item["local_path"]
    if not dest.exists():
        env = dict(os.environ)
        env["GIT_LFS_SKIP_SMUDGE"] = "1"
        run(["git", "clone", "--filter=blob:none", "--no-checkout", item["source"], str(dest)], env)
    run(["git", "-C", str(dest), "fetch", "--depth", "1", "origin", item["revision"]])
    run(["git", "-C", str(dest), "checkout", "--detach", item["revision"]])
    if materialize and item["id"] == "microsoft-aec-challenge":
        if shutil.which("git-lfs") is None and shutil.which("git"):
            try:
                run(["git", "lfs", "version"])
            except subprocess.CalledProcessError as exc:
                raise RuntimeError("git-lfs is required to materialize AEC Challenge audio") from exc
        includes = [path.rstrip("/") + "/**" for path in item.get("required_paths", [])]
        run(["git", "-C", str(dest), "lfs", "pull", "--include", ",".join(includes)])


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 1024)
    partial.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--dataset", action="append", default=[])
    parser.add_argument("--materialize", action="store_true",
                        help="materialize selected public assets; may be very large")
    parser.add_argument("--allow-large-downloads", action="store_true")
    args = parser.parse_args()

    lock = load_json(args.lock)
    validate_lock(lock)
    selected = set(args.dataset)
    args.root.mkdir(parents=True, exist_ok=True)
    for item in lock["datasets"]:
        if selected and item["id"] not in selected:
            continue
        if item["kind"] == "git":
            clone_pinned(item, args.root, args.materialize)
            index_url = item.get("integrity", {}).get("index_url")
            if index_url and args.materialize:
                download(index_url, args.root / "dns5-datasets-files-sha1.csv.bz2")
        elif item["kind"] == "archive":
            if not args.materialize:
                print(f"metadata-only: {item['id']} -> {item['source']}")
                continue
            if not args.allow_large_downloads:
                raise RuntimeError(f"{item['id']} is a large download; pass --allow-large-downloads")
            download(item["source"], args.root / item["local_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
