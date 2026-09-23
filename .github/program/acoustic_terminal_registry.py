#!/usr/bin/env python3
"""Validate and enforce the non-shipping acoustic terminal candidate registry."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY = Path(".github/program/acoustic_terminal_registry.json")
CANDIDATE_ID = re.compile(r"^[0-9a-f]{12,16}$")
SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_DECISIONS = {
    "HOSTED_BLIND_REJECTED_NON_SHIPPING",
    "PUBLIC_RELATIVE_REJECTED_NON_SHIPPING",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_terminal(entry: dict[str, Any], terminal: dict[str, Any], path: Path) -> None:
    candidate_id = str(entry.get("candidate_id", ""))
    source_revision = str(entry.get("source_revision", ""))
    decision = str(entry.get("decision", ""))
    require(CANDIDATE_ID.fullmatch(candidate_id) is not None,
            f"invalid registry candidate id: {candidate_id}")
    require(SOURCE_SHA.fullmatch(source_revision) is not None,
            f"invalid registry source revision: {candidate_id}")
    require(decision in ALLOWED_DECISIONS,
            f"unsupported terminal decision for {candidate_id}: {decision}")
    require(terminal.get("schema_version") == 1,
            f"terminal schema drift: {path}")
    require(terminal.get("terminal") is True,
            f"terminal flag must stay true: {candidate_id}")
    require(terminal.get("decision") == decision,
            f"terminal decision mismatch: {candidate_id}")

    candidate = terminal.get("candidate")
    require(isinstance(candidate, dict),
            f"terminal candidate object missing: {candidate_id}")
    require(candidate.get("candidate_id") == candidate_id,
            f"terminal candidate id mismatch: {candidate_id}")
    require(candidate.get("source_revision") == source_revision,
            f"terminal source mismatch: {candidate_id}")

    boundary = terminal.get("authority_boundary")
    require(isinstance(boundary, dict),
            f"terminal authority boundary missing: {candidate_id}")
    shipping = boundary.get("shipping_promotion")
    require(shipping == "NOT_ADMITTED",
            f"terminal candidate gained shipping authority: {candidate_id}")

    if decision == "PUBLIC_RELATIVE_REJECTED_NON_SHIPPING":
        require(terminal.get("authority") ==
                "non-shipping-public-relative-acoustic-candidate-terminal",
                f"public-relative authority drift: {candidate_id}")
        qualification = terminal.get("qualification")
        require(isinstance(qualification, dict),
                f"public-relative qualification missing: {candidate_id}")
        require(qualification.get("classifier_decision") == decision,
                f"classifier decision mismatch: {candidate_id}")
        require(qualification.get("terminal_candidate") is True,
                f"classifier terminal flag drift: {candidate_id}")
        require(qualification.get("next_gate") is None,
                f"terminal candidate retained next gate: {candidate_id}")
        require(qualification.get("retry_or_reselection_allowed") is False,
                f"terminal candidate regained retry/reselection: {candidate_id}")
        require(qualification.get("absolute_policy_is_promotion_authority") is False,
                f"absolute policy gained promotion authority: {candidate_id}")
        regressions = qualification.get("regressions")
        require(isinstance(regressions, list) and regressions,
                f"terminal public-relative rejection lacks regression evidence: {candidate_id}")
        evidence = terminal.get("evidence")
        require(isinstance(evidence, dict),
                f"terminal evidence missing: {candidate_id}")
        require(str(evidence.get("artifact_digest", "")).startswith("sha256:"),
                f"terminal artifact digest missing: {candidate_id}")
        require(re.fullmatch(r"[0-9a-f]{64}",
                str(evidence.get("public_relative_qualification_sha256", ""))) is not None,
                f"terminal qualification sha missing: {candidate_id}")
        require(boundary.get("blind_qualification") == "NOT_EXECUTED",
                f"public-relative terminal candidate unexpectedly gained blind authority: {candidate_id}")


def validate_registry(root: Path, registry_path: Path) -> dict[str, Any]:
    registry = load_object(root / registry_path)
    require(registry.get("schema_version") == 1, "terminal registry schema drift")
    require(registry.get("authority") == "non-shipping-acoustic-terminal-registry",
            "terminal registry authority drift")
    entries = registry.get("candidates")
    require(isinstance(entries, list), "terminal registry candidates must be a list")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        require(isinstance(raw, dict), "terminal registry entry must be an object")
        candidate_id = str(raw.get("candidate_id", ""))
        require(candidate_id not in seen, f"duplicate terminal candidate: {candidate_id}")
        seen.add(candidate_id)
        rel = Path(str(raw.get("terminal_path", "")))
        require(not rel.is_absolute() and ".." not in rel.parts,
                f"unsafe terminal path: {candidate_id}")
        require(rel.parts[:3] == ("docs", "program", "evidence"),
                f"terminal path outside evidence root: {candidate_id}")
        require(rel.name == "terminal.json",
                f"terminal path must end in terminal.json: {candidate_id}")
        full = root / rel
        require(full.is_file(), f"terminal evidence missing: {candidate_id}")
        terminal = load_object(full)
        validate_terminal(raw, terminal, rel)
        normalized.append({
            "candidate_id": candidate_id,
            "source_revision": raw["source_revision"],
            "decision": raw["decision"],
            "terminal_path": str(rel),
        })
    return {
        "schema_version": 1,
        "authority": registry["authority"],
        "terminal_candidates": sorted(normalized, key=lambda item: item["candidate_id"]),
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-acoustic-terminal-registry-") as tmp:
        root = Path(tmp)
        evidence = root / "docs/program/evidence/acoustic-candidate-deadbeef0000/public-relative-run-1"
        evidence.mkdir(parents=True)
        terminal = {
            "schema_version": 1,
            "authority": "non-shipping-public-relative-acoustic-candidate-terminal",
            "decision": "PUBLIC_RELATIVE_REJECTED_NON_SHIPPING",
            "terminal": True,
            "candidate": {
                "candidate_id": "deadbeef0000",
                "source_revision": "a" * 40,
            },
            "qualification": {
                "classifier_decision": "PUBLIC_RELATIVE_REJECTED_NON_SHIPPING",
                "terminal_candidate": True,
                "next_gate": None,
                "retry_or_reselection_allowed": False,
                "absolute_policy_is_promotion_authority": False,
                "regressions": [{"gate": "case_delta_excursion"}],
            },
            "evidence": {
                "artifact_digest": "sha256:" + "b" * 64,
                "public_relative_qualification_sha256": "c" * 64,
            },
            "authority_boundary": {
                "blind_qualification": "NOT_EXECUTED",
                "shipping_promotion": "NOT_ADMITTED",
            },
        }
        (evidence / "terminal.json").write_text(
            json.dumps(terminal), encoding="utf-8"
        )
        registry_path = root / DEFAULT_REGISTRY
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text(json.dumps({
            "schema_version": 1,
            "authority": "non-shipping-acoustic-terminal-registry",
            "candidates": [{
                "candidate_id": "deadbeef0000",
                "source_revision": "a" * 40,
                "decision": "PUBLIC_RELATIVE_REJECTED_NON_SHIPPING",
                "terminal_path": str((evidence / "terminal.json").relative_to(root)),
            }],
        }), encoding="utf-8")
        result = validate_registry(root, DEFAULT_REGISTRY)
        assert result["terminal_candidates"][0]["candidate_id"] == "deadbeef0000"
        broken = load_object(evidence / "terminal.json")
        broken["qualification"]["next_gate"] = "validation-grade-blind"
        (evidence / "terminal.json").write_text(json.dumps(broken), encoding="utf-8")
        try:
            validate_registry(root, DEFAULT_REGISTRY)
        except ValueError:
            pass
        else:
            raise AssertionError("terminal candidate regained next gate")
    print("acoustic terminal registry self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--assert-not-terminal")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    result = validate_registry(Path("."), args.registry)
    if args.assert_not_terminal:
        candidate_id = str(args.assert_not_terminal)
        item = next((item for item in result["terminal_candidates"]
                     if item["candidate_id"] == candidate_id), None)
        if item is not None:
            print(json.dumps({
                "decision": "TERMINAL_CANDIDATE_REJECTED",
                **item,
            }, sort_keys=True))
            return 3
        print(json.dumps({
            "decision": "CANDIDATE_NOT_TERMINAL",
            "candidate_id": candidate_id,
        }, sort_keys=True))
        return 0

    if args.check or not args.assert_not_terminal:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
