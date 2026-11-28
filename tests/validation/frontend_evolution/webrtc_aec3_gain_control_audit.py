#!/usr/bin/env python3
"""Fail-closed source audit for the bounded AEC3 gain-controlled synthesis study.

This is a source-mechanism gate only. It does not patch, build, execute speech,
or establish that the intervention is isolated or scientifically admissible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ECHO_REMOVER_SHA256 = "c17b624242ab5f2bfce16a0324fae81d22e175f2e7761b150b5ed665974bb4da"
SUPPRESSION_FILTER_SHA256 = "e1a4d52f473f16e631229bffe05103efa135c2246f8ec51bb749ffde3b32ac00"
SUPPRESSION_FILTER_HEADER_SHA256 = "18af87236b8c188546a911222e66be8e6951edd07d14b329b2aacf1243e67d32"

GET_GAIN = "suppression_gain_.GetGain("
APPLY_GAIN = "suppression_filter_.ApplyGain("
CNG_COMPUTE = "cng_.Compute("
EXPECTED_APPLY_ARGS = (
    "comfort_noise", "high_band_comfort_noise", "G",
    "high_bands_gain", "Y_fft", "y",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def call_arguments(source: str, marker: str) -> tuple[str, ...]:
    require(source.count(marker) == 1, "expected exactly one " + marker)
    start = source.index(marker) + len(marker)
    end = source.find(");", start)
    require(end >= 0, "unterminated " + marker)
    body = source[start:end]
    # The pinned invocation is deliberately simple; reject nested call syntax
    # rather than pretending a comma split is a C++ parser.
    require("(" not in body and ")" not in body, "unexpected nested expression in " + marker)
    return tuple(part.strip() for part in body.replace("\n", " ").split(","))


def inspect_structure(echo_remover: str, suppression_filter: str) -> dict:
    require(echo_remover.count(CNG_COMPUTE) == 1, "CNG generation call must be unique")
    require(echo_remover.count(GET_GAIN) == 1, "gain estimator call must be unique")
    require(echo_remover.count(APPLY_GAIN) == 1, "gain application call must be unique")
    cng_at = echo_remover.index(CNG_COMPUTE)
    get_at = echo_remover.index(GET_GAIN)
    apply_at = echo_remover.index(APPLY_GAIN)
    require(cng_at < get_at < apply_at, "CNG -> gain estimate -> gain application order changed")
    args = call_arguments(echo_remover, APPLY_GAIN)
    require(args == EXPECTED_APPLY_ARGS, "ApplyGain ordered argument contract changed")
    require("noise_gain[i] = 1.f - suppression_gain[i] * suppression_gain[i];" in suppression_filter,
            "low-band CNG mixing coefficient no longer derives from suppression gain")
    require("0.4f * std::sqrt(1.f - high_bands_gain * high_bands_gain)" in suppression_filter,
            "high-band CNG mixing coefficient no longer derives from high-band gain")
    require("e_output_old_" in suppression_filter and
            "std::copy(e_extended.begin() + kFftLengthBy2" in suppression_filter,
            "overlap-add output history contract changed")
    return {
        "status": "PASS_SOURCE_MECHANISM_AUDIT_ONLY",
        "call_order": ["CNG_COMPUTE", "GET_GAIN", "APPLY_GAIN"],
        "apply_gain_arguments": list(args),
        "low_band_cng_mix_depends_on_gain": True,
        "high_band_cng_mix_depends_on_gain": True,
        "overlap_add_history_is_mutated": True,
        "cng_inputs_are_materialized_before_gain_estimation": True,
        "intervention_scope": "JOINT_GAIN_CONTROLLED_SUPPRESSION_AND_CNG_SYNTHESIS",
        "not_proven": [
            "byte-identical CNG input arrays across two actual runs",
            "unchanged upstream estimator state across two actual runs",
            "isolated source transformation",
            "binary/build equivalence",
            "acoustic effect or independent confirmation"
        ],
        "speech_execution_authorized": False,
        "promotion_allowed": False,
    }


def audit_files(echo_path: Path, filter_path: Path, header_path: Path) -> dict:
    sources = {
        "echo_remover.cc": (echo_path, ECHO_REMOVER_SHA256),
        "suppression_filter.cc": (filter_path, SUPPRESSION_FILTER_SHA256),
        "suppression_filter.h": (header_path, SUPPRESSION_FILTER_HEADER_SHA256),
    }
    actual = {}
    for name, (path, expected) in sources.items():
        data = path.read_bytes()
        digest = sha256(data)
        require(digest == expected, name + " pinned source SHA-256 mismatch")
        actual[name] = digest
    result = inspect_structure(echo_path.read_text(encoding="utf-8"),
                               filter_path.read_text(encoding="utf-8"))
    result["source_sha256"] = actual
    result["source_bundle_sha256"] = "9e6dcc80317f689779d05da212143cf2d5287f0c30868b469a9ae8c9b1fd6d48"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--echo-remover", type=Path, required=True)
    parser.add_argument("--suppression-filter", type=Path, required=True)
    parser.add_argument("--suppression-filter-header", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_files(args.echo_remover, args.suppression_filter,
                         args.suppression_filter_header)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
