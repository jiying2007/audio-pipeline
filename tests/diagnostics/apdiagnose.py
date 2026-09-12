#!/usr/bin/env python3
"""Repository-internal reasoning over terminal aptriage JSON evidence."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "critical": 3}
KIND_SEVERITY = {
    "trigger_event": "info",
    "quality_transition": "warning",
    "render_underrun": "error",
    "reference_sample_slip": "error",
    "delay_jump": "error",
    "aec_reset": "error",
    "aec_convergence_lost": "error",
    "metadata": "warning",
}
CRITICAL_METADATA_FLAGS = {"clock_reset", "codec_reopen"}
ERROR_METADATA_FLAGS = {"capture_discontinuity", "render_discontinuity", "xrun"}
KIND_ORDER = {"metadata": 0, "trigger_event": 2}

EVENT_NAMES = {
    1: "runtime_started",
    2: "runtime_stopped",
    3: "rt_affinity_failed",
    4: "rt_priority_failed",
    5: "rt_mlock_failed",
    10: "input_queue_high",
    11: "input_queue_full",
    12: "output_dropped",
    13: "dsp_deadline_miss",
    20: "render_missing",
    21: "render_underrun",
    22: "delay_jump",
    23: "stream_discontinuity",
    24: "echo_path_change",
    30: "aec_reset",
    31: "aec_converged",
    32: "erle_collapse",
    40: "quality_full_to_lite",
    41: "quality_lite_to_safe",
    42: "quality_recovered",
    43: "quality_degraded",
    50: "diag_triggered",
    51: "command_rejected",
    52: "pipeline_error",
    53: "cpu_migration",
}

RAW_COUNT_DENOMINATORS = {
    "anomaly_count": "frames",
    "quality_transitions": "metrics_frames",
    "vad_transitions": "metrics_frames",
    "far_end_active_frames": "metrics_frames",
    "double_talk_active_frames": "metrics_frames",
    "aec_converged_frames": "metrics_frames",
}

NORMALIZED_METRICS = {
    "anomaly_rate_per_1000_frames": (
        "anomaly_count", "frames", 1000.0, "events/1000_frames"
    ),
    "quality_transition_rate_per_1000_metrics_frames": (
        "quality_transitions", "metrics_frames", 1000.0, "transitions/1000_metrics_frames"
    ),
    "vad_transition_rate_per_1000_metrics_frames": (
        "vad_transitions", "metrics_frames", 1000.0, "transitions/1000_metrics_frames"
    ),
    "far_end_active_ratio": (
        "far_end_active_frames", "metrics_frames", 1.0, "ratio"
    ),
    "double_talk_active_ratio": (
        "double_talk_active_frames", "metrics_frames", 1.0, "ratio"
    ),
    "aec_converged_ratio": (
        "aec_converged_frames", "metrics_frames", 1.0, "ratio"
    ),
}

HYPOTHESIS_SPECS = (
    {
        "name": "sync-reference-path",
        "kinds": {"delay_jump", "reference_sample_slip", "render_underrun"},
        "kind_weights": {
            "delay_jump": 3,
            "reference_sample_slip": 3,
            "render_underrun": 2,
        },
        "metadata_weights": {
            "render_discontinuity": 4,
            "clock_reset": 4,
            "xrun": 1,
        },
    },
    {
        "name": "aec-adaptation",
        "kinds": {"aec_reset", "aec_convergence_lost", "delay_jump"},
        "kind_weights": {
            "aec_reset": 3,
            "aec_convergence_lost": 2,
            "delay_jump": 1,
        },
        "metadata_weights": {
            "render_discontinuity": 1,
            "clock_reset": 1,
        },
    },
    {
        "name": "capture-io",
        "kinds": set(),
        "kind_weights": {},
        "metadata_weights": {
            "capture_discontinuity": 4,
            "codec_reopen": 4,
            "xrun": 1,
        },
    },
    {
        "name": "runtime-continuity",
        "kinds": {"render_underrun"},
        "kind_weights": {"render_underrun": 2},
        "metadata_weights": {
            "xrun": 4,
            "codec_reopen": 1,
        },
    },
)


def recording_trigger_context(event: Any) -> dict[str, Any] | None:
    if isinstance(event, bool) or not isinstance(event, int) or event <= 0:
        return None
    return {
        "event": event,
        "name": EVENT_NAMES.get(event, f"unknown_event_{event}"),
        "source": "apd-header",
        "relation": "recording-trigger-context-only",
        "causal_proof": False,
    }


def _metadata_flags(item: dict[str, Any]) -> set[str]:
    return {str(flag) for flag in (item.get("flags") or [])}


def _severity(item: dict[str, Any]) -> str:
    if item.get("kind") != "metadata":
        return KIND_SEVERITY.get(str(item.get("kind")), "warning")
    flags = _metadata_flags(item)
    if flags & CRITICAL_METADATA_FLAGS:
        return "critical"
    if flags & ERROR_METADATA_FLAGS:
        return "error"
    return "warning"


def _family(item: dict[str, Any]) -> str:
    kind = str(item.get("kind"))
    if kind in {"delay_jump", "reference_sample_slip", "render_underrun"}:
        return "sync-reference"
    if kind in {"aec_reset", "aec_convergence_lost"}:
        return "aec"
    if kind == "quality_transition":
        return "quality-control"
    if kind == "metadata":
        flags = _metadata_flags(item)
        if flags & {"render_discontinuity", "clock_reset"}:
            return "sync-reference"
        if flags & {"capture_discontinuity", "codec_reopen"}:
            return "capture-io"
        if "xrun" in flags:
            return "runtime-continuity"
        return "metadata"
    if kind == "trigger_event":
        return "trigger"
    return "other"


def annotate_anomalies(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = []
    for anomaly in anomalies:
        item = dict(anomaly)
        item["severity"] = _severity(item)
        item["family"] = _family(item)
        annotated.append(item)
    return sorted(
        annotated,
        key=lambda item: (
            int(item.get("frame", 0)),
            KIND_ORDER.get(str(item.get("kind", "")), 1),
            str(item.get("kind", "")),
        ),
    )


def _interval(events: list[dict[str, Any]]) -> dict[str, Any]:
    max_severity = max(events, key=lambda item: SEVERITY_ORDER[item["severity"]])[
        "severity"
    ]
    return {
        "start_frame": int(events[0]["frame"]),
        "end_frame": int(events[-1]["frame"]),
        "event_count": len(events),
        "kinds": sorted({str(item["kind"]) for item in events}),
        "families": sorted({str(item["family"]) for item in events}),
        "max_severity": max_severity,
    }


def build_intervals(
    annotated: list[dict[str, Any]], gap_frames: int = 10
) -> list[dict[str, Any]]:
    events = [item for item in annotated if item.get("kind") != "trigger_event"]
    if not events:
        return []
    intervals: list[dict[str, Any]] = []
    current = [events[0]]
    for item in events[1:]:
        if int(item["frame"]) - int(current[-1]["frame"]) <= gap_frames:
            current.append(item)
        else:
            intervals.append(_interval(current))
            current = [item]
    intervals.append(_interval(current))
    return intervals


def first_fault(annotated: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in annotated:
        if item.get("kind") != "trigger_event":
            return item
    return None


def _evidence_for_spec(
    annotated: list[dict[str, Any]], spec: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    evidence: list[dict[str, Any]] = []
    score = 0
    kinds = set(spec["kinds"])
    kind_weights = dict(spec["kind_weights"])
    metadata_weights = dict(spec["metadata_weights"])
    last_kind_frame: dict[str, int] = {}

    for item in annotated:
        kind = str(item.get("kind"))
        if kind in kinds:
            frame = int(item.get("frame", 0))
            evidence.append({"frame": item.get("frame"), "kind": kind})
            previous_frame = last_kind_frame.get(kind)
            if previous_frame is None or frame > previous_frame + 1:
                score += int(kind_weights.get(kind, 1))
            last_kind_frame[kind] = frame
            continue
        if kind != "metadata":
            continue
        matching = _metadata_flags(item) & set(metadata_weights)
        if not matching:
            continue
        evidence.append(
            {
                "frame": item.get("frame"),
                "kind": "metadata",
                "flags": sorted(matching),
            }
        )
        score += max(int(metadata_weights[flag]) for flag in matching)
    return evidence, score


def _strength(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "moderate"
    return "low"


def root_cause_hypotheses(
    annotated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for spec in HYPOTHESIS_SPECS:
        evidence, score = _evidence_for_spec(annotated, spec)
        if not score:
            continue
        hypotheses.append(
            {
                "rank": 0,
                "hypothesis": spec["name"],
                "heuristic_score": score,
                "strength": _strength(score),
                "evidence": evidence[:12],
                "causal_proof": False,
            }
        )
    hypotheses.sort(
        key=lambda item: (-int(item["heuristic_score"]), str(item["hypothesis"]))
    )
    for rank, item in enumerate(hypotheses, 1):
        item["rank"] = rank
    return hypotheses


def _ordered_frames(
    annotated: list[dict[str, Any]], kinds: list[str], max_span: int = 200
) -> list[int] | None:
    position = -1
    frames: list[int] = []
    for kind in kinds:
        match = None
        for index in range(position + 1, len(annotated)):
            if annotated[index].get("kind") == kind:
                match = index
                break
        if match is None:
            return None
        position = match
        frames.append(int(annotated[match]["frame"]))
    if frames[-1] - frames[0] > max_span:
        return None
    return frames


def candidate_chains(annotated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    patterns = [
        (
            "delay-instability-to-aec-loss",
            ["delay_jump", "reference_sample_slip", "aec_convergence_lost"],
        ),
        (
            "render-underrun-to-aec-loss",
            ["render_underrun", "aec_reset", "aec_convergence_lost"],
        ),
        ("delay-jump-to-aec-loss", ["delay_jump", "aec_convergence_lost"]),
    ]
    chains = []
    for name, kinds in patterns:
        frames = _ordered_frames(annotated, kinds)
        if frames is None:
            continue
        chains.append(
            {
                "name": name,
                "events": [
                    {"kind": kind, "frame": frame}
                    for kind, frame in zip(kinds, frames)
                ],
                "relation": "temporal-association-only",
                "causal_proof": False,
            }
        )
    return chains


def anomaly_counts(annotated: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get("kind")) for item in annotated).items()))


def build_diagnosis(analysis: dict[str, Any]) -> dict[str, Any]:
    annotated = annotate_anomalies(list(analysis.get("anomalies") or []))
    hypotheses = root_cause_hypotheses(annotated)
    trigger = recording_trigger_context(analysis.get("_recording_trigger_event"))
    return {
        "schema_version": 1,
        "authority": "repository-internal-heuristic-diagnostic-only",
        "causal_proof": False,
        "recording_trigger": trigger,
        "first_fault": first_fault(annotated),
        "intervals": build_intervals(annotated),
        "anomaly_counts": anomaly_counts(annotated),
        "root_cause_hypotheses": hypotheses,
        "candidate_chains": candidate_chains(annotated),
        "top_hypothesis": hypotheses[0] if hypotheses else None,
        "notes": [
            "recording_trigger explains why the dump was frozen; it is not a first-fault or causal claim",
            "recording_trigger does not contribute to intervals or hypothesis scores",
            "same-frame metadata is ordered before downstream counter anomalies without asserting causality",
            "contiguous repeated non-metadata anomalies contribute one heuristic episode score while retaining raw evidence",
            "hypothesis scores are heuristic evidence ranks, not probabilities",
            "metadata-domain weights prevent accidental tie-breaking across fault families",
            "candidate chains encode temporal association only and do not prove causality",
            "diagnosis is not Product Qualification, HIL, certification, or shipping authority",
        ],
    }


def _numeric(summary: dict[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _geometry(summary: dict[str, Any]) -> dict[str, float | int | None]:
    return {
        "frames": summary.get("frames") if isinstance(summary.get("frames"), int) else None,
        "metrics_frames": summary.get("metrics_frames")
        if isinstance(summary.get("metrics_frames"), int)
        else None,
        "duration_ms": summary.get("duration_ms")
        if isinstance(summary.get("duration_ms"), (int, float))
        else None,
    }


def _normalized_value(
    summary: dict[str, Any], numerator: str, denominator: str, scale: float
) -> float | None:
    numerator_value = _numeric(summary, numerator)
    denominator_value = _numeric(summary, denominator)
    if numerator_value is None or denominator_value is None or denominator_value <= 0:
        return None
    return numerator_value / denominator_value * scale


def _normalized_comparison(
    ref_summary: dict[str, Any], cand_summary: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, (numerator, denominator, scale, unit) in NORMALIZED_METRICS.items():
        reference = _normalized_value(ref_summary, numerator, denominator, scale)
        candidate = _normalized_value(cand_summary, numerator, denominator, scale)
        if reference is None or candidate is None:
            continue
        result[name] = {
            "reference": reference,
            "candidate": candidate,
            "delta": candidate - reference,
            "unit": unit,
            "numerator": numerator,
            "denominator": denominator,
        }
    return result


def _raw_count_comparability(
    ref_summary: dict[str, Any], cand_summary: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric, denominator in RAW_COUNT_DENOMINATORS.items():
        reference_denominator = _numeric(ref_summary, denominator)
        candidate_denominator = _numeric(cand_summary, denominator)
        result[metric] = {
            "denominator": denominator,
            "reference_denominator": reference_denominator,
            "candidate_denominator": candidate_denominator,
            "directly_comparable": (
                reference_denominator is not None
                and candidate_denominator is not None
                and reference_denominator > 0
                and reference_denominator == candidate_denominator
            ),
        }
    return result


def compare_diagnoses(
    reference_analysis: dict[str, Any], candidate_analysis: dict[str, Any]
) -> dict[str, Any]:
    reference = build_diagnosis(reference_analysis)
    candidate = build_diagnosis(candidate_analysis)
    ref_counts = Counter(reference["anomaly_counts"])
    cand_counts = Counter(candidate["anomaly_counts"])
    all_kinds = sorted(set(ref_counts) | set(cand_counts))
    count_delta = {
        kind: int(cand_counts[kind] - ref_counts[kind]) for kind in all_kinds
    }

    summary_keys = (
        "anomaly_count",
        "quality_transitions",
        "vad_transitions",
        "far_end_active_frames",
        "double_talk_active_frames",
        "aec_converged_frames",
        "max_abs_delay_error_samples",
        "max_abs_estimated_drift_ppm",
    )
    ref_summary = reference_analysis.get("summary") or {}
    cand_summary = candidate_analysis.get("summary") or {}
    summary_delta = {}
    for key in summary_keys:
        ref_value = ref_summary.get(key)
        cand_value = cand_summary.get(key)
        if isinstance(ref_value, (int, float)) and isinstance(cand_value, (int, float)):
            summary_delta[key] = cand_value - ref_value

    ref_geometry = _geometry(ref_summary)
    cand_geometry = _geometry(cand_summary)
    frames_equal = (
        ref_geometry["frames"] is not None
        and ref_geometry["frames"] == cand_geometry["frames"]
    )
    metrics_frames_equal = (
        ref_geometry["metrics_frames"] is not None
        and ref_geometry["metrics_frames"] == cand_geometry["metrics_frames"]
    )
    warnings = []
    if not frames_equal:
        warnings.append(
            "capture frame counts differ; interpret raw frame-exposure count deltas through normalized rates"
        )
    if not metrics_frames_equal:
        warnings.append(
            "decoded metrics frame counts differ; interpret raw metrics-frame count deltas through normalized ratios/rates"
        )
    if (
        ref_geometry["duration_ms"] is not None
        and cand_geometry["duration_ms"] is not None
        and ref_geometry["duration_ms"] != cand_geometry["duration_ms"]
    ):
        warnings.append(
            "capture durations differ; extrema such as max delay error/drift are duration-sensitive and are not normalized"
        )

    return {
        "schema_version": 1,
        "authority": "repository-internal-heuristic-diagnostic-only",
        "anomaly_count_delta_by_kind": count_delta,
        "new_anomaly_kinds": [
            kind for kind in all_kinds if ref_counts[kind] == 0 and cand_counts[kind] > 0
        ],
        "resolved_anomaly_kinds": [
            kind for kind in all_kinds if ref_counts[kind] > 0 and cand_counts[kind] == 0
        ],
        "summary_delta": summary_delta,
        "comparison_geometry": {
            "reference": ref_geometry,
            "candidate": cand_geometry,
            "frames_equal": frames_equal,
            "metrics_frames_equal": metrics_frames_equal,
        },
        "raw_count_comparability": _raw_count_comparability(ref_summary, cand_summary),
        "normalized_metrics": _normalized_comparison(ref_summary, cand_summary),
        "warnings": warnings,
        "reference_top_hypothesis": reference["top_hypothesis"],
        "candidate_top_hypothesis": candidate["top_hypothesis"],
        "causal_proof": False,
    }


def write_markdown(
    path: Path,
    diagnosis: dict[str, Any],
    comparison: dict[str, Any] | None = None,
) -> None:
    trigger = diagnosis.get("recording_trigger")
    first = diagnosis.get("first_fault")
    top = diagnosis.get("top_hypothesis")
    lines = [
        "# Diagnostic reasoning",
        "",
        "This report is repository-internal heuristic evidence, not causal proof or product qualification authority.",
        "",
        f"- recording trigger: `{trigger.get('name') if trigger else 'none'}`"
        + (f" (`{trigger.get('event')}`)" if trigger else ""),
        f"- first fault: `{first.get('kind') if first else 'none'}`"
        + (f" at frame `{first.get('frame')}`" if first else ""),
        f"- top hypothesis: `{top.get('hypothesis') if top else 'none'}`",
        f"- hypothesis strength: `{top.get('strength') if top else 'n/a'}`",
        f"- anomaly intervals: `{len(diagnosis.get('intervals') or [])}`",
    ]
    hypotheses = diagnosis.get("root_cause_hypotheses") or []
    if hypotheses:
        lines.extend(["", "## Ranked hypotheses", ""])
        for item in hypotheses:
            lines.append(
                f"- #{item['rank']} `{item['hypothesis']}` — strength `{item['strength']}`, "
                f"heuristic score `{item['heuristic_score']}`"
            )
    chains = diagnosis.get("candidate_chains") or []
    if chains:
        lines.extend(["", "## Temporal candidate chains", ""])
        for chain in chains:
            rendered = " → ".join(
                f"{event['kind']}@{event['frame']}" for event in chain["events"]
            )
            lines.append(f"- `{chain['name']}`: {rendered} (temporal association only)")
    if comparison:
        lines.extend(["", "## Reference comparison", ""])
        lines.append(f"- new anomaly kinds: `{comparison['new_anomaly_kinds']}`")
        lines.append(f"- resolved anomaly kinds: `{comparison['resolved_anomaly_kinds']}`")
        lines.append(f"- raw summary deltas: `{comparison['summary_delta']}`")
        geometry = comparison["comparison_geometry"]
        lines.append(
            f"- equal exposure: frames=`{geometry['frames_equal']}`, "
            f"metrics_frames=`{geometry['metrics_frames_equal']}`"
        )
        normalized = comparison.get("normalized_metrics") or {}
        if normalized:
            lines.append("- normalized metrics:")
            for name, item in normalized.items():
                lines.append(
                    f"  - `{name}`: reference `{item['reference']:.6g}`, "
                    f"candidate `{item['candidate']:.6g}`, delta `{item['delta']:.6g}` "
                    f"({item['unit']})"
                )
        for warning in comparison.get("warnings") or []:
            lines.append(f"- warning: {warning}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_triage(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected triage JSON object")
    if payload.get("authority") != "repository-internal-diagnostic-only":
        raise ValueError(f"{path}: expected repository-internal triage authority")
    analysis = payload.get("analysis")
    header = payload.get("header")
    if not isinstance(analysis, dict) or not isinstance(header, dict):
        raise ValueError(f"{path}: expected aptriage triage.json with header and analysis")
    if "summary" not in analysis or "anomalies" not in analysis:
        raise ValueError(f"{path}: triage analysis is incomplete")
    result = dict(analysis)
    event = header.get("trigger_event")
    if isinstance(event, int) and not isinstance(event, bool):
        result["_recording_trigger_event"] = event
    return result


def _metadata_self_test() -> None:
    cases = (
        ("capture_discontinuity", "capture-io", "capture-io"),
        ("render_discontinuity", "sync-reference", "sync-reference-path"),
        ("clock_reset", "sync-reference", "sync-reference-path"),
        ("xrun", "runtime-continuity", "runtime-continuity"),
        ("codec_reopen", "capture-io", "capture-io"),
    )
    for flag, family, hypothesis in cases:
        diagnosis = build_diagnosis(
            {"summary": {}, "anomalies": [{"frame": 0, "kind": "metadata", "flags": [flag]}]}
        )
        assert diagnosis["first_fault"]["family"] == family, flag
        assert diagnosis["top_hypothesis"]["hypothesis"] == hypothesis, flag
        assert diagnosis["top_hypothesis"]["causal_proof"] is False, flag


def _multi_event_self_test() -> None:
    capture = build_diagnosis(
        {
            "summary": {},
            "anomalies": [
                {"frame": 2, "kind": "metadata", "flags": ["capture_discontinuity"]},
                {"frame": 2, "kind": "render_underrun"},
                {"frame": 2, "kind": "aec_reset"},
                {"frame": 3, "kind": "render_underrun"},
                {"frame": 4, "kind": "render_underrun"},
            ],
        }
    )
    assert capture["first_fault"]["kind"] == "metadata"
    assert capture["first_fault"]["family"] == "capture-io"
    assert capture["top_hypothesis"]["hypothesis"] == "capture-io"
    assert capture["top_hypothesis"]["heuristic_score"] == 4

    separated = build_diagnosis(
        {
            "summary": {},
            "anomalies": [
                {"frame": 2, "kind": "render_underrun"},
                {"frame": 3, "kind": "render_underrun"},
                {"frame": 4, "kind": "render_underrun"},
                {"frame": 10, "kind": "render_underrun"},
            ],
        }
    )
    assert separated["top_hypothesis"]["hypothesis"] == "runtime-continuity"
    assert separated["top_hypothesis"]["heuristic_score"] == 4


def _trigger_context_self_test() -> None:
    trigger = recording_trigger_context(23)
    assert trigger is not None
    assert trigger["name"] == "stream_discontinuity"
    assert trigger["relation"] == "recording-trigger-context-only"
    assert trigger["causal_proof"] is False
    assert recording_trigger_context(0) is None
    assert recording_trigger_context(None) is None


def self_test() -> None:
    candidate = {
        "summary": {
            "frames": 200,
            "duration_ms": 2000,
            "metrics_frames": 100,
            "anomaly_count": 4,
            "quality_transitions": 0,
            "vad_transitions": 0,
            "far_end_active_frames": 100,
            "double_talk_active_frames": 0,
            "aec_converged_frames": 40,
            "max_abs_delay_error_samples": 320,
            "max_abs_estimated_drift_ppm": 8.0,
        },
        "anomalies": [
            {"frame": 100, "kind": "delay_jump", "delta": 1},
            {"frame": 104, "kind": "reference_sample_slip", "delta": 1},
            {"frame": 110, "kind": "aec_convergence_lost"},
            {"frame": 120, "kind": "trigger_event", "event": 3},
        ],
    }
    reference = {
        "summary": {
            "frames": 400,
            "duration_ms": 4000,
            "metrics_frames": 200,
            "anomaly_count": 0,
            "quality_transitions": 0,
            "vad_transitions": 0,
            "far_end_active_frames": 200,
            "double_talk_active_frames": 0,
            "aec_converged_frames": 80,
            "max_abs_delay_error_samples": 4,
            "max_abs_estimated_drift_ppm": 1.0,
        },
        "anomalies": [],
    }
    diagnosis = build_diagnosis(candidate)
    assert diagnosis["recording_trigger"] is None
    assert diagnosis["first_fault"]["kind"] == "delay_jump"
    assert diagnosis["top_hypothesis"]["hypothesis"] == "sync-reference-path"
    assert diagnosis["candidate_chains"][0]["name"] == "delay-instability-to-aec-loss"
    assert diagnosis["causal_proof"] is False
    comparison = compare_diagnoses(reference, candidate)
    assert "delay_jump" in comparison["new_anomaly_kinds"]
    assert comparison["summary_delta"]["aec_converged_frames"] == -40
    assert comparison["comparison_geometry"]["metrics_frames_equal"] is False
    assert comparison["raw_count_comparability"]["aec_converged_frames"]["directly_comparable"] is False
    assert abs(comparison["normalized_metrics"]["aec_converged_ratio"]["delta"]) < 1e-12
    assert abs(comparison["normalized_metrics"]["far_end_active_ratio"]["delta"]) < 1e-12
    assert comparison["warnings"]
    _metadata_self_test()
    _multi_event_self_test()
    _trigger_context_self_test()
    print("repository diagnostic reasoning self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path, help="aptriage triage.json")
    parser.add_argument("--reference", type=Path, help="reference aptriage triage.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.input or not args.output_dir:
        parser.error("input triage.json and --output-dir are required")

    try:
        analysis = load_triage(args.input)
        diagnosis = build_diagnosis(analysis)
        comparison = None
        if args.reference:
            comparison = compare_diagnoses(load_triage(args.reference), analysis)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"apdiagnose: {exc}", file=__import__("sys").stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "diagnosis.json").write_text(
        json.dumps(diagnosis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if comparison is not None:
        (args.output_dir / "comparison.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    write_markdown(args.output_dir / "diagnosis.md", diagnosis, comparison)
    print(
        json.dumps(
            {
                "status": "PASS",
                "recording_trigger": diagnosis["recording_trigger"],
                "first_fault": diagnosis["first_fault"],
                "top_hypothesis": diagnosis["top_hypothesis"],
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
