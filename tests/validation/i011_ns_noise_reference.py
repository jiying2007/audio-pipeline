#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))

import run_validation_engine as engine  # type: ignore

REQUIRED_CASES = {
    "stage-vad-stationary-negative",
    "stage-ns-stationary",
    "stage-ns-nonstationary",
}
WARMUP_FRAMES = 80


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def p90(values: list[float]) -> float:
    if not values:
        raise ValueError("p90 requires non-empty values")
    ordered = sorted(values)
    index = max(0, math.ceil(0.90 * len(ordered)) - 1)
    return ordered[index]


def resolve(corpus_path: Path, raw: str | None) -> Path | None:
    return engine.resolve(corpus_path, raw)


def run_probe(probe: Path, raw_pcm: Path) -> list[dict[str, float | int]]:
    completed = subprocess.run(
        [str(probe), str(raw_pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows: list[dict[str, float | int]] = []
    for number, line in enumerate(completed.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid probe JSONL line {number}: {exc.msg}") from exc
        rows.append(row)
    if not rows:
        raise ValueError("I011 probe produced no rows")
    return rows


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = resolve(corpus_path, case.get("mic_audio"))
    labels_path = resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError(f"I011 case missing mic/labels: {case.get('case_id')}")
    if int(case.get("sample_rate_hz", 0)) != 16000:
        raise ValueError(f"I011 requires 16 kHz case: {case.get('case_id')}")
    if int(case.get("mic_channels", 0)) != 1:
        raise ValueError(f"I011 requires mono case: {case.get('case_id')}")

    with tempfile.TemporaryDirectory(prefix="ap-i011-stage-") as tmp:
        work = Path(tmp)
        _, staged_raw = engine.stage_audio(mic, 16000, 1, work, "mic.pcm")
        rows = run_probe(probe, staged_raw)

    labels = engine.load_labels(labels_path)
    count = min(len(labels), len(rows))
    if count <= WARMUP_FRAMES:
        raise ValueError(f"I011 case too short after warmup: {case.get('case_id')}")
    return {
        "case_id": str(case["case_id"]),
        "profile": str(case.get("processor_profile", "")),
        "labels": [int(x) for x in labels[:count]],
        "rows": rows[:count],
    }


def summarize(cases: list[dict[str, Any]], expected_offset: float) -> dict[str, Any]:
    floor_noise_delta = 0.0
    floor_speech_delta = 0.0
    offset_error = 0.0
    stationary_legacy_bias: list[float] = []
    stationary_calibrated_bias: list[float] = []
    speech_proxy_snr: list[float] = []
    noise_proxy_snr: list[float] = []
    speech_upstream: list[float] = []
    noise_upstream: list[float] = []
    case_summaries: list[dict[str, Any]] = []

    for case in cases:
        case_proxy: list[float] = []
        for index, (label, row) in enumerate(zip(case["labels"], case["rows"])):
            legacy_base = float(row["legacy_base_noise_dbfs"])
            legacy_stress = float(row["legacy_stress_noise_dbfs"])
            calibrated = float(row["calibrated_base_noise_dbfs"])
            calibrated_stress = float(row["calibrated_stress_noise_dbfs"])
            input_rms = float(row["input_rms_dbfs"])
            upstream = float(row["base_speech_probability"])
            upstream_stress = float(row["stress_speech_probability"])
            row_offset = float(row["scale_offset_db"])
            values = (
                legacy_base, legacy_stress, calibrated, calibrated_stress,
                input_rms, upstream, upstream_stress, row_offset,
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"non-finite I011 metric: {case['case_id']} frame={index}")
            if int(row["nfft"]) != 512 or int(row["bins"]) != 257:
                raise ValueError("I011 FFT geometry drifted")

            floor_noise_delta = max(
                floor_noise_delta, abs(legacy_base - legacy_stress)
            )
            floor_speech_delta = max(
                floor_speech_delta, abs(upstream - upstream_stress)
            )
            offset_error = max(offset_error, abs(row_offset - expected_offset))

            if index < WARMUP_FRAMES:
                continue
            proxy_snr = input_rms - calibrated
            case_proxy.append(proxy_snr)
            if case["case_id"] == "stage-vad-stationary-negative":
                stationary_legacy_bias.append(legacy_base - input_rms)
                stationary_calibrated_bias.append(calibrated - input_rms)
            if case["case_id"].startswith("stage-ns-"):
                if label:
                    speech_proxy_snr.append(proxy_snr)
                    speech_upstream.append(upstream)
                else:
                    noise_proxy_snr.append(proxy_snr)
                    noise_upstream.append(upstream)

        case_summaries.append({
            "case_id": case["case_id"],
            "profile": case["profile"],
            "frames": len(case["rows"]),
            "post_warmup_proxy_snr_median_db": (
                statistics.median(case_proxy) if case_proxy else None
            ),
        })

    required = (
        stationary_legacy_bias,
        stationary_calibrated_bias,
        speech_proxy_snr,
        noise_proxy_snr,
        speech_upstream,
        noise_upstream,
    )
    if any(not values for values in required):
        raise ValueError("I011 diagnostic did not exercise required stationary/speech/noise frames")

    abs_calibrated = [abs(value) for value in stationary_calibrated_bias]
    return {
        "max_floor_noise_metric_delta_db": floor_noise_delta,
        "max_floor_speech_probability_delta": floor_speech_delta,
        "max_scale_offset_error_db": offset_error,
        "stationary_legacy_median_bias_db": statistics.median(stationary_legacy_bias),
        "stationary_calibrated_median_bias_db": statistics.median(stationary_calibrated_bias),
        "stationary_calibrated_p90_abs_error_db": p90(abs_calibrated),
        "speech_proxy_snr_median_db": statistics.median(speech_proxy_snr),
        "noise_proxy_snr_median_db": statistics.median(noise_proxy_snr),
        "proxy_snr_median_separation_db": (
            statistics.median(speech_proxy_snr) - statistics.median(noise_proxy_snr)
        ),
        "speech_upstream_probability_median": statistics.median(speech_upstream),
        "noise_upstream_probability_median": statistics.median(noise_upstream),
        "case_summaries": case_summaries,
    }


def decide(summary: dict[str, Any], gates: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    checks = [
        (
            "floor_noise_metric_invariance",
            float(summary["max_floor_noise_metric_delta_db"]) <=
            float(gates["max_floor_noise_metric_delta_db"]),
            summary["max_floor_noise_metric_delta_db"],
            gates["max_floor_noise_metric_delta_db"],
        ),
        (
            "floor_speech_probability_invariance",
            float(summary["max_floor_speech_probability_delta"]) <=
            float(gates["max_floor_speech_probability_delta"]),
            summary["max_floor_speech_probability_delta"],
            gates["max_floor_speech_probability_delta"],
        ),
        (
            "legacy_scale_gap_exercised",
            float(summary["stationary_legacy_median_bias_db"]) <
            float(gates["legacy_stationary_bias_must_be_below_db"]),
            summary["stationary_legacy_median_bias_db"],
            gates["legacy_stationary_bias_must_be_below_db"],
        ),
        (
            "calibrated_stationary_median_bias",
            abs(float(summary["stationary_calibrated_median_bias_db"])) <=
            float(gates["max_abs_calibrated_stationary_median_bias_db"]),
            summary["stationary_calibrated_median_bias_db"],
            gates["max_abs_calibrated_stationary_median_bias_db"],
        ),
        (
            "calibrated_stationary_p90_error",
            float(summary["stationary_calibrated_p90_abs_error_db"]) <=
            float(gates["max_calibrated_stationary_p90_abs_error_db"]),
            summary["stationary_calibrated_p90_abs_error_db"],
            gates["max_calibrated_stationary_p90_abs_error_db"],
        ),
    ]
    violations = [
        {"gate": name, "actual": actual, "limit": limit}
        for name, passed, actual, limit in checks
        if not passed
    ]
    decision = (
        "NS_NOISE_REFERENCE_SCALE_SUPPORTED_REVIEW_REQUIRED"
        if not violations
        else "NS_NOISE_REFERENCE_SCALE_NOT_SUPPORTED_REVIEW_REQUIRED"
    )
    return decision, violations


def evaluate(probe: Path, corpora: list[Path], contract_path: Path,
             output: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    expected_seeds = [int(x) for x in contract["fresh_seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("I011 corpus count must match preregistered fresh seeds")
    if contract.get("candidate_limit") != 0 or contract.get("confirmation_limit") != 0:
        raise ValueError("I011 candidate/confirmation budgets must remain zero")
    if contract.get("parameter_search_allowed") is not False or        contract.get("threshold_tuning_allowed") is not False:
        raise ValueError("I011 cannot search parameters or thresholds")

    cases: list[dict[str, Any]] = []
    actual_seeds: list[int] = []
    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if str(case.get("case_id")) in REQUIRED_CASES
        }
        if set(selected) != REQUIRED_CASES:
            raise ValueError(
                f"I011 required cases missing for seed {seed}: "
                f"{sorted(REQUIRED_CASES - set(selected))}"
            )
        for case_id in sorted(REQUIRED_CASES):
            cases.append(run_case(probe, corpus_path, selected[case_id]))

    if actual_seeds != expected_seeds:
        raise ValueError(
            f"I011 seed drift: actual={actual_seeds} expected={expected_seeds}"
        )

    expected_offset = float(contract["hypothesis"]["expected_scale_offset_db"])
    summary = summarize(cases, expected_offset)
    if float(summary["max_scale_offset_error_db"]) > 1.0e-5:
        raise ValueError("I011 probe scale derivation drifted from preregistered contract")

    decision, violations = decide(summary, contract["diagnostic_gates"])
    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": "RESEARCH_DIAGNOSTIC_ONLY",
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": actual_seeds,
        "candidate_limit_consumed": 0,
        "confirmation_limit_consumed": 0,
        "shipping_source_changed": False,
        "summary": summary,
        "violations": violations,
        "interpretation": {
            "legacy_metric_direct_time_domain_use_supported": False,
            "calibrated_noise_reference_candidate_selected": False,
            "same_domain_snr_candidate_selected": False,
            "note": (
                "This run only tests the deterministic NS noise metric scale model "
                "and floor invariance. Proxy SNR separation is descriptive evidence, "
                "not a threshold or candidate selection."
            ),
        },
        "authority_boundary": contract["authority_boundary"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert p90(values) == 5.0
    gates = {
        "max_floor_noise_metric_delta_db": 1e-6,
        "max_floor_speech_probability_delta": 1e-7,
        "legacy_stationary_bias_must_be_below_db": -20.0,
        "max_abs_calibrated_stationary_median_bias_db": 3.0,
        "max_calibrated_stationary_p90_abs_error_db": 5.0,
    }
    good = {
        "max_floor_noise_metric_delta_db": 0.0,
        "max_floor_speech_probability_delta": 0.0,
        "stationary_legacy_median_bias_db": -32.0,
        "stationary_calibrated_median_bias_db": 0.2,
        "stationary_calibrated_p90_abs_error_db": 1.0,
    }
    decision, violations = decide(good, gates)
    assert decision == "NS_NOISE_REFERENCE_SCALE_SUPPORTED_REVIEW_REQUIRED"
    assert violations == []
    bad = dict(good)
    bad["stationary_calibrated_p90_abs_error_db"] = 6.0
    decision, violations = decide(bad, gates)
    assert decision == "NS_NOISE_REFERENCE_SCALE_NOT_SUPPORTED_REVIEW_REQUIRED"
    assert violations[0]["gate"] == "calibrated_stationary_p90_error"
    print("I011 NS noise-reference scale evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.corpus or not args.output:
        parser.error("--probe, --contract, --corpus and --output are required")

    result = evaluate(
        args.probe.resolve(),
        [path.resolve() for path in args.corpus],
        args.contract.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "fresh_seeds": result["fresh_seeds"],
        "summary": result["summary"],
        "violations": result["violations"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
