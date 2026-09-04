#!/usr/bin/env python3
"""Build an NS-only tuning corpus from the stage-isolated generator.

The broad stage corpus is for attribution/regression across VAD, NS, AGC and BF.
An NS optimizer must not score unrelated stage cases, so this builder retains
only the production NS->VAD stationary/non-stationary cases while preserving the
same deterministic source generation and independent seed identity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_stage_validation_corpus import build as build_stage_corpus


def build(output: Path, seed: int, seconds: float) -> dict:
    corpus = build_stage_corpus(output, seed, seconds)
    cases = [
        case for case in corpus["cases"]
        if case.get("processor_profile") == "ns-isolated"
    ]
    if {case["scenario"] for case in cases} != {
        "stage-ns-stationary", "stage-ns-nonstationary"
    }:
        raise ValueError("NS tuning corpus must contain exactly the two canonical NS scenarios")
    corpus = {
        **corpus,
        "corpus_id": f"ns-stage-tuning-seed-{seed}",
        "generator": {
            "name": "build_ns_tuning_corpus.py",
            "version": 1,
            "seed": seed,
            "source_generator": "build_stage_validation_corpus.py",
        },
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ap-ns-tuning-corpus-") as temporary:
        corpus = build(Path(temporary), 1307, 4.0)
        assert len(corpus["cases"]) == 2
        assert all(case["processor_profile"] == "ns-isolated" for case in corpus["cases"])
        assert corpus["generator"]["seed"] == 1307
    print("NS tuning corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=1307)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    if not 4.0 <= args.seconds <= 20.0:
        raise SystemExit("seconds must be 4..20")
    args.output.mkdir(parents=True, exist_ok=True)
    corpus = build(args.output, args.seed, args.seconds)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "seed": args.seed,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
