#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

VERSION = "2.1"
_KV_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")
_SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}


def parse_kv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in _KV_RE.findall(text):
        result[key] = value
    return result


def as_int(values: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(values.get(key, str(default)), 0)
    except ValueError as exc:
        raise ValueError(f"invalid integer {key}={values.get(key)!r}") from exc


def as_float(values: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        value = float(values.get(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"invalid float {key}={values.get(key)!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"non-finite float {key}")
    return value


def thermal_c() -> list[float]:
    values: list[float] = []
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            raw = float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        values.append(raw / 1000.0 if abs(raw) > 1000.0 else raw)
    return values


def power_w(path: Path | None, scale: float) -> float | None:
    if path is None:
        return None
    if scale <= 0.0:
        raise ValueError("power scale must be > 0")
    try:
        raw = float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read power input {path}") from exc
    value = raw / scale
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"invalid power value from {path}: {value}")
    return value


def rss_kib(pid: int) -> int | None:
    try:
        lines = Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            fields = line.split()
            if len(fields) >= 2:
                return int(fields[1])
    return None


def run_monitored(command: list[str], power_input: Path | None, power_scale: float,
                  sample_period: float = 0.10, extra_env: dict[str, str] | None = None
                  ) -> tuple[subprocess.CompletedProcess[str], dict]:
    environment = os.environ.copy()
    if extra_env:
        environment.update(extra_env)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment
    )
    max_rss = 0
    max_temp: float | None = None
    power_samples: list[float] = []
    while process.poll() is None:
        rss = rss_kib(process.pid)
        if rss is not None:
            max_rss = max(max_rss, rss)
        temps = thermal_c()
        if temps:
            observed = max(temps)
            max_temp = observed if max_temp is None else max(max_temp, observed)
        sample = power_w(power_input, power_scale)
        if sample is not None:
            power_samples.append(sample)
        time.sleep(sample_period)
    stdout, stderr = process.communicate()
    completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    sensors = {
        "max_rss_kib": max_rss,
        "max_soc_c": max_temp,
        "average_power_w": (
            sum(power_samples) / len(power_samples) if power_samples else None
        ),
        "power_samples": len(power_samples),
    }
    return completed, sensors


def require_success(result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(result.args)}\n{message}"
        )


def shutil_which(name: str) -> str | None:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def benchmark(args: argparse.Namespace) -> int:
    if args.seconds < 1 or args.idle_seconds < 1:
        raise SystemExit("benchmark durations must be >= 1")
    if args.sample_rate not in _SUPPORTED_RATES or args.mic_channels not in (1, 2):
        raise SystemExit("invalid benchmark route geometry")
    active_cmd = [
        str(args.binary), str(args.seconds), str(args.max_rtf),
        str(args.max_p99_us), "active", str(args.sample_rate), str(args.mic_channels),
    ]
    idle_cmd = [
        str(args.binary), str(args.idle_seconds), "0", "0", "idle",
        str(args.sample_rate), str(args.mic_channels),
    ]
    if args.dsp_cpu >= 0 and shutil_which("taskset"):
        active_cmd = ["taskset", "-c", str(args.dsp_cpu)] + active_cmd
        idle_cmd = ["taskset", "-c", str(args.dsp_cpu)] + idle_cmd

    active, sensors = run_monitored(
        active_cmd, args.power_input, args.power_scale, args.sample_period
    )
    require_success(active)
    idle, idle_sensors = run_monitored(
        idle_cmd, None, args.power_scale, args.sample_period
    )
    require_success(idle)
    active_kv = parse_kv(active.stdout + "\n" + active.stderr)
    idle_kv = parse_kv(idle.stdout + "\n" + idle.stderr)
    required = {
        "p50_us", "p95_us", "p99_us", "deadline_misses", "rtf", "state_bytes",
        "sample_rate_hz", "mic_channels",
    }
    missing = sorted(required - active_kv.keys())
    if missing:
        raise ValueError(f"benchmark output missing keys: {', '.join(missing)}")
    if as_int(active_kv, "sample_rate_hz") != args.sample_rate or \
       as_int(active_kv, "mic_channels") != args.mic_channels:
        raise ValueError("benchmark output geometry does not match requested route")

    thermal = {
        "ambient_c": args.ambient_c,
        "max_soc_c": sensors["max_soc_c"],
        "average_power_w": sensors["average_power_w"],
        "power_samples": sensors["power_samples"],
    }
    if args.require_sensors:
        if thermal["max_soc_c"] is None:
            raise ValueError("no thermal sensor data observed")
        if thermal["average_power_w"] is None:
            raise ValueError("no power samples observed; provide --power-input")

    performance = {
        "active_cpu_percent": as_float(active_kv, "rtf") * 100.0,
        "idle_cpu_percent": as_float(idle_kv, "rtf") * 100.0,
        "p50_us": as_int(active_kv, "p50_us"),
        "p95_us": as_int(active_kv, "p95_us"),
        "p99_us": as_int(active_kv, "p99_us"),
        "deadline_misses": as_int(active_kv, "deadline_misses"),
        "rss_kib": max(int(sensors["max_rss_kib"]), int(idle_sensors["max_rss_kib"])),
        "pipeline_state_bytes": as_int(active_kv, "state_bytes"),
        "rtf": as_float(active_kv, "rtf"),
    }
    output = {
        "schema_version": 1,
        "collector_version": VERSION,
        "kind": "target-benchmark",
        "command": active_cmd,
        "route": {"sample_rate_hz": args.sample_rate, "mic_channels": args.mic_channels},
        "performance": performance,
        "thermal_power": thermal,
        "raw": {"active": active.stdout.strip(), "idle": idle.stdout.strip()},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(args.output)
    return 0


def route_soak(args: argparse.Namespace) -> int:
    if args.seconds < 1:
        raise SystemExit("--seconds must be >= 1")
    if args.sample_rate not in _SUPPORTED_RATES:
        raise SystemExit("unsupported --sample-rate")
    if args.mic_channels not in (1, 2):
        raise SystemExit("--mic-channels must be 1 or 2")
    playback = args.playback_device if args.playback_device else "-"
    farend = str(args.farend) if args.farend else "-"
    command = [
        str(args.binary), args.capture_device, playback, farend, "-",
        str(args.seconds), str(args.dsp_cpu), str(args.sample_rate),
        str(args.mic_channels),
    ]
    fault_profiles = {
        "none": {},
        "accelerated": {
            "AP_FAULT_ROUTE_RESTART_EVERY": "3000",
            "AP_FAULT_RENDER_GAP_EVERY": "6000",
            "AP_FAULT_RENDER_GAP_FRAMES": "5",
            "AP_FAULT_CPU_STALL_EVERY": "9000",
            "AP_FAULT_CPU_STALL_MS": "15",
        },
        "stress": {
            "AP_FAULT_ROUTE_RESTART_EVERY": "1000",
            "AP_FAULT_RENDER_GAP_EVERY": "2000",
            "AP_FAULT_RENDER_GAP_FRAMES": "10",
            "AP_FAULT_CPU_STALL_EVERY": "3000",
            "AP_FAULT_CPU_STALL_MS": "25",
        },
    }
    fault_env = dict(fault_profiles[args.fault_profile])
    if playback == "-":
        fault_env.pop("AP_FAULT_RENDER_GAP_EVERY", None)
        fault_env.pop("AP_FAULT_RENDER_GAP_FRAMES", None)
    result, sensors = run_monitored(
        command, args.power_input, args.power_scale, args.sample_period, fault_env
    )
    combined = result.stdout + "\n" + result.stderr
    values = parse_kv(combined)
    required = {
        "produced", "received", "xruns", "dsp_overruns", "input_full",
        "output_drop", "p95_dsp_us", "p99_dsp_us", "failed_frames",
        "injected_route_restarts", "injected_render_gap_frames",
        "injected_cpu_stalls",
    }
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError(f"route soak output missing keys: {', '.join(missing)}")
    produced = as_int(values, "produced")
    received = as_int(values, "received")
    xruns = as_int(values, "xruns")
    overruns = as_int(values, "dsp_overruns")
    input_full = as_int(values, "input_full")
    output_drop = as_int(values, "output_drop")
    failed_frames = as_int(values, "failed_frames")
    injected_restarts = as_int(values, "injected_route_restarts")
    injected_gaps = as_int(values, "injected_render_gap_frames")
    injected_stalls = as_int(values, "injected_cpu_stalls")
    injection_ok = True
    if args.fault_profile != "none":
        injection_ok = injected_restarts > 0 and injected_stalls > 0
        if playback != "-":
            injection_ok = injection_ok and injected_gaps > 0
    passed = (
        result.returncode == 0 and produced == received and injection_ok
        and xruns <= args.max_xruns and overruns <= args.max_overruns
        and input_full == 0 and output_drop == 0 and failed_frames == 0
    )
    output = {
        "schema_version": 1,
        "collector_version": VERSION,
        "kind": "alsa-route-soak",
        "route": {
            "capture_device": args.capture_device,
            "playback_device": None if playback == "-" else playback,
            "farend": None if farend == "-" else farend,
            "sample_rate_hz": args.sample_rate,
            "mic_channels": args.mic_channels,
            "dsp_cpu": args.dsp_cpu,
        },
        "fault_injection": {
            "profile": args.fault_profile,
            "route_restarts": injected_restarts,
            "render_gap_frames": injected_gaps,
            "cpu_stalls": injected_stalls,
            "observed_required_faults": injection_ok,
        },
        "soak": {
            "hours": args.seconds / 3600.0,
            "passed": passed,
            "xruns": xruns,
            "deadline_misses": overruns,
            "overruns": overruns,
            "input_full_events": input_full,
            "output_drop_events": output_drop,
            "failed_frames": failed_frames,
            "p95_us": as_int(values, "p95_dsp_us"),
            "p99_us": as_int(values, "p99_dsp_us"),
            "max_dsp_us": as_int(values, "max_dsp_us"),
            "critical_events": as_int(values, "critical_events"),
        },
        "thermal_power": {
            "max_soc_c": sensors["max_soc_c"],
            "average_power_w": sensors["average_power_w"],
            "power_samples": sensors["power_samples"],
        },
        "raw": combined.strip(),
        "returncode": result.returncode,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(args.output)
    return 0 if passed else 1


def self_test() -> int:
    bench = (
        "mode=active frames=100 sample_rate_hz=16000 mic_channels=2 audio_s=1 "
        "elapsed_s=0.123 avg_us=12.3 p50_us=11 p95_us=22 p99_us=33 "
        "max_us=44 deadline_misses=0 rtf=0.123 state_bytes=1234\n"
    )
    values = parse_kv(bench)
    assert as_int(values, "p99_us") == 33
    assert as_int(values, "sample_rate_hz") == 16000
    assert abs(as_float(values, "rtf") - 0.123) < 1e-9
    route = (
        "produced=100 received=100 xruns=0 dsp_overruns=0 input_full=0 "
        "output_drop=0 p50_dsp_us=10 p95_dsp_us=20 p99_dsp_us=30 "
        "max_dsp_us=40 failed_frames=0 critical_events=0 "
        "injected_route_restarts=0 injected_render_gap_frames=0 injected_cpu_stalls=0\n"
    )
    r = parse_kv(route)
    assert as_int(r, "produced") == as_int(r, "received") == 100
    assert as_int(r, "p95_dsp_us") == 20
    assert as_int(r, "injected_route_restarts") == 0
    print("target evidence collector self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")

    b = sub.add_parser("benchmark")
    b.add_argument("--binary", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    b.add_argument("--seconds", type=int, default=120)
    b.add_argument("--idle-seconds", type=int, default=30)
    b.add_argument("--max-rtf", type=float, default=0.40)
    b.add_argument("--max-p99-us", type=int, default=9000)
    b.add_argument("--dsp-cpu", type=int, default=1)
    b.add_argument("--sample-rate", type=int, default=16000)
    b.add_argument("--mic-channels", type=int, default=2)
    b.add_argument("--ambient-c", type=float, required=True)
    b.add_argument("--power-input", type=Path)
    b.add_argument("--power-scale", type=float, default=1_000_000.0)
    b.add_argument("--sample-period", type=float, default=0.10)
    b.add_argument("--require-sensors", action="store_true")

    s = sub.add_parser("route-soak")
    s.add_argument("--binary", type=Path, required=True)
    s.add_argument("--output", type=Path, required=True)
    s.add_argument("--capture-device", required=True)
    s.add_argument("--playback-device")
    s.add_argument("--farend", type=Path)
    s.add_argument("--seconds", type=int, default=28800)
    s.add_argument("--dsp-cpu", type=int, default=1)
    s.add_argument("--sample-rate", type=int, default=16000)
    s.add_argument("--mic-channels", type=int, default=2)
    s.add_argument("--max-xruns", type=int, default=0)
    s.add_argument("--max-overruns", type=int, default=0)
    s.add_argument("--power-input", type=Path)
    s.add_argument("--power-scale", type=float, default=1_000_000.0)
    s.add_argument("--sample-period", type=float, default=1.0)
    s.add_argument("--fault-profile", choices=("none", "accelerated", "stress"),
                   default="none")

    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.command == "benchmark":
        return benchmark(args)
    if args.command == "route-soak":
        return route_soak(args)
    parser.error("a command is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
