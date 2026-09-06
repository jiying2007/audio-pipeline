#!/usr/bin/env python3
"""Review I007 wind root cause using frozen baseline/root-cause evidence bundles.

This is a second-stage attribution review, not a new acoustic candidate or a
relaxed threshold. It verifies that the sole first-pass unexplained partition
is caused by a very small set of non-hard-correct fallback frames whose quality
is catastrophically worse, while hard-fault reliable-channel selection is
quality-neutral against the reliable single-mic oracle.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
from pathlib import Path
from typing import Sequence

FRAME = 160
WINDOW_START = 240
WINDOW_END = 480
TARGET = (1707, "bf-only", "soft-wind-ch0")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def read_pcm(path: Path) -> list[int]:
    raw = path.read_bytes()
    require(len(raw) % 2 == 0, f"odd PCM bytes: {path}")
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def load_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def si_sdr(reference: Sequence[int], estimate: Sequence[int]) -> float:
    count = min(len(reference), len(estimate))
    require(count >= 32, "SI-SDR sample set too short")
    r = [float(v) for v in reference[:count]]
    e = [float(v) for v in estimate[:count]]
    rr = sum(v * v for v in r)
    require(rr > 1.0e-12, "silent clean reference")
    scale = sum(x * y for x, y in zip(r, e)) / rr
    target = sum((scale * x) ** 2 for x in r)
    error = sum((y - scale * x) ** 2 for x, y in zip(r, e))
    return 10.0 * math.log10((target + 1.0e-12) / (error + 1.0e-12))


def samples_for_frames(clean: Sequence[int], signal: Sequence[int], frames: list[int], lag: int) -> tuple[list[int], list[int]]:
    ref: list[int] = []
    est: list[int] = []
    for frame in frames:
        start = frame * FRAME
        end = start + FRAME
        for index in range(start, min(end, len(clean))):
            shifted = index + lag
            if 0 <= shifted < len(signal):
                ref.append(int(clean[index]))
                est.append(int(signal[shifted]))
    return ref, est


def delta_for_frames(clean: Sequence[int], output: Sequence[int], reliable: Sequence[int],
                     frames: list[int], output_lag: int, reliable_lag: int) -> float | None:
    if not frames:
        return None
    clean_out, out = samples_for_frames(clean, output, frames, output_lag)
    clean_rel, rel = samples_for_frames(clean, reliable, frames, reliable_lag)
    count = min(len(clean_out), len(out), len(clean_rel), len(rel))
    require(count >= 32, "conditional quality sample set too short")
    return si_sdr(clean_out[:count], out[:count]) - si_sdr(clean_rel[:count], rel[:count])


def locate_case(result: dict, seed: int, frontend: str, scenario: str) -> dict:
    matches = [case for case in result["cases"]
               if int(case["seed"]) == seed and case["frontend"] == frontend and
               case["scenario"] == scenario]
    require(len(matches) == 1, f"baseline case identity: {seed}/{frontend}/{scenario}")
    return matches[0]


def self_test() -> None:
    clean = [1000 if i % 2 else -1000 for i in range(FRAME * 2)]
    same = list(clean)
    inverted = [-v for v in clean]
    # SI-SDR is scale invariant, so exact sign inversion is not a degradation.
    assert abs(si_sdr(clean, same) - si_sdr(clean, inverted)) < 1.0e-6
    print(json.dumps({"result": "PASS", "review": "conditional-frame-attribution"}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--root-cause-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    require(args.baseline_root is not None and args.root_cause_root is not None and args.output is not None,
            "baseline-root/root-cause-root/output required")
    baseline_root = args.baseline_root.resolve()
    root_root = args.root_cause_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    baseline = load_json(baseline_root / "baseline-result.json")
    root = load_json(root_root / "root-cause-result.json")
    require(baseline["source_sha"] == root["source_sha"] ==
            "dd15a956e52e9bc04fe103c62163c6cfa870b57b", "exact-main evidence identity")
    require(baseline["decision"] == "MEASURED_GAP_REVIEW_REQUIRED", "baseline gap required")
    require(root["decision"] == "ROOT_CAUSE_PARTIAL_REVIEW_REQUIRED", "first-pass partial review required")
    require(root["aggregate"] == {
        "explained_partitions": 23,
        "input_failure_partitions": 0,
        "partitions": 24,
        "unexplained_partitions": 1,
    }, "root-cause first-pass partition contract")
    require(len(root["unexplained"]) == 1, "exactly one first-pass unexplained partition required")
    missing = root["unexplained"][0]
    require((int(missing["seed"]), missing["frontend"], missing["scenario"]) == TARGET,
            "unexpected first-pass unexplained identity")
    metrics = missing["metrics"]
    require(float(metrics["fallback_fraction"]) >= 0.95 and
            float(metrics["hard_fault_fraction"]) >= 0.95 and
            float(metrics["energy_strong_is_faulty_fraction"]) >= 0.95 and
            0.0 < float(metrics["soft_fallback_wrong_target_fraction"]) < 0.05,
            "target partition must be low-duty soft-wrong wind selection")

    seed, frontend, scenario = TARGET
    baseline_case = locate_case(baseline, seed, frontend, scenario)
    case_metrics = baseline_case["metrics"]
    require(float(case_metrics["window_output_minus_reliable_si_sdr_db"]) < -1.0,
            "target baseline must fail frozen quality gate")
    reliable_channel = int(case_metrics["reliable_channel"])
    faulty_channel = 1 - reliable_channel
    lags = case_metrics["alignment_lag_samples"]

    case_dir = baseline_root / "runs" / f"seed-{seed}" / frontend / scenario
    corpus_dir = baseline_root / "corpus" / f"seed-{seed}" / "cases" / scenario
    clean = read_pcm(corpus_dir / "clean.pcm")
    output_pcm = read_pcm(case_dir / "bf.pcm")
    reliable = read_pcm(case_dir / f"ch{reliable_channel}.pcm")
    trace = load_trace(case_dir / "trace.jsonl")
    require(len(trace) >= WINDOW_END, "baseline trace too short")

    hard_correct: list[int] = []
    soft_wrong: list[int] = []
    soft_reliable: list[int] = []
    other: list[int] = []
    for frame in range(WINDOW_START, WINDOW_END):
        row = trace[frame]
        fallback = int(row["fallback_active"]) != 0
        hard = int(row["fallback_hard_fault"]) != 0
        selected = int(row["fallback_strong_channel"])
        if fallback and hard and selected == reliable_channel:
            hard_correct.append(frame)
        elif fallback and not hard and selected == faulty_channel:
            soft_wrong.append(frame)
        elif fallback and not hard and selected == reliable_channel:
            soft_reliable.append(frame)
        else:
            other.append(frame)

    hard_delta = delta_for_frames(clean, output_pcm, reliable, hard_correct,
                                  int(lags["bf"]), int(lags[f"ch{reliable_channel}"]))
    soft_wrong_delta = delta_for_frames(clean, output_pcm, reliable, soft_wrong,
                                        int(lags["bf"]), int(lags[f"ch{reliable_channel}"]))
    soft_reliable_delta = delta_for_frames(clean, output_pcm, reliable, soft_reliable,
                                           int(lags["bf"]), int(lags[f"ch{reliable_channel}"]))
    other_delta = delta_for_frames(clean, output_pcm, reliable, other,
                                   int(lags["bf"]), int(lags[f"ch{reliable_channel}"]))

    require(len(hard_correct) >= 200, "target must be mostly hard-correct")
    require(4 <= len(soft_wrong) <= 12, "target must contain small but nonzero soft-wrong burst")
    require(hard_delta is not None and hard_delta >= -0.25,
            "hard-correct output must preserve reliable-channel quality")
    require(soft_wrong_delta is not None and soft_wrong_delta <= -20.0,
            "soft-wrong burst must be catastrophically worse than reliable channel")
    require(len(soft_reliable) == 0 and len(other) == 0,
            "target attribution must partition entirely into hard-correct and soft-wrong")

    reviewed = {
        "schema_version": 1,
        "iteration_id": "I007",
        "phase": "bf-health-root-cause-reviewed",
        "source_sha": baseline["source_sha"],
        "first_pass": {
            "decision": root["decision"],
            "partitions": 24,
            "explained": 23,
            "unexplained": 1,
        },
        "conditional_review": {
            "target": {"seed": seed, "frontend": frontend, "scenario": scenario},
            "window_frames": [WINDOW_START, WINDOW_END],
            "reliable_channel": reliable_channel,
            "faulty_channel": faulty_channel,
            "hard_correct_frames": len(hard_correct),
            "soft_wrong_frames": len(soft_wrong),
            "soft_reliable_frames": len(soft_reliable),
            "other_frames": len(other),
            "hard_correct_output_minus_reliable_si_sdr_db": hard_delta,
            "soft_wrong_output_minus_reliable_si_sdr_db": soft_wrong_delta,
            "aggregate_output_minus_reliable_si_sdr_db":
                float(case_metrics["window_output_minus_reliable_si_sdr_db"]),
            "meaning": "The low-duty soft-wrong frames are sufficient to explain the aggregate failure; hard-fault reliable selection itself is quality-neutral in the same frozen window."
        },
        "final_attribution": {
            "partitions": 24,
            "explained": 24,
            "unexplained": 0,
            "wind_mechanism": "soft fallback uses energy-strong channel and 75/25 mixing; wind raises the faulty channel energy, while hard-fault reliable selection can rescue only when its separate roughness/ratio conditions arm",
            "reverb_mechanism": "coherence falls below the enter threshold but near-equal channel energy keeps ratio above 0.45, so the severe coherence-and-ratio conjunction blocks fallback admission"
        },
        "decision": "ROOT_CAUSE_EXPLAINED_REVIEW_REQUIRED",
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "threshold_tuning_performed": False,
        "shipping_source_changed": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "root-cause-reviewed-result.json", reviewed)
    print(json.dumps({"decision": reviewed["decision"], "explained": 24, "unexplained": 0,
                      "hard_correct_frames": len(hard_correct),
                      "soft_wrong_frames": len(soft_wrong)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I007 BF health root-cause review error: {exc}")
