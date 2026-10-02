#!/usr/bin/env python3
"""Synthesize S003 downstream-transfer exclusion from frozen public evidence.

No audio is generated and no processor is executed. The review binds terminal
public-family results to the committed test-only stage-prefix semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def stage_semantics(path: Path, expected_sha: str) -> dict:
    actual_sha = git_blob_sha1(path)
    if actual_sha != expected_sha:
        raise ValueError(f"stage-prefix source drift: {actual_sha} != {expected_sha}")
    text = path.read_text(encoding="utf-8")

    # Fail closed on the exact diagnostic stage-mask semantics needed by this
    # review. These anchors are intentionally narrower than a C parser.
    required = [
        'strcmp(profile, "prefix-capture") == 0',
        "cfg->stages = AP_STAGE_HPF;",
        'strcmp(profile, "prefix-bf") == 0',
        "cfg->stages = front;",
        "AP_STAGE_HPF | (channels == 2u ? AP_STAGE_BF : 0u)",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise ValueError(f"stage-prefix semantic anchors missing: {missing}")

    capture = re.search(
        r'else if \(strcmp\(profile, "prefix-capture"\) == 0\) \{\s*'
        r'cfg->stages = AP_STAGE_HPF;\s*\}',
        text,
        re.S,
    )
    if capture is None:
        raise ValueError("prefix-capture is not mechanically HPF-only")

    return {
        "source_path": str(path),
        "git_blob_sha1": actual_sha,
        "prefix_capture_mask": "AP_STAGE_HPF",
        "prefix_capture_hpf_only": True,
        "bf_enabled_at_prefix_capture": False,
        "ns_enabled_at_prefix_capture": False,
        "agc_enabled_at_prefix_capture": False,
        "vad_enabled_at_prefix_capture": False,
        "final_full_pipeline_reached_at_prefix_capture": False,
    }


def public_family_observation(result: dict, *, family: str) -> dict:
    failure = result["mechanical_result"]["FR-S003-MIC-GAIN-DELAY-MISMATCH-V1"]
    if family == "dechorate":
        distribution = failure["first_observable_stage_distribution"]
        total = 11
        severe = failure["stable_subsignature_rooms"]
    elif family == "slr31":
        distribution = failure["first_observable_stage_distribution"]
        total = 8
        severe = failure["reproduced_utterances"]
    else:
        raise ValueError(f"unknown family {family}")

    per_seed = []
    for seed_text, stages in sorted(distribution.items(), key=lambda item: int(item[0])):
        capture_count = int(stages.get("capture", 0))
        severe_count = int(severe[seed_text])
        per_seed.append({
            "seed": int(seed_text),
            "total_cases": total,
            "severe_subsignature_cases": severe_count,
            "first_observable_capture_cases": capture_count,
        })
    return {"family": family, "per_seed": per_seed}


def evaluate(contract: dict, d_result: dict, s_result: dict, m_result: dict, stage: dict) -> dict:
    if contract["authority"] != "CANDIDATE_ZERO_EVIDENCE_SYNTHESIS_ONLY":
        raise ValueError("authority drift")
    if contract["candidate_limit"] != 0 or contract["confirmation_limit"] != 0:
        raise ValueError("candidate/confirmation budget drift")
    if d_result["status"] != "CLOSED_DIAGNOSTIC_ONLY_PARTIAL_SUBSIGNATURE_TRANSFER":
        raise ValueError("dEchorate predecessor status drift")
    if s_result["status"] != "CLOSED_DIAGNOSTIC_SECOND_PUBLIC_FAMILY_REPETITION":
        raise ValueError("SLR31 predecessor status drift")
    if m_result["status"] != "CLOSED_DIAGNOSTIC_MEASUREMENT_DOMAIN_ARTIFACT_EXCLUDED":
        raise ValueError("measurement predecessor status drift")
    if not m_result["mechanical_result"]["measurement_domain_artifact_exclusion_satisfied"]:
        raise ValueError("measurement-domain exclusion must already be satisfied")

    rules = contract["preregistered_evidence_rules"]
    d = public_family_observation(d_result, family="dechorate")
    s = public_family_observation(s_result, family="slr31")

    d_expected = rules["required_dechorate_seeds"]
    s_expected = rules["required_slr31_seeds"]
    if [x["seed"] for x in d["per_seed"]] != d_expected:
        raise ValueError("dEchorate seed drift")
    if [x["seed"] for x in s["per_seed"]] != s_expected:
        raise ValueError("SLR31 seed drift")

    d_min = int(rules["dechorate_min_capture_observations_per_seed"])
    s_min = int(rules["slr31_min_capture_observations_per_seed"])
    d_ok = all(
        row["total_cases"] == int(rules["dechorate_total_per_seed"])
        and row["severe_subsignature_cases"] >= d_min
        and row["first_observable_capture_cases"] >= d_min
        for row in d["per_seed"]
    )
    s_ok = all(
        row["total_cases"] == int(rules["slr31_total_per_seed"])
        and row["severe_subsignature_cases"] >= s_min
        and row["first_observable_capture_cases"] >= s_min
        for row in s["per_seed"]
    )
    semantics_ok = bool(stage["prefix_capture_hpf_only"])
    measurement_ok = bool(
        m_result["mechanical_result"]["measurement_domain_artifact_exclusion_satisfied"]
    )
    satisfied = d_ok and s_ok and semantics_ok and measurement_ok

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": "candidate-zero-evidence-synthesis-only",
        "scoped_failure": contract["scoped_failure"],
        "scoped_subsignature": contract["scoped_subsignature"],
        "public_family_evidence": [d, s],
        "measurement_domain_artifact_exclusion_satisfied": measurement_ok,
        "stage_semantics": stage,
        "downstream_transfer_artifact_exclusion_satisfied": satisfied,
        "reviewed_interpretation": {
            "supported": (
                "The scoped severe subsignature is observable at an HPF-only "
                "capture prefix in both independent public families; BF, NS, "
                "AGC, VAD and final/full-pipeline transfer are therefore not "
                "necessary for the subsignature to be observable."
            ) if satisfied else "Prerequisites are insufficient for downstream-transfer exclusion.",
            "not_supported": [
                "HPF is the causal root cause",
                "BF is the causal root cause",
                "any shipping parameter change",
                "candidate selection",
            ],
        },
        "root_cause_claim_authority": False,
        "candidate_authority": False,
        "shipping_change_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    fixture = (
        'const ap_stage_mask_t front = AP_STAGE_HPF | '
        '(channels == 2u ? AP_STAGE_BF : 0u);\n'
        'if (x) {} else if (strcmp(profile, "prefix-capture") == 0) {\n'
        '    cfg->stages = AP_STAGE_HPF;\n'
        '} else if (strcmp(profile, "prefix-bf") == 0) {\n'
        '    cfg->stages = front;\n'
        '}\n'
    )
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "stage.c"
        path.write_text(fixture, encoding="utf-8")
        semantics = stage_semantics(path, git_blob_sha1(path))
        assert semantics["prefix_capture_hpf_only"] is True
        assert semantics["bf_enabled_at_prefix_capture"] is False
    print("downstream-transfer review self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--dechorate-result", type=Path)
    parser.add_argument("--slr31-result", type=Path)
    parser.add_argument("--measurement-result", type=Path)
    parser.add_argument("--stage-source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (
        args.contract, args.dechorate_result, args.slr31_result,
        args.measurement_result, args.stage_source, args.output,
    )
    if any(value is None for value in required):
        parser.error("all evidence/source/output arguments are required")

    contract = load(args.contract)
    stage = stage_semantics(
        args.stage_source,
        contract["stage_semantics"]["expected_source_sha"],
    )
    result = evaluate(
        contract,
        load(args.dechorate_result),
        load(args.slr31_result),
        load(args.measurement_result),
        stage,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "downstream_transfer_artifact_exclusion_satisfied":
            result["downstream_transfer_artifact_exclusion_satisfied"],
        "public_family_evidence": result["public_family_evidence"],
        "stage_semantics": result["stage_semantics"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
