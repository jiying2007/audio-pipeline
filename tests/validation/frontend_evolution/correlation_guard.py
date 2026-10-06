#!/usr/bin/env python3
"""One frozen FE04 lag-correlation veto; reuse Activity/AEC and canonical metrics."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import activity_gates as activity
import bf_aec_order as order
from contracts import ROOT, require, load_json, sha256, hex_digest
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE=Path(__file__).resolve().parent
PLAN=ROOT/'.github/research/frontend-evolution-v1/correlation-guard-v1.json'
DECISION='LAG_CORRELATION_GUARD_DEVELOPMENT_NO_PROMOTION'
EXTRA=['correlation_score','correlation_lag','correlation_warm','correlation_blocked']
SOURCES=('correlation_guard.h','correlation_guard_test.c','correlation_guard.py','bf_aec_order_runner.c','array_native.c','array_native.h','activity_gates.py')
PROBES=(1,20,219,610,799,800,990,1010,1390)


def trace(path):
    rows=[]
    with path.open(newline='') as f:
        reader=csv.DictReader(f)
        require(reader.fieldnames==activity.HEADER+EXTRA,'guard trace columns')
        for index,v in enumerate(reader):
            require(None not in v and None not in v.values(),'partial trace')
            r={k:(float(v[k]) if k in ('mic_energy','reference_energy','correlation_score') else int(v[k])) for k in v}
            require(r['frame']==index,'trace count/order')
            require(all(math.isfinite(r[k]) and r[k]>=0 for k in ('mic_energy','reference_energy','correlation_score')),'invalid trace numeric')
            require(0<=r['correlation_score']<=1 and 0<=r['correlation_lag']<=1023,'score/lag bounds')
            require(all(r[k] in (0,1) for k in activity.HEADER[3:]+EXTRA[2:]),'nonboolean flag')
            r['mic_energy']=activity.f32(r['mic_energy']);r['reference_energy']=activity.f32(r['reference_energy'])
            rows.append(r)
    return rows


def oracle_score(observed,frame):
    """Independent centered-vector formulation, NOT the C raw-moment formula."""
    stop=(frame+1)*160;start=stop-320
    if start<0:return 0.0,0
    indices=list(range(start,stop,4));m=[float(observed[2*k]) for k in indices]
    mean=math.fsum(m)/80;m=[v-mean for v in m];mm=math.fsum(v*v for v in m)
    if mm<=1e-20:return 0.0,0
    best=0.0;best_lag=0
    for lag in range(min(1023,start)+1):
        x=[float(observed[2*(k-lag)+1]) for k in indices]
        mean=math.fsum(x)/80;x=[v-mean for v in x];xx=math.fsum(v*v for v in x)
        if xx<=1e-20:continue
        cross=math.fsum(a*b for a,b in zip(m,x));score=min(1.0,cross*cross/(mm*xx))
        if score>best:best=score;best_lag=lag
    return best,best_lag


def validate(rows,monitored,baseline,observed,out,inp,n):
    require(len(rows)==len(monitored)==len(baseline)==len(out)//960,'guard trace frames')
    require(len(observed)==len(out)//3 and len(inp)==len(out)//6*(2*n+3),'observed count')
    blocked=release=0
    for index,(r,m,b) in enumerate(zip(rows,monitored,baseline)):
        require(all(r[k]==m[k]==b[k] for k in activity.HEADER[:-2]),'detector identity changed')
        require(all(r[k]==m[k] for k in EXTRA),'monitor decision changed')
        require((m['used_far'],m['used_dt'])==(b['used_far'],b['used_dt']),'guard monitor used wrong gates')
        require(r['correlation_warm']==int(index>=1),'warmup fabricated')
        score=r['correlation_score']
        if not r['detected_far']:blocked=release=0
        elif index<1 or score<.55:blocked,release=1,0
        elif blocked:
            release=release+1 if score>=.65 else 0
            if release>=3:blocked=release=0
        else:release=0
        require(r['correlation_blocked']==blocked,'guard hysteresis')
        require(r['used_far']==r['detected_far'] and r['used_dt']==int(bool(r['detected_far'] and (r['detected_dt'] or blocked))),'guard was not actually used')
    for k in range(len(out)//6):
        require(observed[2*k+1]==inp[k*(2*n+3)+2*n],'reference observation drift')
        require(abs(observed[2*k]-float(out[6*k])-float(out[6*k+1]))<=5e-6,'post-BF observation drift')
    audited=0
    for frame in PROBES:
        if frame>=len(rows):continue
        score,lag=oracle_score(observed,frame);r=rows[frame]
        require(abs(score-r['correlation_score'])<=1e-9 and lag==r['correlation_lag'],'independent lag/score disagreement')
        audited+=1
    return audited


def compile_one(base,root,revision,label):
    arm=label=='arm';san=label=='sanitized';cc='arm-linux-gnueabihf-gcc' if arm else 'cc'
    flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'] if san else ['-O2']
    inc=root/'include'/label/'audio_pipeline';inc.mkdir(parents=True)
    shutil.copyfile(base/'activity'/(label+'-build.h'),inc/'audio_pipeline_build.h')
    header=(inc/'audio_pipeline_build.h').read_text()
    require(revision in header and 'AP_HAVE_MODULE_ACTIVITY 1' in header,'unbound upstream library')
    lib=root/(label+'-library.a');shutil.copyfile(base/'activity'/(label+'-library.a'),lib)
    binary=root/('guard-'+label);test=root/('guard-test-'+label)
    cmd=[cc,*order.CFLAGS,*flags,'-DFE04_CORRELATION_GUARD=1','-I'+str(ROOT/'include'),'-I'+str(inc.parent),
         HERE/'array_native.c',HERE/'bf_aec_order_runner.c',lib,'-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'))
    run_logged([cc,*order.CFLAGS,*flags,HERE/'correlation_guard_test.c','-lm','-o',test],root/(label+'-test-build.log'))
    run_logged([cc,'--version'],root/(label+'-compiler.txt'))
    prefix=['qemu-arm','-L','/usr/arm-linux-gnueabihf'] if arm else []
    run_logged([*prefix,test],root/(label+'-test.json'))
    t=load_json(root/(label+'-test.json'));require(t['status']=='PASS' and t['controls']==11 and t['state_bytes']<16384,'guard controls/state')
    if arm:run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'source_revision':revision,'link':list(map(str,cmd)),
        'processor_sha256':sha256(binary.read_bytes()),'library_sha256':sha256(lib.read_bytes()),
        'test_sha256':sha256(test.read_bytes()),'arm':arm,'sanitized':san})
    return binary


def execute(binary,cfg,inp,dest,monitor=False,arm=False):
    flag='--monitor-correlation' if monitor else '--guard-correlation'
    run_logged([*order.command(binary,cfg,inp,dest,arm),flag,dest.with_suffix('.csv')],dest.with_suffix('.log'))


def engineering(base,root,binary,label):
    root.mkdir();src=base/'order'/('engineering-'+label);arm=label=='arm'
    for tag,config,inp in (('adaptive','adaptive.cfg','adaptive-input.f32'),('future','adaptive.cfg','adaptive-future-input.f32'),('steer','ula4-70-fir33.cfg','ula4-70.f32')):
        execute(binary,src/config,src/inp,root/tag,arm=arm)
        execute(binary,src/config,src/inp,root/(tag+'-monitor'),monitor=True,arm=arm)
        rows=trace(root/(tag+'.csv'));mon=trace(root/(tag+'-monitor.csv'))
        previous=base/'activity'/('engineering-'+label)/(('future' if tag=='future' else tag)+'-measured.csv')
        raw=order.floats(root/(tag+'.f32'));obs=order.floats(root/(tag+'.csv.observed.f32'))
        validate(rows,mon,activity.trace_rows(previous),obs,raw,order.floats(src/inp),4)
        require((root/(tag+'-monitor.f32')).read_bytes()==(previous.with_suffix('.f32')).read_bytes(),'monitor altered measured PCM')
    execute(binary,src/'adaptive.cfg',src/'adaptive-input.f32',root/'repeat',arm=arm)
    for suffix in ('.f32','.json','.csv','.csv.observed.f32'):
        require((root/('adaptive'+suffix)).read_bytes()==(root/('repeat'+suffix)).read_bytes(),'guard repeat')
    a=(root/'adaptive.f32').read_bytes();b=(root/'future.f32').read_bytes()
    require(a[:8000*24]==b[:8000*24] and a[8000*24:]!=b[8000*24:],'guard future leak/ignored input')
    require(trace(root/'adaptive.csv')[:50]==trace(root/'future.csv')[:50],'guard future trace leak')
    cmd=[*order.command(binary,src/'adaptive.cfg',src/'adaptive-input.f32',root/'adaptive',arm),'--guard-correlation',root/'overwrite.csv']
    p=subprocess.run(list(map(str,cmd)),capture_output=True);require(p.returncode!=0 and a==(root/'adaptive.f32').read_bytes(),'overwrite')
    (root/'overwrite.log').write_bytes(p.stderr)
    old=base/'activity'/('activity-'+label);old.chmod(0o755)
    cmd=[*order.command(old,src/'adaptive.cfg',src/'adaptive-input.f32',root/'unsupported',arm),'--guard-correlation',root/'unsupported.csv']
    p=subprocess.run(list(map(str,cmd)),capture_output=True);require(p.returncode!=0 and not (root/'unsupported.f32').exists(),'uncompiled guard silently accepted')
    (root/'unsupported.log').write_bytes(p.stderr)
    result={'status':'PASS','cases':3,'repeat':True,'future':True,'overwrite_rejected':True,'uncompiled_rejected':True}
    write_json(root/'result.json',result);return result


def run(base,root,revision):
    require(not root.exists() and hex_digest(revision,40),'fresh output/exact revision')
    activity.verify(base/'order',base/'activity',revision)
    root.mkdir(parents=True);shutil.copyfile(PLAN,root/'experiment.json');(root/'source').mkdir()
    for name in SOURCES:shutil.copyfile(HERE/name,root/'source'/name)
    tests={};bins={}
    for label in activity.LABELS:
        bins[label]=compile_one(base,root,revision,label)
        tests[label]=engineering(base,root/('engineering-'+label),bins[label],label)
    old=load_json(base/'activity/result.json');rows=[]
    for previous in old['cases']:
        key=previous['case_id'];d=root/'cases'/key;d.mkdir(parents=True)
        cfg=base/'order/cases'/key/'config.txt';inp=base/'order'/previous['input']
        execute(bins['native'],cfg,inp,d/'monitor',monitor=True)
        execute(bins['native'],cfg,inp,d/'guard')
        control=base/'activity/cases'/key/'measured.f32'
        require((d/'monitor.f32').read_bytes()==control.read_bytes(),'guard monitor changed baseline')
        execute(bins['native'],cfg,inp,d/'repeat')
        for suffix in ('.f32','.csv','.json','.csv.observed.f32'):
            require((d/('repeat'+suffix)).read_bytes()==(d/('guard'+suffix)).read_bytes(),'recorded guard repeat')
        write_json(d/'repeat-receipt.json',{'output_sha256':sha256((d/'guard.f32').read_bytes()),
            'trace_sha256':sha256((d/'guard.csv').read_bytes()),'observed_sha256':sha256((d/'guard.csv.observed.f32').read_bytes()),
            'monitor_sha256':sha256((d/'monitor.f32').read_bytes())})
        for suffix in ('.f32','.csv','.json','.csv.observed.f32'):(d/('repeat'+suffix)).unlink()
        (d/'monitor.f32').unlink()
        raw=order.floats(d/'guard.f32',order.N*6);tr=trace(d/'guard.csv')
        rows.append({k:previous[k] for k in ('case_id','pair','geometry','bank','event','input')} |
                    {'control':previous['measured'],'guard':activity.measures(raw,tr)})
    r={'schema_version':1,'experiment_id':'FE04-LAG-CORRELATION-GUARD-V1','decision':DECISION,
       'shipping_authority':False,'shadow_decomposition_authority':False,'data_role':order.ROLE,
       'execution_source_revision':revision,'timing_authority':'NONE_TARGET','cases':rows,'case_count':36,
       'order_results':144,'engineering':tests,'activity_manifest_sha256':sha256((base/'activity/manifest.json').read_bytes()),
       'order_manifest_sha256':sha256((base/'order/manifest.json').read_bytes())}
    write_json(root/'result.json',r);seal_output(root,r);return r


def verify(base,root,revision):
    verify_seal(base/'activity');verify_seal(base/'order');verify_seal(root)
    r=load_json(root/'result.json');old=load_json(base/'activity/result.json')
    require(r['execution_source_revision']==revision==old['execution_source_revision'],'execution source')
    require(r['decision']==DECISION and r['shipping_authority'] is False and r['shadow_decomposition_authority'] is False
        and r['data_role']==order.ROLE and r['timing_authority']=='NONE_TARGET','false authority')
    require(r['activity_manifest_sha256']==sha256((base/'activity/manifest.json').read_bytes()) and
        r['order_manifest_sha256']==sha256((base/'order/manifest.json').read_bytes()),'upstream binding')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'frozen design changed')
    for name in SOURCES:require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'source '+name)
    for label in activity.LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['source_revision']==revision and info['processor_sha256']==sha256((root/('guard-'+label)).read_bytes())
            and info['library_sha256']==sha256((root/(label+'-library.a')).read_bytes())
            and info['test_sha256']==sha256((root/('guard-test-'+label)).read_bytes()),'binary identity')
        require((root/(label+'-library.a')).read_bytes()==(base/'activity'/(label+'-library.a')).read_bytes(),'library was changed')
        tests=load_json(root/(label+'-test.json'));require(tests['status']=='PASS' and tests['controls']==11 and tests['state_bytes']<16384,'test/state')
        require(r['engineering'][label]==load_json(root/('engineering-'+label)/'result.json'),'engineering receipt')
        e=root/('engineering-'+label)
        for suffix in ('.f32','.json','.csv','.csv.observed.f32'):
            require((e/('adaptive'+suffix)).read_bytes()==(e/('repeat'+suffix)).read_bytes(),'engineering repeat')
        require((e/'adaptive.f32').read_bytes()[:8000*24]==(e/'future.f32').read_bytes()[:8000*24],'future prefix')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'Arm ELF')
    expected={x['case_id']:x for x in old['cases']}
    require(r['case_count']==36 and r['order_results']==144 and len(r['cases'])==36 and {x['case_id'] for x in r['cases']}==set(expected),'case matrix')
    audited=0
    for row in r['cases']:
        key=row['case_id'];previous=expected[key];d=root/'cases'/key
        require(all(row[k]==previous[k] for k in ('pair','geometry','bank','event','input')),'case identity')
        control=order.floats(base/'activity/cases'/key/'measured.f32',order.N*6)
        out=order.floats(d/'guard.f32',order.N*6);obs=order.floats(d/'guard.csv.observed.f32',order.N*2)
        require(out[0::6]==control[0::6] and out[1::6]==control[1::6],'BF changed')
        tr=trace(d/'guard.csv');mon=trace(d/'monitor.csv');baseline=activity.trace_rows(base/'activity/cases'/key/'measured.csv')
        n=len(order.speech.POSITIONS[row['geometry']]);inp=order.floats(base/'order'/row['input'])
        audited+=validate(tr,mon,baseline,obs,out,inp,n)
        require(row['control']==previous['measured'] and row['guard']==activity.measures(out,tr),'metric recheck')
        m=load_json(d/'guard.json');orig=load_json(base/'activity/cases'/key/'measured.json')
        require(all(m[k]==orig[k] for k in ('source_revision','build_config_digest','frames','samples','microphones','event','mode','columns','common_delay_samples','array_state_bytes','aec_state_bytes','steering_completed','shipping_authority')),'meta mismatch')
        require(m['peak']==max(map(abs,out)) and m['out_of_range_values']==sum(abs(v)>1 for v in out),'PCM range')
        repeat=load_json(d/'repeat-receipt.json')
        require(repeat=={'output_sha256':sha256((d/'guard.f32').read_bytes()),'trace_sha256':sha256((d/'guard.csv').read_bytes()),
            'observed_sha256':sha256((d/'guard.csv.observed.f32').read_bytes()),'monitor_sha256':sha256((base/'activity/cases'/key/'measured.f32').read_bytes())},'repeat/monitor identity')
    return {'status':'VERIFIED_CORRELATION_GUARD','cases':36,'order_results':144,'independent_score_probes':audited,
        'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}


def negatives(base,root,revision):
    kinds=('promotion','shadow','baseline','missing-case','metric','score','used-gate','source','binary')
    rejected=[]
    with tempfile.TemporaryDirectory(prefix='fe-correlation-neg-') as temp:
        copy=Path(temp)/'copy';shutil.copytree(root,copy)
        keep={p:p.read_bytes() for p in (copy/'result.json',copy/'manifest.json',copy/'SHA256SUMS')}
        for kind in kinds:
            r=json.loads(keep[copy/'result.json']);changed=[]
            if kind=='promotion':r['shipping_authority']=True
            elif kind=='shadow':r['shadow_decomposition_authority']=True
            elif kind=='baseline':r['activity_manifest_sha256']='0'*64
            elif kind=='missing-case':r['cases'].pop()
            elif kind=='metric':r['cases'][0]['guard']['gates']['scheduled-double']['frames']+=1
            else:
                p=copy/'source/correlation_guard.h' if kind=='source' else copy/'guard-native' if kind=='binary' else copy/'cases'/r['cases'][0]['case_id']/'guard.csv'
                blob=p.read_bytes();changed.append((p,blob))
                if kind in ('source','binary'):p.write_bytes(blob+b'changed')
                else:
                    lines=blob.decode().splitlines();parts=lines[2].split(',')
                    if kind=='score':parts[9]='0.987654321'
                    else:parts[8]=str(1-int(parts[8]))
                    lines[2]=','.join(parts);p.write_text('\n'.join(lines)+'\n')
            write_json(copy/'result.json',r);seal_output(copy,r)
            try:verify(base,copy,revision)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('resealed negative accepted '+kind)
            for p,blob in changed:p.write_bytes(blob)
            for p,blob in keep.items():p.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}


def summary(r):
    groups=[]
    for geometry in order.speech.POSITIONS:
        for bank in order.BANKS:
            for event in order.EVENTS:
                rows=[x for x in r['cases'] if (x['geometry'],x['bank'],x['event'])==(geometry,bank,event)]
                g={'geometry':geometry,'bank':bank,'event':event,'cases':len(rows)}
                for mode in ('control','guard'):
                    g[mode]={'double_admitted':sum(x[mode]['gates']['scheduled-double']['adaptation_admitted'] for x in rows),
                        'far_admitted':sum(x[mode]['gates']['scheduled-far']['adaptation_admitted'] for x in rows),'orders':{}}
                    for arm in ('bf-then-aec','aec-then-bf'):
                        vals=[x[mode]['orders'][arm] for x in rows]
                        nums=[v['final_far_ratio_db'] for v in vals if v['final_far_ratio_db'] is not None]
                        g[mode]['orders'][arm]={'mean_final_far_db':sum(nums)/len(nums) if nums else None,
                            'recovered':sum(v['recovery_after_event_ms'] is not None for v in vals),
                            'double_after_si_sdr':[v['phases_si_sdr_relative_to_bf_target_db']['double-after'] for v in vals]}
                groups.append(g)
    return {'decision':DECISION,'descriptive_only':True,'independent_speech_confirmation':False,'groups':groups}


def main():
    p=argparse.ArgumentParser();p.add_argument('--base-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source',required=True);p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args();require(hex_digest(a.execution_source,40),'revision')
    if a.negative_evidence:r=negatives(a.base_evidence,a.output,a.execution_source)
    elif a.verify:r=verify(a.base_evidence,a.output,a.execution_source)
    else:
        r=run(a.base_evidence,a.output,a.execution_source)
        print('CORRELATION_EFFECTS '+json.dumps(summary(r),sort_keys=True,allow_nan=False))
        r={'status':'EXECUTED_CORRELATION_GUARD','cases':36,'decision':DECISION}
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__':raise SystemExit(main())
