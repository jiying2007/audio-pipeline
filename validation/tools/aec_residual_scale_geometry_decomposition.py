#!/usr/bin/env python3
"""Candidate-zero AEC residual scale-vs-geometry decomposition."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

import aec_res_gain_contribution_decomposition as contrib

MODES = ("freeze_geometry", "freeze_scale")


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
        raise ValueError("scale-geometry trace is empty")
    if [int(row["frame"]) for row in rows] != list(range(len(rows))):
        raise ValueError("scale-geometry trace frame sequence drift")
    return rows


def require_contract(c: dict) -> None:
    if c.get("authority") != "CANDIDATE_ZERO_SCALE_GEOMETRY_ANALYSIS_ONLY":
        raise ValueError("scale-geometry authority drift")
    if c.get("candidate_limit") != 0 or c.get("confirmation_limit") != 0:
        raise ValueError("scale-geometry candidate budget drift")
    if c["measurement"]["geometry_id"] != "100w-50s":
        raise ValueError("scale-geometry recovery geometry drift")
    if set(c["counterfactuals"]) != {"actual", *MODES}:
        raise ValueError("scale-geometry counterfactual set drift")
    for key, value in c["preregistered_rules"].items():
        if key.startswith("no_") and value is not True:
            raise ValueError(f"scale-geometry rule drift: {key}")


def transition_frame(rows: list[dict]) -> int:
    hits = [
        int(row["frame"])
        for row in rows
        if int(row.get("echo_path_change_event", 0))
    ]
    if len(hits) != 1:
        raise ValueError(f"expected one transition frame, got {hits}")
    return hits[0]


def frame_M_R_G(row: dict, minimum_M: float) -> tuple[bool, float, float, float | None, str | None]:
    M = float(row["subtraction_input_energy"])
    R = float(row["residual_energy"])
    if not math.isfinite(M) or not math.isfinite(R):
        return False, M, R, None, "non_finite_M_or_R"
    if M < minimum_M:
        return False, M, R, None, "M_below_minimum"
    if R < 0.0:
        return False, M, R, None, "negative_R"
    G = R / M
    if not math.isfinite(G):
        return False, M, R, None, "non_finite_G"
    if G < 0.0:
        return False, M, R, G, "negative_G"
    return True, M, R, G, None


def pre_refs(rows: list[dict], frame: int, c: dict) -> dict:
    start_ms, end_ms = c["pre_transition_references"]["interval_ms"]
    start = frame + int(start_ms) // 10
    end = frame + int(end_ms) // 10
    if start < 0 or end > len(rows) or end <= start:
        raise ValueError("pre-transition scale/geometry interval out of range")
    minimum_M = float(c["factorization"]["minimum_M_for_valid_G"])
    valid = []
    for index in range(start, end):
        ok, M, R, G, _reason = frame_M_R_G(rows[index], minimum_M)
        if ok:
            valid.append((M, G))
    if not valid:
        raise ValueError("no valid pre-transition M/G frames")
    return {
        "M": float(statistics.median(M for M, _G in valid)),
        "G": float(statistics.median(G for _M, G in valid)),
        "valid_frames": len(valid),
        "total_frames": end - start,
    }


def required_interval(rows: list[dict], frame: int, c: dict) -> tuple[int, int]:
    start_ms, end_ms = c["physical_validity"]["required_interval_ms"]
    start = frame + int(start_ms) // 10
    end = frame + int(end_ms) // 10
    if start < 0 or end > len(rows) or end <= start:
        raise ValueError("scale/geometry validity interval out of range")
    return start, end


def build_counterfactual(
    rows: list[dict],
    frame: int,
    refs: dict,
    mode: str,
    c: dict,
) -> dict:
    start, end = required_interval(rows, frame, c)
    minimum_M = float(c["factorization"]["minimum_M_for_valid_G"])
    curve = [float(row["residual_energy"]) for row in rows]
    invalid = []

    for index in range(start, end):
        row = rows[index]
        M = float(row["subtraction_input_energy"])
        R = float(row["residual_energy"])

        if mode == "freeze_geometry":
            if not math.isfinite(M) or M < minimum_M:
                invalid.append({
                    "frame": index,
                    "transition_relative_ms": (index - frame) * 10,
                    "reason": "M_below_minimum_or_non_finite",
                    "M": M,
                    "R": R,
                })
                continue
            value = M * float(refs["G"])
        elif mode == "freeze_scale":
            ok, _M, _R, G, reason = frame_M_R_G(row, minimum_M)
            if not ok:
                invalid.append({
                    "frame": index,
                    "transition_relative_ms": (index - frame) * 10,
                    "reason": reason,
                    "M": M,
                    "R": R,
                })
                continue
            value = float(refs["M"]) * float(G)
        else:
            raise ValueError(mode)

        if not math.isfinite(value) or value < 0.0:
            invalid.append({
                "frame": index,
                "transition_relative_ms": (index - frame) * 10,
                "reason": "counterfactual_non_finite_or_negative",
                "value": value,
            })
            continue
        curve[index] = value

    if invalid:
        return {
            "physically_admissible": False,
            "invalid_frame_count": len(invalid),
            "first_invalid": invalid[0],
            "recovery_time_ms": None,
            "recovery_shift_vs_actual_ms": None,
        }

    return {
        "physically_admissible": True,
        "invalid_frame_count": 0,
        "first_invalid": None,
        "curve": curve,
    }


def recovery_delta(actual: int | None, cf: int | None) -> int | None:
    if actual is None or cf is None:
        return None
    return int(cf) - int(actual)


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

    refs = pre_refs(rows, frame, contract)
    echo_energy = contrib.echo_frame_energy(corpus_path, case, len(rows))
    actual_ms = receipt["standard_aec_recovery_ms"]

    modes = {}
    for mode in MODES:
        built = build_counterfactual(rows, frame, refs, mode, contract)
        if built["physically_admissible"]:
            measured = contrib.measure_curve(
                built.pop("curve"),
                echo_energy,
                frame,
                contract,
            )
            recovery = measured["recovery_time_ms"]
            built.update({
                "recovery_time_ms": recovery,
                "recovery_shift_vs_actual_ms": recovery_delta(actual_ms, recovery),
                "censored": bool(measured["censored"]),
                "pre_baseline_db": measured["pre_baseline_db"],
                "recovery_limit_db": measured["recovery_limit_db"],
            })
        modes[mode] = built

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-scale-geometry-analysis-only",
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
        raise ValueError("scale-geometry fresh-seed mismatch")

    summary = {}
    for mode in MODES:
        admissible = [
            seed for seed in expected
            if by_seed[seed]["counterfactuals"][mode]["physically_admissible"]
        ]
        inadmissible = [seed for seed in expected if seed not in admissible]
        shifts = {
            str(seed):
                by_seed[seed]["counterfactuals"][mode]["recovery_shift_vs_actual_ms"]
            for seed in admissible
        }
        summary[mode] = {
            "physically_admissible_seeds": admissible,
            "physically_inadmissible_seeds": inadmissible,
            "admissible_seed_count": len(admissible),
            "inadmissible_seed_count": len(inadmissible),
            "recovery_time_ms": {
                str(seed): by_seed[seed]["counterfactuals"][mode]["recovery_time_ms"]
                for seed in admissible
            },
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
            str(seed): by_seed[seed]["standard_aec_recovery_ms"]
            for seed in expected
        },
        "pre_transition_references": {
            str(seed): by_seed[seed]["pre_transition_references"]
            for seed in expected
        },
        "scale_geometry_summary": summary,
        "receipts": [by_seed[seed] for seed in expected],
        "scale_or_geometry_root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    row = {"subtraction_input_energy": 2.0, "residual_energy": 0.5}
    ok, M, R, G, reason = frame_M_R_G(row, 1e-12)
    assert ok and M == 2.0 and R == 0.5 and abs(G - 0.25) < 1e-12
    assert reason is None
    bad = {"subtraction_input_energy": 0.0, "residual_energy": 0.0}
    ok, _M, _R, _G, reason = frame_M_R_G(bad, 1e-12)
    assert not ok and reason == "M_below_minimum"
    print("AEC residual scale-geometry decomposition self-test: OK")


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
            "pre_transition_references": result["pre_transition_references"],
            "counterfactuals": result["counterfactuals"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "standard_aec_recovery_ms": result["standard_aec_recovery_ms"],
            "scale_geometry_summary": result["scale_geometry_summary"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
