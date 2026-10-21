"""D47 past complex fit/current innovation; original admission and no shipping authority."""
from __future__ import annotations
import argparse
import csv
import io
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import time
if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT,bounded,require,sha,strict_json
from tools.codex_assets.device_exact_reference import read_json,dump
from tools.codex_assets import device_noise_conditioned_protection as d42
from tools.codex_assets import device_power_attribution as d43
from tools.codex_assets.device_power_attribution import records,repeat_future,size_budget,integer,finite,snapshot_frames
from tools.codex_assets import device_post_ns_protection as d45
D45=Path('/tmp/audio-fe-device-post-ns-protection-d45-20261011')
D45_HASHES={'result.json':'0d9dbf01b21510216df648d323c501166a039a5b45d44c93d2699b8eabc4e8de',
    'binding.json':'bb0fbb8b9942e2b9ca5dbecf9a53ac1f13f38d40c7bbb574d5a438506d00cff8'}
PLAN=ROOT/'docs/research/frontend-evolution-v1/DEVICE_CURRENT_INNOVATION_D47_PLAN.zh-CN.md'
REVIEW=PLAN.with_name('DEVICE_CURRENT_INNOVATION_D47_PLAN_REVIEW.zh-CN.md')
C=ROOT/'tests/validation/frontend_evolution/device_current_innovation_d47.c'
NS=C.with_name('device_current_innovation_ns_d47.c')
HEADER=C.with_suffix('.h')
TEST=C.with_name('test_device_current_innovation.py')
OUTPUTS=d43.OUTPUTS
PROTECTION_FIELDS='frame far dt count_before count_after valid_bins raised_bins floor_mean'.split()
CONTROL_FIELDS='frame far dt frequency_active speech_probability noise_rms_dbfs residual_gain agc_allow gain_before gain_after effective_gain vad_probability vad_active vad_noise_rms vad_hangover'.split()
CURRENT_FIELDS=['current_residual_sum','current_innovation_sum','prediction_overshoot_bins']
POWER_FIELDS=d45.POWER_FIELDS+CURRENT_FIELDS
BIN_FIELDS=d43.BIN_FIELDS+['updated_noise','combined_gain_before','combined_gain_after']
POWER_EXCLUDED=frozenset(('raised_bins','positive_floor_bins','would_raise_bins','post_would_raise_bins','floor_mean','floor2_residual_sum',*CURRENT_FIELDS))
BIN_EXCLUDED=frozenset(('floor','combined_gain_after'))

def project_equal(a,b,excluded,label):
    require(len(a)==len(b),label+' length')
    require(all({k:v for k,v in x.items() if k not in excluded}==
        {k:v for k,v in y.items() if k not in excluded} for x,y in zip(a,b)),label+' exact')

def baseline_outputs(directory,baseline,mode):
    names=d42.OUTPUTS[:4] if mode=='monitor' else ('bypass.f32le',)
    require(all(bounded(directory/n,4*1024*1024)==bounded(baseline/n,4*1024*1024) for n in names),'baseline waveform/control exact')
    if mode=='monitor':
        project_equal(list(records(directory/'protection.csv',PROTECTION_FIELDS)),
            list(records(baseline/'protection.csv',PROTECTION_FIELDS)),{'raised_bins','floor_mean'},'monitor protection')

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
        overshoot=integer(row,'prediction_overshoot_bins',257)
        require(overshoot<=valid,'overshoot valid relation')
        current={k:finite(row,k,0.0) for k in CURRENT_FIELDS[:2]}
        if not valid:require(overshoot==0 and all(v==0.0 for v in current.values()),'empty current aggregate')
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

BASE_SOURCE_PINS={
    d45.C:'101ba4441794d8845b82904a8c524db4ea88fea746f29b9d0cb08b967baa048a',
    d45.NS:'ba6c427a2ea01d0a540bc21a14e6ce6a7c172ed278120b9ae1359ae27ff07724',
    d45.HEADER:'82458adbab6fb83708ab89f3cd24b99ccde02f83df1680933b455f74594d570d',
    d45.TEST:'3f6ca5da374fec4afafbc77dd7f44198bf7d79b1241e20bd12bbc08b038bbca0',
    Path(d45.__file__).resolve():'84ae3a41685e46a71769017e17b0ab277c1ef68e3c28e9bd722c5f9872831c17',
}
class PreflightInputs:
    """One start-phase digest per exact path; no PCM cache or end-phase reuse."""
    def __init__(self):
        self.expected={}
        self.checked={}
        self.documents={}

    def add(self,path,expected):
        path=Path(path)
        require(path.is_absolute(),'absolute input identity')
        require(isinstance(expected,str) and len(expected)==64 and
                all(c in '0123456789abcdef' for c in expected),'input SHA format')
        key=str(path)
        require(key not in self.expected or self.expected[key]==expected,
                'conflicting input SHA: '+key)
        self.expected[key]=expected

    def consume(self,path):
        key=str(Path(path))
        require(key in self.expected and key not in self.checked,'unique declared input read: '+key)
        data=bounded(Path(key),4*1024*1024)
        require(sha(data)==self.expected[key],'input drift: '+key)
        self.checked[key]=self.expected[key]
        return data

    def document(self,path):
        key=str(Path(path))
        if key not in self.documents:
            self.documents[key]=strict_json(self.consume(path))
        return self.documents[key]

    def verify_all(self,validators):
        require(set(validators)<=set(self.expected),'semantic input not in frozen domain')
        for name in self.expected:
            if name in self.checked:
                require(name not in validators,'semantic input consumed before validation')
                continue
            raw=self.consume(Path(name))
            if name in validators:
                for validate in validators[name]:validate(raw)
        require(self.checked==self.expected,'complete unique input verification')


def pcm_bytes(raw,samples):
    require(len(raw)==samples*4,'PCM sample length')
    require(all(math.isfinite(v[0]) for v in struct.iter_unpack('<f',raw)),
            'nonfinite PCM')


def activity_bytes(raw,frames):
    require(len(raw)<=1024*1024,'activity file budget')
    rows=list(csv.DictReader(io.StringIO(raw.decode('ascii'))))
    require(len(rows)==frames,'gate count')
    for i,row in enumerate(rows):
        require(row['frame']==str(i) and row['far'] in ('0','1') and
                row['dt'] in ('0','1'),'gate identity')


def preflight():
    inputs=PreflightInputs()
    for p,h in BASE_SOURCE_PINS.items():
        inputs.add(p,h);inputs.consume(p)
    for name,h in D45_HASHES.items():inputs.add(D45/name,h)
    previous=inputs.document(D45/'result.json')
    binding=inputs.document(D45/'binding.json')
    require(len(binding['locked_files'])==9829 and len(binding['artifacts'])==1884,
            'complete frozen D45 domain')
    for name,h in binding['locked_files'].items():inputs.add(Path(name),h)
    for name,h in binding['artifacts'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,
                'relative frozen artifact identity')
        inputs.add(D45/name,h)
    require(len(inputs.expected)==11714,'D45 unique source/input/artifact union')
    require(previous['experiment']=='FE_DEVICE_POST_NS_PROTECTION_D45' and
            previous['executions']==184 and previous['frames']==505944 and
            previous['decision']=='DEVELOPMENT_REJECTED' and
            previous['data_role']=='development-and-synthetic-engineering' and
            previous['promotion_allowed'] is False and previous['shipping_approved'] is False,
            'preserved D45 rejection and role')
    for name,h in d42.HASHES.items():inputs.add(d42.BASE/name,h)
    original=inputs.document(d42.BASE/'result.json');cases=original['cases']
    require(original['data_role']=='development-and-synthetic-engineering' and
            len(cases)==46 and len({c['name'] for c in cases})==46,'D30 case set/data role')
    expected_names={mode+'-'+arm+'-'+c['name'] for c in cases
                    for arm in ('primary','selected') for mode in ('monitor','candidate')}
    require(len(previous['cases'])==184 and {r['name'] for r in previous['cases']}==expected_names,
            'D45 baseline case set')
    baseline=inputs.document(d42.D39/'result.json')
    require(baseline['executions']==92 and baseline['decision']=='DOWNSTREAM_INTEGRATION_DIAGNOSTIC_NO_PROMOTION' and
            baseline['data_role']=='development-and-synthetic-engineering' and
            baseline['promotion_allowed'] is False and baseline['shipping_approved'] is False,
            'D39 baseline role')
    require(len(baseline['cases'])==92 and {c['name'] for c in baseline['cases']}==
            {arm+'-'+c['name'] for c in cases for arm in ('primary','selected')},'D39 baseline case set')
    old=inputs.document(d42.D41/'result.json')
    require(old['experiment']=='FE_DEVICE_SPECTRAL_PROTECTION_D41' and
            old['decision']=='SPECTRAL_PROTECTION_DEVELOPMENT_REJECTED' and old['executions']==184 and
            old['data_role']=='development-and-synthetic-engineering' and
            old['promotion_allowed'] is False and old['shipping_approved'] is False,'D41 role/refusal')
    validators={}
    for case in cases:
        frames=case['execution_summary']['frames'];samples=frames*160
        require(type(frames) is int and 320<=samples<=1600000,'sample budget')
        require(case['execution_summary']['samples']==samples,'case frame/sample contract')
        directory=d42.BASE/case['name']
        validators.setdefault(str(directory/'activity.csv'),[]).append(lambda raw,f=frames:activity_bytes(raw,f))
        for name in ('echo','residual','primary_echo','primary_residual'):
            validators.setdefault(str(directory/(name+'.f32le')),[]).append(lambda raw,n=samples:pcm_bytes(raw,n))
        if case['kind']=='return' and not case['future']:
            near=Path(case['source_directory'])/'near.f32le'
            validators.setdefault(str(near),[]).append(lambda raw,n=samples:pcm_bytes(raw,n))
    pins={
    PLAN:'20906d11069584db58c5ba13855b6d1d36f798361fae690d5dab142b3b23cfc0',
    REVIEW:'ff344052a52f4c8717e0ac2cae1905dc37ec5be3f99dfe5336f48387300945b7',
    PLAN.with_name('DEVICE_CURRENT_INNOVATION_D47_AMENDMENT.zh-CN.md'):'0645bf01701fcdd6ef1f13aafbf8d8a60adc57620f0875b95c4cd7309a6f3f5b',
    Path('/tmp/audio-device-d46-review-snapshot-v1.json'):'74ad422a054e9ba245025b1b59dfecd9560bfb85893d29090f5934deb48b568b',
    PLAN.with_name('DEVICE_RELEASE_PATH_ATTRIBUTION_D46_CLOSEOUT.zh-CN.md'):'27ad3165311d15c9cf00a22bfa57e42b5104f3885caf341070f1af1cbe9a982a',
    Path('/tmp/audio-fe-device-release-path-attribution-d46-20261012/result.json'):'562057335c9e6b49aad19519a799da1f466b47d51f1248bec778600af043f94d',
    Path('/tmp/audio-fe-device-release-path-attribution-d46-20261012/binding.json'):'4feead7e4982576ee7cbb450179de87a26fb64618435064708d69946c536f22b',
    }
    pins[PLAN.with_name('DEVICE_CURRENT_INNOVATION_D47_AMENDMENT_PREFLIGHT.zh-CN.md')]='e7e9cf51211a24483dfba88637e457d91690685f8e0109df1c146fe894cbd8e8'
    for p,h in pins.items():inputs.add(p,h)
    for p in (C,NS,HEADER,TEST,Path(__file__).resolve()):
        raw=bounded(p,4*1024*1024);h=sha(raw)
        inputs.add(p,h);inputs.checked[str(p)]=h
    inputs.verify_all(validators)
    return cases,dict(inputs.expected)

def run(output):
    require(output.is_absolute() and output==Path('/tmp/audio-fe-device-current-innovation-d47-20261013') and
        not output.exists() and not any(p.is_symlink() for p in (output,)+tuple(output.parents)) and
        output.absolute()==output.resolve(),'fixed new direct /tmp root required')
    cases,locks=preflight()
    require(shutil.disk_usage('/tmp').free>=3*1024**3,'startup disk budget')
    previous={r['name']:r for r in read_json(D45/'result.json')['cases']}
    require(len(previous)==184,'D45 execution set')
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
                    require(original_summary=={k:v for k,v in previous[name]['execution_summary'].items() if k not in ('observer_state_bytes','measurement_scoped_bytes')},'D45 algorithm resource/call identity')
                    require(type(summary['observer_state_bytes']) is int and summary['observer_state_bytes']>0 and
                        summary['measurement_scoped_bytes']==summary['scoped_bytes']+summary['observer_state_bytes'] and
                        summary['measurement_scoped_bytes']<=65536 and summary['measurement_scoped_bytes']+71224<=131072,'measurement resource budget')
                    baseline_outputs(directory,D45/name,mode)
                    observation=d42.observe(directory,case,arm,original_summary,mode)
                    if mode=='monitor':require(observation==previous[name]['observation'],'monitor frozen measurement identity')
                    diagnostic=trace(directory,frames,mode,gates)
                    baseline_trace(diagnostic,d45.trace(D45/('monitor-'+arm+'-'+case['name']),frames,'monitor',gates));pair.append(diagnostic)
                    completed.append(dict(name=name,source_case=case['name'],kind=case['kind'],future=case['future'],arm=arm,mode=mode,
                        execution_summary=summary,observation=observation,
                        diagnostic=dict(snapshot_frames=diagnostic['snapshot_frames'],bin_rows=diagnostic['bin_rows'],power_rows=len(diagnostic['power']))))
                    size_budget(output);d42.matrix_budget(matrix_started)
                    print('D47_CASE_PASS '+name,flush=True)
                paired_traces(*pair)
                paired_controls(output/('monitor-'+arm+'-'+case['name']),output/('candidate-'+arm+'-'+case['name']))
        repeat_future(output)
        require(len(completed)==184 and sum(r['execution_summary']['frames'] for r in completed)==505944,'matrix coverage')
        require(all(sha(bounded(Path(p),4*1024*1024))==h for p,h in locks.items()),'source/input end drift')
        size_budget(output);d42.matrix_budget(matrix_started)
        admission=d42.development_admission(completed,cases)
        decision='DEVELOPMENT_CANDIDATE_ONLY' if admission['accepted'] else 'DEVELOPMENT_REJECTED'
        dump(output/'result.json',dict(experiment='FE_DEVICE_CURRENT_INNOVATION_D47',executions=184,frames=505944,
            data_role='development-and-synthetic-engineering',decision=decision,measurement_only=False,
            promotion_allowed=False,shipping_approved=False,baseline_hashes=D45_HASHES,
            development_admission=admission,frequency_enabled=1,integration_changed=True,shipping_algorithm_changed=False,
            cases=completed,matrix_elapsed_seconds=time.monotonic()-matrix_started))
        dump(output/'binding.json',dict(locked_files=locks,baseline_hashes=D45_HASHES,source_input_start_end_equal=True,
            runner_sha256=sha((output/'runner').read_bytes()),artifacts={str(p.relative_to(output)):sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
        size_budget(output)
        print('D47_MEASUREMENT_PASS 184 '+decision+' NO_PROMOTION',flush=True)
    except Exception as error:
        dump(output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID_REPLAN',error=str(error),completed_executions=len(completed)))
        raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Read-only frozen preflight; no DSP')
    mode.add_argument('--run',action='store_true',help='Explicit reviewed formal execution')
    parser.add_argument('--output-root',type=Path,help='New /tmp root after independent review')
    args=parser.parse_args()
    if args.run:
        require(args.output_root is not None,'output root required')
        run(args.output_root);return 0
    require(args.output_root is None,'output root requires explicit --run')
    cases,locks=preflight()
    print(json.dumps(dict(experiment='FE_DEVICE_CURRENT_INNOVATION_D47',cases=len(cases),
        locked_files=len(locks),writes=False,dsp_executed=False,promotion_allowed=False,
        shipping_approved=False,formal_matrix_implemented=True)))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,UnicodeError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(2)
