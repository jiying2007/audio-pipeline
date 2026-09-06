#!/usr/bin/env python3
"""Evaluate candidate-zero I007 BF health behavior on exact reviewed main."""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Sequence

import i007_bf_health_corpus as corpus_builder

RATE = 16000
FRAME = 160
ALIGN_RADIUS = 8


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def read_pcm(path: Path) -> list[int]:
    raw = path.read_bytes()
    require(len(raw) % 2 == 0, f"odd PCM bytes: {path}")
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def rms_dbfs(values: Sequence[int]) -> float:
    if not values:
        return -120.0
    energy = sum(float(v) * float(v) for v in values) / len(values)
    return 10.0 * math.log10(max(energy, 1.0e-18) / (32768.0 * 32768.0))


def dc_dbfs(values: Sequence[int]) -> float:
    if not values:
        return -120.0
    mean = abs(sum(float(v) for v in values) / len(values))
    return 20.0 * math.log10(max(mean, 1.0e-12) / 32768.0)


def clip_fraction(values: Sequence[int]) -> float:
    return sum(abs(int(v)) >= 32760 for v in values) / max(1, len(values))


def si_sdr(reference: Sequence[int], estimate: Sequence[int]) -> float:
    count = min(len(reference), len(estimate))
    require(count >= 32, "SI-SDR window too short")
    r = [float(v) for v in reference[:count]]
    e = [float(v) for v in estimate[:count]]
    rr = sum(v * v for v in r)
    require(rr > 1.0e-12, "silent clean reference")
    scale = sum(x * y for x, y in zip(r, e)) / rr
    target = sum((scale * x) ** 2 for x in r)
    error = sum((y - scale * x) ** 2 for x, y in zip(r, e))
    return 10.0 * math.log10((target + 1.0e-12) / (error + 1.0e-12))


def corr(reference: Sequence[int], estimate: Sequence[int], lag: int,
         start: int, end: int) -> float:
    xy = xx = yy = 0.0
    used = 0
    for i in range(start, min(end, len(reference)), 2):
        j = i + lag
        if j < 0 or j >= len(estimate):
            continue
        x, y = float(reference[i]), float(estimate[j])
        xy += x * y
        xx += x * x
        yy += y * y
        used += 1
    if used < 16 or xx <= 1.0e-12 or yy <= 1.0e-12:
        return -2.0
    return xy / math.sqrt(xx * yy)


def estimate_lag(reference: Sequence[int], estimate: Sequence[int], start: int, end: int) -> int:
    return max(range(-ALIGN_RADIUS, ALIGN_RADIUS + 1),
               key=lambda lag: corr(reference, estimate, lag, start, end))


def aligned(reference: Sequence[int], estimate: Sequence[int], lag: int,
            start: int, end: int) -> tuple[list[int], list[int]]:
    r: list[int] = []
    e: list[int] = []
    for i in range(start, min(end, len(reference))):
        j = i + lag
        if 0 <= j < len(estimate):
            r.append(int(reference[i]))
            e.append(int(estimate[j]))
    return r, e


def score(reference: Sequence[int], estimate: Sequence[int], lag: int,
          start_frame: int, end_frame: int) -> float:
    r, e = aligned(reference, estimate, lag, start_frame * FRAME, end_frame * FRAME)
    return si_sdr(r, e)


def score_with_local_alignment(reference: Sequence[int], estimate: Sequence[int],
                               start_frame: int, end_frame: int) -> tuple[float, int]:
    start = start_frame * FRAME
    end = end_frame * FRAME
    lag = estimate_lag(reference, estimate, start, end)
    return score(reference, estimate, lag, start_frame, end_frame), lag


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = q * (len(ordered) - 1)
    lo = int(math.floor(position))
    hi = int(math.ceil(position))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def load_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def active_fraction(trace: list[dict], start: int, end: int) -> float:
    rows = trace[start:end]
    return sum(int(row["fallback_active"]) != 0 for row in rows) / max(1, len(rows))


def reliable_selected_fraction(trace: list[dict], start: int, end: int,
                               reliable_channel: int) -> float | None:
    rows = [row for row in trace[start:end] if int(row["fallback_active"]) != 0]
    if not rows:
        return None
    return sum(int(row["fallback_strong_channel"]) == reliable_channel for row in rows) / len(rows)


def stable_recovery(trace: list[dict], start: int, stable_frames: int = 40) -> int | None:
    active = [int(row["fallback_active"]) != 0 for row in trace]
    for frame in range(start, max(start, len(active) - stable_frames + 1)):
        if not any(active[frame:frame + stable_frames]):
            return frame - start
    return None


def build_probe(root: Path, output: Path) -> Path:
    build = output / "build"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked(["cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                 "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON",
                 f"-DAP_BUILD_SOURCE_REVISION={revision}"])
    run_checked(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"])
    probe = build / "i007_bf_health_probe"
    run_checked(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(root / "src"), "-I" + str(root / "include"),
                 "-I" + str(build / "generated"),
                 str(root / "tests/validation/i007_bf_health_probe.c"),
                 str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe)])
    return probe


def run_case(probe: Path, corpus_root: Path, case: dict, frontend: str,
             work: Path, contract: dict) -> dict:
    case_work = work / frontend / str(case["case_id"])
    case_work.mkdir(parents=True, exist_ok=True)
    mic = corpus_root / str(case["mic_audio"])
    clean_path = corpus_root / str(case["clean_audio"])
    out = case_work / "bf.pcm"
    ch0 = case_work / "ch0.pcm"
    ch1 = case_work / "ch1.pcm"
    trace_path = case_work / "trace.jsonl"
    run_checked([str(probe), "--sample-rate", str(contract["sample_rate_hz"]),
                 "--spacing-mm", str(contract["mic_spacing_mm"]), "--frontend", frontend,
                 str(mic), str(out), str(ch0), str(ch1), str(trace_path)])
    clean = read_pcm(clean_path)
    bf = read_pcm(out)
    c0 = read_pcm(ch0)
    c1 = read_pcm(ch1)
    trace = load_trace(trace_path)
    frames = int(case["frames"])
    require(len(trace) == frames and len(bf) == frames * FRAME, "probe output length")

    start = int(case["window_start_frame"])
    end = int(case["window_end_frame"])
    pre_start = 60
    pre_end = max(pre_start + 1, start - 20) if start > 100 else min(frames - 1, 180)
    window_start = min(end - 1, start + 40) if start > 0 else 60
    window_end = max(window_start + 1, end - 20) if end < frames else frames - 60
    post_start = min(frames - 1, end + 60)
    post_end = max(post_start + 1, frames - 20)

    align_start = pre_start * FRAME
    align_end = pre_end * FRAME
    lag_bf = estimate_lag(clean, bf, align_start, align_end)
    lag0 = estimate_lag(clean, c0, align_start, align_end)
    lag1 = estimate_lag(clean, c1, align_start, align_end)
    window_scores = {
        "bf": score(clean, bf, lag_bf, window_start, window_end),
        "ch0": score(clean, c0, lag0, window_start, window_end),
        "ch1": score(clean, c1, lag1, window_start, window_end),
    }
    pre_scores = {
        "bf": score(clean, bf, lag_bf, pre_start, pre_end),
        "ch0": score(clean, c0, lag0, pre_start, pre_end),
        "ch1": score(clean, c1, lag1, pre_start, pre_end),
    }
    best_single = max(window_scores["ch0"], window_scores["ch1"])
    pre_best_single = max(pre_scores["ch0"], pre_scores["ch1"])
    metrics: dict[str, object] = {
        "pre_fallback_fraction": active_fraction(trace, 0, max(1, start)) if start else active_fraction(trace, 0, 180),
        "window_fallback_fraction": active_fraction(trace, start, end) if end > start else active_fraction(trace, 60, frames - 60),
        "window_hard_fault_fraction": sum(int(row["fallback_hard_fault"]) != 0 for row in trace[start:end]) /
                                      max(1, end - start) if end > start else 0.0,
        "window_bf_si_sdr_db": window_scores["bf"],
        "window_best_single_si_sdr_db": best_single,
        "window_output_minus_best_single_si_sdr_db": window_scores["bf"] - best_single,
        "pre_output_minus_best_single_si_sdr_db": pre_scores["bf"] - pre_best_single,
        "output_clip_fraction": clip_fraction(bf),
        "output_dc_offset_dbfs": dc_dbfs(bf),
        "output_rms_dbfs": rms_dbfs(bf),
        "alignment_lag_samples": {"bf": lag_bf, "ch0": lag0, "ch1": lag1},
    }

    reliable = case.get("reliable_channel")
    if reliable is not None:
        reliable = int(reliable)
        key = f"ch{reliable}"
        pre_delta = pre_scores["bf"] - pre_scores[key]
        window_delta = window_scores["bf"] - window_scores[key]
        post_bf = score(clean, bf, lag_bf, post_start, post_end)
        post_reliable = score(clean, c0 if reliable == 0 else c1,
                              lag0 if reliable == 0 else lag1, post_start, post_end)
        metrics.update({
            "reliable_channel": reliable,
            "window_reliable_si_sdr_db": window_scores[key],
            "window_output_minus_reliable_si_sdr_db": window_delta,
            "pre_output_minus_reliable_si_sdr_db": pre_delta,
            "post_output_minus_reliable_si_sdr_db": post_bf - post_reliable,
            "post_output_minus_reliable_regression_db": max(0.0, pre_delta - (post_bf - post_reliable)),
            "reliable_selected_fraction_when_fallback": reliable_selected_fraction(trace, start, end, reliable),
            "stable_recovery_frames": stable_recovery(trace, end),
        })

    if case["scenario"] == "motion-tdoa-sweep":
        errors: list[float] = []
        segment_quality: list[dict] = []
        segment_deltas: list[float] = []
        for segment in case["dimensions"]["segments"]:
            seg_start = int(segment["start_frame"])
            seg_end = int(segment["end_frame"])
            expected = int(segment["expected_bf_lag_samples"])
            settled_start = min(seg_end - 1, seg_start + 20)
            settled_end = max(settled_start + 1, seg_end - 20)
            for row in trace[settled_start:seg_end]:
                errors.append(abs(int(row["lag"]) - expected))
            bf_score, bf_align = score_with_local_alignment(clean, bf, settled_start, settled_end)
            ch0_score, ch0_align = score_with_local_alignment(clean, c0, settled_start, settled_end)
            ch1_score, ch1_align = score_with_local_alignment(clean, c1, settled_start, settled_end)
            delta = bf_score - max(ch0_score, ch1_score)
            segment_deltas.append(delta)
            segment_quality.append({
                "start_frame": seg_start,
                "end_frame": seg_end,
                "settled_start_frame": settled_start,
                "settled_end_frame": settled_end,
                "expected_bf_lag_samples": expected,
                "bf_si_sdr_db": bf_score,
                "ch0_si_sdr_db": ch0_score,
                "ch1_si_sdr_db": ch1_score,
                "output_minus_best_single_si_sdr_db": delta,
                "alignment_lag_samples": {"bf": bf_align, "ch0": ch0_align, "ch1": ch1_align},
            })
        require(segment_deltas, "motion segments required")
        metrics["lag_abs_error_p95_samples"] = percentile(errors, 0.95)
        metrics["motion_lag_observations"] = len(errors)
        metrics["motion_segment_quality"] = segment_quality
        metrics["motion_worst_segment_output_minus_best_single_si_sdr_db"] = min(segment_deltas)
        metrics["window_output_minus_best_single_si_sdr_db"] = min(segment_deltas)
    return metrics


def gate_case(case: dict, metrics: dict, contract: dict) -> list[str]:
    failures: list[str] = []
    global_gate = contract["diagnostic_gates"]["global"]
    if float(metrics["output_clip_fraction"]) > float(global_gate["max_output_clip_fraction"]):
        failures.append("output_clip_fraction")
    if float(metrics["output_dc_offset_dbfs"]) > float(global_gate["max_output_dc_offset_dbfs"]):
        failures.append("output_dc_offset")
    if float(metrics["pre_fallback_fraction"]) > float(global_gate["max_pre_fault_fallback_fraction"]):
        failures.append("pre_fault_fallback")

    scenario = str(case["scenario"])
    if scenario == "healthy-control":
        gate = contract["diagnostic_gates"]["healthy_control"]
        if float(metrics["window_output_minus_best_single_si_sdr_db"]) < float(gate["min_output_minus_best_single_si_sdr_db"]):
            failures.append("healthy_quality")
        if float(metrics["window_fallback_fraction"]) > float(gate["max_fault_window_fallback_fraction"]):
            failures.append("healthy_false_fallback")
    elif scenario == "motion-tdoa-sweep":
        gate = contract["diagnostic_gates"]["motion"]
        lag_error = metrics.get("lag_abs_error_p95_samples")
        if lag_error is None or float(lag_error) > float(gate["max_lag_abs_error_p95_samples"]):
            failures.append("motion_lag_tracking")
        if float(metrics["window_fallback_fraction"]) > float(gate["max_fallback_fraction"]):
            failures.append("motion_false_fallback")
        if float(metrics["window_output_minus_best_single_si_sdr_db"]) < float(gate["min_output_minus_best_single_si_sdr_db"]):
            failures.append("motion_quality")
    else:
        gate = contract["diagnostic_gates"]["soft_channel_impairment"]
        if float(metrics["window_output_minus_reliable_si_sdr_db"]) < float(gate["min_output_minus_reliable_si_sdr_db"]):
            failures.append("soft_impairment_quality")
        if float(metrics["post_output_minus_reliable_regression_db"]) > float(gate["max_post_output_minus_reliable_regression_db"]):
            failures.append("post_recovery_quality")
        selected = metrics.get("reliable_selected_fraction_when_fallback")
        if selected is not None and float(metrics["window_fallback_fraction"]) > 0.05 and \
                float(selected) < float(gate["min_reliable_selected_fraction_when_fallback"]):
            failures.append("fallback_channel_selection")
        recovery = metrics.get("stable_recovery_frames")
        if float(metrics["window_fallback_fraction"]) > 0.05 and \
                (recovery is None or int(recovery) > int(gate["max_stable_recovery_frames"])):
            failures.append("fallback_recovery")
    return failures


def validate_contract(contract: dict, root: Path) -> None:
    corpus_builder.validate_contract(contract)
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I007 exact base drift: {current}")
    require(contract["measurement_revision"] == 2, "I007 corrected measurement revision required")
    require(contract["measurement_lineage"]["revision_1"]["workflow_run_id"] == 34022991376 and
            contract["measurement_lineage"]["revision_1"]["artifact_id"] == 9986124236 and
            contract["measurement_lineage"]["revision_1"]["internal_sha256s_verified"] == 509,
            "I007 revision-1 attribution lineage")
    require(contract["measurement_lineage"]["revision_2"]["same_gate_values"] is True and
            contract["measurement_lineage"]["revision_2"]["new_confirmation_data"] is False,
            "I007 revision-2 cannot reset gates or confirmation")
    require(contract["historical_context"]["must_remeasure_current_main"] is True, "current-main remeasurement")
    require(contract["historical_context"]["research_bf_hard_mic_fault_discovery"] ==
            "regression-and-test-design-context-only", "old hard-fault branch authority")
    require(contract["historical_context"]["feat_bf_wind_health_bypass"] ==
            "stale-candidate-context-only", "old wind candidate authority")


def self_test() -> None:
    assert percentile([0.0, 10.0], 0.95) == 9.5
    assert abs(rms_dbfs([3277] * 160) + 19.999) < 0.02
    trace = [{"fallback_active": 1 if 10 <= i < 20 else 0,
              "fallback_strong_channel": 1, "fallback_hard_fault": 0} for i in range(100)]
    assert active_fraction(trace, 10, 20) == 1.0
    assert reliable_selected_fraction(trace, 10, 20, 1) == 1.0
    assert stable_recovery(trace, 20) == 0
    print(json.dumps({"result": "PASS", "measurement_revision": 2,
                      "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract is not None and args.output is not None, "contract/output required")
    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    validate_contract(contract, root)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    probe = build_probe(root, output)

    cases: list[dict] = []
    gate_failures: list[dict] = []
    input_failures: list[dict] = []
    for seed in contract["seeds"]:
        corpus_root = output / "corpus" / f"seed-{seed}"
        corpus = corpus_builder.build(corpus_root, contract, int(seed))
        for case in corpus["cases"]:
            for frontend in contract["frontends"]:
                try:
                    metrics = run_case(probe, corpus_root, case, frontend,
                                       output / "runs" / f"seed-{seed}", contract)
                    failures = gate_case(case, metrics, contract)
                except (ValueError, OSError, subprocess.CalledProcessError) as exc:
                    metrics = {"precondition_error": str(exc)}
                    failures = []
                    input_failures.append({"seed": seed, "scenario": case["scenario"],
                                           "frontend": frontend, "error": str(exc)})
                row = {"seed": seed, "scenario": case["scenario"], "frontend": frontend,
                       "metrics": metrics, "failures": failures}
                cases.append(row)
                if failures:
                    gate_failures.append({"seed": seed, "scenario": case["scenario"],
                                          "frontend": frontend, "failures": failures})
    if input_failures:
        decision = "INPUT_INVALID_REVIEW_REQUIRED"
    elif gate_failures:
        decision = "MEASURED_GAP_REVIEW_REQUIRED"
    else:
        decision = "BASELINE_ADEQUATE_NO_SEARCH"
    failure_counts: dict[str, int] = {}
    for item in gate_failures:
        for failure in item["failures"]:
            failure_counts[failure] = failure_counts.get(failure, 0) + 1
    report = {
        "schema_version": 1,
        "iteration_id": "I007",
        "phase": "bf-health-baseline-measurement",
        "measurement_revision": 2,
        "root_cause_id": contract["root_cause_id"],
        "source_sha": contract["base_sha"],
        "authority": "candidate-zero-current-main-bf-health-only",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "shipping_source_changed": False,
        "candidate_search_performed": False,
        "promotion_allowed": False,
        "probe_sha256": sha256(probe),
        "cases": cases,
        "aggregate": {
            "case_partitions": len(cases),
            "gate_failure_partitions": len(gate_failures),
            "input_failure_partitions": len(input_failures),
            "failure_counts": failure_counts,
        },
        "gate_failures": gate_failures,
        "input_failures": input_failures,
        "decision": decision,
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "measurement_lineage": contract["measurement_lineage"],
        "next_step": "review measured BF health gaps before authorizing any bounded source candidate",
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "baseline-result.json", report)
    manifest = {str(path.relative_to(output)): sha256(path) for path in sorted(output.rglob("*"))
                if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1,
                                                   "source_sha": contract["base_sha"],
                                                   "files": manifest})
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({"decision": decision, "measurement_revision": 2,
                      "partitions": len(cases), "gate_failures": len(gate_failures),
                      "input_failures": len(input_failures), "failure_counts": failure_counts,
                      "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I007 BF health baseline error: {exc}")
