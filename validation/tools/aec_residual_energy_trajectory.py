#!/usr/bin/env python3
"""Candidate-zero AEC residual-energy trajectory decomposition."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import tempfile
from pathlib import Path

import aec_res_gain_contribution_decomposition as contrib
import run_validation_engine as engine

PROFILE = "prefix-aec"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(c: dict) -> None:
    if c.get("authority") != "CANDIDATE_ZERO_AEC_RESIDUAL_GEOMETRY_ANALYSIS_ONLY":
        raise ValueError("residual-geometry authority drift")
    if c.get("candidate_limit") != 0 or c.get("confirmation_limit") != 0:
        raise ValueError("residual-geometry candidate budget drift")
    if c["corpus"]["analysis_profile"] != PROFILE:
        raise ValueError("analysis profile drift")
    if c["measurement"]["geometry_id"] != "100w-50s":
        raise ValueError("recovery geometry drift")
    for key, value in c["preregistered_rules"].items():
        if key.startswith("no_") and value is not True:
            raise ValueError(f"rule drift: {key}")


def read_jsonl(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("residual geometry trace empty")
    if [int(row["frame"]) for row in rows] != list(range(len(rows))):
        raise ValueError("residual geometry frame sequence drift")
    return rows


def run_probe(
    probe: Path,
    corpus_path: Path,
    case: dict,
    work: Path,
) -> tuple[list[int], list[dict]]:
    work.mkdir(parents=True, exist_ok=True)
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    render = engine.resolve(corpus_path, case.get("render_audio"))
    if mic is None or render is None:
        raise ValueError("residual geometry probe requires mic/render")
    change_frame = case.get("control", {}).get("echo_path_change_frame")
    if change_frame is None:
        raise ValueError("echo-path change frame missing")
    out = work / "probe-out.pcm"
    trace = work / "residual-geometry.jsonl"
    subprocess.run(
        [
            str(probe),
            "--sample-rate", str(int(case["sample_rate_hz"])),
            "--mic-channels", str(int(case["mic_channels"])),
            "--state-jsonl", str(trace),
            "--echo-path-change-frame", str(int(change_frame)),
            str(mic), str(render), str(out),
        ],
        check=True,
    )
    return [int(x) for x in engine.read_raw_array(out)], read_jsonl(trace)


def standard_output(
    processor: Path,
    corpus_path: Path,
    case: dict,
    work: Path,
) -> list[int]:
    return contrib.standard_output(processor, corpus_path, case, work)


def pre_geometry_reference(
    rows: list[dict],
    transition_frame: int,
    contract: dict,
) -> tuple[float, float, int]:
    start_ms, end_ms = contract["pre_transition_references"]["interval_ms"]
    start = transition_frame + int(start_ms) // 10
    end = transition_frame + int(end_ms) // 10
    valid = [
        row for row in rows[start:end]
        if int(row["normalized_valid"])
    ]
    if not valid:
        raise ValueError("no valid pre-transition normalized geometry")
    q_ref = float(statistics.median(
        float(row["q_estimate_to_input_power_ratio"]) for row in valid
    ))
    rho_ref = float(statistics.median(
        float(row["rho_input_estimate_similarity"]) for row in valid
    ))
    return q_ref, rho_ref, len(valid)


def residual_from_geometry(mono: float, q: float, rho: float) -> float:
    q = max(0.0, float(q))
    rho = min(1.0, max(-1.0, float(rho)))
    normalized = 1.0 + q - 2.0 * rho * math.sqrt(q)
    # Non-negativity is an algebraic property for |rho|<=1; clamp only
    # roundoff at zero.
    return max(0.0, float(mono) * max(0.0, normalized))


def counterfactual_curve(
    rows: list[dict],
    q_ref: float,
    rho_ref: float,
    mode: str,
) -> list[float]:
    out = []
    for row in rows:
        m = float(row["mono_energy"])
        q = float(row["q_estimate_to_input_power_ratio"])
        rho = float(row["rho_input_estimate_similarity"])
        if not int(row["normalized_valid"]):
            out.append(float(row["residual_energy"]))
            continue
        if mode == "actual":
            pass
        elif mode == "freeze_q":
            q = q_ref
        elif mode == "freeze_rho":
            rho = rho_ref
        elif mode == "freeze_both":
            q, rho = q_ref, rho_ref
        else:
            raise ValueError(mode)
        out.append(residual_from_geometry(m, q, rho))
    return out


def recovery_delta(actual: int | None, cf: int | None) -> int | None:
    if actual is None or cf is None:
        return None
    return int(cf) - int(actual)


def analyze_seed(
    corpus_path: Path,
    report_path: Path,
    processor: Path,
    probe: Path,
    contract: dict,
    trace_output: Path,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    cases = {case["case_id"]: case for case in corpus["cases"]}
    case_id = "echo-path-change--prefix-aec"
    case = cases.get(case_id)
    if case is None:
        raise ValueError("prefix-aec echo-path case missing")
    report_cases = {item["case_id"]: item for item in report.get("cases", [])}
    if set(report_cases) != set(cases):
        raise ValueError("canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("canonical policy failure")

    standard = contrib.analyze_standard_recovery(
        case, corpus_path, processor, contract
    )
    with tempfile.TemporaryDirectory(prefix="ap-aec-residual-geometry-") as raw:
        root = Path(raw)
        reference = standard_output(
            processor, corpus_path, case, root / "reference"
        )
        observed, rows = run_probe(
            probe, corpus_path, case, root / "probe"
        )
    equivalent = reference == observed
    trace_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    identity_max = max(float(row["identity_rel_error"]) for row in rows)
    valid_rows = [row for row in rows if int(row["normalized_valid"])]
    if not valid_rows:
        raise ValueError("no normalized-valid residual geometry frames")
    normalized_max = max(
        float(row["normalized_rel_error"]) for row in valid_rows
    )
    identity_ok = identity_max <= float(
        contract["identity"]["max_relative_identity_error"]
    )
    normalized_ok = normalized_max <= float(
        contract["identity"]["max_relative_normalized_reconstruction_error"]
    )

    transition_frame = int(case["control"]["echo_path_change_frame"])
    q_ref, rho_ref, pre_valid_count = pre_geometry_reference(
        rows, transition_frame, contract
    )
    echo_energy = contrib.echo_frame_energy(
        corpus_path, case, len(rows)
    )
    curves = {}
    for mode in ("actual", "freeze_q", "freeze_rho", "freeze_both"):
        measured = contrib.measure_curve(
            counterfactual_curve(rows, q_ref, rho_ref, mode),
            echo_energy,
            transition_frame,
            contract,
        )
        curves[mode] = {
            "recovery_time_ms": measured["recovery_time_ms"],
            "censored": bool(measured["censored"]),
            "pre_baseline_db": measured["pre_baseline_db"],
            "recovery_limit_db": measured["recovery_limit_db"],
        }

    standard_ms = standard["recovery_time_ms"]
    actual_ms = curves["actual"]["recovery_time_ms"]
    actual_matches = actual_ms == standard_ms
    receipts = {}
    for mode in ("freeze_q", "freeze_rho", "freeze_both"):
        receipts[mode] = {
            "recovery_time_ms": curves[mode]["recovery_time_ms"],
            "recovery_shift_vs_actual_ms":
                recovery_delta(actual_ms, curves[mode]["recovery_time_ms"]),
        }

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-aec-residual-geometry-analysis-only",
        "probe_output_bitwise_equivalent": equivalent,
        "identity_max_relative_error": identity_max,
        "normalized_max_relative_error": normalized_max,
        "identity_valid": identity_ok,
        "normalized_reconstruction_valid": normalized_ok,
        "pre_transition_geometry_reference": {
            "q": q_ref,
            "rho": rho_ref,
            "valid_frames": pre_valid_count,
        },
        "standard_aec_recovery_ms": standard_ms,
        "counterfactual_recovery": curves,
        "actual_reconstruction_matches_standard_aec": actual_matches,
        "driver_receipts": receipts,
        "candidate_authority": False,
        "root_cause_claim_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected = sorted(int(seed) for seed in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected:
        raise ValueError("fresh-seed mismatch")

    equivalent = all(
        by_seed[seed]["probe_output_bitwise_equivalent"] for seed in expected
    )
    identity_ok = all(by_seed[seed]["identity_valid"] for seed in expected)
    normalized_ok = all(
        by_seed[seed]["normalized_reconstruction_valid"] for seed in expected
    )
    actual_matches = all(
        by_seed[seed]["actual_reconstruction_matches_standard_aec"]
        for seed in expected
    )
    accepted = equivalent and identity_ok and normalized_ok and actual_matches

    modes = ("freeze_q", "freeze_rho", "freeze_both")
    summary = {
        mode: {
            "recovery_time_ms": {
                str(seed): by_seed[seed]["driver_receipts"][mode]["recovery_time_ms"]
                for seed in expected
            },
            "recovery_shift_vs_actual_ms": {
                str(seed):
                    by_seed[seed]["driver_receipts"][mode]["recovery_shift_vs_actual_ms"]
                for seed in expected
            },
        }
        for mode in modes
    }
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected,
        "mechanical_validity": {
            "probe_output_bitwise_equivalent_all_seeds": equivalent,
            "identity_valid_all_seeds": identity_ok,
            "normalized_reconstruction_valid_all_seeds": normalized_ok,
            "actual_reconstruction_matches_standard_aec_all_seeds": actual_matches,
            "max_identity_relative_error": max(
                by_seed[s]["identity_max_relative_error"] for s in expected
            ),
            "max_normalized_relative_error": max(
                by_seed[s]["normalized_max_relative_error"] for s in expected
            ),
            "evidence_accepted": accepted,
        },
        "standard_aec_recovery_ms": {
            str(seed): by_seed[seed]["standard_aec_recovery_ms"]
            for seed in expected
        },
        "pre_transition_geometry_reference": {
            str(seed): by_seed[seed]["pre_transition_geometry_reference"]
            for seed in expected
        },
        "counterfactual_summary": summary,
        "receipts": [by_seed[seed] for seed in expected],
        "q_or_rho_root_cause_attribution": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    m, q, rho = 2.0, 0.25, 0.5
    r = residual_from_geometry(m, q, rho)
    expected = m * (1.0 + q - 2.0 * rho * math.sqrt(q))
    assert abs(r - expected) < 1.0e-12
    print("AEC residual-energy trajectory decomposition self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run = sub.add_parser("run")
    for name in (
        "corpus", "report", "processor", "probe",
        "contract", "trace-output", "output",
    ):
        run.add_argument("--" + name, type=Path, required=True)
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
            args.corpus, args.report, args.processor, args.probe,
            contract, args.trace_output,
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
            "pre_transition_geometry_reference":
                result["pre_transition_geometry_reference"],
            "driver_receipts": result["driver_receipts"],
            "identity_max_relative_error": result["identity_max_relative_error"],
            "normalized_max_relative_error":
                result["normalized_max_relative_error"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "mechanical_validity": result["mechanical_validity"],
            "standard_aec_recovery_ms": result["standard_aec_recovery_ms"],
            "counterfactual_summary": result["counterfactual_summary"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
