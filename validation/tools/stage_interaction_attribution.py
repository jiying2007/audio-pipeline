#!/usr/bin/env python3
"""Attribute candidate-zero S003 signatures across deterministic stage prefixes."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from system_robustness_attribution import diagnostic_signatures, load_watch

PROFILE_STAGE = {
    "prefix-raw": "raw",
    "prefix-capture": "capture",
    "prefix-bf": "BF",
    "prefix-sync": "SYNC",
    "prefix-aec": "AEC",
    "prefix-res": "RES",
    "prefix-ns": "NS",
    "prefix-agc": "AGC",
    "prefix-vad": "VAD",
    "default": "final",
}

TELEMETRY_METRICS = (
    "input_rms_dbfs",
    "output_rms_dbfs",
    "output_rms_delta_db",
    "input_peak_dbfs",
    "output_peak_dbfs",
    "input_clip_fraction",
    "output_clip_fraction",
    "input_dc_offset_dbfs",
    "output_dc_offset_dbfs",
    "near_si_sdr_db",
    "near_si_sdr_improvement_db",
    "input_render_max_abs_corr",
    "output_render_max_abs_corr",
    "output_render_corr_ratio",
    "output_render_corr_reduction",
    "erle_db",
    "noise_only_attenuation_db",
    "speech_active_attenuation_db",
    "vad_f1",
    "vad_precision",
    "vad_recall",
    "vad_false_positive_rate",
    "vad_false_negative_rate",
)


def _stage_signatures(result: dict, profile: str, watch: dict) -> list[dict]:
    signatures = diagnostic_signatures(result, watch)
    if profile not in {"prefix-vad", "default"}:
        signatures = [
            item for item in signatures if item["id"] != "severe-vad-degradation"
        ]
    return signatures


def _telemetry(result: dict) -> dict:
    metrics = result.get("metrics", {})
    return {name: metrics[name] for name in TELEMETRY_METRICS if name in metrics}


def build(corpus: dict, report: dict, watch: dict) -> tuple[dict, dict]:
    report_cases = {item["case_id"]: item for item in report.get("cases", [])}
    groups: dict[str, list[dict]] = defaultdict(list)

    for case in corpus["cases"]:
        dims = case.get("dimensions", {})
        base_case_id = str(dims["base_case_id"])
        profile = str(case["processor_profile"])
        result = report_cases.get(case["case_id"])
        if result is None:
            raise ValueError(f"missing report case: {case['case_id']}")
        signatures = _stage_signatures(result, profile, watch)
        groups[base_case_id].append({
            "case_id": case["case_id"],
            "stage_profile": profile,
            "stage": PROFILE_STAGE[profile],
            "stage_index": int(dims["stage_index"]),
            "source_family": dims["source_family"],
            "policy_passed": bool(result.get("passed", False)),
            "policy_violations": result.get("violations", []),
            "diagnostic_signatures": signatures,
            "telemetry": _telemetry(result),
        })

    cases_out: list[dict] = []
    replay: list[dict] = []
    seed = int(corpus.get("generator", {}).get("seed", 0))

    for base_case_id, stages in sorted(groups.items()):
        stages.sort(key=lambda item: item["stage_index"])
        previous: set[str] = set()
        first_observable_stage = None
        first_observable_profile = None
        signature_union: set[str] = set()
        transitions: list[dict] = []

        for stage in stages:
            current = {item["id"] for item in stage["diagnostic_signatures"]}
            new = sorted(current - previous)
            resolved = sorted(previous - current)
            if current and first_observable_stage is None:
                first_observable_stage = stage["stage"]
                first_observable_profile = stage["stage_profile"]
            signature_union.update(current)
            transitions.append({
                "stage": stage["stage"],
                "stage_profile": stage["stage_profile"],
                "new_signatures": new,
                "resolved_signatures": resolved,
                "active_signatures": sorted(current),
            })
            previous = current

        source_family = stages[0]["source_family"]
        item = {
            "base_case_id": base_case_id,
            "source_family": source_family,
            "first_observable_stage": first_observable_stage,
            "first_observable_profile": first_observable_profile,
            "signature_union": sorted(signature_union),
            "all_stage_policy_passed": all(stage["policy_passed"] for stage in stages),
            "stages": stages,
            "transitions": transitions,
        }
        cases_out.append(item)

        if signature_union:
            replay.append({
                "schema_version": 1,
                "failure_id": f"{corpus['corpus_id']}::{base_case_id}",
                "source_identity": {
                    "corpus_id": corpus["corpus_id"],
                    "case_id": base_case_id,
                    "source_revision": report.get("source_revision"),
                },
                "seed": seed,
                "perturbation": {
                    "source_family": source_family,
                    "stage_prefix_replay": True,
                },
                "telemetry": {
                    "stage_trace": stages,
                    "transitions": transitions,
                },
                "expected_failure_signature": {
                    "diagnostic_signature_ids": sorted(signature_union),
                    "release_policy_failure": not item["all_stage_policy_passed"],
                },
                "shipping_output": {
                    "final_case_id": next(
                        (
                            stage["case_id"]
                            for stage in stages
                            if stage["stage_profile"] == "default"
                        ),
                        None,
                    )
                },
                "first_observable_stage": first_observable_stage,
                "regression_assertion": {
                    "must_remain_replayable": True,
                    "candidate_authority": False,
                    "release_acceptance_authority": False,
                    "root_cause_claim_authority": False,
                },
            })

    attribution = {
        "schema_version": 1,
        "corpus_id": corpus["corpus_id"],
        "seed": seed,
        "authority": "candidate-zero-stage-observation-only",
        "watch_authority": watch.get("authority", "none"),
        "root_cause_rule": (
            "first_observable_stage is an observation boundary, not a causal root-cause claim"
        ),
        "cases": cases_out,
    }
    replay_index = {"schema_version": 1, "failures": replay}
    return attribution, replay_index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--watch-contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    watch = load_watch(args.watch_contract)
    attribution, replay = build(corpus, report, watch)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "stage-interaction-attribution.json").write_text(
        json.dumps(attribution, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "failure-replay-index.json").write_text(
        json.dumps(replay, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "seed": attribution["seed"],
        "base_cases": len(attribution["cases"]),
        "replays": len(replay["failures"]),
        "attributed": sum(
            item["first_observable_stage"] is not None
            for item in attribution["cases"]
        ),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
