#!/usr/bin/env python3
"""Create and verify a non-shipping acoustic candidate identity.

This helper deliberately reuses the tuning canonicalization and wrapper semantics
from tuning_iteration_engine.py.  It does not alter product defaults and it is
not a promotion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

import tuning_iteration_engine as engine

_SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_tuning(args: argparse.Namespace) -> dict[str, float]:
    return engine.canonical_tuning({
        "aec_mu": args.aec_mu,
        "ns_floor": args.ns_floor,
        "agc_target_dbfs": args.agc_target_dbfs,
        "limiter_dbfs": args.limiter_dbfs,
    })


def create_identity(args: argparse.Namespace) -> dict:
    if not _SHA40.fullmatch(args.source_revision):
        raise ValueError("source revision must be an exact 40-character commit SHA")
    if not _SHA256.fullmatch(args.provenance_sha256):
        raise ValueError("provenance SHA-256 must be 64 hex characters, optionally prefixed by sha256:")
    tuning = parse_tuning(args)
    actual_id = engine.tuning_id(tuning)
    if actual_id != args.candidate_id:
        raise ValueError(
            f"candidate identity mismatch: expected {args.candidate_id}, canonical tuning yields {actual_id}"
        )
    if not args.processor.is_file():
        raise ValueError(f"processor does not exist: {args.processor}")
    engine.write_wrapper(args.wrapper, args.processor, tuning)
    result = {
        "schema_version": 1,
        "authority": "non-shipping-acoustic-candidate-qualification",
        "source_revision": args.source_revision.lower(),
        "candidate_id": actual_id,
        "tuning": tuning,
        "processor_sha256": sha256_file(args.processor),
        "provenance_sha256": args.provenance_sha256.lower().removeprefix("sha256:"),
        "wrapper": str(args.wrapper),
        "rule": (
            "This identity may qualify a fixed acoustic candidate only. It never changes shipping defaults "
            "and cannot substitute for target, HIL, real-device, soak, or product-certification evidence."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    tuning = engine.canonical_tuning({
        "aec_mu": 0.24,
        "ns_floor": 0.12,
        "agc_target_dbfs": -20.0,
        "limiter_dbfs": -2.0,
    })
    assert engine.tuning_id(tuning) == "4a6a408bf0e3"
    with tempfile.TemporaryDirectory(prefix="ap-acoustic-candidate-") as temporary:
        root = Path(temporary)
        processor = root / "processor"
        processor.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        processor.chmod(0o700)
        namespace = argparse.Namespace(
            source_revision="e2aae1cc2b8b8356b32d82347e39e0bc5bd6dca6",
            provenance_sha256="f57a5a210fd0a7a297254a9008372609d857fbcc6b90e736fd873de1b35eee59",
            candidate_id="4a6a408bf0e3",
            aec_mu=0.24,
            ns_floor=0.12,
            agc_target_dbfs=-20.0,
            limiter_dbfs=-2.0,
            processor=processor,
            wrapper=root / "wrapper",
            output=root / "identity.json",
        )
        result = create_identity(namespace)
        assert result["candidate_id"] == "4a6a408bf0e3"
        assert result["authority"] == "non-shipping-acoustic-candidate-qualification"
        assert namespace.wrapper.is_file()
        bad = argparse.Namespace(**vars(namespace))
        bad.candidate_id = "000000000000"
        try:
            create_identity(bad)
        except ValueError as exc:
            assert "identity mismatch" in str(exc)
        else:
            raise AssertionError("mismatched candidate id must fail closed")
    print("acoustic candidate identity self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-revision")
    parser.add_argument("--provenance-sha256")
    parser.add_argument("--candidate-id")
    parser.add_argument("--aec-mu", type=float)
    parser.add_argument("--ns-floor", type=float)
    parser.add_argument("--agc-target-dbfs", type=float)
    parser.add_argument("--limiter-dbfs", type=float)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--wrapper", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (
        "source_revision", "provenance_sha256", "candidate_id", "aec_mu", "ns_floor",
        "agc_target_dbfs", "limiter_dbfs", "processor", "wrapper", "output",
    )
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(missing))
    result = create_identity(args)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
