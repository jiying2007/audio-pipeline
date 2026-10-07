#!/usr/bin/env python3
"""Pristine SpeexDSP AEC vs current post-BF AEC on one frozen disclosed matrix."""
from __future__ import annotations
import argparse, array, json, math, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import activity_gates as activity
import bf_aec_order as order
import speech_spatial as speech
import speexdsp_source
from contracts import ROOT, admit_execution, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/speexdsp-aec-reference-v1.json'
ADMISSION=ROOT/'.github/research/frontend-evolution-v1/speexdsp-admission.json'
CATALOG=ROOT/'.github/research/frontend-evolution-v1/sources.json'
RUNNER=HERE/'speexdsp_aec_runner.c'
DECISION='SPEEXDSP_AEC_REFERENCE_DIAGNOSTIC_NO_PROMOTION'
ROLE='DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
RATE,HOP,N=16000,160,256000
EVENTS=('none','steer','path')
BACKENDS=('ap','speex')
LABELS=('native','sanitized','arm')
CFLAGS=['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
UPSTREAM_C=('libspeexdsp/mdf.c','libspeexdsp/fftwrap.c','libspeexdsp/smallft.c')

def i16_bytes(values):
    a=array.array('h',values)
    if sys.byteorder!='little':a.byteswap()
    return a.tobytes()

def i16_values(path,count=None):
    data=path.read_bytes();require(len(data)%2==0,'partial S16')
    a=array.array('h');a.frombytes(data)
    if sys.byteorder!='little':a.byteswap()
    require(count is None or len(a)==count,'S16 count')
    return a

def f16(values):
    return [v/32768.0 for v in values]

def qone(x):
    require(math.isfinite(x),'nonfinite quantization input')
    v=float(x)*32768.0
    if v>=32767.0:return 32767,int(v>32767.0)
    if v<=-32768.0:return -32768,int(v<-32768.0)
    q=math.floor(v+.5) if v>=0 else math.ceil(v-.5)
    return int(max(-32768,min(32767,q))),0

def quantize(values):
    out=[];clips=0
    for v in values:
        q,c=qone(v);out.append(q);clips+=c
    return out,clips

def admission(source):
    verified=speexdsp_source.verify(source);receipt=load_json(source/'source-receipt.json')
    catalog=admit_execution(load_json(CATALOG),'speexdsp');review=load_json(ADMISSION)
    require(catalog['commit']==receipt['source_commit']==review['source_commit'],'source commit admission')
    require(review['source_tree']==receipt['source_tree'],'source tree admission')
    require(catalog['materialized_source_sha256']==receipt['materialized_source_sha256']==review['materialized_source_sha256'],'source materialization admission')
    require(catalog['admission_receipt_sha256']==sha256(ADMISSION.read_bytes()),'admission receipt hash')
    require(review['source_lock_sha256']==receipt['source_lock_sha256'],'source lock admission')
    require(review['files_sha256']==receipt['files_sha256'] and review['generated_config_sha256']==receipt['generated_config_sha256'],'source byte admission')
    require(review['admission']['decision']=='EXECUTION_ADMITTED_MINIMAL_AEC_REFERENCE_ONLY','execution not admitted')
    require(verified['status']=='VERIFIED_SOURCE_BYTES_NOT_EXECUTED','preflight status')
    return receipt

def correlation_binding(base,correlation,revision):
    verify_seal(correlation);r=load_json(correlation/'result.json')
    require(r['execution_source_revision']==revision,'correlation source revision')
    require(r['activity_manifest_sha256']==sha256((base/'activity/manifest.json').read_bytes())
      and r['order_manifest_sha256']==sha256((base/'order/manifest.json').read_bytes()),'correlation predecessor binding')
    require(r['shipping_authority'] is False and r['case_count']==36,'correlation evidence authority/count')
    return r

def build(root,source,revision,label):
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    opt=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    b=root/('build-'+label)
    options=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+cc,
      '-DCMAKE_C_FLAGS='+' '.join(opt+['-ffp-contract=off']),'-DAP_BUILD_SOURCE_REVISION='+revision,
      '-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=AEC,ACTIVITY','-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR',
      '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF',
      '-DAP_BUILD_MAX_AEC_TAIL_MS=64','-DAP_STRICT_WARNINGS=ON']
    if arm:options+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(options,root/(label+'-configure.log'));run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    upstream=source/'upstream';gen=source/'generated/include/speex';objs=[]
    extflags=['-std=c99',*opt,'-DFLOATING_POINT','-DUSE_SMALLFT','-DEXPORT=',
      '-I'+str(gen),'-I'+str(upstream/'include'),'-I'+str(upstream/'libspeexdsp')]
    for index,name in enumerate(UPSTREAM_C):
        obj=root/(label+'-speex-'+str(index)+'.o');cmd=[cc,*extflags,'-c',upstream/name,'-o',obj]
        run_logged(cmd,root/(label+'-speex-'+str(index)+'.log'));objs.append(obj)
    runner_obj=root/(label+'-runner.o')
    rflags=[cc,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else []),
      '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),'-I'+str(upstream/'include'),'-I'+str(gen),
      '-c',RUNNER,'-o',runner_obj]
    run_logged(rflags,root/(label+'-runner-build.log'))
    binary=root/('speex-ref-'+label)
    link=[cc,*(['-fsanitize=address,undefined'] if san else []),runner_obj,*objs,b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(link,root/(label+'-link.log'));run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-ap.a'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
      'ap_library_sha256':sha256((root/(label+'-ap.a')).read_bytes()),'compiler':cc,'sanitized':san,'arm':arm,
      'configure':list(map(str,options)),'external_compile_flags':extflags,'link':list(map(str,link))})
    shutil.rmtree(b);return binary

def command(binary,mode,inp,dest,arm=False):
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if arm else []
    return [*prefix,binary,mode,inp,dest.with_suffix('.s16'),dest.with_suffix('.json'),dest.with_suffix('.csv')]

def execute(binary,mode,inp,dest,arm=False):
    run_logged(command(binary,mode,inp,dest,arm),dest.with_suffix('.log'))

def engineering(root,binary,label):
    root.mkdir();arm=label=='arm';count=32000;seed=1709;far=[];near=[]
    for k in range(count):
        seed=(1664525*seed+1013904223)&0xffffffff;far.append(((seed>>8)/16777216-.5)*.18)
        near.append((.08*math.sin(.017*k)+.03*math.cos(.031*k)) if 9600<=k<19200 else 0.0)
    mic=[near[k]+(.55*far[k-64] if k>=64 else 0)+(-.18*far[k-173] if k>=173 else 0) for k in range(count)]
    qm,_=quantize(mic);qr,_=quantize(far);pairs=[v for ab in zip(qm,qr) for v in ab]
    inp=root/'input.s16';inp.write_bytes(i16_bytes(pairs));records=[]
    for mode in BACKENDS:
        dest=root/mode;execute(binary,mode,inp,dest,arm);execute(binary,mode,inp,root/(mode+'-repeat'),arm)
        for suffix in ('.s16','.json','.csv'):
            require(dest.with_suffix(suffix).read_bytes()==(root/(mode+'-repeat')).with_suffix(suffix).read_bytes(),'engineering repeat')
        meta=load_json(dest.with_suffix('.json'));require(meta['samples']==count and meta['frame_samples']==HOP and meta['sample_rate_hz']==RATE,'engineering identity')
        if mode=='ap':
            require(meta['activity_used_by_backend'] is True and meta['ap_active_taps']==1024 and meta['ap_block_samples']>0,'AP control identity')
        else:
            require(meta['activity_used_by_backend'] is False and meta['speex_frame_samples']==160 and meta['speex_sampling_rate_hz']==16000
              and meta['speex_realized_filter_samples']==1120 and meta['speex_fft_window_samples']==320
              and meta['explicit_playback_buffer_delay_samples']==0,'Speex runtime identity')
        records.append({'backend':mode,'sha256':sha256(dest.with_suffix('.s16').read_bytes()),'meta':meta})
    prefix_samples=16000;changed=list(pairs)
    for k in range(prefix_samples*2,len(changed)):changed[k]=-changed[k] if changed[k]!=-32768 else 32767
    future=root/'future.s16';future.write_bytes(i16_bytes(changed))
    for mode in BACKENDS:
        execute(binary,mode,future,root/(mode+'-future'),arm)
        a=(root/(mode+'.s16')).read_bytes();b=(root/(mode+'-future.s16')).read_bytes();cut=prefix_samples*2
        require(a[:cut]==b[:cut] and a[cut:]!=b[cut:],'future causality')
    for kind,data in (('empty',b''),('partial',b'\0')):
        bad=root/(kind+'.s16');bad.write_bytes(data)
        p=subprocess.run(list(map(str,command(binary,'ap',bad,root/('bad-'+kind),arm))),capture_output=True)
        require(p.returncode!=0,'invalid transport accepted');(root/('bad-'+kind+'.log')).write_bytes(p.stderr)
    before=(root/'ap.s16').read_bytes();p=subprocess.run(list(map(str,command(binary,'ap',inp,root/'ap',arm))),capture_output=True)
    require(p.returncode!=0 and before==(root/'ap.s16').read_bytes(),'overwrite accepted');(root/'overwrite.log').write_bytes(p.stderr)
    p=subprocess.run(list(map(str,command(binary,'wrong',inp,root/'wrong',arm))),capture_output=True)
    require(p.returncode!=0,'invalid backend accepted');(root/'wrong.log').write_bytes(p.stderr)
    result={'status':'PASS','label':label,'samples':count,'records':records,'repeat':True,'future':True,
      'invalid_transport_cases':2,'overwrite_rejected':True,'invalid_backend_rejected':True}
    write_json(root/'result.json',result);return result

def windows(actual,echo):
    rows=[]
    for k in range(0,N,1600):
        ee=sum(v*v for v in echo[k:k+1600])/1600;rr=sum(v*v for v in actual[k:k+1600])/1600;idx=k//1600
        valid=21<=idx<60 or 101<=idx<140
        rows.append({'start_sample':k,'echo_energy':ee,'residual_energy':rr,
          'erle_db':10*math.log10(ee/max(rr,1e-30)) if valid and ee>1e-12 else None})
    return rows

def metrics(target,echo,actual):
    w=windows(actual,echo);phases={}
    for tag,a,b in [('near-initial',.1,1.9),('double-before',6.1,7.9),('double-after',8.1,9.9),('near-final',14.1,15.9)]:
        lo,hi=int(a*RATE),int(b*RATE);phases[tag]=speech.si_sdr_span(target,actual,lo,lo,hi-lo)
    rec=order.recovery(w);start=rec['recovery_after_event_ms'];rec['recovery_confirmed_after_event_ms']=None if start is None else start+300
    ee=sum(x['echo_energy'] for x in w[120:139]);rr=sum(x['residual_energy'] for x in w[120:139])
    final=10*math.log10(ee/max(rr,1e-30)) if ee/19>1e-12 else None
    return {'phases_si_sdr_relative_to_quantized_bf_target_db':phases,'far_only_windows':w,'final_far_ratio_db':final,**rec}

def make_case(base,correlation,row,dest):
    raw=order.floats(base/'order/cases'/row['case_id']/'output.f32',N*6)
    observed=order.floats(correlation/'cases'/row['case_id']/'guard.csv.observed.f32',N*2)
    target=list(raw[0::6]);echo=list(raw[1::6]);mic=list(observed[0::2]);ref=list(observed[1::2])
    require(max(abs(mic[k]-float(target[k])-float(echo[k])) for k in range(N))<=5e-6,
            'exact BF observation/component disagreement')
    qm,cm=quantize(mic);qr,cr=quantize(ref);qt,ct=quantize(target);qe,ce=quantize(echo)
    dest.mkdir(parents=True)
    (dest/'input.s16').write_bytes(i16_bytes([v for ab in zip(qm,qr) for v in ab]))
    (dest/'target.s16').write_bytes(i16_bytes(qt));(dest/'echo.s16').write_bytes(i16_bytes(qe))
    receipt={'input_sha256':sha256((dest/'input.s16').read_bytes()),'target_sha256':sha256((dest/'target.s16').read_bytes()),
      'echo_sha256':sha256((dest/'echo.s16').read_bytes()),'mic_clip_count':cm,'render_clip_count':cr,
      'target_clip_count':ct,'echo_clip_count':ce,'samples':N,'layout':'interleaved-mic-render-s16le'}
    write_json(dest/'quantization.json',receipt);return receipt

def selected(base):
    rows=[x for x in load_json(base/'order/result.json')['cases'] if x['geometry']=='ula4-70' and x['bank']=='fir33' and x['event'] in EVENTS]
    require(len(rows)==6 and {(x['pair'],x['event']) for x in rows}=={(p,e) for p in range(2) for e in EVENTS},'fixed six-case selection')
    return sorted(rows,key=lambda x:(x['pair'],EVENTS.index(x['event'])))

def run(base,source,correlation,root,revision):
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    activity.verify(base/'order',base/'activity',revision);receipt=admission(source);correlation_binding(base,correlation,revision)
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');shutil.copyfile(ADMISSION,root/'admission.json')
    shutil.copyfile(source/'source-receipt.json',root/'source-receipt.json');(root/'source').mkdir()
    for p in (RUNNER,Path(__file__)):shutil.copyfile(p,root/'source'/p.name)
    bins={};tests={}
    for label in LABELS:
        bins[label]=build(root,source,revision,label);tests[label]=engineering(root/('engineering-'+label),bins[label],label)
    rows=[];started=time.monotonic()
    for old in selected(base):
        key=old['case_id'];d=root/'cases'/key;quant=make_case(base,correlation,old,d)
        target=f16(i16_values(d/'target.s16',N));echo=f16(i16_values(d/'echo.s16',N));result={}
        for mode in BACKENDS:
            execute(bins['native'],mode,d/'input.s16',d/mode);execute(bins['native'],mode,d/'input.s16',d/(mode+'-repeat'))
            for suffix in ('.s16','.json','.csv'):require((d/(mode+suffix)).read_bytes()==(d/(mode+'-repeat'+suffix)).read_bytes(),'case repeat')
            out=f16(i16_values(d/(mode+'.s16'),N));result[mode]=metrics(target,echo,out)
            write_json(d/(mode+'-repeat-receipt.json'),{'sha256':sha256((d/(mode+'.s16')).read_bytes()),
              'meta_sha256':sha256((d/(mode+'.json')).read_bytes()),'trace_sha256':sha256((d/(mode+'.csv')).read_bytes())})
            for suffix in ('.s16','.json','.csv'):(d/(mode+'-repeat'+suffix)).unlink()
        rows.append({'case_id':key,'pair':old['pair'],'event':old['event'],'geometry':'ula4-70','bank':'fir33',
          'input':old['input'],'quantization':quant,'metrics':result})
    report={'schema_version':1,'experiment_id':'FE04-SPEEXDSP-AEC-REFERENCE-V1','decision':DECISION,
      'shipping_authority':False,'data_role':ROLE,'execution_source_revision':revision,'case_count':6,
      'source_materialized_sha256':receipt['materialized_source_sha256'],'source_receipt_sha256':sha256((source/'source-receipt.json').read_bytes()),
      'admission_sha256':sha256(ADMISSION.read_bytes()),'correlation_manifest_sha256':sha256((correlation/'manifest.json').read_bytes()),'engineering':tests,'cases':rows,
      'host_complete_matrix_elapsed_seconds':time.monotonic()-started,'timing_authority':'NONE_TARGET',
      'comparison':'whole-implementation-post-BF-AEC-not-DTD-causal-isolation','common_boundary':'saturating-s16le'}
    write_json(root/'result.json',report);seal_output(root,report);return report

def verify(base,source,correlation,root,revision,predecessors_verified=False):
    verify_seal(root)
    if predecessors_verified:
        receipt=load_json(source/'source-receipt.json')
    else:
        activity.verify(base/'order',base/'activity',revision)
        receipt=admission(source)
        correlation_binding(base,correlation,revision)
    r=load_json(root/'result.json');p=load_json(PLAN)
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes() and (root/'admission.json').read_bytes()==ADMISSION.read_bytes(),'plan/admission drift')
    require((root/'source-receipt.json').read_bytes()==(source/'source-receipt.json').read_bytes(),'source receipt drift')
    require(r['decision']==DECISION and r['shipping_authority'] is False and r['data_role']==ROLE and r['case_count']==6,'authority/matrix')
    require(r['execution_source_revision']==revision and r['source_materialized_sha256']==receipt['materialized_source_sha256']
      and r['source_receipt_sha256']==sha256((source/'source-receipt.json').read_bytes()) and r['admission_sha256']==sha256(ADMISSION.read_bytes())
      and r['correlation_manifest_sha256']==sha256((correlation/'manifest.json').read_bytes()),'identity binding')
    require(r['comparison']==p['comparison'] and r['common_boundary']==p['common_boundary'] and r['timing_authority']=='NONE_TARGET','mechanism claim')
    for name in ('speexdsp_aec_runner.c','speexdsp_aec_reference.py'):require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'source drift '+name)
    expected={x['case_id']:x for x in selected(base)}
    require(len(r['cases'])==6 and {x['case_id'] for x in r['cases']}==set(expected),'case set')
    for row in r['cases']:
        old=expected[row['case_id']];d=root/'cases'/row['case_id'];require(row['pair']==old['pair'] and row['event']==old['event'],'case identity')
        require(load_json(d/'quantization.json')==row['quantization'],'quantization receipt file')
        with tempfile.TemporaryDirectory(prefix='speex-q-') as temp:
            fresh=Path(temp)/'case';q=make_case(base,correlation,old,fresh);require(q==row['quantization'],'quantization receipt drift')
            for name in ('input.s16','target.s16','echo.s16'):require((fresh/name).read_bytes()==(d/name).read_bytes(),'quantized bytes drift '+name)
        target=f16(i16_values(d/'target.s16',N));echo=f16(i16_values(d/'echo.s16',N))
        for mode in BACKENDS:
            out=f16(i16_values(d/(mode+'.s16'),N));require(row['metrics'][mode]==metrics(target,echo,out),'metric recomputation')
            meta=load_json(d/(mode+'.json'));require(meta['status']=='PASS' and meta['source_revision']==revision and meta['samples']==N,'output identity')
            require(meta['sample_rate_hz']==RATE and meta['frame_samples']==HOP and meta['input_encoding']=='s16le' and meta['output_encoding']=='s16le','I/O contract')
            if mode=='ap':
                require(meta['backend']=='ap-activity-mdf' and meta['activity_used_by_backend'] is True and meta['ap_active_taps']==1024,'AP control drift')
            else:
                require(meta['backend']=='speexdsp-direct' and meta['activity_used_by_backend'] is False and meta['requested_filter_samples']==1024
                  and meta['speex_frame_samples']==160 and meta['speex_sampling_rate_hz']==16000 and meta['speex_realized_filter_samples']==1120
                  and meta['speex_fft_window_samples']==320 and meta['explicit_playback_buffer_delay_samples']==0
                  and meta['output_available_after_samples']==160,'Speex runtime contract')
            repeat=load_json(d/(mode+'-repeat-receipt.json'));require(repeat['sha256']==sha256((d/(mode+'.s16')).read_bytes())
              and repeat['meta_sha256']==sha256((d/(mode+'.json')).read_bytes()) and repeat['trace_sha256']==sha256((d/(mode+'.csv')).read_bytes()),'repeat identity')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'));require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('speex-ref-'+label)).read_bytes()),'binary identity')
        tests=load_json(root/('engineering-'+label)/'result.json');require(tests==r['engineering'][label] and tests['status']=='PASS' and len(tests['records'])==2,'engineering receipt')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'Arm ELF')
    return {'status':'VERIFIED_SPEEXDSP_AEC_REFERENCE','cases':6,'backends':2,'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}

def negatives(base,source,correlation,root,revision):
    kinds=('promotion','source-binding','missing-case','metric','input','output','binary','admission');rejected=[]
    # Immutable predecessor/source evidence is outside each temporary candidate copy.
    # Validate it once for this negative-evidence batch; each mutation below is still
    # resealed and passed through the same candidate verifier.
    activity.verify(base/'order',base/'activity',revision)
    admission(source)
    correlation_binding(base,correlation,revision)
    with tempfile.TemporaryDirectory(prefix='speex-aec-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy);keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            rr=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':rr['shipping_authority']=True
            elif kind=='source-binding':rr['source_materialized_sha256']='0'*64
            elif kind=='missing-case':rr['cases'].pop()
            elif kind=='metric':rr['cases'][0]['metrics']['speex']['final_far_ratio_db']=0.0
            else:
                pth=copy/'cases'/rr['cases'][0]['case_id']/'input.s16' if kind=='input' else copy/'cases'/rr['cases'][0]['case_id']/'speex.s16' if kind=='output' else copy/'speex-ref-native' if kind=='binary' else copy/'admission.json'
                blob=pth.read_bytes();changed.append((pth,blob));pth.write_bytes(blob+b'changed')
            write_json(copy/'result.json',rr);seal_output(copy,rr)
            try:verify(base,source,correlation,copy,revision,predecessors_verified=True)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed negative accepted '+kind)
            for pth,blob in changed:pth.write_bytes(blob)
            for pth,blob in keep.items():pth.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}

def summary(r):
    groups=[]
    for event in EVENTS:
        rows=[x for x in r['cases'] if x['event']==event];g={'event':event,'cases':len(rows)}
        for mode in BACKENDS:
            vals=[x['metrics'][mode] for x in rows];nums=[x['final_far_ratio_db'] for x in vals if x['final_far_ratio_db'] is not None]
            g[mode]={'mean_final_far_db':sum(nums)/len(nums) if nums else None,'recovered':sum(x['recovery_after_event_ms'] is not None for x in vals),
              'double_after_si_sdr':[x['phases_si_sdr_relative_to_quantized_bf_target_db']['double-after'] for x in vals]}
        groups.append(g)
    return {'decision':DECISION,'descriptive_only':True,'groups':groups}

def main():
    p=argparse.ArgumentParser();p.add_argument('--base-evidence',type=Path,required=True);p.add_argument('--source-evidence',type=Path,required=True)
    p.add_argument('--correlation-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'revision')
    if a.negative_evidence:r=negatives(a.base_evidence,a.source_evidence,a.correlation_evidence,a.output,a.execution_source)
    elif a.verify:r=verify(a.base_evidence,a.source_evidence,a.correlation_evidence,a.output,a.execution_source)
    else:
        r=run(a.base_evidence,a.source_evidence,a.correlation_evidence,a.output,a.execution_source);print('SPEEXDSP_AEC_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_SPEEXDSP_AEC_REFERENCE','cases':6,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
