#!/usr/bin/env python3
"""Bounded I004 EMA burst-protection source experiment.

This tool evaluates exactly two pre-registered structural variants in temporary
copies of one exact baseline source tree. It never edits the checked-out source,
does not tune ns_floor, does not search backends or thresholds, and cannot use
confirmation data. Research outcomes (winner, no winner, or multiple eligible)
are evidence, not promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

import i004_ns_nonstationary_diagnostic as diag

RATE = 16000
FRAME = 160
BASELINE_BLOCK = """        speech = ap_clampf((post - 1.4f) * 0.35f, 0.0f, 1.0f);\n        alpha = speech > 0.35f ? 0.995f : 0.92f;\n        noise = alpha * noise + (1.0f - alpha) * power;\n"""
PATCHES = {
    "continuous-confidence-schedule": """        speech = ap_clampf((post - 1.4f) * 0.35f, 0.0f, 1.0f);\n        if (speech >= 0.35f) {\n            alpha = 0.995f;\n        } else {\n            alpha = 0.92f + speech * (0.075f / 0.35f);\n        }\n        noise = alpha * noise + (1.0f - alpha) * power;\n""",
    "rise-only-midconfidence-protection": """        speech = ap_clampf((post - 1.4f) * 0.35f, 0.0f, 1.0f);\n        alpha = speech > 0.35f ? 0.995f : 0.92f;\n        if (power > noise && speech > 0.0f && alpha < 0.97f)\n            alpha = 0.97f;\n        noise = alpha * noise + (1.0f - alpha) * power;\n""",
}


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


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def median(values: list[float]) -> float:
    require(bool(values), "median requires values")
    return float(statistics.median(values))


def copy_exact_source(root: Path, destination: Path) -> None:
    def ignore(path: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name == ".git" or name.startswith("build")}
        ignored.update(name for name in names if name in {"program-evidence", "i004-burst-search-out"})
        return ignored
    shutil.copytree(root, destination, ignore=ignore)


def apply_variant(root: Path, variant: str) -> dict:
    require(variant in PATCHES, f"unknown variant: {variant}")
    path = root / "src/enhance/ap_noise_tracker.c"
    before = path.read_text(encoding="utf-8")
    require(before.count(BASELINE_BLOCK) == 1, "baseline EMA block drift")
    after = before.replace(BASELINE_BLOCK, PATCHES[variant], 1)
    require(after != before and after.count(PATCHES[variant]) == 1, "candidate patch failed")
    path.write_text(after, encoding="utf-8")
    return {
        "variant": variant,
        "path": "src/enhance/ap_noise_tracker.c",
        "base_blob_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "candidate_blob_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "replacement_sha256": hashlib.sha256(PATCHES[variant].encode()).hexdigest(),
    }


def build_tools(root: Path, build_root: Path, source_identity: str) -> tuple[Path, Path]:
    build = build_root / "build"
    run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON",
        f"-DAP_BUILD_SOURCE_REVISION={source_identity}",
    ])
    run_checked(["cmake", "--build", str(build), "--target", "ap_process_pcm", "--parallel"])
    probe = build / "ns_probability_probe"
    run_checked([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(root / "include"), "-I" + str(build / "generated"),
        str(root / "validation/tools/ns_probability_probe.c"),
        str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe),
    ])
    return build / "ap_process_pcm", probe


def build_inputs(contract: dict, output: Path) -> list[dict]:
    root = output / "inputs"
    root.mkdir(parents=True, exist_ok=True)
    samples = int(float(contract["seconds"]) * RATE)
    cases: list[dict] = []
    for seed in contract["development_seeds"]:
        speech, labels = diag.speech_like(samples, seed)
        for index, scenario in enumerate(contract["scenarios"]):
            noise = diag.scenario_noise(scenario, samples, seed + index * 19)
            noise_only = scenario.endswith("-noise")
            case_dir = root / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True, exist_ok=True)
            if noise_only:
                mic = noise
                clean = [0.0] * samples
                case_labels = [0] * (samples // FRAME)
            else:
                mic, clean = diag.mix_at_snr(speech, noise, float(contract["speech_snr_db"][scenario]))
                case_labels = labels
            diag.write_pcm(case_dir / "mic.pcm", mic)
            diag.write_pcm(case_dir / "clean.pcm", clean)
            write_json(case_dir / "labels.json", {"frame_samples": FRAME, "labels": case_labels})
            cases.append({
                "seed": seed,
                "scenario": scenario,
                "noise_only": noise_only,
                "input_dir": case_dir,
                "labels": case_labels,
                "clean": clean,
            })
    require(len(cases) == len(contract["development_seeds"]) * len(contract["scenarios"]),
            "development matrix size")
    return cases


def evaluate_variant(name: str, processor: Path, probe: Path, inputs: list[dict], output: Path,
                     diagnostic_flags: dict) -> list[dict]:
    results: list[dict] = []
    for item in inputs:
        case_dir = output / name / f"seed-{item['seed']}" / item["scenario"]
        case_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("mic.pcm", "clean.pcm", "labels.json"):
            shutil.copy2(item["input_dir"] / filename, case_dir / filename)
        metrics = diag.evaluate_case(
            processor, probe, case_dir, item["labels"], item["clean"],
            item["noise_only"], diagnostic_flags,
        )
        results.append({
            "seed": item["seed"],
            "scenario": item["scenario"],
            "noise_only": item["noise_only"],
            "metrics": metrics,
        })
    return results


def scenario_medians(cases: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for scenario in sorted({item["scenario"] for item in cases}):
        group = [item for item in cases if item["scenario"] == scenario]
        noise_only = group[0]["noise_only"]
        if noise_only:
            result[scenario] = {
                "noise_only": True,
                "noise_attenuation_db": median([x["metrics"]["noise_attenuation_db"] for x in group]),
                "vad_recall": median([x["metrics"].get("vad_recall", 0.0) for x in group]),
                "clip_fraction": max(x["metrics"]["clip_fraction"] for x in group),
            }
        else:
            result[scenario] = {
                "noise_only": False,
                "si_sdr_improvement_db": median([x["metrics"]["si_sdr_improvement_db"] for x in group]),
                "worst_window_si_sdr_improvement_db": median([
                    x["metrics"]["worst_window_si_sdr_improvement_db"] for x in group
                ]),
                "vad_recall": median([x["metrics"]["vad_recall"] for x in group]),
                "vad_false_positive_rate": median([x["metrics"]["vad_false_positive_rate"] for x in group]),
                "clip_fraction": max(x["metrics"]["clip_fraction"] for x in group),
            }
    return result


def run_stage_regression(processor: Path, source_root: Path, seeds: list[int], output: Path) -> dict:
    reports: dict[str, str] = {}
    for seed in seeds:
        root = output / str(seed)
        root.mkdir(parents=True, exist_ok=True)
        corpus = root / "corpus"
        run_checked([
            "python3", str(source_root / "validation/tools/build_stage_validation_corpus.py"),
            "--output", str(corpus), "--seed", str(seed),
        ], source_root)
        report = root / "report.json"
        evidence = root / "evidence.json"
        run_checked([
            "python3", str(source_root / "validation/tools/run_validation.py"),
            "--corpus", str(corpus / "corpus.json"),
            "--policy", str(source_root / "validation/policies/validation-smoke.json"),
            "--dataset-lock", str(source_root / "validation/datasets.lock.json"),
            "--processor", str(processor),
            "--output", str(report),
            "--evidence-manifest", str(evidence),
        ], source_root)
        value = load_json(report)
        reports[str(seed)] = value.get("validation_result", "MISSING")
    return {"seeds": reports, "all_pass": all(value == "PASS" for value in reports.values())}


def eligibility(base_medians: dict, candidate_medians: dict, stage: dict, gates: dict) -> dict:
    failures: list[str] = []
    burst = "ns-burst-start-stop-speech"
    burst_delta = candidate_medians[burst]["si_sdr_improvement_db"] - base_medians[burst]["si_sdr_improvement_db"]
    if burst_delta < float(gates["min_burst_speech_si_sdr_delta_db"]):
        failures.append("burst_speech_improvement")

    for scenario, baseline in base_medians.items():
        candidate = candidate_medians[scenario]
        if baseline["noise_only"]:
            delta = candidate["noise_attenuation_db"] - baseline["noise_attenuation_db"]
            if delta < -float(gates["max_noise_attenuation_regression_db"]):
                failures.append(f"noise_attenuation:{scenario}")
        else:
            if scenario != burst:
                delta = candidate["si_sdr_improvement_db"] - baseline["si_sdr_improvement_db"]
                if delta < -float(gates["max_nonburst_speech_si_sdr_regression_db"]):
                    failures.append(f"speech_si_sdr:{scenario}")
            recall_delta = candidate["vad_recall"] - baseline["vad_recall"]
            if recall_delta < -float(gates["max_vad_recall_regression"]):
                failures.append(f"vad_recall:{scenario}")
            if candidate["clip_fraction"] > baseline["clip_fraction"] + float(gates["max_clip_fraction_increase"]):
                failures.append(f"clip_fraction:{scenario}")
    if not stage["all_pass"]:
        failures.append("stage_regression")
    return {
        "eligible": not failures,
        "failures": failures,
        "burst_speech_si_sdr_delta_db": burst_delta,
    }


def validate_contract(contract: dict) -> None:
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I004", "contract identity")
    require(contract.get("phase") == "bounded-source-candidate-search", "phase")
    require(contract.get("root_cause_id") == "ema-burst-start-stop-speech-protection", "root cause")
    require(contract.get("candidate_limit") == 2 and contract.get("confirmation_limit") == 0,
            "candidate/confirmation budget")
    require(contract.get("promotion_allowed") is False and contract.get("data_role") == "development-exposed",
            "authority")
    require(contract.get("development_seeds") == [14107, 24107, 34107], "development seeds")
    require(contract.get("protection_regression_seeds") == [1307, 2307, 3307], "regression seeds")
    require(contract.get("candidate_variants") == list(PATCHES), "frozen candidate variants")
    require(contract.get("winner_policy") == "exactly-one-eligible", "winner policy")
    authority = contract.get("authority", {})
    require(all(authority.get(key) is False for key in (
        "may_edit_checked_out_source", "may_tune_ns_floor", "may_search_backends",
        "may_add_candidate", "may_consume_confirmation", "may_promote_release",
    )), "source experiment authority")


def self_test() -> None:
    require(len(PATCHES) == 2, "exactly two candidates")
    require(all(BASELINE_BLOCK not in replacement for replacement in PATCHES.values()), "patch must replace baseline")
    fake_base = {
        "ns-burst-start-stop-speech": {"noise_only": False, "si_sdr_improvement_db": -4.0, "vad_recall": 0.3, "clip_fraction": 0.0},
        "ns-motor-ramp-speech": {"noise_only": False, "si_sdr_improvement_db": 4.0, "vad_recall": 0.3, "clip_fraction": 0.0},
        "ns-motor-ramp-noise": {"noise_only": True, "noise_attenuation_db": 5.0, "vad_recall": 0.0, "clip_fraction": 0.0},
    }
    good = json.loads(json.dumps(fake_base))
    good["ns-burst-start-stop-speech"]["si_sdr_improvement_db"] = -2.5
    result = eligibility(fake_base, good, {"all_pass": True}, {
        "min_burst_speech_si_sdr_delta_db": 1.0,
        "max_nonburst_speech_si_sdr_regression_db": 0.5,
        "max_noise_attenuation_regression_db": 0.5,
        "max_vad_recall_regression": 0.03,
        "max_clip_fraction_increase": 0.002,
    })
    assert result["eligible"]
    print(json.dumps({"result": "PASS", "candidates": list(PATCHES)}, sort_keys=True))


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

    inputs = build_inputs(contract, output)
    build_base = output / "tools-baseline"
    base_processor, base_probe = build_tools(root, build_base, current)
    baseline_cases = evaluate_variant("baseline", base_processor, base_probe, inputs, output / "dynamic", contract["diagnostic_flags"])
    baseline_medians = scenario_medians(baseline_cases)

    candidates: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ap-i004-burst-candidates-") as temporary:
        temp_root = Path(temporary)
        for variant in contract["candidate_variants"]:
            candidate_root = temp_root / variant
            copy_exact_source(root, candidate_root)
            patch = apply_variant(candidate_root, variant)
            tools = output / f"tools-{variant}"
            processor, probe = build_tools(candidate_root, tools, f"{current}:{variant}")
            dynamic = evaluate_variant(variant, processor, probe, inputs, output / "dynamic", contract["diagnostic_flags"])
            medians = scenario_medians(dynamic)
            stage = run_stage_regression(
                processor, candidate_root, contract["protection_regression_seeds"],
                output / "stage-regression" / variant,
            )
            eligible = eligibility(baseline_medians, medians, stage, contract["gates"])
            candidates.append({
                "variant": variant,
                "patch": patch,
                "processor_sha256": sha256(processor),
                "scenario_medians": medians,
                "stage_regression": stage,
                "eligibility": eligible,
            })

    eligible_names = [item["variant"] for item in candidates if item["eligibility"]["eligible"]]
    if len(eligible_names) == 1:
        decision = "FREEZE_UNIQUE_CANDIDATE"
        winner = eligible_names[0]
    elif not eligible_names:
        decision = "KEEP_BASELINE_NO_ELIGIBLE_CANDIDATE"
        winner = None
    else:
        decision = "INCONCLUSIVE_MULTIPLE_ELIGIBLE_CANDIDATES"
        winner = None

    report = {
        "schema_version": 1,
        "iteration_id": "I004",
        "root_cause_id": contract["root_cause_id"],
        "phase": contract["phase"],
        "authority": "bounded-development-source-experiment-only",
        "source_sha": current,
        "candidate_limit": 2,
        "confirmation_limit": 0,
        "candidate_variants_consumed": 2,
        "candidate_search_performed": True,
        "ns_floor_tuning_performed": False,
        "backend_search_performed": False,
        "checked_out_source_modified": False,
        "baseline_processor_sha256": sha256(base_processor),
        "baseline_scenario_medians": baseline_medians,
        "candidates": candidates,
        "eligible_candidates": eligible_names,
        "decision": decision,
        "winner": winner,
        "promotion_allowed": False,
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "candidate-search-result.json", report)
    print(json.dumps({"decision": decision, "winner": winner, "eligible": eligible_names}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"I004 burst candidate search error: {exc}")
