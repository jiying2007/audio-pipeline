#!/usr/bin/env python3
"""Frozen spatial weights on newly admitted speakers; no shipping promotion."""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from contracts import ROOT, load_json, require, sha256, hex_digest, verified_file
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal
from array_qualification import delays
from array_fir_checks import config_text as delay_config, taps as delay_taps
import speech_spatial as speech
import spatial_weights as spatial

HERE = Path(__file__).resolve().parent
PLAN = ROOT / '.github/research/frontend-evolution-v1/spatial-weights-v1.json'
ADMISSION = ROOT / '.github/research/frontend-evolution-v1/spatial-speech-admission-v1.json'
ARMS = ('fir33', 'diffuse-0.1', 'diffuse-1.0')
TAGS = ('target', 'interferer', 'mixture')
SOURCES = (*speech.SOURCE_NAMES, 'spatial_weights.py', 'speech_spatial_weights.py', 'array_fir_checks.py', 'speech_fir.py')
DELAY = 21


def source_check(path):
    review = load_json(ADMISSION); record = load_json(path/'source-receipt.json'); plan = load_json(PLAN)
    require(review['decision'] == 'ADMITTED_NEW_SPEAKERS_BEFORE_SCORING' and review['shipping_authority'] is False, 'source not admitted')
    require(record['source_id'] == review['source_id'] == 'librispeech-dev-clean-spatial-v1'
            and record['status'] == 'SOURCE_ONLY_NOT_ACOUSTIC_EVIDENCE' and record['shipping_authority'] is False, 'source authority')
    require(record['url'] == 'https://www.openslr.org/resources/12/dev-clean.tar.gz'
            and record['archive_sha256'] == plan['archive_sha256'] and record['plan_sha256'] == sha256(PLAN.read_bytes()), 'source plan changed')
    bound = {k:record[k] for k in ('archive_sha256','archive_md5','archive_bytes','speaker_selection')}
    bound['files_sha256'] = {k:v for k,v in record['files_sha256'].items() if k != 'decoder-version.txt'}
    require(sha256(json.dumps(bound, sort_keys=True, separators=(',',':'), allow_nan=False).encode()) == review['bound_source_sha256'], 'admitted source bytes changed')
    actual = {p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file()}
    require(actual == set(record['files_sha256']) | {'source-receipt.json'} and all(not p.is_symlink() for p in path.rglob('*')), 'source file set')
    for name,digest in record['files_sha256'].items():
        require(sha256(verified_file(path,name).read_bytes()) == digest, 'source file hash: '+name)
    rows = record['speaker_selection']
    require([r['speaker'] for r in rows] == review['speakers'] and len(rows) == 8
            and not set(review['speakers']) & set(review['excluded_prior_speakers']), 'speaker leakage/selection')
    for k,row in enumerate(rows):
        require((row['pair_index'],row['position'],row['role']) ==
                (k//2, 'target' if k%2 == 0 else 'interferer',plan['roles'][k//2]), 'source role changed')
        speech.values((path/row['window_file']).read_bytes(), 'h', speech.N)
        require(len(row['originals']) == 4, 'source utterance count')
        for original in row['originals']:
            require(speech.flac_info((path/'flac'/Path(original['member']).name).read_bytes())[3] == original['frames'], 'FLAC frame identity')
    return record


def matrix():
    for pair in range(4):
        for name in ('dual70','ula4-70','uca4-70'):
            for look,target,interferer in ((0,0,90),(60,60,150),(90,90,90),(30,45,120)):
                yield f'p{pair}-{name}-{look}-{target}-{interferer}',pair,name,look,target,interferer


def filters(g,arm):
    """Actual spatial floats, or an independent double delay-FIR reference."""
    n = len(g['positions_m'])
    if arm == 'fir33':
        common, ds = delays(g); require(common+16 == DELAY, 'control timing')
        kernels = [[(k,v/n) for k,v in delay_taps(d+16,16)] for d in ds]
        return delay_config(g,'fir33'), None, kernels
    load = {'diffuse-0.1':0.1, 'diffuse-1.0':1.0}[arm]
    bank = spatial.design(g,load)
    kernels = [[(bank['tap_start_samples']+k,v) for k,v in enumerate(row)] for row in bank['coefficients']]
    return spatial.config_text(g,bank),bank,kernels


def summaries(rows):
    answer = []
    for role in ('fresh-fixed-development','fresh-fixed-confirmation'):
        for name in speech.POSITIONS:
            for scene in ('separated-correct-look','co-located','look-mismatch'):
                chosen = [r for r in rows if r['role']==role and r['geometry']==name and
                          ('look-mismatch' if r['look_degrees']!=r['target_degrees'] else
                           'co-located' if r['target_degrees']==r['interferer_degrees'] else 'separated-correct-look')==scene]
                require(len(chosen)==(4 if scene=='separated-correct-look' else 2), 'subgroup count')
                for arm in ARMS:
                    ms = ('component_sir_gain_db','target_gain_db','target_relative_error_energy','canonical_si_sdr_db','output_peak')
                    answer.append({'role':role,'geometry':name,'scene':scene,'arm':arm,'cases':len(chosen),'speaker_pairs':2,
                       **{m:sum(r['arms'][arm][m] for r in chosen)/len(chosen) for m in ms},
                       'sir_change_vs_fir33_db':sum(r['arms'][arm]['component_sir_gain_db']-r['arms']['fir33']['component_sir_gain_db'] for r in chosen)/len(chosen)})
    return answer


def run(data,root,revision):
    require(hex_digest(revision,40) and not root.exists(), 'fresh output/exact execution identity required')
    source = source_check(data); plan = load_json(PLAN)
    root.mkdir(parents=True); shutil.copytree(data,root/'data'); (root/'source').mkdir()
    shutil.copyfile(PLAN,root/'experiment.json'); shutil.copyfile(ADMISSION,root/'admission.json')
    for name in SOURCES: shutil.copyfile(HERE/name,root/'source'/name)
    shutil.copyfile(ROOT/'validation/tools/run_validation_engine.py',root/'source/run_validation_engine.py')
    binaries = speech.build(root); rows = []; speakers = source['speaker_selection']
    # Design all fixed filters from geometry before observing any speech result.
    banks = {(name,look,arm):filters(speech.geometry(name,look),arm)
             for name in speech.POSITIONS for look in (0,30,60,90) for arm in ARMS}
    for key,pair,name,look,target,interferer in matrix():
        d = root/'cases'/key; d.mkdir(parents=True); n = len(speech.POSITIONS[name]); raw = {}
        originals = [speech.values((root/'data'/speakers[2*pair+j]['window_file']).read_bytes(),'h',speech.N) for j in (0,1)]
        gains = speech.gains(*[[v/32768 for v in x] for x in originals])
        for j,tag,angle in ((0,'target',target),(1,'interferer',interferer)):
            cfg = d/(tag+'-render.txt'); cfg.write_bytes(speech.render_config(speech.geometry(name,angle),gains[j]))
            temp = d/(tag+'.f64')
            run_logged([root/'renderer',cfg,root/'data'/speakers[2*pair+j]['window_file'],temp],d/(tag+'-render.log'))
            raw[tag] = [round(v*32768) for v in speech.values(temp.read_bytes(),'d',speech.N*n)]; temp.unlink()
            require(all(abs(v)<32760 for v in raw[tag]), 'component clips; no rescale')
        raw['mixture'] = [a+b for a,b in zip(raw['target'],raw['interferer'])]
        require(max(map(abs,raw['mixture']))<32760, 'mixture clips; no rescale')
        for tag in TAGS: (d/(tag+'.s16')).write_bytes(speech.encode(raw[tag],'h'))
        row = {'case_id':key,'pair':pair,'geometry':name,'role':plan['roles'][pair], 'look_degrees':look,
               'target_degrees':target,'interferer_degrees':interferer,'gains':list(gains),
               'input_peak':max(map(abs,raw['mixture']))/32768,'arms':{}}
        t,i = [[v/32768 for v in raw[tag][::n]] for tag in TAGS[:2]]
        for arm in ARMS:
            dest = d/arm; dest.mkdir(); cfg,bank,_ = banks[name,look,arm]; (dest/'geometry.txt').write_bytes(cfg)
            if bank is not None:
                write_json(dest/'bank.json',bank); write_json(dest/'response.json',{'realized_fir':spatial.response(bank)})
            for tag in (*TAGS,'repeat'):
                run_logged([root/'array',dest/'geometry.txt',d/(('mixture' if tag=='repeat' else tag)+'.s16'),
                            dest/(tag+'.f32'),dest/(tag+'.json')],dest/(tag+'.log'))
            out = {tag:speech.values((dest/(tag+'.f32')).read_bytes(),'f',speech.N) for tag in TAGS}
            require((dest/'mixture.f32').read_bytes()==(dest/'repeat.f32').read_bytes(), 'spatial PCM repeat')
            row['arms'][arm] = {'delay_samples':DELAY,**speech.metrics(t,i,out['target'],out['interferer'],out['mixture'],DELAY)}
        rows.append(row)
    report = {'schema_version':1,'experiment_id':plan['experiment_id'],'execution_source_revision':revision,
              'decision':plan['decision'],'status':'FIXED_SPATIAL_DIAGNOSTICS_COMPLETE','shipping_authority':False,
              'oracle_directions':True,'real_array_recording':False,'native_only':True,'binaries':binaries,
              'source_admission_sha256':sha256(ADMISSION.read_bytes()),'cases':rows,'summary':summaries(rows)}
    write_json(root/'result.json',report); seal_output(root,report)
    return {'status':report['status'],'cases':len(rows),'arms':len(rows)*len(ARMS),'next':'verify complete evidence separately'}


def verify(root,revision=None):
    actual = verify_seal(root); plan = load_json(PLAN); report = load_json(root/'result.json')
    require(load_json(root/'experiment.json')==plan and (root/'admission.json').read_bytes()==ADMISSION.read_bytes(), 'plan/admission drift')
    source = source_check(root/'data')
    require(report['decision']==plan['decision']=='FIXED_SPATIAL_REFERENCE_NO_PROMOTION' and report['shipping_authority'] is False
            and report['oracle_directions'] is True and report['real_array_recording'] is False and report['native_only'] is True
            and report['status']=='FIXED_SPATIAL_DIAGNOSTICS_COMPLETE' and report['experiment_id']==plan['experiment_id'], 'authority drift')
    require(hex_digest(report['execution_source_revision'],40) and (revision is None or report['execution_source_revision']==revision)
            and report['source_admission_sha256']==sha256(ADMISSION.read_bytes()), 'stale source/admission')
    for name in SOURCES: require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(), 'source changed: '+name)
    require((root/'source/run_validation_engine.py').read_bytes()==(ROOT/'validation/tools/run_validation_engine.py').read_bytes(), 'metric source drift')
    require(set(report['binaries'])=={'array','renderer'}, 'binary set')
    for name,digest in report['binaries'].items():
        blob = (root/name).read_bytes(); require(blob[:6]==b'\x7fELF\x02\x01' and sha256(blob)==digest, 'native ELF identity')
    rows = {r['case_id']:r for r in report['cases']}
    require(len(rows)==len(report['cases'])==48 and set(rows)=={r[0] for r in matrix()}, 'partial/duplicate cases')
    banks = {(name,look,arm):filters(speech.geometry(name,look),arm)
             for name in speech.POSITIONS for look in (0,30,60,90) for arm in ARMS}
    for key,pair,name,look,target,interferer in matrix():
        row = rows[key]; d = root/'cases'/key; n = len(speech.POSITIONS[name]); g = speech.geometry(name,look)
        require((row['pair'],row['geometry'],row['role'],row['look_degrees'],row['target_degrees'],row['interferer_degrees'])==
                (pair,name,plan['roles'][pair],look,target,interferer), 'role/geometry changed')
        require(set(row['arms'])==set(ARMS), 'missing/extra arm')
        originals = [speech.values((root/'data'/source['speaker_selection'][2*pair+j]['window_file']).read_bytes(),'h',speech.N) for j in (0,1)]
        gains = speech.gains(*[[v/32768 for v in x] for x in originals]); require(row['gains']==list(gains), 'gain changed')
        raw = {tag:speech.values((d/(tag+'.s16')).read_bytes(),'h',speech.N*n) for tag in TAGS}
        require(raw['mixture']==[a+b for a,b in zip(raw['target'],raw['interferer'])] and
                row['input_peak']==max(map(abs,raw['mixture']))/32768<32760/32768, 'input mixture/headroom changed')
        for j,tag,angle in ((0,'target',target),(1,'interferer',interferer)):
            geometry = speech.geometry(name,angle)
            require((d/(tag+'-render.txt')).read_bytes()==speech.render_config(geometry,gains[j]), 'render config drift')
            common,comp = delays(geometry)
            for mic,delay in enumerate(comp):
                taps = speech.sinc_taps(delay-common)
                for t in range(speech.EDGE,speech.N-speech.EDGE,503):
                    expected = sum(w*originals[j][t+k]*gains[j] for k,w in taps if 0<=t+k<speech.N)
                    require(abs(raw[tag][t*n+mic]-round(expected))<=1, 'render/source finite oracle')
        t,i = [[v/32768 for v in raw[tag][::n]] for tag in TAGS[:2]]
        for arm in ARMS:
            dest = d/arm; cfg,bank,kernels = banks[name,look,arm]
            require((dest/'geometry.txt').read_bytes()==cfg, 'bank config drift')
            if bank is not None:
                require(load_json(dest/'bank.json')==bank and load_json(dest/'response.json')=={'realized_fir':spatial.response(bank)}, 'coefficients/realized response drift')
            out = {tag:speech.values((dest/(tag+'.f32')).read_bytes(),'f',speech.N) for tag in TAGS}
            require((dest/'repeat.f32').read_bytes()==(dest/'mixture.f32').read_bytes() and
                    load_json(dest/'repeat.json')==load_json(dest/'mixture.json'), 'repeat mismatch')
            for tag in TAGS:
                meta = load_json(dest/(tag+'.json'))
                require(meta['status']=='PASS' and meta['interpolation']==(3 if arm=='fir33' else 4) and meta['samples_processed']==speech.N
                        and meta['mic_count']==n and meta['active_mask']==(1<<n)-1 and meta['common_delay_samples']==DELAY and
                        meta['sample_rate_hz']==16000 and meta['output_encoding']=='f32le-unclipped' and meta['direction']==g['direction']
                        and meta['shipping_authority'] is False and meta['steering_accepted']==0, 'native metadata identity')
                for sample in range(speech.EDGE,speech.N-speech.EDGE,503):
                    expected = sum(w*raw[tag][(sample-k)*n+mic]/32768 for mic,kernel in enumerate(kernels) for k,w in kernel)
                    require(abs(out[tag][sample]-expected)<=plan['oracle_error_bound'], 'spatial finite convolution oracle')
            require(row['arms'][arm]=={'delay_samples':DELAY,**speech.metrics(t,i,out['target'],out['interferer'],out['mixture'],DELAY)}, 'canonical/component metric changed')
    require(report['summary']==summaries(report['cases']), 'summary changed')
    return {'status':'VERIFIED_FIXED_SPATIAL_DIAGNOSTICS','files':len(actual),'cases':48,'mixed_arms':144,
            'decision':report['decision'],'shipping_authority':False}


def negatives(root,revision):
    original = load_json(root/'result.json'); answers = {}
    mutations = {'promotion':lambda r:r.update(shipping_authority=True), 'false-real-room':lambda r:r.update(real_array_recording=True),
        'false-estimated-direction':lambda r:r.update(oracle_directions=False), 'stale-execution':lambda r:r.update(execution_source_revision='0'*40),
        'missing-case':lambda r:r['cases'].pop(), 'duplicate-case':lambda r:r['cases'].append(r['cases'][0]),
        'role-leakage':lambda r:r['cases'][0].update(role='fresh-fixed-confirmation'),
        'missing-arm':lambda r:r['cases'][0]['arms'].pop('diffuse-0.1'),
        'forged-score':lambda r:r['cases'][0]['arms']['diffuse-0.1'].update(component_sir_gain_db=999),
        'wrong-look':lambda r:r['cases'][0].update(look_degrees=90)}
    with tempfile.TemporaryDirectory(prefix='fe-spatial-neg-') as temp:
        scratch = Path(temp)/'evidence'; shutil.copytree(root,scratch)
        def reject(name):
            seal_output(scratch,load_json(scratch/'result.json'))
            try: verify(scratch,revision)
            except (ValueError,KeyError): answers[name]='REJECTED'
            else: raise ValueError('semantic mutation accepted: '+name)
        for name,change in mutations.items():
            report = copy.deepcopy(original); change(report); write_json(scratch/'result.json',report); reject(name)
        write_json(scratch/'result.json',original)
        dest = scratch/'cases'/original['cases'][0]['case_id']/'diffuse-0.1'
        for name,path,replacement in [('truncated-pcm',dest/'mixture.f32',(dest/'mixture.f32').read_bytes()[:-4]),
                ('wrong-bank',dest/'bank.json',b'{}\n'),('wrong-realized-response',dest/'response.json',b'{}\n')]:
            old=path.read_bytes();path.write_bytes(replacement);reject(name);path.write_bytes(old)
    return answers


class SpeechSpatialTests(unittest.TestCase):
    def test_fixed_cardinality(self): self.assertEqual(len(list(matrix())),48)
    def test_scope_not_holdout_reuse(self): self.assertEqual(load_json(PLAN)['roles'],['fresh-fixed-development']*2+['fresh-fixed-confirmation']*2)
    def test_zero_aperture_rejected(self):
        g=copy.deepcopy(speech.geometry('dual70',0));g['positions_m'][1]=list(g['positions_m'][0])
        with self.assertRaises(ValueError):spatial.design(g,.1)
    def test_admission_excludes_prior(self):
        a=load_json(ADMISSION);self.assertEqual(len(a['speakers']),8);self.assertFalse(set(a['speakers'])&set(a['excluded_prior_speakers']))
    def test_no_latency_fit(self): self.assertEqual(DELAY,load_json(PLAN)['common_delay_samples'])
    def test_fixed_negative_controls(self): self.assertEqual(sum(t==i for _,_,_,_,t,i in matrix()),12)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--execution-source');p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true');p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:
        require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SpeechSpatialTests)).wasSuccessful(), 'spatial speech tests');return
    require(a.output is not None and hex_digest(a.execution_source,40), 'output/execution identity required')
    existed=a.output.exists()
    try:
        result=negatives(a.output,a.execution_source) if a.negative_evidence else verify(a.output,a.execution_source) if a.verify else run(a.source,a.output,a.execution_source)
        print(json.dumps(result,sort_keys=True))
    except Exception as error:
        if not existed and not a.verify and not a.negative_evidence and a.output.exists():write_json(a.output/'failure.json',{'error':str(error),'shipping_authority':False})
        raise

if __name__=='__main__': main()
