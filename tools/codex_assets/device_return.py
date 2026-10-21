"""D25 frozen return-path and synthetic near-end gating diagnostic; no promotion."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, sha, strict_json
from tools.codex_assets.device_exact_reference import dump, logged, read_json
from tools.codex_assets.device_multipath import KERNELS, f32
from tools.codex_assets.device_path import raw_signal, encoded, signal, FIELDS
from tools.codex_assets.device_shadow import preflight as d24_preflight, step
from tools.codex_assets.device_replay import FLAGS
from tools.codex_assets.device_stages import D18

BASE = Path('/tmp/audio-fe-device-shadow-d24-20261011')
BASE_HASHES = {'result.json':'894417dda2d7240726c464a7197b517fd11e715eadc4ab021c8efcd892c8bcce',
               'binding.json':'870405d2a9145672066f222bcb4ec895f632e9b3b346e288ea42b0737c4191a9'}
PLAN = ROOT/'docs/research/frontend-evolution-v1/DEVICE_RETURN_D25_PLAN.zh-CN.md'
AMEND = ROOT/'docs/research/frontend-evolution-v1/DEVICE_RETURN_D25_AMENDMENT.zh-CN.md'
RUNNER = ROOT/'tests/validation/frontend_evolution/device_return_d25.c'
SELECTOR = ROOT/'tests/validation/frontend_evolution/device_shadow_selector_d24.h'
TEST = ROOT/'tests/validation/frontend_evolution/test_device_return.py'
TRACES = ('mic','reference','echo','residual','primary_echo','primary_residual','shadow_echo','shadow_residual','true_echo','near')
WINDOWS = ((0,2),(8,10),(10,10.5),(10.5,12),(12,12.5),(12.5,14),(16,18),(18,20))
CASES = [(f'{shape}-r{offset}-{condition}-{policy}',shape,offset,condition,policy,False)
         for shape in ('A','ABA') for offset in (16,20) for condition in ('echo','dt','unguarded') for policy in ('keep','shadow')]+[
         ('repeat','ABA',20,'unguarded','shadow',False),('future','ABA',20,'unguarded','shadow',True)]
SELECT_FIELDS = ['frame','active','dt','bank','streak','change','primary_energy','shadow_energy']


def preflight(root):
    d24_preflight(root)
    for name, expected in BASE_HASHES.items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected, 'D24 dependency drift')
    binding = read_json(BASE/'binding.json')
    for name, expected in binding['source_files'].items():
        require(sha(bounded(Path(name),4*1024*1024)) == expected, 'D24 source drift')
    for name, expected in binding['artifacts'].items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected, 'D24 artifact drift')
    require(sha(bounded(BASE/'runner',4*1024*1024)) == binding['runner_sha256'], 'D24 runner drift')


def near_active(frame):
    return 1000 <= frame < 1200 or 1600 <= frame < 1800


def inputs(shape, offset, condition, future):
    raw = raw_signal(future)
    state = 0x87654321
    truth, near, mic = [], [], []
    for n in range(320000):
        state ^= (state << 13) & 0xffffffff; state ^= state >> 17; state ^= (state << 5) & 0xffffffff
        q = f32((int(state & 65535)-32768)/524288.0)
        if future and n >= 160000: q = -q
        q = q if condition != 'echo' and near_active(n//160) else 0.0
        key = 'B' if shape == 'ABA' and 160000 <= n < 192000 else 'A'
        value = 0.0
        for delay, gain in KERNELS[key]:
            if n >= delay: value = f32(value+f32(gain*raw[n-delay]))
        truth.append(value); near.append(q); mic.append(f32(value+q))
    return dict(mic=mic, reference=[0.0]*offset+list(raw[:-offset]), true_echo=truth, near=near)


def rms_peak(values):
    require(len(values)>0 and all(math.isfinite(v) for v in values), 'finite measurement values')
    power = math.fsum(v*v for v in values)/len(values)
    return dict(rms_dbfs=20*math.log10(max(math.sqrt(power),1e-12)), peak=max(abs(v) for v in values))


def window(values, first, last, policy):
    near = values['near'][first:last]; truth = values['true_echo'][first:last]
    powers = math.fsum(v*v for v in truth)/len(truth)
    require(powers > 0, 'empty true echo')
    channels = {}
    for name in ('selected','primary','shadow'):
        if name == 'shadow' and (policy != 'shadow' or first < 160000):
            channels[name] = None; continue
        residual = values['residual' if name == 'selected' else name+'_residual'][first:last]
        error = [v-q for v,q in zip(residual,near)]
        channels[name] = dict(residual=rms_peak(residual), error=rms_peak(error), known_echo_erle_db=None)
        if not any(near):
            err_power = math.fsum(v*v for v in error)/len(error)
            channels[name]['known_echo_erle_db'] = 10*math.log10(powers/max(err_power,1e-20))
    return dict(sample_range=[first,last], samples=last-first, near_present=bool(any(near)),
                true_echo=rms_peak(truth), channels=channels)


def observe(directory, shape, offset, condition, policy, future, summary):
    expected = dict(frames=2000,samples=320000,sync_calls=0,primary_calls=2000,
                    shadow_calls=1000 if policy=='shadow' else 0,shadow_reset_calls=int(policy=='shadow'),
                    dt_frames=400 if condition=='dt' else 0)
    require(set(summary)==set(expected)|{'switch_count','state_bytes'} and all(type(v) is int for v in summary.values()) and
            all(summary[k]==v for k,v in expected.items()) and summary['state_bytes']>0, 'summary schema/counts')
    values = {name:signal(directory/(name+'.f32le')) for name in TRACES}
    for name, value in inputs(shape,offset,condition,future).items():
        require((directory/(name+'.f32le')).read_bytes()==encoded(value), 'input construction '+name)
    first = 160000 if policy=='shadow' else 320000
    require(not any(values['shadow_echo'][:first]) and not any(values['shadow_residual'][:first]), 'inactive shadow trace')
    arithmetic = {}
    for name in ('selected','primary','shadow'):
        if name=='shadow' and policy=='keep': continue
        start = 160000 if name=='shadow' else 0
        echo = values['echo' if name=='selected' else name+'_echo']
        residual = values['residual' if name=='selected' else name+'_residual']
        arithmetic[name] = max(abs(a-b-c) for a,b,c in zip(values['mic'][start:],echo[start:],residual[start:]))
        require(arithmetic[name]<=1e-6, 'AEC identity '+name)
    reader = csv.DictReader(io.StringIO(bounded(directory/'state.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==FIELDS, 'state schema'); rows=list(reader); require(len(rows)==2000,'state length')
    for frame,row in enumerate(rows):
        require(row['frame']==str(frame) and all(math.isfinite(float(v)) for v in row.values()) and row['runtime_stride']=='2' and
                row['adapt_phase'] in ('0','1') and 0<=int(row['constrain_partition'])<48 and 0<=int(row['x_head'])<48 and
                0<=int(row['steady_frames'])<=50 and float(row['x_power_total'])>=0 and float(row['weight_l2'])>=0,'state range')
    reader = csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==SELECT_FIELDS,'selector schema'); selectors=list(reader); require(len(selectors)==2000,'selector length')
    bank,streak=0,0; events=[]; data={name:bounded(directory/(name+'.f32le'),2*1024*1024) for name in TRACES}
    for frame,row in enumerate(selectors):
        a,b=frame*160,(frame+1)*160
        pe=sum(v*v for v in values['primary_residual'][a:b]); se=sum(v*v for v in values['shadow_residual'][a:b])
        active=policy=='shadow' and frame>=1000; dt=condition=='dt' and near_active(frame); old=bank
        bank,streak,change=step(bank,streak,active,not dt,pe,se)
        require([row[k] for k in SELECT_FIELDS[:6]]==[str(frame),str(int(active)),str(int(dt)),str(bank),str(streak),str(change)] and
                float(row['primary_energy'])==pe and float(row['shadow_energy'])==se,'selector recurrence/energy')
        for name in ('echo','residual'):
            chosen=('shadow_' if bank else 'primary_')+name
            require(data[name][a*4:b*4]==data[chosen][a*4:b*4], 'selected bytes')
        if change:
            require(not dt and frame>0,'gated event')
            events.append(dict(frame=frame,from_bank=old,to_bank=bank,
                 adjacent_sample_delta=values['residual'][a]-values['residual'][a-1],
                 banks_first_sample_delta=values['shadow_residual'][a]-values['primary_residual'][a]))
    require(summary['switch_count']==len(events),'switch count')
    return dict(arithmetic_max_abs_error=arithmetic,events=events,final_bank=bank,
                whole=window(values,0,320000,policy),
                windows=[dict(seconds=[a,b],**window(values,int(a*16000),int(b*16000),policy)) for a,b in WINDOWS])


def differences(a,b):
    return [dict(sample_range=x['sample_range'],selected_error_rms_db_delta=y['channels']['selected']['error']['rms_dbfs']-
                 x['channels']['selected']['error']['rms_dbfs']) for x,y in zip([a['whole'],*a['windows']],[b['whole'],*b['windows']])]


def compare_baseline(directory, old, prefix):
    for name in [n+'.f32le' for n in TRACES[:8]]+['state.csv']:
        a=bounded(directory/name,2*1024*1024); b=bounded(old/name,2*1024*1024)
        require(a[:640000]==b[:640000] if prefix and name.endswith('.f32le') else
                a.splitlines()[:1001]==b.splitlines()[:1001] if prefix else a==b, 'D24 equivalence '+name)
    new=list(csv.DictReader(io.StringIO((directory/'selector.csv').read_text())))
    old_rows=list(csv.DictReader(io.StringIO((old/'selector.csv').read_text())))
    count=1000 if prefix else 2000
    require(all(row['dt']=='0' for row in new[:count]) and
            [{k:v for k,v in row.items() if k!='dt'} for row in new[:count]]==old_rows[:count], 'D24 selector projection')


def run(root,output,created):
    preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents, 'new /tmp output required')
    sources=[Path(__file__).resolve(),PLAN,AMEND,RUNNER,SELECTOR,TEST,*[Path(p) for p in read_json(BASE/'binding.json')['source_files']]]
    initial={str(p):sha(bounded(p,4*1024*1024)) for p in sources}
    output.mkdir(); created.append(output)
    flags=D18/'build/CMakeFiles/audio_pipeline.dir/flags.make'
    definitions=[line.split('=',1)[1].split() for line in flags.read_text().splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions)==1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]), 'build definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),
           '-I',str(D18/'build/generated'),str(RUNNER),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    executable_hash=sha((output/'runner').read_bytes())
    logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,shape,offset,condition,policy,extra in [('shape','bad','16','echo','shadow',[]),('offset','A','bad','echo','shadow',[]),
            ('condition','A','16','bad','shadow',[]),('policy','A','16','echo','bad',[]),('future','A','16','echo','shadow',['future'])]:
        directory=output/('invalid-preserve-'+label); directory.mkdir()
        sentinels={n+'.f32le':b'D25_SENTINEL '+n.encode('ascii') for n in TRACES}
        sentinels.update({n:b'D25_SENTINEL '+n.encode('ascii') for n in ('state.csv','selector.csv')})
        for name,data in sentinels.items(): (directory/name).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),shape,offset,condition,str(directory),policy,*extra],ROOT,expected=2)
        require({p.name:p.read_bytes() for p in directory.iterdir()}==sentinels, 'invalid no truncation')
        require(read_json(output/('command-invalid-preserve-'+label+'.json'))['stderr']=='D25_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0\n', 'invalid calls zero')
    cases=[]
    for name,shape,offset,condition,policy,future in CASES:
        directory=output/name; directory.mkdir()
        summary=strict_json(logged(output,name,[str(output/'runner'),shape,str(offset),condition,str(directory),policy,*(['future'] if future else [])],ROOT).encode())
        cases.append(dict(name=name,path_shape=shape,reference_offset=offset,condition=condition,policy=policy,future=future,execution_summary=summary,
                          measurement=observe(directory,shape,offset,condition,policy,future,summary)))
    records={c['name']:c['measurement'] for c in cases}; pairs=[]; gates=[]
    for shape in ('A','ABA'):
        for offset in (16,20):
            for policy in ('keep','shadow'):
                compare_baseline(output/f'{shape}-r{offset}-echo-{policy}',BASE/f'{"A" if shape=="A" else "switch"}-r{offset}-{policy}',shape=='ABA')
                a=output/f'{shape}-r{offset}-dt-{policy}'; b=output/f'{shape}-r{offset}-unguarded-{policy}'
                for name in ('mic','reference','near','true_echo'):
                    require((a/(name+'.f32le')).read_bytes()==(b/(name+'.f32le')).read_bytes(),'gate paired input')
                gates.append(dict(path_shape=shape,reference_offset=offset,policy=policy,
                             dt_minus_unguarded=differences(records[b.name],records[a.name])))
            for condition in ('echo','dt','unguarded'):
                prefix=f'{shape}-r{offset}-{condition}'; a=output/(prefix+'-keep'); b=output/(prefix+'-shadow')
                for name in ('mic','reference','near','true_echo','primary_echo','primary_residual'):
                    require((a/(name+'.f32le')).read_bytes()==(b/(name+'.f32le')).read_bytes(),'primary bank independence')
                require((a/'state.csv').read_bytes()==(b/'state.csv').read_bytes(),'primary state independence')
                pairs.append(dict(path_shape=shape,reference_offset=offset,condition=condition,
                                  shadow_minus_keep=differences(records[a.name],records[b.name])))
    for name in [n+'.f32le' for n in TRACES]+['state.csv','selector.csv']:
        original=(output/'ABA-r20-unguarded-shadow'/name).read_bytes()
        require(original==(output/'repeat'/name).read_bytes(),'repeat equivalence')
        future=(output/'future'/name).read_bytes()
        require(original[:640000]==future[:640000] if name.endswith('.f32le') else
                original.splitlines()[:1001]==future.splitlines()[:1001],'future prefix')
    preflight(root)
    require(initial=={str(p):sha(bounded(p,4*1024*1024)) for p in sources} and executable_hash==sha((output/'runner').read_bytes()), 'experiment identity drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_RETURN_D25',decision='RETURN_NEAR_GATE_DIAGNOSTIC_NO_PROMOTION',
         data_role='synthetic-engineering',executions=26,promotion_allowed=False,shipping_approved=False,
         research_algorithm_changed=False,shipping_algorithm_changed=False,selector=dict(ratio=0.8,confirmation_frames=3,crossfade=False),
         cases=cases,shadow_minus_keep=pairs,dt_minus_unguarded=gates,
         resources=dict(extra_shadow_state_bytes=cases[0]['execution_summary']['state_bytes'],scope='state sizeof/calls only; not CPU/peak/DUT')))
    dump(output/'binding.json',dict(source_files=initial,runner_sha256=executable_hash,d24_hashes=BASE_HASHES,source_start_end_equal=True,input_start_end_equal=True,
         library_sha256=initial[str(D18/'build/libaudio_pipeline.a')],artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
    print('D25_RETURN_PASS 26 executions',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv); created=[]
    try:
        if args.dry_run: preflight(args.root); print('D25_PREFLIGHT_PASS 26 registered executions; writes=False')
        else: run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created==[args.output]: dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_return: '+str(error),file=sys.stderr); return 2


if __name__=='__main__': raise SystemExit(main())
