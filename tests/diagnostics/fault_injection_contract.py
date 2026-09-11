#!/usr/bin/env python3
"""End-to-end runtime fault -> APD -> triage -> diagnosis -> bundle contract.

This stays repository-internal. It validates diagnostic behavior using real runtime
metadata faults and the production Flight Recorder path without changing APD v1,
shipping DSP, public APIs, or product qualification authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


CASES = {
    "capture-gap": {
        "flag": "capture_discontinuity",
        "family": "capture-io",
        "hypothesis": "capture-io",
    },
    "render-gap": {
        "flag": "render_discontinuity",
        "family": "sync-reference",
        "hypothesis": "sync-reference-path",
    },
    "clock-reset": {
        "flag": "clock_reset",
        "family": "sync-reference",
        "hypothesis": "sync-reference-path",
    },
    "xrun": {
        "flag": "xrun",
        "family": "runtime-continuity",
        "hypothesis": "runtime-continuity",
    },
    "codec-reopen": {
        "flag": "codec_reopen",
        "family": "capture-io",
        "hypothesis": "capture-io",
    },
}
EXPECTED_SEQUENCES = [40, 41, 42, 43, 44]
EXPECTED_FAULT_FRAME = 2


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def hypothesis_by_name(diagnosis: dict, name: str) -> dict:
    for item in diagnosis.get("root_cause_hypotheses") or []:
        if item.get("hypothesis") == name:
            return item
    return {}


def has_metadata_evidence(hypothesis: dict, flag: str, frame: int) -> bool:
    for item in hypothesis.get("evidence") or []:
        if item.get("kind") != "metadata" or int(item.get("frame", -1)) != frame:
            continue
        if flag in set(item.get("flags") or []):
            return True
    return False


def validate_case(
    case: str,
    expected: dict,
    triage: dict,
    diagnosis: dict,
    metric_rows: list[dict],
    require_build_identity: bool,
) -> dict:
    trigger = diagnosis.get("recording_trigger") or {}
    first = diagnosis.get("first_fault") or {}
    top = diagnosis.get("top_hypothesis") or {}
    expected_hypothesis = hypothesis_by_name(diagnosis, expected["hypothesis"])
    header = triage.get("header") or {}
    header_trigger = int(header.get("trigger_event") or 0)
    analysis = triage["analysis"]
    analysis_summary = analysis["summary"]
    metadata_anomalies = [
        item for item in analysis["anomalies"] if item.get("kind") == "metadata"
    ]
    sequences = [int(row["sequence"]) for row in metric_rows]
    first_fault_frame = int(first.get("frame", -1))
    metadata_fault = metadata_anomalies[0] if len(metadata_anomalies) == 1 else {}
    metadata_fault_frame = int(metadata_fault.get("frame", -1))
    metadata_flags = set(metadata_fault.get("flags") or [])
    first_flags = set(first.get("flags") or [])
    frames_before = metadata_fault_frame
    frames_after = int(analysis_summary["frames"]) - metadata_fault_frame - 1

    assert triage["status"] == "PASS", case
    assert triage["authority"] == "repository-internal-diagnostic-only", case
    assert int(header.get("frame_count") or 0) == 5, (case, header)
    assert int(analysis_summary["frames"]) == 5, (case, analysis_summary)
    assert int(analysis_summary["metrics_frames"]) == 5, (case, analysis_summary)
    assert len(metric_rows) == 5, (case, len(metric_rows))
    assert sequences == EXPECTED_SEQUENCES, (case, sequences)

    assert header_trigger == 23, (case, header_trigger)
    assert trigger.get("event") == header_trigger, (case, trigger)
    assert trigger.get("name") == "stream_discontinuity", (case, trigger)
    assert trigger.get("source") == "apd-header", (case, trigger)
    assert trigger.get("relation") == "recording-trigger-context-only", (case, trigger)
    assert trigger.get("causal_proof") is False, case

    assert first_fault_frame == EXPECTED_FAULT_FRAME, (case, first)
    assert first.get("kind") == "metadata", (case, first)
    assert first.get("family") == expected["family"], (case, first)
    assert expected["flag"] in first_flags, (case, first_flags)
    assert metadata_fault_frame == EXPECTED_FAULT_FRAME, (case, metadata_anomalies)
    assert expected["flag"] in metadata_flags, (case, metadata_flags)
    assert frames_before == 2 and frames_after == 2, (
        case,
        frames_before,
        frames_after,
    )

    assert expected_hypothesis, (case, diagnosis.get("root_cause_hypotheses"))
    assert expected_hypothesis.get("rank") == 1, (case, expected_hypothesis)
    assert expected_hypothesis.get("causal_proof") is False, case
    assert has_metadata_evidence(
        expected_hypothesis, expected["flag"], EXPECTED_FAULT_FRAME
    ), (case, expected_hypothesis)
    assert top.get("hypothesis") == expected["hypothesis"], (case, top)
    assert top.get("causal_proof") is False, case
    assert diagnosis["causal_proof"] is False, case

    replay = triage.get("replay") or {}
    comparison = replay.get("comparison") if isinstance(replay, dict) else None
    assert isinstance(comparison, dict), (case, replay)
    assert isinstance(comparison.get("bit_exact"), bool), (case, comparison)

    replay_authority = triage.get("replay_authority") or {}
    assert (
        replay_authority.get("authority")
        == "repository-internal-replay-interpretation-only"
    ), (case, replay_authority)
    assert replay_authority.get("mode") == "pcm-only", (case, replay_authority)
    assert replay_authority.get("state_replay") is False, (case, replay_authority)
    assert replay_authority.get("runtime_metadata_state_present") is True, (
        case,
        replay_authority,
    )
    assert set(replay_authority.get("runtime_metadata_flags") or []) == {
        expected["flag"]
    }, (case, replay_authority)
    assert replay_authority.get("comparison_present") is True, (
        case,
        replay_authority,
    )
    assert replay_authority.get("bit_exact") == comparison.get("bit_exact"), (
        case,
        replay_authority,
        comparison,
    )
    assert (
        replay_authority.get("classification")
        == "stateful-runtime-context-not-replayed"
    ), (case, replay_authority)
    assert (
        replay_authority.get("whole_incident_equivalence_authoritative") is False
    ), (case, replay_authority)
    assert "not re-injected" in str(replay_authority.get("bit_exact_claim_scope")), (
        case,
        replay_authority,
    )

    build_identity = triage.get("build_identity") or {}
    if require_build_identity:
        assert (
            build_identity.get("authority")
            == "repository-internal-build-identity-subset-only"
        ), (case, build_identity)
        assert build_identity.get("status") == "MATCH", (case, build_identity)
        assert build_identity.get("shared_fields_match") is True, (
            case,
            build_identity,
        )
        assert build_identity.get("mismatches") == [], (case, build_identity)
        assert build_identity.get("require_match") is True, (case, build_identity)
        assert (
            build_identity.get("exact_source_config_match_authoritative") is False
        ), (case, build_identity)

    return {
        "case": case,
        "metadata_flag": expected["flag"],
        "recording_trigger": {
            "event": trigger.get("event"),
            "name": trigger.get("name"),
            "relation": trigger.get("relation"),
        },
        "incident_window": {
            "recorded_frames": 5,
            "sequences": sequences,
            "metadata_fault_frame": metadata_fault_frame,
            "fault_sequence": sequences[metadata_fault_frame],
            "frames_before_metadata_fault": frames_before,
            "frames_after_metadata_fault": frames_after,
            "balanced_pre_post_context": frames_before == frames_after == 2,
        },
        "temporal_first_fault": {
            "frame": first.get("frame"),
            "kind": first.get("kind"),
            "family": first.get("family"),
        },
        "expected_fault_domain_hypothesis": {
            "hypothesis": expected_hypothesis.get("hypothesis"),
            "rank": expected_hypothesis.get("rank"),
            "heuristic_score": expected_hypothesis.get("heuristic_score"),
        },
        "top_hypothesis": top.get("hypothesis"),
        "top_heuristic_score": top.get("heuristic_score"),
        "replay_bit_exact": comparison.get("bit_exact"),
        "replay_mae_lsb": comparison.get("mae_lsb"),
        "replay_max_abs_lsb": comparison.get("max_abs_lsb"),
        "replay_authority": {
            "mode": replay_authority.get("mode"),
            "state_replay": replay_authority.get("state_replay"),
            "runtime_metadata_state_present": replay_authority.get(
                "runtime_metadata_state_present"
            ),
            "runtime_metadata_flags": replay_authority.get("runtime_metadata_flags"),
            "classification": replay_authority.get("classification"),
            "whole_incident_equivalence_authoritative": replay_authority.get(
                "whole_incident_equivalence_authoritative"
            ),
        },
        "build_identity": {
            "status": build_identity.get("status"),
            "shared_fields_match": build_identity.get("shared_fields_match"),
            "exact_source_config_match_authoritative": build_identity.get(
                "exact_source_config_match_authoritative"
            ),
        },
        "causal_proof": False,
    }


def validate_bundle(bundle: dict) -> None:
    assert bundle["schema_version"] == 1
    assert bundle["authority"] == "repository-internal-cross-dump-correlation-only"
    assert bundle["status"] == "PASS"
    assert bundle["incident_count"] == len(CASES)
    assert bundle["causal_proof"] is False
    assert bundle["consistency"]["build_identity_coverage"] == len(CASES)
    assert bundle["consistency"]["replay_authority_coverage"] == len(CASES)
    assert bundle["consistency"]["unique_build_identity_statuses"] == ["MATCH"]
    assert bundle["consistency"]["all_shared_build_identity_match"] is True
    assert bundle["consistency"]["mixed_build_identity_status"] is False
    assert bundle["consistency"]["unique_replay_classifications"] == [
        "stateful-runtime-context-not-replayed"
    ]
    assert bundle["consistency"]["mixed_replay_classification"] is False
    assert bundle["consistency"]["unique_recording_triggers"] == [
        "stream_discontinuity"
    ]
    assert bundle["consistency"]["mixed_recording_trigger"] is False
    assert bundle["consistency"]["all_incidents_noncausal"] is True

    domain_counts = {
        (
            item["signature"]["first_fault_family"],
            item["signature"]["top_hypothesis"],
        ): int(item["count"])
        for item in bundle["domain_clusters"]
    }
    assert domain_counts == {
        ("capture-io", "capture-io"): 2,
        ("sync-reference", "sync-reference-path"): 2,
        ("runtime-continuity", "runtime-continuity"): 1,
    }
    assert len(bundle["repeated_domain_clusters"]) == 2
    assert bundle["repeated_exact_pattern_clusters"] == []
    assert bundle["dominant_domain_cluster"] is None
    assert bundle["dominant_exact_pattern_cluster"] is None
    assert (
        bundle["interpretation"]["same_domain_does_not_prove_same_root_cause"]
        is True
    )
    assert (
        bundle["interpretation"]["same_exact_pattern_does_not_prove_same_root_cause"]
        is True
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--processor", type=Path, required=True)
    parser.add_argument("--processor-build-info", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    triage_tool = root / "tests/diagnostics/aptriage.py"
    diagnose_tool = root / "tests/diagnostics/apdiagnose.py"
    incident_tool = root / "tests/diagnostics/apincident.py"
    args.work_dir.mkdir(parents=True, exist_ok=True)

    run([sys.executable, str(incident_tool), "--self-test"])

    summary = {
        "schema_version": 1,
        "authority": "repository-internal-diagnostic-contract-only",
        "causal_proof": False,
        "cases": [],
    }

    for case, expected in CASES.items():
        case_dir = args.work_dir / case
        triage_dir = case_dir / "triage"
        diagnosis_dir = case_dir / "diagnosis"
        dump = case_dir / "fault.apd"
        case_dir.mkdir(parents=True, exist_ok=True)

        run([str(args.generator), case, str(dump)])
        triage_command = [
            sys.executable,
            str(triage_tool),
            str(dump),
            "--processor",
            str(args.processor),
            "--output-dir",
            str(triage_dir),
        ]
        if args.processor_build_info:
            triage_command.extend(
                [
                    "--processor-build-info",
                    str(args.processor_build_info),
                    "--require-build-identity-match",
                ]
            )
        run(triage_command)
        run(
            [
                sys.executable,
                str(diagnose_tool),
                str(triage_dir / "triage.json"),
                "--output-dir",
                str(diagnosis_dir),
            ]
        )

        triage = load_json(triage_dir / "triage.json")
        diagnosis = load_json(diagnosis_dir / "diagnosis.json")
        metric_rows = load_jsonl(triage_dir / "extracted" / "metrics.jsonl")
        summary["cases"].append(
            validate_case(
                case,
                expected,
                triage,
                diagnosis,
                metric_rows,
                args.processor_build_info is not None,
            )
        )

    assert len(summary["cases"]) == len(CASES)

    bundle_dir = args.work_dir / "incident-bundle"
    bundle_command = [sys.executable, str(incident_tool)]
    for case in CASES:
        case_dir = args.work_dir / case
        bundle_command.extend(
            [
                "--entry",
                case,
                str(case_dir / "triage" / "triage.json"),
                str(case_dir / "diagnosis" / "diagnosis.json"),
            ]
        )
    bundle_command.extend(["--output-dir", str(bundle_dir)])
    run(bundle_command)

    bundle_path = bundle_dir / "incident-bundle.json"
    bundle_markdown = bundle_dir / "incident-bundle.md"
    assert bundle_path.is_file() and bundle_path.stat().st_size > 0
    assert bundle_markdown.is_file() and bundle_markdown.stat().st_size > 0
    bundle = load_json(bundle_path)
    validate_bundle(bundle)

    summary["incident_bundle"] = {
        "authority": bundle["authority"],
        "incident_count": bundle["incident_count"],
        "repeated_domain_cluster_count": len(bundle["repeated_domain_clusters"]),
        "repeated_exact_pattern_cluster_count": len(
            bundle["repeated_exact_pattern_clusters"]
        ),
        "all_shared_build_identity_match": bundle["consistency"][
            "all_shared_build_identity_match"
        ],
        "all_incidents_noncausal": bundle["consistency"]["all_incidents_noncausal"],
        "causal_proof": False,
        "path": str(bundle_path),
    }

    summary_path = args.work_dir / "fault-injection-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "cases": len(CASES),
                "incident_bundle": str(bundle_path),
                "summary": str(summary_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
