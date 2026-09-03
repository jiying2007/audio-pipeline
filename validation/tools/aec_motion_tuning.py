#!/usr/bin/env python3
"""AEC-motion-specific entrypoint for authority-guarded tuning.

The generic tuning guard intentionally exposes a narrow metric vocabulary. This
wrapper extends it only with continuous-motion render-correlation objectives and
otherwise reuses the same authority, fail-closed metric, partition, replay, and
non-shipping promotion semantics.
"""

from __future__ import annotations

import json

import tuning_iteration as guarded

AEC_MOTION_MEDIAN_METRIC = "median_output_render_corr_reduction"
AEC_MOTION_P10_METRIC = "p10_output_render_corr_reduction"
AEC_MOTION_METRICS = {AEC_MOTION_MEDIAN_METRIC, AEC_MOTION_P10_METRIC}


def install_motion_metrics() -> None:
    guarded.KNOWN_OBJECTIVE_METRICS.update(AEC_MOTION_METRICS)


def self_test() -> None:
    install_motion_metrics()
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
                    "name": AEC_MOTION_MEDIAN_METRIC,
                    "direction": "max",
                    "weight": 4.0,
                    "scale": 0.05,
                    "max_regression": 0.02,
                },
                {
                    "name": AEC_MOTION_P10_METRIC,
                    "direction": "max",
                    "weight": 2.0,
                    "scale": 0.03,
                    "max_regression": 0.01,
                },
            ],
        },
    }
    guarded.strict_validate_search_space(space)
    baseline = {
        "validation_result": "PASS",
        "summary": {
            AEC_MOTION_MEDIAN_METRIC: 0.10,
            AEC_MOTION_P10_METRIC: 0.02,
        },
    }
    better = {
        "validation_result": "PASS",
        "summary": {
            AEC_MOTION_MEDIAN_METRIC: 0.15,
            AEC_MOTION_P10_METRIC: 0.04,
        },
    }
    score, deltas = guarded.strict_score(space, baseline, better)
    assert score > 0.0
    assert {item["metric"] for item in deltas} == AEC_MOTION_METRICS
    assert not guarded.strict_regression(space, baseline, better)
    missing = {
        "validation_result": "PASS",
        "summary": {
            AEC_MOTION_MEDIAN_METRIC: 0.15,
            AEC_MOTION_P10_METRIC: None,
        },
    }
    assert guarded.strict_regression(space, baseline, missing)
    print(json.dumps({"result": "PASS", "metrics": sorted(AEC_MOTION_METRICS)}, sort_keys=True))


def main() -> int:
    install_motion_metrics()
    if "--self-test" in __import__("sys").argv:
        self_test()
        return 0
    return guarded.main()


if __name__ == "__main__":
    raise SystemExit(main())
