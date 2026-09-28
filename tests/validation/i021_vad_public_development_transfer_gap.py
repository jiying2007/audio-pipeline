#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import run_validation_engine as engine  # type: ignore

WARMUP = 80
NOISE_DOMAINS = ("kitchen", "traffic", "living", "office", "cafeteria", "bus", "field")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def empty_accumulator() -> dict[str, Any]:
    return {
        "tp": 0,
        "fn": 0,
        "fp": 0,
        "tn": 0,
        "probability_sum": 0.0,
        "upstream_probability_sum": 0.0,
        "ratio_db_sum": 0.0,
        "crest_db_sum": 0.0,
        "frames": 0,
        "false_negative_mechanisms": Counter(),
        "false_positive_origins": Counter(),
        "probability_bands": Counter(),
    }


def false_negative_mechanism(row: dict[str, Any]) -> str:
    if int(row["transient_capped"]):
        return "transient_cap"
    if not int(row["local_guard_pass"]):
        return "low_local_evidence"
    if not int(row["blend_applied"]):
        return "no_upstream_blend_rescue"
    if float(row["shipping_probability"]) <= 0.35:
        return "blended_below_threshold"
    return "state_other"


def false_positive_origin(row: dict[str, Any]) -> str:
    refresh = int(row["refresh_kind"])
    if refresh == 2:
        return "strong_refresh"
    if refresh == 1:
        return "weak_refresh"
    if int(row["pre_hangover"]) > 0:
        return "hangover_tail"
    return "state_other"


def probability_band(probability: float) -> str:
    if probability < 0.15:
        return "lt_local_guard"
    if probability <= 0.35:
        return "local_to_decision"
    if probability < 0.50:
        return "weak_refresh_band"
    return "strong_refresh_band"


def accumulate(acc: dict[str, Any], row: dict[str, Any], label: int) -> None:
    prob = float(row["shipping_probability"])
    upstream = float(row["upstream_probability"])
    ratio = float(row["ratio_db"])
    crest = float(row["crest_db"])
    if not all(math.isfinite(v) for v in (prob, upstream, ratio, crest)):
        raise ValueError("non-finite diagnostic value")
    active = int(row["shipping_active"])
    if active not in (0, 1) or label not in (0, 1):
        raise ValueError("invalid binary state")
    if label and active:
        acc["tp"] += 1
    elif label and not active:
        acc["fn"] += 1
        acc["false_negative_mechanisms"][false_negative_mechanism(row)] += 1
    elif not label and active:
        acc["fp"] += 1
        acc["false_positive_origins"][false_positive_origin(row)] += 1
    else:
        acc["tn"] += 1
    acc["probability_bands"][probability_band(prob)] += 1
    acc["probability_sum"] += prob
    acc["upstream_probability_sum"] += upstream
    acc["ratio_db_sum"] += ratio
    acc["crest_db_sum"] += crest
    acc["frames"] += 1


def metrics(acc: dict[str, Any]) -> dict[str, Any]:
    tp, fn, fp, tn = (int(acc[key]) for key in ("tp", "fn", "fp", "tn"))
    speech = tp + fn
    noise = fp + tn
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / speech if speech else None
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if recall is not None and precision + recall > 0.0
        else None
    )
    fpr = fp / noise if noise else None
    frames = int(acc["frames"])
    return {
        "frames": frames,
        "speech_frames": speech,
        "noise_frames": noise,
        "tp": tp,
        "fn": fn,
        "fp": fp,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fpr,
        "mean_probability": acc["probability_sum"] / frames if frames else None,
        "mean_upstream_probability": (
            acc["upstream_probability_sum"] / frames if frames else None
        ),
        "mean_ratio_db": acc["ratio_db_sum"] / frames if frames else None,
        "mean_crest_db": acc["crest_db_sum"] / frames if frames else None,
        "false_negative_mechanisms": dict(
            sorted(acc["false_negative_mechanisms"].items())
        ),
        "false_positive_origins": dict(
            sorted(acc["false_positive_origins"].items())
        ),
        "probability_bands": dict(sorted(acc["probability_bands"].items())),
    }


def merge_accumulator(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("tp", "fn", "fp", "tn", "frames"):
        target[key] += int(source[key])
    for key in (
        "probability_sum",
        "upstream_probability_sum",
        "ratio_db_sum",
        "crest_db_sum",
    ):
        target[key] += float(source[key])
    for key in (
        "false_negative_mechanisms",
        "false_positive_origins",
        "probability_bands",
    ):
        target[key].update(source[key])


def analyze_rows(rows: list[dict[str, Any]], labels: list[int]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(rows) != len(labels) or not rows:
        raise ValueError("row/label geometry mismatch")
    mirror_delta = 0.0
    mirror_active = 0
    acc = empty_accumulator()
    for row, label in zip(rows, labels):
        public_prob = float(row["public_shipping_probability"])
        shipping_prob = float(row["shipping_probability"])
        if not math.isfinite(public_prob):
            raise ValueError("non-finite public probability")
        mirror_delta = max(mirror_delta, abs(public_prob - shipping_prob))
        mirror_active += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )
        accumulate(acc, row, int(label))
    return acc, {
        "max_probability_delta": mirror_delta,
        "active_mismatch_frames": mirror_active,
    }


def evaluate_case(
    probe: Path,
    corpus_path: Path,
    case: dict[str, Any],
) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing mic audio or VAD labels")
    with tempfile.TemporaryDirectory(prefix="ap-i021-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    acc, mirror = analyze_rows(rows[WARMUP:count], labels[WARMUP:count])
    return {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "metrics": metrics(acc),
        "accumulator": acc,
        "shipping_mirror": mirror,
    }


def slice_keys(case: dict[str, Any]) -> list[str]:
    dimensions = case.get("dimensions", {})
    keys = [f"scenario:{case['scenario']}"]
    domain = dimensions.get("noise_domain")
    if domain is not None:
        keys.append(f"noise_domain:{domain}")
    if "snr_db" in dimensions:
        keys.append(f"snr_db:{float(dimensions['snr_db']):g}")
    if "reverb" in dimensions:
        keys.append(f"reverb:{str(bool(dimensions['reverb'])).lower()}")
    if dimensions.get("clean_only") is True:
        keys.append("clean_only:true")
    return keys


def compact_accumulator(acc: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: int(acc[key]) for key in ("tp", "fn", "fp", "tn", "frames")},
        **{
            key: float(acc[key])
            for key in (
                "probability_sum",
                "upstream_probability_sum",
                "ratio_db_sum",
                "crest_db_sum",
            )
        },
        "false_negative_mechanisms": dict(acc["false_negative_mechanisms"]),
        "false_positive_origins": dict(acc["false_positive_origins"]),
        "probability_bands": dict(acc["probability_bands"]),
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    if contract["investigation_id"] != "i021-vad-public-development-transfer-gap-v1":
        raise ValueError("contract identity drift")
    authority = contract["fresh_diagnostic_authority"]
    if {
        "diagnostic_execution_limit": authority["diagnostic_execution_limit"],
        "candidate_limit": authority["candidate_limit"],
        "confirmation_limit": authority["confirmation_limit"],
    } != {
        "diagnostic_execution_limit": 1,
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }:
        raise ValueError("I021 budget drift")

    expected_seeds = [int(value) for value in authority["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")
    lock_path = ROOT / contract["dataset_authority"]["lock_path"]
    expected_lock = sha256_file(lock_path)

    actual_seeds: list[int] = []
    per_case: list[dict[str, Any]] = []
    global_acc = empty_accumulator()
    slices: dict[str, dict[str, Any]] = {}
    mirror_delta = 0.0
    mirror_active = 0
    domain_case_counts = {domain: {"mix": 0, "noise": 0} for domain in NOISE_DOMAINS}

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        if corpus.get("tier") != "research-validation":
            raise ValueError("public development tier drift")
        if corpus.get("dataset_lock_sha256") != expected_lock:
            raise ValueError("public development dataset-lock binding drift")
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        cases = corpus.get("cases", [])
        if len(cases) != int(authority["expected_cases_per_seed"]):
            raise ValueError(f"unexpected case count for seed={seed}: {len(cases)}")
        for case in cases:
            result = evaluate_case(probe, corpus_path, case)
            per_case.append({
                key: value for key, value in result.items() if key != "accumulator"
            })
            acc = result["accumulator"]
            merge_accumulator(global_acc, acc)
            mirror_delta = max(
                mirror_delta,
                float(result["shipping_mirror"]["max_probability_delta"]),
            )
            mirror_active += int(
                result["shipping_mirror"]["active_mismatch_frames"]
            )
            for key in slice_keys(case):
                slices.setdefault(key, empty_accumulator())
                merge_accumulator(slices[key], acc)
            dimensions = case.get("dimensions", {})
            domain = dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"] += 1
                elif case["scenario"] == "research-public-noise-only":
                    domain_case_counts[domain]["noise"] += 1

    if actual_seeds != expected_seeds:
        raise ValueError(f"fresh public-development seed mismatch: {actual_seeds}")

    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    if global_acc["tp"] + global_acc["fn"] < int(gates["minimum_total_speech_frames"]):
        invalid_reasons.append("speech_frame_count")
    if global_acc["fp"] + global_acc["tn"] < int(gates["minimum_total_noise_frames"]):
        invalid_reasons.append("noise_frame_count")
    if mirror_delta > float(gates["max_shipping_mirror_probability_delta"]):
        invalid_reasons.append("shipping_mirror_probability")
    if mirror_active != int(gates["shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("shipping_mirror_active")
    for domain, counts in domain_case_counts.items():
        if counts["mix"] < int(authority["minimum_mix_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append(f"domain_mix_coverage:{domain}")
        if counts["noise"] < int(authority["minimum_noise_only_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append(f"domain_noise_coverage:{domain}")

    slice_metrics = {key: metrics(value) for key, value in sorted(slices.items())}
    reference = float(gates["reference_absolute_min_vad_f1"])
    eligible = [
        (key, value)
        for key, value in slice_metrics.items()
        if value["speech_frames"] > 0 and value["f1"] is not None
    ]
    below = sorted(
        [
            {"slice": key, "f1": value["f1"], "recall": value["recall"],
             "false_positive_rate": value["false_positive_rate"],
             "speech_frames": value["speech_frames"],
             "noise_frames": value["noise_frames"]}
            for key, value in eligible
            if float(value["f1"]) < reference
        ],
        key=lambda item: (float(item["f1"]), item["slice"]),
    )
    worst = sorted(
        [
            {"slice": key, "f1": value["f1"], "recall": value["recall"],
             "false_positive_rate": value["false_positive_rate"],
             "speech_frames": value["speech_frames"],
             "noise_frames": value["noise_frames"]}
            for key, value in eligible
        ],
        key=lambda item: (float(item["f1"]), item["slice"]),
    )[:12]

    if invalid_reasons:
        decision = "I021_INPUT_INVALID_REVIEW_REQUIRED"
    elif below:
        decision = "PUBLIC_DEVELOPMENT_VAD_TRANSFER_GAP_DECOMPOSED_REVIEW_REQUIRED"
    else:
        decision = "PUBLIC_DEVELOPMENT_VAD_BASELINE_ADEQUATE_REVIEW_REQUIRED"

    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "dataset_id": contract["dataset_authority"]["dataset_id"],
        "fresh_diagnostic_seeds": actual_seeds,
        "diagnostic_execution_consumed": 1,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
        "global": metrics(global_acc),
        "slices": slice_metrics,
        "domain_case_counts": domain_case_counts,
        "reference_absolute_min_vad_f1": reference,
        "below_reference_slices": below,
        "worst_development_slices": worst,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "authority_boundary": contract["authority_boundary"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    base = {
        "public_shipping_probability": 0.2,
        "public_shipping_active": 0,
        "shipping_probability": 0.2,
        "shipping_active": 0,
        "upstream_probability": 0.1,
        "ratio_db": 1.0,
        "crest_db": 5.0,
        "local_guard_pass": 1,
        "transient_capped": 0,
        "blend_applied": 0,
        "refresh_kind": 0,
        "pre_hangover": 0,
    }
    tp = dict(base, public_shipping_probability=0.7,
              public_shipping_active=1, shipping_probability=0.7,
              shipping_active=1, upstream_probability=0.8,
              refresh_kind=2)
    fn = dict(base, local_guard_pass=0)
    fp_weak = dict(base, public_shipping_probability=0.4,
                   public_shipping_active=1, shipping_probability=0.4,
                   shipping_active=1, refresh_kind=1)
    fp_tail = dict(base, public_shipping_active=1, shipping_active=1,
                   pre_hangover=3)
    acc, mirror = analyze_rows([tp, fn, fp_weak, fp_tail], [1, 1, 0, 0])
    result = metrics(acc)
    assert mirror == {"max_probability_delta": 0.0, "active_mismatch_frames": 0}
    assert (result["tp"], result["fn"], result["fp"], result["tn"]) == (1, 1, 2, 0)
    assert result["false_negative_mechanisms"] == {"low_local_evidence": 1}
    assert result["false_positive_origins"] == {
        "hangover_tail": 1, "weak_refresh": 1
    }
    assert abs(float(result["recall"]) - 0.5) < 1e-12
    print("I021 public-development transfer-gap evaluator self-test: OK")


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
    print(json.dumps({
        "decision": result["decision"],
        "invalid_reasons": result["invalid_reasons"],
        "below_reference_slices": len(result["below_reference_slices"]),
    }, sort_keys=True))
    return 0 if result["decision"] != "I021_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
