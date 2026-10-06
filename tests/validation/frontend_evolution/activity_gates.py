#!/usr/bin/env python3
"""FE04 actual Activity gates. Existing order/evaluator reused; no promotion."""
from __future__ import annotations
import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import bf_aec_order as order
from contracts import ROOT, require, load_json, sha256, hex_digest
from libfvad_reference import write_json, seal_output, run_logged
from speech_fir import verify_seal

HERE = Path(__file__).resolve().parent
PLAN = ROOT / '.github/research/frontend-evolution-v1/activity-gates-v1.json'
DECISION = 'ACTIVITY_GATES_DIAGNOSTIC_NO_PROMOTION'
HEADER = ['frame','mic_energy','reference_energy','oracle_far','oracle_dt',
          'detected_far','detected_dt','used_far','used_dt']
MODES = ('monitor','measured')
LABELS = ('native','sanitized','arm')


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class ActivityReference:
    """Scalar binary32 reference of unchanged source; not a new DSP backend."""
    def __init__(self):
        self.mic = self.ref = 0.0
        self.far_hold = self.dt_hold = 0

    def step(self, mic, ref):
        def smooth(old, value):
            if old <= 0.0:
                return value
            alpha = f32(0.35 if value > old else 0.08)
            return f32(old + f32(alpha * f32(value - old)))
        self.mic = smooth(self.mic, mic)
        self.ref = smooth(self.ref, ref)
        threshold, ratio = f32(1e-7), f32(1.5)
        if self.ref > threshold:
            self.far_hold = 2
        elif self.ref < f32(f32(0.55)*threshold) and self.far_hold:
            self.far_hold -= 1
        far = self.far_hold > 0 or self.ref > threshold
        sr = f32(self.mic / f32(self.ref + f32(1e-12)))
        ir = f32(mic / f32(ref + f32(1e-12)))
        dt_on = far and sr > ratio and ir > f32(f32(0.90)*ratio)
        dt_hold = far and ir > f32(f32(0.72)*ratio)
        if dt_on:
            self.dt_hold = 3
        elif not dt_hold and self.dt_hold:
            self.dt_hold -= 1
        return int(far), int(far and self.dt_hold > 0)


def trace_rows(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == HEADER, 'trace schema')
        rows = []
        for number, row in enumerate(reader):
            require(set(row) == set(HEADER) and None not in row.values(), 'trace columns')
            item = {k: int(row[k]) for k in HEADER if k not in HEADER[1:3]}
            require(item['frame'] == number, 'trace order/count')
            for k in HEADER[1:3]:
                value = float(row[k])
                require(math.isfinite(value) and value >= 0, 'nonfinite/negative energy')
                item[k] = f32(value)
            require(all(item[k] in (0,1) for k in HEADER[3:]), 'nonboolean trace')
            rows.append(item)
    return rows


def validate_trace(rows, mode, out, inp, n):
    count = len(out)//6
    require(mode in MODES and count % 160 == 0 and len(rows)*160 == count, 'trace length/mode')
    require(len(inp) == count*(2*n+3), 'trace input length')
    state = ActivityReference()
    for frame, row in enumerate(rows):
        lo = frame*160
        reference_energy = f32(1e-12)
        mixed_energy = f32(1e-12)
        for k in range(lo, lo+160):
            ref = inp[k*(2*n+3)+2*n]
            reference_energy = f32(reference_energy + f32(ref*ref))
            # Independently split BF components round once each. They are NOT
            # bitwise the mixed BF accumulator; only this energy check is bounded.
            mixture = f32(out[6*k]+out[6*k+1])
            mixed_energy = f32(mixed_energy + f32(mixture*mixture))
            require(row['oracle_far'] == inp[k*(2*n+3)+2*n+1] and
                    row['oracle_dt'] == inp[k*(2*n+3)+2*n+2], 'oracle trace/input disagreement')
        reference_energy = f32(reference_energy/160)
        mixed_energy = f32(mixed_energy/160)
        require(row['reference_energy'] == reference_energy, 'reference energy disagreement')
        require(abs(row['mic_energy']-mixed_energy) <= 2e-8, 'mixed energy disagreement')
        detected = state.step(row['mic_energy'],row['reference_energy'])
        require(detected == (row['detected_far'],row['detected_dt']), 'Activity reference mismatch')
        used = detected if mode == 'measured' else (row['oracle_far'],row['oracle_dt'])
        require(used == (row['used_far'],row['used_dt']), 'wrong actual gate mode')


def measures(out, rows):
    """No shadow columns (3/5) used. Far ratios are actual mixed output only."""
    require(len(out) == order.N*6 and len(rows) == 1600, 'full measured case count')
    gates = {}
    for name, indices in (
        ('scheduled-double',range(610,990)),
        ('scheduled-far',list(range(210,590))+list(range(1010,1390))),
        ('scheduled-near',list(range(10,190))+list(range(1410,1590)))):
        selected = [rows[k] for k in indices]
        gates[name] = {'frames':len(selected),
            'far_flags':sum(r['used_far'] for r in selected),
            'double_flags':sum(r['used_dt'] for r in selected),
            'adaptation_admitted':sum(r['used_far'] and not r['used_dt'] for r in selected)}
    results = {}
    near = list(out[0::6])
    for name,col in (('bf-then-aec',2),('aec-then-bf',4)):
        actual = list(out[col::6])
        windows = order.windows(out,col)
        for k,w in enumerate(windows):
            # Known near signal and the BF histories have drained in these spans.
            if not (21 <= k < 60 or 101 <= k < 140):
                w['erle_db'] = None
        phases = {}
        for tag,a,b in [('near-initial',.1,1.9),('double-before',6.1,7.9),
                        ('double-after',8.1,9.9),('near-final',14.1,15.9)]:
            lo,hi=int(a*16000),int(b*16000)
            phases[tag] = order.speech.si_sdr_span(near,actual,lo,lo,hi-lo)
        rec = order.recovery(windows)
        start = rec['recovery_after_event_ms']
        rec['recovery_confirmed_after_event_ms'] = None if start is None else start+300
        energy = sum(w['echo_energy'] for w in windows[120:139])
        residual = sum(w['residual_energy'] for w in windows[120:139])
        final_ratio = 10*math.log10(energy/max(residual,1e-30)) if energy/19>1e-12 else None
        results[name] = {'phases_si_sdr_relative_to_bf_target_db':phases,
                         'far_only_windows':windows,'final_far_ratio_db':final_ratio,**rec}
    return {'gates':gates,'orders':results}


def build(root, revision, label):
    compiler = 'arm-linux-gnueabihf-gcc' if label=='arm' else 'cc'
    sanitized = label=='sanitized'
    build_dir = root/('build-'+label)
    flags = '-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' if sanitized else '-O2'
    options = ['cmake','-S',ROOT,'-B',build_dir,'-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_C_COMPILER='+compiler,'-DCMAKE_C_FLAGS='+flags+' -ffp-contract=off',
        '-DAP_BUILD_SOURCE_REVISION='+revision,'-DAP_BUILD_PIPELINE=OFF','-DAP_MODULES=AEC,ACTIVITY',
        '-DAP_AEC_BACKEND=MDF','-DAP_SIMD_BACKEND=SCALAR','-DAP_BUILD_TESTS=OFF',
        '-DAP_BUILD_BENCH=OFF','-DAP_BUILD_EXAMPLES=OFF','-DAP_ENABLE_LINUX_RUNTIME=OFF',
        '-DAP_BUILD_MAX_AEC_TAIL_MS=64','-DAP_STRICT_WARNINGS=ON']
    if label=='arm':
        options += ['-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=arm']
    run_logged(options,root/(label+'-configure.log'))
    run_logged(['cmake','--build',build_dir,'--parallel','2'],root/(label+'-build.log'))
    binary=root/('activity-'+label)
    cmd=[compiler,*order.CFLAGS,*flags.split(),'-I'+str(ROOT/'include'),'-I'+str(build_dir/'generated'),
         HERE/'array_native.c',HERE/'bf_aec_order_runner.c',build_dir/'libaudio_pipeline.a','-lm','-o',binary]
    run_logged(cmd,root/(label+'-link.log'))
    shutil.copyfile(build_dir/'generated/audio_pipeline/audio_pipeline_build.h',root/(label+'-build.h'))
    shutil.copyfile(build_dir/'libaudio_pipeline.a',root/(label+'-library.a'))
    run_logged([compiler,'--version'],root/(label+'-compiler.txt'))
    if label=='arm':
        run_logged(['arm-linux-gnueabihf-readelf','-h',binary],root/'arm-elf.txt')
    write_json(root/(label+'-build.json'),{'configure':list(map(str,options)),
        'link':list(map(str,cmd)),'processor_sha256':sha256(binary.read_bytes())})
    shutil.rmtree(build_dir)
    return binary


def execute(binary,cfg,inp,dest,mode,arm=False):
    flag='--measured-activity' if mode=='measured' else '--monitor-activity'
    cmd=[*order.command(binary,cfg,inp,dest,arm),flag,dest.with_suffix('.csv')]
    run_logged(cmd,dest.with_suffix('.log'))
    return cmd


def engineering(base,root,binary,label):
    root.mkdir();src=base/('engineering-'+label);arm=label=='arm';records=[]
    for case,cfg,inp in (
        ('adaptive','adaptive.cfg','adaptive-input.f32'),
        ('future','adaptive.cfg','adaptive-future-input.f32'),
        ('steer','ula4-70-fir33.cfg','ula4-70.f32')):
        for mode in MODES:
            dest=root/(case+'-'+mode)
            execute(binary,src/cfg,src/inp,dest,mode,arm)
            raw=order.floats(dest.with_suffix('.f32'))
            validate_trace(trace_rows(dest.with_suffix('.csv')),mode,raw,order.floats(src/inp),4)
            records.append({'case':case,'mode':mode,'output_sha256':sha256(dest.with_suffix('.f32').read_bytes())})
    repeat=root/'repeat'
    execute(binary,src/'adaptive.cfg',src/'adaptive-input.f32',repeat,'measured',arm)
    for suffix in ('.f32','.csv','.json'):
        require(repeat.with_suffix(suffix).read_bytes()==(root/'adaptive-measured').with_suffix(suffix).read_bytes(),'measured repeat')
    a=(root/'adaptive-measured.f32').read_bytes();b=(root/'future-measured.f32').read_bytes()
    require(a[:8000*24]==b[:8000*24] and a[8000*24:]!=b[8000*24:], 'measured prefix/future')
    ta=trace_rows(root/'adaptive-measured.csv');tb=trace_rows(root/'future-measured.csv')
    require(ta[:50]==tb[:50], 'trace future leakage')
    before=(root/'adaptive-measured.f32').read_bytes()
    cmd=[*order.command(binary,src/'adaptive.cfg',src/'adaptive-input.f32',root/'adaptive-measured',arm),
         '--measured-activity',root/'overwrite.csv']
    p=subprocess.run(list(map(str,cmd)),capture_output=True)
    require(p.returncode!=0 and before==(root/'adaptive-measured.f32').read_bytes(),'overwrite accepted')
    (root/'overwrite.log').write_bytes(p.stderr)
    cmd=[*order.command(binary,src/'adaptive.cfg',src/'adaptive-input.f32',root/'invalid',arm),'--wrong-mode',root/'invalid.csv']
    p=subprocess.run(list(map(str,cmd)),capture_output=True)
    require(p.returncode!=0 and not (root/'invalid.f32').exists(),'invalid gate mode')
    (root/'invalid.log').write_bytes(p.stderr)
    # This real old AEC-only build must reject the requested new capability.
    cmd=[*order.command(base/('order-'+label),src/'adaptive.cfg',src/'adaptive-input.f32',root/'unsupported',arm),
         '--measured-activity',root/'unsupported.csv']
    p=subprocess.run(list(map(str,cmd)),capture_output=True)
    require(p.returncode!=0 and not (root/'unsupported.f32').exists(),'missing Activity silently used oracle')
    (root/'unsupported.log').write_bytes(p.stderr)
    result={'status':'PASS','label':label,'records':records,'repeat':True,'future':True,
            'overwrite_rejected':True,'invalid_rejected':True,'missing_module_rejected':True}
    write_json(root/'result.json',result)
    return result


def run(base,root,revision):
    require(hex_digest(revision,40) and not root.exists(),'new output and exact revision required')
    order.verify(base,revision,require_arm=True)
    root.mkdir(parents=True)
    shutil.copyfile(PLAN,root/'experiment.json')
    (root/'source').mkdir()
    for name in ('activity_gates.py','bf_aec_order_runner.c'):
        shutil.copyfile(HERE/name,root/'source'/name)
    binaries={label:build(root,revision,label) for label in LABELS}
    tests={label:engineering(base,root/('engineering-'+label),binaries[label],label) for label in LABELS}
    baseline=load_json(base/'result.json');rows=[]
    for old in baseline['cases']:
        key=old['case_id'];d=root/'cases'/key;d.mkdir(parents=True)
        cfg=base/'cases'/key/'config.txt';inp=base/old['input']
        for mode in MODES:
            execute(binaries['native'],cfg,inp,d/mode,mode)
        require((d/'monitor.f32').read_bytes()==(base/'cases'/key/'output.f32').read_bytes(),'monitor changed oracle output')
        execute(binaries['native'],cfg,inp,d/'repeat','measured')
        for suffix in ('.f32','.csv','.json'):
            require((d/'repeat').with_suffix(suffix).read_bytes()==(d/'measured').with_suffix(suffix).read_bytes(),'recorded repeat mismatch')
        write_json(d/'repeat.json',{'output_sha256':sha256((d/'measured.f32').read_bytes()),
                                  'trace_sha256':sha256((d/'measured.csv').read_bytes()),'monitor_equals_baseline':True})
        (d/'repeat.f32').unlink();(d/'repeat.csv').unlink();(d/'monitor.f32').unlink()
        measured=order.floats(d/'measured.f32',order.N*6)
        oracle=order.floats(base/'cases'/key/'output.f32',order.N*6)
        n=len(order.speech.POSITIONS[old['geometry']]);input_values=order.floats(inp)
        traces={mode:trace_rows(d/(mode+'.csv')) for mode in MODES}
        for mode,out in (('monitor',oracle),('measured',measured)):
            validate_trace(traces[mode],mode,out,input_values,n)
        rows.append({k:old[k] for k in ('case_id','pair','geometry','bank','event','input')} |
                    {'oracle':measures(oracle,traces['monitor']), 'measured':measures(measured,traces['measured'])})
    result={'schema_version':1,'experiment_id':'FE04-ACTIVITY-GATES-V1','decision':DECISION,
        'shipping_authority':False,'data_role':order.ROLE,'execution_source_revision':revision,
        'base_manifest_sha256':sha256((base/'manifest.json').read_bytes()),
        'synchronization':'exact-reference-no-SYNC-estimator','detector':'unchanged-public-Activity-shared-post-BF',
        'shadow_decomposition_authority':False,'timing_authority':'NONE_TARGET',
        'case_count':36,'order_results':144,'engineering':tests,'cases':rows}
    write_json(root/'result.json',result);seal_output(root,result)
    return result


def verify(base,root,revision):
    verify_seal(base);verify_seal(root)
    r=load_json(root/'result.json');b=load_json(base/'result.json')
    require(r['execution_source_revision']==revision==b['execution_source_revision'],'execution identity')
    require(r['base_manifest_sha256']==sha256((base/'manifest.json').read_bytes()),'baseline binding')
    require(r['decision']==DECISION and r['shipping_authority'] is False and r['data_role']==order.ROLE,'authority drift')
    require(r['shadow_decomposition_authority'] is False and r['timing_authority']=='NONE_TARGET','false shadow/timing authority')
    require(r['synchronization']=='exact-reference-no-SYNC-estimator' and r['detector']=='unchanged-public-Activity-shared-post-BF','mechanism drift')
    require((root/'experiment.json').read_bytes()==PLAN.read_bytes(),'plan drift')
    for name in ('activity_gates.py','bf_aec_order_runner.c'):
        require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'source drift')
    expected={x['case_id']:x for x in b['cases']}
    require(r['case_count']==36 and r['order_results']==144 and len(r['cases'])==36 and
            {x['case_id'] for x in r['cases']}==set(expected),'matrix completeness')
    for row in r['cases']:
        old=expected[row['case_id']];key=row['case_id'];d=root/'cases'/key
        require(all(row[k]==old[k] for k in ('pair','geometry','bank','event','input')),'case identity')
        measured=order.floats(d/'measured.f32',order.N*6);oracle=order.floats(base/'cases'/key/'output.f32',order.N*6)
        n=len(order.speech.POSITIONS[row['geometry']]);inp=order.floats(base/row['input'])
        for mode,out,name in (('monitor',oracle,'oracle'),('measured',measured,'measured')):
            trace=trace_rows(d/(mode+'.csv'));validate_trace(trace,mode,out,inp,n)
            require(row[name]==measures(out,trace),'metric recomputation')
            m=load_json(d/(mode+'.json'))
            require(m['source_revision']==revision and m['samples']==order.N and m['frames']==1600 and m['columns']==6
                    and m['shipping_authority'] is False and m['common_delay_samples']==21,'output metadata')
            require(m['microphones']==n and m['mode']==(3 if row['bank']=='fir33' else 4)
                    and m['event']==order.EVENTS.index(row['event']) and m['steering_completed']==int(row['event']=='steer'),'output configuration')
            require(m['peak']==max(map(abs,out)) and m['out_of_range_values']==sum(abs(v)>1 for v in out),'output range metrics')
        repeat=load_json(d/'repeat.json')
        require(repeat=={'output_sha256':sha256((d/'measured.f32').read_bytes()),
                         'trace_sha256':sha256((d/'measured.csv').read_bytes()),'monitor_equals_baseline':True},'repeat identity')
        # Detector depends only on common pre-AEC observation, never AEC/shadow feedback.
        tm=trace_rows(d/'monitor.csv');tr=trace_rows(d/'measured.csv')
        require(all(all(a[k]==c[k] for k in HEADER[:-2]) for a,c in zip(tm,tr)),'detector feedback contamination')
    for label in LABELS:
        info=load_json(root/(label+'-build.json'))
        require(info['processor_sha256']==sha256((root/('activity-'+label)).read_bytes()),'binary identity')
        header=(root/(label+'-build.h')).read_text()
        require(revision in header and 'AP_HAVE_MODULE_ACTIVITY 1' in header,'wrong compiled capability')
        tests=load_json(root/('engineering-'+label)/'result.json')
        require(tests==r['engineering'][label] and tests['status']=='PASS' and len(tests['records'])==6
                and all(tests[k] is True for k in ('repeat','future','overwrite_rejected','invalid_rejected','missing_module_rejected')),'engineering evidence')
        e=root/('engineering-'+label)
        for suffix in ('.f32','.csv','.json'):
            require((e/'repeat').with_suffix(suffix).read_bytes()==(e/'adaptive-measured').with_suffix(suffix).read_bytes(),'engineering repeat')
        require((e/'adaptive-measured.f32').read_bytes()[:8000*24]==(e/'future-measured.f32').read_bytes()[:8000*24],'engineering future')
    require('ARM' in (root/'arm-elf.txt').read_text() and 'ELF32' in (root/'arm-elf.txt').read_text(),'Arm ELF missing')
    return {'status':'VERIFIED_ACTIVITY_GATES','cases':36,'order_results':144,'trace_frames':115200,
            'files':len(load_json(root/'manifest.json')['files']),'decision':DECISION}


def negatives(base,root,revision):
    kinds=('promotion','shadow','role','missing-case','metric','gate','trace-count','source','binary')
    rejected=[]
    with tempfile.TemporaryDirectory(prefix='fe-activity-negative-') as temp:
        dest=Path(temp)/'copy';shutil.copytree(root,dest)
        originals={p:p.read_bytes() for p in (dest/'result.json',dest/'manifest.json',dest/'SHA256SUMS')}
        for kind in kinds:
            r=json.loads(originals[dest/'result.json']);d=dest/'cases'/r['cases'][0]['case_id'];changed=[]
            if kind=='promotion':r['shipping_authority']=True
            elif kind=='shadow':r['shadow_decomposition_authority']=True
            elif kind=='role':r['data_role']='independent-blind'
            elif kind=='missing-case':r['cases'].pop()
            elif kind=='metric':r['cases'][0]['measured']['gates']['scheduled-double']['frames']+=1
            else:
                path=d/'measured.csv' if kind in ('gate','trace-count') else dest/'source/activity_gates.py' if kind=='source' else dest/'activity-native'
                blob=path.read_bytes();changed.append((path,blob))
                if kind=='gate':
                    lines=blob.decode().splitlines();parts=lines[1].split(',');parts[7]=str(1-int(parts[7]));lines[1]=','.join(parts)
                    path.write_text('\n'.join(lines)+'\n')
                elif kind=='trace-count':path.write_bytes(b'\n'.join(blob.splitlines()[:-1])+b'\n')
                else:path.write_bytes(blob+b'changed')
            write_json(dest/'result.json',r);seal_output(dest,r)
            try:verify(base,dest,revision)
            except (ValueError,KeyError,IndexError,AssertionError,RuntimeError):rejected.append(kind)
            else:raise AssertionError('negative accepted: '+kind)
            for path,blob in changed:path.write_bytes(blob)
            for path,blob in originals.items():path.write_bytes(blob)
    return {'status':'PASS','rejected':rejected}


def summary(r):
    output=[]
    for geometry in order.speech.POSITIONS:
        for bank in order.BANKS:
            for event in order.EVENTS:
                rows=[v for v in r['cases'] if (v['geometry'],v['bank'],v['event'])==(geometry,bank,event)]
                item={'geometry':geometry,'bank':bank,'event':event,'cases':len(rows)}
                for mode in ('oracle','measured'):
                    item[mode]={'double_admit':sum(v[mode]['gates']['scheduled-double']['adaptation_admitted'] for v in rows),
                        'double_frames':sum(v[mode]['gates']['scheduled-double']['frames'] for v in rows),'orders':{}}
                    for arm in ('bf-then-aec','aec-then-bf'):
                        vals=[v[mode]['orders'][arm] for v in rows]
                        nums=[v['final_far_ratio_db'] for v in vals if v['final_far_ratio_db'] is not None]
                        item[mode]['orders'][arm]={'mean_final_far_db':sum(nums)/len(nums) if nums else None,
                            'recovered':sum(v['recovery_after_event_ms'] is not None for v in vals),
                            'double_after_si_sdr':[v['phases_si_sdr_relative_to_bf_target_db']['double-after'] for v in vals]}
                output.append(item)
    return {'decision':DECISION,'descriptive_only':True,'groups':output}


class Tests(unittest.TestCase):
    def test_quiet(self):
        s=ActivityReference()
        self.assertEqual([s.step(0,0) for _ in range(8)],[(0,0)]*8)
    def test_far(self):
        self.assertEqual(ActivityReference().step(f32(.001),f32(.01)),(1,0))
    def test_double(self):
        self.assertEqual(ActivityReference().step(f32(.1),f32(.01)),(1,1))
    def test_hold(self):
        s=ActivityReference();s.step(f32(.1),f32(.01))
        self.assertEqual([s.step(0,f32(.01))[1] for _ in range(4)],[1,1,0,0])
    def test_recovery_confirmation(self):
        w=[{'echo_energy':1,'residual_energy':.1,'erle_db':10} for _ in range(160)]
        self.assertEqual(order.recovery(w)['recovery_after_event_ms'],2100)
    def test_trace_empty(self):
        with self.assertRaises(ValueError):validate_trace([],'measured',[0]*960,[0]*1760,4)


def main():
    p=argparse.ArgumentParser();p.add_argument('--base-evidence',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--execution-source');p.add_argument('--verify',action='store_true')
    p.add_argument('--negative-evidence',action='store_true');p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    if a.self_test:
        return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful() else 1
    require(a.base_evidence and a.output and hex_digest(a.execution_source,40),'paths and exact source required')
    if a.negative_evidence:result=negatives(a.base_evidence,a.output,a.execution_source)
    elif a.verify:result=verify(a.base_evidence,a.output,a.execution_source)
    else:
        result=run(a.base_evidence,a.output,a.execution_source)
        print('ACTIVITY_EFFECTS '+json.dumps(summary(result),sort_keys=True,allow_nan=False))
        result={'status':'EXECUTED_ACTIVITY_GATES','cases':36,'decision':DECISION}
    print(json.dumps(result,sort_keys=True,allow_nan=False));return 0

if __name__=='__main__':raise SystemExit(main())
