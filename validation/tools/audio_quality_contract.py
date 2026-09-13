#!/usr/bin/env python3
"""Fail-closed cross-stage ground-truth quality contract.

This contract exists to prevent a regression from being called an acoustic
quality evaluation merely because it is deterministic and crash-free.  It
requires each algorithm family to carry the truth needed for the metrics that
can actually decide quality.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

REQUIRED_ROLES = {"aec-farend", "aec-res-doubletalk", "ns", "bf", "vad"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def validate_corpus(corpus: dict) -> dict:
    require(corpus.get("schema_version") == 1, "quality corpus schema_version")
    require(corpus.get("tier") == "regression", "quality development corpus must remain regression tier")
    require(corpus.get("sources") == ["deterministic-quality-ground-truth"], "quality source identity")
    cases = corpus.get("cases")
    require(isinstance(cases, list) and len(cases) >= 10, "quality corpus underfilled")
    roles = []
    for case in cases:
        quality = case.get("quality")
        require(isinstance(quality, dict) and quality.get("ground_truth") is True,
                f"ground truth marker missing: {case.get('case_id')}")
        role = quality.get("role")
        require(role in REQUIRED_ROLES, f"unknown quality role: {role}")
        roles.append(role)
        expected = case.get("expected", {})
        case_id = case.get("case_id")
        if role == "aec-farend":
            require(case.get("render_audio") and case.get("echo_audio"), f"AEC far-end truth missing: {case_id}")
            require("min_erle_db" in expected and "max_erle_convergence_ms" in expected,
                    f"AEC far-end quality gates missing: {case_id}")
            if case.get("control", {}).get("echo_path_change_frame") is not None:
                require("max_erle_recovery_ms" in expected, f"AEC recovery gate missing: {case_id}")
        elif role == "aec-res-doubletalk":
            require(case.get("render_audio") and case.get("clean_near_audio") and case.get("interference_audio"),
                    f"AEC/RES double-talk separated truth missing: {case_id}")
            require("min_near_si_sdr_db" in expected and
                    "min_near_projection_gain_db" in expected and
                    "min_interference_corr_reduction" in expected,
                    f"AEC/RES double-talk quality gates missing: {case_id}")
            require(case.get("echo_audio") is None,
                    f"double-talk must not misuse ERLE with near speech present: {case_id}")
        elif role == "ns":
            require(case.get("processor_profile") == "ns-isolated", f"NS must be isolated: {case_id}")
            require(case.get("clean_near_audio") and case.get("noise_audio") and case.get("vad_labels"),
                    f"NS separated truth missing: {case_id}")
            require("min_near_si_sdr_improvement_db" in expected and
                    "min_near_projection_gain_db" in expected and
                    "min_noise_only_attenuation_db" in expected,
                    f"NS quality gates missing: {case_id}")
        elif role == "bf":
            require(case.get("processor_profile") == "bf-isolated" and case.get("mic_channels") == 2,
                    f"BF must be two-channel isolated: {case_id}")
            require(case.get("clean_near_audio") and case.get("interference_audio"),
                    f"BF target/interferer truth missing: {case_id}")
            require("min_near_si_sdr_improvement_db" in expected and
                    "min_near_projection_gain_db" in expected and
                    "min_interference_corr_reduction" in expected,
                    f"BF quality gates missing: {case_id}")
        elif role == "vad":
            require(case.get("processor_profile") == "vad-isolated" and case.get("vad_labels"),
                    f"VAD labels/isolation missing: {case_id}")
            require(any(name in expected for name in (
                "min_vad_f1", "min_vad_recall", "max_vad_false_positive_rate"
            )), f"VAD classification gate missing: {case_id}")
            if any(case.get("vad_labels") for _ in [0]) and not quality.get("negative"):
                require("max_vad_onset_delay_ms" in expected and "max_vad_release_delay_ms" in expected,
                        f"VAD timing gates missing: {case_id}")
    require(set(roles) == REQUIRED_ROLES, f"quality role coverage drift: {sorted(set(roles))}")
    return {role: roles.count(role) for role in sorted(REQUIRED_ROLES)}


def _finite_metric(case: dict, name: str) -> float:
    value = case.get("metrics", {}).get(name)
    require(value is not None, f"quality metric missing: {case.get('case_id')}/{name}")
    number = float(value)
    require(math.isfinite(number), f"quality metric non-finite: {case.get('case_id')}/{name}")
    return number


def validate_report(corpus: dict, report: dict) -> dict:
    require(report.get("schema_version") == 1, "quality report schema_version")
    require(report.get("corpus_id") == corpus.get("corpus_id"), "quality report/corpus identity mismatch")
    require(report.get("validation_result") == "PASS", "quality report must pass")
    report_cases = {case.get("case_id"): case for case in report.get("cases", [])}
    require(len(report_cases) == len(corpus["cases"]), "quality report case-set mismatch")
    checked = 0
    for source in corpus["cases"]:
        case = report_cases.get(source["case_id"])
        require(case is not None and case.get("passed") is True, f"quality case failed: {source['case_id']}")
        role = source["quality"]["role"]
        if role == "aec-farend":
            _finite_metric(case, "erle_db")
            _finite_metric(case, "erle_convergence_ms")
            if source.get("control", {}).get("echo_path_change_frame") is not None:
                _finite_metric(case, "erle_recovery_ms")
        elif role == "aec-res-doubletalk":
            _finite_metric(case, "near_si_sdr_db")
            _finite_metric(case, "near_projection_gain_db")
            _finite_metric(case, "interference_corr_reduction")
        elif role == "ns":
            _finite_metric(case, "near_si_sdr_improvement_db")
            _finite_metric(case, "near_projection_gain_db")
            _finite_metric(case, "noise_only_attenuation_db")
        elif role == "bf":
            _finite_metric(case, "near_si_sdr_improvement_db")
            _finite_metric(case, "near_projection_gain_db")
            _finite_metric(case, "interference_corr_reduction")
        elif role == "vad":
            _finite_metric(case, "vad_false_positive_rate")
            if not source["quality"].get("negative"):
                _finite_metric(case, "vad_onset_delay_ms")
                _finite_metric(case, "vad_release_delay_ms")
        checked += 1
    summary = report.get("summary", {})
    for name in (
        "p10_near_projection_gain_db",
        "p10_interference_corr_reduction",
        "p90_erle_convergence_ms",
        "p90_erle_recovery_ms",
        "p90_vad_onset_delay_ms",
        "p90_vad_release_delay_ms",
    ):
        value = summary.get(name)
        require(value is not None and math.isfinite(float(value)), f"quality aggregate missing: {name}")
    return {"cases_checked": checked, "result": "PASS"}


def validate_policy(policy: dict) -> None:
    require(policy.get("allowed_tiers") == ["regression"], "quality policy authority")
    aggregate = policy.get("aggregate", {})
    for gate in (
        "min_pass_rate",
        "min_p10_near_projection_gain_db",
        "min_p10_interference_corr_reduction",
        "max_p90_erle_convergence_ms",
        "max_p90_erle_recovery_ms",
        "max_p90_vad_onset_delay_ms",
        "max_p90_vad_release_delay_ms",
    ):
        require(gate in aggregate, f"quality aggregate gate missing: {gate}")


def self_test() -> None:
    good = {
        "schema_version": 1,
        "tier": "regression",
        "sources": ["deterministic-quality-ground-truth"],
        "cases": [],
    }
    templates = {
        "aec-farend": {"render_audio": "r", "echo_audio": "e", "expected": {"min_erle_db": -6, "max_erle_convergence_ms": 1}},
        "aec-res-doubletalk": {"render_audio": "r", "clean_near_audio": "c", "interference_audio": "i", "expected": {"min_near_si_sdr_db": -20, "min_near_projection_gain_db": -12, "min_interference_corr_reduction": -0.1}},
        "ns": {"processor_profile": "ns-isolated", "clean_near_audio": "c", "noise_audio": "n", "vad_labels": "v", "expected": {"min_near_si_sdr_improvement_db": -6, "min_near_projection_gain_db": -9, "min_noise_only_attenuation_db": 0.1}},
        "bf": {"processor_profile": "bf-isolated", "mic_channels": 2, "clean_near_audio": "c", "interference_audio": "i", "expected": {"min_near_si_sdr_improvement_db": -1, "min_near_projection_gain_db": -6, "min_interference_corr_reduction": -0.1}},
        "vad": {"processor_profile": "vad-isolated", "vad_labels": "v", "expected": {"min_vad_f1": 0.1, "max_vad_onset_delay_ms": 500, "max_vad_release_delay_ms": 700}},
    }
    for index in range(2):
        for role, body in templates.items():
            case = {"case_id": f"{role}-{index}", "quality": {"role": role, "ground_truth": True}, **body}
            if role == "vad" and index == 1:
                case["quality"]["negative"] = True
                case["expected"] = {"max_vad_false_positive_rate": 0.2}
            good["cases"].append(case)
    validate_corpus(good)
    broken = json.loads(json.dumps(good))
    del broken["cases"][2]["clean_near_audio"]
    try:
        validate_corpus(broken)
    except ValueError:
        pass
    else:
        raise AssertionError("missing separated truth was accepted")
    print("audio quality contract self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.corpus is None or args.policy is None:
        parser.error("--corpus and --policy are required")
    corpus = load(args.corpus)
    counts = validate_corpus(corpus)
    validate_policy(load(args.policy))
    result = {"roles": counts, "corpus": "PASS"}
    if args.report is not None:
        result["report"] = validate_report(corpus, load(args.report))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
