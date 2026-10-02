#!/usr/bin/env python3
"""Confirm the bounded speaker-gain RES→NS recovery extension hypothesis."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path

import build_aec_transition_corpus
from aec_stage_recovery_decomposition import analyze_case

PROFILES = ("prefix-res", "prefix-ns", "default")
PATH_KEYS = (
    "mic_audio",
    "render_audio",
    "clean_near_audio",
    "echo_audio",
    "vad_labels",
)
BASE_CASE = "speaker-acoustic-gain-step"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(contract: dict) -> None:
    if contract.get("authority") != "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION":
        raise ValueError("confirmation authority drift")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("confirmation budget drift")
    if tuple(contract["corpus"]["profiles"]) != PROFILES:
        raise ValueError("confirmation profile set/order drift")
    if contract["hypothesis"]["case_id"] != BASE_CASE:
        raise ValueError("confirmation case drift")


def prefix_paths(case: dict, prefix: str) -> dict:
    out = copy.deepcopy(case)
    for key in PATH_KEYS:
        value = out.get(key)
        if value:
            out[key] = f"{prefix}/{value}"
    return out


def build_corpus(output: Path, seed: int, seconds: float) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source_root = output / "source"
    base = build_aec_transition_corpus.build(source_root, seed, seconds)
    by_id = {case["case_id"]: case for case in base["cases"]}
    if BASE_CASE not in by_id:
        raise ValueError("speaker acoustic gain case missing")

    cases = []
    source_case = by_id[BASE_CASE]
    for order, profile in enumerate(PROFILES):
        case = prefix_paths(source_case, "source")
        case["case_id"] = f"{BASE_CASE}--{profile}"
        case["scenario"] = f"ns-recovery-confirm::{source_case['scenario']}"
        case["processor_profile"] = profile
        case["expected"] = {}
        dims = dict(case.get("dimensions", {}))
        dims.update({
            "base_case_id": BASE_CASE,
            "stage_profile": profile,
            "stage_order": order,
            "source_family": "deterministic-aec-transition-v1",
        })
        case["dimensions"] = dims
        source = dict(case.get("source", {}))
        source.update({
            "source_case_id": BASE_CASE,
            "confirmation_authority": "candidate-zero-single-hypothesis",
        })
        case["source"] = source
        cases.append(case)

    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-speaker-gain-ns-confirm-v1-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "aec_speaker_gain_ns_recovery_confirmation.py",
            "version": 1,
            "seed": seed,
            "seconds": seconds,
        },
        "sources": ["deterministic-aec-transition-v1"],
        "sealed_data": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return corpus


def run_seed(
    corpus_path: Path,
    report_path: Path,
    processor: Path,
    contract: dict,
) -> dict:
    require_contract(contract)
    corpus = load_json(corpus_path)
    report = load_json(report_path)
    expected_ids = {f"{BASE_CASE}--{profile}" for profile in PROFILES}
    if {case["case_id"] for case in corpus["cases"]} != expected_ids:
        raise ValueError("confirmation corpus case-set drift")

    report_cases = {case["case_id"]: case for case in report.get("cases", [])}
    if set(report_cases) != expected_ids:
        raise ValueError("confirmation canonical report case-set drift")
    if not all(bool(item.get("passed", False)) for item in report_cases.values()):
        raise ValueError("confirmation canonical report policy failure")

    rows = [
        analyze_case(case, corpus_path, processor, contract)
        for case in corpus["cases"]
    ]
    rows.sort(key=lambda row: row["stage_order"])
    if tuple(row["stage_profile"] for row in rows) != PROFILES:
        raise ValueError("confirmation stage order drift")

    by_profile = {row["stage_profile"]: row for row in rows}
    res = by_profile["prefix-res"]
    ns = by_profile["prefix-ns"]
    full = by_profile["default"]
    if res["censored"] or ns["censored"]:
        extension = None
        confirmed = False
    else:
        extension = int(ns["recovery_time_ms"]) - int(res["recovery_time_ms"])
        confirmed = extension >= 100

    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "seed": int(corpus["generator"]["seed"]),
        "authority": "candidate-zero-single-hypothesis-confirmation",
        "stages": rows,
        "hypothesis_observation": {
            "res_recovery_time_ms": res["recovery_time_ms"],
            "ns_recovery_time_ms": ns["recovery_time_ms"],
            "full_recovery_time_ms": full["recovery_time_ms"],
            "ns_minus_res_ms": extension,
            "confirmed_on_seed": confirmed,
        },
        "candidate_authority": False,
        "root_cause_claim_authority": False,
    }


def aggregate(items: list[dict], contract: dict) -> dict:
    require_contract(contract)
    expected_seeds = sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by_seed = {int(item["seed"]): item for item in items}
    if sorted(by_seed) != expected_seeds:
        raise ValueError("confirmation fresh seed mismatch")
    observations = [
        {
            "seed": seed,
            **by_seed[seed]["hypothesis_observation"],
        }
        for seed in expected_seeds
    ]
    confirmed = all(obs["confirmed_on_seed"] for obs in observations)
    return {
        "schema_version": 1,
        "investigation_id": contract["id"],
        "fresh_seeds": expected_seeds,
        "hypothesis": contract["hypothesis"],
        "observations": observations,
        "hypothesis_confirmed": confirmed,
        "outcome": "CONFIRMED" if confirmed else "REJECTED",
        "either_outcome_is_valid_evidence": True,
        "ns_root_cause_claim_authority": False,
        "ns_parameter_search_authority": False,
        "candidate_authority": False,
        "s004_open": False,
    }


def self_test() -> None:
    contract = {
        "authority": "CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "corpus": {"profiles": list(PROFILES)},
        "hypothesis": {"case_id": BASE_CASE},
    }
    require_contract(contract)
    assert PROFILES == ("prefix-res", "prefix-ns", "default")
    print("speaker-gain NS recovery confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    build_p = sub.add_parser("build")
    build_p.add_argument("--output", type=Path, required=True)
    build_p.add_argument("--seed", type=int, required=True)
    build_p.add_argument("--seconds", type=float, default=6.0)
    run_p = sub.add_parser("run")
    run_p.add_argument("--corpus", type=Path, required=True)
    run_p.add_argument("--report", type=Path, required=True)
    run_p.add_argument("--processor", type=Path, required=True)
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
    if args.command == "build":
        corpus = build_corpus(args.output, args.seed, args.seconds)
        print(json.dumps({
            "seed": args.seed,
            "cases": len(corpus["cases"]),
            "corpus": str(args.output / "corpus.json"),
        }, sort_keys=True))
        return 0

    contract = load_json(args.contract)
    if args.command == "run":
        result = run_seed(
            args.corpus,
            args.report,
            args.processor,
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
        print(json.dumps({
            "seed": result["seed"],
            **result["hypothesis_observation"],
        }, sort_keys=True))
    else:
        print(json.dumps({
            "outcome": result["outcome"],
            "hypothesis_confirmed": result["hypothesis_confirmed"],
            "observations": result["observations"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
