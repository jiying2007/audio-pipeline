#!/usr/bin/env python3
"""Offline AP scope/transport negative tests. No C compile or DSP is executed."""
import ast
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import types
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

    def test_closed_ci_transport_rows_bind_actual_bytes_from_both_public_bases(self):
        registry = self.config["workflow"]["reviewed_ci_source_transport"]
        for base in (registry["public_parent"], registry["base_main"]):
            changes = {}
            for path, row in registry["files"].items():
                before = ap.git_bytes(base, path)
                after = (ap.ROOT / path).read_bytes()
                key = "base_sha256" if base == registry["public_parent"] else "main_base_sha256"
                self.assertEqual(ap.digest_or_none(before), row[key], path)
                self.assertEqual(ap.sha256(after), row["sha256"], path)
                self.assertEqual(len(after), row["size_bytes"], path)
                changes[path] = (before, after)
            self.assertTrue(changes)
            self.assert_flags(ap.select("pull_request", "", changes, self.current), False, False)

    def test_closed_ci_transport_cannot_admit_reverse_unknown_base_or_changed_payload(self):
        registry = self.config["workflow"]["reviewed_ci_source_transport"]
        for path in registry["files"]:
            before = ap.git_bytes(registry["public_parent"], path)
            after = (ap.ROOT / path).read_bytes()
            self.assertEqual(ap.validate_transition(path, before, after, self.config), "support")
            for bad_before, bad_after in ((after, before),
                    (b"unregistered predecessor\n", after),
                    (before, after + b"\nunreviewed change\n"), (before, None)):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    ap.validate_transition(path, bad_before, bad_after, self.config)

    def test_closed_ci_transport_composition_keeps_required_initial_engineering(self):
        changes = self.initial(True)
        for key in ("reviewed_transport_followup", "reviewed_ref_retention"):
            registry = self.config["workflow"][key]
            for path in registry["files"]:
                changes[path] = (ap.git_bytes(ap.MAIN_REFERENCE, path),
                                 ap.git_bytes(registry["public_revision"], path))
        for path in self.config["workflow"]["reviewed_ci_source_transport"]["files"]:
            changes[path] = (ap.git_bytes(ap.MAIN_REFERENCE, path), (ap.ROOT / path).read_bytes())
        self.assert_flags(ap.select("pull_request", "", changes, self.current), True, True)

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

    def test_reserved_results_only_are_support_before_any_measurement(self):
        changes = {name: (None, b"selector-only future result fixture; no measurement claim\n") for name in ap.RESULT_PATHS}
        self.assert_flags(ap.select("pull_request", "", changes, self.current), False, False)
        current = (ap.ROOT / ap.NAVIGATION).read_bytes()
        from webrtc_aec3_linear_tap_ci import strip_navigation
        current = strip_navigation(current)
        result_link = ap.NAVIGATION_ENTRIES[-1].encode()
        self.assertLessEqual(current.count(result_link), 1)
        unpublished = current.replace(result_link, b"")
        # Construct the declared before-state explicitly even after the real
        # result/navigation has been published. Production duplicate rejection
        # remains unchanged and is exercised for both fixture premises.
        for fixture in (unpublished, unpublished + result_link):
            with self.subTest(already_published=result_link in fixture):
                before = fixture.replace(result_link, b"")
                self.assertNotIn(result_link, before)
                after = before + result_link
                changes[ap.NAVIGATION] = (before, after)
                self.assert_flags(ap.select("pull_request", "", changes, self.current), False, False)
                changes[ap.NAVIGATION] = (before, after + result_link)
                with self.assertRaisesRegex(ValueError, "AP_DUPLICATE_SUPPORT_LINE"):
                    ap.select("pull_request", "", changes, self.current)

    def test_reserved_results_do_not_hide_missing_engineering_in_initial_mix(self):
        changes = self.initial(True)
        changes.update({name: (None, b"future result path fixture\n") for name in ap.RESULT_PATHS})
        self.assert_flags(ap.select("pull_request", "", changes, self.current), True, True)

    def test_unknown_result_or_published_result_rewrite_is_refused(self):
        path = ap.RESULT_PATHS[0]
        for changes in ({path: (b"published", b"rewrite")}, {path: (b"published", None)},
                        {path.replace("README.zh-CN.md", "unregistered.json"): (None, b"unknown")}):
            with self.subTest(), self.assertRaises(ValueError):
                ap.select("pull_request", "", changes, self.current)

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

    def test_verify_git_context_is_exact_and_five_command_scoped(self):
        path = ap.previous.VERIFY_WORKFLOW
        current = (ap.ROOT / path).read_bytes()
        context = ap.VERIFY_RESEARCH_SCOPED.encode()
        self.assertEqual(current.count(context), 1)
        stripped = current.replace(context, ap.VERIFY_RESEARCH_PLAIN.encode())
        self.assertEqual(ap.strip_exact(stripped, ap.VERIFY_LINES), ap.git_bytes(ap.REFERENCE, path))
        for before in (stripped, ap.git_bytes(ap.MAIN_REFERENCE, path), ap.git_bytes(ap.REFERENCE, path),
                       ap.git_bytes(ap.VERIFY_GIT_CONTEXT_FAILED_REVISION, path),
                       ap.git_bytes(ap.VERIFY_GIT_HOST_CONTEXT_FAILED_REVISION, path)):
            with self.subTest(predecessor=ap.sha256(before)):
                self.assert_flags(ap.select("pull_request", "", {path: (before, current)}, self.current), False, False)
        for changed in (
                current.replace(b'GIT_CONFIG_VALUE_0="$ap_verify_workspace"', b'GIT_CONFIG_VALUE_0="*"', 1),
                current.replace(b'            test -n "${GITHUB_WORKSPACE:-}"\n', b"", 1),
                current.replace(b'            case "$GITHUB_WORKSPACE" in /*) ;; *) exit 2 ;; esac\n', b"", 1),
                current.replace(b'            test "$ap_verify_workspace" = "$(pwd -P)"\n', b"", 1),
                current.replace(b'$(cd "$GITHUB_WORKSPACE" && pwd -P)', b'${{ github.workspace }}', 1),
                current.replace(b"GIT_CONFIG_COUNT=1", b"GIT_CONFIG_COUNT=2", 1),
                current.replace(b"GIT_CONFIG_KEY_0=safe.directory", b"GIT_CONFIG_KEY_0=safe.bareRepository", 1),
                current.replace(b"      - name: Validate test-intelligence and assurance tools", b"      - name: Another step", 1),
                current.replace(ap.VERIFY_RESEARCH_COMMANDS[2].encode(), b"", 1),
                current.replace(ap.VERIFY_RESEARCH_COMMANDS[0].encode(), ap.VERIFY_RESEARCH_COMMANDS[0].encode() * 2, 1),
                current.replace(b"          (\n", b"          (\n            set +e\n", 1),
                current.replace(context, b"", 1) + context,
                current + context):
            with self.subTest(), self.assertRaises(ValueError):
                ap.select("pull_request", "", {path: (stripped, changed)}, self.current)

    def test_verify_git_context_cannot_be_removed_after_introduction(self):
        path = ap.previous.VERIFY_WORKFLOW
        current = (ap.ROOT / path).read_bytes()
        stripped = current.replace(ap.VERIFY_RESEARCH_SCOPED.encode(), ap.VERIFY_RESEARCH_PLAIN.encode())
        for previous in (stripped, ap.git_bytes(ap.VERIFY_GIT_CONTEXT_FAILED_REVISION, path),
                         ap.git_bytes(ap.VERIFY_GIT_HOST_CONTEXT_FAILED_REVISION, path)):
            with self.subTest(), self.assertRaisesRegex(ValueError, "EXACT_VERIFY_TINY_CONTEXT"):
                ap.select("pull_request", "", {path: (current, previous)}, self.current)

    def test_host_context_predecessor_must_be_exact_public_failure_bytes(self):
        path = ap.previous.VERIFY_WORKFLOW
        current = (ap.ROOT / path).read_bytes()
        old = ap.git_bytes(ap.VERIFY_GIT_HOST_CONTEXT_FAILED_REVISION, path)
        self.assertEqual(old.count(ap.VERIFY_RESEARCH_HOST_SCOPED.encode()), 1)
        changed = old.replace(b"      - name: Validate test-intelligence and assurance tools",
                              b"      - name: Another step", 1)
        self.assertNotEqual(changed, old)
        with self.assertRaisesRegex(ValueError, "UNREGISTERED_HOST_CONTEXT_GIT_PREDECESSOR"):
            ap.select("pull_request", "", {path: (changed, current)}, self.current)

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


class PrecompiledCorrelationTests(unittest.TestCase):
    """Pure/source/state negative fixtures; never load or compile a helper .so."""
    def test_source_pins_and_compile_flags_match_original_cold_loader(self):
        original = ap.correlation_sources()
        self.assertIsNone(original["module"]._NATIVE_STATE)
        tree = ast.parse((ap.ROOT / ap.CORR_LOADER).read_text())
        flags = next([item.value for item in node.value.right.elts] for node in ast.walk(tree)
                     if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "command" for target in node.targets)
                     and isinstance(node.value, ast.BinOp) and isinstance(node.value.right, ast.List))
        self.assertEqual(ap.CORR_FLAGS, flags + ["-shared"])
        command = ap.render_corr_command(Path("/unit-fixture/build"), {"gcc": {"path": "/unit-fixture/gcc"}}, Path("/frozen/source"))
        self.assertEqual(command, ["/unit-fixture/gcc"] + flags + ["-shared", "/frozen/source/" + ap.CORR_SOURCE,
                                                               "-lm", "-o", "/unit-fixture/build/librender_corr_exact.so"])
        self.assertEqual(len(ap.plan()["source"]["main_reference_files_sha256"]), 59)
        for name, digest in ap.CORR_PINS.items():
            self.assertEqual(ap.sha256((ap.ROOT / name).read_bytes()), digest)
            self.assertEqual(ap.git_bytes(ap.MAIN_REFERENCE, name), (ap.ROOT / name).read_bytes())

    def test_four_short_pure_python_oracles_do_not_initialize_native_state(self):
        original = ap.correlation_sources()
        module = original["module"]
        with mock.patch.object(module, "_load_native", side_effect=AssertionError("must not compile or load")), \
                mock.patch.object(ap.ctypes, "CDLL") as cdll:
            for spec, expected in zip(ap.correlation_fixture_specs(), [(17, 1.0), (-17, 1.0), (0, 0.0), (0, 0.0)]):
                self.assertEqual(ap.correlation_oracle(spec["a"], spec["b"], original["engine"].normalized_corr), expected)
            with self.assertRaisesRegex(ValueError, "sample bound"):
                ap.correlation_oracle([0] * 321, [0] * 64, original["engine"].normalized_corr)
            cdll.assert_not_called()
        self.assertIsNone(module._NATIVE_STATE)

    def test_parent_pollution_cannot_be_hidden_by_removing_current_environment(self):
        ap.reject_loader_pollution({}, b"SAFE=value\x00")
        for name in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "fresh clean Python"):
                ap.reject_loader_pollution({name: "fixture"}, b"SAFE=value\x00")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "fresh clean Python"):
                ap.reject_loader_pollution({}, (name + "=exec-time-fixture\x00").encode())

    def test_preexisting_native_state_and_auto_compile_temp_refuse_before_cdll(self):
        module = ap.correlation_sources()["module"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "librender_corr_exact.so"
            path.write_bytes(b"negative state fixture; this is not an ELF")
            build = {"source_revision": "0" * 40,
                     "render_correlation": {"binary_sha256": ap.sha256(path.read_bytes()), "compiler": "unit fixture"}}
            for state, native_temp in (({"binary_sha256": ap.sha256(path.read_bytes())}, None), (None, object())):
                with self.subTest(), mock.patch.object(module, "_NATIVE_STATE", state), \
                        mock.patch.object(module, "_NATIVE_TEMP", native_temp), mock.patch.object(ap.ctypes, "CDLL") as cdll:
                    with self.assertRaisesRegex(ValueError, "state|compiled"):
                        ap.bind_verified_render_corr(Path(temp), build, {"render_corr": path}, module)
                    cdll.assert_not_called()

    def test_guard_refuses_cleared_or_replaced_state_before_original_score(self):
        for mutation in ("clear", "state", "library", "function", "temporary"):
            module = types.ModuleType("synthetic_native_state_negative")
            module._NATIVE_LOCK = threading.Lock()
            module._NATIVE_TEMP = None
            library, function = object(), object()
            state = {"library": library, "function": function, "library_path": Path("/unit-fixture/helper.so"),
                     "binary_sha256": "1" * 64, "compiler": "unit fixture"}
            module._NATIVE_STATE = state
            module.exact_score, module.find_best_lag, module._load_native = mock.Mock(), mock.Mock(), mock.Mock()
            entry = {"state": state, "library": library, "function": function, "path": state["library_path"], "pid": os.getpid(),
                     "binding": {"binary_sha256": "1" * 64, "compiler": "unit fixture"}}
            with self.subTest(mutation=mutation), mock.patch.dict(ap._RENDER_BINDINGS, {module: entry}):
                guarded = ap.guarded_max_abs_corr(module, lambda *args: 0.0)
                if mutation == "clear":
                    module._NATIVE_STATE = None
                elif mutation == "state":
                    module._NATIVE_STATE = dict(state)
                elif mutation == "temporary":
                    module._NATIVE_TEMP = object()
                else:
                    state[mutation] = object()
                with self.assertRaisesRegex(ValueError, "state|object"):
                    guarded([1] * 64, [1] * 64, 16000)
                module.exact_score.assert_not_called()
                module._load_native.assert_not_called()

    def runtime_fixture(self):
        helper = "/old-host/bundle/lib/librender_corr_exact.so"
        libraries = {"/old-host/lib/libc.so.6": "1" * 64, "/old-host/lib/libm.so.6": "2" * 64,
                     "/old-host/lib/ld-linux-x86-64.so.2": "3" * 64}
        value = {"runtime_identity": {"system": "Linux", "machine": "x86_64", "release": "schema-fixture",
                  "os_release_sha256": "4" * 64, "libraries": libraries,
                  "library_names": {Path(path).name: path for path in libraries}},
                 "helper_library_path": helper, "pid": 1, "loader_environment": "CLEAN_AT_START_AND_NOW",
                 "parent_library_mappings": {path: {"sha256": digest, "inode": index + 1, "device": [0, 1]}
                   for index, (path, digest) in enumerate(dict(libraries, **{helper: "5" * 64}).items())}}
        return value, {"library": ap.PATHS["render_corr"], "binary_sha256": "5" * 64}

    def test_stored_math_runtime_is_portable_without_current_host_or_file_access(self):
        value, binding = self.runtime_fixture()
        with mock.patch.object(ap.previous, "runtime_identity") as ldd, mock.patch.object(ap.ctypes, "CDLL") as cdll:
            self.assertEqual(ap.verify_render_corr_runtime(value, binding), ap.normalize_render_corr_runtime(value["runtime_identity"]))
            ldd.assert_not_called()
            cdll.assert_not_called()

    def test_resealed_math_path_must_still_bind_original_engineering_bundle(self):
        value, binding = self.runtime_fixture()
        ap.verify_render_corr_runtime(value, binding, Path("/old-host/bundle"))
        old = value["helper_library_path"]
        replacement = "/another-host/bundle/" + ap.PATHS["render_corr"]
        value["helper_library_path"] = replacement
        value["parent_library_mappings"][replacement] = value["parent_library_mappings"].pop(old)
        # Its own map is coherent, but it is not the original report's bundle.
        ap.verify_render_corr_runtime(value, binding)
        with self.assertRaisesRegex(ValueError, "original engineering bundle"):
            ap.verify_render_corr_runtime(value, binding, Path("/old-host/bundle"))

    def test_stored_math_runtime_cannot_drop_dependencies_or_change_sha_inode_path(self):
        original, binding = self.runtime_fixture()
        for mutation in ("drop-libc", "only-helper", "wrong-sha", "wrong-helper", "zero-inode", "bool-device", "relative-path"):
            value = json.loads(json.dumps(original))
            mappings = value["parent_library_mappings"]
            key = "/old-host/lib/libc.so.6"
            if mutation == "drop-libc":
                del mappings[key]
            elif mutation == "only-helper":
                value["parent_library_mappings"] = {value["helper_library_path"]: mappings[value["helper_library_path"]]}
            elif mutation == "wrong-sha":
                mappings[key]["sha256"] = "0" * 64
            elif mutation == "wrong-helper":
                mappings[value["helper_library_path"]]["sha256"] = "0" * 64
            elif mutation == "zero-inode":
                mappings[key]["inode"] = 0
            elif mutation == "bool-device":
                mappings[key]["device"] = [True, 1]
            else:
                value["helper_library_path"] = "relative/" + ap.PATHS["render_corr"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                ap.verify_render_corr_runtime(value, binding)


class VerifyGitIsolationTests(unittest.TestCase):
    """Real POSIX shell/Git metadata; timeout stubs never execute a research test."""

    def run_shell_fixture(self, fail_command=None, workspace_kind="same", legacy_host_context=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / "observations.jsonl"
            probe = root / "probe.py"
            probe.write_text(
                "import json,os,sys\nfrom pathlib import Path\n"
                "sys.path.insert(0," + repr(str(ap.ROOT / "tests/validation/frontend_evolution")) + ")\n"
                "from fe09_f1_r8_source_bridge import Git\n"
                "Git(Path(" + repr(str(ap.ROOT)) + "))\n"
                "keys=('GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0')\n"
                "assert not any(os.environ.get(key) for key in keys)\n"
                "with open(os.environ['AP_TEST_LOG'],'a') as out:\n"
                " out.write(json.dumps({'phase':sys.argv[1],'git_env':{key:os.environ.get(key) for key in keys}})+'\\n')\n")
            timeout = root / "timeout"
            timeout.write_text("#!" + sys.executable + "\n"
                "import json,os,sys\n"
                "keys=('GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0')\n"
                "actual={key:os.environ.get(key) for key in keys}\n"
                "assert actual=={'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'safe.directory','GIT_CONFIG_VALUE_0':os.environ['AP_TEST_WORKSPACE']}\n"
                "assert sys.argv[1:4]==['60s','python3','-B'] and len(sys.argv)==5\n"
                "with open(os.environ['AP_TEST_LOG'],'a') as out:\n"
                " out.write(json.dumps({'phase':'tiny-command-schema-only','command':sys.argv[1:],'git_env':actual})+'\\n')\n"
                "raise SystemExit(23 if sys.argv[-1]==os.environ.get('AP_TEST_FAIL_COMMAND') else 0)\n")
            timeout.chmod(0o755)
            # The actual five command bytes remain intact in the workflow;
            # only the test runner's timeout executable is this declared stub.
            # This declared host path is deliberately different from the real
            # checkout. Only the old expression-based block consumes it.
            host_workspace = str(root / "host-workspace")
            source = ap.VERIFY_RESEARCH_HOST_SHELL if legacy_host_context else ap.VERIFY_RESEARCH_SHELL
            shell = "\n".join(line[10:] for line in source.splitlines())
            shell = shell.replace("${{ github.workspace }}", host_workspace)
            script = root / "fixture.sh"
            quoted_python = "'" + sys.executable.replace("'", "'\\''") + "'"
            quoted_probe = "'" + str(probe).replace("'", "'\\''") + "'"
            script.write_text(quoted_python + " -B " + quoted_probe + " before-docs-r11\n" + shell + "\n" +
                              quoted_python + " -B " + quoted_probe + " after-research\n")
            environment = {key:value for key,value in os.environ.items() if not key.startswith("GIT_")}
            environment.update(PATH=str(root) + os.pathsep + os.environ.get("PATH", ""),
                               PYTHONDONTWRITEBYTECODE="1", AP_TEST_LOG=str(log), AP_TEST_WORKSPACE=str(ap.ROOT),
                               GIT_TEST_ASSUME_DIFFERENT_OWNER="1", GIT_CONFIG_GLOBAL="/dev/null",
                               GIT_CONFIG_SYSTEM="/dev/null", GIT_CONFIG_NOSYSTEM="1")
            environment.pop("GITHUB_WORKSPACE", None)
            if workspace_kind == "same":
                environment["GITHUB_WORKSPACE"] = str(ap.ROOT)
            elif workspace_kind == "symlink":
                alias = root / "checkout-alias"
                alias.symlink_to(ap.ROOT, target_is_directory=True)
                environment["GITHUB_WORKSPACE"] = str(alias)
            elif workspace_kind == "wrong":
                environment["GITHUB_WORKSPACE"] = str(root)
            elif workspace_kind == "nonexistent":
                environment["GITHUB_WORKSPACE"] = str(root / "missing-workspace")
            elif workspace_kind == "relative":
                environment["GITHUB_WORKSPACE"] = "."
            elif workspace_kind == "empty":
                environment["GITHUB_WORKSPACE"] = ""
            else:
                self.assertEqual(workspace_kind, "missing")
            if fail_command:
                environment["AP_TEST_FAIL_COMMAND"] = fail_command
            result = subprocess.run(["/bin/sh", "-e", str(script)], cwd=ap.ROOT, env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            observations = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, observations

    def test_real_shell_preserves_clean_parent_and_original_git_reader_boundary(self):
        result, observations = self.run_shell_fixture()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual([row["phase"] for row in observations],
                         ["before-docs-r11"] + ["tiny-command-schema-only"] * 5 + ["after-research"])
        expected = [line.strip().split()[1:] for line in ap.VERIFY_RESEARCH_COMMANDS]
        self.assertEqual([row["command"] for row in observations[1:-1]], expected)

    def test_every_tiny_failure_exits_parent_without_running_later_commands(self):
        paths = [line.strip().split()[-1] for line in ap.VERIFY_RESEARCH_COMMANDS]
        for index, path in enumerate(paths):
            with self.subTest(path=path):
                result, observations = self.run_shell_fixture(fail_command=path)
                self.assertEqual(result.returncode, 23, result.stderr.decode())
                self.assertEqual(len(observations), index + 2)
                self.assertNotIn("after-research", [row["phase"] for row in observations])

    def test_container_workspace_succeeds_where_frozen_host_context_fails(self):
        legacy, old_observations = self.run_shell_fixture(legacy_host_context=True)
        self.assertEqual(legacy.returncode, 128)
        self.assertIn(b"detected dubious ownership", legacy.stderr)
        self.assertEqual([row["phase"] for row in old_observations], ["before-docs-r11"])
        current, observations = self.run_shell_fixture()
        self.assertEqual(current.returncode, 0, current.stderr.decode())
        self.assertEqual(len(observations), 7)
        self.assertTrue(all(row["git_env"]["GIT_CONFIG_VALUE_0"] == str(ap.ROOT)
                            for row in observations[1:-1]))

    def test_exact_workspace_preflight_failure_cannot_reach_any_tiny(self):
        for kind in ("wrong", "nonexistent", "relative", "empty", "missing"):
            with self.subTest(workspace_kind=kind):
                result, observations = self.run_shell_fixture(workspace_kind=kind)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual([row["phase"] for row in observations], ["before-docs-r11"])

    def test_workspace_physical_alias_is_reduced_to_exact_checkout(self):
        result, observations = self.run_shell_fixture(workspace_kind="symlink")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(len(observations), 7)
        self.assertTrue(all(row["git_env"]["GIT_CONFIG_VALUE_0"] == str(ap.ROOT)
                            for row in observations[1:-1]))

    def test_historical_git_reader_still_refuses_step_wide_external_context(self):
        import fe09_f1_r8_source_bridge as historical
        with mock.patch.dict(os.environ, {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                                          "GIT_CONFIG_VALUE_0": str(ap.ROOT)}), \
                mock.patch.object(historical.subprocess, "Popen", side_effect=AssertionError("no old suite process")):
            with self.assertRaisesRegex(ValueError, "EXTERNAL_GIT_CONTEXT_REFUSED"):
                historical.Git(ap.ROOT)


class RuntimeObservationTests(unittest.TestCase):
    """Metadata-only ELF fixtures, never an executable or measured CI result."""

    @staticmethod
    def elf_fixture():
        data = bytearray(1024)
        ap.struct.pack_into("<16sHHIQQQIHHHHHH", data, 0, b"\x7fELF\x02\x01\x01" + bytes(9),
                            3, 62, 1, 0, 64, 768, 0, 64, 56, 1, 64, 4, 0)
        ap.struct.pack_into("<IIQQQQQQ", data, 64, 2, 6, 128, 0x1080, 0x1080, 96, 96, 8)
        names = bytearray(b"\0")
        symbols = [(0, 0, 0, 0, 0, 0)]
        for name in sorted(ap.CRT_WEAK_UNDEFINED):
            symbols.append((len(names), 0x20, 0, 0, 0, 0))
            names.extend(name.encode() + b"\0")
        symbols.append((len(names), 0x12, 0, 1, 0x2000, 1))
        names.extend(ap.CORR_ABI["symbol"].encode() + b"\0")
        data[256:256 + len(names)] = names
        for index, entry in enumerate(((5, 0x1100), (10, len(names)), (6, 0x11c0), (11, 24), (0, 0), (0, 0))):
            ap.struct.pack_into("<qQ", data, 128 + index * 16, *entry)
        for index, symbol in enumerate(symbols):
            ap.struct.pack_into("<IBBHQQ", data, 448 + index * 24, *symbol)
        sections = [(0,) * 10, (0, 6, 0, 0x1080, 128, 96, 2, 0, 8, 16),
                    (0, 3, 0, 0x1100, 256, len(names), 0, 0, 1, 0),
                    (0, 11, 0, 0x11c0, 448, len(symbols) * 24, 2, 1, 8, 24)]
        for index, section in enumerate(sections):
            ap.struct.pack_into("<IIQQQQIIQQ", data, 768 + index * 64, *section)
        return bytes(data)

    @staticmethod
    def raw(stdout=ap.STATIC_LDD_STDOUT, stderr=b"", code=0):
        return {"returncode": code, "timed_out": False, "output_complete": True,
                "stdout_original_bytes": len(stdout), "stderr_original_bytes": len(stderr),
                "stdout_base64": base64.b64encode(stdout).decode(), "stderr_base64": base64.b64encode(stderr).decode()}

    @classmethod
    def empty_runtime_fixture(cls):
        proof = ap.helper_elf_proof(cls.elf_fixture())
        helper = "/old-host/bundle/" + ap.PATHS["render_corr"]
        value = {"runtime_identity": {"system": "Linux", "machine": "x86_64", "release": "schema-fixture",
                  "os_release_sha256": "4" * 64, "libraries": {}, "library_names": {}, "dependency_free_elf": proof},
                 "helper_library_path": helper, "pid": 1, "loader_environment": "CLEAN_AT_START_AND_NOW",
                 "parent_library_mappings": {helper: {"sha256": proof["binary_sha256"], "inode": 1, "device": [0, 1]}}}
        binding = {"library": ap.PATHS["render_corr"], "binary_sha256": proof["binary_sha256"], "dependency_free_elf": proof}
        return value, binding

    def test_bounded_elf_proof_reads_bytes_without_subprocess_or_cdll(self):
        with mock.patch.object(ap.subprocess, "Popen", side_effect=AssertionError("no process")), \
                mock.patch.object(ap.ctypes, "CDLL", side_effect=AssertionError("no native load")):
            value = ap.helper_elf_proof(self.elf_fixture())
            ap.validate_helper_proof(value, ap.sha256(self.elf_fixture()))
            self.assertEqual(value["dt_needed"], [])
            self.assertEqual(set(value["weak_undefined_symbols"]), ap.CRT_WEAK_UNDEFINED)

    def test_helper_proof_rejects_needed_strong_unknown_weak_and_invalid_tables(self):
        for mutation in ("needed", "strong", "unknown-weak", "class", "type", "machine", "ph-range", "sh-range",
                         "dynamic-mismatch", "dynamic-address", "unterminated", "dynsym-range", "dynstr-range",
                         "symbol-pointer", "string-pointer", "string-size"):
            data = bytearray(self.elf_fixture())
            if mutation == "needed":
                ap.struct.pack_into("<qQ", data, 192, 1, 1)
            elif mutation == "strong":
                data[448 + 24 + 4] = 0x10
            elif mutation == "unknown-weak":
                data[257] = ord("X")
            elif mutation == "class":
                data[4] = 1
            elif mutation == "type":
                ap.struct.pack_into("<H", data, 16, 2)
            elif mutation == "machine":
                ap.struct.pack_into("<H", data, 18, 183)
            elif mutation == "ph-range":
                ap.struct.pack_into("<Q", data, 32, 1024)
            elif mutation == "sh-range":
                ap.struct.pack_into("<Q", data, 40, 1024)
            elif mutation == "dynamic-mismatch":
                ap.struct.pack_into("<Q", data, 64 + 32, 48)
            elif mutation == "dynamic-address":
                ap.struct.pack_into("<Q", data, 64 + 16, 0xdead)
            elif mutation == "unterminated":
                ap.struct.pack_into("<qQ", data, 208, 5, 256)
            elif mutation == "dynsym-range":
                ap.struct.pack_into("<Q", data, 768 + 3 * 64 + 24, 1000)
            elif mutation == "dynstr-range":
                ap.struct.pack_into("<Q", data, 768 + 2 * 64 + 32, 2000)
            elif mutation == "string-pointer":
                ap.struct.pack_into("<Q", data, 136, 0xdead)
            elif mutation == "string-size":
                ap.struct.pack_into("<Q", data, 152, 1)
            else:
                ap.struct.pack_into("<Q", data, 168, 0xdead)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                ap.helper_elf_proof(bytes(data))

    def test_only_exact_helper_static_ldd_line_can_take_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "librender_corr_exact.so"
            path.write_bytes(self.elf_fixture())
            good = ap.runtime_from_observation(path, "render_corr", self.raw())
            self.assertEqual(good["libraries"], {})
            ap.normalize_render_corr_runtime(good)
            with self.assertRaises(ValueError):
                ap.runtime_from_observation(path, "processor", self.raw())
            bad = [self.raw(code=1), self.raw(stderr=b"warning\n"), self.raw(b"statically linked\n"),
                   self.raw(ap.STATIC_LDD_STDOUT + b"unknown\n"), self.raw(ap.STATIC_LDD_STDOUT * 2),
                   self.raw(b"libmissing.so => not found\n"), self.raw(b""),
                   self.raw(b"libx.so => /tmp/x (0x1)\nlibx.so => /tmp/x (0x2)\n")]
            for record in bad:
                with self.subTest(record=record), self.assertRaises(ValueError):
                    ap.runtime_from_observation(path, "render_corr", record)
            data = bytearray(path.read_bytes())
            ap.struct.pack_into("<qQ", data, 192, 1, 1)
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "DT_NEEDED"):
                ap.runtime_from_observation(path, "render_corr", self.raw())

    def test_empty_dependency_reader_requires_verified_proof_and_helper_mapping(self):
        value, binding = self.empty_runtime_fixture()
        with mock.patch.object(ap.subprocess, "Popen", side_effect=AssertionError("no process")), \
                mock.patch.object(ap.ctypes, "CDLL", side_effect=AssertionError("no native load")):
            self.assertEqual(ap.verify_render_corr_runtime(value, binding)["libraries"], {})
            for mutation in ("drop-proof", "wrong-sha", "drop-helper", "unproven-binding", "wrong-weak"):
                row, bound = json.loads(json.dumps(value)), json.loads(json.dumps(binding))
                if mutation == "drop-proof":
                    del row["runtime_identity"]["dependency_free_elf"]
                elif mutation == "wrong-sha":
                    row["runtime_identity"]["dependency_free_elf"]["binary_sha256"] = "0" * 64
                elif mutation == "drop-helper":
                    row["parent_library_mappings"].clear()
                elif mutation == "unproven-binding":
                    del bound["dependency_free_elf"]
                else:
                    row["runtime_identity"]["dependency_free_elf"]["weak_undefined_symbols"].append("unknown")
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    ap.verify_render_corr_runtime(row, bound)
            grouped = {key: value["runtime_identity"] for key in ap.ELF_KEYS}
            with self.assertRaisesRegex(ValueError, "SDK runtime"):
                ap.normalize_runtime(grouped)

    def test_raw_ldd_is_flushed_before_parse_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / "librender_corr_exact.so"
            helper.write_bytes(self.elf_fixture())
            def launch(command, **kwargs):
                kwargs["stdout"].write(b"unknown line\n")
                kwargs["stderr"].write(b"original warning\n")
                return types.SimpleNamespace(wait=lambda **kw: 0)
            stream = io.StringIO()
            with mock.patch.object(ap.subprocess, "Popen", side_effect=launch), mock.patch.object(ap.sys, "stderr", stream), \
                    ap.runtime_observation_log(root / "runtime.jsonl"):
                with self.assertRaisesRegex(ValueError, "stderr"):
                    ap.observe_runtime(helper, "render_corr")
                # The descriptor is still open: data must already be flushed.
                lines = (root / "runtime.jsonl").read_text().splitlines()
                self.assertEqual(len(lines), 1)
                raw = json.loads(lines[0])
                self.assertEqual(base64.b64decode(raw["stdout_base64"]), b"unknown line\n")
                self.assertEqual(base64.b64decode(raw["stderr_base64"]), b"original warning\n")
                self.assertEqual(raw["command"][1], str(helper))
                self.assertEqual(raw["returncode"], 0)
                self.assertEqual(stream.getvalue(), lines[0] + "\n")

    def test_aslr_raw_logs_are_separate_from_stable_runtime_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary, library = root / "ap_process_pcm", root / "libschema.so"
            binary.write_bytes(b"not executed: SDK name metadata fixture")
            library.write_bytes(b"not loaded: library metadata fixture")
            counter = [0]
            def launch(command, **kwargs):
                counter[0] += 1
                kwargs["stdout"].write(("libschema.so => " + str(library) + " (0x" + str(counter[0]) + ")\n").encode())
                return types.SimpleNamespace(wait=lambda **kw: 0)
            with mock.patch.object(ap.subprocess, "Popen", side_effect=launch), mock.patch.object(ap.sys, "stderr", io.StringIO()), \
                    ap.runtime_observation_log(root / "runtime.jsonl"):
                before = ap.observe_runtime(binary, "processor")
                after = ap.observe_runtime(binary, "processor")
            rows = [json.loads(line) for line in (root / "runtime.jsonl").read_text().splitlines()]
            self.assertEqual(before, after)
            self.assertNotEqual(rows[0]["stdout_base64"], rows[2]["stdout_base64"])
            self.assertEqual(len(rows), 4)

    def test_oversized_raw_output_retains_explicit_bounded_failure_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            helper = root / "librender_corr_exact.so"
            helper.write_bytes(self.elf_fixture())
            def launch(command, **kwargs):
                kwargs["stdout"].write(b"x" * 70000)
                return types.SimpleNamespace(wait=lambda **kw: 0)
            with mock.patch.object(ap.subprocess, "Popen", side_effect=launch), mock.patch.object(ap.sys, "stderr", io.StringIO()), \
                    ap.runtime_observation_log(root / "runtime.jsonl"):
                with self.assertRaisesRegex(ValueError, "overflow"):
                    ap.observe_runtime(helper, "render_corr")
            rows = [json.loads(line) for line in (root / "runtime.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["output_complete"])
            self.assertEqual(rows[0]["stdout_original_bytes"], 70000)
            self.assertEqual(len(base64.b64decode(rows[0]["stdout_base64"])), 65537)

    def test_runtime_journal_rechecks_actual_helper_bytes_without_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            root, old = Path(temp), Path("/old-host/bundle")
            paths = {key: root / Path(name).name for key, name in ap.PATHS.items() if key in ap.ELF_KEYS}
            for path in paths.values():
                path.write_bytes(self.elf_fixture())
            empty, binding = self.empty_runtime_fixture()
            dynamic = dict(empty["runtime_identity"], libraries={"/old/lib.so": "1" * 64}, library_names={"lib.so": "/old/lib.so"})
            del dynamic["dependency_free_elf"]
            identity = {"processor": dynamic, "build_info": dynamic, "render_corr": empty["runtime_identity"]}
            records = []
            for index, key in enumerate(ap.ELF_KEYS * 2):
                raw = dict(self.raw(stdout=ap.STATIC_LDD_STDOUT if key == "render_corr" else b"lib.so => /old/lib.so (0x123)\n"),
                           event="AP_RUNTIME_RAW_LDD", observation=index + 1, key=key, elapsed_seconds=0.01,
                           command=["/old/bin/ldd", str(old / ap.PATHS[key])], tool_sha256="2" * 64,
                           binary_sha256=ap.sha256(paths[key].read_bytes()))
                resolution = {} if key == "render_corr" else {"lib.so": {"raw_path": "/old/lib.so", "resolved_path": "/old/lib.so", "sha256": "1" * 64}}
                records += [raw, {"event": "AP_RUNTIME_IDENTITY", "observation": index + 1, "key": key,
                                  "identity": identity[key], "library_resolution": resolution}]
            journal = root / "runtime.jsonl"
            def save():
                journal.write_text("".join(json.dumps(record) + "\n" for record in records))
            save()
            with mock.patch.object(ap.subprocess, "Popen", side_effect=AssertionError("no process")), \
                    mock.patch.object(ap.ctypes, "CDLL", side_effect=AssertionError("no native load")):
                ap.verify_runtime_journal(journal, identity, old, paths, "build")
                original_raw = records[0]["stdout_base64"]
                records[0]["stdout_base64"] = base64.b64encode(b"lib.so => /bad/lib.so (0x123)\n").decode()
                save()
                with self.assertRaisesRegex(ValueError, "raw/resolved"):
                    ap.verify_runtime_journal(journal, identity, old, paths, "build")
                records[0]["stdout_base64"] = original_raw
                save()
                data = bytearray(paths["render_corr"].read_bytes())
                ap.struct.pack_into("<qQ", data, 192, 1, 1)
                paths["render_corr"].write_bytes(data)
                digest = ap.sha256(data)
                identity["render_corr"]["dependency_free_elf"]["binary_sha256"] = digest
                for raw in records[::2]:
                    if raw["key"] == "render_corr":
                        raw["binary_sha256"] = digest
                save()
                with self.assertRaisesRegex(ValueError, "DT_NEEDED"):
                    ap.verify_runtime_journal(journal, identity, old, paths, "build")


if __name__ == "__main__":
    unittest.main()
