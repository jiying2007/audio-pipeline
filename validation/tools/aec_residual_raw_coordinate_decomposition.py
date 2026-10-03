#!/usr/bin/env python3
"""Candidate-zero raw M/E/C residual-geometry decomposition."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import aec_res_gain_contribution_decomposition as contrib


MODES = ("freeze_M", "freeze_E", "freeze_C")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def read_jsonl(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("raw-coordinate trace is empty")
    if [int(row["frame"]) for row in rows] != list(range(len(rows))):
        raise ValueError("raw-coordinate trace frame sequence drift")
    return rows


def require_contract(c: dict) -> None:
    if c.get("authority") != "CANDIDATE_ZERO_RAW_COORDINATE_ANALYSIS_ONLY":
        raise ValueError("raw-coordinate authority drift")
    if c.get("candidate_limit") != 0 or c.get("confirmation_limit") != 0:
        raise ValueError("raw-coordinate candidate budget drift")
    if c["measurement"]["geometry_id"] != "100w-50s":
        raise ValueError("raw-coordinate recovery geometry drift")
    for key, value in c["preregistered_rules"].items():
        if key.startswith("no_") and value is not True:
            raise ValueError(f"raw-coordinate rule drift: {key}")


def transition_frame(rows: list[dict]) -> int:
    hits = [int(row["frame"]) for row in rows if int(row.get("echo_path_change_event", 0))]
    if len(hits) != 1:
        raise ValueError(f"expected one echo-path transition frame, got {hits}")
    return hits[0]


def pre_refs(rows: list[dict], frame: int, c: dict) -> dict:
    start_ms, end_ms = c["pre_transition_references"]["interval_ms"]
    start = frame + int(start_ms) // 10
    end = frame + int(end_ms) // 10
    if start < 0 or end > len(rows) or end <= start:
        raise ValueError("pre-transition raw-coordinate interval out of range")
    region = rows[start:end]
    return {
        "M": float(statistics.median(float(row["subtraction_input_energy"]) for row in region)),
        "E": float(statistics.median(float(row["echo_estimate_energy"]) for row in region)),
        "C": float(statistics.median(float(row["cross_energy"]) for row in region)),
        "frames": len(region),
    }


def tolerance(scale: float, c: dict) -> float:
    p = c["physical_validity"]
    return float(p["absolute_numerical_tolerance"]) + (
        float(p["relative_numerical_tolerance"]) * max(abs(float(scale)), 1.0e-18)
    )


def physical_residual(M: float, E: float, C: float, c: dict) -> tuple[bool, float | None, str | None]:
    energy_scale = max(M * E, C * C, 1.0e-18)
    tol_me = tolerance(max(abs(M), abs(E), 1.0e-18), c)
    if M < -tol_me or E < -tol_me:
        return False, None, "negative_energy"
    M = 0.0 if M < 0.0 else M
    E = 0.0 if E < 0.0 else E
    cauchy_tol = tolerance(energy_scale, c)
    if C * C > M * E + cauchy_tol:
        return False, None, "cauchy_violation"
    residual = M + E - 2.0 * C
    residual_tol = tolerance(M + E + 2.0 * abs(C), c)
    if residual < -residual_tol:
        return False, None, "negative_residual"
    if residual < 0.0:
        residual = 0.0
    return True, residual, None


def coordinates(row: dict, refs: dict, mode: str) -> tuple[float, float, float]:
    M = float(row["subtraction_input_energy"])
    E = float(row["echo_estimate_energy"])
    C = float(row["cross_energy"])
    if mode == "freeze_M":
        M = refs["M"]
    elif mode == "freeze_E":
        E = refs["E"]
    elif mode == "freeze_C":
        C = refs["C"]
    else:
        raise ValueError(mode)
    return M, E, C


def analyze_mode(
    rows: list[dict],
    frame: int,
    refs: dict,
    mode: str,
    echo_energy: list[float],
    c: dict,
    actual_ms: int | None,
) -> dict:
    start_ms, end_ms = c["physical_validity"]["required_interval_ms"]
    start = frame + int(start_ms) // 10
    end = frame + int(end_ms) // 10
    if start < 0 or end > len(rows) or end <= start:
        raise ValueError("physical-validity interval out of range")

    curve = [float(row["residual_energy"]) for row in rows]
    invalid = []
    reason_counts: dict[str, int] = {}
    for index in range(start, end):
        M, E, C = coordinates(rows[index], refs, mode)
        valid, residual, reason = physical_residual(M, E, C, c)
        if not valid:
            invalid.append({
                "frame": index,
                "transition_relative_ms": (index - frame) * 10,
                "reason": reason,
                "M": M,
                "E": E,
                "C": C,
            })
            reason_counts[reason or "unknown"] = reason_counts.get(reason or "unknown", 0) + 1
        else:
            curve[index] = float(residual)

    if invalid:
        return {
            "physically_admissible": False,
            "invalid_frame_count": len(invalid),
            "first_invalid": invalid[0],
            "invalid_reason_counts": reason_counts,
            "recovery_time_ms": None,
            "recovery_shift_vs_actual_ms": None,
        }

    measured = contrib.measure_curve(
        curve,
        echo_energy,
        frame,
        c,
    )
    recovery = measured["recovery_time_ms"]
    shift = None if recovery is None or actual_ms is None else int(recovery) - int(actual_ms)
    return {
        "physically_admissible": True,
        "invalid_frame_count": 0,
        "first_invalid": None,
        "invalid_reason_counts": {},
        "recovery_time_ms": recovery,
        "recovery_shift_vs_actual_ms": shift,
        "censored": bool(measured["censored"]),
        "pre_baseline_db": measured["pre_baseline_db"],
        "recovery_limit_db": measured["recovery_limit_db"],
    }


def analyze_seed(
    corpus_path: Path,
    receipt_path: Path,
    trace_path: Path,
    contract: dict,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    receipt = load_json(receipt_path)
    rows = read_jsonl(trace_path)
    frame = transition_frame(rows)

    if not receipt.get("probe_output_bitwise_equivalent"):
        raise ValueError("predecessor probe equivalence failed")
    if not receipt.get("identity_valid"):
        raise ValueError("predecessor identity validity failed")
    if not receipt.get("actual_observed_recovery_matches_standard_aec"):
        raise ValueError("predecessor actual recovery validity failed")

    cases = {case["case_id"]: case for case in corpus["cases"]}
    case = cases.get("echo-path-change--prefix-aec")
    if case is None:
        raise ValueError("prefix-aec echo-path case missing")
    echo_energy = contrib.echo_frame_energy(corpus_path, case, len(rows))
    refs = pre_refs(rows, frame, contract)
    actual_ms = receipt["standard_aec_recovery_ms"]

    modes = {
        mode: analyze_mode(
            rows, frame, refs, mode, echo_energy, contract, actual_ms
        )
        for mode in MODES
    }

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-raw-coordinate-analysis-only",
        "transition_frame": frame,
        "pre_transition_references": refs,
        "standard_aec_recovery_ms": actual_ms,
        "counterfactuals": modes,
        "candidate_authority": False,
        "root_cause_claim_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected = sorted(int(seed) for seed in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected:
        raise ValueError("raw-coordinate fresh-seed mismatch")

    summary = {}
    for mode in MODES:
        admissible = [
            seed for seed in expected
            if by_seed[seed]["counterfactuals"][mode]["physically_admissible"]
        ]
        inadmissible = [seed for seed in expected if seed not in admissible]
        shifts = {
            str(seed): by_seed[seed]["counterfactuals"][mode]["recovery_shift_vs_actual_ms"]
            for seed in admissible
        }
        summary[mode] = {
            "physically_admissible_seeds": admissible,
            "physically_inadmissible_seeds": inadmissible,
            "admissible_seed_count": len(admissible),
            "inadmissible_seed_count": len(inadmissible),
            "recovery_shift_vs_actual_ms": shifts,
            "negative_shift_seed_count": sum(v is not None and v < 0 for v in shifts.values()),
            "zero_shift_seed_count": sum(v == 0 for v in shifts.values()),
            "positive_shift_seed_count": sum(v is not None and v > 0 for v in shifts.values()),
        }

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected,
        "standard_aec_recovery_ms": {
            str(seed): by_seed[seed]["standard_aec_recovery_ms"] for seed in expected
        },
        "raw_coordinate_summary": summary,
        "receipts": [by_seed[seed] for seed in expected],
        "raw_coordinate_root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    c = {
        "physical_validity": {
            "relative_numerical_tolerance": 1e-9,
            "absolute_numerical_tolerance": 1e-18,
        }
    }
    ok, residual, reason = physical_residual(1.0, 1.0, 0.5, c)
    assert ok and abs(residual - 1.0) < 1e-12 and reason is None
    ok, residual, reason = physical_residual(1.0, 1.0, 2.0, c)
    assert not ok and residual is None and reason == "cauchy_violation"
    print("AEC raw-coordinate decomposition self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run = sub.add_parser("run")
    run.add_argument("--corpus", type=Path, required=True)
    run.add_argument("--receipt", type=Path, required=True)
    run.add_argument("--trace", type=Path, required=True)
    run.add_argument("--contract", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    agg = sub.add_parser("aggregate")
    agg.add_argument("--contract", type=Path, required=True)
    agg.add_argument("--input", type=Path, action="append", required=True)
    agg.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0

    contract = load_json(args.contract)
    if args.command == "run":
        result = analyze_seed(
            args.corpus, args.receipt, args.trace, contract
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
        print(json.dumps({
            "seed": result["seed"],
            "standard_aec_recovery_ms": result["standard_aec_recovery_ms"],
            "counterfactuals": result["counterfactuals"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "raw_coordinate_summary": result["raw_coordinate_summary"],
            "standard_aec_recovery_ms": result["standard_aec_recovery_ms"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
