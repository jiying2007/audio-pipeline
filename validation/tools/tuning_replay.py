#!/usr/bin/env python3
"""Replay one already-selected acoustic candidate on an independent corpus.

This tool never searches. It compares an explicit candidate with an explicit
baseline under the same fail-closed objective/regression semantics used by the
optimizer, so a motion-selected candidate can be checked on unrelated call
validation/shadow corpora without letting those corpora influence selection.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from authority import load_authority, optimizer_role_allowed
import tuning_iteration as guarded
import tuning_iteration_engine as engine


def load_tuning(path: Path) -> dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"tuning must be a JSON object: {path}")
    tuning = engine.canonical_tuning(raw)
    if set(tuning) != set(engine.TUNING_KEYS):
        raise ValueError(f"tuning must define all supported keys: {path}")
    return tuning


def enforce_role(corpus: Path, role: str) -> str:
    raw = json.loads(corpus.read_text(encoding="utf-8"))
    tier = raw.get("tier")
    if not isinstance(tier, str) or not tier:
        raise ValueError("corpus tier is required")
    if not optimizer_role_allowed(load_authority(), tier, role):
        raise ValueError(f"authority rejects tier={tier!r} for replay role={role!r}")
    return tier


def replay(repo_root: Path, processor: Path, corpus: Path, policy: Path,
           dataset_lock: Path, search_space: Path, baseline_path: Path,
           candidate_path: Path, role: str, output_dir: Path) -> dict:
    guarded.install_fail_closed_guards()
    space = json.loads(search_space.read_text(encoding="utf-8"))
    guarded.strict_validate_search_space(space)
    tier = enforce_role(corpus, role)
    baseline = load_tuning(baseline_path)
    candidate = load_tuning(candidate_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_report_path = output_dir / "baseline.json"
    candidate_report_path = output_dir / "candidate.json"
    baseline_report, baseline_elapsed = engine.run_validation(
        repo_root, processor, corpus, policy, dataset_lock, baseline, baseline_report_path
    )
    candidate_report, candidate_elapsed = engine.run_validation(
        repo_root, processor, corpus, policy, dataset_lock, candidate, candidate_report_path
    )
    score, deltas = guarded.strict_score(space, baseline_report, candidate_report)
    violations = guarded.strict_regression(space, baseline_report, candidate_report)
    result = {
        "schema_version": 1,
        "authority": "non-shipping-independent-replay",
        "role": role,
        "tier": tier,
        "decision": "PASS" if not violations else "REJECT_CANDIDATE",
        "baseline_tuning": baseline,
        "candidate_tuning": candidate,
        "candidate_score_vs_baseline": score,
        "objective_deltas": deltas,
        "regression_violations": violations,
        "bindings": {
            "processor_sha256": engine.sha256_file(processor),
            "corpus_sha256": engine.sha256_file(corpus),
            "policy_sha256": engine.sha256_file(policy),
            "dataset_lock_sha256": engine.sha256_file(dataset_lock),
            "search_space_sha256": engine.sha256_file(search_space),
            "baseline_tuning_sha256": engine.sha256_file(baseline_path),
            "candidate_tuning_sha256": engine.sha256_file(candidate_path),
        },
        "reports": {
            "baseline": engine.bind_report(baseline_report_path, baseline_report),
            "candidate": engine.bind_report(candidate_report_path, candidate_report),
        },
        "elapsed_s": {
            "baseline": baseline_elapsed,
            "candidate": candidate_elapsed,
        },
    }
    (output_dir / "replay-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def self_test() -> None:
    guarded.install_fail_closed_guards()
    authority = load_authority()
    assert optimizer_role_allowed(authority, "regression", "validation")
    assert optimizer_role_allowed(authority, "regression", "shadow")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "validation")
    with tempfile.TemporaryDirectory(prefix="ap-tuning-replay-selftest-") as raw:
        root = Path(raw)
        valid = {
            "aec_mu": 0.22,
            "ns_floor": 0.12,
            "agc_target_dbfs": -20.0,
            "limiter_dbfs": -2.0,
        }
        path = root / "tuning.json"
        path.write_text(json.dumps(valid), encoding="utf-8")
        assert load_tuning(path) == valid
    print("tuning replay self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--dataset-lock", type=Path)
    parser.add_argument("--search-space", type=Path)
    parser.add_argument("--baseline-tuning", type=Path)
    parser.add_argument("--candidate-tuning", type=Path)
    parser.add_argument("--role", choices=("validation", "shadow"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (
        "processor", "corpus", "policy", "dataset_lock", "search_space",
        "baseline_tuning", "candidate_tuning", "role", "output_dir",
    )
    for name in required:
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    result = replay(
        args.repo_root.resolve(), args.processor.resolve(), args.corpus.resolve(),
        args.policy.resolve(), args.dataset_lock.resolve(), args.search_space.resolve(),
        args.baseline_tuning.resolve(), args.candidate_tuning.resolve(), args.role,
        args.output_dir.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "role": result["role"],
        "score": result["candidate_score_vs_baseline"],
        "violations": len(result["regression_violations"]),
    }, sort_keys=True))
    if args.enforce and result["decision"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
