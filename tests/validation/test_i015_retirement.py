#!/usr/bin/env python3
"""Keep consumed I015 execution retired; parse YAML as data, never run research."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/research-i015-vad-upstream-consumption-decomposition-v1.yml'
HISTORY = 'tests/validation/data/i015-consumed-workflow.yml'
HISTORY_BLOB = '1bf5717bf4bb02f3847606a6d7cba7c61bde70f1'
CLOSURE = ('.github/research/continuous-optimization/development-v4/'
           'i015-vad-upstream-consumption-decomposition-v1-result.json')
SELF = 'tests/validation/test_i015_retirement.py'
LEGACY_TEST = 'tests/validation/test_i015_one_shot_guard.py'
CHECK = 'python3 ' + SELF


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def yaml_data(data):
    # Verify already requires Ruby/Psych. Safe-load one YAML mapping without
    # custom objects or aliases; no workflow shell, expressions or actions run.
    command = ('require "json"; require "yaml"; '
               'print JSON.generate(YAML.safe_load(STDIN.read, aliases: false))')
    result = json.loads(subprocess.check_output(['ruby', '-e', command], input=data))
    if not isinstance(result, dict):
        raise ValueError('workflow mapping required')
    # Psych uses YAML 1.1: the unquoted GitHub key "on" is encoded as "true".
    if 'true' in result:
        if 'on' in result:
            raise ValueError('ambiguous trigger mapping')
        result['on'] = result.pop('true')
    return result


def expected_workflow(history):
    expected = deepcopy(history)
    expected['on'].pop('workflow_dispatch')
    expected['on']['pull_request']['paths'] += [HISTORY, SELF, CLOSURE]
    expected['permissions'] = {'contents': 'read'}
    del expected['jobs']['diagnose']
    steps = expected['jobs']['contract']['steps']
    steps[0]['with']['persist-credentials'] = False
    steps[1]['run'] = steps[1]['run'].replace(
        'set -euo pipefail\n', 'set -euo pipefail\n' + CHECK + '\n', 1)
    return expected


def validate(live, history):
    if live != expected_workflow(history):
        raise ValueError('I015 must retain only the frozen read-only PR contract')


class RetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = (ROOT / HISTORY).read_bytes()
        if blob(raw) != HISTORY_BLOB:
            raise ValueError('consumed workflow fixture drift')
        cls.history = yaml_data(raw)
        cls.live = yaml_data((ROOT / WORKFLOW).read_bytes())

    def test_live_is_contract_only(self):
        validate(self.live, self.history)

    def test_original_execution_surface_rejected(self):
        with self.assertRaises(ValueError):
            validate(self.history, self.history)

    def test_no_new_event_can_restart_consumed_diagnosis(self):
        for event in ('workflow_dispatch', 'repository_dispatch', 'workflow_call',
                      'workflow_run', 'schedule', 'push', 'pull_request_target'):
            with self.subTest(event=event):
                changed = expected_workflow(self.history)
                changed['on'][event] = {}
                with self.assertRaises(ValueError):
                    validate(changed, self.history)

    def test_job_restore_or_rename_rejected(self):
        for name in ('diagnose', 'renamed_diagnosis'):
            changed = expected_workflow(self.history)
            changed['jobs'][name] = self.history['jobs']['diagnose']
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(changed, self.history)

    def test_extra_step_cannot_hide_fresh_generation(self):
        changed = expected_workflow(self.history)
        changed['jobs']['contract']['steps'].append(
            self.history['jobs']['diagnose']['steps'][5])
        with self.assertRaises(ValueError):
            validate(changed, self.history)

    def test_read_only_permissions_and_checkout_cannot_drift(self):
        for change in ('permissions', 'checkout'):
            changed = expected_workflow(self.history)
            if change == 'permissions':
                changed['permissions']['actions'] = 'write'
            else:
                changed['jobs']['contract']['steps'][0]['with']['persist-credentials'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(changed, self.history)

    def test_compile_and_self_test_steps_cannot_be_skipped(self):
        for change in ('remove', 'condition', 'continue-on-error'):
            changed = expected_workflow(self.history)
            if change == 'remove':
                changed['jobs']['contract']['steps'].pop()
            else:
                changed['jobs']['contract'][change if change != 'condition' else 'if'] = 'false'
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(changed, self.history)

    def test_original_closure_bytes_are_unchanged(self):
        data = (ROOT / CLOSURE).read_bytes()
        self.assertEqual(blob(data), '98304a17b23a84350774e85b3706500d02c4dbd2')
        self.assertEqual(json.loads(data)['status'], 'CLOSED_DIAGNOSTIC_ONLY')

    def test_history_is_outside_active_workflow_directory(self):
        self.assertFalse((ROOT / HISTORY).resolve().is_relative_to(ROOT / '.github/workflows'))
        for path in (ROOT / '.github/workflows').glob('*.y*ml'):
            self.assertNotEqual(blob(path.read_bytes()), HISTORY_BLOB, str(path))

    def test_central_registry_matches_retired_execution(self):
        spec = importlib.util.spec_from_file_location(
            'i015_maintenance_registry', ROOT / '.github/program/maintenance_workflow_contract.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        workflow = Path(WORKFLOW)
        self.assertIn(workflow, module.CONTRACT_ONLY_RESEARCH_WORKFLOWS)
        self.assertIn(Path(CLOSURE), module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow])
        # Exercises the existing owner rather than inventing a second path rule.
        module.validate_program_archive_trigger_boundaries(ROOT)

    def test_independent_pr_and_main_contract_cover_retirement(self):
        contract = yaml_data((ROOT / '.github/workflows/i015-evidence-finalization-contract.yml').read_bytes())
        for event in ('pull_request', 'push'):
            paths = contract['on'][event]['paths']
            for path in (WORKFLOW, HISTORY, SELF, LEGACY_TEST):
                self.assertIn(path, paths)
        scripts = '\n'.join(s.get('run', '') for s in contract['jobs']['contract']['steps'])
        self.assertIn(CHECK + '\n', scripts)
        self.assertEqual(contract['permissions'], {'contents': 'read'})


if __name__ == '__main__':
    unittest.main()
