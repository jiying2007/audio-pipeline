#!/usr/bin/env python3
"""HMAC-partition immutable validation case identities without storing the key."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path


def canonical_identity(case: dict) -> str:
    source = case.get("source", {})
    return str(source.get("source_id") or source.get("path") or case["case_id"])



def stratification_value(case: dict, stratify: str | None) -> str:
    if stratify in (None, "none"):
        return "all"
    if stratify == "scenario":
        return str(case.get("scenario", "unknown"))
    if stratify == "dataset":
        source = case.get("source", {})
        return str(source.get("dataset_id", "unknown"))
    raise ValueError(f"unsupported stratification: {stratify}")


def partition_cases(cases: list[dict], key: bytes, holdout_percent: int,
                    stratify: str | None = None) -> tuple[list[dict], list[dict]]:
    validation_cases: list[dict] = []
    blind_cases: list[dict] = []
    groups: dict[str, list[tuple[int, dict]]] = {}
    for case in cases:
        identity = canonical_identity(case).encode("utf-8")
        digest = hmac.new(key, identity, hashlib.sha256).digest()
        bucket = int.from_bytes(digest[:4], "big") % 100
        groups.setdefault(stratification_value(case, stratify), []).append((bucket, case))
    for _group, rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda item: (item[0], canonical_identity(item[1])))
        group_validation: list[dict] = []
        group_blind: list[dict] = []
        for bucket, case in ordered:
            target = group_blind if bucket < holdout_percent else group_validation
            copied = dict(case)
            copied["split"] = "blind" if target is group_blind else "validation"
            target.append(copied)
        if stratify not in (None, "none") and len(ordered) >= 2:
            if not group_blind:
                moved = group_validation.pop(0)
                moved["split"] = "blind"
                group_blind.append(moved)
            if not group_validation:
                moved = group_blind.pop(-1)
                moved["split"] = "validation"
                group_validation.append(moved)
        validation_cases.extend(group_validation)
        blind_cases.extend(group_blind)
    validation_cases.sort(key=lambda case: case["case_id"])
    blind_cases.sort(key=lambda case: case["case_id"])
    return validation_cases, blind_cases


def self_test() -> None:
    key = b"audio-pipeline-holdout-self-test-key"
    cases = [
        {"case_id": f"case-{index:03d}", "scenario": f"s{index % 4}",
         "source": {"source_id": f"case-{index:03d}", "dataset_id": f"d{index % 3}"}}
        for index in range(160)
    ]
    expected_minima = {
        (100, 20): (60, 10),
        (100, 30): (60, 10),
        (160, 20): (100, 16),
        (160, 30): (100, 16),
    }
    for (count, percent), (min_validation, min_blind) in expected_minima.items():
        validation, blind = partition_cases(cases[:count], key, percent)
        assert len(validation) + len(blind) == count
        assert len(validation) >= min_validation, (count, percent, len(validation))
        assert len(blind) >= min_blind, (count, percent, len(blind))
        validation2, blind2 = partition_cases(cases[:count], key, percent)
        assert [item["case_id"] for item in validation] == [item["case_id"] for item in validation2]
        assert [item["case_id"] for item in blind] == [item["case_id"] for item in blind2]
    validation, blind = partition_cases(cases, key, 20, "scenario")
    for scenario in {case["scenario"] for case in cases}:
        assert any(case["scenario"] == scenario for case in validation)
        assert any(case["scenario"] == scenario for case in blind)
    dataset_validation, dataset_blind = partition_cases(cases, key, 20, "dataset")
    for dataset in {case["source"]["dataset_id"] for case in cases}:
        assert any(case["source"]["dataset_id"] == dataset for case in dataset_validation)
        assert any(case["source"]["dataset_id"] == dataset for case in dataset_blind)
    print("validation blind holdout self-test: OK")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--validation-output", type=Path)
    parser.add_argument("--blind-output", type=Path)
    parser.add_argument("--holdout-percent", type=int, default=20)
    parser.add_argument("--key-env", default="AP_VALIDATION_HOLDOUT_KEY")
    parser.add_argument("--stratify", choices=("none", "scenario", "dataset"), default="none")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.corpus is None or args.validation_output is None or args.blind_output is None:
        parser.error("--corpus, --validation-output and --blind-output are required")
    if not 1 <= args.holdout_percent <= 50:
        raise SystemExit("holdout-percent must be 1..50")
    key_text = os.environ.get(args.key_env, "")
    if len(key_text.encode("utf-8")) < 16:
        raise SystemExit(f"{args.key_env} must contain at least 16 bytes and must not be stored in Git")
    key = key_text.encode("utf-8")
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if corpus.get("tier") != "validation-grade" or not corpus.get("sealed_data"):
        raise SystemExit("holdout input must be sealed validation-grade corpus")
    validation_cases, blind_cases = partition_cases(corpus["cases"], key, args.holdout_percent, args.stratify)
    if not validation_cases or not blind_cases:
        raise SystemExit("holdout split produced an empty partition; increase corpus size")
    fingerprint = hashlib.sha256(key).hexdigest()[:16]
    base = {k: v for k, v in corpus.items() if k != "cases"}
    validation = dict(base, corpus_id=corpus["corpus_id"] + "-validation", tier="validation-grade",
                      blind_key_fingerprint=fingerprint, cases=validation_cases)
    blind = dict(base, corpus_id=corpus["corpus_id"] + "-blind", tier="validation-grade-blind",
                 blind_key_fingerprint=fingerprint, cases=blind_cases)
    args.validation_output.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.blind_output.write_text(json.dumps(blind, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validation": len(validation_cases), "blind": len(blind_cases),
                      "holdout_percent": args.holdout_percent,
                      "key_fingerprint": fingerprint, "stratify": args.stratify}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
