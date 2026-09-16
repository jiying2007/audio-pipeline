#!/usr/bin/env python3
"""Candidate-zero temporal route diagnostic for double-talk origin disambiguation.

This research-only probe keeps the shipping processor unchanged. It publishes
multi-window input-domain route trajectories plus already-public processor
metrics. It does not derive a detector threshold, select a candidate, or tune
shipping DSP.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import statistics
import subprocess
import wave
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


def read_wav_pcm16_mono(path: Path) -> tuple[int, list[int]]:
    with wave.open(str(path), "rb") as wav:
        require(wav.getnchannels() == 1, f"mono WAV required: {path}")
        require(wav.getsampwidth() == 2, f"PCM16 WAV required: {path}")
        rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    values = array.array("h")
    values.frombytes(frames)
    if os.sys.byteorder != "little":
        values.byteswap()
    return rate, list(values)


def read_labels(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def median(values: list[float | int | None]) -> float | None:
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return statistics.median(clean) if clean else None


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


def fraction(rows: list[dict], key: str) -> float | None:
    if not rows:
        return None
    return sum(int(row[key]) != 0 for row in rows) / len(rows)


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


def route_snapshot_samples(mic: list[int], render: list[int], rate: int,
                           start: int, end: int, cfg: dict) -> dict:
    start = max(0, start)
    end = min(len(mic), len(render), end)
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
        "start_sample": start,
        "end_sample": end,
        "best_delay_samples": best_delay,
        "best_delay_ms": 1000.0 * best_delay / rate,
        "best_score_squared": best_score,
        "runner_up_score_squared": runner,
        "peak_ratio": ratio,
    }


def window_metrics(rows: list[dict], start_frame: int, end_frame: int) -> dict:
    part = rows[max(0, start_frame):min(len(rows), end_frame)]
    require(part, "empty metrics window")
    return {
        "frames": len(part),
        "double_talk_fraction": fraction(part, "double_talk_active"),
        "far_end_fraction": fraction(part, "far_end_active"),
        "aec_converged_fraction": fraction(part, "aec_converged"),
        "estimated_delay_ms_median": median([row["estimated_delay_ms"] for row in part]),
        "delay_error_abs_p95_samples": percentile(
            [abs(float(row["delay_error_samples"])) for row in part], 0.95
        ),
    }


def trajectory_shape(windows: list[dict]) -> dict:
    require(len(windows) >= 2, "trajectory requires multiple windows")
    lags = [float(w["best_delay_ms"]) for w in windows]
    scores = [float(w["best_score_squared"]) for w in windows]
    ratios = [w["peak_ratio"] for w in windows]
    lag_steps = [abs(lags[i] - lags[i - 1]) for i in range(1, len(lags))]
    score_steps = [abs(scores[i] - scores[i - 1]) for i in range(1, len(scores))]
    return {
        "lag_range_ms": max(lags) - min(lags),
        "lag_total_variation_ms": sum(lag_steps),
        "lag_step_abs_median_ms": median(lag_steps),
        "lag_step_abs_p95_ms": percentile(lag_steps, 0.95),
        "peak_score_median": median(scores),
        "peak_score_min": min(scores),
        "peak_score_max": max(scores),
        "peak_score_total_variation": sum(score_steps),
        "peak_ratio_median": median(ratios),
    }


def event_trajectory(rows: list[dict], mic: list[int], render: list[int], rate: int,
                     event: int, cfg: dict) -> dict:
    frame_samples = rate // 100
    window_frames = int(cfg["window_frames"])
    centers = [int(value) for value in cfg["relative_center_frames"]]
    require(window_frames > 0 and window_frames % 2 == 0, "even window_frames required")
    require(centers == sorted(centers) and 0 in centers, "ordered centers including zero required")
    half = window_frames // 2
    windows: list[dict] = []
    for relative_center in centers:
        center = event + relative_center
        start_frame = center - half
        end_frame = center + half
        require(start_frame >= 0 and end_frame <= len(rows), "event trajectory lacks support")
        route = route_snapshot_samples(
            mic, render, rate, start_frame * frame_samples, end_frame * frame_samples, cfg
        )
        windows.append({
            "relative_center_frame": relative_center,
            "start_frame": start_frame,
            "end_frame": end_frame,
            **{key: route[key] for key in (
                "best_delay_samples", "best_delay_ms", "best_score_squared",
                "runner_up_score_squared", "peak_ratio"
            )},
            "metrics": window_metrics(rows, start_frame, end_frame),
        })

    pre = [w for w in windows if int(w["relative_center_frame"]) < 0]
    post = [w for w in windows if int(w["relative_center_frame"]) > 0]
    require(pre and post, "trajectory requires pre/post windows")
    pre_near = pre[-1]
    post_near = post[0]
    shape = trajectory_shape(windows)
    shape.update({
        "event_lag_step_ms": float(post_near["best_delay_ms"]) - float(pre_near["best_delay_ms"]),
        "event_lag_step_abs_ms": abs(float(post_near["best_delay_ms"]) - float(pre_near["best_delay_ms"])),
        "event_peak_score_delta": float(post_near["best_score_squared"]) - float(pre_near["best_score_squared"]),
        "pre_peak_score_median": median([w["best_score_squared"] for w in pre]),
        "post_peak_score_median": median([w["best_score_squared"] for w in post]),
        "pre_best_delay_ms_median": median([w["best_delay_ms"] for w in pre]),
        "post_best_delay_ms_median": median([w["best_delay_ms"] for w in post]),
    })
    return {"event_frame": event, "windows": windows, "shape": shape}


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
        str(processor), "--sample-rate", str(case["sample_rate_hz"]),
        "--mic-channels", "1", "--metrics-jsonl", str(metrics_path),
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
    require(all(int(row["frame"]) == i for i, row in enumerate(rows)),
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


def summarize_synthetic(records: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for cohort in sorted({row["cohort"] for row in records}):
        group = [row for row in records if row["cohort"] == cohort]
        shapes = [row["trajectory"]["shape"] for row in group]
        out[cohort] = {
            "events": len(group),
            "event_lag_step_abs_ms_median": median([s["event_lag_step_abs_ms"] for s in shapes]),
            "event_peak_score_delta_median": median([s["event_peak_score_delta"] for s in shapes]),
            "lag_range_ms_median": median([s["lag_range_ms"] for s in shapes]),
            "lag_total_variation_ms_median": median([s["lag_total_variation_ms"] for s in shapes]),
            "peak_score_total_variation_median": median([s["peak_score_total_variation"] for s in shapes]),
            "pre_peak_score_median": median([s["pre_peak_score_median"] for s in shapes]),
            "post_peak_score_median": median([s["post_peak_score_median"] for s in shapes]),
            "post_double_talk_fraction_near_median": median([
                next(w["metrics"]["double_talk_fraction"] for w in row["trajectory"]["windows"]
                     if int(w["relative_center_frame"]) > 0)
                for row in group
            ]),
            "reflection_delay_drift_max_samples_median": median([
                row["ground_truth"].get("reflection_delay_drift_max_samples") for row in group
            ]),
        }
    return out


def build_synthetic(processor: Path, manifest: dict, validation_corpora: list[Path],
                    motion_corpora: list[Path], output: Path) -> dict:
    cfg = manifest["synthetic_temporal_probe"]
    records: list[dict] = []
    validation_seeds: list[int] = []
    motion_seeds: list[int] = []
    support = max(abs(int(v)) for v in cfg["relative_center_frames"]) + int(cfg["window_frames"]) // 2

    for corpus_path in validation_corpora:
        corpus = load_json(corpus_path)
        root = corpus_path.parent
        corpus_id = str(corpus["corpus_id"])
        validation_seeds.append(int(corpus["generator"]["seed"]))
        for case in corpus["cases"]:
            scenario = case["scenario"]
            if scenario not in {"aec-doubletalk", "aec-doubletalk-balance", "aec-echo-path-change"}:
                continue
            rows, mic, render = run_processor(processor, root, corpus_id, case, output)
            events: list[tuple[int, str]] = []
            if scenario in {"aec-doubletalk", "aec-doubletalk-balance"}:
                require(case.get("vad_labels"), f"near labels required: {case['case_id']}")
                events = [(event, "near_end_onset") for event in rising_edges(read_labels(root / case["vad_labels"]))]
            else:
                events = [(int(case["control"]["echo_path_change_frame"]), "echo_path_change")]
            for event, cohort in events:
                if event < support or event + support > len(rows):
                    continue
                records.append({
                    "cohort": cohort, "corpus": corpus_id, "case_id": case["case_id"],
                    "scenario": scenario, "event_frame": event,
                    "trajectory": event_trajectory(rows, mic, render, int(case["sample_rate_hz"]), event, cfg),
                    "ground_truth": {},
                })

    for corpus_path in motion_corpora:
        corpus = load_json(corpus_path)
        root = corpus_path.parent
        corpus_id = str(corpus["corpus_id"])
        motion_seeds.append(int(corpus["generator"]["seed"]))
        for case in corpus["cases"]:
            if case["scenario"] != "aec-continuous-motion":
                continue
            rows, mic, render = run_processor(processor, root, corpus_id, case, output)
            event = len(rows) // 2
            require(event >= support and event + support <= len(rows), "motion checkpoint support")
            truth = motion_truth(root, case, event)
            cohort = "stationary_far_control" if truth.get("motion") == "stationary" else "continuous_motion"
            records.append({
                "cohort": cohort, "corpus": corpus_id, "case_id": case["case_id"],
                "scenario": case["scenario"], "event_frame": event,
                "trajectory": event_trajectory(rows, mic, render, int(case["sample_rate_hz"]), event, cfg),
                "ground_truth": truth,
            })

    require(sorted(validation_seeds) == manifest["development_inputs"]["deterministic_validation_seeds"],
            "validation seed mismatch")
    require(sorted(motion_seeds) == manifest["development_inputs"]["motion_geometry_v2_seeds"],
            "motion seed mismatch")
    counts = {name: sum(row["cohort"] == name for row in records) for name in (
        "near_end_onset", "echo_path_change", "continuous_motion", "stationary_far_control"
    )}
    require(all(v > 0 for v in counts.values()), "missing synthetic cohort")
    return {"cohort_counts": counts, "summary": summarize_synthetic(records), "records": records}


def real_case_trajectory(mic: list[int], render: list[int], rate: int, cfg: dict) -> dict:
    window_frames = int(round(float(cfg["window_seconds"]) * 100.0))
    hop_frames = int(round(float(cfg["hop_seconds"]) * 100.0))
    frame_samples = rate // 100
    require(window_frames > 0 and hop_frames > 0, "real window geometry")
    usable_frames = min(len(mic), len(render)) // frame_samples
    starts = list(range(0, max(0, usable_frames - window_frames + 1), hop_frames))
    starts = starts[:int(cfg["max_windows"])]
    require(len(starts) >= 2, "real trajectory requires multiple windows")
    windows: list[dict] = []
    for index, start_frame in enumerate(starts):
        end_frame = start_frame + window_frames
        route = route_snapshot_samples(
            mic, render, rate, start_frame * frame_samples, end_frame * frame_samples, cfg
        )
        windows.append({
            "index": index, "start_seconds": start_frame / 100.0, "end_seconds": end_frame / 100.0,
            **{key: route[key] for key in (
                "best_delay_samples", "best_delay_ms", "best_score_squared",
                "runner_up_score_squared", "peak_ratio"
            )},
        })
    return {"windows": windows, "shape": trajectory_shape(windows)}


def build_real(manifest: dict, lock_path: Path, root: Path) -> dict:
    lock = load_json(lock_path)
    cfg = manifest["real_temporal_crosscheck"]
    require(lock["source_revision"] == cfg["source_revision"], "real source revision drift")
    require(len(lock["cases"]) == 4, "expected four real AEC cases")
    cases: list[dict] = []
    for case in lock["cases"]:
        resolved: dict[str, Path] = {}
        for role in ("mic", "render"):
            meta = case[role]
            path = root / meta["path"]
            require(path.stat().st_size == int(meta["size"]), f"real size mismatch: {case['id']} {role}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(digest == meta["sha256"], f"real sha mismatch: {case['id']} {role}")
            resolved[role] = path
        mic_rate, mic = read_wav_pcm16_mono(resolved["mic"])
        render_rate, render = read_wav_pcm16_mono(resolved["render"])
        require(mic_rate == render_rate, f"sample-rate mismatch: {case['id']}")
        cases.append({
            "case_id": case["id"], "scenario": case["scenario"], "movement": bool(case["movement"]),
            "sample_rate_hz": mic_rate,
            "trajectory": real_case_trajectory(mic, render, mic_rate, cfg),
        })
    require(sum(row["movement"] for row in cases) == 2, "real movement count")
    groups = {"static": [row for row in cases if not row["movement"]],
              "movement": [row for row in cases if row["movement"]]}
    summary: dict[str, dict] = {}
    for name, group in groups.items():
        shapes = [row["trajectory"]["shape"] for row in group]
        summary[name] = {
            "cases": len(group),
            "lag_range_ms_median": median([s["lag_range_ms"] for s in shapes]),
            "lag_total_variation_ms_median": median([s["lag_total_variation_ms"] for s in shapes]),
            "lag_step_abs_median_ms_median": median([s["lag_step_abs_median_ms"] for s in shapes]),
            "lag_step_abs_p95_ms_median": median([s["lag_step_abs_p95_ms"] for s in shapes]),
            "peak_score_median_median": median([s["peak_score_median"] for s in shapes]),
            "peak_score_total_variation_median": median([s["peak_score_total_variation"] for s in shapes]),
            "peak_ratio_median_median": median([s["peak_ratio_median"] for s in shapes]),
        }
    return {"dataset_lock": str(lock_path), "source_revision": lock["source_revision"],
            "summary": summary, "cases": cases}


def validate_manifest(manifest: dict) -> None:
    require(manifest.get("schema_version") == 1, "manifest schema")
    require(manifest.get("investigation_id") == "doubletalk-temporal-route-disambiguation-v2", "manifest identity")
    require(manifest.get("status") == "DIAGNOSTIC_ONLY", "diagnostic status")
    require(manifest.get("candidate_budget") == 0, "candidate budget must remain zero")
    require(manifest["predecessor"]["investigation_id"] == "doubletalk-origin-disambiguation-v1", "predecessor")
    require(manifest["predecessor"]["fresh_main_sha"] == "7654979fd2664954ba6780e5d69caa1029cf1d8f", "predecessor SHA")
    require(manifest["synthetic_temporal_probe"]["selection_threshold"] is None, "synthetic threshold forbidden")
    require(manifest["real_temporal_crosscheck"]["selection_threshold"] is None, "real threshold forbidden")
    authority = manifest["output_authority"]
    require(authority["research_diagnostic_only"] is True, "research authority")
    require(all(authority[key] is False for key in (
        "candidate_selection", "tuning", "automatic_main_mutation", "shipping", "hil", "product_certification"
    )), "promotion/tuning authority must be false")


def self_test() -> None:
    rate = 16000
    frame = rate // 100
    n = rate * 4
    state = 1
    render: list[int] = []
    noise: list[int] = []
    for _ in range(n):
        state = (1664525 * state + 1013904223) & 0xffffffff
        render.append((((state >> 16) & 0xffff) - 32768) // 3)
        state = (1664525 * state + 1013904223) & 0xffffffff
        noise.append((((state >> 16) & 0xffff) - 32768) // 2)
    event = 200
    event_sample = event * frame
    delay_a = 320
    delay_b = 480
    stable = [0 if i < delay_a else render[i - delay_a] for i in range(n)]
    near = stable[:]
    for i in range(event_sample, n):
        near[i] = max(-32768, min(32767, stable[i] + noise[i]))
    path = stable[:]
    for i in range(event_sample, n):
        path[i] = 0 if i < delay_b else render[i - delay_b]
    rows = [{
        "frame": i, "double_talk_active": 0, "far_end_active": 1, "aec_converged": 1,
        "estimated_delay_ms": 20.0, "delay_error_samples": 0.0,
    } for i in range(n // frame)]
    cfg = {
        "window_frames": 8,
        "relative_center_frames": [-12, -8, -4, 0, 4, 8, 12],
        "max_delay_ms": 100,
        "coarse_step_samples": 32,
        "sample_stride": 8,
        "runner_guard_samples": 64,
    }
    near_t = event_trajectory(rows, near, render, rate, event, cfg)
    path_t = event_trajectory(rows, path, render, rate, event, cfg)
    near_pre = next(w for w in near_t["windows"] if w["relative_center_frame"] == -4)
    near_post = next(w for w in near_t["windows"] if w["relative_center_frame"] == 4)
    path_pre = next(w for w in path_t["windows"] if w["relative_center_frame"] == -4)
    path_post = next(w for w in path_t["windows"] if w["relative_center_frame"] == 4)
    assert abs(near_pre["best_delay_samples"] - delay_a) <= 1
    assert abs(near_post["best_delay_samples"] - delay_a) <= 1
    assert abs(path_pre["best_delay_samples"] - delay_a) <= 1
    assert abs(path_post["best_delay_samples"] - delay_b) <= 1
    assert near_post["best_score_squared"] < near_pre["best_score_squared"]
    assert rising_edges([0, 1, 1, 0, 1]) == [1, 4]
    print(json.dumps({"result": "PASS", "candidate_budget": 0, "diagnostic_only": True}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--validation-corpus", action="append", type=Path, default=[])
    parser.add_argument("--motion-corpus", action="append", type=Path, default=[])
    parser.add_argument("--real-lock", type=Path)
    parser.add_argument("--real-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.processor and args.manifest and args.real_lock and args.real_root and args.output,
            "processor/manifest/real-lock/real-root/output required")
    require(args.processor.is_file(), "processor missing")
    require(len(args.validation_corpus) == 2 and len(args.motion_corpus) == 2,
            "exactly two validation and two motion corpora required")
    manifest = load_json(args.manifest)
    validate_manifest(manifest)
    require(not args.output.exists() or (args.output.is_dir() and not any(args.output.iterdir())),
            "output must be absent or empty")
    args.output.mkdir(parents=True, exist_ok=True)

    synthetic = build_synthetic(args.processor, manifest, args.validation_corpus, args.motion_corpus, args.output)
    real = build_real(manifest, args.real_lock, args.real_root)
    payload = {
        "schema_version": 1,
        "investigation_id": manifest["investigation_id"],
        "status": "DIAGNOSTIC_ONLY",
        "authority": "research-diagnostic-only",
        "candidate_budget": 0,
        "selection_performed": False,
        "tuning_performed": False,
        "synthetic": synthetic,
        "real_unlabeled_crosscheck": real,
        "interpretation_rule": manifest["interpretation_rule"],
    }
    write_json(args.output / "temporal-route-result.json", payload)
    print(json.dumps({
        "output": str(args.output / "temporal-route-result.json"),
        "candidate_budget": 0,
        "synthetic_counts": synthetic["cohort_counts"],
        "real_cases": len(real["cases"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
