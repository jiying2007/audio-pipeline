#!/usr/bin/env python3
"""Keep consumed I019 diagnostic execution retired; parse YAML as data only."""

from copy import deepcopy
import hashlib, importlib.util, json, subprocess, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW='.github/workflows/research-i019-vad-weak-start-evidence-decomposition-v1.yml'
HISTORY='tests/validation/data/i019-consumed-workflow.yml'
HISTORY_BLOB='3c9676bd9df8efb3159c1702e9b8eea42c53fc88'
CLOSURE=('.github/research/continuous-optimization/development-v4/'
         'i019-vad-weak-start-evidence-decomposition-v1-result.json')
EVIDENCE_ROOT=Path('validation/research/evidence/i019-36257346949')
EVIDENCE=str(EVIDENCE_ROOT)+'/**'
SELF='tests/validation/test_i019_retirement.py'
GUARD_TEST='tests/validation/test_i019_one_shot_guard.py'
CHECK='python3 '+SELF

def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def yaml_data(data):
    cmd=('require "json"; require "yaml"; '
         'print JSON.generate(YAML.safe_load(STDIN.read, aliases: false))')
    value=json.loads(subprocess.check_output(['ruby','-e',cmd],input=data))
    if 'true' in value:
        value['on']=value.pop('true')
    return value

def expected_workflow(history):
    expected=deepcopy(history)
    expected['on'].pop('workflow_dispatch')
    expected['on']['pull_request']['paths'] += [HISTORY,SELF,CLOSURE,EVIDENCE]
    expected['permissions']={'contents':'read'}
    del expected['jobs']['diagnose']
    steps=expected['jobs']['contract']['steps']
    steps[1]['run']=steps[1]['run'].replace(
        'set -euo pipefail\n','set -euo pipefail\n'+CHECK+'\n',1)
    return expected

def validate(live,history):
    if live != expected_workflow(history):
        raise ValueError('I019 must retain only the frozen read-only PR contract')

class RetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(ROOT/HISTORY).read_bytes()
        if blob(raw)!=HISTORY_BLOB:
            raise ValueError('consumed I019 workflow fixture drift')
        cls.history=yaml_data(raw)
        cls.live=yaml_data((ROOT/WORKFLOW).read_bytes())

    def test_live_is_contract_only(self):
        validate(self.live,self.history)

    def test_original_execution_surface_rejected(self):
        with self.assertRaises(ValueError):
            validate(self.history,self.history)

    def test_no_event_can_restart_consumed_diagnostic(self):
        for event in ('workflow_dispatch','repository_dispatch','workflow_call',
                      'workflow_run','schedule','push','pull_request_target'):
            changed=expected_workflow(self.history); changed['on'][event]={}
            with self.subTest(event=event), self.assertRaises(ValueError):
                validate(changed,self.history)

    def test_diagnose_job_restore_or_rename_rejected(self):
        for name in ('diagnose','renamed_diagnostic'):
            changed=expected_workflow(self.history)
            changed['jobs'][name]=self.history['jobs']['diagnose']
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(changed,self.history)

    def test_closure_is_diagnostic_only(self):
        c=json.loads((ROOT/CLOSURE).read_text())
        self.assertEqual(c['status'],'CLOSED_DIAGNOSTIC_ONLY')
        self.assertEqual(c['decision'],'VAD_WEAK_START_EVIDENCE_DECOMPOSED_REVIEW_REQUIRED')
        self.assertEqual(c['fresh_authority']['candidate_budget_consumed'],0)
        self.assertEqual(c['fresh_authority']['confirmation_budget_consumed'],0)
        self.assertEqual(c['fresh_authority']['diagnostic_execution_consumed'],1)
        self.assertFalse(c['fresh_authority']['rerun_allowed'])
        self.assertFalse(c['authority_boundary']['candidate_selected'])
        self.assertFalse(c['authority_boundary']['threshold_added'])

    def test_measured_separation_is_preserved(self):
        c=json.loads((ROOT/CLOSURE).read_text())
        ns=c['summary']['stage-ns-nonstationary']
        st=c['summary']['stage-ns-stationary']
        self.assertEqual(ns['weak_start_events'],{
            'total':23,'speech':13,'noise':10,'speech_fraction':13/23})
        self.assertEqual(ns['fixed_component_positive_counts']['blend_applied'],
                         {'speech':7,'noise':0})
        self.assertEqual(ns['pre_blend_origin']['blend_dependent']['noise'],0)
        self.assertEqual(st['weak_start_events'],{
            'total':16,'speech':15,'noise':1,'speech_fraction':0.9375})
        self.assertEqual(st['fixed_component_positive_counts']['blend_applied'],
                         {'speech':15,'noise':1})
        self.assertEqual(st['existing_guard']['guard_active']['noise'],1)
        self.assertEqual(st['existing_guard']['guard_active']['speech'],0)

    def test_history_is_outside_active_workflow_directory(self):
        self.assertFalse((ROOT/HISTORY).resolve().is_relative_to(ROOT/'.github/workflows'))
        for path in (ROOT/'.github/workflows').glob('*.y*ml'):
            self.assertNotEqual(blob(path.read_bytes()),HISTORY_BLOB,str(path))

    def test_central_registry_matches_retired_execution(self):
        spec=importlib.util.spec_from_file_location(
            'i019_registry',ROOT/'.github/program/maintenance_workflow_contract.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        workflow=Path(WORKFLOW)
        self.assertIn(workflow,module.CONTRACT_ONLY_RESEARCH_WORKFLOWS)
        evidence=module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow]
        self.assertEqual(set(evidence),{
            Path('.github/research/continuous-optimization/development-v4/'
                 'i019-vad-weak-start-evidence-decomposition-v1.json'),
            Path(CLOSURE),
        })
        module.validate_program_archive_trigger_boundaries(ROOT)

    def test_contract_covers_retirement_surfaces(self):
        paths=self.live['on']['pull_request']['paths']
        for p in (HISTORY,SELF,CLOSURE,EVIDENCE,GUARD_TEST):
            self.assertIn(p,paths)
        scripts='\n'.join(s.get('run','') for s in self.live['jobs']['contract']['steps'])
        self.assertIn(CHECK+'\n',scripts)
        self.assertEqual(self.live['permissions'],{'contents':'read'})

if __name__=='__main__':
    unittest.main()
