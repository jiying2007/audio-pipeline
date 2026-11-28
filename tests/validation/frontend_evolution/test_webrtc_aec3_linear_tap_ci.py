#!/usr/bin/env python3
"""F07 routing/byte/budget tests: no reference compilation or SDK execution."""
import ast
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest import mock

import webrtc_aec3_linear_tap_ci as ci


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = (ci.ROOT / ci.WORKFLOW).read_text()
        cls.frozen = ci.git_bytes(ci.BASE, ci.WORKFLOW)

    def selected(self, changes):
        return ci.select("pull_request", "", changes, self.current)

    def flags(self, result, active):
        self.assertEqual(result["f07_linear"], str(active).lower())
        self.assertEqual(result["webrtc"], "false")
        self.assertEqual(result["ap"], "false")
        self.assertTrue(all(result[key] == "false" for key in ci.previous.HISTORICAL_FLAGS))

    def test_entire_predecessor_and_all_old_jobs_are_real_a70_bytes(self):
        ci.validate_workflow(self.current)
        self.assertEqual(ci.strip_workflow(self.current).encode(), self.frozen)
        self.assertEqual(ci.sha256(self.frozen), ci.BASE_WORKFLOW_SHA256)
        self.assertEqual(self.current.split("\n  matrix:\n", 1)[1].split(ci.JOB_MARKER, 1)[0],
                         self.frozen.decode().split("\n  matrix:\n", 1)[1])
        for path in (ci.REL + "webrtc_aec3_ci.py", ci.REL + "webrtc_aec3_source.py",
                     ci.REL + "test_webrtc_aec3_adapter.py", ci.REL + "webrtc_aec3_reference.py",
                     ".github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json",
                     ".github/research/frontend-evolution-v1/webrtc-aec3-admission.json",
                     ".github/research/frontend-evolution-v1/webrtc-aec3-reference-v1.json",
                     ".github/workflows/verify.yml"):
            self.assertEqual((ci.ROOT / path).read_bytes(), ci.git_bytes(ci.BASE, path), path)

    def test_ap_adapter_and_one_historical_fixture_are_exact_views(self):
        before = ci.git_bytes(ci.BASE, ci.AP_MODULE)
        after = (ci.ROOT / ci.AP_MODULE).read_bytes()
        ci.validate_ap_adapter(before, after)
        suffix = b"def execution_environment() -> dict:\n"
        self.assertEqual(before.split(suffix, 1)[1], after.split(suffix, 1)[1])
        ci.validate_ap_test_view(ci.git_bytes(ci.BASE, ci.AP_TEST), (ci.ROOT / ci.AP_TEST).read_bytes())
        for changed in (after + b"\n# unrelated\n", after.replace(b"AP_FROZEN_PUBLIC_PREDECESSOR_IDENTITY_CHANGED", b"loose")):
            with self.subTest(), self.assertRaises(ValueError):
                ci.validate_ap_adapter(before, changed)

    def test_actual_all_changed_f07_paths_route_one_build_only(self):
        command = ["git", "-C", str(ci.ROOT), "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(ci.ROOT.resolve())]
        names = set(subprocess.check_output(command + ["diff", "--name-only", ci.BASE], timeout=30).decode().splitlines())
        names.update(subprocess.check_output(command + ["ls-files", "--others", "--exclude-standard"], timeout=30).decode().splitlines())
        self.assertTrue(set(ci.CORE_PATHS).issubset(names))
        changes = {}
        for path in sorted(names):
            result = subprocess.run(command + ["show", ci.BASE + ":" + path], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=15)
            changes[path] = (result.stdout if result.returncode == 0 else None, (ci.ROOT / path).read_bytes())
        self.flags(self.selected(changes), True)

    def test_only_explicit_f07_dispatch_is_claimed_by_new_layer(self):
        self.flags(ci.select("workflow_dispatch", ci.EXPERIMENT, {}, self.current), True)
        for choice in ("ap-current-portable", "webrtc-aec3-engineering", "dualmic-broadside-output-d8"):
            self.assertIsNone(ci.select("workflow_dispatch", choice, {}, self.current))
        self.assertIsNone(self.selected({"docs/README.md": (b"before", b"after")}))

    def test_actual_scope_manual_entry_preserves_legacy_routes(self):
        body = self.current.split("          python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
        script = "\n".join(line[10:] if line.startswith("          ") else line for line in body.splitlines())
        for selected in (ci.EXPERIMENT, "ap-current-portable", "webrtc-aec3-engineering", "dualmic-broadside-output-d8"):
            with self.subTest(choice=selected), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "outputs"
                env = dict(os.environ, EVENT_NAME="workflow_dispatch", SELECTED_EXPERIMENT=selected,
                           BASE_SHA=ci.BASE, GITHUB_OUTPUT=str(output), PYTHONDONTWRITEBYTECODE="1")
                result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ci.ROOT, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                flags = dict(line.split("=", 1) for line in output.read_text().splitlines())
                if selected == ci.EXPERIMENT:
                    self.flags(flags, True)
                else:
                    self.assertEqual(flags["f07_linear"], "false")
                    self.assertEqual(flags["ap"], str(selected == "ap-current-portable").lower())
                    self.assertEqual(flags["webrtc"], str(selected == "webrtc-aec3-engineering").lower())
                    for key in ci.previous.HISTORICAL_FLAGS:
                        self.assertEqual(flags[key], str(key == "d8_archive" and selected == "dualmic-broadside-output-d8").lower())

    def test_missing_duplicate_moved_or_changed_f07_wiring_refuses(self):
        for changed in (self.current.replace(ci.OUTPUT_LINE, "", 1),
                        self.current.replace(ci.SCOPE_BLOCK, ci.SCOPE_BLOCK * 2, 1),
                        self.current.replace(ci.TINY_STEP, "", 1),
                        self.current.replace("timeout-minutes: 22", "timeout-minutes: 99", 1),
                        self.current.replace("1260s", "9999s", 1),
                        self.current.replace(ci.JOB_MARKER, "\n  renamed-f07:\n", 1),
                        self.current + "\n  unregistered:\n",
                        self.current.replace(ci.TINY_STEP, "", 1) + ci.TINY_STEP):
            with self.subTest(), self.assertRaises(ValueError):
                ci.validate_workflow(changed)

    def test_old_job_source_scope_and_checkout_cannot_hide_in_new_layer(self):
        for before, after in (("  matrix:\n", "  matrix:\n    hidden: true\n"),
                              ("Fixed WebRTC AEC3 reference engineering", "silent-skip"),
                              ("if: needs.scope.outputs.webrtc == 'true'", "if: false"),
                              ("1050", "9999"),
                              ("ref: ${{ github.event.pull_request.head.sha || github.sha }}", "ref: main")):
            if before not in self.current:
                continue
            with self.subTest(before=before), self.assertRaises(ValueError):
                ci.validate_workflow(self.current.replace(before, after, 1))
        changes = {ci.HARNESS: (None, b"method-only metadata fixture\n")}
        for path in ("src/ap_pipeline.c", ci.REL + "dualmic_target_gate_d5.py",
                     ".github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json",
                     ".github/workflows/quality.yml", "docs/research/frontend-evolution-v1/WEBRTC_AEC3_RESULT_20261128.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected(dict(changes, **{path: (b"old", b"new")}))

    def test_three_first_addition_results_are_support_never_science(self):
        changes = {path: (None, b"pure result-path fixture; no measurement claim\n") for path in ci.RESULT_PATHS}
        self.flags(self.selected(changes), False)
        for path in ci.RESULT_PATHS:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected({path: (b"already-published", b"rewritten")})
        with self.assertRaises(ValueError):
            self.selected({ci.RESULT_DIRECTORY + "/unknown.json": (None, b"unregistered")})
        with self.assertRaises(ValueError):
            self.selected({ci.RESULT_PATHS[0]: (b"already-published", None)})

    def test_navigation_restores_entire_a70_body_and_is_support_only(self):
        before = ci.git_bytes(ci.BASE, ci.NAVIGATION)
        after = (ci.ROOT / ci.NAVIGATION).read_bytes()
        self.assertEqual(after, before + ci.NAVIGATION_APPEND.encode())
        self.assertEqual(ci.strip_navigation(after), before)
        self.flags(self.selected({ci.NAVIGATION: (before, after)}), False)
        self.assertEqual(ci.strip_navigation(before), before)

    def test_navigation_duplicate_position_old_f05_and_other_body_mutations_refuse(self):
        before = ci.git_bytes(ci.BASE, ci.NAVIGATION)
        appendix = ci.NAVIGATION_APPEND.encode()
        after = before + appendix
        for changed in (after + appendix, appendix + before, after + b"\nnot-terminal\n",
                        after.replace(b"F05_DUALMIC_VALIDATION_20261128", b"F05_CHANGED", 1),
                        after.replace(b"# Frontend Evolution", b"# Edited Frontend Evolution", 1),
                        after.replace(b"64/128", b"63/127", 1)):
            with self.subTest(), self.assertRaises(ValueError):
                self.selected({ci.NAVIGATION: (before, changed)})
        changed_before = before.replace(b"# Frontend Evolution", b"# Jointly edited Frontend Evolution", 1)
        with self.assertRaises(ValueError):
            self.selected({ci.NAVIGATION: (changed_before, changed_before + appendix)})

    def test_retained_source_only_appends_exact_non_gc_record(self):
        before = ci.git_bytes(ci.BASE, ci.REGISTRY)
        after = (ci.ROOT / ci.REGISTRY).read_bytes()
        ci.registry_transition(before, after)
        self.flags(self.selected({ci.REGISTRY: (before, after)}), False)
        rows = json.loads(after)
        self.assertEqual(rows["records"][-1], ci.RETAINED_SOURCE)
        for mode in ("old-record", "gc", "head", "policy"):
            changed = json.loads(after)
            if mode == "old-record":
                changed["records"][0]["status"] = "changed"
            elif mode == "gc":
                changed["records"][-1]["auto_gc"] = True
            elif mode == "head":
                changed["records"][-1]["head_sha"] = "0" * 40
            else:
                changed["policy"] = {}
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                ci.registry_transition(before, json.dumps(changed).encode())
        with self.assertRaises(ValueError):
            ci.registry_transition(after, before)

    def test_precise_read_only_git_works_with_different_owner_assumption(self):
        with mock.patch.dict(os.environ, {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}):
            self.assertEqual(ci.git_bytes(ci.BASE, ci.WORKFLOW), self.frozen)

    def test_job_has_one_builder_head_binding_bounded_stages_and_no_work_tree_upload(self):
        job = ci.job_text()
        self.assertIn("--expected-head \"$EXECUTION_SHA\"", job)
        self.assertEqual(job.count("ref: ${{ github.event.pull_request.head.sha || github.sha }}"), 1)
        self.assertIn("timeout-minutes: 22", job)
        self.assertIn("1260s", job)
        self.assertIn("if: always()", job)
        self.assertNotIn("reference-build/work", job)
        self.assertNotIn("/reference-build/\n", job)
        self.assertIn("reference-build/failed-build-evidence/", job)
        self.assertNotIn("webrtc_aec3_linear_tap.py run", job)
        self.assertNotIn("ap_current_ci.py run", job)
        self.assertEqual(ci.CI_SECONDS, 1200)
        plan = json.loads((ci.ROOT / ci.PLAN).read_text())
        self.assertEqual(plan["budget"]["ci_outer_wall_seconds"], ci.CI_SECONDS)
        self.assertEqual(plan["engineering"]["combined_subprocess_invocations"], 87)
        self.assertEqual(plan["engineering"]["combined_requested_capture_audio_seconds"], 15.3699375)


class ReadbackAndFailureTests(unittest.TestCase):
    def test_raw_linear_f32_units_are_not_s16_quantized_and_bad_bytes_refuse(self):
        fixture = ci.fixture_module()
        values = [-1.0, -0.125, 0.0, 0.125, 1.0]
        self.assertEqual(fixture.linear_samples(struct.pack("<5f", *values)), values)
        for raw in (b"partial", struct.pack("<f", float("nan")), struct.pack("<f", float("inf")),
                    struct.pack("<f", 1.01), struct.pack("<f", -1.01)):
            with self.subTest(), self.assertRaises(RuntimeError):
                fixture.linear_samples(raw)

    def test_frozen_cli_omits_observation_flags_for_original_default(self):
        fixture = ci.fixture_module()
        binary, folder = Path("/metadata-only/webrtc-aec3-runner"), Path("/metadata-only/fixture")
        _, original = fixture.invocation(binary, folder, "default-off")
        self.assertNotIn("--aec3-export-mode", original)
        self.assertNotIn("--linear-output", original)
        _, off = fixture.invocation(binary, folder, "factory-off")
        self.assertIn("factory-off", off)
        self.assertNotIn("--linear-output", off)
        paths, on = fixture.invocation(binary, folder, "factory-on")
        self.assertIn("factory-on", on)
        self.assertEqual(on[on.index("--linear-output") + 1], str(paths["--linear-output"]))
        self.assertNotIn("--reset-before-frame", on)

    def test_fixture_time_types_and_failed_readback_never_launch_runtime(self):
        fixture = ci.fixture_module()
        fixture.finite_time(120, 120, "synthetic boundary")
        for value in (0, -1, 120.01, True, "1", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                fixture.finite_time(value, 120, "synthetic negative")
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "engineering.json"
            receipt.write_text(json.dumps({"schema_version": 1, "fixture_id": fixture.FIXTURE_ID,
                                          "status": "FAIL", "failures": ["synthetic rejected-prefix fixture"]}))
            with mock.patch.object(fixture.subprocess, "Popen", side_effect=AssertionError("SDK forbidden")), \
                    mock.patch.object(ci.previous, "runtime_identity", side_effect=AssertionError("ldd forbidden")):
                with self.assertRaises(RuntimeError):
                    fixture.verify_engineering(receipt, "1" * 64, "2" * 64, ci.BASE)

    def test_non_actions_refuses_before_any_build_or_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-run"
            with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), mock.patch.object(ci.previous, "command") as process:
                with self.assertRaises(ValueError):
                    ci.run(ci.BASE, output)
                process.assert_not_called()
            receipt = json.loads((output / "ci-receipt.json").read_text())
            self.assertEqual(receipt["status"], "FAIL")
            self.assertEqual(receipt["stages"], [])
            self.assertEqual(receipt["science_calls"], 0)

    def test_wrong_execution_head_stops_before_control_import_or_build(self):
        with mock.patch.object(ci.subprocess, "check_output", return_value=(ci.BASE + "\n").encode()), \
                mock.patch.object(ci, "git_bytes") as read:
            with self.assertRaises(ValueError):
                ci.committed_controls("1" * 40)
            read.assert_not_called()

    def test_expired_command_budget_launches_nothing(self):
        with mock.patch.object(ci.previous.source, "run_logged") as process:
            with self.assertRaises(ValueError):
                ci.previous.command(["must-not-run"], Path("unused"), {}, 0, 120)
            process.assert_not_called()

    def test_failed_late_packaging_preserves_original_manifest_and_archive(self):
        # Filesystem/schema fixture only; these bytes are not an engineering result.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bundle").mkdir()
            old = {"status": "PASS_ENGINEERING_ONLY", "fixture_notice": "not actual engineering"}
            data = (json.dumps(old) + "\n").encode()
            (root / "bundle/bundle.json").write_bytes(data)
            payload = b"bounded transport fixture, not an actual tar or ELF\n"
            (root / "webrtc-aec3-linear-tap-bundle.tar.gz").write_bytes(payload)
            ci.invalidate_success(root)
            self.assertEqual((root / "bundle/manifest-before-failure.json").read_bytes(), data)
            self.assertEqual((root / "webrtc-aec3-linear-tap-failed-prefix.tar.gz").read_bytes(), payload)
            self.assertFalse((root / "webrtc-aec3-linear-tap-bundle.tar.gz").exists())
            self.assertEqual(json.loads((root / "bundle/bundle.json").read_text())["status"], "FAIL_F07_BUNDLE_NOT_COMMITTED")

    def test_wrong_or_failed_bundle_kind_cannot_reach_any_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kind, status in (("old-engineering-kind", "PASS_ENGINEERING_ONLY"),
                                 (ci.KIND, "FAIL_F07_BUNDLE_NOT_COMMITTED")):
                (root / "bundle.json").write_text(json.dumps({"schema_version": 1, "kind": kind, "status": status, "paths": ci.PATHS}))
                with self.subTest(), mock.patch.object(ci.reference, "verify_bundle") as old, \
                        mock.patch.object(ci.previous, "runtime_identity") as runtime:
                    with self.assertRaises(ValueError):
                        ci.verify_bundle(root)
                    old.assert_not_called()
                    runtime.assert_not_called()

    def test_python38_syntax_for_new_ci_method_and_tests(self):
        for name in (ci.MODULE, ci.TEST):
            ast.parse((ci.ROOT / name).read_text(), filename=name, feature_version=(3, 8))


if __name__ == "__main__":
    unittest.main()
