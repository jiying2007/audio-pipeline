#!/usr/bin/env python3
"""I004 candidate-limit-zero root-cause differential.

Uses the frozen I004 development matrix to compare two existing runtime/build
counterfactuals without changing source code:
  1. vad-isolated vs ns-isolated on the exact same noisy mic;
  2. shipping EMA vs already-supported MCRA NS estimator.

This is diagnostic authority only. It does not tune ns_floor, rank source-code
candidates, consume confirmation data, or promote a release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path

import i004_ns_nonstationary_diagnostic as base

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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_processor(root: Path, output: Path, backend: str, source_sha: str) -> Path:
    build = output / f"build-{backend.lower()}"
    base.run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON",
        f"-DAP_NS_ESTIMATOR={backend}", f"-DAP_BUILD_SOURCE_REVISION={source_sha}",
    ])
    base.run_checked(["cmake", "--build", str(build), "--target", "ap_process_pcm", "--parallel"])
    processor = build / "ap_process_pcm"
    require(processor.is_file(), f"missing {backend} processor")
    return processor


def score_profile(processor: Path, case_dir: Path, profile: str, labels: list[int], clean: list[float], noise_only: bool, tag: str) -> dict:
    out_path = case_dir / f"out-{tag}.pcm"
    metrics_path = case_dir / f"metrics-{tag}.jsonl"
    base.run_checked([
        str(processor), "--sample-rate", "16000", "--mic-channels", "1", "--capture-only",
        "--capture-profile", profile, "--metrics-jsonl", str(metrics_path),
        str(case_dir / "mic.pcm"), str(out_path),
    ])
    rows = [json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(rows, f"missing metrics for {tag}")
    latency_ms = int(rows[0]["algorithmic_latency_ms"])
    latency = latency_ms * RATE // 1000
    latency_frames = latency_ms // 10
    warmup = 40

    tp = fp = fn = tn = 0
    for row in rows[warmup:]:
        frame = int(row["frame"])
        source = frame - latency_frames
        if source < 0 or source >= len(labels):
            continue
        actual = labels[source] != 0
        predicted = int(row["vad_active"]) != 0
        tp += int(actual and predicted)
        fn += int(actual and not predicted)
        fp += int((not actual) and predicted)
        tn += int((not actual) and not predicted)

    result = {
        "profile": profile,
        "latency_ms": latency_ms,
        "vad_recall": tp / max(1, tp + fn),
        "vad_false_positive_rate": fp / max(1, fp + tn),
    }

    if profile == "ns-isolated":
        output = base.read_pcm(out_path)
        mic = base.read_pcm(case_dir / "mic.pcm")
        start = max(latency + warmup * FRAME, latency)
        aligned_out = output[start:]
        aligned_mic = mic[start - latency:len(mic) - latency if latency else len(mic)]
        aligned_clean = clean[start - latency:len(clean) - latency if latency else len(clean)]
        count = min(len(aligned_out), len(aligned_mic), len(aligned_clean))
        aligned_out = aligned_out[:count]
        aligned_mic = aligned_mic[:count]
        aligned_clean = aligned_clean[:count]
        if noise_only:
            attenuation = base.db(base.rms(aligned_mic)) - base.db(base.rms(aligned_out))
            result["noise_attenuation_db"] = attenuation
        else:
            input_sisdr = base.si_sdr(aligned_mic, aligned_clean)
            output_sisdr = base.si_sdr(aligned_out, aligned_clean)
            windows = []
            for off in range(0, max(0, count - RATE + 1), RATE // 2):
                ref = aligned_clean[off:off + RATE]
                if base.rms(ref) < 0.015:
                    continue
                windows.append(base.si_sdr(aligned_out[off:off + RATE], ref) -
                               base.si_sdr(aligned_mic[off:off + RATE], ref))
            result["si_sdr_improvement_db"] = output_sisdr - input_sisdr
            result["worst_window_si_sdr_improvement_db"] = min(windows) if windows else output_sisdr - input_sisdr
    return result


def generate_corpus(contract: dict, output: Path) -> list[dict]:
    data_root = output / "corpus"
    data_root.mkdir(parents=True, exist_ok=True)
    samples = int(float(contract["seconds"]) * RATE)
    cases = []
    for seed in contract["seeds"]:
        speech, labels = base.speech_like(samples, seed)
        for index, scenario in enumerate(contract["scenarios"]):
            noise = base.scenario_noise(scenario, samples, seed + index * 19)
            noise_only = scenario.endswith("-noise")
            case_dir = data_root / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True, exist_ok=True)
            if noise_only:
                mic = noise
                clean = [0.0] * samples
                case_labels = [0] * (samples // FRAME)
            else:
                mic, clean = base.mix_at_snr(speech, noise, float(contract["speech_snr_db"][scenario]))
                case_labels = labels
            base.write_pcm(case_dir / "mic.pcm", mic)
            base.write_pcm(case_dir / "clean.pcm", clean)
            write_json(case_dir / "labels.json", {"frame_samples": FRAME, "labels": case_labels})
            cases.append({
                "seed": seed, "scenario": scenario, "noise_only": noise_only,
                "case_dir": case_dir, "labels": case_labels, "clean": clean,
            })
    return cases


def median(values: list[float]) -> float:
    require(values, "median requires values")
    return float(statistics.median(values))


def summarize(cases: list[dict], threshold: dict) -> dict:
    speech = [c for c in cases if not c["noise_only"]]
    noise = [c for c in cases if c["noise_only"]]

    local_recall = median([c["vad_isolated"]["vad_recall"] for c in speech])
    ns_recall = median([c["ema_ns"]["vad_recall"] for c in speech])
    recall_delta = ns_recall - local_recall
    material_recall = float(threshold["material_vad_recall_delta"])
    if recall_delta <= -material_recall:
        evidence_conclusion = "NS_STAGE_OR_UPSTREAM_EVIDENCE_DEGRADES_VAD"
    elif local_recall < 0.75 and ns_recall < 0.75:
        evidence_conclusion = "LOCAL_VAD_LIMIT_DOMINANT_OR_SHARED_INPUT_LIMIT"
    elif recall_delta >= material_recall:
        evidence_conclusion = "NS_STAGE_IMPROVES_VAD_BUT_REMAINS_DIAGNOSTIC"
    else:
        evidence_conclusion = "NO_MATERIAL_NS_VAD_DELTA"

    burst = [c for c in speech if c["scenario"] == "ns-burst-start-stop-speech"]
    burst_delta = median([
        c["mcra_ns"]["si_sdr_improvement_db"] - c["ema_ns"]["si_sdr_improvement_db"]
        for c in burst
    ])
    all_speech_delta = median([
        c["mcra_ns"]["si_sdr_improvement_db"] - c["ema_ns"]["si_sdr_improvement_db"]
        for c in speech
    ])
    noise_deltas = [
        c["mcra_ns"]["noise_attenuation_db"] - c["ema_ns"]["noise_attenuation_db"]
        for c in noise
    ]
    max_noise_regression = max(0.0, -min(noise_deltas)) if noise_deltas else 0.0
    material_sisdr = float(threshold["material_si_sdr_delta_db"])
    material_noise_reg = float(threshold["material_noise_attenuation_regression_db"])
    if burst_delta >= material_sisdr:
        estimator_conclusion = "MCRA_MATERIALLY_IMPROVES_BURST_SPEECH"
    elif burst_delta <= -material_sisdr:
        estimator_conclusion = "MCRA_MATERIALLY_WORSENS_BURST_SPEECH"
    else:
        estimator_conclusion = "ESTIMATOR_NOT_PRIMARY_FOR_BURST_SPEECH"
    if max_noise_regression > material_noise_reg:
        estimator_tradeoff = "MCRA_HAS_MATERIAL_NOISE_ATTENUATION_REGRESSION"
    else:
        estimator_tradeoff = "NO_MATERIAL_NOISE_ATTENUATION_REGRESSION"

    per_scenario = {}
    for scenario in sorted({c["scenario"] for c in cases}):
        group = [c for c in cases if c["scenario"] == scenario]
        item = {
            "vad_isolated_recall_median": median([c["vad_isolated"]["vad_recall"] for c in group]),
            "ema_ns_vad_recall_median": median([c["ema_ns"]["vad_recall"] for c in group]),
            "mcra_ns_vad_recall_median": median([c["mcra_ns"]["vad_recall"] for c in group]),
            "ema_minus_local_vad_recall_median": median([
                c["ema_ns"]["vad_recall"] - c["vad_isolated"]["vad_recall"] for c in group
            ]),
        }
        if group[0]["noise_only"]:
            item["ema_noise_attenuation_db_median"] = median([c["ema_ns"]["noise_attenuation_db"] for c in group])
            item["mcra_noise_attenuation_db_median"] = median([c["mcra_ns"]["noise_attenuation_db"] for c in group])
            item["mcra_minus_ema_noise_attenuation_db_median"] = median([
                c["mcra_ns"]["noise_attenuation_db"] - c["ema_ns"]["noise_attenuation_db"] for c in group
            ])
        else:
            item["ema_si_sdr_improvement_db_median"] = median([c["ema_ns"]["si_sdr_improvement_db"] for c in group])
            item["mcra_si_sdr_improvement_db_median"] = median([c["mcra_ns"]["si_sdr_improvement_db"] for c in group])
            item["mcra_minus_ema_si_sdr_db_median"] = median([
                c["mcra_ns"]["si_sdr_improvement_db"] - c["ema_ns"]["si_sdr_improvement_db"] for c in group
            ])
        per_scenario[scenario] = item

    return {
        "evidence_path": {
            "local_vad_recall_median": local_recall,
            "ema_ns_vad_recall_median": ns_recall,
            "ema_ns_minus_local_recall": recall_delta,
            "conclusion": evidence_conclusion,
        },
        "estimator": {
            "mcra_minus_ema_burst_si_sdr_db_median": burst_delta,
            "mcra_minus_ema_all_speech_si_sdr_db_median": all_speech_delta,
            "maximum_noise_attenuation_regression_db": max_noise_regression,
            "conclusion": estimator_conclusion,
            "tradeoff": estimator_tradeoff,
        },
        "per_scenario": per_scenario,
    }


def validate_contract(c: dict) -> None:
    require(c.get("schema_version") == 1 and c.get("iteration_id") == "I004", "I004 identity")
    require(c.get("phase") == "root-cause-differential", "I004 differential phase")
    require(c.get("candidate_limit") == 0 and c.get("confirmation_limit") == 0 and c.get("promotion_allowed") is False, "no candidate authority")
    require(c.get("seeds") == [14107, 24107, 34107] and c.get("scenarios") == base.SCENARIOS, "frozen matrix")
    require(c["counterfactuals"]["evidence_path"]["profiles"] == ["vad-isolated", "ns-isolated"], "profile counterfactual")
    require(c["counterfactuals"]["estimator"]["backends"] == ["EMA", "MCRA"], "estimator counterfactual")
    authority = c.get("authority", {})
    require(all(authority.get(k) is False for k in (
        "may_modify_shipping_dsp", "may_tune_ns_floor", "may_add_backend",
        "may_rank_source_candidates", "may_create_candidate", "may_consume_confirmation")), "authority boundary")


def self_test() -> None:
    fake = []
    for seed in (1, 2, 3):
        fake.append({
            "seed": seed, "scenario": "ns-burst-start-stop-speech", "noise_only": False,
            "vad_isolated": {"vad_recall": 0.6},
            "ema_ns": {"vad_recall": 0.4, "si_sdr_improvement_db": -4.0},
            "mcra_ns": {"vad_recall": 0.45, "si_sdr_improvement_db": -2.5},
        })
    # Add one noise scenario so noise tradeoff aggregation is exercised.
    fake.append({
        "seed": 1, "scenario": "ns-burst-start-stop-noise", "noise_only": True,
        "vad_isolated": {"vad_recall": 0.0},
        "ema_ns": {"vad_recall": 0.0, "noise_attenuation_db": 1.0},
        "mcra_ns": {"vad_recall": 0.0, "noise_attenuation_db": 0.8},
    })
    s = summarize(fake, {
        "material_vad_recall_delta": 0.05,
        "material_si_sdr_delta_db": 1.0,
        "material_noise_attenuation_regression_db": 0.5,
    })
    assert s["evidence_path"]["conclusion"] == "NS_STAGE_OR_UPSTREAM_EVIDENCE_DEGRADES_VAD"
    assert s["estimator"]["conclusion"] == "MCRA_MATERIALLY_IMPROVES_BURST_SPEECH"
    print(json.dumps({"result": "PASS", "authority": "root-cause-differential-only"}, sort_keys=True))


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
    validate_contract(contract)
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"exact base drift: {current}")
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    ema = build_processor(root, output, "EMA", current)
    mcra = build_processor(root, output, "MCRA", current)
    processor_sha = {"EMA": sha256(ema), "MCRA": sha256(mcra)}
    generated = generate_corpus(contract, output)
    results = []
    for case in generated:
        common = {k: case[k] for k in ("seed", "scenario", "noise_only")}
        common["vad_isolated"] = score_profile(
            ema, case["case_dir"], "vad-isolated", case["labels"], case["clean"], case["noise_only"], "vad-ema")
        common["ema_ns"] = score_profile(
            ema, case["case_dir"], "ns-isolated", case["labels"], case["clean"], case["noise_only"], "ns-ema")
        common["mcra_ns"] = score_profile(
            mcra, case["case_dir"], "ns-isolated", case["labels"], case["clean"], case["noise_only"], "ns-mcra")
        results.append(common)

    summary = summarize(results, contract["interpretation_thresholds"])
    report = {
        "schema_version": 1,
        "iteration_id": "I004",
        "phase": "root-cause-differential",
        "authority": "development-counterfactual-diagnostic-only",
        "source_sha": current,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "candidate_search_performed": False,
        "source_change_performed": False,
        "ns_floor_tuning_performed": False,
        "new_backend_added": False,
        "processors": processor_sha,
        "cases": results,
        "summary": summary,
        "decision": "ROOT_CAUSE_DIFFERENTIAL_REVIEW_REQUIRED",
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
    }
    write_json(output / "root-cause-report.json", report)
    manifest = {
        str(path.relative_to(output)): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name not in {"SHA256SUMS", "evidence-manifest.json"}
    }
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "source_sha": current, "files": manifest})
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({
        "decision": report["decision"],
        "evidence_path": summary["evidence_path"]["conclusion"],
        "estimator": summary["estimator"]["conclusion"],
        "cases": len(results),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"I004 differential error: {exc}")
