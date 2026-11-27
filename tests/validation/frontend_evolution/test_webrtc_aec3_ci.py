#!/usr/bin/env python3
"""Offline selector/transport/bundle tests; never a compiled AEC3 PASS."""
import io
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

import webrtc_aec3_ci as ci


class SelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Genuine Git object, not a second maintained copy of the old workflow.
        cls.frozen = ci.git("show", ci.BASELINE + ":" + ci.WORKFLOW)
        cls.current = (ci.ROOT / ci.WORKFLOW).read_text()

    def select(self, paths, prior=None, current=None):
        return ci.select("pull_request", "", paths, current or self.current,
                         self.frozen if prior is None else prior, self.frozen)

    def test_original_scope_and_all_jobs_are_exact_git_bytes(self):
        self.assertEqual(ci.old_workflow(self.current).encode(), self.frozen.encode())
        self.assertEqual(ci.historical_jobs(self.current).encode(), ci.historical_jobs(self.frozen).encode())
        self.assertEqual(ci.sha256(self.frozen.encode()), "d5dc866941cd9ca3cbae5a6dc5297b97115e903ca59573dd0a5a6c790a9e313f")

    def test_new_source_selects_only_aec3(self):
        result = self.select(["tests/validation/frontend_evolution/webrtc_aec3_source.py", ci.WORKFLOW])
        self.assertEqual(result["webrtc"], "true")
        self.assertTrue(all(result[key] == "false" for key in ci.HISTORICAL_FLAGS))

    def test_manual_aec3_isolated(self):
        result = ci.select("workflow_dispatch", "webrtc-aec3-engineering", [], self.current, self.current, self.frozen)
        self.assertEqual(result, {**{key: "false" for key in ci.HISTORICAL_FLAGS}, "webrtc": "true"})

    def test_only_new_job_change_selects_aec3(self):
        prior = self.current.replace("Fixed WebRTC AEC3 reference engineering", "Previous AEC3 job label")
        self.assertEqual(self.select([ci.WORKFLOW], prior=prior)["webrtc"], "true")

    def test_unchanged_workflow_and_unrelated_path_do_not_select(self):
        self.assertIsNone(self.select(["docs/README.md"], prior=self.current))
        self.assertIsNone(self.select([], prior=self.current))

    def test_mixed_historical_or_engine_changes_rejected(self):
        for path in ("tests/validation/frontend_evolution/dualmic_target_gate_d5.py", "src/ap_pipeline.c",
                     "docs/research/frontend-evolution-v1/DUALMIC_GAIN_RAMP_D6_RESULT.zh-CN.md"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "SEPARATE_RESEARCH"):
                self.select(["tests/validation/frontend_evolution/webrtc_aec3_ci.py", path])

    def test_historical_job_mutation_rejected(self):
        changed = self.current.replace("  matrix:\n", "  matrix:\n    changed: true\n", 1)
        with self.assertRaisesRegex(ValueError, "HISTORICAL_JOBS"):
            self.select([ci.WORKFLOW], current=changed)

    def test_historical_scope_mutation_rejected(self):
        changed = self.current.replace("          event = os.environ['EVENT_NAME']", "          event = 'changed'")
        with self.assertRaisesRegex(ValueError, "HISTORICAL_SCOPE"):
            self.select([ci.WORKFLOW], current=changed)

    def test_missing_or_duplicate_aec3_job_rejected(self):
        for changed in (self.current.split(ci.JOB_MARKER)[0], self.current + ci.JOB_MARKER):
            with self.subTest(), self.assertRaises(ValueError):
                self.select(["tests/validation/frontend_evolution/webrtc_aec3_ci.py"], current=changed)

    def test_specific_platform_document_is_support_only(self):
        doc = "docs/research/frontend-evolution-v1/LONG_TERM_RESEARCH_PLATFORM.zh-CN.md"
        self.assertIsNone(self.select([doc], prior=self.current))
        self.assertEqual(self.select([doc, "tests/validation/frontend_evolution/webrtc_aec3_ci.py"])["webrtc"], "true")
        with self.assertRaisesRegex(ValueError, "SEPARATE_RESEARCH"):
            self.select(["docs/research/frontend-evolution-v1/UNRELATED.md", "tests/validation/frontend_evolution/webrtc_aec3_ci.py"])

    def test_real_manual_d8_selector_remains_archive_only(self):
        # Only the existing scope Python runs; no workflow job or DSP is launched.
        body = self.current.split("          python3 - <<'PY'\n", 1)[1].split("          PY\n", 1)[0]
        script = "\n".join(line[10:] if line.startswith("          ") else line for line in body.splitlines())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "outputs"
            env = dict(os.environ, EVENT_NAME="workflow_dispatch", SELECTED_EXPERIMENT="dualmic-broadside-output-d8",
                       GITHUB_OUTPUT=str(output), BASE_SHA=ci.BASELINE, PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ci.ROOT, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["d8_archive"], "true")
            self.assertEqual(values["webrtc"], "false")
            self.assertTrue(all(values[key] == "false" for key in ci.HISTORICAL_FLAGS if key != "d8_archive"))

    def test_d8_inputs_do_not_select_aec3(self):
        self.assertIsNone(ci.select("workflow_dispatch", "dualmic-broadside-output-d8", [],
                                    self.current, self.current, self.frozen))
        self.assertIsNone(self.select(["tests/validation/frontend_evolution/dualmic_broadside_output_d8_archive.py"],
                                      prior=self.current))

    def test_new_job_has_bounded_real_binary_entry_and_always_archive(self):
        job = self.current.split(ci.JOB_MARKER, 1)[1]
        for expected in ("runs-on: ubuntu-24.04", "timeout-minutes: 20", "if: always()", "1110s",
                         "webrtc_aec3_ci.py run", "--expected-head", "include-hidden-files: true",
                         "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"):
            self.assertIn(expected, job)
        self.assertNotIn("dualmic_", job)
        self.assertNotIn("webrtc_aec3_reference", job)
        for line in ci.VERIFY_COMMANDS:
            self.assertEqual((ci.ROOT / ci.VERIFY_WORKFLOW).read_text().count(line), 1)

    def test_navigation_allows_only_exact_top_runbook_entry(self):
        before = "# Frontend Evolution v1 / 双麦与四麦开放研究\n\n## Historical result\nunchanged\n"
        allowed = before.replace("\n\n", "\n\n" + ci.NAVIGATION_ENTRY, 1)
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(ci, "ROOT", Path(temp)), mock.patch.object(ci, "git", return_value=before):
            path = Path(temp) / ci.NAVIGATION
            path.parent.mkdir(parents=True)
            path.write_text(allowed)
            ci.support_changes([ci.NAVIGATION], ci.BASELINE)
            for changed in (allowed.replace("unchanged", "AEC3 changed old evidence"),
                            allowed + "\nAEC3 unrelated extra\n", allowed.replace(ci.NAVIGATION_ENTRY, "")):
                path.write_text(changed)
                with self.subTest(), self.assertRaisesRegex(ValueError, "NAVIGATION"):
                    ci.support_changes([ci.NAVIGATION], ci.BASELINE)

    def test_support_changes_reject_other_source_or_verify_edits(self):
        catalog = ".github/research/frontend-evolution-v1/sources.json"
        before = {"sources": [{"id": "webrtc", "status": "PLANNED"}, {"id": "other", "value": 1}]}
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(ci, "ROOT", Path(temp)), mock.patch.object(ci, "git", return_value=json.dumps(before)):
            path = Path(temp) / catalog
            path.parent.mkdir(parents=True)
            changed = json.loads(json.dumps(before))
            changed["sources"][0]["status"] = "EXECUTION_ADMITTED"
            path.write_text(json.dumps(changed))
            ci.support_changes([catalog], ci.BASELINE)
            changed["sources"][1]["value"] = 2
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "OTHER_SOURCE"):
                ci.support_changes([catalog], ci.BASELINE)
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(ci, "ROOT", Path(temp)), mock.patch.object(ci, "git", return_value="old verify\n"):
            path = Path(temp) / ci.VERIFY_WORKFLOW
            path.parent.mkdir(parents=True)
            path.write_text("old verify\n" + "".join(ci.VERIFY_COMMANDS))
            ci.support_changes([ci.VERIFY_WORKFLOW], ci.BASELINE)
            path.write_text("other verify changed\n" + "".join(ci.VERIFY_COMMANDS))
            with self.assertRaisesRegex(ValueError, "OTHER_VERIFY"):
                ci.support_changes([ci.VERIFY_WORKFLOW], ci.BASELINE)


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def response(self, data, url="https://example.invalid/fixed", length=None):
        response = io.BytesIO(data)
        response.geturl = lambda: url
        response.headers = {"Content-Length": str(len(data) if length is None else length)}
        return response

    def test_download_exact_bytes_only(self):
        data = b"synthetic transport fixture, not upstream source\n"
        spec = {"url": "https://example.invalid/fixed", "size": len(data), "sha256": ci.sha256(data)}
        with mock.patch.object(ci.urllib.request, "urlopen", return_value=self.response(data)):
            ci.download(spec, self.root / "archive", time.monotonic() + 5)
        self.assertEqual((self.root / "archive").read_bytes(), data)

    def test_download_wrong_hash_size_redirect_and_reuse_fail(self):
        data = b"tiny"
        base = {"url": "https://example.invalid/fixed", "size": len(data), "sha256": ci.sha256(data)}
        for index, (spec, response) in enumerate([
                (dict(base, sha256="0" * 64), self.response(data)),
                (dict(base, size=3), self.response(data, length=3)),
                (base, self.response(data, url="http://example.invalid/fixed")),
                (base, self.response(b"tin", length=4)),
                (base, self.response(data, length=500))]):
            with self.subTest(index=index), mock.patch.object(ci.urllib.request, "urlopen", return_value=response):
                with self.assertRaises(ValueError):
                    ci.download(spec, self.root / str(index), time.monotonic() + 5)
        existing = self.root / "exists"
        existing.write_bytes(b"preserve")
        with self.assertRaises(ValueError):
            ci.download(base, existing, time.monotonic() + 5)
        self.assertEqual(existing.read_bytes(), b"preserve")

    def test_budget_failure_launches_no_process(self):
        with mock.patch.object(ci.source, "run_logged") as launch:
            with self.assertRaisesRegex(ValueError, "budget"):
                ci.command(["must-not-run"], self.root / "log", {}, 0, 30)
            launch.assert_not_called()

    def test_external_includes_preserve_our_strict_flags(self):
        self.assertEqual(ci.system_includes(["-I/a", "-I", "/b", "-DWEBRTC_POSIX", "-pthread"]),
                         ["-isystem", "/a", "-isystem", "/b", "-DWEBRTC_POSIX", "-pthread"])
        with self.assertRaises(ValueError):
            ci.system_includes(["-I"])

    def test_ldd_parser_requires_resolved_unique_names(self):
        text = "linux-vdso.so.1 (0x123)\nlibwebrtc.so.1 => /tmp/libwebrtc.so.1 (0x456)\n/lib64/ld-linux-x86-64.so.2 (0x789)\n"
        self.assertEqual(ci.parse_libraries(text), {"libwebrtc.so.1": "/tmp/libwebrtc.so.1", "ld-linux-x86-64.so.2": "/lib64/ld-linux-x86-64.so.2"})
        for value in ("liba.so => not found", "statically linked", "liba.so => relative (0x0)",
                      "liba.so => /a (0x0)\nliba.so => /b (0x1)"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ci.parse_libraries(value)

    def test_research_library_copied_as_regular_soname_system_only_recorded(self):
        build, bundle = self.root / "build", self.root / "bundle"
        build.mkdir()
        (bundle / "bin").mkdir(parents=True)
        library = build / "libwebrtc-audio-processing-2.so.1.0"
        library.write_bytes(b"copy-only fixture; never an ELF or compiled result")
        digest = ci.sha256(library.read_bytes())
        identity = {"library_names": {"libwebrtc-audio-processing-2.so.1": str(library), "libc.so.6": "/usr/lib/libc.so.6"},
                    "libraries": {str(library): digest, "/usr/lib/libc.so.6": "1" * 64}}
        with mock.patch.object(ci, "runtime_identity", return_value=identity):
            hashes, system = ci.copy_research_libraries(bundle / "bin/fixture", build, bundle, {},
                                                       [{"path": str(library), "sha256": digest}])
        copied = bundle / "bin/lib/libwebrtc-audio-processing-2.so.1"
        self.assertFalse(copied.is_symlink())
        self.assertEqual(copied.read_bytes(), library.read_bytes())
        self.assertEqual(hashes, {"bin/lib/libwebrtc-audio-processing-2.so.1": digest})
        self.assertIn("libc.so.6", system)
        self.assertFalse((bundle / "bin/lib/libc.so.6").exists())

    def test_wrong_source_build_library_hash_rejected(self):
        library = self.root / "libwebrtc.so.1"
        library.write_bytes(b"tiny")
        with mock.patch.object(ci, "runtime_identity", return_value={"libraries": {str(library): "1" * 64}}):
            with self.assertRaisesRegex(ValueError, "source-build runtime"):
                ci.copy_research_libraries(library, self.root, self.root, {}, [{"path": str(library), "sha256": "0" * 64}])

    def test_absolute_rpath_rejected(self):
        for output, valid in ((b"(RUNPATH) Library runpath: [$ORIGIN/lib]\n", True),
                              (b"(RUNPATH) Library runpath: [/tmp/original/build]\n", False)):
            with mock.patch.object(ci.subprocess, "check_output", return_value=output):
                if valid:
                    ci.no_absolute_rpath(self.root / "fixture", {})
                else:
                    with self.assertRaisesRegex(ValueError, "absolute"):
                        ci.no_absolute_rpath(self.root / "fixture", {})

    def test_bundle_hashes_relative_regular_files_and_tar_preserves_execute_mode(self):
        bundle = self.root / "bundle"
        (bundle / "bin").mkdir(parents=True)
        executable = bundle / "bin/fixture"
        executable.write_bytes(b"archive mode fixture; never executed")
        executable.chmod(0o755)
        self.assertEqual(ci.manifest_files(bundle), {"bin/fixture": ci.sha256(executable.read_bytes())})
        (bundle / "bundle.json").write_text('{"fixture_only": true}\n')
        target = self.root / "fixture.tar.gz"
        self.assertEqual(ci.pack_bundle(bundle, target), ci.sha256(target.read_bytes()))
        with tarfile.open(target) as archive:
            self.assertEqual(archive.getmember("bin/fixture").mode & 0o777, 0o755)
            self.assertTrue(all(item.isfile() and not item.issym() for item in archive))

    def test_bundle_symlink_and_hardlink_rejected(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        original = self.root / "outside"
        original.write_bytes(b"tiny")
        linked = bundle / "link"
        linked.symlink_to(original)
        with self.assertRaises(ValueError):
            ci.manifest_files(bundle)
        linked.unlink()
        os.link(original, linked)
        with self.assertRaises(ValueError):
            ci.manifest_files(bundle)

    def test_local_build_refused_and_failure_prefix_not_pass(self):
        output = self.root / "run"
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(ci.source, "build") as build:
            with self.assertRaisesRegex(ValueError, "restricted to the Actions"):
                ci.run("0" * 40, output)
            build.assert_not_called()
        receipt = json.loads((output / "ci-receipt.json").read_text())
        self.assertEqual(receipt["status"], "FAIL")
        self.assertEqual(receipt["stages"], [])
        self.assertFalse((output / "bundle/bundle.json").exists())

    def test_late_packaging_failure_invalidates_provisional_manifest(self):
        bundle = self.root / "bundle"
        bundle.mkdir()
        manifest = bundle / "bundle.json"
        manifest.write_text('{"status":"PASS_ENGINEERING_ONLY","fixture_only":true}\n')
        archive = self.root / "webrtc-aec3-engineering-bundle.tar.gz"
        archive.write_bytes(b"provisional serialization fixture, not an actual bundle")
        (bundle / "retained-diagnostic").write_bytes(b"keep actual prefix")
        ci.invalidate_bundle(self.root)
        self.assertEqual(json.loads(manifest.read_text())["status"], "FAIL_BUNDLE_NOT_COMMITTED")
        self.assertFalse(archive.exists())
        self.assertTrue((bundle / "retained-diagnostic").is_file())


if __name__ == "__main__":
    unittest.main()
