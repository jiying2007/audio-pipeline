#!/usr/bin/env python3
"""I006 candidate-zero AGC root-cause differential.

This is mechanism evidence only. It replays the already-exposed I006 Development
seeds on the exact reviewed main SHA, observes internal activity/AGC state, and
classifies the two reviewed gaps without changing shipping DSP, tuning any
parameter, ranking a candidate, or consuming confirmation data.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from pathlib import Path

import i004_ns_nonstationary_diagnostic as synth
import i006_agc_residual_floor_baseline as baseline

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


def build_probe(root: Path, output: Path) -> Path:
    build = output / "build-root-cause"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    run_checked([
        "cmake", "-S", str(root), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
        "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON", f"-DAP_BUILD_SOURCE_REVISION={revision}",
    ])
    run_checked(["cmake", "--build", str(build), "--target", "audio_pipeline", "--parallel"])
    probe = build / "i006_agc_root_cause_probe"
    run_checked([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(root / "include"), "-I" + str(root / "src"), "-I" + str(build / "generated"),
        str(root / "tests/validation/i006_agc_root_cause_probe.c"),
        str(build / "libaudio_pipeline.a"), "-lm", "-o", str(probe),
    ])
    return probe


def validate_contract(contract: dict, baseline_contract: dict, root: Path) -> dict:
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I006", "I006 identity")
    require(contract.get("phase") == "root-cause-differential", "I006 differential phase")
    require(contract.get("root_cause_id") == "agc-noise-floor-and-activity-control-dependency", "I006 root cause id")
    require(contract.get("candidate_limit") == 0 and contract.get("confirmation_limit") == 0,
            "I006 root cause must remain candidate-zero")
    require(contract.get("promotion_allowed") is False and contract.get("shipping_source_change_allowed") is False,
            "I006 root cause cannot promote or change shipping source")
    require(contract.get("seeds") == [16107, 26107, 36107], "I006 exposed regression seeds")
    require(contract.get("scenarios") == ["noise-floor-low", "noise-floor-step", "near-far-doubletalk", "near-far-weak-near"],
            "I006 frozen differential scenarios")
    require(all(value is False for value in contract["authority"].values()), "I006 differential authority must remain false")
    require(contract.get("product_qualification") == "DEFERRED_BY_SCOPE", "product boundary")

    baseline.validate_contract(baseline_contract)
    review = load_json(root / "docs/program/iterations/I006-review.json")
    result = load_json(root / "docs/program/iterations/I006-baseline-result.json")
    require(review.get("state") == "REVIEW_REQUIRED" and
            review.get("decision") == "MEASURED_GAP_REVIEW_REQUIRED", "reviewed I006 gap required")
    require(review["authority"].get("root_cause_differential_authorized") is True, "root-cause authority missing")
    require(review["authority"].get("parameter_search_authorized") is False, "parameter search must remain prohibited")
    require(result.get("measurement_revision") == 3 and result.get("candidate_limit_consumed") == 0 and
            result.get("confirmation_limit_consumed") == 0, "revision-3 candidate-zero authority required")

    agc_text = (root / "src/enhance/ap_agc.c").read_text(encoding="utf-8")
    activity_text = (root / "src/activity/ap_activity.c").read_text(encoding="utf-8")
    pipeline_text = (root / "src/core/ap_pipeline.c").read_text(encoding="utf-8")
    require("0.25f, 8.0f" in agc_text, "shipping AGC max-gain clamp drift")
    require("smoothed_ratio > s->double_talk_ratio" in activity_text and
            "instant_ratio > 0.90f * s->double_talk_ratio" in activity_text and
            "instant_ratio > 0.72f * s->double_talk_ratio" in activity_text,
            "shipping activity ratio predicates drift")
    require("!(far_end_active && !double_talk_active)" in pipeline_text, "shipping AGC permission gate drift")
    return {
        "agc_source_sha256": baseline.sha256(root / "src/enhance/ap_agc.c"),
        "activity_source_sha256": baseline.sha256(root / "src/activity/ap_activity.c"),
        "pipeline_source_sha256": baseline.sha256(root / "src/core/ap_pipeline.c"),
        "agc_max_gain_linear": 8.0,
        "agc_max_gain_db": 20.0 * math.log10(8.0),
        "double_talk_ratio": 1.5,
        "instant_on_ratio": 1.35,
        "instant_hold_ratio": 1.08,
        "gain_increase_permission": "!(far_end_active && !double_talk_active)",
    }


def run_probe(probe: Path, case_dir: Path, mic: list[float], render: list[float]) -> list[dict]:
    mic_path = case_dir / "mic.pcm"
    render_path = case_dir / "render.pcm"
    synth.write_pcm(mic_path, mic)
    synth.write_pcm(render_path, render)
    completed = subprocess.run([str(probe), str(mic_path), str(render_path)], check=True,
                               text=True, capture_output=True)
    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    require(rows, "root-cause probe produced no rows")
    return rows


def noise_summary(rows: list[dict], warmup: int, hypothesis: dict) -> dict:
    usable = rows[warmup:]
    require(len(usable) >= 400, "noise-floor differential trace too short")
    gains_db = [float(row["agc_gain_db"]) for row in usable]
    gains_linear = [float(row["agc_gain_linear"]) for row in usable]
    expected = float(hypothesis["expected_max_gain_db"])
    tolerance = float(hypothesis["p95_match_tolerance_db"])
    floor = float(hypothesis["saturation_linear_floor"])
    p95 = baseline.percentile(gains_db, 0.95)
    require(p95 is not None, "noise-floor p95 missing")
    far_active_fraction = sum(int(row["far_end_active"]) != 0 for row in usable) / len(usable)
    saturation_fraction = sum(gain >= floor for gain in gains_linear) / len(gains_linear)
    speech_prob_p95 = baseline.percentile([float(row["ns_speech_probability"]) for row in usable], 0.95)
    confirmed = abs(float(p95) - expected) <= tolerance and max(gains_linear) >= floor and far_active_fraction == 0.0
    return {
        "frames": len(usable),
        "agc_gain_db_p50": statistics.median(gains_db),
        "agc_gain_db_p95": p95,
        "agc_gain_db_max": max(gains_db),
        "agc_gain_linear_max": max(gains_linear),
        "max_gain_saturation_fraction": saturation_fraction,
        "far_end_active_fraction": far_active_fraction,
        "ns_speech_probability_p95": speech_prob_p95,
        "p95_delta_from_shipping_max_db": float(p95) - expected,
        "classification": (hypothesis["classification"]["confirmed"] if confirmed
                           else hypothesis["classification"]["not_confirmed"]),
        "hypothesis_confirmed": confirmed,
    }


def double_talk_summary(rows: list[dict], near_labels: list[int], warmup: int,
                        allowed_classifications: list[str]) -> dict:
    usable = rows[warmup:]
    active = [row for row in usable
              if int(row["frame"]) < len(near_labels)
              and near_labels[int(row["frame"])] != 0
              and int(row["far_end_active"]) != 0]
    require(len(active) >= 80, "double-talk differential has too few near+far frames")
    misses = [row for row in active if int(row["double_talk_active"]) == 0]
    hits = len(active) - len(misses)
    if not misses:
        classification = "DT_NOT_EXPLAINED_BY_CURRENT_RATIO_GATES"
        buckets = {"smoothed_gate_only_limit": 0, "instant_on_gate_only_limit": 0,
                   "both_on_gates_limit": 0, "other": 0}
    else:
        smooth_only = sum(not int(row["smoothed_gate"]) and int(row["instant_on_proxy_gate"]) for row in misses)
        instant_only = sum(int(row["smoothed_gate"]) and not int(row["instant_on_proxy_gate"]) for row in misses)
        both = sum(not int(row["smoothed_gate"]) and not int(row["instant_on_proxy_gate"]) for row in misses)
        other = len(misses) - smooth_only - instant_only - both
        buckets = {
            "smoothed_gate_only_limit": smooth_only,
            "instant_on_gate_only_limit": instant_only,
            "both_on_gates_limit": both,
            "other": other,
        }
        dominant = max(buckets, key=buckets.get)
        if buckets[dominant] == 0 or dominant == "other":
            classification = "DT_NOT_EXPLAINED_BY_CURRENT_RATIO_GATES"
        elif dominant == "smoothed_gate_only_limit":
            classification = "DT_SMOOTHED_RATIO_GATE_LIMIT"
        elif dominant == "instant_on_gate_only_limit":
            classification = "DT_INSTANT_RATIO_GATE_LIMIT"
        else:
            classification = "DT_BOTH_RATIO_GATES_LIMIT"
    require(classification in allowed_classifications, "unexpected double-talk classification")
    hold_rescue = sum(int(row["instant_hold_proxy_gate"]) != 0 for row in misses)
    return {
        "near_active_far_detected_frames": len(active),
        "double_talk_hits": hits,
        "double_talk_misses": len(misses),
        "double_talk_fraction": hits / len(active),
        "miss_partition": buckets,
        "instant_hold_gate_true_on_misses": hold_rescue,
        "instant_hold_gate_true_fraction_on_misses": hold_rescue / max(1, len(misses)),
        "classification": classification,
    }


def self_test() -> None:
    hypothesis = {
        "expected_max_gain_db": 20.0 * math.log10(8.0),
        "p95_match_tolerance_db": 0.10,
        "saturation_linear_floor": 7.9,
        "classification": {"confirmed": "YES", "not_confirmed": "NO"},
    }
    rows = [{"agc_gain_db": 20.0 * math.log10(8.0), "agc_gain_linear": 8.0,
             "far_end_active": 0, "ns_speech_probability": 0.0} for _ in range(500)]
    assert noise_summary(rows, 0, hypothesis)["hypothesis_confirmed"] is True
    dt_rows = [{"frame": i, "far_end_active": 1, "double_talk_active": 0,
                "smoothed_gate": 0, "instant_on_proxy_gate": 1,
                "instant_hold_proxy_gate": 1} for i in range(100)]
    labels = [1] * 100
    result = double_talk_summary(dt_rows, labels, 0, [
        "DT_SMOOTHED_RATIO_GATE_LIMIT", "DT_INSTANT_RATIO_GATE_LIMIT",
        "DT_BOTH_RATIO_GATES_LIMIT", "DT_NOT_EXPLAINED_BY_CURRENT_RATIO_GATES"])
    assert result["classification"] == "DT_SMOOTHED_RATIO_GATE_LIMIT"
    print(json.dumps({"result": "PASS", "candidate_limit": 0, "confirmation_limit": 0}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--baseline-contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract is not None and args.baseline_contract is not None and args.output is not None,
            "contract/baseline-contract/output required")
    root = Path(__file__).resolve().parents[2]
    contract = load_json(args.contract)
    baseline_contract = load_json(args.baseline_contract)
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    require(current == contract["base_sha"], f"I006 exact reviewed main drift: {current}")
    source_contract = validate_contract(contract, baseline_contract, root)

    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    probe = build_probe(root, output)
    corpus = output / "corpus"
    corpus.mkdir()
    warmup = int(baseline_contract["input_preconditions"]["warmup_frames"])
    cases: list[dict] = []
    for seed in contract["seeds"]:
        for scenario in contract["scenarios"]:
            case_dir = corpus / f"seed-{seed}" / scenario
            case_dir.mkdir(parents=True)
            mic, render, near, near_labels, _far_labels, category = baseline.generate_case(
                baseline_contract, scenario, int(seed))
            rows = run_probe(probe, case_dir, mic, render)
            require(len(rows) >= int(baseline_contract["input_preconditions"]["min_trace_frames"]),
                    "root-cause trace too short")
            trace_path = case_dir / "trace.jsonl"
            trace_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
            if category == "noise_floor":
                diagnosis = noise_summary(rows, warmup, contract["hypotheses"]["noise_floor"])
            else:
                require(category == "near_far", "root-cause contract must contain only reviewed gap categories")
                diagnosis = double_talk_summary(rows, near_labels, warmup,
                                                contract["hypotheses"]["double_talk"]["classification"])
            cases.append({"seed": seed, "scenario": scenario, "category": category, "diagnosis": diagnosis})

    noise_cases = [case for case in cases if case["category"] == "noise_floor"]
    dt_cases = [case for case in cases if case["category"] == "near_far"]
    require(len(noise_cases) == 6 and len(dt_cases) == 6, "I006 root-cause case partition drift")
    noise_confirmed = sum(bool(case["diagnosis"]["hypothesis_confirmed"]) for case in noise_cases)
    dt_distribution: dict[str, int] = {}
    for case in dt_cases:
        key = str(case["diagnosis"]["classification"])
        dt_distribution[key] = dt_distribution.get(key, 0) + 1

    report = {
        "schema_version": 1,
        "iteration_id": "I006",
        "phase": "root-cause-differential",
        "root_cause_id": contract["root_cause_id"],
        "source_sha": current,
        "authority": "candidate-zero-exposed-regression-root-cause-only",
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "candidate_search_performed": False,
        "shipping_source_changed": False,
        "parameter_tuning_performed": False,
        "promotion_allowed": False,
        "source_contract": source_contract,
        "probe_sha256": baseline.sha256(probe),
        "cases": cases,
        "aggregate": {
            "noise_floor_cases": len(noise_cases),
            "noise_floor_max_gain_hypothesis_confirmed": noise_confirmed,
            "double_talk_cases": len(dt_cases),
            "double_talk_classification_distribution": dt_distribution,
        },
        "decision": "ROOT_CAUSE_DIFFERENTIAL_REVIEW_REQUIRED",
        "candidate_decision": "NOT_AN_ACOUSTIC_CANDIDATE",
        "next_step": "review mechanism evidence before any explicit bounded source-candidate contract",
        "product_qualification": "DEFERRED_BY_SCOPE",
    }
    write_json(output / "root-cause-result.json", report)
    manifest = {str(path.relative_to(output)): baseline.sha256(path)
                for path in sorted(output.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"}
    write_json(output / "evidence-manifest.json", {"schema_version": 1, "source_sha": current, "files": manifest})
    manifest["evidence-manifest.json"] = baseline.sha256(output / "evidence-manifest.json")
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(manifest.items()):
            handle.write(f"{digest}  {rel}\n")
    print(json.dumps({
        "decision": report["decision"],
        "cases": len(cases),
        "noise_floor_confirmed": noise_confirmed,
        "double_talk_classifications": dt_distribution,
        "candidate_limit": 0,
        "confirmation_limit": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
