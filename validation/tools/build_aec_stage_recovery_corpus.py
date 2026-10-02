#!/usr/bin/env python3
"""Build deterministic stage-prefix AEC transition recovery corpus."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path

import build_aec_transition_corpus

TARGET_CASES = (
    "echo-path-change",
    "speaker-acoustic-gain-step",
    "render-level-step",
)
PROFILES = (
    "prefix-aec",
    "prefix-res",
    "prefix-ns",
    "prefix-agc",
    "default",
)
STAGE_ORDER = {profile: index for index, profile in enumerate(PROFILES)}
PATH_KEYS = (
    "mic_audio",
    "render_audio",
    "clean_near_audio",
    "echo_audio",
    "vad_labels",
)


def prefix_paths(case: dict, prefix: str) -> dict:
    out = copy.deepcopy(case)
    for key in PATH_KEYS:
        value = out.get(key)
        if value:
            out[key] = f"{prefix}/{value}"
    return out


def build(output: Path, seed: int, seconds: float) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source_root = output / "source"
    base = build_aec_transition_corpus.build(source_root, seed, seconds)
    by_id = {case["case_id"]: case for case in base["cases"]}
    missing = sorted(set(TARGET_CASES) - set(by_id))
    if missing:
        raise ValueError(f"base AEC transition cases missing: {missing}")

    cases: list[dict] = []
    for base_case_id in TARGET_CASES:
        base_case = by_id[base_case_id]
        for profile in PROFILES:
            case = prefix_paths(base_case, "source")
            case["case_id"] = f"{base_case_id}--{profile}"
            case["scenario"] = f"stage-recovery::{base_case['scenario']}"
            case["processor_profile"] = profile
            case["expected"] = {}
            dims = dict(case.get("dimensions", {}))
            dims.update({
                "base_case_id": base_case_id,
                "stage_profile": profile,
                "stage_order": STAGE_ORDER[profile],
                "source_family": "deterministic-aec-transition-v1",
            })
            case["dimensions"] = dims
            source = dict(case.get("source", {}))
            source.update({
                "source_case_id": base_case_id,
                "stage_recovery_authority": "candidate-zero-measurement-only",
            })
            case["source"] = source
            cases.append(case)

    if len(cases) != len(TARGET_CASES) * len(PROFILES):
        raise ValueError(f"unexpected case count: {len(cases)}")
    if len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("stage recovery case ids must be unique")

    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-stage-recovery-v1-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_aec_stage_recovery_corpus.py",
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


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-aec-stage-recovery-") as raw:
        a = build(Path(raw) / "a", 10707, 6.0)
        b = build(Path(raw) / "b", 10707, 6.0)
        c = build(Path(raw) / "c", 10807, 6.0)
        assert len(a["cases"]) == 15
        assert a["candidate_limit"] == a["confirmation_limit"] == 0
        assert (Path(raw) / "a" / "corpus.json").read_bytes() == (
            Path(raw) / "b" / "corpus.json"
        ).read_bytes()
        assert (Path(raw) / "a" / "corpus.json").read_bytes() != (
            Path(raw) / "c" / "corpus.json"
        ).read_bytes()
        groups = {}
        for case in a["cases"]:
            groups.setdefault(case["dimensions"]["base_case_id"], []).append(
                case["processor_profile"]
            )
        assert set(groups) == set(TARGET_CASES)
        assert all(tuple(values) == PROFILES for values in groups.values())
    print("AEC stage recovery corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=10707)
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if not 6.0 <= args.seconds <= 20.0:
        parser.error("--seconds must be within 6..20")
    corpus = build(args.output, args.seed, args.seconds)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
