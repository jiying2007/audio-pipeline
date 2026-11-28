#!/usr/bin/env python3
"""Pure metadata/arithmetic negatives. No real speech, SDK, codec or build."""
from __future__ import annotations

import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest import mock

import webrtc_aec3_linear_tap as study


class MathTests(unittest.TestCase):
    def test_canonical_float_units_and_exact_identity(self):
        target = [0.125, -0.25, 0.375, -0.5] * 8
        actual = target[:]
        actual[3] += 2 ** -20
        value = study.span_metrics(target, actual, 0, len(target), 0)
        self.assertEqual(value["si_sdr_db"], study.reference.speech.si_sdr_span(target, actual, 0, 0, len(target)))
        self.assertFalse(value["exact_float_identity"])
        self.assertTrue(value["projection_identifiable"])
        self.assertFalse(value["degenerate_projection"])
        self.assertEqual(value["output_energy"], value["estimate_energy"])
        self.assertGreater(value["normalized_mse"], 0)
        identity = study.span_metrics(target, target, 0, len(target), 0)
        self.assertTrue(identity["exact_float_identity"])
        self.assertEqual(identity["normalized_mse"], 0)

    def test_declared_offsets_and_common_span_are_not_searched(self):
        target = [0.25, -0.25] * 80
        linear = [0.0] * 64 + target[:96]
        final = [0.0] * 128 + target[:32]
        self.assertEqual(study.span_metrics(target, linear, 0, 32, 64)["normalized_mse"], 0)
        self.assertEqual(study.span_metrics(target, final, 0, 32, 128)["normalized_mse"], 0)
        with self.assertRaisesRegex(ValueError, "outside"):
            study.span_metrics(target, final, 0, 33, 128)
        with self.assertRaisesRegex(ValueError, "outside"):
            study.span_metrics(target, final, 0, 32, -1)

    def test_zero_output_keeps_canonical_zero_but_is_not_identifiable(self):
        target = [0.25, -0.5] * 16
        zero = study.span_metrics(target, [0.0] * 32, 0, 32, 0)
        good = study.span_metrics(target, target, 0, 32, 0)
        self.assertEqual(zero["si_sdr_db"], 0.0)
        self.assertEqual(zero["normalized_mse"], 1.0)
        self.assertEqual(zero["projected_target_energy"], 0.0)
        self.assertFalse(zero["projection_identifiable"])
        self.assertEqual(study.primary_decision(zero, good), "NOT_IDENTIFIABLE")
        self.assertEqual(study.primary_decision(good, zero), "NOT_IDENTIFIABLE")

    def test_orthogonal_projection_is_not_identifiable(self):
        target, estimate = [0.5, 0.5] * 16, [0.5, -0.5] * 16
        row = study.span_metrics(target, estimate, 0, 32, 0)
        self.assertTrue(study.finite(row["si_sdr_db"]))
        self.assertEqual(row["projection_scale"], 0)
        self.assertFalse(row["projection_identifiable"])
        self.assertEqual(study.primary_decision(row, row), "NOT_IDENTIFIABLE")

    def test_zero_target_preserves_nulls(self):
        row = study.span_metrics([0.0] * 16, [0.2] * 16, 0, 16, 0)
        self.assertIsNone(row["si_sdr_db"])
        self.assertIsNone(row["normalized_mse"])
        self.assertIsNone(row["projection_scale"])
        self.assertFalse(row["projection_identifiable"])
        self.assertEqual(study.primary_decision(row, row), "NOT_IDENTIFIABLE")

    def test_all_four_directional_outcomes_and_equal_boundary(self):
        def row(score, mse, identifiable=True):
            return {"si_sdr_db": score, "normalized_mse": mse, "projection_identifiable": identifiable}
        final = row(3, 0.2)
        self.assertEqual(study.primary_decision(row(4, 0.1), final), "SUPPORTED_IN_DISCLOSED_WINDOW")
        self.assertEqual(study.primary_decision(row(3, 0.2), final), "NOT_SUPPORTED_IN_DISCLOSED_WINDOW")
        self.assertEqual(study.primary_decision(row(4, 0.2), final), "INCONCLUSIVE_MIXED_INDICATORS")
        self.assertEqual(study.primary_decision(row(2, 0.1), final), "INCONCLUSIVE_MIXED_INDICATORS")
        self.assertEqual(study.primary_decision(row(None, 0.1), final), "NOT_IDENTIFIABLE")
        self.assertEqual(study.primary_decision(row(float("inf"), 0.1), final), "NOT_IDENTIFIABLE")

    def test_float32_partial_nonfinite_and_range_rejected(self):
        valid = struct.pack("<3f", -1, 0.12500011920928955, 1)
        self.assertEqual(study.fixture.linear_samples(valid)[1], 0.12500011920928955)
        for raw in (b"x", struct.pack("<f", float("nan")), struct.pack("<f", float("inf")), struct.pack("<f", 1.01)):
            with self.subTest(raw_length=len(raw)), self.assertRaises(RuntimeError):
                study.fixture.linear_samples(raw)

    def test_raw_endpoints_do_not_claim_clipping(self):
        value = study.amplitude([-1, 0, 1], 1)
        self.assertEqual(value["negative_endpoint_count"], 1)
        self.assertEqual(value["positive_endpoint_count"], 1)
        self.assertFalse(value["endpoint_counts_are_proven_clipping_events"])

    def test_projection_energy_matches_canonical_multiply_order(self):
        target = [0.000123, -0.1564321, 0.8754321, -0.998123] * 16
        actual = [x * 0.37 + (index % 3) * 0.0001 for index, x in enumerate(target)]
        energy = cross = 0.0
        for ref, est in zip(target, actual):
            energy += ref * ref
            cross += ref * est
        alpha, projected = cross / energy, 0.0
        for ref in target:
            projection = alpha * ref
            projected += projection * projection
        row = study.span_metrics(target, actual, 0, len(target), 0)
        self.assertEqual(row["projection_scale"], alpha)
        self.assertEqual(row["projected_target_energy"], projected)

    def test_far_blocks_keep_all_nulls_and_canonical_floor(self):
        plan = {"metrics": {"final_far_samples": [0, 38], "far_block_samples": 2}}
        result = study.far_metrics([0.0] * 40, [0.0] * 40, 0, plan)
        self.assertEqual(len(result["blocks"]), 19)
        self.assertTrue(all(row["echo_to_output_ratio_db"] is None for row in result["blocks"]))
        self.assertIsNone(result["aggregate_ratio_db"])
        result = study.far_metrics([0.5] * 40, [0.25] * 40, 0, plan)
        self.assertAlmostEqual(result["aggregate_ratio_db"], 6.020599913279624)
        self.assertTrue(all(row["samples"] == 2 for row in result["blocks"]))

    def test_far_zero_residual_uses_canonical_mean_square_floor(self):
        plan = {"metrics": {"final_far_samples": [0, 38], "far_block_samples": 2}}
        zero_output = study.far_metrics([0.5] * 40, [0.0] * 40, 0, plan)
        self.assertEqual(zero_output["aggregate_ratio_db"], 10 * math.log10((19 * 0.25) / 1e-30))


def saved_case(root):
    folder = root / "case"
    observed = folder / "observation"
    observed.mkdir(parents=True)
    final = struct.pack("<160h", *([0] * 160))
    case = {"samples": 160, "archived_aec3_final": {"bytes": len(final), "sha256": hashlib.sha256(final).hexdigest()}}
    for path in (folder / "archived-final.pcm", folder / "mic.pcm", folder / "render.pcm", observed / "output.pcm"):
        path.write_bytes(final)
    (observed / "linear.f32").write_bytes(struct.pack("<160f", *([0.0] * 160)))
    for name in ("stdout.log", "stderr.log"):
        (observed / name).write_bytes(b"")
    for name in ("invocation-start.json", "command.json"):
        study.write_json(observed / name, {})
    config = study.reference.config_for("aec3")
    config["echo_canceller"]["export_linear_aec_output"] = True
    meta = {"schema_version": 1, "adapter": "webrtc-aec3-offline-v1", "status": "OK", "detail": "",
            "mode": "aec3", "sample_format": "S16LE", "sample_rate_hz": 16000, "frame_samples": 160,
            "mic_channels": 1, "render_channels": 1, "output_channels": 1, "channel_map": [0],
            "actual_processing_channels": 1, "actual_processing_sample_rate_hz": 16000,
            "input_frames": 1, "completed_frames": 1, "output_sample_frames": 160,
            "stream_delay_ms": 0, "adapter_lookahead_frames": 0, "padded_samples": 0, "tail_flush_samples": 0,
            "algorithmic_latency_samples": 128, "algorithmic_latency_ms": 8,
            "first_output_frame_input_samples_required": 160, "first_output_frame_host_completion_ns": 20,
            "reset_before_frame": None, "adapter_normalization": False, "physical_target_measurement": False,
            "acoustic_acceptance": False, "promotion_authority": False, "host_timing_only": True,
            "pure_linear_aec": False, "requested_config": config, "applied_config": config,
            "call_order": "ProcessReverseStream,set_stream_delay_ms(0),ProcessStream,GetLinearAecOutput",
            "aec3_linear_observation": {
                "mode": "factory-on", "enabled": True, "internal_filter_export_linear_aec_output": True,
                "factory": "explicit_default_aec3", "tap_signal_delay_samples": 64,
                "final_signal_delay_samples": 128, "tap_lead_relative_to_final_samples": 64,
                "upstream_getter_clamp_float_s16": [-32768, 32768], "upstream_getter_divisor": 32768,
                "output_samples": 160, "format": "F32LE", "channels": 1, "samples_per_frame": 160,
                "first_frame_input_samples_required": 160, "capture_fixed_delay_samples": 0,
                "distribution_commit": "846fe90a289f58b7c9303a635142aa2c7caa93e5",
                "adapter_scaling": False, "adapter_clipping": False, "adapter_quantization": False, "pure_lti": False,
                "first_linear_frame_host_completion_ns": 21}}
    frame = {"frame_index": 0, "input_sample_frames_available": 160, "output_sample_frames_emitted": 160,
             "host_processing_begin_ns": 10, "host_processing_completed_ns": 20, "host_processing_duration_ns": 10,
             "algorithmic_latency_samples": 128, "algorithmic_latency_ms": 8, "reset_before_frame": False,
             "aec3_export_mode": "factory-on", "linear_output_sample_frames_emitted": 160,
             "linear_signal_delay_samples": 64, "linear_getter_completed_ns": 21, "host_timing_only": True}
    study.write_json(observed / "metadata.json", meta)
    (observed / "frames.jsonl").write_text(json.dumps(frame) + "\n")
    return folder, case, meta, frame


class EvidenceTests(unittest.TestCase):
    def test_current_plan_exact_hash_roles_counts_windows(self):
        value = study.frozen_plan()
        self.assertEqual(len(value["cases"]), 6)
        self.assertEqual(sum(row["samples"] for row in value["cases"]), 1536000)
        self.assertEqual(value["primary"]["effective_unique_conditions"], 1)
        self.assertEqual(value["timing_contract"]["common_target_span"], [0, 255872])
        self.assertEqual(value["metrics"]["near_phase_samples"]["double-before"], [97600, 126400])
        self.assertFalse(value["promotion_allowed"])

    def test_science_command_has_one_explicit_export_and_no_reset(self):
        command = study.runner_command(Path("/e/bundle/reference/bin/webrtc-aec3-runner"), Path("/e/cases/c"))
        self.assertEqual(command.count("--aec3-export-mode"), 1)
        self.assertEqual(command[-4:], ["--aec3-export-mode", "factory-on", "--linear-output", "/e/cases/c/observation/linear.f32"])
        self.assertNotIn("--reset-before-frame", command)

    def test_valid_saved_observation_with_no_execution(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(study.subprocess, "Popen", side_effect=AssertionError("no process")), mock.patch.object(ctypes, "CDLL", side_effect=AssertionError("no native")):
            folder, case, _, _ = saved_case(Path(directory))
            result = study.observation_outputs(folder, case)
            self.assertEqual(len(result["linear"]), 640)
            self.assertEqual(len(result["final"]), 320)

    def test_final_mismatch_rejects_before_tap_or_metric_read(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, case, _, _ = saved_case(Path(directory))
            (folder / "observation/output.pcm").write_bytes(b"\x01\x00" * 160)
            with mock.patch.object(study.fixture, "inspect_outputs", side_effect=AssertionError("too late")), self.assertRaisesRegex(ValueError, "NEW_FINAL_DIFFERS"):
                study.observation_outputs(folder, case)

    def test_missing_extra_partial_and_duplicate_trace_rejected(self):
        for change in ("missing", "extra", "partial", "duplicate", "bool"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                folder, case, _, frame = saved_case(Path(directory))
                if change == "missing":
                    del frame["linear_signal_delay_samples"]
                elif change == "extra":
                    frame["undeclared"] = 1
                elif change == "bool":
                    frame["algorithmic_latency_samples"] = True
                raw = json.dumps(frame) + "\n"
                if change == "partial":
                    raw = raw.rstrip("\n")
                elif change == "duplicate":
                    raw = raw.replace('"frame_index": 0', '"frame_index": 0, "frame_index": 0')
                (folder / "observation/frames.jsonl").write_text(raw)
                with self.assertRaises(ValueError):
                    study.observation_outputs(folder, case)

    def test_duplicate_metadata_and_extra_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, case, _, _ = saved_case(Path(directory))
            path = folder / "observation/metadata.json"
            path.write_text(path.read_text().replace('"status": "OK"', '"status": "OK", "status": "OK"'))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                study.observation_outputs(folder, case)
        with tempfile.TemporaryDirectory() as directory:
            folder, case, _, _ = saved_case(Path(directory))
            (folder / "observation/extra-output.pcm").write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "observation files"):
                study.observation_outputs(folder, case)

    def test_failures_preserve_original_bytes_and_reader_stops_early(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in (("result.json", b'{"unaltered": "result"}\n'), ("manifest.json", b'not-even-valid-json\n')):
                (root / name).write_bytes(data)
            study.fail_output(root, ValueError("late seal error"))
            self.assertEqual((root / "result-before-failure.json").read_bytes(), b'{"unaltered": "result"}\n')
            self.assertEqual((root / "manifest-before-failure.json").read_bytes(), b'not-even-valid-json\n')
            with mock.patch.object(study.ci, "verify_bundle", side_effect=AssertionError("reader must reject earlier")), self.assertRaisesRegex(ValueError, "failed prefix"):
                study.verify(root)
        for marker in study.FAILURE_NAMES:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / marker).write_bytes(b"x")
                with self.assertRaises(ValueError):
                    study.reject_failure(root)

    def test_execution_binary_path_cannot_be_repointed(self):
        bundle = {"manifest": {"paths": {"runner": "reference/bin/webrtc-aec3-runner"}}}
        good = {"execution_root": "/archived/path", "processor_execution_path": "/archived/path/bundle/reference/bin/webrtc-aec3-runner"}
        self.assertEqual(study.execution_paths(good, bundle)[0], Path("/archived/path"))
        for changed in (dict(good, processor_execution_path="/other/bin"), dict(good, execution_root="/archived/../path"), dict(good, execution_root="relative")):
            with self.assertRaises(ValueError):
                study.execution_paths(changed, bundle)

    def test_clean_environment_and_strict_return_code_budget(self):
        command = ["/portable/runner"]
        env = study.ci.execution_environment(Path("/portable"))
        self.assertEqual(set(env), {"PATH", "LC_ALL", "PYTHONDONTWRITEBYTECODE", "LD_LIBRARY_PATH"})
        begin = {"command": command, "environment": env, "started_monotonic_ns": 1000000000,
                 "per_case_timeout_seconds": 30.0, "retry_index": 0}
        record = dict(begin, returncode=0, finished_monotonic_ns=2000000000, elapsed_seconds=1.0)
        study.validate_call(record, begin, command, env)
        for changed in (dict(record, returncode=False), dict(record, elapsed_seconds=31), dict(record, environment=dict(env, LD_PRELOAD="bad")), dict(record, retry_index=1)):
            with self.assertRaises(ValueError):
                study.validate_call(changed, begin, command, env)

    def test_single_invocation_propagates_exact_sanitized_environment(self):
        environment = study.ci.execution_environment(Path("/sealed/bundle"))
        process = mock.Mock()
        process.wait.return_value = 0
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(study.subprocess, "Popen", return_value=process) as call:
            folder = Path(directory)
            result = study.run_process(["/sealed/runner"], folder, environment, time.monotonic() + 10)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.kwargs["env"], environment)
            self.assertTrue(call.call_args.kwargs["start_new_session"])
            self.assertEqual(result["retry_index"], 0)
            self.assertEqual({p.name for p in folder.iterdir()}, {"stdout.log", "stderr.log", "invocation-start.json", "command.json"})

    def test_lock_wrong_size_hash_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source").write_bytes(b"locked")
            spec = {"bytes": 6, "sha256": hashlib.sha256(b"locked").hexdigest()}
            self.assertEqual(study.locked_file(root / "source", spec), b"locked")
            for bad in (dict(spec, bytes=5), dict(spec, sha256="0" * 64)):
                with self.assertRaises(ValueError):
                    study.locked_file(root / "source", bad)
            (root / "alias").symlink_to(root / "source")
            with self.assertRaises(ValueError):
                study.locked_file(root / "alias", spec)

    def test_correlated_observation_mismatch_is_method_failure(self):
        ids = ["p1-none", "p1-steer", "p1-path"]
        metric = {"si_sdr_db": 1.0, "normalized_mse": 0.5, "projection_identifiable": True}
        rows = [{"case_id": name, "metrics": {view: {"near": {"before": metric}} for view in study.DELAYS},
                 "linear_minus_final_near": {"before": {"si_sdr_db": 0.0, "normalized_mse": 0.0}}} for name in ids]
        plan = {"primary": {"case_id": ids[0], "phase": "before", "target_window_samples": [0, 16],
                            "correlated_consistency_cases": ids[1:]}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ids:
                folder = root / "cases" / name / "observation"
                folder.mkdir(parents=True)
                (folder / "linear.f32").write_bytes(struct.pack("<160f", *([0.25] * 160)))
                (folder / "output.pcm").write_bytes(struct.pack("<160h", *([8192] * 160)))
            result = study.primary_summary(rows, plan, root)
            self.assertEqual(result["effective_unique_conditions"], 1)
            self.assertTrue(all(row["same_aligned_output_bytes_as_primary"] for row in result["correlated_consistency_checks"]))
            broken = root / "cases" / ids[-1] / "observation/linear.f32"
            data = bytearray(broken.read_bytes())
            data[64 * 4:65 * 4] = struct.pack("<f", 0.125)
            broken.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "CORRELATED_PREFIX_OBSERVATION_MISMATCH"):
                study.primary_summary(rows, plan, root)
            self.assertEqual(broken.read_bytes(), data)

    def test_copy_host_wrapper_preserves_complete_file_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "host", root / "retained-host"
            (source / "engineering").mkdir(parents=True)
            (source / "engineering/engineering.json").write_bytes(b"{}\n")
            (source / "host-engineering.json").write_bytes(b'{"wrapper":true}\n')
            (source / "engineering.log").write_bytes(b"original host log\n")
            study.copy_tree(source, destination)
            self.assertEqual(study.reference.file_set(source), study.reference.file_set(destination))
            self.assertTrue((destination / "host-engineering.json").is_file())


if __name__ == "__main__":
    unittest.main()
