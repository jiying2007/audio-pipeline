#!/usr/bin/env python3
"""Candidate-zero I006 AGC residual/floor/mismatch baseline.

The production full-call path is authoritative. The existing raw AGC probe is
reported only as a diagnostic counterfactual because it always allows gain
increase and therefore does not include the production far-end activity gate.
No AGC tuning or candidate ranking is performed here.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from pathlib import Path

import i004_ns_nonstationary_diagnostic as synth

RATE = 16000
FRAME = 160


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def sha256(path: Path) -> str:
    return synth.sha256(path)


def rms(values: list[float]) -> float:
    return synth.rms(values)


def db_rms(values: list[float]) -> float:
    return 20.0 * math.log10(max(rms(values), 1.0e-12))


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    pos = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    f = pos - lo
    return ordered[lo] * (1.0 - f) + ordered[hi] * f


def scale(values: list[float], factor: float) -> list[float]:
    return [factor * v for v in values]


def bounded_mix(*signals: list[float]) -> list[float]:
    require(signals and len({len(v) for v in signals}) == 1, "mix geometry")
    mixed = [sum(parts) for parts in zip(*signals)]
    peak = max(max(abs(v) for v in mixed), 1.0e-9)
    factor = min(1.0, 0.92 / peak)
    return [factor * v for v in mixed]


def delayed_echo(render: list[float], taps: list[list[float]]) -> list[float]:
    out = [0.0] * len(render)
    for delay_raw, gain_raw in taps:
        delay = int(delay_raw)
        gain = float(gain_raw)
        require(delay >= 0 and abs(gain) <= 1.0, "invalid echo tap")
        for n in range(delay, len(render)):
            out[n] += gain * render[n - delay]
    return out


def ramp_echo(render: list[float], before: list[list[float]], after: list[list[float]]) -> list[float]:
    a = delayed_echo(render, before)
    b = delayed_echo(render, after)
    split = len(render) // 2
    fade = RATE // 4
    out = []
    for n, (x, y) in enumerate(zip(a, b)):
        if n <= split - fade:
            w = 0.0
        elif n >= split + fade:
            w = 1.0
        else:
            w = (n - (split - fade)) / float(2 * fade)
        out.append((1.0 - w) * x + w * y)
    return out


def colored_noise(samples: int, seed: int) -> list[float]:
    state = 0.0
    out = []
    for n in range(samples):
        state = 0.86 * state + 0.14 * synth.hash_noise(n, seed)
        out.append(state)
    return synth.scale_to_rms(out, 1.0)


def noise_floor_case(samples: int, seed: int, before: float, after: float | None = None) -> list[float]:
    noise = colored_noise(samples, seed)
    if after is None:
        return scale(noise, before)
    split = samples // 2
    fade = RATE // 5
    out = []
    for n, value in enumerate(noise):
        if n <= split - fade:
            level = before
        elif n >= split + fade:
            level = after
        else:
            w = (n - (split - fade)) / float(2 * fade)
            level = before * (1.0 - w) + after * w
        out.append(level * value)
    return out


def build_tools(root: Path, output: Path) -> tuple[Path, Path]:
    build = output / "build"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON", f"-DAP_BUILD_SOURCE_REVISION={revision}",
    ])
    run_checked(["cmake", "--build", str(build), "--target", "ap_process_pcm", "--parallel"])
    probe = build / "agc_dynamics_probe"
    run_checked([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(root / "include"), "-I" + str(build / "generated"),
        str(root / "tests/validation/agc_dynamics_probe.c"), str(build / "libaudio_pipeline.a"),
        "-lm", "-o", str(probe),
    ])
    return build / "ap_process_pcm", probe


def validate_contract(c: dict) -> None:
    require(c.get("schema_version") == 1 and c.get("iteration_id") == "I006", "I006 identity")
    require(c.get("phase") == "baseline-measurement" and
            c.get("root_cause_id") == "agc-residual-floor-mismatch-baseline", "I006 phase")
    require(c.get("candidate_limit") == 0 and c.get("confirmation_limit") == 0 and
            c.get("promotion_allowed") is False, "I006 candidate-zero authority")
    require(c.get("seeds") == [16107, 26107, 36107] and c.get("seconds") == 8.0, "I006 fresh data")
    require(c.get("existing_exposed_agc_search") == {
        "seeds": [1307, 2307, 3307],
        "parameters": ["agc_target_dbfs", "limiter_dbfs"],
        "role": "regression-only",
        "prohibited_for_this_measurement": True,
    }, "I006 must not reuse old AGC search authority")
    require(all(value is False for value in c["authority"].values()), "I006 authority must remain false")
    require(c.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")


def validate_production_gate_source(root: Path) -> dict:
    text = (root / "src/core/ap_pipeline.c").read_text(encoding="utf-8")
    require("ap_agc_process_controlled(&pipeline->agc" in text, "production controlled AGC call missing")
    require("!(far_end_active && !double_talk_active)" in text, "production far-end AGC gate drift")
    return {
        "controlled_call_present": True,
        "allow_gain_expression": "!(far_end_active && !double_talk_active)",
        "source_sha256": sha256(root / "src/core/ap_pipeline.c"),
    }


def run_raw_probe(probe: Path, pcm: Path, warmup: int) -> dict:
    completed = subprocess.run([str(probe), "-20.0", "-2.0", str(pcm)], check=True,
                               text=True, capture_output=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    require(len(rows) > warmup, "raw AGC probe produced too few rows")
    rows = rows[warmup:]
    gains = [float(row["gain_db"]) for row in rows]
    return {
        "authority": "raw-agc-uncontrolled-diagnostic-only",
        "frames": len(rows),
        "gain_db_p50": statistics.median(gains),
        "gain_db_p95": percentile(gains, 0.95),
        "gain_db_max": max(gains),
        "max_output_peak_dbfs": max(float(row["output_peak_dbfs"]) for row in rows),
    }


def run_production(processor: Path, case_dir: Path, mic: list[float], render: list[float],
                   near_clean: list[float], near_labels: list[int], far_labels: list[int],
                   contract: dict, category: str) -> dict:
    mic_path = case_dir / "mic.pcm"
    render_path = case_dir / "render.pcm"
    out_path = case_dir / "out.pcm"
    metrics_path = case_dir / "metrics.jsonl"
    synth.write_pcm(mic_path, mic)
    synth.write_pcm(render_path, render)
    synth.write_pcm(case_dir / "near-clean.pcm", near_clean)
    run_checked([
        str(processor), "--sample-rate", "16000", "--mic-channels", "1",
        "--metrics-jsonl", str(metrics_path), str(mic_path), str(render_path), str(out_path),
    ])
    metrics = [json.loads(line) for line in metrics_path.read_text().splitlines() if line.strip()]
    pre = contract["input_preconditions"]
    require(len(metrics) >= int(pre["min_trace_frames"]), "production trace too short")
    latency_ms = int(metrics[0]["algorithmic_latency_ms"])
    latency = latency_ms * RATE // 1000
    warmup = int(pre["warmup_frames"])
    source_start = warmup * FRAME
    source_end = len(mic) - latency if latency else len(mic)
    output = synth.read_pcm(out_path)
    aligned_out = output[source_start + latency: source_start + latency + max(0, source_end - source_start)]
    aligned_mic = mic[source_start:source_end]
    aligned_near = near_clean[source_start:source_end]
    count = min(len(aligned_out), len(aligned_mic), len(aligned_near))
    aligned_out, aligned_mic, aligned_near = aligned_out[:count], aligned_mic[:count], aligned_near[:count]
    require(count >= RATE * 4, "insufficient aligned production output")

    frame_gains = []
    for offset in range(0, count - FRAME + 1, FRAME):
        inp = aligned_mic[offset:offset + FRAME]
        out = aligned_out[offset:offset + FRAME]
        if rms(inp) > 1.0e-7:
            frame_gains.append(db_rms(out) - db_rms(inp))
    clip_fraction = sum(abs(v) >= 0.999 for v in output) / max(1, len(output))
    tail = aligned_out[-2 * RATE:]
    result = {
        "latency_ms": latency_ms,
        "output_vs_input_rms_gain_db": db_rms(aligned_out) - db_rms(aligned_mic),
        "p95_frame_gain_db": percentile(frame_gains, 0.95),
        "tail_output_rms_dbfs": db_rms(tail),
        "clip_fraction": clip_fraction,
    }

    usable = metrics[warmup:]
    if category == "pure_far_end":
        active = [row for row in usable if int(row["frame"]) < len(far_labels) and
                  far_labels[int(row["frame"])] != 0]
        require(len(active) >= int(pre["min_pure_far_active_frames"]), "too few pure-far active frames")
        far_only = [row for row in active if int(row["far_end_active"]) and not int(row["double_talk_active"])]
        result["far_active_frames"] = len(active)
        result["far_only_fraction_on_far_active"] = len(far_only) / len(active)
    elif category == "near_far":
        active = [row for row in usable if int(row["frame"]) < len(near_labels) and
                  near_labels[int(row["frame"])] != 0]
        require(len(active) >= int(pre["min_near_active_frames"]), "too few near-active frames")
        result["near_active_frames"] = len(active)
        result["far_active_fraction_on_near_active"] = sum(int(row["far_end_active"]) != 0 for row in active) / len(active)
        result["double_talk_fraction_on_near_active"] = sum(int(row["double_talk_active"]) != 0 for row in active) / len(active)
        require(rms(aligned_near) > 1.0e-7, "near reference is silent")
        result["input_si_sdr_db"] = synth.si_sdr(aligned_mic, aligned_near)
        result["output_si_sdr_db"] = synth.si_sdr(aligned_out, aligned_near)
        result["speech_si_sdr_improvement_db"] = result["output_si_sdr_db"] - result["input_si_sdr_db"]
    else:
        require(len(usable) >= int(pre["min_noise_frames"]), "too few noise-floor frames")
    return result


def gate_case(category: str, metrics: dict, contract: dict) -> list[str]:
    failures: list[str] = []
    if category == "pure_far_end":
        gate = contract["diagnostic_gates"]["pure_far_end"]
        if metrics["far_only_fraction_on_far_active"] < float(gate["min_far_only_fraction_on_far_active"]):
            failures.append("far_only_fraction")
        if metrics["output_vs_input_rms_gain_db"] > float(gate["max_output_vs_input_rms_gain_db"]):
            failures.append("pure_far_gain_up")
        if metrics["clip_fraction"] > float(gate["max_clip_fraction"]):
            failures.append("clip_fraction")
    elif category == "noise_floor":
        gate = contract["diagnostic_gates"]["noise_floor"]
        if metrics["tail_output_rms_dbfs"] > float(gate["max_tail_output_rms_dbfs"]):
            failures.append("noise_floor_output_level")
        if metrics["p95_frame_gain_db"] is None or metrics["p95_frame_gain_db"] > float(gate["max_p95_frame_gain_db"]):
            failures.append("noise_floor_gain")
        if metrics["clip_fraction"] > float(gate["max_clip_fraction"]):
            failures.append("clip_fraction")
    else:
        gate = contract["diagnostic_gates"]["near_far"]
        if metrics["far_active_fraction_on_near_active"] < float(gate["min_far_active_fraction_on_near_active"]):
            failures.append("far_activity")
        if metrics["double_talk_fraction_on_near_active"] < float(gate["min_double_talk_fraction_on_near_active"]):
            failures.append("double_talk_activity")
        if metrics["speech_si_sdr_improvement_db"] < float(gate["min_speech_si_sdr_improvement_db"]):
            failures.append("speech_preservation")
        if metrics["clip_fraction"] > float(gate["max_clip_fraction"]):
            failures.append("clip_fraction")
    return failures


def generate_case(contract: dict, scenario: str, seed: int) -> tuple[list[float], list[float], list[float], list[int], list[int], str]:
    samples = int(float(contract["seconds"]) * RATE)
    g = contract["generator"]
    far, far_labels = synth.speech_like(samples, seed + 701)
    near, near_labels = synth.speech_like(samples, seed + 1701)
    zero = [0.0] * samples
    if scenario == "pure-far-end-residual-low":
        mic = delayed_echo(far, [[640, 0.16], [960, 0.06]])
        return mic, far, zero, [0] * len(near_labels), far_labels, "pure_far_end"
    if scenario == "pure-far-end-residual-ramp":
        mic = ramp_echo(far, [[640, 0.10], [960, 0.04]], [[640, 0.28], [960, 0.10]])
        return mic, far, zero, [0] * len(near_labels), far_labels, "pure_far_end"
    if scenario == "noise-floor-low":
        mic = noise_floor_case(samples, seed + 2701, float(g["noise_floor_low_rms"]))
        return mic, zero, zero, [0] * len(near_labels), [0] * len(far_labels), "noise_floor"
    if scenario == "noise-floor-step":
        mic = noise_floor_case(samples, seed + 3701, float(g["noise_floor_step_rms_before"]),
                               float(g["noise_floor_step_rms_after"]))
        return mic, zero, zero, [0] * len(near_labels), [0] * len(far_labels), "noise_floor"
    echo = delayed_echo(far, [[640, 0.16], [960, 0.06]])
    near_scale = float(g["near_scale_balanced"] if scenario == "near-far-doubletalk" else g["near_scale_weak"])
    near_scaled = scale(near, near_scale)
    mic = bounded_mix(near_scaled, echo)
    return mic, far, near_scaled, near_labels, far_labels, "near_far"


def self_test() -> None:
    values = colored_noise(RATE, 7)
    assert values == colored_noise(RATE, 7)
    assert abs(rms(values) - 1.0) < 1.0e-6
    render, _ = synth.speech_like(RATE * 2, 11)
    echo = delayed_echo(render, [[640, 0.2]])
    assert len(echo) == len(render) and echo[:640] == [0.0] * 640
    assert percentile([0.0, 10.0], 0.95) == 9.5
    print(json.dumps({"result": "PASS", "candidate_limit": 0, "production_gate": True}, sort_keys=True))


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
    require(current == contract["base_sha"], f"I006 exact base drift: {current}")
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    production_gate = validate_production_gate_source(root)
    processor, raw_probe = build_tools(root, output)
    cases = []
    gate_failures = []
    precondition_failures = []
    corpus = output / "corpus"
    corpus.mkdir()
    warmup = int(contract["input_preconditions"]["warmup_frames"])
    for seed in contract["seeds"]:
        for scenario in contract["scenarios"]:
            case_dir = corpus / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            mic, render, near, near_labels, far_labels, category = generate_case(contract, scenario, int(seed))
            try:
                production = run_production(processor, case_dir, mic, render, near, near_labels,
                                            far_labels, contract, category)
                failures = gate_case(category, production, contract)
            except ValueError as exc:
                production = {"precondition_error": str(exc)}
                failures = []
                precondition_failures.append({"seed": seed, "scenario": scenario, "error": str(exc)})
            raw = run_raw_probe(raw_probe, case_dir / "mic.pcm", warmup)
            row = {
                "seed": seed,
                "scenario": scenario,
                "category": category,
                "production": production,
                "raw_agc_diagnostic": raw,
                "failures": failures,
            }
            cases.append(row)
            if failures:
                gate_failures.append({"seed": seed, "scenario": scenario, "failures": failures})
    if precondition_failures:
        decision = "INPUT_OR_ACTIVITY_INVALID_REVIEW_REQUIRED"
    elif gate_failures:
        decision = "MEASURED_GAP_REVIEW_REQUIRED"
    else:
        decision = "BASELINE_ADEQUATE_NO_SEARCH"
    report = {
        "schema_version": 1,
        "iteration_id": "I006",
        "phase": "baseline-measurement",
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "authority": "candidate-zero-production-agc-baseline-only",
        "production_gate": production_gate,
        "processor_sha256": sha256(processor),
        "raw_probe_sha256": sha256(raw_probe),
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "candidate_search_performed": False,
        "agc_target_tuning_performed": False,
        "limiter_tuning_performed": False,
        "attack_release_tuning_performed": False,
        "promotion_allowed": False,
        "seeds": contract["seeds"],
        "scenarios": contract["scenarios"],
        "cases": cases,
        "precondition_failures": precondition_failures,
        "gate_failures": gate_failures,
        "decision": decision,
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "next_step": (
            "review measured production-path AGC gaps before authorizing any root-cause candidate"
            if decision != "BASELINE_ADEQUATE_NO_SEARCH" else
            "keep baseline; no AGC search justified by this frozen measurement"
        ),
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "baseline-result.json", report)
    manifest = {str(path.relative_to(output)): sha256(path) for path in sorted(output.rglob("*"))
                if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "source_sha": current, "files": manifest})
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({"decision": decision, "cases": len(cases),
                      "gate_failures": len(gate_failures),
                      "precondition_failures": len(precondition_failures),
                      "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I006 AGC baseline error: {exc}")
