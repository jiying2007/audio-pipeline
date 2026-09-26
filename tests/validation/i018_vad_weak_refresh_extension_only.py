#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import run_validation_engine as engine  # type: ignore

CASES = ("stage-ns-nonstationary", "stage-ns-stationary")
WARMUP = 80
LANES = ("shipping", "candidate")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def run_probe(probe: Path, pcm: Path) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [str(probe), str(pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("probe output invalid")
    return rows


def lane_metrics(
    rows: list[dict[str, Any]], labels: list[int], lane: str
) -> dict[str, Any]:
    speech = noise = speech_active = noise_active = noise_segments = 0
    previous_label = 0
    previous_active = 0
    for index, (row, label) in enumerate(zip(rows, labels)):
        prob = float(row[f"{lane}_probability"])
        active = int(row[f"{lane}_active"])
        if not math.isfinite(prob):
            raise ValueError("non-finite probability")
        if label:
            speech += 1
            speech_active += active
        else:
            noise += 1
            noise_active += active
            previous_noise_active = (
                index > 0 and previous_label == 0 and previous_active == 1
            )
            if active and not previous_noise_active:
                noise_segments += 1
        previous_label = label
        previous_active = active
    return {
        "speech_frames": speech,
        "noise_frames": noise,
        "speech_active": speech_active,
        "noise_active": noise_active,
        "noise_active_segments": noise_segments,
        "recall": speech_active / speech,
        "false_positive_rate": noise_active / noise,
    }


def evaluate_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing audio/labels")
    with tempfile.TemporaryDirectory(prefix="ap-i018-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]

    shipping_mirror_probability_delta = max(
        abs(float(row["public_shipping_probability"]) -
            float(row["shipping_probability"]))
        for row in rows
    )
    shipping_mirror_active = sum(
        int(row["public_shipping_active"]) != int(row["shipping_active"])
        for row in rows
    )
    candidate_probability_delta = max(
        abs(float(row["shipping_probability"]) -
            float(row["candidate_probability"]))
        for row in rows
    )
    blocked = sum(int(row["candidate_weak_start_blocked"]) for row in rows)

    return {
        "case_id": str(case["case_id"]),
        "shipping": lane_metrics(rows, labels, "shipping"),
        "candidate": lane_metrics(rows, labels, "candidate"),
        "shipping_mirror": {
            "max_probability_delta": shipping_mirror_probability_delta,
            "active_mismatch_frames": shipping_mirror_active,
        },
        "candidate_probability_identity": {
            "max_probability_delta": candidate_probability_delta,
        },
        "candidate_weak_start_blocked_frames": blocked,
    }


def merge(parts: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lane in LANES:
        speech = sum(int(part[lane]["speech_frames"]) for part in parts)
        noise = sum(int(part[lane]["noise_frames"]) for part in parts)
        speech_active = sum(int(part[lane]["speech_active"]) for part in parts)
        noise_active = sum(int(part[lane]["noise_active"]) for part in parts)
        segments = sum(int(part[lane]["noise_active_segments"]) for part in parts)
        out[lane] = {
            "speech_frames": speech,
            "noise_frames": noise,
            "speech_active": speech_active,
            "noise_active": noise_active,
            "noise_active_segments": segments,
            "recall": speech_active / speech,
            "false_positive_rate": noise_active / noise,
        }
    out["shipping_mirror"] = {
        "max_probability_delta": max(
            float(part["shipping_mirror"]["max_probability_delta"]) for part in parts
        ),
        "active_mismatch_frames": sum(
            int(part["shipping_mirror"]["active_mismatch_frames"]) for part in parts
        ),
    }
    out["candidate_probability_identity"] = {
        "max_probability_delta": max(
            float(part["candidate_probability_identity"]["max_probability_delta"])
            for part in parts
        )
    }
    out["candidate_weak_start_blocked_frames"] = sum(
        int(part["candidate_weak_start_blocked_frames"]) for part in parts
    )
    out["candidate_vs_shipping"] = {
        "recall_delta": out["candidate"]["recall"] - out["shipping"]["recall"],
        "fpr_delta": (
            out["candidate"]["false_positive_rate"] -
            out["shipping"]["false_positive_rate"]
        ),
        "noise_active_reduction_frames": (
            out["shipping"]["noise_active"] - out["candidate"]["noise_active"]
        ),
        "noise_active_segment_reduction": (
            out["shipping"]["noise_active_segments"] -
            out["candidate"]["noise_active_segments"]
        ),
    }
    return out


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    if contract["investigation_id"] != "i018-vad-weak-refresh-extension-only-v1":
        raise ValueError("contract identity drift")
    if contract["budget"] != {
        "candidate_limit": 1,
        "confirmation_limit": 0,
        "development_execution_limit": 1,
    }:
        raise ValueError("budget drift")
    expected_seeds = [int(x) for x in contract["fresh_development"]["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")

    partitions: dict[str, list[dict[str, Any]]] = {case: [] for case in CASES}
    per_seed: list[dict[str, Any]] = []
    actual_seeds: list[int] = []

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if case.get("processor_profile") == "ns-isolated"
            and case.get("vad_labels")
            and case.get("render_audio") is None
            and str(case.get("case_id")) in CASES
        }
        if set(selected) != set(CASES):
            raise ValueError(f"missing required cases for seed {seed}")
        seed_result: dict[str, Any] = {"seed": seed, "cases": {}}
        for case_id in CASES:
            result = evaluate_case(probe, corpus_path, selected[case_id])
            partitions[case_id].append(result)
            seed_result["cases"][case_id] = result
        per_seed.append(seed_result)

    if actual_seeds != expected_seeds:
        raise ValueError(f"seed mismatch: {actual_seeds}")

    summaries = {case_id: merge(parts) for case_id, parts in partitions.items()}
    gates = contract["development_gates"]
    mirror = {
        "max_probability_delta": max(
            value["shipping_mirror"]["max_probability_delta"]
            for value in summaries.values()
        ),
        "active_mismatch_frames": sum(
            value["shipping_mirror"]["active_mismatch_frames"]
            for value in summaries.values()
        ),
    }
    candidate_probability_delta = max(
        value["candidate_probability_identity"]["max_probability_delta"]
        for value in summaries.values()
    )
    valid = (
        mirror["max_probability_delta"]
        <= float(gates["max_shipping_mirror_probability_delta"])
        and mirror["active_mismatch_frames"]
        == int(gates["shipping_mirror_active_mismatch_frames"])
        and candidate_probability_delta
        <= float(gates["max_candidate_probability_delta"])
    )
    passed = valid
    failed: list[str] = []

    for case_id, summary in summaries.items():
        delta = summary["candidate_vs_shipping"]
        if float(delta["recall_delta"]) < -float(gates["max_recall_regression"]):
            passed = False
            failed.append(f"{case_id}:recall")
        if float(delta["fpr_delta"]) > float(gates["max_fpr_regression"]):
            passed = False
            failed.append(f"{case_id}:fpr")

    nonstat = summaries["stage-ns-nonstationary"]["candidate_vs_shipping"]
    if int(nonstat["noise_active_reduction_frames"]) < int(
        gates["min_nonstationary_noise_active_reduction_frames"]
    ):
        passed = False
        failed.append("nonstationary:noise_active_reduction")
    if int(nonstat["noise_active_segment_reduction"]) < int(
        gates["min_nonstationary_noise_segment_reduction"]
    ):
        passed = False
        failed.append("nonstationary:segment_reduction")

    if not valid:
        decision = "I018_INPUT_INVALID_REVIEW_REQUIRED"
    elif passed:
        decision = "FROZEN_RESEARCH_CANDIDATE_REVIEW_REQUIRED"
    else:
        decision = "REJECTED_DEVELOPMENT_ONLY"

    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "fresh_development_seeds": actual_seeds,
        "candidate_id": contract["candidate"]["candidate_id"],
        "candidate_budget_consumed": 1,
        "confirmation_budget_consumed": 0,
        "shipping_mirror": mirror,
        "candidate_probability_identity": {
            "max_probability_delta": candidate_probability_delta,
        },
        "per_seed": per_seed,
        "summaries": summaries,
        "decision": decision,
        "failed_gates": failed,
        "output_authority": contract["output_authority"],
    }
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    rows = [
        {"shipping_probability": 0.4, "shipping_active": 1,
         "candidate_probability": 0.4, "candidate_active": 0},
        {"shipping_probability": 0.2, "shipping_active": 1,
         "candidate_probability": 0.2, "candidate_active": 0},
        {"shipping_probability": 0.7, "shipping_active": 1,
         "candidate_probability": 0.7, "candidate_active": 1},
        {"shipping_probability": 0.2, "shipping_active": 1,
         "candidate_probability": 0.2, "candidate_active": 1},
    ]
    labels = [0, 0, 1, 1]
    shipping = lane_metrics(rows, labels, "shipping")
    candidate = lane_metrics(rows, labels, "candidate")
    assert shipping["noise_active"] == 2
    assert candidate["noise_active"] == 0
    assert shipping["noise_active_segments"] == 1
    assert candidate["noise_active_segments"] == 0
    assert candidate["recall"] == shipping["recall"] == 1.0
    print("I018 weak-refresh extension-only evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.corpus:
        parser.error("--probe --contract --corpus --output are required")
    result = evaluate(args.probe, args.corpus, args.contract, args.output)
    print(json.dumps(
        {"decision": result["decision"], "failed_gates": result["failed_gates"]},
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
