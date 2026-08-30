#!/usr/bin/env python3
"""Normalize CI failures into a small stable taxonomy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

TAXONOMY = {
    "BUILD_FAILURE", "ABI_BREAK", "UNIT_FAILURE", "SANITIZER",
    "DSP_QUALITY_REGRESSION", "PERFORMANCE_REGRESSION", "RESOURCE_REGRESSION",
    "FLAKY_SUSPECT", "QEMU_FAILURE", "HARDWARE_FAILURE", "XRUN_FAILURE",
    "EVIDENCE_INVALID", "INFRA_FAILURE", "STATIC_SECURITY_FAILURE",
    "UNKNOWN_FAILURE",
}


def aggregate(results: dict[str, str]) -> dict:
    order = [
        ("fast", "BUILD_FAILURE"),
        ("lab", "INFRA_FAILURE"),
        ("audio", "DSP_QUALITY_REGRESSION"),
        ("resource", "RESOURCE_REGRESSION"),
        ("quality", "UNIT_FAILURE"),
        ("codeql", "STATIC_SECURITY_FAILURE"),
        ("ci", "BUILD_FAILURE"),
    ]
    failed = [name for name, value in results.items() if value not in {"success", "skipped"}]
    category = "UNKNOWN_FAILURE"
    component = failed[0] if failed else "none"
    for name, candidate in order:
        if results.get(name) not in {None, "success", "skipped"}:
            category = candidate
            component = name
            break
    return {
        "schema_version": 1,
        "category": category if failed else "NONE",
        "component": component,
        "failed_domains": failed,
        "domain_results": results,
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
    out = aggregate({"fast": "success", "audio": "failure", "ci": "success"})
    assert out["category"] == "DSP_QUALITY_REGRESSION"
    lab = aggregate({"fast": "success", "lab": "failure", "audio": "success"})
    assert lab["category"] == "INFRA_FAILURE" and lab["component"] == "lab"
    assert "DSP_QUALITY_REGRESSION" in TAXONOMY
    print("CI failure classifier self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    agg = sub.add_parser("aggregate")
    for name in ("fast", "lab", "ci", "quality", "audio", "resource", "codeql"):
        agg.add_argument(f"--{name}", default="skipped")
    val = sub.add_parser("validation")
    val.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.command is None:
        parser.error("aggregate or validation is required")
    if args.command == "aggregate":
        names = ("fast", "lab", "ci", "quality", "audio", "resource", "codeql")
        result = aggregate({name: getattr(args, name) for name in names})
    else:
        result = validation(args.report)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
