#!/usr/bin/env python3
"""Candidate-zero I007 BF wind/reverb root-cause differential on exact main."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import i007_bf_health_corpus as corpus_builder


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_checked(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=str(cwd) if cwd else None, check=True)


def validate_shipping_source(root: Path, contract: dict) -> dict:
    text = (root / "src/frontend/ap_beamformer.c").read_text(encoding="utf-8")
    expected = {
        "#define AP_BF_FALLBACK_ENTER_COHERENCE 0.980f": contract["shipping_constants"]["fallback_enter_coherence"],
        "#define AP_BF_FALLBACK_ENTER_RATIO 0.45f": contract["shipping_constants"]["fallback_enter_ratio"],
        "#define AP_BF_HARD_FAULT_MIN_RATIO 0.08f": contract["shipping_constants"]["hard_fault_min_ratio"],
        "#define AP_BF_HARD_FAULT_MAX_RATIO 0.28f": contract["shipping_constants"]["hard_fault_max_ratio"],
        "#define AP_BF_HARD_FAULT_ROUGHNESS_RATIO 0.18f": contract["shipping_constants"]["hard_fault_roughness_ratio"],
    }
    for needle in expected:
        require(text.count(needle) == 1, f"shipping BF constant drift: {needle}")
    require("coherence < AP_BF_FALLBACK_ENTER_COHERENCE &&" in text and
            "ratio < AP_BF_FALLBACK_ENTER_RATIO" in text,
            "shipping severe admission conjunction drift")
    require("s->fallback_strong_channel = energy_strong_channel;" in text,
            "shipping soft fallback energy-strong selection drift")
    require("const uint32_t hard_target_channel = 1u - energy_strong_channel;" in text,
            "shipping hard fallback target drift")
    return {"source_sha256": sha256(root / "src/frontend/ap_beamformer.c"),
            "constants_bound": True, "admission_conjunction_bound": True,
            "soft_selection_energy_strong_bound": True, "hard_target_energy_weak_bound": True}


def validate_contract(contract: dict, baseline: dict, root: Path) -> None:
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I007",
            "I007 root-cause identity")
    require(contract.get("phase") == "bf-health-root-cause-differential", "I007 root-cause phase")
    require(contract.get("base_sha") == baseline.get("base_sha"), "root-cause/baseline exact base")
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I007 root-cause exact base drift: {current}")
    require(contract.get("candidate_limit") == 0 and contract.get("confirmation_limit") == 0 and
            contract.get("promotion_allowed") is False and
            contract.get("shipping_source_change_allowed") is False, "candidate-zero authority")
    require(contract.get("seeds") == baseline.get("seeds") == [1707, 2707, 3707], "same exposed seeds")
    require(contract.get("frontends") == baseline.get("frontends") == ["bf-only", "hpf-bf"],
            "same frontend partitions")
    require(set(contract.get("scenarios", [])) == {
        "soft-wind-ch0", "soft-wind-ch1", "asymmetric-reverb-ch0", "asymmetric-reverb-ch1"},
        "frozen root-cause scenario subset")
    require(all(value is False for value in contract["authority"].values()), "root-cause authority false")
    require(contract["source_reuse"]["baseline_development_data_already_exposed"] is True and
            contract["source_reuse"]["may_be_independent_confirmation"] is False and
            contract["source_reuse"]["may_be_promotion_data"] is False,
            "exposed source cannot become independent")
    require(contract.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")


def build_probe(root: Path, output: Path) -> Path:
    build = output / "build"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked(["cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                 "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON",
                 f"-DAP_BUILD_SOURCE_REVISION={revision}"])
    run_checked(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"])
    probe = build / "i007_bf_health_root_cause_probe"
    run_checked(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(root / "src"), "-I" + str(root / "include"),
                 "-I" + str(build / "generated"),
                 str(root / "tests/validation/i007_bf_health_root_cause_probe.c"),
                 str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe)])
    return probe


def load_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fraction(rows: list[dict], predicate) -> float:
    return sum(bool(predicate(row)) for row in rows) / max(1, len(rows))


def update_rows(rows: list[dict]) -> list[dict]:
    updates: list[dict] = []
    previous = None
    for row in rows:
        current = int(row["score_updates"])
        if previous is None or current != previous:
            updates.append(row)
        previous = current
    return updates


def classify_case(rows: list[dict], scenario: str, reliable_channel: int,
                  contract: dict, start: int, end: int) -> dict:
    window = rows[start:end]
    updates = update_rows(window)
    require(len(updates) >= int(contract["preconditions"]["min_window_updates"]),
            "too few BF score updates")
    faulty = 1 - reliable_channel
    c = contract["shipping_constants"]
    coh_gate = float(c["fallback_enter_coherence"])
    ratio_gate = float(c["fallback_enter_ratio"])
    hard_min = float(c["hard_fault_min_ratio"])
    hard_max = float(c["hard_fault_max_ratio"])
    rough_gate = float(c["hard_fault_roughness_ratio"])

    def severe(row: dict) -> bool:
        return float(row["best_smoothed_coherence"]) < coh_gate and float(row["energy_ratio"]) < ratio_gate

    def hard_proxy(row: dict) -> bool:
        strong = int(row["energy_strong_channel"])
        strong_r = float(row[f"roughness{strong}"])
        weak_r = float(row[f"roughness{1 - strong}"])
        ratio = float(row["energy_ratio"])
        return severe(row) and hard_min < ratio < hard_max and strong_r < rough_gate * max(weak_r, 1.0e-12)

    metrics = {
        "updates": len(updates),
        "fallback_fraction": fraction(window, lambda r: int(r["fallback_active"]) != 0),
        "hard_fault_fraction": fraction(window, lambda r: int(r["fallback_hard_fault"]) != 0),
        "coherence_below_enter_fraction": fraction(updates, lambda r: float(r["best_smoothed_coherence"]) < coh_gate),
        "ratio_below_enter_fraction": fraction(updates, lambda r: float(r["energy_ratio"]) < ratio_gate),
        "severe_proxy_fraction": fraction(updates, severe),
        "energy_strong_is_faulty_fraction": fraction(updates, lambda r: int(r["energy_strong_channel"]) == faulty),
        "hard_contamination_proxy_fraction": fraction(updates, hard_proxy),
        "fallback_selected_faulty_fraction": fraction(
            updates, lambda r: int(r["fallback_active"]) != 0 and int(r["fallback_strong_channel"]) == faulty),
        "fallback_selected_reliable_fraction": fraction(
            updates, lambda r: int(r["fallback_active"]) != 0 and int(r["fallback_strong_channel"]) == reliable_channel),
        "soft_fallback_wrong_target_fraction": fraction(
            updates, lambda r: int(r["fallback_active"]) != 0 and int(r["fallback_hard_fault"]) == 0 and
                              int(r["fallback_strong_channel"]) == faulty and
                              int(r["energy_strong_channel"]) == faulty),
        "hard_fallback_correct_target_fraction": fraction(
            updates, lambda r: int(r["fallback_hard_fault"]) != 0 and
                              int(r["fallback_strong_channel"]) == reliable_channel),
        "energy_ratio_min": min(float(r["energy_ratio"]) for r in updates),
        "energy_ratio_median": sorted(float(r["energy_ratio"]) for r in updates)[len(updates) // 2],
        "coherence_min": min(float(r["best_smoothed_coherence"]) for r in updates),
        "coherence_median": sorted(float(r["best_smoothed_coherence"]) for r in updates)[len(updates) // 2],
    }

    if scenario.startswith("soft-wind"):
        explained = (metrics["fallback_fraction"] >= float(contract["preconditions"]["min_wind_fallback_fraction"]) and
                     metrics["energy_strong_is_faulty_fraction"] >= 0.80 and
                     metrics["fallback_selected_faulty_fraction"] >= 0.05)
        mechanism = "fallback-enters-but-energy-strong-selection-exposes-wind-contaminated-channel"
    else:
        explained = (metrics["fallback_fraction"] <=
                     float(contract["preconditions"]["max_reverb_fallback_fraction_for_admission_analysis"]) and
                     metrics["ratio_below_enter_fraction"] <= 0.05 and
                     metrics["severe_proxy_fraction"] <= 0.05)
        mechanism = "fallback-admission-blocked-by-energy-ratio-conjunction-on-equal-energy-reverb"
    return {"metrics": metrics, "explained": bool(explained), "mechanism": mechanism}


def self_test() -> None:
    rows = [
        {"score_updates": i + 1, "best_smoothed_coherence": 0.5, "energy_ratio": 0.2,
         "energy_strong_channel": 0, "roughness0": 0.01, "roughness1": 0.2,
         "fallback_active": 1, "fallback_hard_fault": 0, "fallback_strong_channel": 0}
        for i in range(80)
    ]
    contract = {"preconditions": {"min_window_updates": 60, "min_wind_fallback_fraction": 0.8,
                                   "max_reverb_fallback_fraction_for_admission_analysis": 0.1},
                "shipping_constants": {"fallback_enter_coherence": 0.98, "fallback_enter_ratio": 0.45,
                                       "hard_fault_min_ratio": 0.08, "hard_fault_max_ratio": 0.28,
                                       "hard_fault_roughness_ratio": 0.18}}
    result = classify_case(rows, "soft-wind-ch0", 1, contract, 0, 80)
    assert result["explained"] and result["metrics"]["energy_strong_is_faulty_fraction"] == 1.0
    print(json.dumps({"result": "PASS", "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--baseline-contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test(); return 0
    require(args.contract is not None and args.baseline_contract is not None and args.output is not None,
            "contract/baseline-contract/output required")
    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    baseline = load_json(args.baseline_contract)
    validate_contract(contract, baseline, root)
    shipping = validate_shipping_source(root, contract)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    probe = build_probe(root, output)

    cases: list[dict] = []
    input_failures: list[dict] = []
    unexplained: list[dict] = []
    start_frame, end_frame = [int(v) for v in baseline["fault_window_frames"]]
    start = start_frame + 40
    end = end_frame - 20
    for seed in contract["seeds"]:
        corpus_root = output / "corpus" / f"seed-{seed}"
        corpus = corpus_builder.build(corpus_root, baseline, int(seed))
        selected = [case for case in corpus["cases"] if case["scenario"] in contract["scenarios"]]
        require(len(selected) == 4, "I007 root-cause corpus subset")
        for case in selected:
            reliable = int(case["reliable_channel"])
            for frontend in contract["frontends"]:
                case_dir = output / "traces" / f"seed-{seed}" / frontend / str(case["case_id"])
                case_dir.mkdir(parents=True, exist_ok=True)
                trace_path = case_dir / "trace.jsonl"
                try:
                    run_checked([str(probe), "--sample-rate", str(baseline["sample_rate_hz"]),
                                 "--spacing-mm", str(baseline["mic_spacing_mm"]),
                                 "--frontend", frontend,
                                 str(corpus_root / str(case["mic_audio"])), str(trace_path)])
                    rows = load_trace(trace_path)
                    require(len(rows) == int(case["frames"]), "root-cause trace frame count")
                    classified = classify_case(rows, str(case["scenario"]), reliable,
                                               contract, start, end)
                except (ValueError, OSError, subprocess.CalledProcessError) as exc:
                    classified = {"metrics": {"precondition_error": str(exc)},
                                  "explained": False, "mechanism": "input-invalid"}
                    input_failures.append({"seed": seed, "scenario": case["scenario"],
                                           "frontend": frontend, "error": str(exc)})
                row = {"seed": seed, "scenario": case["scenario"], "frontend": frontend,
                       "reliable_channel": reliable, **classified}
                cases.append(row)
                if not classified["explained"] and classified["mechanism"] != "input-invalid":
                    unexplained.append({"seed": seed, "scenario": case["scenario"],
                                        "frontend": frontend, "metrics": classified["metrics"]})

    if input_failures:
        decision = "INPUT_INVALID_REVIEW_REQUIRED"
    elif unexplained:
        decision = "ROOT_CAUSE_PARTIAL_REVIEW_REQUIRED"
    else:
        decision = "ROOT_CAUSE_EXPLAINED_REVIEW_REQUIRED"
    report = {
        "schema_version": 1,
        "iteration_id": "I007",
        "phase": "bf-health-root-cause-differential",
        "root_cause_id": contract["root_cause_id"],
        "source_sha": contract["base_sha"],
        "authority": "candidate-zero-mechanism-attribution-only",
        "shipping_source_contract": shipping,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "candidate_search_performed": False,
        "threshold_tuning_performed": False,
        "promotion_allowed": False,
        "cases": cases,
        "aggregate": {
            "partitions": len(cases),
            "explained_partitions": sum(bool(case["explained"]) for case in cases),
            "unexplained_partitions": len(unexplained),
            "input_failure_partitions": len(input_failures),
        },
        "unexplained": unexplained,
        "input_failures": input_failures,
        "decision": decision,
        "next_step": "review wind selection and reverb admission as separate structural candidate domains",
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "root-cause-result.json", report)
    manifest = {str(path.relative_to(output)): sha256(path) for path in sorted(output.rglob("*"))
                if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1,
                                                   "source_sha": contract["base_sha"],
                                                   "files": manifest})
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({"decision": decision, "partitions": len(cases),
                      "explained": report["aggregate"]["explained_partitions"],
                      "unexplained": len(unexplained), "input_failures": len(input_failures),
                      "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"I007 BF health root-cause error: {exc}")
