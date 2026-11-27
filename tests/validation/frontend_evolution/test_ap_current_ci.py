#!/usr/bin/env python3
"""Offline AP scope/transport negative tests. No C compile or DSP is executed."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock

import ap_current_ci as ap


class SelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = ap.plan()
        cls.current = (ap.ROOT / ap.WORKFLOW).read_text()
        cls.reference = cls.config["workflow"]["reviewed_integration"]
        cls.transport = cls.config["workflow"]["reviewed_transport"]
        cls.c7_files = {name: ap.git_bytes(ap.REFERENCE, name) for name in cls.reference["files"]}
        cls.base_files = {name: ap.git_bytes(ap.MAIN_REFERENCE, name) for name in cls.reference["files"]}

    def added(self):
        changes = {}
        for name in self.config["workflow"]["trigger_core_paths"]:
            path = ap.ROOT / name
            # An absent sibling-owned F05 path is a selector-only synthetic
            # name fixture. It is never executed or a scientific receipt.
            changes[name] = (None, path.read_bytes() if path.exists() else b"selector-only path fixture\n")
        for name in (ap.WORKFLOW, ap.previous.VERIFY_WORKFLOW, ap.NAVIGATION,
                     "tests/validation/frontend_evolution/test_webrtc_aec3_ci.py"):
            changes[name] = (ap.git_bytes(ap.REFERENCE, name), (ap.ROOT / name).read_bytes())
        return changes

    def initial(self, include_transport=False):
        final = dict(self.c7_files)
        final.update({name: row[1] for name, row in self.added().items()})
        if include_transport:
            for name in self.transport["files"]:
                if name == ".github/scripts/verify-docs-gate.sh":
                    data = ap.git_bytes(self.transport["public_revision"], name)
                    anchor = b"python3 tests/validation/frontend_evolution/test_contracts.py\n"
                    final[name] = data.replace(anchor, anchor + ap.DOCS_LINES[0].encode())
                else:
                    final[name] = ap.git_bytes(self.transport["public_revision"], name)
        return {name: (ap.git_bytes(ap.MAIN_REFERENCE, name), data) for name, data in final.items()}

    def assert_flags(self, value, ap_flag, aec3_flag):
        self.assertEqual(value["ap"], str(ap_flag).lower())
        self.assertEqual(value["webrtc"], str(aec3_flag).lower())
        self.assertTrue(all(value[key] == "false" for key in ap.previous.HISTORICAL_FLAGS))

    def test_full_actual_workflow_restores_public_predecessor_bytes(self):
        restored = ap.predecessor_workflow(self.current)
        self.assertEqual(restored.encode(), ap.git_bytes(ap.PREDECESSOR, ap.WORKFLOW))
        self.assertEqual(ap.previous.old_workflow(restored).encode(), ap.git_bytes(ap.MAIN_REFERENCE, ap.WORKFLOW))
        self.assertEqual(ap.previous.historical_jobs(restored), ap.previous.historical_jobs(self.current))
        self.assertEqual((ap.ROOT / "tests/validation/frontend_evolution/webrtc_aec3_ci.py").read_bytes(),
                         ap.git_bytes(ap.REFERENCE, "tests/validation/frontend_evolution/webrtc_aec3_ci.py"))

    def test_actual_c7_mixed_introduction_selects_both_engineering_jobs(self):
        self.assertEqual(len(self.c7_files), 64)
        self.assert_flags(ap.select("pull_request", "", self.initial(), self.current), True, True)

    def test_actual_c7_plus_exact_38_transport_still_selects_both(self):
        self.assert_flags(ap.select("pull_request", "", self.initial(True), self.current), True, True)

    def test_actual_apt_followup_composes_from_main_without_generic_allowlist(self):
        changes = self.initial(True)
        followup = self.config["workflow"]["reviewed_transport_followup"]
        for name in followup["files"]:
            changes[name] = (ap.git_bytes(ap.MAIN_REFERENCE, name), ap.git_bytes(followup["public_revision"], name))
        self.assert_flags(ap.select("pull_request", "", changes, self.current), True, True)
        only_followup = {name: (ap.git_bytes(followup["public_parent"], name), ap.git_bytes(followup["public_revision"], name))
                         for name in followup["files"]}
        self.assert_flags(ap.select("pull_request", "", only_followup, self.current), False, False)
        name = ".github/workflows/quality.yml"
        only_followup[name] = tuple(reversed(only_followup[name]))
        with self.assertRaisesRegex(ValueError, "ROLLBACK"):
            ap.select("pull_request", "", only_followup, self.current)

    def test_final_public_transport_and_custody_full_main_diff_selects_both(self):
        changes = self.initial(True)
        for key in ("reviewed_transport_followup", "reviewed_ref_retention"):
            registry = self.config["workflow"][key]
            for name in registry["files"]:
                changes[name] = (ap.git_bytes(ap.MAIN_REFERENCE, name), ap.git_bytes(registry["public_revision"], name))
        self.assert_flags(ap.select("pull_request", "", changes, self.current), True, True)

    def test_custody_is_support_only_and_arbitrary_or_reverse_registry_change_refuses(self):
        registry = self.config["workflow"]["reviewed_ref_retention"]
        changes = {name: (ap.git_bytes(registry["public_parent"], name), ap.git_bytes(registry["public_revision"], name))
                   for name in registry["files"]}
        self.assert_flags(ap.select("pull_request", "", changes, self.current), False, False)
        path = ".github/research/evidence-index.json"
        for before, after in (tuple(reversed(changes[path])), (changes[path][0], changes[path][1] + b"\nunknown\n")):
            invalid = dict(changes)
            invalid[path] = (before, after)
            with self.assertRaisesRegex(ValueError, "ROLLBACK"):
                ap.select("pull_request", "", invalid, self.current)

    def test_after_transport_merge_actual_base_is_used(self):
        final = {name: value[1] for name, value in self.initial(True).items()}
        before = {name: ap.git_bytes(self.transport["public_revision"], name) for name in final}
        changes = {name: (before[name], value) for name, value in final.items() if before[name] != value}
        self.assertNotIn(".github/workflows/quality.yml", changes)
        self.assert_flags(ap.select("pull_request", "", changes, self.current), True, True)

    def test_ap_only_after_aec3_unchanged_does_not_repeat_aec3(self):
        self.assert_flags(ap.select("pull_request", "", self.added(), self.current), True, False)

    def test_registered_metadata_alone_never_runs_engineering(self):
        name = "docs/research/frontend-evolution-v1/DECHORATE_RIR_GAP_20261128/result.json"
        self.assert_flags(ap.select("pull_request", "", {name: (None, self.c7_files[name])}, self.current), False, False)

    def test_exact_transport_alone_never_runs_engineering(self):
        changes = {name: (ap.git_bytes(ap.MAIN_REFERENCE, name), ap.git_bytes(self.transport["public_revision"], name))
                   for name in self.transport["files"]}
        self.assert_flags(ap.select("pull_request", "", changes, self.current), False, False)

    def test_later_quality_rollback_to_known_c7_bytes_is_refused(self):
        name = ".github/workflows/quality.yml"
        changes = self.added()
        changes[name] = (ap.git_bytes(self.transport["public_revision"], name), ap.git_bytes(ap.REFERENCE, name))
        with self.assertRaisesRegex(ValueError, "ROLLBACK"):
            ap.select("pull_request", "", changes, self.current)

    def test_unknown_old_science_dsp_and_workflow_changes_refuse(self):
        for name in ("src/core/ap_pipeline.c", ".github/workflows/unregistered.yml",
                     "tests/validation/frontend_evolution/dualmic_target_gate_d5.py",
                     "docs/research/frontend-evolution-v1/DUALMIC_GAIN_RAMP_D6_RESULT.zh-CN.md"):
            changes = self.added()
            changes[name] = (b"before", b"after")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "UNREGISTERED"):
                ap.select("pull_request", "", changes, self.current)

    def test_mutated_known_result_source_catalog_or_old_observer_refuses(self):
        for name in (".github/research/frontend-evolution-v1/sources.json",
                     "tests/validation/frontend_evolution/webrtc_aec3_ci.py",
                     "docs/research/frontend-evolution-v1/DECHORATE_RIR_GAP_20261128/result.json"):
            changes = self.initial()
            changes[name] = (changes[name][0], changes[name][1] + b"\nchanged\n")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "UNREGISTERED"):
                ap.select("pull_request", "", changes, self.current)

    def test_hidden_workflow_edits_cannot_be_stripped_away(self):
        for before, after in (("  matrix:\n", "  matrix:\n    hidden: true\n"),
                              ("Fixed WebRTC AEC3 reference engineering", "Changed AEC3 job"),
                              ("timeout-minutes: 12", "timeout-minutes: 99"),
                              ("from ap_current_ci import select_workflow", "from changed import select_workflow"),
                              ("      ap: ${{ steps.select.outputs.ap }}", "      ap: 'false'")):
            changed = self.current.replace(before, after, 1)
            with self.subTest(before=before), self.assertRaises(ValueError):
                ap.select("workflow_dispatch", "ap-current-portable", {}, changed)

    def test_old_jobs_and_plan_hash_cannot_be_changed_together(self):
        original = ap.git_bytes(ap.PREDECESSOR, ap.WORKFLOW).decode()
        changed = original.replace("  matrix:\n", "  matrix:\n    hidden: true\n", 1)
        configuration = json.loads(json.dumps(self.config))
        configuration["workflow"]["predecessor_workflow_sha256"] = ap.sha256(changed.encode())
        with mock.patch.object(ap, "plan", return_value=configuration):
            with self.assertRaisesRegex(ValueError, "FROZEN_PUBLIC_PREDECESSOR"):
                ap.predecessor_workflow(changed)

    def test_missing_duplicate_trigger_or_job_refuses(self):
        line = "      - '" + self.config["workflow"]["trigger_core_paths"][0] + "'\n"
        for changed in (self.current.replace(line, "", 1), self.current.replace(line, line + line, 1),
                        self.current + ap.JOB_MARKER):
            with self.subTest(), self.assertRaises(ValueError):
                ap.predecessor_workflow(changed)

    def test_other_verify_or_navigation_change_cannot_hide_in_extensions(self):
        for name in (ap.previous.VERIFY_WORKFLOW, ap.NAVIGATION, ".github/scripts/verify-docs-gate.sh"):
            changes = self.initial()
            before, after = changes[name]
            changes[name] = (before, after + b"unregistered change\n")
            with self.subTest(name=name), self.assertRaises(ValueError):
                ap.select("pull_request", "", changes, self.current)

    def test_metadata_does_not_replace_actual_workflow(self):
        changes = self.initial()
        changes[ap.WORKFLOW] = (changes[ap.WORKFLOW][0], ap.git_bytes(ap.REFERENCE, ap.WORKFLOW))
        with self.assertRaisesRegex(ValueError, "ACTUAL_WORKFLOW"):
            ap.select("pull_request", "", changes, self.current)

    def test_actual_scope_manual_ap_and_aec3_and_closed_d8(self):
        body = self.current.split("          python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
        script = "\n".join(line[10:] if line.startswith("          ") else line for line in body.splitlines())
        for choice in ("ap-current-portable", "webrtc-aec3-engineering", "dualmic-broadside-output-d8"):
            with self.subTest(choice=choice), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "outputs"
                env = dict(os.environ, EVENT_NAME="workflow_dispatch", SELECTED_EXPERIMENT=choice,
                           GITHUB_OUTPUT=str(output), BASE_SHA=ap.MAIN_REFERENCE, PYTHONDONTWRITEBYTECODE="1")
                result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ap.ROOT, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                if choice == "dualmic-broadside-output-d8":
                    self.assertEqual(values["d8_archive"], "true")
                    self.assertTrue(all(values[name] == "false" for name in ap.previous.HISTORICAL_FLAGS if name != "d8_archive"))
                    self.assertEqual(values["webrtc"], "false")
                    self.assertEqual(values["ap"], "false")
                else:
                    self.assert_flags(values, choice == "ap-current-portable", choice == "webrtc-aec3-engineering")


class EngineeringDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def trace(self, count=2):
        result = []
        for index in range(count):
            row = {name: 0 for name in ap.TRACE_KEYS}
            row.update(frame=index, algorithmic_latency_ms=10, vad_probability=0.0, erle_db=0.0)
            result.append(row)
        path = self.root / "trace"
        path.write_text("".join(json.dumps(row) + "\n" for row in result))
        return path, result

    def test_fixed_fixture_audio_budget_and_zero_search(self):
        values = ap.fixture_specs()
        self.assertEqual(len(values), 42)
        self.assertEqual(sum(len(row["mic"]) / 4 / 16000 for row in values), 3.7404375)
        self.assertEqual(len({row["id"] for row in values}), 42)
        self.assertTrue(all(row["output_frames"] <= 20 for row in values))
        self.assertNotIn("argmax", (ap.ROOT / ap.MODULE).read_text())

    def test_trace_requires_all_fields_count_order_and_declared_latency(self):
        path, rows = self.trace()
        self.assertEqual(ap.trace_rows(path, 2), rows)
        for field, value in (("frame", 7), ("algorithmic_latency_ms", 8), ("vad_probability", float("nan")), ("frame", False)):
            changed = [dict(row) for row in rows]
            changed[0][field] = value
            path.write_text("".join(json.dumps(row) + "\n" for row in changed))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                ap.trace_rows(path, 2)
        path.write_text(json.dumps(rows[0]))
        with self.assertRaisesRegex(ValueError, "truncated"):
            ap.trace_rows(path, 1)
        path.write_text(json.dumps(rows[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            ap.trace_rows(path, 2)

    def test_missing_extra_trace_field_refused(self):
        path, rows = self.trace(1)
        for changed in ({key: value for key, value in rows[0].items() if key != "erle_valid"}, dict(rows[0], score=100)):
            path.write_text(json.dumps(changed) + "\n")
            with self.assertRaises(ValueError):
                ap.trace_rows(path, 1)

    def test_duplicate_trace_key_or_string_numeric_refused(self):
        path, rows = self.trace(1)
        text = json.dumps(rows[0])
        path.write_text(text[:-1] + ', "frame":0}\n')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ap.trace_rows(path, 1)
        rows[0]["erle_db"] = "not-numeric"
        path.write_text(json.dumps(rows[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "trace fields"):
            ap.trace_rows(path, 1)

    def test_render_length_and_alias_refused_before_invocation(self):
        mic, render = self.root / "mic", self.root / "render"
        mic.write_bytes(bytes(640))
        render.write_bytes(bytes(318))
        with mock.patch.object(ap.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "render must equal"):
                ap.validate_audio_paths(mic, render, self.root / "out", self.root / "trace")
            with self.assertRaises(ValueError):
                ap.validate_audio_paths(mic, None, self.root / "same", self.root / "same")
            with self.assertRaises(ValueError):
                ap.validate_audio_paths(mic, None, mic, self.root / "trace")
            run.assert_not_called()
        render.write_bytes(bytes(320))
        ap.validate_audio_paths(mic, render, self.root / "out", self.root / "trace")

    def test_manifest_extra_missing_changed_and_symlink_refused(self):
        path = self.root / "data"
        path.write_bytes(b"pure transport unit fixture\n")
        files = ap.file_map(self.root)
        ap.check_map(self.root, files)
        path.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            ap.check_map(self.root, files)
        path.unlink()
        with self.assertRaises(ValueError):
            ap.check_map(self.root, files)
        path.write_bytes(b"pure transport unit fixture\n")
        (self.root / "extra").write_bytes(b"extra")
        with self.assertRaises(ValueError):
            ap.check_map(self.root, files)
        (self.root / "extra").unlink()
        (self.root / "link").symlink_to(path)
        with self.assertRaises(ValueError):
            ap.file_map(self.root)

    def test_hardlinks_and_path_traversal_refused(self):
        (self.root / "one").write_bytes(b"x")
        os.link(str(self.root / "one"), str(self.root / "two"))
        with self.assertRaises(ValueError):
            ap.file_map(self.root)
        for name in ("../outside", "/absolute", "a/../b", "a//b", "a\\b"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                ap.relative_file(self.root, name)

    def test_archive_actual_tiny_transport_readback(self):
        folder = self.root / "bundle"
        folder.mkdir()
        (folder / "fixture.txt").write_bytes(b"no ELF, no DSP, no execution evidence\n")
        target = self.root / "tiny.tar.gz"
        digest = ap.archive_readback(folder, target)
        self.assertEqual(digest, ap.sha256(target.read_bytes()))
        with tarfile.open(target) as archive:
            self.assertEqual(archive.getnames(), ["fixture.txt"])
        with self.assertRaises(ValueError):
            ap.archive_readback(folder, target)

    def test_duplicate_json_keys_and_nonfinite_refused(self):
        path = self.root / "value.json"
        for text in ('{"same":1,"same":2}', '{"value":NaN}'):
            path.write_text(text)
            with self.assertRaises(ValueError):
                ap.read_json(path)

    def test_execution_environment_removes_loader_and_compiler_injection(self):
        with mock.patch.dict(os.environ, {"LD_PRELOAD": "untrusted", "LD_LIBRARY_PATH": "/tmp/lib", "CFLAGS": "injected"}):
            value = ap.execution_environment()
            for key in ("LD_PRELOAD", "LD_LIBRARY_PATH", "CFLAGS"):
                self.assertNotIn(key, value)
            self.assertEqual(value["LC_ALL"], "C")

    def test_expired_budget_never_launches_process(self):
        with mock.patch.object(ap.subprocess, "Popen") as run:
            with self.assertRaisesRegex(ValueError, "budget"):
                ap.invoke(["never-execute"], self.root, 0)
            run.assert_not_called()

    def test_wall_clock_gate_prevents_any_step_after_budget(self):
        entered = []
        with self.assertRaisesRegex(ValueError, "budget"):
            with ap.wall_guard(time.monotonic() - 1):
                entered.append("must not run")
        self.assertEqual(entered, [])
        with self.assertRaises(TimeoutError):
            with ap.wall_guard(time.monotonic() + 0.02):
                time.sleep(0.1)
                entered.append("must not continue after alarm")
        self.assertEqual(entered, [])

    def test_actual_tiny_process_logs_and_timeout_prefix_are_preserved(self):
        ok = self.root / "ok"
        ok.mkdir()
        record = ap.invoke([sys.executable, "-B", "-c", "print('non-DSP transport test')"], ok, time.monotonic() + 5)
        ap.validate_invocation(record, ok)
        self.assertEqual(record["returncode"], 0)
        timeout = self.root / "timeout"
        timeout.mkdir()
        with self.assertRaisesRegex(ValueError, "timeout"):
            ap.invoke([sys.executable, "-B", "-c", "import time; time.sleep(1)"], timeout, time.monotonic() + 5, 0.02)
        self.assertTrue((timeout / "invocation-start.json").is_file())
        self.assertTrue(ap.read_json(timeout / "invocation-result.json")["timed_out"])

    def test_late_failure_revokes_success_but_preserves_original_archive_bytes(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        ap.write_json(bundle / "bundle.json", {"status": "PASS_ENGINEERING_ONLY", "fixture_only": True})
        manifest = (bundle / "bundle.json").read_bytes()
        archive = self.root / "ap-current-portable-bundle.tar.gz"
        archive.write_bytes(b"pure failed transport unit fixture, not a research archive\n")
        original = archive.read_bytes()
        ap.invalidate_success(self.root)
        self.assertFalse(archive.exists())
        self.assertEqual((self.root / "ap-current-portable-failed-bundle.tar.gz").read_bytes(), original)
        self.assertEqual((bundle / "bundle-manifest-before-failure.json").read_bytes(), manifest)
        self.assertEqual(ap.read_json(bundle / "bundle.json")["status"], "FAIL_BUNDLE_NOT_COMMITTED")

    def test_reusing_existing_output_never_mutates_its_receipts(self):
        ap.write_json(self.root / "ci-receipt.json", {"status": "PASS_ENGINEERING_ONLY", "fixture_only": True})
        before = ap.file_map(self.root)
        with self.assertRaisesRegex(ValueError, "fresh CI output"):
            ap.run("0" * 40, self.root)
        self.assertEqual(ap.file_map(self.root), before)
        with mock.patch.object(ap, "verify_bundle", side_effect=ValueError("admission fixture refusal")):
            with self.assertRaisesRegex(ValueError, "admission fixture"):
                ap.engineering(self.root / "not-a-bundle", self.root)
        self.assertEqual(ap.file_map(self.root), before)

    def test_main_dsp_and_observer_pins_are_actual_git_bytes(self):
        pins = ap.plan()["source"]["main_reference_files_sha256"]
        self.assertEqual(len(pins), 59)
        for name, digest in pins.items():
            self.assertEqual(ap.sha256((ap.ROOT / name).read_bytes()), digest)
            self.assertEqual((ap.ROOT / name).read_bytes(), ap.git_bytes(ap.MAIN_REFERENCE, name))

    def test_configuration_has_no_revision_or_dsp_override(self):
        tools = {name: {"path": "/usr/bin/" + name} for name in ("gcc", "cmake", "make")}
        command = ap.configure_command(Path("/test/not-executed"), tools, Path("/frozen/source"))
        self.assertIn("-DAP_ENABLE_FAST_MATH=OFF", command)
        self.assertIn("-DAP_SIMD_BACKEND=SCALAR", command)
        self.assertFalse(any("AP_BUILD_SOURCE_REVISION=" in part for part in command))
        self.assertEqual(ap.compile_command(Path("/test/not-executed"), tools)[-2:], ["--parallel", "2"])
        self.assertEqual(command[command.index("-S") + 1], "/frozen/source")

    def test_actual_elf_architecture_and_search_path_semantics(self):
        text = "  Class: ELF64\n  Machine: Advanced Micro Devices X86-64\n (RUNPATH) Library runpath: [$ORIGIN/lib]\n"
        ap.validate_elf_observation(text)
        for changed in (text.replace("ELF64", "ELF32"), text.replace("Advanced Micro Devices X86-64", "AArch64"),
                        text.replace("$ORIGIN/lib", "/original/build")):
            with self.subTest(), self.assertRaises(ValueError):
                ap.validate_elf_observation(changed)

    def test_saved_failure_flag_refuses_even_with_resealed_outer_manifest(self):
        folder = self.root / "engineering"
        folder.mkdir()
        (folder / "failure.json").write_text('{"status":"FAIL"}\n')
        value = {"schema_version": 1, "status": "PASS_ENGINEERING_ONLY", "failures": [],
                 "files": ap.file_map(folder)}
        ap.write_json(folder / "engineering.json", value)
        with self.assertRaisesRegex(ValueError, "failed or incomplete"):
            ap.semantic_engineering(self.root, folder / "engineering.json", {})

    def test_engineering_wrong_source_rejected_before_any_runtime_query(self):
        folder = self.root / "engineering"
        folder.mkdir()
        (folder / "fixture-only.txt").write_text("synthetic schema negative; never execution evidence\n")
        value = {"schema_version": 1, "status": "PASS_ENGINEERING_ONLY", "failures": [],
                 "source_revision": "1" * 40, "files": ap.file_map(folder)}
        ap.write_json(folder / "engineering.json", value)
        with mock.patch.object(ap, "runtime_identity") as runtime:
            with self.assertRaisesRegex(ValueError, "source/binary binding"):
                ap.semantic_engineering(self.root, folder / "engineering.json", {"source_revision": "2" * 40})
            runtime.assert_not_called()

    def test_source_and_test_parse_as_python38(self):
        for name in (ap.MODULE, ap.TEST):
            ast.parse((ap.ROOT / name).read_text(), feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()
