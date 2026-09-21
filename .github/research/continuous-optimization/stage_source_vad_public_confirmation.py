#!/usr/bin/env python3
"""One-shot public AMI confirmation for the frozen VAD exact-source candidate."""
from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
import urllib.error
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))

import ami_vad_microset_eval as ami_eval
import i005_vad_baseline_measurement as event_metrics
import run_validation_engine as engine
import stage_profile_support

_BASE_INVOKE = engine.invoke
STAGE_INVOKE = stage_profile_support.build_invoke(engine)
assert engine.invoke is _BASE_INVOKE

RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def retry_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    for attempt in range(MAX_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_HTTP_STATUS or attempt + 1 >= MAX_ATTEMPTS:
                raise
            raw = error.headers.get("Retry-After") if error.headers is not None else None
            delay = None
            if raw:
                try:
                    delay = min(max(float(raw), 0.25), 8.0)
                except ValueError:
                    delay = None
            if delay is None:
                delay = min(float(1 << attempt), 8.0)
            time.sleep(delay)
    raise AssertionError("unreachable bounded retry loop")


def invoke_window(processor: Path, pcm_path: Path, corpus_path: Path,
                  window_id: str) -> tuple[list[float], list[int]]:
    case = {
        "case_id": window_id,
        "scenario": "ami-external-timing-real-speech",
        "sample_rate_hz": 16000,
        "mic_channels": 1,
        "mic_audio": pcm_path.name,
        "render_audio": None,
        "processor_profile": "ns-isolated",
        "control": {},
    }
    with tempfile.TemporaryDirectory(prefix="ap-vad-es2006a-run-") as work:
        _, trace, _ = STAGE_INVOKE(processor, case, corpus_path, Path(work))
    return (
        [float(row.get("vad_probability", 0.0)) for row in trace],
        [int(row.get("vad_active", 0)) for row in trace],
    )


def vad_stats(labels: list[int], active: list[int]) -> dict[str, float | None]:
    return engine.vad_stats(labels, [{"vad_active": value} for value in active])


def metric_delta(base: dict[str, Any], cand: dict[str, Any], key: str) -> float:
    return finite(cand[key], f"candidate {key}") - finite(base[key], f"baseline {key}")


def event_aggregate(reports: list[dict[str, Any]]) -> dict[str, Any]:
    return event_metrics.aggregate_reports(reports, 0, 1)["event"]


def apply_gates(
    contract: dict[str, Any],
    aggregate_base: dict[str, Any],
    aggregate_cand: dict[str, Any],
    event_base: dict[str, Any],
    event_cand: dict[str, Any],
    windows: list[dict[str, Any]],
    probability_mismatches: int,
    active_contractions: int,
    changed_active_frames: int,
) -> list[dict[str, Any]]:
    gates = contract["gates"]
    violations: list[dict[str, Any]] = []

    if gates["require_probability_trace_identity"] and probability_mismatches:
        violations.append({"gate": "probability_trace_identity", "count": probability_mismatches})
    if gates["require_no_active_contraction"] and active_contractions:
        violations.append({"gate": "active_contraction", "count": active_contractions})
    if gates["require_candidate_behavior_exercised"] and changed_active_frames <= 0:
        violations.append({"gate": "candidate_behavior_not_exercised"})

    recall_improvement = metric_delta(aggregate_base, aggregate_cand, "recall")
    f1_drop = -metric_delta(aggregate_base, aggregate_cand, "f1")
    fpr_rise = metric_delta(aggregate_base, aggregate_cand, "false_positive_rate")
    if recall_improvement < float(gates["min_aggregate_recall_improvement"]) - 1.0e-12:
        violations.append({
            "gate": "aggregate_recall_improvement",
            "actual": recall_improvement,
            "required": gates["min_aggregate_recall_improvement"],
        })
    if f1_drop > float(gates["max_aggregate_f1_drop"]) + 1.0e-12:
        violations.append({
            "gate": "aggregate_f1_drop",
            "actual": f1_drop,
            "allowed": gates["max_aggregate_f1_drop"],
        })
    if fpr_rise > float(gates["max_aggregate_fpr_rise"]) + 1.0e-12:
        violations.append({
            "gate": "aggregate_fpr_rise",
            "actual": fpr_rise,
            "allowed": gates["max_aggregate_fpr_rise"],
        })

    for item in windows:
        base = item["baseline"]
        cand = item["candidate"]
        recall_drop = -metric_delta(base, cand, "recall")
        f1_drop_window = -metric_delta(base, cand, "f1")
        fpr_rise_window = metric_delta(base, cand, "false_positive_rate")
        if recall_drop > float(gates["max_window_recall_drop"]) + 1.0e-12:
            violations.append({
                "gate": "window_recall_drop",
                "window_id": item["window_id"],
                "actual": recall_drop,
                "allowed": gates["max_window_recall_drop"],
            })
        if f1_drop_window > float(gates["max_window_f1_drop"]) + 1.0e-12:
            violations.append({
                "gate": "window_f1_drop",
                "window_id": item["window_id"],
                "actual": f1_drop_window,
                "allowed": gates["max_window_f1_drop"],
            })
        if fpr_rise_window > float(gates["max_window_fpr_rise"]) + 1.0e-12:
            violations.append({
                "gate": "window_fpr_rise",
                "window_id": item["window_id"],
                "actual": fpr_rise_window,
                "allowed": gates["max_window_fpr_rise"],
            })

    event_recall_drop = (
        finite(event_base["event_recall"], "baseline event recall")
        - finite(event_cand["event_recall"], "candidate event recall")
    )
    if event_recall_drop > float(gates["max_event_recall_drop"]) + 1.0e-12:
        violations.append({
            "gate": "event_recall_drop",
            "actual": event_recall_drop,
            "allowed": gates["max_event_recall_drop"],
        })

    def regression(key: str, gate: str, allowed: float) -> None:
        b = event_base.get(key)
        c = event_cand.get(key)
        if b is None and c is None:
            return
        if b is None or c is None:
            violations.append({"gate": gate + "_missing", "baseline": b, "candidate": c})
            return
        value = finite(c, gate + " candidate") - finite(b, gate + " baseline")
        if value > allowed + 1.0e-12:
            violations.append({"gate": gate, "actual": value, "allowed": allowed})

    regression(
        "onset_delay_p95_ms",
        "onset_p95_regression_ms",
        float(gates["max_onset_p95_regression_ms"]),
    )
    regression(
        "release_tail_p95_ms",
        "release_tail_p95_regression_ms",
        float(gates["max_release_tail_p95_regression_ms"]),
    )
    return violations


def confirm(base_processor: Path, candidate_processor: Path, lock_path: Path,
            contract_path: Path, output: Path) -> dict[str, Any]:
    contract = load(contract_path)
    lock = load(lock_path)
    if contract.get("authority") != "INDEPENDENT_PUBLIC_SOURCE_CONFIRMATION_ONLY":
        raise ValueError("unexpected public confirmation authority")
    if contract.get("candidate_id") != "vad-confidence-tiered-hold-v1":
        raise ValueError("unexpected public candidate")
    if lock.get("dataset", {}).get("meeting") != "ES2006a":
        raise ValueError("public authority must remain ES2006a")
    if lock.get("confirmation_policy", {}).get("candidate_id") != contract["candidate_id"]:
        raise ValueError("public lock candidate identity drift")
    if lock.get("confirmation_policy", {}).get("public_confirmation_consumed") is not False:
        raise ValueError("public authority already marked consumed before one-shot confirmation")
    ami_eval.validate_lock(lock)

    intervals, annotation_evidence = ami_eval.load_annotations(lock)
    audio_url = ami_eval.discovery.hf_resolve_url(str(lock["audio"]["path"]))

    aggregate_labels: list[int] = []
    aggregate_base_active: list[int] = []
    aggregate_cand_active: list[int] = []
    event_base_reports: list[dict[str, Any]] = []
    event_cand_reports: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    total_probability_mismatch = 0
    total_active_contraction = 0
    total_changed = 0

    with tempfile.TemporaryDirectory(prefix="ap-vad-es2006a-") as temporary:
        root = Path(temporary)
        corpus_path = root / "corpus.json"
        corpus_path.write_text('{"schema_version":1,"cases":[]}\n', encoding="utf-8")

        for window in lock["windows"]:
            start = int(window["start_byte"])
            end = int(window["end_byte"])
            pcm = retry_call(ami_eval.request_exact_range, audio_url, start, end)
            digest = ami_eval.sha256_bytes(pcm)
            if digest != window["sha256"] or len(pcm) != int(window["length_bytes"]):
                raise ValueError(f"audio window identity drifted: {window['window_id']}")
            pcm_path = root / f"{window['window_id']}.pcm"
            pcm_path.write_bytes(pcm)

            labels = ami_eval.labels_for_window(
                intervals, float(window["start_s"]), float(window["end_s"])
            )
            measured_activity = sum(labels) / len(labels)
            if abs(measured_activity - float(window["activity_fraction"])) > 0.005:
                raise ValueError(f"annotation activity drifted: {window['window_id']}")

            base_prob, base_active = invoke_window(
                base_processor, pcm_path, corpus_path, str(window["window_id"])
            )
            cand_prob, cand_active = invoke_window(
                candidate_processor, pcm_path, corpus_path, str(window["window_id"])
            )
            count = min(len(labels), len(base_prob), len(base_active), len(cand_prob), len(cand_active))
            if count < 1900:
                raise ValueError(f"insufficient public confirmation frames: {window['window_id']} count={count}")
            labels = labels[:count]
            base_prob = base_prob[:count]
            cand_prob = cand_prob[:count]
            base_active = base_active[:count]
            cand_active = cand_active[:count]

            probability_mismatch = sum(abs(x - y) > 1.0e-7 for x, y in zip(base_prob, cand_prob))
            active_contraction = sum(b == 1 and c == 0 for b, c in zip(base_active, cand_active))
            changed = sum(b != c for b, c in zip(base_active, cand_active))
            total_probability_mismatch += probability_mismatch
            total_active_contraction += active_contraction
            total_changed += changed

            base_stats = vad_stats(labels, base_active)
            cand_stats = vad_stats(labels, cand_active)
            aggregate_labels.extend(labels)
            aggregate_base_active.extend(base_active)
            aggregate_cand_active.extend(cand_active)
            event_base_reports.append({"labels": labels, "predicted": base_active})
            event_cand_reports.append({"labels": labels, "predicted": cand_active})
            windows.append({
                "window_id": window["window_id"],
                "activity_fraction": measured_activity,
                "audio_sha256": digest,
                "frames": count,
                "probability_mismatches": probability_mismatch,
                "active_contractions": active_contraction,
                "changed_active_frames": changed,
                "baseline": base_stats,
                "candidate": cand_stats,
                "deltas": {
                    "recall": metric_delta(base_stats, cand_stats, "recall"),
                    "f1": metric_delta(base_stats, cand_stats, "f1"),
                    "false_positive_rate": metric_delta(base_stats, cand_stats, "false_positive_rate"),
                },
            })

    aggregate_base = vad_stats(aggregate_labels, aggregate_base_active)
    aggregate_cand = vad_stats(aggregate_labels, aggregate_cand_active)
    event_base = event_aggregate(event_base_reports)
    event_cand = event_aggregate(event_cand_reports)
    violations = apply_gates(
        contract, aggregate_base, aggregate_cand, event_base, event_cand,
        windows, total_probability_mismatch, total_active_contraction, total_changed,
    )
    result = {
        "schema_version": 1,
        "authority": "independent-public-source-confirmation-only",
        "candidate_id": contract["candidate_id"],
        "decision": contract["outcome"]["pass"] if not violations else contract["outcome"]["reject"],
        "public_authority": {
            "meeting": lock["dataset"]["meeting"],
            "license": lock["dataset"]["license"],
            "lock_path": str(lock_path),
            "transport_revision": lock["transport_mirror"]["revision"],
            "annotation_semantics": lock["dataset"]["annotation_semantics"],
        },
        "annotations": annotation_evidence,
        "probability_mismatches": total_probability_mismatch,
        "active_contractions": total_active_contraction,
        "changed_active_frames": total_changed,
        "aggregate": {
            "baseline": aggregate_base,
            "candidate": aggregate_cand,
            "deltas": {
                "recall": metric_delta(aggregate_base, aggregate_cand, "recall"),
                "f1": metric_delta(aggregate_base, aggregate_cand, "f1"),
                "false_positive_rate": metric_delta(aggregate_base, aggregate_cand, "false_positive_rate"),
            },
        },
        "event": {
            "baseline": event_base,
            "candidate": event_cand,
        },
        "windows": windows,
        "violations": violations,
        "public_authority_consumed": True,
        "shipping_authority": False,
        "source_merge_authorized": False,
        "automatic_main_mutation": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    assert engine.invoke is _BASE_INVOKE
    contract = {
        "gates": {
            "require_probability_trace_identity": True,
            "require_no_active_contraction": True,
            "require_candidate_behavior_exercised": True,
            "min_aggregate_recall_improvement": 0.005,
            "max_aggregate_f1_drop": 0.02,
            "max_aggregate_fpr_rise": 0.01,
            "max_window_recall_drop": 0.0,
            "max_window_f1_drop": 0.03,
            "max_window_fpr_rise": 0.01,
            "max_event_recall_drop": 0.0,
            "max_onset_p95_regression_ms": 0.0,
            "max_release_tail_p95_regression_ms": 25.0,
        }
    }
    base = {"recall": 0.80, "f1": 0.82, "false_positive_rate": 0.20}
    cand = {"recall": 0.81, "f1": 0.825, "false_positive_rate": 0.205}
    event_base = {"event_recall": 0.9, "onset_delay_p95_ms": 10.0, "release_tail_p95_ms": 80.0}
    event_cand = {"event_recall": 0.9, "onset_delay_p95_ms": 10.0, "release_tail_p95_ms": 100.0}
    windows = [{"window_id": "w1", "baseline": base, "candidate": cand}]
    assert not apply_gates(contract, base, cand, event_base, event_cand, windows, 0, 0, 3)
    bad = dict(cand)
    bad["recall"] = 0.801
    assert any(
        item["gate"] == "aggregate_recall_improvement"
        for item in apply_gates(contract, base, bad, event_base, event_cand, windows, 0, 0, 3)
    )
    assert engine.invoke is _BASE_INVOKE
    print("VAD ES2006a public confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-processor", type=Path)
    parser.add_argument("--candidate-processor", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if None in (args.base_processor, args.candidate_processor, args.lock, args.contract, args.output):
        parser.error("base processor, candidate processor, lock, contract and output are required")
    result = confirm(
        args.base_processor.resolve(),
        args.candidate_processor.resolve(),
        args.lock.resolve(),
        args.contract.resolve(),
        args.output.resolve(),
    )
    print(json.dumps({
        "candidate_id": result["candidate_id"],
        "decision": result["decision"],
        "changed_active_frames": result["changed_active_frames"],
        "probability_mismatches": result["probability_mismatches"],
        "active_contractions": result["active_contractions"],
        "violations": len(result["violations"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
