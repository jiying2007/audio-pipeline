#!/usr/bin/env python3
"""Finite FIR speech comparison on disclosed, admitted mixtures. No promotion."""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from contracts import ROOT, load_json, require, sha256, hex_digest
from libfvad_reference import write_json, seal_output, run_logged
import speech_spatial as speech
from array_qualification import FLAGS
from array_fir_checks import PLAN, RADII, MODES, config_text

HERE=Path(__file__).resolve().parent
ARMS=('lagrange3','fir17','fir33')
ROLE='DISCLOSED_DIAGNOSTIC_REUSE_NOT_INDEPENDENT_HOLDOUT'
SOURCES=('array_native.c','array_native.h','array_runner.c','array_fir_checks.py','speech_fir.py','speech_spatial.py')


def verify_seal(root):
    require(not (root/'failure.json').exists() and all(not p.is_symlink() for p in root.rglob('*')),'failed/symlink evidence')
    actual={p.relative_to(root).as_posix():sha256(p.read_bytes()) for p in root.rglob('*') if p.is_file() and p.name not in ()
            and p.relative_to(root).as_posix() not in ('manifest.json','SHA256SUMS')}
    manifest=load_json(root/'manifest.json');require(manifest['files']==actual and manifest['shipping_authority'] is False,'file set/hash mismatch')
    lines=(root/'SHA256SUMS').read_text().splitlines();sums={}
    for line in lines:
        digest,name=line.split('  ',1);require(name not in sums,'duplicate checksum');sums[name]=digest
    require(sums=={**actual,'manifest.json':sha256((root/'manifest.json').read_bytes())},'checksum mismatch')
    return actual


def summary(rows):
    result=[]
    for group in ('development-diagnostic','speaker-disjoint-confirmation-diagnostic'):
        for geometry in speech.POSITIONS:
            for mode in ARMS:
                selected=[r for r in rows if r['original_role']==group and r['geometry']==geometry and r['target_degrees']!=r['interferer_degrees']]
                require(len(selected)==4,'fixed subgroup count')
                metrics=('component_sir_gain_db','target_gain_db','target_relative_error_energy','canonical_si_sdr_db')
                result.append({'original_role':group,'effective_role':ROLE,'geometry':geometry,'arm':mode,'cases':4,
                    **{m:sum(r['arms'][mode][m] for r in selected)/4 for m in metrics},
                    'sir_change_vs_cubic_db':sum(r['arms'][mode]['component_sir_gain_db']-r['arms']['lagrange3']['component_sir_gain_db'] for r in selected)/4})
    return result


def raw(base,key,tag,n):
    return speech.values((base/'cases'/key/(tag+'.s16')).read_bytes(),'h',speech.N*n)


def outputs(path):
    return {tag:speech.values((path/(tag+'.f32')).read_bytes(),'f',speech.N) for tag in ('target','interferer','mixture')}


def run(base,root,revision):
    require(hex_digest(revision,40) and not root.exists(),'exact revision/fresh output required')
    # The original pipeline's canonical verifier establishes the source/renderer.
    speech.verify(base)
    plan=load_json(PLAN);root.mkdir(parents=True);(root/'source').mkdir()
    for name in SOURCES:shutil.copyfile(HERE/name,root/'source'/name)
    shutil.copyfile(ROOT/'validation/tools/run_validation_engine.py',root/'source/run_validation_engine.py')
    shutil.copyfile(PLAN,root/'experiment.json')
    binary=root/'array'
    command=['cc',*FLAGS,HERE/'array_native.c',HERE/'array_runner.c','-lm','-o',binary]
    run_logged(command,root/'build.log');run_logged(['cc','--version'],root/'compiler.txt')
    write_json(root/'build.json',{'command':list(map(str,command)),'timing_authority':'NONE_TARGET','native_only':True})
    old=load_json(base/'result.json');rows=[]
    for prior in old['cases']:
        key=prior['case_id'];g=speech.geometry(prior['geometry'],prior['target_degrees']);n=len(g['positions_m'])
        sub=root/'cases'/key;sub.mkdir(parents=True)
        t=[v/32768 for v in raw(base,key,'target',n)[::n]];i=[v/32768 for v in raw(base,key,'interferer',n)[::n]]
        row={k:prior[k] for k in ('case_id','pair','geometry','target_degrees','interferer_degrees')}
        row.update(original_role=prior['role'],effective_role=ROLE,arms={})
        for mode in ARMS:
            dest=sub/mode;dest.mkdir();cfg=dest/'geometry.txt'
            cfg.write_bytes(speech.geometry_text(g,'lagrange3') if mode=='lagrange3' else config_text(g,mode))
            for tag in ('target','interferer','mixture','repeat'):
                source_tag='mixture' if tag=='repeat' else tag
                run_logged([binary,cfg,base/'cases'/key/(source_tag+'.s16'),dest/(tag+'.f32'),dest/(tag+'.json')],dest/(tag+'.log'))
            out=outputs(dest);delay=5+RADII.get(mode,0)
            require((dest/'repeat.f32').read_bytes()==(dest/'mixture.f32').read_bytes(),'FIR repeat mismatch')
            if mode=='lagrange3':
                for tag in out:require((dest/(tag+'.f32')).read_bytes()==(base/'cases'/key/mode/(tag+'.f32')).read_bytes(),'old cubic output changed')
            row['arms'][mode]={'delay_samples':delay,**speech.metrics(t,i,out['target'],out['interferer'],out['mixture'],delay)}
        rows.append(row)
    report={'schema_version':1,'experiment_id':plan['experiment_id'],'decision':plan['decision'],
            'execution_source_revision':revision,'shipping_authority':False,'effective_data_role':ROLE,
            'source_evidence_revision':old['execution_source_revision'],'source_manifest_sha256':sha256((base/'manifest.json').read_bytes()),
            'processor_sha256':sha256(binary.read_bytes()),'oracle_directions':True,'real_array_recording':False,'native_only':True,
            'cases':rows,'summary':summary(rows)}
    write_json(root/'result.json',report);seal_output(root,report)
    return verify(base,root,revision)


def verify(base,root,revision=None):
    actual=verify_seal(root);verify_seal(base)
    plan=load_json(PLAN);require(load_json(root/'experiment.json')==plan,'FIR experiment changed')
    for name in SOURCES:require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'FIR source changed: '+name)
    require((root/'source/run_validation_engine.py').read_bytes()==(ROOT/'validation/tools/run_validation_engine.py').read_bytes(),'canonical metric changed')
    speech.source_check(base/'data')
    report=load_json(root/'result.json');old=load_json(base/'result.json')
    require(report['experiment_id']==plan['experiment_id'] and report['decision']==plan['decision'] and report['shipping_authority'] is False
            and report['effective_data_role']==ROLE and report['oracle_directions'] is True and report['real_array_recording'] is False and report['native_only'] is True,'FIR evidence authority changed')
    require(hex_digest(report['execution_source_revision'],40) and (revision is None or report['execution_source_revision']==revision),'stale FIR execution')
    require(report['source_manifest_sha256']==sha256((base/'manifest.json').read_bytes()) and report['source_evidence_revision']==old['execution_source_revision'],'stale base evidence')
    binary=(root/'array').read_bytes();require(binary[:4]==b'\x7fELF' and sha256(binary)==report['processor_sha256'],'wrong FIR binary')
    expected={key for key,*_ in speech.all_cases()};rows={r['case_id']:r for r in report['cases']};priors={r['case_id']:r for r in old['cases']}
    require(set(rows)==set(priors)==expected and len(rows)==len(report['cases'])==36,'FIR missing/duplicate case')
    for key,pair,name,target,interferer in speech.all_cases():
        row=rows[key];prior=priors[key];g=speech.geometry(name,target);n=len(g['positions_m'])
        require(row['pair']==pair and row['geometry']==name and row['target_degrees']==target and row['interferer_degrees']==interferer and row['original_role']==prior['role'] and row['effective_role']==ROLE,'FIR geometry/role changed')
        require(set(row['arms'])==set(ARMS),'missing/extra FIR arm')
        t=[v/32768 for v in raw(base,key,'target',n)[::n]];i=[v/32768 for v in raw(base,key,'interferer',n)[::n]]
        for mode in ARMS:
            dest=root/'cases'/key/mode;out=outputs(dest);delay=5+RADII.get(mode,0)
            cfg=speech.geometry_text(g,'lagrange3') if mode=='lagrange3' else config_text(g,mode)
            require((dest/'geometry.txt').read_bytes()==cfg,'FIR direction/config changed')
            require((dest/'repeat.f32').read_bytes()==(dest/'mixture.f32').read_bytes(),'FIR repeated audio changed')
            for tag in (*out,'repeat'):
                meta=load_json(dest/(tag+'.json'))
                require(meta['status']=='PASS' and meta['common_delay_samples']==delay and meta['interpolation']==(1 if mode=='lagrange3' else MODES[mode]) and meta['samples_processed']==speech.N and meta['mic_count']==n and meta['active_mask']==(1<<n)-1 and meta['shipping_authority'] is False,'FIR count/delay metadata changed')
                require(meta['state_bytes']<=plan['maximum_state_bytes'] and meta['steering_accepted']==0,'unregistered resource/steering')
            expected_metrics={'delay_samples':delay,**speech.metrics(t,i,out['target'],out['interferer'],out['mixture'],delay)}
            require(row['arms'][mode]==expected_metrics,'FIR metric recomputation failed')
            if mode=='lagrange3':
                require(row['arms'][mode]==prior['arms'][mode],'cubic baseline metric drift')
                for tag in out:require((dest/(tag+'.f32')).read_bytes()==(base/'cases'/key/mode/(tag+'.f32')).read_bytes(),'cubic output drift')
    require(report['summary']==summary(report['cases']),'FIR summary changed')
    return {'status':'VERIFIED','files':len(actual),'cases':36,'mixed_arms':108,'decision':report['decision'],'execution_source_revision':report['execution_source_revision']}


def negative(base,root):
    original=load_json(root/'result.json');answers={}
    mutations={'missing-case':lambda r:r['cases'].pop(), 'missing-arm':lambda r:r['cases'][0]['arms'].pop('fir17'),
               'promotion':lambda r:r.update(shipping_authority=True),'holdout-relabel':lambda r:r.update(effective_data_role='INDEPENDENT'),
               'wrong-delay':lambda r:r['cases'][0]['arms']['fir33'].update(delay_samples=5),
               'wrong-score':lambda r:r['cases'][0]['arms']['fir17'].update(component_sir_gain_db=999.0),
               'stale-source':lambda r:r.update(source_manifest_sha256='0'*64),
               'false-real-array':lambda r:r.update(real_array_recording=True)}
    with tempfile.TemporaryDirectory(prefix='fe-fir-negative-') as temp:
        scratch=Path(temp)/'evidence';shutil.copytree(root,scratch)
        for name,change in mutations.items():
            report=copy.deepcopy(original);change(report);write_json(scratch/'result.json',report);seal_output(scratch,report)
            try:verify(base,scratch,original['execution_source_revision'])
            except (ValueError,KeyError):answers[name]='REJECTED'
            else:raise ValueError('FIR semantic mutation accepted: '+name)
        write_json(scratch/'result.json',original)
        path=scratch/'cases'/original['cases'][0]['case_id']/'fir17/mixture.f32';path.write_bytes(path.read_bytes()[:-4]);seal_output(scratch,original)
        try:verify(base,scratch,original['execution_source_revision'])
        except ValueError:answers['truncated-pcm']='REJECTED'
        else:raise ValueError('truncated FIR accepted')
    return answers


class FIRSpeechTests(unittest.TestCase):
    def test_delays_in_fixed_span(self):
        for delay in (5,13,21):self.assertLessEqual(speech.EDGE+delay+(speech.N-2*speech.EDGE-5),speech.N)
    def test_latency_not_optimized(self):
        self.assertEqual([5+RADII.get(m,0) for m in ARMS],[5,13,21])
    def test_disclosed_not_holdout(self):
        self.assertEqual(load_json(PLAN)['speech_data_role'],ROLE)
    def test_reference_is_control(self):
        self.assertEqual(load_json(PLAN)['speech_arms'],list(ARMS))


def main():
    p=argparse.ArgumentParser();p.add_argument('--base-evidence',type=Path);p.add_argument('--output',type=Path);p.add_argument('--execution-source')
    p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true');p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FIRSpeechTests)).wasSuccessful() else 1
    require(a.base_evidence and a.output and hex_digest(a.execution_source,40),'required exact source/base/output')
    base=a.base_evidence.resolve();root=a.output.resolve()
    if a.negative_evidence:result=negative(base,root)
    elif a.verify:result=verify(base,root,a.execution_source)
    else:result=run(base,root,a.execution_source)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as error:
        print(f'FIR speech failed: {error}',file=__import__('sys').stderr);raise SystemExit(1)
