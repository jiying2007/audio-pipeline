#!/usr/bin/env python3
"""Run actual AEC3/APM binary engineering fixtures; never acoustic acceptance."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

RATE, HOP = 16000, 160
SIGNAL_DELAY = {"aec3": 128, "apm": 224}
MAX_REQUESTED_SAMPLES = 10 * RATE
MAX_WALL_SECONDS = 120


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pcm(values):
    result = array.array("h", values)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def samples(data):
    result = array.array("h")
    result.frombytes(data)
    if sys.byteorder != "little":
        result.byteswap()
    return list(result)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def signal(channels, frames=12, seed=37):
    """Integer-only 10 ms framed engineering noise/buzz plus a short echo."""
    state = seed
    render = []
    for _ in range(frames * HOP):
        state = (1103515245 * state + 12345) & 0x7fffffff
        render.append(((state >> 8) & 2047) - 1024)
    capture = []
    for index in range(frames * HOP):
        for channel in range(channels):
            value = ((index * (19 + channel * 7) + seed * 17) % 4001) - 2000
            delay = 8 * (channel + 1)
            echo = render[index - delay] // 2 if index >= delay else 0
            capture.append(value + echo)
    return pcm(capture), pcm(render)


def permute(data, channels, mapping):
    original = samples(data)
    return pcm(original[index + channel]
               for index in range(0, len(original), channels) for channel in mapping)


def near_only_probes():
    impulse = [0] * (20 * HOP)
    impulse[4 * HOP] = 1000
    chirp = [0] * (40 * HOP)
    start, stop = 4 * HOP, 36 * HOP
    duration = (stop - start) / RATE
    for index in range(start, stop):
        t = (index - start) / RATE
        phase = 2.0 * math.pi * (600.0 * t + 0.5 * (3600.0 / duration) * t * t)
        envelope = math.sin(math.pi * (index - start) / (stop - start)) ** 2
        chirp[index] = round(1000 * envelope * math.sin(phase))
    return {"impulse": pcm(impulse), "chirp": pcm(chirp)}


def correlation_at_lag(reference, output, lag):
    count = min(len(reference), len(output) - lag)
    require(count > 0, "empty synthetic correlation window")
    dot = sum(reference[i] * output[i + lag] for i in range(count))
    energy = sum(value * value for value in reference[:count])
    output_energy = sum(output[i + lag] ** 2 for i in range(count))
    return dot / math.sqrt(energy * output_energy) if energy and output_energy else 0.0


class Fixtures:
    def __init__(self, binary, output, build_receipt=None, code_revision=None):
        self.binary = binary.resolve(strict=True)
        require(self.binary.is_file(), "binary is not a file")
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.start = time.monotonic()
        self.requested_samples = 0
        self.rows = []
        self.checks = []
        self.failures = []
        self.receipt = {
            "schema_version": 1, "fixture_id": "webrtc-aec3-engineering-v1",
            "status": "RUNNING", "binary": str(self.binary),
            "binary_sha256": digest(self.binary.read_bytes()),
            "fixture_source_sha256": digest(Path(__file__).read_bytes()),
            "signal_delay_predeclared_samples": SIGNAL_DELAY,
            "data_role": "synthetic_engineering_only_not_real_acoustic_evidence",
            "acoustic_acceptance": False, "physical_target_measurement": False,
            "promotion_authority": False, "calls": self.rows, "checks": self.checks,
            "failures": self.failures,
        }
        if build_receipt:
            self.receipt["build_receipt_sha256"] = digest(build_receipt.read_bytes())
        if code_revision is not None:
            require(len(code_revision) == 40 and
                    all(character in "0123456789abcdef" for character in code_revision),
                    "code-revision must be an explicit lowercase 40-character commit")
            self.receipt["code_revision"] = code_revision
        self.save()

    def save(self):
        self.receipt["requested_capture_audio_seconds"] = self.requested_samples / RATE
        self.receipt["wall_seconds"] = time.monotonic() - self.start
        write_json(self.output / "engineering.json", self.receipt)

    def check(self, name, operation):
        try:
            operation()
            self.checks.append({"name": name, "status": "PASS"})
        except Exception as exc:
            self.failures.append({"name": name, "error": str(exc)})
            self.checks.append({"name": name, "status": "FAIL"})
        self.save()

    def execute(self, name, mode, channels, mic, render, mapping=None, reset=None,
                overrides=None, preexisting=None, expect_error=False):
        require(len(mic) <= RATE * channels * 2 and len(render) <= RATE * 2,
                "every fixture stream must be at most one second")
        self.requested_samples += (len(mic) + 2 * channels - 1) // (2 * channels)
        require(self.requested_samples <= MAX_REQUESTED_SAMPLES, "10 second audio budget exceeded")
        folder = self.output / name
        folder.mkdir()
        mic_path, render_path = folder / "mic.pcm", folder / "render.pcm"
        mic_path.write_bytes(mic)
        render_path.write_bytes(render)
        output, metadata, timing = folder / "output.pcm", folder / "metadata.json", folder / "frames.jsonl"
        options = {
            "--mode": mode, "--mic-channels": str(channels),
            "--channel-map": ",".join(map(str, mapping if mapping is not None else range(channels))),
            "--mic": str(mic_path), "--render": str(render_path),
            "--output": str(output), "--metadata": str(metadata), "--frame-times": str(timing),
        }
        if reset is not None:
            options["--reset-before-frame"] = str(reset)
        for key, value in (overrides or {}).items():
            if value is None:
                options.pop(key, None)
            else:
                options[key] = str(value).replace("{mic}", str(mic_path)).replace(
                    "{output}", str(output))
        before = {}
        for key in preexisting or ():
            path = Path(options[key])
            path.write_bytes(b"existing-evidence-must-survive\n")
            before[path] = path.read_bytes()
        command = [str(self.binary)]
        for key, value in options.items():
            command += [key, value]
        row = {
            "case_id": name, "command": command, "mode": mode, "mic_channels": channels,
            "mic_sha256": digest(mic_path.read_bytes()), "render_sha256": digest(render),
            "expected_error": expect_error, "reset_before_frame": reset,
        }
        self.rows.append(row)
        self.save()
        remaining = MAX_WALL_SECONDS - (time.monotonic() - self.start)
        require(remaining > 0, "engineering wall-time budget exhausted")
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, timeout=min(30, remaining))
        except subprocess.TimeoutExpired as exc:
            row["status"] = "TIMEOUT"
            for key, value in (("stdout", exc.stdout), ("stderr", exc.stderr)):
                (folder / (key + ".log")).write_text(
                    value.decode("utf-8", "replace") if isinstance(value, bytes) else value or "",
                    encoding="utf-8")
            self.save()
            raise RuntimeError("real binary timed out; no fallback") from exc
        (folder / "stdout.log").write_text(result.stdout, encoding="utf-8")
        (folder / "stderr.log").write_text(result.stderr, encoding="utf-8")
        row["returncode"] = result.returncode
        row["status"] = "UNSUPPORTED" if result.returncode == 3 else (
            "OK" if result.returncode == 0 else "ERROR")
        require(digest(mic_path.read_bytes()) == row["mic_sha256"], "capture input was modified")
        require(digest(render_path.read_bytes()) == row["render_sha256"], "render input was modified")
        if expect_error:
            require(result.returncode == 2, "invalid input did not fail with contract exit code 2")
            require('"status":"ERROR"' in result.stderr, "missing explicit error receipt")
            for key in ("--output", "--metadata", "--frame-times"):
                path = Path(options[key])
                if path in before:
                    require(path.read_bytes() == before[path], "existing evidence was overwritten")
                elif path not in (mic_path, render_path):
                    require(not path.exists(), "invalid input created a partial output")
            self.save()
            return None
        require(result.returncode == 0, "real binary " + row["status"] + ": " + result.stderr[-2000:])
        require(output.stat().st_size == len(mic), "output channel/frame length changed")
        meta = json.loads(metadata.read_text())
        trace = [json.loads(line) for line in timing.read_text().splitlines()]
        frames = len(mic) // (2 * channels * HOP)
        require(meta["status"] == "OK" and meta["completed_frames"] == frames, "metadata frame status")
        require(meta["actual_processing_channels"] == channels and meta["output_channels"] == channels,
                "silent channel downmix")
        require(meta["actual_processing_sample_rate_hz"] == RATE, "hidden sample-rate conversion")
        require(meta["channel_map"] == list(mapping if mapping is not None else range(channels)),
                "channel map metadata drift")
        require(meta["reset_before_frame"] == reset, "reset identity drift")
        require(meta["algorithmic_latency_samples"] == SIGNAL_DELAY[mode], "frozen delay drift")
        require(meta["first_output_frame_input_samples_required"] == HOP, "first-frame input requirement")
        require(meta["requested_config"] == meta["applied_config"], "config application drift")
        config = meta["applied_config"]
        require(config["echo_canceller"] == {
            "enabled": True, "mobile_mode": False, "export_linear_aec_output": False,
            "enforce_high_pass_filtering": False}, "AEC3 config drift")
        require(config["high_pass_filter"] == {"enabled": mode == "apm", "apply_in_full_band": True},
                "HPF config drift")
        require(config["noise_suppression"] == {
            "enabled": mode == "apm", "level": "moderate",
            "analyze_linear_aec_output_when_available": False}, "NS config drift")
        require(config["gain_controller1"]["enabled"] is False, "AGC1 must remain disabled")
        require(config["gain_controller2"] == {
            "enabled": mode == "apm", "input_volume_controller_enabled": False,
            "adaptive_digital": {"enabled": mode == "apm", "headroom_db": 5, "max_gain_db": 50,
                                 "initial_gain_db": 15, "max_gain_change_db_per_second": 6,
                                 "max_output_noise_level_dbfs": -50},
            "fixed_digital_gain_db": 0}, "AGC2 config drift")
        for key in ("pre_amplifier_enabled", "capture_level_adjustment_enabled",
                    "transient_suppression_enabled"):
            require(config[key] is False, "unexpected processing: " + key)
        require(meta["adapter_normalization"] is False and meta["padded_samples"] == 0 and
                meta["tail_flush_samples"] == 0, "hidden normalization/padding")
        require(len(trace) == frames, "frame timing coverage")
        previous = 0
        for index, frame in enumerate(trace):
            require(frame["frame_index"] == index and
                    frame["input_sample_frames_available"] == (index + 1) * HOP and
                    frame["output_sample_frames_emitted"] == (index + 1) * HOP,
                    "streaming input/output clock drift")
            begin, end = frame["host_processing_begin_ns"], frame["host_processing_completed_ns"]
            require(previous <= begin <= end and
                    end - begin == frame["host_processing_duration_ns"], "invalid host timing")
            require(frame["reset_before_frame"] == (index == reset), "reset trace drift")
            previous = end
        require(meta["first_output_frame_host_completion_ns"] == trace[0]["host_processing_completed_ns"],
                "first-frame host completion drift")
        data = output.read_bytes()
        row["output_sha256"] = digest(data)
        row["metadata_sha256"] = digest(metadata.read_bytes())
        row["frame_times_sha256"] = digest(timing.read_bytes())
        row["output_peak_absolute_s16"] = max(abs(value) for value in samples(data))
        self.save()
        return {"pcm": data, "metadata": meta, "trace": trace}

    def geometry(self, mode, channels):
        prefix = mode + "-" + str(channels)
        mic, render = signal(channels)
        mapping = list(reversed(range(channels)))
        base = self.execute(prefix + "-base", mode, channels, mic, render, mapping)
        require(any(base["pcm"]), "nonzero engineering probe became entirely silent")
        again = self.execute(prefix + "-repeat", mode, channels, mic, render, mapping)
        require(base["pcm"] == again["pcm"], "fresh-instance repeat is not bitwise deterministic")
        cut = 6 * HOP
        for changed in ("capture", "render"):
            mic_values, render_values = samples(mic), samples(render)
            if changed == "capture":
                mic_values[cut * channels:] = [-value + 113 for value in mic_values[cut * channels:]]
            else:
                render_values[cut:] = [-value + 71 for value in render_values[cut:]]
            future = self.execute(prefix + "-future-" + changed, mode, channels,
                                  pcm(mic_values), pcm(render_values), mapping)
            require(base["pcm"][:cut * channels * 2] == future["pcm"][:cut * channels * 2],
                    "future " + changed + " changed an already emitted prefix")
            require(any(base["pcm"][:cut * channels * 2]), "vacuous zero prefix")
        if channels > 1:
            equivalent = self.execute(prefix + "-mapped-equivalent", mode, channels,
                                      permute(mic, channels, mapping), render)
            require(base["pcm"] == equivalent["pcm"], "channel map differs from physical permutation")
        if channels == 4:
            dirty_mic, dirty_render = signal(channels, seed=911)
            reset = self.execute(prefix + "-reset", mode, channels, dirty_mic + mic,
                                 dirty_render + render, mapping, reset=12)
            require(reset["pcm"][len(dirty_mic):] == base["pcm"],
                    "fresh instance reset did not erase previous stream history")
        self.execute(prefix + "-zero", mode, channels, b"\0" * (2 * HOP * channels * 2),
                     b"\0" * (2 * HOP * 2))

    def long_tail(self, mode):
        render = [0] * (80 * HOP)
        render[0] = 10000
        capture = [0] * len(render)
        value = 9000
        for index in range(80, len(capture)):
            capture[index] = value
            value = value * 32700 // 32768
        capture[-1] = 701
        self.execute(mode + "-synthetic-tail", mode, 1, pcm(capture), pcm(render))

    def latency(self, mode):
        observations = {"mode": mode, "predeclared_signal_delay_samples": SIGNAL_DELAY[mode],
                        "used_for_target_alignment_selection": False}
        for name, mic in near_only_probes().items():
            run = self.execute(mode + "-latency-" + name, mode, 1, mic, b"\0" * len(mic))
            before, after = samples(mic), samples(run["pcm"])
            require(any(after), "latency probe produced no observable signal")
            observed = {
                "first_output_frame_input_time_ms": 10,
                "first_output_frame_host_completion_ns":
                    run["metadata"]["first_output_frame_host_completion_ns"],
                "predeclared_signal_delay_samples": SIGNAL_DELAY[mode],
            }
            if name == "impulse":
                location = max(range(len(after)), key=lambda index: abs(after[index]))
                observed["observed_impulse_peak_delay_samples"] = location - 4 * HOP
            else:
                # Calibration-only observation; never re-used to fit speech targets.
                scores = [correlation_at_lag(before, after, lag) for lag in range(385)]
                observed["observed_chirp_correlation_peak_delay_samples"] = max(
                    range(len(scores)), key=scores.__getitem__)
                observed["correlation_at_predeclared_delay"] = scores[SIGNAL_DELAY[mode]]
            observations[name] = observed
        write_json(self.output / (mode + "-latency-observation.json"), observations)
        require(observations["impulse"]["observed_impulse_peak_delay_samples"] == SIGNAL_DELAY[mode],
                "impulse observation disagrees with source-predeclared delay; investigate, do not retune")
        require(observations["chirp"]["observed_chirp_correlation_peak_delay_samples"] == SIGNAL_DELAY[mode],
                "chirp observation disagrees with source-predeclared delay; investigate, do not retune")

    def negatives(self):
        mic, render = signal(1, frames=1)
        for name, bad_mic, bad_render in [
                ("empty-capture", b"", render), ("empty-render", mic, b""),
                ("odd-capture", mic + b"\0", render), ("odd-render", mic, render + b"\0"),
                ("partial-capture-frame", mic[:-2], render),
                ("partial-render-frame", mic, render[:-2]),
                ("unequal-duration", mic, render * 2)]:
            self.execute("invalid-" + name, "aec3", 1, bad_mic, bad_render, expect_error=True)
        for name, overrides in [
                ("channels", {"--mic-channels": "3"}),
                ("mode", {"--mode": "unknown"}),
                ("missing-map", {"--channel-map": None}),
                ("outside-map", {"--channel-map": "1"}),
                ("negative-map", {"--channel-map": "-1"}),
                ("reset-outside", {"--reset-before-frame": "1"}),
                ("reset-negative", {"--reset-before-frame": "-1"}),
                ("same-output-input", {"--output": "{mic}"}),
                ("same-outputs", {"--metadata": "{output}"})]:
            self.execute("invalid-" + name, "aec3", 1, mic, render,
                         overrides=overrides, expect_error=True)
        stereo, render = signal(2, frames=1)
        self.execute("invalid-duplicate-map", "aec3", 2, stereo, render,
                     overrides={"--channel-map": "0,0"}, expect_error=True)
        for key in ("--output", "--metadata", "--frame-times"):
            self.execute("invalid-existing-" + key[2:], "aec3", 1, mic, render,
                         preexisting=[key], expect_error=True)

    def record_runtime_identity(self):
        # Shared with bundle construction and reference replay: inspect the actual
        # loader resolution in this process's environment, including system libs.
        import webrtc_aec3_ci as runtime_source
        self.receipt["runtime_identity_source_sha256"] = digest(
            Path(runtime_source.__file__).read_bytes())
        self.receipt["runtime_identity"] = runtime_source.runtime_identity(self.binary)

    def verify_runtime_identity(self):
        import webrtc_aec3_ci as runtime_source
        require(digest(Path(runtime_source.__file__).read_bytes()) ==
                self.receipt["runtime_identity_source_sha256"],
                "runtime identity helper changed during engineering fixtures")
        require(runtime_source.runtime_identity(self.binary) == self.receipt["runtime_identity"],
                "host or resolved runtime libraries changed during engineering fixtures")
        require(digest(self.binary.read_bytes()) == self.receipt["binary_sha256"],
                "binary changed during engineering fixtures")
        require(time.monotonic() - self.start <= MAX_WALL_SECONDS,
                "engineering wall-time budget exhausted during final verification")

    def run(self):
        self.check("runtime-identity-initial", self.record_runtime_identity)
        if self.failures:
            self.receipt["status"] = "FAIL"
            self.save()
            return 1
        for mode in ("aec3", "apm"):
            for channels in (1, 2, 4):
                self.check(mode + "-" + str(channels) + "-geometry",
                           lambda mode=mode, channels=channels: self.geometry(mode, channels))
            self.check(mode + "-tail", lambda mode=mode: self.long_tail(mode))
            self.check(mode + "-latency", lambda mode=mode: self.latency(mode))
        self.check("invalid-inputs", self.negatives)
        self.check("runtime-identity-stable", self.verify_runtime_identity)
        self.receipt["status"] = "PASS_ENGINEERING_ONLY" if not self.failures else "FAIL"
        self.save()
        return 1 if self.failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--code-revision")
    args = parser.parse_args()
    try:
        fixtures = Fixtures(args.binary, args.output, args.build_receipt, args.code_revision)
        return fixtures.run()
    except (OSError, ValueError, RuntimeError) as exc:
        print("AEC3 engineering fixtures: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
