#!/usr/bin/env python3
"""Validate the research dataset registry and optimizer authority boundary."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = Path(__file__).resolve().with_name("dataset-registry.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
OPTIMIZER_ROLES = {"development", "validation", "shadow"}
SOURCE_KINDS = {"synthetic", "public", "hosted-real", "product-external"}
STAGES = {"aec", "ns", "vad", "bf", "agc", "res", "sync", "pipeline"}
EXPECTED_SHIPPING = {
    "tag": "v2.3.16",
    "source_sha": "57e4c64adc1cf06819e46e24e275ecd746d5f17f",
}
EXPECTED_NEXT_GATE = "validation-grade-blind"


def _repo_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must stay in repository: {raw}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {raw}")
    return resolved


def _identity(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def validate_registry(registry: dict[str, Any], root: Path) -> dict[str, Any]:
    expected_keys = {
        "schema_version", "registry_id", "shipping_baseline", "forbidden_optimizer_tiers",
        "terminal_candidates", "datasets", "output_authority",
    }
    if set(registry) != expected_keys:
        raise ValueError(f"dataset registry fields drift: {sorted(set(registry) ^ expected_keys)}")
    if registry["schema_version"] != 1 or not str(registry["registry_id"]):
        raise ValueError("dataset registry identity invalid")

    shipping = registry["shipping_baseline"]
    if shipping != {**EXPECTED_SHIPPING, "frozen": True}:
        raise ValueError("research registry must bind the immutable v2.3.16 shipping baseline")

    forbidden = registry["forbidden_optimizer_tiers"]
    if not isinstance(forbidden, list) or len(forbidden) != len(set(forbidden)):
        raise ValueError("forbidden_optimizer_tiers must be unique")
    if "validation-grade-blind" not in forbidden or "product-certified" not in forbidden:
        raise ValueError("blind/product authorities must be forbidden optimizer inputs")

    terminal = registry["terminal_candidates"]
    if not isinstance(terminal, list):
        raise ValueError("terminal_candidates must be a list")
    terminal_ids: set[str] = set()
    for item in terminal:
        if set(item) != {"candidate_id", "source_sha", "decision"}:
            raise ValueError("terminal candidate record fields invalid")
        if not str(item["candidate_id"]) or not SHA_RE.fullmatch(str(item["source_sha"])):
            raise ValueError("terminal candidate identity invalid")
        candidate_id = str(item["candidate_id"])
        if candidate_id in terminal_ids:
            raise ValueError("duplicate terminal candidate id")
        terminal_ids.add(candidate_id)
        if not str(item["decision"]):
            raise ValueError("terminal candidate decision required")

    datasets = registry["datasets"]
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("datasets must be non-empty")
    seen_ids: set[str] = set()
    selection_sources = 0
    evaluation_sources = 0
    resolved: list[dict[str, Any]] = []
    for entry in datasets:
        required = {
            "id", "source_kind", "stages", "lock_path", "builder_path",
            "identity_key", "identity_value", "selection_roles", "evaluation_roles",
            "frozen_holdout", "may_promote_shipping", "notes",
        }
        if set(entry) != required:
            raise ValueError(f"dataset entry fields invalid for {entry.get('id')}")
        dataset_id = entry["id"]
        if not isinstance(dataset_id, str) or not dataset_id or dataset_id in seen_ids:
            raise ValueError("dataset ids must be unique non-empty strings")
        seen_ids.add(dataset_id)
        if entry["source_kind"] not in SOURCE_KINDS:
            raise ValueError(f"unknown source_kind for {dataset_id}")
        stages = entry["stages"]
        if not isinstance(stages, list) or not stages or set(stages) - STAGES:
            raise ValueError(f"invalid stages for {dataset_id}")
        if len(stages) != len(set(stages)):
            raise ValueError(f"duplicate stages for {dataset_id}")
        selection_roles = entry["selection_roles"]
        evaluation_roles = entry["evaluation_roles"]
        if (not isinstance(selection_roles, list) or not isinstance(evaluation_roles, list) or
                set(selection_roles) - OPTIMIZER_ROLES or set(evaluation_roles) - OPTIMIZER_ROLES):
            raise ValueError(f"invalid optimizer roles for {dataset_id}")
        if len(selection_roles) != len(set(selection_roles)) or len(evaluation_roles) != len(set(evaluation_roles)):
            raise ValueError(f"duplicate optimizer role for {dataset_id}")
        if set(selection_roles) - {"development"}:
            raise ValueError(f"candidate selection must be development-only: {dataset_id}")
        if entry["may_promote_shipping"] is not False:
            raise ValueError(f"research dataset cannot gain shipping promotion authority: {dataset_id}")
        if not isinstance(entry["frozen_holdout"], bool):
            raise ValueError(f"frozen_holdout must be boolean: {dataset_id}")
        if entry["frozen_holdout"] and selection_roles:
            raise ValueError(f"frozen holdout cannot select candidates: {dataset_id}")
        if entry["source_kind"] == "product-external" and (selection_roles or evaluation_roles):
            raise ValueError(f"product-external data cannot enter hosted optimizer feedback: {dataset_id}")
        if not isinstance(entry["notes"], str) or not entry["notes"]:
            raise ValueError(f"notes required for {dataset_id}")

        lock_path = entry["lock_path"]
        builder_path = entry["builder_path"]
        if entry["source_kind"] == "product-external":
            if lock_path is not None or builder_path is not None or entry["identity_key"] is not None or entry["identity_value"] is not None:
                raise ValueError(f"product-external entry must not bind hosted repository material: {dataset_id}")
            bound_identity = "external-physical-only"
        elif (lock_path is None) == (builder_path is None):
            raise ValueError(f"exactly one lock_path or builder_path required: {dataset_id}")
        else:
            bound_identity = None
        if entry["source_kind"] != "product-external" and lock_path is not None:
            if not isinstance(lock_path, str):
                raise ValueError(f"lock_path invalid: {dataset_id}")
            path = _repo_path(root, lock_path)
            if not path.is_file():
                raise ValueError(f"missing lock file: {lock_path}")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1:
                raise ValueError(f"dataset lock schema drift: {lock_path}")
            identity_key = entry["identity_key"]
            identity_value = entry["identity_value"]
            if not isinstance(identity_key, str) or not isinstance(identity_value, str):
                raise ValueError(f"lock identity required: {dataset_id}")
            actual = _identity(payload, identity_key)
            if actual != identity_value:
                raise ValueError(
                    f"dataset lock identity drift for {dataset_id}: {identity_key}={actual!r} expected={identity_value!r}"
                )
            bound_identity = actual
        elif entry["source_kind"] != "product-external":
            if entry["identity_key"] is not None or entry["identity_value"] is not None:
                raise ValueError(f"builder entry cannot declare lock identity: {dataset_id}")
            if not isinstance(builder_path, str):
                raise ValueError(f"builder_path invalid: {dataset_id}")
            path = _repo_path(root, builder_path)
            if not path.is_file():
                raise ValueError(f"missing builder: {builder_path}")
            bound_identity = builder_path

        if selection_roles:
            selection_sources += 1
        if evaluation_roles:
            evaluation_sources += 1
        resolved.append({"id": dataset_id, "identity": bound_identity})

    if selection_sources < 1:
        raise ValueError("registry requires at least one development selection source")
    if evaluation_sources < 3:
        raise ValueError("registry requires at least three independent evaluation-capable sources")

    authority = registry["output_authority"]
    if authority != {
        "candidate_status": "FROZEN_RESEARCH_CANDIDATE",
        "next_gate": EXPECTED_NEXT_GATE,
        "shipping_authority": False,
        "hil_authority": False,
        "product_certification_authority": False,
        "automatic_main_mutation": False,
    }:
        raise ValueError("research optimizer output authority drift")
    return {"registry_id": registry["registry_id"], "datasets": resolved, "terminal_candidates": len(terminal)}


def load_registry(path: Path = DEFAULT_REGISTRY, root: Path = REPO_ROOT) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    validate_registry(registry, root)
    return registry


def dataset_entry(registry: dict[str, Any], dataset_id: str) -> dict[str, Any]:
    match = next((item for item in registry["datasets"] if item["id"] == dataset_id), None)
    if match is None:
        raise ValueError(f"dataset is not registered for research optimization: {dataset_id}")
    return match


def role_allowed(registry: dict[str, Any], dataset_id: str, role: str, *, selection: bool) -> bool:
    if role not in OPTIMIZER_ROLES:
        raise ValueError(f"unknown optimizer role: {role}")
    entry = dataset_entry(registry, dataset_id)
    allowed = entry["selection_roles"] if selection else entry["evaluation_roles"]
    return role in allowed


def is_terminal_candidate(registry: dict[str, Any], candidate_id: str, source_sha: str) -> bool:
    if not SHA_RE.fullmatch(str(source_sha)):
        raise ValueError("source_sha must be an exact 40-char commit SHA")
    return any(item["candidate_id"] == candidate_id for item in registry["terminal_candidates"])


def self_test() -> None:
    live = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    validate_registry(live, REPO_ROOT)
    with tempfile.TemporaryDirectory(prefix="ap-dataset-registry-") as temporary:
        root = Path(temporary)
        (root / "validation").mkdir(parents=True)
        (root / "validation/tools").mkdir(parents=True, exist_ok=True)
        (root / "validation/tools/build.py").write_text("# fixture\n", encoding="utf-8")
        (root / "validation/lock.json").write_text(
            json.dumps({"schema_version": 1, "catalog_id": "fixture-v1"}) + "\n",
            encoding="utf-8",
        )
        fixture = {
            "schema_version": 1,
            "registry_id": "fixture",
            "shipping_baseline": {**EXPECTED_SHIPPING, "frozen": True},
            "forbidden_optimizer_tiers": ["validation-grade-blind", "product-certified"],
            "terminal_candidates": [{
                "candidate_id": "old", "source_sha": "a" * 40, "decision": "REJECTED"
            }],
            "datasets": [
                {
                    "id": "synthetic", "source_kind": "synthetic", "stages": ["pipeline"],
                    "lock_path": None, "builder_path": "validation/tools/build.py",
                    "identity_key": None, "identity_value": None,
                    "selection_roles": ["development"],
                    "evaluation_roles": ["validation", "shadow"], "frozen_holdout": False,
                    "may_promote_shipping": False, "notes": "fixture",
                },
                {
                    "id": "holdout-a", "source_kind": "public", "stages": ["aec"],
                    "lock_path": "validation/lock.json", "builder_path": None,
                    "identity_key": "catalog_id", "identity_value": "fixture-v1",
                    "selection_roles": [], "evaluation_roles": ["validation", "shadow"],
                    "frozen_holdout": True, "may_promote_shipping": False, "notes": "fixture",
                },
                {
                    "id": "holdout-b", "source_kind": "public", "stages": ["ns"],
                    "lock_path": "validation/lock.json", "builder_path": None,
                    "identity_key": "catalog_id", "identity_value": "fixture-v1",
                    "selection_roles": [], "evaluation_roles": ["validation", "shadow"],
                    "frozen_holdout": True, "may_promote_shipping": False, "notes": "fixture",
                },
            ],
            "output_authority": {
                "candidate_status": "FROZEN_RESEARCH_CANDIDATE",
                "next_gate": EXPECTED_NEXT_GATE,
                "shipping_authority": False, "hil_authority": False,
                "product_certification_authority": False, "automatic_main_mutation": False,
            },
        }
        validate_registry(fixture, root)
        assert role_allowed(fixture, "synthetic", "development", selection=True)
        assert not role_allowed(fixture, "holdout-a", "development", selection=True)
        assert is_terminal_candidate(fixture, "old", "a" * 40)
        assert is_terminal_candidate(fixture, "old", "b" * 40)
        bad = json.loads(json.dumps(fixture))
        bad["terminal_candidates"].append({
            "candidate_id": "old", "source_sha": "b" * 40, "decision": "REJECTED_AGAIN"
        })
        try:
            validate_registry(bad, root)
        except ValueError:
            pass
        else:
            raise AssertionError("terminal candidate id was duplicated across source SHAs")
        bad = json.loads(json.dumps(fixture))
        bad["datasets"][1]["selection_roles"] = ["development"]
        try:
            validate_registry(bad, root)
        except ValueError:
            pass
        else:
            raise AssertionError("frozen holdout gained candidate-selection authority")
        bad = json.loads(json.dumps(fixture))
        bad["output_authority"]["shipping_authority"] = True
        try:
            validate_registry(bad, root)
        except ValueError:
            pass
        else:
            raise AssertionError("research output gained shipping authority")
    print("research dataset registry self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.check and not args.self_test:
        parser.error("choose --check and/or --self-test")
    if args.self_test:
        self_test()
    if args.check:
        registry = load_registry(args.registry)
        summary = validate_registry(registry, REPO_ROOT)
        print(json.dumps({"result": "PASS", **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
