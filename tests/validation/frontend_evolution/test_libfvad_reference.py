#!/usr/bin/env python3
"""Offline adapter/evidence negatives; actual upstream execution is a CI step."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import shutil
import sys
import unittest
from unittest.mock import patch

import libfvad_reference as ref
from contracts import ROOT, load_json, sha256


def metric(recall=0.8, fpr=0.2):
    return {'positive_frames': 10, 'negative_frames': 10, 'recall': recall, 'false_positive_rate': fpr}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        (self.source / 'src').mkdir(parents=True)
        (self.source / 'include').mkdir()
        (self.source / 'src/core.c').write_bytes(b'int x;\n')
        (self.source / 'LICENSE').write_bytes(b'unit fixture, not upstream\n')
        self.lock = self.root / 'lock.json'
        ref.write_json(self.lock, {'upstream_commit': '532ab666c20d3cfda38bca63abbb0f152706c369',
            'git_blob_sha1': {n: ref.git_blob((self.source / n).read_bytes()) for n in ('src/core.c', 'LICENSE')},
            'scope': 'unit-fixture-not-executed', 'rights_review': {}})

    def run_preflight(self):
        with patch.object(ref, 'LOCK', self.lock):
            return ref.source_preflight(self.source, self.root / 'out')

    def test_source_copy_and_manifest(self):
        result = self.run_preflight()
        self.assertEqual(result['status'], 'SOURCE_BYTES_VERIFIED_NOT_EXECUTED')
        self.assertEqual(len(result['files_sha256']), 2)
        self.assertEqual((self.root / 'out/upstream/src/core.c').read_bytes(), b'int x;\n')

    def test_mutated_file_fails_before_copy(self):
        (self.source / 'src/core.c').write_bytes(b'int changed;\n')
        with self.assertRaisesRegex(ValueError, 'blob mismatch'):
            self.run_preflight()
        self.assertFalse((self.root / 'out').exists())

    def test_extra_header_rejected(self):
        (self.source / 'include/stdio.h').write_text('not a system header')
        with self.assertRaisesRegex(ValueError, 'set mismatch'):
            self.run_preflight()

    def test_missing_input_rejected(self):
        (self.source / 'src/core.c').unlink()
        with self.assertRaises(ValueError):
            self.run_preflight()

    def test_symlink_rejected(self):
        (self.source / 'LICENSE').unlink()
        (self.source / 'LICENSE').symlink_to(self.source / 'src/core.c')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.run_preflight()

    def test_reused_output_rejected(self):
        (self.root / 'out').mkdir()
        with self.assertRaisesRegex(ValueError, 'reuse'):
            self.run_preflight()

    def test_actual_admission_catalog_binding(self):
        admission = load_json(ref.ADMISSION)
        self.assertEqual(len(admission['files_sha256']), 24)
        self.assertEqual(ref.check_admission(admission)['id'], 'libfvad')
        corrupted = copy.deepcopy(admission)
        corrupted['materialized_source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            ref.check_admission(corrupted)

    def test_git_tree_known_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(ref.git_tree(root), '4b825dc642cb6eb9a060e54bf8d69288fbee4904')
            (root / 'a').write_text('one')
            first = ref.git_tree(root)
            (root / 'a').chmod(0o755)
            self.assertNotEqual(ref.git_tree(root), first)
            (root / 'a').unlink(); (root / 'a').symlink_to('/dev/null')
            with self.assertRaises(ValueError): ref.git_tree(root)


class TraceTests(unittest.TestCase):
    def check(self, text, count=1, mode=2):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.jsonl'; path.write_text(text)
            return ref.strict_trace(path, count, mode)

    def test_complete_trace(self):
        rows = self.check('{"frame":0,"mode":2,"vad_active":1,"decision_available_after_samples":160}\n')
        self.assertEqual(ref.checked_stats([1], rows)['recall'], 1.0)

    def test_short_trace_rejected_before_canonical_min(self):
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            self.check('{"frame":0,"mode":2,"vad_active":1,"decision_available_after_samples":160}\n', count=2)
        with self.assertRaises(ValueError): ref.checked_stats([1, 0], [{'vad_active': 1}])

    def test_trace_negatives(self):
        good = {'frame': 0, 'mode': 2, 'vad_active': 1, 'decision_available_after_samples': 160}
        for key, value in [('frame', 1), ('frame', False), ('mode', 1), ('vad_active', 2),
                           ('vad_active', True), ('decision_available_after_samples', 0), ('score', float('nan'))]:
            row = {**good, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.check(json.dumps(row))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.check('{"frame":0,"frame":0,"vad_active":1}')

    def test_invalid_labels(self):
        for labels in ([True], [2], [-1], [0.5]):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                ref.checked_stats(labels, [{'vad_active': 1}])

    def test_environment_has_no_credentials_or_preload(self):
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'unit-secret', 'LD_PRELOAD': 'bad.so', 'PYTHONPATH': 'bad'}):
            environment = ref.process_env(Path('/tmp/test'))
        self.assertNotIn('GITHUB_TOKEN', environment)
        self.assertNotIn('LD_PRELOAD', environment)
        self.assertNotIn('PYTHONPATH', environment)


class SelectionTests(unittest.TestCase):
    def test_recall_floor_then_fpr_then_mode(self):
        modes = {0: metric(0.9, 0.3), 1: metric(0.8, 0.2), 2: metric(0.8, 0.2), 3: metric(0.79, 0.0)}
        self.assertEqual(ref.select_mode(metric(), modes), 1)

    def test_no_fallback_when_no_recall_match(self):
        self.assertIsNone(ref.select_mode(metric(1.0), {m: metric(0.999) for m in range(4)}))

    def test_invalid_or_missing_calibration(self):
        with self.assertRaises(ValueError): ref.select_mode(metric(), {0: metric()})
        modes = {m: metric() for m in range(4)}
        for key, value in [('recall', float('nan')), ('false_positive_rate', 1.1), ('positive_frames', 0)]:
            broken = copy.deepcopy(modes); broken[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): ref.select_mode(metric(), broken)

    def test_frozen_plan_geometry_and_nonpromotion(self):
        plan = load_json(ref.PLAN)
        self.assertEqual(plan['modes'], [0, 1, 2, 3])
        self.assertEqual(plan['calibration_seed'], 1307)
        self.assertEqual(plan['evaluation_seeds'], [2307, 3307])
        self.assertEqual(len(plan['case_ids']), 5)
        self.assertNotIn('clean-capture', plan['case_ids'])
        self.assertFalse(plan['shipping_authority'])
        self.assertTrue(plan['dataset_role'].startswith('D0-'))


def evidence_negatives(source: Path) -> None:
    ref.verify_output(source)
    tests = ('short-trace', 'wrong-score', 'wrong-mode', 'stale-receipt',
             'mutated-source', 'missing-case', 'binary-tamper', 'failed-status', 'nested-hidden-file',
             'unreviewed-admission', 'wrong-authority', 'global-stale-identity', 'control-code-drift')
    for test in tests:
        with tempfile.TemporaryDirectory(prefix='fe-evidence-negative-') as tmp:
            root = Path(tmp) / 'evidence'; shutil.copytree(source, root)
            report = load_json(root / 'result.json')
            case = report['calibration']['cases'][0]
            base = root / 'cases' / str(case['seed']) / case['case_id'] / 'b0'
            if test == 'short-trace':
                p = base / 'trace.jsonl'; p.write_text('\n'.join(p.read_text().splitlines()[:-1]) + '\n')
            elif test == 'wrong-score':
                case['arms']['b0']['recall'] = 0.123456
            elif test == 'wrong-mode':
                frozen = load_json(root / 'frozen-selection.json')
                frozen['mode'] = (frozen['mode'] + 1) % 4 if frozen['mode'] is not None else 0
                ref.write_json(root / 'frozen-selection.json', frozen)
                report['calibration']['selection'] = frozen
                report['frozen_selection_sha256'] = sha256((root / 'frozen-selection.json').read_bytes())
            elif test == 'stale-receipt':
                p = base / 'receipt.json'; receipt = load_json(p); receipt['identity']['source_sha'] = '0' * 40
                ref.write_json(p, receipt)
            elif test == 'mutated-source':
                p = root / 'upstream/src/fvad.c'; p.write_bytes(p.read_bytes() + b'\n')
            elif test == 'missing-case':
                report['evaluation']['cases'].pop()
            elif test == 'binary-tamper':
                p = root / 'libfvad-runner'; p.write_bytes(p.read_bytes() + b'\0')
            elif test == 'failed-status':
                report['status'] = 'FAIL'
            elif test == 'unreviewed-admission':
                p = root / 'admission.json'; admission = load_json(p)
                admission['admission']['decision'] = 'UNREVIEWED'
                ref.write_json(p, admission)
            elif test == 'wrong-authority':
                report['authority'] = 'SHIPPING'
            elif test == 'global-stale-identity':
                report['identities']['b0']['source_sha'] = '0' * 40
            elif test == 'control-code-drift':
                first = next(iter(report['control_files_sha256']))
                report['control_files_sha256'][first] = '0' * 64
            else:
                (root / 'nested').mkdir(); (root / 'nested/manifest.json').write_text('must not be hidden')
                try:
                    ref.verify_output(root)
                except ValueError:
                    continue
                raise AssertionError('untracked nested manifest escaped exact file set')
            ref.write_json(root / 'result.json', report)
            ref.seal_output(root, report)  # Re-sign hash envelope: semantic checks must still reject.
            try:
                ref.verify_output(root)
            except ValueError:
                continue
            raise AssertionError(f'evidence mutation accepted: {test}')
    print(f'actual-evidence semantic negatives: {len(tests)}/{len(tests)} rejected')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--evidence':
        evidence_negatives(Path(sys.argv[2]).resolve())
    else:
        unittest.main()
