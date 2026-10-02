#!/usr/bin/env python3
"""Build deterministic S003 stage-interaction corpus from frozen S001/S002 generators."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path

import build_aec_transition_corpus
import build_system_robustness_corpus

STAGE_INDEX = {
    "prefix-capture": 0,
    "prefix-bf": 1,
    "prefix-sync": 2,
    "prefix-aec": 3,
    "prefix-res": 4,
    "prefix-ns": 5,
    "prefix-agc": 6,
    "prefix-vad": 7,
    "default": 8,
}

PATH_KEYS = (
    "mic_audio",
    "render_audio",
    "clean_near_audio",
    "echo_audio",
    "vad_labels",
)

S001_SELECTION = {
    "capture-clipping": [
        "prefix-capture", "prefix-ns", "prefix-agc", "prefix-vad", "default"
    ],
    "mic-gain-delay-mismatch": [
        "prefix-capture", "prefix-bf", "prefix-ns", "prefix-agc",
        "prefix-vad", "default",
    ],
    "robot-motor-transient": [
        "prefix-capture", "prefix-ns", "prefix-agc", "prefix-vad", "default"
    ],
}

S002_SELECTION = {
    "double-talk": [
        "prefix-capture", "prefix-sync", "prefix-aec", "prefix-res",
        "prefix-ns", "prefix-agc", "prefix-vad", "default",
    ],
    "echo-path-change": [
        "prefix-capture", "prefix-sync", "prefix-aec", "prefix-res",
        "prefix-ns", "prefix-agc", "prefix-vad", "default",
    ],
    "clipped-playback": [
        "prefix-capture", "prefix-sync", "prefix-aec", "prefix-res",
        "prefix-ns", "prefix-agc", "prefix-vad", "default",
    ],
}


def _prefix_paths(case: dict, prefix: str) -> dict:
    out = copy.deepcopy(case)
    for key in PATH_KEYS:
        value = out.get(key)
        if value:
            out[key] = f"{prefix}/{value}"
    return out


def _expand(
    source_corpus: dict,
    source_prefix: str,
    source_family: str,
    selection: dict[str, list[str]],
) -> list[dict]:
    by_id = {case["case_id"]: case for case in source_corpus["cases"]}
    missing = sorted(set(selection) - set(by_id))
    if missing:
        raise ValueError(f"missing selected source cases: {missing}")

    expanded: list[dict] = []
    for base_case_id, profiles in selection.items():
        base = by_id[base_case_id]
        for profile in profiles:
            case = _prefix_paths(base, source_prefix)
            case["case_id"] = f"{base_case_id}--{profile}"
            case["scenario"] = f"stage-interaction::{base['scenario']}"
            case["processor_profile"] = profile
            case["expected"] = {}
            dimensions = dict(case.get("dimensions", {}))
            dimensions.update({
                "base_case_id": base_case_id,
                "source_family": source_family,
                "stage_profile": profile,
                "stage_index": STAGE_INDEX[profile],
            })
            case["dimensions"] = dimensions
            source = dict(case.get("source", {}))
            source.update({
                "source_family": source_family,
                "source_case_id": base_case_id,
                "stage_interaction_authority": "candidate-zero-diagnostic",
            })
            case["source"] = source
            expanded.append(case)
    return expanded


def build(output: Path, seed: int, seconds: float) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source_root = output / "sources"
    s001_root = source_root / "s001"
    s002_root = source_root / "s002"

    s001 = build_system_robustness_corpus.build(s001_root, seed, seconds)
    s002 = build_aec_transition_corpus.build(s002_root, seed + 1000, max(6.0, seconds))

    cases = [
        *_expand(s001, "sources/s001", "s001-perturbation", S001_SELECTION),
        *_expand(s002, "sources/s002", "s002-aec-transition", S002_SELECTION),
    ]
    if len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("stage-interaction case ids must be unique")

    corpus = {
        "schema_version": 1,
        "corpus_id": f"stage-interaction-v1-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": "build_stage_interaction_corpus.py",
            "version": 1,
            "seed": seed,
            "seconds": seconds,
        },
        "sources": [
            "deterministic-s001-perturbation",
            "deterministic-s002-aec-transition",
        ],
        "sealed_data": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-s003-stage-") as raw:
        a = build(Path(raw) / "a", 7307, 6.0)
        b = build(Path(raw) / "b", 7307, 6.0)
        assert a["candidate_limit"] == a["confirmation_limit"] == 0
        assert len(a["cases"]) == 40
        assert [x["dimensions"] for x in a["cases"]] == [
            x["dimensions"] for x in b["cases"]
        ]
        full_duplex = [
            x for x in a["cases"]
            if x["dimensions"]["base_case_id"] == "double-talk"
        ]
        assert [x["processor_profile"] for x in full_duplex] == S002_SELECTION["double-talk"]
        assert all(x["render_audio"] for x in full_duplex)
        stereo = [
            x for x in a["cases"]
            if x["dimensions"]["base_case_id"] == "mic-gain-delay-mismatch"
        ]
        assert any(x["processor_profile"] == "prefix-bf" for x in stereo)
    print("S003 stage-interaction corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=7307)
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if not 6.0 <= args.seconds <= 20.0:
        parser.error("--seconds must be within 6..20")
    built = build(args.output, args.seed, args.seconds)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(built["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
