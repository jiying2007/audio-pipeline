#!/usr/bin/env python3
"""Build S003 cross-source artifact-exclusion cases from frozen dEchorate RIRs.

Authority: candidate-zero research-development diagnostics only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

import h5py
import numpy as np

from build_validation_corpus import (
    FRAME,
    RATE,
    clamp16,
    delayed,
    interleave,
    mix,
    noise,
    nonstationary_noise,
    rotate,
    scale,
    speech_like,
    write_pcm,
)

ROOM_RE = re.compile(r"_room([0-9]{6})_")
REFERENCE_ROOM = "000000"
TARGET_RMS = 3500.0
STAGE_INDEX = {
    "prefix-raw": -1,
    "prefix-capture": 0,
    "prefix-bf": 1,
    "prefix-ns": 5,
    "prefix-agc": 6,
    "default": 8,
}
FAILURE_PROFILES = {
    "capture-clipping": [
        "prefix-raw", "prefix-capture", "prefix-ns", "prefix-agc", "default"
    ],
    "mic-gain-delay-mismatch": [
        "prefix-raw", "prefix-capture", "prefix-bf", "prefix-ns",
        "prefix-agc", "default",
    ],
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _dataset(handle: h5py.File, *names: str) -> np.ndarray:
    for name in names:
        if name in handle:
            return np.asarray(handle[name])
    raise KeyError(f"missing SOFA dataset; tried {names}")


def load_frozen_rirs(input_dir: Path, qualification: dict) -> dict[str, np.ndarray]:
    objects = [
        item
        for item in qualification["inventory_protocol"]["expected_selected_objects"]
        if item["name"].endswith(".sofa")
    ]
    require(len(objects) == 11, "expected exactly 11 frozen SOFA objects")
    rooms: dict[str, np.ndarray] = {}
    for item in objects:
        path = input_dir / item["name"]
        data = path.read_bytes()
        require(len(data) == int(item["size_bytes"]), f"size drift: {path.name}")
        require(sha256_bytes(data) == item["sha256"], f"sha256 drift: {path.name}")
        match = ROOM_RE.search(path.name)
        require(match is not None, f"room token missing: {path.name}")
        room = match.group(1)
        with h5py.File(path, "r") as handle:
            ir = _dataset(handle, "Data.IR", "Data_IR")
            if ir.ndim == 3 and ir.shape[0] == 1:
                ir = ir[0]
            require(ir.ndim == 2 and ir.shape[0] == 5, f"unexpected RIR shape {ir.shape}")
            fs = _dataset(handle, "Data.SamplingRate", "Data_SamplingRate").reshape(-1)
            require(fs.size == 1 and float(fs[0]) == 48000.0, "dEchorate sampling-rate drift")
            require(np.isfinite(ir).all(), "non-finite dEchorate RIR")
            rooms[room] = np.asarray(ir[:2], dtype=np.float64)
    require(len(rooms) == 11 and REFERENCE_ROOM in rooms, "room coverage drift")
    return rooms


def resample_rir_48k_to_16k(rir: np.ndarray) -> np.ndarray:
    require(rir.ndim == 1 and rir.size >= 16, "invalid RIR vector")
    source_x = np.arange(rir.size, dtype=np.float64)
    target_size = max(1, int(math.ceil(rir.size / 3.0)))
    target_x = np.arange(target_size, dtype=np.float64) * 3.0
    out = np.interp(target_x, source_x, rir)
    require(np.isfinite(out).all(), "non-finite resampled RIR")
    return out


def fft_convolve_same(signal: list[int], rir: np.ndarray) -> np.ndarray:
    x = np.asarray(signal, dtype=np.float64)
    h = np.asarray(rir, dtype=np.float64)
    require(x.size > 0 and h.size > 0, "empty convolution input")
    total = x.size + h.size - 1
    nfft = 1 << (total - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(h, nfft), nfft)
    return np.asarray(y[:x.size], dtype=np.float64)


def rms_float(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(values * values)))


def pcm(values: np.ndarray, gain: float) -> list[int]:
    return [clamp16(float(value) * gain) for value in values]


def hard_clip(values: list[int], limit: int) -> list[int]:
    return [max(-limit, min(limit, int(value))) for value in values]


def write_clean(path: Path, samples: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_pcm(path, samples)


def build(
    input_dir: Path,
    qualification_manifest: Path,
    output: Path,
    seed: int,
    seconds: float,
) -> dict:
    qualification = json.loads(qualification_manifest.read_text(encoding="utf-8"))
    require(qualification["authority"] == "SOURCE_QUALIFICATION_ONLY", "source authority drift")
    require(qualification["candidate_budget"] == 0, "source candidate authority drift")
    require(
        qualification["inventory_protocol"]["expected_selected_fingerprint_sha256"]
        == "7e5077c77e9700699eedd27d76357a820bcae2f14ee5f211a7afdb0ae2620953",
        "frozen dEchorate fingerprint drift",
    )
    rooms = load_frozen_rirs(input_dir, qualification)

    frames = max(600, int(round(seconds * 100.0)))
    active = [(0.55, 1.75), (2.35, min(seconds - 0.35, 4.75))]
    excitation, _labels = speech_like(frames, seed + 1, active, amplitude=9000.0)
    sample_count = len(excitation)
    rir16 = {
        room: np.stack([
            resample_rir_48k_to_16k(rirs[0]),
            resample_rir_48k_to_16k(rirs[1]),
        ])
        for room, rirs in rooms.items()
    }
    acoustic_float = {
        room: [
            fft_convolve_same(excitation, rir16[room][0]),
            fft_convolve_same(excitation, rir16[room][1]),
        ]
        for room in sorted(rir16)
    }

    ref_rms = rms_float(acoustic_float[REFERENCE_ROOM][0])
    require(math.isfinite(ref_rms) and ref_rms > 1.0e-12, "reference room is silent")
    global_gain = TARGET_RMS / ref_rms
    require(math.isfinite(global_gain) and global_gain > 0.0, "invalid global gain")

    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    noise_nonstationary = nonstationary_noise(sample_count, seed + 101, 6000.0)
    mismatch_noise = noise(sample_count, seed + 202, 2200.0)

    room_manifest: list[dict] = []
    for room in sorted(acoustic_float):
        clean0 = pcm(acoustic_float[room][0], global_gain)
        clean1 = pcm(acoustic_float[room][1], global_gain)
        room_dir = output / "rooms" / room
        write_clean(room_dir / "clean-mic0.pcm", clean0)
        write_clean(room_dir / "clean-mic1.pcm", clean1)

        pre_clip_fraction = sum(abs(v) >= 32760 for v in clean0) / max(1, len(clean0))
        room_manifest.append({
            "room": room,
            "clean_mic0_rms": math.sqrt(sum(float(v) * v for v in clean0) / len(clean0)),
            "clean_mic0_clip_fraction": pre_clip_fraction,
        })

        clipping_mic = hard_clip(
            mix(clean0, scale(noise_nonstationary, 0.35)), 7000
        )
        clip_dir = room_dir / "capture-clipping"
        write_clean(clip_dir / "mic.pcm", clipping_mic)
        for profile in FAILURE_PROFILES["capture-clipping"]:
            case_id = f"capture-clipping-room{room}--{profile}"
            cases.append({
                "case_id": case_id,
                "split": "dev",
                "scenario": "s003-cross-source-capture-clipping",
                "sample_rate_hz": RATE,
                "mic_channels": 1,
                "mic_audio": str((clip_dir / "mic.pcm").relative_to(output)),
                "render_audio": None,
                "clean_near_audio": str((room_dir / "clean-mic0.pcm").relative_to(output)),
                "echo_audio": None,
                "vad_labels": None,
                "control": {},
                "processor_profile": profile,
                "expected": {},
                "dimensions": {
                    "base_case_id": f"capture-clipping-room{room}",
                    "durable_failure_id": "FR-S003-CAPTURE-CLIPPING-V1",
                    "failure_kind": "capture-clipping",
                    "room": room,
                    "source_family": "dechorate-measured-rir",
                    "stage_profile": profile,
                    "stage_index": STAGE_INDEX[profile],
                    "clip_limit": 7000,
                    "noise_scale": 0.35,
                },
                "source": {
                    "dataset_id": "dechorate-measured-rir",
                    "room": room,
                    "authority": "candidate-zero-research-development",
                },
            })

        left = mix(clean0, scale(mismatch_noise, 0.25))
        right = mix(
            scale(delayed(clean1, 3), 0.72),
            scale(rotate(mismatch_noise, 137), 0.38),
        )
        mismatch_dir = room_dir / "mic-gain-delay-mismatch"
        write_clean(mismatch_dir / "mic-stereo.pcm", interleave(left, right))
        for profile in FAILURE_PROFILES["mic-gain-delay-mismatch"]:
            case_id = f"mic-gain-delay-mismatch-room{room}--{profile}"
            cases.append({
                "case_id": case_id,
                "split": "dev",
                "scenario": "s003-cross-source-mic-gain-delay-mismatch",
                "sample_rate_hz": RATE,
                "mic_channels": 2,
                "mic_audio": str((mismatch_dir / "mic-stereo.pcm").relative_to(output)),
                "render_audio": None,
                "clean_near_audio": str((room_dir / "clean-mic0.pcm").relative_to(output)),
                "echo_audio": None,
                "vad_labels": None,
                "control": {},
                "processor_profile": profile,
                "expected": {},
                "dimensions": {
                    "base_case_id": f"mic-gain-delay-mismatch-room{room}",
                    "durable_failure_id": "FR-S003-MIC-GAIN-DELAY-MISMATCH-V1",
                    "failure_kind": "mic-gain-delay-mismatch",
                    "room": room,
                    "source_family": "dechorate-measured-rir",
                    "stage_profile": profile,
                    "stage_index": STAGE_INDEX[profile],
                    "right_gain": 0.72,
                    "right_delay_samples": 3,
                    "left_noise_scale": 0.25,
                    "right_noise_scale": 0.38,
                },
                "source": {
                    "dataset_id": "dechorate-measured-rir",
                    "room": room,
                    "authority": "candidate-zero-research-development",
                },
            })

    require(len(cases) == 11 * (5 + 6), f"unexpected case count: {len(cases)}")
    selected_objects = [
        item
        for item in qualification["inventory_protocol"]["expected_selected_objects"]
        if item["name"].endswith(".sofa")
    ]
    source_manifest = {
        "schema_version": 1,
        "dataset_id": "dechorate-measured-rir",
        "license": qualification["source"]["license"],
        "qualification_manifest": str(qualification_manifest),
        "qualification_manifest_sha256": sha256_bytes(qualification_manifest.read_bytes()),
        "selected_fingerprint_sha256": qualification["inventory_protocol"][
            "expected_selected_fingerprint_sha256"
        ],
        "objects": [
            {
                "name": item["name"],
                "size_bytes": int(item["size_bytes"]),
                "sha256": item["sha256"],
            }
            for item in selected_objects
        ],
    }
    source_manifest_path = output / "source-manifest.json"
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\\n", encoding="utf-8"
    )
    corpus = {
        "schema_version": 1,
        "corpus_id": f"s003-dechorate-artifact-exclusion-seed-{seed}",
        "tier": "research-validation",
        "generator": {
            "name": "build_dechorate_artifact_exclusion_corpus.py",
            "version": 1,
            "seed": seed,
            "seconds": frames / 100.0,
        },
        "sources": ["dechorate-measured-rir"],
        "sealed_data": True,
        "source_manifest_sha256": sha256_bytes(source_manifest_path.read_bytes()),
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "promotion_allowed": False,
        "shipping_change_allowed": False,
        "level_calibration": {
            "reference_room": REFERENCE_ROOM,
            "target_rms": TARGET_RMS,
            "global_gain": global_gain,
            "per_room_normalization": False,
        },
        "room_manifest": room_manifest,
        "cases": cases,
    }
    (output / "corpus.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def self_test() -> None:
    assert STAGE_INDEX["prefix-raw"] < STAGE_INDEX["prefix-capture"]
    assert len(FAILURE_PROFILES["capture-clipping"]) == 5
    assert len(FAILURE_PROFILES["mic-gain-delay-mismatch"]) == 6
    impulse = np.zeros(48, dtype=np.float64)
    impulse[3] = 1.0
    down = resample_rir_48k_to_16k(impulse)
    assert down.size == 16 and abs(float(down[1]) - 1.0) < 1.0e-12
    x = [1000, 0, 0, 0]
    y = fft_convolve_same(x, np.asarray([1.0, 0.5]))
    assert y.shape == (4,) and abs(float(y[0]) - 1000.0) < 1.0e-6
    print("dEchorate artifact-exclusion corpus self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--qualification-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=8307)
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if None in (args.input_dir, args.qualification_manifest, args.output):
        parser.error("--input-dir, --qualification-manifest and --output are required")
    if not 6.0 <= args.seconds <= 12.0:
        parser.error("--seconds must be within 6..12")
    corpus = build(
        args.input_dir,
        args.qualification_manifest,
        args.output,
        args.seed,
        args.seconds,
    )
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "cases": len(corpus["cases"]),
        "rooms": len(corpus["room_manifest"]),
        "seed": args.seed,
        "global_gain": corpus["level_calibration"]["global_gain"],
        "source_manifest": str(args.output / "source-manifest.json"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
