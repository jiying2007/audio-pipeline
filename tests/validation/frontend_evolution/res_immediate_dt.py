#!/usr/bin/env python3
"""Immediate detected-double-talk protection for the existing time-domain RES."""
from __future__ import annotations
import argparse, array, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import aec_res_collab as base
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/res-immediate-dt-v1.json'
RUNNER=HERE/'res_immediate_dt_runner.c'
DECISION='RES_IMMEDIATE_DT_PROTECTION_DIAGNOSTIC_NO_PROMOTION'
ROLE=base.ROLE
RATE,HOP,N=base.RATE,base.HOP,base.N
FAULTS=base.FAULTS
LABELS=base.LABELS
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off',
        '-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f']
ENVELOPE_RATIO=10.0**0.1

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def predecessor_receipt(sync_root:Path,reset_root:Path,exact_root:Path,res_root:Path,
                        revision:str,full:bool)->dict:
    if full:
        v=base.verify(sync_root,reset_root,exact_root,res_root,revision)
        require(v['status']=='VERIFIED_AEC_RES_COLLAB','current RES predecessor verify')
    else:
        for root in (sync_root,reset_root,exact_root,res_root):
            verify_seal(root)
    r=load_json(res_root/'result.json')
    require(r['experiment_id']=='FE04-AEC-RES-COLLAB-V1' and r['case_count']==6
      and r['decision']=='AEC_RES_COLLAB_DIAGNOSTIC_NO_PROMOTION'
      and r['execution_source_revision']==revision,'current RES predecessor identity')
    return {
      'sync_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'reset_manifest_sha256':sha256((reset_root/'manifest.json').read_bytes()),
      'exact_manifest_sha256':sha256((exact_root/'manifest.json').read_bytes()),
      'res_manifest_sha256':sha256((res_root/'manifest.json').read_bytes()),
      'res_result_sha256':sha256((res_root/'result.json').read_bytes()),
      'source_revision':revision
    }

def build(root:Path,revision:str,label:str)->Path:
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    definition='-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f'
    b=root/('build-'+label)
    opts=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(flags+['-ffp-contract=off',definition]),
      '-DAP_BUILD_SOURCE_REVISION='+revision,'-DAP_BUILD_PIPELINE=OFF',
      '-DAP_MODULES=SYNC,ACTIVITY,AEC,RES','-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR',
      '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF',
      '-DAP_ENABLE_LINUX_RUNTIME=OFF','-DAP_BUILD_MAX_AEC_TAIL_MS=64',
      '-DAP_BUILD_MAX_DELAY_MS=120','-DAP_STRICT_WARNINGS=ON']
    if arm:opts+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(opts,root/(label+'-configure.log'))
    run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('res-immediate-dt-'+label)
    cmd=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),RUNNER,b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'));run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-library.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,
      'processor_sha256':sha256(binary.read_bytes()),
      'library_sha256':sha256((root/(label+'-library.a')).read_bytes()),
      'compiler':cc,'sanitized':san,'arm':arm,
      'res_near_protection_release_alpha':1.0,
      'compile_definition':definition,'configure':list(map(str,opts)),'link':list(map(str,cmd))})
    shutil.rmtree(b);return binary

def command(binary:Path,fault:str,inp:Path,dest:Path,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,fault,inp,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary:Path,fault:str,inp:Path,dest:Path,under_arm:bool=False)->None:
    run_logged(command(binary,fault,inp,dest,under_arm),dest.with_suffix('.log'))

def run_one(binary:Path,label:str,inp:Path,fault:str,dest:Path)->dict:
    under_arm=label=='arm'
    execute(binary,fault,inp,dest,under_arm)
    execute(binary,fault,inp,dest.with_name(dest.name+'-repeat'),under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==
                dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),
                'immediate-DT repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=base.trace_rows(dest.with_suffix('.csv'),fault);meta=load_json(dest.with_suffix('.json'))
    expected=1 if fault=='route' else 0
    require(meta['status']=='PASS' and meta['timestamp_authority'] is True
      and meta['route_jump_resets_aec'] is True and meta['route_jump_resets_res'] is False
      and meta['res_quality']=='FULL','immediate-DT meta')
    require(meta['timestamp_observations']==N//HOP and meta['route_jumps']==expected
      and meta['aec_resets']==expected and meta['underruns']==0,'immediate-DT counters')
    require(meta['double_talk_gain_lt_0_99_frames']==0
      and meta['double_talk_gain_lt_0_95_frames']==0,'detected-DT not fully protected')
    return {'rows':rows,'meta':meta,
      'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
      'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def stable_trace_identity(candidate:list[dict],predecessor:list[dict])->dict:
    require(len(candidate)==len(predecessor)==N//HOP,'trace length')
    ignored={'res_gain','post_output_energy'}
    mismatches=0
    for a,b in zip(candidate,predecessor):
        for key in base.HEADER:
            if key in ignored:continue
            if a[key]!=b[key]:mismatches+=1
    require(mismatches==0,'candidate changed non-RES predecessor trace')
    return {'non_res_trace_field_mismatches':0,'non_res_trace_identity':True}

def lane_identity(candidate:Path,predecessor:Path)->dict:
    cw=base.words(candidate);pw=base.words(predecessor)
    require(len(cw)==len(pw)==N*3,'packed candidate/predecessor size')
    pre=sum(a!=b for a,b in zip(cw[0::3],pw[0::3]))
    ref=sum(a!=b for a,b in zip(cw[2::3],pw[2::3]))
    require(pre==0,'candidate changed pre-RES AEC lane')
    require(ref==0,'candidate changed reference lane')
    return {'pre_res_aec_bit_mismatches':pre,'reference_bit_mismatches':ref,
      'pre_res_aec_bit_identity':True,'reference_bit_identity':True}

def dt_causal_identity(candidate:Path,predecessor:Path,rows:list[dict])->dict:
    cw=base.words(candidate);pw=base.words(predecessor)
    cpre=cw[0::3];cpost=cw[1::3];ppost=pw[1::3]
    first=next((r['frame'] for r in rows if r['used_dt']),None)
    require(first is not None,'no detected-DT coverage')
    prefix_samples=first*HOP
    prefix=sum(a!=b for a,b in zip(cpost[:prefix_samples],ppost[:prefix_samples]))
    require(prefix==0,'candidate changed output before first detected-DT frame')
    dt_sample_mismatches=0;dt_frames=0
    for row in rows:
        if not row['used_dt']:continue
        dt_frames+=1
        require(row['res_gain']==1.0,'candidate detected-DT gain is not unity')
        lo=row['frame']*HOP;hi=lo+HOP
        dt_sample_mismatches+=sum(a!=b for a,b in zip(cpost[lo:hi],cpre[lo:hi]))
    require(dt_frames>0 and dt_sample_mismatches==0,'candidate detected-DT output not AEC-identical')
    return {'first_detected_dt_frame':first,'pre_dt_post_bit_mismatches':prefix,
      'detected_dt_frames':dt_frames,'detected_dt_post_vs_pre_bit_mismatches':dt_sample_mismatches,
      'detected_dt_unity_gain':True}

def dt_intervals(rows:list[dict])->list[tuple[int,int]]:
    out=[];i=0
    while i<len(rows):
        if not rows[i]['used_dt']:
            i+=1;continue
        start=i
        while i<len(rows) and rows[i]['used_dt']:i+=1
        out.append((start,i))
    return out

def reacquisition(candidate:list[dict],predecessor:list[dict])->list[dict]:
    runs=dt_intervals(candidate);require(runs==dt_intervals(predecessor),'DT runs changed')
    out=[]
    for idx,(start,end) in enumerate(runs):
        stop=runs[idx+1][0] if idx+1<len(runs) else len(candidate)
        ge099=ge095=within=None
        for frame in range(end,stop):
            if candidate[frame]['used_dt']:break
            offset=frame-end
            if ge099 is None and candidate[frame]['res_gain']<0.99:ge099=offset
            if ge095 is None and candidate[frame]['res_gain']<0.95:ge095=offset
            if within is None and candidate[frame]['post_output_energy'] <=
               predecessor[frame]['post_output_energy']*ENVELOPE_RATIO:
                within=offset
        out.append({'start_frame':start,'end_frame_exclusive':end,
          'first_gain_lt_0_99_offset_frames':ge099,
          'first_gain_lt_0_99_ms':None if ge099 is None else ge099*10,
          'first_gain_lt_0_95_offset_frames':ge095,
          'first_gain_lt_0_95_ms':None if ge095 is None else ge095*10,
          'first_within_predecessor_plus_1db_offset_frames':within,
          'first_within_predecessor_plus_1db_ms':None if within is None else within*10})
    return out

def engineering(root:Path,binaries:dict,sync_root:Path,res_root:Path,revision:str)->dict:
    root.mkdir();pc=case_map(load_json(sync_root/'result.json'))['p0-route'];inp=sync_root/pc['input']
    predecessor=res_root/'cases'/'p0-route'/'candidate.f32';records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+
                   [binaries[label],'--self-test'],d/'self-test.log')
        rec=run_one(binaries[label],label,inp,'route',d/'candidate')
        records[label]={'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256'],
          'route_jumps':rec['meta']['route_jumps'],'aec_resets':rec['meta']['aec_resets'],
          'res_state_bytes':rec['meta']['res_state_bytes']}
        if label=='native':
            records[label]['lane_identity']=lane_identity(d/'candidate.f32',predecessor)
            records[label]['dt_causal_identity']=dt_causal_identity(
                d/'candidate.f32',predecessor,rec['rows'])
    data=array.array('f');data.frombytes(inp.read_bytes())
    if sys.byteorder!='little':data.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        for c in range(4):data[4*k+c]*=-1.0
    if sys.byteorder!='little':data.byteswap()
    future=root/'future-input.f32';future.write_bytes(data.tobytes())
    execute(binaries['native'],'route',future,root/'future')
    a=base.sync.floats(root/'native/candidate.f32',N*3)
    b=base.sync.floats(root/'future.f32',N*3)
    require(a[:(cutoff-2*HOP)*3]==b[:(cutoff-2*HOP)*3]
      and a[(cutoff+2*HOP)*3:]!=b[(cutoff+2*HOP)*3:],'immediate-DT future causality')
    z=array.array('f');z.frombytes(inp.read_bytes())
    if sys.byteorder!='little':z.byteswap()
    for k in range(N):z[4*k+3]=0.0
    if sys.byteorder!='little':z.byteswap()
    zero=root/'zero-render.f32';zero.write_bytes(z.tobytes())
    execute(binaries['native'],'static',zero,root/'zero-render-output')
    zr=base.trace_rows(root/'zero-render-output.csv','static')
    require(all(x['res_gain']==1.0 for x in zr),'immediate-DT RES attenuated zero-render control')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],'static',bad,root/'bad'))),
                     capture_output=True)
    require(p.returncode!=0,'partial immediate-DT input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/candidate.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],'route',inp,root/'native/candidate'))),
                     capture_output=True)
    require(p.returncode!=0 and before==(root/'native/candidate.f32').read_bytes(),
            'immediate-DT overwrite accepted')
    (root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,
      'zero_render_unity_gain':True,'invalid_transport_rejected':True,
      'overwrite_rejected':True,'immediate_dt_self_test':True}
    write_json(root/'result.json',result);return result

def run(sync_root:Path,reset_root:Path,exact_root:Path,res_root:Path,root:Path,
        revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor_receipt(sync_root,reset_root,exact_root,res_root,revision,full=True)
    sr=load_json(sync_root/'result.json');br=load_json(res_root/'result.json')
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json')
    write_json(root/'predecessor-verification.json',pred);(root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,sync_root,res_root,revision)
    sm=case_map(sr);bm=case_map(br);cases=[]
    for case_id in sorted(sm,key=lambda x:(sm[x]['pair'],FAULTS.index(sm[x]['fault']))):
        pc=sm[case_id];bp=bm[case_id];fault=pc['fault'];inp=sync_root/pc['input']
        d=root/'cases'/case_id;d.mkdir(parents=True)
        rec=run_one(binaries['native'],'native',inp,fault,d/'candidate')
        predecessor=res_root/'cases'/case_id/'candidate.f32'
        prows=base.trace_rows(res_root/'cases'/case_id/'candidate.csv',fault)
        identity=lane_identity(d/'candidate.f32',predecessor)
        stable=stable_trace_identity(rec['rows'],prows)
        causal=dt_causal_identity(d/'candidate.f32',predecessor,rec['rows'])
        pre=base.floats(d/'candidate.f32',3,0);post=base.floats(d/'candidate.f32',3,1)
        pre_m=base.metrics(inp,d/'candidate.f32',0,fault)
        post_m=base.metrics(inp,d/'candidate.f32',1,fault)
        require(pre_m==bp['pre_res_metrics']==bp['aec_only_metrics'],'candidate pre-RES baseline drift')
        phases=base.phase_gain(rec['rows'],pre,post)
        reacq=reacquisition(rec['rows'],prows)
        cases.append({'case_id':case_id,'pair':pc['pair'],'fault':fault,
          'lane_identity':identity,'trace_identity':stable,'dt_causal_identity':causal,
          'predecessor_post_res_metrics':bp['post_res_metrics'],'pre_res_metrics':pre_m,
          'candidate_post_res_metrics':post_m,
          'delta_final_far_db_vs_current_res':None if bp['post_res_metrics']['final_far_ratio_db'] is None
             or post_m['final_far_ratio_db'] is None else
             post_m['final_far_ratio_db']-bp['post_res_metrics']['final_far_ratio_db'],
          'phase_gain':phases,'post_dt_reacquisition':reacq,
          'double_talk_gain_lt_0_99_frames':rec['meta']['double_talk_gain_lt_0_99_frames'],
          'double_talk_gain_lt_0_95_frames':rec['meta']['double_talk_gain_lt_0_95_frames'],
          'candidate_output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE04-RES-IMMEDIATE-DT-PROTECTION-V1',
      'decision':DECISION,'shipping_authority':False,'data_role':ROLE,
      'execution_source_revision':revision,'case_count':6,'predecessor':pred,
      'transport':'EXACT_SYNTHETIC_TIMESTAMP_NOT_DUT','res_mode':'TIME_DOMAIN_FULL_NO_NS',
      'current_near_protection_release_alpha':0.20,'candidate_near_protection_release_alpha':1.0,
      'predecessor_envelope_db':1.0,'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(sync_root:Path,reset_root:Path,exact_root:Path,res_root:Path,root:Path,
           revision:str,predecessors_verified=False)->dict:
    verify_seal(root)
    pred=predecessor_receipt(sync_root,reset_root,exact_root,res_root,revision,full=False)
    r=load_json(root/'result.json');receipt=load_json(root/'predecessor-verification.json')
    require(r['predecessor']==receipt==pred,'immediate-DT predecessor receipt')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'immediate-DT plan drift')
    require(r['experiment_id']=='FE04-RES-IMMEDIATE-DT-PROTECTION-V1'
      and r['decision']==DECISION and r['shipping_authority'] is False
      and r['data_role']==ROLE and r['execution_source_revision']==revision
      and r['case_count']==6,'immediate-DT authority')
    require(r['current_near_protection_release_alpha']==0.20
      and r['candidate_near_protection_release_alpha']==1.0
      and r['predecessor_envelope_db']==1.0,'immediate-DT fixed constants')
    for name in ('res_immediate_dt_runner.c','res_immediate_dt.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),
                'immediate-DT source drift '+name)
    sr=load_json(sync_root/'result.json');br=load_json(res_root/'result.json')
    sm=case_map(sr);bm=case_map(br)
    require({c['case_id'] for c in r['cases']}==set(sm)==set(bm),'immediate-DT case set')
    for c in r['cases']:
        pc=sm[c['case_id']];bp=bm[c['case_id']];fault=c['fault'];inp=sync_root/pc['input']
        d=root/'cases'/c['case_id'];pred_path=res_root/'cases'/c['case_id']/'candidate.f32'
        rows=base.trace_rows(d/'candidate.csv',fault)
        prows=base.trace_rows(res_root/'cases'/c['case_id']/'candidate.csv',fault)
        identity=lane_identity(d/'candidate.f32',pred_path)
        stable=stable_trace_identity(rows,prows)
        causal=dt_causal_identity(d/'candidate.f32',pred_path,rows)
        pre=base.floats(d/'candidate.f32',3,0);post=base.floats(d/'candidate.f32',3,1)
        pre_m=base.metrics(inp,d/'candidate.f32',0,fault)
        post_m=base.metrics(inp,d/'candidate.f32',1,fault)
        require(c['lane_identity']==identity and c['trace_identity']==stable
          and c['dt_causal_identity']==causal,'immediate-DT identity recomputation')
        require(c['pre_res_metrics']==pre_m==bp['pre_res_metrics']==bp['aec_only_metrics'],
                'immediate-DT pre-RES metrics')
        require(c['predecessor_post_res_metrics']==bp['post_res_metrics']
          and c['candidate_post_res_metrics']==post_m,'immediate-DT metrics')
        require(c['phase_gain']==base.phase_gain(rows,pre,post)
          and c['post_dt_reacquisition']==reacquisition(rows,prows),'immediate-DT gain/reacquisition')
        meta=load_json(d/'candidate.json')
        require(c['double_talk_gain_lt_0_99_frames']==0==meta['double_talk_gain_lt_0_99_frames']
          and c['double_talk_gain_lt_0_95_frames']==0==meta['double_talk_gain_lt_0_95_frames'],
          'immediate-DT protection counts')
        require(c['candidate_output_sha256']==sha256((d/'candidate.f32').read_bytes())
          and c['trace_sha256']==sha256((d/'candidate.csv').read_bytes()),'immediate-DT hashes')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision
          and info['res_near_protection_release_alpha']==1.0
          and info['compile_definition']=='-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f'
          and info['processor_sha256']==sha256((root/('res-immediate-dt-'+label)).read_bytes()),
          'immediate-DT binary/build identity')
    eng=load_json(root/'engineering/result.json')
    require(eng==r['engineering'] and eng['status']=='PASS','immediate-DT engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),
            'immediate-DT Arm ELF')
    return {'status':'VERIFIED_RES_IMMEDIATE_DT_PROTECTION','cases':6,
      'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(sync_root:Path,reset_root:Path,exact_root:Path,res_root:Path,
              root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','dt-protection','binary')
    rejected=[]
    predecessor_receipt(sync_root,reset_root,exact_root,res_root,revision,full=False)
    with tempfile.TemporaryDirectory(prefix='res-immediate-dt-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor']['res_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['candidate_post_res_metrics']['final_far_ratio_db']=0.0
            elif kind=='dt-protection':rr['cases'][0]['double_talk_gain_lt_0_99_frames']=1
            else:
                case=rr['cases'][0]['case_id'];basepath=copy/'cases'/case/'candidate'
                pth=basepath.with_suffix('.f32') if kind=='output' else basepath.with_suffix('.csv') if kind=='trace' else copy/'res-immediate-dt-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(sync_root,reset_root,exact_root,res_root,copy,revision,
                       predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed immediate-DT negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        base_vals=[x['predecessor_post_res_metrics']['final_far_ratio_db'] for x in rows]
        cand_vals=[x['candidate_post_res_metrics']['final_far_ratio_db'] for x in rows]
        groups.append({'fault':fault,'cases':len(rows),
          'current_res_mean_final_far_db':sum(base_vals)/len(base_vals),
          'immediate_dt_mean_final_far_db':sum(cand_vals)/len(cand_vals),
          'delta_final_far_db':[x['delta_final_far_db_vs_current_res'] for x in rows],
          'double_talk_gain_lt_0_99_frames':[x['double_talk_gain_lt_0_99_frames'] for x in rows],
          'double_talk_gain_lt_0_95_frames':[x['double_talk_gain_lt_0_95_frames'] for x in rows],
          'double_before_gain_mean':[x['phase_gain']['double-before']['gain_mean'] for x in rows],
          'double_after_gain_mean':[x['phase_gain']['double-after']['gain_mean'] for x in rows],
          'double_before_rms_delta_db':[x['phase_gain']['double-before']['output_rms_delta_db'] for x in rows],
          'double_after_rms_delta_db':[x['phase_gain']['double-after']['output_rms_delta_db'] for x in rows],
          'post_dt_reacquisition':[x['post_dt_reacquisition'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('--sync-predecessor',type=Path,required=True)
    p.add_argument('--reset-predecessor',type=Path,required=True)
    p.add_argument('--exact-predecessor',type=Path,required=True)
    p.add_argument('--res-predecessor',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execution-source',required=True)
    p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'immediate-DT revision')
    if a.negative_evidence:
        r=negatives(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,
                    a.res_predecessor,a.output,a.execution_source)
    elif a.verify:
        r=verify(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,
                 a.res_predecessor,a.output,a.execution_source)
    else:
        r=run(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,
              a.res_predecessor,a.output,a.execution_source)
        print('RES_IMMEDIATE_DT_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_RES_IMMEDIATE_DT_PROTECTION','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
