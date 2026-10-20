"""D24 protected shadow-reset research prototype, never shipping authority."""
from __future__ import annotations
import argparse
import csv
import io
from pathlib import Path
import subprocess
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import dump,logged,read_json
from tools.codex_assets.device_multipath import measure,TRACES,signal
from tools.codex_assets.device_reset import preflight as d23_preflight,difference,BASE as D22
from tools.codex_assets.device_replay import FLAGS
from tools.codex_assets.device_stages import D18

BASE=Path('/tmp/audio-fe-device-reset-d23-20261011')
BASE_HASHES={'result.json':'34999146de3ef13d1364d289165cc5381c420fb4e4f40a40cc31d0d484803f60',
             'binding.json':'e5e7ce39b20a9a077439cb2417dbd0eb26065c0248c09e9c011821d88167859a'}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_SHADOW_D24_PLAN.zh-CN.md'
AMENDMENT=ROOT/'docs/research/frontend-evolution-v1/DEVICE_SHADOW_D24_AMENDMENT.zh-CN.md'
RUNNER=ROOT/'tests/validation/frontend_evolution/device_shadow_d24.c'
SELECTOR=ROOT/'tests/validation/frontend_evolution/device_shadow_selector_d24.h'
EXTRA=('primary_echo','primary_residual','shadow_echo','shadow_residual')
CASES=[(f'{shape}-r{offset}-{policy}',shape,offset,'normal',policy)
       for shape in ('A','B','switch') for offset in (16,20) for policy in ('keep','shadow')]+[
       (mode,'A',16,mode,'shadow') for mode in ('disabled','hold','zero')]+[
       ('repeat','switch',20,'normal','shadow'),('future','switch',20,'future','shadow')]


def preflight(root):
    d23_preflight(root)
    for name,expected in BASE_HASHES.items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected,'D23 dependency drift')
    binding=read_json(BASE/'binding.json')
    for name,expected in binding['source_files'].items():
        require(sha(bounded(Path(name),4*1024*1024)) == expected,'D23 source drift')
    for name,expected in binding['artifacts'].items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected,'D23 artifact drift')
    require(sha(bounded(BASE/'runner',4*1024*1024)) == binding['runner_sha256'],'D23 runner drift')


def step(bank,streak,active,eligible,primary,shadow):
    if not active: return 0,0,0
    current,other=(shadow,primary) if bank else (primary,shadow)
    streak=streak+1 if eligible and current>1e-20 and other<0.8*current else 0
    return (1-bank,0,1) if streak==3 else (bank,streak,0)


def observe(directory,shape,offset,mode,policy,summary):
    require(set(summary)=={'frames','samples','sync_calls','primary_calls','shadow_calls','shadow_reset_calls','switch_count','state_bytes'} and
            all(type(v) is int for v in summary.values()),'summary schema/types')
    require(summary['frames']==2000 and summary['samples']==320000 and summary['sync_calls']==0 and summary['primary_calls']==2000 and
            summary['shadow_calls']==(1000 if policy=='shadow' else 0) and summary['shadow_reset_calls']==(1 if policy=='shadow' else 0) and
            summary['state_bytes']>0,'execution summary')
    result=measure(directory,shape,offset,mode)
    values={name:signal(directory/(name+'.f32le')) for name in EXTRA}
    mic=signal(directory/'mic.f32le')
    require(max(abs(a-b-c) for a,b,c in zip(mic,values['primary_echo'],values['primary_residual']))<=1e-6,'primary identity')
    first=160000 if policy=='shadow' else 320000
    require(not any(values['shadow_echo'][:first]) and not any(values['shadow_residual'][:first]),'inactive shadow zeros')
    if policy=='shadow':
        require(max(abs(a-b-c) for a,b,c in zip(mic[first:],values['shadow_echo'][first:],values['shadow_residual'][first:]))<=1e-6,'shadow identity')
    reader=csv.DictReader(io.StringIO(bounded(directory/'selector.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==['frame','active','bank','streak','change','primary_energy','shadow_energy'],'selector schema')
    rows=list(reader); require(len(rows)==2000,'selector frame count')
    data={name:bounded(directory/(name+'.f32le'),2*1024*1024) for name in ('echo','residual',*EXTRA)}
    bank,streak,changes=0,0,[]
    for frame,row in enumerate(rows):
        a,b=frame*160,(frame+1)*160
        pe=sum(v*v for v in values['primary_residual'][a:b]); se=sum(v*v for v in values['shadow_residual'][a:b])
        active=policy=='shadow' and frame>=1000
        bank,streak,change=step(bank,streak,active,mode not in ('disabled','hold'),pe,se)
        require(row['frame']==str(frame) and row['active']==str(int(active)) and row['bank']==str(bank) and row['streak']==str(streak) and
                row['change']==str(change) and float(row['primary_energy'])==pe and float(row['shadow_energy'])==se,'selector recurrence/energy')
        if change: changes.append(frame)
        for name in ('echo','residual'):
            chosen=('shadow_' if bank else 'primary_')+name
            require(data[name][a*4:b*4]==data[chosen][a*4:b*4],'selected output')
    require(summary['switch_count']==len(changes),'switch count')
    return dict(**result,selection=dict(change_frames=changes,final_bank=bank))


def run(root,output,created):
    preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    sources=[Path(__file__).resolve(),PLAN,AMENDMENT,RUNNER,SELECTOR,*[Path(p) for p in read_json(BASE/'binding.json')['source_files']]]
    initial={str(f):sha(bounded(f,4*1024*1024)) for f in sources}
    output.mkdir(); created.append(output)
    flags=D18/'build/CMakeFiles/audio_pipeline.dir/flags.make'
    definitions=[line.split('=',1)[1].split() for line in flags.read_text().splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions)==1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]),'build definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),
           '-I',str(D18/'build/generated'),str(RUNNER),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    runner_hash=sha((output/'runner').read_bytes())
    logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    for label,shape,offset,mode in [('shape','invalid','16','normal'),('offset','A','invalid','normal'),('mode','A','16','invalid'),('combination','B','16','hold')]:
        directory=output/('invalid-preserve-'+label); directory.mkdir()
        sentinels={name:(b'D24_INVALID_ARGUMENT_SENTINEL '+name.encode('ascii')) for name in
                   ('primary_echo.f32le','primary_residual.f32le','shadow_echo.f32le','shadow_residual.f32le','selector.csv')}
        for name,data in sentinels.items(): (directory/name).write_bytes(data)
        logged(output,'invalid-preserve-'+label,[str(output/'runner'),shape,offset,mode,str(directory),'shadow'],ROOT,expected=2)
        require({p.name:p.read_bytes() for p in directory.iterdir()}==sentinels,'invalid argument output preservation')
        receipt=read_json(output/('command-invalid-preserve-'+label+'.json'))
        require(receipt['stderr']=='D24_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0\n','invalid argument no processing')
    logged(output,'selector-self-test',[str(output/'runner'),'--selector-self-test'],ROOT)
    cases=[]
    for name,shape,offset,mode,policy in CASES:
        directory=output/name; directory.mkdir()
        summary=strict_json(logged(output,name,[str(output/'runner'),shape,str(offset),mode,str(directory),policy],ROOT).encode())
        cases.append(dict(name=name,path_shape=shape,reference_offset=offset,mode=mode,policy=policy,execution_summary=summary,
                          measurement=observe(directory,shape,offset,mode,policy,summary)))
    names=[n+'.f32le' for n in (*TRACES,*EXTRA)]+['state.csv','selector.csv']
    records={c['name']:c['measurement'] for c in cases}; pairs=[]
    for shape in ('A','B','switch'):
        for offset in (16,20):
            prefix=f'{shape}-r{offset}'
            for policy in ('keep','shadow'):
                directory=output/(prefix+'-'+policy)
                for current,old in [('mic','mic'),('reference','reference'),('primary_echo','echo'),('primary_residual','residual')]:
                    require((directory/(current+'.f32le')).read_bytes()==(D22/prefix/(old+'.f32le')).read_bytes(),'primary D22 equivalence')
                require((directory/'state.csv').read_bytes()==(D22/prefix/'state.csv').read_bytes(),'primary state D22 equivalence')
            for name in [n+'.f32le' for n in TRACES]+['state.csv']:
                keep=(output/(prefix+'-keep')/name).read_bytes(); candidate=(output/(prefix+'-shadow')/name).read_bytes()
                require(keep==(D22/prefix/name).read_bytes(),'keep D22 equivalence')
                require(keep[:640000]==candidate[:640000] if name.endswith('.f32le') else
                        keep.splitlines()[:1001]==candidate.splitlines()[:1001],'candidate prefix equivalence')
            for name in ('echo','residual'):
                require((output/(prefix+'-shadow')/('shadow_'+name+'.f32le')).read_bytes()[640000:]==
                        (BASE/(prefix+'-reset')/(name+'.f32le')).read_bytes()[640000:],'shadow D23 equivalence')
            a,b=records[prefix+'-keep'],records[prefix+'-shadow']
            pairs.append(dict(path_shape=shape,reference_offset=offset,whole=difference(a['whole'],b['whole']),
                         windows=[dict(seconds=x['seconds'],**difference(x,y)) for x,y in zip(a['windows'],b['windows'])]))
    for name in names:
        original=(output/'switch-r20-shadow'/name).read_bytes()
        require(original==(output/'repeat'/name).read_bytes(),'repeat equivalence')
        future=(output/'future'/name).read_bytes()
        require(original[:640000]==future[:640000] if name.endswith('.f32le') else
                original.splitlines()[:1001]==future.splitlines()[:1001],'future prefix causality')
    require(len({c['execution_summary']['state_bytes'] for c in cases})==1,'state size identity')
    preflight(root)
    require(initial=={str(f):sha(bounded(f,4*1024*1024)) for f in sources} and runner_hash==sha((output/'runner').read_bytes()),'experiment identity drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_SHADOW_D24',decision='PROTECTED_SHADOW_PROTOTYPE_NO_PROMOTION',data_role='synthetic-engineering',
         executions=17,promotion_allowed=False,shipping_approved=False,shipping_algorithm_changed=False,research_algorithm_changed=True,
         selector=dict(ratio=0.8,confirmation_frames=3,crossfade=False),cases=cases,shadow_minus_keep=pairs,
         resources=dict(extra_shadow_state_bytes=cases[0]['execution_summary']['state_bytes'],
                        shadow_aec_calls_per_activated_run=1000,scope='state sizeof and call counts only; not peak/CPU/DUT')))
    dump(output/'binding.json',dict(source_files=initial,runner_sha256=runner_hash,d23_hashes=BASE_HASHES,source_start_end_equal=True,input_start_end_equal=True,
         library_sha256=initial[str(D18/'build/libaudio_pipeline.a')],artifacts={str(f.relative_to(output)):sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}))
    print('D24_SHADOW_PASS 17 executions',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv); created=[]
    try:
        if args.dry_run: preflight(args.root); print('D24_PREFLIGHT_PASS 17 registered executions; writes=False')
        else: run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created==[args.output]: dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_shadow: '+str(error),file=sys.stderr); return 2


if __name__=='__main__': raise SystemExit(main())
