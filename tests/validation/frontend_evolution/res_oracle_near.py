#!/usr/bin/env python3
"""Oracle near-presence upper bound for the existing immediate-DT RES path."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import aec_res_collab as base
import res_immediate_dt as immediate
import sync_faults as sync
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/res-oracle-near-bound-v1.json'
RUNNER=HERE/'res_oracle_near_runner.c'
DECISION='RES_ORACLE_NEAR_BOUND_DIAGNOSTIC_NO_PROMOTION'
ROLE=base.ROLE
RATE,HOP,N=base.RATE,base.HOP,base.N
FAULTS=base.FAULTS
LABELS=base.LABELS
MODES=('measured','oracle')
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off',
        '-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f']
TRACE_HEADER=['frame','used_far','measured_dt','oracle_near','res_control_near',
  'aec_echo_energy','pre_residual_energy','predecessor_gain','candidate_gain',
  'pre_output_energy','predecessor_post_output_energy','candidate_post_output_energy']
STABLE={
  'scheduled-double': list(range(610,990)),
  'scheduled-far-only': list(range(210,590))+list(range(1010,1390)),
  'scheduled-near-only': list(range(10,190))+list(range(1410,1590))
}

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def oracle_near(frame:int)->int:
    return int(frame<204 or 600<=frame<1004 or frame>=1400)

def predecessor_receipt(sync_root:Path,res_root:Path,revision:str)->dict:
    verify_seal(sync_root);verify_seal(res_root)
    sr=load_json(sync_root/'result.json');rr=load_json(res_root/'result.json')
    require(sr['experiment_id']=='FE04-SYNC-FAULTS-V1' and sr['case_count']==6
      and sr['execution_source_revision']==revision,'oracle-near SYNC predecessor')
    require(rr['experiment_id']=='FE04-RES-IMMEDIATE-DT-PROTECTION-V1' and rr['case_count']==6
      and rr['decision']=='RES_IMMEDIATE_DT_PROTECTION_DIAGNOSTIC_NO_PROMOTION'
      and rr['execution_source_revision']==revision
      and rr['candidate_near_protection_release_alpha']==1.0,'oracle-near RES predecessor')
    return {'sync_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'res_manifest_sha256':sha256((res_root/'manifest.json').read_bytes()),
      'res_result_sha256':sha256((res_root/'result.json').read_bytes()),
      'source_revision':revision}

def trace_rows(path:Path)->list[dict]:
    rows=[]
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==TRACE_HEADER,'oracle-near trace schema')
        for index,row in enumerate(rd):
            require(index<N//HOP and None not in row.values(),'oracle-near trace count/partial')
            item={}
            for key in TRACE_HEADER:
                if key in ('aec_echo_energy','pre_residual_energy','predecessor_gain','candidate_gain',
                           'pre_output_energy','predecessor_post_output_energy','candidate_post_output_energy'):
                    value=float(row[key]);require(math.isfinite(value) and value>=0.0,'oracle-near nonfinite/negative')
                    item[key]=value
                else:item[key]=int(row[key])
            require(item['frame']==index and item['used_far'] in (0,1) and item['measured_dt'] in (0,1)
              and item['oracle_near']==oracle_near(index) and item['res_control_near'] in (0,1),
              'oracle-near trace identity')
            rows.append(item)
    require(len(rows)==N//HOP,'oracle-near frame count')
    return rows

def build(root:Path,revision:str,label:str)->Path:
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    definition='-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f'
    b=root/('build-'+label)
    opts=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(flags+['-ffp-contract=off',definition]),
      '-DAP_BUILD_SOURCE_REVISION='+revision,'-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=RES',
      '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF',
      '-DAP_ENABLE_LINUX_RUNTIME=OFF','-DAP_STRICT_WARNINGS=ON']
    if arm:opts+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(opts,root/(label+'-configure.log'));run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('res-oracle-near-'+label)
    cmd=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),RUNNER,b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'));run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-library.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
      'library_sha256':sha256((root/(label+'-library.a')).read_bytes()),'compiler':cc,'sanitized':san,'arm':arm,
      'near_protection_release_alpha':1.0,'compile_definition':definition,
      'configure':list(map(str,opts)),'link':list(map(str,cmd))})
    shutil.rmtree(b);return binary

def command(binary:Path,mode:str,pred_audio:Path,pred_trace:Path,dest:Path,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,mode,pred_audio,pred_trace,dest.with_suffix('.f32'),
            dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary:Path,mode:str,pred_audio:Path,pred_trace:Path,dest:Path,under_arm:bool=False)->None:
    run_logged(command(binary,mode,pred_audio,pred_trace,dest,under_arm),dest.with_suffix('.log'))

def words(path:Path)->array.array:
    a=array.array('I');a.frombytes(path.read_bytes())
    if sys.byteorder!='little':a.byteswap()
    return a

def lane_identity(candidate:Path,predecessor:Path)->dict:
    cw=words(candidate);pw=words(predecessor)
    require(len(cw)==len(pw)==N*3,'oracle-near packed size')
    pre=sum(a!=b for a,b in zip(cw[0::3],pw[0::3]))
    ref=sum(a!=b for a,b in zip(cw[2::3],pw[2::3]))
    require(pre==0 and ref==0,'oracle-near changed immutable lanes')
    return {'pre_res_aec_bit_mismatches':pre,'reference_bit_mismatches':ref,
      'pre_res_aec_bit_identity':True,'reference_bit_identity':True}

def replay_identity(candidate:Path,predecessor:Path)->dict:
    same=candidate.read_bytes()==predecessor.read_bytes()
    require(same,'measured RES replay is not predecessor-byte-identical')
    return {'packed_output_byte_identity':True,'sha256':sha256(candidate.read_bytes())}

def longest_run(values:list[bool])->int:
    best=cur=0
    for value in values:
        if value:cur+=1;best=max(best,cur)
        else:cur=0
    return best

def confusion(pred_rows:list[dict],candidate_rows:list[dict])->dict:
    require(len(pred_rows)==len(candidate_rows)==1600,'oracle-near confusion count')
    truth=[bool(oracle_near(i)) for i in range(1600)]
    detected=[bool(r['used_dt']) for r in pred_rows]
    tp=sum(t and d for t,d in zip(truth,detected));fn=sum(t and not d for t,d in zip(truth,detected))
    fp=sum((not t) and d for t,d in zip(truth,detected));tn=sum((not t) and (not d) for t,d in zip(truth,detected))
    result={'full':{'frames':1600,'tp':tp,'fn':fn,'fp':fp,'tn':tn,
      'recall':tp/(tp+fn) if tp+fn else None,'precision':tp/(tp+fp) if tp+fp else None,
      'longest_fn_run_frames':longest_run([t and not d for t,d in zip(truth,detected)]),
      'longest_fp_run_frames':longest_run([(not t) and d for t,d in zip(truth,detected)])}}
    for name,indices in STABLE.items():
        t=[truth[i] for i in indices];d=[detected[i] for i in indices]
        result[name]={'frames':len(indices),'oracle_near_frames':sum(t),'measured_dt_frames':sum(d),
          'missed_near_frames':sum(a and not b for a,b in zip(t,d)),
          'false_positive_frames':sum((not a) and b for a,b in zip(t,d)),
          'adaptation_admitted':sum(pred_rows[i]['used_far'] and not pred_rows[i]['used_dt'] for i in indices),
          'longest_missed_run_frames':longest_run([a and not b for a,b in zip(t,d)]),
          'longest_false_positive_run_frames':longest_run([(not a) and b for a,b in zip(t,d)])}
    newly=[i for i in range(1600) if truth[i] and not detected[i]]
    falsep=[i for i in range(1600) if not truth[i] and detected[i]]
    def gain_stats(indices):
        if not indices:return {'frames':0,'gain_mean':None,'gain_min':None,'gain_lt_0_99_frames':0,'gain_lt_0_95_frames':0,'rms_attenuation_db':None}
        gains=[pred_rows[i]['res_gain'] for i in indices]
        pre=sum(pred_rows[i]['pre_output_energy'] for i in indices)
        post=sum(pred_rows[i]['post_output_energy'] for i in indices)
        return {'frames':len(indices),'gain_mean':sum(gains)/len(gains),'gain_min':min(gains),
          'gain_lt_0_99_frames':sum(g<0.99 for g in gains),'gain_lt_0_95_frames':sum(g<0.95 for g in gains),
          'rms_attenuation_db':10*math.log10(max(post,1e-30)/max(pre,1e-30))}
    result['newly-protected-predecessor']=gain_stats(newly)
    result['measured-false-positive-predecessor']=gain_stats(falsep)
    require(all(candidate_rows[i]['candidate_gain']==1.0 for i in range(1600) if truth[i]),
            'oracle-near frame not unity gain')
    return result

def output_causal_identity(candidate:Path,rows:list[dict])->dict:
    cw=words(candidate)
    require(len(cw)==N*3,'oracle-near output size')
    mismatches=0;frames=0
    for row in rows:
        if not row['oracle_near']:continue
        frames+=1;lo=row['frame']*HOP
        for k in range(lo,lo+HOP):
            if cw[3*k+1]!=cw[3*k]:mismatches+=1
    require(frames==808 and mismatches==0,'oracle-near post output not pre-RES identical')
    return {'oracle_near_frames':frames,'post_vs_pre_bit_mismatches':mismatches,'unity_gain':True}

def phase_gain(rows:list[dict],pre:list[float],post:list[float])->dict:
    adapted=[{'res_gain':r['candidate_gain'],'used_dt':r['res_control_near']} for r in rows]
    return base.phase_gain(adapted,pre,post)

def run_one(binary:Path,label:str,mode:str,pred_audio:Path,pred_trace:Path,dest:Path)->dict:
    under_arm=label=='arm'
    execute(binary,mode,pred_audio,pred_trace,dest,under_arm)
    execute(binary,mode,pred_audio,pred_trace,dest.with_name(dest.name+'-repeat'),under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),
                'oracle-near repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=trace_rows(dest.with_suffix('.csv'));meta=load_json(dest.with_suffix('.json'))
    require(meta['status']=='PASS' and meta['mode']==('measured-replay' if mode=='measured' else 'oracle-near')
      and meta['near_protection_release_alpha']==1.0 and meta['frames']==1600,'oracle-near meta')
    return {'rows':rows,'meta':meta,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
      'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def engineering(root:Path,binaries:dict,sync_root:Path,res_root:Path,revision:str)->dict:
    root.mkdir();pc=case_map(load_json(sync_root/'result.json'))['p0-route'];pred=res_root/'cases'/'p0-route'/'candidate'
    records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+[binaries[label],'--self-test'],d/'self-test.log')
        measured=run_one(binaries[label],label,'measured',pred.with_suffix('.f32'),pred.with_suffix('.csv'),d/'measured')
        oracle=run_one(binaries[label],label,'oracle',pred.with_suffix('.f32'),pred.with_suffix('.csv'),d/'oracle')
        records[label]={'measured_sha256':measured['output_sha256'],'oracle_sha256':oracle['output_sha256'],
          'oracle_newly_protected_frames':oracle['meta']['newly_protected_frames'],
          'measured_dt_frames':measured['meta']['measured_dt_frames'],
          'oracle_near_frames':oracle['meta']['oracle_near_frames']}
        if label=='native':
            records[label]['replay_identity']=replay_identity(d/'measured.f32',pred.with_suffix('.f32'))
            records[label]['lane_identity']=lane_identity(d/'oracle.f32',pred.with_suffix('.f32'))
            records[label]['oracle_output_identity']=output_causal_identity(d/'oracle.f32',oracle['rows'])
    raw=array.array('f');raw.frombytes(pred.with_suffix('.f32').read_bytes())
    if sys.byteorder!='little':raw.byteswap()
    cutoff=200000
    for k in range(cutoff,N):raw[3*k]*=-1.0
    if sys.byteorder!='little':raw.byteswap()
    future=root/'future.f32';future.write_bytes(raw.tobytes())
    execute(binaries['native'],'oracle',future,pred.with_suffix('.csv'),root/'future-output')
    a=sync.floats(root/'native/oracle.f32',N*3);b=sync.floats(root/'future-output.f32',N*3)
    require(a[:(cutoff-2*HOP)*3]==b[:(cutoff-2*HOP)*3] and a[(cutoff+2*HOP)*3:]!=b[(cutoff+2*HOP)*3:],
            'oracle-near future causality')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],'oracle',bad,pred.with_suffix('.csv'),root/'bad'))),capture_output=True)
    require(p.returncode!=0,'oracle-near partial input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/oracle.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],'oracle',pred.with_suffix('.f32'),pred.with_suffix('.csv'),root/'native/oracle'))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/oracle.f32').read_bytes(),'oracle-near overwrite accepted')
    (root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,
      'invalid_transport_rejected':True,'overwrite_rejected':True,'res_self_test':True}
    write_json(root/'result.json',result);return result

def run(sync_root:Path,res_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor_receipt(sync_root,res_root,revision)
    sr=load_json(sync_root/'result.json');rr=load_json(res_root/'result.json')
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');write_json(root/'predecessor-verification.json',pred)
    (root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,sync_root,res_root,revision)
    sm=case_map(sr);rm=case_map(rr);cases=[]
    pair_gate_sequences={}
    for case_id in sorted(sm,key=lambda x:(sm[x]['pair'],FAULTS.index(sm[x]['fault']))):
        pc=sm[case_id];pr=rm[case_id];fault=pc['fault'];inp=sync_root/pc['input']
        pred_path=res_root/'cases'/case_id/'candidate';d=root/'cases'/case_id;d.mkdir(parents=True)
        measured=run_one(binaries['native'],'native','measured',pred_path.with_suffix('.f32'),pred_path.with_suffix('.csv'),d/'measured')
        oracle=run_one(binaries['native'],'native','oracle',pred_path.with_suffix('.f32'),pred_path.with_suffix('.csv'),d/'oracle')
        replay=replay_identity(d/'measured.f32',pred_path.with_suffix('.f32'))
        identity=lane_identity(d/'oracle.f32',pred_path.with_suffix('.f32'))
        causal=output_causal_identity(d/'oracle.f32',oracle['rows'])
        predecessor_rows=base.trace_rows(pred_path.with_suffix('.csv'),fault)
        require([r['used_far'] for r in predecessor_rows]==[r['used_far'] for r in measured['rows']]
          and [r['used_dt'] for r in predecessor_rows]==[r['measured_dt'] for r in measured['rows']],
          'oracle-near predecessor gate copy')
        for a,b in zip(predecessor_rows,measured['rows']):
            require(a['res_gain']==b['candidate_gain'],'measured replay gain drift')
        seq=tuple((r['used_far'],r['used_dt']) for r in predecessor_rows)
        old=pair_gate_sequences.setdefault(pc['pair'],seq);require(old==seq,'Activity gates changed across transport faults')
        audit=confusion(predecessor_rows,oracle['rows'])
        pre=base.floats(d/'oracle.f32',3,0);post=base.floats(d/'oracle.f32',3,1)
        candidate_metrics=base.metrics(inp,d/'oracle.f32',1,fault)
        require(base.metrics(inp,d/'measured.f32',1,fault)==pr['candidate_post_res_metrics'],
                'measured replay metric drift')
        cases.append({'case_id':case_id,'pair':pc['pair'],'fault':fault,'replay_identity':replay,
          'lane_identity':identity,'oracle_output_identity':causal,'coverage_audit':audit,
          'predecessor_metrics':pr['candidate_post_res_metrics'],'candidate_metrics':candidate_metrics,
          'delta_final_far_db':None if pr['candidate_post_res_metrics']['final_far_ratio_db'] is None
            or candidate_metrics['final_far_ratio_db'] is None else
            candidate_metrics['final_far_ratio_db']-pr['candidate_post_res_metrics']['final_far_ratio_db'],
          'predecessor_phase_gain':pr['phase_gain'],'candidate_phase_gain':phase_gain(oracle['rows'],pre,post),
          'measured_output_sha256':measured['output_sha256'],'oracle_output_sha256':oracle['output_sha256'],
          'oracle_trace_sha256':oracle['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE04-RES-ORACLE-NEAR-BOUND-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'predecessor':pred,'oracle_near_schedule':'frame<204 || 600<=frame<1004 || frame>=1400',
      'single_variable':'RES_NEAR_PROTECTION_CONTROL_ONLY','aec_activity_sync_immutable':True,
      'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(sync_root:Path,res_root:Path,root:Path,revision:str,predecessors_verified=False)->dict:
    verify_seal(root);pred=predecessor_receipt(sync_root,res_root,revision)
    r=load_json(root/'result.json');receipt=load_json(root/'predecessor-verification.json')
    require(r['predecessor']==receipt==pred,'oracle-near predecessor receipt')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'oracle-near plan drift')
    require(r['experiment_id']=='FE04-RES-ORACLE-NEAR-BOUND-V1' and r['decision']==DECISION
      and r['shipping_authority'] is False and r['data_role']==ROLE
      and r['execution_source_revision']==revision and r['case_count']==6
      and r['single_variable']=='RES_NEAR_PROTECTION_CONTROL_ONLY'
      and r['aec_activity_sync_immutable'] is True,'oracle-near authority')
    for name in ('res_oracle_near_runner.c','res_oracle_near.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'oracle-near source drift '+name)
    sr=load_json(sync_root/'result.json');rr=load_json(res_root/'result.json');sm=case_map(sr);rm=case_map(rr)
    require({c['case_id'] for c in r['cases']}==set(sm)==set(rm),'oracle-near case set')
    pair_gate_sequences={}
    for c in r['cases']:
        pc=sm[c['case_id']];pr=rm[c['case_id']];fault=c['fault'];inp=sync_root/pc['input'];d=root/'cases'/c['case_id']
        pred_path=res_root/'cases'/c['case_id']/'candidate'
        measured=trace_rows(d/'measured.csv');oracle=trace_rows(d/'oracle.csv');pred_rows=base.trace_rows(pred_path.with_suffix('.csv'),fault)
        require(c['replay_identity']==replay_identity(d/'measured.f32',pred_path.with_suffix('.f32')),'oracle-near replay receipt')
        require(c['lane_identity']==lane_identity(d/'oracle.f32',pred_path.with_suffix('.f32')),'oracle-near lane receipt')
        require(c['oracle_output_identity']==output_causal_identity(d/'oracle.f32',oracle),'oracle-near causal receipt')
        for a,b in zip(pred_rows,measured):require(a['res_gain']==b['candidate_gain'],'oracle-near measured gain')
        seq=tuple((x['used_far'],x['used_dt']) for x in pred_rows)
        old=pair_gate_sequences.setdefault(pc['pair'],seq);require(old==seq,'oracle-near gate transport drift')
        require(c['coverage_audit']==confusion(pred_rows,oracle),'oracle-near confusion recomputation')
        pre=base.floats(d/'oracle.f32',3,0);post=base.floats(d/'oracle.f32',3,1)
        cm=base.metrics(inp,d/'oracle.f32',1,fault)
        require(c['predecessor_metrics']==pr['candidate_post_res_metrics'] and c['candidate_metrics']==cm,
                'oracle-near metrics')
        require(c['predecessor_phase_gain']==pr['phase_gain']
          and c['candidate_phase_gain']==phase_gain(oracle,pre,post),'oracle-near phase gain')
        require(c['measured_output_sha256']==sha256((d/'measured.f32').read_bytes())
          and c['oracle_output_sha256']==sha256((d/'oracle.f32').read_bytes())
          and c['oracle_trace_sha256']==sha256((d/'oracle.csv').read_bytes()),'oracle-near hashes')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision and info['near_protection_release_alpha']==1.0
          and info['compile_definition']=='-DAP_RES_NEAR_PROTECTION_RELEASE_ALPHA=1.0f'
          and info['processor_sha256']==sha256((root/('res-oracle-near-'+label)).read_bytes()),
          'oracle-near binary/build identity')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','oracle-near engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'oracle-near Arm ELF')
    return {'status':'VERIFIED_RES_ORACLE_NEAR_BOUND','cases':6,
      'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(sync_root:Path,res_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','coverage','binary');rejected=[]
    predecessor_receipt(sync_root,res_root,revision)
    with tempfile.TemporaryDirectory(prefix='res-oracle-near-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor']['res_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['candidate_metrics']['final_far_ratio_db']=0.0
            elif kind=='coverage':rr['cases'][0]['coverage_audit']['full']['fn']+=1
            else:
                case=rr['cases'][0]['case_id'];basepath=copy/'cases'/case/'oracle'
                pth=basepath.with_suffix('.f32') if kind=='output' else basepath.with_suffix('.csv') if kind=='trace' else copy/'res-oracle-near-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(sync_root,res_root,copy,revision,predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed oracle-near negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        old=[x['predecessor_metrics']['final_far_ratio_db'] for x in rows]
        new=[x['candidate_metrics']['final_far_ratio_db'] for x in rows]
        groups.append({'fault':fault,'cases':len(rows),
          'immediate_dt_mean_final_far_db':sum(old)/len(old),
          'oracle_near_mean_final_far_db':sum(new)/len(new),
          'delta_final_far_db':[x['delta_final_far_db'] for x in rows],
          'full_confusion':[x['coverage_audit']['full'] for x in rows],
          'stable_double':[x['coverage_audit']['scheduled-double'] for x in rows],
          'stable_far_only':[x['coverage_audit']['scheduled-far-only'] for x in rows],
          'stable_near_only':[x['coverage_audit']['scheduled-near-only'] for x in rows],
          'newly_protected':[x['coverage_audit']['newly-protected-predecessor'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--sync-predecessor',type=Path,required=True)
    p.add_argument('--res-predecessor',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'oracle-near revision')
    if a.negative_evidence:r=negatives(a.sync_predecessor,a.res_predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.sync_predecessor,a.res_predecessor,a.output,a.execution_source)
    else:
        r=run(a.sync_predecessor,a.res_predecessor,a.output,a.execution_source)
        print('RES_ORACLE_NEAR_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_RES_ORACLE_NEAR_BOUND','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
