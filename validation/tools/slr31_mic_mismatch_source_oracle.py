#!/usr/bin/env python3
"""Source-domain oracle for S003 mic gain/delay mismatch.

This tool never invokes the audio pipeline and never consumes pipeline output.
It validates the public clean reference and constructed microphone inputs using
absolute source-domain geometry/quality metrics.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from build_slr31_subsig_transfer_corpus import (
    MICROSET_SIZE,
    TARGET_SAMPLES,
    decode_flac,
    materialize_length,
    normalize,
    select_microset,
    source_record,
)
from build_validation_corpus import delayed, mix, noise, rotate, scale


def power(values: list[int]) -> float:
    return sum(float(x) * x for x in values) / max(1, len(values))


def clip_fraction(values: list[int]) -> float:
    if not values:
        return 0.0
    return sum(abs(int(x)) >= 32760 for x in values) / len(values)


def component_snr_db(expected: list[int], observed: list[int]) -> float:
    count = min(len(expected), len(observed))
    signal = 0.0
    error = 0.0
    for index in range(count):
        x = float(expected[index])
        e = float(observed[index]) - x
        signal += x * x
        error += e * e
    if signal <= 1.0e-12:
        raise ValueError("oracle expected component has zero energy")
    return 10.0 * math.log10((signal + 1.0e-12) / (error + 1.0e-12))


def aligned_pair(reference: list[int], estimate: list[int], lag: int) -> tuple[list[int], list[int]]:
    if lag >= 0:
        count = min(len(reference), len(estimate) - lag)
        if count <= 0:
            return [], []
        return reference[:count], estimate[lag:lag + count]
    offset = -lag
    count = min(len(reference) - offset, len(estimate))
    if count <= 0:
        return [], []
    return reference[offset:offset + count], estimate[:count]


def cosine_corr(reference: list[int], estimate: list[int], lag: int = 0) -> float:
    x, y = aligned_pair(reference, estimate, lag)
    if len(x) < 16:
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(x, y))
    xx = sum(float(a) * a for a in x)
    yy = sum(float(b) * b for b in y)
    if xx <= 1.0e-12 or yy <= 1.0e-12:
        return 0.0
    return dot / math.sqrt(xx * yy)


def best_lag(reference: list[int], estimate: list[int], limit: int = 8) -> tuple[int, float]:
    candidates = [(lag, cosine_corr(reference, estimate, lag)) for lag in range(-limit, limit + 1)]
    return max(candidates, key=lambda item: (item[1], -abs(item[0])))


def recovered_gain(reference: list[int], estimate: list[int], lag: int) -> float:
    x, y = aligned_pair(reference, estimate, lag)
    denom = sum(float(a) * a for a in x)
    if denom <= 1.0e-12:
        raise ValueError("oracle reference has zero energy")
    return sum(float(a) * float(b) for a, b in zip(x, y)) / denom


def load_contract(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("authority") != "CANDIDATE_ZERO_DIAGNOSTIC_ONLY":
        raise ValueError("measurement oracle authority drift")
    if value.get("candidate_limit") != 0 or value.get("confirmation_limit") != 0:
        raise ValueError("measurement oracle budget drift")
    return value


def check_metrics(metrics: dict, thresholds: dict) -> list[str]:
    failures: list[str] = []
    checks = (
        ("clean_clip_fraction", "<=", thresholds["max_clean_clip_fraction"]),
        ("left_clip_fraction", "<=", thresholds["max_left_clip_fraction"]),
        ("right_clip_fraction", "<=", thresholds["max_right_clip_fraction"]),
        ("left_component_snr_db", ">=", thresholds["min_left_component_snr_db"]),
        ("right_expected_component_snr_db", ">=", thresholds["min_right_expected_component_snr_db"]),
        ("left_clean_cosine_corr", ">=", thresholds["min_left_clean_cosine_corr"]),
        ("right_expected_cosine_corr", ">=", thresholds["min_right_expected_cosine_corr"]),
        ("right_recovered_gain", ">=", thresholds["min_right_recovered_gain"]),
        ("right_recovered_gain", "<=", thresholds["max_right_recovered_gain"]),
    )
    for name, operator, limit in checks:
        value = float(metrics[name])
        if operator == "<=" and value > float(limit):
            failures.append(f"{name}={value} > {limit}")
        if operator == ">=" and value < float(limit):
            failures.append(f"{name}={value} < {limit}")
    if int(metrics["left_best_lag_samples"]) != int(thresholds["required_left_best_lag_samples"]):
        failures.append(
            f"left_best_lag_samples={metrics['left_best_lag_samples']} != "
            f"{thresholds['required_left_best_lag_samples']}"
        )
    right_lag = int(metrics["right_best_lag_samples"])
    if not int(thresholds["min_right_best_lag_samples"]) <= right_lag <= int(
        thresholds["max_right_best_lag_samples"]
    ):
        failures.append(f"right_best_lag_samples={right_lag} outside expected range")
    return failures


def run_oracle(source_root: Path, seed: int, contract: dict) -> dict:
    selected = select_microset(source_root)
    thresholds = contract["source_domain_oracle"]["thresholds"]
    rows: list[dict] = []

    for index, path in enumerate(selected):
        record = source_record(path, source_root)
        decoded = materialize_length(decode_flac(path))
        clean, normalization_gain = normalize(decoded)

        raw_noise = noise(TARGET_SAMPLES, seed * 103 + index, 2200.0)
        left_noise = scale(raw_noise, 0.25)
        right_noise = scale(rotate(raw_noise, 137), 0.38)
        expected_right = scale(delayed(clean, 3), 0.72)
        left = mix(clean, left_noise)
        right = mix(expected_right, right_noise)

        left_lag, left_best_corr = best_lag(clean, left)
        right_lag, right_best_corr = best_lag(clean, right)
        metrics = {
            "clean_clip_fraction": clip_fraction(clean),
            "left_clip_fraction": clip_fraction(left),
            "right_clip_fraction": clip_fraction(right),
            "left_component_snr_db": component_snr_db(clean, left),
            "right_expected_component_snr_db": component_snr_db(expected_right, right),
            "left_clean_cosine_corr": cosine_corr(clean, left, 0),
            "right_expected_cosine_corr": cosine_corr(expected_right, right, 0),
            "left_best_lag_samples": left_lag,
            "left_best_lag_cosine_corr": left_best_corr,
            "right_best_lag_samples": right_lag,
            "right_best_lag_cosine_corr": right_best_corr,
            "right_recovered_gain": recovered_gain(clean, right, right_lag),
            "clean_rms": math.sqrt(power(clean)),
            "left_rms": math.sqrt(power(left)),
            "right_rms": math.sqrt(power(right)),
        }
        failures = check_metrics(metrics, thresholds)
        rows.append({
            "microset_id": f"u{index:02d}",
            "source": record,
            "normalization_gain": normalization_gain,
            "metrics": metrics,
            "oracle_valid": not failures,
            "oracle_failures": failures,
        })

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": "source-domain-oracle-only-no-pipeline-output",
        "seed": seed,
        "dataset_id": contract["public_source"]["dataset_id"],
        "utterances": rows,
        "summary": {
            "utterances": len(rows),
            "oracle_valid": sum(row["oracle_valid"] for row in rows),
            "oracle_invalid": sum(not row["oracle_valid"] for row in rows),
        },
        "candidate_authority": False,
        "shipping_change_authority": False,
    }


def aggregate(results: list[dict], contract: dict) -> dict:
    expected_seeds = sorted(int(x) for x in contract["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in results}
    if sorted(by_seed) != expected_seeds:
        raise ValueError(f"seed mismatch: {sorted(by_seed)} != {expected_seeds}")

    expected_paths = None
    observations = []
    minimum = int(
        contract["preregistered_evidence_rules"]["minimum_oracle_valid_utterances_per_seed"]
    )
    for seed in expected_seeds:
        item = by_seed[seed]
        paths = [row["source"]["relative_path"] for row in item["utterances"]]
        if expected_paths is None:
            expected_paths = paths
        elif paths != expected_paths:
            raise ValueError("oracle microset drift across fresh seeds")
        valid = int(item["summary"]["oracle_valid"])
        observations.append({
            "seed": seed,
            "oracle_valid_utterances": valid,
            "total_utterances": int(item["summary"]["utterances"]),
            "measurement_domain_input_control_passed": valid >= minimum,
        })

    satisfied = all(item["measurement_domain_input_control_passed"] for item in observations)
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "authority": "candidate-zero-measurement-domain-review-only",
        "scoped_failure": contract["predecessor"]["scoped_failure"],
        "scoped_subsignature": contract["predecessor"]["required_subsignature"],
        "fresh_seeds": expected_seeds,
        "fixed_microset_paths": expected_paths,
        "per_seed": observations,
        "measurement_domain_artifact_exclusion_satisfied": satisfied,
        "interpretation": (
            "PASS means the public clean/reference and constructed two-mic input geometry "
            "are independently valid under absolute source-domain oracle metrics. "
            "No pipeline output or output-vs-input delta metric participates in this gate."
        ),
        "candidate_authority": False,
        "root_cause_claim_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    reference = [0, 1000, -500, 250] * 100
    estimate = delayed(reference, 3)
    lag, corr = best_lag(reference, estimate)
    assert lag == 3 and corr > 0.999999
    assert abs(recovered_gain(reference, scale(estimate, 0.72), 3) - 0.72) < 0.01
    noisy = mix(reference, [10] * len(reference))
    assert component_snr_db(reference, noisy) > 20.0
    assert cosine_corr(reference, noisy) > 0.99
    print("mic-mismatch source-domain oracle self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run = sub.add_parser("run")
    run.add_argument("--source-root", type=Path, required=True)
    run.add_argument("--contract", type=Path, required=True)
    run.add_argument("--seed", type=int, required=True)
    run.add_argument("--output", type=Path, required=True)
    agg = sub.add_parser("aggregate")
    agg.add_argument("--contract", type=Path, required=True)
    agg.add_argument("--input", type=Path, action="append", required=True)
    agg.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0

    contract = load_contract(args.contract)
    if args.command == "run":
        result = run_oracle(args.source_root, args.seed, contract)
    else:
        result = aggregate(
            [json.loads(path.read_text(encoding="utf-8")) for path in args.input],
            contract,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.command == "run":
        print(json.dumps({"seed": result["seed"], **result["summary"]}, sort_keys=True))
    else:
        print(json.dumps({
            "measurement_domain_artifact_exclusion_satisfied":
                result["measurement_domain_artifact_exclusion_satisfied"],
            "per_seed": result["per_seed"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
