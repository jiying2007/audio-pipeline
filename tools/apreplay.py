#!/usr/bin/env python3
"""Replay an APD flight-recorder dump through ap_process_pcm."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import apdump


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
    import array
    left = array.array("h")
    right = array.array("h")
    left.frombytes(expected)
    right.frombytes(actual)
    if sys.byteorder != "little":
        left.byteswap()
        right.byteswap()
    diffs = [abs(int(a) - int(b)) for a, b in zip(left, right)]
    return {
        "bit_exact": False,
        "expected_bytes": len(expected),
        "actual_bytes": len(actual),
        "mae_lsb": sum(diffs) / len(diffs) if diffs else 0.0,
        "max_abs_lsb": max(diffs, default=0),
    }


def replay(dump_path: Path, processor: Path, output_path: Path | None) -> dict:
    header, data = apdump.read_dump(dump_path)
    records = list(apdump.iter_records(header, data))
    if not records or records[0]["mic"] is None:
        raise ValueError("dump does not contain microphone PCM")

    mic = b"".join(record["mic"] or b"" for record in records)
    render_present = bool(header.record_mask & apdump.AP_DIAG_RECORD_RENDER)
    render = b"".join(record["render"] or b"" for record in records)
    expected_present = bool(header.record_mask & apdump.AP_DIAG_RECORD_OUTPUT)
    expected = b"".join(record["output"] or b"" for record in records)

    with tempfile.TemporaryDirectory(prefix="ap-replay-") as directory:
        root = Path(directory)
        mic_path = root / "mic.pcm"
        render_path = root / "render.pcm"
        generated = root / "replay.pcm"
        mic_path.write_bytes(mic)
        if render_present:
            render_path.write_bytes(render)
        command = [
            str(processor),
            "--sample-rate", str(header.sample_rate_hz),
            "--mic-channels", str(header.mic_channels),
        ]
        if render_present:
            command.extend([str(mic_path), str(render_path), str(generated)])
        else:
            command.append("--capture-only")
            command.extend([str(mic_path), str(generated)])
        subprocess.run(command, check=True)
        actual = generated.read_bytes()
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(actual)

    result = {
        "dump": str(dump_path),
        "processor": str(processor),
        "dump_build": apdump.header_json(header)["build"],
        "frames": header.frame_count,
        "sample_rate_hz": header.sample_rate_hz,
        "mic_channels": header.mic_channels,
        "capture_only": not render_present,
        "recorded_output_present": expected_present,
    }
    if expected_present:
        result["comparison"] = compare_s16(expected, actual)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("--processor", type=Path, required=True)
    parser.add_argument("--output-pcm", type=Path)
    parser.add_argument("--require-bit-exact", action="store_true")
    args = parser.parse_args()
    try:
        result = replay(args.dump, args.processor, args.output_pcm)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"apreplay: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    comparison = result.get("comparison")
    if args.require_bit_exact and (not comparison or not comparison["bit_exact"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
