#!/usr/bin/env python3
"""Deterministic acoustic tuning iteration with strict anti-overfit boundaries.

This tool searches only a designated development corpus, then independently
replays the selected tuning on validation and shadow corpora. It never promotes
shipping defaults. The output is an ACOUSTIC_CANDIDATE at most; blind, target
resource/HIL and product certification remain separate authorities.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TUNING_KEYS = ("aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs")
TUNING_FLAGS = {
    "aec_mu": "--aec-mu",
    "ns_floor": "--ns-floor",
    "agc_target_dbfs": "--agc-target-dbfs",
    "limiter_dbfs": "--limiter-dbfs",
}

DEFAULT_METRICS = [
    {"name": "pass_rate", "direction": "max", "weight": 8.0, "scale": 0.02, "max_regression": 0.0},
    {"name": "p10_near_si_sdr_improvement_db", "direction": "max", "weight": 1.4, "scale": 1.0, "max_regression": 0.75},
    {"name": "p10_noise_only_attenuation_db", "direction": "max", "weight": 0.8, "scale": 1.0, "max_regression": 0.75},
    {"name": "median_erle_db", "direction": "max", "weight": 1.0, "scale": 1.0, "max_regression": 1.0},
    {"name": "min_vad_f1", "direction": "max", "weight": 1.0, "scale": 0.05, "max_regression": 0.05},
    {"name": "max_vad_false_positive_rate", "direction": "min", "weight": 0.6, "scale": 0.05, "max_regression": 0.05},
    {"name": "max_output_clip_fraction", "direction": "min", "weight": 2.0, "scale": 0.002, "max_regression": 0.002},
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_tuning(raw: dict[str, Any]) -> dict[str, float]:
    unknown = set(raw) - set(TUNING_KEYS)
    if unknown:
        raise ValueError(f"unknown tuning keys: {sorted(unknown)}")
    tuning = {key: float(raw[key]) for key in TUNING_KEYS if key in raw}
    for key, value in tuning.items():
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite")
    if "aec_mu" in tuning and not 0.0 < tuning["aec_mu"] <= 1.0:
        raise ValueError("aec_mu must be in (0, 1]")
    if "ns_floor" in tuning and not 0.02 <= tuning["ns_floor"] <= 1.0:
        raise ValueError("ns_floor must be in [0.02, 1]")
    if "agc_target_dbfs" in tuning and not -60.0 <= tuning["agc_target_dbfs"] <= -1.0:
        raise ValueError("agc_target_dbfs must be in [-60, -1]")
    if "limiter_dbfs" in tuning and not -20.0 <= tuning["limiter_dbfs"] <= -0.1:
        raise ValueError("limiter_dbfs must be in [-20, -0.1]")
    if ("agc_target_dbfs" in tuning and "limiter_dbfs" in tuning and
            tuning["agc_target_dbfs"] >= tuning["limiter_dbfs"]):
        raise ValueError("agc_target_dbfs must be below limiter_dbfs")
    return tuning


def validate_search_space(space: dict[str, Any]) -> None:
    if space.get("schema_version") != 1:
        raise ValueError("search space schema_version must be 1")
    if not str(space.get("search_space_id", "")):
        raise ValueError("search_space_id is required")
    baseline = canonical_tuning(space.get("baseline", {}))
    if set(baseline) != set(TUNING_KEYS):
        raise ValueError("baseline must define all supported tuning keys")
    params = space.get("parameters")
    if not isinstance(params, dict) or not params:
        raise ValueError("parameters must be a non-empty object")
    for key, values in params.items():
        if key not in TUNING_KEYS or not isinstance(values, list) or not values:
            raise ValueError(f"invalid parameter grid for {key}")
        for value in values:
            probe = dict(baseline)
            probe[key] = value
            canonical_tuning(probe)
    if space.get("strategy", "one-at-a-time") not in {"one-at-a-time", "cartesian"}:
        raise ValueError("strategy must be one-at-a-time or cartesian")
    maximum = int(space.get("max_candidates", 32))
    if maximum < 1 or maximum > 256:
        raise ValueError("max_candidates must be 1..256")
    objective = space.get("objective", {})
    metrics = objective.get("metrics", DEFAULT_METRICS)
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("objective.metrics must be non-empty")
    for metric in metrics:
        if metric.get("direction") not in {"min", "max"}:
            raise ValueError("metric direction must be min or max")
        if float(metric.get("weight", 0.0)) < 0.0 or float(metric.get("scale", 0.0)) <= 0.0:
            raise ValueError("metric weight/scale invalid")
        if float(metric.get("max_regression", 0.0)) < 0.0:
            raise ValueError("max_regression must be >= 0")


def tuning_id(tuning: dict[str, float]) -> str:
    payload = json.dumps(tuning, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def generate_candidates(space: dict[str, Any]) -> list[dict[str, Any]]:
    validate_search_space(space)
    baseline = canonical_tuning(space["baseline"])
    strategy = space.get("strategy", "one-at-a-time")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(tuning: dict[str, Any], label: str) -> None:
        canonical = canonical_tuning(tuning)
        ident = tuning_id(canonical)
        if ident in seen:
            return
        seen.add(ident)
        candidates.append({"candidate_id": ident, "label": label, "tuning": canonical})

    add(baseline, "baseline")
    if strategy == "one-at-a-time":
        for key in TUNING_KEYS:
            for value in space["parameters"].get(key, []):
                candidate = dict(baseline)
                candidate[key] = float(value)
                add(candidate, f"{key}={value}")
    else:
        keys = [key for key in TUNING_KEYS if key in space["parameters"]]
        grids = [space["parameters"][key] for key in keys]
        for values in itertools.product(*grids):
            candidate = dict(baseline)
            candidate.update(dict(zip(keys, values)))
            add(candidate, "cartesian")

    maximum = int(space.get("max_candidates", 32))
    if len(candidates) > maximum:
        raise ValueError(f"generated {len(candidates)} candidates > max_candidates={maximum}")
    return candidates


def summary_value(report: dict[str, Any], name: str) -> float | None:
    value = report.get("summary", {}).get(name)
    return None if value is None else float(value)


def objective_metrics(space: dict[str, Any]) -> list[dict[str, Any]]:
    return list(space.get("objective", {}).get("metrics", DEFAULT_METRICS))


def score_against_baseline(space: dict[str, Any], baseline: dict[str, Any],
                           candidate: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    score = 0.0
    deltas = []
    for metric in objective_metrics(space):
        name = str(metric["name"])
        base = summary_value(baseline, name)
        cand = summary_value(candidate, name)
        if base is None or cand is None:
            continue
        direction = str(metric["direction"])
        directed = (cand - base) if direction == "max" else (base - cand)
        scale = float(metric.get("scale", 1.0))
        weighted = float(metric.get("weight", 1.0)) * directed / scale
        score += weighted
        deltas.append({
            "metric": name, "baseline": base, "candidate": cand,
            "directed_delta": directed, "weighted_score": weighted,
        })
    return score, deltas


def regression_violations(space: dict[str, Any], baseline: dict[str, Any],
                          candidate: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if candidate.get("validation_result") != "PASS":
        violations.append({"gate": "candidate_validation_result", "actual": candidate.get("validation_result")})
    for metric in objective_metrics(space):
        name = str(metric["name"])
        base = summary_value(baseline, name)
        cand = summary_value(candidate, name)
        if base is None or cand is None:
            continue
        direction = str(metric["direction"])
        regression = (base - cand) if direction == "max" else (cand - base)
        allowed = float(metric.get("max_regression", 0.0))
        if regression > allowed + 1.0e-12:
            violations.append({
                "gate": "metric_regression", "metric": name, "baseline": base,
                "candidate": cand, "regression": regression, "allowed": allowed,
            })
    return violations


def load_corpus_identity(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    return {
        "corpus_id": corpus.get("corpus_id"),
        "tier": corpus.get("tier"),
        "sha256": sha256_file(path),
        "generator_seed": corpus.get("generator", {}).get("seed"),
    }


def enforce_partition_independence(dev: Path, validation: Path, shadow: Path) -> dict[str, Any]:
    identities = {
        "development": load_corpus_identity(dev),
        "validation": load_corpus_identity(validation),
        "shadow": load_corpus_identity(shadow),
    }
    hashes = [item["sha256"] for item in identities.values()]
    ids = [item["corpus_id"] for item in identities.values()]
    seeds = [item["generator_seed"] for item in identities.values()]
    if len(set(hashes)) != 3 or len(set(ids)) != 3:
        raise ValueError("development/validation/shadow corpora must be distinct")
    if all(seed is not None for seed in seeds) and len(set(seeds)) != 3:
        raise ValueError("generated partitions must use distinct seeds")
    if identities["development"]["tier"] not in {"regression", "research-validation"}:
        raise ValueError(
            "development corpus must be regression or research-validation; "
            "validation-grade/blind/product evidence is never legal tuning input"
        )
    return identities


def write_wrapper(path: Path, processor: Path, tuning: dict[str, float]) -> None:
    flags = []
    for key in TUNING_KEYS:
        if key in tuning:
            flags += [TUNING_FLAGS[key], repr(float(tuning[key]))]
    script = [
        "#!/usr/bin/env python3",
        "import os, sys",
        f"processor = {str(processor.resolve())!r}",
        f"prefix = {flags!r}",
        "os.execv(processor, [processor] + prefix + sys.argv[1:])",
        "",
    ]
    path.write_text("\n".join(script), encoding="utf-8")
    path.chmod(0o700)


def run_validation(repo_root: Path, processor: Path, corpus: Path, policy: Path,
                   dataset_lock: Path, tuning: dict[str, float], output: Path) -> tuple[dict[str, Any], float]:
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.with_suffix(".evidence.json")
    with tempfile.TemporaryDirectory(prefix="ap-tuning-wrapper-") as temporary:
        wrapper = Path(temporary) / "processor"
        write_wrapper(wrapper, processor, tuning)
        command = [
            sys.executable, str(repo_root / "validation/tools/run_validation.py"),
            "--corpus", str(corpus), "--policy", str(policy),
            "--dataset-lock", str(dataset_lock), "--processor", str(wrapper),
            "--output", str(output), "--evidence-manifest", str(evidence),
            "--source-revision", os.environ.get("GITHUB_SHA", "local-tuning-iteration"),
            "--enforce",
        ]
        started = time.monotonic()
        completed = subprocess.run(command, cwd=repo_root, text=True, capture_output=True)
        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            if not output.exists():
                raise RuntimeError(
                    f"validation execution failed rc={completed.returncode}: "
                    f"{completed.stderr[-2000:] or completed.stdout[-2000:]}"
                )
        report = json.loads(output.read_text(encoding="utf-8"))
        report["_iteration_elapsed_s"] = elapsed
        report["_iteration_returncode"] = completed.returncode
        return report, elapsed


def bind_report(path: Path, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "validation_result": report.get("validation_result"),
        "summary": report.get("summary", {}),
    }


def iterate(repo_root: Path, processor: Path, dev: Path, validation: Path, shadow: Path,
            policy: Path, dataset_lock: Path, search_space_path: Path, output_dir: Path,
            candidate_jobs: int = 1) -> dict[str, Any]:
    space = json.loads(search_space_path.read_text(encoding="utf-8"))
    validate_search_space(space)
    identities = enforce_partition_independence(dev, validation, shadow)
    candidates = generate_candidates(space)
    output_dir.mkdir(parents=True, exist_ok=True)

    if candidate_jobs < 1 or candidate_jobs > 8:
        raise ValueError("candidate_jobs must be 1..8")
    baseline_candidate = candidates[0]

    def evaluate_development(candidate: dict[str, Any]) -> dict[str, Any]:
        report_path = output_dir / "development" / f"{candidate['candidate_id']}.json"
        report, elapsed = run_validation(repo_root, processor, dev, policy, dataset_lock,
                                         candidate["tuning"], report_path)
        return {
            **candidate,
            "report_path": str(report_path),
            "report_sha256": sha256_file(report_path),
            "validation_result": report.get("validation_result"),
            "elapsed_s": elapsed,
            "report": report,
        }

    if candidate_jobs == 1:
        dev_results = [evaluate_development(candidate) for candidate in candidates]
    else:
        with ThreadPoolExecutor(max_workers=candidate_jobs) as executor:
            dev_results = list(executor.map(evaluate_development, candidates))
    baseline_dev_report = next(
        item["report"] for item in dev_results if item["label"] == "baseline"
    )

    for result in dev_results:
        score, deltas = score_against_baseline(space, baseline_dev_report, result["report"])
        result["score"] = score
        result["objective_deltas"] = deltas

    eligible_dev = [result for result in dev_results if result["validation_result"] == "PASS"]
    eligible_dev.sort(key=lambda item: (-float(item["score"]), item["candidate_id"]))
    selected = eligible_dev[0] if eligible_dev else dev_results[0]
    min_score = float(space.get("objective", {}).get("minimum_improvement_score", 0.05))
    if selected["candidate_id"] == baseline_candidate["candidate_id"] or selected["score"] < min_score:
        selected = dev_results[0]

    validation_reports = {}
    shadow_reports = {}
    for role, candidate in (("baseline", dev_results[0]), ("candidate", selected)):
        val_path = output_dir / "validation" / f"{role}.json"
        val_report, val_elapsed = run_validation(
            repo_root, processor, validation, policy, dataset_lock, candidate["tuning"], val_path
        )
        validation_reports[role] = (val_path, val_report, val_elapsed)
        shadow_path = output_dir / "shadow" / f"{role}.json"
        shadow_report, shadow_elapsed = run_validation(
            repo_root, processor, shadow, policy, dataset_lock, candidate["tuning"], shadow_path
        )
        shadow_reports[role] = (shadow_path, shadow_report, shadow_elapsed)

    validation_violations = regression_violations(
        space, validation_reports["baseline"][1], validation_reports["candidate"][1]
    )
    shadow_violations = regression_violations(
        space, shadow_reports["baseline"][1], shadow_reports["candidate"][1]
    )
    same_as_baseline = selected["candidate_id"] == baseline_candidate["candidate_id"]
    decision = "KEEP_BASELINE" if same_as_baseline else (
        "ACOUSTIC_CANDIDATE" if not validation_violations and not shadow_violations else "REJECT_CANDIDATE"
    )

    result = {
        "schema_version": 1,
        "iteration_id": f"{space['search_space_id']}:{selected['candidate_id']}",
        "decision": decision,
        "authority": "non-shipping-acoustic-iteration",
        "search_space": {
            "id": space["search_space_id"],
            "sha256": sha256_file(search_space_path),
            "strategy": space.get("strategy", "one-at-a-time"),
            "candidate_count": len(candidates),
            "candidate_jobs": candidate_jobs,
        },
        "bindings": {
            "processor_sha256": sha256_file(processor),
            "policy_sha256": sha256_file(policy),
            "dataset_lock_sha256": sha256_file(dataset_lock),
            "partitions": identities,
        },
        "baseline": dev_results[0]["tuning"],
        "selected": {
            "candidate_id": selected["candidate_id"],
            "label": selected["label"],
            "tuning": selected["tuning"],
            "development_score": selected["score"],
        },
        "development_ranking": [
            {
                "candidate_id": item["candidate_id"], "label": item["label"],
                "tuning": item["tuning"], "score": item["score"],
                "validation_result": item["validation_result"],
                "report_sha256": item["report_sha256"],
                "elapsed_s": item["elapsed_s"],
            }
            for item in sorted(dev_results, key=lambda item: (-float(item["score"]), item["candidate_id"]))
        ],
        "validation": {
            "baseline": bind_report(validation_reports["baseline"][0], validation_reports["baseline"][1]),
            "candidate": bind_report(validation_reports["candidate"][0], validation_reports["candidate"][1]),
            "regression_violations": validation_violations,
        },
        "shadow": {
            "baseline": bind_report(shadow_reports["baseline"][0], shadow_reports["baseline"][1]),
            "candidate": bind_report(shadow_reports["candidate"][0], shadow_reports["candidate"][1]),
            "regression_violations": shadow_violations,
        },
        "promotion_required": [
            "validation-grade-blind acoustic gate with a repository-external holdout key",
            "same-candidate target CPU/RSS/latency evidence",
            "SSC305/target HIL and soak evidence",
            "product certification record on shipping hardware/corpus",
            "reviewed source change or runtime product configuration; never automatic main mutation",
        ],
    }
    output_path = output_dir / "iteration-result.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    space = {
        "schema_version": 1,
        "search_space_id": "self-test",
        "strategy": "one-at-a-time",
        "max_candidates": 8,
        "baseline": {
            "aec_mu": 0.22, "ns_floor": 0.12,
            "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0,
        },
        "parameters": {"aec_mu": [0.18, 0.22, 0.26], "ns_floor": [0.10, 0.12]},
        "objective": {
            "minimum_improvement_score": 0.05,
            "metrics": [
                {"name": "pass_rate", "direction": "max", "weight": 8.0, "scale": 0.02, "max_regression": 0.0},
                {"name": "median_erle_db", "direction": "max", "weight": 1.0, "scale": 1.0, "max_regression": 1.0},
            ],
        },
    }
    validate_search_space(space)
    candidates = generate_candidates(space)
    assert candidates[0]["label"] == "baseline"
    assert len(candidates) == 4
    baseline = {"validation_result": "PASS", "summary": {"pass_rate": 1.0, "median_erle_db": 10.0}}
    better = {"validation_result": "PASS", "summary": {"pass_rate": 1.0, "median_erle_db": 11.5}}
    score, _ = score_against_baseline(space, baseline, better)
    assert score > 1.0
    assert not regression_violations(space, baseline, better)
    worse = {"validation_result": "PASS", "summary": {"pass_rate": 0.98, "median_erle_db": 12.0}}
    assert regression_violations(space, baseline, worse)
    with tempfile.TemporaryDirectory(prefix="ap-tuning-selftest-") as temporary:
        root = Path(temporary)
        for index, seed in enumerate((1, 2, 3)):
            corpus = {
                "schema_version": 1, "corpus_id": f"c{index}", "tier": "regression",
                "generator": {"seed": seed}, "cases": [{"case_id": "same"}],
            }
            (root / f"{index}.json").write_text(json.dumps(corpus), encoding="utf-8")
        identities = enforce_partition_independence(root / "0.json", root / "1.json", root / "2.json")
        assert identities["development"]["generator_seed"] == 1
        validation_grade = json.loads((root / "0.json").read_text())
        validation_grade["tier"] = "validation-grade"
        (root / "0.json").write_text(json.dumps(validation_grade), encoding="utf-8")
        try:
            enforce_partition_independence(root / "0.json", root / "1.json", root / "2.json")
        except ValueError:
            pass
        else:
            raise AssertionError("validation-grade corpus must be rejected for selection")
    print("tuning iteration self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("validation/policies/validation-smoke.json"))
    parser.add_argument("--dataset-lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--search-space", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--candidate-jobs", type=int, default=1,
                        help="parallel development candidates; deterministic output order is preserved")
    parser.add_argument("--require-candidate", action="store_true",
                        help="return non-zero unless an independent-gate ACOUSTIC_CANDIDATE is produced")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = ("processor", "development_corpus", "validation_corpus",
                "shadow_corpus", "search_space", "output_dir")
    for name in required:
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    result = iterate(
        args.repo_root.resolve(), args.processor.resolve(),
        args.development_corpus.resolve(), args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(), args.policy.resolve(), args.dataset_lock.resolve(),
        args.search_space.resolve(), args.output_dir.resolve(), args.candidate_jobs,
    )
    print(json.dumps({
        "decision": result["decision"], "iteration_id": result["iteration_id"],
        "selected": result["selected"],
    }, sort_keys=True))
    if args.require_candidate and result["decision"] != "ACOUSTIC_CANDIDATE":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
