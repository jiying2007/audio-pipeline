#!/usr/bin/env python3
"""Discover a hash-bindable AMI external-timing VAD research microset.

This is deliberately discovery-only. It does not create canonical validation
corpora or shipping authority. It pins one AMI transport mirror commit, obtains
LFS object identity for Mix-Headset audio, hashes the four small manual segment
annotation XML files, derives deterministic windows from annotation timing only,
and verifies that byte-range audio materialization is possible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

HF_REPOSITORY = "ggfox00000/dia-AMICorpus-all"
HF_REVISION = "a249db53de253a3a0a864c93a51d613159dfec7c"
MEETING = "ES2003a"
SPEAKERS = ("A", "B", "C", "D")
OFFICIAL_CORPUS = "https://groups.inf.ed.ac.uk/ami/corpus/"
OFFICIAL_AUDIO = (
    "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/"
    f"{MEETING}/audio/{MEETING}.Mix-Headset.wav"
)
LICENSE = "CC-BY-4.0"
WINDOW_SECONDS = 20.0
WINDOW_TARGET_OCCUPANCIES = (0.25, 0.50, 0.75)
WINDOW_STEP_SECONDS = 5.0
WINDOW_MIN_CENTER_GAP_SECONDS = 60.0
HEADER_RANGE_BYTES = 256 * 1024
MAX_XML_BYTES = 2 * 1024 * 1024
USER_AGENT = "audio-pipeline-ami-vad-discovery/1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_bytes(url: str, *, max_bytes: int, headers: dict[str, str] | None = None) -> tuple[bytes, Any]:
    request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"response exceeded max_bytes={max_bytes}: {url}")
        return data, response


def hf_tree_url() -> str:
    path = f"amicorpus/{MEETING}/audio"
    return (
        "https://huggingface.co/api/datasets/"
        f"{HF_REPOSITORY}/tree/{HF_REVISION}/{urllib.parse.quote(path, safe='/')}"
        "?recursive=false&expand=false"
    )


def hf_resolve_url(path: str) -> str:
    return (
        f"https://huggingface.co/datasets/{HF_REPOSITORY}/resolve/{HF_REVISION}/"
        f"{urllib.parse.quote(path, safe='/')}?download=true"
    )


def load_audio_metadata() -> dict[str, Any]:
    data, _ = request_bytes(hf_tree_url(), max_bytes=2 * 1024 * 1024)
    listing = json.loads(data.decode("utf-8"))
    if not isinstance(listing, list):
        raise ValueError("Hugging Face tree response must be a list")
    wanted = f"amicorpus/{MEETING}/audio/{MEETING}.Mix-Headset.wav"
    match = next((item for item in listing if item.get("path") == wanted), None)
    if match is None:
        raise ValueError(f"Mix-Headset file missing from pinned mirror: {wanted}")
    size = int(match.get("size", 0))
    lfs = match.get("lfs") or {}
    lfs_sha256 = str(lfs.get("sha256", ""))
    if size <= 0:
        raise ValueError("invalid audio object size")
    if re.fullmatch(r"[0-9a-f]{64}", lfs_sha256) is None:
        raise ValueError("Mix-Headset must expose a pinned LFS SHA-256")
    return {
        "path": wanted,
        "size_bytes": size,
        "lfs_sha256": lfs_sha256,
        "mirror_resolve_url": hf_resolve_url(wanted),
    }


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_segments(xml_bytes: bytes, speaker: str) -> list[tuple[float, float]]:
    root = ET.fromstring(xml_bytes)
    intervals: list[tuple[float, float]] = []
    for element in root.iter():
        if local_name(element.tag) != "segment":
            continue
        raw_start = element.attrib.get("transcriber_start", element.attrib.get("starttime"))
        raw_end = element.attrib.get("transcriber_end", element.attrib.get("endtime"))
        if raw_start is None or raw_end is None:
            continue
        start = float(raw_start)
        end = float(raw_end)
        if not (math.isfinite(start) and math.isfinite(end)) or end <= start or start < 0.0:
            continue
        intervals.append((start, end))
    if not intervals:
        raise ValueError(f"no usable segment timing for speaker {speaker}")
    return sorted(intervals)


def load_segment_annotations() -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
    all_intervals: list[tuple[float, float]] = []
    files = []
    for speaker in SPEAKERS:
        path = f"ami_public_manual_1.6.2/segments/{MEETING}.{speaker}.segments.xml"
        url = hf_resolve_url(path)
        data, _ = request_bytes(url, max_bytes=MAX_XML_BYTES)
        intervals = parse_segments(data, speaker)
        all_intervals.extend(intervals)
        files.append({
            "speaker": speaker,
            "path": path,
            "sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "segments": len(intervals),
            "mirror_resolve_url": url,
        })
    return merge_intervals(all_intervals), files


def merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(item[0], item[1]) for item in merged]


def interval_overlap(intervals: list[tuple[float, float]], start: float, end: float) -> float:
    overlap = 0.0
    for left, right in intervals:
        if right <= start:
            continue
        if left >= end:
            break
        overlap += max(0.0, min(end, right) - max(start, left))
    return overlap


def select_windows(intervals: list[tuple[float, float]], duration: float) -> list[dict[str, float]]:
    if duration < 4.0 * WINDOW_SECONDS:
        raise ValueError("audio too short for discovery windows")
    first = 30.0
    last = max(first, duration - WINDOW_SECONDS - 30.0)
    starts = []
    value = first
    while value <= last + 1.0e-9:
        starts.append(round(value, 3))
        value += WINDOW_STEP_SECONDS
    candidates = []
    for start in starts:
        end = start + WINDOW_SECONDS
        occupancy = interval_overlap(intervals, start, end) / WINDOW_SECONDS
        candidates.append({"start_s": start, "end_s": end, "activity_fraction": occupancy})
    chosen: list[dict[str, float]] = []
    for target in WINDOW_TARGET_OCCUPANCIES:
        eligible = [
            item for item in candidates
            if all(
                abs((item["start_s"] + WINDOW_SECONDS / 2.0) -
                    (other["start_s"] + WINDOW_SECONDS / 2.0)) >= WINDOW_MIN_CENTER_GAP_SECONDS
                for other in chosen
            )
        ]
        if not eligible:
            eligible = [item for item in candidates if item not in chosen]
        if not eligible:
            raise ValueError("not enough distinct discovery windows")
        best = min(eligible, key=lambda item: (abs(item["activity_fraction"] - target), item["start_s"]))
        chosen.append({**best, "target_activity_fraction": target})
    return sorted(chosen, key=lambda item: item["start_s"])


def parse_wav_header(data: bytes) -> dict[str, int]:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Mix-Headset is not a RIFF/WAVE stream")
    offset = 12
    fmt: dict[str, int] | None = None
    data_offset = None
    data_size = None
    while offset + 8 <= len(data):
        chunk_id = data[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        payload = offset + 8
        if chunk_id == b"fmt " and payload + min(chunk_size, 16) <= len(data):
            if chunk_size < 16:
                raise ValueError("invalid WAV fmt chunk")
            audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample = struct.unpack_from(
                "<HHIIHH", data, payload
            )
            fmt = {
                "audio_format": audio_format,
                "channels": channels,
                "sample_rate_hz": sample_rate,
                "byte_rate": byte_rate,
                "block_align": block_align,
                "bits_per_sample": bits_per_sample,
            }
        elif chunk_id == b"data":
            data_offset = payload
            data_size = chunk_size
            break
        next_offset = payload + chunk_size + (chunk_size & 1)
        if next_offset <= offset:
            break
        offset = next_offset
    if fmt is None or data_offset is None or data_size is None:
        raise ValueError("WAV fmt/data chunks not found in bounded header")
    if fmt["audio_format"] != 1 or fmt["bits_per_sample"] != 16:
        raise ValueError("AMI microset requires uncompressed PCM16")
    if fmt["channels"] < 1 or fmt["sample_rate_hz"] <= 0 or fmt["byte_rate"] <= 0:
        raise ValueError("invalid WAV geometry")
    return {**fmt, "data_offset": data_offset, "data_size": data_size}


def load_wav_header(audio_url: str) -> tuple[dict[str, int], dict[str, str | int | bool]]:
    data, response = request_bytes(
        audio_url,
        max_bytes=HEADER_RANGE_BYTES,
        headers={"Range": f"bytes=0-{HEADER_RANGE_BYTES - 1}"},
    )
    status = int(getattr(response, "status", response.getcode()))
    content_range = response.headers.get("Content-Range")
    if status != 206 or not content_range:
        raise ValueError(f"pinned AMI mirror does not honor HTTP Range for audio: status={status}")
    return parse_wav_header(data), {
        "range_supported": True,
        "header_status": status,
        "header_content_range": content_range,
        "header_bytes": len(data),
    }


def probe_window_range(audio_url: str, wav: dict[str, int], window: dict[str, float]) -> dict[str, Any]:
    byte_rate = int(wav["byte_rate"])
    block_align = int(wav["block_align"])
    data_offset = int(wav["data_offset"])
    start_byte = data_offset + int(window["start_s"] * byte_rate)
    start_byte -= (start_byte - data_offset) % block_align
    probe_bytes = min(byte_rate, 256 * 1024)
    end_byte = start_byte + probe_bytes - 1
    data, response = request_bytes(
        audio_url,
        max_bytes=probe_bytes,
        headers={"Range": f"bytes={start_byte}-{end_byte}"},
    )
    status = int(getattr(response, "status", response.getcode()))
    content_range = response.headers.get("Content-Range")
    if status != 206 or not content_range:
        raise ValueError(f"audio window range request was not honored: status={status}")
    if len(data) != probe_bytes:
        raise ValueError(f"audio range byte count mismatch: {len(data)} != {probe_bytes}")
    return {
        "status": status,
        "content_range": content_range,
        "requested_start_byte": start_byte,
        "requested_end_byte": end_byte,
        "received_bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def discover() -> dict[str, Any]:
    audio = load_audio_metadata()
    intervals, annotation_files = load_segment_annotations()
    wav, range_info = load_wav_header(audio["mirror_resolve_url"])
    duration = wav["data_size"] / float(wav["byte_rate"])
    if duration <= 0.0:
        raise ValueError("invalid WAV duration")
    if intervals[-1][1] > duration + 2.0:
        raise ValueError("manual segment timing extends beyond audio duration")
    windows = select_windows(intervals, duration)
    range_probe = probe_window_range(audio["mirror_resolve_url"], wav, windows[0])
    return {
        "schema_version": 1,
        "authority": "research-discovery-only",
        "dataset": {
            "name": "AMI Meeting Corpus",
            "meeting": MEETING,
            "license": LICENSE,
            "official_corpus_url": OFFICIAL_CORPUS,
            "official_audio_url": OFFICIAL_AUDIO,
            "annotation_semantics": (
                "manual transcription segment timing; external human-adjusted timing, "
                "not a dedicated audited speech-activity-detection gold label"
            ),
        },
        "transport_mirror": {
            "repository": HF_REPOSITORY,
            "revision": HF_REVISION,
        },
        "audio": {
            **audio,
            "wav": wav,
            "duration_s": duration,
            **range_info,
            "range_probe": range_probe,
        },
        "annotations": {
            "files": annotation_files,
            "merged_intervals": len(intervals),
            "last_end_s": intervals[-1][1],
        },
        "window_plan": windows,
        "next_step": (
            "pin discovered hashes/geometry into a research lock, then materialize only "
            "the planned byte ranges and 10 ms external-timing labels"
        ),
    }


def self_test() -> None:
    merged = merge_intervals([(2.0, 3.0), (1.0, 2.5), (5.0, 6.0)])
    assert merged == [(1.0, 3.0), (5.0, 6.0)]
    assert abs(interval_overlap(merged, 0.0, 2.0) - 1.0) < 1.0e-9

    xml = b'''<?xml version="1.0"?><root><segment transcriber_start="1.25" transcriber_end="2.75"/></root>'''
    assert parse_segments(xml, "A") == [(1.25, 2.75)]

    fmt_payload = struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16)
    wav = (
        b"RIFF" + struct.pack("<I", 1000) + b"WAVE" +
        b"fmt " + struct.pack("<I", len(fmt_payload)) + fmt_payload +
        b"data" + struct.pack("<I", 960) + b"\x00" * 32
    )
    parsed = parse_wav_header(wav)
    assert parsed["sample_rate_hz"] == 16000 and parsed["channels"] == 1
    assert abs(parsed["data_size"] / parsed["byte_rate"] - 0.03) < 1.0e-9

    windows = select_windows([(30.0, 40.0), (100.0, 118.0), (180.0, 200.0)], 260.0)
    assert len(windows) == 3
    assert all(0.0 <= item["activity_fraction"] <= 1.0 for item in windows)
    print("AMI VAD microset discovery self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    result = discover()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "meeting": result["dataset"]["meeting"],
        "audio_lfs_sha256": result["audio"]["lfs_sha256"],
        "annotation_files": len(result["annotations"]["files"]),
        "duration_s": result["audio"]["duration_s"],
        "windows": result["window_plan"],
        "range_supported": result["audio"]["range_supported"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
