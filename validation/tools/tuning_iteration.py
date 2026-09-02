#!/usr/bin/env python3
"""Authority-guarded acoustic tuning CLI.

The search implementation lives in tuning_iteration_engine.py. This entrypoint
owns optimizer data-role admission so blind/product evidence cannot enter an
iterative feedback loop even if callers invoke the tool outside GitHub Actions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from authority import load_authority, optimizer_role_allowed
import tuning_iteration_engine as engine


def corpus_tier(path: Path) -> str:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    tier = corpus.get("tier")
    if not isinstance(tier, str) or not tier:
        raise ValueError(f"corpus tier is required: {path}")
    return tier


def enforce_optimizer_authority(development: Path, validation: Path, shadow: Path) -> None:
    authority = load_authority()
    for role, path in (
        ("development", development),
        ("validation", validation),
        ("shadow", shadow),
    ):
        tier = corpus_tier(path)
        if not optimizer_role_allowed(authority, tier, role):
            raise ValueError(f"authority rejects {tier!r} corpus for optimizer role {role!r}")


def self_test() -> None:
    authority = load_authority()
    assert optimizer_role_allowed(authority, "regression", "development")
    assert optimizer_role_allowed(authority, "research-validation", "development")
    assert not optimizer_role_allowed(authority, "validation-grade", "development")
    assert optimizer_role_allowed(authority, "validation-grade", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "shadow")
    engine.self_test()
    print("authority-guarded tuning self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    args, _ = parser.parse_known_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("development_corpus", "validation_corpus", "shadow_corpus"):
        if getattr(args, name) is None:
            raise SystemExit(f"--{name.replace('_', '-')} is required")
    enforce_optimizer_authority(
        args.development_corpus.resolve(),
        args.validation_corpus.resolve(),
        args.shadow_corpus.resolve(),
    )
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
