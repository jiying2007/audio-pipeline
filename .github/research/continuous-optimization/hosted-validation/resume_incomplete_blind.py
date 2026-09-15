#!/usr/bin/env python3
"""Prepare a fail-closed resume of one INCOMPLETE blind qualification.

The helper never creates a holdout key or repartitions a corpus. It accepts only
sealed `visible-evidence-incomplete` evidence for the same frozen candidate,
then rebinds ephemeral absolute Microsoft AEC cache paths to the current runner.
Case membership, ordering, split identity and blind-key fingerprint must remain
unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

AUDIO_FIELDS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload


def ordered_case_hash(corpus: dict[str, Any]) -> str:
    ids = [str(case.get("case_id", "")) for case in corpus.get("cases", [])]
    if not ids or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("corpus case IDs must be non-empty and unique")
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def validate_incomplete(evidence: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    summary = load(evidence / "qualification-summary.json")
    if summary.get("decision") != "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING":
        raise ValueError("resume source must be an INCOMPLETE qualification")
    if summary.get("terminal_candidate") is not False:
        raise ValueError("terminal candidate cannot be resumed")
    if summary.get("failed_stage") != "visible-evidence-incomplete":
        raise ValueError("only visible-evidence-incomplete may use this resume path")
    if summary.get("visible_result") is not None or summary.get("blind_result") is not None:
        raise ValueError("resume source already carries an acoustic result")
    for key in ("research_candidate_id", "candidate_id", "source_sha"):
        if summary.get(key) != manifest.get(key):
            raise ValueError(f"resume candidate identity mismatch: {key}")
    for forbidden in ("validation-report.json", "blind-report.json"):
        if (evidence / forbidden).exists():
            raise ValueError(f"resume source unexpectedly contains {forbidden}")
    return summary


def aec_suffix(path: Path) -> Path | None:
    parts = path.parts
    try:
        index = parts.index("AEC-Challenge")
    except ValueError:
        return None
    return Path(*parts[index + 1:])


def rebind_corpus(corpus: dict[str, Any], data_root: Path) -> tuple[dict[str, Any], int]:
    result = json.loads(json.dumps(corpus))
    changed = 0
    for case in result.get("cases", []):
        source = case.get("source", {}) if isinstance(case.get("source", {}), dict) else {}
        for field in AUDIO_FIELDS:
            value = case.get(field)
            if not value:
                continue
            path = Path(str(value))
            if not path.is_absolute():
                continue
            suffix = aec_suffix(path)
            if suffix is None:
                raise ValueError(f"unexpected absolute audio path outside AEC cache: {path}")
            rebound = (data_root / "AEC-Challenge" / suffix).resolve()
            if not rebound.is_file():
                raise ValueError(f"rebound AEC audio missing: {rebound}")
            if field == "mic_audio" and source.get("mic_sha256"):
                if sha256_file(rebound) != source["mic_sha256"]:
                    raise ValueError(f"rebound mic hash mismatch: {case.get('case_id')}")
            if field == "render_audio" and source.get("render_sha256"):
                if sha256_file(rebound) != source["render_sha256"]:
                    raise ValueError(f"rebound render hash mismatch: {case.get('case_id')}")
            case[field] = str(rebound)
            changed += 1
    return result, changed


def prepare(evidence: Path, manifest_path: Path, data_root: Path,
            visible_output: Path, blind_output: Path, receipt_output: Path) -> dict[str, Any]:
    manifest = load(manifest_path)
    summary = validate_incomplete(evidence, manifest)
    visible_path = evidence / "public/corpus-validation.json"
    blind_path = evidence / "public/corpus-blind.json"
    visible = load(visible_path)
    blind = load(blind_path)
    if visible.get("blind_key_fingerprint") != blind.get("blind_key_fingerprint"):
        raise ValueError("saved visible/blind corpora do not share one blind-key fingerprint")
    fingerprint = visible.get("blind_key_fingerprint")
    if not fingerprint:
        raise ValueError("saved partition is missing blind-key fingerprint")
    visible_ids = [case["case_id"] for case in visible.get("cases", [])]
    blind_ids = [case["case_id"] for case in blind.get("cases", [])]
    if set(visible_ids) & set(blind_ids):
        raise ValueError("visible and blind partitions overlap")
    before_visible_order = ordered_case_hash(visible)
    before_blind_order = ordered_case_hash(blind)
    rebound_visible, visible_changes = rebind_corpus(visible, data_root)
    rebound_blind, blind_changes = rebind_corpus(blind, data_root)
    if ordered_case_hash(rebound_visible) != before_visible_order:
        raise ValueError("visible case membership/order changed during rebound")
    if ordered_case_hash(rebound_blind) != before_blind_order:
        raise ValueError("blind case membership/order changed during rebound")
    if rebound_visible.get("blind_key_fingerprint") != fingerprint or rebound_blind.get("blind_key_fingerprint") != fingerprint:
        raise ValueError("blind fingerprint changed during rebound")
    for path, payload in ((visible_output, rebound_visible), (blind_output, rebound_blind)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": 1,
        "authority": "resume-incomplete-blind-same-partition-only",
        "research_candidate_id": manifest["research_candidate_id"],
        "candidate_id": manifest["candidate_id"],
        "source_sha": manifest["source_sha"],
        "source_decision": summary["decision"],
        "source_failed_stage": summary["failed_stage"],
        "blind_key_fingerprint": fingerprint,
        "visible_case_count": len(visible_ids),
        "blind_case_count": len(blind_ids),
        "visible_order_sha256": before_visible_order,
        "blind_order_sha256": before_blind_order,
        "original_visible_corpus_sha256": sha256_file(visible_path),
        "original_blind_corpus_sha256": sha256_file(blind_path),
        "rebound_visible_corpus_sha256": sha256_file(visible_output),
        "rebound_blind_corpus_sha256": sha256_file(blind_output),
        "rebound_path_count": visible_changes + blind_changes,
        "partition_changed": False,
        "new_holdout_key_generated": False,
    }
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def self_test() -> None:
    assert aec_suffix(Path("/x/AEC-Challenge/datasets/a.wav")) == Path("datasets/a.wav")
    corpus = {"cases": [{"case_id": "a"}, {"case_id": "b"}]}
    assert ordered_case_hash(corpus) == ordered_case_hash(json.loads(json.dumps(corpus)))
    print("incomplete blind resume self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--visible-output", type=Path)
    parser.add_argument("--blind-output", type=Path)
    parser.add_argument("--receipt-output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.evidence, args.manifest, args.data_root, args.visible_output,
                args.blind_output, args.receipt_output)
    if any(item is None for item in required):
        parser.error("all resume inputs/outputs are required")
    receipt = prepare(args.evidence.resolve(), args.manifest.resolve(), args.data_root.resolve(),
                      args.visible_output.resolve(), args.blind_output.resolve(),
                      args.receipt_output.resolve())
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
