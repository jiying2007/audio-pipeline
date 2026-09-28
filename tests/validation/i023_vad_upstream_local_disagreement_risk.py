#!/usr/bin/env python3
"""I023 candidate-zero risk profile for upstream-high/local-low VAD disagreement."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import run_validation_engine as engine  # type: ignore

WARMUP = 80
TAIL_HORIZON = 8
NOISE_DOMAINS = ("kitchen", "traffic", "living", "office", "cafeteria", "bus", "field")


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


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def empty_accumulator() -> dict[str, Any]:
    return {
        "tp": 0, "fn": 0, "fp": 0, "tn": 0, "frames": 0,
        "speech_frames": 0, "noise_frames": 0,
        "low_local_false_negatives": 0,
        "disagreement_low_local_false_negatives": 0,
        "disagreement_speech_frames": 0,
        "disagreement_noise_frames": 0,
        "disagreement_speech_active_frames": 0,
        "disagreement_noise_active_frames": 0,
        "disagreement_noise_pre_hangover_frames": 0,
        "disagreement_noise_blend_frames": 0,
        "disagreement_noise_refresh": Counter(),
        "disagreement_noise_probability": [],
        "disagreement_noise_upstream_probability": [],
        "disagreement_noise_ratio_db": [],
        "noise_disagreement_episode_lengths": [],
        "post_disagreement_tail_noise_frames": 0,
        "post_disagreement_tail_active_frames": 0,
    }


def disagreement(row: dict[str, Any], upstream_guard: float) -> bool:
    return (
        float(row["upstream_probability"]) > upstream_guard
        and not int(row["local_guard_pass"])
    )


def analyze_sequence(
    acc: dict[str, Any],
    rows: list[dict[str, Any]],
    labels: list[int],
    upstream_guard: float,
) -> None:
    if len(rows) != len(labels) or not rows:
        raise ValueError("row/label geometry mismatch")
    flags = [disagreement(row, upstream_guard) for row in rows]

    for row, label, flag in zip(rows, labels, flags):
        if label not in (0, 1):
            raise ValueError("invalid VAD label")
        active = int(row["shipping_active"])
        if active not in (0, 1):
            raise ValueError("invalid shipping active state")
        for key in (
            "shipping_probability", "public_shipping_probability",
            "upstream_probability", "ratio_db",
        ):
            if not math.isfinite(float(row[key])):
                raise ValueError("non-finite diagnostic value: " + key)
        if label:
            acc["speech_frames"] += 1
            if active:
                acc["tp"] += 1
            else:
                acc["fn"] += 1
                if not int(row["local_guard_pass"]):
                    acc["low_local_false_negatives"] += 1
                    if flag:
                        acc["disagreement_low_local_false_negatives"] += 1
            if flag:
                acc["disagreement_speech_frames"] += 1
                acc["disagreement_speech_active_frames"] += active
        else:
            acc["noise_frames"] += 1
            if active:
                acc["fp"] += 1
            else:
                acc["tn"] += 1
            if flag:
                acc["disagreement_noise_frames"] += 1
                acc["disagreement_noise_active_frames"] += active
                acc["disagreement_noise_pre_hangover_frames"] += int(
                    int(row["pre_hangover"]) > 0
                )
                acc["disagreement_noise_blend_frames"] += int(
                    int(row["blend_applied"]) != 0
                )
                refresh = int(row["refresh_kind"])
                if refresh == 2:
                    acc["disagreement_noise_refresh"]["strong"] += 1
                elif refresh == 1:
                    acc["disagreement_noise_refresh"]["weak"] += 1
                elif refresh == 0:
                    acc["disagreement_noise_refresh"]["none"] += 1
                else:
                    raise ValueError("invalid refresh kind")
                acc["disagreement_noise_probability"].append(
                    float(row["shipping_probability"])
                )
                acc["disagreement_noise_upstream_probability"].append(
                    float(row["upstream_probability"])
                )
                acc["disagreement_noise_ratio_db"].append(float(row["ratio_db"]))
        acc["frames"] += 1

    i = 0
    count = len(rows)
    while i < count:
        if labels[i] != 0 or not flags[i]:
            i += 1
            continue
        start = i
        while i + 1 < count and labels[i + 1] == 0 and flags[i + 1]:
            i += 1
        end = i
        acc["noise_disagreement_episode_lengths"].append(end - start + 1)

        for j in range(end + 1, min(count, end + 1 + TAIL_HORIZON)):
            if labels[j] == 1 or flags[j]:
                break
            acc["post_disagreement_tail_noise_frames"] += 1
            acc["post_disagreement_tail_active_frames"] += int(
                int(rows[j]["shipping_active"]) != 0
            )
        i += 1


def merge_accumulator(target: dict[str, Any], source: dict[str, Any]) -> None:
    scalar_keys = (
        "tp", "fn", "fp", "tn", "frames", "speech_frames", "noise_frames",
        "low_local_false_negatives", "disagreement_low_local_false_negatives",
        "disagreement_speech_frames", "disagreement_noise_frames",
        "disagreement_speech_active_frames", "disagreement_noise_active_frames",
        "disagreement_noise_pre_hangover_frames", "disagreement_noise_blend_frames",
        "post_disagreement_tail_noise_frames", "post_disagreement_tail_active_frames",
    )
    for key in scalar_keys:
        target[key] += int(source[key])
    target["disagreement_noise_refresh"].update(source["disagreement_noise_refresh"])
    for key in (
        "disagreement_noise_probability",
        "disagreement_noise_upstream_probability",
        "disagreement_noise_ratio_db",
        "noise_disagreement_episode_lengths",
    ):
        target[key].extend(source[key])


def metrics(acc: dict[str, Any]) -> dict[str, Any]:
    tp, fn, fp, tn = (int(acc[key]) for key in ("tp", "fn", "fp", "tn"))
    speech = int(acc["speech_frames"])
    noise = int(acc["noise_frames"])
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / speech if speech else None
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if recall is not None and precision + recall > 0.0 else None
    )
    fpr = fp / noise if noise else None

    ds = int(acc["disagreement_speech_frames"])
    dn = int(acc["disagreement_noise_frames"])
    dt = ds + dn
    llfn = int(acc["low_local_false_negatives"])
    dllfn = int(acc["disagreement_low_local_false_negatives"])
    refresh = dict(sorted(acc["disagreement_noise_refresh"].items()))
    tail_noise = int(acc["post_disagreement_tail_noise_frames"])

    def median(key: str) -> float | None:
        values = acc[key]
        return statistics.median(values) if values else None

    return {
        "frames": int(acc["frames"]),
        "speech_frames": speech,
        "noise_frames": noise,
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "false_positive_rate": fpr,
        "low_local_false_negatives": llfn,
        "disagreement_low_local_false_negatives": dllfn,
        "disagreement_coverage_of_low_local_false_negatives": (
            dllfn / llfn if llfn else None
        ),
        "disagreement_speech_frames": ds,
        "disagreement_noise_frames": dn,
        "disagreement_total_frames": dt,
        "disagreement_conditional_speech_precision": ds / dt if dt else None,
        "disagreement_speech_occupancy": ds / speech if speech else None,
        "disagreement_noise_occupancy": dn / noise if noise else None,
        "disagreement_speech_active_fraction": (
            acc["disagreement_speech_active_frames"] / ds if ds else None
        ),
        "disagreement_noise_active_fraction": (
            acc["disagreement_noise_active_frames"] / dn if dn else None
        ),
        "disagreement_noise_pre_hangover_fraction": (
            acc["disagreement_noise_pre_hangover_frames"] / dn if dn else None
        ),
        "disagreement_noise_blend_fraction": (
            acc["disagreement_noise_blend_frames"] / dn if dn else None
        ),
        "disagreement_noise_refresh": refresh,
        "disagreement_noise_refresh_fraction": {
            key: value / dn if dn else None for key, value in refresh.items()
        },
        "disagreement_noise_shipping_probability_median": median(
            "disagreement_noise_probability"
        ),
        "disagreement_noise_upstream_probability_median": median(
            "disagreement_noise_upstream_probability"
        ),
        "disagreement_noise_ratio_db_median": median(
            "disagreement_noise_ratio_db"
        ),
        "noise_disagreement_episodes": len(acc["noise_disagreement_episode_lengths"]),
        "noise_disagreement_episode_length_median": median(
            "noise_disagreement_episode_lengths"
        ),
        "noise_disagreement_episode_length_p90": percentile(
            [float(x) for x in acc["noise_disagreement_episode_lengths"]], 0.90
        ),
        "post_disagreement_tail_noise_frames": tail_noise,
        "post_disagreement_tail_active_frames": int(
            acc["post_disagreement_tail_active_frames"]
        ),
        "post_disagreement_tail_active_fraction": (
            acc["post_disagreement_tail_active_frames"] / tail_noise
            if tail_noise else None
        ),
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


def evaluate_case(
    probe: Path,
    corpus_path: Path,
    case: dict[str, Any],
    upstream_guard: float,
) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing mic audio or VAD labels")
    with tempfile.TemporaryDirectory(prefix="ap-i023-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    rows = rows[WARMUP:count]
    labels = labels[WARMUP:count]

    mirror_delta = 0.0
    mirror_active = 0
    for row in rows:
        public_prob = float(row["public_shipping_probability"])
        shipping_prob = float(row["shipping_probability"])
        if not math.isfinite(public_prob):
            raise ValueError("non-finite public probability")
        mirror_delta = max(mirror_delta, abs(public_prob - shipping_prob))
        mirror_active += int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )

    acc = empty_accumulator()
    analyze_sequence(acc, rows, labels, upstream_guard)
    return {
        "case_id": str(case["case_id"]),
        "scenario": str(case["scenario"]),
        "dimensions": case.get("dimensions", {}),
        "metrics": metrics(acc),
        "accumulator": acc,
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    if contract["investigation_id"] != "i023-vad-upstream-local-disagreement-risk-v1":
        raise ValueError("contract identity drift")
    authority = contract["fresh_diagnostic_authority"]
    expected_seeds = [int(seed) for seed in authority["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")
    if {
        "diagnostic_execution_limit": authority["diagnostic_execution_limit"],
        "candidate_limit": authority["candidate_limit"],
        "confirmation_limit": authority["confirmation_limit"],
    } != {
        "diagnostic_execution_limit": 1,
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }:
        raise ValueError("I023 budget drift")

    upstream_guard = float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock = contract["dataset_authority"]["dataset_lock_sha256"]

    actual_seeds: list[int] = []
    global_acc = empty_accumulator()
    slices: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    mirror_delta = 0.0
    mirror_active = 0
    domain_case_counts = {domain: {"mix": 0, "noise": 0} for domain in NOISE_DOMAINS}

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        if corpus.get("tier") != "research-validation":
            raise ValueError("public development tier drift")
        if corpus.get("dataset_lock_sha256") != expected_lock:
            raise ValueError("dataset lock binding drift")
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        cases = corpus.get("cases", [])
        if len(cases) != int(authority["expected_cases_per_seed"]):
            raise ValueError(f"unexpected case count for seed={seed}")
        for case in cases:
            result = evaluate_case(probe, corpus_path, case, upstream_guard)
            per_case.append({
                key: value for key, value in result.items() if key != "accumulator"
            })
            merge_accumulator(global_acc, result["accumulator"])
            mirror_delta = max(
                mirror_delta,
                float(result["shipping_mirror"]["max_probability_delta"]),
            )
            mirror_active += int(
                result["shipping_mirror"]["active_mismatch_frames"]
            )
            for key in slice_keys(case):
                slices.setdefault(key, empty_accumulator())
                merge_accumulator(slices[key], result["accumulator"])
            dimensions = case.get("dimensions", {})
            domain = dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"] += 1
                elif case["scenario"] == "research-public-noise-only":
                    domain_case_counts[domain]["noise"] += 1

    if actual_seeds != expected_seeds:
        raise ValueError(f"fresh seed mismatch: {actual_seeds}")

    global_metrics = metrics(global_acc)
    slice_metrics = {key: metrics(acc) for key, acc in sorted(slices.items())}
    invalid_reasons: list[str] = []
    gates = contract["diagnostic_gates"]
    if len(per_case) < int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    if int(global_metrics["disagreement_speech_frames"]) < int(
        gates["minimum_disagreement_speech_frames"]
    ):
        invalid_reasons.append("disagreement_speech_count")
    if int(global_metrics["disagreement_noise_frames"]) < int(
        gates["minimum_disagreement_noise_frames"]
    ):
        invalid_reasons.append("disagreement_noise_count")
    if mirror_delta > float(gates["max_shipping_mirror_probability_delta"]):
        invalid_reasons.append("shipping_mirror_probability")
    if mirror_active != int(gates["shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("shipping_mirror_active")
    for domain, counts in domain_case_counts.items():
        if counts["mix"] < int(authority["minimum_mix_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:" + domain)
        if counts["noise"] < int(authority["minimum_noise_only_cases_per_noise_domain_per_seed"]) * len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:" + domain)

    risk_slices = sorted(
        [
            {
                "slice": key,
                "disagreement_total_frames": value["disagreement_total_frames"],
                "disagreement_conditional_speech_precision": value[
                    "disagreement_conditional_speech_precision"
                ],
                "disagreement_noise_occupancy": value["disagreement_noise_occupancy"],
                "disagreement_coverage_of_low_local_false_negatives": value[
                    "disagreement_coverage_of_low_local_false_negatives"
                ],
                "disagreement_noise_active_fraction": value[
                    "disagreement_noise_active_fraction"
                ],
                "disagreement_noise_refresh_fraction": value[
                    "disagreement_noise_refresh_fraction"
                ],
                "post_disagreement_tail_active_fraction": value[
                    "post_disagreement_tail_active_fraction"
                ],
            }
            for key, value in slice_metrics.items()
            if int(value["disagreement_total_frames"]) > 0
        ],
        key=lambda item: (
            -int(item["disagreement_total_frames"]),
            item["slice"],
        ),
    )

    if invalid_reasons:
        decision = "I023_INPUT_INVALID_REVIEW_REQUIRED"
    elif int(global_metrics["disagreement_total_frames"]) > 0:
        decision = "VAD_UPSTREAM_LOCAL_DISAGREEMENT_RISK_PROFILED_REVIEW_REQUIRED"
    else:
        decision = "VAD_UPSTREAM_LOCAL_DISAGREEMENT_NOT_REPRODUCED_REVIEW_REQUIRED"

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
        "global": global_metrics,
        "slices": slice_metrics,
        "per_case": per_case,
        "domain_case_counts": domain_case_counts,
        "risk_slices": risk_slices,
        "decision": decision,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "interpretation_boundary": {
            "disagreement_state": (
                "Existing upstream probability above the unchanged shipping "
                "upstream guard while the unchanged local guard fails."
            ),
            "conditional_precision_is_diagnostic_only": True,
            "no_guard_bypass_counterfactual_is_executed": True,
            "tail_horizon_frames": TAIL_HORIZON,
        },
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
        "shipping_active": 0,
        "public_shipping_active": 0,
        "shipping_probability": 0.2,
        "public_shipping_probability": 0.2,
        "upstream_probability": 0.2,
        "ratio_db": -2.0,
        "local_guard_pass": 0,
        "pre_hangover": 0,
        "blend_applied": 0,
        "refresh_kind": 0,
    }
    speech_disagree = dict(
        base,
        upstream_probability=0.8,
        shipping_probability=0.4,
        public_shipping_probability=0.4,
        blend_applied=1,
        refresh_kind=1,
    )
    noise_disagree = dict(
        speech_disagree,
        shipping_active=1,
        public_shipping_active=1,
        upstream_probability=0.7,
        pre_hangover=2,
    )
    tail = dict(
        base,
        shipping_active=1,
        public_shipping_active=1,
        pre_hangover=1,
    )
    rows = [speech_disagree, noise_disagree, tail, base]
    labels = [1, 0, 0, 0]
    acc = empty_accumulator()
    analyze_sequence(acc, rows, labels, upstream_guard=0.55)
    m = metrics(acc)
    assert m["disagreement_speech_frames"] == 1
    assert m["disagreement_noise_frames"] == 1
    assert m["disagreement_conditional_speech_precision"] == 0.5
    assert m["disagreement_noise_active_fraction"] == 1.0
    assert m["disagreement_noise_refresh"]["weak"] == 1
    assert m["post_disagreement_tail_noise_frames"] == 2
    assert m["post_disagreement_tail_active_frames"] == 1
    print("I023 disagreement risk evaluator self-test: OK")


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
        "conditional_speech_precision": result["global"][
            "disagreement_conditional_speech_precision"
        ],
        "noise_occupancy": result["global"]["disagreement_noise_occupancy"],
        "low_local_fn_coverage": result["global"][
            "disagreement_coverage_of_low_local_false_negatives"
        ],
    }, sort_keys=True))
    return 0 if result["decision"] != "I023_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
