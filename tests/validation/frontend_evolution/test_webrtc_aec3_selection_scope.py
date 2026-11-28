#!/usr/bin/env python3
"""Read-only scope and negative tests; no compilation, DSP or speech runs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import webrtc_aec3_selection_scope as scope


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = (scope.ROOT / scope.WORKFLOW).read_text()
        cls.frozen = scope.git_bytes(scope.BASE, scope.WORKFLOW)

    def selected(self, changes, event="pull_request"):
        return scope.select(event, "", changes, self.current)

    def flags(self, result, engineering):
        self.assertEqual(result["f07_selection"], str(engineering).lower())
        self.assertTrue(all(value == "false" for name, value in result.items()
                            if name != "f07_selection"))

    def test_exact_full_predecessor_workflow_is_real_base(self):
        scope.validate_workflow(self.current)
        self.assertEqual(scope.strip_workflow(self.current).encode(), self.frozen)
        self.assertEqual(scope.sha256(self.frozen), scope.BASE_WORKFLOW_SHA256)
        self.assertEqual(scope.strip_workflow(self.frozen.decode()).encode(), self.frozen)
        old_jobs = self.frozen.decode().split("\n  matrix:\n", 1)[1]
        new_jobs = self.current.split("\n  matrix:\n", 1)[1].split(scope.JOB_MARKER, 1)[0]
        self.assertEqual(new_jobs, old_jobs)

    def test_only_exact_dispatch_is_claimed(self):
        self.flags(scope.select("workflow_dispatch", scope.EXPERIMENT, {}, self.current), True)
        for choice in ("webrtc-aec3-linear-tap", "ap-current-portable", "webrtc-aec3-engineering",
                       "dualmic-broadside-output-d8", "unknown"):
            with self.subTest(choice=choice):
                self.assertIsNone(scope.select("workflow_dispatch", choice, {}, self.current))

    def test_each_declared_new_core_requires_engineering(self):
        for path in scope.CORE_PATHS:
            with self.subTest(path=path):
                self.flags(self.selected({path: (None, b"path-only scope fixture; no acoustic result\n")}), True)

    def test_unrelated_change_is_not_claimed(self):
        self.assertIsNone(self.selected({"docs/README.md": (b"before", b"after")}))
        self.assertIsNone(self.selected({}))

    def test_only_exact_initial_workflow_transition(self):
        self.flags(self.selected({scope.WORKFLOW: (self.frozen, self.current.encode())}), True)
        for before, after in ((b"unknown", self.current.encode()),
                              (self.current.encode(), self.frozen),
                              (None, self.current.encode()),
                              (self.frozen, self.current.encode() + b"\n")):
            with self.subTest(), self.assertRaises(ValueError):
                self.selected({scope.WORKFLOW: (before, after)})

    def test_missing_duplicate_moved_changed_job_or_wiring_refused(self):
        corruptions = [
            self.current.replace(scope.OUTPUT_LINE, "", 1),
            self.current.replace(scope.SCOPE_BLOCK, scope.SCOPE_BLOCK * 2, 1),
            self.current.replace(scope.TINY_STEP, "", 1),
            self.current.replace(scope.JOB_MARKER, "\n  selector-renamed:\n", 1),
            self.current.replace(scope.job_text(), scope.job_text().replace("1260s", "9999s"), 1),
            self.current.replace(scope.job_text(), scope.job_text().replace("timeout-minutes: 22", "timeout-minutes: 99"), 1),
            self.current.replace(scope.TINY_STEP, "", 1) + scope.TINY_STEP,
            self.current + "\n  unregistered-job:\n",
            self.current.replace(scope.OPTION, "]", 1),
        ]
        for changed in corruptions:
            with self.subTest(), self.assertRaises(ValueError):
                scope.validate_workflow(changed)

    def test_old_jobs_checkout_and_permissions_cannot_hide(self):
        for before, after in (("  matrix:\n", "  matrix:\n    extra: true\n"),
                              ("contents: read", "contents: write"),
                              ("if: needs.scope.outputs.f07_linear == 'true'", "if: false"),
                              ("ref: ${{ github.event.pull_request.head.sha || github.sha }}", "ref: main"),
                              ("persist-credentials: false", "persist-credentials: true")):
            with self.subTest(before=before), self.assertRaises(ValueError):
                scope.validate_workflow(self.current.replace(before, after, 1))

    def test_mixed_frozen_science_or_new_workflow_is_rejected(self):
        for path in ("src/ap_pipeline.c", "include/audio_pipeline/audio_pipeline.h",
                     scope.REL + "webrtc_aec3_runner.cc",
                     scope.REL + "webrtc_aec3_linear_tap.py",
                     ".github/research/frontend-evolution-v1/webrtc-aec3-linear-tap-v1.json",
                     ".github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json",
                     ".github/workflows/verify.yml", ".github/workflows/selector-extra.yml",
                     "docs/research/frontend-evolution-v1/WEBRTC_AEC3_LINEAR_TAP_20261128/result.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected({scope.MODULE: (None, b"new scope fixture"), path: (b"old", b"changed")})

    def test_deletion_of_any_declared_path_rejected(self):
        for path in tuple(scope.CORE_PATHS) + scope.RESULT_PATHS + (scope.DOCUMENT, scope.NAVIGATION, scope.REGISTRY):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected({path: (b"existing", None)})

    def test_result_publication_is_only_registered_first_additions_without_engineering(self):
        changes = {path: (None, b"result-path-only fixture; not a measurement") for path in scope.RESULT_PATHS}
        self.flags(self.selected(changes), False)
        self.flags(self.selected(changes, "push"), False)
        for path in scope.RESULT_PATHS:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected({path: (b"published", b"changed")})
        with self.assertRaises(ValueError):
            self.selected({scope.RESULT_DIRECTORY + "/extra.json": (None, b"unknown")})
        with self.assertRaises(ValueError):
            self.selected({scope.LT2_RESULT_DIRECTORY + "/extra.json": (None, b"unknown")})

    def test_registry_exact_new_record_without_policy_or_historical_drift(self):
        before = scope.git_bytes(scope.BASE, scope.REGISTRY)
        after = (scope.ROOT / scope.REGISTRY).read_bytes()
        self.assertEqual(after, scope.expected_registry())
        self.assertEqual(scope.strip_registry(after), before)
        self.flags(self.selected({scope.REGISTRY: (before, after)}), False)
        old, new = json.loads(before), json.loads(after)
        self.assertEqual(new["records"][-1], scope.RETAINED_GAIN_SOURCE)
        self.assertEqual(new["records"][-2], scope.RETAINED_SOURCE)
        self.flags(self.selected({scope.REGISTRY: (scope.expected_selection_registry(), after)}), False)
        self.assertFalse(new["records"][-1]["gc_eligible"])
        self.assertFalse(new["records"][-1]["auto_gc"])
        new["records"].pop()
        new["records"].pop()
        self.assertEqual(new, old)
        for mutation in ("gc", "head", "history", "policy", "extra", "format"):
            value = json.loads(after)
            if mutation == "gc":
                value["records"][-1]["auto_gc"] = True
            elif mutation == "head":
                value["records"][-1]["head_sha"] = "0" * 40
            elif mutation == "history":
                value["records"][0]["status"] = "CHANGED"
            elif mutation == "policy":
                value["policy"] = {}
            elif mutation == "extra":
                value["records"].append(value["records"][-1])
            changed = json.dumps(value).encode()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.selected({scope.REGISTRY: (before, changed)})
        with self.assertRaises(ValueError):
            self.selected({scope.REGISTRY: (after, before)})

    def test_navigation_is_exact_terminal_append_and_support_only(self):
        before = scope.git_bytes(scope.BASE, scope.NAVIGATION)
        after = (scope.ROOT / scope.NAVIGATION).read_bytes()
        self.assertEqual(after, before + scope.NAVIGATION_APPEND.encode())
        self.assertEqual(scope.strip_navigation(after), before)
        self.flags(self.selected({scope.NAVIGATION: (before, after)}), False)
        for changed in (after + b"\nunknown", scope.NAVIGATION_APPEND.encode() + before,
                        after + scope.NAVIGATION_APPEND.encode(),
                        after.replace(b"F05_DUALMIC_VALIDATION_20261128", b"MUTATED_F05", 1)):
            with self.subTest(), self.assertRaises(ValueError):
                self.selected({scope.NAVIGATION: (before, changed)})

    def test_predecessor_adapters_are_exact_not_blanket_exemptions(self):
        for path in (scope.F07_MODULE, scope.F07_TEST):
            before = scope.git_bytes(scope.BASE, path)
            after = (scope.ROOT / path).read_bytes()
            self.assertEqual(after, scope.expected_predecessor_adapter(path))
            self.assertEqual(scope.predecessor_test_view(path, after), before)
            self.flags(self.selected({scope.MODULE: (None, b"new scope fixture"), path: (before, after)}), True)
            for bad in (after + b"\n# unrelated\n", before + b"\n# replacement\n"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    self.selected({scope.MODULE: (None, b"new scope fixture"), path: (before, bad)})
                with self.subTest(path=path), self.assertRaises(ValueError):
                    scope.predecessor_test_view(path, bad)

    def test_historical_fixture_view_keeps_all_old_changes(self):
        unknown = "src/ap_pipeline.c"
        before = b"historical before"
        after = b"historical after"
        got = scope.predecessor_test_changes({scope.MODULE: (None, b"new addition"), unknown: (before, after)})
        self.assertEqual(got, {unknown: (before, after)})
        for path in (scope.MODULE, scope.RESULT_PATHS[0]):
            with self.subTest(path=path), self.assertRaises(ValueError):
                scope.predecessor_test_changes({path: (b"already exists", b"rewrite")})
        with self.assertRaises(ValueError):
            scope.predecessor_test_changes({scope.RESULT_DIRECTORY + "/unknown.json": (None, b"unknown")})
        with self.assertRaises(ValueError):
            scope.predecessor_test_changes({scope.LT2_RESULT_DIRECTORY + "/unknown.json": (None, b"unknown")})

    def test_real_scope_dispatch_routes_new_and_existing_jobs_separately(self):
        body = self.current.split("          python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
        script = "\n".join(line[10:] if line.startswith("          ") else line for line in body.splitlines())
        cases = {scope.EXPERIMENT: "f07_selection", "webrtc-aec3-linear-tap": "f07_linear",
                 "ap-current-portable": "ap", "webrtc-aec3-engineering": "webrtc",
                 "dualmic-broadside-output-d8": "d8_archive"}
        for choice, active in cases.items():
            with self.subTest(choice=choice), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "outputs"
                env = dict(os.environ, EVENT_NAME="workflow_dispatch", SELECTED_EXPERIMENT=choice,
                           BASE_SHA=scope.BASE, GITHUB_OUTPUT=str(output), PYTHONDONTWRITEBYTECODE="1")
                result = subprocess.run([sys.executable, "-B", "-c", script], cwd=scope.ROOT, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                flags = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertEqual(flags[active], "true")
                self.assertTrue(all(value == "false" for name, value in flags.items() if name != active))

    def test_actual_initial_diff_routes_only_the_new_engineering_job(self):
        command = ["git", "-C", str(scope.ROOT), "-c", "core.fsmonitor=false",
                   "-c", "safe.directory=" + str(scope.ROOT.resolve())]
        names = set(subprocess.check_output(command + ["diff", "--name-only", scope.BASE], timeout=30).decode().splitlines())
        names.update(subprocess.check_output(command + ["ls-files", "--others", "--exclude-standard"], timeout=30).decode().splitlines())
        changes = {}
        for path in sorted(names):
            before = subprocess.run(command + ["show", scope.BASE + ":" + path], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=15)
            changes[path] = (before.stdout if before.returncode == 0 else None, (scope.ROOT / path).read_bytes())
        self.assertIn(scope.MODULE, changes)
        self.flags(self.selected(changes), True)

    def test_job_has_exact_head_finite_budget_and_no_old_or_speech_execution(self):
        job = scope.job_text()
        self.assertIn('--expected-head "$EXECUTION_SHA"', job)
        self.assertIn("timeout-minutes: 22", job)
        self.assertIn("1260s", job)
        self.assertIn("if: always()", job)
        self.assertIn("failed-build-evidence/", job)
        self.assertNotIn("/work/", job)
        self.assertNotIn("webrtc_aec3_selection.py run", job)
        self.assertNotIn("webrtc_aec3_linear_tap_ci.py run", job)
        self.assertNotIn("webrtc_aec3_ci.py run", job)
        self.assertEqual(job.count("webrtc_aec3_selection_ci.py run"), 1)
        self.assertEqual(job.count("ref: ${{ github.event.pull_request.head.sha || github.sha }}"), 1)

    def test_unsupported_events_and_bad_revision_refuse(self):
        for event in ("pull_request_target", "schedule", "repository_dispatch"):
            with self.subTest(event=event), self.assertRaises(ValueError):
                scope.select(event, "", {}, self.current)
        for revision in ("main", "0" * 40, "../main", True):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                scope.git_bytes(revision)

    def test_live_git_view_rejects_symlink_executable_or_ambiguous_members(self):
        invalid_entries = (b"120000 blob " + b"1" * 40 + b"\t" + scope.MODULE.encode() + b"\n",
                           b"100755 blob " + b"1" * 40 + b"\t" + scope.MODULE.encode() + b"\n",
                           b"040000 tree " + b"1" * 40 + b"\t" + scope.MODULE.encode() + b"\n",
                           b"100644 blob " + b"1" * 40 + b"\tfirst\n100644 blob " + b"2" * 40 + b"\tsecond\n")
        for entry in invalid_entries:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                env = {"EVENT_NAME": "pull_request", "BASE_SHA": scope.BASE,
                       "GITHUB_OUTPUT": str(Path(directory) / "outputs")}
                responses = [(scope.BASE + "\n").encode(), (scope.MODULE + "\n").encode(), entry]
                with mock.patch.dict(os.environ, env), mock.patch.object(scope, "git_bytes", return_value=b"exists"), \
                        mock.patch.object(scope.subprocess, "check_output", side_effect=responses), \
                        self.assertRaisesRegex(ValueError, "nonregular or ambiguous"):
                    scope.select_workflow()

    def test_read_only_git_survives_different_owner_assumption(self):
        with mock.patch.dict(os.environ, {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}):
            self.assertEqual(scope.git_bytes(scope.BASE, scope.WORKFLOW), self.frozen)


if __name__ == "__main__":
    unittest.main()
