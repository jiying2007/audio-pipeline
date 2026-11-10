#!/usr/bin/env python3
"""Real disposable Git/source fixtures; no codec, model or measurement claims."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import dualmic_source_identity as admission


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dualmic-source-identity-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.version = (admission.ROOT / "CMakeLists.txt").read_text().splitlines()[1].split()[2]
        expected = admission.registered_sources(self.version,
                                               lambda p: (admission.ROOT / p).read_bytes())
        for name in (*admission.BOUND_SOURCES, *expected):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(admission.ROOT / name, path)
        self.git("init", "-q")
        self.commit()

    def git(self, *args, input=None):
        return subprocess.run(["git", *args], cwd=self.root, input=input,
                              check=True, capture_output=True, timeout=30).stdout

    def commit(self):
        self.git("add", ".")
        self.git("-c", "user.name=Source identity fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-qm", "Source fixture")
        self.revision = self.git("rev-parse", "HEAD").decode().strip()

    def migrate_fixture(self, version):
        if self.version == version:
            return
        for current, reverse in ((self.version, True), (version, False)):
            plan_path = admission.PROFILES[current][0]
            plan = json.loads((admission.ROOT / plan_path).read_bytes())
            patch = base64.b64decode((admission.ROOT / plan["source_delta"]["path"]).read_bytes())
            self.assertEqual(admission.digest(patch), plan["source_delta"]["sha256"])
            self.git("apply", *(('--reverse',) if reverse else ()), "--unidiff-zero", "-", input=patch)
        self.version = version
        self.commit()

    def reject(self, version=None, revision=None, reason=None):
        with self.assertRaisesRegex(admission.Rejected, reason or "."):
            admission.verify_build(version or self.version, revision or self.revision, root=self.root)

    def test_both_reviewed_versions_require_their_own_exact_source(self):
        for version in ("2.3.63", "2.3.64"):
            self.migrate_fixture(version)
            result = admission.verify_build(version, self.revision, root=self.root)
            self.assertEqual(result["public_source_members"], 56)
            self.assertFalse(result["historical_result_inherited"])
            self.reject("2.3.64" if version == "2.3.63" else "2.3.63")

    def test_unknown_or_missing_version_rejected(self):
        for version in ("2.3.62", "2.3.65", "3.0.0", "2.3.64-rc", None, True):
            with self.subTest(version=version), self.assertRaisesRegex(admission.Rejected, "unregistered"):
                admission.verify_build(version, self.revision, root=self.root)

    def test_wrong_or_dirty_revision_rejected(self):
        for revision in ("0" * 40, self.revision + "-dirty", "HEAD", self.revision[:12]):
            self.reject(revision=revision)

    def test_old_r8_terminal_lf_is_not_r9_source(self):
        self.migrate_fixture("2.3.64")
        path = self.root / "src/frontend/ap_beamformer.c"
        path.write_bytes(path.read_bytes() + b"\n")
        self.reject(reason="uncommitted source")
        self.commit()
        self.reject(reason="unreviewed public source")

    def test_unreviewed_unchanged_dsp_rejected_even_when_committed(self):
        path = self.root / "src/enhance/ap_ns.c"
        path.write_bytes(path.read_bytes() + b"\n")
        self.reject(reason="uncommitted source")
        self.commit()
        self.reject(reason="unreviewed public source")

    def test_version_only_substitution_does_not_admit_source(self):
        other = "2.3.63" if self.version == "2.3.64" else "2.3.64"
        path = self.root / "CMakeLists.txt"
        path.write_text(path.read_text().replace("VERSION " + self.version, "VERSION " + other, 1))
        self.commit()
        self.reject(version=other, reason="unreviewed public source")

    def test_registration_and_original_lock_are_hash_bound(self):
        for name in (admission.LOCK, admission.PROFILES[self.version][0]):
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            self.reject(reason="changed")
            path.write_bytes(original)

    def test_untracked_public_source_or_header_rejected(self):
        for name in ("src/untracked.c", "include/untracked.h"):
            path = self.root / name
            path.write_text("/* untracked build input */\n")
            self.reject(reason="working public source membership changed")
            path.unlink()

    def test_added_or_missing_public_source_rejected(self):
        path = self.root / "src/unreviewed.c"
        path.write_text("/* unreviewed source fixture */\n")
        self.commit()
        self.reject(reason="membership changed")
        path.unlink()
        (self.root / "src/enhance/ap_ns.c").unlink()
        self.commit()
        self.reject(reason="membership changed")

    def test_uncommitted_adapter_and_symlink_rejected(self):
        path = self.root / admission.BOUND_SOURCES[0]
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        self.reject(reason="uncommitted source")
        path.write_bytes(original)
        target = self.root / "src/enhance/ap_ns.c"
        saved = self.root / "saved-ns.c"
        saved.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(saved)
        self.reject(reason="unsafe public source path")


if __name__ == "__main__":
    unittest.main()
