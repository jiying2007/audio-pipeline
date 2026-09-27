#!/usr/bin/env python3
"""Keep consumed I020 development execution retired while blind review remains separate."""

from copy import deepcopy
import hashlib, importlib.util, json, subprocess, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW='.github/workflows/research-i020-vad-weak-start-requires-blend-v1.yml'
HISTORY='tests/validation/data/i020-consumed-workflow.yml'
HISTORY_BLOB='4396acd02e7f842017d3be52c9b47602387bef4b'
RESULT=('.github/research/continuous-optimization/development-v4/'
        'i020-vad-weak-start-requires-blend-v1-result.json')
MANIFEST=('.github/research/continuous-optimization/code-candidates/'
          'i020-vad-weak-start-requires-blend-v1.json')
PATCH=('.github/research/continuous-optimization/code-candidates/'
       'i020-vad-weak-start-requires-blend-v1.patch')
SELF='tests/validation/test_i020_retirement.py'
GUARD_TEST='tests/validation/test_i020_one_shot_guard.py'
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
    expected['on']['pull_request']['paths'] += [HISTORY,SELF,RESULT,MANIFEST,PATCH]
    expected['permissions']={'contents':'read'}
    del expected['jobs']['develop']
    steps=expected['jobs']['contract']['steps']
    steps[1]['run']=steps[1]['run'].replace(
        'set -euo pipefail\n','set -euo pipefail\n'+CHECK+'\n',1)
    return expected

def validate(live,history):
    if live != expected_workflow(history):
        raise ValueError('I020 development workflow must be retired to read-only PR contract')

class RetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=(ROOT/HISTORY).read_bytes()
        if blob(raw)!=HISTORY_BLOB:
            raise ValueError('consumed I020 workflow fixture drift')
        cls.history=yaml_data(raw)
        cls.live=yaml_data((ROOT/WORKFLOW).read_bytes())

    def test_live_is_contract_only(self):
        validate(self.live,self.history)

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

    def test_candidate_is_frozen_not_shipping(self):
        r=json.loads((ROOT/RESULT).read_text())
        m=json.loads((ROOT/MANIFEST).read_text())
        self.assertEqual(r['status'],'FROZEN_RESEARCH_CANDIDATE')
        self.assertEqual(r['next_gate'],'validation-grade-blind')
        self.assertEqual(r['decision'],'FROZEN_RESEARCH_CANDIDATE_REVIEW_REQUIRED')
        self.assertFalse(r['fresh_authority']['rerun_allowed'])
        self.assertEqual(r['fresh_authority']['candidate_budget_consumed'],1)
        self.assertEqual(r['fresh_authority']['confirmation_budget_consumed'],0)
        self.assertEqual(r['failed_gates'],[])
        self.assertEqual(r['research_candidate_id'],m['research_candidate_id'])
        self.assertEqual(r['candidate_patch']['sha256'],m['patch']['sha256'])
        self.assertFalse(r['authority_boundary']['source_merge_authorized'])
        self.assertFalse(m['output_authority']['shipping_authority'])

    def test_development_pass_is_preserved(self):
        r=json.loads((ROOT/RESULT).read_text())
        ns=r['summary']['stage-ns-nonstationary']['candidate_vs_shipping']
        st=r['summary']['stage-ns-stationary']['candidate_vs_shipping']
        self.assertEqual(ns['noise_active_reduction_frames'],56)
        self.assertEqual(ns['noise_active_segment_reduction'],6)
        self.assertGreaterEqual(ns['recall_delta'],-0.03)
        self.assertLessEqual(ns['fpr_delta'],0.0)
        self.assertEqual(st['recall_delta'],0.0)
        self.assertEqual(st['fpr_delta'],0.0)
        self.assertEqual(r['candidate_probability_identity']['max_probability_delta'],0.0)

    def test_history_is_outside_active_workflow_directory(self):
        self.assertFalse((ROOT/HISTORY).resolve().is_relative_to(ROOT/'.github/workflows'))
        for path in (ROOT/'.github/workflows').glob('*.y*ml'):
            self.assertNotEqual(blob(path.read_bytes()),HISTORY_BLOB,str(path))

    def test_central_registry_matches_frozen_candidate(self):
        spec=importlib.util.spec_from_file_location(
            'i020_registry',ROOT/'.github/program/maintenance_workflow_contract.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        workflow=Path(WORKFLOW)
        self.assertIn(workflow,module.CONTRACT_ONLY_RESEARCH_WORKFLOWS)
        evidence=module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow]
        self.assertEqual(set(evidence),{
            Path('.github/research/continuous-optimization/development-v4/'
                 'i020-vad-weak-start-requires-blend-v1.json'),
            Path(RESULT),Path(MANIFEST),Path(PATCH),
        })
        module.validate_program_archive_trigger_boundaries(ROOT)

    def test_contract_covers_frozen_surfaces(self):
        paths=self.live['on']['pull_request']['paths']
        for p in (HISTORY,SELF,RESULT,MANIFEST,PATCH,GUARD_TEST):
            self.assertIn(p,paths)
        scripts='\n'.join(s.get('run','') for s in self.live['jobs']['contract']['steps'])
        self.assertIn(CHECK+'\n',scripts)
        self.assertEqual(self.live['permissions'],{'contents':'read'})

if __name__=='__main__':
    unittest.main()
