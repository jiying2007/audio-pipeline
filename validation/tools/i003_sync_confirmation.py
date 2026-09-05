#!/usr/bin/env python3
"""Fixed-candidate independent confirmation for I003 Sync delay selection.

The confirmation contract is frozen before any confirmation seed is executed.
This tool compares one exact base processor with one exact candidate processor
on the same newly generated geometry-v2 PCM. It cannot search candidates or
change tuning parameters.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "validation/tools/build_aec_motion_corpus.py"
RUN_VALIDATION = ROOT / "validation/tools/run_validation.py"
POLICY = ROOT / "validation/policies/validation-aec-motion-development.json"
DATASET_LOCK = ROOT / "validation/datasets.lock.json"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def percentile(values: list[float], q: float) -> float:
    require(values, "empty percentile")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def load_generator():
    spec = importlib.util.spec_from_file_location("i003_confirmation_generator", GENERATOR)
    require(spec is not None and spec.loader is not None, "cannot load canonical motion generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_contract(contract: dict) -> None:
    require(contract.get("schema_version") == 1, "confirmation schema")
    require(contract.get("iteration_id") == "I003", "confirmation iteration")
    require(contract.get("root_cause_id") == "aec-motion-continuous-tracking", "confirmation root cause")
    require(contract.get("phase") == "independent-confirmation", "confirmation phase")
    require(contract.get("authority") == "fixed-candidate-independent-confirmation", "confirmation authority")
    require(contract.get("candidate") == "incumbent-qualified", "frozen candidate")
    for field in ("base_sha", "candidate_implementation_sha"):
        value = contract.get(field)
        require(isinstance(value, str) and len(value) == 40 and
                all(c in "0123456789abcdef" for c in value), f"{field} must be exact SHA")
    source = contract.get("source_group")
    require(isinstance(source, dict), "source group")
    require(source.get("id") == "aec-motion-geometry-v2-i003-confirmation-1", "source group id")
    require(source.get("kind") == "deterministic-synthetic", "source group kind")
    require(source.get("generator") == "validation/tools/build_aec_motion_corpus.py" and
            source.get("generator_version") == 2, "generator contract")
    require(source.get("seeds") == [51107, 52107, 53107], "confirmation seeds")
    require(source.get("seconds") == 8.0, "confirmation duration")
    require(source.get("observed_before_candidate_freeze") is False, "source group independence")
    require(source.get("role_before_execution") == "confirmation-pending" and
            source.get("role_after_execution") == "regression-retired", "source group lifecycle")
    budget = contract.get("budget")
    require(budget == {
        "confirmation_sets_limit": 2,
        "confirmation_sets_consumed_before": 0,
        "confirmation_sets_consumed_if_executed": 1,
    }, "confirmation budget")
    acceptance = contract.get("acceptance")
    require(isinstance(acceptance, dict), "acceptance contract")
    require(acceptance.get("warmup_frames") == 20, "warmup")
    require(acceptance.get("direct_delay_ms") == 42, "direct delay")
    require(acceptance.get("late_error_ms") == 4 and acceptance.get("severe_error_ms") == 20,
            "error thresholds")
    per_seed = acceptance.get("per_seed")
    require(per_seed == {
        "candidate_median_abs_delay_error_ms_must_not_exceed_base": True,
        "candidate_p95_abs_delay_error_ms_must_not_exceed_base": True,
        "candidate_late_error_count_must_not_exceed_base": True,
        "candidate_severe_error_count_must_not_exceed_base": True,
        "canonical_validation_must_pass": True,
    }, "per-seed acceptance")
    aggregate = acceptance.get("aggregate")
    require(aggregate == {
        "strict_improvement_required": True,
        "strict_improvement_metrics": [
            "p95_abs_delay_error_ms", "late_error_count", "severe_error_count"
        ],
        "all_three_seeds_must_pass": True,
    }, "aggregate acceptance")
    constraints = contract.get("constraints")
    require(isinstance(constraints, dict) and
            constraints.get("candidate_search_allowed") is False and
            constraints.get("candidate_ranking_allowed") is False and
            constraints.get("threshold_tuning_allowed") is False and
            constraints.get("confirmation_result_may_change_candidate") is False and
            constraints.get("promotion_allowed_by_confirmation_alone") is False,
            "confirmation must be one-way fixed-candidate")


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def run_processor(processor: Path, corpus_root: Path, corpus: dict, output: Path, label: str) -> None:
    metrics_root = output / f"{label}-metrics"
    pcm_root = output / f"{label}-pcm"
    metrics_root.mkdir(parents=True, exist_ok=False)
    pcm_root.mkdir(parents=True, exist_ok=False)
    for case in corpus["cases"]:
        case_id = case["case_id"]
        mic = corpus_root / case["mic_audio"]
        render = corpus_root / case["render_audio"]
        metrics = metrics_root / f"{case_id}.jsonl"
        out_pcm = pcm_root / f"{case_id}.pcm"
        run_checked([
            str(processor),
            "--sample-rate", str(case["sample_rate_hz"]),
            "--mic-channels", str(case["mic_channels"]),
            "--metrics-jsonl", str(metrics),
            str(mic), str(render), str(out_pcm),
        ])


def load_metric_rows(path: Path, warmup: int) -> list[dict]:
    rows: list[dict] = []
    seen: set[int] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            frame = row.get("frame")
            require(type(frame) is int and frame >= 0 and frame not in seen, f"metric frame: {path}")
            seen.add(frame)
            if frame >= warmup:
                rows.append(row)
    require(rows, f"no post-warmup metrics: {path}")
    return rows


def summarize_seed(corpus: dict, root: Path, label: str, acceptance: dict) -> dict:
    direct = float(acceptance["direct_delay_ms"])
    late = float(acceptance["late_error_ms"])
    severe = float(acceptance["severe_error_ms"])
    warmup = int(acceptance["warmup_frames"])
    errors: list[float] = []
    case_summaries: dict[str, dict] = {}
    for case in corpus["cases"]:
        case_id = case["case_id"]
        path = root / f"{label}-metrics" / f"{case_id}.jsonl"
        rows = load_metric_rows(path, warmup)
        case_errors = [abs(float(row["estimated_delay_ms"]) - direct) for row in rows]
        errors.extend(case_errors)
        case_summaries[case_id] = {
            "observations": len(case_errors),
            "median_abs_delay_error_ms": statistics.median(case_errors),
            "p95_abs_delay_error_ms": percentile(case_errors, 0.95),
            "late_error_count": sum(value > late for value in case_errors),
            "severe_error_count": sum(value > severe for value in case_errors),
        }
    require(len(case_summaries) == 12, "confirmation case matrix")
    return {
        "observations": len(errors),
        "median_abs_delay_error_ms": statistics.median(errors),
        "p95_abs_delay_error_ms": percentile(errors, 0.95),
        "late_error_count": sum(value > late for value in errors),
        "severe_error_count": sum(value > severe for value in errors),
        "late_error_rate": sum(value > late for value in errors) / len(errors),
        "severe_error_rate": sum(value > severe for value in errors) / len(errors),
        "cases": case_summaries,
    }


def seed_pass(base: dict, candidate: dict, canonical_pass: bool) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if candidate["median_abs_delay_error_ms"] > base["median_abs_delay_error_ms"]:
        failures.append("median_abs_delay_error_ms_regressed")
    if candidate["p95_abs_delay_error_ms"] > base["p95_abs_delay_error_ms"]:
        failures.append("p95_abs_delay_error_ms_regressed")
    if candidate["late_error_count"] > base["late_error_count"]:
        failures.append("late_error_count_regressed")
    if candidate["severe_error_count"] > base["severe_error_count"]:
        failures.append("severe_error_count_regressed")
    if not canonical_pass:
        failures.append("canonical_validation_failed")
    return not failures, failures


def aggregate_stats(items: list[dict]) -> dict:
    total_obs = sum(item["observations"] for item in items)
    require(total_obs > 0, "aggregate observations")
    # Seed summaries use equal geometry/case duration, so count aggregation is exact;
    # p95 is intentionally the worst seed p95 for a conservative fixed-candidate gate.
    return {
        "observations": total_obs,
        "median_abs_delay_error_ms": max(item["median_abs_delay_error_ms"] for item in items),
        "p95_abs_delay_error_ms": max(item["p95_abs_delay_error_ms"] for item in items),
        "late_error_count": sum(item["late_error_count"] for item in items),
        "severe_error_count": sum(item["severe_error_count"] for item in items),
    }


def self_test() -> None:
    assert percentile([0.0, 1.0, 2.0, 3.0], 0.5) == 1.5
    base = {
        "median_abs_delay_error_ms": 1.0,
        "p95_abs_delay_error_ms": 12.0,
        "late_error_count": 9,
        "severe_error_count": 2,
    }
    good = dict(base, p95_abs_delay_error_ms=4.0, late_error_count=2, severe_error_count=0)
    bad = dict(good, median_abs_delay_error_ms=2.0)
    assert seed_pass(base, good, True)[0]
    assert not seed_pass(base, bad, True)[0]
    assert not seed_pass(base, good, False)[0]
    print(json.dumps({"result": "PASS", "mode": "fixed-candidate-confirmation"}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--base-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract and args.base_processor and args.candidate_processor and args.output,
            "contract, processors and output are required")
    contract = load_json(args.contract)
    validate_contract(contract)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    base_processor = args.base_processor.resolve()
    candidate_processor = args.candidate_processor.resolve()
    require(base_processor.is_file() and candidate_processor.is_file(), "processor binaries")

    gen = load_generator()
    require(gen.GENERATOR_VERSION == contract["source_group"]["generator_version"], "generator version drift")
    gen.validate_model(gen.MODEL)
    seed_results: list[dict] = []

    for seed in contract["source_group"]["seeds"]:
        seed_root = output / f"seed-{seed}"
        corpus_root = seed_root / "corpus"
        seed_root.mkdir(parents=True, exist_ok=False)
        corpus = gen.build(corpus_root, seed, contract["source_group"]["seconds"])
        run_processor(base_processor, corpus_root, corpus, seed_root, "base")
        run_processor(candidate_processor, corpus_root, corpus, seed_root, "candidate")

        report = seed_root / "candidate-validation-report.json"
        evidence = seed_root / "candidate-validation-evidence.json"
        run_checked([
            "python3", str(RUN_VALIDATION),
            "--source-revision", contract["candidate_implementation_sha"],
            "--corpus", str(corpus_root / "corpus.json"),
            "--policy", str(POLICY),
            "--dataset-lock", str(DATASET_LOCK),
            "--source-manifest", str(corpus_root / "source-manifest.json"),
            "--processor", str(candidate_processor),
            "--output", str(report),
            "--evidence-manifest", str(evidence),
            "--enforce",
        ])
        canonical = load_json(report)
        canonical_pass = canonical.get("validation_result") == "PASS"
        base_summary = summarize_seed(corpus, seed_root, "base", contract["acceptance"])
        candidate_summary = summarize_seed(corpus, seed_root, "candidate", contract["acceptance"])
        passed, failures = seed_pass(base_summary, candidate_summary, canonical_pass)
        seed_results.append({
            "seed": seed,
            "corpus_id": corpus["corpus_id"],
            "model_sha256": corpus["generator"]["model_sha256"],
            "base": base_summary,
            "candidate": candidate_summary,
            "canonical_validation_result": canonical.get("validation_result"),
            "passed": passed,
            "failures": failures,
        })

    base_aggregate = aggregate_stats([item["base"] for item in seed_results])
    candidate_aggregate = aggregate_stats([item["candidate"] for item in seed_results])
    strict = any([
        candidate_aggregate["p95_abs_delay_error_ms"] < base_aggregate["p95_abs_delay_error_ms"],
        candidate_aggregate["late_error_count"] < base_aggregate["late_error_count"],
        candidate_aggregate["severe_error_count"] < base_aggregate["severe_error_count"],
    ])
    all_pass = all(item["passed"] for item in seed_results)
    decision = "CONFIRM_CANDIDATE" if all_pass and strict else "REJECT_CANDIDATE"
    result = {
        "schema_version": 1,
        "iteration_id": "I003",
        "root_cause_id": contract["root_cause_id"],
        "authority": contract["authority"],
        "base_sha": contract["base_sha"],
        "candidate_implementation_sha": contract["candidate_implementation_sha"],
        "candidate": contract["candidate"],
        "source_group": contract["source_group"],
        "budget_consumed": 1,
        "candidate_search_performed": False,
        "threshold_tuning_performed": False,
        "seed_results": seed_results,
        "aggregate": {
            "base": base_aggregate,
            "candidate": candidate_aggregate,
            "strict_improvement": strict,
        },
        "decision": decision,
        "source_group_next_role": "regression-retired",
        "promotion_allowed_by_this_result_alone": False,
        "processor_sha256": {
            "base": sha256(base_processor),
            "candidate": sha256(candidate_processor),
        },
    }
    write_json(output / "confirmation-result.json", result)
    print(json.dumps({
        "decision": decision,
        "base_p95_ms": base_aggregate["p95_abs_delay_error_ms"],
        "candidate_p95_ms": candidate_aggregate["p95_abs_delay_error_ms"],
        "base_late": base_aggregate["late_error_count"],
        "candidate_late": candidate_aggregate["late_error_count"],
        "base_severe": base_aggregate["severe_error_count"],
        "candidate_severe": candidate_aggregate["severe_error_count"],
    }, sort_keys=True))
    return 0 if decision == "CONFIRM_CANDIDATE" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"I003 confirmation contract error: {exc}")
