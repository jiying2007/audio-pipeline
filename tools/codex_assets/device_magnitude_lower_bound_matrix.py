"""D49 structural magnitude-lower-bound experiment with frozen D48 scoring."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets import device_current_measurement as d48
from tools.codex_assets import device_current_innovation as d47
from tools.codex_assets import device_noise_conditioned_protection as d42
from tools.codex_assets import device_magnitude_lower_bound as core
from tools.codex_assets.device_capture import ROOT,sha,strict_json
from tools.codex_assets.device_exact_reference import dump
from tools.codex_assets.device_noise_conditioned_protection import bounded,require,read_json

EXPERIMENT='FE_DEVICE_MAGNITUDE_LOWER_BOUND_D49'
FORMAL_ROOT=Path('/tmp/audio-fe-device-magnitude-lower-bound-d49-20261015')
D48=Path('/tmp/audio-fe-device-current-measurement-d48-20261013')
DOC=ROOT/'docs/research/frontend-evolution-v1'
C=core.C;NS=core.NS;HEADER=core.HEADER;OUTPUTS=d47.OUTPUTS
TEST=ROOT/'tests/validation/frontend_evolution/test_device_magnitude_lower_bound_matrix.py'
SNAPSHOT=Path('/tmp/audio-device-d48-review-snapshot-v1.json')
D48_HASHES={'result.json':'d8c80ee2c612fccd62de1bae86bf107e71062e95c1609cddf7abe5714992a6cf',
    'binding.json':'5f8fa795e386e32c83743f66ffdc1361bf48cc00705f13f11efa7238c0d3e9ff'}
PINS={
    Path(d48.__file__).resolve():'27b5ae3e00d9e74e2cbbc1c8b37a185119d493e295243236ff1b1e936a6c3fed',
    d48.TEST:'4f9a5a536bdb699119d72ef62c5b3691611bf91c7b08d0596ac6376010bc5c85',
    **core.FROZEN_SOURCES,
    C:'fbcb151d7543fdb3e2d006aa9670ffc8233cb331d0da75c2d6aa1da10fae0dd9',
    NS:'92d142c7a409412937f5bf5266e1b9c495460ae7079754377f56889d0bad5618',
    HEADER:'727c80d5474ad1d73504a4ae71ac8249ad2e8707d01a8cdd4ec6d25f83d0e4e4',
    Path(core.__file__).resolve():'7d2845003b3a107e41b3a582d0ab77648508b8b6cd06f77dde5d1d68c2b74a1e',
    core.DIRECTORY/'test_device_magnitude_lower_bound.py':'af1318f929adbed5a44ff52d007c4524396889cce8eab78e90831e600647637b',
    SNAPSHOT:'ad1482fce4bf777f65cea0d13c46f58fb7799c6247366e80a349f1d48f6db131',
    Path('/tmp/audio-device-d48-closeout-v1-10.json'):'e1405f5a98cb22f01bd362b8bc72eff57bb556ffbadbf38cfae77aa765d07838',
    Path('/tmp/audio-device-d48-closeout-v1-11.json'):'000a4f17267846d5320715980a9960ca3bdcf27162206c466669ff319d42bc79',
    Path('/tmp/audio-device-d49-c-selftest-v1/intent.json'):'9e0f47e10d0aaefade22d011dad684ce6a38664f9e970be7d8db742c7d9ee538',
    Path('/tmp/audio-device-d49-c-selftest-v1/receipt.json'):'930ff37d927d11862411d8a2739d00611a9c5b1224a0584e8341319d2a916019',
    DOC/'DEVICE_MAGNITUDE_LOWER_BOUND_D49_PLAN.zh-CN.md':'e8ffa4a9db2165b80f036c4791fdf1af6b7ca5215a7cc2daec47d8e8d2cbb119',
    DOC/'DEVICE_MAGNITUDE_LOWER_BOUND_D49_AMENDMENT.zh-CN.md':'9e7ddaa0e82d434f3d2addc631d878562c35719a21bb03e98dcf7a810ec87a65',
    DOC/'DEVICE_MAGNITUDE_LOWER_BOUND_D49_PLAN_REVIEW.zh-CN.md':'772cfe8f5328eee065fcb47ccf0d13b19c750c0ca9eb262d68569e8576d0d06d',
    DOC/'DEVICE_MAGNITUDE_LOWER_BOUND_D49_C_PREFLIGHT.zh-CN.md':'db88a55d3b78501759bfbdfa25bdfff9db3dacb2cd23a74f307f68e1d7aa8cf1',
    **{D48/name:h for name,h in D48_HASHES.items()},
}

def root_guard(output):
    require(output.is_absolute() and output==FORMAL_ROOT and not output.exists() and
            not any(p.is_symlink() for p in (output,)+tuple(output.parents)) and
            output.absolute()==output.resolve(),'fixed new direct /tmp root required')

def add_identity(locks,path,digest):
    path=Path(path);key=str(path)
    require(path.is_absolute() and isinstance(digest,str) and len(digest)==64 and
            all(c in '0123456789abcdef' for c in digest),'absolute SHA256 identity')
    require(key not in locks or locks[key]==digest,'conflicting input SHA: '+key)
    locks[key]=digest

def baseline_contract(result,binding,cases):
    require(result['experiment']=='FE_DEVICE_CURRENT_MEASUREMENT_D48' and
            result['decision']=='MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION' and
            result['measurement_only'] is True and result['executions']==184 and
            result['frames']==505944 and
            result['data_role']=='development-and-synthetic-engineering' and
            result['promotion_allowed'] is False and result['shipping_approved'] is False and
            result['development_admission']['accepted'] is False and
            all(v['accepted'] is False for v in result['development_admission']['arms'].values()),
            'actual D48 measurement baseline, not algorithm approval')
    names={mode+'-'+arm+'-'+c['name'] for c in cases
           for arm in ('primary','selected') for mode in ('monitor','candidate')}
    require(len(names)==184 and len(result['cases'])==184 and
            {c['name'] for c in result['cases']}==names,'D48 exact baseline case set')
    require(binding['source_input_start_end_equal'] is True and
            len(binding['locked_files'])==11744 and len(binding['artifacts'])==1884,
            'complete frozen D48 input/artifact domain')

def baseline_trace(current,previous):
    # Current P/J and overshoot remain diagnostics, and must stay exactly equal.
    excluded=d47.POWER_EXCLUDED-set(d47.CURRENT_FIELDS)
    d47.project_equal(current['power'],previous['power'],excluded,'D48 original power and raw current operands')
    d47.project_equal(current['bins'],previous['bins'],d47.BIN_EXCLUDED,'D48 original bin operands')

def preflight():
    # Pin the source/terminal chain before invoking inherited semantic validators.
    pins={}
    for path,h in PINS.items():
        require(not path.is_symlink() and sha(bounded(path,4*1024*1024))==h,
                'D49 literal frozen input: '+str(path))
        add_identity(pins,path,h)
    cases,locks=d48.preflight()
    require(len(locks)==11744,'complete D48 original preflight')
    for p,h in pins.items():add_identity(locks,p,h)
    result=read_json(D48/'result.json');binding=read_json(D48/'binding.json')
    baseline_contract(result,binding,cases)
    for p,h in binding['locked_files'].items():
        require(locks.get(p)==h,'D48 locked file inherited: '+p)
    for relative,h in binding['artifacts'].items():
        p=Path(relative)
        require(not p.is_absolute() and '..' not in p.parts,'relative D48 artifact')
        add_identity(locks,D48/p,h)
    snapshot=read_json(SNAPSHOT)
    require(snapshot['status']=='FROZEN' and snapshot['exit_code']==0 and
            snapshot['experiment']=='FE_DEVICE_CURRENT_MEASUREMENT_D48' and
            snapshot['source_start_end_equal'] is True and len(snapshot['files'])==13671 and
            snapshot['promotion_allowed'] is False and snapshot['shipping_approved'] is False,
            'actual complete D48 final snapshot')
    for p,h in snapshot['files'].items():add_identity(locks,p,h)
    gate=read_json(Path('/tmp/audio-device-d48-closeout-v1-10.json'))
    require(gate['exit_code']==0 and gate['child_terminal'] is True and
            gate['snapshot_sha256']==PINS[SNAPSHOT],'D48 actual final gate terminal')
    final=strict_json(gate['stdout'].encode())
    require(final['goal_id']=='task-fe8e96504fd58d9d71dd496b' and
            final['goal_status']=='completed' and final['gate_event']=='final' and
            final['gate_allowed'] is True and final['completion_allowed'] is True and
            final['reasons']==[] and final['missing_evidence']==[],'D48 actual final allowed')
    terminal=read_json(Path('/tmp/audio-device-d48-closeout-v1-11.json'))
    require(terminal['exit_code']==0 and terminal['child_terminal'] is True,
            'D48 actual status terminal')
    state=strict_json(terminal['stdout'].encode())
    require(state['goal']['goal_id']=='task-fe8e96504fd58d9d71dd496b' and
            state['goal']['status']=='completed' and state['goal']['open_items_count']==0 and
            state['checkpoint']['revision']==9 and state['checkpoint']['verified'] is True,
            'D48 completed local stage, not overall goal')
    private=read_json(Path('/tmp/audio-device-d49-c-selftest-v1/receipt.json'))
    require(private['status']=='C_IMPLEMENTATION_SELF_TEST_VERIFIED' and
            private['source_end_verified'] is True and
            [v['exit_code'] for v in private['commands']]==[0,0,2] and
            all(v['terminal'] is True and v['timed_out'] is False for v in private['commands']),
            'actual D49 private selftest')
    # Inherited preflight already hashed its 11744 files; do not read these twice.
    verified=set(d48_input for d48_input in binding['locked_files'])|set(pins)
    for path,h in locks.items():
        if path not in verified:
            require(not Path(path).is_symlink() and sha(bounded(Path(path),4*1024*1024))==h,
                    'D49 inherited final artifact drift: '+path)
    for path in (Path(__file__).resolve(),TEST):
        add_identity(locks,path,sha(bounded(path,4*1024*1024)))
    return cases,locks

def run(output):
    root_guard(output)
    cases,locks=preflight()
    require(shutil.disk_usage('/tmp').free>=3*1024**3,'startup disk budget')
    previous={r['name']:r for r in read_json(D48/'result.json')['cases']}
    require(len(previous)==184,'D48 execution set')
    output.mkdir();completed=[];matrix_started=None
    try:
        flags=(d42.D18/'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
        defs=[s.split('=',1)[1].split() for s in flags.splitlines() if s.startswith('C_DEFINES =')]
        require(len(defs)==1 and all(x.startswith('-DAP_BUILD_') for x in defs[0]),'original build defines')
        d42.logged(output,'compile',['rtk','cc',*d42.FLAGS,'-ffp-contract=off',*defs[0],'-I',str(d42.D18/'source/src'),'-I',str(d42.D18/'source/include'),'-I',str(d42.D18/'build/generated'),str(C),str(NS),str(d42.D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
        d42.logged(output,'self-test',['rtk',str(output/'runner'),'--self-test'],ROOT)
        d42.logged(output,'invalid-argc',['rtk',str(output/'runner'),'invalid'],ROOT,expected=2)
        for label,frame_text,mode,bad_gate in [('frames','bad','monitor',False),('mode','1','bad',False),('gates','1','monitor',True)]:
            directory=output/('invalid-preserve-'+label);directory.mkdir()
            for name in OUTPUTS:(directory/name).write_bytes(b'D48_SENTINEL '+name.encode())
            source=d42.BASE/cases[0]['name']
            for name in ('residual','echo'):(directory/(name+'.f32le')).write_bytes(bounded(source/(name+'.f32le'),4*1024*1024)[:640])
            (directory/'gates.bin').write_bytes(bytes((2,0)) if bad_gate else bytes((0,0)))
            before={p.name:p.read_bytes() for p in directory.iterdir()}
            d42.logged(output,'invalid-preserve-'+label,['rtk',str(output/'runner'),str(directory/'residual.f32le'),str(directory/'echo.f32le'),str(directory/'gates.bin'),frame_text,str(directory),mode],ROOT,expected=4 if bad_gate else 2)
            require({p.name:p.read_bytes() for p in directory.iterdir()}==before,'seven-output sentinel preservation')
        matrix_started=time.monotonic()
        for case in cases:
            source=d42.BASE/case['name'];frames=case['execution_summary']['frames'];gates=d42.gate_bytes(source,frames)
            for arm in ('primary','selected'):
                pair=[]
                for mode in ('monitor','candidate'):
                    d42.matrix_budget(matrix_started)
                    name=mode+'-'+arm+'-'+case['name'];directory=output/name;directory.mkdir()
                    (directory/'gates.bin').write_bytes(gates);prefix='primary_' if arm=='primary' else ''
                    command=['rtk',str(output/'runner'),str(source/(prefix+'residual.f32le')),str(source/(prefix+'echo.f32le')),str(directory/'gates.bin'),str(frames),str(directory),mode]
                    summary=strict_json(d42.logged(output,name,command,ROOT).encode())
                    require(set(summary)==set(previous[name]['execution_summary']),'summary schema')
                    original_summary={k:v for k,v in summary.items() if k not in ('observer_state_bytes','measurement_scoped_bytes')}
                    require(original_summary=={k:v for k,v in previous[name]['execution_summary'].items() if k not in ('observer_state_bytes','measurement_scoped_bytes')},'D48 algorithm resource/call identity')
                    require(type(summary['observer_state_bytes']) is int and summary['observer_state_bytes']>0 and
                        summary['measurement_scoped_bytes']==summary['scoped_bytes']+summary['observer_state_bytes'] and
                        summary['measurement_scoped_bytes']<=65536 and summary['measurement_scoped_bytes']+71224<=131072,'measurement resource budget')
                    d47.baseline_outputs(directory,D48/name,mode)
                    observation=d48.observe(directory,case,arm,original_summary,mode)
                    if mode=='monitor':require(d48.common_observation(observation)==d48.common_observation(previous[name]['observation']),'monitor frozen common measurement identity')
                    diagnostic=d47.trace(directory,frames,mode,gates)
                    baseline_trace(diagnostic,d47.trace(D48/('monitor-'+arm+'-'+case['name']),frames,'monitor',gates));pair.append(diagnostic)
                    completed.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,mode=mode,
                        execution_summary=summary,observation=observation,
                        diagnostic=dict(snapshot_frames=diagnostic['snapshot_frames'],bin_rows=diagnostic['bin_rows'],power_rows=len(diagnostic['power']))))
                    d47.size_budget(output);d42.matrix_budget(matrix_started)
                    print('D49_CASE_PASS '+name,flush=True)
                d47.paired_traces(*pair)
                d47.paired_controls(output/('monitor-'+arm+'-'+case['name']),output/('candidate-'+arm+'-'+case['name']))
        d47.repeat_future(output)
        require(len(completed)==184 and sum(r['execution_summary']['frames'] for r in completed)==505944,'matrix coverage')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        d47.size_budget(output);d42.matrix_budget(matrix_started)
        admission=d42.development_admission(completed,cases)
        decision='DEVELOPMENT_CANDIDATE_ONLY' if admission['accepted'] else 'DEVELOPMENT_REJECTED'
        dump(output/'result.json',dict(experiment=EXPERIMENT,executions=184,frames=505944,
            data_role='development-and-synthetic-engineering',decision=decision,measurement_only=False,
            promotion_allowed=False,shipping_approved=False,baseline_hashes=D48_HASHES,
            development_admission=admission,algorithm_basis=EXPERIMENT,frequency_enabled=1,integration_changed=True,shipping_algorithm_changed=False,
            cases=completed,matrix_elapsed_seconds=time.monotonic()-matrix_started))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=D48_HASHES,source_input_start_end_equal=True,
            runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        d47.size_budget(output)
        print('D49_MATRIX_COMPLETE 184 '+decision+' NO_PROMOTION',flush=True)
    except Exception as error:
        dump(output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID_REPLAN',error=str(error),completed_executions=len(completed)))
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run',action='store_true',help='Complete inherited semantic preflight; no DSP or writes')
    mode.add_argument('--run',action='store_true',help='Independently reviewed single formal matrix')
    parser.add_argument('--output-root',type=Path)
    args=parser.parse_args()
    if args.run:
        require(args.output_root is not None,'output root required')
        run(args.output_root);return 0
    require(args.output_root is None,'output root requires explicit --run')
    cases,locks=preflight()
    print(json.dumps(dict(experiment=EXPERIMENT,cases=len(cases),locked_files=len(locks),
        writes=False,dsp_executed=False,measurement_only=False,promotion_allowed=False,
        shipping_approved=False,formal_matrix_implemented=True)))
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)

