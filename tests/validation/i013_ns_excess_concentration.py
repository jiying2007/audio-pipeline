#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))

import run_validation_engine as engine  # type: ignore

REQUIRED_CASES = {"stage-ns-stationary", "stage-ns-nonstationary"}
NONSTATIONARY_CASE = "stage-ns-nonstationary"
WARMUP_FRAMES = 80


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def roc_auc(scores: list[float], labels: list[int]) -> float:
    if len(scores) != len(labels) or not scores:
        raise ValueError("AUC requires aligned non-empty scores/labels")
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUC requires both positive and negative labels")

    ordered = sorted(zip(scores, labels), key=lambda item: item[0])
    rank = 1
    pos_rank_sum = 0.0
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        avg_rank = (rank + (rank + (j - i) - 1)) / 2.0
        pos_rank_sum += avg_rank * sum(label for _, label in ordered[i:j])
        rank += j - i
        i = j
    return (
        pos_rank_sum - n_pos * (n_pos + 1) / 2.0
    ) / (n_pos * n_neg)


def run_probe(probe: Path, raw_pcm: Path) -> list[dict[str, float | int]]:
    completed = subprocess.run(
        [str(probe), str(raw_pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows: list[dict[str, float | int]] = []
    for number, line in enumerate(completed.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid I013 probe JSONL line {number}: {exc.msg}"
            ) from exc
    if not rows:
        raise ValueError("I013 probe produced no rows")
    return rows


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError(f"I013 case missing mic/labels: {case.get('case_id')}")
    if int(case.get("sample_rate_hz", 0)) != 16000:
        raise ValueError("I013 requires 16 kHz")
    if int(case.get("mic_channels", 0)) != 1:
        raise ValueError("I013 requires mono input")

    with tempfile.TemporaryDirectory(prefix="ap-i013-stage-") as tmp:
        work = Path(tmp)
        _, raw = engine.stage_audio(mic, 16000, 1, work, "mic.pcm")
        rows = run_probe(probe, raw)

    labels = engine.load_labels(labels_path)
    count = min(len(labels), len(rows))
    if count <= WARMUP_FRAMES:
        raise ValueError("I013 case too short after warmup")
    return {
        "case_id": str(case["case_id"]),
        "labels": [int(x) for x in labels[:count]],
        "rows": rows[:count],
    }


def metric_auc(rows: list[dict[str, float | int]],
               labels: list[int],
               key: str) -> float:
    return roc_auc([float(row[key]) for row in rows], labels)


def summarize(seed_cases: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    all_concentration: list[float] = []
    all_scalar: list[float] = []
    all_upstream: list[float] = []
    all_labels: list[int] = []

    nonstationary_concentration: list[float] = []
    nonstationary_scalar: list[float] = []
    nonstationary_upstream: list[float] = []
    nonstationary_labels: list[int] = []

    speech_concentration: list[float] = []
    noise_concentration: list[float] = []
    floor_concentration_delta = 0.0
    floor_scalar_delta = 0.0
    floor_upstream_delta = 0.0
    per_seed: list[dict[str, Any]] = []

    for seed, cases in sorted(seed_cases.items()):
        seed_concentration: list[float] = []
        seed_scalar: list[float] = []
        seed_upstream: list[float] = []
        seed_labels: list[int] = []
        seed_non_concentration: list[float] = []
        seed_non_scalar: list[float] = []
        seed_non_upstream: list[float] = []
        seed_non_labels: list[int] = []
        case_summaries: list[dict[str, Any]] = []

        for case in cases:
            case_rows: list[dict[str, float | int]] = []
            case_labels: list[int] = []
            for index, (label, row) in enumerate(zip(case["labels"], case["rows"])):
                concentration = float(row["concentration_base"])
                concentration_stress = float(row["concentration_stress"])
                scalar = float(row["spectral_base_snr_db"])
                scalar_stress = float(row["spectral_stress_snr_db"])
                upstream = float(row["base_speech_probability"])
                upstream_stress = float(row["stress_speech_probability"])
                values = (
                    concentration, concentration_stress,
                    scalar, scalar_stress,
                    upstream, upstream_stress,
                )
                if not all(math.isfinite(value) for value in values):
                    raise ValueError(
                        f"non-finite I013 metric seed={seed} "
                        f"case={case['case_id']} frame={index}"
                    )
                if int(row["nfft"]) != 512:
                    raise ValueError("I013 FFT geometry drifted")
                if (
                    int(row["band_lo_exclusive"]) != 8
                    or int(row["band_hi_exclusive"]) != 224
                    or int(row["band_bins"]) != 215
                ):
                    raise ValueError("I013 speech-band geometry drifted")

                floor_concentration_delta = max(
                    floor_concentration_delta,
                    abs(concentration - concentration_stress),
                )
                floor_scalar_delta = max(
                    floor_scalar_delta,
                    abs(scalar - scalar_stress),
                )
                floor_upstream_delta = max(
                    floor_upstream_delta,
                    abs(upstream - upstream_stress),
                )
                if index < WARMUP_FRAMES:
                    continue

                row_base = {
                    "concentration": concentration,
                    "scalar": scalar,
                    "upstream": upstream,
                }
                case_rows.append(row_base)
                case_labels.append(label)

                seed_concentration.append(concentration)
                seed_scalar.append(scalar)
                seed_upstream.append(upstream)
                seed_labels.append(label)

                all_concentration.append(concentration)
                all_scalar.append(scalar)
                all_upstream.append(upstream)
                all_labels.append(label)

                if case["case_id"] == NONSTATIONARY_CASE:
                    seed_non_concentration.append(concentration)
                    seed_non_scalar.append(scalar)
                    seed_non_upstream.append(upstream)
                    seed_non_labels.append(label)
                    nonstationary_concentration.append(concentration)
                    nonstationary_scalar.append(scalar)
                    nonstationary_upstream.append(upstream)
                    nonstationary_labels.append(label)

                if label:
                    speech_concentration.append(concentration)
                else:
                    noise_concentration.append(concentration)

            case_summaries.append({
                "case_id": case["case_id"],
                "frames_after_warmup": len(case_rows),
                "concentration_auc": roc_auc(
                    [float(row["concentration"]) for row in case_rows],
                    case_labels,
                ),
                "scalar_snr_auc": roc_auc(
                    [float(row["scalar"]) for row in case_rows],
                    case_labels,
                ),
                "upstream_speech_probability_auc": roc_auc(
                    [float(row["upstream"]) for row in case_rows],
                    case_labels,
                ),
            })

        per_seed.append({
            "seed": seed,
            "concentration_auc": roc_auc(seed_concentration, seed_labels),
            "scalar_snr_auc": roc_auc(seed_scalar, seed_labels),
            "upstream_speech_probability_auc": roc_auc(seed_upstream, seed_labels),
            "nonstationary_concentration_auc": roc_auc(
                seed_non_concentration, seed_non_labels
            ),
            "nonstationary_scalar_snr_auc": roc_auc(
                seed_non_scalar, seed_non_labels
            ),
            "nonstationary_upstream_speech_probability_auc": roc_auc(
                seed_non_upstream, seed_non_labels
            ),
            "case_summaries": case_summaries,
        })

    if not speech_concentration or not noise_concentration:
        raise ValueError("I013 did not exercise speech and noise labels")

    combined_concentration_auc = roc_auc(all_concentration, all_labels)
    combined_scalar_auc = roc_auc(all_scalar, all_labels)
    combined_upstream_auc = roc_auc(all_upstream, all_labels)
    non_concentration_auc = roc_auc(
        nonstationary_concentration, nonstationary_labels
    )
    non_scalar_auc = roc_auc(nonstationary_scalar, nonstationary_labels)
    non_upstream_auc = roc_auc(nonstationary_upstream, nonstationary_labels)

    return {
        "max_floor_concentration_delta": floor_concentration_delta,
        "max_floor_scalar_snr_delta_db": floor_scalar_delta,
        "max_floor_speech_probability_delta": floor_upstream_delta,
        "combined_concentration_auc": combined_concentration_auc,
        "combined_scalar_snr_auc": combined_scalar_auc,
        "combined_upstream_speech_probability_auc": combined_upstream_auc,
        "combined_concentration_auc_gain_over_scalar_snr": (
            combined_concentration_auc - combined_scalar_auc
        ),
        "combined_nonstationary_concentration_auc": non_concentration_auc,
        "combined_nonstationary_scalar_snr_auc": non_scalar_auc,
        "combined_nonstationary_upstream_speech_probability_auc": non_upstream_auc,
        "combined_nonstationary_auc_gain_over_scalar_snr": (
            non_concentration_auc - non_scalar_auc
        ),
        "speech_concentration_median": statistics.median(speech_concentration),
        "noise_concentration_median": statistics.median(noise_concentration),
        "per_seed": per_seed,
    }


def decide(
    summary: dict[str, Any], gates: dict[str, Any]
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    input_checks = [
        (
            "floor_concentration_invariance",
            float(summary["max_floor_concentration_delta"])
            <= float(gates["max_floor_concentration_delta"]),
            summary["max_floor_concentration_delta"],
            gates["max_floor_concentration_delta"],
        ),
        (
            "floor_scalar_snr_invariance",
            float(summary["max_floor_scalar_snr_delta_db"])
            <= float(gates["max_floor_scalar_snr_delta_db"]),
            summary["max_floor_scalar_snr_delta_db"],
            gates["max_floor_scalar_snr_delta_db"],
        ),
        (
            "floor_upstream_probability_invariance",
            float(summary["max_floor_speech_probability_delta"])
            <= float(gates["max_floor_speech_probability_delta"]),
            summary["max_floor_speech_probability_delta"],
            gates["max_floor_speech_probability_delta"],
        ),
    ]
    min_seed_nonstationary = min(
        float(item["nonstationary_concentration_auc"])
        for item in summary["per_seed"]
    )
    info_checks = [
        (
            "combined_concentration_auc",
            float(summary["combined_concentration_auc"])
            >= float(gates["min_combined_concentration_auc"]),
            summary["combined_concentration_auc"],
            gates["min_combined_concentration_auc"],
        ),
        (
            "combined_nonstationary_concentration_auc",
            float(summary["combined_nonstationary_concentration_auc"])
            >= float(gates["min_combined_nonstationary_concentration_auc"]),
            summary["combined_nonstationary_concentration_auc"],
            gates["min_combined_nonstationary_concentration_auc"],
        ),
        (
            "combined_nonstationary_auc_gain_over_scalar_snr",
            float(summary["combined_nonstationary_auc_gain_over_scalar_snr"])
            >= float(gates["min_combined_nonstationary_auc_gain_over_scalar_snr"]),
            summary["combined_nonstationary_auc_gain_over_scalar_snr"],
            gates["min_combined_nonstationary_auc_gain_over_scalar_snr"],
        ),
        (
            "per_seed_nonstationary_concentration_auc",
            min_seed_nonstationary
            >= float(gates["min_per_seed_nonstationary_concentration_auc"]),
            min_seed_nonstationary,
            gates["min_per_seed_nonstationary_concentration_auc"],
        ),
    ]
    input_violations = [
        {"gate": name, "actual": actual, "limit": limit}
        for name, passed, actual, limit in input_checks
        if not passed
    ]
    info_violations = [
        {"gate": name, "actual": actual, "limit": limit}
        for name, passed, actual, limit in info_checks
        if not passed
    ]
    if input_violations:
        decision = "NS_EXCESS_CONCENTRATION_INPUT_INVALID_REVIEW_REQUIRED"
    elif info_violations:
        decision = "NS_EXCESS_CONCENTRATION_INFORMATION_NOT_SUPPORTED_REVIEW_REQUIRED"
    else:
        decision = "NS_EXCESS_CONCENTRATION_INFORMATION_SUPPORTED_REVIEW_REQUIRED"
    return decision, input_violations, info_violations


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    fresh = contract["fresh_diagnostic_authority"]
    seeds = [int(x) for x in fresh["seeds"]]
    if len(corpora) != len(seeds):
        raise ValueError("I013 corpus count must match preregistered seeds")
    if contract["budget"] != {
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_execution_limit": 1,
    }:
        raise ValueError("I013 budget drift")
    if (
        contract["parameter_search_allowed"] is not False
        or contract["threshold_tuning_allowed"] is not False
        or contract["shipping_source_change_allowed"] is not False
        or contract["promotion_allowed"] is not False
    ):
        raise ValueError("I013 authority boundary drift")

    seed_cases: dict[int, list[dict[str, Any]]] = {}
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
            and str(case.get("case_id")) in REQUIRED_CASES
        }
        if set(selected) != REQUIRED_CASES:
            raise ValueError(
                f"missing I013 required cases seed={seed}: "
                f"{sorted(REQUIRED_CASES - set(selected))}"
            )
        seed_cases[seed] = [
            run_case(probe, corpus_path, selected[case_id])
            for case_id in sorted(REQUIRED_CASES)
        ]

    if actual_seeds != seeds:
        raise ValueError(
            f"I013 seed drift: actual={actual_seeds} expected={seeds}"
        )

    summary = summarize(seed_cases)
    decision, input_violations, information_violations = decide(
        summary, contract["diagnostic_gates"]
    )
    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": actual_seeds,
        "summary": summary,
        "input_violations": input_violations,
        "information_violations": information_violations,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "shipping_source_changed": False,
        "interpretation": {
            "excess_concentration_feature_selected": False,
            "vad_mapping_selected": False,
            "adaptive_state_guard_selected": False,
            "vad_threshold_selected": False,
            "note": (
                "ROC AUC is threshold-free evidence about information content only. "
                "This investigation cannot select a production feature mapping, "
                "adaptive state rule, source candidate, or threshold."
            ),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    assert roc_auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0
    assert roc_auc([0.8, 0.9, 0.1, 0.2], [0, 0, 1, 1]) == 0.0
    summary = {
        "max_floor_concentration_delta": 0.0,
        "max_floor_scalar_snr_delta_db": 0.0,
        "max_floor_speech_probability_delta": 0.0,
        "combined_concentration_auc": 0.68,
        "combined_nonstationary_concentration_auc": 0.64,
        "combined_nonstationary_auc_gain_over_scalar_snr": 0.04,
        "per_seed": [
            {"nonstationary_concentration_auc": 0.61},
            {"nonstationary_concentration_auc": 0.63},
            {"nonstationary_concentration_auc": 0.62},
        ],
    }
    gates = {
        "max_floor_concentration_delta": 1e-6,
        "max_floor_scalar_snr_delta_db": 1e-6,
        "max_floor_speech_probability_delta": 1e-7,
        "min_combined_concentration_auc": 0.65,
        "min_combined_nonstationary_concentration_auc": 0.62,
        "min_combined_nonstationary_auc_gain_over_scalar_snr": 0.03,
        "min_per_seed_nonstationary_concentration_auc": 0.60,
    }
    decision, input_violations, info_violations = decide(summary, gates)
    assert decision == "NS_EXCESS_CONCENTRATION_INFORMATION_SUPPORTED_REVIEW_REQUIRED"
    assert not input_violations
    assert not info_violations
    print("I013 excess concentration evaluator self-test: OK")


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
    if not args.probe or not args.contract or not args.corpus or not args.output:
        parser.error("--probe, --contract, --corpus and --output are required")

    result = evaluate(
        args.probe.resolve(),
        [path.resolve() for path in args.corpus],
        args.contract.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "fresh_seeds": result["fresh_seeds"],
        "combined_concentration_auc":
            result["summary"]["combined_concentration_auc"],
        "combined_scalar_snr_auc":
            result["summary"]["combined_scalar_snr_auc"],
        "combined_nonstationary_concentration_auc":
            result["summary"]["combined_nonstationary_concentration_auc"],
        "combined_nonstationary_scalar_snr_auc":
            result["summary"]["combined_nonstationary_scalar_snr_auc"],
        "combined_nonstationary_auc_gain_over_scalar_snr":
            result["summary"]["combined_nonstationary_auc_gain_over_scalar_snr"],
        "input_violations": len(result["input_violations"]),
        "information_violations": len(result["information_violations"]),
    }, sort_keys=True))
    return 2 if result["decision"] == (
        "NS_EXCESS_CONCENTRATION_INPUT_INVALID_REVIEW_REQUIRED"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
