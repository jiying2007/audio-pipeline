#!/usr/bin/env python3
"""Repository-internal reasoning over aptriage JSON evidence.

This module is deliberately diagnostic-only. It ranks evidence-backed hypotheses and
reports temporal associations; it does not claim causal proof, alter APD v1, change
shipping DSP, or participate in product qualification gates.
"""

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

# Count metrics need equal exposure to make raw deltas directly comparable.
RAW_COUNT_DENOMINATORS = {
    "anomaly_count": "frames",
    "quality_transitions": "metrics_frames",
    "vad_transitions": "metrics_frames",
    "far_end_active_frames": "metrics_frames",
    "double_talk_active_frames": "metrics_frames",
    "aec_converged_frames": "metrics_frames",
}

# Normalized metrics are additive diagnostic views. They do not alter any gate.
NORMALIZED_METRICS = {
    "anomaly_rate_per_1000_frames": ("anomaly_count", "frames", 1000.0, "events/1000_frames"),
    "quality_transition_rate_per_1000_metrics_frames": (
        "quality_transitions", "metrics_frames", 1000.0, "transitions/1000_metrics_frames"
    ),
    "vad_transition_rate_per_1000_metrics_frames": (
        "vad_transitions", "metrics_frames", 1000.0, "transitions/1000_metrics_frames"
    ),
    "far_end_active_ratio": ("far_end_active_frames", "metrics_frames", 1.0, "ratio"),
    "double_talk_active_ratio": ("double_talk_active_frames", "metrics_frames", 1.0, "ratio"),
    "aec_converged_ratio": ("aec_converged_frames", "metrics_frames", 1.0, "ratio"),
}


def _metadata_flags(item: dict[str, Any]) -> set[str]:
    flags = item.get("flags") or []
    return {str(flag) for flag in flags}


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
        key=lambda item: (int(item.get("frame", 0)), str(item.get("kind", ""))),
    )


def build_intervals(
    annotated: list[dict[str, Any]], gap_frames: int = 10
) -> list[dict[str, Any]]:
    """Cluster temporally adjacent non-trigger anomalies without asserting causality."""
    events = [item for item in annotated if item.get("kind") != "trigger_event"]
    if not events:
        return []
    intervals: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = [events[0]]
    for item in events[1:]:
        if int(item["frame"]) - int(current[-1]["frame"]) <= gap_frames:
            current.append(item)
        else:
            intervals.append(_interval(current))
            current = [item]
    intervals.append(_interval(current))
    return intervals


def _interval(events: list[dict[str, Any]]) -> dict[str, Any]:
    max_severity = max(
        events, key=lambda item: SEVERITY_ORDER[item["severity"]]
    )["severity"]
    return {
        "start_frame": int(events[0]["frame"]),
        "end_frame": int(events[-1]["frame"]),
        "event_count": len(events),
        "kinds": sorted({str(item["kind"]) for item in events}),
        "families": sorted({str(item["family"]) for item in events}),
        "max_severity": max_severity,
    }


def first_fault(annotated: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in annotated:
        if item.get("kind") != "trigger_event":
            return item
    return None


def _evidence(
    annotated: list[dict[str, Any]],
    kinds: set[str],
    metadata_flags: set[str] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for item in annotated:
        if item.get("kind") in kinds:
            result.append({"frame": item.get("frame"), "kind": item.get("kind")})
            continue
        if (
            item.get("kind") == "metadata"
            and metadata_flags
            and (_metadata_flags(item) & metadata_flags)
        ):
            result.append(
                {
                    "frame": item.get("frame"),
                    "kind": "metadata",
                    "flags": sorted(_metadata_flags(item) & metadata_flags),
                }
            )
    return result


def _strength(score: int) -> str:
    if score >= 6:
        return "high"
    if score >= 3:
        return "moderate"
    return "low"


def root_cause_hypotheses(
    annotated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank diagnostic hypotheses from explicit events only.

    Scores are intentionally heuristic and diagnostic-only. They are not probabilities.
    """
    specs = [
        (
            "sync-reference-path",
            {"delay_jump", "reference_sample_slip", "render_underrun"},
            {"render_discontinuity", "clock_reset", "xrun"},
            {"delay_jump": 3, "reference_sample_slip": 3, "render_underrun": 2},
        ),
        (
            "aec-adaptation",
            {"aec_reset", "aec_convergence_lost", "delay_jump"},
            {"render_discontinuity", "clock_reset"},
            {"aec_reset": 3, "aec_convergence_lost": 2, "delay_jump": 1},
        ),
        (
            "capture-io",
            set(),
            {"capture_discontinuity", "codec_reopen", "xrun"},
            {},
        ),
        (
            "runtime-continuity",
            {"render_underrun"},
            {"xrun", "codec_reopen"},
            {"render_underrun": 2},
        ),
    ]
    hypotheses: list[dict[str, Any]] = []
    for name, kinds, metadata_flags, weights in specs:
        evidence = _evidence(annotated, kinds, metadata_flags)
        score = 0
        for item in evidence:
            if item["kind"] == "metadata":
                flags = set(item.get("flags", []))
                score += 3 if "clock_reset" in flags or "codec_reopen" in flags else 2
            else:
                score += weights.get(str(item["kind"]), 1)
        if score:
            hypotheses.append(
                {
                    "rank": 0,
                    "hypothesis": name,
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
        if frames is not None:
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
    return dict(
        sorted(Counter(str(item.get("kind")) for item in annotated).items())
    )


def build_diagnosis(analysis: dict[str, Any]) -> dict[str, Any]:
    annotated = annotate_anomalies(list(analysis.get("anomalies") or []))
    hypotheses = root_cause_hypotheses(annotated)
    first = first_fault(annotated)
    return {
        "schema_version": 1,
        "authority": "repository-internal-heuristic-diagnostic-only",
        "causal_proof": False,
        "first_fault": first,
        "intervals": build_intervals(annotated),
        "anomaly_counts": anomaly_counts(annotated),
        "root_cause_hypotheses": hypotheses,
        "candidate_chains": candidate_chains(annotated),
        "top_hypothesis": hypotheses[0] if hypotheses else None,
        "notes": [
            "hypothesis scores are heuristic evidence ranks, not probabilities",
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
        "metrics_frames": (
            summary.get("metrics_frames")
            if isinstance(summary.get("metrics_frames"), int)
            else None
        ),
        "duration_ms": (
            summary.get("duration_ms")
            if isinstance(summary.get("duration_ms"), (int, float))
            else None
        ),
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
        directly_comparable = (
            reference_denominator is not None
            and candidate_denominator is not None
            and reference_denominator > 0
            and reference_denominator == candidate_denominator
        )
        result[metric] = {
            "denominator": denominator,
            "reference_denominator": reference_denominator,
            "candidate_denominator": candidate_denominator,
            "directly_comparable": directly_comparable,
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
        if key in ref_summary and key in cand_summary:
            ref_value = ref_summary[key]
            cand_value = cand_summary[key]
            if isinstance(ref_value, (int, float)) and isinstance(
                cand_value, (int, float)
            ):
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
        # Retained for compatibility. Count deltas require the comparability map below.
        "summary_delta": summary_delta,
        "comparison_geometry": {
            "reference": ref_geometry,
            "candidate": cand_geometry,
            "frames_equal": frames_equal,
            "metrics_frames_equal": metrics_frames_equal,
        },
        "raw_count_comparability": _raw_count_comparability(
            ref_summary, cand_summary
        ),
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
    first = diagnosis.get("first_fault")
    top = diagnosis.get("top_hypothesis")
    lines = [
        "# Diagnostic reasoning",
        "",
        "This report is repository-internal heuristic evidence, not causal proof or product qualification authority.",
        "",
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
            lines.append(
                f"- `{chain['name']}`: {rendered} (temporal association only)"
            )
    if comparison:
        lines.extend(["", "## Reference comparison", ""])
        lines.append(
            f"- new anomaly kinds: `{comparison['new_anomaly_kinds']}`"
        )
        lines.append(
            f"- resolved anomaly kinds: `{comparison['resolved_anomaly_kinds']}`"
        )
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


def load_analysis(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "analysis" in payload:
        payload = payload["analysis"]
    if (
        not isinstance(payload, dict)
        or "summary" not in payload
        or "anomalies" not in payload
    ):
        raise ValueError(f"{path}: expected aptriage triage.json or analysis.json")
    return payload


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
    assert diagnosis["first_fault"]["kind"] == "delay_jump"
    assert diagnosis["top_hypothesis"]["hypothesis"] == "sync-reference-path"
    assert diagnosis["candidate_chains"][0]["name"] == "delay-instability-to-aec-loss"
    assert diagnosis["causal_proof"] is False
    comparison = compare_diagnoses(reference, candidate)
    assert "delay_jump" in comparison["new_anomaly_kinds"]
    assert comparison["summary_delta"]["aec_converged_frames"] == -40
    assert comparison["comparison_geometry"]["metrics_frames_equal"] is False
    assert (
        comparison["raw_count_comparability"]["aec_converged_frames"][
            "directly_comparable"
        ]
        is False
    )
    assert abs(comparison["normalized_metrics"]["aec_converged_ratio"]["delta"]) < 1e-12
    assert comparison["warnings"]
    print("repository diagnostic reasoning self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input", nargs="?", type=Path, help="aptriage triage.json or analysis.json"
    )
    parser.add_argument(
        "--reference", type=Path, help="reference triage.json or analysis.json"
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.input or not args.output_dir:
        parser.error("input and --output-dir are required")

    try:
        analysis = load_analysis(args.input)
        diagnosis = build_diagnosis(analysis)
        comparison = None
        if args.reference:
            comparison = compare_diagnoses(load_analysis(args.reference), analysis)
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
