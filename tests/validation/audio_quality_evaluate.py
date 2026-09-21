#!/usr/bin/env python3
"""Release-neutral quality wrapper around the canonical acoustic evaluator."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "validation/tools", ROOT / "tests/validation"):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import quality_metric_support
import run_validation

QUALITY_SEMANTICS = quality_metric_support.build_validation_semantics(
    run_validation
)


def self_test() -> None:
    base_evaluate = run_validation.engine.evaluate_case
    base_policy = run_validation.engine.policy_violations
    quality_metric_support.self_test()
    run_validation.self_test()
    assert run_validation.engine.evaluate_case is base_evaluate
    assert run_validation.engine.policy_violations is base_policy
    print("release-neutral audio quality evaluator self-test: OK")


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        self_test()
        return 0
    return run_validation.main(semantics=QUALITY_SEMANTICS)


if __name__ == "__main__":
    raise SystemExit(main())
