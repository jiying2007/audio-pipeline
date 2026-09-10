#!/usr/bin/env python3
"""Summarize real Microsoft AEC 32/48/64 ms tail confirmation.

The acceptance contract is frozen before measurement. A shorter tail is only
CONFIRMATION_POSITIVE when it passes the existing far-end and double-talk
research policies, does not regress aggregate/static/moving far-end median
render-correlation reduction versus the 64 ms incumbent, and reduces static
pipeline state. Positive means eligible for PCR02/SSC305 HIL confirmation only;
this tool never promotes or changes shipping configuration.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

TAILS_MS = (32, 48, 64)
INCUMBENT_MS = 64
SCENARIOS = ("aec-farend-static", "aec-farend-moving")


def finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def scenario_median(report: dict, scenario: str) -> float | None:
    node = report.get("summary", {}).get("scenario_metrics", {}).get(scenario, {})
    metric = node.get("metrics", {}).get("output_render_corr_reduction", {})
    return finite(metric.get("median"))


def load(root: Path, tail: int, kind: str) -> dict:
    path = root / f"{kind}-tail-{tail}.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def aggregate(root: Path) -> dict:
    rows = []
    corpus_bindings = None
    for tail in TAILS_MS:
        far = load(root, tail, "farend")
        dt = load(root, tail, "doubletalk")
        state_path = root / f"state-{tail}.txt"
        if not state_path.is_file():
            raise FileNotFoundError(state_path)
        bindings = {
            "farend_corpus_sha256": far.get("bindings", {}).get("corpus_sha256"),
            "farend_source_manifest_sha256": far.get("bindings", {}).get("source_manifest_sha256"),
            "doubletalk_corpus_sha256": dt.get("bindings", {}).get("corpus_sha256"),
            "doubletalk_source_manifest_sha256": dt.get("bindings", {}).get("source_manifest_sha256"),
        }
        if corpus_bindings is None:
            corpus_bindings = bindings
        elif bindings != corpus_bindings:
            raise ValueError(f"cross-tail corpus/source binding drift at {tail} ms")
        row = {
            "tail_ms": tail,
            "shipping_incumbent": tail == INCUMBENT_MS,
            "pipeline_state_bytes": int(state_path.read_text(encoding="utf-8").strip()),
            "farend_result": far.get("validation_result"),
            "doubletalk_result": dt.get("validation_result"),
            "farend_pass_rate": finite(far.get("summary", {}).get("pass_rate")),
            "doubletalk_pass_rate": finite(dt.get("summary", {}).get("pass_rate")),
            "farend_median_corr_reduction": finite(far.get("summary", {}).get("median_output_render_corr_reduction")),
            "farend_static_median_corr_reduction": scenario_median(far, "aec-farend-static"),
            "farend_moving_median_corr_reduction": scenario_median(far, "aec-farend-moving"),
            "max_output_clip_fraction": max(
                finite(far.get("summary", {}).get("max_output_clip_fraction")) or 0.0,
                finite(dt.get("summary", {}).get("max_output_clip_fraction")) or 0.0,
            ),
        }
        if any(row[name] is None for name in (
            "farend_pass_rate", "doubletalk_pass_rate", "farend_median_corr_reduction",
            "farend_static_median_corr_reduction", "farend_moving_median_corr_reduction"
        )):
            raise ValueError(f"missing canonical real-AEC metrics at {tail} ms")
        rows.append(row)

    incumbent = next(row for row in rows if row["tail_ms"] == INCUMBENT_MS)
    if incumbent["farend_result"] != "PASS" or incumbent["doubletalk_result"] != "PASS":
        raise ValueError("64 ms incumbent failed existing real-AEC research policy")

    for row in rows:
        row["state_bytes_delta_vs_64ms"] = row["pipeline_state_bytes"] - incumbent["pipeline_state_bytes"]
        row["aggregate_corr_delta_vs_64ms"] = row["farend_median_corr_reduction"] - incumbent["farend_median_corr_reduction"]
        row["static_corr_delta_vs_64ms"] = row["farend_static_median_corr_reduction"] - incumbent["farend_static_median_corr_reduction"]
        row["moving_corr_delta_vs_64ms"] = row["farend_moving_median_corr_reduction"] - incumbent["farend_moving_median_corr_reduction"]
        if row["shipping_incumbent"]:
            row["confirmation"] = "INCUMBENT"
            continue
        positive = (
            row["farend_result"] == "PASS"
            and row["doubletalk_result"] == "PASS"
            and row["farend_median_corr_reduction"] >= incumbent["farend_median_corr_reduction"]
            and row["farend_static_median_corr_reduction"] >= incumbent["farend_static_median_corr_reduction"]
            and row["farend_moving_median_corr_reduction"] >= incumbent["farend_moving_median_corr_reduction"]
            and row["pipeline_state_bytes"] < incumbent["pipeline_state_bytes"]
        )
        row["confirmation"] = "CONFIRMATION_POSITIVE" if positive else "HOLD"

    positives = [row["tail_ms"] for row in rows if row["confirmation"] == "CONFIRMATION_POSITIVE"]
    return {
        "schema_version": 1,
        "authority": "research-validation-confirmation-only",
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "eligible_for_pcr02_hil_confirmation": positives,
        "shipping_incumbent_tail_ms": INCUMBENT_MS,
        "frozen_acceptance": {
            "existing_farend_policy_pass": True,
            "existing_doubletalk_policy_pass": True,
            "aggregate_farend_median_not_below_64ms": True,
            "static_farend_median_not_below_64ms": True,
            "moving_farend_median_not_below_64ms": True,
            "pipeline_state_bytes_below_64ms": True,
        },
        "source_bindings": corpus_bindings,
        "rows": rows,
        "interpretation_boundary": [
            "Public Microsoft AEC research data is not PCR02 real-SKU, SSC305 HIL, or Product Qualification evidence.",
            "CONFIRMATION_POSITIVE only admits a shorter tail to PCR02/SSC305 HIL confirmation.",
            "No result from this tool changes the 64 ms shipping preset.",
        ],
    }


def self_test() -> None:
    assert TAILS_MS == (32, 48, 64)
    assert INCUMBENT_MS in TAILS_MS
    assert set(SCENARIOS) == {"aec-farend-static", "aec-farend-moving"}
    print("PCR02 real-AEC tail confirmation summary self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test(); return 0
    if args.root is None or args.output is None:
        p.error("--root and --output are required")
    result = aggregate(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "authority": result["authority"],
        "promotion_allowed": result["promotion_allowed"],
        "eligible_for_pcr02_hil_confirmation": result["eligible_for_pcr02_hil_confirmation"],
        "rows": result["rows"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
