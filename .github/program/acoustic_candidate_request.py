#!/usr/bin/env python3
"""Validate and materialize the single non-shipping acoustic qualification request."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path
from typing import Any

import acoustic_candidate

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY = "non-shipping-acoustic-candidate-qualification-request"
_BINDING_KEYS = ("dataset_lock_sha256", "policy_sha256", "search_space_sha256")


def _require_sha40(value: Any, label: str) -> str:
    text = str(value)
    if not _SHA40.fullmatch(text):
        raise ValueError(f"{label} must be exactly 40 lowercase hex characters")
    return text


def _require_sha256(value: Any, label: str) -> str:
    text = str(value).removeprefix("sha256:")
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{label} must be exactly 64 lowercase hex characters")
    return text


def load_request(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("qualification request must be a JSON object")
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported qualification request schema")
    if raw.get("authority") != _AUTHORITY:
        raise ValueError("qualification request authority mismatch")

    source = _require_sha40(raw.get("candidate_source_revision"), "candidate_source_revision")
    candidate_id = str(raw.get("candidate_id", ""))
    if not re.fullmatch(r"[0-9a-f]{12}", candidate_id):
        raise ValueError("candidate_id must be exactly 12 lowercase hex characters")
    tuning = acoustic_candidate.canonical_tuning(raw.get("tuning", {}))
    actual_id = acoustic_candidate.tuning_id(tuning)
    if actual_id != candidate_id:
        raise ValueError(
            f"request candidate mismatch: declared {candidate_id}, canonical tuning yields {actual_id}"
        )

    provenance = raw.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")
    for key in ("audio_quality_run_id", "artifact_id"):
        value = provenance.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"provenance.{key} must be a positive integer")
    artifact_archive = _require_sha256(
        provenance.get("artifact_archive_sha256"), "provenance.artifact_archive_sha256"
    )
    iteration_result = _require_sha256(
        provenance.get("iteration_result_sha256"), "provenance.iteration_result_sha256"
    )

    bindings = raw.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(_BINDING_KEYS):
        raise ValueError("bindings must contain exactly dataset-lock, policy and search-space SHA256 values")
    normalized_bindings = {key: _require_sha256(bindings[key], f"bindings.{key}") for key in _BINDING_KEYS}

    boundary = raw.get("release_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("release_boundary must be an object")
    release = str(boundary.get("shipping_release", ""))
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", release):
        raise ValueError("shipping_release must be a SemVer tag")
    release_source = _require_sha40(boundary.get("shipping_release_source"), "shipping_release_source")
    if boundary.get("shipping_mutation_allowed") is not False:
        raise ValueError("qualification request must explicitly forbid shipping mutation")

    return {
        "schema_version": 1,
        "authority": _AUTHORITY,
        "candidate_source_revision": source,
        "candidate_id": candidate_id,
        "tuning": tuning,
        "provenance": {
            "audio_quality_run_id": provenance["audio_quality_run_id"],
            "artifact_id": provenance["artifact_id"],
            "artifact_archive_sha256": artifact_archive,
            "iteration_result_sha256": iteration_result,
        },
        "bindings": normalized_bindings,
        "release_boundary": {
            "shipping_release": release,
            "shipping_release_source": release_source,
            "shipping_mutation_allowed": False,
        },
        "rule": str(raw.get("rule", "")),
    }


def write_env(path: Path, request: dict[str, Any]) -> None:
    tuning = request["tuning"]
    lines = [
        f"AP_CANDIDATE_SOURCE_SHA={request['candidate_source_revision']}",
        f"AP_ACOUSTIC_CANDIDATE_ID={request['candidate_id']}",
        f"AP_CANDIDATE_PROVENANCE_SHA256={request['provenance']['iteration_result_sha256']}",
        f"AP_CANDIDATE_AQT_RUN_ID={request['provenance']['audio_quality_run_id']}",
        f"AP_CANDIDATE_AQT_ARTIFACT_ID={request['provenance']['artifact_id']}",
        f"AP_CANDIDATE_AQT_ARCHIVE_SHA256={request['provenance']['artifact_archive_sha256']}",
        f"AP_CANDIDATE_DATASET_LOCK_SHA256={request['bindings']['dataset_lock_sha256']}",
        f"AP_CANDIDATE_POLICY_SHA256={request['bindings']['policy_sha256']}",
        f"AP_CANDIDATE_SEARCH_SPACE_SHA256={request['bindings']['search_space_sha256']}",
        f"AP_TUNING_AEC_MU={repr(float(tuning['aec_mu']))}",
        f"AP_TUNING_NS_FLOOR={repr(float(tuning['ns_floor']))}",
        f"AP_TUNING_AGC_TARGET_DBFS={repr(float(tuning['agc_target_dbfs']))}",
        f"AP_TUNING_LIMITER_DBFS={repr(float(tuning['limiter_dbfs']))}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def self_test() -> None:
    valid = {
        "schema_version": 1,
        "authority": _AUTHORITY,
        "candidate_source_revision": "73ae803047d5e7a6b54cdf58b4a28331ab0c2163",
        "candidate_id": "4a6a408bf0e3",
        "tuning": {
            "aec_mu": 0.24,
            "ns_floor": 0.12,
            "agc_target_dbfs": -20.0,
            "limiter_dbfs": -2.0,
        },
        "provenance": {
            "audio_quality_run_id": 34796251702,
            "artifact_id": 10329589387,
            "artifact_archive_sha256": "7d1d4e221fc07b45cb7e92cfb2a6dcae1b88503a6c09b34ee167f9e570479eb0",
            "iteration_result_sha256": "1f00ec48b1467fd39b13044ced41f1016818c5a24a2894799d83eb5e7082b6f2",
        },
        "bindings": {
            "dataset_lock_sha256": "46b854fc54be3a4c454c4fd17a1f0b582f37f62ca1cd7ae9bc2128d4c96e40dc",
            "policy_sha256": "d2b56fb7fa826ac0b88859e58a93baeaa09c88d65f7f0661c2246901b83eba15",
            "search_space_sha256": "0b3006ec7d2fec1bb703f6f756e204a6f6fcf241f7a646557cb1a85c4d876d92",
        },
        "release_boundary": {
            "shipping_release": "v2.3.16",
            "shipping_release_source": "57e4c64adc1cf06819e46e24e275ecd746d5f17f",
            "shipping_mutation_allowed": False,
        },
        "rule": "non-shipping only",
    }
    with tempfile.TemporaryDirectory(prefix="ap-acoustic-request-") as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        request_path.write_text(json.dumps(valid), encoding="utf-8")
        request = load_request(request_path)
        assert request["candidate_id"] == "4a6a408bf0e3"
        env_path = root / "request.env"
        write_env(env_path, request)
        env = env_path.read_text(encoding="utf-8")
        assert "AP_CANDIDATE_SOURCE_SHA=73ae803047d5e7a6b54cdf58b4a28331ab0c2163" in env
        assert "AP_TUNING_AEC_MU=0.24" in env
        broken = dict(valid)
        broken["candidate_id"] = "000000000000"
        request_path.write_text(json.dumps(broken), encoding="utf-8")
        try:
            load_request(request_path)
        except ValueError as exc:
            assert "candidate mismatch" in str(exc)
        else:
            raise AssertionError("mismatched request candidate must fail closed")
    print("acoustic candidate qualification request self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--request", type=Path)
    parser.add_argument("--env-output", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.request is None:
        parser.error("--request is required")
    request = load_request(args.request)
    if args.env_output is not None:
        write_env(args.env_output, request)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(request, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
