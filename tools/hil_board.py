#!/usr/bin/env python3
"""HIL board preflight/cleanup contract.

The tool classifies board/runner readiness failures as infrastructure failures so
product regressions are not conflated with broken lab equipment.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

REQUIRED = {
    "schema_version", "board_id", "revision", "soc", "ram_mib",
    "kernel_family", "audio_codec", "mic_board_revision", "speaker_revision",
}


def load_board(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED - set(data))
    if missing or data.get("schema_version") != 1:
        raise ValueError(f"invalid board manifest; missing={missing}")
    return data


def read_temp(path: str | None) -> float | None:
    if not path:
        return None
    raw = float(Path(path).read_text(encoding="utf-8").strip())
    return raw / 1000.0 if abs(raw) > 1000.0 else raw


def cpu_governors() -> dict[str, str]:
    result = {}
    for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"):
        try:
            result[path.parent.parent.name] = path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return result


def hook(command: str | None) -> None:
    if command:
        subprocess.run(command, shell=True, check=True)


def ntp_state() -> str:
    if not shutil.which("timedatectl"):
        return "unknown"
    proc = subprocess.run(
        ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def alsa_inventory() -> dict:
    result = {"capture": [], "playback": []}
    for key, command in (("capture", ["arecord", "-l"]), ("playback", ["aplay", "-l"])):
        if not shutil.which(command[0]):
            continue
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode == 0:
            result[key] = [line for line in proc.stdout.splitlines() if line.strip()]
    return result


def preflight(board: dict, output: Path, settle_seconds: int) -> int:
    failures = []
    try:
        hook(board.get("power_cycle_hook"))
    except subprocess.CalledProcessError as exc:
        failures.append(f"power_cycle_hook failed: {exc.returncode}")

    max_c = float(board.get("preflight_max_soc_c", 60.0))
    temp = None
    deadline = time.monotonic() + max(0, settle_seconds)
    while True:
        try:
            temp = read_temp(board.get("thermal_sensor"))
        except (OSError, ValueError) as exc:
            failures.append(f"thermal sensor unreadable: {exc}")
            break
        if temp is None or temp <= max_c or time.monotonic() >= deadline:
            break
        time.sleep(1.0)
    if temp is not None and temp > max_c:
        failures.append(f"board too hot for deterministic test: {temp:.2f}C > {max_c:.2f}C")

    free_mib = shutil.disk_usage(Path.cwd()).free // (1024 * 1024)
    min_free = int(board.get("min_free_mib", 256))
    if free_mib < min_free:
        failures.append(f"insufficient free disk: {free_mib} MiB < {min_free} MiB")

    inventory = alsa_inventory()
    if not inventory["capture"]:
        failures.append("no ALSA capture inventory detected")

    report = {
        "schema_version": 1,
        "classification": "INFRA_FAILURE" if failures else "READY",
        "board": board,
        "observed": {
            "hostname": os.uname().nodename,
            "kernel": os.uname().release,
            "machine": os.uname().machine,
            "free_mib": free_mib,
            "soc_temp_c": temp,
            "cpu_governors": cpu_governors(),
            "ntp_synchronized": ntp_state(),
            "alsa": inventory,
        },
        "failures": failures,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"classification": report["classification"], "board_id": board["board_id"], "failures": failures}, sort_keys=True))
    return 2 if failures else 0


def cleanup(board: dict, output: Path | None) -> int:
    failures = []
    try:
        hook(board.get("cleanup_hook"))
    except subprocess.CalledProcessError as exc:
        failures.append(f"cleanup_hook failed: {exc.returncode}")
    try:
        subprocess.run(["sync"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        failures.append(f"sync failed: {exc}")
    report = {
        "schema_version": 1,
        "classification": "INFRA_FAILURE" if failures else "CLEAN",
        "board_id": board["board_id"],
        "failures": failures,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 2 if failures else 0


def self_test() -> None:
    sample = {
        "schema_version": 1, "board_id": "b", "revision": "r", "soc": "s",
        "ram_mib": 64, "kernel_family": "linux", "audio_codec": "c",
        "mic_board_revision": "m", "speaker_revision": "sp",
    }
    path = Path("/tmp/ap-hil-board-self-test.json")
    path.write_text(json.dumps(sample), encoding="utf-8")
    assert load_board(path)["board_id"] == "b"
    path.unlink(missing_ok=True)
    print("HIL board controller self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("preflight")
    p.add_argument("--board", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--settle-seconds", type=int, default=120)
    c = sub.add_parser("cleanup")
    c.add_argument("--board", type=Path, required=True)
    c.add_argument("--output", type=Path)
    m = sub.add_parser("metadata")
    m.add_argument("--board", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.command == "metadata":
        print(json.dumps(load_board(args.board), indent=2, sort_keys=True))
        return 0
    if args.command == "preflight":
        return preflight(load_board(args.board), args.output, args.settle_seconds)
    if args.command == "cleanup":
        return cleanup(load_board(args.board), args.output)
    parser.error("preflight, cleanup or metadata is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
