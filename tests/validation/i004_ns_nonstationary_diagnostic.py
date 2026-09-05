#!/usr/bin/env python3
"""I004 fixed-baseline diagnostic for nonstationary mechanical noise and low-SNR speech.

This tool is development/measurement authority only. It builds the exact current
shipping implementation, generates a frozen deterministic scenario matrix and
reports whether the existing NS baseline exposes a measurable gap. It does not
search parameters, rank candidates, alter ns_floor, or consume confirmation data.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import random
import shutil
import statistics
import subprocess
from pathlib import Path

RATE = 16000
FRAME = 160
SCENARIOS = [
    "ns-motor-ramp-speech", "ns-motor-ramp-noise",
    "ns-fan-am-speech", "ns-fan-am-noise",
    "ns-burst-start-stop-speech", "ns-burst-start-stop-noise",
    "ns-mixed-dynamic-low-snr-speech", "ns-mixed-dynamic-noise",
]


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def clamp16(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def write_pcm(path: Path, values: list[float]) -> None:
    data = array.array("h", [clamp16(v * 32767.0) for v in values])
    if __import__("sys").byteorder != "little":
        data.byteswap()
    path.write_bytes(data.tobytes())


def read_pcm(path: Path) -> list[float]:
    data = array.array("h")
    data.frombytes(path.read_bytes())
    if __import__("sys").byteorder != "little":
        data.byteswap()
    return [v / 32768.0 for v in data]


def rms(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values) / max(1, len(values)))


def db(value: float) -> float:
    return 20.0 * math.log10(max(value, 1.0e-12))


def scale_to_rms(values: list[float], target: float) -> list[float]:
    current = rms(values)
    require(current > 1.0e-9, "cannot normalize silence")
    factor = target / current
    return [v * factor for v in values]


def hash_noise(n: int, seed: int) -> float:
    x = (n + 0x9E3779B9 + seed * 0x85EBCA6B) & 0xFFFFFFFF
    x ^= x >> 16
    x = (x * 0x7FEB352D) & 0xFFFFFFFF
    x ^= x >> 15
    x = (x * 0x846CA68B) & 0xFFFFFFFF
    x ^= x >> 16
    return ((x >> 8) / 0xFFFFFF) * 2.0 - 1.0


def activity_envelope(t: float) -> float:
    segments = ((0.45, 1.55), (2.05, 3.05), (3.65, 5.45))
    for start, stop in segments:
        if start <= t < stop:
            edge = 0.08
            return min(1.0, (t - start) / edge, (stop - t) / edge)
    return 0.0


def speech_like(samples: int, seed: int) -> tuple[list[float], list[int]]:
    phase = [0.0, 0.0, 0.0]
    colored = 0.0
    out: list[float] = []
    labels: list[int] = []
    for n in range(samples):
        t = n / RATE
        env = activity_envelope(t)
        f0 = 118.0 + 16.0 * math.sin(2.0 * math.pi * 0.37 * t + (seed % 23) * 0.07)
        freqs = (f0, 2.03 * f0, 3.91 * f0)
        sample = 0.0
        for i, f in enumerate(freqs):
            phase[i] += 2.0 * math.pi * f / RATE
            sample += (0.55 / (i + 1)) * math.sin(phase[i])
        colored = 0.82 * colored + 0.18 * hash_noise(n, seed + 17)
        sample = env * (0.72 * sample + 0.18 * colored)
        out.append(sample)
        if n % FRAME == 0:
            labels.append(1 if activity_envelope((n + FRAME / 2) / RATE) > 0.5 else 0)
    return scale_to_rms(out, 0.10), labels


def motor_ramp(samples: int, seed: int) -> list[float]:
    phase = 0.0
    colored = 0.0
    out = []
    for n in range(samples):
        t = n / RATE
        sweep = 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.11 * t + (seed % 31) * 0.03)
        f = 72.0 + 168.0 * sweep
        phase += 2.0 * math.pi * f / RATE
        colored = 0.93 * colored + 0.07 * hash_noise(n, seed + 101)
        value = (0.70 * math.sin(phase) + 0.30 * math.sin(2.0 * phase + 0.4) +
                 0.18 * math.sin(3.0 * phase + 1.1) + 0.12 * colored)
        out.append(value)
    return scale_to_rms(out, 0.14)


def fan_am(samples: int, seed: int) -> list[float]:
    colored = 0.0
    phase = 0.0
    out = []
    for n in range(samples):
        t = n / RATE
        colored = 0.90 * colored + 0.10 * hash_noise(n, seed + 211)
        phase += 2.0 * math.pi * (145.0 + 8.0 * math.sin(2.0 * math.pi * 0.19 * t)) / RATE
        mod = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(2.0 * math.pi * 2.7 * t + 0.2))
        out.append(mod * (0.72 * colored + 0.34 * math.sin(phase) + 0.17 * math.sin(2.0 * phase)))
    return scale_to_rms(out, 0.14)


def burst_noise(samples: int, seed: int) -> list[float]:
    colored = 0.0
    out = []
    for n in range(samples):
        t = n / RATE
        colored = 0.78 * colored + 0.22 * hash_noise(n, seed + 307)
        cycle = t % 1.25
        gate = 1.0 if 0.16 <= cycle < 0.72 else 0.08
        edge = min(1.0, max(0.0, (cycle - 0.12) / 0.04), max(0.0, (0.78 - cycle) / 0.06))
        transient = math.exp(-max(0.0, cycle - 0.16) * 18.0) if cycle >= 0.16 else 0.0
        out.append(gate * edge * colored + 0.45 * transient * math.sin(2.0 * math.pi * 420.0 * t))
    return scale_to_rms(out, 0.14)


def mixed_noise(samples: int, seed: int) -> list[float]:
    a, b, c = motor_ramp(samples, seed), fan_am(samples, seed + 1), burst_noise(samples, seed + 2)
    return scale_to_rms([0.45 * x + 0.40 * y + 0.35 * z for x, y, z in zip(a, b, c)], 0.14)


def scenario_noise(name: str, samples: int, seed: int) -> list[float]:
    if "motor-ramp" in name:
        return motor_ramp(samples, seed)
    if "fan-am" in name:
        return fan_am(samples, seed)
    if "burst-start-stop" in name:
        return burst_noise(samples, seed)
    return mixed_noise(samples, seed)


def mix_at_snr(clean: list[float], noise: list[float], snr_db: float) -> tuple[list[float], list[float]]:
    active = [v for i, v in enumerate(clean) if activity_envelope(i / RATE) > 0.5]
    target_noise = rms(active) / (10.0 ** (snr_db / 20.0))
    scaled_noise = scale_to_rms(noise, target_noise)
    peak = max(max(abs(c + n) for c, n in zip(clean, scaled_noise)), 1.0e-9)
    factor = min(1.0, 0.92 / peak)
    return [factor * (c + n) for c, n in zip(clean, scaled_noise)], [factor * c for c in clean]


def si_sdr(est: list[float], ref: list[float]) -> float:
    require(len(est) == len(ref) and len(est) > 32, "SI-SDR alignment")
    dot = sum(e * r for e, r in zip(est, ref))
    ref_energy = sum(r * r for r in ref) + 1.0e-18
    scale = dot / ref_energy
    target = [scale * r for r in ref]
    noise = [e - t for e, t in zip(est, target)]
    return 10.0 * math.log10((sum(t * t for t in target) + 1.0e-18) /
                             (sum(v * v for v in noise) + 1.0e-18))


def percentile(values: list[float], q: float) -> float:
    require(values, "empty percentile")
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return values[lo]
    f = pos - lo
    return values[lo] * (1.0 - f) + values[hi] * f


def stable_probability_margin(trace: list[dict], labels: list[int], latency_frames: int, warmup: int) -> dict:
    pos, neg = [], []
    for row in trace:
        frame = int(row.get("frame", -1))
        source = frame - latency_frames
        if frame < warmup or source <= 0 or source + 1 >= len(labels):
            continue
        if labels[source - 1] != labels[source] or labels[source] != labels[source + 1]:
            continue
        value = float(row.get("ns_speech_probability", 0.0))
        (pos if labels[source] else neg).append(value)
    p10 = percentile(pos, 0.10) if pos else None
    n90 = percentile(neg, 0.90) if neg else None
    return {
        "stable_positive_frames": len(pos), "stable_negative_frames": len(neg),
        "positive_p10": p10, "negative_p90": n90,
        "margin": None if p10 is None or n90 is None else p10 - n90,
    }


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def build_tools(root: Path, output: Path) -> tuple[Path, Path]:
    build = output / "build"
    run_checked(["cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                 "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON",
                 f"-DAP_BUILD_SOURCE_REVISION={subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()}"])
    run_checked(["cmake", "--build", str(build), "--target", "ap_process_pcm", "--parallel"])
    probe = build / "ns_probability_probe"
    run_checked(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(root / "include"),
                 "-I" + str(build / "generated"), str(root / "validation/tools/ns_probability_probe.c"),
                 str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe)])
    return build / "ap_process_pcm", probe


def validate_contract(c: dict) -> None:
    require(c.get("schema_version") == 1 and c.get("iteration_id") == "I004", "I004 contract identity")
    require(c.get("phase") == "measurement-diagnostic" and c.get("root_cause_id") == "ns-nonstationary-low-snr", "I004 phase")
    require(c.get("candidate_limit") == 0 and c.get("confirmation_limit") == 0 and c.get("promotion_allowed") is False, "I004 authority")
    require(c.get("data_role") == "development" and c.get("seeds") == [14107, 24107, 34107], "I004 data")
    require(c.get("scenarios") == SCENARIOS and c.get("seconds") == 6.0, "I004 matrix")
    require(c.get("existing_exposed_ns_tuning_seeds") == [1307, 2307, 3307], "legacy seed exposure")
    authority = c.get("authority", {})
    require(all(authority.get(k) is False for k in ("may_modify_shipping_dsp", "may_tune_ns_floor", "may_add_backend", "may_create_candidate", "may_consume_confirmation")), "I004 no-candidate authority")


def evaluate_case(processor: Path, probe: Path, case_dir: Path, labels: list[int], clean: list[float], noise_only: bool, flags: dict) -> dict:
    mic_path, out_path, metrics_path = case_dir / "mic.pcm", case_dir / "out.pcm", case_dir / "metrics.jsonl"
    run_checked([str(processor), "--sample-rate", "16000", "--mic-channels", "1", "--capture-only",
                 "--capture-profile", "ns-isolated", "--metrics-jsonl", str(metrics_path), str(mic_path), str(out_path)])
    metrics = [json.loads(line) for line in metrics_path.read_text().splitlines() if line.strip()]
    require(metrics, "missing processor metrics")
    latency_ms = int(metrics[0]["algorithmic_latency_ms"])
    latency = latency_ms * RATE // 1000
    latency_frames = latency_ms // 10
    output = read_pcm(out_path)
    mic = read_pcm(mic_path)
    warmup = 40
    start = max(latency + warmup * FRAME, latency)
    aligned_out = output[start:]
    aligned_mic = mic[start - latency:len(mic) - latency if latency else len(mic)]
    aligned_clean = clean[start - latency:len(clean) - latency if latency else len(clean)]
    count = min(len(aligned_out), len(aligned_mic), len(aligned_clean))
    aligned_out, aligned_mic, aligned_clean = aligned_out[:count], aligned_mic[:count], aligned_clean[:count]
    result: dict = {"latency_ms": latency_ms, "clip_fraction": sum(abs(v) >= 0.999 for v in output) / max(1, len(output))}
    if noise_only:
        attenuation = db(rms(aligned_mic)) - db(rms(aligned_out))
        windows = []
        for off in range(0, max(0, count - RATE + 1), RATE // 2):
            windows.append(db(rms(aligned_mic[off:off + RATE])) - db(rms(aligned_out[off:off + RATE])))
        result.update({"noise_attenuation_db": attenuation, "worst_window_noise_attenuation_db": min(windows) if windows else attenuation})
    else:
        input_sisdr = si_sdr(aligned_mic, aligned_clean)
        output_sisdr = si_sdr(aligned_out, aligned_clean)
        windows = []
        for off in range(0, max(0, count - RATE + 1), RATE // 2):
            ref = aligned_clean[off:off + RATE]
            if rms(ref) < 0.015:
                continue
            windows.append(si_sdr(aligned_out[off:off + RATE], ref) - si_sdr(aligned_mic[off:off + RATE], ref))
        tp = fp = fn = tn = 0
        for row in metrics[warmup:]:
            frame = int(row["frame"])
            source = frame - latency_frames
            if source < 0 or source >= len(labels):
                continue
            actual = labels[source] != 0
            predicted = int(row["vad_active"]) != 0
            tp += actual and predicted; fp += (not actual) and predicted
            fn += actual and (not predicted); tn += (not actual) and (not predicted)
        result.update({
            "input_si_sdr_db": input_sisdr, "output_si_sdr_db": output_sisdr,
            "si_sdr_improvement_db": output_sisdr - input_sisdr,
            "worst_window_si_sdr_improvement_db": min(windows) if windows else output_sisdr - input_sisdr,
            "vad_recall": tp / max(1, tp + fn), "vad_false_positive_rate": fp / max(1, fp + tn),
        })
    trace_path = case_dir / "ns-probability.jsonl"
    run_checked([str(probe), str(mic_path), str(trace_path)])
    trace = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
    result["ns_probability"] = stable_probability_margin(trace, labels, latency_frames, warmup)
    failures = []
    if result["clip_fraction"] > float(flags["max_clip_fraction"]): failures.append("clip_fraction")
    if noise_only:
        if result["noise_attenuation_db"] < float(flags["min_noise_only_attenuation_db"]): failures.append("noise_attenuation")
        if result["worst_window_noise_attenuation_db"] < 0.0: failures.append("worst_window_noise_amplification")
    else:
        if result["si_sdr_improvement_db"] < float(flags["min_speech_si_sdr_improvement_db"]): failures.append("speech_si_sdr")
        if result["worst_window_si_sdr_improvement_db"] < -0.5: failures.append("worst_window_speech_degradation")
        if result["vad_recall"] < float(flags["min_vad_recall"]): failures.append("vad_recall")
        if result["vad_false_positive_rate"] > float(flags["max_vad_false_positive_rate"]): failures.append("vad_false_positive")
        margin = result["ns_probability"]["margin"]
        if margin is None or margin < float(flags["min_ns_probability_margin"]): failures.append("ns_probability_margin")
    result["failures"] = failures
    result["passed_diagnostic_flags"] = not failures
    return result


def self_test() -> None:
    samples = RATE * 4
    speech_a, labels_a = speech_like(samples, 7)
    speech_b, labels_b = speech_like(samples, 7)
    assert speech_a == speech_b and labels_a == labels_b
    assert motor_ramp(samples, 9) == motor_ramp(samples, 9)
    assert fan_am(samples, 9) != fan_am(samples, 10)
    assert len(labels_a) == samples // FRAME
    clean = [0.1 * math.sin(2 * math.pi * 200 * n / RATE) for n in range(RATE)]
    assert si_sdr(clean, clean) > 100.0
    print(json.dumps({"result": "PASS", "authority": "baseline-diagnostic-only"}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    require(args.contract is not None and args.output is not None, "contract/output required")
    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    validate_contract(contract)
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I004 exact base drift: {current}")
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    processor, probe = build_tools(root, output)
    cases = []
    data_root = output / "corpus"
    data_root.mkdir()
    samples = int(contract["seconds"] * RATE)
    snr_map = contract["speech_snr_db"]
    for seed in contract["seeds"]:
        speech, labels = speech_like(samples, seed)
        for index, scenario in enumerate(contract["scenarios"]):
            noise = scenario_noise(scenario, samples, seed + index * 19)
            noise_only = scenario.endswith("-noise")
            case_dir = data_root / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            if noise_only:
                mic = noise
                clean = [0.0] * samples
                case_labels = [0] * (samples // FRAME)
            else:
                mic, clean = mix_at_snr(speech, noise, float(snr_map[scenario]))
                case_labels = labels
            write_pcm(case_dir / "mic.pcm", mic)
            write_pcm(case_dir / "clean.pcm", clean)
            write_json(case_dir / "labels.json", {"frame_samples": FRAME, "labels": case_labels})
            metrics = evaluate_case(processor, probe, case_dir, case_labels, clean, noise_only, contract["diagnostic_flags"])
            cases.append({"seed": seed, "scenario": scenario, "noise_only": noise_only, "metrics": metrics})
    failures = [{"seed": c["seed"], "scenario": c["scenario"], "failures": c["metrics"]["failures"]} for c in cases if c["metrics"]["failures"]]
    decision = "MEASURED_GAP_REVIEW_REQUIRED" if failures else "BASELINE_ADEQUATE_NO_SEARCH"
    report = {
        "schema_version": 1, "iteration_id": "I004", "root_cause_id": contract["root_cause_id"],
        "authority": "development-baseline-diagnostic-only", "source_sha": current,
        "candidate_limit": 0, "confirmation_limit": 0, "candidate_search_performed": False,
        "ns_floor_tuning_performed": False, "backend_change_performed": False,
        "seeds": contract["seeds"], "scenarios": contract["scenarios"], "cases": cases,
        "failed_flags": failures, "decision": decision, "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "next_step": "review measured gaps before authorizing any candidate" if failures else "keep baseline; no NS search justified by this diagnostic",
    }
    write_json(output / "baseline-report.json", report)
    manifest = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "source_sha": current, "files": manifest})
    with (output / "SHA256SUMS").open("w") as handle:
        for rel, digest in sorted(manifest.items()): handle.write(f"{digest}  {rel}\n")
    print(json.dumps({"decision": decision, "cases": len(cases), "failed_cases": len(failures)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(f"I004 diagnostic contract error: {exc}")
