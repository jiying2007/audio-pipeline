#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))

import run_validation_engine as engine  # type: ignore


DIAGNOSTIC_ID = "vad-domain-state-divergence-v1"
FORBIDDEN_PRIOR_SEEDS = {91123, 92123, 93123}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != 1:
        raise ValueError("diagnostic schema_version must be 1")
    if contract.get("diagnostic_id") != DIAGNOSTIC_ID:
        raise ValueError("diagnostic_id drifted")
    if contract.get("authority") != "DIAGNOSTIC_ONLY_VAD_STATE_DECOMPOSITION":
        raise ValueError("diagnostic authority drifted")
    budget = contract.get("budget", {})
    if budget.get("candidate_limit") != 0 or budget.get("confirmation_limit") != 0:
        raise ValueError("diagnostic cannot consume candidate/confirmation budget")
    if budget.get("diagnostic_execution_limit") != 1:
        raise ValueError("diagnostic must remain one-shot")
    fresh = contract.get("fresh_diagnostic_authority", {})
    seeds = [int(x) for x in fresh.get("seeds", [])]
    if len(seeds) != 3 or len(set(seeds)) != 3:
        raise ValueError("diagnostic requires three unique fresh seeds")
    if set(seeds) & FORBIDDEN_PRIOR_SEEDS:
        raise ValueError("diagnostic reused rejected candidate authority")
    if fresh.get("candidate_value_search") is not False:
        raise ValueError("diagnostic cannot search candidate values")
    if fresh.get("threshold_search") is not False:
        raise ValueError("diagnostic cannot search thresholds")
    if fresh.get("case_profile") != "ns-isolated":
        raise ValueError("diagnostic must remain ns-isolated")
    mirror = contract.get("mirror_contract", {})
    if mirror.get("shipping_source_mutation") is not False:
        raise ValueError("diagnostic cannot mutate shipping source")
    if mirror.get("public_api_mutation") is not False:
        raise ValueError("diagnostic cannot mutate public API")
    boundary = contract.get("authority_boundary", {})
    if any(value is not False for value in boundary.values()):
        raise ValueError("diagnostic authority boundary must remain all-false")


def resolve_case_paths(corpus_path: Path, case: dict[str, Any],
                       work: Path) -> tuple[Path, Path]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels is None:
        raise ValueError(f"missing mic/labels: {case.get('case_id')}")
    rate = int(case.get("sample_rate_hz", 0))
    channels = int(case.get("mic_channels", 0))
    if rate != 16000 or channels != 1:
        raise ValueError(
            f"diagnostic requires 16 kHz mono ns-isolated case: "
            f"{case.get('case_id')} rate={rate} channels={channels}"
        )
    _, staged = engine.stage_audio(mic, rate, channels, work, "mic.pcm")
    return staged, labels


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any],
             work: Path) -> dict[str, Any]:
    staged, labels = resolve_case_paths(corpus_path, case, work)
    output = work / "result.json"
    subprocess.run(
        [str(probe), str(staged), str(labels), str(output)],
        check=True,
    )
    result = load_json(output)
    result["case_id"] = str(case["case_id"])
    result["profile"] = str(case["processor_profile"])
    speech = int(result["speech_frames"])
    noise = int(result["noise_frames"])
    result["derived"] = {
        "shipping_recall": (
            int(result["speech_shipping_active"]) / speech if speech else None
        ),
        "pre_ns_recall": (
            int(result["speech_pre_active"]) / speech if speech else None
        ),
        "shipping_false_positive_rate": (
            int(result["noise_shipping_active"]) / noise if noise else None
        ),
        "pre_ns_false_positive_rate": (
            int(result["noise_pre_active"]) / noise if noise else None
        ),
    }
    return result


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("no diagnostic rows")
    scalar_counts = (
        "frames",
        "speech_frames",
        "noise_frames",
        "mirror_probability_mismatch_frames",
        "mirror_active_mismatch_frames",
        "raw_probability_diff_frames",
        "upstream_guard_diff_frames",
        "transient_cap_diff_frames",
        "blend_diff_frames",
        "noise_update_diff_frames",
        "refresh_diff_frames",
        "hangover_before_diff_frames",
        "hangover_after_diff_frames",
        "active_diff_frames",
        "speech_shipping_active",
        "speech_pre_active",
        "noise_shipping_active",
        "noise_pre_active",
        "lost_speech_frames",
        "gained_speech_frames",
    )
    totals = {
        key: sum(int(row.get(key, 0)) for row in rows)
        for key in scalar_counts
    }
    attribution_keys = sorted({
        key
        for row in rows
        for key in row.get("lost_speech_attribution", {})
    })
    totals["lost_speech_attribution"] = {
        key: sum(int(row.get("lost_speech_attribution", {}).get(key, 0))
                 for row in rows)
        for key in attribution_keys
    }
    totals["max_public_mirror_probability_delta"] = max(
        float(row.get("max_public_mirror_probability_delta", 0.0))
        for row in rows
    )
    for key in (
        "max_raw_probability_delta",
        "max_final_probability_delta",
        "max_noise_rms_delta",
        "max_ratio_db_delta",
    ):
        totals[key] = max(float(row.get(key, 0.0)) for row in rows)

    speech = int(totals["speech_frames"])
    noise = int(totals["noise_frames"])
    totals["shipping_recall"] = (
        int(totals["speech_shipping_active"]) / speech if speech else None
    )
    totals["pre_ns_recall"] = (
        int(totals["speech_pre_active"]) / speech if speech else None
    )
    totals["shipping_false_positive_rate"] = (
        int(totals["noise_shipping_active"]) / noise if noise else None
    )
    totals["pre_ns_false_positive_rate"] = (
        int(totals["noise_pre_active"]) / noise if noise else None
    )
    return totals


def evaluate(probe: Path, contract_path: Path,
             corpora: list[Path], output: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    validate_contract(contract)
    expected_seeds = [
        int(x) for x in contract["fresh_diagnostic_authority"]["seeds"]
    ]
    if len(corpora) != len(expected_seeds):
        raise ValueError("one corpus per preregistered diagnostic seed is required")

    partitions: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    actual_seeds: list[int] = []

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        cases = [
            case for case in corpus.get("cases", [])
            if case.get("processor_profile") == "ns-isolated"
            and case.get("vad_labels")
            and case.get("render_audio") is None
        ]
        if not cases:
            raise ValueError(f"no ns-isolated VAD cases: {corpus_path}")
        rows: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            with tempfile.TemporaryDirectory(
                prefix=f"ap-vad-state-divergence-{seed}-{index}-"
            ) as tmp:
                rows.append(
                    run_case(probe, corpus_path, case, Path(tmp))
                )
        summary = aggregate(rows)
        partitions.append({
            "seed": seed,
            "corpus_id": corpus.get("corpus_id"),
            "summary": summary,
            "cases": rows,
        })
        all_rows.extend(rows)

    if actual_seeds != expected_seeds:
        raise ValueError(
            f"diagnostic seed order drift: actual={actual_seeds} "
            f"expected={expected_seeds}"
        )

    summary = aggregate(all_rows)
    mirror_invalid = (
        int(summary["mirror_probability_mismatch_frames"]) > 0
        or int(summary["mirror_active_mismatch_frames"]) > 0
        or float(summary["max_public_mirror_probability_delta"])
        > float(contract["mirror_contract"]["mirror_probability_tolerance"])
    )
    if mirror_invalid:
        decision = "MIRROR_IDENTITY_INVALID_REVIEW_REQUIRED"
    elif int(summary["lost_speech_frames"]) > 0:
        decision = "VAD_STATE_DIVERGENCE_CONFIRMED_REVIEW_REQUIRED"
    else:
        decision = "NO_RECALL_DIVERGENCE_EXERCISED_REVIEW_REQUIRED"

    result = {
        "schema_version": 1,
        "diagnostic_id": DIAGNOSTIC_ID,
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": expected_seeds,
        "summary": summary,
        "partitions": partitions,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "shipping_source_changed": False,
        "candidate_selected": False,
        "thresholds_tuned": False,
        "interpretation_rule": (
            "Counts describe which frozen shipping VAD state-machine mechanisms "
            "co-occur with fresh speech-active divergence. They do not rank or "
            "authorize a candidate, threshold, blend weight, hold duration, or "
            "shipping change."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    contract = {
        "schema_version": 1,
        "diagnostic_id": DIAGNOSTIC_ID,
        "authority": "DIAGNOSTIC_ONLY_VAD_STATE_DECOMPOSITION",
        "fresh_diagnostic_authority": {
            "seeds": [101123, 111123, 121123],
            "case_profile": "ns-isolated",
            "candidate_value_search": False,
            "threshold_search": False,
        },
        "mirror_contract": {
            "shipping_source_mutation": False,
            "public_api_mutation": False,
        },
        "budget": {
            "candidate_limit": 0,
            "confirmation_limit": 0,
            "diagnostic_execution_limit": 1,
        },
        "authority_boundary": {
            "may_select_candidate": False,
            "may_tune_thresholds": False,
            "may_consume_confirmation": False,
            "may_modify_shipping_source": False,
            "may_modify_public_api": False,
            "may_claim_hil": False,
            "may_claim_product_certification": False,
            "may_promote_release": False,
        },
    }
    validate_contract(contract)
    bad = json.loads(json.dumps(contract))
    bad["budget"]["candidate_limit"] = 1
    try:
        validate_contract(bad)
    except ValueError as exc:
        assert "candidate/confirmation" in str(exc)
    else:
        raise AssertionError("candidate budget leaked into diagnostic")

    row = {
        "frames": 10,
        "speech_frames": 4,
        "noise_frames": 6,
        "mirror_probability_mismatch_frames": 0,
        "mirror_active_mismatch_frames": 0,
        "raw_probability_diff_frames": 3,
        "upstream_guard_diff_frames": 2,
        "transient_cap_diff_frames": 1,
        "blend_diff_frames": 0,
        "noise_update_diff_frames": 2,
        "refresh_diff_frames": 2,
        "hangover_before_diff_frames": 3,
        "hangover_after_diff_frames": 3,
        "active_diff_frames": 2,
        "speech_shipping_active": 4,
        "speech_pre_active": 2,
        "noise_shipping_active": 1,
        "noise_pre_active": 1,
        "lost_speech_frames": 2,
        "gained_speech_frames": 0,
        "lost_speech_attribution": {
            "raw_probability_lower": 2,
            "upstream_guard_lost": 1,
            "refresh_changed": 2,
        },
        "max_public_mirror_probability_delta": 0.0,
        "max_raw_probability_delta": 0.2,
        "max_final_probability_delta": 0.1,
        "max_noise_rms_delta": 0.01,
        "max_ratio_db_delta": 2.0,
    }
    summary = aggregate([row, row])
    assert summary["frames"] == 20
    assert summary["lost_speech_frames"] == 4
    assert summary["shipping_recall"] == 1.0
    assert summary["pre_ns_recall"] == 0.5
    assert summary["lost_speech_attribution"]["refresh_changed"] == 4
    print("VAD domain state-divergence diagnostic self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--probe", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.corpus:
        parser.error("--probe, --contract, --corpus and --output are required")

    result = evaluate(
        args.probe.resolve(),
        args.contract.resolve(),
        [path.resolve() for path in args.corpus],
        args.output.resolve(),
    )
    print(json.dumps({
        "decision": result["decision"],
        "fresh_seeds": result["fresh_seeds"],
        "lost_speech_frames": result["summary"]["lost_speech_frames"],
        "gained_speech_frames": result["summary"]["gained_speech_frames"],
        "shipping_recall": result["summary"]["shipping_recall"],
        "pre_ns_recall": result["summary"]["pre_ns_recall"],
        "mirror_probability_mismatch_frames":
            result["summary"]["mirror_probability_mismatch_frames"],
        "mirror_active_mismatch_frames":
            result["summary"]["mirror_active_mismatch_frames"],
        "lost_speech_attribution":
            result["summary"]["lost_speech_attribution"],
    }, sort_keys=True))
    return 2 if result["decision"] == "MIRROR_IDENTITY_INVALID_REVIEW_REQUIRED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
