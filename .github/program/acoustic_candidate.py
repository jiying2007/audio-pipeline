#!/usr/bin/env python3
"""CI-only identity adapter for a fixed non-shipping acoustic candidate.

This file intentionally contains only the small canonicalization/identity/wrapper
contract needed by candidate evidence workflows. It does not define shipping
defaults, modify the SDK, consume blind data for tuning, or grant promotion
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

_SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
TUNING_KEYS = ("aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs")
TUNING_FLAGS = {
    "aec_mu": "--aec-mu",
    "ns_floor": "--ns-floor",
    "agc_target_dbfs": "--agc-target-dbfs",
    "limiter_dbfs": "--limiter-dbfs",
}
_RUNTIME_ENV = {
    "aec_mu": "AP_TUNING_AEC_MU",
    "ns_floor": "AP_TUNING_NS_FLOOR",
    "agc_target_dbfs": "AP_TUNING_AGC_TARGET_DBFS",
    "limiter_dbfs": "AP_TUNING_LIMITER_DBFS",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_tuning(raw: dict[str, Any]) -> dict[str, float]:
    unknown = set(raw) - set(TUNING_KEYS)
    if unknown:
        raise ValueError(f"unknown tuning keys: {sorted(unknown)}")
    if set(raw) != set(TUNING_KEYS):
        raise ValueError("fixed candidate must define all supported tuning keys")
    tuning = {key: float(raw[key]) for key in TUNING_KEYS}
    for key, value in tuning.items():
        if not math.isfinite(value):
            raise ValueError(f"{key} must be finite")
    if not 0.0 < tuning["aec_mu"] <= 1.0:
        raise ValueError("aec_mu must be in (0, 1]")
    if not 0.02 <= tuning["ns_floor"] <= 1.0:
        raise ValueError("ns_floor must be in [0.02, 1]")
    if not -60.0 <= tuning["agc_target_dbfs"] <= -1.0:
        raise ValueError("agc_target_dbfs must be in [-60, -1]")
    if not -20.0 <= tuning["limiter_dbfs"] <= -0.1:
        raise ValueError("limiter_dbfs must be in [-20, -0.1]")
    if tuning["agc_target_dbfs"] >= tuning["limiter_dbfs"]:
        raise ValueError("agc_target_dbfs must be below limiter_dbfs")
    return tuning


def tuning_id(tuning: dict[str, float]) -> str:
    payload = json.dumps(tuning, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def write_wrapper(path: Path, processor: Path, tuning: dict[str, float]) -> None:
    flags: list[str] = []
    for key in TUNING_KEYS:
        flags += [TUNING_FLAGS[key], repr(float(tuning[key]))]
    script = [
        "#!/usr/bin/env python3",
        "import os, sys",
        f"processor = {str(processor.resolve())!r}",
        f"prefix = {flags!r}",
        "os.execv(processor, [processor] + prefix + sys.argv[1:])",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(script), encoding="utf-8")
    path.chmod(0o700)


def parse_tuning(args: argparse.Namespace) -> dict[str, float]:
    return canonical_tuning({
        "aec_mu": args.aec_mu,
        "ns_floor": args.ns_floor,
        "agc_target_dbfs": args.agc_target_dbfs,
        "limiter_dbfs": args.limiter_dbfs,
    })


def runtime_env(tuning: dict[str, float]) -> dict[str, str]:
    return {_RUNTIME_ENV[key]: repr(float(tuning[key])) for key in TUNING_KEYS}


def create_identity(args: argparse.Namespace) -> dict[str, Any]:
    if not _SHA40.fullmatch(args.source_revision):
        raise ValueError("source revision must be an exact 40-character commit SHA")
    if not _SHA256.fullmatch(args.provenance_sha256):
        raise ValueError(
            "provenance SHA-256 must be 64 hex characters, optionally prefixed by sha256:"
        )
    if not re.fullmatch(r"[0-9a-f]{12}", args.candidate_id):
        raise ValueError("candidate id must be exactly 12 lowercase hex characters")
    tuning = parse_tuning(args)
    actual_id = tuning_id(tuning)
    if actual_id != args.candidate_id:
        raise ValueError(
            f"candidate identity mismatch: expected {args.candidate_id}, canonical tuning yields {actual_id}"
        )
    if not args.processor.is_file():
        raise ValueError(f"processor does not exist: {args.processor}")
    write_wrapper(args.wrapper, args.processor, tuning)
    env = runtime_env(tuning)
    if args.env_output is not None:
        args.env_output.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"AP_ACOUSTIC_CANDIDATE_ID={actual_id}"]
        lines.extend(f"{key}={env[key]}" for key in sorted(env))
        args.env_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = {
        "schema_version": 1,
        "authority": "non-shipping-acoustic-candidate-qualification",
        "source_revision": args.source_revision.lower(),
        "candidate_id": actual_id,
        "tuning": tuning,
        "runtime_env": env,
        "processor_sha256": sha256_file(args.processor),
        "provenance_sha256": args.provenance_sha256.lower().removeprefix("sha256:"),
        "wrapper": str(args.wrapper),
        "rule": (
            "This CI identity may qualify a fixed acoustic candidate only. It never changes shipping defaults "
            "and cannot substitute for target, HIL, real-device, soak, product-certification, or release evidence."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> None:
    tuning = canonical_tuning({
        "aec_mu": 0.24,
        "ns_floor": 0.12,
        "agc_target_dbfs": -20.0,
        "limiter_dbfs": -2.0,
    })
    assert tuning_id(tuning) == "4a6a408bf0e3"
    assert runtime_env(tuning)["AP_TUNING_AEC_MU"] == "0.24"
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
            env_output=root / "candidate.env",
            output=root / "identity.json",
        )
        result = create_identity(namespace)
        assert result["candidate_id"] == "4a6a408bf0e3"
        assert result["runtime_env"]["AP_TUNING_AEC_MU"] == "0.24"
        wrapper_text = namespace.wrapper.read_text(encoding="utf-8")
        assert "--aec-mu" in wrapper_text and "0.24" in wrapper_text
        assert "AP_ACOUSTIC_CANDIDATE_ID=4a6a408bf0e3" in namespace.env_output.read_text()
        bad = argparse.Namespace(**vars(namespace))
        bad.candidate_id = "000000000000"
        try:
            create_identity(bad)
        except ValueError as exc:
            assert "identity mismatch" in str(exc)
        else:
            raise AssertionError("mismatched candidate id must fail closed")
    try:
        canonical_tuning({
            "aec_mu": float("nan"), "ns_floor": 0.12,
            "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0,
        })
    except ValueError:
        pass
    else:
        raise AssertionError("non-finite tuning must fail closed")
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
    parser.add_argument("--env-output", type=Path)
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
