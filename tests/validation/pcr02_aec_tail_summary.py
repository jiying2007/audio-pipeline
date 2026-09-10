#!/usr/bin/env python3
"""Aggregate PCR02 AEC tail counterfactual reports.

The 64 ms SSC305 setting is the incumbent. Other tail lengths are diagnostic
candidates only; this tool never promotes a candidate or changes thresholds.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

TAILS_MS = (32, 48, 64, 80, 96)
SEEDS = (4107, 4207, 4307)
INCUMBENT_MS = 64


def finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def median(values):
    values = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(values) if values else None


def aggregate(root: Path) -> dict:
    rows = []
    for tail in TAILS_MS:
        state_path = root / f"state-{tail}.txt"
        if not state_path.is_file():
            raise FileNotFoundError(state_path)
        state_bytes = int(state_path.read_text(encoding="utf-8").strip())
        reports = []
        for seed in SEEDS:
            path = root / f"report-tail-{tail}-seed-{seed}.json"
            if not path.is_file():
                raise FileNotFoundError(path)
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        pass_rates = [float(r["summary"]["pass_rate"]) for r in reports]
        corr = [finite(r["summary"].get("median_output_render_corr_reduction")) for r in reports]
        clip = [finite(r["summary"].get("max_output_clip_fraction")) for r in reports]
        corr_values = [v for v in corr if v is not None]
        clip_values = [v for v in clip if v is not None]
        if not corr_values or not clip_values:
            raise ValueError(f"missing canonical AEC metrics for tail={tail}")
        rows.append({
            "tail_ms": tail,
            "shipping_incumbent": tail == INCUMBENT_MS,
            "pipeline_state_bytes": state_bytes,
            "pass_rate": {"min": min(pass_rates), "median": statistics.median(pass_rates), "max": max(pass_rates)},
            "median_output_render_corr_reduction": {"min": min(corr_values), "median": median(corr_values), "max": max(corr_values)},
            "max_output_clip_fraction": max(clip_values),
            "reports": [r.get("corpus_id") for r in reports],
        })

    incumbent = next(row for row in rows if row["tail_ms"] == INCUMBENT_MS)
    for row in rows:
        row["state_bytes_delta_vs_64ms"] = row["pipeline_state_bytes"] - incumbent["pipeline_state_bytes"]
        row["state_bytes_ratio_vs_64ms"] = row["pipeline_state_bytes"] / incumbent["pipeline_state_bytes"]
        row["median_corr_reduction_delta_vs_64ms"] = row["median_output_render_corr_reduction"]["median"] - incumbent["median_output_render_corr_reduction"]["median"]
    return {
        "schema_version": 1,
        "authority": "diagnostic-regression-only",
        "promotion_allowed": False,
        "shipping_incumbent_tail_ms": INCUMBENT_MS,
        "fixed_conditions": {
            "sample_rate_hz": 16000,
            "max_delay_ms": 60,
            "initial_delay_ms": 40,
            "aec_backend": "MDF",
            "seeds": list(SEEDS),
        },
        "tails_ms": list(TAILS_MS),
        "rows": rows,
        "interpretation_boundary": [
            "pipeline_state_bytes is host-build static state evidence, not SSC305 HIL RAM proof",
            "candidate acoustic deltas do not authorize a shipping tail change",
            "negative candidate results are preserved",
        ],
    }


def self_test() -> None:
    assert INCUMBENT_MS in TAILS_MS
    assert max(TAILS_MS) <= 120
    assert len(SEEDS) == 3
    print("PCR02 AEC tail counterfactual summary self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.root or not args.output:
        p.error("--root and --output are required")
    result = aggregate(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"authority": result["authority"], "promotion_allowed": result["promotion_allowed"], "shipping_incumbent_tail_ms": result["shipping_incumbent_tail_ms"], "rows": result["rows"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
