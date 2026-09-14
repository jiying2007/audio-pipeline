#!/usr/bin/env python3
"""Fail-closed identity and decision helper for one frozen research candidate.

This helper binds a manually produced FROZEN_RESEARCH_CANDIDATE to its exact
Research Optimization artifact and can wrap an offline processor with the
candidate's runtime-safe tuning. It has no shipping, target, HIL, Product
Certification, release, or main-mutation authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID12_RE = re.compile(r"^[0-9a-f]{12}$")
ID16_RE = re.compile(r"^[0-9a-f]{16}$")
TUNING_KEYS = ("aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs")
TUNING_FLAGS = {
    "aec_mu": "--aec-mu",
    "ns_floor": "--ns-floor",
    "agc_target_dbfs": "--agc-target-dbfs",
    "limiter_dbfs": "--limiter-dbfs",
}
EXPECTED_STATUS = "FROZEN_RESEARCH_CANDIDATE"
EXPECTED_NEXT_GATE = "validation-grade-blind"
EXPECTED_AUTHORITY = {
    "shipping_authority": False,
    "hil_authority": False,
    "product_certification_authority": False,
    "automatic_main_mutation": False,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_tuning(raw: dict[str, Any]) -> dict[str, float]:
    if set(raw) != set(TUNING_KEYS):
        raise ValueError("candidate tuning must define exactly the runtime-safe tuning surface")
    tuning = {key: float(raw[key]) for key in TUNING_KEYS}
    if any(not math.isfinite(value) for value in tuning.values()):
        raise ValueError("candidate tuning values must be finite")
    if not 0.0 < tuning["aec_mu"] <= 1.0:
        raise ValueError("aec_mu must be in (0, 1]")
    if not 0.02 <= tuning["ns_floor"] <= 1.0:
        raise ValueError("ns_floor must be in [0.02, 1]")
    if not -60.0 <= tuning["agc_target_dbfs"] <= -1.0:
        raise ValueError("agc_target_dbfs must be in [-60, -1]")
    if not -20.0 <= tuning["limiter_dbfs"] <= -0.1:
        raise ValueError("limiter_dbfs must be in [-20, -0.1]")
    if tuning["agc_target_dbfs"] >= tuning["limiter_dbfs"]:
        raise ValueError("agc_target_dbfs must be below limiter_dbfs")
    return tuning


def tuning_id(tuning: dict[str, float]) -> str:
    payload = json.dumps(tuning, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def research_candidate_id(hypothesis_id: str, source_sha: str,
                          tuning: dict[str, float]) -> str:
    payload = json.dumps({
        "hypothesis_id": hypothesis_id,
        "source_sha": source_sha,
        "tuning": tuning,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def validate_manifest(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version", "status", "next_gate", "research_candidate_id", "candidate_id",
        "source_sha", "hypothesis_id", "tuning", "research_provenance",
        "selection_evidence", "output_authority",
    }
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise ValueError("research candidate manifest fields/schema invalid")
    if manifest["status"] != EXPECTED_STATUS or manifest["next_gate"] != EXPECTED_NEXT_GATE:
        raise ValueError("manifest must describe a frozen candidate awaiting validation-grade-blind")
    source_sha = str(manifest["source_sha"])
    candidate_id = str(manifest["candidate_id"])
    research_id = str(manifest["research_candidate_id"])
    hypothesis_id = str(manifest["hypothesis_id"])
    if not SHA40_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be exact lowercase SHA-40")
    if not ID12_RE.fullmatch(candidate_id) or not ID16_RE.fullmatch(research_id):
        raise ValueError("candidate identities have invalid shape")
    if not hypothesis_id:
        raise ValueError("hypothesis_id required")
    tuning = canonical_tuning(manifest["tuning"])
    if tuning_id(tuning) != candidate_id:
        raise ValueError("candidate_id does not match canonical tuning")
    if research_candidate_id(hypothesis_id, source_sha, tuning) != research_id:
        raise ValueError("research_candidate_id does not match source/hypothesis/tuning")

    provenance = manifest["research_provenance"]
    provenance_keys = {
        "workflow", "run_id", "artifact_id", "artifact_name", "artifact_digest",
        "optimization_result_path", "search_space_path", "search_space_sha256",
    }
    if not isinstance(provenance, dict) or set(provenance) != provenance_keys:
        raise ValueError("research_provenance fields invalid")
    if provenance["workflow"] != "Research Optimization":
        raise ValueError("candidate provenance must come from Research Optimization")
    if type(provenance["run_id"]) is not int or provenance["run_id"] <= 0:
        raise ValueError("research run_id invalid")
    if type(provenance["artifact_id"]) is not int or provenance["artifact_id"] <= 0:
        raise ValueError("research artifact_id invalid")
    if provenance["artifact_name"] != f"research-optimization-{provenance['run_id']}":
        raise ValueError("research artifact name/run mismatch")
    if not SHA256_RE.fullmatch(str(provenance["artifact_digest"])):
        raise ValueError("research artifact digest invalid")
    if provenance["optimization_result_path"] != "research-optimization-out/optimization-result.json":
        raise ValueError("optimization result path drift")
    if not str(provenance["search_space_path"]).startswith("validation/tuning/search-spaces/"):
        raise ValueError("search space path invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(provenance["search_space_sha256"])):
        raise ValueError("search space digest invalid")

    selection = manifest["selection_evidence"]
    if set(selection) != {
        "development_score", "worst_development_unit_score", "generalization_gate_count",
        "gate_violation_count",
    }:
        raise ValueError("selection_evidence fields invalid")
    if not math.isfinite(float(selection["development_score"])) or not math.isfinite(
            float(selection["worst_development_unit_score"])):
        raise ValueError("selection scores must be finite")
    if int(selection["generalization_gate_count"]) < 1:
        raise ValueError("at least one independent generalization gate required")
    if int(selection["gate_violation_count"]) != 0:
        raise ValueError("frozen candidate cannot carry generalization gate violations")

    if manifest["output_authority"] != EXPECTED_AUTHORITY:
        raise ValueError("candidate manifest gained forbidden authority")
    terminal_ids = {str(item["candidate_id"]) for item in registry.get("terminal_candidates", [])}
    if candidate_id in terminal_ids:
        raise ValueError("terminal tuning candidate cannot enter blind qualification")
    forbidden_tiers = set(registry.get("forbidden_optimizer_tiers", []))
    if EXPECTED_NEXT_GATE not in forbidden_tiers:
        raise ValueError("registry no longer excludes blind data from optimizer feedback")
    shipping = registry.get("shipping_baseline", {})
    if shipping.get("frozen") is not True:
        raise ValueError("shipping baseline must remain frozen")
    return {
        "candidate_id": candidate_id,
        "research_candidate_id": research_id,
        "source_sha": source_sha,
        "artifact_id": provenance["artifact_id"],
        "artifact_digest": provenance["artifact_digest"],
    }


def verify_optimization_result(manifest: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("schema_version") != 1:
        raise ValueError("optimization result schema invalid")
    if result.get("decision") != "FREEZE_RESEARCH_CANDIDATE":
        raise ValueError("research result did not freeze a candidate")
    if result.get("status") != EXPECTED_STATUS or result.get("next_gate") != EXPECTED_NEXT_GATE:
        raise ValueError("research result status/next_gate mismatch")
    if result.get("source_sha") != manifest["source_sha"]:
        raise ValueError("research source SHA mismatch")
    if result.get("hypothesis_id") != manifest["hypothesis_id"]:
        raise ValueError("research hypothesis mismatch")
    selected = result.get("selected")
    if not isinstance(selected, dict):
        raise ValueError("optimization selected record missing")
    for key in ("candidate_id", "research_candidate_id"):
        if selected.get(key) != manifest[key]:
            raise ValueError(f"optimization selected {key} mismatch")
    if canonical_tuning(selected.get("tuning", {})) != canonical_tuning(manifest["tuning"]):
        raise ValueError("optimization tuning mismatch")
    evidence = manifest["selection_evidence"]
    if float(selected.get("development_score")) != float(evidence["development_score"]):
        raise ValueError("development score mismatch")
    if float(selected.get("worst_development_unit_score")) != float(evidence["worst_development_unit_score"]):
        raise ValueError("worst development unit score mismatch")
    gates = result.get("generalization_gates")
    violations = result.get("gate_violations")
    if not isinstance(gates, list) or len(gates) != int(evidence["generalization_gate_count"]):
        raise ValueError("generalization gate count mismatch")
    if not isinstance(violations, list) or len(violations) != int(evidence["gate_violation_count"]):
        raise ValueError("generalization violation count mismatch")
    search = result.get("search_space", {})
    provenance = manifest["research_provenance"]
    if search.get("path") != provenance["search_space_path"] or search.get("sha256") != provenance["search_space_sha256"]:
        raise ValueError("search-space provenance mismatch")
    authority = result.get("output_authority", {})
    for key, value in EXPECTED_AUTHORITY.items():
        if authority.get(key) is not value:
            raise ValueError(f"optimization result gained forbidden authority: {key}")
    if result.get("automatic_shipping_promotion") is not False:
        raise ValueError("optimization result gained shipping promotion authority")
    if result.get("automatic_main_mutation") is not False:
        raise ValueError("optimization result gained main mutation authority")


def write_wrapper(path: Path, processor: Path, tuning: dict[str, float]) -> None:
    flags: list[str] = []
    for key in TUNING_KEYS:
        flags += [TUNING_FLAGS[key], repr(float(tuning[key]))]
    script = [
        "#!/usr/bin/env python3",
        "import os, sys",
        f"processor = {str(processor.resolve())!r}",
        f"prefix = {flags!r}",
        "os.execv(processor, [processor] + prefix + sys.argv[1:])",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(script), encoding="utf-8")
    path.chmod(0o700)


def seal_identity(manifest: dict[str, Any], optimization_result: dict[str, Any],
                  processor: Path, wrapper: Path, output: Path) -> dict[str, Any]:
    verify_optimization_result(manifest, optimization_result)
    if not processor.is_file():
        raise ValueError(f"processor missing: {processor}")
    tuning = canonical_tuning(manifest["tuning"])
    write_wrapper(wrapper, processor, tuning)
    result = {
        "schema_version": 1,
        "authority": "non-shipping-research-candidate-blind-qualification",
        "status": EXPECTED_STATUS,
        "next_gate": EXPECTED_NEXT_GATE,
        "research_candidate_id": manifest["research_candidate_id"],
        "candidate_id": manifest["candidate_id"],
        "source_sha": manifest["source_sha"],
        "hypothesis_id": manifest["hypothesis_id"],
        "tuning": tuning,
        "research_provenance": manifest["research_provenance"],
        "processor_sha256": sha256_file(processor),
        "output_authority": EXPECTED_AUTHORITY,
        "rule": (
            "This identity may only execute visible+blind validation for one frozen research candidate. "
            "It cannot rank, rescue, mutate, promote, run target/HIL, certify product, or change shipping."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def classify(identity: dict[str, Any], visible: dict[str, Any] | None,
             blind: dict[str, Any] | None, output: Path) -> tuple[dict[str, Any], int]:
    if identity.get("authority") != "non-shipping-research-candidate-blind-qualification":
        raise ValueError("invalid qualification identity authority")

    visible_result = None if visible is None else visible.get("validation_result")
    blind_result = None if blind is None else blind.get("validation_result")
    complete_results = {"PASS", "FAIL"}

    if visible_result not in complete_results:
        decision = "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
        next_gate = EXPECTED_NEXT_GATE
        terminal = False
        failed_stage = "visible-evidence-incomplete"
        rc = 2
    elif visible_result == "FAIL":
        decision = "BLIND_REJECTED_NON_SHIPPING"
        next_gate = None
        terminal = True
        failed_stage = "visible-validation"
        rc = 1
    elif blind_result not in complete_results:
        decision = "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
        next_gate = EXPECTED_NEXT_GATE
        terminal = False
        failed_stage = "blind-evidence-incomplete"
        rc = 2
    elif blind_result == "FAIL":
        decision = "BLIND_REJECTED_NON_SHIPPING"
        next_gate = None
        terminal = True
        failed_stage = "blind-holdout"
        rc = 1
    else:
        decision = "BLIND_QUALIFIED_NON_SHIPPING"
        next_gate = "target-resource"
        terminal = False
        failed_stage = None
        rc = 0

    result = {
        "schema_version": 1,
        "authority": "non-shipping-research-candidate-blind-qualification",
        "decision": decision,
        "research_candidate_id": identity["research_candidate_id"],
        "candidate_id": identity["candidate_id"],
        "source_sha": identity["source_sha"],
        "tuning": identity["tuning"],
        "next_gate": next_gate,
        "terminal_candidate": terminal,
        "failed_stage": failed_stage,
        "visible_result": visible_result,
        "blind_result": blind_result,
        "shipping_authority": False,
        "target_execution_authority": False,
        "hil_authority": False,
        "product_certification_authority": False,
        "automatic_main_mutation": False,
        "automatic_promotion": False,
        "rule": (
            "PASS+PASS only admits this exact frozen candidate to separate target-resource review; "
            "an explicit validation FAIL is terminal for this tuning identity; missing or invalid "
            "evidence is INCOMPLETE and keeps the candidate frozen. Neither outcome changes shipping."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result, rc


def self_test() -> None:
    tuning = {"aec_mu": 0.22, "ns_floor": 0.10, "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0}
    candidate_id = tuning_id(tuning)
    source_sha = "a" * 40
    hypothesis = "fixture-hypothesis"
    research_id = research_candidate_id(hypothesis, source_sha, canonical_tuning(tuning))
    manifest = {
        "schema_version": 1,
        "status": EXPECTED_STATUS,
        "next_gate": EXPECTED_NEXT_GATE,
        "research_candidate_id": research_id,
        "candidate_id": candidate_id,
        "source_sha": source_sha,
        "hypothesis_id": hypothesis,
        "tuning": tuning,
        "research_provenance": {
            "workflow": "Research Optimization", "run_id": 1, "artifact_id": 2,
            "artifact_name": "research-optimization-1", "artifact_digest": "sha256:" + "b" * 64,
            "optimization_result_path": "research-optimization-out/optimization-result.json",
            "search_space_path": "validation/tuning/search-spaces/fixture.json",
            "search_space_sha256": "c" * 64,
        },
        "selection_evidence": {
            "development_score": 0.1, "worst_development_unit_score": 0.05,
            "generalization_gate_count": 2, "gate_violation_count": 0,
        },
        "output_authority": dict(EXPECTED_AUTHORITY),
    }
    registry = {
        "shipping_baseline": {"frozen": True},
        "forbidden_optimizer_tiers": ["validation-grade-blind", "product-certified"],
        "terminal_candidates": [{"candidate_id": "deadbeef0000"}],
    }
    validate_manifest(manifest, registry)
    optimization = {
        "schema_version": 1, "decision": "FREEZE_RESEARCH_CANDIDATE",
        "status": EXPECTED_STATUS, "next_gate": EXPECTED_NEXT_GATE,
        "source_sha": source_sha, "hypothesis_id": hypothesis,
        "selected": {
            "candidate_id": candidate_id, "research_candidate_id": research_id,
            "tuning": tuning, "development_score": 0.1, "worst_development_unit_score": 0.05,
        },
        "generalization_gates": [{}, {}], "gate_violations": [],
        "search_space": {"path": "validation/tuning/search-spaces/fixture.json", "sha256": "c" * 64},
        "output_authority": {**EXPECTED_AUTHORITY, "candidate_status": EXPECTED_STATUS,
                             "next_gate": EXPECTED_NEXT_GATE},
        "automatic_shipping_promotion": False, "automatic_main_mutation": False,
    }
    verify_optimization_result(manifest, optimization)
    bad_registry = json.loads(json.dumps(registry))
    bad_registry["terminal_candidates"].append({"candidate_id": candidate_id})
    try:
        validate_manifest(manifest, bad_registry)
    except ValueError as exc:
        assert "terminal tuning" in str(exc)
    else:
        raise AssertionError("terminal candidate entered blind qualification")
    with tempfile.TemporaryDirectory(prefix="ap-research-blind-") as temporary:
        root = Path(temporary)
        processor = root / "processor"
        processor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        processor.chmod(0o700)
        identity = seal_identity(manifest, optimization, processor, root / "wrapper", root / "identity.json")
        assert "--ns-floor" in (root / "wrapper").read_text(encoding="utf-8")
        passed, rc = classify(identity, {"validation_result": "PASS"}, {"validation_result": "PASS"}, root / "pass.json")
        assert rc == 0 and passed["decision"] == "BLIND_QUALIFIED_NON_SHIPPING"
        assert passed["next_gate"] == "target-resource" and passed["terminal_candidate"] is False

        rejected, rc = classify(identity, {"validation_result": "PASS"}, {"validation_result": "FAIL"}, root / "reject.json")
        assert rc == 1 and rejected["decision"] == "BLIND_REJECTED_NON_SHIPPING"
        assert rejected["terminal_candidate"] is True and rejected["failed_stage"] == "blind-holdout"

        visible_rejected, rc = classify(
            identity, {"validation_result": "FAIL"}, None, root / "visible-reject.json"
        )
        assert rc == 1 and visible_rejected["terminal_candidate"] is True
        assert visible_rejected["failed_stage"] == "visible-validation"

        missing_visible, rc = classify(identity, None, None, root / "missing-visible.json")
        assert rc == 2 and missing_visible["decision"] == "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
        assert missing_visible["terminal_candidate"] is False
        assert missing_visible["next_gate"] == EXPECTED_NEXT_GATE
        assert missing_visible["failed_stage"] == "visible-evidence-incomplete"

        missing_blind, rc = classify(
            identity, {"validation_result": "PASS"}, None, root / "missing-blind.json"
        )
        assert rc == 2 and missing_blind["decision"] == "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING"
        assert missing_blind["terminal_candidate"] is False
        assert missing_blind["next_gate"] == EXPECTED_NEXT_GATE
        assert missing_blind["failed_stage"] == "blind-evidence-incomplete"

        invalid_visible, rc = classify(
            identity, {"validation_result": "ERROR"}, {"validation_result": "PASS"}, root / "invalid-visible.json"
        )
        assert rc == 2 and invalid_visible["terminal_candidate"] is False
        assert invalid_visible["failed_stage"] == "visible-evidence-incomplete"
    print("research candidate blind helper self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--optimization-result", type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--wrapper", type=Path)
    parser.add_argument("--identity-output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--seal-identity", action="store_true")
    parser.add_argument("--classify", action="store_true")
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--visible-report", type=Path)
    parser.add_argument("--blind-report", type=Path)
    parser.add_argument("--qualification-output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.classify:
        if args.identity is None or args.qualification_output is None:
            parser.error("--classify requires --identity and --qualification-output")
        identity = load_json(args.identity)
        visible = load_json(args.visible_report) if args.visible_report and args.visible_report.is_file() else None
        blind = load_json(args.blind_report) if args.blind_report and args.blind_report.is_file() else None
        result, rc = classify(identity, visible, blind, args.qualification_output)
        print(json.dumps(result, sort_keys=True))
        return rc
    if args.manifest is None or args.registry is None:
        parser.error("--manifest and --registry are required")
    manifest = load_json(args.manifest)
    registry = load_json(args.registry)
    summary = validate_manifest(manifest, registry)
    if args.check:
        if args.optimization_result is not None:
            verify_optimization_result(manifest, load_json(args.optimization_result))
        print(json.dumps({"result": "PASS", **summary}, sort_keys=True))
    if args.seal_identity:
        required = (args.optimization_result, args.processor, args.wrapper, args.identity_output)
        if any(item is None for item in required):
            parser.error("--seal-identity requires optimization result, processor, wrapper and identity output")
        result = seal_identity(
            manifest, load_json(args.optimization_result), args.processor, args.wrapper, args.identity_output
        )
        print(json.dumps(result, sort_keys=True))
    if not args.check and not args.seal_identity:
        parser.error("choose --check and/or --seal-identity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
