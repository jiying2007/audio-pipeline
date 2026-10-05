#!/usr/bin/env python3
"""FE02/03 C array engineering qualification, NOT a second acoustic evaluator.

Analytic transport/filter known answers only. Speech quality continues to use the
canonical validation/tools authority. No external source or model is downloaded.
"""
from __future__ import annotations
import argparse
import cmath
import copy
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from contracts import ROOT, hex_digest, load_json, require, sha256, verified_file
from libfvad_reference import write_json, seal_output, process_env, run_logged

HERE = Path(__file__).resolve().parent
PLAN = ROOT / '.github/research/frontend-evolution-v1/array-native-v1.json'
SOURCES = ('array_native.h', 'array_native.c', 'array_native_test.c', 'array_runner.c',
           'array_qualification.py', 'contracts.py', 'libfvad_reference.py',
           'array_direction_control.h', 'array_direction_control.c', 'array_steering_test.c', 'array_steering_checks.py')
FLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow',
         '-pedantic', '-ffp-contract=off']


def delays(g: dict) -> tuple[int, list[float]]:
    positions = g['positions_m']; ref = positions[g['reference_mic']]
    delta = [[p[k]-ref[k] for k in range(3)] for p in positions]
    radius = max(math.sqrt(sum(x*x for x in p)) for p in delta)
    latency = math.ceil(radius*g['sample_rate_hz']/343.0 + max(map(abs,g['latency_samples'])))+1
    values = [latency + sum(p[k]*g['direction'][k] for k in range(3))*g['sample_rate_hz']/343.0 - c
              for p,c in zip(delta,g['latency_samples'])]
    return latency, values


def geometry_text(g: dict, mode: str) -> bytes:
    n = len(g['positions_m'])
    header = ['FE_ARRAY_V1', str(g['sample_rate_hz']), str(n), str(('linear','lagrange3').index(mode)),
              str(g['active_mask']), str(g['reference_mic']), *map(repr,g['direction'])]
    rows = [' '.join(header)]
    for i,p in enumerate(g['positions_m']):
        rows.append(' '.join(map(str,[*p,g['gains'][i],g['latency_samples'][i],g['channel_map'][i]])))
    return ('\n'.join(rows)+'\n').encode()


def make_input(g: dict, pattern: str, count: int) -> bytes:
    """Independent analytic continuous-time inputs, then explicit S16 quantization."""
    n = len(g['positions_m']); common,d = delays(g); out = []
    for j in range(count):
        row = [0]*n
        for i in range(n):
            t = j+d[i]-common
            if pattern == 'impulse':
                value = (i+1)*0.04 if j == 19+i*11 else 0.0
            elif pattern == 'polynomial':
                x=t/10000.0; value=(0.1+x+x*x+x*x*x)/g['gains'][i]
            else:
                # Distinct channel components prevent a first-channel-only fake from passing.
                value=(0.12*math.sin(2*math.pi*731*t/16000.0)+
                       0.035*math.sin(2*math.pi*(1709+103*i)*j/16000.0))/g['gains'][i]
            row[g['channel_map'][i]] = max(-32768,min(32767,round(value*32768)))
        out.extend(row)
    return struct.pack('<'+'h'*len(out),*out)


def interpolation_taps(delay: float, mode: str) -> list[tuple[int,float]]:
    """Generic Lagrange basis product, not the C implementation's closed forms."""
    m = math.floor(delay); nodes = [m,m+1] if mode=='linear' else [m-1,m,m+1,m+2]
    return [(node, math.prod((delay-other)/(node-other) for other in nodes if other!=node)) for node in nodes]


def oracle(payload: bytes, g: dict, mode: str) -> list[float]:
    n=len(g['positions_m']); raw=[v[0]/32768.0 for v in struct.iter_unpack('<h',payload)]
    _,d=delays(g); active=[i for i in range(n) if g['active_mask']&(1<<i)]
    taps=[interpolation_taps(x,mode) for x in d]; result=[]
    for t in range(len(raw)//n):
        result.append(sum(g['gains'][i]*sum(w*raw[(t-k)*n+g['channel_map'][i]]
                      for k,w in taps[i] if t>=k) for i in active)/len(active))
    return result


def cases(plan: dict):
    for g in plan['geometries']:
        for pattern in plan['patterns']:
            for mode in plan['interpolations']:
                yield f"{g['id']}-{pattern}-{mode}",g,pattern,mode


def frequency_response(plan: dict) -> list[dict]:
    # Fixed half-sample transfer; reports a limitation, never an optimization target.
    result=[]
    for mode in plan['interpolations']:
        for f in (0,1000,3000,6000,7500):
            omega=2*math.pi*f/16000
            h=sum(w*cmath.exp(-1j*omega*k) for k,w in interpolation_taps(2.5,mode))
            result.append({'mode':mode,'frequency_hz':f,'magnitude_db':20*math.log10(max(abs(h),1e-30))})
    return result


def execute(binary: Path, prefix: list[str], config: Path, pcm: Path, dest: Path) -> dict:
    run_logged([*prefix,binary,config,pcm,dest.with_suffix('.f32'),dest.with_suffix('.json')],
               dest.with_suffix('.log'))
    return load_json(dest.with_suffix('.json'))


def probe_negative_cli(binary: Path, root: Path) -> dict:
    results={}; pcm=root/'negative.pcm'; pcm.write_bytes(b'\0\0'*640)
    config=root/'negative.txt'; g=load_json(PLAN)['geometries'][3]
    for label,data in [('nan',geometry_text(g,'linear').replace(b'0.6',b'nan',1)),
                       ('trailing',geometry_text(g,'linear')+b'extra\n'),
                       ('bad-count',geometry_text(g,'linear').replace(b'16000 4 ',b'16000 3 ',1))]:
        config.write_bytes(data)
        r=subprocess.run([str(binary),str(config),str(pcm),str(root/(label+'.f32')),str(root/(label+'.json'))],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=process_env(root),timeout=20)
        require(r.returncode==2 and not (root/(label+'.f32')).exists(),f'negative config accepted: {label}')
        results[label]=r.returncode
    config.write_bytes(geometry_text(g,'linear'))
    for label,payload in [('empty',b''),('partial',b'\0\0'*639),('odd',b'\0'*1281)]:
        pcm.write_bytes(payload)
        r=subprocess.run([str(binary),str(config),str(pcm),str(root/(label+'.f32')),str(root/(label+'.json'))],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=process_env(root),timeout=20)
        require(r.returncode==2 and not (root/(label+'.f32')).exists(),f'bad PCM accepted: {label}')
        results[label]=r.returncode
    pcm.write_bytes(b'\0\0'*640)
    existing=root/'existing.f32'; existing.write_bytes(b'KEEP')
    r=subprocess.run([str(binary),str(config),str(pcm),str(existing),str(root/'existing.json')],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=process_env(root),timeout=20)
    require(r.returncode==2 and existing.read_bytes()==b'KEEP','overwritten existing output')
    results['existing-output']=r.returncode
    return results


def qualify(output: Path, revision: str, require_arm: bool) -> dict:
    require(hex_digest(revision,40),'full execution source required')
    require(not output.exists(),'refuse reused evidence directory')
    output.mkdir(parents=True)
    plan=load_json(PLAN); shutil.copyfile(PLAN,output/'experiment.json')
    (output/'source').mkdir()
    for name in SOURCES: shutil.copyfile(HERE/name,output/'source'/name)
    # Native compilation is a real first-party build, not an upstream runtime.
    runner=output/'array-native'; unit=output/'unit-native'; sanitized=output/'unit-sanitized'
    commands=[['cc',*FLAGS,str(HERE/'array_native.c'),str(HERE/'array_runner.c'),'-lm','-o',str(runner)],
              ['cc',*FLAGS,str(HERE/'array_native.c'),str(HERE/'array_native_test.c'),'-lm','-o',str(unit)],
              ['cc',*FLAGS,'-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
               str(HERE/'array_native.c'),str(HERE/'array_native_test.c'),'-lm','-o',str(sanitized)],
              ['cc',*FLAGS,'-fstack-usage','-c',str(HERE/'array_native.c'),'-o',str(output/'array-native.o')]]
    steering_sources=[str(HERE/name) for name in ('array_native.c','array_direction_control.c','array_steering_test.c')]
    commands.extend([['cc',*FLAGS,*steering_sources,'-lm','-o',str(output/'steering-unit-native')],
                     ['cc',*FLAGS,'-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie',
                      *steering_sources,'-lm','-o',str(output/'steering-unit-sanitized')]])
    for i,command in enumerate(commands):run_logged(command,output/f'build-{i}.log')
    for arch in ('native','sanitized'):run_logged([output/f'steering-unit-{arch}'],output/f'steering-unit-{arch}.json')
    run_logged(['cc','--version'],output/'compiler-native.txt')
    run_logged([unit],output/'unit-native.json'); run_logged([sanitized],output/'unit-sanitized.json')
    run_logged(['nm','-u',output/'array-native.o'],output/'undefined-symbols.txt')
    forbidden={'malloc','calloc','realloc','free','fopen','printf','pthread_mutex_lock'}
    symbols=(output/'undefined-symbols.txt').read_text().split()
    require(not forbidden.intersection(symbols),'data plane imports a forbidden service')
    targets=[('native',runner,[])]
    has_arm=all(shutil.which(x) for x in ('arm-linux-gnueabihf-gcc','qemu-arm'))
    require(has_arm or not require_arm,'required AArch32/QEMU tools missing')
    if has_arm:
        armflags=['arm-linux-gnueabihf-gcc',*FLAGS,'-mcpu=cortex-a32','-mfpu=neon-fp-armv8','-mfloat-abi=hard']
        arm=output/'array-arm'; au=output/'unit-arm'; prefix=['qemu-arm','-cpu','max','-L','/usr/arm-linux-gnueabihf']
        for i,(src,binary) in enumerate([('array_runner.c',arm),('array_native_test.c',au)]):
            command=[*armflags,str(HERE/'array_native.c'),str(HERE/src),'-lm','-o',str(binary)]
            commands.append(command);run_logged(command,output/f'build-arm-{i}.log')
        run_logged(['arm-linux-gnueabihf-gcc','--version'],output/'compiler-arm.txt')
        run_logged(['qemu-arm','--version'],output/'qemu.txt')
        run_logged(['arm-linux-gnueabihf-readelf','-h',arm],output/'arm-elf.txt')
        run_logged([*prefix,au],output/'unit-arm.json',timeout=180)
        command=[*armflags,*steering_sources,'-lm','-o',str(output/'steering-unit-arm')]
        commands.append(command);run_logged(command,output/'build-steering-arm.log')
        run_logged([*prefix,output/'steering-unit-arm'],output/'steering-unit-arm.json',timeout=180)
        targets.append(('arm',arm,prefix))
    write_json(output/'build-commands.json',{'commands':commands})
    report={'schema_version':2,'experiment_id':plan['experiment_id'],'execution_source_revision':revision,
            'status':'NATIVE_ARRAY_ENGINEERING_PASS','shipping_authority':False,'acoustic_improvement_proved':False,
            'arm_qualified':bool(has_arm),'cases':[],'frequency_response':frequency_response(plan),
            'processors':{arch:sha256(binary.read_bytes()) for arch,binary,_ in targets}}
    for key,g,pattern,mode in cases(plan):
        d=output/'cases'/key;d.mkdir(parents=True)
        cfg=d/'geometry.txt';pcm=d/'input.pcm';cfg.write_bytes(geometry_text(g,mode))
        pcm.write_bytes(make_input(g,pattern,plan['frames_per_case']))
        expected=oracle(pcm.read_bytes(),g,mode)
        for arch,binary,prefix in targets:
            dest=d/arch;meta=execute(binary,prefix,cfg,pcm,dest)
            values=[x[0] for x in struct.iter_unpack('<f',dest.with_suffix('.f32').read_bytes())]
            require(len(values)==len(expected),'lost array frames')
            error=max(abs(x-y) for x,y in zip(values,expected))
            require(error<=plan['maximum_absolute_oracle_error'],'array/oracle mismatch')
            row={'case_id':key,'target':arch,'maximum_absolute_oracle_error':error}
            if key in plan['repeat_cases']:
                repeat=d/(arch+'-repeat');execute(binary,prefix,cfg,pcm,repeat)
                require(repeat.with_suffix('.f32').read_bytes()==dest.with_suffix('.f32').read_bytes(),'repeat changed PCM')
                mutated=bytearray(pcm.read_bytes()); boundary=plan['prefix_frames']*len(g['positions_m'])*2
                for i in range(boundary,len(mutated)): mutated[i]^=0x35
                future=d/'different-future.pcm';future.write_bytes(mutated)
                alternate=d/(arch+'-future');execute(binary,prefix,cfg,future,alternate)
                require(alternate.with_suffix('.f32').read_bytes()[:plan['prefix_frames']*4]==
                        dest.with_suffix('.f32').read_bytes()[:plan['prefix_frames']*4],'future leakage')
            report['cases'].append(row)
    import array_steering_checks
    report['steering']=array_steering_checks.run(output,targets)
    neg=output/'negative';neg.mkdir();report['negative_cli']=probe_negative_cli(runner,neg)
    write_json(output/'result.json',report); seal_output(output,report)
    return verify(output,revision)


def verify(root: Path, revision: str | None=None, require_arm: bool=False) -> dict:
    require(not (root/'failure.json').exists(),'failed run')
    require(all(not p.is_symlink() for p in root.rglob('*')),'symlink evidence forbidden')
    manifest=load_json(root/'manifest.json')
    actual={p.relative_to(root).as_posix():sha256(verified_file(root,p.relative_to(root).as_posix()).read_bytes())
            for p in root.rglob('*') if p.is_file() and p.relative_to(root).as_posix() not in ('manifest.json','SHA256SUMS')}
    require(actual==manifest['files'] and manifest['shipping_authority'] is False,'file set/hash/authority mismatch')
    sums={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);require(name not in sums,'duplicate checksum');sums[name]=digest
    require(sums=={**actual,'manifest.json':sha256((root/'manifest.json').read_bytes())},'checksum mismatch')
    plan=load_json(root/'experiment.json'); require(plan==load_json(PLAN),'experiment changed')
    for name in SOURCES:require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'stale source file '+name)
    report=load_json(root/'result.json')
    require(report['schema_version']==2,'unsupported array result schema')
    require(report['status']=='NATIVE_ARRAY_ENGINEERING_PASS' and report['shipping_authority'] is False
            and report['acoustic_improvement_proved'] is False,'invalid result authority')
    require(report['experiment_id']==manifest['experiment_id']==plan['experiment_id'],'experiment identity')
    require(hex_digest(report['execution_source_revision'],40),'invalid execution revision')
    if revision is not None:require(report['execution_source_revision']==revision,'stale source revision')
    require(type(report['arm_qualified']) is bool and (not require_arm or report['arm_qualified']),'missing Arm qualification')
    targets=['native','arm'] if report['arm_qualified'] else ['native']
    require(set(report['processors'])==set(targets),'missing processor identity')
    for arch in targets:
        blob=verified_file(root,'array-'+arch).read_bytes()
        require(sha256(blob)==report['processors'][arch] and blob[:4]==b'\x7fELF','stale/non-ELF processor')
        if arch=='arm':require(blob[4:6]==b'\x01\x01' and int.from_bytes(blob[18:20],'little')==40,'not AArch32 ELF')
    expected_keys={(key,arch) for key,_,_,_ in cases(plan) for arch in targets}
    rows={(r['case_id'],r['target']):r for r in report['cases']}
    require(set(rows)==expected_keys and len(rows)==len(report['cases']),'partial or duplicate cases')
    require(report['frequency_response']==frequency_response(plan),'frequency report changed')
    require(report['negative_cli']==dict.fromkeys(('nan','trailing','bad-count','empty','partial','odd','existing-output'),2),'negative cases missing')
    for arch in [*targets,'sanitized']:
        unit=load_json(root/f'unit-{arch}.json')
        require(unit['status']=='PASS' and unit['stress_frames']==64000 and unit['lifecycles']==64
                and unit['assertions']>=100000,'incomplete native contracts')
        a,b,c=unit['state_bytes'];require(0<a<b<c<=plan['maximum_state_bytes'] and b-a==512 and c-b==1024,'state does not scale')
    for key,g,pattern,mode in cases(plan):
        d=root/'cases'/key; data=verified_file(root,f'cases/{key}/input.pcm').read_bytes()
        require(data==make_input(g,pattern,plan['frames_per_case']),'input fixture changed')
        require((d/'geometry.txt').read_bytes()==geometry_text(g,mode),'geometry changed')
        expected=oracle(data,g,mode);latency,compensation=delays(g)
        for arch in targets:
            meta=load_json(d/f'{arch}.json');blob=(d/f'{arch}.f32').read_bytes()
            require(len(blob)==len(expected)*4,'truncated PCM')
            values=[v[0] for v in struct.iter_unpack('<f',blob)]
            require(all(math.isfinite(v) for v in values),'non-finite PCM')
            error=max(abs(x-y) for x,y in zip(values,expected))
            require(error==rows[key,arch]['maximum_absolute_oracle_error'] and error<=plan['maximum_absolute_oracle_error'],'oracle error changed')
            require(meta['status']=='PASS' and meta['shipping_authority'] is False
                    and meta['output_encoding']=='f32le-unclipped','bad native receipt')
            require(meta['mic_count']==len(g['positions_m']) and meta['sample_rate_hz']==g['sample_rate_hz']
                    and meta['active_mask']==g['active_mask'] and meta['samples_processed']==len(expected)
                    and meta['interpolation']==plan['interpolations'].index(mode)
                    and meta['common_delay_samples']==latency,'native geometry/count mismatch')
            require(len(meta['compensation_samples'])==len(compensation) and
                    max(abs(a-b) for a,b in zip(meta['compensation_samples'],compensation))<1e-10,'wrong compensation')
            unit=load_json(root/f'unit-{arch}.json')
            require(meta['state_bytes']==unit['state_bytes'][{1:0,2:1,4:2}[len(compensation)]],'state receipt mismatch')
            if key in plan['repeat_cases']:
                require((d/f'{arch}-repeat.f32').read_bytes()==blob,'repeat missing/different')
                prefix=plan['prefix_frames'];future=(d/'different-future.pcm').read_bytes();boundary=prefix*len(compensation)*2
                require(len(future)==len(data) and future[:boundary]==data[:boundary] and future[boundary:]!=data[boundary:],'invalid prefix test')
                alt=(d/f'{arch}-future.f32').read_bytes()
                require(len(alt)==len(blob) and alt[:prefix*4]==blob[:prefix*4],'future prefix changed')
                require(all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',alt)),'non-finite future result')
    import array_steering_checks
    steering_cases=array_steering_checks.verify(root,report['steering'],targets)
    return {'status':'VERIFIED','steering_cases':steering_cases,'cases':len(rows),'files':len(actual),'targets':targets,
            'execution_source_revision':report['execution_source_revision'],'shipping_authority':False}


class OracleTests(unittest.TestCase):
    def test_integer(self):
        for mode in ('linear','lagrange3'):
            self.assertEqual(sum(w for _,w in interpolation_taps(3.0,mode)),1.0)
            self.assertEqual(dict(interpolation_taps(3.0,mode))[3],1.0)
    def test_polynomials(self):
        for mode,degree in [('linear',1),('lagrange3',3)]:
            for delay in (1.0,1.1,2.5,5.99,125.0):
                for power in range(degree+1):
                    actual=sum(w*k**power for k,w in interpolation_taps(delay,mode))
                    self.assertAlmostEqual(actual,delay**power,places=7)
    def test_fixed_mask_latency(self):
        for g in load_json(PLAN)['geometries']:
            other=copy.deepcopy(g);other['active_mask']=1
            self.assertEqual(delays(g),delays(other))
    def test_fixed_direction_latency(self):
        for g in load_json(PLAN)['geometries']:
            other=copy.deepcopy(g);other['direction']=[1.,0.,0.]
            self.assertEqual(delays(g)[0],delays(other)[0])
    def test_known_aperture(self):
        g=copy.deepcopy(load_json(PLAN)['geometries'][1]);g['direction']=[1.,0.,0.]
        common,ds=delays(g);self.assertEqual(common,3)
        self.assertAlmostEqual(ds[1]-ds[0],0.035*16000/343)
    def test_mode_set(self):
        p=load_json(PLAN);self.assertEqual(p['interpolations'],['linear','lagrange3'])
        self.assertEqual(len(list(cases(p))),60)
        self.assertFalse(p['shipping_authority'])


def _mutate_evidence(root: Path, revision: str) -> dict:
    """Re-seal semantic mutations; checksum correctness alone must not admit them."""
    report=load_json(root/'result.json'); key=report['cases'][0]['case_id']
    failures=[]
    mutations=[('missing-case',lambda r:r['cases'].pop()),
               ('fake-promotion',lambda r:r.update(shipping_authority=True)),
               ('stale-sha',lambda r:r.update(execution_source_revision='0'*40)),
               ('wrong-metric',lambda r:r['cases'][0].update(maximum_absolute_oracle_error=1.0)),
               ('wrong-frequency',lambda r:r['frequency_response'][0].update(magnitude_db=5.0)),
               ('missing-steering-case',lambda r:r['steering']['cases'].pop()),
               ('fake-doa',lambda r:r['steering'].update(automatic_doa=True)),
               ('fake-aec-recovery',lambda r:r['steering'].update(aec_recovery_proved=True))]
    for name,change in mutations:
        changed=copy.deepcopy(report);change(changed);write_json(root/'result.json',changed);seal_output(root,changed)
        try:verify(root,revision)
        except (ValueError,KeyError):failures.append(name)
        else:raise ValueError('semantic mutation accepted: '+name)
    write_json(root/'result.json',report)
    for name,path,data in [('stale-binary',root/'array-native',b'NOT ELF'),
                           ('truncated-pcm',root/'cases'/key/'native.f32',b'\0'*4),
                           ('wrong-mask',root/'cases'/key/'geometry.txt',b'fake\n'),
                           ('missing-trace',root/'unit-native.json',b'{"status":"FAIL"}\n')]:
        original=path.read_bytes();path.write_bytes(data);seal_output(root,report)
        try:verify(root,revision)
        except (ValueError,KeyError):failures.append(name)
        else:raise ValueError('semantic mutation accepted: '+name)
        finally:path.write_bytes(original)
    steering_key=report['steering']['cases'][0]['case_id']
    for name,path,data in [('steering-command',root/'steering'/steering_key/'commands.txt',b'FORGED\n'),
                           ('steering-unit',root/'steering-unit-native.json',b'{"status":"FAIL"}\n'),
                           ('steering-chunk',root/'steering'/steering_key/'native-chunk.f32',b'\0'*4)]:
        original=path.read_bytes();path.write_bytes(data);seal_output(root,report)
        try:verify(root,revision)
        except (ValueError,KeyError):failures.append(name)
        else:raise ValueError('semantic mutation accepted: '+name)
        finally:path.write_bytes(original)
    seal_output(root,report);verify(root,revision)
    return {'status':'PASS','rejected_semantic_mutations':failures}


def negative_evidence(root: Path, revision: str) -> dict:
    # Never mutate the real receipt when testing tampered/resealed evidence.
    with tempfile.TemporaryDirectory(prefix='fe-array-negative-') as directory:
        copy_root=Path(directory)/'evidence'
        shutil.copytree(root,copy_root)
        return _mutate_evidence(copy_root,revision)


def main() -> int:
    p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--execution-source');p.add_argument('--verify',action='store_true')
    p.add_argument('--require-arm',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args()
    if a.self_test:
        import array_steering_checks
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(OracleTests),
                                 unittest.defaultTestLoader.loadTestsFromTestCase(array_steering_checks.SteeringOracleTests)])
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    require(a.output is not None and hex_digest(a.execution_source,40),'output and exact execution source required')
    root=a.output.resolve()
    if a.negative_evidence:result=negative_evidence(root,a.execution_source)
    elif a.verify:result=verify(root,a.execution_source,a.require_arm)
    else:result=qualify(root,a.execution_source,a.require_arm)
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError,subprocess.TimeoutExpired) as error:
        print(f'array qualification failed: {error}',file=sys.stderr);raise SystemExit(1)
