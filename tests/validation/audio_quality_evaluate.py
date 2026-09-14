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

quality_metric_support.install(run_validation.engine)


def self_test() -> None:
    quality_metric_support.self_test()
    run_validation.self_test()
    print("release-neutral audio quality evaluator self-test: OK")


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        self_test()
        return 0
    return run_validation.main()


if __name__ == "__main__":
    raise SystemExit(main())
