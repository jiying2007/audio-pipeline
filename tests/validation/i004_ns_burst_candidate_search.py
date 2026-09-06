#!/usr/bin/env python3
"""Bounded I004 EMA burst-protection source experiment.

Evaluate exactly two pre-registered structural EMA variants in temporary copies
of one exact baseline source tree. This is Development/selection evidence only:
no ns_floor tuning, backend search, confirmation use, promotion, or mutation of
the checked-out source is permitted.
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


def run(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def median(values: list[float]) -> float:
    require(bool(values), "median requires values")
    return float(statistics.median(values))


def copy_exact_source(root: Path, destination: Path) -> None:
    # Worktree sources must be copied byte-for-byte except Git metadata. Do not
    # pattern-ignore names such as build_info.c: that is a real source file.
    def ignore(_path: str, names: list[str]) -> set[str]:
        return {name for name in names if name == ".git"}
    shutil.copytree(root, destination, ignore=ignore)
    require((destination / "examples/build_info.c").is_file(), "exact source copy lost build_info.c")


def apply_variant(root: Path, variant: str) -> dict:
    require(variant in PATCHES, f"unknown variant: {variant}")
    path = root / "src/enhance/ap_noise_tracker.c"
    before = path.read_text(encoding="utf-8")
    require(before.count(BASELINE_BLOCK) == 1, "baseline EMA block drift")
    after = before.replace(BASELINE_BLOCK, PATCHES[variant], 1)
    path.write_text(after, encoding="utf-8")
    return {
        "variant": variant,
        "path": "src/enhance/ap_noise_tracker.c",
        "base_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "replacement_sha256": hashlib.sha256(PATCHES[variant].encode()).hexdigest(),
    }


def build_tools(root: Path, build_root: Path, identity: str) -> tuple[Path, Path]:
    build = build_root / "build"
    run([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON",
        f"-DAP_BUILD_SOURCE_REVISION={identity}",
    ])
    run(["cmake", "--build", str(build), "--target", "ap_process_pcm", "--parallel"])
    probe = build / "ns_probability_probe"
    run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(root / "include"), "-I" + str(build / "generated"),
        str(root / "validation/tools/ns_probability_probe.c"),
        str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe),
    ])
    return build / "ap_process_pcm", probe


def build_inputs(contract: dict, output: Path) -> list[dict]:
    input_root = output / "inputs"
    samples = int(float(contract["seconds"]) * RATE)
    cases: list[dict] = []
    for seed in contract["development_seeds"]:
        speech, labels = diag.speech_like(samples, seed)
        for index, scenario in enumerate(contract["scenarios"]):
            noise = diag.scenario_noise(scenario, samples, seed + index * 19)
            noise_only = scenario.endswith("-noise")
            case_dir = input_root / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True, exist_ok=True)
            if noise_only:
                mic, clean, case_labels = noise, [0.0] * samples, [0] * (samples // FRAME)
            else:
                mic, clean = diag.mix_at_snr(speech, noise, float(contract["speech_snr_db"][scenario]))
                case_labels = labels
            diag.write_pcm(case_dir / "mic.pcm", mic)
            diag.write_pcm(case_dir / "clean.pcm", clean)
            write_json(case_dir / "labels.json", {"frame_samples": FRAME, "labels": case_labels})
            cases.append({
                "seed": seed, "scenario": scenario, "noise_only": noise_only,
                "input_dir": case_dir, "labels": case_labels, "clean": clean,
            })
    require(len(cases) == 24, "expected frozen 24-case development matrix")
    return cases


def evaluate(name: str, processor: Path, probe: Path, inputs: list[dict], output: Path,
             flags: dict) -> list[dict]:
    rows: list[dict] = []
    for item in inputs:
        case_dir = output / name / f"seed-{item['seed']}" / item["scenario"]
        case_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("mic.pcm", "clean.pcm", "labels.json"):
            shutil.copy2(item["input_dir"] / filename, case_dir / filename)
        metrics = diag.evaluate_case(
            processor, probe, case_dir, item["labels"], item["clean"], item["noise_only"], flags
        )
        rows.append({"seed": item["seed"], "scenario": item["scenario"],
                     "noise_only": item["noise_only"], "metrics": metrics})
    return rows


def medians(rows: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for scenario in sorted({row["scenario"] for row in rows}):
        group = [row for row in rows if row["scenario"] == scenario]
        noise_only = group[0]["noise_only"]
        if noise_only:
            result[scenario] = {
                "noise_only": True,
                "noise_attenuation_db": median([row["metrics"]["noise_attenuation_db"] for row in group]),
                "clip_fraction": max(row["metrics"]["clip_fraction"] for row in group),
            }
        else:
            result[scenario] = {
                "noise_only": False,
                "si_sdr_improvement_db": median([row["metrics"]["si_sdr_improvement_db"] for row in group]),
                "worst_window_si_sdr_improvement_db": median([
                    row["metrics"]["worst_window_si_sdr_improvement_db"] for row in group
                ]),
                "vad_recall": median([row["metrics"]["vad_recall"] for row in group]),
                "clip_fraction": max(row["metrics"]["clip_fraction"] for row in group),
            }
    return result


def stage_regression(processor: Path, source_root: Path, seeds: list[int], output: Path) -> dict:
    results: dict[str, str] = {}
    for seed in seeds:
        root = output / str(seed)
        corpus = root / "corpus"
        root.mkdir(parents=True, exist_ok=True)
        run(["python3", str(source_root / "validation/tools/build_stage_validation_corpus.py"),
             "--output", str(corpus), "--seed", str(seed)], source_root)
        report = root / "report.json"
        run([
            "python3", str(source_root / "validation/tools/run_validation.py"),
            "--corpus", str(corpus / "corpus.json"),
            "--policy", str(source_root / "validation/policies/validation-smoke.json"),
            "--dataset-lock", str(source_root / "validation/datasets.lock.json"),
            "--processor", str(processor), "--output", str(report),
            "--evidence-manifest", str(root / "evidence.json"),
        ], source_root)
        results[str(seed)] = load_json(report).get("validation_result", "MISSING")
    return {"seeds": results, "all_pass": all(value == "PASS" for value in results.values())}


def eligibility(base: dict, candidate: dict, stage: dict, gates: dict) -> dict:
    failures: list[str] = []
    burst = "ns-burst-start-stop-speech"
    burst_delta = candidate[burst]["si_sdr_improvement_db"] - base[burst]["si_sdr_improvement_db"]
    if burst_delta < float(gates["min_burst_speech_si_sdr_delta_db"]):
        failures.append("burst_speech_improvement")
    for scenario, baseline in base.items():
        trial = candidate[scenario]
        if baseline["noise_only"]:
            if trial["noise_attenuation_db"] - baseline["noise_attenuation_db"] < -float(gates["max_noise_attenuation_regression_db"]):
                failures.append(f"noise_attenuation:{scenario}")
        else:
            if scenario != burst and trial["si_sdr_improvement_db"] - baseline["si_sdr_improvement_db"] < -float(gates["max_nonburst_speech_si_sdr_regression_db"]):
                failures.append(f"speech_si_sdr:{scenario}")
            if trial["vad_recall"] - baseline["vad_recall"] < -float(gates["max_vad_recall_regression"]):
                failures.append(f"vad_recall:{scenario}")
            if trial["clip_fraction"] > baseline["clip_fraction"] + float(gates["max_clip_fraction_increase"]):
                failures.append(f"clip_fraction:{scenario}")
    if not stage["all_pass"]:
        failures.append("stage_regression")
    return {"eligible": not failures, "failures": failures,
            "burst_speech_si_sdr_delta_db": burst_delta}


def validate_contract(c: dict) -> None:
    require(c.get("schema_version") == 1 and c.get("iteration_id") == "I004", "contract identity")
    require(c.get("phase") == "bounded-source-candidate-search", "phase")
    require(c.get("root_cause_id") == "ema-burst-start-stop-speech-protection", "root cause")
    require(c.get("candidate_limit") == 2 and c.get("confirmation_limit") == 0, "budget")
    require(c.get("development_seeds") == [14107, 24107, 34107], "development seeds")
    require(c.get("protection_regression_seeds") == [1307, 2307, 3307], "regression seeds")
    require(c.get("candidate_variants") == list(PATCHES), "candidate variants")
    require(c.get("winner_policy") == "exactly-one-eligible", "winner policy")
    require(c.get("promotion_allowed") is False, "promotion authority")
    require(all(value is False for value in c.get("authority", {}).values()), "authority must be false")


def self_test() -> None:
    require(len(PATCHES) == 2, "exactly two candidates")
    require("build_info.c" not in {"build", "build-stage"}, "copy guard")
    print(json.dumps({"result": "PASS", "candidates": list(PATCHES)}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
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
    require(current == contract["base_sha"], f"exact base drift: {current}")
    output = args.output.resolve()
    require(not output.exists() or not any(output.iterdir()), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)

    inputs = build_inputs(contract, output)
    base_processor, base_probe = build_tools(root, output / "tools-baseline", current)
    base_rows = evaluate("baseline", base_processor, base_probe, inputs, output / "dynamic", contract["diagnostic_flags"])
    base_medians = medians(base_rows)

    candidates: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="ap-i004-burst-") as temporary:
        for variant in contract["candidate_variants"]:
            candidate_root = Path(temporary) / variant
            copy_exact_source(root, candidate_root)
            patch = apply_variant(candidate_root, variant)
            processor, probe = build_tools(candidate_root, output / f"tools-{variant}", f"{current}:{variant}")
            rows = evaluate(variant, processor, probe, inputs, output / "dynamic", contract["diagnostic_flags"])
            candidate_medians = medians(rows)
            stage = stage_regression(processor, candidate_root, contract["protection_regression_seeds"], output / "stage-regression" / variant)
            gate = eligibility(base_medians, candidate_medians, stage, contract["gates"])
            candidates.append({"variant": variant, "patch": patch,
                               "processor_sha256": sha256(processor),
                               "scenario_medians": candidate_medians,
                               "stage_regression": stage, "eligibility": gate})

    eligible = [item["variant"] for item in candidates if item["eligibility"]["eligible"]]
    if len(eligible) == 1:
        decision, winner = "FREEZE_UNIQUE_CANDIDATE", eligible[0]
    elif not eligible:
        decision, winner = "KEEP_BASELINE_NO_ELIGIBLE_CANDIDATE", None
    else:
        decision, winner = "INCONCLUSIVE_MULTIPLE_ELIGIBLE_CANDIDATES", None
    write_json(output / "candidate-search-result.json", {
        "schema_version": 1, "iteration_id": "I004", "root_cause_id": contract["root_cause_id"],
        "phase": contract["phase"], "authority": "bounded-development-source-experiment-only",
        "source_sha": current, "candidate_limit": 2, "confirmation_limit": 0,
        "candidate_variants_consumed": 2, "candidate_search_performed": True,
        "ns_floor_tuning_performed": False, "backend_search_performed": False,
        "checked_out_source_modified": False, "baseline_processor_sha256": sha256(base_processor),
        "baseline_scenario_medians": base_medians, "candidates": candidates,
        "eligible_candidates": eligible, "decision": decision, "winner": winner,
        "promotion_allowed": False, "product_qualification": "DEFERRED_BY_SCOPE"
    })
    print(json.dumps({"decision": decision, "winner": winner, "eligible": eligible}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"I004 burst candidate search error: {exc}")
