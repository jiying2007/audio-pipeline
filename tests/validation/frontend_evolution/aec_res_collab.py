#!/usr/bin/env python3
"""AEC -> time-domain RES collaboration under exact FE04 timestamp authority."""
from __future__ import annotations
import argparse, array, csv, json, math, shutil, subprocess, sys, tempfile
from pathlib import Path
import sync_faults as sync
import sync_timestamp_authority as authority
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/aec-res-collab-v1.json'
RUNNER=HERE/'aec_res_collab_runner.c'
DECISION='AEC_RES_COLLAB_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
FAULTS=sync.FAULTS
LABELS=sync.LABELS
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
HEADER=['frame','known_lead_samples','timestamp_observed','route_jump','aec_reset','sync_delay_samples',
        'underrun','used_far','used_dt','aec_echo_energy','pre_residual_energy','res_gain',
        'pre_output_energy','post_output_energy']
PHASES={
  'near-initial':(10,190),'far-before':(210,600),'double-before':(610,790),
  'double-after':(810,990),'far-after':(1010,1400),'near-final':(1410,1590)
}

def case_map(r:dict)->dict:
    return {c['case_id']:c for c in r['cases']}

def predecessor_receipt(sync_root:Path,reset_root:Path,exact_root:Path,revision:str,full:bool)->dict:
    if full:
        v=authority.verify(sync_root,reset_root,exact_root,revision)
        require(v['status']=='VERIFIED_SYNC_TIMESTAMP_AUTHORITY','exact timestamp predecessor verify')
    else:
        for root in (sync_root,reset_root,exact_root): verify_seal(root)
    sr=load_json(sync_root/'result.json');rr=load_json(reset_root/'result.json');er=load_json(exact_root/'result.json')
    require(sr['execution_source_revision']==rr['execution_source_revision']==er['execution_source_revision']==revision,'predecessor revision')
    require(er['experiment_id']=='FE04-SYNC-TIMESTAMP-AUTHORITY-V1' and er['case_count']==6,'exact predecessor')
    return {'sync_manifest_sha256':sha256((sync_root/'manifest.json').read_bytes()),
      'reset_manifest_sha256':sha256((reset_root/'manifest.json').read_bytes()),
      'exact_manifest_sha256':sha256((exact_root/'manifest.json').read_bytes()),
      'exact_result_sha256':sha256((exact_root/'result.json').read_bytes()),'source_revision':revision}

def trace_rows(path:Path,fault:str)->list[dict]:
    rows=[]
    with path.open(newline='') as f:
        rd=csv.DictReader(f);require(rd.fieldnames==HEADER,'AEC/RES trace schema')
        for index,row in enumerate(rd):
            require(index<N//HOP and None not in row.values(),'AEC/RES trace count/partial')
            item={}
            for key in HEADER:
                if key in ('aec_echo_energy','pre_residual_energy','res_gain','pre_output_energy','post_output_energy'):
                    value=float(row[key]);require(math.isfinite(value),'nonfinite AEC/RES trace');item[key]=value
                else:item[key]=int(row[key])
            require(item['frame']==index,'AEC/RES trace order')
            lead=sync.expected_lead(fault,index,N//HOP)
            require(item['known_lead_samples']==lead and item['timestamp_observed']==1
              and item['sync_delay_samples']==lead and item['underrun']==0,'AEC/RES timestamp authority')
            expected=int(fault=='route' and index==800)
            require(item['route_jump']==expected and item['aec_reset']==expected,'AEC/RES route/reset')
            require(item['used_far'] in (0,1) and item['used_dt'] in (0,1),'AEC/RES Activity flags')
            require(0.0 < item['res_gain'] <= 1.0 and item['aec_echo_energy']>=0.0
              and item['pre_residual_energy']>=0.0 and item['pre_output_energy']>=0.0
              and item['post_output_energy']>=0.0,'AEC/RES physical bounds')
            rows.append(item)
    require(len(rows)==N//HOP,'AEC/RES frame count')
    return rows

def build(root:Path,revision:str,label:str)->Path:
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    b=root/('build-'+label)
    opts=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(flags+['-ffp-contract=off']),'-DAP_BUILD_SOURCE_REVISION='+revision,
      '-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=SYNC,ACTIVITY,AEC,RES','-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR',
      '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF',
      '-DAP_BUILD_MAX_AEC_TAIL_MS=64','-DAP_BUILD_MAX_DELAY_MS=120','-DAP_STRICT_WARNINGS=ON']
    if arm:opts+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(opts,root/(label+'-configure.log'));run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('aec-res-'+label)
    cmd=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),RUNNER,b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'));run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-library.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
      'library_sha256':sha256((root/(label+'-library.a')).read_bytes()),'compiler':cc,'sanitized':san,'arm':arm,
      'configure':list(map(str,opts)),'link':list(map(str,cmd))})
    shutil.rmtree(b);return binary

def command(binary:Path,fault:str,inp:Path,dest:Path,under_arm:bool=False)->list:
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if under_arm else []
    return [*prefix,binary,fault,inp,dest.with_suffix('.f32'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary:Path,fault:str,inp:Path,dest:Path,under_arm:bool=False)->None:
    run_logged(command(binary,fault,inp,dest,under_arm),dest.with_suffix('.log'))

def words(path:Path)->array.array:
    a=array.array('I');a.frombytes(path.read_bytes())
    if sys.byteorder!='little':a.byteswap()
    return a

def floats(path:Path,stride:int,lane:int)->list[float]:
    raw=sync.floats(path,N*stride)
    return list(raw[lane::stride])

def pre_res_identity(candidate:Path,exact:Path)->dict:
    cw=words(candidate);ew=words(exact)
    require(len(cw)==N*3 and len(ew)==N*2,'AEC/RES packed size')
    pre_mismatch=sum(a!=b for a,b in zip(cw[0::3],ew[0::2]))
    ref_mismatch=sum(a!=b for a,b in zip(cw[2::3],ew[1::2]))
    require(pre_mismatch==0,'pre-RES AEC output diverged from exact predecessor')
    require(ref_mismatch==0,'AEC/RES reference diverged from exact predecessor')
    return {'pre_res_aec_bit_mismatches':pre_mismatch,'reference_bit_mismatches':ref_mismatch,
      'pre_res_aec_bit_identity':True,'reference_bit_identity':True}

def metrics(inp:Path,out:Path,lane:int,fault:str)->dict:
    source=sync.floats(inp,N*4);target=list(source[1::4]);echo=list(source[2::4]);actual=floats(out,3,lane)
    return sync.metrics(target,echo,actual,fault)

def phase_gain(rows:list[dict],pre:list[float],post:list[float])->dict:
    result={}
    for name,(a,b) in PHASES.items():
        subset=rows[a:b];require(subset,'empty gain phase')
        gains=[x['res_gain'] for x in subset]
        lo=a*HOP;hi=b*HOP
        pre_e=sum(x*x for x in pre[lo:hi])/max(1,hi-lo)
        post_e=sum(x*x for x in post[lo:hi])/max(1,hi-lo)
        result[name]={'frames':len(subset),'gain_mean':sum(gains)/len(gains),'gain_min':min(gains),'gain_max':max(gains),
          'double_talk_frames':sum(x['used_dt'] for x in subset),
          'gain_lt_0_99_frames':sum(x['res_gain']<0.99 for x in subset),
          'gain_lt_0_95_frames':sum(x['res_gain']<0.95 for x in subset),
          'output_rms_delta_db':10.0*math.log10(max(post_e,1e-30)/max(pre_e,1e-30))}
    return result

def dt_runs(rows:list[dict])->list[dict]:
    out=[];i=0
    while i<len(rows):
        if not rows[i]['used_dt']:
            i+=1;continue
        start=i
        while i<len(rows) and rows[i]['used_dt']:i+=1
        end=i
        gains=[x['res_gain'] for x in rows[start:end]]
        first_099=next((k for k,g in enumerate(gains) if g>=0.99),None)
        out.append({'start_frame':start,'end_frame_exclusive':end,'frames':end-start,
          'first_gain':gains[0],'min_gain':min(gains),'max_gain':max(gains),
          'first_ge_0_99_offset_frames':first_099,
          'first_ge_0_99_ms':None if first_099 is None else first_099*10})
    return out

def run_one(binary:Path,label:str,inp:Path,fault:str,dest:Path)->dict:
    under_arm=label=='arm'
    execute(binary,fault,inp,dest,under_arm);execute(binary,fault,inp,dest.with_name(dest.name+'-repeat'),under_arm)
    for suffix in ('.f32','.json','.csv'):
        require(dest.with_suffix(suffix).read_bytes()==dest.with_name(dest.name+'-repeat').with_suffix(suffix).read_bytes(),'AEC/RES repeat')
        dest.with_name(dest.name+'-repeat').with_suffix(suffix).unlink()
    rows=trace_rows(dest.with_suffix('.csv'),fault);meta=load_json(dest.with_suffix('.json'))
    expected=1 if fault=='route' else 0
    require(meta['status']=='PASS' and meta['timestamp_authority'] is True and meta['route_jump_resets_aec'] is True
      and meta['route_jump_resets_res'] is False and meta['res_quality']=='FULL','AEC/RES meta')
    require(meta['timestamp_observations']==N//HOP and meta['route_jumps']==expected
      and meta['aec_resets']==expected and meta['underruns']==0,'AEC/RES counters')
    return {'rows':rows,'meta':meta,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes()),
      'trace_sha256':sha256(dest.with_suffix('.csv').read_bytes())}

def engineering(root:Path,binaries:dict,sync_root:Path,exact_root:Path,revision:str)->dict:
    root.mkdir();pc=case_map(load_json(sync_root/'result.json'))['p0-route'];inp=sync_root/pc['input']
    exact=exact_root/'cases'/'p0-route'/'timestamp-reset.f32';records={}
    for label in LABELS:
        d=root/label;d.mkdir()
        run_logged((['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if label=='arm' else [])+[binaries[label],'--self-test'],d/'self-test.log')
        rec=run_one(binaries[label],label,inp,'route',d/'candidate')
        records[label]={'output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256'],
          'route_jumps':rec['meta']['route_jumps'],'aec_resets':rec['meta']['aec_resets'],
          'res_state_bytes':rec['meta']['res_state_bytes']}
        if label=='native':records[label]['predecessor_identity']=pre_res_identity(d/'candidate.f32',exact)
    # Native common-prefix future causality.
    data=array.array('f');data.frombytes(inp.read_bytes())
    if sys.byteorder!='little':data.byteswap()
    cutoff=200000
    for k in range(cutoff,N):
        for c in range(4):data[4*k+c]*=-1.0
    if sys.byteorder!='little':data.byteswap()
    future=root/'future-input.f32';future.write_bytes(data.tobytes())
    execute(binaries['native'],'route',future,root/'future')
    a=sync.floats(root/'native/candidate.f32',N*3);b=sync.floats(root/'future.f32',N*3)
    require(a[:(cutoff-2*HOP)*3]==b[:(cutoff-2*HOP)*3] and a[(cutoff+2*HOP)*3:]!=b[(cutoff+2*HOP)*3:],'AEC/RES future causality')
    # Zero-render control: far detector/RES must not invent attenuation from a missing render.
    z=array.array('f');z.frombytes(inp.read_bytes())
    if sys.byteorder!='little':z.byteswap()
    for k in range(N):z[4*k+3]=0.0
    if sys.byteorder!='little':z.byteswap()
    zero=root/'zero-render.f32';zero.write_bytes(z.tobytes())
    execute(binaries['native'],'static',zero,root/'zero-render')
    zr=trace_rows(root/'zero-render.csv','static')
    require(all(x['res_gain']==1.0 for x in zr),'RES attenuated zero-render control')
    bad=root/'partial.f32';bad.write_bytes(b'\0')
    p=subprocess.run(list(map(str,command(binaries['native'],'static',bad,root/'bad'))),capture_output=True)
    require(p.returncode!=0,'partial AEC/RES input accepted');(root/'bad.log').write_bytes(p.stderr)
    before=(root/'native/candidate.f32').read_bytes()
    p=subprocess.run(list(map(str,command(binaries['native'],'route',inp,root/'native/candidate'))),capture_output=True)
    require(p.returncode!=0 and before==(root/'native/candidate.f32').read_bytes(),'AEC/RES overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    result={'status':'PASS','fixed_case':'p0-route','records':records,'future':True,'zero_render_unity_gain':True,
      'invalid_transport_rejected':True,'overwrite_rejected':True,'res_reset_lifecycle_self_test':True}
    write_json(root/'result.json',result);return result

def run(sync_root:Path,reset_root:Path,exact_root:Path,root:Path,revision:str)->dict:
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    pred=predecessor_receipt(sync_root,reset_root,exact_root,revision,full=True)
    sr=load_json(sync_root/'result.json');er=load_json(exact_root/'result.json')
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');write_json(root/'predecessor-verification.json',pred)
    (root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    binaries={label:build(root,revision,label) for label in LABELS}
    eng=engineering(root/'engineering',binaries,sync_root,exact_root,revision)
    sm=case_map(sr);em=case_map(er);cases=[]
    for case_id in sorted(sm,key=lambda x:(sm[x]['pair'],FAULTS.index(sm[x]['fault']))):
        pc=sm[case_id];ex=em[case_id];fault=pc['fault'];inp=sync_root/pc['input'];d=root/'cases'/case_id;d.mkdir(parents=True)
        rec=run_one(binaries['native'],'native',inp,fault,d/'candidate')
        exact=exact_root/'cases'/case_id/'timestamp-reset.f32'
        identity=pre_res_identity(d/'candidate.f32',exact)
        pre=floats(d/'candidate.f32',3,0);post=floats(d/'candidate.f32',3,1)
        pre_m=metrics(inp,d/'candidate.f32',0,fault);post_m=metrics(inp,d/'candidate.f32',1,fault)
        require(pre_m==ex['timestamp_reset_metrics'],'pre-RES metrics differ from exact predecessor')
        phases=phase_gain(rec['rows'],pre,post);runs=dt_runs(rec['rows'])
        cases.append({'case_id':case_id,'pair':pc['pair'],'fault':fault,'predecessor_identity':identity,
          'aec_only_metrics':ex['timestamp_reset_metrics'],'pre_res_metrics':pre_m,'post_res_metrics':post_m,
          'delta_final_far_db':None if pre_m['final_far_ratio_db'] is None or post_m['final_far_ratio_db'] is None
            else post_m['final_far_ratio_db']-pre_m['final_far_ratio_db'],
          'phase_gain':phases,'double_talk_runs':runs,
          'double_talk_gain_lt_0_99_frames':rec['meta']['double_talk_gain_lt_0_99_frames'],
          'double_talk_gain_lt_0_95_frames':rec['meta']['double_talk_gain_lt_0_95_frames'],
          'res_gain_mean':rec['meta']['res_gain_mean'],'res_gain_min':rec['meta']['res_gain_min'],
          'candidate_output_sha256':rec['output_sha256'],'trace_sha256':rec['trace_sha256']})
    report={'schema_version':1,'experiment_id':'FE04-AEC-RES-COLLAB-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'predecessor':pred,'transport':'EXACT_SYNTHETIC_TIMESTAMP_NOT_DUT','res_mode':'TIME_DOMAIN_FULL_NO_NS',
      'route_jump_resets_aec':True,'route_jump_resets_res':False,'engineering':eng,'cases':cases}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(sync_root:Path,reset_root:Path,exact_root:Path,root:Path,revision:str,predecessors_verified=False)->dict:
    verify_seal(root);pred=predecessor_receipt(sync_root,reset_root,exact_root,revision,full=False)
    r=load_json(root/'result.json');receipt=load_json(root/'predecessor-verification.json')
    require(r['predecessor']==receipt==pred,'AEC/RES predecessor receipt')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'AEC/RES plan drift')
    require(r['experiment_id']=='FE04-AEC-RES-COLLAB-V1' and r['decision']==DECISION
      and r['shipping_authority'] is False and r['data_role']==ROLE and r['execution_source_revision']==revision
      and r['case_count']==6,'AEC/RES authority')
    require(r['transport']=='EXACT_SYNTHETIC_TIMESTAMP_NOT_DUT' and r['res_mode']=='TIME_DOMAIN_FULL_NO_NS'
      and r['route_jump_resets_aec'] is True and r['route_jump_resets_res'] is False,'AEC/RES scope')
    for name in ('aec_res_collab_runner.c','aec_res_collab.py'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'AEC/RES source drift '+name)
    sr=load_json(sync_root/'result.json');er=load_json(exact_root/'result.json');sm=case_map(sr);em=case_map(er)
    require({c['case_id'] for c in r['cases']}==set(sm)==set(em),'AEC/RES case set')
    for c in r['cases']:
        pc=sm[c['case_id']];ex=em[c['case_id']];fault=c['fault'];inp=sync_root/pc['input'];d=root/'cases'/c['case_id']
        rows=trace_rows(d/'candidate.csv',fault);identity=pre_res_identity(d/'candidate.f32',exact_root/'cases'/c['case_id']/'timestamp-reset.f32')
        pre=floats(d/'candidate.f32',3,0);post=floats(d/'candidate.f32',3,1)
        pre_m=metrics(inp,d/'candidate.f32',0,fault);post_m=metrics(inp,d/'candidate.f32',1,fault)
        require(c['predecessor_identity']==identity and c['pre_res_metrics']==pre_m and c['post_res_metrics']==post_m,'AEC/RES recomputation')
        require(c['aec_only_metrics']==ex['timestamp_reset_metrics']==pre_m,'AEC/RES baseline')
        require(c['phase_gain']==phase_gain(rows,pre,post) and c['double_talk_runs']==dt_runs(rows),'AEC/RES gain stats')
        meta=load_json(d/'candidate.json')
        require(c['double_talk_gain_lt_0_99_frames']==meta['double_talk_gain_lt_0_99_frames']
          and c['double_talk_gain_lt_0_95_frames']==meta['double_talk_gain_lt_0_95_frames']
          and c['res_gain_mean']==meta['res_gain_mean'] and c['res_gain_min']==meta['res_gain_min'],'AEC/RES meta receipt')
        require(c['candidate_output_sha256']==sha256((d/'candidate.f32').read_bytes())
          and c['trace_sha256']==sha256((d/'candidate.csv').read_bytes()),'AEC/RES hashes')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('aec-res-'+label)).read_bytes()),'AEC/RES binary')
    eng=load_json(root/'engineering/result.json');require(eng==r['engineering'] and eng['status']=='PASS','AEC/RES engineering')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'AEC/RES Arm ELF')
    return {'status':'VERIFIED_AEC_RES_COLLAB','cases':6,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(sync_root:Path,reset_root:Path,exact_root:Path,root:Path,revision:str)->dict:
    kinds=('promotion','predecessor','missing-case','metric','output','trace','gain-stat','binary');rejected=[]
    predecessor_receipt(sync_root,reset_root,exact_root,revision,full=False)
    with tempfile.TemporaryDirectory(prefix='aec-res-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='predecessor':rr['predecessor']['exact_manifest_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['post_res_metrics']['final_far_ratio_db']=0.0
            elif kind=='gain-stat':rr['cases'][0]['res_gain_min']=1.0
            else:
                case=rr['cases'][0]['case_id'];base=copy/'cases'/case/'candidate'
                pth=base.with_suffix('.f32') if kind=='output' else base.with_suffix('.csv') if kind=='trace' else copy/'aec-res-native'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(sync_root,reset_root,exact_root,copy,revision,predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed AEC/RES negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r:dict)->dict:
    groups=[]
    for fault in FAULTS:
        rows=[x for x in r['cases'] if x['fault']==fault]
        before=[x['pre_res_metrics']['final_far_ratio_db'] for x in rows];after=[x['post_res_metrics']['final_far_ratio_db'] for x in rows]
        groups.append({'fault':fault,'cases':len(rows),'aec_only_mean_final_far_db':sum(before)/len(before),
          'aec_res_mean_final_far_db':sum(after)/len(after),'delta_final_far_db':[x['delta_final_far_db'] for x in rows],
          'double_talk_gain_lt_0_99_frames':[x['double_talk_gain_lt_0_99_frames'] for x in rows],
          'double_talk_gain_lt_0_95_frames':[x['double_talk_gain_lt_0_95_frames'] for x in rows],
          'double_before_gain_mean':[x['phase_gain']['double-before']['gain_mean'] for x in rows],
          'double_after_gain_mean':[x['phase_gain']['double-after']['gain_mean'] for x in rows],
          'double_before_rms_delta_db':[x['phase_gain']['double-before']['output_rms_delta_db'] for x in rows],
          'double_after_rms_delta_db':[x['phase_gain']['double-after']['output_rms_delta_db'] for x in rows]})
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument('--sync-predecessor',type=Path,required=True);p.add_argument('--reset-predecessor',type=Path,required=True)
    p.add_argument('--exact-predecessor',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'AEC/RES revision')
    if a.negative_evidence:r=negatives(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.output,a.execution_source)
    elif a.verify:r=verify(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.output,a.execution_source)
    else:
        r=run(a.sync_predecessor,a.reset_predecessor,a.exact_predecessor,a.output,a.execution_source)
        print('AEC_RES_COLLAB_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_AEC_RES_COLLAB','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
