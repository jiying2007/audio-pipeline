#!/usr/bin/env python3
"""D9 bounded isolated C replay of the immutable disclosed D2 input archive."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import signal
import statistics
import struct
import subprocess
import tarfile
import time
import zipfile
import dualmic_gain_d2 as d2

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT/'docs/research/frontend-evolution-v1/DUALMIC_GATED_RISE_D9_PLAN.zh-CN.md'
ZIP_HASH = 'a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d'
BEFORE = '        if (!allow_gain_increase && target_gain > 1.0f) target_gain = 1.0f;'
AFTER = BEFORE+'\n        if (!allow_gain_increase && target_gain > state->gain) target_gain = state->gain;'

def need(value, message):
    if not value: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def desc(raw): return {'bytes':len(raw),'sha256':sha(raw)}
def dump(path, value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n')
def timeout(*_): raise TimeoutError('D9_PHASE_300_SECONDS_EXCEEDED')
def phase(): signal.alarm(300)
def invoke(args):
    done=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30,check=False)
    need(done.returncode==0,'D9_COMMAND_FAILED '+str(args)+' '+done.stdout.decode(errors='replace'))
    return done.stdout.decode()
def floats(raw): return struct.unpack('<%df'%(len(raw)//4),raw)

def audit_candidate(input_raw, output_raw, trace, controls, target, limit):
    signal_values=floats(input_raw);records=list(struct.iter_unpack('<ff',trace));counts=[0,0]
    n=len(controls)
    for arm in range(2):
        expected=bytearray();previous=1.0
        for frame,(allow,reset,_,_) in enumerate(controls):
            before,after=records[arm*n+frame]
            need(d2.bits(before)==d2.bits(1.0 if reset or frame==0 else previous),'D9_STATE_CONTINUITY')
            signal_frame=signal_values[frame*160:(frame+1)*160]
            obs,_=d2.gain_observation(signal_frame,before,allow,target,limit)
            desired=obs['target_gain']
            if arm and not allow:desired=min(desired,before)
            alpha=d2.f32(.25 if desired<before else .015)
            predicted=d2.f32(before+d2.f32(alpha*d2.f32(desired-before)))
            need(d2.bits(after)==d2.bits(predicted),'D9_CANDIDATE_FORMULA')
            gain=min(after,1.) if not allow else after
            peak=obs['input_peak']
            if d2.f32(peak*gain)>limit and peak>d2.f32(1e-6):gain=d2.f32(limit/peak)
            for x in signal_frame:
                product=d2.f32(x*gain);counts[arm]+=int(product < -limit or product > limit)
                expected.extend(struct.pack('<f',max(-limit,min(limit,product))))
            previous=after
        need(bytes(expected)==output_raw[arm],'D9_OUTPUT_FORMULA')
    return counts

def main():
    p=argparse.ArgumentParser();p.add_argument('--zip',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    start=time.monotonic();signal.signal(signal.SIGALRM,timeout);phase()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    need(a.zip.stat().st_size==474165229,'D9_ZIP_SIZE')
    h=hashlib.sha256()
    with a.zip.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    need(h.hexdigest()==ZIP_HASH,'D9_ZIP_HASH')
    source_revision=invoke(['git','-C',str(ROOT),'rev-parse','HEAD']).strip()
    need(not invoke(['git','-C',str(ROOT),'status','--porcelain']),'D9_DIRTY_SOURCE')
    z=zipfile.ZipFile(a.zip)
    need(len(z.infolist())==3551 and sum(x.file_size for x in z.infolist())==861385743,'D9_ZIP_INVENTORY')
    need(len(set(z.namelist()))==3551,'D9_DUPLICATE_MEMBER')
    lock=json.loads((ROOT/d2.LOCK_NAME).read_text())
    old=json.loads(z.read('gain-d2/report.json'))
    need([x['key'] for x in old['cases']]==[x['catalog']['key'] for x in lock['cases']],'D9_CASE_ORDER')
    archive=z.read('build/exact-source.tar')
    with tarfile.open(fileobj=io.BytesIO(archive)) as t:
        original=t.extractfile('src/enhance/ap_agc.c').read()
        header=t.extractfile('src/enhance/ap_enhance.h').read()
    need(original==(ROOT/'src/enhance/ap_agc.c').read_bytes(),'D9_BASE_SOURCE_DRIFT')
    need(header==(ROOT/'src/enhance/ap_enhance.h').read_bytes(),'D9_HEADER_DRIFT')
    text=original.decode();need(text.count(BEFORE)==1,'D9_TRANSFORM_COUNT')
    candidate=text.replace(BEFORE,AFTER).replace('ap_agc_','d9_agc_').replace('d9_agc_state_t','ap_agc_state_t')
    need(candidate.replace('d9_agc_','ap_agc_').replace(AFTER,BEFORE)==text,'D9_TRANSFORM_REVERSE')
    (out/'candidate.c').write_text(candidate);(out/'baseline.c').write_bytes(original)
    (out/'enhance').mkdir();(out/'enhance/ap_enhance.h').write_bytes(header)
    driver=Path(__file__).with_suffix('.c');(out/'driver.c').write_bytes(driver.read_bytes())
    flags=['cc','-std=c11','-O2','-ffp-contract=off','-DAP_BUILD_STAGE_AGC=1','-I'+str(out)]
    argv=flags+[str(out/'baseline.c'),str(out/'candidate.c'),str(out/'driver.c'),'-lm','-o',str(out/'replay')]
    compiler=invoke(['cc','--version']);compile_log=invoke(argv)
    selftest=json.loads(invoke([str(out/'replay'),'--self-test']))
    dump(out/'build.json',{'source_revision':source_revision,'source_archive':desc(archive),'baseline_source':desc(original),'candidate_source':desc(candidate.encode()),'header':desc(header),'driver':desc(driver.read_bytes()),'compiler':compiler,'argv':argv,'compile_log':compile_log,'selftest':selftest,'replay':desc((out/'replay').read_bytes()),'plan':desc(PLAN.read_bytes())})
    phase();cases=[];cpu=[[],[]];total_frames=0;gated_rises=0
    for index,entry in enumerate(lock['cases']):
        case=entry['catalog'];folder=out/'cases'/case['key'];folder.mkdir(parents=True)
        taps='result/cases/'+case['key']+'/taps/'
        for name,expected in entry['parent_taps'].items():
            raw=z.read(taps+name);need(desc(raw)==expected,'D9_INPUT_HASH '+name);(folder/name).write_bytes(raw)
        controls=d2.control_bytes(folder/'control.csv',case);(folder/'control.bin').write_bytes(controls)
        args=[str(out/'replay'),str(folder/'ns_output.f32le'),str(folder/'agc_output.f32le'),str(folder/'control.bin'),str(folder/'baseline.f32le'),str(folder/'candidate.f32le'),str(folder/'trace.bin'),case['profile'],str(case['frames'])]
        runtime=json.loads(invoke(args));dump(folder/'runtime.json',runtime)
        total_frames+=runtime['frames'];gated_rises+=runtime['baseline_gated_rise_frames']
        for arm in range(2):cpu[arm].append(runtime['cpu_seconds'][arm])
        base=(folder/'baseline.f32le').read_bytes();candidate_raw=(folder/'candidate.f32le').read_bytes()
        need(base==(folder/'agc_output.f32le').read_bytes(),'D9_BASELINE_BYTES')
        ctl=list(struct.iter_unpack('<IIff',controls))
        if all(row[0] for row in ctl):need(base==candidate_raw,'D9_ALLOW_TRUE_NEUTRALITY')
        trace=(folder/'trace.bin').read_bytes();need(len(trace)==case['frames']*16,'D9_TRACE_SIZE')
        clamps=audit_candidate((folder/'ns_output.f32le').read_bytes(),[base,candidate_raw],trace,ctl,runtime['target_linear'],runtime['limiter_linear'])
        reference=None;reason='no_clean_near_reference'
        if entry['clean_near'] is not None:
            raw=z.read('result/originals/A/'+case['inputs']['clean_near']);need(desc(raw)==entry['clean_near'],'D9_REFERENCE_HASH')
            reference=[x[0]/32768 for x in struct.iter_unpack('<h',raw)]
        if case['group']=='C':reason='C_has_no_admitted_clean_near_reference'
        stages={name:d2.d1.measure_lane(floats(raw),160,case['samples'],reference,reason,True) for name,raw in [('baseline',base),('candidate',candidate_raw)]}
        need(stages['baseline']==old['cases'][index]['stages']['replay_final'],'D9_BASELINE_CANONICAL_SCORE')
        delta=d2.d1.stage_delta(stages,'baseline','candidate','gated_state_rise_hold_total_intervention')
        cases.append({'key':case['key'],'profile':case['profile'],'scenario':case['scenario'],'group':case['group'],'stages':stages,'delta':delta,'runtime':runtime,'actual_clamp_sample_counts':clamps,'all_allow_true':all(row[0] for row in ctl),'changed_samples':sum(x!=y for x,y in zip(struct.iter_unpack('<I',base),struct.iter_unpack('<I',candidate_raw))),'files':{p.name:desc(p.read_bytes()) for p in folder.iterdir()}})
        need(sum(p.stat().st_size for p in out.rglob('*') if p.is_file())<=256*1024*1024,'D9_OUTPUT_BUDGET')
    need(total_frames==35916 and len(cases)==60,'D9_MATRIX')
    phase()
    scores=[c['delta']['common']['near_si_sdr_change_db'] for c in cases if c['delta']['common']['near_si_sdr_change_db'] is not None]
    windows=[w['near_si_sdr_change_db'] for c in cases for w in c['delta']['one_second_windows'] if w['near_si_sdr_change_db'] is not None]
    double=[c['delta']['common']['near_si_sdr_change_db'] for c in cases if c['scenario'] in ('doubletalk-nominal','doubletalk-weak')]
    energy_bad=[]
    for c in cases:
        if c['scenario'] not in ('far-only','path-change','render-gap') and c['group']!='C':continue
        b,t=c['stages']['baseline'],c['stages']['candidate']
        spans=[('common',b['common'],t['common']),('native',b['native_whole_buffer_energy'],t['native_whole_buffer_energy'])]+[(str(i),x,y) for i,(x,y) in enumerate(zip(b['one_second_windows'],t['one_second_windows']))]
        for label,x,y in spans:
            for metric in ('rms_dbfs','peak'):
                if y[metric]>x[metric]:energy_bad.append({'case':c['key'],'span':label,'metric':metric,'baseline':x[metric],'candidate':y[metric]})
    totals=[[sum(row[r] for row in cpu[a]) for r in range(7)] for a in range(2)]
    med=[statistics.median(row) for row in totals];ratio=med[1]/med[0]
    clip_bad=[]
    for c in cases:
        folder=out/'cases'/c['key']
        counts=c['actual_clamp_sample_counts']
        if counts[1]>counts[0]:clip_bad.append(c['key'])
    predicates={'common_nonregression':all(x>=0 for x in scores),'window_nonregression':all(x>=0 for x in windows),'doubletalk_1db':any(x>=1 for x in double),'far_and_c_energy_nonincrease':not energy_bad,'limit_sample_nonincrease':not clip_bad,'host_cpu_10pct':ratio<=1.1}
    report={'experiment':'FE-DUALMIC-GATED-RISE-D9','measurement_valid':True,'decision':'REVIEW_NO_PROMOTION' if all(predicates.values()) else 'NO_ADVANCE','promotion_allowed':False,'source_revision':source_revision,'input_zip_sha256':ZIP_HASH,'data_role':'disclosed-regression','endpoint':'original Float32 AGC output; frozen upstream and control, not full independently evolving pipeline','cases':cases,'counts':{'cases':60,'frames':total_frames,'samples':5746560,'windows':sum(len(c['delta']['one_second_windows']) for c in cases),'reference_common':len(scores),'baseline_gated_rise_frames':gated_rises},'screen':predicates,'energy_violations':energy_bad,'limit_sample_violations':clip_bad,'host_cpu':{'total_seconds_repetitions':totals,'median_seconds':med,'candidate_baseline_ratio':ratio,'scope':'C thread CPU including memcpy/init/reset/bridge checks; excludes disk, compile, Python; no SSC305 claim'},'common_delta_db':{'min':min(scores),'median':statistics.median(scores),'max':max(scores)},'elapsed_seconds':time.monotonic()-start}
    dump(out/'report.json',report)
    # Readback the saved JSON and every retained per-case payload without repairs.
    need(json.loads((out/'report.json').read_text())==report,'D9_REPORT_READBACK')
    for c in cases:
        folder=out/'cases'/c['key']
        for name,expected in c['files'].items():need(desc((folder/name).read_bytes())==expected,'D9_PAYLOAD_READBACK')
    dump(out/'completion.json',{'report':desc((out/'report.json').read_bytes()),'output_bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),'elapsed_seconds':time.monotonic()-start,'status':'COMPLETE','all_case_payloads_readback':True})
    signal.alarm(0)
    print(json.dumps({k:report[k] for k in ('experiment','decision','counts','screen','host_cpu','common_delta_db','elapsed_seconds')},indent=2))
if __name__=='__main__':main()
