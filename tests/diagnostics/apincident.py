#!/usr/bin/env python3
"""Aggregate multiple repository diagnostic incidents without claiming causality."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import tempfile
from typing import Any

AUTHORITY = "repository-internal-cross-dump-correlation-only"
TRIAGE_AUTHORITY = "repository-internal-diagnostic-only"
DIAGNOSIS_AUTHORITY = "repository-internal-heuristic-diagnostic-only"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object")
    return payload


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _sorted_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return sorted({item for item in values if isinstance(item, str) and item})


def load_incident(incident_id: str, triage_path: Path, diagnosis_path: Path) -> dict[str, Any]:
    if not incident_id:
        raise ValueError("incident id must be non-empty")
    triage = load_json(triage_path)
    diagnosis = load_json(diagnosis_path)
    if triage.get("authority") != TRIAGE_AUTHORITY:
        raise ValueError(f"{incident_id}: unexpected triage authority {triage.get('authority')!r}")
    if diagnosis.get("authority") != DIAGNOSIS_AUTHORITY:
        raise ValueError(f"{incident_id}: unexpected diagnosis authority {diagnosis.get('authority')!r}")
    if diagnosis.get("causal_proof") is not False:
        raise ValueError(f"{incident_id}: diagnosis must preserve causal_proof=false")

    header = triage.get("header") or {}
    trigger = diagnosis.get("recording_trigger")
    first_fault = diagnosis.get("first_fault")
    top = diagnosis.get("top_hypothesis")
    replay = triage.get("replay_authority") or {}
    identity = triage.get("build_identity") or {}

    header_trigger = header.get("trigger_event")
    if trigger is not None:
        if not isinstance(trigger, dict):
            raise ValueError(f"{incident_id}: invalid recording_trigger")
        if trigger.get("causal_proof") is not False:
            raise ValueError(f"{incident_id}: recording trigger must remain non-causal context")
        if isinstance(header_trigger, int) and not isinstance(header_trigger, bool) and trigger.get("event") != header_trigger:
            raise ValueError(f"{incident_id}: recording trigger does not match APD header")

    if first_fault is not None and not isinstance(first_fault, dict):
        raise ValueError(f"{incident_id}: invalid first_fault")
    if top is not None:
        if not isinstance(top, dict):
            raise ValueError(f"{incident_id}: invalid top_hypothesis")
        if top.get("causal_proof") is not False:
            raise ValueError(f"{incident_id}: top hypothesis must preserve causal_proof=false")

    if replay:
        if replay.get("authority") != "repository-internal-replay-interpretation-only":
            raise ValueError(f"{incident_id}: unexpected replay authority")
        if replay.get("whole_incident_equivalence_authoritative") is not False:
            raise ValueError(f"{incident_id}: whole-incident replay equivalence must remain false")

    if identity:
        if identity.get("authority") != "repository-internal-build-identity-subset-only":
            raise ValueError(f"{incident_id}: unexpected build identity authority")
        if identity.get("exact_source_config_match_authoritative") is not False:
            raise ValueError(f"{incident_id}: exact source/config identity must remain non-authoritative")

    return {
        "id": incident_id,
        "source": {"triage": str(triage_path), "diagnosis": str(diagnosis_path)},
        "triage_status": _text(triage.get("status")),
        "recording_trigger": (
            {"event": trigger.get("event"), "name": _text(trigger.get("name")), "relation": _text(trigger.get("relation"))}
            if isinstance(trigger, dict)
            else None
        ),
        "first_fault": (
            {"frame": first_fault.get("frame"), "kind": _text(first_fault.get("kind")), "family": _text(first_fault.get("family"))}
            if isinstance(first_fault, dict)
            else None
        ),
        "top_hypothesis": (
            {"hypothesis": _text(top.get("hypothesis")), "heuristic_score": top.get("heuristic_score"), "strength": _text(top.get("strength"))}
            if isinstance(top, dict)
            else None
        ),
        "runtime_metadata_flags": _sorted_strings(replay.get("runtime_metadata_flags")),
        "replay_authority": {
            "classification": _text(replay.get("classification")),
            "state_replay": _bool(replay.get("state_replay")),
            "whole_incident_equivalence_authoritative": _bool(replay.get("whole_incident_equivalence_authoritative")),
        },
        "build_identity": {
            "status": _text(identity.get("status")),
            "shared_fields_match": _bool(identity.get("shared_fields_match")),
            "exact_source_config_match_authoritative": _bool(identity.get("exact_source_config_match_authoritative")),
        },
        "causal_proof": False,
    }


def _domain_signature(incident: dict[str, Any]) -> tuple[str, str]:
    first = incident.get("first_fault") or {}
    top = incident.get("top_hypothesis") or {}
    return (_text(first.get("family")) or "none", _text(top.get("hypothesis")) or "none")


def _exact_signature(incident: dict[str, Any]) -> tuple[str, str, str, tuple[str, ...], str, str]:
    trigger = incident.get("recording_trigger") or {}
    first = incident.get("first_fault") or {}
    top = incident.get("top_hypothesis") or {}
    identity = incident.get("build_identity") or {}
    replay = incident.get("replay_authority") or {}
    return (
        _text(trigger.get("name")) or "none",
        _text(first.get("family")) or "none",
        _text(top.get("hypothesis")) or "none",
        tuple(incident.get("runtime_metadata_flags") or []),
        _text(identity.get("status")) or "unknown",
        _text(replay.get("classification")) or "unknown",
    )


def _domain_clusters(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for incident in incidents:
        grouped[_domain_signature(incident)].append(incident["id"])
    clusters = []
    for (family, hypothesis), incident_ids in grouped.items():
        clusters.append({
            "signature": {"first_fault_family": family, "top_hypothesis": hypothesis},
            "count": len(incident_ids),
            "incident_ids": sorted(incident_ids),
            "correlation_only": True,
            "causal_proof": False,
        })
    return sorted(clusters, key=lambda item: (-int(item["count"]), item["signature"]["first_fault_family"], item["signature"]["top_hypothesis"]))


def _exact_clusters(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, tuple[str, ...], str, str], list[str]] = defaultdict(list)
    for incident in incidents:
        grouped[_exact_signature(incident)].append(incident["id"])
    clusters = []
    for signature, incident_ids in grouped.items():
        trigger, family, hypothesis, flags, identity_status, replay_class = signature
        clusters.append({
            "signature": {
                "recording_trigger": trigger,
                "first_fault_family": family,
                "top_hypothesis": hypothesis,
                "runtime_metadata_flags": list(flags),
                "build_identity_status": identity_status,
                "replay_classification": replay_class,
            },
            "count": len(incident_ids),
            "incident_ids": sorted(incident_ids),
            "correlation_only": True,
            "causal_proof": False,
        })
    return sorted(clusters, key=lambda item: (-int(item["count"]), json.dumps(item["signature"], sort_keys=True)))


def _unique_text(incidents: list[dict[str, Any]], getter) -> list[str]:
    values = []
    for incident in incidents:
        value = getter(incident)
        if isinstance(value, str) and value:
            values.append(value)
    return sorted(set(values))


def _dominant_cluster(clusters: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not clusters:
        return None
    max_count = max(int(item["count"]) for item in clusters)
    winners = [item for item in clusters if int(item["count"]) == max_count]
    if max_count < 2 or len(winners) != 1:
        return None
    return winners[0]


def build_bundle(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    if len(incidents) < 2:
        raise ValueError("incident bundle requires at least two incidents")
    ids = [item["id"] for item in incidents]
    if len(set(ids)) != len(ids):
        raise ValueError("incident ids must be unique")

    domain_clusters = _domain_clusters(incidents)
    exact_clusters = _exact_clusters(incidents)
    repeated_domains = [item for item in domain_clusters if item["count"] >= 2]
    repeated_exact = [item for item in exact_clusters if item["count"] >= 2]

    build_statuses = _unique_text(incidents, lambda item: (item.get("build_identity") or {}).get("status"))
    replay_classes = _unique_text(incidents, lambda item: (item.get("replay_authority") or {}).get("classification"))
    trigger_names = _unique_text(incidents, lambda item: (item.get("recording_trigger") or {}).get("name"))

    build_coverage = sum(1 for item in incidents if _text((item.get("build_identity") or {}).get("status")))
    replay_coverage = sum(1 for item in incidents if _text((item.get("replay_authority") or {}).get("classification")))
    all_shared_build_identity_match = (
        build_coverage == len(incidents)
        and all(
            (item.get("build_identity") or {}).get("status") == "MATCH"
            and (item.get("build_identity") or {}).get("shared_fields_match") is True
            for item in incidents
        )
    )

    return {
        "schema_version": 1,
        "authority": AUTHORITY,
        "status": "PASS",
        "incident_count": len(incidents),
        "incidents": incidents,
        "domain_clusters": domain_clusters,
        "exact_pattern_clusters": exact_clusters,
        "repeated_domain_clusters": repeated_domains,
        "repeated_exact_pattern_clusters": repeated_exact,
        "dominant_domain_cluster": _dominant_cluster(domain_clusters),
        "dominant_exact_pattern_cluster": _dominant_cluster(exact_clusters),
        "consistency": {
            "build_identity_coverage": build_coverage,
            "replay_authority_coverage": replay_coverage,
            "unique_build_identity_statuses": build_statuses,
            "unique_replay_classifications": replay_classes,
            "unique_recording_triggers": trigger_names,
            "all_shared_build_identity_match": all_shared_build_identity_match,
            "mixed_build_identity_status": len(build_statuses) > 1,
            "mixed_replay_classification": len(replay_classes) > 1,
            "mixed_recording_trigger": len(trigger_names) > 1,
            "all_incidents_noncausal": all(item.get("causal_proof") is False for item in incidents),
        },
        "interpretation": {
            "domain_recurrence_scope": "same first-fault family and top heuristic hypothesis only",
            "exact_pattern_scope": "same trigger, fault domain, metadata flags, build-identity status, and replay-authority classification",
            "same_domain_does_not_prove_same_root_cause": True,
            "same_exact_pattern_does_not_prove_same_root_cause": True,
        },
        "causal_proof": False,
    }


def write_markdown(path: Path, bundle: dict[str, Any]) -> None:
    lines = [
        "# Cross-dump incident bundle",
        "",
        "Repository-internal correlation evidence only; this is not causal proof or Product Qualification authority.",
        "",
        f"- incidents: `{bundle['incident_count']}`",
        f"- repeated fault-domain clusters: `{len(bundle['repeated_domain_clusters'])}`",
        f"- repeated exact-pattern clusters: `{len(bundle['repeated_exact_pattern_clusters'])}`",
        f"- shared build identity all match: `{bundle['consistency']['all_shared_build_identity_match']}`",
        "- causal proof: `false`",
        "",
        "## Repeated fault-domain clusters",
        "",
    ]
    repeated = bundle["repeated_domain_clusters"]
    if not repeated:
        lines.append("- none")
    else:
        for cluster in repeated:
            sig = cluster["signature"]
            lines.append(f"- `{sig['first_fault_family']} / {sig['top_hypothesis']}`: {cluster['count']} incidents ({', '.join(cluster['incident_ids'])})")
    lines.extend(["", "## Repeated exact patterns", ""])
    exact = bundle["repeated_exact_pattern_clusters"]
    if not exact:
        lines.append("- none")
    else:
        for cluster in exact:
            sig = cluster["signature"]
            lines.append(f"- `{sig['first_fault_family']} / {sig['top_hypothesis']}` flags=`{sig['runtime_metadata_flags']}`: {cluster['count']} incidents ({', '.join(cluster['incident_ids'])})")
    lines.extend([
        "",
        "## Consistency",
        "",
        f"- build identity statuses: `{bundle['consistency']['unique_build_identity_statuses']}`",
        f"- replay classifications: `{bundle['consistency']['unique_replay_classifications']}`",
        f"- recording triggers: `{bundle['consistency']['unique_recording_triggers']}`",
        "",
        "Equal domains or equal exact patterns are diagnostic correlation only and do not establish a shared physical root cause.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _synthetic_payload(trigger: str, family: str, hypothesis: str, flag: str, *, identity_status: str = "MATCH") -> tuple[dict[str, Any], dict[str, Any]]:
    triage = {
        "authority": TRIAGE_AUTHORITY,
        "status": "PASS",
        "header": {"trigger_event": 23},
        "replay_authority": {
            "authority": "repository-internal-replay-interpretation-only",
            "classification": "stateful-runtime-context-not-replayed",
            "state_replay": False,
            "runtime_metadata_flags": [flag],
            "whole_incident_equivalence_authoritative": False,
        },
        "build_identity": {
            "authority": "repository-internal-build-identity-subset-only",
            "status": identity_status,
            "shared_fields_match": identity_status == "MATCH",
            "exact_source_config_match_authoritative": False,
        },
    }
    diagnosis = {
        "authority": DIAGNOSIS_AUTHORITY,
        "recording_trigger": {
            "event": 23,
            "name": trigger,
            "relation": "recording-trigger-context-only",
            "causal_proof": False,
        },
        "first_fault": {"frame": 2, "kind": "metadata", "family": family},
        "top_hypothesis": {
            "hypothesis": hypothesis,
            "heuristic_score": 4,
            "strength": "strong",
            "causal_proof": False,
        },
        "causal_proof": False,
    }
    return triage, diagnosis


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        specs = [
            ("a", "capture-io", "capture-io", "capture_discontinuity", "MATCH"),
            ("b", "capture-io", "capture-io", "codec_reopen", "MATCH"),
            ("c", "sync-reference", "sync-reference-path", "render_discontinuity", "MATCH"),
            ("d", "capture-io", "capture-io", "capture_discontinuity", "MATCH"),
        ]
        incidents = []
        for incident_id, family, hypothesis, flag, status in specs:
            triage, diagnosis = _synthetic_payload("stream_discontinuity", family, hypothesis, flag, identity_status=status)
            triage_path = root / f"{incident_id}-triage.json"
            diagnosis_path = root / f"{incident_id}-diagnosis.json"
            triage_path.write_text(json.dumps(triage), encoding="utf-8")
            diagnosis_path.write_text(json.dumps(diagnosis), encoding="utf-8")
            incidents.append(load_incident(incident_id, triage_path, diagnosis_path))

        bundle = build_bundle(incidents)
        assert bundle["incident_count"] == 4
        assert bundle["causal_proof"] is False
        assert bundle["consistency"]["all_shared_build_identity_match"] is True
        assert bundle["repeated_domain_clusters"][0]["count"] == 3
        assert bundle["repeated_exact_pattern_clusters"][0]["count"] == 2
        assert bundle["repeated_exact_pattern_clusters"][0]["signature"]["runtime_metadata_flags"] == ["capture_discontinuity"]

        mixed = [dict(item) for item in incidents]
        mixed[-1] = dict(mixed[-1])
        mixed[-1]["build_identity"] = dict(mixed[-1]["build_identity"])
        mixed[-1]["build_identity"]["status"] = "MISMATCH"
        mixed[-1]["build_identity"]["shared_fields_match"] = False
        mixed_bundle = build_bundle(mixed)
        assert mixed_bundle["consistency"]["mixed_build_identity_status"] is True
        assert mixed_bundle["consistency"]["all_shared_build_identity_match"] is False

        try:
            build_bundle([incidents[0], incidents[0]])
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate incident ids must fail closed")
    print("repository incident bundle self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entry", action="append", nargs=3, metavar=("ID", "TRIAGE_JSON", "DIAGNOSIS_JSON"), help="incident id plus matching triage.json and diagnosis.json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.entry or not args.output_dir:
        parser.error("--entry (at least twice) and --output-dir are required")
    try:
        incidents = [load_incident(incident_id, Path(triage), Path(diagnosis)) for incident_id, triage, diagnosis in args.entry]
        bundle = build_bundle(incidents)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"apincident: {exc}", file=__import__("sys").stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "incident-bundle.json"
    md_path = args.output_dir / "incident-bundle.md"
    json_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(md_path, bundle)
    print(json.dumps({
        "status": "PASS",
        "incidents": bundle["incident_count"],
        "repeated_domain_clusters": len(bundle["repeated_domain_clusters"]),
        "repeated_exact_pattern_clusters": len(bundle["repeated_exact_pattern_clusters"]),
        "output_dir": str(args.output_dir),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
