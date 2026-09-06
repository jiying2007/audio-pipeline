#!/usr/bin/env python3
"""Attribution-corrected I006 candidate-zero AGC baseline.

Revision 2 preserves the original I006 seeds, scenarios, thresholds and product
settings. The decision authority is the production activity classifier plus the
same ap_agc_process_controlled() call used by the full pipeline. Full-pipeline
results are retained only as non-gating context because AEC/RES/NS otherwise
confound AGC-specific speech-preservation attribution.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
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


def build_tools(root: Path, output: Path) -> tuple[Path, Path, Path]:
    build = output / "build-controlled"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON", f"-DAP_BUILD_SOURCE_REVISION={revision}",
    ])
    run_checked(["cmake", "--build", str(build), "--target", "ap_process_pcm", "--parallel"])
    raw_probe = build / "agc_dynamics_probe"
    controlled_probe = build / "i006_agc_activity_control_probe"
    common = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
              "-I" + str(root / "include"), "-I" + str(root / "src"),
              "-I" + str(build / "generated")]
    run_checked(common + [str(root / "tests/validation/agc_dynamics_probe.c"),
                          str(build / "libaudio_pipeline.a"), "-lm", "-o", str(raw_probe)])
    run_checked(common + [str(root / "tests/validation/i006_agc_activity_control_probe.c"),
                          str(build / "libaudio_pipeline.a"), "-lm", "-o", str(controlled_probe)])
    return build / "ap_process_pcm", raw_probe, controlled_probe


def run_controlled(probe: Path, case_dir: Path, mic: list[float], render: list[float],
                   near_clean: list[float], near_labels: list[int], far_labels: list[int],
                   contract: dict, category: str) -> dict:
    mic_path = case_dir / "mic.pcm"
    render_path = case_dir / "render.pcm"
    out_path = case_dir / "controlled-out.pcm"
    synth.write_pcm(mic_path, mic)
    synth.write_pcm(render_path, render)
    synth.write_pcm(case_dir / "near-clean.pcm", near_clean)
    completed = subprocess.run([str(probe), str(mic_path), str(render_path), str(out_path)],
                               check=True, text=True, capture_output=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    pre = contract["input_preconditions"]
    require(len(rows) >= int(pre["min_trace_frames"]), "controlled AGC trace too short")
    warmup = int(pre["warmup_frames"])
    usable = rows[warmup:]
    output = synth.read_pcm(out_path)
    start = warmup * FRAME
    aligned_out = output[start:]
    aligned_mic = mic[start:start + len(aligned_out)]
    aligned_near = near_clean[start:start + len(aligned_out)]
    count = min(len(aligned_out), len(aligned_mic), len(aligned_near))
    aligned_out = aligned_out[:count]
    aligned_mic = aligned_mic[:count]
    aligned_near = aligned_near[:count]
    require(count >= RATE * 4, "insufficient controlled output")

    gains = [float(row["gain_db"]) for row in usable]
    result = {
        "authority": "production-activity-controlled-agc",
        "frames": len(usable),
        "output_vs_input_rms_gain_db": v1.db_rms(aligned_out) - v1.db_rms(aligned_mic),
        "p95_frame_gain_db": v1.percentile(gains, 0.95),
        "tail_output_rms_dbfs": v1.db_rms(aligned_out[-2 * RATE:]),
        "clip_fraction": sum(abs(value) >= 0.999 for value in output) / max(1, len(output)),
        "allow_gain_fraction": sum(int(row["allow_gain_increase"]) != 0 for row in usable) / len(usable),
    }

    if category == "pure_far_end":
        active = [row for row in usable if int(row["frame"]) < len(far_labels) and
                  far_labels[int(row["frame"])] != 0]
        require(len(active) >= int(pre["min_pure_far_active_frames"]), "too few pure-far active frames")
        far_only = [row for row in active if int(row["far_end_active"]) and
                    not int(row["double_talk_active"])]
        blocked = [row for row in active if not int(row["allow_gain_increase"])]
        result.update({
            "far_active_frames": len(active),
            "far_only_fraction_on_far_active": len(far_only) / len(active),
            "gain_blocked_fraction_on_far_active": len(blocked) / len(active),
        })
    elif category == "near_far":
        active = [row for row in usable if int(row["frame"]) < len(near_labels) and
                  near_labels[int(row["frame"])] != 0]
        require(len(active) >= int(pre["min_near_active_frames"]), "too few near-active frames")
        result.update({
            "near_active_frames": len(active),
            "far_active_fraction_on_near_active": sum(int(row["far_end_active"]) != 0 for row in active) / len(active),
            "double_talk_fraction_on_near_active": sum(int(row["double_talk_active"]) != 0 for row in active) / len(active),
            "allow_gain_fraction_on_near_active": sum(int(row["allow_gain_increase"]) != 0 for row in active) / len(active),
        })
        require(v1.rms(aligned_near) > 1.0e-7, "near reference is silent")
        result["input_si_sdr_db"] = synth.si_sdr(aligned_mic, aligned_near)
        result["output_si_sdr_db"] = synth.si_sdr(aligned_out, aligned_near)
        result["speech_si_sdr_improvement_db"] = result["output_si_sdr_db"] - result["input_si_sdr_db"]
    else:
        require(len(usable) >= int(pre["min_noise_frames"]), "too few noise-floor frames")
    return result


def full_pipeline_context(processor: Path, case_dir: Path, mic: list[float], render: list[float],
                          near_clean: list[float], near_labels: list[int], far_labels: list[int],
                          contract: dict, category: str) -> dict:
    context_dir = case_dir / "full-pipeline-context"
    context_dir.mkdir()
    try:
        metrics = v1.run_production(processor, context_dir, mic, render, near_clean,
                                    near_labels, far_labels, contract, category)
        return {"available": True, "authority": "end-to-end-context-non-gating", "metrics": metrics}
    except (ValueError, subprocess.CalledProcessError) as exc:
        return {"available": False, "authority": "end-to-end-context-non-gating", "error": str(exc)}


def self_test() -> None:
    assert v1.percentile([0.0, 10.0], 0.95) == 9.5
    values = [0.01, -0.01] * 800
    assert math.isfinite(v1.db_rms(values))
    print(json.dumps({"result": "PASS", "measurement_revision": 2,
                      "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))


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
    require(contract.get("measurement_revision") == 2, "I006 corrected measurement revision required")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I006 exact base drift: {current}")
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    production_gate = v1.validate_production_gate_source(root)
    processor, raw_probe, controlled_probe = build_tools(root, output)
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
            synth.write_pcm(case_dir / "near-clean.pcm", near)
            try:
                controlled = run_controlled(controlled_probe, case_dir, mic, render, near,
                                            near_labels, far_labels, contract, category)
                failures = v1.gate_case(category, controlled, contract)
            except ValueError as exc:
                controlled = {"precondition_error": str(exc)}
                failures = []
                precondition_failures.append({"seed": seed, "scenario": scenario, "error": str(exc)})
            raw = v1.run_raw_probe(raw_probe, case_dir / "mic.pcm", warmup)
            full = full_pipeline_context(processor, case_dir, mic, render, near, near_labels,
                                         far_labels, contract, category)
            row = {
                "seed": seed,
                "scenario": scenario,
                "category": category,
                "controlled_agc": controlled,
                "raw_agc_diagnostic": raw,
                "full_pipeline_context": full,
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
        "measurement_revision": 2,
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "authority": "candidate-zero-production-controlled-agc-baseline-only",
        "production_gate": production_gate,
        "processor_sha256": v1.sha256(processor),
        "controlled_probe_sha256": v1.sha256(controlled_probe),
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
            "review AGC-specific controlled-path gaps before authorizing any root-cause candidate"
            if decision != "BASELINE_ADEQUATE_NO_SEARCH" else
            "keep baseline; no AGC search justified by this corrected frozen measurement"
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
                      "measurement_revision": 2, "candidate_limit": 0,
                      "confirmation_limit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I006 controlled AGC baseline error: {exc}")
