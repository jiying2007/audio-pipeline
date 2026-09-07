#!/usr/bin/env python3
"""Aggregate trusted-runner readiness for E001 without granting hardware/PQ authority."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/program/iterations/E001-readiness.json"
WORKFLOW = ROOT / ".github/workflows/e001-activation-preflight.yml"
ROLES = (
    "audio-validation",
    "audio-builder",
    "audio-target",
    "certification-archive",
)
READY_RESULT = "E001_TRUSTED_INFRASTRUCTURE_READY"
NOT_READY_RESULT = "E001_TRUSTED_INFRASTRUCTURE_NOT_READY"
FORBIDDEN = {
    "PRODUCT_CERTIFIED",
    "PRODUCT_QUALIFICATION_PASS",
    "DUT_HIL_PASS",
    "HARDWARE_VALIDATED",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    require(path.is_file(), f"missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_committed_contract() -> None:
    contract = load_json(CONTRACT)
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "E001",
            "E001 activation contract identity")
    require(contract.get("state") == "DEFERRED" and contract.get("lane") == "external",
            "E001 activation must remain external and deferred")
    baseline = contract.get("software_baseline") or {}
    require(baseline == {
        "release": "v2.3.13",
        "source_sha": "d70e18b12b899a67fa20adf3d281d10b901afbe8",
        "immutable_required": True,
    }, "E001 activation preflight must bind the immutable v2.3.13 baseline")

    static = contract.get("required_static_contracts") or {}
    require(static.get("activation_preflight") == ".github/workflows/e001-activation-preflight.yml",
            "E001 readiness must register the activation preflight workflow")
    require(static.get("trusted_runner_readiness") == ".github/workflows/trusted-runner-readiness.yml",
            "E001 readiness must retain per-role trusted-runner readiness")

    requirements = contract.get("activation_requirements") or {}
    require(requirements.get("trusted_runner_roles") == list(ROLES),
            "E001 activation trusted runner role set/order drift")
    require(requirements.get("activation_preflight_result") == READY_RESULT,
            "E001 activation preflight result drift")
    require(requirements.get("manual_activation_preflight_only") is True,
            "E001 activation preflight must remain manual-only")
    require(requirements.get("manual_product_certification_only") is True,
            "E001 Product Certification must remain manual-only")
    require(requirements.get("exact_source_sha_required") is True and
            requirements.get("immutable_release_binding_required") is True,
            "E001 activation must require exact immutable release identity")
    require(int(requirements.get("minimum_certification_soak_hours", 0)) >= 72,
            "E001 certification soak minimum regressed")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    require("on:\n  workflow_dispatch:" in workflow,
            "E001 activation preflight must expose manual workflow_dispatch")
    for forbidden_trigger in ("\n  push:", "\n  pull_request:", "\n  schedule:", "\n  repository_dispatch:"):
        require(forbidden_trigger not in workflow,
                f"E001 activation preflight acquired forbidden automatic trigger: {forbidden_trigger.strip()}")
    require("gh workflow run" not in workflow and "repository_dispatch" not in workflow,
            "E001 activation preflight may not trigger HIL/Extended Real/Product Certification")
    require("HIL_ENABLED: ${{ vars.HIL_ENABLED }}" in workflow and
            "EXTENDED_REAL_ENABLED: ${{ vars.EXTENDED_REAL_ENABLED }}" in workflow and
            "E001 activation requires HIL_ENABLED=true" in workflow and
            "E001 activation requires EXTENDED_REAL_ENABLED=true" in workflow,
            "E001 activation controls must be enabled fail-closed")
    require("source_sha does not match committed E001 software baseline" in workflow and
            "release_tag does not match committed E001 software baseline" in workflow and
            "releases/tags/$RELEASE_TAG" in workflow and "--jq '.immutable'" in workflow,
            "E001 activation preflight must bind exact immutable release identity")
    require("actions/runners?per_page=100" in workflow and
            "E001 trusted runner roles not online" in workflow,
            "E001 activation preflight must fail before allocation when trusted roles are offline")
    for role in ROLES:
        require(f"runs-on: [self-hosted, linux, {role}]" in workflow,
                f"E001 activation preflight missing trusted runner label: {role}")
    require(workflow.count("ref: ${{ needs.resolve.outputs.sha }}") >= 4,
            "all trusted role checks must execute the exact immutable release source")
    require("ref: ${{ github.sha }}" in workflow and
            "--control-source-sha '${{ github.sha }}'" in workflow,
            "aggregate control-plane evidence must bind the current governance source")
    require("--report audio-validation=" in workflow and
            "--report audio-builder=" in workflow and
            "--report audio-target=" in workflow and
            "--report certification-archive=" in workflow,
            "aggregate preflight must consume all four role reports")
    require("Enforce all trusted roles READY" in workflow and
            "e001-activation-evidence" in workflow and "SHA256SUMS" in workflow,
            "aggregate preflight must be sealed and fail closed")
    require("hil_board.py preflight" not in workflow and "target_evidence.py" not in workflow,
            "activation preflight may validate infrastructure but may not execute hardware qualification")

    authority = contract.get("authority_boundary") or {}
    require(authority.get("hardware_collection_performed") is False and
            authority.get("product_qualification") == "DEFERRED_BY_SCOPE" and
            authority.get("dut_hil") == "DEFERRED_BY_SCOPE" and
            authority.get("readiness_is_certification") is False,
            "E001 activation readiness cannot acquire hardware/PQ authority")


def load_report(spec: str) -> tuple[str, dict]:
    role, sep, raw_path = spec.partition("=")
    require(bool(sep) and role in ROLES and bool(raw_path),
            "report must be role=path for a registered role")
    path = Path(raw_path)
    require(path.is_file(), f"missing readiness report: {path}")
    return role, json.loads(path.read_text(encoding="utf-8"))


def aggregate(
    source_sha: str,
    release_tag: str,
    control_source_sha: str,
    reports: list[tuple[str, dict]],
) -> dict:
    require(re.fullmatch(r"[0-9a-fA-F]{40}", source_sha) is not None,
            "source_sha must be exact 40-hex")
    require(re.fullmatch(r"[0-9a-fA-F]{40}", control_source_sha) is not None,
            "control_source_sha must be exact 40-hex")
    source_sha = source_sha.lower()
    control_source_sha = control_source_sha.lower()
    require(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release_tag) is not None,
            "release_tag must be semantic vX.Y.Z")
    require(len(reports) == len(ROLES), "all four trusted runner roles are required")
    require({role for role, _ in reports} == set(ROLES),
            "readiness roles must be complete and unique")

    rendered_roles: dict[str, dict] = {}
    all_ready = True
    for role, report in reports:
        require(report.get("schema_version") == 1, f"{role}: unsupported readiness schema")
        require(report.get("role") == role, f"{role}: report role mismatch")
        require(report.get("source_revision") == source_sha, f"{role}: source revision drift")
        classification = report.get("classification")
        require(classification in {"READY", "NOT_READY"}, f"{role}: invalid readiness classification")
        failure_count = report.get("failure_count")
        require(isinstance(failure_count, int) and failure_count >= 0,
                f"{role}: invalid failure_count")
        require((classification == "READY") == (failure_count == 0),
                f"{role}: classification/failure_count inconsistency")
        runner = report.get("runner") or {}
        require(bool(runner.get("name")), f"{role}: runner identity missing")
        require(runner.get("os") == "Linux", f"{role}: runner OS must be Linux")
        rendered_roles[role] = {
            "classification": classification,
            "failure_count": failure_count,
            "runner": {
                "name": runner["name"],
                "arch": runner.get("arch"),
                "os": runner["os"],
            },
        }
        all_ready = all_ready and classification == "READY"

    result = {
        "schema_version": 1,
        "iteration_id": "E001",
        "result": READY_RESULT if all_ready else NOT_READY_RESULT,
        "release": {
            "tag": release_tag,
            "source_sha": source_sha,
            "immutable_verified_by_workflow": True,
        },
        "control_plane": {
            "source_sha": control_source_sha,
            "activation_controls_verified_by_workflow": True,
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
    require(not any(token in text for token in FORBIDDEN),
            "activation preflight attempted a forbidden authority claim")
    return result


def self_test() -> None:
    validate_committed_contract()
    sha = "1" * 40
    control_sha = "3" * 40
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
        out = aggregate(sha, "v2.3.13", control_sha, parsed)
        assert out["result"] == READY_RESULT
        assert set(out["roles"]) == set(ROLES)
        assert out["control_plane"]["source_sha"] == control_sha
        assert out["authority"]["product_qualification"] == "DEFERRED_BY_SCOPE"

        bad = json.loads((root / "audio-target.json").read_text())
        bad["classification"] = "NOT_READY"
        bad["failure_count"] = 1
        (root / "audio-target.json").write_text(json.dumps(bad), encoding="utf-8")
        out = aggregate(sha, "v2.3.13", control_sha, [load_report(spec) for spec in specs])
        assert out["result"] == NOT_READY_RESULT
        assert out["roles"]["audio-target"]["failure_count"] == 1

        bad["classification"] = "READY"
        bad["failure_count"] = 0
        bad["source_revision"] = "2" * 40
        (root / "audio-target.json").write_text(json.dumps(bad), encoding="utf-8")
        try:
            aggregate(sha, "v2.3.13", control_sha, [load_report(spec) for spec in specs])
        except ValueError:
            pass
        else:
            raise AssertionError("source drift was accepted")
    print("E001 activation preflight aggregator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha")
    parser.add_argument("--release-tag")
    parser.add_argument("--control-source-sha")
    parser.add_argument("--report", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    validate_committed_contract()
    result = aggregate(
        args.source_sha or "",
        args.release_tag or "",
        args.control_source_sha or "",
        [load_report(spec) for spec in args.report],
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
