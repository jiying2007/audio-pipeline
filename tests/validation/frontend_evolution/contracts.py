#!/usr/bin/env python3
"""Research admission and adapter contracts; not an acoustic evaluator or SDK.

No external process is launched here. Effects still use validation/tools and its
canonical authority. A contract PASS is not an acoustic or silicon PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT / "docs/research/frontend-evolution-v1"
B0 = "37a1792861a89c815bec462f819f3deac7d29b09"
ARCHIVE_SHA256 = {
    "PLAN.zh-CN.md": "7ac18a4e608db4514eeb42f98b31c4c61c280b73bd98731473bf8701897e6383",
    "TASKS.json": "3cfc45a99e268b32d185cc44f499a394d531da2bb759c69b780a10d7632f7b20",
}
RIGHTS = ("code", "dependencies", "weights", "data", "redistribution")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def positive_int(value: int, name: str, maximum: int) -> None:
    require(type(value) is int and 0 < value <= maximum, f"invalid {name}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hex_digest(value: str, length: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def load_json(path: Path) -> dict:
    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value: {value}")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                       parse_constant=constant)
    require(isinstance(value, dict), "expected JSON object")
    return value


def check_archive(directory: Path = ARCHIVE) -> dict:
    for name, expected in ARCHIVE_SHA256.items():
        require(sha256((directory / name).read_bytes()) == expected, f"approved archive drift: {name}")
    sums = "".join(f"{value}  {name}\n" for name, value in ARCHIVE_SHA256.items())
    require((directory / "SHA256SUMS").read_text() == sums, "archive checksum manifest drift")
    tasks = load_json(directory / "TASKS.json")
    require(tasks["baseline_source"] == B0, "B0 changed")
    require(tasks["status"] == "PLAN_ONLY_NOT_EXECUTED", "proposal is not execution evidence")
    graph = {task["id"]: task["depends_on"] for task in tasks["tasks"]}
    require(set(graph) == {f"FE{i:02d}" for i in range(10)}, "work package set changed")
    visited, active = set(), set()
    def visit(name: str) -> None:
        require(name in graph and name not in active, "missing dependency or cycle")
        if name in visited:
            return
        active.add(name)
        for dep in graph[name]:
            visit(dep)
        active.remove(name)
        visited.add(name)
    for name in graph:
        visit(name)
    return tasks


def check_catalog(catalog: dict) -> None:
    require(catalog.get("schema_version") == 1, "unsupported catalog version")
    require(catalog.get("stage") == "frontend-evolution-v1", "wrong research stage")
    require(catalog.get("baseline_source") == B0, "wrong research baseline")
    seen = set()
    for source in catalog["sources"]:
        key = source["id"]
        require(isinstance(key, str) and key not in seen, "duplicate source id")
        seen.add(key)
        parsed = urlparse(source["url"])
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username,
                "source URL must be public HTTPS without credentials")
        state = source["status"]
        require(state in {"PLANNED", "PINNED_PENDING_REVIEW", "REFERENCE_REVIEW_ONLY", "EXECUTION_ADMITTED"},
                "invalid source state")
        commit = source["commit"]
        require(commit is None or hex_digest(commit, 40), "full source commit required")
        if state != "PLANNED":
            require(hex_digest(commit, 40), "pinned source missing commit")
        rights = source["rights"]
        require(set(rights) == set(RIGHTS), "five separate rights dispositions required")
        for value in rights.values():
            require(value in {"PENDING", "ALLOWED", "NOT_APPLICABLE", "RESTRICTED"}, "invalid rights disposition")
        if state == "EXECUTION_ADMITTED":
            require(rights["code"] == "ALLOWED" and rights["dependencies"] != "PENDING",
                    "code/dependency rights not reviewed")
            require(all(value in {"ALLOWED", "NOT_APPLICABLE"} for value in rights.values()),
                    "unresolved/restricted rights cannot admit execution")
            require(hex_digest(source.get("admission_receipt_sha256")), "review receipt required")
            require(hex_digest(source.get("materialized_source_sha256")), "materialized source hash required")


def admit_execution(catalog: dict, source_id: str) -> dict:
    check_catalog(catalog)
    matches = [s for s in catalog["sources"] if s["id"] == source_id]
    require(len(matches) == 1 and matches[0]["status"] == "EXECUTION_ADMITTED",
            "reference is not admitted for execution")
    return matches[0]


@dataclass(frozen=True)
class FrameContract:
    sample_rate: int
    mic_count: int
    render_count: int
    native_hop: int
    channel_map: tuple[int, ...]
    encoding: str = "s16le"
    layout: str = "interleaved"

    def __post_init__(self) -> None:
        require(type(self.sample_rate) is int and self.sample_rate in (8000, 16000, 24000, 32000, 48000),
                "unsupported sample rate")
        require(type(self.mic_count) is int and self.mic_count in (1, 2, 4), "mic count must be 1/2/4")
        require(type(self.render_count) is int and 0 <= self.render_count <= 2, "invalid render count")
        positive_int(self.native_hop, "native hop", self.sample_rate)
        require(self.encoding in ("s16le", "f32le") and self.layout == "interleaved",
                "unsupported PCM contract; conversion must be explicit")
        require(isinstance(self.channel_map, tuple) and len(self.channel_map) == self.mic_count
                and all(type(x) is int for x in self.channel_map)
                and sorted(self.channel_map) == list(range(self.mic_count)), "invalid microphone channel map")

    @property
    def outer_hop(self) -> int:
        return self.sample_rate // 100

    @property
    def channels(self) -> int:
        return self.mic_count + self.render_count

    @property
    def sample_bytes(self) -> int:
        return 2 if self.encoding == "s16le" else 4

    def pcm(self, payload: bytes, channels: int) -> int:
        require(type(payload) is bytes, "PCM must be bytes")
        positive_int(channels, "PCM channels", 6)
        require(len(payload) % (channels * self.sample_bytes) == 0, "partial PCM sample frame")
        if self.encoding == "f32le":
            require(all(math.isfinite(x[0]) and abs(x[0]) <= 1 for x in struct.iter_unpack("<f", payload)),
                    "non-finite or unnormalized float PCM")
        return len(payload) // (channels * self.sample_bytes)


class Reblocker:
    """10 ms interleaved input to native hops; no normalization or hidden padding.

This is an offline Python adapter primitive, not allocation-free shipping code.
Mic channels precede separately counted render channels. Byte order is preserved;
channel_map describes the frozen route and is not silently applied here.
"""
    def __init__(self, contract: FrameContract):
        self.contract = contract
        self.pending = bytearray()
        self.high_water_sample_frames = 0
        self.input_sample_frames = 0
        self.output_sample_frames = 0

    def push(self, payload: bytes) -> list[bytes]:
        c = self.contract
        count = c.pcm(payload, c.channels)
        require(count == c.outer_hop, "exact 10 ms input required")
        self.pending.extend(payload)
        self.input_sample_frames += count
        stride = c.sample_bytes * c.channels
        self.high_water_sample_frames = max(self.high_water_sample_frames, len(self.pending) // stride)
        require(self.high_water_sample_frames <= c.native_hop - 1 + c.outer_hop, "FIFO bound exceeded")
        result = []
        size = c.native_hop * stride
        while len(self.pending) >= size:
            result.append(bytes(self.pending[:size]))
            del self.pending[:size]
            self.output_sample_frames += c.native_hop
        return result

    def finish(self) -> None:
        require(not self.pending, "incomplete native hop: explicit tail policy required")
        require(self.input_sample_frames == self.output_sample_frames, "sample accounting mismatch")


def verified_file(root: Path, relative: str) -> Path:
    path = Path(relative)
    require(not path.is_absolute() and path.parts and ".." not in path.parts, "unsafe output path")
    resolved_root = root.resolve()
    current = root
    for component in path.parts:
        current = current / component
        require(not current.is_symlink(), "symlink output forbidden")
    require(current.resolve().is_relative_to(resolved_root) and current.is_file(), "missing output")
    return current


def check_outputs(expected: dict, results: list[dict], root: Path,
                  contract: FrameContract, identity: dict) -> dict:
    """Validate receipts before calling the canonical evaluator; no quality score."""
    require(bool(expected) and len(results) == len(expected), "partial/empty execution")
    require(set(identity) == {"source_sha", "config_sha256", "processor_sha256", "evaluator_sha256"},
            "incomplete frozen identity")
    require(hex_digest(identity["source_sha"], 40)
            and all(hex_digest(v) for k, v in identity.items() if k != "source_sha"), "invalid frozen identity")
    seen, outputs = set(), set()
    for item in results:
        key = item["case_id"]
        require(key in expected and key not in seen, "unknown or duplicate case")
        seen.add(key)
        require(type(item["exit_code"]) is int and item["exit_code"] == 0
                and item["status"] == "SUCCESS", "case execution failed")
        require(item["identity"] == identity, "stale processor/config/source/evaluator")
        spec = expected[key]
        require(item["input_sha256"] == spec["input_sha256"]
                and hex_digest(item["input_sha256"]), "wrong input identity")
        positive_int(spec["output_samples"], "output samples", contract.sample_rate * 3600)
        path = verified_file(root, item["output_path"])
        require(path.resolve() not in outputs, "cases share one output")
        outputs.add(path.resolve())
        expected_bytes = spec["output_samples"] * contract.sample_bytes
        require(path.stat().st_size == expected_bytes, "lost/extra output samples")
        data = path.read_bytes()
        require(contract.pcm(data, 1) == spec["output_samples"], "invalid mono output")
        require(sha256(data) == item["output_sha256"], "output digest mismatch")
        require(type(spec["require_nonzero"]) is bool, "missing silence expectation")
        if spec["require_nonzero"]:
            fmt = "<h" if contract.encoding == "s16le" else "<f"
            require(any(x[0] != 0 for x in struct.iter_unpack(fmt, data)), "unexpected all-silence output")
    return {"status": "OUTPUT_CONTRACT_PASS", "cases": len(seen), "acoustic_authority": False}


def check_prefix_causality(a: list[float], b: list[float], ya: list[float], yb: list[float],
                           prefix_samples: int, delay_samples: int = 0,
                           lookahead_samples: int = 0) -> int:
    """Check mono equal-length input/output with preregistered sample latency.

Output index j may depend on inputs through j-delay+lookahead. Stable output
therefore ends before prefix+delay-lookahead, not an optimised per-case alignment.
This is a finite prefix test, not a proof covering every possible input.
"""
    require(len(a) == len(b) == len(ya) == len(yb), "input/output length mismatch")
    positive_int(prefix_samples, "prefix", len(a) - 1)
    require(type(delay_samples) is int and type(lookahead_samples) is int
            and 0 <= delay_samples < prefix_samples and 0 <= lookahead_samples < prefix_samples,
            "invalid preregistered delay/lookahead")
    require(all(math.isfinite(x) for values in (a, b, ya, yb) for x in values), "non-finite causality input")
    require(a[:prefix_samples] == b[:prefix_samples] and a[prefix_samples:] != b[prefix_samples:],
            "test requires identical past and different future")
    stop = min(len(ya), prefix_samples + delay_samples - lookahead_samples)
    require(stop > 0, "no causality coverage")
    require(ya[:stop] == yb[:stop], "future information changed stable output prefix")
    return stop
