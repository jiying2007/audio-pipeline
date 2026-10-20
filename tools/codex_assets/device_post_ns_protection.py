"""D45 protection after NS/RES combined gain; development research with no shipping authority."""
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
from tools.codex_assets.device_power_attribution import records,repeat_future,size_budget,integer,finite,snapshot_frames
from tools.codex_assets import device_innovation_noise_gate as d44
D44=Path('/tmp/audio-fe-device-innovation-noise-gate-d44-20261011')
D44_HASHES={'result.json':'ba7d97c484e4e1315f019415d33e11f1228e72119db46d3b2595f970e78155be',
    'binding.json':'3edd5471650e97700c5e51b1a86bdda46f0500881473e7224c1163e854590f6a'}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_POST_NS_PROTECTION_D45_PLAN.zh-CN.md'
REVIEW=PLAN.with_name('DEVICE_POST_NS_PROTECTION_D45_PLAN_REVIEW.zh-CN.md')
C=ROOT/'tests/validation/frontend_evolution/device_post_ns_protection_d45.c'
NS=C.with_name('device_post_ns_d45.c')
HEADER=C.with_suffix('.h')
TEST=C.with_name('test_device_post_ns_protection.py')
OUTPUTS=d43.OUTPUTS
PROTECTION_FIELDS='frame far dt count_before count_after valid_bins raised_bins floor_mean'.split()
CONTROL_FIELDS='frame far dt frequency_active speech_probability noise_rms_dbfs residual_gain agc_allow gain_before gain_after effective_gain vad_probability vad_active vad_noise_rms vad_hangover'.split()
POWER_FIELDS=d43.POWER_FIELDS+['post_would_raise_bins']
BIN_FIELDS=d43.BIN_FIELDS+['updated_noise','combined_gain_before','combined_gain_after']
POWER_EXCLUDED=frozenset(('raised_bins','post_would_raise_bins'))
BIN_EXCLUDED=frozenset(('updated_noise','combined_gain_before','combined_gain_after'))

def project_equal(a,b,excluded,label):
    require(len(a)==len(b),label+' length')
    require(all({k:v for k,v in x.items() if k not in excluded}==
        {k:v for k,v in y.items() if k not in excluded} for x,y in zip(a,b)),label+' exact')

def baseline_outputs(directory,baseline,mode):
    names=d42.OUTPUTS[:4] if mode=='monitor' else ('bypass.f32le',)
    require(all(bounded(directory/n,4*1024*1024)==bounded(baseline/n,4*1024*1024) for n in names),'baseline waveform/control exact')
    if mode=='monitor':
        project_equal(list(records(directory/'protection.csv',PROTECTION_FIELDS)),
            list(records(baseline/'protection.csv',PROTECTION_FIELDS)),{'raised_bins'},'monitor protection')

def baseline_trace(current,previous):
    project_equal(current['power'],previous['power'],POWER_EXCLUDED,'baseline power operands')
    project_equal(current['bins'],previous['bins'],BIN_EXCLUDED,'baseline bin operands')

def trace(directory,frames,mode,gates):
    """Validate all rows; independent snapshot arithmetic belongs to separate audit."""
    require(mode in ('monitor','candidate'),'mode')
    require(len(gates)==frames*2 and all(x in (0,1) for x in gates),'gate count/value')
    power=[];previous_count=0
    for index,row in enumerate(records(directory/'power.csv',POWER_FIELDS)):
        require(index<frames and integer(row,'frame',frames-1)==index,'power frame sequence')
        far=integer(row,'far',1);dt=integer(row,'dt',1)
        require((far,dt)==tuple(gates[index*2:index*2+2]),'power gate identity')
        count=integer(row,'count_before',10)
        counts={k:integer(row,k,257) for k in POWER_FIELDS[4:9]}
        valid=counts['valid_bins'];active=bool(far and not dt)
        require(count==previous_count,'past count continuity')
        previous_count=min(10,count+1) if active else 0
        require((active and count==10) or valid==0,'warmup valid count')
        require(all(v<=valid for v in counts.values()),'bin count relation')
        require(mode!='monitor' or counts['raised_bins']==0,'monitor raised')
        post_would=integer(row,'post_would_raise_bins',257)
        require(post_would<=valid,'post count relation')
        require(mode!='candidate' or counts['raised_bins']==post_would,'candidate raised')
        nums={k:finite(row,k,0.0,1.0 if k in ('q_mean','floor_mean') else None) for k in d43.POWER_FIELDS[9:]}
        require(nums['innovation_sum']<=nums['residual_sum']+1e-12*nums['residual_sum'],'innovation bound')
        require(nums['excess_sum']<=nums['innovation_sum']+1e-12*nums['innovation_sum'],'excess bound')
        if not valid:require(all(v==0.0 for v in nums.values()),'empty aggregate')
        power.append(dict(row))
    require(len(power)==frames,'power frame count')
    protection=list(records(directory/'protection.csv',PROTECTION_FIELDS))
    require(len(protection)==frames,'protection frame count')
    for p,g in zip(power,protection):
        for key in ('frame','far','dt','count_before','valid_bins','raised_bins','floor_mean'):
            require(p[key]==g[key],'protection/power identity '+key)
        active=p['far']=='1' and p['dt']=='0'
        expected=min(10,int(p['count_before'])+1) if active else 0
        require(integer(g,'count_after',10)==expected,'protection count after')
    snapshots=snapshot_frames(frames);rows=0;selected=[];valid_in_snapshot=0;post_in_snapshot=0
    for row in records(directory/'bins.csv',BIN_FIELDS):
        require(rows<len(snapshots)*257,'extra bin row')
        frame=snapshots[rows//257];k=rows%257
        require(integer(row,'frame',frames-1)==frame and integer(row,'bin',256)==k,'snapshot/bin sequence')
        p=power[frame]
        for name in ('far','dt','count_before'):require(row[name]==p[name],'snapshot state identity')
        valid=integer(row,'valid',1)
        valid_in_snapshot+=valid
        if valid:require(p['far']=='1' and p['dt']=='0' and p['count_before']=='10','snapshot valid state')
        for key in ('E','R','N','power','echo_power'):finite(row,key,0.0)
        for key in ('Cr','Ci','er','ei','rr','ri'):finite(row,key)
        for key in ('original_target','old_gain','floor','applied_target','res_gain'):finite(row,key,0.0,1.0)
        finite(row,'updated_noise',0.0)
        before=finite(row,'combined_gain_before',0.0,1.0)
        after=finite(row,'combined_gain_after',0.0,1.0)
        require(row['applied_target']==row['original_target'],'original RES target unchanged')
        active=p['far']=='1' and p['dt']=='0'
        expected=max(before,float(row['floor'])) if active and mode=='candidate' else before
        require(after==expected,'post protection position')
        post_in_snapshot+=int(active and float(row['floor'])>before)
        if not valid:require(float(row['floor'])==0.0,'invalid floor')
        if p['far']!='1' or p['dt']!='0':
            require(all(float(row[key])==0.0 for key in ('E','R','Cr','Ci','er','ei','echo_power','original_target','old_gain','floor','applied_target','res_gain')) and valid==0,'inactive snapshot')
        selected.append(dict(row));rows+=1
        if k==256:
            require(valid_in_snapshot==int(p['valid_bins']),'snapshot valid aggregate')
            require(post_in_snapshot==int(p['post_would_raise_bins']),'snapshot post aggregate')
            valid_in_snapshot=0;post_in_snapshot=0
    require(rows==len(snapshots)*257,'snapshot bin count')
    return dict(power=power,bins=selected,snapshot_frames=snapshots,bin_rows=rows)

def paired_traces(a,b):
    for key,excluded in (('power',{'raised_bins'}),('bins',{'combined_gain_after'})):
        project_equal(a[key],b[key],excluded,'D45 mode past-state '+key)

def paired_controls(a,b):
    preserved={'frame','far','dt','frequency_active','speech_probability','noise_rms_dbfs','residual_gain'}
    project_equal(list(records(a/'control.csv',CONTROL_FIELDS)),
        list(records(b/'control.csv',CONTROL_FIELDS)),set(CONTROL_FIELDS)-preserved,'original NS/RES control')

def preflight():
    cases,locks=d44.preflight()
    for name,h in D44_HASHES.items():
        p=D44/name;require(sha(bounded(p,4*1024*1024))==h,'D44 identity');locks[str(p)]=h
    binding=read_json(D44/'binding.json')
    for group in ('locked_files','artifacts'):
        for name,h in binding[group].items():
            p=D44/name if group=='artifacts' else Path(name)
            require(sha(bounded(p,4*1024*1024))==h,'D44 drift '+str(p));locks[str(p)]=h
    for p,h in ((PLAN,'15e94e9f589aa6ceb9933f8193cbbf4b10bbfc34d57bf05c794c6213fd2c24ce'),
        (REVIEW,'4694589c1c59b9d6bc4da81621648c6a108a873d3ab6b0fbce2ba0053fb66558'),
        (Path('/tmp/audio-device-d44-review-snapshot-v1.json'),'0cf2c83f9c556416d464a765c6d86806d4aa161d8539a6afcc5719f349b2aea5'),
        (PLAN.with_name('DEVICE_INNOVATION_NOISE_GATE_D44_CLOSEOUT.zh-CN.md'),'c6397cffae756f628d398bfd1f705ba8ca7db752b0509dba5b9413d638d2631d')):
        require(sha(bounded(p,4*1024*1024))==h,'frozen identity '+str(p));locks[str(p)]=h
    for p in (C,NS,HEADER,TEST,Path(__file__).resolve()):
        locks[str(p)]=sha(bounded(p,4*1024*1024))
    return cases,locks

def run(output):
    require(not output.exists() and not output.is_symlink() and
        output.absolute()==output.resolve() and Path('/tmp') in output.resolve().parents,'new /tmp root required')
    cases,locks=preflight()
    require(shutil.disk_usage('/tmp').free>=3*1024**3,'startup disk budget')
    previous={r['name']:r for r in read_json(D44/'result.json')['cases']}
    require(len(previous)==184,'D44 execution set')
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
            for name in OUTPUTS:(directory/name).write_bytes(b'D45_SENTINEL '+name.encode())
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
                    require(original_summary=={k:v for k,v in previous[name]['execution_summary'].items() if k not in ('observer_state_bytes','measurement_scoped_bytes')},'D44 algorithm resource/call identity')
                    require(type(summary['observer_state_bytes']) is int and summary['observer_state_bytes']>0 and
                        summary['measurement_scoped_bytes']==summary['scoped_bytes']+summary['observer_state_bytes'] and
                        summary['measurement_scoped_bytes']<=65536 and summary['measurement_scoped_bytes']+71224<=131072,'measurement resource budget')
                    baseline_outputs(directory,D44/name,mode)
                    observation=d42.observe(directory,case,arm,original_summary,mode)
                    if mode=='monitor':require(observation==previous[name]['observation'],'monitor frozen measurement identity')
                    diagnostic=trace(directory,frames,mode,gates)
                    baseline_trace(diagnostic,d43.trace(D44/('monitor-'+arm+'-'+case['name']),frames,'monitor',gates));pair.append(diagnostic)
                    completed.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,mode=mode,
                        execution_summary=summary,observation=observation,
                        diagnostic=dict(snapshot_frames=diagnostic['snapshot_frames'],bin_rows=diagnostic['bin_rows'],power_rows=len(diagnostic['power']))))
                    size_budget(output);d42.matrix_budget(matrix_started)
                    print('D45_CASE_PASS '+name,flush=True)
                paired_traces(*pair)
                paired_controls(output/('monitor-'+arm+'-'+case['name']),output/('candidate-'+arm+'-'+case['name']))
        repeat_future(output)
        require(len(completed)==184 and sum(r['execution_summary']['frames'] for r in completed)==505944,'matrix coverage')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        size_budget(output);d42.matrix_budget(matrix_started)
        admission=d42.development_admission(completed,cases)
        decision='DEVELOPMENT_CANDIDATE_ONLY' if admission['accepted'] else 'DEVELOPMENT_REJECTED'
        dump(output/'result.json',dict(experiment='FE_DEVICE_POST_NS_PROTECTION_D45',executions=184,frames=505944,
            data_role='development-and-synthetic-engineering',decision=decision,measurement_only=False,
            promotion_allowed=False,shipping_approved=False,baseline_hashes=D44_HASHES,
            development_admission=admission,frequency_enabled=1,integration_changed=True,shipping_algorithm_changed=False,
            cases=completed,matrix_elapsed_seconds=time.monotonic()-matrix_started))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=D44_HASHES,source_input_start_end_equal=True,
            runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        size_budget(output)
        print('D45_MEASUREMENT_PASS 184 '+decision+' NO_PROMOTION',flush=True)
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
    print(json.dumps(dict(experiment='FE_DEVICE_POST_NS_PROTECTION_D45',cases=len(cases),
        locked_files=len(locks),writes=False,dsp_executed=False,promotion_allowed=False,
        shipping_approved=False,formal_matrix_implemented=True)))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)
