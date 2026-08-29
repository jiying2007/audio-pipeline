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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--blind-output", type=Path, required=True)
    parser.add_argument("--holdout-percent", type=int, default=20)
    parser.add_argument("--key-env", default="AP_VALIDATION_HOLDOUT_KEY")
    args = parser.parse_args()
    if not 1 <= args.holdout_percent <= 50:
        raise SystemExit("holdout-percent must be 1..50")
    key_text = os.environ.get(args.key_env, "")
    if len(key_text.encode("utf-8")) < 16:
        raise SystemExit(f"{args.key_env} must contain at least 16 bytes and must not be stored in Git")
    key = key_text.encode("utf-8")
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    if corpus.get("tier") != "validation-grade" or not corpus.get("sealed_data"):
        raise SystemExit("holdout input must be sealed validation-grade corpus")
    validation_cases = []
    blind_cases = []
    for case in corpus["cases"]:
        identity = canonical_identity(case).encode("utf-8")
        bucket = int.from_bytes(hmac.new(key, identity, hashlib.sha256).digest()[:4], "big") % 100
        target = blind_cases if bucket < args.holdout_percent else validation_cases
        copied = dict(case)
        copied["split"] = "blind" if target is blind_cases else "validation"
        target.append(copied)
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
                      "key_fingerprint": fingerprint}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
