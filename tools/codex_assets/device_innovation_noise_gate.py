"""D44 fixed innovation/noise gate; development research with no shipping authority."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import read_json,dump
from tools.codex_assets import device_noise_conditioned_protection as d42
from tools.codex_assets import device_power_attribution as d43
from tools.codex_assets.device_power_attribution import trace,records,paired_traces,repeat_future,size_budget
D43=Path('/tmp/audio-fe-device-power-attribution-d43-20261011')
D43_HASHES={'result.json':'3642acfaa5ccf2e9c452c013bae0ca5539e0ef70a418eb69862b7eaaa64d6d1f',
    'binding.json':'f6ed4dbcd4cbfc9e7a0aa4351ac00117afc63d8f966d443d30a54a799299a87b'}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_INNOVATION_NOISE_GATE_D44_PLAN.zh-CN.md'
AMEND=PLAN.with_name('DEVICE_INNOVATION_NOISE_GATE_D44_AMENDMENT.zh-CN.md')
REVIEW=PLAN.with_name('DEVICE_INNOVATION_NOISE_GATE_D44_PLAN_REVIEW.zh-CN.md')
C=ROOT/'tests/validation/frontend_evolution/device_innovation_noise_gate_d44.c'
NS=C.with_name('device_innovation_ns_d44.c')
HEADER=C.with_suffix('.h')
TEST=C.with_name('test_device_innovation_noise_gate.py')
OUTPUTS=d43.OUTPUTS
PROTECTION_FIELDS='frame far dt count_before count_after valid_bins raised_bins floor_mean'.split()
POWER_EXCLUDED=frozenset(('positive_floor_bins','would_raise_bins','raised_bins','floor_mean','floor2_residual_sum'))
BIN_EXCLUDED=frozenset(('old_gain','floor','applied_target','res_gain'))

def project_equal(a,b,excluded,label):
    require(len(a)==len(b),label+' length')
    require(all({k:v for k,v in x.items() if k not in excluded}==
        {k:v for k,v in y.items() if k not in excluded} for x,y in zip(a,b)),label+' exact')

def baseline_outputs(directory,baseline,mode):
    names=d42.OUTPUTS[:4] if mode=='monitor' else ('bypass.f32le',)
    require(all(bounded(directory/n,4*1024*1024)==bounded(baseline/n,4*1024*1024) for n in names),'baseline waveform/control exact')
    if mode=='monitor':
        project_equal(list(records(directory/'protection.csv',PROTECTION_FIELDS)),
            list(records(baseline/'protection.csv',PROTECTION_FIELDS)),{'floor_mean'},'monitor protection')

def baseline_trace(current,previous):
    project_equal(current['power'],previous['power'],POWER_EXCLUDED,'baseline power operands')
    project_equal(current['bins'],previous['bins'],BIN_EXCLUDED,'baseline bin operands')

def preflight():
    cases,locks=d43.preflight()
    for name,h in D43_HASHES.items():
        p=D43/name;require(sha(bounded(p,4*1024*1024))==h,'D43 identity');locks[str(p)]=h
    binding=read_json(D43/'binding.json')
    for group in ('locked_files','artifacts'):
        for name,h in binding[group].items():
            p=D43/name if group=='artifacts' else Path(name)
            require(sha(bounded(p,4*1024*1024))==h,'D43 drift '+str(p));locks[str(p)]=h
    for p,h in ((PLAN,'844bcdf4e5904577e08ae3d33cb8a93381cca272f7e33e49c6e0cf5b2ab5874b'),
        (AMEND,'f765cb47945d2687ad86554bb69dab3c5ca08f280cbf8e9f41dc840ba3a2f128'),
        (REVIEW,'ff5e9febeecfedc4aa43cb837ee87f6ffeb33f8136f58a22759b56aff7b19775'),
        (Path('/tmp/audio-device-d43-review-snapshot-v1.json'),'b00d2bbb92e733dda91c0440b96269ab1d14c4096d50cdcb45ca069a91f878b3'),
        (PLAN.with_name('DEVICE_POWER_ATTRIBUTION_D43_CLOSEOUT.zh-CN.md'),'d56e26e43745197fd14a7e6335867c8e79c55558768542b0f352c819009a3290')):
        require(sha(bounded(p,4*1024*1024))==h,'frozen identity '+str(p));locks[str(p)]=h
    for p in (C,NS,HEADER,TEST,Path(__file__).resolve()):
        locks[str(p)]=sha(bounded(p,4*1024*1024))
    return cases,locks

def run(output):
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp root required')
    cases,locks=preflight()
    require(shutil.disk_usage('/tmp').free>=3*1024**3,'startup disk budget')
    previous={r['name']:r for r in read_json(D43/'result.json')['cases']}
    require(len(previous)==184,'D43 execution set')
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
            for name in OUTPUTS:(directory/name).write_bytes(b'D44_SENTINEL '+name.encode())
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
                    require(summary==previous[name]['execution_summary'],'D43 resource/call identity')
                    require(type(summary['observer_state_bytes']) is int and summary['observer_state_bytes']>0 and
                        summary['measurement_scoped_bytes']==summary['scoped_bytes']+summary['observer_state_bytes'] and
                        summary['measurement_scoped_bytes']<=65536 and summary['measurement_scoped_bytes']+71224<=131072,'measurement resource budget')
                    baseline_outputs(directory,D43/name,mode)
                    observation=d42.observe(directory,case,arm,original_summary,mode)
                    if mode=='monitor':require(observation==previous[name]['observation'],'monitor frozen measurement identity')
                    diagnostic=trace(directory,frames,mode,gates)
                    baseline_trace(diagnostic,trace(D43/name,frames,mode,gates));pair.append(diagnostic)
                    completed.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,mode=mode,
                        execution_summary=summary,observation=observation,
                        diagnostic=dict(snapshot_frames=diagnostic['snapshot_frames'],bin_rows=diagnostic['bin_rows'],power_rows=len(diagnostic['power']))))
                    size_budget(output);d42.matrix_budget(matrix_started)
                    print('D44_CASE_PASS '+name,flush=True)
                paired_traces(*pair)
        repeat_future(output)
        require(len(completed)==184 and sum(r['execution_summary']['frames'] for r in completed)==505944,'matrix coverage')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        size_budget(output);d42.matrix_budget(matrix_started)
        admission=d42.development_admission(completed,cases)
        decision='DEVELOPMENT_CANDIDATE_ONLY' if admission['accepted'] else 'DEVELOPMENT_REJECTED'
        dump(output/'result.json',dict(experiment='FE_DEVICE_INNOVATION_NOISE_GATE_D44',executions=184,frames=505944,
            data_role='development-and-synthetic-engineering',decision=decision,measurement_only=False,
            promotion_allowed=False,shipping_approved=False,baseline_hashes=D43_HASHES,
            development_admission=admission,frequency_enabled=1,integration_changed=True,shipping_algorithm_changed=False,
            cases=completed,matrix_elapsed_seconds=time.monotonic()-matrix_started))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=D43_HASHES,source_input_start_end_equal=True,
            runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        size_budget(output)
        print('D44_MEASUREMENT_PASS 184 '+decision+' NO_PROMOTION',flush=True)
    except Exception as error:
        dump(output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID_REPLAN',error=str(error),completed_executions=len(completed)))
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true',help='Read-only frozen preflight; no DSP')
    parser.add_argument('--output-root',type=Path,help='New /tmp root after independent review')
    args=parser.parse_args()
    if not args.dry_run:
        require(args.output_root is not None,'output root required')
        run(args.output_root);return 0
    cases,locks=preflight()
    print(json.dumps(dict(experiment='FE_DEVICE_INNOVATION_NOISE_GATE_D44',cases=len(cases),
        locked_files=len(locks),writes=False,dsp_executed=False,promotion_allowed=False,
        shipping_approved=False,formal_matrix_implemented=True)))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)

