#!/usr/bin/env python3
"""FE04 paired BF/AEC-order diagnosis using actual native modules. No promotion."""
from __future__ import annotations
import argparse
import array
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from contracts import ROOT, hex_digest, load_json, require, sha256
from libfvad_reference import write_json, seal_output, run_logged, git_tree
from speech_fir import verify_seal
import speech_spatial as speech
import speech_spatial_weights as spatial

HERE = Path(__file__).resolve().parent
PLAN = ROOT/'.github/research/frontend-evolution-v1/bf-aec-order-v1.json'
RATE, HOP, N, DELAY = 16000, 160, 256000, 21
BANKS = ('fir33', 'diffuse-1.0')
EVENTS = ('none', 'steer', 'path')
ROLE = 'DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT'
DECISION = 'BF_AEC_ORDER_DIAGNOSTIC_NO_PROMOTION'
CFLAGS = ['-std=c11','-O2','-Wall','-Wextra','-Wpedantic','-Werror','-ffp-contract=off']
DEPENDENCIES = ('array_native.c','array_native.h','bf_aec_order_runner.c','bf_aec_order.py',
 'contracts.py','libfvad_reference.py','speech_fir.py','speech_spatial.py','speech_source.py',
 'speech_spatial_weights.py','spatial_weights.py','array_qualification.py','array_fir_checks.py')


def packed(values):
    a=array.array('f', values)
    if sys.byteorder!='little': a.byteswap()
    return a.tobytes()


def floats(path, count=None):
    blob=path.read_bytes();require(len(blob)%4==0,'partial F32')
    a=array.array('f');a.frombytes(blob)
    if sys.byteorder!='little':a.byteswap()
    require((count is None or len(a)==count) and all(math.isfinite(v) for v in a),'F32 count/nonfinite')
    return a


def design(name, arm):
    g=speech.geometry(name,0);n=len(g['positions_m']);mode=3 if arm=='fir33' else 4
    tokens=['FE04_ORDER_V1',str(n),str(mode),'EVENT']
    tokens += [format(v,'.17g') for row in g['positions_m'] for v in row]
    banks=[]
    for angle in (0,60):
        config,bank,kernels=spatial.filters(speech.geometry(name,angle),arm)
        banks.append({'angle':angle,'bank':bank,'kernels':kernels})
        if bank is not None:tokens += [format(v,'.9g') for row in bank['coefficients'] for v in row]
    return ' '.join(tokens)+'\n',banks


def echo_path(m, changed):
    return ([(96+2*m,.38+.02*m),(229+4*m,.23),(511+3*m,-.13)] if changed else
            [(64+3*m,.55-.03*m),(173+5*m,-.19+.01*m),(349+7*m,.11)])


def envelope(k,start,end):
    if not start<=k<end:return 0.0
    return min(1.0,(k-start)/160.0,(end-1-k)/160.0)


def render_inputs(data, root, renderer):
    """Offline generator. Existing future-using renderer is NOT deployable DSP."""
    record=spatial.source_check(data);rows=record['speaker_selection']
    require([r['speaker'] for r in rows[:4]]==[1673,1919,1988,1993],'fixed development selection')
    result={}
    for pair in range(2):
        far_raw=speech.values((data/rows[2*pair+1]['window_file']).read_bytes(),'h',64000)
        far=array.array('f',(far_raw[k%64000]/32768*.15*envelope(k%64000,0,64000)*envelope(k,32000,224000) for k in range(N)))
        for name in speech.POSITIONS:
            n=len(speech.POSITIONS[name]);prefix=f'p{pair}-{name}';dest=root/prefix;dest.mkdir()
            cfg=dest/'render.txt';cfg.write_bytes(speech.render_config(speech.geometry(name,0),.15))
            raw=dest/'render.f64'
            run_logged([renderer,cfg,data/rows[2*pair]['window_file'],raw],dest/'render.log')
            base=speech.values(raw.read_bytes(),'d',64000*n);raw.unlink()
            near=array.array('f',(base[(k%64000)*n+m]*envelope(k%64000,0,64000)*
                sum(envelope(k,a,b) for a,b in ((0,32000),(96000,160000),(224000,N))) for k in range(N) for m in range(n)))
            for changed in (False,True):
                dest_file=dest/('path.f32' if changed else 'static.f32');samples=array.array('f')
                for k in range(N):
                    samples.extend(near[k*n:(k+1)*n])
                    for m in range(n):
                        samples.append(sum(v*far[k-t] for t,v in echo_path(m,changed and k>=128000) if k>=t))
                    frame=k//HOP;dt=frame<204 or 600<=frame<1004 or frame>=1400
                    samples.extend((far[k],float(200<=frame<1404),float(dt)))
                if sys.byteorder!='little':samples.byteswap()
                dest_file.write_bytes(samples.tobytes())
                result[pair,name,changed]=dest_file
    return result


def build(root,revision,compiler='cc',sanitize=False,arm=False):
    label='arm' if arm else 'sanitized' if sanitize else 'native'
    b=root/('build-'+label)
    flags='-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' if sanitize else '-O2'
    options=['cmake','-S',ROOT,'-B',b,'-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_C_COMPILER={compiler}',
        f'-DCMAKE_C_FLAGS={flags} -ffp-contract=off',f'-DAP_BUILD_SOURCE_REVISION={revision}',
        '-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=AEC','-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR',
        '-DAP_BUILD_TESTS=OFF','-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF',
        '-DAP_BUILD_MAX_AEC_TAIL_MS=64','-DAP_STRICT_WARNINGS=ON']
    if arm:options+=['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(options,root/(label+'-configure.log'))
    run_logged(['cmake','--build',b,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('order-'+label)
    cmd=[compiler,*CFLAGS,*(['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitize else []),
        '-I'+str(ROOT/'include'),'-I'+str(b/'generated'),HERE/'array_native.c',HERE/'bf_aec_order_runner.c',
        b/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'))
    shutil.copyfile(b/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(b/'libaudio_pipeline.a',root/(label+'-aec.a'))
    write_json(root/(label+'-build.json'),{'configure':list(map(str,options)),'link':list(map(str,cmd)),
        'processor_sha256':sha256(binary.read_bytes()),'compiler':compiler,'sanitize':sanitize,'arm':arm})
    run_logged([compiler,'--version'],root/(label+'-compiler.txt'))
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf-header.txt')
    shutil.rmtree(b)
    return binary


def command(binary, cfg, inp, dest, arm=False):
    cmd=([shutil.which('qemu-arm'),'-L','/usr/arm-linux-gnueabihf'] if arm else [])
    return [*cmd,binary,cfg,inp,dest.with_suffix('.f32'),dest.with_suffix('.json')]


def engineering(root,binary,arm=False):
    """Actual zero-render and fixed-transfer controls, including a full 8s transition."""
    root.mkdir();reports=[]
    for name in speech.POSITIONS:
        n=len(speech.POSITIONS[name]);samples=[]
        for k in range(131200): # 8.2s: includes scheduled 20ms direction/bank change
            value=.08*math.sin(.021*k)+.01*math.cos(.073*k)
            samples.extend([value]*n+[0.0]*n+[0.0,0.0,1.0])
        inp=root/(name+'.f32');inp.write_bytes(packed(samples))
        for mode in BANKS:
            cfg_text,_=design(name,mode);cfg=root/(name+'-'+mode+'.cfg');cfg.write_text(cfg_text.replace('EVENT','1'))
            dest=root/(name+'-'+mode)
            run_logged(command(binary,cfg,inp,dest,arm),dest.with_suffix('.log'))
            out=floats(dest.with_suffix('.f32'),131200*6);meta=load_json(dest.with_suffix('.json'))
            require(meta['steering_completed']==1 and meta['max_commutation_error']<=5e-6 and meta['max_additivity_error']<=5e-6,'zero-render algebra')
            require(all(out[k+2]==out[k] and out[k+4]==out[k] and out[k+1]==out[k+3]==out[k+5]==0 for k in range(0,len(out),6)), 'zero-render pass through')
            reports.append({'geometry':name,'mode':mode,'meta':meta})
    # Transport negatives leave earlier inputs/results untouched.
    cfg=next(root.glob('*.cfg'));inp=root/'invalid.f32'
    for kind,blob in [('empty',b''),('partial',b'\0'),('nonfinite',packed([float('nan')]*1120))]:
        inp.write_bytes(blob);dest=root/('bad-'+kind)
        proc=subprocess.run(list(map(str,command(binary,cfg,inp,dest,arm))),capture_output=True)
        require(proc.returncode!=0,'invalid transport accepted: '+kind)
        (root/('bad-'+kind+'.log')).write_bytes(proc.stderr)
        for suffix in ('.f32','.json'):
            p=dest.with_suffix(suffix)
            if p.exists():p.unlink()
    inp.unlink();adaptive=adaptive_control(root,binary,arm)
    write_json(root/'result.json',{'status':'PASS','cases':reports,'negative_cases':3,'adaptive_control':adaptive,'arm':arm})



def adaptive_control(root,binary,arm):
    """Run actual adapting AEC on every architecture; check repeat and future isolation."""
    name='ula4-70';n=4;count=16000;values=[];seed=1701;far=[]
    for k in range(count):
        seed=(1664525*seed+1013904223)&0xffffffff
        far.append(((seed>>8)/16777216-.5)*.1)
    for k in range(count):
        echo=[.55*far[k-64-3*m] if k>=64+3*m else 0 for m in range(n)]
        values.extend([0.0]*n+echo+[far[k],1.0,0.0])
    cfg=root/'adaptive.cfg';cfg.write_text(design(name,'diffuse-1.0')[0].replace('EVENT','0'))
    inp=root/'adaptive-input.f32';inp.write_bytes(packed(values));dest=root/'adaptive'
    run_logged(command(binary,cfg,inp,dest,arm),root/'adaptive.log')
    run_logged(command(binary,cfg,inp,root/'adaptive-repeat',arm),root/'adaptive-repeat.log')
    require((root/'adaptive.f32').read_bytes()==(root/'adaptive-repeat.f32').read_bytes(),'adaptive repeat')
    require(load_json(root/'adaptive.json')==load_json(root/'adaptive-repeat.json'),'adaptive repeat state')
    changed=values[:];prefix=8000
    for k in range(prefix,count):
        for j in range(2*n+1):changed[k*(2*n+3)+j]*=-1
    future=root/'adaptive-future-input.f32';future.write_bytes(packed(changed))
    run_logged(command(binary,cfg,future,root/'adaptive-future',arm),root/'adaptive-future.log')
    a=floats(root/'adaptive.f32',count*6);b=floats(root/'adaptive-future.f32',count*6)
    require(a[:prefix*6]==b[:prefix*6] and a[prefix*6:]!=b[prefix*6:],'adaptive hidden future or ignored input')
    require(any(abs(a[k*6+2]-a[k*6+1])>1e-7 for k in range(count)),'AEC did not execute/adapt')
    # Existing output must survive rejected overwrite unchanged.
    before=(root/'adaptive.f32').read_bytes()
    proc=subprocess.run(list(map(str,command(binary,cfg,inp,dest,arm))),capture_output=True)
    require(proc.returncode!=0 and (root/'adaptive.f32').read_bytes()==before,'overwrite protection')
    (root/'overwrite.log').write_bytes(proc.stderr)
    return {'status':'PASS','samples':count,'prefix_samples':prefix,'repeat_sha256':sha256(before),
            'future_prefix_equal':True,'future_suffix_different':True,'overwrite_rejected':True}


def check_sampled_inputs(root):
    """Independent finite input oracle: raw source -> near renderer and echo taps."""
    rows=load_json(root/'data/source-receipt.json')['speaker_selection']
    points=sorted(set(range(0,N,9973))|{0,159,160,31999,32000,63999,64000,95999,96000,
                                      127999,128000,128001,159999,160000,223999,224000,N-1})
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    for pair in range(2):
        near=speech.values((root/'data'/rows[2*pair]['window_file']).read_bytes(),'h',64000)
        far=speech.values((root/'data'/rows[2*pair+1]['window_file']).read_bytes(),'h',64000)
        def ref(k):
            return 0.0 if k<0 else f32(far[k%64000]/32768*.15*envelope(k%64000,0,64000)*envelope(k,32000,224000))
        for name,positions in speech.POSITIONS.items():
            n=len(positions);orig=positions[0];advances=[(v[0]-orig[0])*RATE/343 for v in positions]
            for event in ('static','path'):
                data=floats(root/'inputs'/f'p{pair}-{name}'/(event+'.f32'),N*(2*n+3))
                for k in points:
                    at=k*(2*n+3);frame=k//HOP
                    expected_flags=[float(200<=frame<1404),float(frame<204 or 600<=frame<1004 or frame>=1400)]
                    require(list(data[at+2*n+1:at+2*n+3])==expected_flags,'oracle gate corruption')
                    require(data[at+2*n]==ref(k),'render sample corruption')
                    for m,advance in enumerate(advances):
                        total=value=0.0;center=math.floor(advance)
                        for j in range(center-31,center+32):
                            t=advance-j
                            w=(1.0 if abs(t)<1e-14 else math.sin(math.pi*t)/(math.pi*t))*(.5*(1+math.cos(math.pi*t/32)) if abs(t)<=32 else 0)
                            total+=w;pos=k%64000+j
                            if 0<=pos<64000:value+=w*near[pos]/32768*.15
                        expected=value/total*envelope(k%64000,0,64000)*sum(envelope(k,a,b) for a,b in ((0,32000),(96000,160000),(224000,N)))
                        require(abs(data[at+m]-expected)<=2e-8,'near input renderer corruption')
                        expected=sum(v*ref(k-delay) for delay,v in echo_path(m,event=='path' and k>=128000))
                        require(abs(data[at+n+m]-expected)<=2e-8,'synthetic echo corruption')
    return len(points)*12


def windows(out, column):
    result=[]
    for k in range(0,N,1600):
        known=sum(float(out[t*6+1])**2 for t in range(k,k+1600))
        residual=sum(float(out[t*6+column])**2 for t in range(k,k+1600))
        valid=known/1600>1e-12
        result.append({'start_sample':k,'echo_energy':known/1600,'residual_energy':residual/1600,
                       'erle_db':10*math.log10(known/max(residual,1e-30)) if valid else None})
    return result


def recovery(rows):
    baseline=rows[50:60];be=sum(r['echo_energy'] for r in baseline);br=sum(r['residual_energy'] for r in baseline)
    if be/10<=1e-12:return {'baseline_erle_db':None,'recovery_after_event_ms':None}
    value=10*math.log10(be/max(br,1e-30));found=None
    for k in range(101,138):
        if all(r['erle_db'] is not None and r['erle_db']>=value-3 for r in rows[k:k+3]):found=(k-80)*100;break
    return {'baseline_erle_db':value,'recovery_after_event_ms':found}


def measure(path):
    out=floats(path,N*6);result={}
    for name,col in (('bf-then-aec',2),('aec-then-bf',4)):
        w=windows(out,col+1);near=list(out[0::6]);actual=list(out[col::6]);shadow=list(out[col+1::6])
        phases={}
        for tag,a,b in [('near-initial',.1,1.9),('far-before',5,6),('double-before',6.1,7.9),('double-after',8.1,9.9),('far-after',12,13.9),('near-final',14.1,15.9)]:
            lo,hi=int(a*RATE),int(b*RATE)
            phases[tag]={'start_sample':lo,'stop_sample':hi}
            if not tag.startswith('far'):
                phases[tag]['canonical_si_sdr_db']=speech.si_sdr_span(near,actual,lo,lo,hi-lo)
                refpower=sum(v*v for v in near[lo:hi]);err=sum((actual[k]-shadow[k]-near[k])**2 for k in range(lo,hi))
                phases[tag]['near_additivity_relative_error_energy']=err/max(refpower,1e-30)
        result[name]={'phases':phases,'windows':w,**recovery(w)}
    return result


def run(data,root,revision,require_arm=False):
    require(hex_digest(revision,40) and not root.exists(),'fresh root and exact revision')
    spatial.source_check(data);root.mkdir(parents=True);shutil.copytree(data,root/'data')
    shutil.copyfile(PLAN,root/'experiment.json');(root/'source').mkdir()
    for name in DEPENDENCIES:shutil.copyfile(HERE/name,root/'source'/name)
    shutil.copyfile(ROOT/'validation/tools/run_validation_engine.py',root/'source/run_validation_engine.py')
    # Copy exact production compilation inputs separately, not a fork in Git.
    for directory in ('src','include','cmake'):shutil.copytree(ROOT/directory,root/'production-source'/directory)
    shutil.copyfile(ROOT/'CMakeLists.txt',root/'production-source/CMakeLists.txt')
    binary=build(root,revision);sanitized=build(root,revision,sanitize=True)
    engineering(root/'engineering-native',binary);engineering(root/'engineering-sanitized',sanitized)
    if require_arm:
        require(shutil.which('arm-linux-gnueabihf-gcc') and shutil.which('qemu-arm'),'required Arm tools missing')
        arm=build(root,revision,'arm-linux-gnueabihf-gcc',arm=True)
        engineering(root/'engineering-arm',arm,arm=True)
    renderer=root/'renderer';run_logged(['cc',*CFLAGS,HERE/'speech_render.c','-lm','-o',renderer],root/'render-build.log')
    shutil.copyfile(HERE/'speech_render.c',root/'source/speech_render.c')
    (root/'inputs').mkdir();inputs=render_inputs(root/'data',root/'inputs',renderer)
    rows=[];started=time.monotonic()
    for pair in range(2):
        for geometry in speech.POSITIONS:
            for bank in BANKS:
                text,filters=design(geometry,bank)
                for event in EVENTS:
                    key=f'p{pair}-{geometry}-{bank}-{event}';d=root/'cases'/key;d.mkdir(parents=True)
                    cfg=d/'config.txt';cfg.write_text(text.replace('EVENT',str(EVENTS.index(event))))
                    write_json(d/'filters.json',{'filters':filters})
                    inp=inputs[pair,geometry,event=='path'];dest=d/'output'
                    run_logged(command(binary,cfg,inp,dest),d/'run.log')
                    run_logged(command(binary,cfg,inp,d/'repeat'),d/'repeat.log')
                    require(dest.with_suffix('.f32').read_bytes()==(d/'repeat.f32').read_bytes(),'paired repeat bytes')
                    require(load_json(dest.with_suffix('.json'))==load_json(d/'repeat.json'),'repeat state/metadata')
                    # Retain explicit repeated digest, avoid duplicating every 6-channel output.
                    write_json(d/'repeat-receipt.json',{'sha256':sha256((d/'repeat.f32').read_bytes()),'samples':N,'columns':6})
                    (d/'repeat.f32').unlink();(d/'repeat.json').unlink()
                    rows.append({'case_id':key,'pair':pair,'geometry':geometry,'bank':bank,'event':event,
                        'input':inp.relative_to(root).as_posix(),'metrics':measure(d/'output.f32')})
    report={'schema_version':1,'experiment_id':'FE04-BF-AEC-ORDER-V1','decision':DECISION,'shipping_authority':False,
        'data_role':ROLE,'execution_source_revision':revision,'processor_sha256':sha256(binary.read_bytes()),
        'require_arm':require_arm,'case_count':36,'orders':2,'cases':rows,'host_complete_matrix_elapsed_seconds':time.monotonic()-started,
        'timing_authority':'NONE_TARGET','synchronization':'exact-sample-reference-no-SYNC-estimator','activity':'oracle-schedule-not-measured-DTD'}
    write_json(root/'result.json',report);seal_output(root,report)
    return report


def verify(root,revision, require_arm=False):
    verify_seal(root);r=load_json(root/'result.json');p=load_json(PLAN)
    require(type(r['require_arm']) is bool and (not require_arm or r['require_arm']), 'required Arm evidence absent')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'changed plan')
    require(r['decision']==DECISION and r['data_role']==ROLE and r['shipping_authority'] is False,'false promotion/data authority')
    require(r['synchronization']==p['synchronization'] and r['activity']==p['activity'] and r['timing_authority']=='NONE_TARGET','false mechanism/target claim')
    require(r['execution_source_revision']==revision and r['processor_sha256']==sha256((root/'order-native').read_bytes()),'source/binary identity')
    spatial.source_check(root/'data')
    for name in (*DEPENDENCIES,'speech_render.c'):require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'changed source '+name)
    require((root/'source/run_validation_engine.py').read_bytes()==(ROOT/'validation/tools/run_validation_engine.py').read_bytes(),'canonical evaluator drift')
    for directory in ('src','include','cmake'):
        require(git_tree(root/'production-source'/directory)==git_tree(ROOT/directory),'production source drift')
    require((root/'production-source/CMakeLists.txt').read_bytes()==(ROOT/'CMakeLists.txt').read_bytes(),'build configuration drift')
    expected={f'p{k}-{g}-{b}-{e}' for k in range(2) for g in speech.POSITIONS for b in BANKS for e in EVENTS}
    require(r['case_count']==36 and r['orders']==2 and len(r['cases'])==36 and {x['case_id'] for x in r['cases']}==expected,'incomplete case matrix')
    for row in r['cases']:
        key=f"p{row['pair']}-{row['geometry']}-{row['bank']}-{row['event']}";require(key==row['case_id'],'wrong case mapping')
        d=root/'cases'/key;cfg,filters=design(row['geometry'],row['bank'])
        require((d/'config.txt').read_text()==cfg.replace('EVENT',str(EVENTS.index(row['event']))),'changed bank/event')
        require(load_json(d/'filters.json')==json.loads(json.dumps({'filters':filters})),'changed filters')
        require(row['input']==f"inputs/p{row['pair']}-{row['geometry']}/{'path' if row['event']=='path' else 'static'}.f32",'input selection')
        n=len(speech.POSITIONS[row['geometry']]);floats(root/row['input'],N*(2*n+3))
        m=load_json(d/'output.json');repeat=load_json(d/'repeat-receipt.json')
        require(m['status']=='PASS' and m['source_revision']==revision and m['samples']==N and m['frames']==1600 and m['columns']==6 and m['common_delay_samples']==DELAY,'incorrect output identity/count/timing')
        require(m['microphones']==n and m['mode']==(3 if row['bank']=='fir33' else 4) and m['event']==EVENTS.index(row['event']),'incorrect configuration metadata')
        require(m['shipping_authority'] is False and m['steering_completed']==int(row['event']=='steer'),'steering authority/count')
        require(m['pre_order_state_bytes']==m['array_state_bytes']+n*m['aec_state_bytes'] and m['post_order_state_bytes']==m['array_state_bytes']+m['aec_state_bytes'],'state accounting')
        require(m['max_additivity_error']<=5e-6 and m['max_commutation_error']<=5e-6,'additivity/linear reference check')
        raw=floats(d/'output.f32',N*6)
        measured=max(abs(float(raw[k+a])-raw[k+a+1]-raw[k]) for k in range(0,len(raw),6) for a in (2,4))
        require(m['max_additivity_error']==measured and m['peak']==max(map(abs,raw))
                and m['out_of_range_values']==sum(abs(v)>1 for v in raw),'output metrics contradict PCM')
        require(repeat=={'sha256':sha256((d/'output.f32').read_bytes()),'samples':N,'columns':6},'repeat not bound')
        require(row['metrics']==measure(d/'output.f32'),'metric recomputation failed')
    for label in ('native','sanitized',*(['arm'] if r['require_arm'] else [])):
        build_info=load_json(root/(label+'-build.json'))
        require(build_info['processor_sha256']==sha256((root/('order-'+label)).read_bytes()) and build_info['arm']==(label=='arm') and build_info['sanitize']==(label=='sanitized'),'built processor identity')
        if label=='arm':require('ARM' in (root/'arm-elf-header.txt').read_text() and 'ELF32' in (root/'arm-elf-header.txt').read_text(),'not an Arm ELF')
        tests=load_json(root/('engineering-'+label)/'result.json')
        require(tests['status']=='PASS' and len(tests['cases'])==6 and tests['negative_cases']==3,'engineering missing')
        require(tests['adaptive_control']['status']=='PASS' and tests['adaptive_control']['future_prefix_equal'] is True
                and tests['adaptive_control']['overwrite_rejected'] is True,'adaptive controls missing')
        prefix=root/('engineering-'+label)
        require((prefix/'adaptive.f32').read_bytes()==(prefix/'adaptive-repeat.f32').read_bytes(),'adaptive repeat mismatch')
        require((prefix/'adaptive.f32').read_bytes()[:8000*24]==(prefix/'adaptive-future.f32').read_bytes()[:8000*24],'adaptive future-prefix mismatch')
        require(sha256((prefix/'adaptive.f32').read_bytes())==tests['adaptive_control']['repeat_sha256'],'adaptive byte identity')
    probes=check_sampled_inputs(root)
    return {'status':'PASS','cases':36,'orders':72,'input_oracle_probes':probes,'files':len(load_json(root/'manifest.json')['files'])}


def negative_evidence(root,revision):
    """Reseal mutations on an independent copy; never damage the real evidence."""
    mutations=('promotion','oracle-authority','role','missing-case','order-count','metric','metadata','truncated','source','required-arm')
    rejected=[]
    with tempfile.TemporaryDirectory(prefix='fe04-neg-') as temp:
        copyroot=Path(temp)/'evidence';shutil.copytree(root,copyroot)
        original={name:(copyroot/name).read_bytes() for name in ('result.json','manifest.json','SHA256SUMS')}
        for kind in mutations:
            r=json.loads(original['result.json']);row=r['cases'][0];d=copyroot/'cases'/row['case_id'];restore=[]
            if kind=='promotion':r['shipping_authority']=True
            elif kind=='oracle-authority':r['activity']='production-DTD-qualified'
            elif kind=='role':r['data_role']='blind-product-confirmation'
            elif kind=='missing-case':r['cases'].pop()
            elif kind=='order-count':r['orders']=1
            elif kind=='metric':row['metrics']['bf-then-aec']['baseline_erle_db']+=1
            elif kind=='required-arm':r['require_arm']=False
            else:
                path=(d/'output.json' if kind=='metadata' else d/'output.f32' if kind=='truncated' else copyroot/'source/bf_aec_order_runner.c')
                b=path.read_bytes();restore.append((path,b))
                if kind=='metadata':v=json.loads(b);v['samples']-=1;write_json(path,v)
                elif kind=='truncated':path.write_bytes(b[:-4])
                else:path.write_bytes(b+b'\n/* changed source */\n')
            write_json(copyroot/'result.json',r);seal_output(copyroot,r)
            try:verify(copyroot,revision,require_arm=(kind=='required-arm'))
            except (ValueError,KeyError,IndexError,RuntimeError,AssertionError):rejected.append(kind)
            else:raise AssertionError('resealed negative passed: '+kind)
            for path,b in restore:path.write_bytes(b)
            for name,b in original.items():(copyroot/name).write_bytes(b)
    require(len(rejected)==len(mutations),'negative suite incomplete')
    return {'status':'PASS','rejected':rejected}


class ContractTests(unittest.TestCase):
    def test_ramp(self):
        self.assertEqual(envelope(0,0,32000),0);self.assertEqual(envelope(31999,0,32000),0)
        self.assertEqual(envelope(160,0,32000),1);self.assertEqual(envelope(32000,0,32000),0)
    def test_echo_bounds(self):
        for m in range(4):
            for changed in (False,True):self.assertLess(max(t for t,v in echo_path(m,changed))+54,1024)
    def test_recovery_missing(self):
        rows=[{'echo_energy':0,'residual_energy':0,'erle_db':None} for _ in range(160)]
        self.assertIsNone(recovery(rows)['recovery_after_event_ms'])
    def test_recovery_three(self):
        rows=[{'echo_energy':1,'residual_energy':.1,'erle_db':10} for _ in range(160)]
        self.assertAlmostEqual(recovery(rows)['recovery_after_event_ms'],2100)
        for row in rows[101:]:row['erle_db']=None
        self.assertIsNone(recovery(rows)['recovery_after_event_ms'])
    def test_canonical_signature(self):
        x=[math.sin(.1*k) for k in range(160)]
        self.assertTrue(math.isfinite(speech.si_sdr_span(x,x,0,0,160)))
    def test_fixed_matrix(self):
        for name in speech.POSITIONS:
            for arm in BANKS:
                cfg,banks=design(name,arm);self.assertIn('EVENT',cfg);self.assertEqual(len(banks),2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--execution-source');parser.add_argument('--require-arm',action='store_true')
    parser.add_argument('--verify',action='store_true');parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--negative-evidence',action='store_true')
    args=parser.parse_args()
    if args.self_test:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests))
        return 0 if result.wasSuccessful() else 1
    require(args.output is not None and hex_digest(args.execution_source,40),'output/revision required')
    try:
        if args.negative_evidence:result=negative_evidence(args.output,args.execution_source)
        elif args.verify:result=verify(args.output,args.execution_source,args.require_arm)
        else:
            require(args.source is not None,'source required');run(args.source,args.output,args.execution_source,args.require_arm)
            result=verify(args.output,args.execution_source)
        print(json.dumps(result));return 0
    except Exception as exc:
        if not args.verify and not args.negative_evidence and args.output.exists():write_json(args.output/'failure.json',{'status':'FAILED','error':str(exc),'shipping_authority':False})
        raise
if __name__=='__main__':raise SystemExit(main())
