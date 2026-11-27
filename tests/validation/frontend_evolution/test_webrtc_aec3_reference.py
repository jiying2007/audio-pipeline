#!/usr/bin/env python3
"""Constructed transport/metadata/math fixtures only; never execute an AEC binary."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
import warnings
import zipfile

import webrtc_aec3_reference as reference


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tiny_metadata(mode="aec3"):
    # Constructed JSON, not a fake processor invocation or acoustic receipt.
    rows = [{"frame_index": i, "input_sample_frames_available": (i + 1) * 160,
             "output_sample_frames_emitted": (i + 1) * 160,
             "host_processing_begin_ns": i * 100 + 10,
             "host_processing_completed_ns": i * 100 + 30,
             "host_processing_duration_ns": 20,
             "algorithmic_latency_samples": 128 if mode == "aec3" else 224,
             "algorithmic_latency_ms": 8 if mode == "aec3" else 14,
             "reset_before_frame": False, "host_timing_only": True} for i in range(2)]
    value = {"schema_version": 1, "adapter": "webrtc-aec3-offline-v1", "status": "OK", "detail": "", "mode": mode,
             "sample_format": "S16LE", "sample_rate_hz": 16000, "frame_samples": 160,
             "mic_channels": 1, "render_channels": 1, "output_channels": 1, "channel_map": [0],
             "actual_processing_channels": 1, "actual_processing_sample_rate_hz": 16000,
             "input_frames": 2, "completed_frames": 2, "output_sample_frames": 320,
             "stream_delay_ms": 0, "adapter_lookahead_frames": 0, "padded_samples": 0, "tail_flush_samples": 0,
             "algorithmic_latency_samples": 128 if mode == "aec3" else 224,
             "algorithmic_latency_ms": 8 if mode == "aec3" else 14,
             "first_output_frame_input_samples_required": 160, "first_output_frame_host_completion_ns": 30,
             "reset_before_frame": None, "call_order": "ProcessReverseStream,set_stream_delay_ms(0),ProcessStream",
             "adapter_normalization": False, "host_timing_only": True,
             "physical_target_measurement": False, "acoustic_acceptance": False, "promotion_authority": False,
             "requested_config": reference.config_for(mode), "applied_config": reference.config_for(mode)}
    return value, rows


class ReferenceTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="aec3-reference-transport-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def zip_fixture(self, mutation=None):
        cases, rows = [], [("manifest.json", b'{"fixture":"not real audio evidence"}\n')]
        for index in range(6):
            case = {"case_id": "fixture-" + str(index), "samples": 2, "members": {}}
            for name in ("input.s16", "target.s16", "echo.s16", "ap.s16", "speex.s16"):
                raw = bytes(range(8 if name == "input.s16" else 4))
                case["members"][name] = {"bytes": len(raw), "sha256": digest(raw)}
                rows.append(("cases/" + case["case_id"] + "/" + name, raw))
            cases.append(case)
        rows += [("unused/source-%03d.txt" % i, b"metadata-only\n") for i in range(252 - len(rows))]
        if mutation:
            rows = mutation(rows)
        path = self.root / "fixture.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w") as archive:
                for name, raw in rows:
                    archive.writestr(name, raw)
        plan = {"cases": cases, "predecessor": {"archive_bytes": path.stat().st_size,
                "archive_sha256": reference.sha_file(path), "manifest_sha256": digest(rows[0][1])}}
        return path, plan

    def test_frozen_plan_and_python38_syntax(self):
        plan = reference.frozen_plan()
        self.assertEqual(plan["budget"]["new_full_case_executions"], 12)
        self.assertEqual(plan["arms"]["webrtc_aec3"]["declared_delay_samples"], 128)
        self.assertEqual(plan["arms"]["webrtc_apm"]["declared_delay_samples"], 224)
        self.assertFalse(plan["promotion_allowed"])
        for path in (Path(reference.__file__), Path(__file__)):
            ast.parse(path.read_text(), filename=str(path), feature_version=(3, 8))

    def test_exact_sample_split_preserves_sign_bytes_and_roles(self):
        raw = bytes.fromhex("0080ff7fffff000001000080")
        mic, render = reference.split_mic_render(raw, 3)
        self.assertEqual(mic, bytes.fromhex("0080ffff0100"))
        self.assertEqual(render, bytes.fromhex("ff7f00000080"))
        for wrong in (raw[:-1], raw + b"\0", raw + b"\0\0\0\0"):
            with self.assertRaisesRegex(ValueError, "cardinality"):
                reference.split_mic_render(wrong, 3)

    def test_fixed_zip_data_transport_and_rehash(self):
        path, plan = self.zip_fixture()
        result = reference.archive_members(path, plan)
        self.assertEqual(len(result), 30)
        self.assertEqual(result["cases/fixture-0/input.s16"], bytes(range(8)))
        plan["cases"][0]["members"]["target.s16"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "selected SHA256"):
            reference.archive_members(path, plan)

    def test_corrupted_original_archive_rejected(self):
        path, plan = self.zip_fixture()
        raw = bytearray(path.read_bytes())
        raw[100] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "ZIP identity"):
            reference.archive_members(path, plan)

    def test_zip_traversal_duplicate_link_and_missing_case_rejected(self):
        def link(rows):
            info = zipfile.ZipInfo("unused/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            return rows[:-1] + [(info, b"../../outside")]
        changes = (
            lambda rows: rows[:-1] + [("../outside", b"x")],
            lambda rows: rows[:-1] + [rows[0]],
            link,
            lambda rows: rows[:1] + [("unused/replaced-input", rows[1][1])] + rows[2:],
        )
        for change in changes:
            with self.subTest(change=change):
                path, plan = self.zip_fixture(change)
                with self.assertRaises(ValueError):
                    reference.archive_members(path, plan)

    def test_file_manifest_refuses_symlinks_hardlinks_and_empty_directories(self):
        directory = self.root / "evidence"
        directory.mkdir()
        path = directory / "real"
        path.write_bytes(b"frozen")
        self.assertEqual(reference.file_set(directory), {"real": digest(b"frozen")})
        link = directory / "link"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            reference.file_set(directory)
        link.unlink()
        os.link(path, link)
        with self.assertRaises(ValueError):
            reference.file_set(directory)
        link.unlink()
        (directory / "unexpected-empty").mkdir()
        with self.assertRaisesRegex(ValueError, "empty"):
            reference.file_set(directory)

    def test_metadata_mode_latency_geometry_and_frame_failures(self):
        for mode in reference.MODES:
            meta, rows = tiny_metadata(mode)
            reference.verify_metadata(meta, rows, mode, 320)
            for key, value in (("algorithmic_latency_samples", 0), ("reset_before_frame", 0),
                               ("actual_processing_channels", 2), ("mic_channels", True),
                               ("padded_samples", 160), ("promotion_authority", True),
                               ("completed_frames", 1), ("first_output_frame_host_completion_ns", 29)):
                bad = copy.deepcopy(meta)
                bad[key] = value
                with self.subTest(mode=mode, key=key), self.assertRaises(ValueError):
                    reference.verify_metadata(bad, rows, mode, 320)
            bad = copy.deepcopy(meta)
            bad["requested_config"]["echo_canceller"]["enabled"] = False
            bad["applied_config"] = copy.deepcopy(bad["requested_config"])
            with self.assertRaises(ValueError):
                reference.verify_metadata(bad, rows, mode, 320)
            for broken in (rows[:1], [rows[0], rows[0]], list(reversed(rows))):
                with self.assertRaises(ValueError):
                    reference.verify_metadata(meta, broken, mode, 320)

    def test_trace_duplicate_keys_and_unbounded_lines_rejected(self):
        path = self.root / "frames.jsonl"
        path.write_text('{"frame_index":0,"frame_index":1}\n')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            reference.trace_rows(path, 1)
        path.write_text('"' + 'x' * 2048 + '"\n')
        with self.assertRaises(ValueError):
            reference.trace_rows(path, 1)

    def test_fixed_alignment_uses_canonical_offsets_and_excludes_tail(self):
        target = [math.sin(i * 0.7) for i in range(24)]
        echo = [0.5] * 24
        actual = [0.0, 0.0] + target[:-2]
        plan = {"rate_hz": 10, "metrics": {"near_phase_seconds": {"tiny": [0.1, 0.5]},
                                           "final_far_seconds": [0.6, 1.0]}}
        result = reference.aligned_metrics(target, echo, actual, 2, plan)
        oracle = reference.speech.si_sdr_span(target, actual, 1, 3, 4)
        self.assertEqual(result["phases_si_sdr_relative_to_quantized_bf_target_db"]["tiny"], oracle)
        self.assertEqual(result["near_windows"]["tiny"], {"target_start": 1, "output_start": 3, "samples": 4})
        self.assertEqual(result["final_far_window"], {"echo_start": 6, "output_start": 8, "samples": 4})
        self.assertEqual(result["unobserved_tail"], "EXCLUDED_NOT_ZERO_FILLED")
        for delay in (-1, 22):
            with self.assertRaises(ValueError):
                reference.aligned_metrics(target, echo, actual, delay, plan)
        with self.assertRaises(ValueError):
            reference.aligned_metrics(target, echo, actual[:-1], 2, plan)

    def test_zero_residual_retains_canonical_mean_square_floor(self):
        # Twenty constructed samples, not a real-data or AEC execution. The
        # independent oracle sums two 100-ms windows of mean-square energy.
        plan = {"rate_hz": 100, "metrics": {"near_phase_seconds": {"tiny": [0.0, 0.1]},
                                            "final_far_seconds": [0.0, 0.2]}}
        result = reference.aligned_metrics([0.0] * 20, [0.5] * 20, [0.0] * 20, 0, plan)
        self.assertEqual(result["far_energy_window_samples"], 10)
        self.assertEqual(result["final_far_ratio_db"], 10 * math.log10((0.25 + 0.25) / 1e-30))

    def test_runtime_relocation_and_new_host_are_distinct(self):
        identity = {"system": "Linux", "machine": "x86_64", "release": "fixture-kernel",
                    "os_release_sha256": "1" * 64,
                    "libraries": {"/old/bin/lib/libwebrtc.so": "2" * 64, "/lib/libc.so": "3" * 64},
                    "library_names": {"libwebrtc.so": "/old/bin/lib/libwebrtc.so", "libc.so": "/lib/libc.so"}}
        moved = copy.deepcopy(identity)
        moved["libraries"]["/new/bin/lib/libwebrtc.so"] = moved["libraries"].pop("/old/bin/lib/libwebrtc.so")
        moved["library_names"]["libwebrtc.so"] = "/new/bin/lib/libwebrtc.so"
        self.assertEqual(reference.normalized_runtime(identity), reference.normalized_runtime(moved))
        moved["libraries"]["/lib/libc.so"] = "4" * 64
        self.assertNotEqual(reference.normalized_runtime(identity), reference.normalized_runtime(moved))

    def test_runtime_research_binding_rejects_library_substitution(self):
        library = "libwebrtc-audio-processing-2.so.1"
        identity = {"system": "Linux", "machine": "x86_64", "release": "fixture-kernel",
                    "os_release_sha256": "1" * 64,
                    "libraries": {"/fixture/bin/lib/" + library: "2" * 64, "/lib/libc.so": "3" * 64},
                    "library_names": {library: "/fixture/bin/lib/" + library, "libc.so": "/lib/libc.so"}}
        adapter = {"runtime_libraries": {"bin/lib/" + library: "2" * 64}}
        reference.research_runtime_binding(identity, adapter, Path("/fixture"))
        bad = copy.deepcopy(identity)
        bad["libraries"]["/fixture/bin/lib/" + library] = "9" * 64
        with self.assertRaisesRegex(ValueError, "research libraries differ"):
            reference.research_runtime_binding(bad, adapter)
        with self.assertRaisesRegex(ValueError, "outside portable"):
            reference.research_runtime_binding(identity, adapter, Path("/wrong"))

    def test_missing_case_role_lag_score_promotion_and_source_hash_semantics(self):
        plan = reference.frozen_plan()
        cases = [{"case_id": row["case_id"], "data_role": reference.ROLE,
                  "metrics": {"tiny_constructed_score": 0.5, "declared_delay": 128}} for row in plan["cases"]]
        calls = [{"case_id": row["case_id"], "mode": mode} for row in plan["cases"] for mode in reference.MODES]
        expected = reference.result_body(plan, {"code_revision": "1" * 40, "files": {"fixture": "2" * 64}},
            {"code_revision": "3" * 40}, "fixture-only-engineering", {}, cases, calls, 1.0, "/fixture-only")
        reference.check_result(copy.deepcopy(expected), expected, plan)
        mutations = [
            lambda r: r["cases"].pop(),
            lambda r: r["cases"][0].update(data_role="BLIND_HOLDOUT"),
            lambda r: r["cases"][0]["metrics"].update(declared_delay=127),
            lambda r: r["cases"][0]["metrics"].update(tiny_constructed_score=999),
            lambda r: r.update(promotion_allowed=True),
            lambda r: r.update(acoustic_acceptance=0),
            lambda r: r["comparison_sources"]["files"].update(fixture="9" * 64),
            lambda r: r["calls"].pop(),
            lambda r: r["calls"][0].update(mode="searched-configuration"),
        ]
        for change in mutations:
            bad = copy.deepcopy(expected)
            change(bad)
            with self.subTest(change=change), self.assertRaises(ValueError):
                reference.check_result(bad, expected, plan)

    def test_resealed_failed_directory_cannot_become_success(self):
        output = self.root / "failed"
        output.mkdir()
        reference.write_json(output / "failure.json", {
            "status": "FAILED_OR_PARTIAL_NO_ACOUSTIC_ACCEPTANCE",
            "error": "constructed post-seal wall-budget failure; no binary executed"})
        reference.write_json(output / "manifest.json", {
            "schema_version": 1, "files": reference.file_set(output)})
        self.assertEqual(reference.read_json(output / "manifest.json")["files"],
                         reference.file_set(output, ("manifest.json",)))
        with self.assertRaisesRegex(ValueError, "failed or partial"):
            reference.verify(output)

    def test_actual_disposable_git_source_binding_rejects_forged_hashes(self):
        repository, output = self.root / "repository", self.root / "output"
        repository.mkdir()
        files = {}
        for name in reference.METRIC_SOURCES:
            raw = ("metadata fixture only: " + name + "\n").encode()
            for path in (repository / name, output / "measurement-source" / name):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            files[name] = digest(raw)
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=repository, stderr=subprocess.PIPE, timeout=10)
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Metadata fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "tiny source fixture")
        binding = {"code_revision": git("rev-parse", "HEAD").decode().strip(), "files": files}
        reference.verify_measurement_sources(output, binding, repository)
        name = reference.METRIC_SOURCES[0]
        (output / "measurement-source" / name).write_bytes(b"changed source\n")
        forged = copy.deepcopy(binding)
        forged["files"][name] = digest(b"changed source\n")
        with self.assertRaisesRegex(ValueError, "implementation identity"):
            reference.verify_measurement_sources(output, forged, repository)


if __name__ == "__main__":
    unittest.main()
