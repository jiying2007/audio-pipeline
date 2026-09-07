#!/usr/bin/env python3
"""Aggregate trusted-runner readiness for E001 without granting hardware/PQ authority."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

ROLES = (
    "audio-validation",
    "audio-builder",
    "audio-target",
    "certification-archive",
)
FORBIDDEN = {
    "PRODUCT_CERTIFIED",
    "PRODUCT_QUALIFICATION_PASS",
    "DUT_HIL_PASS",
    "HARDWARE_VALIDATED",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_report(spec: str) -> tuple[str, dict]:
    role, sep, raw_path = spec.partition("=")
    require(bool(sep) and role in ROLES and bool(raw_path), "report must be role=path for a registered role")
    path = Path(raw_path)
    require(path.is_file(), f"missing readiness report: {path}")
    return role, json.loads(path.read_text(encoding="utf-8"))


def aggregate(source_sha: str, release_tag: str, reports: list[tuple[str, dict]]) -> dict:
    require(re.fullmatch(r"[0-9a-fA-F]{40}", source_sha) is not None, "source_sha must be exact 40-hex")
    source_sha = source_sha.lower()
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release_tag) is not None, "release_tag must be semantic vX.Y.Z")
    require(len(reports) == len(ROLES), "all four trusted runner roles are required")
    require({role for role, _ in reports} == set(ROLES), "readiness roles must be complete and unique")

    rendered_roles: dict[str, dict] = {}
    for role, report in reports:
        require(report.get("schema_version") == 1, f"{role}: unsupported readiness schema")
        require(report.get("role") == role, f"{role}: report role mismatch")
        require(report.get("source_revision") == source_sha, f"{role}: source revision drift")
        require(report.get("classification") == "READY", f"{role}: runner is not READY")
        require(report.get("failure_count") == 0, f"{role}: nonzero readiness failure count")
        runner = report.get("runner") or {}
        require(bool(runner.get("name")), f"{role}: runner identity missing")
        require(runner.get("os") == "Linux", f"{role}: runner OS must be Linux")
        rendered_roles[role] = {
            "classification": "READY",
            "runner": {
                "name": runner["name"],
                "arch": runner.get("arch"),
                "os": runner["os"],
            },
        }

    result = {
        "schema_version": 1,
        "iteration_id": "E001",
        "result": "E001_TRUSTED_INFRASTRUCTURE_READY",
        "release": {
            "tag": release_tag,
            "source_sha": source_sha,
            "immutable_verified_by_workflow": True,
        },
        "roles": rendered_roles,
        "authority": {
            "hardware_test_executed": False,
            "extended_real_executed": False,
            "product_certification_executed": False,
            "product_qualification": "DEFERRED_BY_SCOPE",
            "dut_hil": "DEFERRED_BY_SCOPE",
            "readiness_is_certification": False,
        },
    }
    text = json.dumps(result, sort_keys=True)
    require(not any(token in text for token in FORBIDDEN), "activation preflight attempted a forbidden authority claim")
    return result


def self_test() -> None:
    sha = "1" * 40
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        specs: list[str] = []
        for index, role in enumerate(ROLES):
            report = {
                "schema_version": 1,
                "role": role,
                "source_revision": sha,
                "classification": "READY",
                "runner": {"name": f"runner-{index}", "arch": "X64", "os": "Linux"},
                "checks": [],
                "failure_count": 0,
            }
            path = root / f"{role}.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            specs.append(f"{role}={path}")
        parsed = [load_report(spec) for spec in specs]
        out = aggregate(sha, "v2.3.13", parsed)
        assert out["result"] == "E001_TRUSTED_INFRASTRUCTURE_READY"
        assert set(out["roles"]) == set(ROLES)
        assert out["authority"]["product_qualification"] == "DEFERRED_BY_SCOPE"

        bad = json.loads((root / "audio-target.json").read_text())
        bad["classification"] = "NOT_READY"
        (root / "audio-target.json").write_text(json.dumps(bad), encoding="utf-8")
        try:
            aggregate(sha, "v2.3.13", [load_report(spec) for spec in specs])
        except ValueError:
            pass
        else:
            raise AssertionError("NOT_READY target was accepted")

        bad["classification"] = "READY"
        bad["source_revision"] = "2" * 40
        (root / "audio-target.json").write_text(json.dumps(bad), encoding="utf-8")
        try:
            aggregate(sha, "v2.3.13", [load_report(spec) for spec in specs])
        except ValueError:
            pass
        else:
            raise AssertionError("source drift was accepted")
    print("E001 activation preflight aggregator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha")
    parser.add_argument("--release-tag")
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = aggregate(args.source_sha or "", args.release_tag or "", [load_report(spec) for spec in args.report])
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
