#!/usr/bin/env python3
"""Candidate-zero diagnostic for double-talk onset vs route-change origin.

The probe runs the unchanged baseline processor, reads only already-public
per-frame metrics, and adds an offline input-domain mic/render correlation view.
It does not tune thresholds, select a candidate, or change shipping DSP.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import statistics
import subprocess
from pathlib import Path


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def read_pcm16(path: Path) -> list[int]:
    values = array.array("h")
    values.frombytes(path.read_bytes())
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def read_labels(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fraction(rows: list[dict], key: str) -> float | None:
    if not rows:
        return None
    return sum(int(row[key]) != 0 for row in rows) / len(rows)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def median(values: list[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(clean) if clean else None


def score_window(mic: list[int], render: list[int], start: int, end: int,
                 delay: int, stride: int) -> float:
    lo = max(start, delay)
    hi = min(end, len(mic), len(render) + delay)
    if hi - lo < stride * 16:
        return 0.0
    xy = 0.0
    xx = 1.0e-12
    yy = 1.0e-12
    for index in range(lo, hi, stride):
        x = float(render[index - delay])
        y = float(mic[index])
        xy += x * y
        xx += x * x
        yy += y * y
    return (xy * xy) / (xx * yy)


def route_snapshot(mic: list[int], render: list[int], rate: int, frame_samples: int,
                   start_frame: int, end_frame: int, cfg: dict) -> dict:
    start = max(0, start_frame * frame_samples)
    end = min(len(mic), len(render), end_frame * frame_samples)
    require(end > start, "empty route-correlation window")
    max_delay = int(round(float(cfg["max_delay_ms"]) * rate / 1000.0))
    coarse = int(cfg["coarse_step_samples"])
    stride = int(cfg["sample_stride"])
    guard = int(cfg["runner_guard_samples"])
    require(max_delay > 0 and coarse > 0 and stride > 0 and guard >= coarse,
            "invalid route-correlation configuration")

    candidates = [(score_window(mic, render, start, end, delay, stride), delay)
                  for delay in range(0, max_delay + 1, coarse)]
    best_score, best_delay = max(candidates)
    refine_lo = max(0, best_delay - coarse)
    refine_hi = min(max_delay, best_delay + coarse)
    for delay in range(refine_lo, refine_hi + 1):
        value = score_window(mic, render, start, end, delay, stride)
        if value > best_score:
            best_score, best_delay = value, delay
    runner = max((value for value, delay in candidates if abs(delay - best_delay) > guard),
                 default=0.0)
    ratio = None if runner <= 1.0e-12 else best_score / runner
    return {
        "start_frame": start_frame,
        "end_frame": end_frame,
        "best_delay_samples": best_delay,
        "best_delay_ms": 1000.0 * best_delay / rate,
        "best_score_squared": best_score,
        "runner_up_score_squared": runner,
        "peak_ratio": ratio,
    }


def metric_window(rows: list[dict], event: int, before: int, after: int) -> dict:
    require(0 <= event < len(rows), "metric event outside trace")
    pre = rows[max(0, event - before):event]
    post = rows[event:min(len(rows), event + after)]

    def delay_error_p95(part: list[dict]) -> float | None:
        return percentile([abs(float(row["delay_error_samples"])) for row in part], 0.95)

    def estimated_delay_median(part: list[dict]) -> float | None:
        return median([row["estimated_delay_ms"] for row in part])

    first_dt = next((int(row["frame"]) for row in post if int(row["double_talk_active"]) != 0), None)
    pre_delay = estimated_delay_median(pre)
    post_delay = estimated_delay_median(post)
    return {
        "event_frame": event,
        "pre_frames": len(pre),
        "post_frames": len(post),
        "pre_double_talk_fraction": fraction(pre, "double_talk_active"),
        "post_double_talk_fraction": fraction(post, "double_talk_active"),
        "pre_far_end_fraction": fraction(pre, "far_end_active"),
        "post_far_end_fraction": fraction(post, "far_end_active"),
        "pre_aec_converged_fraction": fraction(pre, "aec_converged"),
        "post_aec_converged_fraction": fraction(post, "aec_converged"),
        "pre_delay_error_abs_p95_samples": delay_error_p95(pre),
        "post_delay_error_abs_p95_samples": delay_error_p95(post),
        "pre_estimated_delay_ms_median": pre_delay,
        "post_estimated_delay_ms_median": post_delay,
        "estimated_delay_shift_ms": None if pre_delay is None or post_delay is None else post_delay - pre_delay,
        "first_double_talk_frame_in_post": first_dt,
        "double_talk_delay_from_event_frames": None if first_dt is None else first_dt - event,
    }


def rising_edges(labels: list[int]) -> list[int]:
    return [index for index, value in enumerate(labels)
            if value != 0 and (index == 0 or labels[index - 1] == 0)]


def run_processor(processor: Path, corpus_root: Path, corpus_id: str, case: dict,
                  output: Path) -> tuple[list[dict], list[int], list[int]]:
    require(case["mic_channels"] == 1, f"diagnostic requires mono case: {case['case_id']}")
    require(case.get("render_audio"), f"render required: {case['case_id']}")
    case_dir = output / "processor" / corpus_id / case["case_id"]
    case_dir.mkdir(parents=True, exist_ok=False)
    metrics_path = case_dir / "metrics.jsonl"
    out_path = case_dir / "out.pcm"
    mic_path = corpus_root / case["mic_audio"]
    render_path = corpus_root / case["render_audio"]
    command = [
        str(processor),
        "--sample-rate", str(case["sample_rate_hz"]),
        "--mic-channels", "1",
        "--metrics-jsonl", str(metrics_path),
    ]
    control = case.get("control") or {}
    if "echo_path_change_frame" in control:
        command += ["--echo-path-change-frame", str(control["echo_path_change_frame"])]
    if "discontinuity_frame" in control:
        command += [
            "--discontinuity-frame", str(control["discontinuity_frame"]),
            "--discontinuity-flags", str(control["discontinuity_flags"]),
            "--discontinuity-lost-frames", str(control["discontinuity_lost_frames"]),
        ]
    command += [str(mic_path), str(render_path), str(out_path)]
    subprocess.run(command, check=True)
    rows = [json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows, f"empty metrics trace: {case['case_id']}")
    require(all(int(row["frame"]) == index for index, row in enumerate(rows)),
            f"non-contiguous metrics trace: {case['case_id']}")
    return rows, read_pcm16(mic_path), read_pcm16(render_path)


def motion_truth(corpus_root: Path, case: dict, event: int) -> dict:
    source = case.get("source") or {}
    path = source.get("ground_truth")
    if not path:
        return {}
    truth = load_json(corpus_root / path)
    frames = truth["frame_start_paths"]
    require(frames, "motion ground truth has no frames")
    index = min(event, len(frames) - 1)
    initial = frames[0]["delay_samples"]
    current = frames[index]["delay_samples"]
    require(len(initial) == len(current) >= 2, "motion path vector")
    return {
        "motion": source.get("motion"),
        "direct_delay_delta_samples": current[0] - initial[0],
        "reflection_delay_drift_max_samples": max(abs(current[i] - initial[i]) for i in range(1, len(current))),
        "reflection_delay_drift_median_samples": statistics.median(
            [abs(current[i] - initial[i]) for i in range(1, len(current))]
        ),
    }


def event_record(cohort: str, corpus_id: str, case: dict, event: int,
                 rows: list[dict], mic: list[int], render: list[int], manifest: dict,
                 truth: dict | None = None) -> dict:
    before = int(manifest["analysis_window"]["metrics_frames_before"])
    after = int(manifest["analysis_window"]["metrics_frames_after"])
    route_cfg = manifest["observable_evidence"]["input_domain_route_probe"]
    route_before = int(route_cfg["event_window_frames_before"])
    route_after = int(route_cfg["event_window_frames_after"])
    rate = int(case["sample_rate_hz"])
    frame_samples = rate // 100
    pre_start = max(0, event - route_before)
    post_end = min(len(rows), event + route_after)
    require(event > pre_start and post_end > event, "event lacks correlation support")
    pre_route = route_snapshot(mic, render, rate, frame_samples, pre_start, event, route_cfg)
    post_route = route_snapshot(mic, render, rate, frame_samples, event, post_end, route_cfg)
    metrics = metric_window(rows, event, before, after)
    return {
        "cohort": cohort,
        "corpus": corpus_id,
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "event_frame": event,
        "metrics": metrics,
        "route_pre": pre_route,
        "route_post": post_route,
        "route_best_delay_shift_ms": post_route["best_delay_ms"] - pre_route["best_delay_ms"],
        "route_peak_score_delta": post_route["best_score_squared"] - pre_route["best_score_squared"],
        "route_peak_ratio_delta": None if pre_route["peak_ratio"] is None or post_route["peak_ratio"] is None
                                  else post_route["peak_ratio"] - pre_route["peak_ratio"],
        "ground_truth": truth or {},
    }


def summarize(records: list[dict]) -> dict:
    cohorts = sorted({record["cohort"] for record in records})
    out: dict[str, dict] = {}
    for cohort in cohorts:
        rows = [record for record in records if record["cohort"] == cohort]
        out[cohort] = {
            "events": len(rows),
            "post_double_talk_fraction_median": median([row["metrics"]["post_double_talk_fraction"] for row in rows]),
            "post_aec_converged_fraction_median": median([row["metrics"]["post_aec_converged_fraction"] for row in rows]),
            "post_delay_error_abs_p95_samples_median": median([
                row["metrics"]["post_delay_error_abs_p95_samples"] for row in rows
            ]),
            "estimated_delay_shift_ms_abs_median": median([
                abs(row["metrics"]["estimated_delay_shift_ms"])
                if row["metrics"]["estimated_delay_shift_ms"] is not None else None for row in rows
            ]),
            "route_best_delay_shift_ms_abs_median": median([
                abs(row["route_best_delay_shift_ms"]) for row in rows
            ]),
            "route_peak_score_pre_median": median([row["route_pre"]["best_score_squared"] for row in rows]),
            "route_peak_score_post_median": median([row["route_post"]["best_score_squared"] for row in rows]),
            "route_peak_ratio_pre_median": median([row["route_pre"]["peak_ratio"] for row in rows]),
            "route_peak_ratio_post_median": median([row["route_post"]["peak_ratio"] for row in rows]),
            "reflection_delay_drift_max_samples_median": median([
                row["ground_truth"].get("reflection_delay_drift_max_samples") for row in rows
            ]),
        }
    return out


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "doubletalk-origin-disambiguation-v1", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic-only status")
    require(manifest.get("candidate_budget") == 0, "candidate budget must remain zero")
    authority = manifest.get("output_authority") or {}
    require(authority.get("research_diagnostic_only") is True, "research diagnostic authority")
    require(all(authority.get(key) is False for key in (
        "candidate_selection", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion authority must be false")
    require(manifest["development_inputs"]["deterministic_validation_seeds"] == [1307, 1407],
            "validation seed drift")
    require(manifest["development_inputs"]["motion_geometry_v2_seeds"] == [4107, 4207],
            "motion seed drift")
    require(manifest["observable_evidence"]["input_domain_route_probe"]["selection_threshold"] is None,
            "route probe must not contain selection threshold")


def self_test() -> None:
    rate = 16000
    frame = 160
    state = 1
    render: list[int] = []
    for _ in range(rate * 2):
        state = (1664525 * state + 1013904223) & 0xffffffff
        render.append((((state >> 16) & 0xffff) - 32768) // 2)
    delay_a = 320
    delay_b = 640
    mic_a = [0] * delay_a + render[:-delay_a]
    mic_b = [0] * delay_b + render[:-delay_b]
    cfg = {
        "max_delay_ms": 100,
        "coarse_step_samples": 32,
        "sample_stride": 8,
        "runner_guard_samples": 64,
    }
    a = route_snapshot(mic_a, render, rate, frame, 20, 120, cfg)
    b = route_snapshot(mic_b, render, rate, frame, 20, 120, cfg)
    assert abs(a["best_delay_samples"] - delay_a) <= 1
    assert abs(b["best_delay_samples"] - delay_b) <= 1
    assert a["best_score_squared"] > 0.99 and b["best_score_squared"] > 0.99
    assert rising_edges([0, 0, 1, 1, 0, 1, 0]) == [2, 5]
    print(json.dumps({"result": "PASS", "candidate_budget": 0, "diagnostic_only": True}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--validation-corpus", action="append", type=Path, default=[])
    parser.add_argument("--motion-corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.processor and args.manifest and args.output, "processor/manifest/output required")
    require(args.processor.is_file(), "processor missing")
    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    require(len(args.validation_corpus) == 2 and len(args.motion_corpus) == 2,
            "exactly two validation and two motion corpora required")
    require(not args.output.exists() or (args.output.is_dir() and not any(args.output.iterdir())),
            "output must be absent or empty")
    args.output.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    observed_validation_seeds: list[int] = []
    observed_motion_seeds: list[int] = []

    for corpus_path in args.validation_corpus:
        corpus = load_json(corpus_path)
        root = corpus_path.parent
        corpus_id = str(corpus["corpus_id"])
        seed = int(corpus["generator"]["seed"])
        observed_validation_seeds.append(seed)
        for case in corpus["cases"]:
            scenario = case["scenario"]
            if scenario not in {"aec-doubletalk", "aec-doubletalk-balance", "aec-echo-path-change"}:
                continue
            rows, mic, render = run_processor(args.processor, root, corpus_id, case, args.output)
            if scenario in {"aec-doubletalk", "aec-doubletalk-balance"}:
                require(case.get("vad_labels"), f"near labels required: {case['case_id']}")
                labels = read_labels(root / case["vad_labels"])
                for event in rising_edges(labels):
                    if event >= 12 and event + 12 < len(rows):
                        records.append(event_record("near_end_onset", corpus_id, case,
                                                    event, rows, mic, render, manifest))
            else:
                event = int(case["control"]["echo_path_change_frame"])
                require(event >= 12 and event + 12 < len(rows), "path-change event support")
                records.append(event_record("echo_path_change", corpus_id, case,
                                            event, rows, mic, render, manifest))

    for corpus_path in args.motion_corpus:
        corpus = load_json(corpus_path)
        root = corpus_path.parent
        corpus_id = str(corpus["corpus_id"])
        seed = int(corpus["generator"]["seed"])
        observed_motion_seeds.append(seed)
        for case in corpus["cases"]:
            if case["scenario"] != "aec-continuous-motion":
                continue
            rows, mic, render = run_processor(args.processor, root, corpus_id, case, args.output)
            event = len(rows) // 2
            require(event >= 12 and event + 12 < len(rows), "motion checkpoint support")
            truth = motion_truth(root, case, event)
            cohort = "stationary_far_control" if truth.get("motion") == "stationary" else "continuous_motion"
            records.append(event_record(cohort, corpus_id, case, event,
                                        rows, mic, render, manifest, truth))

    require(sorted(observed_validation_seeds) == manifest["development_inputs"]["deterministic_validation_seeds"],
            "validation corpus seed mismatch")
    require(sorted(observed_motion_seeds) == manifest["development_inputs"]["motion_geometry_v2_seeds"],
            "motion corpus seed mismatch")
    require(records, "no diagnostic records")
    cohort_counts = {name: sum(record["cohort"] == name for record in records)
                     for name in ("near_end_onset", "echo_path_change", "continuous_motion", "stationary_far_control")}
    require(all(value > 0 for value in cohort_counts.values()), "missing diagnostic cohort")

    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "selection_performed": False,
        "cohort_counts": cohort_counts,
        "cohort_summary": summarize(records),
        "records": records,
        "interpretation_rule": manifest["interpretation_rule"],
    }
    write_json(args.output / "result.json", payload)
    print(json.dumps({
        "output": str(args.output / "result.json"),
        "candidate_budget": 0,
        "records": len(records),
        "cohort_counts": cohort_counts,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
