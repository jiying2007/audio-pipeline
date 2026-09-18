#!/usr/bin/env python3
"""Independent confirmation for frozen VAD/AGC exact source candidates."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))
sys.path.insert(0, str(ROOT / ".github/research/continuous-optimization"))

import agc_dynamics_diagnostic as agc_diag
import i005_vad_baseline_measurement as event_metrics
import stage_source_candidate_evaluate as source_eval


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def metric_delta(base: dict[str, Any], cand: dict[str, Any],
                 key: str, missing_ok: bool = False) -> tuple[float | None, float | None, float | None]:
    b = base.get(key)
    c = cand.get(key)
    if b is None and c is None and missing_ok:
        return None, None, None
    if b is None or c is None:
        raise ValueError(f"confirmation metric missing: {key} base={b} candidate={c}")
    bf = finite(b, f"base {key}")
    cf = finite(c, f"candidate {key}")
    return bf, cf, cf - bf


def vad_event_aggregate(partition: dict[str, Any], bridge_frames: int,
                        min_event_frames: int) -> dict[str, Any]:
    reports = [
        {"labels": case["labels"], "predicted": case["active"]}
        for case in partition["cases"]
    ]
    return event_metrics.aggregate_reports(reports, bridge_frames, min_event_frames)


def vad_changed_frames(base: dict[str, Any], candidate: dict[str, Any]) -> int:
    if [case["case_id"] for case in base["cases"]] != [
        case["case_id"] for case in candidate["cases"]
    ]:
        raise ValueError("VAD confirmation case identity drift")
    changed = 0
    for b, c in zip(base["cases"], candidate["cases"]):
        if b["labels"] != c["labels"] or b["profile"] != c["profile"]:
            raise ValueError("VAD confirmation binding drift")
        if len(b["probabilities"]) != len(c["probabilities"]):
            raise ValueError("VAD confirmation probability trace length drift")
        probability_mismatch = sum(
            abs(x - y) > 1.0e-7
            for x, y in zip(b["probabilities"], c["probabilities"])
        )
        if probability_mismatch:
            raise ValueError(
                f"VAD probability generation drift in {c['case_id']}: {probability_mismatch}"
            )
        changed += sum(x != y for x, y in zip(b["active"], c["active"]))
    return changed


def confirm_vad(base_processor: Path, candidate_processor: Path,
                corpora: list[Path], contract_path: Path, output: Path) -> dict[str, Any]:
    contract = load(contract_path)
    if contract.get("authority") != "INDEPENDENT_SOURCE_CANDIDATE_CONFIRMATION_ONLY":
        raise ValueError("unexpected VAD confirmation authority")
    if contract.get("candidate_id") != "vad-confidence-tiered-hold-v1":
        raise ValueError("unexpected VAD candidate")
    spec = contract["synthetic_confirmation"]
    expected_seeds = [int(x) for x in spec["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("VAD confirmation corpus count mismatch")
    gates = spec["gates"]
    bridge = int(spec["event_bridge_frames"])
    minimum = int(spec["min_event_frames"])

    partitions = []
    total_changed = 0
    total_benefit = 0.0
    violations: list[dict[str, Any]] = []
    observed_seeds: list[int] = []

    for corpus in corpora:
        base = source_eval.collect_vad_partition(base_processor, corpus)
        cand = source_eval.collect_vad_partition(candidate_processor, corpus)
        seed = int(cand["seed"])
        observed_seeds.append(seed)
        changed = vad_changed_frames(base, cand)
        total_changed += changed

        base_frame = source_eval.vad_partition_summary(base)
        cand_frame = source_eval.vad_partition_summary(cand)
        base_event = vad_event_aggregate(base, bridge, minimum)
        cand_event = vad_event_aggregate(cand, bridge, minimum)

        local_violations: list[dict[str, Any]] = []
        if gates["require_candidate_case_gates_pass"] and cand_frame["validation_result"] != "PASS":
            local_violations.append({
                "gate": "candidate_case_gates",
                "actual": cand_frame["validation_result"],
            })

        b_recall, c_recall, recall_delta = metric_delta(
            base_frame["summary"], cand_frame["summary"], "min_vad_recall"
        )
        b_f1, c_f1, f1_delta = metric_delta(
            base_frame["summary"], cand_frame["summary"], "min_vad_f1"
        )
        b_fpr, c_fpr, fpr_delta = metric_delta(
            base_frame["summary"], cand_frame["summary"], "max_vad_false_positive_rate"
        )

        if -float(recall_delta) > float(gates["max_frame_recall_drop"]) + 1.0e-12:
            local_violations.append({
                "gate": "frame_recall_drop",
                "actual": -float(recall_delta),
                "allowed": gates["max_frame_recall_drop"],
            })
        if -float(f1_delta) > float(gates["max_frame_f1_drop"]) + 1.0e-12:
            local_violations.append({
                "gate": "frame_f1_drop",
                "actual": -float(f1_delta),
                "allowed": gates["max_frame_f1_drop"],
            })
        if float(fpr_delta) > float(gates["max_false_positive_rate_rise"]) + 1.0e-12:
            local_violations.append({
                "gate": "false_positive_rate_rise",
                "actual": fpr_delta,
                "allowed": gates["max_false_positive_rate_rise"],
            })

        be = base_event["event"]
        ce = cand_event["event"]
        b_event_recall, c_event_recall, event_recall_delta = metric_delta(
            be, ce, "event_recall"
        )
        if -float(event_recall_delta) > float(gates["max_event_recall_drop"]) + 1.0e-12:
            local_violations.append({
                "gate": "event_recall_drop",
                "actual": -float(event_recall_delta),
                "allowed": gates["max_event_recall_drop"],
            })

        def regression(base_value: Any, candidate_value: Any, gate: str,
                       allowed: float) -> float:
            if base_value is None and candidate_value is None:
                return 0.0
            if base_value is None or candidate_value is None:
                local_violations.append({
                    "gate": gate + "_missing",
                    "baseline": base_value,
                    "candidate": candidate_value,
                })
                return float("inf")
            delta = finite(candidate_value, gate + " candidate") - finite(base_value, gate + " base")
            if delta > allowed + 1.0e-12:
                local_violations.append({
                    "gate": gate,
                    "actual_regression": delta,
                    "allowed": allowed,
                })
            return delta

        onset_reg = regression(
            be.get("onset_delay_p95_ms"), ce.get("onset_delay_p95_ms"),
            "onset_p95_regression_ms",
            float(gates["max_onset_p95_regression_ms"]),
        )
        release_reg = regression(
            be.get("release_tail_p95_ms"), ce.get("release_tail_p95_ms"),
            "release_tail_p95_regression_ms",
            float(gates["max_release_tail_p95_regression_ms"]),
        )
        false_active_reg = (
            finite(ce["false_active_fraction"], "candidate false active")
            - finite(be["false_active_fraction"], "base false active")
        )
        if false_active_reg > float(gates["max_false_active_fraction_rise"]) + 1.0e-12:
            local_violations.append({
                "gate": "false_active_fraction_rise",
                "actual": false_active_reg,
                "allowed": gates["max_false_active_fraction_rise"],
            })

        benefit = (
            max(0.0, float(recall_delta))
            + max(0.0, float(f1_delta))
            + max(0.0, float(event_recall_delta))
            + max(0.0, -float(false_active_reg))
        )
        total_benefit += benefit
        partitions.append({
            "seed": seed,
            "changed_active_frames": changed,
            "benefit": benefit,
            "baseline_frame": base_frame["summary"],
            "candidate_frame": cand_frame["summary"],
            "baseline_event": be,
            "candidate_event": ce,
            "onset_p95_regression_ms": onset_reg,
            "release_tail_p95_regression_ms": release_reg,
            "false_active_fraction_regression": false_active_reg,
            "violations": local_violations,
        })
        if local_violations:
            violations.append({"seed": seed, "violations": local_violations})

    if observed_seeds != expected_seeds:
        raise ValueError(
            f"VAD confirmation seeds drifted: observed={observed_seeds} expected={expected_seeds}"
        )
    if gates["require_candidate_behavior_exercised"] and total_changed <= 0:
        violations.append({"gate": "candidate_behavior_not_exercised"})
    min_benefit = float(gates["minimum_total_frame_or_event_benefit"])
    if gates["require_independent_benefit"] and total_benefit < min_benefit - 1.0e-12:
        violations.append({
            "gate": "independent_benefit",
            "actual": total_benefit,
            "expected_min": min_benefit,
        })

    result = {
        "schema_version": 1,
        "authority": "independent-source-candidate-confirmation-only",
        "candidate_id": contract["candidate_id"],
        "decision": (
            contract["outcome"]["pass"]
            if not violations else contract["outcome"]["reject"]
        ),
        "seeds": observed_seeds,
        "total_changed_active_frames": total_changed,
        "total_frame_or_event_benefit": total_benefit,
        "partitions": partitions,
        "violations": violations,
        "public_authority_consumed": False,
        "shipping_authority": False,
        "automatic_main_mutation": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def agc_case(report: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(case for case in report["cases"] if case["case_id"] == case_id)


def compare_full_pipeline(base: dict[str, Any], candidate: dict[str, Any],
                          gates: dict[str, Any], seed: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if gates["require_baseline_pass"] and base.get("validation_result") != "PASS":
        raise ValueError(f"AGC confirmation baseline failed full-pipeline seed {seed}")
    if gates["require_candidate_pass"] and candidate.get("validation_result") != "PASS":
        out.append({
            "gate": "full_pipeline_candidate_pass",
            "actual": candidate.get("validation_result"),
        })
    b = base.get("summary", {})
    c = candidate.get("summary", {})

    comparisons = (
        ("pass_rate", "min_delta", float(gates["min_pass_rate_delta"])),
        ("p10_near_si_sdr_improvement_db", "max_drop",
         float(gates["max_p10_near_si_sdr_drop_db"])),
        ("p10_noise_only_attenuation_db", "max_drop",
         float(gates["max_p10_noise_attenuation_drop_db"])),
        ("min_vad_f1", "max_drop", float(gates["max_min_vad_f1_drop"])),
        ("max_vad_false_positive_rate", "max_rise",
         float(gates["max_max_vad_fpr_rise"])),
        ("max_output_clip_fraction", "max_rise",
         float(gates["max_clip_fraction_rise"])),
    )
    for metric, kind, allowed in comparisons:
        base_value = b.get(metric)
        cand_value = c.get(metric)
        if base_value is None and cand_value is None:
            continue
        if base_value is None or cand_value is None:
            out.append({
                "gate": "full_pipeline_metric_missing",
                "metric": metric,
                "baseline": base_value,
                "candidate": cand_value,
            })
            continue
        bv = finite(base_value, f"base {metric}")
        cv = finite(cand_value, f"candidate {metric}")
        if kind == "min_delta":
            delta = cv - bv
            if delta < allowed - 1.0e-12:
                out.append({
                    "gate": "full_pipeline_pass_rate_delta",
                    "metric": metric, "actual": delta, "expected_min": allowed,
                })
        elif kind == "max_drop":
            drop = bv - cv
            if drop > allowed + 1.0e-12:
                out.append({
                    "gate": "full_pipeline_metric_drop",
                    "metric": metric, "actual": drop, "allowed": allowed,
                })
        else:
            rise = cv - bv
            if rise > allowed + 1.0e-12:
                out.append({
                    "gate": "full_pipeline_metric_rise",
                    "metric": metric, "actual": rise, "allowed": allowed,
                })
    return out


def confirm_agc(base_probe: Path, candidate_probe: Path,
                dynamic_corpora: list[Path],
                full_base_reports: list[Path],
                full_candidate_reports: list[Path],
                contract_path: Path, output: Path) -> dict[str, Any]:
    contract = load(contract_path)
    if contract.get("authority") != "INDEPENDENT_SOURCE_CANDIDATE_CONFIRMATION_ONLY":
        raise ValueError("unexpected AGC confirmation authority")
    if contract.get("candidate_id") != "agc-error-adaptive-release-v1":
        raise ValueError("unexpected AGC candidate")
    dyn_spec = contract["dynamics_confirmation"]
    full_spec = contract["full_pipeline_confirmation"]
    expected_dyn = [int(x) for x in dyn_spec["seeds"]]
    expected_full = [int(x) for x in full_spec["seeds"]]
    if len(dynamic_corpora) != len(expected_dyn):
        raise ValueError("AGC dynamics confirmation corpus count mismatch")
    if len(full_base_reports) != len(expected_full) or len(full_candidate_reports) != len(expected_full):
        raise ValueError("AGC full-pipeline confirmation report count mismatch")

    dyn_gates = dyn_spec["gates"]
    dynamic_rows = []
    improvements: list[float] = []
    violations: list[dict[str, Any]] = []
    observed_dyn: list[int] = []

    for corpus in dynamic_corpora:
        payload = load(corpus)
        seed = int(payload.get("generator", {}).get("seed"))
        observed_dyn.append(seed)
        base = agc_diag.diagnose(base_probe, corpus, -20.0, -2.0)
        cand = agc_diag.diagnose(candidate_probe, corpus, -20.0, -2.0)
        local: list[dict[str, Any]] = []
        if dyn_gates["require_baseline_pass"] and base["validation_result"] != "PASS":
            raise ValueError(f"AGC baseline failed dynamics confirmation seed {seed}")
        if dyn_gates["require_candidate_pass"] and cand["validation_result"] != "PASS":
            local.append({"gate": "candidate_dynamic_gates", "actual": cand["validation_result"]})

        bstep = agc_case(base, "agc-level-step")
        cstep = agc_case(cand, "agc-level-step")
        improvement = (
            finite(bstep["hot_to_low_settle_frames"], "base hot-to-low")
            - finite(cstep["hot_to_low_settle_frames"], "candidate hot-to-low")
        )
        improvements.append(improvement)
        attack_reg = (
            finite(cstep["low_to_hot_settle_frames"], "candidate low-to-hot")
            - finite(bstep["low_to_hot_settle_frames"], "base low-to-hot")
        )
        slew_reg = (
            finite(cstep["p95_abs_gain_step_db"], "candidate slew")
            - finite(bstep["p95_abs_gain_step_db"], "base slew")
        )
        peak_reg = max(
            finite(c["max_output_peak_dbfs"], "candidate peak")
            - finite(b["max_output_peak_dbfs"], "base peak")
            for b, c in zip(base["cases"], cand["cases"])
        )

        steady_reg = 0.0
        for case_id in ("agc-steady-low", "agc-steady-hot"):
            bcase = agc_case(base, case_id)
            ccase = agc_case(cand, case_id)
            b_error = abs(finite(bcase["tail_output_rms_dbfs"], "base steady") + 20.0)
            c_error = abs(finite(ccase["tail_output_rms_dbfs"], "candidate steady") + 20.0)
            steady_reg = max(steady_reg, c_error - b_error)

        if attack_reg > float(dyn_gates["max_low_to_hot_regression_frames"]) + 1.0e-12:
            local.append({"gate": "low_to_hot_regression", "actual": attack_reg,
                          "allowed": dyn_gates["max_low_to_hot_regression_frames"]})
        if slew_reg > float(dyn_gates["max_slew_regression_db"]) + 1.0e-12:
            local.append({"gate": "slew_regression", "actual": slew_reg,
                          "allowed": dyn_gates["max_slew_regression_db"]})
        if peak_reg > float(dyn_gates["max_peak_regression_db"]) + 1.0e-12:
            local.append({"gate": "peak_regression", "actual": peak_reg,
                          "allowed": dyn_gates["max_peak_regression_db"]})
        if steady_reg > float(dyn_gates["max_steady_level_error_regression_db"]) + 1.0e-12:
            local.append({"gate": "steady_level_error_regression", "actual": steady_reg,
                          "allowed": dyn_gates["max_steady_level_error_regression_db"]})

        dynamic_rows.append({
            "seed": seed,
            "hot_to_low_improvement_frames": improvement,
            "low_to_hot_regression_frames": attack_reg,
            "slew_regression_db": slew_reg,
            "peak_regression_db": peak_reg,
            "steady_level_error_regression_db": steady_reg,
            "violations": local,
        })
        if local:
            violations.append({"seed": seed, "dynamics_violations": local})

    if observed_dyn != expected_dyn:
        raise ValueError(
            f"AGC dynamics confirmation seeds drifted: {observed_dyn} != {expected_dyn}"
        )
    median_improvement = statistics.median(improvements)
    if median_improvement < float(dyn_gates["min_median_hot_to_low_improvement_frames"]) - 1.0e-12:
        violations.append({
            "gate": "median_hot_to_low_improvement_frames",
            "actual": median_improvement,
            "expected_min": dyn_gates["min_median_hot_to_low_improvement_frames"],
        })

    full_rows = []
    for seed, base_path, cand_path in zip(expected_full, full_base_reports, full_candidate_reports):
        base = load(base_path)
        cand = load(cand_path)
        local = compare_full_pipeline(base, cand, full_spec["gates"], seed)
        full_rows.append({
            "seed": seed,
            "baseline_validation_result": base.get("validation_result"),
            "candidate_validation_result": cand.get("validation_result"),
            "baseline_summary": base.get("summary", {}),
            "candidate_summary": cand.get("summary", {}),
            "violations": local,
        })
        if local:
            violations.append({"seed": seed, "full_pipeline_violations": local})

    result = {
        "schema_version": 1,
        "authority": "independent-source-candidate-confirmation-only",
        "candidate_id": contract["candidate_id"],
        "decision": (
            contract["outcome"]["pass"]
            if not violations else contract["outcome"]["reject"]
        ),
        "dynamic_seeds": observed_dyn,
        "full_pipeline_seeds": expected_full,
        "median_hot_to_low_improvement_frames": median_improvement,
        "dynamics": dynamic_rows,
        "full_pipeline": full_rows,
        "violations": violations,
        "shipping_authority": False,
        "automatic_main_mutation": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    assert abs(event_metrics.percentile([0.0, 10.0], 0.95) - 9.5) < 1.0e-9
    base = {"pass_rate": 1.0, "min_vad_f1": 0.8}
    cand = {"pass_rate": 1.0, "min_vad_f1": 0.81}
    _, _, delta = metric_delta(base, cand, "min_vad_f1")
    assert delta is not None and delta > 0
    print("stage source confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--candidate", choices=("vad", "agc"))
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--base-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--base-probe", type=Path)
    parser.add_argument("--candidate-probe", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--full-base-report", action="append", type=Path, default=[])
    parser.add_argument("--full-candidate-report", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.candidate is None or args.contract is None or args.output is None:
        parser.error("--candidate, --contract and --output are required")
    if args.candidate == "vad":
        if args.base_processor is None or args.candidate_processor is None:
            parser.error("VAD confirmation requires processors")
        result = confirm_vad(
            args.base_processor.resolve(),
            args.candidate_processor.resolve(),
            [path.resolve() for path in args.corpus],
            args.contract.resolve(),
            args.output.resolve(),
        )
    else:
        if args.base_probe is None or args.candidate_probe is None:
            parser.error("AGC confirmation requires probes")
        result = confirm_agc(
            args.base_probe.resolve(),
            args.candidate_probe.resolve(),
            [path.resolve() for path in args.corpus],
            [path.resolve() for path in args.full_base_report],
            [path.resolve() for path in args.full_candidate_report],
            args.contract.resolve(),
            args.output.resolve(),
        )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "decision": result["decision"],
        "violations": len(result["violations"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
