#!/usr/bin/env python3
"""Retirement and archive replay controls; no live GitHub/model/device calls."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "archived_governance", ROOT / "scripts/run_archived_governance_tests.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class ArchiveBoundary(unittest.TestCase):
    def test_no_retired_entry_can_run_from_current_tree(self):
        manifest = M.load_manifest(ROOT)
        for name in manifest["retired_paths"]:
            with self.subTest(path=name):
                self.assertFalse((ROOT / name).exists())
        self.assertTrue((ROOT / "scripts/research_github_governance.py").is_file())
        self.assertTrue((ROOT / ".github/workflows/research-dechorate-ground-truth-diagnostic-v1.yml").is_file())

    def test_gate_uses_only_fixed_replay_for_retired_tests(self):
        gate = (ROOT / ".github/scripts/verify-docs-gate.sh").read_text()
        self.assertEqual(gate.count("python3 scripts/run_archived_governance_tests.py"), 1)
        for name, _, _ in M.TESTS:
            self.assertNotIn("python3 " + name, gate)
        source = (ROOT / "scripts/run_archived_governance_tests.py").read_text()
        self.assertNotIn('"fetch"', source)
        self.assertNotIn("urllib.request", source)
        self.assertNotIn("requests.get", source)

    def test_all_original_test_modes_still_run(self):
        self.assertEqual(sum(len(modes) for _, modes, _ in M.TESTS), 8)
        self.assertEqual(len(M.TESTS), 4)
        self.assertEqual(M.TESTS[0][1], ("", "-O", "-OO"))
        self.assertEqual(M.TESTS[3][1], ("", "-O", "-OO"))
        self.assertEqual(M.TESTS[1][2], ("--self-test",))
        for name, _, _ in M.TESTS:
            self.assertTrue(Path(name).name.startswith("test_"))

    def test_credential_context_and_injection_environment_is_not_inherited(self):
        forbidden = ("GH_TOKEN", "GITHUB_TOKEN", "REPOSITORY_METADATA_TOKEN",
                     "REPOSITORY_GOVERNANCE_TOKEN", "GITHUB_EVENT_PATH", "GH_CONFIG_DIR",
                     "GITHUB_RUN_ID", "PYTHONPATH", "PYTHONHOME", "HTTP_PROXY", "HTTPS_PROXY",
                     "SSH_AUTH_SOCK", "GIT_CONFIG_COUNT", "GIT_SSH_COMMAND", "GIT_DIR")
        with mock.patch.dict(os.environ, {name: "SENTINEL" for name in forbidden}):
            env = M.clean_environment(Path("/tmp/offline-home"))
        self.assertFalse(set(forbidden) & set(env))
        self.assertNotIn("SENTINEL", json.dumps(env))
        self.assertEqual(env["GIT_ALLOW_PROTOCOL"], "file")
        self.assertEqual(env["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(env["HOME"], "/tmp/offline-home")

    def test_missing_history_cannot_become_success_or_fetch(self):
        with mock.patch.object(M, "git", side_effect=subprocess.CalledProcessError(128, ["git"])) as git:
            with self.assertRaises(subprocess.CalledProcessError):
                M.replay(ROOT)
        self.assertEqual(git.call_count, 1)
        self.assertEqual(git.call_args.args[-3:], ("rev-parse", "--verify", M.COMMIT + "^{tree}"))

    def test_wrong_tree_stops_before_checkout_or_test(self):
        with mock.patch.object(M, "git", return_value="0" * 40) as git:
            with self.assertRaises(ValueError):
                M.replay(ROOT)
        self.assertEqual(git.call_count, 1)

    def test_no_live_or_revision_cli_override(self):
        for args in (("--revision", "HEAD"), ("--live",), ("--repository", "example/other")):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/run_archived_governance_tests.py"), *args],
                                    capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)

    def test_manifest_identity_roster_paths_and_hashes_are_checked(self):
        original = M.load_manifest(ROOT)
        variants = []
        for key in ("historical_commit", "historical_tree"):
            changed = copy.deepcopy(original); changed[key] = "0" * 40; variants.append(changed)
        for name in original["retired_paths"]:
            changed = copy.deepcopy(original); del changed["retired_paths"][name]; variants.append(changed)
        for name in ("../outside.py", "/outside.py", "scripts/../outside.py"):
            changed = copy.deepcopy(original)
            digest = changed["retired_paths"].pop(".github/program/dechorate_governance_v2.json")
            changed["retired_paths"][name] = digest; variants.append(changed)
        changed = copy.deepcopy(original); changed["retired_paths"]["scripts/github_governance.py"] = "0" * 64; variants.append(changed)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = root / M.MANIFEST; path.parent.mkdir(parents=True)
            for index, value in enumerate(variants):
                with self.subTest(index=index):
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        M.load_manifest(root)

    def test_each_historical_member_missing_mutated_or_symlinked_is_rejected(self):
        # Invented content verifies the staging primitive, not old protocol bytes.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = {"retired_paths": {}}
            for index in range(3):
                name = "source-%d.py" % index
                data = ("# synthetic fixture %d\n" % index).encode()
                (root / name).write_bytes(data)
                manifest["retired_paths"][name] = hashlib.sha256(data).hexdigest()
            M.verify_archive(root, manifest)
            for name in manifest["retired_paths"]:
                path = root / name; before = path.read_bytes()
                for kind in ("missing", "changed", "symlink"):
                    path.unlink()
                    if kind == "changed": path.write_bytes(before + b"\n")
                    if kind == "symlink": path.symlink_to(root / "outside")
                    with self.assertRaises(ValueError): M.verify_archive(root, manifest)
                    if path.is_symlink() or path.exists(): path.unlink()
                    path.write_bytes(before)

    def test_subprocess_failure_and_expired_deadline_are_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); env = M.clean_environment(root)
            with self.assertRaises(subprocess.CalledProcessError):
                M.run([sys.executable, "-c", "raise SystemExit(7)"], root, env, time.monotonic()+10, True)
            with mock.patch.object(M.subprocess, "Popen") as process:
                with self.assertRaises(TimeoutError):
                    M.run([sys.executable, "-c", "pass"], root, env, time.monotonic()-1)
                process.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
