#!/usr/bin/env python3
"""Single source of truth for validation/certification authority boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_VALIDATION_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTHORITY = _VALIDATION_ROOT / "authority.json"
DEFAULT_CORPUS_SCHEMA = _VALIDATION_ROOT / "corpus.schema.json"
DEFAULT_POLICY_SCHEMA = _VALIDATION_ROOT / "policy.schema.json"
DEFAULT_REPORT_SCHEMA = _VALIDATION_ROOT / "report.schema.json"
VALID_OPTIMIZER_ROLES = {"development", "validation", "shadow"}
REQUIRED_TIER_FLAGS = {
    "requires_sealed_data",
    "allows_dev_split",
    "requires_blind_key",
    "blind",
    "shipping_authority",
}


def load_authority(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    authority = json.loads(path.read_text(encoding="utf-8"))
    validate_authority(authority)
    return authority


def validate_authority(authority: dict[str, Any]) -> None:
    if authority.get("schema_version") != 1:
        raise ValueError("authority schema_version must be 1")
    tiers = authority.get("corpus_tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("authority.corpus_tiers must be a non-empty object")
    ranks = []
    for name, spec in tiers.items():
        if not isinstance(name, str) or not name or not isinstance(spec, dict):
            raise ValueError("invalid corpus tier entry")
        rank = int(spec.get("rank", -1))
        if rank < 0:
            raise ValueError(f"invalid authority rank for {name}")
        ranks.append(rank)
        roles = spec.get("optimizer_roles", [])
        if not isinstance(roles, list) or any(role not in VALID_OPTIMIZER_ROLES for role in roles):
            raise ValueError(f"invalid optimizer_roles for {name}")
        missing = REQUIRED_TIER_FLAGS - set(spec)
        if missing:
            raise ValueError(f"missing authority flags for {name}: {sorted(missing)}")
        for flag in REQUIRED_TIER_FLAGS:
            if not isinstance(spec[flag], bool):
                raise ValueError(f"authority flag {name}.{flag} must be boolean")
        if spec["shipping_authority"]:
            raise ValueError(f"validation corpus tier cannot be shipping authority: {name}")
        if spec["blind"] != spec["requires_blind_key"]:
            raise ValueError(f"blind/key authority mismatch for {name}")
        if spec["blind"] and spec["optimizer_roles"]:
            raise ValueError(f"blind corpus cannot be optimizer input: {name}")
        if spec["blind"] and spec["allows_dev_split"]:
            raise ValueError(f"blind corpus cannot allow dev split: {name}")
    if len(ranks) != len(set(ranks)):
        raise ValueError("corpus tier authority ranks must be unique")

    terminal = authority.get("terminal_authority", {})
    product = terminal.get("product-certified") if isinstance(terminal, dict) else None
    if not isinstance(product, dict) or product.get("system") != "certification":
        raise ValueError("product-certified terminal authority must be owned by certification")
    if product.get("shipping_authority") is not True:
        raise ValueError("product-certified must be the shipping authority")
    if int(product.get("record_schema_version", 0)) != 4:
        raise ValueError("product-certified authority must bind certification schema v4")

    chain = authority.get("candidate_promotion_chain")
    if not isinstance(chain, list) or not chain or chain[-1] != "product-certified":
        raise ValueError("candidate promotion chain must terminate at product-certified")
    if "validation-grade-blind" not in chain or "hil-soak" not in chain:
        raise ValueError("candidate promotion chain must retain blind and HIL authorities")


def corpus_tiers(authority: dict[str, Any]) -> set[str]:
    return set(authority["corpus_tiers"])


def tier_spec(authority: dict[str, Any], tier: str) -> dict[str, Any]:
    spec = authority["corpus_tiers"].get(tier)
    if not isinstance(spec, dict):
        raise ValueError(f"unknown corpus tier: {tier}")
    return spec


def optimizer_role_allowed(authority: dict[str, Any], tier: str, role: str) -> bool:
    if role not in VALID_OPTIMIZER_ROLES:
        raise ValueError(f"unknown optimizer role: {role}")
    return role in tier_spec(authority, tier).get("optimizer_roles", [])


def _schema_enum(path: Path, kind: str) -> set[str]:
    schema = json.loads(path.read_text(encoding="utf-8"))
    if kind in {"corpus", "report"}:
        enum = schema.get("properties", {}).get("tier", {}).get("enum", [])
    elif kind == "policy":
        enum = (
            schema.get("properties", {})
            .get("allowed_tiers", {})
            .get("items", {})
            .get("enum", [])
        )
    else:
        raise ValueError(f"unknown validation schema kind: {kind}")
    return set(enum)


def validate_schema_sync(authority: dict[str, Any], corpus_schema: Path,
                         policy_schema: Path, report_schema: Path) -> None:
    expected = corpus_tiers(authority)
    for kind, path in (
        ("corpus", corpus_schema),
        ("policy", policy_schema),
        ("report", report_schema),
    ):
        actual = _schema_enum(path, kind)
        if actual != expected:
            raise ValueError(
                f"{path.name} tier enum drift: schema={sorted(actual)} "
                f"authority={sorted(expected)}"
            )
    report = json.loads(report_schema.read_text(encoding="utf-8"))
    binding_required = set(
        report.get("properties", {}).get("bindings", {}).get("required", [])
    )
    if "authority_sha256" not in binding_required:
        raise ValueError("report schema must require authority_sha256 binding")


def corpus_identity(path: Path) -> dict[str, Any]:
    corpus = json.loads(path.read_text(encoding="utf-8"))
    generator = corpus.get("generator") or {}
    if not isinstance(generator, dict):
        raise ValueError(f"corpus generator must be object/null: {path}")
    return {
        "path": str(path),
        "corpus_id": corpus.get("corpus_id"),
        "tier": corpus.get("tier"),
        "generator_seed": generator.get("seed"),
    }


def validate_optimizer_partitions(authority: dict[str, Any], development: Path,
                                  validation: Path, shadow: Path) -> dict[str, Any]:
    paths = {"development": development, "validation": validation, "shadow": shadow}
    identities = {role: corpus_identity(path) for role, path in paths.items()}
    for role, identity in identities.items():
        tier = identity["tier"]
        if tier not in corpus_tiers(authority):
            raise ValueError(f"unknown corpus tier for {role}: {tier}")
        if not optimizer_role_allowed(authority, tier, role):
            raise ValueError(f"authority forbids tier={tier} as optimizer role={role}")
    return identities


def self_test() -> None:
    authority = load_authority()
    assert optimizer_role_allowed(authority, "regression", "development")
    assert optimizer_role_allowed(authority, "research-validation", "development")
    assert optimizer_role_allowed(authority, "validation-grade", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade", "development")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "shadow")
    assert tier_spec(authority, "research-validation")["requires_sealed_data"] is True
    assert tier_spec(authority, "research-validation")["allows_dev_split"] is True
    assert tier_spec(authority, "validation-grade")["allows_dev_split"] is False
    assert tier_spec(authority, "validation-grade-blind")["requires_blind_key"] is True
    validate_schema_sync(
        authority, DEFAULT_CORPUS_SCHEMA, DEFAULT_POLICY_SCHEMA, DEFAULT_REPORT_SCHEMA
    )
    print("validation authority self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--corpus-schema", type=Path, default=DEFAULT_CORPUS_SCHEMA)
    parser.add_argument("--policy-schema", type=Path, default=DEFAULT_POLICY_SCHEMA)
    parser.add_argument("--report-schema", type=Path, default=DEFAULT_REPORT_SCHEMA)
    parser.add_argument("--development-corpus", type=Path)
    parser.add_argument("--validation-corpus", type=Path)
    parser.add_argument("--shadow-corpus", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    authority = load_authority(args.authority)
    validate_schema_sync(
        authority, args.corpus_schema, args.policy_schema, args.report_schema
    )
    provided = [args.development_corpus, args.validation_corpus, args.shadow_corpus]
    identities = None
    if any(item is not None for item in provided):
        if not all(item is not None for item in provided):
            parser.error("development/validation/shadow corpora must be supplied together")
        identities = validate_optimizer_partitions(
            authority, args.development_corpus, args.validation_corpus, args.shadow_corpus
        )
    print(json.dumps({
        "result": "PASS",
        "corpus_tiers": sorted(corpus_tiers(authority)),
        "terminal_authority": "product-certified",
        "optimizer_partitions": identities,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
