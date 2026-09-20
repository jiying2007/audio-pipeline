#!/usr/bin/env python3
"""Fail-closed validator for matched gain-chain lab metadata binding."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT_REL = Path(".github/research/continuous-optimization/development-v3")
RESOLUTION_NAME = "matched-gain-chain-factor-plan-resolution-v1.json"
SCHEMA_NAME = "matched-gain-chain-factor-plan-lab-binding-v1.schema.json"
TEMPLATE_NAME = "matched-gain-chain-factor-plan-lab-binding-v1.template.json"
BINDING_NAME = "matched-gain-chain-factor-plan-lab-binding-v1.json"
EXPECTED_PREDECESSOR_BLOB = "4ed9b2c84e3e0e83b29245cefdeb73b082dd837d"
EXPECTED_SHIPPING = {
    "version": "v2.3.16",
    "sha": "57e4c64adc1cf06819e46e24e275ecd746d5f17f",
}
EXPECTED_STATE = {
    "lab_resolution_complete": True,
    "freeze_complete": True,
    "hardware_execution_authorized": False,
    "candidate_budget": 0,
}
EXPECTED_TOP_LEVEL = {
    "schema_version",
    "investigation",
    "authority",
    "predecessor",
    "coordinate_frame",
    "lab_values",
    "state",
    "shipping_immutable",
}
BANNED = {
    "",
    "unknown",
    "default",
    "auto",
    "tbd",
    "n/a",
    "same as current",
    "same as device",
    "lab_value_required",
}
STRING_VALUE_FIELDS = {
    "device_id_or_fixture_id",
    "hardware_revision",
    "software_firmware_revision",
    "volume_control_state",
    "room_or_fixture_id",
    "RIR_measurement_method",
}
XYZ_FIELDS = {"source_position_xyz_m", "microphone_position_xyz_m"}
ANALOG_GAIN_FIELDS = {
    "playback_analog_gain_db_or_exact_setting",
    "capture_analog_gain_db_or_exact_setting",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return payload


def reject_placeholders(value: Any, path: str) -> None:
    if value is None:
        raise ValueError(f"{path}: must not be null")
    if isinstance(value, str):
        if not value.strip():
            raise ValueError(f"{path}: must not be blank")
        if value.strip().lower() in BANNED:
            raise ValueError(f"{path}: placeholder value {value!r} is forbidden")
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        return
    if isinstance(value, list):
        if not value:
            raise ValueError(f"{path}: list must not be empty")
        for index, item in enumerate(value):
            reject_placeholders(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        if not value:
            raise ValueError(f"{path}: object must not be empty")
        for key, item in value.items():
            reject_placeholders(item, f"{path}.{key}")
        return
    raise ValueError(f"{path}: unsupported value type {type(value).__name__}")


def validate_resolution_contract(
    resolution: dict[str, Any],
    template: dict[str, Any],
) -> set[str]:
    if resolution.get("authority") != "PRECAPTURE_RESOLUTION_ONLY":
        raise ValueError("resolution authority changed")
    if resolution.get("candidate_budget") != 0:
        raise ValueError("resolution candidate budget must remain zero")

    state = resolution.get("state", {})
    expected_resolution_state = {
        "repository_resolution_complete": True,
        "lab_resolution_complete": False,
        "freeze_complete": False,
        "hardware_execution_authorized": False,
    }
    for key, expected in expected_resolution_state.items():
        if state.get(key) is not expected:
            raise ValueError(f"resolution state {key} must remain {expected!r}")

    next_step = resolution.get("next_authorized_step", {})
    required_next = {
        "name": "matched-gain-chain-factor-plan-lab-binding-v1",
        "scope": "supply_exact_lab_values_and_provenance_only",
        "may_execute_hardware": False,
        "may_run_audio_pipeline": False,
        "may_compute_dtd_or_quality_result": False,
        "may_create_algorithm_candidate": False,
    }
    for key, expected in required_next.items():
        if next_step.get(key) != expected:
            raise ValueError(f"next_authorized_step.{key} changed")

    required = set(resolution.get("lab_resolution_required", {}))
    if len(required) != 16:
        raise ValueError(f"expected 16 lab-resolution fields, got {len(required)}")

    if template.get("schema_version") != 1:
        raise ValueError("template schema_version must be 1")
    if template.get("investigation") != "matched-gain-chain-factor-plan-lab-binding-v1":
        raise ValueError("template investigation id mismatch")
    if template.get("authority") != "LAB_METADATA_BINDING_ONLY":
        raise ValueError("template authority mismatch")
    expected_predecessor = {
        "manifest": str(ROOT_REL / RESOLUTION_NAME),
        "blob_sha": EXPECTED_PREDECESSOR_BLOB,
    }
    if template.get("predecessor") != expected_predecessor:
        raise ValueError("template predecessor binding mismatch")
    if set(template.get("lab_values", {})) != required:
        raise ValueError("template lab_values must exactly match resolution requirements")
    for key, item in template["lab_values"].items():
        if item != {"value": "LAB_VALUE_REQUIRED", "provenance": "LAB_VALUE_REQUIRED"}:
            raise ValueError(f"template field {key} must remain an unresolved placeholder")
    if template.get("state") != EXPECTED_STATE:
        raise ValueError("template state must preserve metadata-only authority")
    if template.get("shipping_immutable") != EXPECTED_SHIPPING:
        raise ValueError("template shipping authority changed")
    return required


def validate_binding(
    binding: dict[str, Any],
    required: set[str],
    template: dict[str, Any],
) -> None:
    if set(binding) != EXPECTED_TOP_LEVEL:
        raise ValueError("binding top-level fields are not exact")
    if binding.get("schema_version") != 1:
        raise ValueError("binding schema_version must be 1")
    if binding.get("investigation") != "matched-gain-chain-factor-plan-lab-binding-v1":
        raise ValueError("binding investigation id mismatch")
    if binding.get("authority") != "LAB_METADATA_BINDING_ONLY":
        raise ValueError("binding authority mismatch")
    if binding.get("predecessor") != template["predecessor"]:
        raise ValueError("binding predecessor must match template")
    if binding.get("shipping_immutable") != EXPECTED_SHIPPING:
        raise ValueError("binding shipping authority changed")
    if binding.get("state") != EXPECTED_STATE:
        raise ValueError("binding state must remain metadata-only and candidate-budget zero")

    coordinate_frame = binding.get("coordinate_frame")
    if not isinstance(coordinate_frame, str):
        raise ValueError("coordinate_frame must be a string")
    reject_placeholders(coordinate_frame, "coordinate_frame")

    lab_values = binding.get("lab_values")
    if not isinstance(lab_values, dict) or set(lab_values) != required:
        raise ValueError("binding lab_values must exactly match resolution requirements")

    for key, item in lab_values.items():
        if not isinstance(item, dict) or set(item) != {"value", "provenance"}:
            raise ValueError(f"lab_values.{key}: expected value + provenance only")
        if not isinstance(item["provenance"], str):
            raise ValueError(f"lab_values.{key}.provenance must be a string")
        reject_placeholders(item["value"], f"lab_values.{key}.value")
        reject_placeholders(item["provenance"], f"lab_values.{key}.provenance")

    for key in STRING_VALUE_FIELDS:
        if not isinstance(lab_values[key]["value"], str):
            raise ValueError(f"lab_values.{key}.value must be a string")

    metadata = lab_values["render_source_metadata"]["value"]
    if not isinstance(metadata, dict):
        raise ValueError("render_source_metadata.value must be an object")

    for key in XYZ_FIELDS:
        value = lab_values[key]["value"]
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError(f"lab_values.{key}.value must be a 3-vector")
        if any(not isinstance(x, (int, float)) or isinstance(x, bool) for x in value):
            raise ValueError(f"lab_values.{key}.value must contain numeric coordinates")

    render_hash = lab_values["render_source_hash"]["value"]
    if not isinstance(render_hash, str) or not re.fullmatch(
        r"(?:sha256:)?[0-9a-fA-F]{64}", render_hash
    ):
        raise ValueError("render_source_hash.value must be a SHA-256 digest")

    for key in ANALOG_GAIN_FIELDS:
        value = lab_values[key]["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(
                f"lab_values.{key}.value must be numeric dB or an exact setting string"
            )


def git_blob(path: Path, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path.relative_to(cwd))],
        cwd=cwd,
        text=True,
    ).strip()


def check_repository(root: Path, require_binding: bool = False) -> dict[str, Any]:
    root = root.resolve()
    contract_root = root / ROOT_REL
    resolution_path = contract_root / RESOLUTION_NAME
    schema_path = contract_root / SCHEMA_NAME
    template_path = contract_root / TEMPLATE_NAME
    binding_path = contract_root / BINDING_NAME

    resolution = load_json(resolution_path)
    schema = load_json(schema_path)
    template = load_json(template_path)

    if git_blob(resolution_path, root) != EXPECTED_PREDECESSOR_BLOB:
        raise ValueError("resolution predecessor blob no longer matches the frozen binding")
    if not str(schema.get("$id", "")).endswith(SCHEMA_NAME):
        raise ValueError("binding schema id mismatch")

    required = validate_resolution_contract(resolution, template)

    if not binding_path.exists():
        if require_binding:
            raise ValueError(f"required binding manifest is absent: {binding_path}")
        return {
            "result": "CONTRACT_READY",
            "binding_present": False,
            "hardware_execution_authorized": False,
            "candidate_budget": 0,
        }

    binding = load_json(binding_path)
    validate_binding(binding, required, template)
    return {
        "result": "LAB_BINDING_COMPLETE",
        "binding_present": True,
        "manifest_blob_sha": git_blob(binding_path, root),
        "hardware_execution_authorized": False,
        "candidate_budget": 0,
    }


def _valid_binding(required: set[str], template: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {}
    for key in sorted(required):
        value: Any = f"exact-{key}"
        if key in XYZ_FIELDS:
            value = [0.0, 0.0, 0.0]
        elif key == "render_source_hash":
            value = "a" * 64
        elif key == "render_source_metadata":
            value = {"sample_rate_hz": 16000, "channels": 1, "duration_samples": 16000}
        values[key] = {"value": value, "provenance": f"lab-log:{key}"}
    return {
        "schema_version": 1,
        "investigation": "matched-gain-chain-factor-plan-lab-binding-v1",
        "authority": "LAB_METADATA_BINDING_ONLY",
        "predecessor": deepcopy(template["predecessor"]),
        "coordinate_frame": "fixture-origin-right-handed-meters",
        "lab_values": values,
        "state": deepcopy(EXPECTED_STATE),
        "shipping_immutable": deepcopy(EXPECTED_SHIPPING),
    }


def self_test() -> None:
    required = {
        "device_id_or_fixture_id",
        "hardware_revision",
        "software_firmware_revision",
        "playback_analog_gain_db_or_exact_setting",
        "capture_analog_gain_db_or_exact_setting",
        "AGC_enabled_and_exact_config",
        "device_DSP_enabled_modules_and_exact_config",
        "volume_control_state",
        "room_or_fixture_id",
        "source_position_xyz_m",
        "microphone_position_xyz_m",
        "source_orientation",
        "microphone_orientation",
        "render_source_hash",
        "render_source_metadata",
        "RIR_measurement_method",
    }
    template = {
        "predecessor": {
            "manifest": str(ROOT_REL / RESOLUTION_NAME),
            "blob_sha": EXPECTED_PREDECESSOR_BLOB,
        }
    }
    valid = _valid_binding(required, template)
    validate_binding(valid, required, template)

    bad = deepcopy(valid)
    bad["lab_values"]["hardware_revision"]["value"] = "unknown"
    try:
        validate_binding(bad, required, template)
    except ValueError:
        pass
    else:
        raise AssertionError("placeholder hardware revision was accepted")

    bad = deepcopy(valid)
    bad["lab_values"]["source_position_xyz_m"]["value"] = [0.0, 1.0]
    try:
        validate_binding(bad, required, template)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid xyz vector was accepted")

    bad = deepcopy(valid)
    bad["lab_values"]["render_source_hash"]["value"] = "abc"
    try:
        validate_binding(bad, required, template)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid render hash was accepted")

    bad = deepcopy(valid)
    bad["state"]["hardware_execution_authorized"] = True
    try:
        validate_binding(bad, required, template)
    except ValueError:
        pass
    else:
        raise AssertionError("hardware authority escalation was accepted")

    print("matched gain-chain lab binding validator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--require-binding", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    result = check_repository(args.root, require_binding=args.require_binding)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
