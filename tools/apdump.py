#!/usr/bin/env python3
"""Inspect and extract audio-pipeline APD flight-recorder dumps."""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


AP_DUMP_MAGIC = 0x32445041
AP_DUMP_FORMAT_VERSION = 1
AP_DUMP_ENDIAN_TAG = 0x01020304
AP_DIAG_RECORD_MIC = 1 << 0
AP_DIAG_RECORD_RENDER = 1 << 1
AP_DIAG_RECORD_OUTPUT = 1 << 2
AP_DIAG_RECORD_METRICS = 1 << 3

# Mirrors the stable v1 public ap_metrics_t contract. The dump format version
# must change before this on-disk block changes.
METRICS_SIZE_V1 = 120
HEADER = struct.Struct("<12I24s12s12s12s16s")
RECORD_HEADER = struct.Struct("<QQQII")


@dataclass(frozen=True)
class DumpHeader:
    format_version: int
    header_size: int
    sample_rate_hz: int
    mic_channels: int
    frame_samples: int
    record_mask: int
    record_stride: int
    frame_count: int
    trigger_event: int
    module_mask: int
    version: str
    aec_backend: str
    ns_estimator: str
    simd_backend: str
    resampler_mode: str


def _cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def read_header(data: bytes) -> DumpHeader:
    if len(data) < HEADER.size:
        raise ValueError("truncated APD header")
    fields = HEADER.unpack_from(data)
    (magic, fmt, header_size, endian_tag, rate, channels, frame_samples,
     mask, stride, count, trigger, module_mask,
     version, aec, ns, simd, resampler) = fields
    if magic != AP_DUMP_MAGIC:
        raise ValueError(f"bad APD magic 0x{magic:08x}")
    if fmt != AP_DUMP_FORMAT_VERSION:
        raise ValueError(f"unsupported APD format version {fmt}")
    if endian_tag != AP_DUMP_ENDIAN_TAG:
        raise ValueError("APD producer is not little-endian or endian tag is corrupt")
    if header_size < HEADER.size or header_size > len(data):
        raise ValueError("invalid APD header_size")
    if channels not in (1, 2) or frame_samples <= 0 or rate <= 0:
        raise ValueError("invalid APD audio geometry")
    minimum_stride = RECORD_HEADER.size
    if mask & AP_DIAG_RECORD_METRICS:
        minimum_stride += METRICS_SIZE_V1
    if mask & AP_DIAG_RECORD_MIC:
        minimum_stride += frame_samples * channels * 2
    if mask & AP_DIAG_RECORD_RENDER:
        minimum_stride += frame_samples * 2
    if mask & AP_DIAG_RECORD_OUTPUT:
        minimum_stride += frame_samples * 2
    minimum_stride = (minimum_stride + 7) & ~7
    if stride != minimum_stride:
        raise ValueError(f"unexpected APD record stride {stride}, expected {minimum_stride}")
    if header_size + stride * count > len(data):
        raise ValueError("truncated APD records")
    return DumpHeader(fmt, header_size, rate, channels, frame_samples, mask,
                      stride, count, trigger, module_mask, _cstr(version),
                      _cstr(aec), _cstr(ns), _cstr(simd), _cstr(resampler))


def read_dump(path: Path) -> tuple[DumpHeader, bytes]:
    data = path.read_bytes()
    return read_header(data), data


def iter_records(header: DumpHeader, data: bytes):
    offset = header.header_size
    mic_bytes = header.frame_samples * header.mic_channels * 2
    mono_bytes = header.frame_samples * 2
    for index in range(header.frame_count):
        base = offset + index * header.record_stride
        cursor = base
        sequence, capture_ns, render_ns, metadata_flags, trigger_event = \
            RECORD_HEADER.unpack_from(data, cursor)
        cursor += RECORD_HEADER.size
        metrics = None
        if header.record_mask & AP_DIAG_RECORD_METRICS:
            metrics = data[cursor:cursor + METRICS_SIZE_V1]
            cursor += METRICS_SIZE_V1
        mic = None
        if header.record_mask & AP_DIAG_RECORD_MIC:
            mic = data[cursor:cursor + mic_bytes]
            cursor += mic_bytes
        render = None
        if header.record_mask & AP_DIAG_RECORD_RENDER:
            render = data[cursor:cursor + mono_bytes]
            cursor += mono_bytes
        output = None
        if header.record_mask & AP_DIAG_RECORD_OUTPUT:
            output = data[cursor:cursor + mono_bytes]
        yield {
            "index": index,
            "sequence": sequence,
            "capture_timestamp_ns": capture_ns,
            "render_timestamp_ns": render_ns,
            "metadata_flags": metadata_flags,
            "trigger_event": trigger_event,
            "metrics": metrics,
            "mic": mic,
            "render": render,
            "output": output,
        }


def header_json(header: DumpHeader) -> dict:
    return {
        "format_version": header.format_version,
        "sample_rate_hz": header.sample_rate_hz,
        "mic_channels": header.mic_channels,
        "frame_samples": header.frame_samples,
        "record_mask": header.record_mask,
        "record_stride": header.record_stride,
        "frame_count": header.frame_count,
        "duration_ms": header.frame_count * 10,
        "trigger_event": header.trigger_event,
        "module_mask": header.module_mask,
        "build": {
            "version": header.version,
            "aec_backend": header.aec_backend,
            "ns_estimator": header.ns_estimator,
            "simd_backend": header.simd_backend,
            "resampler_mode": header.resampler_mode,
        },
    }


def extract(path: Path, output_dir: Path) -> dict:
    header, data = read_dump(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    streams = {
        "mic": bytearray(),
        "render": bytearray(),
        "output": bytearray(),
    }
    timeline: list[dict] = []
    for record in iter_records(header, data):
        for name in streams:
            block = record[name]
            if block is not None:
                streams[name].extend(block)
        timeline.append({
            "index": record["index"],
            "sequence": record["sequence"],
            "capture_timestamp_ns": record["capture_timestamp_ns"],
            "render_timestamp_ns": record["render_timestamp_ns"],
            "metadata_flags": record["metadata_flags"],
            "trigger_event": record["trigger_event"],
        })
    written = {}
    for name, payload in streams.items():
        if payload:
            target = output_dir / f"{name}.pcm"
            target.write_bytes(payload)
            written[name] = str(target)
    timeline_path = output_dir / "timeline.json"
    timeline_path.write_text(json.dumps(timeline, indent=2) + "\n", encoding="utf-8")
    manifest = header_json(header)
    manifest["streams"] = written
    manifest["timeline"] = str(timeline_path)
    manifest_path = output_dir / "dump.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    info_parser = sub.add_parser("info")
    info_parser.add_argument("dump", type=Path)
    extract_parser = sub.add_parser("extract")
    extract_parser.add_argument("dump", type=Path)
    extract_parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "info":
            header, _ = read_dump(args.dump)
            print(json.dumps(header_json(header), indent=2, sort_keys=True))
        else:
            print(json.dumps(extract(args.dump, args.output_dir), indent=2,
                             sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"apdump: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
