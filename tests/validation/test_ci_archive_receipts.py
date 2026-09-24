#!/usr/bin/env python3
"""Real Git metadata fixtures for append-only research receipt versioning."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ci_impact_receipt_test', ROOT / 'scripts/ci_impact.py')
ci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci)
ARCHIVE = 'validation/research/evidence/i015-35994848668/'
MANIFEST = '.github/program/i015-finalization.json'
MEMBERS = {name: ('metadata fixture: ' + name + '\n').encode() for name in (
    'SHA256SUMS', 'build-info.txt', 'compiler.txt', 'contract.json', 'corpora.txt',
    'diagnostic-infra-revision.txt', 'probe.sha256', 'result.json',
    'source-base-revision.txt', 'summary.json',
)}


@contextmanager
def repository():
    original = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(original)


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, text=True).strip()


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def commit(message):
    git('add', '-A')
    git('commit', '-qm', message, '--allow-empty')
    return git('rev-parse', 'HEAD')


class ReceiptVersionTests(unittest.TestCase):
    def setUp(self):
        self.repo = repository()
        self.repo.__enter__()
        self.addCleanup(self.repo.__exit__, None, None, None)
        git('init', '-q')
        git('config', 'user.name', 'offline-test')
        git('config', 'user.email', 'offline-test@example.invalid')
        put('CMakeLists.txt', b'project(audio_pipeline VERSION 2.3.49)\n')
        put('CHANGELOG.md', b'# 2.3.49\n')
        self.frozen = {'run_id': 35994848668, 'archive_root': ARCHIVE[:-1],
                       'member_sha256': {name: hashlib.sha256(data).hexdigest()
                                         for name, data in MEMBERS.items()}}
        put(MANIFEST, (json.dumps(self.frozen) + '\n').encode())
        self.base = commit('trusted registration')
        for name, data in MEMBERS.items():
            put(ARCHIVE + name, data)
        self.head = commit('receipt metadata only')
        self.paths = [ARCHIVE + name for name in MEMBERS]

    def check(self, base=None, head=None, paths=None):
        ci.enforce_release_version(base or self.base, head or self.head,
                                   paths if paths is not None else self.paths)

    def test_complete_byte_exact_receipts_keep_version(self):
        self.assertEqual(ci.verified_archive_paths(self.base, self.head, self.paths), set(self.paths))
        self.check()

    def test_names_alone_are_not_release_neutral(self):
        self.assertTrue(all(not ci.is_release_neutral(path) for path in self.paths))

    def test_tampered_bytes_rejected(self):
        put(ARCHIVE + 'result.json', b'tampered\n')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.check(head=commit('tamper'))

    def test_same_pr_manifest_cannot_approve_tamper(self):
        put(ARCHIVE + 'result.json', b'tampered\n')
        self.frozen['member_sha256']['result.json'] = hashlib.sha256(b'tampered\n').hexdigest()
        put(MANIFEST, json.dumps(self.frozen).encode())
        with self.assertRaisesRegex(ValueError, 'registration changed'):
            self.check(head=commit('self-approval'), paths=self.paths + [MANIFEST])

    def test_head_only_registration_is_not_trusted(self):
        git('checkout', '-q', self.base)
        Path(MANIFEST).unlink()
        no_registration = commit('base without registration')
        with self.assertRaisesRegex(ValueError, 'advance SemVer'):
            self.check(base=no_registration)

    def test_partial_archive_requires_version(self):
        with self.assertRaisesRegex(ValueError, 'advance SemVer'):
            self.check(paths=self.paths[:-1])

    def test_missing_member_rejected(self):
        Path(ARCHIVE + 'compiler.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'regular text file'):
            self.check(head=commit('missing'))

    def test_existing_archive_is_not_append_only(self):
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.check(base=self.head)

    def test_executable_receipt_rejected(self):
        Path(ARCHIVE + 'result.json').chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'regular text file'):
            self.check(head=commit('executable'))

    def test_symlink_receipt_rejected(self):
        path = Path(ARCHIVE + 'result.json')
        path.unlink()
        path.symlink_to('summary.json')
        with self.assertRaisesRegex(ValueError, 'regular text file'):
            self.check(head=commit('symlink'))

    def test_unknown_and_nested_paths_are_not_exempt(self):
        for name in ('validator.py', 'run.sh', 'probe.c', 'probe', 'policy.json',
                     'corpus.json', 'nested/result.json', '../result.json'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'advance SemVer'):
                self.check(paths=self.paths + [ARCHIVE + name])
        with self.assertRaisesRegex(ValueError, 'advance SemVer'):
            self.check(paths=self.paths + ['validation/research/evidence/other/result.json'])

    def test_mixed_product_paths_still_require_version(self):
        for path in ('src/core/ap_pipeline.c', 'include/audio_pipeline/audio_pipeline.h',
                     'validation/authority.json', 'validation/tools/run_validation.py',
                     'validation/policies/validation-smoke.json'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'advance SemVer'):
                self.check(paths=self.paths + [path])

    def test_archive_does_not_reduce_ci(self):
        paths = self.paths + ['.github/research/continuous-optimization/development-v4/'
                             'i015-vad-upstream-consumption-decomposition-v1-result.json',
                             'docs/program/I015-FINALIZATION.md']
        self.check(paths=paths)
        self.assertTrue(ci.analyze(paths)['full'])
        self.assertTrue(ci.analyze(paths)['run_tuning'])
        self.assertTrue(ci.analyze(paths, True)['full'])

    def test_deletion_is_not_a_new_receipt(self):
        Path(ARCHIVE + 'result.json').unlink()
        with self.assertRaisesRegex(ValueError, 'advance SemVer'):
            self.check(base=self.head, head=commit('deleted'), paths=[ARCHIVE + 'result.json'])


if __name__ == '__main__':
    unittest.main()
