#!/usr/bin/env python3
"""Offline controls for protected product soak duration. No DUT/72h execution."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).with_name("product_soak_observed_duration.py")
SPEC = importlib.util.spec_from_file_location("soak_duration_guard", MODULE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

SECONDS = 259200
START = 100000000000
END = START + SECONDS * 1000000000
CONTROL = "a" * 40
RELEASE = "b" * 40


def fixture(seconds=SECONDS):
    return {
        "schema_version": 1,
        "collector_version": "2.1",
        "kind": "alsa-route-soak",
        "route": {"capture_device": "hw:0,0", "sample_rate_hz": 16000, "mic_channels": 2},
        "fault_injection": {"profile": "none", "observed_required_faults": True},
        "soak": {
            "hours": seconds / 3600.0, "passed": True, "xruns": 0,
            "deadline_misses": 0, "overruns": 0,
            "input_full_events": 0, "output_drop_events": 0,
            "failed_frames": 0,
        },
        "raw": f"produced={seconds*100} received={seconds*100} xruns=0 dsp_overruns=0",
        "returncode": 0,
    }


def encode(x):
    return (json.dumps(x, sort_keys=True) + "\n").encode()


class GuardTests(unittest.TestCase):
    def observed(self, data=None, **kwargs):
        values = dict(seconds=SECONDS, start_ns=START, end_ns=END,
                      control_sha=CONTROL, release_source_sha=RELEASE)
        values.update(kwargs)
        if data is None:
            data = fixture()
        raw = data if type(data) is bytes else encode(data)
        return M.observe(raw, **values)

    def denied(self, reason, data=None, **kwargs):
        with self.assertRaises(M.Rejected) as err:
            self.observed(data, **kwargs)
        self.assertEqual(err.exception.reason, reason)

    def test_exact_true_72_hours_accepted(self):
        output = self.observed()
        obs = output["duration_observation"]
        self.assertEqual(output["soak"]["hours"], 72.0)
        self.assertEqual(output["soak"]["requested_hours"], 72.0)
        self.assertEqual(output["soak"]["requested_seconds"], SECONDS)
        self.assertEqual(obs["expected_frames"], 25920000)
        self.assertEqual(obs["observed_elapsed_seconds"], SECONDS)
        self.assertFalse(obs["real_hardware_run_claimed_by_this_helper"])

    def test_longer_real_duration_accepted(self):
        output = self.observed(end_ns=END + 5000000000)
        self.assertGreater(output["soak"]["hours"], 72.0)

    def test_fast_finish_rejected(self):
        self.denied("SOAK_OBSERVED_DURATION_TOO_SHORT", end_ns=START + 10000000000)

    def test_one_nanosecond_short_rejected(self):
        self.denied("SOAK_OBSERVED_DURATION_TOO_SHORT", end_ns=END - 1)

    def test_zero_or_equal_clock_rejected(self):
        for start,end in ((0,END),(START,START),(END,START)):
            self.denied("SOAK_INVALID_MONOTONIC_CLOCK", start_ns=start, end_ns=end)

    def test_noninteger_clock_rejected(self):
        self.denied("SOAK_INVALID_MONOTONIC_CLOCK", start_ns=True)
        self.denied("SOAK_INVALID_MONOTONIC_CLOCK", end_ns=float(END))

    def test_invalid_source_sha_rejected(self):
        self.denied("SOAK_SOURCE_IDENTITY_INVALID", control_sha="invalid")
        self.denied("SOAK_SOURCE_IDENTITY_INVALID", release_source_sha="a"*39)

    def test_bad_requested_seconds_rejected(self):
        for n in (0,-1,True,42949673):
            self.denied("SOAK_INVALID_REQUESTED_SECONDS", seconds=n)

    def test_zero_produced_frames_rejected(self):
        data = fixture()
        data["raw"] = "produced=0 received=0 xruns=0"
        self.denied("SOAK_FRAME_COUNT_INCOMPLETE_OR_DRIFT", data)

    def test_short_produced_frames_rejected(self):
        data = fixture()
        data["raw"] = "produced=25919999 received=25919999 xruns=0"
        self.denied("SOAK_FRAME_COUNT_INCOMPLETE_OR_DRIFT", data)

    def test_mismatched_frames_rejected(self):
        data = fixture()
        data["raw"] = "produced=25920000 received=25919999 xruns=0"
        self.denied("SOAK_FRAME_COUNT_INCOMPLETE_OR_DRIFT", data)

    def test_extra_frames_rejected(self):
        data = fixture()
        data["raw"] = "produced=25920001 received=25920001 xruns=0"
        self.denied("SOAK_FRAME_COUNT_INCOMPLETE_OR_DRIFT", data)

    def test_duplicate_counter_rejected(self):
        data = fixture()
        data["raw"] += " produced=25920000"
        self.denied("SOAK_COUNTER_MISSING_DUPLICATE_OR_INVALID", data)

    def test_missing_counter_rejected(self):
        data = fixture()
        data["raw"] = "produced=25920000"
        self.denied("SOAK_COUNTER_MISSING_DUPLICATE_OR_INVALID", data)

    def test_raw_bound_rejected(self):
        data = fixture()
        data["raw"] = "0" * (M.MAX_RAW + 1)
        self.denied("SOAK_RAW_COUNTER_BOUND", data)

    def test_missing_pass_rejected(self):
        data = fixture()
        data["soak"].pop("passed")
        self.denied("SOAK_ORIGINAL_RESULT_NOT_PASS", data)

    def test_false_pass_rejected(self):
        data = fixture()
        data["soak"]["passed"] = False
        self.denied("SOAK_ORIGINAL_RESULT_NOT_PASS", data)

    def test_nonzero_returncode_rejected(self):
        data = fixture()
        data["returncode"] = 1
        self.denied("SOAK_ORIGINAL_COLLECTOR_IDENTITY_OR_RESULT", data)

    def test_wrong_collector_or_kind_rejected(self):
        data = fixture()
        data["collector_version"] = "unknown"
        self.denied("SOAK_ORIGINAL_COLLECTOR_IDENTITY_OR_RESULT", data)
        data = fixture()
        data["kind"] = "target-benchmark"
        self.denied("SOAK_ORIGINAL_COLLECTOR_IDENTITY_OR_RESULT", data)

    def test_wrong_requested_hours_rejected(self):
        data = fixture()
        data["soak"]["hours"] = 0.5
        self.denied("SOAK_ORIGINAL_REQUESTED_DURATION_DRIFT", data)

    def test_wrong_fault_profile_rejected(self):
        data = fixture()
        data["fault_injection"]["profile"] = "accelerated"
        self.denied("SOAK_NOMINAL_FAULT_PROFILE_REQUIRED", data)

    def test_refuse_second_observation(self):
        data = self.observed()
        self.denied("SOAK_OBSERVATION_ALREADY_PRESENT", data)

    def test_duplicate_json_field_rejected(self):
        self.denied("SOAK_DUPLICATE_JSON_KEY", b'{"soak":{},"soak":{}}')

    def test_literal_nonfinite_rejected(self):
        for value in (b'NaN', b'Infinity', b'-Infinity'):
            self.denied("SOAK_NONFINITE_JSON", b'{"v":' + value + b'}')

    def test_numeric_overflow_rejected(self):
        self.denied("SOAK_NONFINITE_JSON", b'{"v":1e999}')

    def test_invalid_utf8_and_malformed_json_rejected(self):
        self.denied("SOAK_INVALID_JSON", b'{')
        self.denied("SOAK_INVALID_JSON", b'{"a":"\xff"}')

    def test_missing_root_rejected(self):
        self.denied("SOAK_INVALID_ROOT", b'[]')

    def test_missing_original_body_rejected(self):
        self.denied("SOAK_INPUT_BYTES_BOUND", b'')
        self.denied("SOAK_INPUT_BYTES_BOUND", b' '* (M.MAX_BYTES + 1))

    def test_original_sha256_bound(self):
        raw = encode(fixture())
        output = self.observed(raw)
        self.assertEqual(output["duration_observation"]["original_collector_json_sha256"],
                         hashlib.sha256(raw).hexdigest())

    def test_atomic_output_and_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "soak.json"
            raw = encode(fixture())
            path.write_bytes(raw)
            obs = M.write_observation(path, SECONDS, START, END, CONTROL, RELEASE)
            output = json.loads(path.read_bytes())
            self.assertEqual(output["duration_observation"], obs)
            self.assertEqual(output["soak"]["hours"], 72.0)
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_failure_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "soak.json"
            raw = encode(fixture())
            path.write_bytes(raw)
            with self.assertRaises(M.Rejected):
                M.write_observation(path, SECONDS, START, START+1000000000,
                                    CONTROL, RELEASE)
            self.assertEqual(path.read_bytes(), raw)

    def test_no_double_rewriting(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "soak.json"
            path.write_bytes(encode(fixture()))
            M.write_observation(path, SECONDS, START, END, CONTROL, RELEASE)
            preserved = path.read_bytes()
            with self.assertRaises(M.Rejected):
                M.write_observation(path, SECONDS, START, END, CONTROL, RELEASE)
            self.assertEqual(path.read_bytes(), preserved)

    def test_workflow_executes_protected_guard_and_preserves_source(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root / ".github/workflows/product-certification.yml").read_text(
            encoding="utf-8")
        self.assertIn("ref: ${{ needs.resolve.outputs.sha }}", workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', workflow)
        self.assertIn('test "$(git -C certification-control rev-parse HEAD)" = "$GITHUB_SHA"',
                      workflow)
        self.assertIn("soak_start_ns=$(python3 -c 'import time; print(time.monotonic_ns())')",
                      workflow)
        self.assertIn("soak_end_ns=$(python3 -c 'import time; print(time.monotonic_ns())')",
                      workflow)
        self.assertIn(
            "python3 certification-control/.github/program/product_soak_observed_duration.py",
            workflow)
        self.assertIn("--soak-json /tmp/soak.json", workflow)
        self.assertIn("--release-source-sha '${{ needs.resolve.outputs.sha }}'", workflow)
        self.assertIn("--soak-json /tmp/soak.json --deployment-provenance", workflow)

    def test_no_runtime_or_dut_claim(self):
        obs = self.observed()["duration_observation"]
        self.assertEqual(obs["source"], M.SOURCE)
        self.assertFalse(obs["real_hardware_run_claimed_by_this_helper"])
        self.assertEqual(obs["release_source_sha"], RELEASE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
