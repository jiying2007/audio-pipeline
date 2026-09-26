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

CASES = ("stage-ns-nonstationary", "stage-ns-stationary")
WARMUP = 80
LABELS = ("speech", "noise")
ORIGINS = ("local_admissible", "blend_dependent")
GUARDS = ("guard_active", "guard_inactive")
CROSS = tuple(f"{origin}_{guard}" for origin in ORIGINS for guard in GUARDS)
PROBS = (
    "raw_probability",
    "pre_blend_probability",
    "upstream_probability",
    "shipping_probability",
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def run_probe(probe: Path, pcm: Path) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [str(probe), str(pcm)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("probe output invalid")
    return rows


def empty_counts(keys: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {key: {label: 0 for label in LABELS} for key in keys}


def speech_fraction(counts: dict[str, int]) -> float | None:
    total = sum(counts.values())
    return counts["speech"] / total if total else None


def analyze(rows: list[dict[str, Any]], labels: list[int]) -> dict[str, Any]:
    if len(rows) != len(labels) or not rows:
        raise ValueError("row/label geometry mismatch")

    origin = empty_counts(ORIGINS)
    guard = empty_counts(GUARDS)
    cross = empty_counts(CROSS)
    components = empty_counts(
        ("upstream_guard_pass", "local_guard_pass", "blend_applied")
    )
    totals = {label: 0 for label in LABELS}
    prob_sum = {
        label: {field: 0.0 for field in PROBS}
        for label in LABELS
    }
    mirror_delta = 0.0
    mirror_active = 0

    for row, numeric_label in zip(rows, labels):
        if numeric_label not in (0, 1):
            raise ValueError(f"invalid label: {numeric_label}")
        values = [float(row[field]) for field in PROBS]
        public_prob = float(row["public_shipping_probability"])
        if not all(math.isfinite(value) for value in values + [public_prob]):
            raise ValueError("non-finite probability")

        shipping_prob = float(row["shipping_probability"])
        shipping_active = int(row["shipping_active"])
        public_active = int(row["public_shipping_active"])
        mirror_delta = max(mirror_delta, abs(public_prob - shipping_prob))
        mirror_active += int(public_active != shipping_active)

        pre = int(row["pre_hangover"])
        post = int(row["post_hangover"])
        refresh = int(row["refresh_kind"])
        is_weak_start = (
            pre == 0
            and refresh == 1
            and post == 6
            and shipping_active == 1
        )
        if not is_weak_start:
            continue

        if not (shipping_prob > 0.35 and shipping_prob < 0.50):
            raise ValueError("weak-start probability outside frozen weak band")

        label = "speech" if numeric_label else "noise"
        totals[label] += 1

        pre_blend = float(row["pre_blend_probability"])
        local_origin = pre_blend > 0.35
        origin_key = "local_admissible" if local_origin else "blend_dependent"
        if not local_origin and int(row["blend_applied"]) != 1:
            raise ValueError("blend-dependent weak start without blend")

        guard_key = "guard_active" if int(row["guard_active"]) else "guard_inactive"
        origin[origin_key][label] += 1
        guard[guard_key][label] += 1
        cross[f"{origin_key}_{guard_key}"][label] += 1

        for field in ("upstream_guard_pass", "local_guard_pass", "blend_applied"):
            if int(row[field]):
                components[field][label] += 1

        for field in PROBS:
            prob_sum[label][field] += float(row[field])

    means: dict[str, dict[str, float | None]] = {}
    for label in LABELS:
        means[label] = {}
        for field in PROBS:
            means[label][field] = (
                prob_sum[label][field] / totals[label]
                if totals[label]
                else None
            )

    return {
        "weak_start_events": {
            "total": sum(totals.values()),
            "speech": totals["speech"],
            "noise": totals["noise"],
            "speech_fraction": (
                totals["speech"] / sum(totals.values())
                if sum(totals.values())
                else None
            ),
        },
        "pre_blend_origin": {
            key: {
                **origin[key],
                "total": sum(origin[key].values()),
                "speech_fraction": speech_fraction(origin[key]),
            }
            for key in ORIGINS
        },
        "existing_guard": {
            key: {
                **guard[key],
                "total": sum(guard[key].values()),
                "speech_fraction": speech_fraction(guard[key]),
            }
            for key in GUARDS
        },
        "cross_cells": {
            key: {
                **cross[key],
                "total": sum(cross[key].values()),
                "speech_fraction": speech_fraction(cross[key]),
            }
            for key in CROSS
        },
        "fixed_component_positive_counts": components,
        "mean_probabilities": means,
        "shipping_mirror": {
            "max_probability_delta": mirror_delta,
            "active_mismatch_frames": mirror_active,
        },
    }


def evaluate_case(
    probe: Path, corpus_path: Path, case: dict[str, Any]
) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing audio/labels")
    with tempfile.TemporaryDirectory(prefix="ap-i019-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    return analyze(rows[WARMUP:count], labels[WARMUP:count])


def merge(parts: list[dict[str, Any]]) -> dict[str, Any]:
    merged_totals = {label: 0 for label in LABELS}
    merged_origin = empty_counts(ORIGINS)
    merged_guard = empty_counts(GUARDS)
    merged_cross = empty_counts(CROSS)
    merged_components = empty_counts(
        ("upstream_guard_pass", "local_guard_pass", "blend_applied")
    )
    weighted = {
        label: {field: 0.0 for field in PROBS}
        for label in LABELS
    }

    for part in parts:
        events = part["weak_start_events"]
        for label in LABELS:
            count = int(events[label])
            merged_totals[label] += count
            for field in PROBS:
                mean = part["mean_probabilities"][label][field]
                if mean is not None:
                    weighted[label][field] += float(mean) * count
        for key in ORIGINS:
            for label in LABELS:
                merged_origin[key][label] += int(part["pre_blend_origin"][key][label])
        for key in GUARDS:
            for label in LABELS:
                merged_guard[key][label] += int(part["existing_guard"][key][label])
        for key in CROSS:
            for label in LABELS:
                merged_cross[key][label] += int(part["cross_cells"][key][label])
        for key in merged_components:
            for label in LABELS:
                merged_components[key][label] += int(
                    part["fixed_component_positive_counts"][key][label]
                )

    total = sum(merged_totals.values())
    return {
        "weak_start_events": {
            "total": total,
            "speech": merged_totals["speech"],
            "noise": merged_totals["noise"],
            "speech_fraction": merged_totals["speech"] / total if total else None,
        },
        "pre_blend_origin": {
            key: {
                **merged_origin[key],
                "total": sum(merged_origin[key].values()),
                "speech_fraction": speech_fraction(merged_origin[key]),
            }
            for key in ORIGINS
        },
        "existing_guard": {
            key: {
                **merged_guard[key],
                "total": sum(merged_guard[key].values()),
                "speech_fraction": speech_fraction(merged_guard[key]),
            }
            for key in GUARDS
        },
        "cross_cells": {
            key: {
                **merged_cross[key],
                "total": sum(merged_cross[key].values()),
                "speech_fraction": speech_fraction(merged_cross[key]),
            }
            for key in CROSS
        },
        "fixed_component_positive_counts": merged_components,
        "mean_probabilities": {
            label: {
                field: (
                    weighted[label][field] / merged_totals[label]
                    if merged_totals[label]
                    else None
                )
                for field in PROBS
            }
            for label in LABELS
        },
        "shipping_mirror": {
            "max_probability_delta": max(
                float(part["shipping_mirror"]["max_probability_delta"])
                for part in parts
            ),
            "active_mismatch_frames": sum(
                int(part["shipping_mirror"]["active_mismatch_frames"])
                for part in parts
            ),
        },
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str, Any]:
    contract = load_json(contract_path)
    if contract["investigation_id"] != "i019-vad-weak-start-evidence-decomposition-v1":
        raise ValueError("contract identity drift")
    if contract["budget"] != {
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_execution_limit": 1,
    }:
        raise ValueError("budget drift")

    expected_seeds = [
        int(value) for value in contract["fresh_diagnostic_authority"]["seeds"]
    ]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")

    partitions: dict[str, list[dict[str, Any]]] = {case: [] for case in CASES}
    per_seed: list[dict[str, Any]] = []
    actual_seeds: list[int] = []

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
            and str(case.get("case_id")) in CASES
        }
        if set(selected) != set(CASES):
            raise ValueError(f"missing required cases for seed {seed}")
        seed_result: dict[str, Any] = {"seed": seed, "cases": {}}
        for case_id in CASES:
            result = evaluate_case(probe, corpus_path, selected[case_id])
            partitions[case_id].append(result)
            seed_result["cases"][case_id] = result
        per_seed.append(seed_result)

    if actual_seeds != expected_seeds:
        raise ValueError(f"seed mismatch: {actual_seeds}")

    summaries = {case_id: merge(parts) for case_id, parts in partitions.items()}
    mirror = {
        "max_probability_delta": max(
            value["shipping_mirror"]["max_probability_delta"]
            for value in summaries.values()
        ),
        "active_mismatch_frames": sum(
            value["shipping_mirror"]["active_mismatch_frames"]
            for value in summaries.values()
        ),
    }

    gates = contract["input_gates"]
    valid = (
        mirror["max_probability_delta"]
        <= float(gates["max_shipping_mirror_probability_delta"])
        and mirror["active_mismatch_frames"]
        == int(gates["shipping_mirror_active_mismatch_frames"])
    )
    invalid_reasons: list[str] = []
    for case_id, summary in summaries.items():
        events = summary["weak_start_events"]
        if int(events["speech"]) < int(
            gates["min_speech_weak_start_events_per_domain"]
        ):
            valid = False
            invalid_reasons.append(f"{case_id}:speech_weak_start")
        if int(events["noise"]) < int(
            gates["min_noise_weak_start_events_per_domain"]
        ):
            valid = False
            invalid_reasons.append(f"{case_id}:noise_weak_start")

    decision = (
        "VAD_WEAK_START_EVIDENCE_DECOMPOSED_REVIEW_REQUIRED"
        if valid
        else "I019_INPUT_INVALID_REVIEW_REQUIRED"
    )
    result = {
        "schema_version": 1,
        "investigation_id": contract["investigation_id"],
        "authority": contract["authority"],
        "source_base_sha": contract["source_base_sha"],
        "fresh_diagnostic_seeds": actual_seeds,
        "candidate_budget_consumed": 0,
        "confirmation_budget_consumed": 0,
        "diagnostic_execution_consumed": 1,
        "shipping_mirror": mirror,
        "per_seed": per_seed,
        "summaries": summaries,
        "decision": decision,
        "invalid_reasons": invalid_reasons,
        "authority_boundary": contract["authority_boundary"],
    }
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    base = {
        "public_shipping_probability": 0.4,
        "public_shipping_active": 1,
        "shipping_probability": 0.4,
        "shipping_active": 1,
        "raw_probability": 0.20,
        "pre_blend_probability": 0.20,
        "upstream_probability": 0.70,
        "pre_hangover": 0,
        "post_hangover": 6,
        "refresh_kind": 1,
        "guard_active": 1,
        "upstream_guard_pass": 1,
        "local_guard_pass": 1,
        "blend_applied": 1,
    }
    local = dict(base)
    local["pre_blend_probability"] = 0.40
    noise = dict(base)
    noise["guard_active"] = 0
    noise["local_guard_pass"] = 0
    result = analyze([base, local, noise], [1, 1, 0])
    assert result["weak_start_events"] == {
        "total": 3, "speech": 2, "noise": 1, "speech_fraction": 2 / 3
    }
    assert result["pre_blend_origin"]["local_admissible"]["speech"] == 1
    assert result["pre_blend_origin"]["blend_dependent"]["speech"] == 1
    assert result["pre_blend_origin"]["blend_dependent"]["noise"] == 1
    assert result["cross_cells"]["blend_dependent_guard_active"]["speech"] == 1
    assert result["cross_cells"]["blend_dependent_guard_inactive"]["noise"] == 1
    print("I019 weak-start evidence evaluator self-test: OK")


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
        parser.error("--probe --contract --corpus --output are required")
    result = evaluate(args.probe, args.corpus, args.contract, args.output)
    print(json.dumps(
        {"decision": result["decision"], "invalid_reasons": result["invalid_reasons"]},
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
