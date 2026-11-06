#!/usr/bin/env python3
"""Actual host Opus + public Runtime integration with an explicit simulated network.

The frozen experiment is a functional transport/Render contract, not an acoustic
quality evaluation, hardware timing measurement or production network stack.
"""
from __future__ import annotations

import argparse
import array
import ctypes as ct
import ctypes.util
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "validation/tools"))
from build_validation_corpus import (echo_from_render, interleave, mix,
                                    render_signal, speech_like)

EXPERIMENT = "FE-C2-INTERCOM-TRANSPORT-V1"
RATE, FRAME, PACKET_SAMPLES = 16000, 160, 320
PACKET_US, BUFFER_US, CAPACITY = 20000, 60000, 6
STARTUP_SAMPLES = (PACKET_US + BUFFER_US) * RATE // 1000000
SOURCE_SAMPLES = 96000
LOCAL_SAMPLES = SOURCE_SAMPLES + STARTUP_SAMPLES
LOCAL_FRAMES = LOCAL_SAMPLES // FRAME
MAX_PACKET_BYTES = 1275
BUDGET_SECONDS = 300
SCENARIOS = ("normal", "reorder", "duplicate", "single-loss", "burst-loss",
             "late", "gain-mute", "reopen")
BOUND_SOURCES = (
    "CMakeLists.txt", "validation/tools/build_validation_corpus.py",
    "tests/validation/frontend_evolution/dualmic_intercom_transport.py",
    "tests/validation/frontend_evolution/dualmic_intercom_runtime.c",
    "tests/validation/frontend_evolution/test_dualmic_intercom_transport.py",
    "docs/research/frontend-evolution-v1/DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md",
    "docs/research/frontend-evolution-v1/DUALMIC_INTERCOM_TRANSPORT_V1_PLAN.zh-CN.md",
    "docs/research/frontend-evolution-v1/DUALMIC_INTERCOM_TRANSPORT_V1_IDENTITY_CORRECTION.zh-CN.md",
)


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_binding(path: Path) -> dict:
    data = path.read_bytes()
    return {"sha256": sha(data), "size_bytes": len(data)}


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def pcm_bytes(samples: list[int]) -> bytes:
    require(sys.byteorder == "little", "this adapter requires a little-endian host")
    require(all(type(x) is int and -32768 <= x <= 32767 for x in samples), "invalid S16 PCM")
    return array.array("h", samples).tobytes()


def pcm_samples(data: bytes) -> list[int]:
    require(len(data) % 2 == 0, "truncated S16 sample")
    values = array.array("h")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tolist()


class Budget:
    def __init__(self, seconds: float = BUDGET_SECONDS):
        self.start = time.monotonic()
        self.seconds = seconds

    def check(self) -> None:
        require(time.monotonic() - self.start < self.seconds, "frozen 300 s budget exhausted")

    def timeout(self, maximum: float) -> float:
        self.check()
        return min(maximum, self.seconds - (time.monotonic() - self.start))


class _DlInfo(ct.Structure):
    _fields_ = [("filename", ct.c_char_p), ("base", ct.c_void_p),
                ("symbol", ct.c_char_p), ("address", ct.c_void_p)]


class OpusLibrary:
    """Minimal documented C API binding; real errors are never silent PCM."""
    SETTINGS = {4000: 2048, 4002: 24000, 4006: 0, 4010: 5,
                4012: 0, 4014: 0, 4016: 0}
    SETTING_NAMES = {4000: "application", 4002: "bitrate", 4006: "vbr",
                     4010: "complexity", 4012: "inband_fec",
                     4014: "packet_loss_perc", 4016: "dtx"}

    def __init__(self, requested: str | None = None):
        name = requested or ctypes.util.find_library("opus")
        require(bool(name), "actual libopus is unavailable")
        self.lib = ct.CDLL(name)
        lib = self.lib
        for prefix in ("encoder", "decoder"):
            create = getattr(lib, "opus_" + prefix + "_create")
            create.restype = ct.c_void_p
            create.argtypes = ([ct.c_int32, ct.c_int, ct.c_int, ct.POINTER(ct.c_int)]
                               if prefix == "encoder" else
                               [ct.c_int32, ct.c_int, ct.POINTER(ct.c_int)])
            destroy = getattr(lib, "opus_" + prefix + "_destroy")
            destroy.restype, destroy.argtypes = None, [ct.c_void_p]
        lib.opus_encode.restype = ct.c_int32
        lib.opus_encode.argtypes = [ct.c_void_p, ct.POINTER(ct.c_int16), ct.c_int,
                                   ct.POINTER(ct.c_ubyte), ct.c_int32]
        lib.opus_decode.restype = ct.c_int
        lib.opus_decode.argtypes = [ct.c_void_p, ct.POINTER(ct.c_ubyte), ct.c_int32,
                                   ct.POINTER(ct.c_int16), ct.c_int, ct.c_int]
        lib.opus_encoder_ctl.restype = ct.c_int
        lib.opus_encoder_ctl.argtypes = [ct.c_void_p, ct.c_int]
        lib.opus_packet_get_nb_samples.restype = ct.c_int
        lib.opus_packet_get_nb_samples.argtypes = [ct.POINTER(ct.c_ubyte), ct.c_int32, ct.c_int32]
        lib.opus_get_version_string.restype, lib.opus_get_version_string.argtypes = ct.c_char_p, []
        dynamic = ct.CDLL(None)
        dynamic.dladdr.argtypes = [ct.c_void_p, ct.POINTER(_DlInfo)]
        dynamic.dladdr.restype = ct.c_int
        info = _DlInfo()
        require(dynamic.dladdr(ct.cast(lib.opus_get_version_string, ct.c_void_p),
                               ct.byref(info)) != 0 and bool(info.filename),
                "cannot identify actual loaded libopus bytes")
        self.path = Path(info.filename.decode()).resolve(strict=True)
        if requested:
            require(Path(requested).resolve(strict=True) == self.path,
                    "requested libopus does not identify loaded library")
        self.identity = {"loaded_path": str(self.path), **file_binding(self.path),
                         "version": lib.opus_get_version_string().decode(),
                         "license_url": "https://www.opus-codec.org/license/"}
        copyright_file = Path("/usr/share/doc/libopus0/copyright")
        if copyright_file.is_file():
            self.identity["installed_copyright"] = {"path": str(copyright_file),
                                                     **file_binding(copyright_file)}

    def session(self):
        return OpusSession(self)


class OpusSession:
    def __init__(self, library: OpusLibrary):
        self.library = library
        self.encoder = self.decoder = None
        error = ct.c_int()
        self.encoder = library.lib.opus_encoder_create(RATE, 1, 2048, ct.byref(error))
        require(error.value == 0 and bool(self.encoder), f"opus encoder creation error {error.value}")
        try:
            self.decoder = library.lib.opus_decoder_create(RATE, 1, ct.byref(error))
            require(error.value == 0 and bool(self.decoder), f"opus decoder creation error {error.value}")
            self.settings = {}
            for request, value in library.SETTINGS.items():
                self._ctl(request, ct.c_int(value))
                actual = ct.c_int()
                self._ctl(request + 1, ct.byref(actual))
                require(actual.value == value, f"Opus effective setting mismatch {request}")
                self.settings[library.SETTING_NAMES[request]] = actual.value
            lookahead = ct.c_int()
            self._ctl(4027, ct.byref(lookahead))
            require(0 <= lookahead.value <= RATE, "invalid codec lookahead")
            self.settings.update({"sample_rate_hz": RATE, "channels": 1,
                                  "packet_samples": PACKET_SAMPLES,
                                  "lookahead_samples": lookahead.value})
        except Exception:
            self.close()
            raise

    def _ctl(self, request: int, argument) -> None:
        status = self.library.lib.opus_encoder_ctl(self.encoder, request, argument)
        require(status == 0, f"Opus CTL {request} error {status}")

    def encode(self, samples: list[int]) -> bytes:
        require(len(samples) == PACKET_SAMPLES, "codec input must be one complete 20 ms frame")
        pcm_bytes(samples)  # Reject invalid types/ranges before ctypes coercion.
        source = (ct.c_int16 * PACKET_SAMPLES)(*samples)
        encoded = (ct.c_ubyte * MAX_PACKET_BYTES)()
        count = self.library.lib.opus_encode(self.encoder, source, PACKET_SAMPLES,
                                             encoded, MAX_PACKET_BYTES)
        require(0 < count <= MAX_PACKET_BYTES, f"Opus encode error {count}")
        return bytes(encoded[:count])

    def decode(self, payload: bytes | None) -> list[int]:
        encoded = None
        if payload is not None:
            require(type(payload) is bytes and 0 < len(payload) <= MAX_PACKET_BYTES,
                    "invalid encoded packet length")
            encoded = (ct.c_ubyte * len(payload)).from_buffer_copy(payload)
            count = self.library.lib.opus_packet_get_nb_samples(encoded, len(payload), RATE)
            require(count == PACKET_SAMPLES, f"invalid Opus packet duration/error {count}")
        output = (ct.c_int16 * PACKET_SAMPLES)()
        count = self.library.lib.opus_decode(self.decoder, encoded,
                                             len(payload) if payload is not None else 0,
                                             output, PACKET_SAMPLES, 0)
        require(count == PACKET_SAMPLES, f"Opus decode/PLC error {count}")
        return list(output)

    def close(self) -> None:
        if self.encoder:
            self.library.lib.opus_encoder_destroy(self.encoder)
            self.encoder = None
        if self.decoder:
            self.library.lib.opus_decoder_destroy(self.decoder)
            self.decoder = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@dataclass(frozen=True)
class Arrival:
    time_us: int
    sequence: int
    payload: bytes


def arrival_schedule(packets: list[bytes], scenario: str) -> list[Arrival]:
    require(scenario in SCENARIOS, "unknown frozen scenario")
    events = []
    dropped = {100} if scenario == "single-loss" else {100, 101} if scenario == "burst-loss" else set()
    for sequence, payload in enumerate(packets):
        if sequence in dropped:
            continue
        delay = 50000 if scenario == "reorder" and sequence == 40 else (
                90000 if scenario == "late" and sequence == 100 else 10000)
        arrival = (sequence + 1) * PACKET_US + delay
        events.append(Arrival(arrival, sequence, payload))
        if scenario == "duplicate" and sequence == 70:
            events.append(Arrival(arrival + 1000, sequence, payload))
    return sorted(events, key=lambda event: (event.time_us, event.sequence))


def playout(packets: list[bytes], events: list[Arrival], decode,
            *, capacity: int = CAPACITY) -> tuple[list[int], dict, list[dict]]:
    """Bounded queue; only this scheduler determines decode order and PLC slots."""
    require(type(capacity) is int and capacity > 0, "invalid queue capacity")
    require(bool(packets), "empty packet stream")
    require(all(type(p) is bytes and 0 < len(p) <= MAX_PACKET_BYTES for p in packets),
            "invalid packet payload")
    for event in events:
        require(type(event.sequence) is int and 0 <= event.sequence < len(packets),
                "invalid packet sequence")
        require(type(event.time_us) is int and event.time_us >= (event.sequence + 1) * PACKET_US,
                "invalid simulated arrival time")
    events = sorted(events, key=lambda event: (event.time_us, event.sequence))
    queue, seen = {}, {}
    cursor, high_water, duplicate, late, plc = 0, 0, 0, 0, 0
    timeline = []
    samples = [0] * STARTUP_SAMPLES

    def arrive(event: Arrival, next_sequence: int) -> None:
        nonlocal high_water, duplicate, late
        action = "enqueued"
        if event.sequence in seen:
            require(seen[event.sequence] == event.payload, "conflicting duplicate packet")
            duplicate += 1
            action = "duplicate"
        else:
            require(event.payload == packets[event.sequence], "payload identity mismatch")
            seen[event.sequence] = event.payload
            if event.sequence < next_sequence:
                late += 1
                action = "late_discard"
            else:
                require(len(queue) < capacity, "bounded jitter queue full")
                queue[event.sequence] = event.payload
                high_water = max(high_water, len(queue))
        timeline.append({"kind": "arrival", "time_us": event.time_us,
                         "sequence": event.sequence, "action": action,
                         "queue_depth": len(queue), "payload_sha256": sha(event.payload)})

    for sequence in range(len(packets)):
        deadline = (sequence + 1) * PACKET_US + BUFFER_US
        while cursor < len(events) and events[cursor].time_us <= deadline:
            arrive(events[cursor], sequence)
            cursor += 1
        payload = queue.pop(sequence, None)
        decoded = decode(payload)
        require(len(decoded) == PACKET_SAMPLES, "decoder lost or appended samples")
        pcm_bytes(decoded)
        samples.extend(decoded)
        plc += payload is None
        timeline.append({"kind": "playout", "time_us": deadline, "sequence": sequence,
                         "action": "plc" if payload is None else "decode",
                         "samples": len(decoded), "queue_depth": len(queue),
                         "pcm_sha256": sha(pcm_bytes(decoded))})
    while cursor < len(events):
        arrive(events[cursor], len(packets))
        cursor += 1
    require(not queue, "queue retained packets after finite playout")
    stats = {"encoded_packets": len(packets), "arrival_events": len(events),
             "network_dropped_packets": len(packets) - len({e.sequence for e in events}),
             "duplicates": duplicate, "late_packets": late, "plc_packets": plc,
             "decoded_packets": len(packets) - plc, "queue_high_water": high_water,
             "queue_capacity": capacity, "startup_samples": STARTUP_SAMPLES,
             "playout_samples": len(samples), "decode_order": list(range(len(packets)))}
    return samples, stats, timeline


def check_counts(stats: dict, scenario: str, packet_count: int) -> None:
    loss = {"single-loss": 1, "burst-loss": 2}.get(scenario, 0)
    late = int(scenario == "late")
    duplicate = int(scenario == "duplicate")
    for key, value in {"encoded_packets": packet_count,
                       "network_dropped_packets": loss, "duplicates": duplicate,
                       "late_packets": late, "plc_packets": loss + late,
                       "decoded_packets": packet_count - loss - late,
                       "arrival_events": packet_count - loss + duplicate,
                       "playout_samples": packet_count * PACKET_SAMPLES + STARTUP_SAMPLES}.items():
        require(stats.get(key) == value, f"{scenario}: unexpected {key}")
    require(stats.get("decode_order") == list(range(packet_count)), "decode order/coverage mismatch")
    require(0 < stats.get("queue_high_water", 0) <= CAPACITY, "queue bound mismatch")


def transport(library: OpusLibrary, samples: list[int], scenario: str,
              directory: Path, budget: Budget) -> dict:
    require(len(samples) > 0 and len(samples) % PACKET_SAMPLES == 0,
            "codec stream must contain complete 20 ms packets")
    directory.mkdir()
    with library.session() as codec:
        packets = []
        for start in range(0, len(samples), PACKET_SAMPLES):
            budget.check()
            packets.append(codec.encode(samples[start:start + PACKET_SAMPLES]))
        schedule = arrival_schedule(packets, scenario)
        decoded, stats, timeline = playout(packets, schedule, codec.decode)
        settings = codec.settings
    check_counts(stats, scenario, len(packets))
    payload_bytes = bytearray()
    records = []
    for sequence, payload in enumerate(packets):
        records.append({"sequence": sequence, "offset": len(payload_bytes),
                        "payload_bytes": len(payload), "sha256": sha(payload)})
        payload_bytes.extend(struct.pack("<II", sequence, len(payload)))
        payload_bytes.extend(payload)
    (directory / "packets.bin").write_bytes(payload_bytes)
    (directory / "decoded.pcm").write_bytes(pcm_bytes(decoded))
    write_jsonl(directory / "packets.jsonl", records)
    write_jsonl(directory / "timeline.jsonl", timeline)
    report = {"settings": settings, "stats": stats,
              "input_samples": len(samples), "input_sha256": sha(pcm_bytes(samples)),
              "packets": file_binding(directory / "packets.bin"),
              "decoded_pcm": file_binding(directory / "decoded.pcm"),
              "simulated_network": True, "startup_buffer_trimmed": False,
              "codec_lookahead_tail_flushed": False,
              "unflushed_codec_tail_samples": settings["lookahead_samples"]}
    write_json(directory / "report.json", report)
    return {"samples": decoded, "packets": packets, "report": report}


def apply_playback(samples: list[int], scenario: str) -> list[int]:
    output = list(samples)
    if scenario == "gain-mute":
        output[200 * FRAME:240 * FRAME] = [0] * (40 * FRAME)
        output[240 * FRAME:320 * FRAME] = [int(value * 0.5) for value in output[240 * FRAME:320 * FRAME]]
    elif scenario == "reopen":
        output[300 * FRAME:302 * FRAME] = [0] * (2 * FRAME)
    return output


def require_reference(playback: bytes, consumed_render: bytes) -> None:
    require(playback == consumed_render, "Render is not exact post-PLC/post-volume playback PCM")


def validate_build(identity: dict, revision: str) -> None:
    require(identity.get("source_revision") == revision, "linked build source identity mismatch")
    require(identity.get("version") == "2.3.63" and identity.get("module_mask") == 1023
            and identity.get("fast_math") == 0 and identity.get("has_linux_runtime") == 1,
            "unexpected source version/module/runtime envelope")
    require(identity.get("effective_readback") is True
            and identity.get("readback_phase") == "post_init_before_worker",
            "effective post-init configuration readback missing")
    cfg = identity.get("config", {})
    tuning = identity.get("tuning", {})
    require(tuning.get("mask") == 15, "effective tuning readback is incomplete")
    for key, value in {"io_sample_rate_hz": RATE, "mic_channels": 2,
                       "aec_filter_ms": 96, "stages": 255}.items():
        require(cfg.get(key) == value, f"effective CALL {key} mismatch")
    for key, value in {"aec_mu": 0.22, "ns_floor": 0.12,
                       "agc_target_dbfs": -20.0, "limiter_dbfs": -2.0}.items():
        require(type(cfg.get(key)) in (int, float) and math.isfinite(cfg[key])
                and abs(cfg[key] - value) < 1e-7, f"effective CALL {key} mismatch")
        require(tuning.get(key) == cfg[key], "effective config/tuning readbacks disagree")


def verify_source(revision: str) -> dict:
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "source revision must be exact 40-hex")
    paths = subprocess.run(["git", "ls-files", "src", "include"], cwd=ROOT,
                           check=True, capture_output=True, text=True, timeout=30).stdout.splitlines()
    paths = sorted(set(paths) | set(BOUND_SOURCES))
    subprocess.run(["git", "diff", "--quiet", revision, "--", *paths], cwd=ROOT,
                   check=True, capture_output=True, timeout=30)
    bindings = {}
    for name in paths:
        original = subprocess.run(["git", "show", f"{revision}:{name}"], cwd=ROOT,
                                  check=True, capture_output=True, timeout=30).stdout
        require((ROOT / name).read_bytes() == original, f"unbound working source {name}")
        bindings[name] = {"sha256": sha(original), "size_bytes": len(original)}
    return bindings


def invoke_bridge(bridge: Path, case_dir: Path, mode: str, revision: str,
                  scenario: str, budget: Budget) -> dict:
    directory = case_dir / mode
    directory.mkdir()
    command = [str(bridge), mode, str(case_dir / "capture.pcm"),
               str(case_dir / "playback.pcm"), str(directory / "output.pcm"),
               str(directory / "consumed-render.pcm"), str(directory / "trace.jsonl"),
               str(directory / "report.json"), "302" if scenario == "reopen" else "0"]
    started = time.monotonic()
    write_json(directory / "command.json", command)
    try:
        result = subprocess.run(command, capture_output=True, timeout=budget.timeout(30))
    except subprocess.TimeoutExpired as exc:
        (directory / "stdout.log").write_bytes(exc.stdout or b"")
        (directory / "stderr.log").write_bytes(exc.stderr or b"")
        write_json(directory / "execution.json", {"returncode": None, "status": "TIMEOUT",
                                                    "elapsed_seconds": time.monotonic() - started})
        raise
    (directory / "stdout.log").write_bytes(result.stdout)
    (directory / "stderr.log").write_bytes(result.stderr)
    write_json(directory / "execution.json", {"returncode": result.returncode,
                                                "elapsed_seconds": time.monotonic() - started})
    require(result.returncode == 0, f"{mode} bridge failed with exit {result.returncode}")
    report = json.loads((directory / "report.json").read_text())
    require(report.get("status") == "PASS" and report.get("frames") == LOCAL_FRAMES,
            "bridge frame/status mismatch")
    validate_build(report.get("build", {}), revision)
    require(len((directory / "output.pcm").read_bytes()) == LOCAL_SAMPLES * 2, "output sample loss")
    require_reference((case_dir / "playback.pcm").read_bytes(),
                      (directory / "consumed-render.pcm").read_bytes())
    trace = [json.loads(line) for line in (directory / "trace.jsonl").read_text().splitlines()]
    require(len(trace) == LOCAL_FRAMES, "trace frame loss")
    for frame, row in enumerate(trace):
        require(row.get("frame") == frame and type(row.get("frame")) is int
                and row.get("quality") == 2 and row.get("render_present") is True,
                "non-contiguous/invalid worker trace")
        require(all(not isinstance(value, float) or math.isfinite(value) for value in row.values()),
                "non-finite worker telemetry")
        require(row.get("metadata_flags") == (72 if scenario == "reopen" and frame == 302 else 0)
                and row.get("timestamp_observations") == 0, "false hardware metadata")
    if mode == "runtime":
        counts = report["runtime"]
        for key in ("submitted_frames", "processed_frames"):
            require(counts.get(key) == LOCAL_FRAMES, "incomplete actual worker execution")
        for key in ("failed_frames", "input_full_events", "output_drop_events",
                    "render_push_failures", "capture_process_failures", "capture_gap_frames", "timestamp_frames"):
            require(counts.get(key) == 0, f"runtime {key} failure")
        require(counts.get("stream_discontinuities") == int(scenario == "reopen")
                and counts.get("render_gap_frames") == (2 if scenario == "reopen" else 0),
                "network PLC and playback discontinuity conflated")
        require(counts.get("overload_us") == 9000 and counts.get("recover_frames") == 1000,
                "runtime thresholds changed")
    return report


def run_case(name: str, scenario: str, library: OpusLibrary, bridge: Path,
             revision: str, output: Path, budget: Budget, *, future: bool = False,
             direct: bool = True) -> dict:
    directory = output / name
    directory.mkdir()
    far = render_signal(SOURCE_SAMPLES, 95931)
    if future:
        far[180 * PACKET_SAMPLES:] = [-x for x in far[180 * PACKET_SAMPLES:]]
    (directory / "far-source.pcm").write_bytes(pcm_bytes(far))
    down = transport(library, far, scenario, directory / "downlink", budget)
    playback = apply_playback(down["samples"], scenario)
    require(len(playback) == LOCAL_SAMPLES, "local playout length mismatch")
    near, _ = speech_like(LOCAL_FRAMES, 95932, [(0.7, 1.6), (2.4, 3.4), (4.4, 5.5)], amplitude=4500.0)
    if future:
        near[368 * FRAME:] = [-x for x in near[368 * FRAME:]]
    left = mix(near, echo_from_render(playback, [(320, 0.5), (640, 0.2)]))
    right = mix(near, echo_from_render(playback, [(321, 0.47), (641, 0.19)]))
    capture = interleave(left, right)
    (directory / "near-source.pcm").write_bytes(pcm_bytes(near))
    (directory / "capture.pcm").write_bytes(pcm_bytes(capture))
    (directory / "playback.pcm").write_bytes(pcm_bytes(playback))
    runtime = invoke_bridge(bridge, directory, "runtime", revision, scenario, budget)
    comparison = None
    if direct:
        invoke_bridge(bridge, directory, "direct", revision, scenario, budget)
        comparison = {}
        for filename in ("output.pcm", "trace.jsonl", "consumed-render.pcm"):
            comparison[filename] = ((directory / "runtime" / filename).read_bytes()
                                    == (directory / "direct" / filename).read_bytes())
        require(all(comparison.values()), "Runtime/public synchronous API control differs")
    uplink_input = pcm_samples((directory / "runtime/output.pcm").read_bytes())
    up = transport(library, uplink_input, scenario, directory / "uplink", budget)
    report = {"case": name, "scenario": scenario, "status": "PASS",
              "capture_frames": LOCAL_FRAMES, "capture_mic_channels": 2,
              "downlink": down["report"], "uplink": up["report"],
              "worker": runtime, "public_api_comparison": comparison,
              "render_binding": file_binding(directory / "playback.pcm"),
              "runtime_output": file_binding(directory / "runtime/output.pcm"),
              "simulated_playback_reopen": scenario == "reopen"}
    write_json(directory / "case-report.json", report)
    return report


def check_controls(output: Path) -> dict:
    normal, repeat, future = (output / name for name in ("normal", "normal-repeat", "normal-future"))
    repeated = ("capture.pcm", "playback.pcm", "runtime/output.pcm", "runtime/trace.jsonl",
                "downlink/packets.bin", "downlink/decoded.pcm", "downlink/timeline.jsonl",
                "uplink/packets.bin", "uplink/decoded.pcm", "uplink/timeline.jsonl")
    repeat_results = {name: (normal / name).read_bytes() == (repeat / name).read_bytes() for name in repeated}
    require(all(repeat_results.values()), "same-input deterministic replay differs")
    prefixes = {"capture.pcm": 368 * FRAME * 4, "playback.pcm": 368 * FRAME * 2,
                "runtime/output.pcm": 368 * FRAME * 2,
                "uplink/decoded.pcm": 376 * FRAME * 2}
    prefix_results = {name: (normal / name).read_bytes()[:count] == (future / name).read_bytes()[:count]
                      for name, count in prefixes.items()}
    for direction, count in (("downlink", 180), ("uplink", 184)):
        a = (normal / direction / "packets.jsonl").read_text().splitlines()
        b = (future / direction / "packets.jsonl").read_text().splitlines()
        prefix_results[direction + "_packets"] = a[:count] == b[:count]
    require(all(prefix_results.values()), "different-future prefix changed")
    require((normal / "capture.pcm").read_bytes() != (future / "capture.pcm").read_bytes(),
            "future control did not actually alter input")
    rejected = {}
    pairs = {"pre_volume_reference": (output / "gain-mute/playback.pcm", output / "gain-mute/downlink/decoded.pcm"),
             "pre_plc_reference": (output / "single-loss/playback.pcm", output / "normal/playback.pcm")}
    for name, (real, wrong) in pairs.items():
        try:
            require_reference(real.read_bytes(), wrong.read_bytes())
        except ContractError:
            rejected[name] = True
        else:
            raise ContractError(f"wrong {name} accepted")
    return {"repeat": repeat_results, "future_prefix": prefix_results,
            "negative_real_render_references_rejected": rejected}


def artifact_manifest(output: Path) -> dict:
    return {"files": {str(path.relative_to(output)): file_binding(path)
                       for path in sorted(output.rglob("*"))
                       if path.is_file() and path.name != "artifact-manifest.json"}}


def run(bridge: Path, revision: str, output: Path, library_path: str | None = None) -> dict:
    budget = Budget()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "experiment": EXPERIMENT,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_revision": revision, "result": "FAIL", "cases": [], "failures": [],
              "quality_decision": "NOT_EVALUATED", "data_role": "engineering-regression",
              "simulated_network": True, "actual_host_runtime": True,
              "physical_device": "NOT_RUN", "human_listening": "NOT_RUN", "real_WAN": "NOT_RUN",
              "mouth_to_ear_latency": None, "promotion_allowed": False,
              "budget_seconds": BUDGET_SECONDS}
    try:
        require(sys.byteorder == "little", "only little-endian host is admitted")
        bridge = bridge.resolve(strict=True)
        bindings = verify_source(revision)
        report["source_files"] = bindings
        report["bridge"] = {"path": str(bridge), **file_binding(bridge)}
        info = subprocess.run([str(bridge), "--identity"], check=True, capture_output=True,
                              text=True, timeout=budget.timeout(30))
        report["build"] = json.loads(info.stdout)
        validate_build(report["build"], revision)
        library = OpusLibrary(library_path)
        report["opus"] = library.identity
        write_json(output / "progress.json", report)
        for scenario in SCENARIOS:
            budget.check()
            report["cases"].append(run_case(scenario, scenario, library, bridge, revision, output, budget))
            write_json(output / "progress.json", report)
        for name, future in (("normal-repeat", False), ("normal-future", True)):
            budget.check()
            report["cases"].append(run_case(name, "normal", library, bridge, revision,
                                            output, budget, future=future, direct=False))
            write_json(output / "progress.json", report)
        report["controls"] = check_controls(output)
        require(verify_source(revision) == bindings, "source changed during run")
        require(file_binding(bridge) == {key: report["bridge"][key] for key in ("sha256", "size_bytes")},
                "bridge bytes changed during run")
        require(file_binding(library.path) == {key: library.identity[key] for key in ("sha256", "size_bytes")},
                "libopus bytes changed during run")
        report["matrix_cases"] = len(SCENARIOS)
        report["control_runs"] = 2
        report["public_api_control_runs"] = 8
        report["actual_runtime_frames"] = 10 * LOCAL_FRAMES
        report["actual_direct_api_frames"] = 8 * LOCAL_FRAMES
        report["latency_components"] = {
            "unit": "ms", "per_direction_packet_collection_max": 20,
            "simulated_buffer_after_packet_ready": 60,
            "first_packet_playout_start": 80,
            "opus_added_delay": report["cases"][0]["downlink"]["settings"]["lookahead_samples"] * 1000 / RATE,
            "frontend_algorithmic": report["cases"][0]["worker"]["algorithmic_latency_ms"],
            "actual_device_network_io": None,
            "note": "Logical components; no physical mouth-to-ear measurement or claim."}
        budget.check()
        report["result"] = "HOST_INTEGRATION_COMPLETE"
    except Exception as exc:
        report["failures"].append({"type": type(exc).__name__, "message": str(exc)})
    report["elapsed_seconds"] = time.monotonic() - budget.start
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "report.json", report)
    write_json(output / "artifact-manifest.json", artifact_manifest(output))
    # Sealing belongs to this run's original wall-clock budget.
    if time.monotonic() - budget.start >= budget.seconds:
        report["result"] = "FAIL"
        report["failures"].append({"type": "BudgetExceeded", "message": "300 s including evidence sealing exceeded"})
        report["elapsed_seconds"] = time.monotonic() - budget.start
        write_json(output / "report.json", report)
        write_json(output / "artifact-manifest.json", artifact_manifest(output))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--opus-library")
    args = parser.parse_args()
    report = run(args.bridge, args.source_revision, args.output, args.opus_library)
    print(json.dumps({"result": report["result"], "cases": len(report["cases"]),
                      "elapsed_seconds": report["elapsed_seconds"], "failures": report["failures"]},
                     sort_keys=True))
    return 0 if report["result"] == "HOST_INTEGRATION_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
