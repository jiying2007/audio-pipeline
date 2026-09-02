#!/usr/bin/env python3
"""Single source of truth for validation/certification authority boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_AUTHORITY = Path(__file__).resolve().parents[1] / "authority.json"
DEFAULT_CORPUS_SCHEMA = Path(__file__).resolve().parents[1] / "corpus.schema.json"
VALID_OPTIMIZER_ROLES = {"development", "validation", "shadow"}


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
        if bool(spec.get("shipping_authority", False)):
            raise ValueError(f"validation corpus tier cannot be shipping authority: {name}")
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


def optimizer_role_allowed(authority: dict[str, Any], tier: str, role: str) -> bool:
    if role not in VALID_OPTIMIZER_ROLES:
        raise ValueError(f"unknown optimizer role: {role}")
    spec = authority["corpus_tiers"].get(tier)
    return isinstance(spec, dict) and role in spec.get("optimizer_roles", [])


def validate_schema_sync(authority: dict[str, Any], schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    enum = schema.get("properties", {}).get("tier", {}).get("enum", [])
    if set(enum) != corpus_tiers(authority):
        raise ValueError(
            f"corpus.schema.json tier enum drift: schema={sorted(enum)} "
            f"authority={sorted(corpus_tiers(authority))}"
        )


def self_test() -> None:
    authority = load_authority()
    assert optimizer_role_allowed(authority, "regression", "development")
    assert optimizer_role_allowed(authority, "validation-grade", "validation")
    assert not optimizer_role_allowed(authority, "validation-grade", "development")
    assert not optimizer_role_allowed(authority, "validation-grade-blind", "shadow")
    validate_schema_sync(authority, DEFAULT_CORPUS_SCHEMA)
    print("validation authority self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--corpus-schema", type=Path, default=DEFAULT_CORPUS_SCHEMA)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    authority = load_authority(args.authority)
    validate_schema_sync(authority, args.corpus_schema)
    print(json.dumps({
        "result": "PASS",
        "corpus_tiers": sorted(corpus_tiers(authority)),
        "terminal_authority": "product-certified",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
