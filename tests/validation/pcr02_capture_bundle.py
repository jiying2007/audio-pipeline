#!/usr/bin/env python3
"""PCR02 real-capture bundle v1: create, seal, validate, replay and diagnose.

Repository-internal measurement tooling only. It does not change APD v1 or grant
HIL, Extended Real, Product Qualification, or Product Certification authority.
"""
from __future__ import annotations

import argparse
import array
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
TAG = "v2.3.16"
SOURCE = "57e4c64adc1cf06819e46e24e275ecd746d5f17f"
VERSION = "2.3.16"
ZERO = "0" * 64
REQUIRED_ROLES = {
    "mic_raw", "render_reference", "pipeline_output", "frame_timeline", "telemetry",
}
OPTIONAL_ROLES = {
    "aec_output", "bf_output", "ns_output", "agc_output", "frame_metrics",
    "system_metrics", "app_log", "dmesg", "apd", "config_snapshot",
}
MONO_PCM = {
    "render_reference", "pipeline_output", "aec_output", "bf_output",
    "ns_output", "agc_output",
}
REQUIRED_SIGNALS = {
    "timestamp_ns", "left_motor_rpm", "right_motor_rpm", "left_foc_iq",
    "right_foc_iq", "left_pwm", "right_pwm", "servo_state", "motion_state",
}
H40 = re.compile(r"^[0-9a-f]{40}$")
H64 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def rooted_path(root: Path, value: str) -> Path:
    if not safe_relative(value):
        raise ValueError(f"unsafe relative path: {value!r}")
    root = root.resolve()
    target = (root / value).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes bundle root: {value!r}")
    return target


def bundle_digest(value: dict) -> str:
    normalized = copy.deepcopy(value)
    normalized.pop("bundle_digest_sha256", None)
    payload = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: bad JSONL line {line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}: line {line_number} is not an object")
        rows.append(row)
    return rows


def read_plan_slot(plan_path: Path, slot_id: str) -> tuple[dict, dict]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or plan.get("product") != "PCR02":
        raise ValueError("capture plan identity mismatch")
    matches = [slot for slot in plan.get("slots", []) if slot.get("slot_id") == slot_id]
    if len(matches) != 1:
        raise ValueError(f"expected one capture-plan slot {slot_id!r}")
    slot = matches[0]
    scene = {key: value for key, value in slot.items() if key not in {"slot_id", "track"}}
    return slot, scene


def check_structure(value: dict, *, allow_unsealed: bool = False) -> None:
    required_keys = {
        "schema_version", "authority", "sealed", "capture_id", "capture_purpose",
        "product", "slot_id", "track", "created_utc", "release_authority",
        "software", "hardware", "scene", "context", "clock", "duration_seconds",
        "files", "telemetry_signals", "evidence_claims", "bundle_digest_sha256",
    }
    if set(value) != required_keys:
        raise ValueError(
            "manifest keys drifted: "
            f"missing={sorted(required_keys - set(value))} "
            f"unexpected={sorted(set(value) - required_keys)}"
        )
    if (
        value["schema_version"] != 1
        or value["authority"] != "pcr02-real-capture-bundle"
        or value["product"] != "PCR02"
    ):
        raise ValueError("bundle identity mismatch")
    if not isinstance(value["sealed"], bool):
        raise ValueError("sealed must be boolean")
    if not value["sealed"] and not allow_unsealed:
        raise ValueError("unsealed working set is not evidence")
    if not isinstance(value["capture_id"], str) or not value["capture_id"]:
        raise ValueError("capture_id is required")
    if value["capture_purpose"] not in {"development", "qualification-candidate"}:
        raise ValueError("capture purpose invalid")
    if value["track"] not in {"bf-geometry", "self-noise", "aec-product-path"}:
        raise ValueError("track invalid")
    if value["release_authority"] != {"tag": TAG, "source_sha": SOURCE}:
        raise ValueError("immutable release authority drifted")

    software = value["software"]
    if set(software) != {"git_sha", "version", "binary_sha256", "build_info"}:
        raise ValueError("software identity keys invalid")
    if H40.fullmatch(str(software["git_sha"])) is None:
        raise ValueError("software git_sha invalid")
    if H64.fullmatch(str(software["binary_sha256"])) is None:
        raise ValueError("software binary_sha256 invalid")
    build_info = software["build_info"]
    if set(build_info) != {"aec_backend", "ns_estimator", "simd_backend", "resampler_mode"}:
        raise ValueError("build_info keys invalid")
    if any(not str(item) for item in build_info.values()):
        raise ValueError("build_info values must be non-empty")
    if value["capture_purpose"] == "qualification-candidate" and (
        software["git_sha"] != SOURCE or software["version"] != VERSION
    ):
        raise ValueError("qualification candidate must execute exact v2.3.16 source")

    hardware = value["hardware"]
    expected_hardware = {
        "soc": "SSC305",
        "mic_channels": 2,
        "mic_spacing_mm": 35.0,
        "sample_rate_hz": 16000,
        "sample_format": "s16le",
        "frame_samples": 160,
    }
    if set(hardware) != set(expected_hardware) | {"board_revision", "device_id"}:
        raise ValueError("PCR02 hardware identity keys invalid")
    if any(hardware.get(key) != expected for key, expected in expected_hardware.items()):
        raise ValueError("PCR02 hardware geometry drifted")
    if not str(hardware["board_revision"]) or not str(hardware["device_id"]):
        raise ValueError("PCR02 board/device identity missing")

    if not isinstance(value["scene"], dict):
        raise ValueError("scene must be an object")
    context = value["context"]
    context_keys = {
        "room_id", "ambient_condition", "speaker_volume_percent",
        "battery_mv", "charging_state",
    }
    if set(context) != context_keys:
        raise ValueError("capture context keys invalid")
    if not str(context["room_id"]) or not str(context["ambient_condition"]):
        raise ValueError("capture room/ambient context missing")
    if not isinstance(context["speaker_volume_percent"], int) or not 0 <= context["speaker_volume_percent"] <= 100:
        raise ValueError("speaker_volume_percent must be 0..100")
    if not isinstance(context["battery_mv"], int) or context["battery_mv"] <= 0:
        raise ValueError("battery_mv must be positive")
    if not str(context["charging_state"]):
        raise ValueError("charging_state is required")

    if value["clock"] != {"domain": "monotonic", "timestamp_unit": "ns"}:
        raise ValueError("clock must be monotonic nanoseconds")
    if float(value["duration_seconds"]) < 0:
        raise ValueError("duration_seconds must be non-negative")

    descriptors = value["files"]
    missing = REQUIRED_ROLES - set(descriptors)
    unknown = set(descriptors) - REQUIRED_ROLES - OPTIONAL_ROLES
    if missing or unknown:
        raise ValueError(
            f"file roles invalid: missing={sorted(missing)} unknown={sorted(unknown)}"
        )
    paths: set[str] = set()
    for role, descriptor in descriptors.items():
        if set(descriptor) != {"path", "sha256", "size_bytes"}:
            raise ValueError(f"file descriptor keys invalid: {role}")
        path = str(descriptor["path"])
        if not safe_relative(path) or path in paths:
            raise ValueError(f"file path invalid/duplicated: {role}")
        paths.add(path)
        if H64.fullmatch(str(descriptor["sha256"])) is None:
            raise ValueError(f"file SHA-256 invalid: {role}")
        if not isinstance(descriptor["size_bytes"], int) or descriptor["size_bytes"] < 0:
            raise ValueError(f"file size invalid: {role}")

    signals = value["telemetry_signals"]
    if not isinstance(signals, list) or len(signals) != len(set(signals)):
        raise ValueError("telemetry_signals must be a unique list")
    missing_signals = REQUIRED_SIGNALS - set(signals)
    if missing_signals:
        raise ValueError(f"telemetry signal contract incomplete: {sorted(missing_signals)}")

    claims = value["evidence_claims"]
    claim_keys = {
        "real_capture", "hil_pass", "extended_real_pass",
        "product_qualification_pass", "product_certification_pass",
    }
    if set(claims) != claim_keys or not isinstance(claims["real_capture"], bool):
        raise ValueError("evidence claim keys invalid")
    if any(claims[key] is not False for key in claim_keys - {"real_capture"}):
        raise ValueError("capture bundle cannot claim HIL/Extended Real/PQ/Certification PASS")
    if value["sealed"] != claims["real_capture"]:
        raise ValueError("sealed/real_capture state mismatch")
    if H64.fullmatch(str(value["bundle_digest_sha256"])) is None:
        raise ValueError("bundle digest format invalid")


def check_plan(value: dict, plan_path: Path) -> None:
    slot, scene = read_plan_slot(plan_path, value["slot_id"])
    if value["track"] != slot["track"] or value["scene"] != scene:
        raise ValueError("manifest scene does not exactly match capture-plan slot")


def bind_files(value: dict, root: Path, *, verify_hashes: bool = True) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for role, descriptor in value["files"].items():
        path = rooted_path(root, descriptor["path"])
        if not path.is_file():
            raise FileNotFoundError(path)
        if verify_hashes:
            if path.stat().st_size != descriptor["size_bytes"]:
                raise ValueError(f"file size mismatch: {role}")
            actual = sha256(path)
            if actual != descriptor["sha256"]:
                raise ValueError(f"file SHA-256 mismatch: {role}")
        result[role] = path
    return result


def check_payload(
    value: dict,
    paths: dict[str, Path],
    *,
    verify_declared_duration: bool = True,
) -> dict:
    hardware = value["hardware"]
    mic_bytes = paths["mic_raw"].stat().st_size
    if mic_bytes <= 0 or mic_bytes % (2 * hardware["mic_channels"]):
        raise ValueError("mic_raw must be non-empty interleaved s16le stereo")
    samples = mic_bytes // (2 * hardware["mic_channels"])

    for role in MONO_PCM & set(paths):
        size = paths[role].stat().st_size
        if size % 2 or size // 2 != samples:
            raise ValueError(f"PCM sample count mismatch: {role}")
    if samples % hardware["frame_samples"]:
        raise ValueError("audio is not an integer number of 10 ms frames")

    frame_count = samples // hardware["frame_samples"]
    timeline = read_jsonl(paths["frame_timeline"])
    if len(timeline) != frame_count:
        raise ValueError("frame timeline row count does not match audio")
    previous_sequence = previous_capture = previous_render = None
    for index, row in enumerate(timeline):
        required = {"index", "sequence", "capture_timestamp_ns", "render_timestamp_ns"}
        if not required <= set(row) or int(row["index"]) != index:
            raise ValueError(f"frame timeline row {index} invalid")
        sequence = int(row["sequence"])
        capture_ns = int(row["capture_timestamp_ns"])
        render_ns = int(row["render_timestamp_ns"])
        if previous_sequence is not None and sequence != previous_sequence + 1:
            raise ValueError("frame sequence discontinuity")
        if previous_capture is not None and capture_ns <= previous_capture:
            raise ValueError("capture timestamp not strictly monotonic")
        if previous_render is not None and render_ns < previous_render:
            raise ValueError("render timestamp regressed")
        previous_sequence, previous_capture, previous_render = sequence, capture_ns, render_ns

    telemetry = read_jsonl(paths["telemetry"])
    if not telemetry:
        raise ValueError("telemetry is empty")
    declared_signals = set(value["telemetry_signals"])
    previous_timestamp = None
    for index, row in enumerate(telemetry):
        if not declared_signals <= set(row):
            raise ValueError(f"telemetry row {index} missing declared signals")
        timestamp = int(row["timestamp_ns"])
        if previous_timestamp is not None and timestamp < previous_timestamp:
            raise ValueError("telemetry timestamp regressed")
        previous_timestamp = timestamp

    capture_start = int(timeline[0]["capture_timestamp_ns"])
    capture_end = int(timeline[-1]["capture_timestamp_ns"])
    if (
        int(telemetry[0]["timestamp_ns"]) > capture_start
        or int(telemetry[-1]["timestamp_ns"]) < capture_end
    ):
        raise ValueError("telemetry does not cover the capture interval")

    duration = samples / hardware["sample_rate_hz"]
    if verify_declared_duration and abs(float(value["duration_seconds"]) - duration) > 1 / hardware["sample_rate_hz"]:
        raise ValueError("manifest duration does not match PCM")
    return {
        "audio_samples": samples,
        "frame_count": frame_count,
        "telemetry_rows": len(telemetry),
        "duration_seconds": duration,
    }


def validate(manifest: Path, root: Path, plan: Path) -> dict:
    value = json.loads(manifest.read_text(encoding="utf-8"))
    check_structure(value)
    check_plan(value, plan)
    statistics = check_payload(value, bind_files(value, root))
    if value["bundle_digest_sha256"] != bundle_digest(value):
        raise ValueError("bundle digest mismatch")
    return {
        "result": "PASS",
        "capture_id": value["capture_id"],
        "slot_id": value["slot_id"],
        "track": value["track"],
        "capture_purpose": value["capture_purpose"],
        "bundle_digest_sha256": value["bundle_digest_sha256"],
        "file_roles": sorted(value["files"]),
        "evidence_claims": value["evidence_claims"],
        **statistics,
    }


def file_descriptor(path: str) -> dict:
    return {"path": path, "sha256": ZERO, "size_bytes": 0}


def new_capture(args) -> dict:
    slot, scene = read_plan_slot(args.plan, args.slot_id)
    if args.purpose == "qualification-candidate" and (
        args.source_sha != SOURCE or args.version != VERSION
    ):
        raise ValueError("qualification candidate requires exact v2.3.16 source/version")
    if H40.fullmatch(args.source_sha) is None or H64.fullmatch(args.binary_sha256) is None:
        raise ValueError("source/binary identity format invalid")

    files = {
        "mic_raw": file_descriptor("audio/mic_raw.pcm"),
        "render_reference": file_descriptor("audio/render_reference.pcm"),
        "pipeline_output": file_descriptor("audio/pipeline_output.pcm"),
        "frame_timeline": file_descriptor("frame_timeline.jsonl"),
        "telemetry": file_descriptor("telemetry.jsonl"),
    }
    for item in args.optional_file:
        role, separator, path = item.partition("=")
        if not separator or role not in OPTIONAL_ROLES or role in files:
            raise ValueError(f"bad --optional-file {item!r}")
        files[role] = file_descriptor(path)

    value = {
        "schema_version": 1,
        "authority": "pcr02-real-capture-bundle",
        "sealed": False,
        "capture_id": args.capture_id,
        "capture_purpose": args.purpose,
        "product": "PCR02",
        "slot_id": args.slot_id,
        "track": slot["track"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "release_authority": {"tag": TAG, "source_sha": SOURCE},
        "software": {
            "git_sha": args.source_sha,
            "version": args.version,
            "binary_sha256": args.binary_sha256,
            "build_info": {
                "aec_backend": args.aec_backend,
                "ns_estimator": args.ns_estimator,
                "simd_backend": args.simd_backend,
                "resampler_mode": args.resampler_mode,
            },
        },
        "hardware": {
            "soc": "SSC305",
            "board_revision": args.board_revision,
            "device_id": args.device_id,
            "mic_channels": 2,
            "mic_spacing_mm": 35.0,
            "sample_rate_hz": 16000,
            "sample_format": "s16le",
            "frame_samples": 160,
        },
        "scene": scene,
        "context": {
            "room_id": args.room_id,
            "ambient_condition": args.ambient_condition,
            "speaker_volume_percent": args.speaker_volume_percent,
            "battery_mv": args.battery_mv,
            "charging_state": args.charging_state,
        },
        "clock": {"domain": "monotonic", "timestamp_unit": "ns"},
        "duration_seconds": 0.0,
        "files": files,
        "telemetry_signals": sorted(REQUIRED_SIGNALS),
        "evidence_claims": {
            "real_capture": False,
            "hil_pass": False,
            "extended_real_pass": False,
            "product_qualification_pass": False,
            "product_certification_pass": False,
        },
        "bundle_digest_sha256": ZERO,
    }
    check_structure(value, allow_unsealed=True)
    check_plan(value, args.plan)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for descriptor in files.values():
        rooted_path(args.output_dir, descriptor["path"]).parent.mkdir(parents=True, exist_ok=True)
    manifest = args.output_dir / "manifest.json"
    manifest.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "result": "INITIALIZED",
        "manifest": str(manifest),
        "required_paths": {role: files[role]["path"] for role in sorted(REQUIRED_ROLES)},
    }


def seal(manifest: Path, root: Path, plan: Path) -> dict:
    value = json.loads(manifest.read_text(encoding="utf-8"))
    check_structure(value, allow_unsealed=True)
    check_plan(value, plan)
    if value["sealed"]:
        raise ValueError("sealed evidence is immutable; create a new capture")

    paths = bind_files(value, root, verify_hashes=False)
    for role, path in paths.items():
        value["files"][role]["sha256"] = sha256(path)
        value["files"][role]["size_bytes"] = path.stat().st_size
    statistics = check_payload(value, paths, verify_declared_duration=False)
    value["duration_seconds"] = statistics["duration_seconds"]
    value["sealed"] = True
    value["evidence_claims"]["real_capture"] = True
    value["bundle_digest_sha256"] = bundle_digest(value)

    temporary = manifest.with_suffix(manifest.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(manifest)
    return validate(manifest, root, plan)


def compare_s16(expected: bytes, actual: bytes) -> dict:
    if len(expected) != len(actual):
        return {
            "bit_exact": False,
            "expected_bytes": len(expected),
            "actual_bytes": len(actual),
            "mae_lsb": None,
            "max_abs_lsb": None,
        }
    if expected == actual:
        return {
            "bit_exact": True,
            "expected_bytes": len(expected),
            "actual_bytes": len(actual),
            "mae_lsb": 0.0,
            "max_abs_lsb": 0,
        }
    left = array.array("h")
    right = array.array("h")
    left.frombytes(expected)
    right.frombytes(actual)
    if sys.byteorder != "little":
        left.byteswap()
        right.byteswap()
    differences = [abs(int(a) - int(b)) for a, b in zip(left, right)]
    return {
        "bit_exact": False,
        "expected_bytes": len(expected),
        "actual_bytes": len(actual),
        "mae_lsb": sum(differences) / len(differences),
        "max_abs_lsb": max(differences),
    }


def replay(args) -> dict:
    summary = validate(args.manifest, args.root, args.plan)
    value = json.loads(args.manifest.read_text(encoding="utf-8"))
    paths = bind_files(value, args.root)
    with tempfile.TemporaryDirectory(prefix="pcr02-replay-") as directory:
        generated = Path(directory) / "output.pcm"
        subprocess.run(
            [
                str(args.processor), "--sample-rate", "16000", "--mic-channels", "2",
                str(paths["mic_raw"]), str(paths["render_reference"]), str(generated),
            ],
            check=True,
        )
        actual = generated.read_bytes()
    if args.output_pcm:
        args.output_pcm.parent.mkdir(parents=True, exist_ok=True)
        args.output_pcm.write_bytes(actual)
    return {
        "result": "PASS",
        "capture_id": summary["capture_id"],
        "bundle_digest_sha256": summary["bundle_digest_sha256"],
        "comparison": compare_s16(paths["pipeline_output"].read_bytes(), actual),
        "causal_proof": False,
        "note": (
            "Replay is A/B evidence unless the complete effective runtime "
            "configuration is independently bound."
        ),
    }


def diagnose(args) -> dict:
    summary = validate(args.manifest, args.root, args.plan)
    value = json.loads(args.manifest.read_text(encoding="utf-8"))
    paths = bind_files(value, args.root)
    if "apd" not in paths:
        raise ValueError("diagnose requires optional file role apd")

    triage_dir = args.output_dir / "triage"
    diagnosis_dir = args.output_dir / "diagnosis"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "tests/diagnostics/aptriage.py"),
        str(paths["apd"]),
        "--processor", str(args.processor.resolve()),
        "--processor-build-info", str(args.processor_build_info.resolve()),
        "--output-dir", str(triage_dir.resolve()),
    ]
    if args.require_bit_exact:
        command.append("--require-bit-exact")
    if args.stage_counterfactuals:
        command.append("--stage-counterfactuals")
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/diagnostics/apdiagnose.py"),
            str((triage_dir / "triage.json").resolve()),
            "--output-dir", str(diagnosis_dir.resolve()),
        ],
        cwd=ROOT,
        check=True,
    )
    result = {
        "result": "PASS",
        "capture_id": summary["capture_id"],
        "bundle_digest_sha256": summary["bundle_digest_sha256"],
        "apd_sha256": value["files"]["apd"]["sha256"],
        "triage_sha256": sha256(triage_dir / "triage.json"),
        "diagnosis_sha256": sha256(diagnosis_dir / "diagnosis.json"),
        "causal_proof": False,
    }
    (args.output_dir / "capture-analysis.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def write_self_test_payload(root: Path) -> None:
    samples = 320
    (root / "audio/mic_raw.pcm").write_bytes(b"\0" * samples * 4)
    (root / "audio/render_reference.pcm").write_bytes(b"\0" * samples * 2)
    (root / "audio/pipeline_output.pcm").write_bytes(b"\0" * samples * 2)
    timeline = [
        {
            "index": 0,
            "sequence": 100,
            "capture_timestamp_ns": 1_000_000_000,
            "render_timestamp_ns": 999_000_000,
        },
        {
            "index": 1,
            "sequence": 101,
            "capture_timestamp_ns": 1_010_000_000,
            "render_timestamp_ns": 1_009_000_000,
        },
    ]
    (root / "frame_timeline.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in timeline), encoding="utf-8"
    )
    telemetry = []
    for timestamp in (999_000_000, 1_011_000_000):
        row = {key: 0 for key in REQUIRED_SIGNALS}
        row.update(timestamp_ns=timestamp, servo_state="idle", motion_state="idle")
        telemetry.append(row)
    (root / "telemetry.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in telemetry), encoding="utf-8"
    )


def self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        plan = {
            "schema_version": 1,
            "product": "PCR02",
            "slots": [
                {
                    "slot_id": "self-noise-01",
                    "track": "self-noise",
                    "motion_class": "idle",
                    "floor_surface": "hard-floor",
                    "speech_state": "none",
                }
            ],
        }
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        capture_root = root / "capture"
        args = SimpleNamespace(
            plan=plan_path,
            slot_id="self-noise-01",
            capture_id="self-test",
            purpose="qualification-candidate",
            output_dir=capture_root,
            source_sha=SOURCE,
            version=VERSION,
            binary_sha256="1" * 64,
            board_revision="test-rev",
            device_id="test-device",
            room_id="test-room",
            ambient_condition="quiet-fixture",
            speaker_volume_percent=0,
            battery_mv=7600,
            charging_state="discharging",
            aec_backend="nlms",
            ns_estimator="mcra",
            simd_backend="neon",
            resampler_mode="bandlimited",
            optional_file=[],
        )
        initialized = new_capture(args)
        manifest = Path(initialized["manifest"])
        unsealed = json.loads(manifest.read_text(encoding="utf-8"))
        assert unsealed["sealed"] is False
        try:
            validate(manifest, capture_root, plan_path)
        except ValueError:
            pass
        else:
            raise AssertionError("unsealed working set was accepted as evidence")

        write_self_test_payload(capture_root)
        sealed = seal(manifest, capture_root, plan_path)
        assert sealed["result"] == "PASS"
        assert sealed["frame_count"] == 2
        assert sealed["duration_seconds"] == 0.02
        final = json.loads(manifest.read_text(encoding="utf-8"))
        assert final["sealed"] is True
        assert final["evidence_claims"]["real_capture"] is True
        assert final["bundle_digest_sha256"] == bundle_digest(final)

        try:
            seal(manifest, capture_root, plan_path)
        except ValueError:
            pass
        else:
            raise AssertionError("sealed evidence was mutable")

        overclaim = copy.deepcopy(final)
        overclaim["evidence_claims"]["hil_pass"] = True
        try:
            check_structure(overclaim)
        except ValueError:
            pass
        else:
            raise AssertionError("HIL overclaim accepted")

        bad_digest = copy.deepcopy(final)
        bad_digest["bundle_digest_sha256"] = "f" * 64
        bad_path = root / "bad-digest.json"
        bad_path.write_text(json.dumps(bad_digest), encoding="utf-8")
        try:
            validate(bad_path, capture_root, plan_path)
        except ValueError:
            pass
        else:
            raise AssertionError("bad bundle digest accepted")

        bad_timeline = (capture_root / "frame_timeline.jsonl").read_text(encoding="utf-8")
        (capture_root / "frame_timeline.jsonl").write_text(
            bad_timeline.replace('"sequence": 101', '"sequence": 103'), encoding="utf-8"
        )
        try:
            validate(manifest, capture_root, plan_path)
        except ValueError:
            pass
        else:
            raise AssertionError("mutated capture bytes were accepted")
    print("PCR02 capture bundle self-test: OK")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument(
        "--plan",
        type=Path,
        default=ROOT / "tests/validation/pcr02_capture_plan.json",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--slot-id", required=True)
    new_parser.add_argument("--capture-id", required=True)
    new_parser.add_argument(
        "--purpose", choices=["development", "qualification-candidate"], required=True
    )
    new_parser.add_argument("--output-dir", type=Path, required=True)
    new_parser.add_argument(
        "--plan", type=Path, default=ROOT / "tests/validation/pcr02_capture_plan.json"
    )
    new_parser.add_argument("--source-sha", required=True)
    new_parser.add_argument("--version", required=True)
    new_parser.add_argument("--binary-sha256", required=True)
    new_parser.add_argument("--board-revision", required=True)
    new_parser.add_argument("--device-id", required=True)
    new_parser.add_argument("--room-id", required=True)
    new_parser.add_argument("--ambient-condition", required=True)
    new_parser.add_argument("--speaker-volume-percent", type=int, required=True)
    new_parser.add_argument("--battery-mv", type=int, required=True)
    new_parser.add_argument("--charging-state", required=True)
    new_parser.add_argument("--aec-backend", required=True)
    new_parser.add_argument("--ns-estimator", required=True)
    new_parser.add_argument("--simd-backend", required=True)
    new_parser.add_argument("--resampler-mode", required=True)
    new_parser.add_argument("--optional-file", action="append", default=[])

    seal_parser = subparsers.add_parser("seal")
    add_common_arguments(seal_parser)
    validate_parser = subparsers.add_parser("validate")
    add_common_arguments(validate_parser)
    replay_parser = subparsers.add_parser("replay")
    add_common_arguments(replay_parser)
    replay_parser.add_argument("--processor", type=Path, required=True)
    replay_parser.add_argument("--output-pcm", type=Path)
    replay_parser.add_argument("--require-bit-exact", action="store_true")
    diagnose_parser = subparsers.add_parser("diagnose")
    add_common_arguments(diagnose_parser)
    diagnose_parser.add_argument("--processor", type=Path, required=True)
    diagnose_parser.add_argument("--processor-build-info", type=Path, required=True)
    diagnose_parser.add_argument("--output-dir", type=Path, required=True)
    diagnose_parser.add_argument("--require-bit-exact", action="store_true")
    diagnose_parser.add_argument("--stage-counterfactuals", action="store_true")

    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if args.command == "new":
            result = new_capture(args)
        elif args.command:
            args.root = args.root or args.manifest.parent
            if args.command == "seal":
                result = seal(args.manifest, args.root, args.plan)
            elif args.command == "validate":
                result = validate(args.manifest, args.root, args.plan)
            elif args.command == "replay":
                result = replay(args)
                if args.require_bit_exact and not result["comparison"]["bit_exact"]:
                    print(json.dumps(result, indent=2, sort_keys=True))
                    return 1
            else:
                result = diagnose(args)
        else:
            parser.error("choose a command or --self-test")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"pcr02_capture_bundle: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
