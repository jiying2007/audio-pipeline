#!/usr/bin/env python3
"""Collect and qualify conservative/effect-first AArch32 delivery profiles.

This is build/resource evidence only. It deliberately leaves silicon timing,
RSS, whole-thread stack, thermal and power as calibration-required instead of
manufacturing target claims from hosted/QEMU execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ALLOCATOR = re.compile(r"(?:^|\s)(malloc|calloc|realloc|free)$")


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def section_sizes(size_tool: str, elf: Path) -> dict[str, int]:
    text = subprocess.check_output(
        [size_tool, "-A", str(elf)], text=True, stderr=subprocess.STDOUT
    )
    sections: dict[str, int] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2 or not fields[0].startswith("."):
            continue
        try:
            sections[fields[0]] = int(fields[1], 0)
        except ValueError:
            continue
    if ".text" not in sections:
        raise ValueError(f"missing .text section in {elf}")
    return sections


def unresolved_allocator_refs(nm_tool: str, libraries: list[Path]) -> list[str]:
    output = subprocess.check_output(
        [nm_tool, "-u", *map(str, libraries)],
        text=True,
        stderr=subprocess.STDOUT,
    )
    refs: set[str] = set()
    for line in output.splitlines():
        match = ALLOCATOR.search(line.strip())
        if match:
            refs.add(match.group(1))
    return sorted(refs)


def collect(args: argparse.Namespace) -> dict:
    first = load_json(args.probe)
    load_json(args.probe_repeat)  # Validate both outputs before comparing raw bytes.
    deterministic = args.probe.read_bytes() == args.probe_repeat.read_bytes()
    sections = section_sizes(args.size_tool, args.elf)
    rodata = sum(
        size for name, size in sections.items()
        if name == ".rodata" or name.startswith(".rodata.")
    )
    text_bytes = sections[".text"]
    allocator_refs = unresolved_allocator_refs(args.nm_tool, args.library)
    elf_bytes = args.elf.stat().st_size
    result = {
        "schema_version": 2,
        "profile_id": args.profile_id,
        "preset": args.preset,
        "probe": first,
        "qemu_probe_repeat_identical": deterministic,
        "qemu_probe_repeat_sha256": hashlib.sha256(
            args.probe_repeat.read_bytes()
        ).hexdigest(),
        "rom": {
            "text_bytes": text_bytes,
            "rodata_bytes": rodata,
            "text_rodata_bytes": text_bytes + rodata,
            "linked_elf_file_bytes": elf_bytes,
        },
        "direct_heap_allocator_symbol_references": allocator_refs,
        "allocator_scan_scope": [str(path) for path in args.library],
        "timing_authority": "none-target",
    }
    return result


def validate_profile(
    profile_id: str,
    profile_spec: dict,
    measured: dict,
    source_revision: str,
) -> list[str]:
    errors: list[str] = []
    if measured.get("schema_version") != 2:
        errors.append("measured schema_version must be 2")
    if measured.get("profile_id") != profile_id:
        errors.append("profile_id mismatch")
    if measured.get("preset") != profile_spec["preset"]:
        errors.append("preset mismatch")
    probe = measured.get("probe", {})
    expected = profile_spec["expected_build"]
    for key, expected_value in expected.items():
        if probe.get(key) != expected_value:
            errors.append(
                f"expected_build.{key}: {probe.get(key)!r} != {expected_value!r}"
            )

    if probe.get("source_revision") != source_revision:
        errors.append(
            f"source_revision mismatch: {probe.get('source_revision')!r} != {source_revision!r}"
        )
    digest = probe.get("config_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        errors.append("invalid config_digest")
    if "arm" not in str(probe.get("target_triple", "")).lower():
        errors.append("target_triple is not Arm/AArch32")

    ceilings = profile_spec["ceilings"]
    sizes = [probe.get("pipeline_state_bytes"), probe.get("runtime_state_bytes")]
    if any(type(size) is not int or size <= 0 for size in sizes):
        errors.append("state sizes must be positive integers")
    elif sum(sizes) > ceilings["caller_owned_state_bytes"]:
        errors.append("caller_owned_state_bytes ceiling exceeded")
    if int(probe.get("pipeline_state_bytes", 1 << 60)) > ceilings["pipeline_state_bytes"]:
        errors.append("pipeline_state_bytes ceiling exceeded")
    if int(probe.get("runtime_state_bytes", 1 << 60)) > ceilings["runtime_state_bytes"]:
        errors.append("runtime_state_bytes ceiling exceeded")
    if int(measured.get("rom", {}).get("text_rodata_bytes", 1 << 60)) > ceilings[
        "rom_text_rodata_bytes"
    ]:
        errors.append("rom_text_rodata_bytes ceiling exceeded")
    if measured.get("direct_heap_allocator_symbol_references") != []:
        errors.append("direct heap allocator symbol reference present")
    if measured.get("qemu_probe_repeat_identical") is not True:
        errors.append("QEMU resource-probe stdout bytes differ")
    if int(probe.get("algorithmic_latency_frames", -1)) < 0:
        errors.append("invalid algorithmic_latency_frames")
    return errors


def qualify(spec: dict, metrics: dict[str, dict], source_revision: str) -> dict:
    if spec.get("schema_version") != 3:
        raise ValueError("resource profile spec schema_version must be 3")
    expected_profiles = set(spec["profiles"])
    if set(metrics) != expected_profiles:
        raise ValueError(
            f"profile set mismatch: {sorted(metrics)} != {sorted(expected_profiles)}"
        )

    profiles: dict[str, dict] = {}
    all_errors: list[str] = []
    for profile_id in sorted(expected_profiles):
        measured = metrics[profile_id]
        errors = validate_profile(
            profile_id, spec["profiles"][profile_id], measured, source_revision
        )
        all_errors.extend(f"{profile_id}: {item}" for item in errors)
        profiles[profile_id] = {
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "authority": spec["profiles"][profile_id]["authority"],
            "intent": spec["profiles"][profile_id]["intent"],
            "preset": spec["profiles"][profile_id]["preset"],
            "measured": measured,
        }

    target_calibration = {
        metric: {
            "status": "CALIBRATION_REQUIRED",
            "value": None,
            "authority": "shipping-silicon-only",
        }
        for metric in spec["silicon_calibration_required"]
    }
    return {
        "schema_version": 2,
        "qualification_id": "ssc305-delivery-profiles-v2",
        "source_revision": source_revision,
        "status": "PASS" if not all_errors else "FAIL",
        "errors": all_errors,
        "authority": spec["authority"],
        "profiles": profiles,
        "qualified_now": spec["qualify_now"],
        "silicon_calibration": target_calibration,
        "rules": spec["rules"],
        "s004_candidate_authority": False,
        "product_certification_authority": False,
    }


def self_test() -> None:
    spec = {
        "schema_version": 3,
        "authority": "build-only",
        "profiles": {
            "conservative": {
                "authority": "shipping-default-build-contract",
                "preset": "low",
                "intent": "stable",
                "expected_build": {
                    "simd_backend": "NEON",
                    "max_io_rate_hz": 16000,
                },
                "ceilings": {
                    "pipeline_state_bytes": 80000,
                    "runtime_state_bytes": 65536,
                    "rom_text_rodata_bytes": 40960,
                    "caller_owned_state_bytes": 65000,
                },
            },
            "effect-first": {
                "authority": "research-only-resource-envelope",
                "preset": "full",
                "intent": "effect",
                "expected_build": {
                    "simd_backend": "NEON",
                    "max_io_rate_hz": 48000,
                },
                "ceilings": {
                    "pipeline_state_bytes": 80000,
                    "runtime_state_bytes": 65536,
                    "rom_text_rodata_bytes": 40960,
                    "caller_owned_state_bytes": 65000,
                },
            },
        },
        "qualify_now": ["pipeline_state_bytes"],
        "silicon_calibration_required": ["frame_p99_ms"],
        "rules": ["no target timing from QEMU"],
    }

    def metric(profile: str, preset: str, rate: int) -> dict:
        return {
            "schema_version": 2,
            "profile_id": profile,
            "preset": preset,
            "probe": {
                "simd_backend": "NEON",
                "max_io_rate_hz": rate,
                "source_revision": "abc",
                "config_digest": "a" * 64,
                "target_triple": "arm-linux-gnueabihf",
                "pipeline_state_bytes": 40000,
                "runtime_state_bytes": 20000,
                "algorithmic_latency_frames": 1,
            },
            "qemu_probe_repeat_identical": True,
            "rom": {"text_rodata_bytes": 30000},
            "direct_heap_allocator_symbol_references": [],
        }

    result = qualify(
        spec,
        {
            "conservative": metric("conservative", "low", 16000),
            "effect-first": metric("effect-first", "full", 48000),
        },
        "abc",
    )
    assert result["status"] == "PASS"
    assert result["silicon_calibration"]["frame_p99_ms"]["value"] is None
    assert result["s004_candidate_authority"] is False

    bad = metric("conservative", "low", 16000)
    bad["direct_heap_allocator_symbol_references"] = ["malloc"]
    errors = validate_profile(
        "conservative", spec["profiles"]["conservative"], bad, "abc"
    )
    assert any("allocator" in item for item in errors)

    revision_bad = metric("conservative", "low", 16000)
    revision_bad["probe"]["source_revision"] = "unknown"
    errors = validate_profile(
        "conservative", spec["profiles"]["conservative"], revision_bad, "abc"
    )
    assert any("source_revision mismatch" in item for item in errors)
    import copy
    for key, value, fragment in (
        ("schema_version", 1, "schema_version"),
        ("qemu_probe_repeat_identical", False, "stdout"),
    ):
        broken = metric("conservative", "low", 16000)
        broken[key] = value
        assert any(fragment in error for error in validate_profile(
            "conservative", spec["profiles"]["conservative"], broken, "abc"))
    over_budget = metric("conservative", "low", 16000)
    over_budget["probe"]["pipeline_state_bytes"] = 50001
    assert any("caller_owned_state_bytes" in error for error in validate_profile(
        "conservative", spec["profiles"]["conservative"], over_budget, "abc"))
    # Individual public ceilings pass, aggregate SKU budget must still fail.
    for value in (0, -1, True):
        broken = metric("conservative", "low", 16000)
        broken["probe"]["pipeline_state_bytes"] = value
        assert any("positive integers" in error for error in validate_profile(
            "conservative", spec["profiles"]["conservative"], broken, "abc"))
    old_spec = copy.deepcopy(spec)
    old_spec["schema_version"] = 2
    try:
        qualify(old_spec, {}, "abc")
    except ValueError:
        pass
    else:
        raise AssertionError("old spec must not be silently accepted")
    print("resource profile qualification self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    collect_parser = sub.add_parser("collect")
    collect_parser.add_argument("--profile-id", required=True)
    collect_parser.add_argument("--preset", required=True)
    collect_parser.add_argument("--probe", type=Path, required=True)
    collect_parser.add_argument("--probe-repeat", type=Path, required=True)
    collect_parser.add_argument("--elf", type=Path, required=True)
    collect_parser.add_argument("--library", type=Path, action="append", required=True)
    collect_parser.add_argument("--size-tool", default="arm-linux-gnueabihf-size")
    collect_parser.add_argument("--nm-tool", default="arm-linux-gnueabihf-nm")
    collect_parser.add_argument("--output", type=Path, required=True)

    qualify_parser = sub.add_parser("qualify")
    qualify_parser.add_argument("--spec", type=Path, required=True)
    qualify_parser.add_argument("--metrics", action="append", required=True)
    qualify_parser.add_argument("--source-revision", required=True)
    qualify_parser.add_argument("--output", type=Path, required=True)

    sub.add_parser("self-test")

    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
        return 0

    if args.command == "collect":
        value = collect(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "profile_id": value["profile_id"],
            "pipeline_state_bytes": value["probe"]["pipeline_state_bytes"],
            "runtime_state_bytes": value["probe"]["runtime_state_bytes"],
            "rom_text_rodata_bytes": value["rom"]["text_rodata_bytes"],
            "heap_allocator_refs": value["direct_heap_allocator_symbol_references"],
            "qemu_probe_repeat_identical": value["qemu_probe_repeat_identical"],
        }, sort_keys=True))
        return 0

    spec = load_json(args.spec)
    metrics: dict[str, dict] = {}
    for item in args.metrics:
        if "=" not in item:
            parser.error("--metrics requires PROFILE=PATH")
        profile_id, raw_path = item.split("=", 1)
        if profile_id in metrics:
            parser.error(f"duplicate metrics profile: {profile_id}")
        metrics[profile_id] = load_json(Path(raw_path))
    result = qualify(spec, metrics, args.source_revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": result["status"],
        "profiles": {
            key: value["status"] for key, value in result["profiles"].items()
        },
        "target_calibration_required": len(result["silicon_calibration"]),
    }, sort_keys=True))
    return 0 if result["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
