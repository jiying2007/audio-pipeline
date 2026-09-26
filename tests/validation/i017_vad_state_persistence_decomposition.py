#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import run_validation_engine as engine  # type: ignore

CASES = ("stage-ns-nonstationary", "stage-ns-stationary")
WARMUP = 80
REFRESH = {0: "hangover_carry", 1: "weak_refresh", 2: "strong_refresh"}


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


def add(counter: Counter[str], key: str) -> None:
    counter[key] += 1


def analyze(rows: list[dict[str, Any]], labels: list[int]) -> dict[str, Any]:
    if len(rows) != len(labels) or not rows:
        raise ValueError("row/label geometry mismatch")

    frame_origins: Counter[str] = Counter()
    segment_starts: Counter[str] = Counter()
    refresh_extensions: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    previous_label = 0
    previous_active = 0

    for index, (row, label) in enumerate(zip(rows, labels)):
        prob = float(row["shipping_probability"])
        public_prob = float(row["public_shipping_probability"])
        active = int(row["shipping_active"])
        public_active = int(row["public_shipping_active"])
        pre = int(row["pre_hangover"])
        post = int(row["post_hangover"])
        refresh = int(row["refresh_kind"])
        if refresh not in REFRESH:
            raise ValueError(f"unknown refresh kind: {refresh}")
        if not all(math.isfinite(x) for x in (prob, public_prob)):
            raise ValueError("non-finite probability")
        if active != int(post > 0):
            raise ValueError("active/post-hangover identity mismatch")
        if public_active != active:
            totals["mirror_active_mismatch_frames"] += 1
        totals["frames"] += 1
        totals["speech_frames" if label else "noise_frames"] += 1
        totals["active_frames" if active else "inactive_frames"] += 1
        totals["max_probability_delta_scaled"] = max(
            totals["max_probability_delta_scaled"],
            int(round(abs(public_prob - prob) * 1_000_000_000_000)),
        )

        if not label and active:
            totals["noise_active_frames"] += 1
            if refresh == 2:
                add(frame_origins, "strong_refresh")
            elif refresh == 1:
                add(frame_origins, "weak_refresh")
            elif pre > 0 and post > 0:
                add(frame_origins, "hangover_carry")
            else:
                raise ValueError("noise-active frame has no state origin")

            previous_noise_active = (
                index > 0 and previous_label == 0 and previous_active == 1
            )
            if not previous_noise_active:
                if refresh == 2:
                    add(segment_starts, "strong_refresh")
                elif refresh == 1:
                    add(segment_starts, "weak_refresh")
                elif pre > 0:
                    add(segment_starts, "carry_from_prior_active")
                else:
                    raise ValueError("noise-active segment start has no origin")

            if pre > 0 and refresh == 2:
                add(refresh_extensions, "strong_refresh")
            elif pre > 0 and refresh == 1:
                add(refresh_extensions, "weak_refresh")

            if index > 0 and previous_label == 1 and previous_active == 1:
                totals["speech_to_noise_active_boundary_frames"] += 1

        previous_label = label
        previous_active = active

    if sum(frame_origins.values()) != totals["noise_active_frames"]:
        raise ValueError("noise-active attribution does not partition frames")

    return {
        "frames": totals["frames"],
        "speech_frames": totals["speech_frames"],
        "noise_frames": totals["noise_frames"],
        "noise_active_frames": totals["noise_active_frames"],
        "noise_false_positive_rate": (
            totals["noise_active_frames"] / totals["noise_frames"]
        ),
        "noise_active_frame_origin": {
            key: frame_origins[key]
            for key in ("strong_refresh", "weak_refresh", "hangover_carry")
        },
        "noise_active_segment_start_origin": {
            key: segment_starts[key]
            for key in ("strong_refresh", "weak_refresh", "carry_from_prior_active")
        },
        "noise_refresh_extension_events": {
            key: refresh_extensions[key]
            for key in ("strong_refresh", "weak_refresh")
        },
        "speech_to_noise_active_boundary_frames":
            totals["speech_to_noise_active_boundary_frames"],
        "shipping_mirror": {
            "active_mismatch_frames": totals["mirror_active_mismatch_frames"],
            "max_probability_delta":
                totals["max_probability_delta_scaled"] / 1_000_000_000_000.0,
        },
    }


def evaluate_case(probe: Path, corpus_path: Path, case: dict[str, Any]) -> dict[str, Any]:
    mic = engine.resolve(corpus_path, case.get("mic_audio"))
    labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
    if mic is None or labels_path is None:
        raise ValueError("case missing audio/labels")
    with tempfile.TemporaryDirectory(prefix="ap-i017-") as tmp:
        _, raw = engine.stage_audio(mic, 16000, 1, Path(tmp), "mic.pcm")
        rows = run_probe(probe, raw)
    labels = [int(value) for value in engine.load_labels(labels_path)]
    count = min(len(rows), len(labels))
    if count <= WARMUP:
        raise ValueError("case too short")
    return analyze(rows[WARMUP:count], labels[WARMUP:count])


def merge(parts: list[dict[str, Any]]) -> dict[str, Any]:
    total_noise = sum(int(part["noise_frames"]) for part in parts)
    total_noise_active = sum(int(part["noise_active_frames"]) for part in parts)
    frame_origin = {
        key: sum(int(part["noise_active_frame_origin"][key]) for part in parts)
        for key in ("strong_refresh", "weak_refresh", "hangover_carry")
    }
    segment_origin = {
        key: sum(int(part["noise_active_segment_start_origin"][key]) for part in parts)
        for key in ("strong_refresh", "weak_refresh", "carry_from_prior_active")
    }
    extension = {
        key: sum(int(part["noise_refresh_extension_events"][key]) for part in parts)
        for key in ("strong_refresh", "weak_refresh")
    }
    if sum(frame_origin.values()) != total_noise_active:
        raise ValueError("merged attribution does not partition noise-active frames")
    return {
        "frames": sum(int(part["frames"]) for part in parts),
        "speech_frames": sum(int(part["speech_frames"]) for part in parts),
        "noise_frames": total_noise,
        "noise_active_frames": total_noise_active,
        "noise_false_positive_rate": total_noise_active / total_noise,
        "noise_active_frame_origin": frame_origin,
        "noise_active_frame_origin_fraction": {
            key: (frame_origin[key] / total_noise_active if total_noise_active else 0.0)
            for key in frame_origin
        },
        "noise_active_segment_start_origin": segment_origin,
        "noise_refresh_extension_events": extension,
        "speech_to_noise_active_boundary_frames": sum(
            int(part["speech_to_noise_active_boundary_frames"]) for part in parts
        ),
        "shipping_mirror": {
            "active_mismatch_frames": sum(
                int(part["shipping_mirror"]["active_mismatch_frames"]) for part in parts
            ),
            "max_probability_delta": max(
                float(part["shipping_mirror"]["max_probability_delta"]) for part in parts
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
    if contract["investigation_id"] != "i017-vad-state-persistence-decomposition-v1":
        raise ValueError("contract identity drift")
    if contract["budget"] != {
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_execution_limit": 1,
    }:
        raise ValueError("budget drift")
    expected_seeds = [int(x) for x in contract["fresh_diagnostic_authority"]["seeds"]]
    if len(corpora) != len(expected_seeds):
        raise ValueError("corpus count mismatch")

    per_case: dict[str, list[dict[str, Any]]] = {case: [] for case in CASES}
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
            per_case[case_id].append(result)
            seed_result["cases"][case_id] = result
        per_seed.append(seed_result)

    if actual_seeds != expected_seeds:
        raise ValueError(f"seed mismatch: {actual_seeds}")

    summaries = {case_id: merge(parts) for case_id, parts in per_case.items()}
    mirror = {
        "active_mismatch_frames": sum(
            value["shipping_mirror"]["active_mismatch_frames"]
            for value in summaries.values()
        ),
        "max_probability_delta": max(
            value["shipping_mirror"]["max_probability_delta"]
            for value in summaries.values()
        ),
    }
    gates = contract["input_gates"]
    valid = (
        mirror["active_mismatch_frames"]
        == int(gates["shipping_mirror_active_mismatch_frames"])
        and mirror["max_probability_delta"]
        <= float(gates["max_shipping_mirror_probability_delta"])
    )
    decision = (
        "VAD_STATE_PERSISTENCE_DECOMPOSED_REVIEW_REQUIRED"
        if valid
        else "I017_INPUT_INVALID_REVIEW_REQUIRED"
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
        "authority_boundary": contract["authority_boundary"],
    }
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    rows = [
        {"shipping_probability": 0.6, "public_shipping_probability": 0.6,
         "shipping_active": 1, "public_shipping_active": 1,
         "pre_hangover": 0, "post_hangover": 8, "refresh_kind": 2},
        {"shipping_probability": 0.2, "public_shipping_probability": 0.2,
         "shipping_active": 1, "public_shipping_active": 1,
         "pre_hangover": 8, "post_hangover": 7, "refresh_kind": 0},
        {"shipping_probability": 0.4, "public_shipping_probability": 0.4,
         "shipping_active": 1, "public_shipping_active": 1,
         "pre_hangover": 0, "post_hangover": 6, "refresh_kind": 1},
    ]
    result = analyze(rows, [0, 0, 0])
    assert result["noise_active_frame_origin"] == {
        "strong_refresh": 1, "weak_refresh": 1, "hangover_carry": 1
    }
    assert result["noise_active_segment_start_origin"] == {
        "strong_refresh": 1, "weak_refresh": 0, "carry_from_prior_active": 0
    }
    print("I017 state-persistence evaluator self-test: OK")


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
    print(json.dumps({"decision": result["decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
