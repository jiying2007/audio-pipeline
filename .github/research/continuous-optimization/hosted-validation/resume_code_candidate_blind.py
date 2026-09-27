#!/usr/bin/env python3
"""Resume one consumed source-patch blind partition without repartitioning.

This helper never creates a holdout key and never changes case membership/order.
It accepts only the sealed I020 INCOMPLETE blind artifact from run 36304120808,
then rebinds ephemeral absolute AEC paths to the current runner cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import resume_incomplete_blind as common  # type: ignore

EXPECTED_SOURCE_RUN_ID = 36304120808
EXPECTED_SOURCE_ARTIFACT_ID = 10927016997
EXPECTED_SOURCE_ARTIFACT_DIGEST = (
    "sha256:eafc16de6a8984a25eca8cc383ca8ceb0d6291d63adf09ee6159397e6fe11fe8"
)
EXPECTED_QUALIFICATION_INFRA_SHA = "99ba1bf6844be910bc851f5449fb4f2388984977"
EXPECTED_SOURCE_BASE_SHA = "57e4c64adc1cf06819e46e24e275ecd746d5f17f"
EXPECTED_RESEARCH_CANDIDATE_ID = "b98b172f26ccaee3"
EXPECTED_CANDIDATE_ID = "vad-weak-start-requires-blend-v1"
EXPECTED_FINGERPRINT = "ebeec484da932ee7"
EXPECTED_VISIBLE_SHA256 = "e792054e5e04b255e82814bbf70a7be6eab1bef9a85b376dec2d41db5a3d92ee"
EXPECTED_BLIND_SHA256 = "175c74ff64e804d917fbfe1b468bfa90bc5d731d48a0300b7fe95d6fe415e7b0"
EXPECTED_VISIBLE_ORDER_SHA256 = "2520512119c1cbb339e8a0792fcc896d19f5066a6140f976c15551cd2db9e165"
EXPECTED_BLIND_ORDER_SHA256 = "41da0335d60fa5ca3cc1cdb225265d9c5b4b6e850768cde33c12d64898e44cd1"
EXPECTED_VISIBLE_CASES = 130
EXPECTED_BLIND_CASES = 30


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_single_line(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value:
        raise ValueError(f"single-line identity required: {path}")
    return value


def validate_source_evidence(evidence: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    summary = load(evidence / "qualification-summary.json")
    if summary.get("decision") != "BLIND_QUALIFICATION_INCOMPLETE_NON_SHIPPING":
        raise ValueError("resume source must be INCOMPLETE")
    if summary.get("terminal_candidate") is not False:
        raise ValueError("terminal candidate cannot be resumed")
    if summary.get("failed_stage") != "evidence-incomplete":
        raise ValueError("unexpected source failed_stage")
    if summary.get("research_candidate_id") != EXPECTED_RESEARCH_CANDIDATE_ID:
        raise ValueError("research candidate identity mismatch")
    if summary.get("candidate_id") != EXPECTED_CANDIDATE_ID:
        raise ValueError("candidate identity mismatch")
    if summary.get("source_base_sha") != EXPECTED_SOURCE_BASE_SHA:
        raise ValueError("source base identity mismatch")

    if manifest.get("research_candidate_id") != EXPECTED_RESEARCH_CANDIDATE_ID:
        raise ValueError("manifest research candidate drift")
    if manifest.get("candidate_id") != EXPECTED_CANDIDATE_ID:
        raise ValueError("manifest candidate drift")
    if manifest.get("source_base_sha") != EXPECTED_SOURCE_BASE_SHA:
        raise ValueError("manifest source base drift")

    if _read_single_line(evidence / "qualification-infra-revision.txt") != EXPECTED_QUALIFICATION_INFRA_SHA:
        raise ValueError("qualification infra revision mismatch")
    if _read_single_line(evidence / "source-base-revision.txt") != EXPECTED_SOURCE_BASE_SHA:
        raise ValueError("source base revision receipt mismatch")

    origin = load(evidence / "holdout-key-origin.json")
    if origin.get("origin") != "github-hosted-run-ephemeral":
        raise ValueError("holdout origin mismatch")
    if origin.get("key_persisted") is not False:
        raise ValueError("holdout key must not be persisted")
    if str(origin.get("github_run_id")) != str(EXPECTED_SOURCE_RUN_ID):
        raise ValueError("holdout source run mismatch")
    if str(origin.get("github_run_attempt")) != "1":
        raise ValueError("holdout source attempt mismatch")
    if origin.get("key_fingerprint") != EXPECTED_FINGERPRINT:
        raise ValueError("holdout fingerprint mismatch")

    for forbidden in (
        "baseline-visible-report.json",
        "candidate-visible-report.json",
        "baseline-blind-report.json",
        "candidate-blind-report.json",
    ):
        if (evidence / forbidden).exists():
            raise ValueError(f"source evidence unexpectedly contains {forbidden}")

    visible_path = evidence / "public/corpus-validation.json"
    blind_path = evidence / "public/corpus-blind.json"
    if sha256_file(visible_path) != EXPECTED_VISIBLE_SHA256:
        raise ValueError("visible corpus digest mismatch")
    if sha256_file(blind_path) != EXPECTED_BLIND_SHA256:
        raise ValueError("blind corpus digest mismatch")
    visible = load(visible_path)
    blind = load(blind_path)
    if visible.get("blind_key_fingerprint") != EXPECTED_FINGERPRINT:
        raise ValueError("visible fingerprint mismatch")
    if blind.get("blind_key_fingerprint") != EXPECTED_FINGERPRINT:
        raise ValueError("blind fingerprint mismatch")
    if len(visible.get("cases", [])) != EXPECTED_VISIBLE_CASES:
        raise ValueError("visible case count mismatch")
    if len(blind.get("cases", [])) != EXPECTED_BLIND_CASES:
        raise ValueError("blind case count mismatch")
    if common.ordered_case_hash(visible) != EXPECTED_VISIBLE_ORDER_SHA256:
        raise ValueError("visible case order mismatch")
    if common.ordered_case_hash(blind) != EXPECTED_BLIND_ORDER_SHA256:
        raise ValueError("blind case order mismatch")
    visible_ids = {case["case_id"] for case in visible["cases"]}
    blind_ids = {case["case_id"] for case in blind["cases"]}
    if visible_ids & blind_ids:
        raise ValueError("visible/blind partition overlap")
    return summary


def prepare(
    evidence: Path,
    manifest_path: Path,
    data_root: Path,
    visible_output: Path,
    blind_output: Path,
    receipt_output: Path,
) -> dict[str, Any]:
    manifest = load(manifest_path)
    summary = validate_source_evidence(evidence, manifest)

    visible_path = evidence / "public/corpus-validation.json"
    blind_path = evidence / "public/corpus-blind.json"
    visible = load(visible_path)
    blind = load(blind_path)

    rebound_visible, visible_changes = common.rebind_corpus(visible, data_root)
    rebound_blind, blind_changes = common.rebind_corpus(blind, data_root)

    if common.ordered_case_hash(rebound_visible) != EXPECTED_VISIBLE_ORDER_SHA256:
        raise ValueError("visible case membership/order changed during rebound")
    if common.ordered_case_hash(rebound_blind) != EXPECTED_BLIND_ORDER_SHA256:
        raise ValueError("blind case membership/order changed during rebound")
    if rebound_visible.get("blind_key_fingerprint") != EXPECTED_FINGERPRINT:
        raise ValueError("visible fingerprint changed during rebound")
    if rebound_blind.get("blind_key_fingerprint") != EXPECTED_FINGERPRINT:
        raise ValueError("blind fingerprint changed during rebound")

    for path, payload in (
        (visible_output, rebound_visible),
        (blind_output, rebound_blind),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    receipt = {
        "schema_version": 1,
        "authority": "resume-consumed-source-patch-blind-same-partition-only",
        "source_run_id": EXPECTED_SOURCE_RUN_ID,
        "source_artifact_id": EXPECTED_SOURCE_ARTIFACT_ID,
        "source_artifact_digest": EXPECTED_SOURCE_ARTIFACT_DIGEST,
        "source_decision": summary["decision"],
        "source_failed_stage": summary["failed_stage"],
        "research_candidate_id": EXPECTED_RESEARCH_CANDIDATE_ID,
        "candidate_id": EXPECTED_CANDIDATE_ID,
        "source_base_sha": EXPECTED_SOURCE_BASE_SHA,
        "qualification_infra_sha": EXPECTED_QUALIFICATION_INFRA_SHA,
        "blind_key_fingerprint": EXPECTED_FINGERPRINT,
        "visible_case_count": EXPECTED_VISIBLE_CASES,
        "blind_case_count": EXPECTED_BLIND_CASES,
        "visible_order_sha256": EXPECTED_VISIBLE_ORDER_SHA256,
        "blind_order_sha256": EXPECTED_BLIND_ORDER_SHA256,
        "original_visible_corpus_sha256": EXPECTED_VISIBLE_SHA256,
        "original_blind_corpus_sha256": EXPECTED_BLIND_SHA256,
        "rebound_visible_corpus_sha256": sha256_file(visible_output),
        "rebound_blind_corpus_sha256": sha256_file(blind_output),
        "rebound_path_count": visible_changes + blind_changes,
        "partition_changed": False,
        "new_holdout_key_generated": False,
        "candidate_or_policy_changed": False,
    }
    receipt_output.parent.mkdir(parents=True, exist_ok=True)
    receipt_output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def self_test() -> None:
    assert EXPECTED_VISIBLE_CASES == 130
    assert EXPECTED_BLIND_CASES == 30
    assert EXPECTED_VISIBLE_ORDER_SHA256 != EXPECTED_BLIND_ORDER_SHA256
    assert common.aec_suffix(Path("/x/AEC-Challenge/datasets/a.wav")) == Path("datasets/a.wav")
    print("I020 source-patch same-partition resume self-test: OK")


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

    required = (
        args.evidence, args.manifest, args.data_root,
        args.visible_output, args.blind_output, args.receipt_output,
    )
    if any(item is None for item in required):
        parser.error("all resume inputs/outputs are required")

    receipt = prepare(
        args.evidence.resolve(),
        args.manifest.resolve(),
        args.data_root.resolve(),
        args.visible_output.resolve(),
        args.blind_output.resolve(),
        args.receipt_output.resolve(),
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
