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
    require(isinstance(entries, list) and entries,
            "terminal registry candidates must be a non-empty list")
    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        require(isinstance(raw, dict), "terminal registry entry must be an object")
        candidate_id = str(raw.get("candidate_id", ""))
        source_revision = str(raw.get("source_revision", ""))
        identity = (source_revision, candidate_id)
        require(identity not in seen, f"duplicate terminal candidate identity: {source_revision}:{candidate_id}")
        seen.add(identity)
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
    # Check the converse as well: validating only listed entries lets a missing
    # row turn a rejected identity back into CANDIDATE_NOT_TERMINAL. Every
    # archived acoustic terminal must have exactly one validated registry row.
    archived_paths = {
        str(path.relative_to(root))
        for path in root.glob("docs/program/evidence/acoustic-candidate-*/**/terminal.json")
    }
    registered_paths = {item["terminal_path"] for item in normalized}
    require(registered_paths == archived_paths,
            "terminal registry evidence coverage mismatch: "
            f"missing={sorted(archived_paths - registered_paths)} "
            f"unarchived={sorted(registered_paths - archived_paths)}")
    return {
        "schema_version": 1,
        "authority": registry["authority"],
        "terminal_candidates": sorted(normalized, key=lambda item: item["candidate_id"]),
    }


def find_terminal(result: dict[str, Any], candidate_id: str,
                  source_revision: str) -> dict[str, Any] | None:
    return next((
        item for item in result["terminal_candidates"]
        if item["candidate_id"] == candidate_id
        and item["source_revision"] == source_revision
    ), None)


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
        assert find_terminal(result, "deadbeef0000", "a" * 40) is not None
        # Candidate IDs are tuning-only hashes. A new source revision with the
        # same tuning is a distinct candidate lineage and must remain eligible.
        assert find_terminal(result, "deadbeef0000", "b" * 40) is None
        broken = load_object(evidence / "terminal.json")
        broken["qualification"]["next_gate"] = "validation-grade-blind"
        (evidence / "terminal.json").write_text(json.dumps(broken), encoding="utf-8")
        try:
            validate_registry(root, DEFAULT_REGISTRY)
        except ValueError:
            pass
        else:
            raise AssertionError("terminal candidate regained next gate")
        # Metadata-only regression fixtures; never execute a candidate or audio.
        (evidence / "terminal.json").write_text(json.dumps(terminal), encoding="utf-8")
        first = load_object(registry_path)
        other_path = root / "docs/program/evidence/acoustic-candidate-feedface0000/public-relative-run-2/terminal.json"
        other_path.parent.mkdir(parents=True)
        other = json.loads(json.dumps(terminal))
        other["candidate"] = {"candidate_id": "feedface0000", "source_revision": "d" * 40}
        other_path.write_text(json.dumps(other), encoding="utf-8")
        complete = json.loads(json.dumps(first))
        complete["candidates"].append({
            "candidate_id": "feedface0000", "source_revision": "d" * 40,
            "decision": other["decision"],
            "terminal_path": str(other_path.relative_to(root)),
        })

        def write_registry(value: dict[str, Any]) -> None:
            registry_path.write_text(json.dumps(value), encoding="utf-8")

        def rejected(value: dict[str, Any], message: str) -> None:
            write_registry(value)
            try:
                validate_registry(root, DEFAULT_REGISTRY)
            except ValueError:
                pass
            else:
                raise AssertionError(message)
            finally:
                write_registry(complete)

        write_registry(complete)
        assert len(validate_registry(root, DEFAULT_REGISTRY)["terminal_candidates"]) == 2
        # Empty, missing collection, and either non-empty incomplete subset.
        for entries in ([], None, complete["candidates"][:1], complete["candidates"][1:]):
            broken_registry = {**complete, "candidates": entries}
            rejected(broken_registry, "incomplete terminal registry was accepted")
        rejected({k: v for k, v in complete.items() if k != "candidates"},
                 "missing terminal collection was accepted")
        rejected({**complete, "candidates": complete["candidates"] * 2},
                 "duplicate terminal identities were accepted")
        # Indexed paths must still exist and belong to the archive namespace.
        other_path.unlink()
        rejected(complete, "missing indexed evidence was accepted")
        other_path.write_text(json.dumps(other), encoding="utf-8")
        outside = root / "docs/program/evidence/other/terminal.json"
        outside.parent.mkdir(parents=True)
        outside.write_text(json.dumps(other), encoding="utf-8")
        moved = json.loads(json.dumps(complete))
        moved["candidates"][1]["terminal_path"] = str(outside.relative_to(root))
        rejected(moved, "non-canonical terminal copy replaced archived evidence")
        # Restore canonical coverage: unrelated non-acoustic archives do not
        # become acoustic candidates, and registry ordering is not authority.
        write_registry({**complete, "candidates": list(reversed(complete["candidates"]))})
        assert len(validate_registry(root, DEFAULT_REGISTRY)["terminal_candidates"]) == 2
    print("acoustic terminal registry self-test: OK; 8 coverage negative cases passed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--assert-not-terminal")
    parser.add_argument("--source-revision")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    result = validate_registry(Path("."), args.registry)
    if args.assert_not_terminal:
        candidate_id = str(args.assert_not_terminal)
        source_revision = str(args.source_revision or "")
        if SOURCE_SHA.fullmatch(source_revision) is None:
            parser.error("--source-revision is required with --assert-not-terminal")
        item = find_terminal(result, candidate_id, source_revision)
        if item is not None:
            print(json.dumps({
                "decision": "TERMINAL_CANDIDATE_REJECTED",
                **item,
            }, sort_keys=True))
            return 3
        print(json.dumps({
            "decision": "CANDIDATE_NOT_TERMINAL",
            "candidate_id": candidate_id,
            "source_revision": source_revision,
        }, sort_keys=True))
        return 0

    if args.check or not args.assert_not_terminal:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
