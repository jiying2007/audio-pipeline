#!/usr/bin/env python3
"""Fail-closed ZIP-source tests: no external acquisition and no DSP execution."""
from pathlib import Path
import stat
import tempfile
import time
import unittest
import warnings
import zipfile

from dualmic_stages_source import digest, validate_extract


class SourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def archive(self, names):
        path = self.root / 'source.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w') as archive:
                for name in names:
                    archive.writestr(name, b'locked-source')
        return path, dict(zip_bytes=path.stat().st_size, sha256=digest(path), members=len(names))

    def extract(self, path, spec, **bounds):
        return validate_extract(path, self.root / 'target', spec,
                                dict(max_members=8, max_uncompressed_bytes=100, **bounds), time.monotonic(), 3)

    def test_valid_member_bytes_and_hash(self):
        path, spec = self.archive(['source/input.pcm'])
        result = self.extract(path, spec)
        actual = self.root / 'target/source/input.pcm'
        self.assertEqual(actual.read_bytes(), b'locked-source')
        self.assertEqual(result['member_hashes'], {'source/input.pcm': digest(actual)})

    def test_locked_hash_rejects_tamper_before_extract(self):
        path, spec = self.archive(['a'])
        spec['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash/size'):
            self.extract(path, spec)
        self.assertFalse((self.root / 'target').exists())

    def test_duplicate_and_escape_rejected(self):
        for names in (['a', 'a'], ['../escape'], ['/absolute'], ['a\\escape'], ['C:escape']):
            with self.subTest(names=names):
                path, spec = self.archive(names)
                with self.assertRaisesRegex(ValueError, 'unsafe/duplicate'):
                    self.extract(path, spec)
                self.assertFalse((self.root / 'target').exists())

    def test_symlink_and_special_file_rejected(self):
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o644):
            with self.subTest(mode=mode):
                info = zipfile.ZipInfo('source')
                info.create_system = 3
                info.external_attr = mode << 16
                path, spec = self.archive([info])
                with self.assertRaises(ValueError):
                    self.extract(path, spec)
                self.assertFalse((self.root / 'target').exists())

    def test_existing_destination_never_overwritten(self):
        path, spec = self.archive(['a'])
        target = self.root / 'target'
        target.mkdir()
        (target / 'keep').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'new extraction'):
            self.extract(path, spec)
        self.assertEqual((target / 'keep').read_bytes(), b'keep')

    def test_member_and_size_bounds(self):
        path, spec = self.archive(['a'])
        spec['members'] = 2
        with self.assertRaisesRegex(ValueError, 'member count'):
            self.extract(path, spec)
        spec['members'] = 1
        with self.assertRaisesRegex(ValueError, 'uncompressed byte'):
            validate_extract(path, self.root / 'target', spec,
                             dict(max_members=8, max_uncompressed_bytes=1), time.monotonic(), 3)
        self.assertFalse((self.root / 'target').exists())

    def test_expired_stage_cannot_pass(self):
        path, spec = self.archive(['a'])
        with self.assertRaisesRegex(ValueError, 'SOURCE_BUDGET_EXCEEDED'):
            validate_extract(path, self.root / 'target', spec,
                             dict(max_members=8, max_uncompressed_bytes=100), time.monotonic() - 4, 3)


if __name__ == '__main__':
    unittest.main()
