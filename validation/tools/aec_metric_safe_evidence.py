#!/usr/bin/env python3
"""Build candidate-zero AEC stage-appropriate metric evidence.

No algorithm thresholds are tuned here. The tool replays the frozen S002
transition corpus, preserves canonical report metrics, adds HPF-aware near-end
reference metrics, and records transition residual trajectories.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path

import run_validation_engine as engine
from build_validation_corpus import RATE, write_pcm

TRANSITION_CASES = {
    "echo-path-change",
    "speaker-acoustic-gain-step",
    "render-level-step",
}
NEAR_REFERENCE_CASES = {"near-end-only", "double-talk"}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def read_trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_hpf_reference(
    processor: Path,
    clean: list[int],
    work: Path,
) -> tuple[list[int], int]:
    inp = work / "clean-hpf-in.pcm"
    out = work / "clean-hpf-out.pcm"
    metrics = work / "clean-hpf-metrics.jsonl"
    write_pcm(inp, clean)
    subprocess.run(
        [
            str(processor),
            "--sample-rate", str(RATE),
            "--mic-channels", "1",
            "--metrics-jsonl", str(metrics),
            "--capture-profile", "prefix-capture",
            "--capture-only",
            str(inp),
            str(out),
        ],
        check=True,
    )
    trace = read_trace(metrics)
    if not trace:
        raise ValueError("HPF reference trace missing")
    latency_ms = int(trace[0].get("algorithmic_latency_ms", -1))
    if latency_ms < 0:
        raise ValueError("HPF reference latency invalid")
    return [int(x) for x in engine.read_raw_array(out)], latency_ms * RATE // 1000


def power_ratio_db(
    echo: list[int],
    output: list[int],
    *,
    start_sample: int,
    end_sample: int,
    output_delay_samples: int,
) -> float | None:
    start = max(0, start_sample)
    end = min(len(echo), end_sample)
    if end - start < RATE // 20:
        return None
    echo_energy = 0.0
    output_energy = 0.0
    count = 0
    for index in range(start, end):
        out_index = index + output_delay_samples
        if out_index < 0 or out_index >= len(output):
            continue
        x = float(echo[index])
        y = float(output[out_index])
        echo_energy += x * x
        output_energy += y * y
        count += 1
    if count < RATE // 20 or echo_energy <= 1.0e-12:
        return None
    return 10.0 * math.log10((output_energy + 1.0e-12) / (echo_energy + 1.0e-12))


def transition_windows(
    case: dict,
    output: list[int],
    echo: list[int],
    output_delay_samples: int,
    contract: dict,
) -> dict:
    dims = case.get("dimensions", {})
    frame = int(dims.get("frame", -1))
    if frame < 0:
        raise ValueError(f"{case['case_id']}: transition frame missing")
    transition_sample = frame * (RATE // 100)
    result = {}
    for name in ("pre_ms", "early_post_ms", "late_post_ms"):
        start_ms, end_ms = contract["transition_windows"][name]
        start = transition_sample + int(start_ms * RATE / 1000)
        end = transition_sample + int(end_ms * RATE / 1000)
        result[name.removesuffix("_ms")] = {
            "start_ms_relative": start_ms,
            "end_ms_relative": end_ms,
            "residual_to_echo_power_db": power_ratio_db(
                echo,
                output,
                start_sample=start,
                end_sample=end,
                output_delay_samples=output_delay_samples,
            ),
        }
    return result


def canonical_case_map(report: dict) -> dict[str, dict]:
    return {str(item["case_id"]): item for item in report.get("cases", [])}


def evaluate_seed(
    corpus_path: Path,
    report_path: Path,
    full_processor: Path,
    hpf_processor: Path,
    contract: dict,
) -> dict:
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    report_cases = canonical_case_map(report)
    expected_cases = set(contract["metric_applicability"])
    actual_cases = {case["case_id"] for case in corpus["cases"]}
    if actual_cases != expected_cases:
        raise ValueError(
            f"AEC transition case set drift: {sorted(actual_cases)} != {sorted(expected_cases)}"
        )

    rows: list[dict] = []
    for case in corpus["cases"]:
        case_id = case["case_id"]
        canonical = report_cases.get(case_id)
        if canonical is None:
            raise ValueError(f"canonical report missing {case_id}")
        with tempfile.TemporaryDirectory(prefix=f"ap-aec-metric-{case_id}-") as raw:
            work = Path(raw)
            # Canonical report metrics remain authoritative. This replay is
            # used only to materialize output PCM for additional metric-safe
            # evidence; it intentionally does not reimplement canonical
            # render-correlation semantics.
            output, trace, _inputs = engine.invoke(
                full_processor, case, corpus_path, work
            )
            metrics = dict(canonical["metrics"])
            derived: dict = {}
            declared_latency_ms = int(metrics.get("declared_algorithmic_latency_ms", 0) or 0)
            output_delay_samples = declared_latency_ms * RATE // 1000

            if case_id in NEAR_REFERENCE_CASES:
                clean_path = engine.resolve(
                    corpus_path, case.get("clean_near_audio")
                )
                if clean_path is None:
                    raise ValueError(f"{case_id}: clean reference missing")
                clean = engine.read_audio_samples(clean_path, RATE, 1)
                hpf_ref, hpf_delay = run_hpf_reference(
                    hpf_processor,
                    [int(x) for x in clean],
                    work,
                )
                expected_delay = max(0, output_delay_samples - hpf_delay)
                hpf_sdr, alignment = engine.aligned_si_sdr(
                    hpf_ref,
                    output,
                    RATE,
                    expected_delay,
                )
                derived["hpf_aware_near_si_sdr_db"] = hpf_sdr
                derived["hpf_aware_alignment_samples"] = alignment
                derived["raw_near_improvement_primary_applicable"] = not (
                    case_id == "near-end-only"
                )
                derived["raw_input_reference_identical"] = bool(
                    metrics.get("input_near_reference_identical")
                )

            if case_id in TRANSITION_CASES:
                echo_path = engine.resolve(corpus_path, case.get("echo_audio"))
                if echo_path is None:
                    raise ValueError(f"{case_id}: echo reference missing")
                echo = engine.read_audio_samples(echo_path, RATE, 1)
                derived["transition_residual_windows"] = transition_windows(
                    case,
                    [int(x) for x in output],
                    [int(x) for x in echo],
                    output_delay_samples,
                    contract,
                )

        applicability = contract["metric_applicability"][case_id]
        required = list(applicability.get("required_metrics", []))
        combined = {**metrics, **derived}
        missing = []
        for metric in required:
            if metric == "transition_residual_windows":
                value = derived.get(metric)
                if not isinstance(value, dict):
                    missing.append(metric)
                elif any(
                    window.get("residual_to_echo_power_db") is None
                    for window in value.values()
                ):
                    missing.append(metric)
            elif combined.get(metric) is None:
                missing.append(metric)

        rows.append({
            "case_id": case_id,
            "role": applicability["role"],
            "canonical_policy_passed": bool(canonical.get("passed", False)),
            "required_metrics": required,
            "forbidden_primary_metrics": applicability.get(
                "forbidden_primary_metrics", []
            ),
            "secondary_metrics": applicability.get("secondary_metrics", []),
            "canonical_metrics": metrics,
            "derived_metrics": derived,
            "metric_contract_complete": not missing,
            "missing_required_metrics": missing,
        })

    seed = int(corpus["generator"]["seed"])
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": seed,
        "authority": "candidate-zero-metric-applicability-only",
        "cases": rows,
        "summary": {
            "cases": len(rows),
            "metric_contract_complete_cases": sum(
                item["metric_contract_complete"] for item in rows
            ),
            "incomplete_cases": sum(
                not item["metric_contract_complete"] for item in rows
            ),
            "near_end_only_raw_near_improvement_primary_rejected": True,
        },
        "candidate_authority": False,
        "algorithm_performance_verdict_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("fresh seed mismatch")

    case_ids = sorted(contract["metric_applicability"])
    rows = []
    for case_id in case_ids:
        observations = []
        role = contract["metric_applicability"][case_id]["role"]
        required = sorted(
            contract["metric_applicability"][case_id].get("required_metrics", [])
        )
        for seed in expected_seeds:
            match = next(
                (item for item in by_seed[seed]["cases"] if item["case_id"] == case_id),
                None,
            )
            if match is None:
                raise ValueError(f"{case_id}: missing on seed {seed}")
            observations.append({
                "seed": seed,
                "role": match["role"],
                "required_metrics": sorted(match["required_metrics"]),
                "metric_contract_complete": match["metric_contract_complete"],
            })
        consistent = all(
            item["role"] == role
            and item["required_metrics"] == required
            and item["metric_contract_complete"]
            for item in observations
        )
        rows.append({
            "case_id": case_id,
            "role": role,
            "required_metrics": required,
            "fresh_seed_metric_role_consistent": consistent,
            "observations": observations,
        })

    complete = all(row["fresh_seed_metric_role_consistent"] for row in rows)
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "cases": rows,
        "metric_applicability_map_complete": complete,
        "near_end_only_raw_clean_si_sdr_primary_metric_rejected": True,
        "transition_recovery_is_evidence_only": True,
        "algorithm_performance_verdict": "NOT_AUTHORIZED",
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    echo = [1000] * RATE
    output = [100] * RATE
    value = power_ratio_db(
        echo,
        output,
        start_sample=0,
        end_sample=RATE,
        output_delay_samples=0,
    )
    assert value is not None and abs(value + 20.0) < 1.0e-6
    print("AEC metric-safe evidence self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    run_p = sub.add_parser("run")
    run_p.add_argument("--corpus", type=Path, required=True)
    run_p.add_argument("--report", type=Path, required=True)
    run_p.add_argument("--full-processor", type=Path, required=True)
    run_p.add_argument("--hpf-processor", type=Path, required=True)
    run_p.add_argument("--contract", type=Path, required=True)
    run_p.add_argument("--output", type=Path, required=True)
    agg_p = sub.add_parser("aggregate")
    agg_p.add_argument("--contract", type=Path, required=True)
    agg_p.add_argument("--input", type=Path, action="append", required=True)
    agg_p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "self-test":
        self_test()
        return 0

    contract = load_json(args.contract)
    if contract["authority"] != "CANDIDATE_ZERO_DIAGNOSTIC_ONLY":
        raise ValueError("authority drift")
    if args.command == "run":
        result = evaluate_seed(
            args.corpus,
            args.report,
            args.full_processor,
            args.hpf_processor,
            contract,
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
        print(json.dumps({"seed": result["seed"], **result["summary"]}, sort_keys=True))
    else:
        print(json.dumps({
            "metric_applicability_map_complete":
                result["metric_applicability_map_complete"],
            "cases": len(result["cases"]),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
