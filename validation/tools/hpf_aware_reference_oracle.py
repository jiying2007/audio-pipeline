#!/usr/bin/env python3
"""HPF-aware reference oracle for the S003 mic-mismatch severe subsignature.

Candidate-zero only. This tool compares the existing raw-clean SI-SDR target
with a clean reference passed through the exact same HPF-only stage. It also
checks whether changing only the right channel can affect the HPF-only output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import run_validation_engine as engine
from build_slr31_subsig_transfer_corpus import (
    RATE,
    TARGET_SAMPLES,
    decode_flac,
    materialize_length,
    normalize,
    select_microset,
    source_record,
)
from build_validation_corpus import delayed, interleave, mix, noise, rotate, scale, write_pcm

PROFILE = "prefix-capture"


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def parse_trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def invoke_prefix(
    processor: Path,
    samples: list[int],
    channels: int,
    work: Path,
    name: str,
) -> tuple[list[int], int]:
    input_path = work / f"{name}-in.pcm"
    output_path = work / f"{name}-out.pcm"
    metrics_path = work / f"{name}-metrics.jsonl"
    write_pcm(input_path, samples)
    subprocess.run(
        [
            str(processor),
            "--sample-rate", str(RATE),
            "--mic-channels", str(channels),
            "--metrics-jsonl", str(metrics_path),
            "--capture-profile", PROFILE,
            "--capture-only",
            str(input_path),
            str(output_path),
        ],
        check=True,
    )
    output = [int(x) for x in engine.read_raw_array(output_path)]
    trace = parse_trace(metrics_path)
    if not trace:
        raise ValueError(f"{name}: processor metrics trace missing")
    latency_ms = int(trace[0].get("algorithmic_latency_ms", -1))
    if latency_ms < 0:
        raise ValueError(f"{name}: invalid latency")
    return output, latency_ms * RATE // 1000


def metric_pair(
    clean: list[int],
    left: list[int],
    clean_hpf: list[int],
    mismatch_hpf: list[int],
    output_latency_samples: int,
) -> dict:
    input_sdr, input_alignment = engine.aligned_si_sdr(clean, left, RATE, 0)
    current_sdr, current_alignment = engine.aligned_si_sdr(
        clean, mismatch_hpf, RATE, output_latency_samples
    )
    hpf_aware_sdr, hpf_alignment = engine.aligned_si_sdr(
        clean_hpf, mismatch_hpf, RATE, 0
    )
    if input_sdr is None or current_sdr is None or hpf_aware_sdr is None:
        raise ValueError("SI-SDR oracle metric unavailable")
    return {
        "input_source_si_sdr_db": float(input_sdr),
        "current_output_si_sdr_db": float(current_sdr),
        "hpf_aware_output_si_sdr_db": float(hpf_aware_sdr),
        "current_near_si_sdr_improvement_db": float(current_sdr - input_sdr),
        "hpf_aware_quality_delta_db": float(hpf_aware_sdr - input_sdr),
        "input_alignment_samples": int(input_alignment),
        "current_output_alignment_samples": int(current_alignment),
        "hpf_aware_alignment_samples": int(hpf_alignment),
    }


def classify(metrics: dict, outputs_identical: bool, limit: float) -> dict:
    current_severe = float(metrics["current_near_si_sdr_improvement_db"]) < limit
    aware_severe = float(metrics["hpf_aware_quality_delta_db"]) < limit
    artifact_case = current_severe and not aware_severe and outputs_identical
    return {
        "current_severe": current_severe,
        "hpf_aware_severe": aware_severe,
        "right_channel_change_affects_prefix_capture": not outputs_identical,
        "reference_metric_artifact_case": artifact_case,
    }


def run(
    source_root: Path,
    processor: Path,
    stage_source: Path,
    contract: dict,
    slr31_result: dict,
    seed: int,
) -> dict:
    expected_blob = contract["processor_contract"]["expected_git_blob_sha1"]
    actual_blob = git_blob_sha1(stage_source)
    if actual_blob != expected_blob:
        raise ValueError(f"stage source drift: {actual_blob} != {expected_blob}")
    if contract["authority"] != "CANDIDATE_ZERO_DIAGNOSTIC_ONLY":
        raise ValueError("authority drift")
    if contract["candidate_limit"] != 0 or contract["confirmation_limit"] != 0:
        raise ValueError("candidate budget drift")

    selected = select_microset(source_root)
    expected_paths = [
        item["path"] for item in slr31_result["source_review"]["selected_microset"]
    ]
    actual_paths = [path.relative_to(source_root).as_posix() for path in selected]
    if actual_paths != expected_paths:
        raise ValueError("SLR31 fixed microset drift")

    limit = float(contract["oracle"]["original_watch_limit_db"])
    rows: list[dict] = []
    for index, path in enumerate(selected):
        decoded = materialize_length(decode_flac(path))
        clean, normalization_gain = normalize(decoded)
        raw_noise = noise(TARGET_SAMPLES, seed * 103 + index, 2200.0)
        left = mix(clean, scale(raw_noise, 0.25))
        right = mix(
            scale(delayed(clean, 3), 0.72),
            scale(rotate(raw_noise, 137), 0.38),
        )

        stereo_clean = interleave(clean, clean)
        stereo_control = interleave(left, left)
        stereo_mismatch = interleave(left, right)

        with tempfile.TemporaryDirectory(prefix=f"ap-hpf-aware-{seed}-{index}-") as raw:
            work = Path(raw)
            clean_hpf, clean_latency = invoke_prefix(
                processor, stereo_clean, 2, work, "clean"
            )
            control_hpf, control_latency = invoke_prefix(
                processor, stereo_control, 2, work, "control"
            )
            mismatch_hpf, mismatch_latency = invoke_prefix(
                processor, stereo_mismatch, 2, work, "mismatch"
            )

        if len({clean_latency, control_latency, mismatch_latency}) != 1:
            raise ValueError("prefix-capture latency drift across controls")

        metrics = metric_pair(
            clean,
            left,
            clean_hpf,
            mismatch_hpf,
            mismatch_latency,
        )
        identical = control_hpf == mismatch_hpf
        verdict = classify(metrics, identical, limit)
        record = source_record(path, source_root)
        rows.append({
            "microset_id": f"u{index:02d}",
            "source": record,
            "normalization_gain": normalization_gain,
            "algorithmic_latency_samples": mismatch_latency,
            "metrics": metrics,
            "controls": {
                "stereo_left_equal_vs_right_mismatch_prefix_output_bitwise_identical":
                    identical,
            },
            **verdict,
        })

    artifact_cases = sum(row["reference_metric_artifact_case"] for row in rows)
    current_severe = sum(row["current_severe"] for row in rows)
    aware_severe = sum(row["hpf_aware_severe"] for row in rows)
    right_affects = sum(
        row["right_channel_change_affects_prefix_capture"] for row in rows
    )
    minimum = int(
        contract["preregistered_evidence_rules"]["minimum_artifact_cases_per_seed"]
    )
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": "candidate-zero-metric-reference-oracle-only",
        "seed": seed,
        "watch_limit_db": limit,
        "utterances": rows,
        "summary": {
            "total_cases": len(rows),
            "current_severe_cases": current_severe,
            "hpf_aware_severe_cases": aware_severe,
            "right_channel_affects_prefix_capture_cases": right_affects,
            "reference_metric_artifact_cases": artifact_cases,
            "reference_metric_artifact_gate_satisfied": artifact_cases >= minimum,
        },
        "candidate_authority": False,
        "shipping_change_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    expected_seeds = sorted(int(x) for x in contract["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("fresh seed mismatch")
    total = int(contract["preregistered_evidence_rules"]["total_cases_per_seed"])
    minimum = int(
        contract["preregistered_evidence_rules"]["minimum_artifact_cases_per_seed"]
    )
    observations = []
    paths = None
    for seed in expected_seeds:
        item = by_seed[seed]
        current_paths = [row["source"]["relative_path"] for row in item["utterances"]]
        if paths is None:
            paths = current_paths
        elif current_paths != paths:
            raise ValueError("microset drift across seeds")
        summary = item["summary"]
        if int(summary["total_cases"]) != total:
            raise ValueError("case count drift")
        observations.append({
            "seed": seed,
            "current_severe_cases": int(summary["current_severe_cases"]),
            "hpf_aware_severe_cases": int(summary["hpf_aware_severe_cases"]),
            "right_channel_affects_prefix_capture_cases":
                int(summary["right_channel_affects_prefix_capture_cases"]),
            "reference_metric_artifact_cases":
                int(summary["reference_metric_artifact_cases"]),
            "gate_satisfied":
                int(summary["reference_metric_artifact_cases"]) >= minimum,
        })
    satisfied = all(item["gate_satisfied"] for item in observations)
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "scoped_failure": contract["scoped_failure"],
        "scoped_subsignature": contract["scoped_subsignature"],
        "fresh_seeds": expected_seeds,
        "per_seed": observations,
        "metric_reference_domain_artifact_detected": satisfied,
        "candidate_relevant_subsignature_valid": not satisfied,
        "interpretation": (
            "The severe raw-clean SI-SDR improvement signature is explained by "
            "reference-target mismatch at the HPF-only observation, while the "
            "right-channel gain/delay change does not affect prefix-capture output."
            if satisfied
            else
            "The severe signature persists under the HPF-aware clean reference or "
            "depends on the right-channel mismatch; reference-domain artifact is not proven."
        ),
        "candidate_authority": False,
        "root_cause_claim_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    metrics = {
        "current_near_si_sdr_improvement_db": -20.0,
        "hpf_aware_quality_delta_db": -1.0,
    }
    result = classify(metrics, True, -10.0)
    assert result["reference_metric_artifact_case"] is True
    assert classify(metrics, False, -10.0)["reference_metric_artifact_case"] is False
    metrics["hpf_aware_quality_delta_db"] = -12.0
    assert classify(metrics, True, -10.0)["reference_metric_artifact_case"] is False
    print("HPF-aware reference oracle self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run_p = sub.add_parser("run")
    run_p.add_argument("--source-root", type=Path, required=True)
    run_p.add_argument("--processor", type=Path, required=True)
    run_p.add_argument("--stage-source", type=Path, required=True)
    run_p.add_argument("--contract", type=Path, required=True)
    run_p.add_argument("--slr31-result", type=Path, required=True)
    run_p.add_argument("--seed", type=int, required=True)
    run_p.add_argument("--output", type=Path, required=True)
    agg_p = sub.add_parser("aggregate")
    agg_p.add_argument("--contract", type=Path, required=True)
    agg_p.add_argument("--input", type=Path, action="append", required=True)
    agg_p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0

    contract = load_json(args.contract)
    if args.command == "run":
        result = run(
            args.source_root,
            args.processor,
            args.stage_source,
            contract,
            load_json(args.slr31_result),
            args.seed,
        )
    else:
        result = aggregate(
            [load_json(path) for path in args.input],
            contract,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.command == "run":
        print(json.dumps({"seed": result["seed"], **result["summary"]}, sort_keys=True))
    else:
        print(json.dumps({
            "metric_reference_domain_artifact_detected":
                result["metric_reference_domain_artifact_detected"],
            "candidate_relevant_subsignature_valid":
                result["candidate_relevant_subsignature_valid"],
            "per_seed": result["per_seed"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
