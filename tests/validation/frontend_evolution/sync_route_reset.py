#!/usr/bin/env python3
"""Causal diagnostic for the production route_jump -> AEC reset semantic."""
from __future__ import annotations
import argparse, array, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import sync_faults as sync
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/sync-route-reset-v1.json'
DECISION='SYNC_ROUTE_RESET_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
FAULTS=sync.FAULTS
LABELS=sync.LABELS
N=sync.N

def predecessor(root:Path,revision:str)->dict:
    verify_seal(root)
    r=load_json(root/'result.json')
    require(r['experiment_id']=='FE04-SYNC-FAULTS-V1' and r['decision']=='SYNC_FAULTS_DIAGNOSTIC_NO_PROMOTION','wrong predecessor')
    require(r['shipping_authority'] is False and r['data_role']==ROLE and r['execution_source_revision']==revision,'predecessor authority/revision')
    require(r['case_count']==6 and r['arms']==3 and r['route_jump_resets_aec'] is False,'predecessor matrix/reset drift')
    require(r['timestamp_assistance'] is False and r['res_enabled'] is False,'predecessor scope drift')
    expected={(p,f) for p in (0,1) for f in FAULTS}
    require({(c['pair'],c['fault']) for c in r['cases']}==expected,'predecessor case set')
    for c in r['cases']:
        inp=root/c['input'];require(inp.is_file() and sha256(inp.read_bytes())==c['input_receipt']['sha256'],'predecessor input')
        d=root/'cases'/c['case_id'];meta=load_json(d/'sync.json')
        require(meta['route_jump_resets_aec'] is False and meta.get('aec_resets',0)==0,'predecessor reset semantics')
        rows=sync.trace_rows(d/'sync.csv',c['fault'],'sync',N//sync.HOP)
        require(c['arms']['sync']['alignment']==sync.alignment(rows,c['fault']),'predecessor alignment')
    return r

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def run_one(binary:Path,label:str,pred_root:Path,pred_case:dict,dest:Path)->dict:
    under_arm=label=='arm';inp=pred_root/pred_case['input'];fault=pred_case['fault']
    sync.execute(binary,'sync-reset',fault,inp,dest,under_arm)
    sync.execute(binary,'sync-reset',fault,inp,dest.with_name(dest.name+'-repeat'),under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),'reset repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=sync.trace_rows(dest.with_suffix('.csv'),fault,'sync-reset',N//sync.HOP)
    meta=load_json(dest.with_suffix('.json'));events=sum(x['route_jump'] for x in rows)
    require(meta['status']=='PASS' and meta['arm']=='public-sync-reset' and meta['route_jump_resets_aec'] is True,'reset meta')
    require(meta['aec_resets']==meta['route_jumps']==events,'reset count')
    require(meta['source_revision']==pred_case['_revision'] and meta['samples']==N,'reset identity')
    return {'meta':meta,'rows':rows,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
            'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def engineering(root:Path,binaries:dict,pred_root:Path,pred:dict,revision:str)->dict:
    fixed=case_map(pred)['p0-route'];fixed=dict(fixed);fixed['_revision']=revision
    records={}
    for label in LABELS:
        d=root/label;d.mkdir(parents=True)
        rec=run_one(binaries[label],label,pred_root,fixed,d/'reset')
        require(rec['meta']['aec_resets']>=1,'fixed route case did not execute reset')
        records[label]={'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256'],
                        'aec_resets':rec['meta']['aec_resets'],'route_jumps':rec['meta']['route_jumps']}
    # Candidate-specific common-prefix future causality on native.
    data=array.array('f');data.frombytes((pred_root/fixed['input']).read_bytes())
    if sys.byteorder!='little':data.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        data[4*k]*=-1.0;data[4*k+1]*=-1.0;data[4*k+2]*=-1.0;data[4*k+3]*=-1.0
    if sys.byteorder!='little':data.byteswap()
    future=root/'future-input.f32';future.write_bytes(data.tobytes())
    sync.execute(binaries['native'],'sync-reset','route',future,root/'future')
    a=sync.floats(root/'native/reset.f32',N*2);b=sync.floats(root/'future.f32',N*2)
    require(a[:(cutoff-2*sync.HOP)*2]==b[:(cutoff-2*sync.HOP)*2] and a[(cutoff+2*sync.HOP)*2:]!=b[(cutoff+2*sync.HOP)*2:],'reset future causality')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,sync.command(binaries['native'],'sync-reset','route',bad,root/'bad'))),capture_output=True)
    require(p.returncode!=0,'partial reset input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/reset.f32').read_bytes()
    p=subprocess.run(list(map(str,sync.command(binaries['native'],'sync-reset','route',pred_root/fixed['input'],root/'native/reset'))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/reset.f32').read_bytes(),'reset overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,'invalid_rejected':True,'overwrite_rejected':True}
    write_json(root/'result.json',result);return result

def metrics_for_input(inp:Path,out:Path,fault:str)->dict:
    source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4])
    raw=sync.floats(out,N*2);return sync.metrics(target,echo,list(raw[0::2]),fault)

def run(pred_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor(pred_root,revision);root.mkdir(parents=True)
    shutil.copyfile(PLAN,root/'experiment.json');(root/'source').mkdir()
    for p in (HERE/'sync_route_reset.py',HERE/'sync_fault_runner.c',HERE/'sync_faults.py'):
        shutil.copyfile(p,root/'source'/p.name)
    binaries={label:sync.build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,pred_root,pred,revision)
    cases=[]
    for pc in sorted(pred['cases'],key=lambda c:(c['pair'],FAULTS.index(c['fault']))):
        d=root/'cases'/pc['case_id'];d.mkdir(parents=True)
        tagged=dict(pc);tagged['_revision']=revision
        rec=run_one(binaries['native'],'native',pred_root,tagged,d/'reset')
        pred_d=pred_root/'cases'/pc['case_id']
        require((d/'reset.csv').read_bytes()==(pred_d/'sync.csv').read_bytes(),'AEC reset changed SYNC/Activity trace')
        rows=rec['rows'];events=sum(x['route_jump'] for x in rows)
        control_bytes=(pred_d/'sync.f32').read_bytes();candidate_bytes=(d/'reset.f32').read_bytes()
        control_raw=sync.floats(pred_d/'sync.f32',N*2);candidate_raw=sync.floats(d/'reset.f32',N*2)
        require(list(control_raw[1::2])==list(candidate_raw[1::2]),'AEC reset changed reference samples')
        if events==0:require(control_bytes==candidate_bytes,'zero-route case changed despite no reset')
        control_metrics=metrics_for_input(pred_root/pc['input'],pred_d/'sync.f32',pc['fault'])
        require(control_metrics==pc['arms']['sync']['metrics'],'predecessor metric drift')
        candidate_metrics=metrics_for_input(pred_root/pc['input'],d/'reset.f32',pc['fault'])
        reset_frames=[x['frame'] for x in rows if x['route_jump']]
        cases.append({'case_id':pc['case_id'],'pair':pc['pair'],'fault':pc['fault'],
          'predecessor_route_jump_events':events,'reset_count':rec['meta']['aec_resets'],'reset_frames':reset_frames,
          'zero_event_output_identity':control_bytes==candidate_bytes,
          'control_metrics':control_metrics,'candidate_metrics':candidate_metrics,
          'delta_final_far_db':None if control_metrics['final_far_ratio_db'] is None or candidate_metrics['final_far_ratio_db'] is None
              else candidate_metrics['final_far_ratio_db']-control_metrics['final_far_ratio_db'],
          'control_output_sha256':sha256(control_bytes),'candidate_output_sha256':sha256(candidate_bytes),
          'trace_sha256':rec['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE04-SYNC-ROUTE-RESET-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'predecessor_manifest_sha256':sha256((pred_root/'manifest.json').read_bytes()),
      'predecessor_decision':pred['decision'],'route_jump_resets_aec':True,'activity_reset':False,'sync_reset':False,
      'res_enabled':False,'timestamp_assistance':False,'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(pred_root:Path,root:Path,revision:str,predecessor_verified=False)->dict:
    verify_seal(root);pred=load_json(pred_root/'result.json') if predecessor_verified else predecessor(pred_root,revision)
    r=load_json(root/'result.json');require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'plan drift')
    require(r['experiment_id']=='FE04-SYNC-ROUTE-RESET-V1' and r['decision']==DECISION and r['shipping_authority'] is False and r['data_role']==ROLE,'authority drift')
    require(r['execution_source_revision']==revision and r['case_count']==6 and r['predecessor_manifest_sha256']==sha256((pred_root/'manifest.json').read_bytes()),'identity drift')
    require(r['route_jump_resets_aec'] is True and r['activity_reset'] is False and r['sync_reset'] is False
      and r['res_enabled'] is False and r['timestamp_assistance'] is False,'scope drift')
    for name in ('sync_route_reset.py','sync_fault_runner.c','sync_faults.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'source drift '+name)
    expected=case_map(pred);require({c['case_id'] for c in r['cases']}==set(expected),'case set')
    for c in r['cases']:
        pc=expected[c['case_id']];d=root/'cases'/c['case_id'];pred_d=pred_root/'cases'/c['case_id']
        rows=sync.trace_rows(d/'reset.csv',c['fault'],'sync-reset',N//sync.HOP);events=sum(x['route_jump'] for x in rows)
        require((d/'reset.csv').read_bytes()==(pred_d/'sync.csv').read_bytes(),'trace causal guard')
        meta=load_json(d/'reset.json');require(meta['route_jump_resets_aec'] is True and meta['aec_resets']==meta['route_jumps']==events,'reset receipt')
        control=sync.floats(pred_d/'sync.f32',N*2);candidate=sync.floats(d/'reset.f32',N*2)
        require(list(control[1::2])==list(candidate[1::2]),'reference causal guard')
        if events==0:require((pred_d/'sync.f32').read_bytes()==(d/'reset.f32').read_bytes(),'zero-event identity')
        cm=metrics_for_input(pred_root/pc['input'],pred_d/'sync.f32',c['fault']);nm=metrics_for_input(pred_root/pc['input'],d/'reset.f32',c['fault'])
        require(c['control_metrics']==cm and c['candidate_metrics']==nm,'metric recomputation')
        require(c['predecessor_route_jump_events']==events and c['reset_count']==events
          and c['reset_frames']==[x['frame'] for x in rows if x['route_jump']],'event/reset binding')
        require(c['control_output_sha256']==sha256((pred_d/'sync.f32').read_bytes())
          and c['candidate_output_sha256']==sha256((d/'reset.f32').read_bytes())
          and c['trace_sha256']==sha256((d/'reset.csv').read_bytes()),'case hash binding')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'));require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('sync-fault-'+label)).read_bytes()),'binary identity')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','engineering receipt')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'Arm ELF')
    return {'status':'VERIFIED_SYNC_ROUTE_RESET','cases':6,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(pred_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','reset-count','binary');rejected=[]
    predecessor(pred_root,revision)
    with tempfile.TemporaryDirectory(prefix='sync-reset-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['candidate_metrics']['final_far_ratio_db']=0.0
            elif kind=='reset-count':rr['cases'][0]['reset_count']+=1
            else:
                case=rr['cases'][0]['case_id'];pth=copy/'cases'/case/'reset.f32' if kind=='output' else copy/'cases'/case/'reset.csv' if kind=='trace' else copy/'sync-fault-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(pred_root,copy,revision,predecessor_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed reset negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        groups.append({'fault':fault,'cases':len(rows),'reset_counts':[x['reset_count'] for x in rows],
          'control_mean_final_far_db':sum(x['control_metrics']['final_far_ratio_db'] for x in rows)/len(rows),
          'candidate_mean_final_far_db':sum(x['candidate_metrics']['final_far_ratio_db'] for x in rows)/len(rows),
          'delta_final_far_db':[x['delta_final_far_db'] for x in rows],
          'zero_event_output_identity':[x['zero_event_output_identity'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--predecessor',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'revision')
    if a.negative_evidence:r=negatives(a.predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.predecessor,a.output,a.execution_source)
    else:
        r=run(a.predecessor,a.output,a.execution_source);print('SYNC_ROUTE_RESET_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_SYNC_ROUTE_RESET','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
