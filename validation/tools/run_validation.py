#!/usr/bin/env python3
"""Authority-guarded canonical acoustic validation CLI.

The metric/evaluation implementation lives in run_validation_engine.py. This
entrypoint owns corpus-tier authority so every workflow and local invocation
uses validation/authority.json as the single source of truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import render_corr_exact
import run_validation_engine as engine
from authority import corpus_tiers, load_authority, tier_spec

# Canonical render-correlation search is installed once at the authority-guarded
# entrypoint. The native helper selects the global lag only; final metric scores
# remain run_validation_engine.normalized_corr(..., stride=4).
render_corr_exact.install(engine)


def validate_corpus_shape(corpus: dict, authority: dict) -> None:
    if corpus.get("schema_version") != 1:
        raise ValueError("corpus schema_version must be 1")
    tier = corpus.get("tier")
    if tier not in corpus_tiers(authority):
        raise ValueError(f"invalid corpus tier: {tier}")
    ids = [case.get("case_id") for case in corpus.get("cases", [])]
    if not ids or len(set(ids)) != len(ids) or any(not item for item in ids):
        raise ValueError("case_id values must be non-empty and unique")
    invalid_profiles = sorted(
        {case.get("processor_profile", "default") for case in corpus.get("cases", [])}
        - {"default", "ns-isolated"}
    )
    if invalid_profiles:
        raise ValueError(f"invalid processor_profile values: {invalid_profiles}")
    for case in corpus.get("cases", []):
        dimensions = case.get("dimensions", {})
        if not isinstance(dimensions, dict):
            raise ValueError(f"dimensions must be an object: {case.get('case_id')}")
        for name, value in dimensions.items():
            if not isinstance(name, str) or not isinstance(value, (str, int, float, bool)):
                raise ValueError(
                    f"dimensions must contain scalar values: {case.get('case_id')}/{name}"
                )


def policy_violations(policy: dict, corpus: dict, cases: list[dict],
                      authority: dict) -> tuple[dict, list[dict]]:
    allowed = policy.get("allowed_tiers", [])
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("policy.allowed_tiers must be a non-empty list")
    unknown = set(allowed) - corpus_tiers(authority)
    if unknown:
        raise ValueError(f"policy contains unknown authority tiers: {sorted(unknown)}")

    summary, violations = engine.policy_violations(policy, corpus, cases)
    authority_gates = {
        "allowed_tiers",
        "sealed_data",
        "no_dev_cases_in_validation_grade",
        "blind_key_fingerprint",
    }
    violations = [item for item in violations if item.get("gate") not in authority_gates]

    tier = corpus["tier"]
    spec = tier_spec(authority, tier)
    if tier not in allowed:
        violations.append({"gate": "allowed_tiers", "actual": tier})
    if spec["requires_sealed_data"] and not corpus.get("sealed_data"):
        violations.append({"gate": "sealed_data", "actual": False})
    if not spec["allows_dev_split"] and any(
        case.get("split") == "dev" for case in corpus["cases"]
    ):
        violations.append({"gate": "dev_split_not_allowed", "tier": tier})
    if spec["requires_blind_key"] and not corpus.get("blind_key_fingerprint"):
        violations.append({"gate": "blind_key_fingerprint"})
    return summary, violations


def self_test() -> None:
    authority = load_authority()
    render_corr_exact.self_test(engine.normalized_corr)
    engine.self_test()
    research = {
        "schema_version": 1,
        "corpus_id": "research-dev",
        "tier": "research-validation",
        "sealed_data": True,
        "cases": [{
            "case_id": "r1", "split": "dev", "scenario": "research",
            "sample_rate_hz": 16000, "mic_channels": 1, "mic_audio": "mic.pcm",
        }],
    }
    validate_corpus_shape(research, authority)
    summary, violations = policy_violations(
        {"allowed_tiers": ["research-validation"], "minimum_cases": 1},
        research,
        [{"scenario": "research", "passed": True, "dimensions": {}, "metrics": {}}],
        authority,
    )
    assert summary["pass_rate"] == 1.0 and not violations
    blind = dict(research)
    blind["tier"] = "validation-grade-blind"
    blind["cases"] = [dict(research["cases"][0], split="blind")]
    _, violations = policy_violations(
        {"allowed_tiers": ["validation-grade-blind"], "minimum_cases": 1},
        blind,
        [{"scenario": "research", "passed": True, "dimensions": {}, "metrics": {}}],
        authority,
    )
    assert any(item["gate"] == "blind_key_fingerprint" for item in violations)
    print("authority-guarded validation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--dataset-lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--blind-summary-only", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("corpus", "policy", "processor", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")

    authority = load_authority()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    validate_corpus_shape(corpus, authority)
    cases = [engine.evaluate_case(args.processor, args.corpus, case) for case in corpus["cases"]]
    summary, aggregate_violations = policy_violations(policy, corpus, cases, authority)
    case_violations = [
        {"case_id": case["case_id"], "violations": case["violations"]}
        for case in cases if case["violations"]
    ]
    violations = case_violations + aggregate_violations
    report_cases = cases
    if args.blind_summary_only and tier_spec(authority, corpus["tier"])["blind"]:
        report_cases = [{"case_id": case["case_id"], "passed": case["passed"]} for case in cases]
    report = {
        "schema_version": 1,
        "validation_result": "PASS" if not violations else "FAIL",
        "tier": corpus["tier"],
        "corpus_id": corpus["corpus_id"],
        "policy_id": policy.get("policy_id"),
        "source_revision": engine.load_revision(args.source_revision),
        "bindings": {
            "authority_sha256": engine.sha256_file(Path("validation/authority.json")),
            "dataset_lock_sha256": engine.sha256_file(args.dataset_lock),
            "corpus_sha256": engine.sha256_file(args.corpus),
            "policy_sha256": engine.sha256_file(args.policy),
            **render_corr_exact.report_bindings(Path(engine.__file__)),
        },
        "summary": summary,
        "cases": report_cases,
        "violations": violations,
    }
    if args.source_manifest is not None:
        report["bindings"]["source_manifest_sha256"] = engine.sha256_file(args.source_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.evidence_manifest:
        engine.write_evidence(
            args.evidence_manifest, args.output, args.corpus, args.policy,
            args.dataset_lock, args.source_manifest,
        )
        render_corr_exact.extend_evidence_manifest(
            args.evidence_manifest, Path(engine.__file__)
        )
    print(json.dumps({"result": report["validation_result"], "tier": report["tier"], **summary}, sort_keys=True))
    return 1 if args.enforce and violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
