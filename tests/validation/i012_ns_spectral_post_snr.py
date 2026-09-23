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
            raise ValueError(f"invalid probe JSONL line {number}: {exc.msg}") from exc
    if not rows:
        raise ValueError("I012 probe produced no rows")
    return rows


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError(f"I012 case missing mic/labels: {case.get('case_id')}")
    if int(case.get("sample_rate_hz", 0)) != 16000:
        raise ValueError("I012 requires 16 kHz")
    if int(case.get("mic_channels", 0)) != 1:
        raise ValueError("I012 requires mono input")

    with tempfile.TemporaryDirectory(prefix="ap-i012-stage-") as tmp:
        work = Path(tmp)
        _, raw = engine.stage_audio(mic, 16000, 1, work, "mic.pcm")
        rows = run_probe(probe, raw)

    labels = engine.load_labels(labels_path)
    count = min(len(labels), len(rows))
    if count <= WARMUP_FRAMES:
        raise ValueError("I012 case too short after warmup")
    return {
        "case_id": str(case["case_id"]),
        "labels": [int(x) for x in labels[:count]],
        "rows": rows[:count],
    }


def summarize(seed_cases: dict[int, list[dict[str, Any]]]) -> dict[str, Any]:
    spectral_scores: list[float] = []
    upstream_scores: list[float] = []
    labels_all: list[int] = []
    speech_spectral: list[float] = []
    noise_spectral: list[float] = []
    floor_spectral_delta = 0.0
    floor_upstream_delta = 0.0
    per_seed: list[dict[str, Any]] = []

    for seed, cases in sorted(seed_cases.items()):
        seed_spectral: list[float] = []
        seed_upstream: list[float] = []
        seed_labels: list[int] = []
        case_summaries: list[dict[str, Any]] = []

        for case in cases:
            case_spectral: list[float] = []
            case_labels: list[int] = []
            for index, (label, row) in enumerate(zip(case["labels"], case["rows"])):
                base_snr = float(row["spectral_base_snr_db"])
                stress_snr = float(row["spectral_stress_snr_db"])
                upstream = float(row["base_speech_probability"])
                upstream_stress = float(row["stress_speech_probability"])
                if not all(math.isfinite(value) for value in (
                    base_snr, stress_snr, upstream, upstream_stress
                )):
                    raise ValueError(
                        f"non-finite I012 metric seed={seed} "
                        f"case={case['case_id']} frame={index}"
                    )
                if int(row["nfft"]) != 512:
                    raise ValueError("I012 FFT geometry drifted")
                if int(row["band_lo_exclusive"]) != 8 or                    int(row["band_hi_exclusive"]) != 224 or                    int(row["band_bins"]) != 215:
                    raise ValueError("I012 speech-band geometry drifted")

                floor_spectral_delta = max(
                    floor_spectral_delta, abs(base_snr - stress_snr)
                )
                floor_upstream_delta = max(
                    floor_upstream_delta, abs(upstream - upstream_stress)
                )
                if index < WARMUP_FRAMES:
                    continue

                seed_spectral.append(base_snr)
                seed_upstream.append(upstream)
                seed_labels.append(label)
                spectral_scores.append(base_snr)
                upstream_scores.append(upstream)
                labels_all.append(label)
                case_spectral.append(base_snr)
                case_labels.append(label)
                if label:
                    speech_spectral.append(base_snr)
                else:
                    noise_spectral.append(base_snr)

            case_summaries.append({
                "case_id": case["case_id"],
                "frames_after_warmup": len(case_spectral),
                "spectral_snr_auc": roc_auc(case_spectral, case_labels),
            })

        per_seed.append({
            "seed": seed,
            "spectral_snr_auc": roc_auc(seed_spectral, seed_labels),
            "upstream_speech_probability_auc": roc_auc(seed_upstream, seed_labels),
            "case_summaries": case_summaries,
        })

    if not speech_spectral or not noise_spectral:
        raise ValueError("I012 did not exercise speech and noise labels")
    combined_spectral_auc = roc_auc(spectral_scores, labels_all)
    combined_upstream_auc = roc_auc(upstream_scores, labels_all)
    return {
        "max_floor_spectral_snr_delta_db": floor_spectral_delta,
        "max_floor_speech_probability_delta": floor_upstream_delta,
        "combined_spectral_snr_auc": combined_spectral_auc,
        "combined_upstream_speech_probability_auc": combined_upstream_auc,
        "combined_auc_gain_over_upstream": (
            combined_spectral_auc - combined_upstream_auc
        ),
        "speech_spectral_snr_median_db": statistics.median(speech_spectral),
        "noise_spectral_snr_median_db": statistics.median(noise_spectral),
        "spectral_snr_median_separation_db": (
            statistics.median(speech_spectral) - statistics.median(noise_spectral)
        ),
        "per_seed": per_seed,
    }


def decide(summary: dict[str, Any], gates: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    min_seed_auc = min(float(item["spectral_snr_auc"]) for item in summary["per_seed"])
    checks = [
        (
            "floor_spectral_snr_invariance",
            float(summary["max_floor_spectral_snr_delta_db"]) <=
            float(gates["max_floor_spectral_snr_delta_db"]),
            summary["max_floor_spectral_snr_delta_db"],
            gates["max_floor_spectral_snr_delta_db"],
        ),
        (
            "floor_upstream_probability_invariance",
            float(summary["max_floor_speech_probability_delta"]) <=
            float(gates["max_floor_speech_probability_delta"]),
            summary["max_floor_speech_probability_delta"],
            gates["max_floor_speech_probability_delta"],
        ),
        (
            "combined_spectral_snr_auc",
            float(summary["combined_spectral_snr_auc"]) >=
            float(gates["min_combined_spectral_snr_auc"]),
            summary["combined_spectral_snr_auc"],
            gates["min_combined_spectral_snr_auc"],
        ),
        (
            "combined_auc_gain_over_upstream",
            float(summary["combined_auc_gain_over_upstream"]) >=
            float(gates["min_combined_auc_gain_over_upstream"]),
            summary["combined_auc_gain_over_upstream"],
            gates["min_combined_auc_gain_over_upstream"],
        ),
        (
            "per_seed_spectral_snr_auc",
            min_seed_auc >= float(gates["min_per_seed_spectral_snr_auc"]),
            min_seed_auc,
            gates["min_per_seed_spectral_snr_auc"],
        ),
    ]
    violations = [
        {"gate": name, "actual": actual, "limit": limit}
        for name, passed, actual, limit in checks
        if not passed
    ]
    decision = (
        "NS_SPECTRAL_POST_SNR_INFORMATION_GAIN_SUPPORTED_REVIEW_REQUIRED"
        if not violations
        else "NS_SPECTRAL_POST_SNR_INFORMATION_GAIN_NOT_SUPPORTED_REVIEW_REQUIRED"
    )
    return decision, violations


def evaluate(probe: Path, corpora: list[Path], contract_path: Path,
             output: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    seeds = [int(x) for x in contract["fresh_seeds"]]
    if len(corpora) != len(seeds):
        raise ValueError("I012 corpus count must match preregistered seeds")
    if contract["candidate_limit"] != 0 or contract["confirmation_limit"] != 0:
        raise ValueError("I012 budgets must remain zero")
    if contract["parameter_search_allowed"] is not False or        contract["threshold_tuning_allowed"] is not False:
        raise ValueError("I012 search/tuning must remain forbidden")

    seed_cases: dict[int, list[dict[str, Any]]] = {}
    actual_seeds: list[int] = []
    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if str(case.get("case_id")) in REQUIRED_CASES
        }
        if set(selected) != REQUIRED_CASES:
            raise ValueError(f"I012 required NS cases missing for seed {seed}")
        seed_cases[seed] = [
            run_case(probe, corpus_path, selected[case_id])
            for case_id in sorted(REQUIRED_CASES)
        ]
    if actual_seeds != seeds:
        raise ValueError(f"I012 seed drift: {actual_seeds} != {seeds}")

    summary = summarize(seed_cases)
    decision, violations = decide(summary, contract["diagnostic_gates"])
    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": "RESEARCH_DIAGNOSTIC_ONLY",
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": actual_seeds,
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "shipping_source_changed": False,
        "summary": summary,
        "violations": violations,
        "interpretation": {
            "spectral_post_snr_feature_selected": False,
            "vad_mapping_selected": False,
            "vad_threshold_selected": False,
            "note": (
                "ROC AUC is threshold-free evidence about information content only. "
                "This investigation cannot select a production mapping or threshold."
            ),
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
    scores = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    assert abs(roc_auc(scores, labels) - 1.0) < 1e-12
    assert abs(roc_auc([0.5, 0.5, 0.5, 0.5], labels) - 0.5) < 1e-12

    summary = {
        "max_floor_spectral_snr_delta_db": 0.0,
        "max_floor_speech_probability_delta": 0.0,
        "combined_spectral_snr_auc": 0.80,
        "combined_upstream_speech_probability_auc": 0.60,
        "combined_auc_gain_over_upstream": 0.20,
        "per_seed": [
            {"spectral_snr_auc": 0.75},
            {"spectral_snr_auc": 0.80},
            {"spectral_snr_auc": 0.78},
        ],
    }
    gates = {
        "max_floor_spectral_snr_delta_db": 1e-6,
        "max_floor_speech_probability_delta": 1e-7,
        "min_combined_spectral_snr_auc": 0.65,
        "min_combined_auc_gain_over_upstream": 0.05,
        "min_per_seed_spectral_snr_auc": 0.60,
    }
    decision, violations = decide(summary, gates)
    assert decision == "NS_SPECTRAL_POST_SNR_INFORMATION_GAIN_SUPPORTED_REVIEW_REQUIRED"
    assert violations == []
    summary["combined_auc_gain_over_upstream"] = 0.01
    decision, violations = decide(summary, gates)
    assert decision == "NS_SPECTRAL_POST_SNR_INFORMATION_GAIN_NOT_SUPPORTED_REVIEW_REQUIRED"
    assert violations[0]["gate"] == "combined_auc_gain_over_upstream"
    print("I012 spectral post-SNR evaluator self-test: OK")


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
        "summary": result["summary"],
        "violations": result["violations"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
