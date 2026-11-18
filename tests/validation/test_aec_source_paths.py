#!/usr/bin/env python3
"""Synthetic source-path checks; no source split or acoustic qualification."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('aec_builder', ROOT / 'validation/tools/build_aec_research_corpus.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SourcePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.expected = []
        for scenario in builder.SCENARIOS:
            directory = builder.ROOTS['aec-doubletalk' if 'doubletalk' in scenario else 'aec-farend-singletalk']
            suffix = '_with-movement' if scenario.endswith('moving') else ''
            for index in range(2):
                paths = {}
                for role, key in [('mic', 'mic'), ('lpb', 'render')]:
                    relative = f'{directory}/id{index}{suffix}_{role}.wav'
                    path = self.root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with wave.open(str(path), 'wb') as audio:
                        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
                        audio.writeframes(b'\0\0' * 8000)
                    paths[key] = relative
                self.expected.append({'id': f'{scenario}-{index}', 'scenario': scenario,
                    **paths, 'movement': scenario.endswith('moving'), 'doubletalk': 'doubletalk' in scenario})
        self.selection = self.root / 'selection.json'
        self.selection.write_text(json.dumps({'schema_version': 1,
            'source_revision': builder.SOURCE_REVISION, 'cases': self.expected}))

    def reject_build(self, value):
        self.selection.write_text(json.dumps(value))
        with patch.object(builder, 'inspect_wav') as inspect:
            with self.assertRaises(ValueError):
                builder.build(self.selection, self.root, self.root / 'output')
            inspect.assert_not_called()
        self.assertFalse((self.root / 'output').exists())

    def test_existing_selection_and_eight_case_build_unchanged(self):
        selected = builder.select(self.root)
        self.assertEqual(selected, json.loads(self.selection.read_text()))
        result = builder.build(self.selection, self.root, self.root / 'output')
        self.assertEqual(result['cases'], 8)
        corpus = json.loads(Path(result['corpus']).read_text())
        self.assertEqual([c['case_id'] for c in corpus['cases']], [c['id'] for c in self.expected])
        for case in corpus['cases']:
            self.assertEqual(case['expected'], {'max_output_clip_fraction': .02,
                'max_output_dc_offset_dbfs': -20., 'max_output_rms_delta_db': 6.})

    def test_noncanonical_and_outside_source_paths_rejected(self):
        original = json.loads(self.selection.read_text())
        for role in ('mic', 'render'):
            for bad in ('../outside.wav', '/tmp/outside.wav', 'datasets/other.wav',
                        original['cases'][0][role].replace('/', '//', 1),
                        original['cases'][0][role].replace('/', '/./', 1),
                        'datasets\\outside.wav', None, 'bad\0path'):
                with self.subTest(role=role, path=repr(bad)):
                    value = json.loads(json.dumps(original)); value['cases'][0][role] = bad
                    self.reject_build(value)

    def test_source_file_symlink_rejected_in_select_and_build(self):
        original = json.loads(self.selection.read_text())
        for role in ('mic', 'render'):
            path = self.root / original['cases'][0][role]; saved = path.read_bytes()
            target = self.root / ('external-' + role + '.wav'); target.write_bytes(saved)
            path.unlink(); path.symlink_to(target)
            with self.assertRaises(ValueError): builder.select(self.root)
            self.reject_build(original)
            path.unlink(); path.write_bytes(saved)

    def test_directory_symlink_rejected_in_select_and_build(self):
        original = json.loads(self.selection.read_text())
        for relative in ('datasets', 'datasets/test_set_icassp2022', builder.ROOTS['aec-doubletalk']):
            path = self.root / relative; target = self.root / 'external-directory'
            path.rename(target); path.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError): builder.select(self.root)
            self.reject_build(original)
            path.unlink(); target.rename(path)

    def test_output_case_id_cannot_escape(self):
        original = json.loads(self.selection.read_text())
        for bad in ('../escape', '/tmp/escape', '.', '..', 'a/b', 'a\\b', 'bad\nname', '', None):
            with self.subTest(identity=repr(bad)):
                value = json.loads(json.dumps(original)); value['cases'][0]['id'] = bad
                self.reject_build(value)

    def test_late_invalid_path_precedes_all_audio_reads(self):
        value = json.loads(self.selection.read_text()); value['cases'][-1]['render'] = '../late.wav'
        self.reject_build(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
