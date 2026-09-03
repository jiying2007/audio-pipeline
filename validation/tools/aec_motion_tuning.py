#!/usr/bin/env python3
"""AEC-motion-specific entrypoint for authority-guarded tuning.

The generic tuning guard intentionally exposes a narrow metric vocabulary. This
wrapper extends it only with the continuous-motion render-correlation objective
and otherwise reuses the same authority, fail-closed metric, partition, replay,
and non-shipping promotion semantics.
"""

from __future__ import annotations

import json

import tuning_iteration as guarded

AEC_MOTION_METRIC = "median_output_render_corr_reduction"


def self_test() -> None:
    guarded.KNOWN_OBJECTIVE_METRICS.add(AEC_MOTION_METRIC)
    guarded.install_fail_closed_guards()
    space = {
        "schema_version": 1,
        "search_space_id": "aec-motion-self-test",
        "strategy": "one-at-a-time",
        "max_candidates": 4,
        "baseline": {
            "aec_mu": 0.22,
            "ns_floor": 0.12,
            "agc_target_dbfs": -20.0,
            "limiter_dbfs": -2.0,
        },
        "parameters": {"aec_mu": [0.20, 0.22, 0.24]},
        "objective": {
            "minimum_improvement_score": 0.1,
            "metrics": [
                {
                    "name": AEC_MOTION_METRIC,
                    "direction": "max",
                    "weight": 4.0,
                    "scale": 0.05,
                    "max_regression": 0.02,
                }
            ],
        },
    }
    guarded.strict_validate_search_space(space)
    baseline = {"validation_result": "PASS", "summary": {AEC_MOTION_METRIC: 0.10}}
    better = {"validation_result": "PASS", "summary": {AEC_MOTION_METRIC: 0.15}}
    score, deltas = guarded.strict_score(space, baseline, better)
    assert score > 0.0
    assert deltas[0]["metric"] == AEC_MOTION_METRIC
    assert not guarded.strict_regression(space, baseline, better)
    missing = {"validation_result": "PASS", "summary": {AEC_MOTION_METRIC: None}}
    assert guarded.strict_regression(space, baseline, missing)
    print(json.dumps({"result": "PASS", "metric": AEC_MOTION_METRIC}, sort_keys=True))


def main() -> int:
    guarded.KNOWN_OBJECTIVE_METRICS.add(AEC_MOTION_METRIC)
    if "--self-test" in __import__("sys").argv:
        self_test()
        return 0
    return guarded.main()


if __name__ == "__main__":
    raise SystemExit(main())
