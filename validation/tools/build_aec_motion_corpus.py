#!/usr/bin/env python3
"""Build the canonical deterministic continuous-motion AEC development corpus.

The model represents a rigid on-device speaker/microphone pair in a rectangular
room. Device I/O plus the acoustic direct path is fixed at 42 ms, while six
first-order wall reflections vary under quasi-static translation/rotation. The
render probes are deterministic colored broadband signals, one with a smooth
speech-like amplitude envelope. They are not recorded speech, measured RIRs, or
DUT evidence.

This corpus is always regression/development authority. It can expose AEC/sync
failure modes and support bounded candidate development, but it cannot authorize
shipping, HIL, Extended Real, or Product Certification.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import random
import tempfile
from pathlib import Path

RATE = 16000
FRAME = RATE // 100
DEFAULT_SECONDS = 8.0
GENERATOR_VERSION = 2
DATASET_ID = "deterministic-aec-motion-geometry-v2"
MODEL = {
    "sample_rate_hz": RATE,
    "direct_total_delay_ms": 42.0,
    "nominal_reference_delay_ms": 40.0,
    "speaker_mic_distance_m": 0.08,
    "room_dimensions_m": [6.0, 5.0, 2.8],
    "speed_of_sound_m_s": 343.0,
    "paths": "direct plus six first-order wall images",
    "approximation": "quasi-static moving geometry; linear fractional-delay interpolation; no full wave model, diffuse late tail, nonlinear transducer or real DUT",
    "excitation": ["colored-broadband", "speech-envelope-broadband"],
    "motion": ["stationary", "translation", "rotation"],
    "direct_gain": [0.30, 0.03],
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def clamp16(value: float) -> int:
    return max(-32768, min(32767, int(round(value))))


def write_pcm(path: Path, values: list[int]) -> None:
    data = array.array("h", values)
    if os.sys.byteorder != "little":
        data.byteswap()
    path.write_bytes(data.tobytes())


def sample(signal: list[int], position: float) -> float:
    require(math.isfinite(position), "sample position must be finite")
    base = math.floor(position)
    frac = position - base
    left = signal[base] if 0 <= base < len(signal) else 0
    right = signal[base + 1] if 0 <= base + 1 < len(signal) else 0
    return left * (1.0 - frac) + right * frac


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(file_sha256(path)))
    return digest.hexdigest()


def validate_model(model: dict) -> None:
    require(set(model) == {"sample_rate_hz", "direct_total_delay_ms", "nominal_reference_delay_ms",
                           "speaker_mic_distance_m", "room_dimensions_m", "speed_of_sound_m_s",
                           "paths", "approximation", "excitation", "motion", "direct_gain"},
            "model keys")
    room = model["room_dimensions_m"]
    require(isinstance(room, list) and len(room) == 3 and
            all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 2.0 for v in room),
            "room geometry")
    values = [model["direct_total_delay_ms"], model["nominal_reference_delay_ms"],
              model["speaker_mic_distance_m"], model["speed_of_sound_m_s"]]
    require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in values), "finite model")
    require(model["sample_rate_hz"] == RATE, "sample rate")
    require(0.01 <= model["speaker_mic_distance_m"] <= 0.20, "speaker/mic distance")
    require(300.0 <= model["speed_of_sound_m_s"] <= 370.0, "speed of sound")
    require(0 <= model["nominal_reference_delay_ms"] < model["direct_total_delay_ms"] < 100,
            "reference/direct delay")
    require(model["direct_total_delay_ms"] / 1000.0 >
            model["speaker_mic_distance_m"] / model["speed_of_sound_m_s"],
            "device I/O latency must be nonnegative")
    require(model["paths"] == "direct plus six first-order wall images", "path model")
    require(model["excitation"] == ["colored-broadband", "speech-envelope-broadband"], "excitation set")
    require(model["motion"] == ["stationary", "translation", "rotation"], "motion set")
    require(model["direct_gain"] == [0.30, 0.03], "direct gain set")


def excitation(samples: int, seed: int, kind: str) -> list[int]:
    require(kind in set(MODEL["excitation"]), "excitation kind")
    require(type(samples) is int and samples >= FRAME, "sample count")
    rng = random.Random(seed)
    state = 0.0
    phase = rng.random() * math.tau
    out: list[int] = []
    for n in range(samples):
        state = 0.65 * state + 0.35 * rng.uniform(-1.0, 1.0)
        envelope = 1.0
        if kind == "speech-envelope-broadband":
            # Synthetic modulation only; this is not speech or VAD ground truth.
            envelope = 0.12 + 0.88 * (0.5 + 0.5 * math.sin(math.tau * 2.7 * n / RATE + phase)) ** 2
        out.append(clamp16(11000.0 * state * envelope))
    return out


def _path_state_validated(model: dict, time_s: float, motion: str, seed: int, direct_gain: float) -> tuple[list[float], list[float]]:
    require(math.isfinite(time_s) and time_s >= 0.0, "time")
    require(motion in set(model["motion"]), "motion kind")
    require(direct_gain in model["direct_gain"], "direct gain")
    room = model["room_dimensions_m"]
    phase = (seed % 997) / 997.0 * math.tau
    x, y, z = room[0] / 2.0, room[1] / 2.0, 0.7
    yaw = phase
    if motion == "translation":
        x += 0.65 * math.sin(math.tau * 0.11 * time_s + phase)
        y += 0.45 * math.sin(math.tau * 0.13 * time_s + phase)
    elif motion == "rotation":
        yaw += 2.0 * time_s

    distance = model["speaker_mic_distance_m"]
    dx = distance * math.cos(yaw) / 2.0
    dy = distance * math.sin(yaw) / 2.0
    speaker = [x + dx, y + dy, z]
    mic = [x - dx, y - dy, z]
    require(all(0.0 < speaker[i] < room[i] and 0.0 < mic[i] < room[i] for i in range(3)),
            "device outside room")

    images = [speaker]
    for axis, length in enumerate(room):
        low, high = speaker.copy(), speaker.copy()
        low[axis] = -speaker[axis]
        high[axis] = 2.0 * length - speaker[axis]
        images.extend([low, high])
    distances = [math.dist(mic, image) for image in images]
    io_s = model["direct_total_delay_ms"] / 1000.0 - distance / model["speed_of_sound_m_s"]
    delays = [(io_s + d / model["speed_of_sound_m_s"]) * RATE for d in distances]
    wall_pressure = [0.75, 0.64, 0.60, 0.52, 0.45, 0.35]
    gains = [direct_gain] + [0.10 * beta / d for beta, d in zip(wall_pressure, distances[1:])]
    direct_samples = model["direct_total_delay_ms"] * RATE / 1000.0
    require(abs(delays[0] - direct_samples) < 1e-6, "direct path moved")
    require(min(delays[1:]) > delays[0], "reflection precedes direct path")
    require(all(math.isfinite(v) and v > 0.0 for v in gains), "invalid gain")
    return delays, gains


def path_state(model: dict, time_s: float, motion: str, seed: int, direct_gain: float) -> tuple[list[float], list[float]]:
    validate_model(model)
    return _path_state_validated(model, time_s, motion, seed, direct_gain)


def excitation_sidelobe(signal: list[int]) -> dict:
    """Fixed ambiguity diagnostic; not the canonical render-correlation metric."""
    indices = list(range(2048, min(len(signal), 10240), 4))
    require(len(indices) >= 1024, "insufficient excitation support")
    a = [signal[i] for i in indices]
    mean_a = sum(a) / len(a)
    aa = sum((v - mean_a) ** 2 for v in a)
    scores: list[tuple[float, int]] = []
    for lag in range(32, 1921):
        b = [signal[i - lag] for i in indices]
        mean_b = sum(b) / len(b)
        bb = sum((v - mean_b) ** 2 for v in b)
        cross = sum((u - mean_a) * (v - mean_b) for u, v in zip(a, b))
        scores.append((abs(cross) / math.sqrt(max(1.0, aa * bb)), lag))
    score, lag = max(scores)
    return {"definition": "absolute mean-free cosine, indices 2048:10240:4, lags 32..1920",
            "peak": score, "lag_samples": lag, "samples_compared": len(indices)}


def validate_truth(truth: dict, model: dict) -> None:
    require(truth["schema_version"] == 1 and truth["sample_rate_hz"] == RATE and
            truth["frame_samples"] == FRAME, "truth header")
    require(truth["model_sha256"] == json_sha256(model), "truth model binding")
    lower = truth["path_min_samples"]
    upper = truth["path_max_samples"]
    require(len(lower) == len(upper) == 7, "path count")
    direct = model["direct_total_delay_ms"] * RATE / 1000.0
    require(abs(lower[0] - direct) < 1e-6 and abs(upper[0] - direct) < 1e-6, "truth direct path")
    require(min(lower[1:]) > upper[0], "truth causal order")
    margin = lower[0] - model["nominal_reference_delay_ms"] * RATE / 1000.0
    require(abs(truth["initial_causal_margin_samples"] - margin) < 1e-6 and margin > 0.0,
            "truth causal margin")
    frames = truth["frame_start_paths"]
    require(isinstance(frames, list) and frames, "truth frames")
    previous = -1
    for frame in frames:
        require(frame["sample"] % FRAME == 0 and frame["sample"] > previous, "truth frame index")
        previous = frame["sample"]
        require(len(frame["delay_samples"]) == len(frame["gain"]) == 7, "truth frame paths")
        require(abs(frame["delay_samples"][0] - direct) < 1e-6 and
                min(frame["delay_samples"][1:]) > direct, "truth frame causality")


def build(output: Path, seed: int, seconds: float) -> dict:
    validate_model(MODEL)
    require(type(seed) is int and 0 <= seed < 2 ** 32, "seed must be uint32")
    require(isinstance(seconds, (int, float)) and math.isfinite(seconds) and 4.0 <= seconds <= 60.0,
            "seconds must be finite within 4..60")
    require(not output.is_symlink() and (not output.exists() or (output.is_dir() and not any(output.iterdir()))),
            "output must be absent or empty")
    samples = math.ceil(float(seconds) * 100.0) * FRAME
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []

    for kind_index, kind in enumerate(MODEL["excitation"]):
        render = excitation(samples, seed * 17 + 101 + kind_index, kind)
        for motion_index, motion in enumerate(MODEL["motion"]):
            for gain_index, direct_gain in enumerate(MODEL["direct_gain"]):
                case_seed = seed * 1009 + kind_index * 211 + motion_index * 37 + gain_index * 13
                case_id = f"motion-{kind}-{motion}-direct-{direct_gain:.2f}"
                folder = output / "cases" / case_id
                folder.mkdir(parents=True, exist_ok=False)
                echo: list[int] = []
                truth_frames: list[dict] = []
                lower, upper = [math.inf] * 7, [-math.inf] * 7
                for n in range(samples):
                    delays, gains = _path_state_validated(MODEL, n / RATE, motion, case_seed, direct_gain)
                    value = 0.0
                    for tap in range(7):
                        lower[tap] = min(lower[tap], delays[tap])
                        upper[tap] = max(upper[tap], delays[tap])
                        value += gains[tap] * sample(render, n - delays[tap])
                    echo.append(clamp16(value))
                    if n % FRAME == 0:
                        truth_frames.append({"sample": n, "delay_samples": delays, "gain": gains})
                require(max(abs(v) for v in echo) < 32767, "generated echo clipped")
                render_path, mic_path, echo_path = folder / "render.pcm", folder / "mic.pcm", folder / "echo.pcm"
                write_pcm(render_path, render)
                write_pcm(mic_path, echo)
                write_pcm(echo_path, echo)
                margin = lower[0] - MODEL["nominal_reference_delay_ms"] * RATE / 1000.0
                truth = {
                    "schema_version": 1,
                    "sample_rate_hz": RATE,
                    "frame_samples": FRAME,
                    "model_sha256": json_sha256(MODEL),
                    "case_seed": case_seed,
                    "excitation": kind,
                    "motion": motion,
                    "direct_gain": direct_gain,
                    "path_min_samples": lower,
                    "path_max_samples": upper,
                    "initial_causal_margin_samples": margin,
                    "frame_start_paths": truth_frames,
                }
                validate_truth(truth, MODEL)
                truth_path = folder / "ground-truth.json"
                write_json(truth_path, truth)
                rel = folder.relative_to(output)
                cases.append({
                    "case_id": case_id,
                    "split": "dev",
                    "scenario": "aec-continuous-motion",
                    "sample_rate_hz": RATE,
                    "mic_channels": 1,
                    "mic_audio": str(rel / "mic.pcm"),
                    "render_audio": str(rel / "render.pcm"),
                    "clean_near_audio": None,
                    "echo_audio": str(rel / "echo.pcm"),
                    "vad_labels": None,
                    "control": {},
                    "processor_profile": "default",
                    "expected": {
                        "max_output_render_corr_ratio": 1.20,
                        "max_output_rms_delta_db": 0.0,
                        "min_erle_db": -6.0,
                    },
                    "source": {
                        "dataset_id": DATASET_ID,
                        "source_id": case_id,
                        "generator_seed": case_seed,
                        "movement": motion != "stationary",
                        "motion": motion,
                        "excitation": kind,
                        "direct_gain": direct_gain,
                        "ground_truth": str(rel / "ground-truth.json"),
                        "model_sha256": json_sha256(MODEL),
                    },
                })

    require(len(cases) == 12 and len({case["case_id"] for case in cases}) == 12, "case matrix")
    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-motion-geometry-v{GENERATOR_VERSION}-seed-{seed}",
        "tier": "regression",
        "generator": {
            "name": Path(__file__).name,
            "version": GENERATOR_VERSION,
            "seed": seed,
            "seconds": samples / RATE,
            "requested_seconds": seconds,
            "continuous_motion": True,
            "explicit_path_change_notifications": False,
            "model": MODEL,
            "model_sha256": json_sha256(MODEL),
        },
        "sources": [DATASET_ID],
        "sealed_data": False,
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    write_json(corpus_path, corpus)
    files = {
        str(path.relative_to(output)): file_sha256(path)
        for path in sorted(item for item in output.rglob("*") if item.is_file())
    }
    manifest = {
        "schema_version": 1,
        "authority": "development-only-non-shipping",
        "seed": seed,
        "cases": len(cases),
        "dataset_id": DATASET_ID,
        "generator_version": GENERATOR_VERSION,
        "generator_sha256": file_sha256(Path(__file__)),
        "model_sha256": json_sha256(MODEL),
        "corpus_sha256": file_sha256(corpus_path),
        "files": files,
    }
    write_json(output / "source-manifest.json", manifest)
    return corpus


def self_test() -> None:
    validate_model(MODEL)
    direct = MODEL["direct_total_delay_ms"] * RATE / 1000.0
    for motion in MODEL["motion"]:
        for seed in (0, 16411, 36411):
            states = [path_state(MODEL, t, motion, seed, 0.30)[0] for t in (0.0, 0.13, 1.7, 3.99)]
            assert all(abs(delays[0] - direct) < 1e-6 and min(delays[1:]) > direct for delays in states)
            if motion == "stationary":
                assert all(states[0] == state for state in states[1:])
    for kind in MODEL["excitation"]:
        a = excitation(16000, 1, kind)
        assert a == excitation(16000, 1, kind)
        assert a != excitation(16000, 2, kind)
        assert excitation_sidelobe(a)["peak"] < 0.30
    periodic = [round(10000 * math.sin(math.tau * n / 80)) for n in range(16000)]
    assert excitation_sidelobe(periodic)["peak"] > 0.999
    assert sample([100, 200], -0.5) == 50.0
    assert sample([100, 200], 0.5) == 150.0
    assert sample([100, 200], 1.5) == 100.0
    for field, value in (("direct_total_delay_ms", 39.0), ("speed_of_sound_m_s", float("nan")),
                         ("speaker_mic_distance_m", -1.0)):
        bad = dict(MODEL, **{field: value})
        try:
            validate_model(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("bad model accepted")
    with tempfile.TemporaryDirectory(prefix="ap-aec-motion-v2-") as raw:
        root = Path(raw)
        a, b, c = root / "a", root / "b", root / "c"
        ca, cb, cc = build(a, 4107, 4.0), build(b, 4107, 4.0), build(c, 4207, 4.0)
        assert len(ca["cases"]) == len(cb["cases"]) == len(cc["cases"]) == 12
        assert all(case["split"] == "dev" and case["control"] == {} for case in ca["cases"])
        assert tree_digest(a) == tree_digest(b)
        assert tree_digest(a) != tree_digest(c)
        try:
            build(a, 4307, 4.0)
        except ValueError:
            pass
        else:
            raise AssertionError("nonempty output was reused")
    print("AEC motion geometry v2 self-test: known-answer/causality/alias/determinism controls OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=4107)
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    try:
        corpus = build(args.output, args.seed, args.seconds)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"corpus": str(args.output / "corpus.json"), "corpus_id": corpus["corpus_id"],
                      "cases": len(corpus["cases"]), "seed": args.seed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
