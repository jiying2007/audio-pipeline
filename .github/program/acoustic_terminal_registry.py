#!/usr/bin/env python3
"""Validate and query terminal acoustic candidate identities."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

EXPECTED_AUTHORITY = "non-shipping-acoustic-terminal-registry"
EXPECTED_IDENTITY_KEY = ["source_revision", "candidate_id"]
SOURCE_RE = re.compile(r"^[0-9a-f]{40}$")
CANDIDATE_RE = re.compile(r"^[0-9a-f]{12}$")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def validate_registry(path: Path, repo_root: Path) -> list[dict[str, Any]]:
    registry = load_json(path)
    if registry.get("schema_version") != 1:
        raise ValueError("terminal registry schema drift")
    if registry.get("authority") != EXPECTED_AUTHORITY:
        raise ValueError("terminal registry authority drift")
    if registry.get("identity_key") != EXPECTED_IDENTITY_KEY:
        raise ValueError("terminal registry identity key drift")
    entries = registry.get("terminal_candidates")
    if not isinstance(entries, list) or not entries:
        raise ValueError("terminal registry must contain candidates")
    seen: set[tuple[str, str]] = set()
    normalized: list[dict[str, Any]] = []
    evidence_root = (repo_root / "docs/program/evidence").resolve()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ValueError(f"terminal registry entry {index} must be an object")
        source = str(item.get("source_revision", ""))
        candidate = str(item.get("candidate_id", ""))
        decision = str(item.get("decision", ""))
        evidence_raw = str(item.get("evidence_path", ""))
        if not SOURCE_RE.fullmatch(source):
            raise ValueError(f"terminal registry source invalid: {source}")
        if not CANDIDATE_RE.fullmatch(candidate):
            raise ValueError(f"terminal registry candidate invalid: {candidate}")
        if not decision:
            raise ValueError(f"terminal registry decision missing: {source}:{candidate}")
        identity = (source, candidate)
        if identity in seen:
            raise ValueError(f"duplicate terminal identity: {source}:{candidate}")
        seen.add(identity)
        evidence = (repo_root / evidence_raw).resolve()
        try:
            evidence.relative_to(evidence_root)
        except ValueError as exc:
            raise ValueError(f"terminal evidence escapes evidence root: {evidence_raw}") from exc
        if not evidence.is_file():
            raise ValueError(f"terminal evidence missing: {evidence_raw}")
        terminal = load_json(evidence)
        terminal_candidate = terminal.get("candidate") or {}
        if terminal.get("schema_version") != 1 or terminal.get("terminal") is not True:
            raise ValueError(f"terminal evidence is not terminal: {evidence_raw}")
        if terminal.get("decision") != decision:
            raise ValueError(f"terminal decision mismatch: {evidence_raw}")
        if terminal_candidate.get("source_revision") != source or terminal_candidate.get("candidate_id") != candidate:
            raise ValueError(f"terminal identity mismatch: {evidence_raw}")
        qualification = terminal.get("qualification") or {}
        if qualification.get("retry_or_reselection_allowed") is not False:
            raise ValueError(f"terminal evidence must forbid retry/reselection: {evidence_raw}")
        normalized.append({
            "source_revision": source,
            "candidate_id": candidate,
            "decision": decision,
            "evidence_path": evidence_raw,
        })
    return normalized


def find_terminal(entries: list[dict[str, Any]], source_revision: str,
                  candidate_id: str) -> dict[str, Any] | None:
    for item in entries:
        if item["source_revision"] == source_revision and item["candidate_id"] == candidate_id:
            return item
    return None


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-terminal-registry-") as temporary:
        root = Path(temporary)
        evidence_dir = root / "docs/program/evidence/c"
        evidence_dir.mkdir(parents=True)
        terminal = {
            "schema_version": 1,
            "decision": "REJECTED",
            "terminal": True,
            "candidate": {
                "source_revision": "a" * 40,
                "candidate_id": "b" * 12,
            },
            "qualification": {"retry_or_reselection_allowed": False},
        }
        terminal_path = evidence_dir / "terminal.json"
        terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
        registry = {
            "schema_version": 1,
            "authority": EXPECTED_AUTHORITY,
            "identity_key": EXPECTED_IDENTITY_KEY,
            "terminal_candidates": [{
                "source_revision": "a" * 40,
                "candidate_id": "b" * 12,
                "decision": "REJECTED",
                "evidence_path": "docs/program/evidence/c/terminal.json",
            }],
        }
        registry_path = root / "docs/program/evidence/acoustic-terminal-registry.json"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        entries = validate_registry(registry_path, root)
        assert find_terminal(entries, "a" * 40, "b" * 12) is not None
        assert find_terminal(entries, "c" * 40, "b" * 12) is None
        assert find_terminal(entries, "a" * 40, "d" * 12) is None
    print("acoustic terminal registry self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path,
                        default=Path("docs/program/evidence/acoustic-terminal-registry.json"))
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--source-revision")
    parser.add_argument("--candidate-id")
    parser.add_argument("--reject-terminal", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    entries = validate_registry(args.registry, args.repo_root.resolve())
    if args.source_revision is None and args.candidate_id is None:
        print(json.dumps({"terminal_candidates": entries}, sort_keys=True))
        return 0
    if not args.source_revision or not args.candidate_id:
        parser.error("--source-revision and --candidate-id must be supplied together")
    if not SOURCE_RE.fullmatch(args.source_revision):
        parser.error("--source-revision must be 40 lowercase hex")
    if not CANDIDATE_RE.fullmatch(args.candidate_id):
        parser.error("--candidate-id must be 12 lowercase hex")
    terminal = find_terminal(entries, args.source_revision, args.candidate_id)
    if terminal is None:
        print(json.dumps({
            "terminal": False,
            "source_revision": args.source_revision,
            "candidate_id": args.candidate_id,
        }, sort_keys=True))
        return 0
    print(json.dumps({"terminal": True, **terminal}, sort_keys=True))
    return 3 if args.reject_terminal else 0


if __name__ == "__main__":
    raise SystemExit(main())
