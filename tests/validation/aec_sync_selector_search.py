#!/usr/bin/env python3
"""Bounded counterfactual search for the I003 AEC/Sync route selector.

This tool evaluates three pre-registered selector architectures against the
already-observed geometry-v2 development/validation model. It does not modify
shipping DSP, consume independent confirmation, or authorize promotion.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "validation/tools/build_aec_motion_corpus.py"
MIN_SCORE = 0.0324
COARSE_STEP = 32
MAX_DELAY = 1920
CLUSTER_GAP = 3 * COARSE_STEP
CANDIDATES = (
    "earliest-qualified",
    "incumbent-qualified",
    "causal-cluster-leading-edge",
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def load_generator():
    spec = importlib.util.spec_from_file_location("i003_motion_generator", GENERATOR)
    require(spec is not None and spec.loader is not None, "cannot load canonical generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_contract(contract: dict) -> None:
    expected = {
        "schema_version", "iteration_id", "root_cause_id", "phase", "base_sha",
        "policy", "candidate_limit", "confirmation_limit", "promotion_allowed",
        "run_timeout_seconds", "canonical_generator", "generator_version", "seconds",
        "development_seeds", "validation_seeds", "selector_candidates", "budget_before",
        "budget_after_this_run", "confirmation_source_group", "acceptance",
        "next_on_success", "next_on_failure",
    }
    require(set(contract) == expected, "I003 contract keys")
    require(contract["schema_version"] == 1 and contract["iteration_id"] == "I003", "I003 identity")
    require(contract["root_cause_id"] == "aec-motion-continuous-tracking" and
            contract["phase"] == "candidate-selection", "I003 phase/root cause")
    require(isinstance(contract["base_sha"], str) and len(contract["base_sha"]) == 40 and
            all(c in "0123456789abcdef" for c in contract["base_sha"]), "exact base SHA")
    require(contract["policy"] == "docs/program/promotion-policy.json", "policy path")
    require(contract["candidate_limit"] == 3 and contract["confirmation_limit"] == 0 and
            contract["promotion_allowed"] is False, "I003 authority budget")
    require(type(contract["run_timeout_seconds"]) is int and 1 <= contract["run_timeout_seconds"] <= 900,
            "timeout")
    require(contract["canonical_generator"] == "validation/tools/build_aec_motion_corpus.py" and
            contract["generator_version"] == 2, "generator contract")
    require(contract["seconds"] == 4.0, "frozen duration")
    dev = contract["development_seeds"]
    val = contract["validation_seeds"]
    require(dev == [4107, 4207] and val == [9107, 9207] and not (set(dev) & set(val)),
            "frozen observed development/validation seeds")
    require(contract["selector_candidates"] == list(CANDIDATES), "selector set must be frozen")
    require(contract["budget_before"] == {
        "search_rounds_consumed": 1,
        "candidate_variants_consumed": 9,
        "confirmation_sets_consumed": 0,
    }, "inherited budget before")
    require(contract["budget_after_this_run"] == {
        "search_rounds_consumed": 2,
        "candidate_variants_consumed": 12,
        "confirmation_sets_consumed": 0,
    }, "budget consumption for this search")
    require(contract["confirmation_source_group"] is None, "confirmation must remain unconsumed")
    require(isinstance(contract["acceptance"], list) and contract["acceptance"], "acceptance contract")


def local_peaks(scores: list[tuple[int, float]]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for i, item in enumerate(scores):
        delay, score = item
        left = scores[i - 1][1] if i else -1.0
        right = scores[i + 1][1] if i + 1 < len(scores) else -1.0
        if score >= MIN_SCORE and score >= left and score >= right:
            out.append((delay, score))
    return out


def select_global(scores: list[tuple[int, float]], _incumbent: int) -> tuple[int, float]:
    return max(scores, key=lambda item: (item[1], -item[0]))


def select_earliest(scores: list[tuple[int, float]], incumbent: int) -> tuple[int, float]:
    peaks = local_peaks(scores)
    return min(peaks, key=lambda item: item[0]) if peaks else select_global(scores, incumbent)


def select_incumbent(scores: list[tuple[int, float]], incumbent: int) -> tuple[int, float]:
    peaks = local_peaks(scores)
    near = [item for item in peaks if abs(item[0] - incumbent) <= 2 * COARSE_STEP]
    if near:
        return max(near, key=lambda item: (item[1], -item[0]))
    return select_global(scores, incumbent)


def select_cluster(scores: list[tuple[int, float]], incumbent: int) -> tuple[int, float]:
    peaks = local_peaks(scores)
    if not peaks:
        return select_global(scores, incumbent)
    clusters: list[list[tuple[int, float]]] = []
    for peak in peaks:
        if not clusters or peak[0] - clusters[-1][-1][0] > CLUSTER_GAP:
            clusters.append([peak])
        else:
            clusters[-1].append(peak)
    cluster = max(clusters, key=lambda c: (sum(score for _, score in c), -c[0][0]))
    return cluster[0]


SELECTORS = {
    "baseline-global-max": select_global,
    "earliest-qualified": select_earliest,
    "incumbent-qualified": select_incumbent,
    "causal-cluster-leading-edge": select_cluster,
}


def percentile(values: list[float], q: float) -> float:
    require(values, "empty percentile")
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return ordered[lo]
    frac = index - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def summarize(rows: list[dict]) -> dict:
    errors = [float(row["abs_error_samples"]) for row in rows]
    retention = [float(row["score_retention"]) for row in rows]
    return {
        "observations": len(rows),
        "median_abs_error_samples": statistics.median(errors),
        "p95_abs_error_samples": percentile(errors, 0.95),
        "near_32_rate": sum(v <= 32.0 for v in errors) / len(errors),
        "late_64_rate": sum(v > 64.0 for v in errors) / len(errors),
        "severe_320_rate": sum(v > 320.0 for v in errors) / len(errors),
        "median_score_retention": statistics.median(retention),
    }


def score_landscape(gen, render: list[int], case_seed: int, motion: str,
                    direct_gain: float, frame_start: int) -> tuple[list[tuple[int, float]], float]:
    indices = list(range(0, gen.FRAME, 4))
    mic: list[float] = []
    for i in indices:
        n = frame_start + i
        delays, gains = gen._path_state_validated(gen.MODEL, n / gen.RATE, motion, case_seed, direct_gain)
        y = 0.0
        for delay, gain in zip(delays, gains):
            y += gain * gen.sample(render, n - delay)
        mic.append(y)
    yy = 1.0e-12 + sum(y * y for y in mic)
    scores: list[tuple[int, float]] = []
    for delay in range(0, MAX_DELAY + 1, COARSE_STEP):
        xy = 0.0
        xx = 1.0e-12
        for i, y in zip(indices, mic):
            at = frame_start + i - delay
            x = float(render[at]) if 0 <= at < len(render) else 0.0
            xy += x * y
            xx += x * x
        scores.append((delay, (xy * xy) / (xx * yy)))
    direct = gen.MODEL["direct_total_delay_ms"] * gen.RATE / 1000.0
    return scores, direct


def evaluate_split(gen, seeds: list[int], seconds: float) -> dict:
    samples = math.ceil(seconds * 100.0) * gen.FRAME
    rows = {name: [] for name in SELECTORS}
    for seed in seeds:
        for kind_index, kind in enumerate(gen.MODEL["excitation"]):
            render = gen.excitation(samples, seed * 17 + 101 + kind_index, kind)
            for motion_index, motion in enumerate(gen.MODEL["motion"]):
                for gain_index, direct_gain in enumerate(gen.MODEL["direct_gain"]):
                    case_seed = seed * 1009 + kind_index * 211 + motion_index * 37 + gain_index * 13
                    incumbents = {name: int(gen.MODEL["nominal_reference_delay_ms"] * gen.RATE / 1000.0)
                                  for name in SELECTORS}
                    for frame in range(20, math.ceil(seconds * 100.0), 10):
                        start = frame * gen.FRAME
                        scores, direct = score_landscape(gen, render, case_seed, motion, direct_gain, start)
                        global_delay, global_score = select_global(scores, incumbents["baseline-global-max"])
                        for name, selector in SELECTORS.items():
                            selected_delay, selected_score = selector(scores, incumbents[name])
                            incumbents[name] = selected_delay
                            error = abs(selected_delay - direct)
                            rows[name].append({
                                "seed": seed,
                                "excitation": kind,
                                "motion": motion,
                                "direct_gain": direct_gain,
                                "frame": frame,
                                "selected_delay": selected_delay,
                                "global_delay": global_delay,
                                "direct_delay": direct,
                                "abs_error_samples": error,
                                "score": selected_score,
                                "global_score": global_score,
                                "score_retention": selected_score / max(global_score, 1.0e-12),
                            })
    return {name: {"summary": summarize(items), "rows": items} for name, items in rows.items()}


def eligible(validation: dict, candidate: str) -> bool:
    base = validation["baseline-global-max"]["summary"]
    cur = validation[candidate]["summary"]
    return (
        cur["median_abs_error_samples"] <= base["median_abs_error_samples"] and
        cur["p95_abs_error_samples"] <= base["p95_abs_error_samples"] and
        cur["severe_320_rate"] <= base["severe_320_rate"] and
        (cur["p95_abs_error_samples"] < base["p95_abs_error_samples"] or
         cur["median_abs_error_samples"] < base["median_abs_error_samples"] or
         cur["severe_320_rate"] < base["severe_320_rate"])
    )


def rank_key(validation: dict, candidate: str) -> tuple:
    s = validation[candidate]["summary"]
    return (
        s["severe_320_rate"],
        s["p95_abs_error_samples"],
        s["median_abs_error_samples"],
        s["late_64_rate"],
        -s["near_32_rate"],
        -s["median_score_retention"],
        candidate,
    )


def self_test() -> None:
    toy = [(d, 0.0) for d in range(0, 1344, COARSE_STEP)]
    def put(delay: int, score: float) -> None:
        toy[delay // COARSE_STEP] = (delay, score)
    put(672, 0.08)
    put(704, 0.05)
    put(1280, 0.40)
    assert select_global(toy, 640)[0] == 1280
    assert select_earliest(toy, 640)[0] == 672
    assert select_incumbent(toy, 640)[0] == 672
    assert select_cluster(toy, 640)[0] in {672, 1280}
    print(json.dumps({"result": "PASS", "candidates": list(CANDIDATES)}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract is not None and args.output is not None, "contract/output required")
    contract = load_json(args.contract)
    validate_contract(contract)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    gen = load_generator()
    require(gen.GENERATOR_VERSION == contract["generator_version"], "generator version drift")
    gen.validate_model(gen.MODEL)
    development = evaluate_split(gen, contract["development_seeds"], contract["seconds"])
    validation = evaluate_split(gen, contract["validation_seeds"], contract["seconds"])
    eligible_candidates = [name for name in CANDIDATES if eligible(validation, name)]
    selected = min(eligible_candidates, key=lambda name: rank_key(validation, name)) if eligible_candidates else None
    result = {
        "schema_version": 1,
        "iteration_id": "I003",
        "authority": "non-shipping-development-validation-selection",
        "base_sha": contract["base_sha"],
        "root_cause_id": contract["root_cause_id"],
        "budget_before": contract["budget_before"],
        "budget_after_this_run": contract["budget_after_this_run"],
        "confirmation_consumed": False,
        "confirmation_source_group": None,
        "baseline_selector": "baseline-global-max",
        "candidate_set": list(CANDIDATES),
        "development": {name: data["summary"] for name, data in development.items()},
        "validation": {name: data["summary"] for name, data in validation.items()},
        "eligible_candidates": eligible_candidates,
        "selected_candidate": selected,
        "decision": "SELECT_CANDIDATE_FOR_IMPLEMENTATION" if selected else "NO_CANDIDATE_SELECTED",
        "freeze_state": "FROZEN_FOR_IMPLEMENTATION" if selected else "NO_FROZEN_CANDIDATE",
        "notes": [
            "All four seeds are already-observed geometry-v2 development/validation authority; none is independent confirmation.",
            "The three selector architectures and constants are frozen before execution and are not tuned by the results.",
            "A selected architecture is not shipping approval; it must be implemented exactly, pass engineering/shadow gates, then use a new unobserved confirmation source group."
        ]
    }
    write_json(output / "selector-search-result.json", result)
    write_json(output / "development-detail.json", {name: data["rows"] for name, data in development.items()})
    write_json(output / "validation-detail.json", {name: data["rows"] for name, data in validation.items()})
    print(json.dumps({"decision": result["decision"], "selected_candidate": selected}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"i003 selector search: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1)
