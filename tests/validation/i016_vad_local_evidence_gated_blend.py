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


def roc_auc(scores: list[float], labels: list[int]) -> float:
    if len(scores) != len(labels) or not scores:
        raise ValueError("AUC inputs invalid")
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        raise ValueError("AUC requires two classes")
    ordered = sorted(zip(scores, labels), key=lambda x: x[0])
    rank = 1
    pos_rank = 0.0
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        avg = (rank + rank + (j - i) - 1) / 2.0
        pos_rank += avg * sum(label for _, label in ordered[i:j])
        rank += j - i
        i = j
    return (pos_rank - pos * (pos + 1) / 2.0) / (pos * neg)


def run_probe(probe: Path, pcm: Path) -> list[dict[str, Any]]:
    p = subprocess.run([str(probe), str(pcm)], check=True, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rows = [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("probe output invalid")
    return rows


def metrics(rows: list[dict[str, Any]], labels: list[int], lane: str) -> dict[str, Any]:
    speech = noise = speech_active = noise_active = 0
    scores: list[float] = []
    for row, label in zip(rows, labels):
        prob = float(row[f"{lane}_probability"])
        active = int(row[f"{lane}_active"])
        if not math.isfinite(prob):
            raise ValueError("non-finite probability")
        scores.append(prob)
        if label:
            speech += 1
            speech_active += active
        else:
            noise += 1
            noise_active += active
    return {
        "speech_frames": speech,
        "noise_frames": noise,
        "speech_active": speech_active,
        "noise_active": noise_active,
        "recall": speech_active / speech,
        "false_positive_rate": noise_active / noise,
        "probability_auc": roc_auc(scores, labels),
    }


def evaluate_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing audio/labels")
    with tempfile.TemporaryDirectory(prefix="ap-i016-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(v) for v in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]
    mirror_delta = max(abs(float(r["public_shipping_probability"]) -
                           float(r["shipping_probability"])) for r in rows)
    mirror_active = sum(int(r["public_shipping_active"]) != int(r["shipping_active"])
                        for r in rows)
    blocked = sum(int(r["candidate_blend_blocked_by_local_gate"]) for r in rows)
    return {
        "case_id": str(case["case_id"]),
        "shipping": metrics(rows, labels, "shipping"),
        "candidate": metrics(rows, labels, "candidate"),
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
        "candidate_blend_blocked_frames": blocked,
    }


def merge(parts: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lane in LANES:
        speech = sum(int(p[lane]["speech_frames"]) for p in parts)
        noise = sum(int(p[lane]["noise_frames"]) for p in parts)
        speech_active = sum(int(p[lane]["speech_active"]) for p in parts)
        noise_active = sum(int(p[lane]["noise_active"]) for p in parts)
        out[lane] = {
            "speech_frames": speech,
            "noise_frames": noise,
            "speech_active": speech_active,
            "noise_active": noise_active,
            "recall": speech_active / speech,
            "false_positive_rate": noise_active / noise,
            "probability_auc": sum(float(p[lane]["probability_auc"]) for p in parts) / len(parts),
        }
    out["candidate_blend_blocked_frames"] = sum(int(p["candidate_blend_blocked_frames"]) for p in parts)
    out["shipping_mirror"] = {
        "max_probability_delta": max(float(p["shipping_mirror"]["max_probability_delta"]) for p in parts),
        "active_mismatch_frames": sum(int(p["shipping_mirror"]["active_mismatch_frames"]) for p in parts),
    }
    out["candidate_vs_shipping"] = {
        "recall_delta": out["candidate"]["recall"] - out["shipping"]["recall"],
        "fpr_delta": out["candidate"]["false_positive_rate"] - out["shipping"]["false_positive_rate"],
        "auc_delta": out["candidate"]["probability_auc"] - out["shipping"]["probability_auc"],
        "noise_active_reduction_frames": out["shipping"]["noise_active"] - out["candidate"]["noise_active"],
    }
    return out


def evaluate(probe: Path, corpora: list[Path], contract_path: Path, output: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    if contract["investigation_id"] != "i016-vad-local-evidence-gated-blend-v1":
        raise ValueError("contract identity drift")
    if contract["budget"] != {"candidate_limit": 1, "confirmation_limit": 0, "development_execution_limit": 1}:
        raise ValueError("budget drift")
    expected_seeds = [int(x) for x in contract["fresh_development"]["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")

    partitions: dict[str, list[dict[str, Any]]] = {case: [] for case in CASES}
    actual_seeds: list[int] = []
    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {str(c.get("case_id")): c for c in corpus.get("cases", [])
                    if c.get("processor_profile") == "ns-isolated"
                    and c.get("vad_labels") and c.get("render_audio") is None
                    and str(c.get("case_id")) in CASES}
        if set(selected) != set(CASES):
            raise ValueError(f"missing required cases for seed {seed}")
        for case_id in CASES:
            partitions[case_id].append(evaluate_case(probe, corpus_path, selected[case_id]))

    if actual_seeds != expected_seeds:
        raise ValueError(f"seed mismatch: {actual_seeds}")
    summaries = {case_id: merge(parts) for case_id, parts in partitions.items()}
    gates = contract["development_gates"]
    mirror = {
        "max_probability_delta": max(v["shipping_mirror"]["max_probability_delta"] for v in summaries.values()),
        "active_mismatch_frames": sum(v["shipping_mirror"]["active_mismatch_frames"] for v in summaries.values()),
    }
    valid = (
        mirror["max_probability_delta"] <= float(gates["max_shipping_mirror_probability_delta"])
        and mirror["active_mismatch_frames"] == int(gates["shipping_mirror_active_mismatch_frames"])
    )
    passed = valid
    reasons: list[str] = []
    for case_id, summary in summaries.items():
        delta = summary["candidate_vs_shipping"]
        if float(delta["recall_delta"]) < -float(gates["max_recall_regression"]):
            passed = False
            reasons.append(f"{case_id}:recall")
        if float(delta["auc_delta"]) < -float(gates["max_auc_regression"]):
            passed = False
            reasons.append(f"{case_id}:auc")
        if float(delta["fpr_delta"]) > float(gates["max_fpr_regression"]):
            passed = False
            reasons.append(f"{case_id}:fpr")
    if summaries["stage-ns-nonstationary"]["candidate_vs_shipping"]["noise_active_reduction_frames"] < int(
        gates["min_nonstationary_noise_active_reduction_frames"]
    ):
        passed = False
        reasons.append("nonstationary:noise_reduction")
    if not valid:
        decision = "I016_INPUT_INVALID_REVIEW_REQUIRED"
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
        "summaries": summaries,
        "decision": decision,
        "failed_gates": reasons,
        "output_authority": contract["output_authority"],
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    labels = [0, 0, 1, 1]
    rows = [
        {"shipping_probability": 0.1, "shipping_active": 0, "candidate_probability": 0.1, "candidate_active": 0},
        {"shipping_probability": 0.8, "shipping_active": 1, "candidate_probability": 0.2, "candidate_active": 0},
        {"shipping_probability": 0.6, "shipping_active": 1, "candidate_probability": 0.6, "candidate_active": 1},
        {"shipping_probability": 0.7, "shipping_active": 1, "candidate_probability": 0.7, "candidate_active": 1},
    ]
    assert metrics(rows, labels, "shipping")["false_positive_rate"] == 0.5
    assert metrics(rows, labels, "candidate")["false_positive_rate"] == 0.0
    assert metrics(rows, labels, "candidate")["recall"] == 1.0
    print("I016 gated-blend evaluator self-test: OK")


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
    print(json.dumps({"decision": result["decision"], "failed_gates": result["failed_gates"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
