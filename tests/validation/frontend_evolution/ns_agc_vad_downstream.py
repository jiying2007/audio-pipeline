#!/usr/bin/env python3
"""FE05 NS frequency-RES downstream propagation through controlled AGC and VAD."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, struct, subprocess, sys, tempfile
from pathlib import Path
import sync_faults as sync
import aec_res_collab as aecres
import ns_frequency_res as nsfreq
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/ns-agc-vad-downstream-v1.json'
RUNNER=HERE/'ns_agc_vad_downstream_runner.c'
DECISION='NS_AGC_VAD_DOWNSTREAM_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
FAULTS=sync.FAULTS
LABELS=sync.LABELS
PHASES=aecres.PHASES
AGC_TARGET_DBFS=-18.0
LIMITER_DBFS=-2.0
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
TRACE_HEADER=[
 'frame','used_far','used_dt','allow_gain_increase','upstream_speech_probability',
 'pre_diff_samples','agc_state_before_equal','agc0_gain_before','agc1_gain_before',
 'pre0_rms','pre1_rms','pre0_peak','pre1_peak','agc0_gain_after','agc1_gain_after',
 'post0_rms','post1_rms','post0_peak','post1_peak','limiter0_active','limiter1_active',
 'post_diff_samples','vad_state_before_equal','vad0_noise_before','vad1_noise_before',
 'vad0_hangover_before','vad1_hangover_before','vad0_probability','vad1_probability',
 'vad0_active','vad1_active','vad0_noise_after','vad1_noise_after','vad0_hangover_after',
 'vad1_hangover_after','vad_state_after_equal'
]
INT_FIELDS={
 'frame','used_far','used_dt','allow_gain_increase','pre_diff_samples','agc_state_before_equal',
 'limiter0_active','limiter1_active','post_diff_samples','vad_state_before_equal',
 'vad0_hangover_before','vad1_hangover_before','vad0_active','vad1_active',
 'vad0_hangover_after','vad1_hangover_after','vad_state_after_equal'
}

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def predecessor_receipt(ns_root:Path,sync_root:Path,revision:str)->dict:
    verify_seal(ns_root);verify_seal(sync_root)
    nr=load_json(ns_root/'result.json');sr=load_json(sync_root/'result.json')
    require(nr['experiment_id']=='FE05-NS-FREQUENCY-RES-V1' and nr['decision']=='NS_FREQUENCY_RES_DIAGNOSTIC_NO_PROMOTION','wrong NS predecessor')
    require(nr['shipping_authority'] is False and nr['data_role']==ROLE and nr['case_count']==6,'NS predecessor authority')
    require(nr['execution_source_revision']==sr['execution_source_revision']==revision,'downstream predecessor revision')
    require(nr['predecessor']['sync_manifest_sha256']==sha256((sync_root/'manifest.json').read_bytes()),'NS/sync binding')
    require(nr['ns_quality']=='FULL' and nr['floor_gain']==0.18 and nr['time_domain_res_executed'] is False,'NS predecessor scope')
    return {'ns_manifest_sha256':sha256((ns_root/'manifest.json').read_bytes()),
      'ns_result_sha256':sha256((ns_root/'result.json').read_bytes()),
      'sync_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'source_revision':revision}

def words(path:Path)->array.array:
    a=array.array('I');a.frombytes(path.read_bytes())
    if sys.byteorder!='little':a.byteswap()
    return a

def floats(path:Path,stride:int,lane:int)->list[float]:
    raw=sync.floats(path,N*stride);return list(raw[lane::stride])

def lane_words(path:Path,stride:int,lane:int)->list[int]:
    raw=words(path);require(len(raw)==N*stride,'downstream packed word count')
    return list(raw[lane::stride])

def controls_bytes(rows:list[dict])->bytes:
    require(len(rows)==N//HOP,'downstream control frame count')
    chunks=[]
    for row in rows:
        p=float(row['ns_only_speech_probability'])
        require(p==float(row['ns_freq_speech_probability']) and 0.0<=p<=1.0,'upstream probability identity')
        chunks.append(struct.pack('<fff',p,float(row['used_far']),float(row['used_dt'])))
    return b''.join(chunks)

def write_controls(ns_root:Path,case_id:str,fault:str,dest:Path)->dict:
    rows=nsfreq.trace_rows(ns_root/'cases'/case_id/'candidate.csv',fault)
    data=controls_bytes(rows);dest.write_bytes(data)
    receipt={'frames':len(rows),'bytes':len(data),'sha256':sha256(data),
      'source_trace_sha256':sha256((ns_root/'cases'/case_id/'candidate.csv').read_bytes()),
      'upstream_probability_source':'ns_only_speech_probability-bit-identity-enforced-by-predecessor',
      'far_dt_source':'measured-Activity-retained-by-predecessor'}
    return receipt

def trace_rows(path:Path)->list[dict]:
    rows=[]
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==TRACE_HEADER,'downstream trace schema')
        for index,row in enumerate(rd):
            require(index<N//HOP and None not in row.values(),'downstream trace count/partial')
            item={}
            for key in TRACE_HEADER:
                if key in INT_FIELDS:item[key]=int(row[key])
                else:
                    v=float(row[key]);require(math.isfinite(v),'nonfinite downstream trace');item[key]=v
            require(item['frame']==index,'downstream trace order')
            require(item['used_far'] in (0,1) and item['used_dt'] in (0,1),'downstream Activity flags')
            require(item['allow_gain_increase']==int(not(item['used_far'] and not item['used_dt'])),'controlled AGC flag')
            require(0.0<=item['upstream_speech_probability']<=1.0,'upstream probability bounds')
            for key in ('agc_state_before_equal','limiter0_active','limiter1_active','vad_state_before_equal',
                        'vad0_active','vad1_active','vad_state_after_equal'):
                require(item[key] in (0,1),'downstream boolean')
            require(0<=item['pre_diff_samples']<=HOP and 0<=item['post_diff_samples']<=HOP,'downstream diff count')
            if item['pre_diff_samples']==0 and item['agc_state_before_equal']:
                require(item['post_diff_samples']==0,'identical AGC input/state diverged')
            if item['post_diff_samples']==0 and item['vad_state_before_equal']:
                require(item['vad0_probability']==item['vad1_probability'] and item['vad0_active']==item['vad1_active'],
                        'identical VAD input/state diverged')
            rows.append(item)
    require(len(rows)==N//HOP,'downstream trace frame count')
    return rows

def build(root:Path,revision:str,label:str)->Path:
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    b=root/('build-'+label)
    opts=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(flags+['-ffp-contract=off']),'-DAP_BUILD_SOURCE_REVISION='+revision,
      '-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=AGC,VAD','-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF',
      '-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF','-DAP_STRICT_WARNINGS=ON']
    if arm:opts+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(opts,root/(label+'-configure.log'));run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('ns-agc-vad-'+label)
    cmd=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-DAP_BUILD_STAGE_AGC=1','-DAP_BUILD_STAGE_VAD=1',
      '-I'+str(ROOT/'include'),'-I'+str(ROOT/'src'),'-I'+str(b/'generated'),RUNNER,b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'));run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-library.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
      'library_sha256':sha256((root/(label+'-library.a')).read_bytes()),'compiler':cc,'sanitized':san,'arm':arm,
      'configure':list(map(str,opts)),'link':list(map(str,cmd))})
    shutil.rmtree(b);return binary

def command(binary:Path,inp:Path,controls:Path,dest:Path,revision:str,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,inp,controls,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv'),revision]

def execute(binary:Path,inp:Path,controls:Path,dest:Path,revision:str,under_arm:bool=False)->None:
    run_logged(command(binary,inp,controls,dest,revision,under_arm),dest.with_suffix('.log'))

def predecessor_lane_identity(pred:Path,out:Path)->dict:
    pw=words(pred);ow=words(out)
    require(len(pw)==N*5 and len(ow)==N*4,'downstream packed size')
    c=sum(a!=b for a,b in zip(pw[2::5],ow[0::4]))
    n=sum(a!=b for a,b in zip(pw[3::5],ow[1::4]))
    require(c==0 and n==0,'pre-AGC predecessor lane drift')
    return {'ns_only_pre_agc_bit_mismatches':c,'ns_freq_pre_agc_bit_mismatches':n,
      'pre_agc_predecessor_identity':True}

def metrics(inp:Path,out:Path,lane:int,fault:str)->dict:
    source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4]);actual=floats(out,4,lane)
    return sync.metrics(target,echo,actual,fault)

def longest_run(flags:list[bool])->int:
    best=cur=0
    for x in flags:
        cur=cur+1 if x else 0;best=max(best,cur)
    return best

def oracle_near(frame:int)->bool:
    return frame<204 or 600<=frame<1004 or frame>=1400

def confusion(active:list[int],indices:list[int]|None=None)->dict:
    idx=range(len(active)) if indices is None else indices
    tp=fn=fp=tn=0;fn_flags=[];fp_flags=[]
    for i in idx:
        truth=oracle_near(i);pred=bool(active[i])
        tp+=int(truth and pred);fn+=int(truth and not pred)
        fp+=int((not truth) and pred);tn+=int((not truth) and not pred)
        fn_flags.append(truth and not pred);fp_flags.append((not truth) and pred)
    return {'tp':tp,'fn':fn,'fp':fp,'tn':tn,'recall':tp/max(1,tp+fn),'fpr':fp/max(1,fp+tn),
      'longest_fn_run':longest_run(fn_flags),'longest_fp_run':longest_run(fp_flags)}

def stable_indices()->list[int]:
    out=[]
    for a,b in ((10,190),(210,590),(610,990),(1010,1390),(1410,1590)):out.extend(range(a,b))
    return out

def segment_events(active:list[int])->list[dict]:
    result=[]
    for a,b in ((0,204),(600,1004),(1400,1600)):
        onset=next((i for i in range(a,b) if active[i]),None)
        offset=None if b==1600 else next((i for i in range(b,min(N//HOP,b+80)) if not active[i]),None)
        result.append({'start':a,'end':b,'first_active':onset,'first_inactive_after_end':offset})
    return result

def phase_stats(rows:list[dict],control:list[float],candidate:list[float])->dict:
    out={}
    for name,(a,b) in PHASES.items():
        lo=a*HOP;hi=b*HOP;subset=rows[a:b]
        ce=sum(x*x for x in control[lo:hi])/max(1,hi-lo)
        ne=sum(x*x for x in candidate[lo:hi])/max(1,hi-lo)
        out[name]={'frames':len(subset),'output_rms_delta_db':10.0*math.log10(max(ne,1e-30)/max(ce,1e-30)),
          'mean_agc0_gain_after':sum(x['agc0_gain_after'] for x in subset)/len(subset),
          'mean_agc1_gain_after':sum(x['agc1_gain_after'] for x in subset)/len(subset),
          'post_diff_frames':sum(x['post_diff_samples']>0 for x in subset),
          'vad_active_disagreements':sum(x['vad0_active']!=x['vad1_active'] for x in subset),
          'limiter0_frames':sum(x['limiter0_active'] for x in subset),
          'limiter1_frames':sum(x['limiter1_active'] for x in subset)}
    return out

def audit(rows:list[dict])->dict:
    a0=[x['vad0_active'] for x in rows];a1=[x['vad1_active'] for x in rows]
    probdiff=[x['vad0_probability']!=x['vad1_probability'] for x in rows]
    actdiff=[a!=b for a,b in zip(a0,a1)]
    agcdiff=[x['agc0_gain_after']!=x['agc1_gain_after'] for x in rows]
    return {'full_control':confusion(a0),'full_candidate':confusion(a1),
      'stable_control':confusion(a0,stable_indices()),'stable_candidate':confusion(a1,stable_indices()),
      'control_segments':segment_events(a0),'candidate_segments':segment_events(a1),
      'vad_probability_diff_frames':sum(probdiff),'vad_probability_diff_longest_run':longest_run(probdiff),
      'vad_active_disagreement_frames':sum(actdiff),'vad_active_disagreement_longest_run':longest_run(actdiff),
      'agc_gain_state_diff_frames':sum(agcdiff),'agc_gain_state_diff_longest_run':longest_run(agcdiff),
      'post_agc_diff_frames':sum(x['post_diff_samples']>0 for x in rows),
      'post_agc_diff_longest_run':longest_run([x['post_diff_samples']>0 for x in rows])}

def run_one(binary:Path,label:str,pred:Path,controls:Path,dest:Path,revision:str)->dict:
    under_arm=label=='arm'
    execute(binary,pred,controls,dest,revision,under_arm)
    execute(binary,pred,controls,dest.with_name(dest.name+'-repeat'),revision,under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),'downstream repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=trace_rows(dest.with_suffix('.csv'));meta=load_json(dest.with_suffix('.json'))
    require(meta['status']=='PASS' and meta['production_controlled_agc'] is True
      and meta['vad_uses_upstream_probability'] is True and meta['agc_target_dbfs']==AGC_TARGET_DBFS
      and meta['limiter_dbfs']==LIMITER_DBFS and meta['frames']==N//HOP and meta['samples']==N,'downstream meta')
    require(meta['source_revision']==revision,'downstream source revision')
    require(meta['allow_gain_increase_false_frames']==sum(not x['allow_gain_increase'] for x in rows)
      and meta['pre_diff_frames']==sum(x['pre_diff_samples']>0 for x in rows)
      and meta['post_diff_frames']==sum(x['post_diff_samples']>0 for x in rows)
      and meta['agc_state_before_diff_frames']==sum(not x['agc_state_before_equal'] for x in rows)
      and meta['agc_state_after_diff_frames']==sum(x['agc0_gain_after']!=x['agc1_gain_after'] for x in rows)
      and meta['vad_state_before_diff_frames']==sum(not x['vad_state_before_equal'] for x in rows)
      and meta['vad_state_after_diff_frames']==sum(not x['vad_state_after_equal'] for x in rows)
      and meta['vad_probability_diff_frames']==sum(x['vad0_probability']!=x['vad1_probability'] for x in rows)
      and meta['vad_active_disagreement_frames']==sum(x['vad0_active']!=x['vad1_active'] for x in rows)
      and meta['limiter0_active_frames']==sum(x['limiter0_active'] for x in rows)
      and meta['limiter1_active_frames']==sum(x['limiter1_active'] for x in rows),
      'downstream meta/trace count mismatch')
    return {'rows':rows,'meta':meta,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
      'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def engineering(root:Path,binaries:dict,ns_root:Path,sync_root:Path,revision:str)->dict:
    root.mkdir();case_id='p0-route';pc=case_map(load_json(sync_root/'result.json'))[case_id]
    pred=ns_root/'cases'/case_id/'candidate.f32';controls=root/'controls.f32'
    receipt=write_controls(ns_root,case_id,pc['fault'],controls);records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+[binaries[label],'--self-test'],d/'self-test.log')
        rec=run_one(binaries[label],label,pred,controls,d/'candidate',revision)
        identity=predecessor_lane_identity(pred,d/'candidate.f32')
        records[label]={'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256'],
          'predecessor_identity':identity,'vad_active_disagreement_frames':rec['meta']['vad_active_disagreement_frames']}

    # Common-prefix future causality.
    raw=array.array('f');raw.frombytes(pred.read_bytes())
    if sys.byteorder!='little':raw.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        raw[5*k+2]*=-1.0;raw[5*k+3]*=-1.0
    if sys.byteorder!='little':raw.byteswap()
    future=root/'future-input.f32';future.write_bytes(raw.tobytes())
    execute(binaries['native'],future,controls,root/'future',revision)
    a=sync.floats(root/'native/candidate.f32',N*4);b=sync.floats(root/'future.f32',N*4)
    require(a[:(cutoff-2*HOP)*4]==b[:(cutoff-2*HOP)*4] and a[(cutoff+2*HOP)*4:]!=b[(cutoff+2*HOP)*4:],
            'downstream future causality')

    # Zero-audio/control identity.
    zero=root/'zero-input.f32';zero.write_bytes(b'\x00'*(N*5*4))
    zctl=root/'zero-controls.f32';zctl.write_bytes(b'\x00'*((N//HOP)*3*4))
    execute(binaries['native'],zero,zctl,root/'zero-output',revision)
    zr=trace_rows(root/'zero-output.csv')
    require(all(x['pre_diff_samples']==0 and x['post_diff_samples']==0 and x['vad0_active']==x['vad1_active'] for x in zr),
            'zero downstream arm identity')

    bad=root/'partial-controls.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],pred,bad,root/'bad',revision))),capture_output=True)
    require(p.returncode!=0,'partial downstream controls accepted');(root/'bad.log').write_bytes(p.stderr)

    invalid=root/'invalid-controls.f32';data=bytearray(controls.read_bytes());data[0:4]=struct.pack('<f',2.0);invalid.write_bytes(data)
    p=subprocess.run(list(map(str,command(binaries['native'],pred,invalid,root/'invalid',revision))),capture_output=True)
    require(p.returncode!=0,'invalid downstream probability accepted');(root/'invalid.log').write_bytes(p.stderr)

    before=(root/'native/candidate.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],pred,controls,root/'native/candidate',revision))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/candidate.f32').read_bytes(),'downstream overwrite accepted')
    (root/'overwrite.log').write_bytes(p.stderr)

    result={'status':'PASS','fixed_case':case_id,'controls_receipt':receipt,'records':records,
      'future':True,'zero_input_arm_identity':True,'invalid_controls_rejected':True,
      'invalid_probability_rejected':True,'overwrite_rejected':True,'self_test':True}
    write_json(root/'result.json',result);return result

def run(ns_root:Path,sync_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor_receipt(ns_root,sync_root,revision);nr=load_json(ns_root/'result.json');sr=load_json(sync_root/'result.json')
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');write_json(root/'predecessor-verification.json',pred)
    (root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,ns_root,sync_root,revision)
    nm=case_map(nr);sm=case_map(sr);cases=[]
    for case_id in sorted(nm,key=lambda x:(nm[x]['pair'],FAULTS.index(nm[x]['fault']))):
        nc=nm[case_id];sc=sm[case_id];fault=nc['fault'];d=root/'cases'/case_id;d.mkdir(parents=True)
        controls=d/'controls.f32';receipt=write_controls(ns_root,case_id,fault,controls)
        pred_file=ns_root/'cases'/case_id/'candidate.f32'
        rec=run_one(binaries['native'],'native',pred_file,controls,d/'candidate',revision)
        identity=predecessor_lane_identity(pred_file,d/'candidate.f32')
        control=floats(d/'candidate.f32',4,2);candidate=floats(d/'candidate.f32',4,3)
        control_m=metrics(sync_root/sc['input'],d/'candidate.f32',2,fault)
        candidate_m=metrics(sync_root/sc['input'],d/'candidate.f32',3,fault)
        require(nc['ns_only_metrics']==sync.metrics(list(sync.floats(sync_root/sc['input'],N*4)[1::4]),
          list(sync.floats(sync_root/sc['input'],N*4)[2::4]),floats(pred_file,5,2),fault),'control pre-AGC predecessor metric')
        require(nc['ns_freq_res_metrics']==sync.metrics(list(sync.floats(sync_root/sc['input'],N*4)[1::4]),
          list(sync.floats(sync_root/sc['input'],N*4)[2::4]),floats(pred_file,5,3),fault),'candidate pre-AGC predecessor metric')
        cases.append({'case_id':case_id,'pair':nc['pair'],'fault':fault,'controls_receipt':receipt,
          'predecessor_identity':identity,'ns_only_pre_agc_metrics':nc['ns_only_metrics'],
          'ns_freq_pre_agc_metrics':nc['ns_freq_res_metrics'],'post_agc_control_metrics':control_m,
          'post_agc_candidate_metrics':candidate_m,'phase_stats':phase_stats(rec['rows'],control,candidate),
          'downstream_audit':audit(rec['rows']),'meta':rec['meta'],
          'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE05-NS-AGC-VAD-DOWNSTREAM-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'predecessor':pred,'agc_target_dbfs':AGC_TARGET_DBFS,'limiter_dbfs':LIMITER_DBFS,
      'controlled_agc':True,'vad_uses_same_upstream_probability':True,'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(ns_root:Path,sync_root:Path,root:Path,revision:str,predecessor_verified=False)->dict:
    verify_seal(root);pred=predecessor_receipt(ns_root,sync_root,revision)
    r=load_json(root/'result.json');receipt=load_json(root/'predecessor-verification.json')
    require(r['predecessor']==receipt==pred,'downstream predecessor receipt')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'downstream plan drift')
    require(r['experiment_id']=='FE05-NS-AGC-VAD-DOWNSTREAM-V1' and r['decision']==DECISION
      and r['shipping_authority'] is False and r['data_role']==ROLE and r['execution_source_revision']==revision
      and r['case_count']==6,'downstream authority')
    require(r['agc_target_dbfs']==AGC_TARGET_DBFS and r['limiter_dbfs']==LIMITER_DBFS
      and r['controlled_agc'] is True and r['vad_uses_same_upstream_probability'] is True,'downstream scope')
    for name in ('ns_agc_vad_downstream_runner.c','ns_agc_vad_downstream.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'downstream source drift '+name)

    nr=load_json(ns_root/'result.json');sr=load_json(sync_root/'result.json');nm=case_map(nr);sm=case_map(sr)
    require({c['case_id'] for c in r['cases']}==set(nm)==set(sm),'downstream case set')
    for c in r['cases']:
        nc=nm[c['case_id']];sc=sm[c['case_id']];fault=c['fault'];d=root/'cases'/c['case_id']
        expected_controls=controls_bytes(nsfreq.trace_rows(ns_root/'cases'/c['case_id']/'candidate.csv',fault))
        require((d/'controls.f32').read_bytes()==expected_controls,'downstream controls derivation')
        require(c['controls_receipt']['sha256']==sha256(expected_controls)
          and c['controls_receipt']['source_trace_sha256']==sha256((ns_root/'cases'/c['case_id']/'candidate.csv').read_bytes()),
          'downstream controls receipt')
        rows=trace_rows(d/'candidate.csv');identity=predecessor_lane_identity(ns_root/'cases'/c['case_id']/'candidate.f32',d/'candidate.f32')
        require(c['predecessor_identity']==identity,'downstream predecessor lane identity')
        control=floats(d/'candidate.f32',4,2);candidate=floats(d/'candidate.f32',4,3)
        cm=metrics(sync_root/sc['input'],d/'candidate.f32',2,fault);nmtr=metrics(sync_root/sc['input'],d/'candidate.f32',3,fault)
        require(c['ns_only_pre_agc_metrics']==nc['ns_only_metrics'] and c['ns_freq_pre_agc_metrics']==nc['ns_freq_res_metrics'],
                'downstream pre-AGC metrics drift')
        require(c['post_agc_control_metrics']==cm and c['post_agc_candidate_metrics']==nmtr,'downstream post-AGC metrics')
        require(c['phase_stats']==phase_stats(rows,control,candidate) and c['downstream_audit']==audit(rows),'downstream audit recomputation')
        meta=load_json(d/'candidate.json');require(c['meta']==meta and meta['source_revision']==revision,'downstream meta receipt')
        require(c['output_sha256']==sha256((d/'candidate.f32').read_bytes())
          and c['trace_sha256']==sha256((d/'candidate.csv').read_bytes()),'downstream case hashes')

    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('ns-agc-vad-'+label)).read_bytes()),
                'downstream binary identity')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','downstream engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'downstream Arm ELF')
    return {'status':'VERIFIED_NS_AGC_VAD_DOWNSTREAM','cases':6,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(ns_root:Path,sync_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','controls','binary');rejected=[]
    predecessor_receipt(ns_root,sync_root,revision)
    with tempfile.TemporaryDirectory(prefix='ns-agc-vad-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor']['ns_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['post_agc_candidate_metrics']['final_far_ratio_db']=0.0
            else:
                c=rr['cases'][0];base=copy/'cases'/c['case_id']
                pth=base/'candidate.f32' if kind=='output' else base/'candidate.csv' if kind=='trace' else base/'controls.f32' if kind=='controls' else copy/'ns-agc-vad-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(ns_root,sync_root,copy,revision,predecessor_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed downstream negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        def mean(key):
            vals=[x[key]['final_far_ratio_db'] for x in rows];return sum(vals)/len(vals)
        groups.append({'fault':fault,'cases':len(rows),
          'pre_agc_ns_only_mean_final_far_db':mean('ns_only_pre_agc_metrics'),
          'pre_agc_ns_freq_mean_final_far_db':mean('ns_freq_pre_agc_metrics'),
          'post_agc_control_mean_final_far_db':mean('post_agc_control_metrics'),
          'post_agc_candidate_mean_final_far_db':mean('post_agc_candidate_metrics'),
          'vad_active_disagreement_frames':[x['downstream_audit']['vad_active_disagreement_frames'] for x in rows],
          'vad_probability_diff_frames':[x['downstream_audit']['vad_probability_diff_frames'] for x in rows],
          'agc_gain_state_diff_frames':[x['downstream_audit']['agc_gain_state_diff_frames'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--ns-predecessor',type=Path,required=True)
    p.add_argument('--sync-predecessor',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'downstream revision')
    if a.negative_evidence:r=negatives(a.ns_predecessor,a.sync_predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.ns_predecessor,a.sync_predecessor,a.output,a.execution_source)
    else:
        r=run(a.ns_predecessor,a.sync_predecessor,a.output,a.execution_source)
        print('NS_AGC_VAD_DOWNSTREAM_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_NS_AGC_VAD_DOWNSTREAM','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
