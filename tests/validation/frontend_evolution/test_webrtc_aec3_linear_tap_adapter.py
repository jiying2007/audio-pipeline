#!/usr/bin/env python3
"""Actual mono AEC3 linear-observation engineering; no speech or acoustic verdict."""

from __future__ import annotations

import argparse
import json
import math
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path

import test_webrtc_aec3_adapter as original

RATE, HOP = 16000, 160
MAX_WALL_SECONDS = 120
MAX_REQUESTED_SAMPLES = 10 * RATE
EXPECTED_VALID_CALLS = 13
EXPECTED_VALID_SAMPLES = 132800  # 8.3 s, counting every accepted invocation.
EXPECTED_REQUESTED_SAMPLES = 134719  # Includes all twelve rejected input requests.
FIXTURE_ID = "webrtc-aec3-linear-tap-engineering-v1"
CHECK_NAMES = (
    "runtime-identity-initial", "three-way-final-byte-equivalence",
    "source-declared-delay-and-units", "repeat-future-prefix-and-reset",
    "invalid-observation-contracts", "fixed-invocation-and-audio-budget",
    "runtime-identity-stable",
)
MODES = ("default-off", "factory-off", "factory-on")
require, digest = original.require, original.digest
PRESERVED_LINEAR = b"existing-linear-evidence-must-survive\n"
OUTPUT_FILES = {"--mic": "mic.pcm", "--render": "render.pcm", "--output": "output.pcm",
                "--metadata": "metadata.json", "--frame-times": "frames.jsonl",
                "--linear-output": "linear.f32le"}


def invocation(binary, folder, mode, reset=None, overrides=None):
    paths = {key: folder / value for key, value in OUTPUT_FILES.items()}
    options = {"--mode": "aec3", "--mic-channels": "1", "--channel-map": "0"}
    options.update({key: str(path) for key, path in paths.items() if key != "--linear-output"})
    # Omission is intentional: this arm tests the original unmodified CLI path.
    if mode != "default-off":
        options["--aec3-export-mode"] = mode
    if mode == "factory-on":
        options["--linear-output"] = str(paths["--linear-output"])
    if reset is not None:
        options["--reset-before-frame"] = str(reset)
    for key, value in (overrides or {}).items():
        if value is None:
            options.pop(key, None)
        else:
            options[key] = str(value).replace("{linear}", str(paths["--linear-output"])).replace(
                "{mic}", str(paths["--mic"])).replace("{output}", str(paths["--output"]))
    command = [str(binary)]
    for key, value in options.items():
        command.extend((key, value))
    return paths, command


def linear_samples(data):
    require(len(data) % 4 == 0, "partial F32LE sample")
    values = [value[0] for value in struct.iter_unpack("<f", data)]
    require(all(math.isfinite(x) and -1.0 <= x <= 1.0 for x in values),
            "nonfinite/out-of-range upstream getter sample")
    return values


def finite_time(value, maximum, label):
    require(type(value) in (float, int) and math.isfinite(value) and 0 < value <= maximum,
            "invalid or over-budget time: " + label)


def inspect_outputs(paths, mode, mic, reset):
    """Pure saved-byte interpretation shared by execution and independent readback."""
    final = paths["--output"].read_bytes()
    require(len(final) == len(mic), "final cardinality changed")
    meta = json.loads(paths["--metadata"].read_text())
    trace = [json.loads(x) for x in paths["--frame-times"].read_text().splitlines()]
    count, frames = len(mic) // 2, len(mic) // (2 * HOP)
    require(meta["status"] == "OK" and meta["completed_frames"] == frames and len(trace) == frames,
            "frame completion cardinality")
    require(meta["sample_rate_hz"] == meta["actual_processing_sample_rate_hz"] == RATE and
            meta["mic_channels"] == meta["actual_processing_channels"] == meta["output_channels"] == 1,
            "geometry changed")
    require(meta["channel_map"] == [0] and meta["reset_before_frame"] == reset and
            meta["padded_samples"] == meta["tail_flush_samples"] == 0, "input/reset/tail contract")
    require(meta["algorithmic_latency_samples"] == 128 and
            meta["first_output_frame_input_samples_required"] == HOP, "final timeline changed")
    require(meta["mode"] == "aec3" and meta["sample_format"] == "S16LE" and
            meta["frame_samples"] == HOP and meta["render_channels"] == 1 and
            meta["input_frames"] == frames and meta["output_sample_frames"] == count and
            meta["adapter_lookahead_frames"] == meta["stream_delay_ms"] == 0,
            "stream contract changed")
    require(meta["first_output_frame_host_completion_ns"] == trace[0]["host_processing_completed_ns"],
            "first final frame timestamp differs")
    require(all(meta[key] is False for key in
            ("adapter_normalization", "physical_target_measurement", "acoustic_acceptance",
             "promotion_authority", "pure_linear_aec")) and meta["host_timing_only"] is True,
            "research role or normalization changed")
    require(meta["requested_config"] == meta["applied_config"], "APM config readback differs")
    enabled = mode == "factory-on"
    cfg = meta["applied_config"]
    require(cfg["echo_canceller"] == {"enabled": True, "mobile_mode": False,
            "export_linear_aec_output": enabled, "enforce_high_pass_filtering": False},
            "APM echo settings differ")
    require(not cfg["high_pass_filter"]["enabled"] and not cfg["noise_suppression"]["enabled"] and
            not cfg["gain_controller1"]["enabled"] and not cfg["gain_controller2"]["enabled"],
            "extra processing enabled")
    require(not cfg["pre_amplifier_enabled"] and not cfg["capture_level_adjustment_enabled"] and
            not cfg["transient_suppression_enabled"] and
            not cfg["noise_suppression"]["analyze_linear_aec_output_when_available"],
            "additional preprocessing enabled")
    observation = meta.get("aec3_linear_observation")
    if mode == "default-off":
        require(observation is None, "original CLI metadata changed")
    else:
        require(observation["mode"] == mode and observation["enabled"] is enabled and
                observation["internal_filter_export_linear_aec_output"] is enabled and
                observation["factory"] == "explicit_default_aec3", "factory/export contract")
        require(observation["tap_signal_delay_samples"] == 64 and
                observation["final_signal_delay_samples"] == 128 and
                observation["tap_lead_relative_to_final_samples"] == 64 and
                observation["upstream_getter_clamp_float_s16"] == [-32768, 32768] and
                observation["upstream_getter_divisor"] == 32768 and
                observation["output_samples"] == (count if enabled else 0), "tap units/timeline")
        require(observation["format"] == "F32LE" and observation["channels"] == 1 and
                observation["samples_per_frame"] == HOP and
                observation["first_frame_input_samples_required"] == HOP and
                observation["capture_fixed_delay_samples"] == 0 and
                observation["distribution_commit"] == "846fe90a289f58b7c9303a635142aa2c7caa93e5",
                "tap source or geometry changed")
        require(not any(observation[key] for key in
                ("adapter_scaling", "adapter_clipping", "adapter_quantization", "pure_lti")),
                "tap conversion or interpretation changed")
    linear = paths["--linear-output"].read_bytes() if enabled else None
    if enabled:
        require(len(linear) == count * 4 and len(linear_samples(linear)) == count, "tap cardinality")
        require(observation["first_linear_frame_host_completion_ns"] ==
                trace[0]["linear_getter_completed_ns"], "first getter timing differs")
    else:
        require(not paths["--linear-output"].exists(), "disabled tap output exists")
    previous_completed = 0
    for index, frame in enumerate(trace):
        require(all(type(frame[key]) is int and frame[key] >= 0 for key in
                ("frame_index", "input_sample_frames_available", "output_sample_frames_emitted",
                 "host_processing_begin_ns", "host_processing_completed_ns", "host_processing_duration_ns")),
                "invalid frame integer fields")
        require(frame["frame_index"] == index and frame["input_sample_frames_available"] == (index + 1) * HOP
                and frame["output_sample_frames_emitted"] == (index + 1) * HOP, "frame timeline")
        require(previous_completed <= frame["host_processing_begin_ns"] <=
                frame["host_processing_completed_ns"], "nonmonotonic host timing")
        require(frame["host_processing_duration_ns"] == frame["host_processing_completed_ns"] -
                frame["host_processing_begin_ns"] and frame["algorithmic_latency_samples"] == 128 and
                frame["algorithmic_latency_ms"] == 8 and frame["host_timing_only"] is True,
                "invalid frame timing interpretation")
        require(frame["reset_before_frame"] is (index == reset), "reset frame differs")
        if mode != "default-off":
            require(frame["aec3_export_mode"] == mode and frame["linear_signal_delay_samples"] == 64 and
                    frame["linear_output_sample_frames_emitted"] == ((index + 1) * HOP if enabled else 0),
                    "tap frame timeline")
            if enabled:
                require(type(frame["linear_getter_completed_ns"]) is int and
                        frame["linear_getter_completed_ns"] >= frame["host_processing_completed_ns"],
                        "getter predates final readiness")
            else:
                require(frame["linear_getter_completed_ns"] is None, "disabled getter timestamp")
        previous_completed = (frame["linear_getter_completed_ns"] if enabled
                              else frame["host_processing_completed_ns"])
    return {"final": final, "linear": linear, "metadata": meta, "trace": trace}


class Fixtures:
    def __init__(self, binary, output, build_receipt, code_revision):
        require(len(code_revision) == 40 and all(x in "0123456789abcdef" for x in code_revision),
                "explicit lowercase exact code revision required")
        self.binary = binary.resolve(strict=True)
        require(self.binary.is_file(), "binary is not a regular file")
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.start = time.monotonic()
        self.requested_samples = 0
        self.accepted_samples = 0
        self.accepted_calls = 0
        self.rows, self.checks, self.failures = [], [], []
        self.result = {
            "schema_version": 1, "fixture_id": FIXTURE_ID,
            "status": "RUNNING", "code_revision": code_revision,
            "binary": str(self.binary), "binary_sha256": digest(self.binary.read_bytes()),
            "execution_output": str(self.output),
            "fixture_source_sha256": digest(Path(__file__).read_bytes()),
            "base_fixture_source_sha256": digest(Path(original.__file__).read_bytes()),
            "signal_delay_predeclared_samples": {"linear": 64, "final": 128},
            "data_role": "synthetic_engineering_only_not_real_acoustic_evidence",
            "acoustic_acceptance": False, "promotion_authority": False,
            "physical_target_measurement": False, "calls": self.rows,
            "checks": self.checks, "failures": self.failures,
        }
        if build_receipt:
            self.result["build_receipt_sha256"] = digest(build_receipt.read_bytes())
        self.save()

    def save(self):
        self.result["requested_capture_audio_seconds"] = self.requested_samples / RATE
        self.result["accepted_capture_audio_seconds"] = self.accepted_samples / RATE
        self.result["accepted_binary_calls"] = self.accepted_calls
        self.result["binary_process_calls"] = len(self.rows)
        self.result["rejected_before_dsp_calls"] = sum(
            row.get("returncode") == 2 and row["expected_error"] for row in self.rows)
        self.result["wall_seconds"] = time.monotonic() - self.start
        original.write_json(self.output / "engineering.json", self.result)

    def check(self, name, operation):
        try:
            operation()
            self.checks.append({"name": name, "status": "PASS"})
        except Exception as exc:
            self.checks.append({"name": name, "status": "FAIL"})
            self.failures.append({"name": name, "error": str(exc)})
            self.save()
            raise
        self.save()

    def runtime_start(self):
        import webrtc_aec3_ci as runtime
        self.result["runtime_identity_source_sha256"] = digest(Path(runtime.__file__).read_bytes())
        self.result["runtime_identity"] = runtime.runtime_identity(self.binary)
        self.result["runtime_observations_completed"] = 1

    def runtime_finish(self):
        import webrtc_aec3_ci as runtime
        require(digest(Path(runtime.__file__).read_bytes()) ==
                self.result["runtime_identity_source_sha256"], "runtime helper changed")
        self.result["runtime_identity_after"] = runtime.runtime_identity(self.binary)
        self.result["runtime_observations_completed"] = 2
        require(self.result["runtime_identity_after"] == self.result["runtime_identity"],
                "host/resolved libraries changed")
        require(digest(self.binary.read_bytes()) == self.result["binary_sha256"], "binary changed")
        require(digest(Path(__file__).read_bytes()) == self.result["fixture_source_sha256"],
                "fixture changed")
        require(digest(Path(original.__file__).read_bytes()) ==
                self.result["base_fixture_source_sha256"], "synthetic generator source changed")
        require(time.monotonic() - self.start <= MAX_WALL_SECONDS, "engineering deadline exceeded")

    def execute(self, name, mode, mic, render, reset=None, overrides=None,
                existing_linear=False, expect_error=False):
        require(len(mic) <= RATE * 2 and len(render) <= RATE * 2, "fixture exceeds one second")
        self.requested_samples += (len(mic) + 1) // 2
        require(self.requested_samples <= MAX_REQUESTED_SAMPLES, "10 second requested-audio budget")
        folder = self.output / name
        folder.mkdir()
        paths, command = invocation(self.binary, folder, mode, reset, overrides)
        paths["--mic"].write_bytes(mic)
        paths["--render"].write_bytes(render)
        if existing_linear:
            paths["--linear-output"].write_bytes(PRESERVED_LINEAR)
        row = {"case_id": name, "command": command, "mode": "aec3", "mic_channels": 1,
               "aec3_export_mode": mode, "reset_before_frame": reset,
               "expected_error": expect_error, "mic_sha256": digest(mic),
               "render_sha256": digest(render), "requested_samples": (len(mic) + 1) // 2}
        self.rows.append(row)
        self.save()
        remaining = MAX_WALL_SECONDS - (time.monotonic() - self.start)
        require(remaining > 0, "engineering deadline exceeded before binary")
        started = time.monotonic()
        try:
            call = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=min(30, remaining))
        except subprocess.TimeoutExpired as exc:
            (folder / "stdout.log").write_bytes(exc.stdout or b"")
            (folder / "stderr.log").write_bytes(exc.stderr or b"")
            row.update({"status": "TIMEOUT", "wall_seconds": time.monotonic() - started})
            self.save()
            raise RuntimeError("actual binary timeout; no fallback or retry") from exc
        (folder / "stdout.log").write_bytes(call.stdout)
        (folder / "stderr.log").write_bytes(call.stderr)
        row.update({"returncode": call.returncode, "wall_seconds": time.monotonic() - started,
                    "status": "OK" if call.returncode == 0 else "ERROR",
                    "stdout_sha256": digest(call.stdout), "stderr_sha256": digest(call.stderr)})
        require(paths["--mic"].read_bytes() == mic and paths["--render"].read_bytes() == render,
                "binary modified its inputs")
        if expect_error:
            require(call.returncode == 2 and b'"status":"ERROR"' in call.stderr,
                    "invalid observation contract did not explicitly fail before DSP")
            for key in ("--output", "--metadata", "--frame-times"):
                require(not paths[key].exists(), "invalid input produced an output")
            if existing_linear:
                require(paths["--linear-output"].read_bytes() == PRESERVED_LINEAR, "existing tap overwritten")
            else:
                require(not paths["--linear-output"].exists(), "invalid input produced tap samples")
            self.save()
            return None
        require(call.returncode == 0, "actual binary failed: " + call.stderr[-2000:].decode("utf-8", "replace"))
        require(time.monotonic() - self.start <= MAX_WALL_SECONDS, "late binary completion")
        observed = inspect_outputs(paths, mode, mic, reset)
        final, linear = observed["final"], observed["linear"]
        count, frames = len(mic) // 2, len(mic) // (2 * HOP)
        self.accepted_calls += 1
        self.accepted_samples += count
        row.update({"completed_frames": frames, "output_sha256": digest(final),
                    "linear_sha256": digest(linear) if linear is not None else None,
                    "metadata_sha256": digest(paths["--metadata"].read_bytes()),
                    "frames_sha256": digest(paths["--frame-times"].read_bytes())})
        self.save()
        return observed

    def equivalence(self):
        probes = original.near_only_probes()
        mixed = original.signal(1, frames=100)
        fixtures = [(name, mic, b"\0" * len(mic)) for name, mic in probes.items()]
        fixtures.append(("mixed", mixed[0], mixed[1]))
        self.triples = {}
        for name, mic, render in fixtures:
            values = {mode: self.execute(name + "-" + mode, mode, mic, render) for mode in MODES}
            require(len({value["final"] for value in values.values()}) == 1,
                    "default/factory/export altered final PCM: " + name)
            normalized = []
            for value in values.values():
                config = json.loads(json.dumps(value["metadata"]["applied_config"]))
                config["echo_canceller"]["export_linear_aec_output"] = False
                normalized.append(config)
            require(normalized[0] == normalized[1] == normalized[2], "non-export APM config changed")
            self.triples[name] = values
        self.mixed = mixed

    def delays_and_units(self):
        observations = {}
        for name, mic in original.near_only_probes().items():
            actual = self.triples[name]["factory-on"]
            before = original.samples(mic)
            expected = [0.0] * 64 + [x / 32768.0 for x in before[:-64]]
            expected_bytes = b"".join(struct.pack("<f", value) for value in expected)
            require(actual["linear"] == expected_bytes, "near-only tap is not exact source-declared shift64")
            final = original.samples(actual["final"])
            item = {"tap_exact_normalized_shift64": True, "tap_initial_zero_samples": 64,
                    "tap_signal_delay_samples": 64, "final_signal_delay_samples": 128,
                    "first_frame_input_samples_required": HOP}
            if name == "impulse":
                observed = max(range(len(final)), key=lambda index: abs(final[index])) - 4 * HOP
                require(observed == 128, "synthetic impulse disagrees with declared final128")
                item["observed_final_impulse_peak_delay_samples"] = observed
            else:
                # Engineering-only observation over a frozen synthetic probe.
                # This diagnostic search is never used on speech or to set a lag.
                scores = [original.correlation_at_lag(before, final, lag) for lag in range(257)]
                observed = max(range(len(scores)), key=lambda lag: scores[lag])
                require(observed == 128, "synthetic chirp disagrees with declared final128")
                item["observed_final_chirp_peak_delay_samples"] = observed
                item["synthetic_correlation_at_predeclared_final_delay"] = scores[128]
            observations[name] = item
        self.result["synthetic_delay_observations"] = observations

    def repeat_future_reset(self):
        mic, render = self.mixed
        baseline = self.triples["mixed"]["factory-on"]
        repeated = self.execute("repeat", "factory-on", mic, render)
        for key in ("final", "linear"):
            require(repeated[key] == baseline[key], "fresh-instance repeat differs: " + key)
        cut = 50 * HOP
        changed_mic = original.pcm(original.samples(mic)[:cut] +
                                   [-x for x in original.samples(mic)[cut:]])
        changed_render = original.pcm(original.samples(render)[:cut] +
                                      [-x for x in original.samples(render)[cut:]])
        require(changed_mic != mic and changed_render != render, "future perturbation is empty")
        future = self.execute("future-perturbed", "factory-on", changed_mic, changed_render)
        require(future["final"][:cut * 2] == baseline["final"][:cut * 2] and
                future["linear"][:cut * 4] == baseline["linear"][:cut * 4], "future input leaked to prefix")
        reset = self.execute("reset", "factory-on", mic, render, reset=50)
        suffix = self.execute("fresh-suffix", "factory-on", mic[cut * 2:], render[cut * 2:])
        for key, width in (("final", 2), ("linear", 4)):
            require(reset[key][:cut * width] == baseline[key][:cut * width] and
                    reset[key][cut * width:] == suffix[key], "fresh reset lifecycle differs: " + key)

    def negatives(self):
        mic, render = original.signal(1, frames=1)
        cases = [
            ("missing-linear", "factory-on", {"--linear-output": None}),
            ("unrequested-linear", "default-off", {"--linear-output": "{linear}"}),
            ("disabled-linear", "factory-off", {"--linear-output": "{linear}"}),
            ("apm", "factory-on", {"--mode": "apm"}),
            ("stereo", "factory-on", {"--mic-channels": "2", "--channel-map": "0,1"}),
            ("unknown-mode", "factory-on", {"--aec3-export-mode": "unknown"}),
            ("empty-mode", "factory-on", {"--aec3-export-mode": ""}),
            ("same-linear-input", "factory-on", {"--linear-output": "{mic}"}),
            ("same-linear-final", "factory-on", {"--linear-output": "{output}"}),
        ]
        for name, mode, overrides in cases:
            self.execute("invalid-" + name, mode, mic, render, overrides=overrides, expect_error=True)
        self.execute("invalid-existing-linear", "factory-on", mic, render,
                     existing_linear=True, expect_error=True)
        self.execute("invalid-partial-frame", "factory-on", mic[:-2], render, expect_error=True)
        self.execute("invalid-length", "factory-on", mic, render * 2, expect_error=True)

    def budget(self):
        require(self.accepted_calls == EXPECTED_VALID_CALLS and
                self.accepted_samples == EXPECTED_VALID_SAMPLES, "fixed13/8.3s execution accounting")
        require(len(self.rows) == EXPECTED_VALID_CALLS + 12, "fixed negative/positive invocation count")
        require(self.requested_samples == EXPECTED_REQUESTED_SAMPLES <= MAX_REQUESTED_SAMPLES,
                "requested-audio budget differs")
        require(time.monotonic() - self.start <= MAX_WALL_SECONDS, "wall budget exceeded")

    def run(self):
        try:
            for name, operation in (
                    ("runtime-identity-initial", self.runtime_start),
                    ("three-way-final-byte-equivalence", self.equivalence),
                    ("source-declared-delay-and-units", self.delays_and_units),
                    ("repeat-future-prefix-and-reset", self.repeat_future_reset),
                    ("invalid-observation-contracts", self.negatives),
                    ("fixed-invocation-and-audio-budget", self.budget),
                    ("runtime-identity-stable", self.runtime_finish)):
                self.check(name, operation)
            self.result["status"] = "PASS_ENGINEERING_ONLY"
        except Exception as exc:
            self.result["status"] = "FAIL"
            if not self.failures:
                self.failures.append({"name": "engineering", "error": str(exc)})
        self.save()
        if self.result["wall_seconds"] > MAX_WALL_SECONDS:
            self.result["status"] = "FAIL"
            self.failures.append({"name": "final-save", "error": "engineering deadline exceeded"})
            self.save()
        return 0 if self.result["status"] == "PASS_ENGINEERING_ONLY" else 1


class SavedFixtures(Fixtures):
    """Replay only validation over saved bytes; never construct or invoke a binary."""

    def __init__(self, report, root):
        self.report, self.output = report, root
        self.result = {}
        self.position = 0
        self.requested_samples = self.accepted_samples = self.accepted_calls = 0
        self.expected_files = {"engineering.json"}
        self.wall_sum = 0.0

    def execute(self, name, mode, mic, render, reset=None, overrides=None,
                existing_linear=False, expect_error=False):
        require(self.position < len(self.report["calls"]), "missing saved invocation")
        row = self.report["calls"][self.position]
        self.position += 1
        recorded_root = Path(self.report["execution_output"])
        _, expected_command = invocation(self.report["binary"], recorded_root / name,
                                         mode, reset, overrides)
        require(row["case_id"] == name and row["command"] == expected_command and
                row["mode"] == "aec3" and type(row["mic_channels"]) is int and row["mic_channels"] == 1 and
                row["aec3_export_mode"] == mode and row["reset_before_frame"] == reset and
                row["expected_error"] is expect_error, "saved invocation identity differs")
        require(type(row["returncode"]) is int and row["returncode"] == (2 if expect_error else 0) and
                row["status"] == ("ERROR" if expect_error else "OK"), "saved invocation did not finish")
        finite_time(row["wall_seconds"], 30, name)
        self.wall_sum += row["wall_seconds"]
        require(type(row["requested_samples"]) is int and
                row["requested_samples"] == (len(mic) + 1) // 2 <= RATE,
                "saved request audio budget differs")
        self.requested_samples += row["requested_samples"]
        folder = self.output / name
        paths, _ = invocation(self.report["binary"], folder, mode, reset, overrides)
        for key, expected in (("--mic", mic), ("--render", render)):
            raw = paths[key].read_bytes()
            require(raw == expected and row[key[2:] + "_sha256"] == digest(raw),
                    "saved synthetic input differs")
        names = {"mic.pcm", "render.pcm", "stdout.log", "stderr.log"}
        for filename in ("stdout.log", "stderr.log"):
            raw = (folder / filename).read_bytes()
            require(row[filename[:-4] + "_sha256"] == digest(raw), "saved process log hash differs")
        if expect_error:
            require(b'"status":"ERROR"' in (folder / "stderr.log").read_bytes(),
                    "saved explicit input rejection is absent")
            if existing_linear:
                names.add("linear.f32le")
                require(paths["--linear-output"].read_bytes() == PRESERVED_LINEAR,
                        "saved existing output was overwritten")
            result = None
        else:
            names.update(("output.pcm", "metadata.json", "frames.jsonl"))
            if mode == "factory-on":
                names.add("linear.f32le")
            result = inspect_outputs(paths, mode, mic, reset)
            for key, raw in (("output", result["final"]), ("linear", result["linear"]),
                             ("metadata", paths["--metadata"].read_bytes()),
                             ("frames", paths["--frame-times"].read_bytes())):
                require(row[key + "_sha256"] == (digest(raw) if raw is not None else None),
                        "saved output hash differs: " + key)
            require(type(row["completed_frames"]) is int and
                    row["completed_frames"] == len(mic) // (2 * HOP), "saved completed frames differ")
            self.accepted_calls += 1
            self.accepted_samples += len(mic) // 2
        require({path.name for path in folder.iterdir()} == names, "missing/unexpected case file")
        self.expected_files.update(name + "/" + filename for filename in names)
        return result


def verify_engineering(receipt: Path, binary_sha: str, build_sha: str, revision: str) -> dict:
    """Pure byte readback of the fixed 25-process/13-DSP experiment; no ldd or SDK."""
    receipt = Path(receipt)
    require(receipt.name == "engineering.json" and receipt.is_file() and not receipt.is_symlink(),
            "expected regular engineering.json")
    root = receipt.parent
    require(not any(path.is_symlink() for path in (root,) + tuple(root.parents)),
            "engineering parent contains symlink")
    files, directories, total, entries = set(), set(), 0, 0
    for path in root.rglob("*"):
        entries += 1
        require(entries <= 538, "engineering entry budget")
        require(not path.is_symlink() and (path.is_dir() or path.is_file()), "unsafe engineering path")
        if path.is_file():
            info = path.stat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not info.st_mode & 0o7000,
                    "regular singly-linked engineering file without special mode required")
            total += info.st_size
            files.add(path.relative_to(root).as_posix())
            require(len(files) <= 512 and total <= 8 * 1024 * 1024, "engineering byte/file budget")
        else:
            directories.add(path.relative_to(root).as_posix())
    report = json.loads(receipt.read_text(encoding="utf-8"))
    require(report["schema_version"] == 1 and report["fixture_id"] == FIXTURE_ID and
            report["status"] == "PASS_ENGINEERING_ONLY" and report["failures"] == [],
            "saved engineering did not pass")
    require(report["code_revision"] == revision and report["binary_sha256"] == binary_sha and
            report.get("build_receipt_sha256") == build_sha, "engineering provenance differs")
    for value, length in ((revision, 40), (binary_sha, 64), (build_sha, 64)):
        require(isinstance(value, str) and len(value) == length and
                all(character in "0123456789abcdef" for character in value), "invalid provenance digest")
    for key in ("binary", "execution_output"):
        path = Path(report[key])
        require(path.is_absolute() and ".." not in path.parts and str(path) == report[key],
                "invalid recorded absolute execution path")
    require(Path(report["binary"]).name == "webrtc-aec3-runner", "unexpected recorded binary name")
    require(report["fixture_source_sha256"] == digest(Path(__file__).read_bytes()) and
            report["base_fixture_source_sha256"] == digest(Path(original.__file__).read_bytes()),
            "engineering fixture/generator source differs")
    import webrtc_aec3_ci as runtime
    require(report["runtime_identity_source_sha256"] == digest(Path(runtime.__file__).read_bytes()),
            "runtime identity helper source differs")
    require(report["runtime_observations_completed"] == 2 and
            report["runtime_identity_after"] == report["runtime_identity"] and
            isinstance(report["runtime_identity"], dict) and report["runtime_identity"],
            "runtime identity observation is incomplete/unstable")
    require(report["checks"] == [{"name": name, "status": "PASS"} for name in CHECK_NAMES],
            "engineering checks differ")
    require(report["signal_delay_predeclared_samples"] == {"linear": 64, "final": 128} and
            report["data_role"] == "synthetic_engineering_only_not_real_acoustic_evidence" and
            all(report[key] is False for key in
                ("acoustic_acceptance", "promotion_authority", "physical_target_measurement")),
            "engineering role or fixed delay differs")
    finite_time(report["wall_seconds"], MAX_WALL_SECONDS, "engineering")
    require(isinstance(report["calls"], list) and len(report["calls"]) == 25,
            "fixed invocation set differs")
    # Only these pure methods are replayed. Runtime observations are never rerun.
    saved = SavedFixtures(report, root)
    saved.equivalence()
    saved.delays_and_units()
    saved.repeat_future_reset()
    saved.negatives()
    require(saved.position == 25 and files == saved.expected_files and
            directories == {row["case_id"] for row in report["calls"]},
            "engineering file/directory/call closure differs")
    require(saved.accepted_calls == EXPECTED_VALID_CALLS and
            saved.accepted_samples == EXPECTED_VALID_SAMPLES and
            saved.requested_samples == EXPECTED_REQUESTED_SAMPLES <= MAX_REQUESTED_SAMPLES,
            "saved engineering audio budget differs")
    require(report["accepted_binary_calls"] == 13 and report["binary_process_calls"] == 25 and
            report["rejected_before_dsp_calls"] == 12 and
            report["accepted_capture_audio_seconds"] == EXPECTED_VALID_SAMPLES / RATE and
            report["requested_capture_audio_seconds"] == EXPECTED_REQUESTED_SAMPLES / RATE and
            saved.wall_sum <= report["wall_seconds"], "engineering reported accounting differs")
    require(saved.result["synthetic_delay_observations"] == report["synthetic_delay_observations"],
            "synthetic delay observations do not rederive")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    try:
        return Fixtures(args.binary, args.output, args.build_receipt, args.code_revision).run()
    except (OSError, ValueError, RuntimeError) as exc:
        print("AEC3 linear engineering: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
