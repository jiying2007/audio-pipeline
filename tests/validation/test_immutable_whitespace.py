"""Real Git positive/negative tests for protected-base immutable imports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("immutable_whitespace", ROOT / "tools/codex_assets/immutable_whitespace.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ImmutableWhitespaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.put("ordinary.txt", b"clean\n")
        self.commit()
        self.initial = self.sha()
        self.raw = b"original \n"
        self.put("archive.txt", self.raw)
        self.commit()
        diagnostic = module.diff_check(self.root, self.initial + "...HEAD").stdout
        self.policy = {"schema_version": 1, "scope": "immutable-historical-import-only", "files": {
            "archive.txt": {"sha256": hashlib.sha256(self.raw).hexdigest(), "mode": "100644",
                            "diagnostics_sha256": hashlib.sha256(diagnostic).hexdigest(), "warnings": 1}}}
        self.git("checkout", "-qb", "policy", self.initial)
        self.put(module.POLICY, json.dumps(self.policy).encode() + b"\n")
        self.put(module.HELPER, (ROOT / module.HELPER).read_bytes())
        self.commit()
        self.base = self.sha()
        self.put("archive.txt", self.raw)
        self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE)

    def sha(self):
        return self.git("rev-parse", "HEAD").decode().strip()

    def put(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")

    def check(self, base=None):
        return module.check(self.root, base or self.base, "HEAD")

    def reject(self):
        with self.assertRaises(ValueError):
            self.check()

    def test_strict_policy_pr_passes_without_using_itself(self):
        self.assertEqual(module.check(self.root, self.initial, self.base)["status"], "STRICT_PASS")

    def test_registered_exact_import(self):
        result = self.check()
        self.assertEqual((result["status"], result["exceptions"], result["warnings"]), ("IMMUTABLE_IMPORT_VERIFIED", 1, 1))

    def test_unregistered_path(self):
        self.put("unknown.txt", b"new \n")
        self.commit()
        self.reject()

    def test_same_path_changed_blob(self):
        self.put("archive.txt", b"different \n")
        self.commit()
        self.reject()

    def test_added_whitespace(self):
        self.put("archive.txt", self.raw + b" \n")
        self.commit()
        self.reject()

    def test_conflict_marker(self):
        self.put("ordinary.txt", b"<<<<<<< HEAD\nproblem\n=======\nother\n>>>>>>> topic\n")
        self.commit()
        self.reject()

    def test_head_policy_cannot_self_authorize(self):
        self.policy["files"]["archive.txt"]["warnings"] = 2
        self.put(module.POLICY, json.dumps(self.policy).encode())
        self.commit()
        self.reject()

    def test_head_checker_cannot_self_authorize(self):
        self.put(module.HELPER, b"# replacement\n")
        self.commit()
        self.reject()

    def test_no_base_registration(self):
        with self.assertRaises(ValueError):
            self.check(self.initial)

    def test_file_mode(self):
        self.git("update-index", "--chmod=+x", "archive.txt")
        self.git("commit", "-qm", "mode")
        self.reject()

    def test_registered_executable_mode(self):
        self.git("checkout", "-qb", "executable-base", self.base)
        self.policy["files"]["archive.txt"]["mode"] = "100755"
        self.put(module.POLICY, json.dumps(self.policy).encode())
        self.commit()
        base = self.sha()
        self.put("archive.txt", self.raw)
        (self.root / "archive.txt").chmod(0o755)
        self.commit()
        self.assertEqual(self.check(base)["exceptions"], 1)

    def test_symlink(self):
        path = self.root / "archive.txt"
        path.unlink()
        # Preserve a whitespace diagnostic so this exercises the exception
        # branch; clean strict diffs intentionally need no exception authority.
        path.symlink_to("ordinary.txt ")
        self.commit()
        self.reject()

    def test_renamed_path(self):
        self.git("mv", "archive.txt", "moved.txt")
        self.git("commit", "-qm", "rename")
        self.reject()

    def test_worktree_does_not_grant_authority(self):
        self.put(module.POLICY, b"not a policy")
        self.put("archive.txt", b"not the committed blob")
        self.assertEqual(self.check()["exceptions"], 1)

    def test_unexpected_git_exit(self):
        proc = subprocess.CompletedProcess([], 128, b"", b"failed")
        with patch.object(module.subprocess, "run", return_value=proc), self.assertRaises(ValueError):
            module.diff_check(self.root, "anything")

    def test_unexpected_git_output(self):
        proc = subprocess.CompletedProcess([], 0, b"surprise", b"")
        with patch.object(module.subprocess, "run", return_value=proc), self.assertRaises(ValueError):
            module.diff_check(self.root, "anything")

    def test_policy_rejects_duplicate_keys(self):
        with self.assertRaises(ValueError):
            module.records(b'{"schema_version":1,"schema_version":1}')

    def test_policy_rejects_traversal(self):
        self.policy["files"]["../outside"] = self.policy["files"].pop("archive.txt")
        with self.assertRaises(ValueError):
            module.records(json.dumps(self.policy).encode())

    def test_diagnostic_mismatch(self):
        self.git("checkout", "-qb", "diagnostic-base", self.base)
        self.policy["files"]["archive.txt"]["diagnostics_sha256"] = "0" * 64
        self.put(module.POLICY, json.dumps(self.policy).encode())
        self.commit()
        base = self.sha()
        self.put("archive.txt", self.raw)
        self.commit()
        with self.assertRaises(ValueError):
            self.check(base)

    def test_worktree_attributes_cannot_suppress(self):
        self.put(".gitattributes", b"* -whitespace -diff\n")
        self.assertEqual(self.check()["exceptions"], 1)

    def test_committed_attributes_cannot_suppress_unknown(self):
        self.put(".gitattributes", b"* -whitespace -diff\n")
        self.put("unknown.txt", b"new \n")
        self.commit()
        self.reject()

    def test_global_attributes_cannot_suppress(self):
        attr = self.root / "global-attributes"
        self.put("global-attributes", b"* -whitespace -diff\n")
        self.git("config", "core.attributesFile", str(attr))
        self.assertEqual(self.check()["exceptions"], 1)

    def test_info_attributes_cannot_suppress(self):
        self.put(".git/info/attributes", b"* -whitespace -diff\n")
        self.assertEqual(self.check()["exceptions"], 1)

    def test_incoming_rename(self):
        self.git("checkout", "-qb", "rename-base", self.base)
        self.put("original.txt", self.raw)
        self.commit()
        base = self.sha()
        self.git("mv", "original.txt", "archive.txt")
        self.commit()
        with self.assertRaises(ValueError):
            self.check(base)


if __name__ == "__main__":
    unittest.main()
