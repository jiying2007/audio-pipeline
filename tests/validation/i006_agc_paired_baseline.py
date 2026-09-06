#!/usr/bin/env python3
"""Paired exact-production I006 candidate-zero AGC baseline (revision 3).

For every frozen case this evaluator runs two exact-base full call pipelines
with identical upstream configuration and inputs. The only configuration
difference is AP_STAGE_AGC. Frozen AGC gates are evaluated on the ON-minus-OFF
causal contribution; raw AGC remains diagnostic only. No tuning or candidate
search is performed.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import i004_ns_nonstationary_diagnostic as synth
import i006_agc_residual_floor_baseline as v1

RATE = 16000
FRAME = 160


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def build_tools(root: Path, output: Path) -> tuple[Path, Path]:
    build = output / "build-paired"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON", f"-DAP_BUILD_SOURCE_REVISION={revision}",
    ])
    run_checked(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"])
    paired = build / "i006_agc_paired_pipeline_probe"
    raw = build / "agc_dynamics_probe"
    common = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
              "-I" + str(root / "include"), "-I" + str(build / "generated")]
    run_checked(common + [str(root / "tests/validation/i006_agc_paired_pipeline_probe.c"),
                          str(build / "libaudio_pipeline.a"), "-lm", "-o", str(paired)])
    run_checked(common + [str(root / "tests/validation/agc_dynamics_probe.c"),
                          str(build / "libaudio_pipeline.a"), "-lm", "-o", str(raw)])
    return paired, raw


def aligned_pair(with_path: Path, without_path: Path, near_clean: list[float],
                 latency_ms: int, warmup_frames: int) -> tuple[list[float], list[float], list[float]]:
    with_audio = synth.read_pcm(with_path)
    without_audio = synth.read_pcm(without_path)
    latency = latency_ms * RATE // 1000
    source_start = warmup_frames * FRAME
    source_end = len(near_clean) - latency if latency else len(near_clean)
    output_start = source_start + latency
    count = max(0, source_end - source_start)
    with_aligned = with_audio[output_start:output_start + count]
    without_aligned = without_audio[output_start:output_start + count]
    near_aligned = near_clean[source_start:source_start + count]
    count = min(len(with_aligned), len(without_aligned), len(near_aligned))
    return with_aligned[:count], without_aligned[:count], near_aligned[:count]


def run_paired(probe: Path, case_dir: Path, mic: list[float], render: list[float],
               near_clean: list[float], near_labels: list[int], far_labels: list[int],
               contract: dict, category: str) -> dict:
    mic_path = case_dir / "mic.pcm"
    render_path = case_dir / "render.pcm"
    with_path = case_dir / "with-agc.pcm"
    without_path = case_dir / "without-agc.pcm"
    synth.write_pcm(mic_path, mic)
    synth.write_pcm(render_path, render)
    synth.write_pcm(case_dir / "near-clean.pcm", near_clean)
    completed = subprocess.run([str(probe), str(mic_path), str(render_path),
                                str(with_path), str(without_path)],
                               check=True, text=True, capture_output=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    pre = contract["input_preconditions"]
    require(len(rows) >= int(pre["min_trace_frames"]), "paired pipeline trace too short")
    warmup = int(pre["warmup_frames"])
    latency_ms = int(rows[0]["algorithmic_latency_ms"])
    with_audio = synth.read_pcm(with_path)
    without_audio = synth.read_pcm(without_path)
    with_aligned, without_aligned, near_aligned = aligned_pair(
        with_path, without_path, near_clean, latency_ms, warmup)
    require(len(with_aligned) >= RATE * 4, "insufficient paired output")

    frame_effects = []
    for offset in range(0, len(with_aligned) - FRAME + 1, FRAME):
        w = with_aligned[offset:offset + FRAME]
        n = without_aligned[offset:offset + FRAME]
        if v1.rms(n) > 1.0e-7:
            frame_effects.append(v1.db_rms(w) - v1.db_rms(n))
    usable = rows[warmup:]
    result = {
        "authority": "paired-exact-production-agc-on-vs-off",
        "frames": len(usable),
        "latency_ms": latency_ms,
        "agc_effect_rms_gain_db": v1.db_rms(with_aligned) - v1.db_rms(without_aligned),
        "output_vs_input_rms_gain_db": v1.db_rms(with_aligned) - v1.db_rms(without_aligned),
        "p95_frame_gain_db": v1.percentile(frame_effects, 0.95),
        "tail_output_rms_dbfs": v1.db_rms(with_aligned[-2 * RATE:]),
        "without_agc_tail_output_rms_dbfs": v1.db_rms(without_aligned[-2 * RATE:]),
        "clip_fraction": sum(abs(value) >= 0.999 for value in with_audio) / max(1, len(with_audio)),
    }

    if category == "pure_far_end":
        active = [row for row in usable if int(row["frame"]) < len(far_labels) and
                  far_labels[int(row["frame"])] != 0]
        require(len(active) >= int(pre["min_pure_far_active_frames"]), "too few pure-far active frames")
        far_only = [row for row in active if int(row["far_end_active"]) and
                    not int(row["double_talk_active"])]
        result.update({
            "far_active_frames": len(active),
            "far_only_fraction_on_far_active": len(far_only) / len(active),
        })
    elif category == "near_far":
        active = [row for row in usable if int(row["frame"]) < len(near_labels) and
                  near_labels[int(row["frame"])] != 0]
        require(len(active) >= int(pre["min_near_active_frames"]), "too few near-active frames")
        result.update({
            "near_active_frames": len(active),
            "far_active_fraction_on_near_active": sum(int(row["far_end_active"]) != 0 for row in active) / len(active),
            "double_talk_fraction_on_near_active": sum(int(row["double_talk_active"]) != 0 for row in active) / len(active),
        })
        require(v1.rms(near_aligned) > 1.0e-7, "near reference is silent")
        with_sisdr = synth.si_sdr(with_aligned, near_aligned)
        without_sisdr = synth.si_sdr(without_aligned, near_aligned)
        result.update({
            "with_agc_si_sdr_db": with_sisdr,
            "without_agc_si_sdr_db": without_sisdr,
            "speech_si_sdr_improvement_db": with_sisdr - without_sisdr,
        })
    else:
        require(len(usable) >= int(pre["min_noise_frames"]), "too few noise-floor frames")
    return result


def self_test() -> None:
    assert v1.percentile([0.0, 10.0], 0.95) == 9.5
    assert abs(v1.db_rms([0.1] * 160) + 20.0) < 1.0e-6
    print(json.dumps({"result": "PASS", "measurement_revision": 3,
                      "paired_production": True, "candidate_limit": 0}, sort_keys=True))


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
    contract = v1.load_json(args.contract)
    v1.validate_contract(contract)
    require(contract.get("measurement_revision") == 3, "I006 paired measurement revision required")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I006 exact base drift: {current}")
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    production_gate = v1.validate_production_gate_source(root)
    paired_probe, raw_probe = build_tools(root, output)
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
            mic, render, near, near_labels, far_labels, category = v1.generate_case(contract, scenario, int(seed))
            synth.write_pcm(case_dir / "mic.pcm", mic)
            synth.write_pcm(case_dir / "render.pcm", render)
            try:
                paired = run_paired(paired_probe, case_dir, mic, render, near,
                                    near_labels, far_labels, contract, category)
                failures = v1.gate_case(category, paired, contract)
            except ValueError as exc:
                paired = {"precondition_error": str(exc)}
                failures = []
                precondition_failures.append({"seed": seed, "scenario": scenario, "error": str(exc)})
            raw = v1.run_raw_probe(raw_probe, case_dir / "mic.pcm", warmup)
            row = {
                "seed": seed,
                "scenario": scenario,
                "category": category,
                "paired_production": paired,
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
        "measurement_revision": 3,
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "authority": "candidate-zero-paired-exact-production-agc-baseline-only",
        "production_gate": production_gate,
        "paired_probe_sha256": v1.sha256(paired_probe),
        "raw_probe_sha256": v1.sha256(raw_probe),
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
        "measurement_lineage": contract["measurement_lineage"],
        "next_step": (
            "review paired-production AGC gaps before authorizing any root-cause candidate"
            if decision != "BASELINE_ADEQUATE_NO_SEARCH" else
            "keep baseline; no AGC search justified by paired exact-production measurement"
        ),
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "baseline-result.json", report)
    manifest = {str(path.relative_to(output)): v1.sha256(path) for path in sorted(output.rglob("*"))
                if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "source_sha": current, "files": manifest})
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({"decision": decision, "cases": len(cases),
                      "gate_failures": len(gate_failures),
                      "precondition_failures": len(precondition_failures),
                      "measurement_revision": 3, "candidate_limit": 0,
                      "confirmation_limit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I006 paired AGC baseline error: {exc}")
