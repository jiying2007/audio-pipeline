#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import tempfile
from pathlib import Path

SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}
REQUIRED_RUNNER_LABELS = {"self-hosted", "linux", "audio-target"}
_PLACEHOLDER_PREFIX = "replace-with-"


def _string(value: object, field: str, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    value = value.strip()
    if value.startswith(_PLACEHOLDER_PREFIX):
        raise ValueError(f"{field} still contains an example placeholder")
    return value


def load_route_authority(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("board manifest schema_version must be 1")

    board_id = _string(data.get("board_id"), "board_id", required=True)
    revision = _string(data.get("revision"), "revision", required=True)
    labels = data.get("runner_labels")
    if not isinstance(labels, list) or not all(isinstance(item, str) for item in labels):
        raise ValueError("runner_labels must be a string list")
    missing_labels = sorted(REQUIRED_RUNNER_LABELS - set(labels))
    if missing_labels:
        raise ValueError(f"board manifest missing audio-target runner labels: {missing_labels}")

    route = data.get("route")
    if not isinstance(route, dict):
        raise ValueError("board manifest route must be an object")
    capture = _string(route.get("capture_device"), "route.capture_device", required=True)
    playback = _string(route.get("playback_device"), "route.playback_device", required=False)
    # AEC candidate target qualification must exercise a real render-reference path.
    farend = _string(route.get("farend_file"), "route.farend_file", required=True)
    sample_rate = int(route.get("sample_rate_hz", 0))
    mic_channels = int(route.get("mic_channels", 0))
    dsp_cpu = int(route.get("dsp_cpu", -2))
    if sample_rate not in SUPPORTED_RATES:
        raise ValueError(f"unsupported route.sample_rate_hz={sample_rate}")
    if mic_channels not in (1, 2):
        raise ValueError(f"route.mic_channels must be 1 or 2, got {mic_channels}")
    if dsp_cpu < -1:
        raise ValueError(f"route.dsp_cpu must be >= -1, got {dsp_cpu}")

    power_input = _string(data.get("power_sensor"), "power_sensor", required=False)
    thermal_sensor = _string(data.get("thermal_sensor"), "thermal_sensor", required=False)

    return {
        "schema_version": 1,
        "authority": "audio-target-board-manifest-route",
        "board_id": board_id,
        "board_revision": revision,
        "runner_labels": sorted(set(labels)),
        "route": {
            "capture_device": capture,
            "playback_device": playback,
            "farend_file": farend,
            "sample_rate_hz": sample_rate,
            "mic_channels": mic_channels,
            "dsp_cpu": dsp_cpu,
        },
        "power_input": power_input,
        "thermal_sensor": thermal_sensor,
    }


def write_env(authority: dict, path: Path) -> None:
    route = authority["route"]
    values = {
        "AP_TARGET_BOARD_ID": authority["board_id"],
        "AP_TARGET_BOARD_REVISION": authority["board_revision"],
        "AP_TARGET_CAPTURE_DEVICE": route["capture_device"],
        "AP_TARGET_PLAYBACK_DEVICE": route["playback_device"] or "",
        "AP_TARGET_FAREND_FILE": route["farend_file"],
        "AP_TARGET_SAMPLE_RATE": str(route["sample_rate_hz"]),
        "AP_TARGET_MIC_CHANNELS": str(route["mic_channels"]),
        "AP_TARGET_DSP_CPU": str(route["dsp_cpu"]),
        "AP_TARGET_POWER_INPUT": authority["power_input"] or "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{key}={shlex.quote(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )


def self_test() -> None:
    good = {
        "schema_version": 1,
        "board_id": "ssc305-lab-01",
        "revision": "DVT1",
        "runner_labels": ["audio-target", "linux", "self-hosted"],
        "route": {
            "capture_device": "hw:0,0",
            "playback_device": "hw:0,0",
            "farend_file": "/opt/audio/farend.pcm",
            "sample_rate_hz": 16000,
            "mic_channels": 2,
            "dsp_cpu": 1,
        },
        "power_sensor": "/sys/class/hwmon/hwmon0/power1_input",
        "thermal_sensor": "/sys/class/thermal/thermal_zone0/temp",
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "board.json"
        path.write_text(json.dumps(good), encoding="utf-8")
        authority = load_route_authority(path)
        assert authority["route"]["capture_device"] == "hw:0,0"
        assert authority["route"]["farend_file"] == "/opt/audio/farend.pcm"
        env = Path(tmp) / "route.env"
        write_env(authority, env)
        text = env.read_text(encoding="utf-8")
        assert "AP_TARGET_SAMPLE_RATE=16000" in text

        bad = dict(good)
        bad["route"] = dict(good["route"])
        bad["route"]["capture_device"] = "replace-with-controller-visible-capture-device"
        path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            load_route_authority(path)
        except ValueError:
            pass
        else:
            raise AssertionError("example placeholder unexpectedly accepted")

        bad = dict(good)
        bad["route"] = dict(good["route"])
        bad["route"]["farend_file"] = None
        path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            load_route_authority(path)
        except ValueError:
            pass
        else:
            raise AssertionError("AEC target route without far-end reference unexpectedly accepted")
    print("candidate target route authority self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--board", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env-output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.board is None:
        parser.error("--board is required")
    authority = load_route_authority(args.board)
    text = json.dumps(authority, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.env_output:
        write_env(authority, args.env_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
