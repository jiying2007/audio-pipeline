#!/usr/bin/env python3
"""Classify post-release laboratory qualification without conflating availability with regression."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def classify(enabled: str, conclusion: str, blocked_status: str) -> str:
    if enabled.strip().lower() != "true":
        return blocked_status
    conclusion = conclusion.strip().lower()
    if conclusion == "success":
        return "PASS"
    if conclusion in {"failure", "cancelled", "timed_out", "action_required"}:
        return "FAIL"
    if conclusion in {"queued", "in_progress", "waiting", "pending", ""}:
        return "PENDING"
    return "UNKNOWN"


def build(source_sha: str, tag: str, hil_enabled: str, hil_conclusion: str,
          extended_enabled: str, extended_conclusion: str) -> dict:
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be exact 40-hex commit")
    if not tag.startswith("v"):
        raise ValueError("tag must begin with v")
    return {
        "schema_version": 1,
        "source_sha": source_sha,
        "tag": tag,
        "software_release": "PASS",
        "lab_qualification": {
            "hil": classify(hil_enabled, hil_conclusion, "BLOCKED_RUNNER"),
            "extended_real": classify(extended_enabled, extended_conclusion, "BLOCKED_CONFIG"),
        },
    }


def self_test() -> None:
    assert classify("", "failure", "BLOCKED_RUNNER") == "BLOCKED_RUNNER"
    assert classify("true", "success", "BLOCKED_RUNNER") == "PASS"
    assert classify("true", "failure", "BLOCKED_RUNNER") == "FAIL"
    assert classify("true", "", "BLOCKED_RUNNER") == "PENDING"
    result = build("a" * 40, "v2.3.6", "", "failure", "true", "success")
    assert result["lab_qualification"] == {"hil": "BLOCKED_RUNNER", "extended_real": "PASS"}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "status.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        assert json.loads(path.read_text())["software_release"] == "PASS"
    print("post release status self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha")
    parser.add_argument("--tag")
    parser.add_argument("--hil-enabled", default="")
    parser.add_argument("--hil-conclusion", default="")
    parser.add_argument("--extended-real-enabled", default="")
    parser.add_argument("--extended-real-conclusion", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.source_sha or not args.tag:
        parser.error("--source-sha and --tag are required")
    result = build(
        args.source_sha, args.tag, args.hil_enabled, args.hil_conclusion,
        args.extended_real_enabled, args.extended_real_conclusion,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
