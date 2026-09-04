#!/usr/bin/env python3
"""Build a single audit manifest for immutable audio-pipeline releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()


def availability(enabled: str, blocked: str) -> str:
    return "DISPATCH_PENDING" if enabled.strip().lower() == "true" else blocked


def build_manifest(*, version: str, tag: str, source_sha: str, verify_run_id: str,
                   prs_json: Path, assets: list[Path], output: Path,
                   hil_enabled: str, extended_real_enabled: str,
                   root: Path = Path(".")) -> dict:
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be exact 40-hex commit")
    prs = json.loads(prs_json.read_text(encoding="utf-8"))
    eligible = sorted(
        int(pr["number"]) for pr in prs
        if pr.get("merged_at") and pr.get("base", {}).get("ref") == "main"
    )
    if not eligible:
        raise ValueError("release manifest requires merged PR lineage")
    asset_records = []
    for path in assets:
        if not path.is_file():
            raise ValueError(f"release asset missing: {path}")
        asset_records.append({"name": path.name, "size": path.stat().st_size, "sha256": sha256(path)})
    binding_paths = [
        root / "validation/authority.json",
        root / "validation/datasets.lock.json",
        root / "validation/tools/run_validation.py",
        root / "validation/tools/run_validation_engine.py",
        root / "validation/tools/render_corr_exact.py",
        root / "validation/tools/render_corr_exact.c",
    ]
    bindings = {
        path.relative_to(root).as_posix(): sha256(path)
        for path in binding_paths if path.is_file()
    }
    try:
        tree_sha = git_output("rev-parse", f"{source_sha}^{{tree}}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        tree_sha = ""
    manifest = {
        "schema_version": 1,
        "release": {"version": version, "tag": tag, "immutable_required": True},
        "source": {"commit_sha": source_sha, "tree_sha": tree_sha},
        "lineage": {"merged_pr_numbers": eligible, "main_verify_run_id": str(verify_run_id)},
        "validation_bindings": bindings,
        "assets": sorted(asset_records, key=lambda item: item["name"]),
        "lab_qualification": {
            "hil": availability(hil_enabled, "BLOCKED_RUNNER"),
            "extended_real": availability(extended_real_enabled, "BLOCKED_CONFIG"),
            "note": "post-release lab workflows are separate from immutable software release authority",
        },
    }
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        asset = root / "sdk.tar.gz"
        asset.write_bytes(b"sdk")
        prs = root / "prs.json"
        prs.write_text(json.dumps([{"number": 7, "merged_at": "x", "base": {"ref": "main"}}]), encoding="utf-8")
        out = root / "manifest.json"
        manifest = build_manifest(
            version="2.3.7", tag="v2.3.7", source_sha="a" * 40, verify_run_id="123",
            prs_json=prs, assets=[asset], output=out, hil_enabled="", extended_real_enabled="true",
            root=root,
        )
        assert manifest["lineage"]["merged_pr_numbers"] == [7]
        assert manifest["lab_qualification"]["hil"] == "BLOCKED_RUNNER"
        assert manifest["lab_qualification"]["extended_real"] == "DISPATCH_PENDING"
        assert manifest["assets"][0]["sha256"] == hashlib.sha256(b"sdk").hexdigest()
    print("release manifest self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version")
    parser.add_argument("--tag")
    parser.add_argument("--source-sha")
    parser.add_argument("--verify-run-id")
    parser.add_argument("--prs-json", type=Path)
    parser.add_argument("--asset", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hil-enabled", default="")
    parser.add_argument("--extended-real-enabled", default="")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("version", "tag", "source_sha", "verify_run_id", "prs_json", "output"):
        if getattr(args, name) in (None, ""):
            parser.error(f"--{name.replace('_', '-')} is required")
    build_manifest(
        version=args.version, tag=args.tag, source_sha=args.source_sha,
        verify_run_id=args.verify_run_id, prs_json=args.prs_json, assets=args.asset,
        output=args.output, hil_enabled=args.hil_enabled,
        extended_real_enabled=args.extended_real_enabled,
    )
    print("release evidence manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
