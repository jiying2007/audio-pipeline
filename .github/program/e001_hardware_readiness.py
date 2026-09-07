#!/usr/bin/env python3
"""Validate software-side prerequisites for future E001 hardware activation.

This tool is deliberately not a HIL runner and not a Product Qualification authority.
It proves only that the committed contracts preserve the boundary between the current
immutable software baseline and future trusted-runner / real-DUT work.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/program/iterations/E001-readiness.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def text(path: str) -> str:
    p = ROOT / path
    require(p.is_file(), f"missing required file: {path}")
    return p.read_text(encoding="utf-8")


def load(path: str) -> dict:
    return json.loads(text(path))


def validate_deferred_evidence(evidence: dict, baseline: dict, minimum: int) -> None:
    require(set(evidence) == {
        "schema_version", "iteration_id", "state", "evidence_kind", "main_sha",
        "workflow_run_id", "workflow_run_number", "workflow_conclusion", "artifact_id",
        "artifact_digest", "result", "configuration", "static_contracts",
        "software_baseline", "authority_boundary", "interpretation",
    }, "E001 deferred evidence unknown/missing fields")
    require(evidence["schema_version"] == 1 and evidence["iteration_id"] == "E001" and
            evidence["state"] == "DEFERRED" and
            evidence["evidence_kind"] == "software-side-hardware-activation-readiness",
            "E001 deferred evidence identity")
    require(evidence["main_sha"] == "06e9c30ef2d86c4a9291ecf1d38fc778264f7d6f" and
            evidence["workflow_run_id"] == 34078425136 and
            evidence["workflow_run_number"] == 7 and
            evidence["workflow_conclusion"] == "success" and
            evidence["artifact_id"] == 10002861733 and
            evidence["artifact_digest"] ==
            "sha256:630e6c989a8e5bf2bbaa8a64c4f60c5dd26219b896ec4c92e5f1be772a15a5c1",
            "E001 deferred evidence must bind the verified main execution")
    require(evidence["result"] == "E001_DEFERRED_INFRASTRUCTURE_DISABLED" and
            evidence["configuration"] == {"hil_enabled": False, "extended_real_enabled": False} and
            evidence["static_contracts"] == "PASS",
            "E001 deferred evidence result/configuration drift")
    require(evidence["software_baseline"] == {
                "release": baseline["release"],
                "source_sha": baseline["source_sha"],
                "minimum_certification_soak_hours": minimum,
            }, "E001 deferred evidence baseline drift")
    require(evidence["authority_boundary"] == {
                "hardware_test_executed": False,
                "product_certification_executed": False,
                "product_qualification": "DEFERRED_BY_SCOPE",
                "dut_hil": "DEFERRED_BY_SCOPE",
                "readiness_is_certification": False,
                "shipping_source_changed": False,
                "release_created": False,
            }, "E001 deferred evidence cannot acquire certification authority")
    require(bool(evidence["interpretation"]), "E001 deferred evidence interpretation")


def validate_static(contract: dict) -> dict:
    require(contract["schema_version"] == 1 and contract["iteration_id"] == "E001",
            "E001 readiness identity")
    require(contract["phase"] == "external-hardware-activation-readiness" and
            contract["state"] == "DEFERRED" and contract["lane"] == "external",
            "E001 readiness must remain external and deferred")

    baseline = contract["software_baseline"]
    require(baseline == {
        "release": "v2.3.13",
        "source_sha": "d70e18b12b899a67fa20adf3d281d10b901afbe8",
        "immutable_required": True,
    }, "E001 readiness must bind the current immutable software baseline")

    plan = load("docs/program/plan.json")
    require(plan["phase"] == "software-public-data" and
            plan["product_qualification"] == "DEFERRED_BY_SCOPE" and
            plan["hardware_collection"] is False and plan["auto_promote"] is False,
            "program must preserve the software/public-data authority boundary")
    require(plan["baseline"]["software_release"] == baseline["release"] and
            plan["baseline"]["source_sha"] == baseline["source_sha"],
            "E001 readiness baseline must match the committed program baseline")
    tasks = {item["id"]: item for item in plan["tasks"]}
    e001 = tasks["E001"]
    require(e001["status"] == "DEFERRED" and e001["lane"] == "external" and
            e001["handler"] is None,
            "E001 may not become executable through software readiness")
    require(e001["contract"] in (None, "docs/program/iterations/E001-readiness.json"),
            "E001 may bind only the deferred readiness contract")

    hil = text(".github/workflows/hil-soak.yml")
    require("types: [hil-post-release]" in hil and
            "HIL_REQUIRED_BUT_DISABLED" in hil and
            "HIL_ENABLED" in hil and
            "exit 1" in hil,
            "HIL control plane must fail closed when disabled")
    require("runs-on: [self-hosted, linux, audio-target]" in hil,
            "HIL must require the trusted audio-target runner")
    require("certification-72h) seconds=259200" in hil,
            "HIL must preserve the 72-hour certification tier")

    ext_auto = text(".github/workflows/extended-real-automation.yml")
    require("types: [extended-real-post-release]" in ext_auto and
            "EXTENDED_REAL_REQUIRED_BUT_DISABLED" in ext_auto and
            "EXTENDED_REAL_ENABLED" in ext_auto and
            "exit 1" in ext_auto,
            "Extended Real control plane must fail closed when disabled")
    ext_validation = text(".github/workflows/validation-extended-real.yml")
    require("runs-on: [self-hosted, linux, audio-validation]" in ext_validation,
            "Extended Real validation must require audio-validation runner")
    require("source_sha must be a 40-character commit SHA" in ext_validation,
            "Extended Real must bind an exact source SHA")

    readiness = text(".github/workflows/trusted-runner-readiness.yml")
    for role in ("audio-validation", "audio-builder", "audio-target", "certification-archive"):
        require(role in readiness, f"trusted readiness missing role: {role}")
    for label in (
        "runs-on: [self-hosted, linux, audio-validation]",
        "runs-on: [self-hosted, linux, audio-builder]",
        "runs-on: [self-hosted, linux, audio-target]",
        "runs-on: [self-hosted, linux, certification-archive]",
    ):
        require(label in readiness, f"trusted readiness missing runner boundary: {label}")

    certification = text(".github/workflows/product-certification.yml")
    require("workflow_dispatch:" in certification and
            "repository_dispatch:" not in certification and
            "schedule:" not in certification,
            "Product Certification must remain manual-only")
    require("source_sha must be a 40-character commit SHA" in certification and
            "policy is not shipping_approved" in certification,
            "Product Certification must require exact source and shipping-approved policy")
    require("release_tag:" in certification and
            "git cat-file -t \"$RELEASE_TAG\"" in certification and
            "gh api \"$api\" --jq '.immutable'" in certification and
            "'type': 'release-identity'" in certification and
            "record['evidence_manifest_sha256'] = manifest_sha" in certification and
            "schema-unknown top-level fields" in certification and
            "record['release'] = release" not in certification,
            "Product Certification must bind immutable Release identity through schema-compatible evidence")
    record_schema = load("certification/record.schema.json")
    require(record_schema.get("additionalProperties") is False and
            "release" not in record_schema.get("properties", {}),
            "v4 record schema must stay closed and must not acquire an ad-hoc release field")
    require("runs-on: [self-hosted, linux, audio-builder]" in certification and
            "runs-on: [self-hosted, linux, audio-target]" in certification,
            "Product Certification must use trusted shipping builder and DUT target")

    policy = load("certification/policies/cortex-a32-low-shipping.json")
    minimum = int(contract["activation_requirements"]["minimum_certification_soak_hours"])
    require(policy["shipping_approved"] is True and
            policy["sku"] == "cortex-a32-low" and
            float(policy["min_soak_hours"]) >= minimum,
            "shipping policy must remain explicitly approved with >=72h soak")

    post = text("scripts/post_release_status.py")
    require("BLOCKED_RUNNER" in post and "BLOCKED_CONFIG" in post and
            "disabled HIL post-release gate unexpectedly succeeded" in post and
            "disabled Extended Real post-release gate unexpectedly succeeded" in post,
            "post-release status must reject false success while infrastructure is disabled")

    observed = contract["observed_deferred_state"]
    require(observed["hil_post_release_run_id"] == 34070991028 and
            observed["hil_control_result"] == "HIL_REQUIRED_BUT_DISABLED" and
            observed["extended_real_post_release_run_id"] == 34070991134 and
            observed["extended_real_control_result"] == "EXTENDED_REAL_REQUIRED_BUT_DISABLED",
            "observed E001 deferred evidence identity")

    evidence_path = contract.get("deferred_evidence_file")
    require(evidence_path == "docs/program/iterations/E001-deferred-evidence.json",
            "E001 readiness must bind the reviewed deferred evidence file")
    validate_deferred_evidence(load(evidence_path), baseline, minimum)

    authority = contract["authority_boundary"]
    require(authority == {
        "shipping_source_changed": False,
        "software_candidate_promoted": False,
        "release_created": False,
        "hardware_collection_performed": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "dut_hil": "DEFERRED_BY_SCOPE",
        "readiness_is_certification": False,
    }, "readiness contract cannot acquire hardware/product authority")

    return {
        "static_contracts": "PASS",
        "deferred_evidence": "PASS",
        "software_release": baseline["release"],
        "software_source_sha": baseline["source_sha"],
        "minimum_certification_soak_hours": minimum,
        "product_qualification": "DEFERRED_BY_SCOPE",
        "dut_hil": "DEFERRED_BY_SCOPE",
    }


def classify(hil_enabled: str, extended_enabled: str) -> str:
    hil = hil_enabled.strip().lower() == "true"
    ext = extended_enabled.strip().lower() == "true"
    if not hil and not ext:
        return "E001_DEFERRED_INFRASTRUCTURE_DISABLED"
    if hil and ext:
        return "E001_CONFIGURED_REQUIRES_TRUSTED_RUNNER_READINESS"
    return "E001_PARTIAL_CONFIGURATION_REQUIRES_COMPLETION"


def build(contract: dict, hil_enabled: str, extended_enabled: str) -> dict:
    static = validate_static(contract)
    result = classify(hil_enabled, extended_enabled)
    require(result in contract["allowed_readiness_results"], "unregistered readiness result")
    rendered = {
        "schema_version": 1,
        "iteration_id": "E001",
        "result": result,
        "static": static,
        "configuration": {
            "hil_enabled": hil_enabled.strip().lower() == "true",
            "extended_real_enabled": extended_enabled.strip().lower() == "true",
        },
        "authority": {
            "hardware_test_executed": False,
            "product_certification_executed": False,
            "product_qualification": "DEFERRED_BY_SCOPE",
            "dut_hil": "DEFERRED_BY_SCOPE",
        },
    }
    forbidden = set(contract["forbidden_claims"])
    require(result not in forbidden and not forbidden.intersection(static.values()),
            "readiness output attempted a forbidden certification claim")
    return rendered


def self_test() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    validate_static(contract)
    assert classify("", "") == "E001_DEFERRED_INFRASTRUCTURE_DISABLED"
    assert classify("true", "") == "E001_PARTIAL_CONFIGURATION_REQUIRES_COMPLETION"
    assert classify("", "true") == "E001_PARTIAL_CONFIGURATION_REQUIRES_COMPLETION"
    assert classify("true", "true") == "E001_CONFIGURED_REQUIRES_TRUSTED_RUNNER_READINESS"
    for h, e in (("", ""), ("true", ""), ("", "true"), ("true", "true")):
        out = build(contract, h, e)
        assert out["authority"]["hardware_test_executed"] is False
        assert out["authority"]["product_certification_executed"] is False
        assert out["authority"]["product_qualification"] == "DEFERRED_BY_SCOPE"
        assert out["static"]["deferred_evidence"] == "PASS"
    evidence = load(contract["deferred_evidence_file"])
    bad = copy.deepcopy(evidence)
    bad["authority_boundary"]["product_qualification"] = "PASS"
    try:
        validate_deferred_evidence(bad, contract["software_baseline"], 72)
    except ValueError:
        pass
    else:
        raise AssertionError("E001 false Product Qualification evidence was accepted")
    bad = copy.deepcopy(evidence)
    bad["artifact_digest"] = "sha256:" + "0" * 64
    try:
        validate_deferred_evidence(bad, contract["software_baseline"], 72)
    except ValueError:
        pass
    else:
        raise AssertionError("E001 evidence digest drift was accepted")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "result.json"
        p.write_text(json.dumps(build(contract, "", "")), encoding="utf-8")
        assert "PRODUCT_CERTIFIED" not in p.read_text(encoding="utf-8")
    print("E001 hardware readiness self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--hil-enabled", default=os.getenv("HIL_ENABLED", ""))
    parser.add_argument("--extended-real-enabled", default=os.getenv("EXTENDED_REAL_ENABLED", ""))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    result = build(contract, args.hil_enabled, args.extended_enabled if hasattr(args, 'extended_enabled') else args.extended_real_enabled)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
