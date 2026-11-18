#!/usr/bin/env python3
"""Synthetic metadata isolation regressions; never acoustic qualification."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import build_aec_research_corpus as builder


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.roots = builder._load_test_inventory()['roots']
        self.paths = {}
        bounds = {}
        for i, name in enumerate(self.roots):
            paths = [f'nested/held{i}_doubletalk_mic.wav', 'README.md']
            self.paths[name] = paths
            for relative in paths:
                p = self.root / 'datasets' / name / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
            bounds[name] = {'file_count': len(paths), 'paths_sha256': hashlib.sha256(
                ('\n'.join(sorted(paths)) + '\n').encode()).hexdigest()}
        self.mock = patch.object(builder, '_load_test_inventory', return_value={'roots': bounds})
        self.mock.start()
        self.addCleanup(self.mock.stop)
        train = self.root / builder.TRAIN_ROOT
        train.mkdir()
        for i, scenario in enumerate(builder.SCENARIOS):
            for j in range(2):
                for role in ('mic', 'lpb'):
                    with wave.open(str(train / f'train{i}{j}{builder.SUFFIXES[scenario]}_{role}.wav'), 'wb') as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
                        w.writeframes(b'\0\0' * 8000)

    def selection_file(self):
        p = self.root / 'selection.json'
        p.write_text(json.dumps(builder.select(self.root)))
        return p

    def assert_closed(self, selection):
        with self.assertRaises(ValueError):
            builder.select(self.root)
        with self.assertRaises(ValueError):
            builder.build(selection, self.root, self.root / 'output')
        self.assertFalse((self.root / 'output').exists())

    def test_full_inventory_select_and_build_bind_trusted_digest(self):
        selection = self.selection_file()
        self.assertEqual(len(builder.excluded_test_ids(self.root)), 7)
        result = builder.build(selection, self.root, self.root / 'output')
        self.assertEqual(result['cases'], 8)
        manifest = json.loads(Path(result['manifest']).read_text())
        self.assertEqual(manifest['test_inventory_sha256'], builder.TEST_INVENTORY_SHA256)

    def test_empty_all_test_roots_fail_select_and_build(self):
        selection = self.selection_file()
        for p in (self.root / 'datasets').glob('*test_set*/**/*'):
            if p.is_file(): p.unlink()
        self.assert_closed(selection)

    def test_missing_root_fails(self):
        selection = self.selection_file()
        import shutil
        shutil.rmtree(self.root / 'datasets' / next(iter(self.roots)))
        self.assert_closed(selection)

    def test_partial_mic_inventory_fails(self):
        selection = self.selection_file()
        name = next(iter(self.roots))
        (self.root / 'datasets' / name / self.paths[name][0]).unlink()
        self.assert_closed(selection)

    def test_missing_non_mic_file_also_fails(self):
        selection = self.selection_file()
        (self.root / 'datasets' / next(iter(self.roots)) / 'README.md').unlink()
        self.assert_closed(selection)

    def test_same_count_renamed_identity_fails(self):
        selection = self.selection_file()
        name = next(iter(self.roots))
        p = self.root / 'datasets' / name / self.paths[name][0]
        p.rename(p.with_name('substituted_doubletalk_mic.wav'))
        self.assert_closed(selection)

    def test_extra_file_fails(self):
        selection = self.selection_file()
        (self.root / 'datasets' / next(iter(self.roots)) / 'extra').touch()
        self.assert_closed(selection)

    def test_extra_test_root_fails(self):
        selection = self.selection_file()
        (self.root / 'datasets/extra_test_set').mkdir()
        self.assert_closed(selection)

    def test_symlink_fails_even_with_expected_name(self):
        selection = self.selection_file()
        p = self.root / 'datasets' / next(iter(self.roots)) / 'README.md'
        p.unlink(); target = self.root / 'other'; target.touch(); p.symlink_to(target)
        self.assert_closed(selection)

    def test_old_or_forged_selection_binding_fails(self):
        p = self.selection_file()
        original = json.loads(p.read_text())
        for digest in (None, '0' * 64):
            value = dict(original); value['test_inventory_sha256'] = digest
            p.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                builder.build(p, self.root, self.root / 'output')
        self.assertFalse((self.root / 'output').exists())


class TrustedLockTests(unittest.TestCase):
    def test_committed_lock_is_pinned_to_revision_and_seven_roots(self):
        lock = builder._load_test_inventory()
        self.assertEqual(lock['source_revision'], builder.SOURCE_REVISION)
        self.assertEqual(len(lock['roots']), 7)
        self.assertEqual(sum(r['file_count'] for r in lock['roots'].values()), 12387)

    def test_modified_lock_rejected(self):
        with patch.object(builder, 'sha256', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                builder._load_test_inventory()


if __name__ == '__main__':
    unittest.main(verbosity=2)
