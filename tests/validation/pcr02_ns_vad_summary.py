#!/usr/bin/env python3
"""Compare EMA and MCRA on identical PCR02-like mechanical counterfactual reports.

This is a diagnostic comparator. It reports signed MCRA-minus-EMA deltas and
never selects or promotes an estimator.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

METRICS = (
    "noise_only_attenuation_db",
    "vad_false_positive_rate",
    "near_si_sdr_improvement_db",
    "vad_f1",
    "vad_recall",
    "speech_active_attenuation_db",
)


def finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def median(values):
    values = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(values) if values else None


def summarize(report: dict) -> dict:
    rows = report.get("cases", [])
    noise = [row for row in rows if not bool(row.get("dimensions", {}).get("speech_present"))]
    speech = [row for row in rows if bool(row.get("dimensions", {}).get("speech_present"))]
    out = {
        "cases": len(rows),
        "validation_result": report.get("validation_result"),
        "noise_only": {},
        "speech_mix": {},
    }
    for name in METRICS:
        out["noise_only"][name] = median(finite(row.get("metrics", {}).get(name)) for row in noise)
        out["speech_mix"][name] = median(finite(row.get("metrics", {}).get(name)) for row in speech)
    return out


def compare(ema: dict, mcra: dict) -> dict:
    ema_by_id = {row["case_id"]: row for row in ema.get("cases", [])}
    mcra_by_id = {row["case_id"]: row for row in mcra.get("cases", [])}
    if set(ema_by_id) != set(mcra_by_id) or not ema_by_id:
        raise ValueError("EMA/MCRA report case identity mismatch")

    ema_summary = summarize(ema)
    mcra_summary = summarize(mcra)
    deltas = {"noise_only": {}, "speech_mix": {}}
    for group in deltas:
        for metric in METRICS:
            a = ema_summary[group][metric]
            b = mcra_summary[group][metric]
            deltas[group][metric] = None if a is None or b is None else b - a

    per_case = []
    for case_id in sorted(ema_by_id):
        a = ema_by_id[case_id]
        b = mcra_by_id[case_id]
        row = {"case_id": case_id, "dimensions": a.get("dimensions", {}), "mcra_minus_ema": {}}
        if row["dimensions"] != b.get("dimensions", {}):
            raise ValueError(f"dimension drift: {case_id}")
        for metric in METRICS:
            av = finite(a.get("metrics", {}).get(metric))
            bv = finite(b.get("metrics", {}).get(metric))
            row["mcra_minus_ema"][metric] = None if av is None or bv is None else bv - av
        per_case.append(row)

    return {
        "schema_version": 1,
        "authority": "diagnostic-regression-only",
        "promotion_allowed": False,
        "shipping_incumbent": "EMA",
        "candidate": "MCRA",
        "delta_convention": "MCRA minus EMA; positive is not universally better because metric directions differ",
        "metric_direction": {
            "noise_only_attenuation_db": "higher-better",
            "vad_false_positive_rate": "lower-better",
            "near_si_sdr_improvement_db": "higher-better",
            "vad_f1": "higher-better",
            "vad_recall": "higher-better",
            "speech_active_attenuation_db": "lower-better",
        },
        "ema": ema_summary,
        "mcra": mcra_summary,
        "mcra_minus_ema": deltas,
        "cases": per_case,
    }


def self_test() -> None:
    template = {
        "validation_result": "PASS",
        "cases": [
            {"case_id": "noise", "dimensions": {"speech_present": False}, "metrics": {"noise_only_attenuation_db": 2.0, "vad_false_positive_rate": 0.1}},
            {"case_id": "speech", "dimensions": {"speech_present": True}, "metrics": {"near_si_sdr_improvement_db": 1.0, "vad_f1": 0.8}},
        ],
    }
    other = json.loads(json.dumps(template))
    other["cases"][0]["metrics"]["noise_only_attenuation_db"] = 3.0
    result = compare(template, other)
    assert result["mcra_minus_ema"]["noise_only"]["noise_only_attenuation_db"] == 1.0
    assert result["promotion_allowed"] is False
    print("PCR02 NS/VAD counterfactual summary self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ema-report", type=Path)
    p.add_argument("--mcra-report", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.ema_report or not args.mcra_report or not args.output:
        p.error("--ema-report, --mcra-report and --output are required")
    result = compare(
        json.loads(args.ema_report.read_text(encoding="utf-8")),
        json.loads(args.mcra_report.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"authority": result["authority"], "promotion_allowed": result["promotion_allowed"], "mcra_minus_ema": result["mcra_minus_ema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
