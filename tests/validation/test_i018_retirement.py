#!/usr/bin/env python3
"""Keep consumed I018 development execution retired; parse YAML as data only."""

from copy import deepcopy
import hashlib, importlib.util, json, subprocess, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW='.github/workflows/research-i018-vad-weak-refresh-extension-only-v1.yml'
HISTORY='tests/validation/data/i018-consumed-workflow.yml'
HISTORY_BLOB='568e8d07becb864c4d74d823ee6274098c0d2976'
CLOSURE=('.github/research/continuous-optimization/development-v4/'
         'i018-vad-weak-refresh-extension-only-v1-result.json')
EVIDENCE_ROOT=Path('validation/research/evidence/i018-36253477019')
EVIDENCE=str(EVIDENCE_ROOT)+'/**'
EVIDENCE_MEMBERS=(
    'SHA256SUMS','build-info.txt','contract.json','corpora.txt',
    'probe.sha256','result.json','summary.json',
)
SELF='tests/validation/test_i018_retirement.py'
GUARD_TEST='tests/validation/test_i018_one_shot_guard.py'
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
    del expected['jobs']['develop']
    steps=expected['jobs']['contract']['steps']
    steps[1]['run']=steps[1]['run'].replace(
        'set -euo pipefail\n','set -euo pipefail\n'+CHECK+'\n',1)
    return expected

def validate(live,history):
    if live != expected_workflow(history):
        raise ValueError('I018 must retain only the frozen read-only PR contract')

class RetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(ROOT/HISTORY).read_bytes()
        if blob(raw)!=HISTORY_BLOB:
            raise ValueError('consumed I018 workflow fixture drift')
        cls.history=yaml_data(raw)
        cls.live=yaml_data((ROOT/WORKFLOW).read_bytes())

    def test_live_is_contract_only(self): validate(self.live,self.history)

    def test_original_execution_surface_rejected(self):
        with self.assertRaises(ValueError): validate(self.history,self.history)

    def test_no_event_can_restart_consumed_development(self):
        for event in ('workflow_dispatch','repository_dispatch','workflow_call',
                      'workflow_run','schedule','push','pull_request_target'):
            changed=expected_workflow(self.history); changed['on'][event]={}
            with self.subTest(event=event), self.assertRaises(ValueError):
                validate(changed,self.history)

    def test_develop_job_restore_or_rename_rejected(self):
        for name in ('develop','renamed_development'):
            changed=expected_workflow(self.history)
            changed['jobs'][name]=self.history['jobs']['develop']
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(changed,self.history)

    def test_closure_is_terminal_rejection(self):
        c=json.loads((ROOT/CLOSURE).read_text())
        self.assertEqual(c['status'],'CLOSED_REJECTED_DEVELOPMENT_ONLY')
        self.assertEqual(c['decision'],'REJECTED_DEVELOPMENT_ONLY')
        self.assertEqual(c['fresh_authority']['candidate_budget_consumed'],1)
        self.assertEqual(c['fresh_authority']['confirmation_budget_consumed'],0)
        self.assertFalse(c['fresh_authority']['rerun_allowed'])
        self.assertEqual(c['failed_gates'],[
            'stage-ns-nonstationary:recall','stage-ns-stationary:recall'])
        self.assertEqual(c['candidate_probability_identity']['max_probability_delta'],0.0)
        self.assertFalse(c['authority_boundary']['blind_validation_authorized'])

    def test_measured_tradeoff_is_preserved(self):
        c=json.loads((ROOT/CLOSURE).read_text())
        ns=c['summary']['stage-ns-nonstationary']['candidate_vs_shipping']
        st=c['summary']['stage-ns-stationary']['candidate_vs_shipping']
        self.assertEqual(ns['noise_active_reduction_frames'],87)
        self.assertEqual(ns['noise_active_segment_reduction'],8)
        self.assertLess(ns['recall_delta'],-0.03)
        self.assertEqual(st['noise_active_reduction_frames'],16)
        self.assertLess(st['recall_delta'],-0.03)

    def test_raw_evidence_matches_trusted_closure_hashes(self):
        c=json.loads((ROOT/CLOSURE).read_text())
        expected=c['authoritative_execution']['member_sha256']
        self.assertEqual(set(expected),set(EVIDENCE_MEMBERS))
        for name in EVIDENCE_MEMBERS:
            data=(ROOT/EVIDENCE_ROOT/name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),expected[name],name)
        raw=json.loads((ROOT/EVIDENCE_ROOT/'result.json').read_text())
        self.assertEqual(raw['decision'],c['decision'])
        self.assertEqual(raw['source_base_sha'],c['source_base_sha'])
        self.assertEqual(raw['fresh_development_seeds'],c['fresh_authority']['seeds'])
        self.assertEqual(raw['shipping_mirror'],c['shipping_mirror'])
        self.assertEqual(raw['candidate_probability_identity'],
                         c['candidate_probability_identity'])

    def test_history_is_outside_active_workflow_directory(self):
        self.assertFalse((ROOT/HISTORY).resolve().is_relative_to(ROOT/'.github/workflows'))
        for path in (ROOT/'.github/workflows').glob('*.y*ml'):
            self.assertNotEqual(blob(path.read_bytes()),HISTORY_BLOB,str(path))

    def test_central_registry_matches_retired_execution(self):
        spec=importlib.util.spec_from_file_location(
            'i018_registry',ROOT/'.github/program/maintenance_workflow_contract.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        workflow=Path(WORKFLOW)
        self.assertIn(workflow,module.CONTRACT_ONLY_RESEARCH_WORKFLOWS)
        evidence=module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow]
        self.assertIn(Path(CLOSURE),evidence)
        self.assertEqual(set(evidence),{
            Path('.github/research/continuous-optimization/development-v4/'
                 'i018-vad-weak-refresh-extension-only-v1.json'),
            Path(CLOSURE),
            *(EVIDENCE_ROOT/name for name in EVIDENCE_MEMBERS),
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
