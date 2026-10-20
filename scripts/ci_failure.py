#!/usr/bin/env python3
"""Normalize CI failures into a small stable taxonomy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

TAXONOMY = {
    "BUILD_FAILURE", "ABI_BREAK", "UNIT_FAILURE", "SANITIZER",
    "DSP_QUALITY_REGRESSION", "PERFORMANCE_REGRESSION", "RESOURCE_REGRESSION",
    "FLAKY_SUSPECT", "QEMU_FAILURE", "HARDWARE_FAILURE", "XRUN_FAILURE",
    "EVIDENCE_INVALID", "INFRA_FAILURE", "STATIC_SECURITY_FAILURE",
    "UNKNOWN_FAILURE",
}


DOMAIN_CATEGORIES = {
    "impact": "EVIDENCE_INVALID",
    "fast": "BUILD_FAILURE",
    "lab": "INFRA_FAILURE",
    "hosted_real": "DSP_QUALITY_REGRESSION",
    "audio": "DSP_QUALITY_REGRESSION",
    "resource": "RESOURCE_REGRESSION",
    "quality": "UNIT_FAILURE",
    "codeql": "STATIC_SECURITY_FAILURE",
    "ci": "BUILD_FAILURE",
}
SELECTED_DOMAINS = ("lab", "ci", "quality", "audio", "resource", "codeql")
JOB_RESULTS = {"success", "failure", "cancelled", "skipped"}


def aggregate(results: dict[str, str], *, docs_only: str,
              selected: dict[str, str]) -> dict:
    """Evaluate the exact Verify needs matrix and describe that same decision.

    Missing or malformed impact outputs cannot authorize a skipped job. Keep
    input errors in the receipt instead of raising before the receipt is saved.
    """
    expected: dict[str, str | None] = {"impact": "success", "fast": "success"}
    violations = []

    def invalid_selection(name: str, value: str | None) -> None:
        violations.append({"domain": "impact", "reason": "invalid_selection",
                           "input": name, "expected": "true or false", "actual": value})

    if docs_only in {"true", "false"}:
        expected["hosted_real"] = "skipped" if docs_only == "true" else "success"
    else:
        expected["hosted_real"] = None
        invalid_selection("docs_only", docs_only)
    for name in SELECTED_DOMAINS:
        value = selected.get(name)
        if value in {"true", "false"}:
            expected[name] = "success" if value == "true" else "skipped"
        else:
            expected[name] = None
            invalid_selection("run_" + name, value)

    for name in DOMAIN_CATEGORIES:
        actual = results.get(name)
        if actual not in JOB_RESULTS:
            violations.append({"domain": name, "reason": "invalid_job_result",
                               "expected": expected[name], "actual": actual})
        elif expected[name] is not None and actual != expected[name]:
            violations.append({"domain": name, "reason": "unexpected_job_result",
                               "expected": expected[name], "actual": actual})

    failed = [name for name in DOMAIN_CATEGORIES
              if any(item["domain"] == name for item in violations)]
    component = failed[0] if failed else "none"
    category = "NONE"
    if failed:
        primary = next(item for item in violations if item["domain"] == component)
        # A required job that was skipped, an unexpected execution, or bad
        # metadata is an evidence failure; an executed failing job keeps its
        # existing domain category. Cancellation still fails the same gate.
        if (primary["reason"] == "unexpected_job_result"
                and primary["expected"] == "success"
                and primary["actual"] in {"failure", "cancelled"}):
            category = DOMAIN_CATEGORIES[component]
        else:
            category = "EVIDENCE_INVALID"
    return {
        "schema_version": 1,
        "category": category,
        "component": component,
        "failed_domains": failed,
        "domain_results": results,
        "expected_results": expected,
        "selection": {"docs_only": docs_only, **selected},
        "violations": violations,
        "passed": not violations,
        "likely_infra": False,
    }


def validation(report_path: Path) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failed = [case for case in report.get("cases", []) if not case.get("passed", False)]
    primary = failed[0] if failed else None
    return {
        "schema_version": 1,
        "category": "DSP_QUALITY_REGRESSION" if failed else "NONE",
        "component": primary.get("scenario") if primary else "validation",
        "test": primary.get("case_id") if primary else None,
        "metrics": primary.get("metrics") if primary else {},
        "violations": primary.get("violations") if primary else [],
        "failed_cases": len(failed),
        "likely_infra": False,
    }


def self_test() -> None:
    subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]
                                       / "tests/test_ci_failure.py")], check=True)
    print("CI failure classifier self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    agg = sub.add_parser("aggregate")
    for name in DOMAIN_CATEGORIES:
        agg.add_argument("--" + name.replace("_", "-"), default="")
    agg.add_argument("--docs-only", default="")
    for name in SELECTED_DOMAINS:
        agg.add_argument(f"--expect-{name}", default="")
    agg.add_argument("--enforce", action="store_true",
                     help="write the receipt, then fail unless the exact needs matrix passed")
    val = sub.add_parser("validation")
    val.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.command is None:
        parser.error("aggregate or validation is required")
    if args.command == "aggregate":
        result = aggregate({name: getattr(args, name) for name in DOMAIN_CATEGORIES},
                           docs_only=args.docs_only,
                           selected={name: getattr(args, "expect_" + name)
                                     for name in SELECTED_DOMAINS})
    else:
        result = validation(args.report)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if args.command == "aggregate" and args.enforce and not result["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
