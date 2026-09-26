#!/usr/bin/env python3
"""Keep consumed I017 diagnostic execution retired; parse YAML as data only."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/research-i017-vad-state-persistence-decomposition-v1.yml'
HISTORY = 'tests/validation/data/i017-consumed-workflow.yml'
HISTORY_BLOB = '93e84be5e886fdd5377468cb78f81b95bee54a15'
CLOSURE = ('.github/research/continuous-optimization/development-v4/'
           'i017-vad-state-persistence-decomposition-v1-result.json')
EVIDENCE_ROOT = Path('validation/research/evidence/i017-36249750866')
EVIDENCE = str(EVIDENCE_ROOT) + '/**'
EVIDENCE_MEMBERS = (
    'SHA256SUMS', 'build-info.txt', 'contract.json', 'corpora.txt',
    'probe.sha256', 'result.json', 'summary.json',
)
SELF = 'tests/validation/test_i017_retirement.py'
GUARD_TEST = 'tests/validation/test_i017_one_shot_guard.py'
CHECK = 'python3 ' + SELF


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def yaml_data(data: bytes) -> dict:
    command = ('require "json"; require "yaml"; '
               'print JSON.generate(YAML.safe_load(STDIN.read, aliases: false))')
    result = json.loads(subprocess.check_output(['ruby', '-e', command], input=data))
    if not isinstance(result, dict):
        raise ValueError('workflow mapping required')
    if 'true' in result:
        if 'on' in result:
            raise ValueError('ambiguous trigger mapping')
        result['on'] = result.pop('true')
    return result


def expected_workflow(history: dict) -> dict:
    expected = deepcopy(history)
    expected['on'].pop('workflow_dispatch')
    expected['on']['pull_request']['paths'] += [HISTORY, SELF, CLOSURE, EVIDENCE]
    expected['permissions'] = {'contents': 'read'}
    del expected['jobs']['diagnose']
    steps = expected['jobs']['contract']['steps']
    steps[1]['run'] = steps[1]['run'].replace(
        'set -euo pipefail\n', 'set -euo pipefail\n' + CHECK + '\n', 1)
    return expected


def validate(live: dict, history: dict) -> None:
    if live != expected_workflow(history):
        raise ValueError('I017 must retain only the frozen read-only PR contract')


class RetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (ROOT / HISTORY).read_bytes()
        if blob(raw) != HISTORY_BLOB:
            raise ValueError('consumed I017 workflow fixture drift')
        cls.history = yaml_data(raw)
        cls.live = yaml_data((ROOT / WORKFLOW).read_bytes())

    def test_live_is_contract_only(self):
        validate(self.live, self.history)

    def test_original_execution_surface_rejected(self):
        with self.assertRaises(ValueError):
            validate(self.history, self.history)

    def test_no_event_can_restart_consumed_diagnostic(self):
        for event in ('workflow_dispatch', 'repository_dispatch', 'workflow_call',
                      'workflow_run', 'schedule', 'push', 'pull_request_target'):
            with self.subTest(event=event):
                changed = expected_workflow(self.history)
                changed['on'][event] = {}
                with self.assertRaises(ValueError):
                    validate(changed, self.history)

    def test_diagnose_job_restore_or_rename_rejected(self):
        for name in ('diagnose', 'renamed_diagnostic'):
            changed = expected_workflow(self.history)
            changed['jobs'][name] = self.history['jobs']['diagnose']
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(changed, self.history)

    def test_read_only_permissions_cannot_drift(self):
        changed = expected_workflow(self.history)
        changed['permissions']['actions'] = 'write'
        with self.assertRaises(ValueError):
            validate(changed, self.history)

    def test_closure_is_diagnostic_only(self):
        closure = json.loads((ROOT / CLOSURE).read_text(encoding='utf-8'))
        self.assertEqual(closure['status'], 'CLOSED_DIAGNOSTIC_ONLY')
        self.assertEqual(
            closure['decision'],
            'VAD_STATE_PERSISTENCE_DECOMPOSED_REVIEW_REQUIRED',
        )
        self.assertFalse(closure['fresh_authority']['rerun_allowed'])
        self.assertEqual(closure['fresh_authority']['candidate_budget_consumed'], 0)
        self.assertEqual(closure['fresh_authority']['confirmation_budget_consumed'], 0)
        self.assertEqual(closure['fresh_authority']['diagnostic_execution_consumed'], 1)
        self.assertFalse(closure['authority_boundary']['candidate_selected'])
        self.assertFalse(closure['authority_boundary']['shipping_source_changed'])

    def test_diagnostic_interpretation_is_specific(self):
        closure = json.loads((ROOT / CLOSURE).read_text(encoding='utf-8'))
        nonstat = closure['summary']['stage-ns-nonstationary']
        stationary = closure['summary']['stage-ns-stationary']
        self.assertEqual(
            nonstat['noise_active_frame_origin'],
            {'hangover_carry': 96, 'strong_refresh': 4, 'weak_refresh': 22},
        )
        self.assertEqual(
            nonstat['noise_active_segment_start_origin'],
            {'carry_from_prior_active': 3, 'strong_refresh': 2, 'weak_refresh': 10},
        )
        self.assertEqual(
            stationary['noise_active_frame_origin'],
            {'hangover_carry': 28, 'strong_refresh': 1, 'weak_refresh': 2},
        )

    def test_raw_evidence_matches_trusted_closure_hashes(self):
        closure = json.loads((ROOT / CLOSURE).read_text(encoding='utf-8'))
        expected = closure['authoritative_execution']['member_sha256']
        self.assertEqual(set(expected), set(EVIDENCE_MEMBERS))
        for name in EVIDENCE_MEMBERS:
            data = (ROOT / EVIDENCE_ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected[name], name)
        raw = json.loads((ROOT / EVIDENCE_ROOT / 'result.json').read_text(encoding='utf-8'))
        self.assertEqual(raw['decision'], closure['decision'])
        self.assertEqual(raw['source_base_sha'], closure['source_base_sha'])
        self.assertEqual(raw['fresh_diagnostic_seeds'],
                         closure['fresh_authority']['seeds'])
        self.assertEqual(raw['shipping_mirror'], closure['shipping_mirror'])

    def test_history_is_outside_active_workflow_directory(self):
        self.assertFalse((ROOT / HISTORY).resolve().is_relative_to(ROOT / '.github/workflows'))
        for path in (ROOT / '.github/workflows').glob('*.y*ml'):
            self.assertNotEqual(blob(path.read_bytes()), HISTORY_BLOB, str(path))

    def test_central_registry_matches_retired_execution(self):
        spec = importlib.util.spec_from_file_location(
            'i017_maintenance_registry', ROOT / '.github/program/maintenance_workflow_contract.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        workflow = Path(WORKFLOW)
        self.assertIn(workflow, module.CONTRACT_ONLY_RESEARCH_WORKFLOWS)
        evidence = module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow]
        self.assertIn(Path(CLOSURE), evidence)
        self.assertEqual(
            set(evidence),
            {
                Path('.github/research/continuous-optimization/development-v4/'
                     'i017-vad-state-persistence-decomposition-v1.json'),
                Path(CLOSURE),
                *(EVIDENCE_ROOT / name for name in EVIDENCE_MEMBERS),
            },
        )
        module.validate_program_archive_trigger_boundaries(ROOT)

    def test_contract_covers_retirement_surfaces(self):
        paths = self.live['on']['pull_request']['paths']
        for path in (HISTORY, SELF, CLOSURE, EVIDENCE, GUARD_TEST):
            self.assertIn(path, paths)
        scripts = '\n'.join(
            step.get('run', '') for step in self.live['jobs']['contract']['steps']
        )
        self.assertIn(CHECK + '\n', scripts)
        self.assertEqual(self.live['permissions'], {'contents': 'read'})


if __name__ == '__main__':
    unittest.main()
