#!/usr/bin/env python3
"""Run a command repeatedly and distinguish deterministic failures from flakes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def signature(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def run_guard(command: list[str], runs: int, max_rate: float) -> dict:
    outcomes = []
    for index in range(runs):
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = proc.stdout or ""
        outcomes.append({
            "run": index + 1,
            "returncode": proc.returncode,
            "passed": proc.returncode == 0,
            "signature": None if proc.returncode == 0 else signature(output),
            "tail": "\n".join(output.splitlines()[-20:]),
        })
    failures = [item for item in outcomes if not item["passed"]]
    rate = len(failures) / max(1, runs)
    transitions = sum(1 for a, b in zip(outcomes, outcomes[1:]) if a["passed"] != b["passed"])
    if not failures:
        status = "STABLE_PASS"
    elif len(failures) == runs:
        status = "STABLE_FAIL"
    else:
        status = "FLAKY_SUSPECT"
    return {
        "schema_version": 1,
        "status": status,
        "runs": runs,
        "failures": len(failures),
        "failure_rate": rate,
        "max_failure_rate": max_rate,
        "budget_exceeded": rate > max_rate,
        "pass_fail_transitions": transitions,
        "failure_signatures": sorted({item["signature"] for item in failures}),
        "outcomes": outcomes,
        "command": command,
    }


def self_test() -> None:
    result = run_guard([sys.executable, "-c", "pass"], 3, 0.02)
    assert result["status"] == "STABLE_PASS" and not result["budget_exceeded"]
    result = run_guard([sys.executable, "-c", "raise SystemExit(7)"], 2, 0.02)
    assert result["status"] == "STABLE_FAIL" and result["budget_exceeded"]
    print("flaky guard self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--max-rate", type=float, default=0.02)
    parser.add_argument("--output", type=Path, required=False)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command or args.runs < 1 or not (0.0 <= args.max_rate <= 1.0):
        parser.error("valid --runs/--max-rate and a command after -- are required")
    report = run_guard(command, args.runs, args.max_rate)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "runs", "failures", "failure_rate", "budget_exceeded")}, sort_keys=True))
    return 1 if report["budget_exceeded"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
