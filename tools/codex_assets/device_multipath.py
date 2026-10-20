"""D22 frozen MDF multipath/transition engineering diagnostic, no promotion."""
from __future__ import annotations
import argparse
from array import array
import csv
import io
import math
from pathlib import Path
import struct
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, sha, strict_json
from tools.codex_assets.device_exact_reference import dump, logged, read_json
from tools.codex_assets.device_path import preflight as d21_preflight, raw_signal, encoded, signal, stats, FIELDS, TRACES
from tools.codex_assets.device_replay import FLAGS
from tools.codex_assets.device_stages import D18

BASE = Path('/tmp/audio-fe-device-path-d21-20261011')
BASE_HASHES = {'result.json':'7441e49b516a810fdda0f7acc91095771ddb29a4c9fd2fab5b376205bd4c55c0',
               'binding.json':'a368f3f69ffbfe1a567343e4be96c8c06fbfdc5de97f80e49a59b025ff4539d9'}
PLAN = ROOT/'docs/research/frontend-evolution-v1/DEVICE_MULTIPATH_D22_PLAN.zh-CN.md'
RUNNER = ROOT/'tests/validation/frontend_evolution/device_multipath_d22.c'
KERNELS = {'A':((48,0.5),(176,-0.25),(400,0.125)), 'B':((80,0.375),(240,-0.125),(560,0.25))}
WINDOWS = ((0,2),(8,10),(10,10.5),(10.5,12),(12,14),(18,20))
CASES = [(f'{shape}-r{offset}',shape,offset,'normal') for shape in ('A','B','switch') for offset in (16,20)] + [
    (mode,'A',16,mode) for mode in ('disabled','hold','zero')] + [('repeat','switch',20,'normal'),('future','switch',20,'future')]


def preflight(root):
    d21_preflight(root)
    for name, expected in BASE_HASHES.items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected,'D21 dependency drift')
    binding = read_json(BASE/'binding.json')
    for name, expected in binding['source_files'].items():
        require(sha(bounded(Path(name),4*1024*1024)) == expected,'D21 source drift')
    for name, expected in binding['artifacts'].items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected,'D21 artifact drift')
    require(sha(bounded(BASE/'runner',4*1024*1024)) == binding['runner_sha256'],'D21 runner drift')


def f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


def mic_sample(raw, n, shape):
    key = ('A' if n < 160000 else 'B') if shape == 'switch' else shape
    value = 0.0
    for delay, gain in KERNELS[key]:
        if n >= delay:
            value = f32(value + f32(gain * raw[n-delay]))
    return value


def measure(directory, shape, offset, mode):
    values = {name:signal(directory/(name+'.f32le')) for name in TRACES}
    raw = raw_signal(mode == 'future')
    require((directory/'mic.f32le').read_bytes() == encoded(mic_sample(raw,n,shape) for n in range(320000)), 'multipath mic construction')
    ref = [0.0]*320000 if mode == 'zero' else [0.0]*offset+list(raw[:-offset])
    require((directory/'reference.f32le').read_bytes() == encoded(ref),'known reference construction')
    error = max(abs(a-(b+c)) for a,b,c in zip(values['mic'],values['echo'],values['residual']))
    require(error <= 1e-6,'AEC identity')
    reader = csv.DictReader(io.StringIO(bounded(directory/'state.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames == FIELDS,'state schema')
    rows = list(reader)
    require(len(rows) == 2000,'state frame count')
    for i,row in enumerate(rows):
        require(set(row) == set(FIELDS) and row['frame'] == str(i) and all(math.isfinite(float(v)) for v in row.values()),'state finite/sequence')
        require(row['runtime_stride'] == '2' and row['adapt_phase'] in ('0','1') and
                0 <= int(row['constrain_partition']) < 48 and 0 <= int(row['x_head']) < 48 and
                0 <= int(row['steady_frames']) <= 50 and float(row['x_power_total']) >= 0 and float(row['weight_l2']) >= 0,'state range')
    if mode in ('disabled','hold','zero'):
        require(not any(values['echo']) and values['residual'] == values['mic'] and
                all(float(row['weight_l2']) == 0 for row in rows),'negative output/weight')
    return dict(arithmetic_max_abs_error=error,whole=stats(values['mic'],values['residual'],0,320000),
                windows=[dict(seconds=[a,b],sample_range=[int(a*16000),int(b*16000)],
                              **stats(values['mic'],values['residual'],int(a*16000),int(b*16000))) for a,b in WINDOWS],final_state=rows[-1])


def run(root, output, created):
    preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    inherited = [Path(p) for p in read_json(BASE/'binding.json')['source_files']]
    sources = [Path(__file__).resolve(),PLAN,RUNNER,*inherited]
    initial = {str(f):sha(bounded(f,4*1024*1024)) for f in sources}
    output.mkdir(); created.append(output)
    flags = D18/'build/CMakeFiles/audio_pipeline.dir/flags.make'
    definitions = [line.split('=',1)[1].split() for line in flags.read_text().splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions) == 1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]),'build definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),
           '-I',str(D18/'build/generated'),str(RUNNER),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    executable_hash = sha((output/'runner').read_bytes())
    logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    cases = []
    for name,shape,offset,mode in CASES:
        directory = output/name; directory.mkdir()
        summary = strict_json(logged(output,name,[str(output/'runner'),shape,str(offset),mode,str(directory)],ROOT).encode())
        require(summary == dict(frames=2000,samples=320000,sync_calls=0),'execution summary')
        cases.append(dict(name=name,path_shape=shape,reference_offset=offset,mode=mode,measurement=measure(directory,shape,offset,mode)))
    names = [n+'.f32le' for n in TRACES]+['state.csv']
    for name in names:
        original = (output/'switch-r20'/name).read_bytes()
        require(original == (output/'repeat'/name).read_bytes(),'repeat equivalence')
        other = (output/'future'/name).read_bytes()
        require(original[:640000] == other[:640000] if name.endswith('.f32le') else
                original.splitlines()[:1001] == other.splitlines()[:1001],'future prefix causality')
        for offset in (16,20):
            switch = (output/f'switch-r{offset}'/name).read_bytes()
            static = (output/f'A-r{offset}'/name).read_bytes()
            require(switch[:640000] == static[:640000] if name.endswith('.f32le') else
                    switch.splitlines()[:1001] == static.splitlines()[:1001],'switch prefix equivalence')
    for offset in (16,20):
        for name in ('mic.f32le','reference.f32le'):
            require((output/f'switch-r{offset}'/name).read_bytes()[640000:] ==
                    (output/f'B-r{offset}'/name).read_bytes()[640000:],'switch B suffix input')
    difference = lambda a,b: {key:b[key]-a[key] for key in ('residual_rms_dbfs','known_echo_erle_db')}
    records = {c['name']:c['measurement'] for c in cases}
    pairs, recovery = [],[]
    for shape in ('A','B','switch'):
        require((output/f'{shape}-r16/mic.f32le').read_bytes() == (output/f'{shape}-r20/mic.f32le').read_bytes(),'paired mic drift')
        a,b = records[f'{shape}-r16'],records[f'{shape}-r20']
        pairs.append(dict(path_shape=shape,whole=difference(a['whole'],b['whole']),
                          windows=[dict(seconds=x['seconds'],**difference(x,y)) for x,y in zip(a['windows'],b['windows'])]))
    for offset in (16,20):
        a,b = records[f'B-r{offset}'],records[f'switch-r{offset}']
        recovery.append(dict(reference_offset=offset,windows=[dict(seconds=x['seconds'],**difference(x,y))
                          for x,y in zip(a['windows'][2:],b['windows'][2:])]))
    preflight(root)
    require(initial == {str(f):sha(bounded(f,4*1024*1024)) for f in sources} and
            executable_hash == sha((output/'runner').read_bytes()),'experiment identity drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_MULTIPATH_D22',decision='MULTIPATH_TRANSITION_DIAGNOSTIC_NO_PROMOTION',
         data_role='synthetic-engineering',executions=11,promotion_allowed=False,shipping_approved=False,algorithm_changed=False,
         kernels=KERNELS,cases=cases,offset20_minus_offset16=pairs,switch_minus_static_B=recovery))
    dump(output/'binding.json',dict(source_files=initial,runner_sha256=executable_hash,d21_hashes=BASE_HASHES,
         source_start_end_equal=True,input_start_end_equal=True,library_sha256=initial[str(D18/'build/libaudio_pipeline.a')],
         artifacts={str(f.relative_to(output)):sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}))
    print('D22_MULTIPATH_PASS 11 executions',flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args(argv); created = []
    try:
        if args.dry_run:
            preflight(args.root); print('D22_PREFLIGHT_PASS 11 registered executions; writes=False')
        else:
            run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created == [args.output]:
            dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_multipath: '+str(error),file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
