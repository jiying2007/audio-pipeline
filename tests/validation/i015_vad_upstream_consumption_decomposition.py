#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))

import run_validation_engine as engine  # type: ignore

REQUIRED_CASES = {"stage-ns-stationary", "stage-ns-nonstationary"}
NONSTATIONARY_CASE = "stage-ns-nonstationary"
WARMUP_FRAMES = 80
LANES = ("shipping", "no_upstream", "blend_only", "guard_only")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def roc_auc(scores: list[float], labels: list[int]) -> float:
    if len(scores) != len(labels) or not scores:
        raise ValueError("AUC requires aligned non-empty scores/labels")
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("AUC requires both positive and negative labels")

    ordered = sorted(zip(scores, labels), key=lambda item: item[0])
    rank = 1
    pos_rank_sum = 0.0
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        avg_rank = (rank + (rank + (j - i) - 1)) / 2.0
        pos_rank_sum += avg_rank * sum(label for _, label in ordered[i:j])
        rank += j - i
        i = j
    return (
        pos_rank_sum - n_pos * (n_pos + 1) / 2.0
    ) / (n_pos * n_neg)


def run_probe(probe: Path, raw_pcm: Path) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [str(probe), str(raw_pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(completed.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid I015 probe JSONL line {number}: {exc.msg}"
            ) from exc
        if not isinstance(value, dict):
            raise ValueError(f"I015 probe row {number} must be an object")
        rows.append(value)
    if not rows:
        raise ValueError("I015 probe produced no rows")
    return rows


def run_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError(f"I015 case missing mic/labels: {case.get('case_id')}")
    if int(case.get("sample_rate_hz", 0)) != 16000:
        raise ValueError("I015 requires 16 kHz")
    if int(case.get("mic_channels", 0)) != 1:
        raise ValueError("I015 requires mono input")

    with tempfile.TemporaryDirectory(prefix="ap-i015-stage-") as tmp:
        work = Path(tmp)
        _, raw = engine.stage_audio(mic, 16000, 1, work, "mic.pcm")
        rows = run_probe(probe, raw)

    labels = engine.load_labels(labels_path)
    count = min(len(labels), len(rows))
    if count <= WARMUP_FRAMES:
        raise ValueError("I015 case too short after warmup")
    return {
        "case_id": str(case["case_id"]),
        "labels": [int(x) for x in labels[:count]],
        "rows": rows[:count],
    }


def empty_lane_counts() -> dict[str, int]:
    return {
        "speech_active": 0,
        "noise_active": 0,
        "speech_frames": 0,
        "noise_frames": 0,
    }


def summarize_rows(rows: list[dict[str, Any]], labels: list[int]) -> dict[str, Any]:
    lane_scores = {lane: [] for lane in LANES}
    lane_counts = {lane: empty_lane_counts() for lane in LANES}
    shipping_vs_no_active_diff_frames = 0
    shipping_vs_no_probability_diff_frames = 0
    max_shipping_vs_no_probability_delta = 0.0

    rescued_speech_frames = 0
    lost_speech_frames = 0
    added_noise_active_frames = 0
    removed_noise_active_frames = 0

    rescue_attribution = {
        "blend_only_active": 0,
        "guard_only_active": 0,
        "both_single_lanes_active": 0,
        "blend_only_exclusive": 0,
        "guard_only_exclusive": 0,
        "interaction_only": 0,
    }
    added_noise_attribution = {
        "blend_only_active": 0,
        "guard_only_active": 0,
        "both_single_lanes_active": 0,
        "blend_only_exclusive": 0,
        "guard_only_exclusive": 0,
        "interaction_only": 0,
    }

    shipping_guard_active_frames = 0
    shipping_blend_applied_frames = 0
    shipping_transient_capped_frames = 0
    shipping_fast_noise_update_frames = 0
    shipping_strong_refresh_frames = 0
    shipping_weak_refresh_frames = 0

    for row, label in zip(rows, labels):
        for lane in LANES:
            probability = float(row[f"{lane}_probability"])
            active = int(row[f"{lane}_active"])
            if not math.isfinite(probability):
                raise ValueError(f"non-finite I015 {lane} probability")
            lane_scores[lane].append(probability)
            counts = lane_counts[lane]
            if label:
                counts["speech_frames"] += 1
                counts["speech_active"] += active
            else:
                counts["noise_frames"] += 1
                counts["noise_active"] += active

        shipping_active = int(row["shipping_active"])
        no_active = int(row["no_upstream_active"])
        blend_active = int(row["blend_only_active"])
        guard_active = int(row["guard_only_active"])
        shipping_prob = float(row["shipping_probability"])
        no_prob = float(row["no_upstream_probability"])

        if shipping_active != no_active:
            shipping_vs_no_active_diff_frames += 1
        delta = abs(shipping_prob - no_prob)
        max_shipping_vs_no_probability_delta = max(
            max_shipping_vs_no_probability_delta, delta
        )
        if delta > 1e-6:
            shipping_vs_no_probability_diff_frames += 1

        if int(row["shipping_guard_active"]):
            shipping_guard_active_frames += 1
        if int(row["shipping_blend_applied"]):
            shipping_blend_applied_frames += 1
        if int(row["shipping_transient_capped"]):
            shipping_transient_capped_frames += 1
        if int(row["shipping_noise_update_class"]) == 2:
            shipping_fast_noise_update_frames += 1
        if int(row["shipping_refresh_class"]) == 1:
            shipping_strong_refresh_frames += 1
        if int(row["shipping_refresh_class"]) == 2:
            shipping_weak_refresh_frames += 1

        if label:
            if shipping_active and not no_active:
                rescued_speech_frames += 1
                b = bool(blend_active and not no_active)
                g = bool(guard_active and not no_active)
                rescue_attribution["blend_only_active"] += int(b)
                rescue_attribution["guard_only_active"] += int(g)
                rescue_attribution["both_single_lanes_active"] += int(b and g)
                rescue_attribution["blend_only_exclusive"] += int(b and not g)
                rescue_attribution["guard_only_exclusive"] += int(g and not b)
                rescue_attribution["interaction_only"] += int(not b and not g)
            if no_active and not shipping_active:
                lost_speech_frames += 1
        else:
            if shipping_active and not no_active:
                added_noise_active_frames += 1
                b = bool(blend_active and not no_active)
                g = bool(guard_active and not no_active)
                added_noise_attribution["blend_only_active"] += int(b)
                added_noise_attribution["guard_only_active"] += int(g)
                added_noise_attribution["both_single_lanes_active"] += int(b and g)
                added_noise_attribution["blend_only_exclusive"] += int(b and not g)
                added_noise_attribution["guard_only_exclusive"] += int(g and not b)
                added_noise_attribution["interaction_only"] += int(not b and not g)
            if no_active and not shipping_active:
                removed_noise_active_frames += 1

    lane_metrics: dict[str, dict[str, float | int]] = {}
    for lane in LANES:
        counts = lane_counts[lane]
        speech_frames = counts["speech_frames"]
        noise_frames = counts["noise_frames"]
        lane_metrics[lane] = {
            **counts,
            "recall": counts["speech_active"] / speech_frames,
            "false_positive_rate": counts["noise_active"] / noise_frames,
            "probability_auc": roc_auc(lane_scores[lane], labels),
        }

    return {
        "frames": len(labels),
        "lane_metrics": lane_metrics,
        "shipping_vs_no_upstream_active_diff_frames":
            shipping_vs_no_active_diff_frames,
        "shipping_vs_no_upstream_probability_diff_frames":
            shipping_vs_no_probability_diff_frames,
        "max_shipping_vs_no_upstream_probability_delta":
            max_shipping_vs_no_probability_delta,
        "shipping_recall_gain_over_no_upstream":
            lane_metrics["shipping"]["recall"]
            - lane_metrics["no_upstream"]["recall"],
        "shipping_fpr_change_vs_no_upstream":
            lane_metrics["shipping"]["false_positive_rate"]
            - lane_metrics["no_upstream"]["false_positive_rate"],
        "shipping_probability_auc_gain_over_no_upstream":
            lane_metrics["shipping"]["probability_auc"]
            - lane_metrics["no_upstream"]["probability_auc"],
        "rescued_speech_frames": rescued_speech_frames,
        "lost_speech_frames": lost_speech_frames,
        "added_noise_active_frames": added_noise_active_frames,
        "removed_noise_active_frames": removed_noise_active_frames,
        "rescued_speech_attribution": rescue_attribution,
        "added_noise_attribution": added_noise_attribution,
        "shipping_guard_active_frames": shipping_guard_active_frames,
        "shipping_blend_applied_frames": shipping_blend_applied_frames,
        "shipping_transient_capped_frames": shipping_transient_capped_frames,
        "shipping_fast_noise_update_frames": shipping_fast_noise_update_frames,
        "shipping_strong_refresh_frames": shipping_strong_refresh_frames,
        "shipping_weak_refresh_frames": shipping_weak_refresh_frames,
    }


def merge_summaries(parts: list[dict[str, Any]]) -> dict[str, Any]:
    lane_counts = {lane: empty_lane_counts() for lane in LANES}
    lane_score_labels: dict[str, list[tuple[float, int]]] = {
        lane: [] for lane in LANES
    }
    totals = {
        "shipping_vs_no_upstream_active_diff_frames": 0,
        "shipping_vs_no_upstream_probability_diff_frames": 0,
        "rescued_speech_frames": 0,
        "lost_speech_frames": 0,
        "added_noise_active_frames": 0,
        "removed_noise_active_frames": 0,
        "shipping_guard_active_frames": 0,
        "shipping_blend_applied_frames": 0,
        "shipping_transient_capped_frames": 0,
        "shipping_fast_noise_update_frames": 0,
        "shipping_strong_refresh_frames": 0,
        "shipping_weak_refresh_frames": 0,
    }
    rescue = {
        "blend_only_active": 0,
        "guard_only_active": 0,
        "both_single_lanes_active": 0,
        "blend_only_exclusive": 0,
        "guard_only_exclusive": 0,
        "interaction_only": 0,
    }
    added = dict(rescue)
    max_delta = 0.0

    for part in parts:
        raw_rows = part["_rows"]
        raw_labels = part["_labels"]
        for lane in LANES:
            for row, label in zip(raw_rows, raw_labels):
                lane_score_labels[lane].append(
                    (float(row[f"{lane}_probability"]), int(label))
                )
            metrics = part["summary"]["lane_metrics"][lane]
            for key in ("speech_active", "noise_active", "speech_frames", "noise_frames"):
                lane_counts[lane][key] += int(metrics[key])

        summary = part["summary"]
        for key in totals:
            totals[key] += int(summary[key])
        for key in rescue:
            rescue[key] += int(summary["rescued_speech_attribution"][key])
            added[key] += int(summary["added_noise_attribution"][key])
        max_delta = max(
            max_delta,
            float(summary["max_shipping_vs_no_upstream_probability_delta"]),
        )

    lane_metrics: dict[str, dict[str, float | int]] = {}
    for lane in LANES:
        counts = lane_counts[lane]
        pairs = lane_score_labels[lane]
        scores = [p[0] for p in pairs]
        labels = [p[1] for p in pairs]
        lane_metrics[lane] = {
            **counts,
            "recall": counts["speech_active"] / counts["speech_frames"],
            "false_positive_rate": counts["noise_active"] / counts["noise_frames"],
            "probability_auc": roc_auc(scores, labels),
        }

    return {
        "frames": sum(len(part["_labels"]) for part in parts),
        "lane_metrics": lane_metrics,
        **totals,
        "max_shipping_vs_no_upstream_probability_delta": max_delta,
        "shipping_recall_gain_over_no_upstream":
            lane_metrics["shipping"]["recall"]
            - lane_metrics["no_upstream"]["recall"],
        "shipping_fpr_change_vs_no_upstream":
            lane_metrics["shipping"]["false_positive_rate"]
            - lane_metrics["no_upstream"]["false_positive_rate"],
        "shipping_probability_auc_gain_over_no_upstream":
            lane_metrics["shipping"]["probability_auc"]
            - lane_metrics["no_upstream"]["probability_auc"],
        "rescued_speech_attribution": rescue,
        "added_noise_attribution": added,
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    seeds = [
        int(x) for x in contract["fresh_diagnostic_authority"]["seeds"]
    ]
    if len(corpora) != len(seeds):
        raise ValueError("I015 corpus count must match preregistered seeds")
    if contract["budget"] != {
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_execution_limit": 1,
    }:
        raise ValueError("I015 budget drift")
    if (
        contract["parameter_search_allowed"] is not False
        or contract["threshold_tuning_allowed"] is not False
        or contract["shipping_source_change_allowed"] is not False
        or contract["promotion_allowed"] is not False
    ):
        raise ValueError("I015 authority boundary drift")

    actual_seeds: list[int] = []
    partitions: list[dict[str, Any]] = []
    max_mirror_delta = 0.0
    mirror_active_mismatch_frames = 0
    mirror_probability_mismatch_frames = 0

    for corpus_path in corpora:
        corpus = load_json(corpus_path)
        seed = int(corpus.get("generator", {}).get("seed", -1))
        actual_seeds.append(seed)
        selected = {
            str(case.get("case_id")): case
            for case in corpus.get("cases", [])
            if case.get("processor_profile") == "ns-isolated"
            and case.get("vad_labels")
            and case.get("render_audio") is None
            and str(case.get("case_id")) in REQUIRED_CASES
        }
        if set(selected) != REQUIRED_CASES:
            raise ValueError(
                f"missing I015 required cases seed={seed}: "
                f"{sorted(REQUIRED_CASES - set(selected))}"
            )

        case_results: list[dict[str, Any]] = []
        for case_id in sorted(REQUIRED_CASES):
            case = run_case(probe, corpus_path, selected[case_id])
            rows = case["rows"]
            labels = case["labels"]

            for row in rows:
                values = [
                    float(row["upstream_probability"]),
                    float(row["public_shipping_probability"]),
                ]
                for lane in LANES:
                    values.extend([
                        float(row[f"{lane}_probability"]),
                        float(row[f"{lane}_raw_probability"]),
                        float(row[f"{lane}_ratio_db"]),
                        float(row[f"{lane}_crest_db"]),
                        float(row[f"{lane}_noise_rms_before"]),
                        float(row[f"{lane}_noise_rms_after"]),
                    ])
                if not all(math.isfinite(value) for value in values):
                    raise ValueError(
                        f"non-finite I015 metric seed={seed} case={case_id}"
                    )
                delta = abs(
                    float(row["public_shipping_probability"])
                    - float(row["shipping_probability"])
                )
                max_mirror_delta = max(max_mirror_delta, delta)
                if delta > float(
                    contract["diagnostic_gates"][
                        "max_shipping_mirror_probability_delta"
                    ]
                ):
                    mirror_probability_mismatch_frames += 1
                if int(row["public_shipping_active"]) != int(row["shipping_active"]):
                    mirror_active_mismatch_frames += 1

            trimmed_rows = rows[WARMUP_FRAMES:]
            trimmed_labels = labels[WARMUP_FRAMES:]
            summary = summarize_rows(trimmed_rows, trimmed_labels)
            case_results.append({
                "case_id": case_id,
                "summary": summary,
                "_rows": trimmed_rows,
                "_labels": trimmed_labels,
            })

        seed_summary = merge_summaries(case_results)
        nonstationary = next(
            item for item in case_results
            if item["case_id"] == NONSTATIONARY_CASE
        )
        stationary = next(
            item for item in case_results
            if item["case_id"] != NONSTATIONARY_CASE
        )
        partitions.append({
            "seed": seed,
            "summary": seed_summary,
            "nonstationary": nonstationary["summary"],
            "stationary": stationary["summary"],
            "_nonstationary_rows": nonstationary["_rows"],
            "_nonstationary_labels": nonstationary["_labels"],
            "_stationary_rows": stationary["_rows"],
            "_stationary_labels": stationary["_labels"],
        })

    if actual_seeds != seeds:
        raise ValueError(
            f"I015 seed drift: actual={actual_seeds} expected={seeds}"
        )

    non_parts = [
        {
            "summary": item["nonstationary"],
            "_rows": item["_nonstationary_rows"],
            "_labels": item["_nonstationary_labels"],
        }
        for item in partitions
    ]
    stat_parts = [
        {
            "summary": item["stationary"],
            "_rows": item["_stationary_rows"],
            "_labels": item["_stationary_labels"],
        }
        for item in partitions
    ]
    combined_nonstationary = merge_summaries(non_parts)
    combined_stationary = merge_summaries(stat_parts)

    gates = contract["diagnostic_gates"]
    input_violations: list[dict[str, Any]] = []
    if max_mirror_delta > float(gates["max_shipping_mirror_probability_delta"]):
        input_violations.append({
            "gate": "shipping_mirror_probability_identity",
            "actual": max_mirror_delta,
            "limit": gates["max_shipping_mirror_probability_delta"],
        })
    if mirror_active_mismatch_frames != int(
        gates["shipping_mirror_active_mismatch_frames"]
    ):
        input_violations.append({
            "gate": "shipping_mirror_active_identity",
            "actual": mirror_active_mismatch_frames,
            "limit": gates["shipping_mirror_active_mismatch_frames"],
        })

    exercised = (
        int(combined_nonstationary[
            "shipping_vs_no_upstream_active_diff_frames"
        ])
        >= int(gates["min_nonstationary_shipping_vs_no_upstream_active_diff_frames"])
    )

    if input_violations:
        decision = "VAD_UPSTREAM_CONSUMPTION_INPUT_INVALID_REVIEW_REQUIRED"
    elif not exercised:
        decision = "NO_VAD_UPSTREAM_CONSUMPTION_EFFECT_REVIEW_REQUIRED"
    else:
        decision = "VAD_UPSTREAM_CONSUMPTION_DECOMPOSED_REVIEW_REQUIRED"

    public_partitions = []
    for item in partitions:
        public_partitions.append({
            "seed": item["seed"],
            "summary": item["summary"],
            "nonstationary": item["nonstationary"],
            "stationary": item["stationary"],
        })

    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "decision": decision,
        "fresh_seeds": actual_seeds,
        "shipping_mirror": {
            "max_probability_delta": max_mirror_delta,
            "probability_mismatch_frames": mirror_probability_mismatch_frames,
            "active_mismatch_frames": mirror_active_mismatch_frames,
        },
        "combined_nonstationary": combined_nonstationary,
        "combined_stationary": combined_stationary,
        "partitions": public_partitions,
        "input_violations": input_violations,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "shipping_source_changed": False,
        "interpretation": {
            "lane_selected": False,
            "guard_change_selected": False,
            "blend_change_selected": False,
            "vad_mapping_selected": False,
            "vad_threshold_selected": False,
            "note": (
                "The four fixed lanes are causal decomposition of existing shipping "
                "consumption paths. Their outcomes cannot select a lane, change guard/"
                "blend behavior, tune thresholds, or authorize shipping."
            ),
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    assert roc_auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0
    rows = []
    labels = [0, 0, 1, 1]
    for index, label in enumerate(labels):
        base = 0.1 + 0.2 * index
        row: dict[str, Any] = {}
        for lane in LANES:
            row[f"{lane}_probability"] = base
            row[f"{lane}_active"] = int(label)
        row["shipping_guard_active"] = 0
        row["shipping_blend_applied"] = 1
        row["shipping_transient_capped"] = 0
        row["shipping_noise_update_class"] = 0
        row["shipping_refresh_class"] = 1 if label else 0
        rows.append(row)
    summary = summarize_rows(rows, labels)
    assert summary["lane_metrics"]["shipping"]["recall"] == 1.0
    assert summary["lane_metrics"]["shipping"]["false_positive_rate"] == 0.0
    assert summary["lane_metrics"]["shipping"]["probability_auc"] == 1.0
    print("I015 VAD upstream consumption evaluator self-test: OK")


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
    if not args.probe or not args.contract or not args.corpus or not args.output:
        parser.error("--probe, --contract, --corpus and --output are required")

    result = evaluate(
        args.probe.resolve(),
        [path.resolve() for path in args.corpus],
        args.contract.resolve(),
        args.output.resolve(),
    )
    n = result["combined_nonstationary"]
    print(json.dumps({
        "decision": result["decision"],
        "fresh_seeds": result["fresh_seeds"],
        "mirror_max_delta": result["shipping_mirror"]["max_probability_delta"],
        "mirror_active_mismatches": result["shipping_mirror"]["active_mismatch_frames"],
        "shipping_recall": n["lane_metrics"]["shipping"]["recall"],
        "no_upstream_recall": n["lane_metrics"]["no_upstream"]["recall"],
        "blend_only_recall": n["lane_metrics"]["blend_only"]["recall"],
        "guard_only_recall": n["lane_metrics"]["guard_only"]["recall"],
        "shipping_fpr": n["lane_metrics"]["shipping"]["false_positive_rate"],
        "no_upstream_fpr": n["lane_metrics"]["no_upstream"]["false_positive_rate"],
        "rescued_speech_frames": n["rescued_speech_frames"],
        "added_noise_active_frames": n["added_noise_active_frames"],
        "active_diff_frames": n["shipping_vs_no_upstream_active_diff_frames"],
    }, sort_keys=True))
    return 2 if result["decision"] == (
        "VAD_UPSTREAM_CONSUMPTION_INPUT_INVALID_REVIEW_REQUIRED"
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
