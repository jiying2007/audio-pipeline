#!/usr/bin/env python3
"""Evaluate exact-C beamformer behavior on deterministic hard microphone faults."""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

QUALITY_ONSET_MARGIN_FRAMES = 40
QUALITY_END_MARGIN_FRAMES = 20
POST_RECOVERY_MARGIN_FRAMES = 60
STABLE_RECOVERY_FRAMES = 40
ALIGNMENT_RADIUS_SAMPLES = 8


def read_pcm(path: Path) -> list[int]:
    raw = path.read_bytes()
    if len(raw) % 2:
        raise ValueError(f"odd PCM byte count: {path}")
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def corr_for_lag(reference: Sequence[int], estimate: Sequence[int], lag: int,
                 start: int, end: int, stride: int = 2) -> float:
    # lag > 0 means estimate is delayed relative to reference.
    ref_start = start
    est_start = start + lag
    if est_start < 0:
        ref_start -= est_start
        est_start = 0
    ref_end = min(end, len(reference), len(estimate) - lag if lag >= 0 else len(reference))
    count = min(ref_end - ref_start, len(estimate) - est_start)
    if count <= 16:
        return -1.0
    xy = xx = yy = 0.0
    for offset in range(0, count, stride):
        x = float(reference[ref_start + offset])
        y = float(estimate[est_start + offset])
        xy += x * y
        xx += x * x
        yy += y * y
    if xx <= 1.0e-12 or yy <= 1.0e-12:
        return -1.0
    return xy / math.sqrt(xx * yy)


def estimate_lag(reference: Sequence[int], estimate: Sequence[int],
                 start: int, end: int) -> int:
    best_lag = 0
    best_corr = -2.0
    for lag in range(-ALIGNMENT_RADIUS_SAMPLES, ALIGNMENT_RADIUS_SAMPLES + 1):
        corr = corr_for_lag(reference, estimate, lag, start, end)
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_lag


def aligned_window(reference: Sequence[int], estimate: Sequence[int], lag: int,
                   start: int, end: int) -> tuple[list[int], list[int]]:
    ref_start = start
    est_start = start + lag
    if est_start < 0:
        ref_start -= est_start
        est_start = 0
    count = min(end - ref_start, len(reference) - ref_start, len(estimate) - est_start)
    if count <= 0:
        return [], []
    return list(reference[ref_start:ref_start + count]), list(estimate[est_start:est_start + count])


def si_sdr_db(reference: Sequence[int], estimate: Sequence[int]) -> float | None:
    count = min(len(reference), len(estimate))
    if count < 16:
        return None
    ref = [float(value) for value in reference[:count]]
    est = [float(value) for value in estimate[:count]]
    ref_energy = sum(value * value for value in ref)
    if ref_energy <= 1.0e-12:
        return None
    scale = sum(r * e for r, e in zip(ref, est)) / ref_energy
    target_energy = sum((scale * r) ** 2 for r in ref)
    error_energy = sum((e - scale * r) ** 2 for r, e in zip(ref, est))
    return 10.0 * math.log10((target_energy + 1.0e-12) / (error_energy + 1.0e-12))


def aligned_si_sdr(reference: Sequence[int], estimate: Sequence[int], lag: int,
                   start: int, end: int) -> float | None:
    ref, est = aligned_window(reference, estimate, lag, start, end)
    return si_sdr_db(ref, est)


def rms_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return -120.0
    energy = sum(float(value) * float(value) for value in samples) / len(samples)
    if energy <= 1.0e-18:
        return -120.0
    return 10.0 * math.log10(energy / (32768.0 * 32768.0))


def dc_offset_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return -120.0
    mean = abs(sum(float(value) for value in samples) / len(samples))
    if mean <= 1.0e-12:
        return -120.0
    return 20.0 * math.log10(mean / 32768.0)


def clip_fraction(samples: Sequence[int], threshold: int = 32760) -> float:
    if not samples:
        return 0.0
    return sum(1 for value in samples if abs(int(value)) >= threshold) / len(samples)


def load_trace(path: Path) -> list[dict]:
    trace: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            trace.append(json.loads(line))
    return trace


def first_entry_latency(trace: list[dict], start: int, end: int) -> int | None:
    for row in trace[start:end]:
        if int(row.get("fallback_active", 0)):
            return int(row["frame"]) - start
    return None


def stable_recovery_latency(trace: list[dict], start: int) -> int | None:
    active = [bool(int(row.get("fallback_active", 0))) for row in trace]
    if start >= len(active):
        return None
    for frame in range(start, max(start, len(active) - STABLE_RECOVERY_FRAMES + 1)):
        if not any(active[frame:frame + STABLE_RECOVERY_FRAMES]):
            return frame - start
    return None


def transition_count(trace: list[dict], start: int, end: int) -> int:
    count = 0
    previous = bool(int(trace[start - 1].get("fallback_active", 0))) if start > 0 else False
    for row in trace[start:end]:
        current = bool(int(row.get("fallback_active", 0)))
        if current and not previous:
            count += 1
        previous = current
    return count


def active_fraction(trace: list[dict], start: int, end: int) -> float:
    rows = trace[start:end]
    if not rows:
        return 0.0
    return sum(1 for row in rows if int(row.get("fallback_active", 0))) / len(rows)


def reliable_selected_fraction(trace: list[dict], start: int, end: int,
                               reliable_channel: int) -> float | None:
    active_rows = [row for row in trace[start:end] if int(row.get("fallback_active", 0))]
    if not active_rows:
        return None
    selected = sum(
        1 for row in active_rows
        if int(row.get("fallback_strong_channel", 0)) == reliable_channel
    )
    return selected / len(active_rows)


def energy_dominance_fraction(interleaved: Sequence[int], frame_samples: int,
                              start: int, end: int, faulty_channel: int) -> float:
    frames = 0
    faulty_dominant = 0
    for frame in range(start, end):
        base = frame * frame_samples * 2
        energy = [0.0, 0.0]
        for offset in range(frame_samples):
            energy[0] += float(interleaved[base + 2 * offset]) ** 2
            energy[1] += float(interleaved[base + 2 * offset + 1]) ** 2
        frames += 1
        if energy[faulty_channel] > energy[1 - faulty_channel]:
            faulty_dominant += 1
    return faulty_dominant / frames if frames else 0.0


def metric_window(samples: Sequence[int], frame_samples: int,
                  start_frame: int, end_frame: int) -> list[int]:
    return list(samples[start_frame * frame_samples:end_frame * frame_samples])


def evaluate_case(probe: Path, corpus_path: Path, case: dict, work_root: Path) -> dict:
    case_id = str(case["case_id"])
    rate = int(case["sample_rate_hz"])
    frame_samples = int(case["frame_samples"])
    frames = int(case["frames"])
    fault_start = int(case["fault_start_frame"])
    fault_end = int(case["fault_end_frame"])
    reliable_channel = int(case["reliable_channel"])
    faulty_channel = case.get("faulty_channel")
    mic_path = corpus_path.parent / str(case["mic_audio"])
    clean_path = corpus_path.parent / str(case["clean_audio"])
    reliable_path = corpus_path.parent / str(case["reliable_audio"])
    case_work = work_root / case_id
    case_work.mkdir(parents=True, exist_ok=True)
    output_path = case_work / "out.pcm"
    trace_path = case_work / "trace.jsonl"

    subprocess.run([
        str(probe), "--sample-rate", str(rate), "--spacing-mm", "50",
        str(mic_path), str(output_path), str(trace_path),
    ], check=True)

    mic = read_pcm(mic_path)
    clean = read_pcm(clean_path)
    reliable = read_pcm(reliable_path)
    output = read_pcm(output_path)
    trace = load_trace(trace_path)
    if len(trace) != frames:
        raise ValueError(f"trace frame mismatch {case_id}: {len(trace)} != {frames}")
    if len(output) != frames * frame_samples:
        raise ValueError(f"output sample mismatch {case_id}")

    pre_start = 50
    pre_end = max(pre_start + 1, fault_start - QUALITY_END_MARGIN_FRAMES)
    fault_quality_start = min(fault_end - 1, fault_start + QUALITY_ONSET_MARGIN_FRAMES)
    fault_quality_end = max(fault_quality_start + 1, fault_end - QUALITY_END_MARGIN_FRAMES)
    post_start = min(frames - 1, fault_end + POST_RECOVERY_MARGIN_FRAMES)
    post_end = max(post_start + 1, frames - QUALITY_END_MARGIN_FRAMES)
    pre_start_sample = pre_start * frame_samples
    pre_end_sample = pre_end * frame_samples

    output_lag = estimate_lag(clean, output, pre_start_sample, pre_end_sample)
    reliable_lag = estimate_lag(clean, reliable, pre_start_sample, pre_end_sample)

    def score(signal: Sequence[int], lag: int, start_frame: int, end_frame: int) -> float | None:
        return aligned_si_sdr(
            clean, signal, lag,
            start_frame * frame_samples,
            end_frame * frame_samples,
        )

    pre_current = score(output, output_lag, pre_start, pre_end)
    pre_reliable = score(reliable, reliable_lag, pre_start, pre_end)
    fault_current = score(output, output_lag, fault_quality_start, fault_quality_end)
    fault_reliable = score(reliable, reliable_lag, fault_quality_start, fault_quality_end)
    post_current = score(output, output_lag, post_start, post_end)
    post_reliable = score(reliable, reliable_lag, post_start, post_end)
    fault_output = metric_window(output, frame_samples, fault_quality_start, fault_quality_end)

    fault_delta = None
    if fault_current is not None and fault_reliable is not None:
        fault_delta = fault_current - fault_reliable
    post_delta = None
    if post_current is not None and post_reliable is not None:
        post_delta = post_current - post_reliable

    dynamics = {
        "pre_fallback_active_fraction": active_fraction(trace, 0, fault_start),
        "fault_fallback_active_fraction": active_fraction(trace, fault_start, fault_end),
        "fallback_entry_latency_frames": first_entry_latency(trace, fault_start, fault_end),
        "fault_fallback_entries": transition_count(trace, fault_start, fault_end),
        "stable_recovery_latency_frames": stable_recovery_latency(trace, fault_end),
        "reliable_selected_fraction_when_fallback": reliable_selected_fraction(
            trace, fault_start, fault_end, reliable_channel
        ),
    }
    if faulty_channel is not None:
        dynamics["faulty_channel_energy_dominant_fraction"] = energy_dominance_fraction(
            mic, frame_samples, fault_start, fault_end, int(faulty_channel)
        )
    else:
        dynamics["faulty_channel_energy_dominant_fraction"] = None

    return {
        "case_id": case_id,
        "fault_type": case["fault_type"],
        "faulty_channel": faulty_channel,
        "reliable_channel": reliable_channel,
        "alignment": {
            "output_lag_samples": output_lag,
            "reliable_lag_samples": reliable_lag,
        },
        "quality": {
            "pre_current_si_sdr_db": pre_current,
            "pre_reliable_si_sdr_db": pre_reliable,
            "fault_current_si_sdr_db": fault_current,
            "fault_reliable_si_sdr_db": fault_reliable,
            "fault_current_minus_reliable_db": fault_delta,
            "fault_output_rms_dbfs": rms_dbfs(fault_output),
            "fault_output_dc_offset_dbfs": dc_offset_dbfs(fault_output),
            "fault_output_clip_fraction": clip_fraction(fault_output),
            "post_current_si_sdr_db": post_current,
            "post_reliable_si_sdr_db": post_reliable,
            "post_current_minus_reliable_db": post_delta,
        },
        "dynamics": dynamics,
        "artifacts": {
            "output": str(output_path),
            "trace": str(trace_path),
        },
    }


def evaluate(probe: Path, corpus_path: Path, output_path: Path) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    if corpus.get("authority") != "diagnostic-regression-only":
        raise ValueError("hard-fault corpus must remain diagnostic-regression-only")
    with tempfile.TemporaryDirectory(prefix="ap-bf-hard-fault-eval-") as temporary:
        work = Path(temporary)
        cases = [evaluate_case(probe, corpus_path, case, work) for case in corpus["cases"]]

    control = next((case for case in cases if case["fault_type"] == "control"), None)
    structural_violations: list[dict] = []
    if control is None:
        structural_violations.append({"gate": "control_present"})
    else:
        control_delta = control["quality"]["fault_current_minus_reliable_db"]
        if control_delta is None or float(control_delta) < -1.5:
            structural_violations.append({
                "gate": "control_beamformer_sanity",
                "actual_db": control_delta,
                "expected_min_db": -1.5,
            })
        if control["dynamics"]["pre_fallback_active_fraction"] > 0.05:
            structural_violations.append({
                "gate": "control_false_fallback_fraction",
                "actual": control["dynamics"]["pre_fallback_active_fraction"],
                "expected_max": 0.05,
            })

    result = {
        "schema_version": 1,
        "authority": "diagnostic-regression-only",
        "corpus_id": corpus["corpus_id"],
        "probe": "bf_hard_fault_probe exact src/frontend/ap_beamformer.c",
        "cases": cases,
        "structural_violations": structural_violations,
        "validation_result": "PASS" if not structural_violations else "FAIL",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    reference = [int(9000 * math.sin(math.tau * 0.017 * index)) for index in range(4000)]
    delayed = [0, 0] + reference[:-2]
    lag = estimate_lag(reference, delayed, 100, 3000)
    assert lag == 2, lag
    score = aligned_si_sdr(reference, delayed, lag, 100, 3000)
    assert score is not None and score > 100.0
    assert rms_dbfs([0] * 100) == -120.0
    assert clip_fraction([32767, 0, -32768, 4]) == 0.5
    fake_trace = [
        {"frame": index, "fallback_active": 1 if 10 <= index < 20 else 0,
         "fallback_strong_channel": 0}
        for index in range(80)
    ]
    assert first_entry_latency(fake_trace, 8, 30) == 2
    assert transition_count(fake_trace, 8, 30) == 1
    assert stable_recovery_latency(fake_trace, 20) == 0
    print("BF hard-fault evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.probe is None or args.corpus is None or args.output is None:
        parser.error("--probe, --corpus and --output are required")
    result = evaluate(args.probe, args.corpus, args.output)
    for case in result["cases"]:
        quality = case["quality"]
        dynamics = case["dynamics"]
        print(
            f"{case['case_id']}: delta_vs_reliable={quality['fault_current_minus_reliable_db']} dB "
            f"fallback={dynamics['fault_fallback_active_fraction']:.3f} "
            f"entry={dynamics['fallback_entry_latency_frames']}f "
            f"reliable_selected={dynamics['reliable_selected_fraction_when_fallback']} "
            f"recovery={dynamics['stable_recovery_latency_frames']}f"
        )
    for violation in result["structural_violations"]:
        print(f"STRUCTURAL FAIL: {json.dumps(violation, sort_keys=True)}")
    return 1 if result["structural_violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
