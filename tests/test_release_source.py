#!/usr/bin/env python3
"""Exercise the release source preflight against real temporary Git states."""
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify-release-source.sh"


class ReleaseSourceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Release source test")
        self.git("config", "user.email", "release-source-test@example.invalid")
        (self.root / "source.c").write_text("/* tracked fixture */\n")
        self.git("add", "source.c")
        self.git("commit", "-qm", "test source")
        self.revision = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True).strip()

    def preflight(self, revision=None):
        return subprocess.run(
            ["sh", str(SCRIPT), self.revision if revision is None else revision],
            cwd=self.root, text=True, capture_output=True)

    def test_clean_checkout(self):
        self.assertEqual(self.preflight().returncode, 0)

    def test_untracked_delivery_evidence_is_not_a_source_edit(self):
        evidence = self.root / "verified-delivery"
        evidence.mkdir()
        (evidence / "fixture.txt").write_text("unit fixture, not delivery evidence\n")
        self.assertEqual(self.preflight().returncode, 0)

    def test_unstaged_source_edit_rejected(self):
        (self.root / "source.c").write_text("/* modified */\n")
        result = self.preflight()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tracked source has local changes", result.stderr)

    def test_staged_source_edit_rejected(self):
        (self.root / "source.c").write_text("/* modified */\n")
        self.git("add", "source.c")
        self.assertNotEqual(self.preflight().returncode, 0)

    def test_staged_edit_cancelled_in_worktree_still_rejected(self):
        (self.root / "source.c").write_text("/* staged modification */\n")
        self.git("add", "source.c")
        (self.root / "source.c").write_text("/* tracked fixture */\n")
        self.assertNotEqual(self.preflight().returncode, 0)

    def test_wrong_revision_rejected(self):
        self.assertNotEqual(self.preflight("0" * 40).returncode, 0)

    def test_abbreviated_or_malformed_revision_rejected(self):
        for revision in (self.revision[:12], self.revision + "-dirty", "g" * 40, ""):
            with self.subTest(revision=revision):
                self.assertNotEqual(self.preflight(revision).returncode, 0)


if __name__ == "__main__":
    unittest.main()
