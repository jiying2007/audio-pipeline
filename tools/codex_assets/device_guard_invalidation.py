"""D33 one frozen causal guard candidate; no shipping authority."""
from __future__ import annotations
import argparse
import csv
import io
import math
from pathlib import Path
import sys
import subprocess
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_causal_guard import preflight as old_preflight
from tools.codex_assets.device_activity import activity_step, frame_energy, f32, ACT_FIELDS, STATE_FIELDS
from tools.codex_assets.device_online import input_info, TRACES, LIB_SHA
from tools.codex_assets.device_capture import ROOT, bounded, require, sha, strict_json
from tools.codex_assets.device_exact_reference import dump, logged, read_json
from tools.codex_assets.device_stages import D18, floats
from tools.codex_assets.device_dwell import recurrence, score, FIELDS as SELECT_FIELDS
from tools.codex_assets.device_transition import mix, FIELDS as TRANS_FIELDS
from tools.codex_assets.device_path import encoded
from tools.codex_assets.device_replay import FLAGS

BASE = Path('/tmp/audio-fe-device-activity-d30-20261011')
OBSERVATION = Path('/tmp/audio-fe-device-observability-d31-attempt1-20261011')
HASHES = {'result.json': 'e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d',
          'binding.json': '2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956'}
OBS_HASHES = {'result.json': 'd1465d24fb2b26d378dd2e6590c661f2a67d5e23ca1255ab7f6bd5970961aee2',
              'binding.json': '04990be63adfb174d37f6483fa6e1d3e0679276ee6581577eba59baf30cdc506'}
PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_GUARD_INVALIDATION_D33_PLAN.zh-CN.md'
D32 = Path('/tmp/audio-fe-device-causal-guard-d32-20261011')
D32_HASHES = {'result.json': 'a9e8d6f1120c420361d10daae103f207679638439da4ff65d01fa621af8b477a', 'binding.json': 'd6a49352c331734bd4015b2c2e56ba3fa0a1f4c36a957b968566ae0d03ce80fe'}
C = ROOT / 'tests/validation/frontend_evolution/device_guard_invalidation_d33.c'
HEADER = C.with_suffix('.h')
TEST = C.parent / 'test_device_guard_invalidation.py'
OUTPUTS = tuple(k + '.f32le' for k in TRACES) + ('state.csv', 'selector.csv', 'transition.csv', 'activity.csv', 'guard.csv')
GUARD_FIELDS = ['frame', 'mode', 'detected_dt', 'guard', 'used_dt', 'armed_before', 'stable_before', 'hold_after_gate',
                'cme', 'cre', 'ratio', 'valid_me', 'valid_re', 'armed_after', 'stable_after']


def preflight(root):
    sources = old_preflight(root)
    for directory, hashes in ((BASE, HASHES), (OBSERVATION, OBS_HASHES), (D32, D32_HASHES)):
        for name, expected in hashes.items():
            require(sha(bounded(directory / name, 4 * 1024 * 1024)) == expected, 'baseline identity')
        b = read_json(directory / 'binding.json')
        for group in ('source_files', 'input_files', 'artifacts'):
            for name, expected in b[group].items():
                require(sha(bounded(directory / name if group == 'artifacts' else Path(name), 4 * 1024 * 1024)) == expected, 'baseline drift')
    actual = read_json(BASE / 'result.json')['cases']
    for s in sources:
        s['actual'] = next(c for c in actual if c['name'] == s['kind'] + '-' + s['case']['name'])
    previous = read_json(D32 / 'result.json')['cases']
    for s in sources:
        s['d32'] = {mode: next(c for c in previous if c['name'] == mode + '-' + s['actual']['name']) for mode in ('monitor', 'feedback')}
    return sources


def invalidate(state, mode, notified):
    return initial_guard() if mode == 'feedback' and notified else dict(state)


def initial_guard():
    return dict(cme=0., cre=0., ratio=0., valid_me=0, valid_re=0, stable=0, armed=0, hold=0)


def gate(state, far):
    s = dict(state)
    if not far:
        return initial_guard(), 0
    onset = s['armed'] and s['valid_me'] and s['valid_re'] and .2 < s['cme'] < .9 and s['cre'] < .1 and s['ratio'] > .2
    s['hold'] = 3 if onset else max(0, s['hold'] - 1)
    return s, int(s['hold'] > 0)


def observe_guard(state, mic, echo, residual, far, detected_dt):
    require(all(len(v) == 160 and all(math.isfinite(x) for x in v) for v in (mic, echo, residual)), 'guard finite frame')
    mm, ee, rr = [sum(x * x for x in v) for v in (mic, echo, residual)]
    me = sum(x * y for x, y in zip(mic, echo)); re = sum(x * y for x, y in zip(residual, echo))
    s = dict(state); s['valid_me'] = int(mm > 0 and ee > 0); s['valid_re'] = int(rr > 0 and ee > 0)
    s['cme'] = me * me / (mm * ee) if s['valid_me'] else -1.
    s['cre'] = re * re / (rr * ee) if s['valid_re'] else -1.
    s['ratio'] = rr / mm if mm else -1.
    require(all(math.isfinite(s[k]) for k in ('cme', 'cre', 'ratio')) and s['cme'] <= 1 + 1e-12 and s['cre'] <= 1 + 1e-12, 'guard metrics')
    s['stable'] = min(100, s['stable'] + 1) if far and not detected_dt and s['valid_me'] and s['cme'] > .95 and 0 <= s['ratio'] < .05 else 0
    if s['stable'] == 100:
        s['armed'] = 1
    return s


def runner_command(runner, source, directory, future, mode):
    _, mic, ref, _, n, notify = input_info(source)
    return [str(runner), str(mic), str(ref), str(n // 160), 'none' if notify is None else str(notify), str(directory), 'future' if future else 'normal', mode]
def observe(directory,source,future,execution,mode):
    original,mic_path,ref_path,old_gates,n,notify=input_info(source)
    values={k:floats(directory/(k+'.f32le'),n) for k in TRACES}
    for k,p in [('mic',mic_path),('reference',ref_path)]:
        expected=floats(p,n)
        if future:expected=[-v if i>=notify*160 else v for i,v in enumerate(expected)]
        require((directory/(k+'.f32le')).read_bytes()==encoded(expected),'actual inputs '+k)
    tables=[]
    for name,fields in [('activity.csv',ACT_FIELDS),('selector.csv',SELECT_FIELDS),('transition.csv',TRANS_FIELDS),('state.csv',STATE_FIELDS)]:
        reader=csv.DictReader(io.StringIO(bounded(directory/name,1024*1024).decode('ascii')))
        require(reader.fieldnames==fields,'CSV schema');rows=list(reader)
        require(len(rows)==n//160 and all(all(math.isfinite(float(v)) for v in r.values()) for r in rows),'CSV finite/count');tables.append(rows)
    activity,selectors,transitions,states=tables
    require(all(r['frame']==str(i) and int(r['runtime_stride'])==2 and int(r['adapt_phase']) in (0,1) and
        float(r['x_power_total'])>=0 and float(r['weight_l2'])>=0 for i,r in enumerate(states)),'primary diagnostic CSV')
    reader=csv.DictReader(io.StringIO(bounded(directory/'guard.csv',1024*1024).decode('ascii')))
    require(reader.fieldnames==GUARD_FIELDS,'guard schema');guard_rows=list(reader);require(len(guard_rows)==n//160,'guard count')
    guard_state=initial_guard();guard_flags=[];used_flags=[]
    state=(0.0,0.0,0,0);gates=[];disagreement={'far':0,'dt':0,'either':0}
    for frame,row in enumerate(activity):
        a,b=frame*160,(frame+1)*160;me,re=frame_energy(values['mic'][a:b]),frame_energy(values['reference'][a:b]);state,flag=activity_step(state,me,re)
        require(row['frame']==str(frame) and [f32(float(row[k])) for k in ACT_FIELDS[1:5]]==[me,re,state[0],state[1]] and
            [int(row[k]) for k in ACT_FIELDS[5:]]==[state[2],state[3],*flag],'actual Activity recurrence')
        guard_state=invalidate(guard_state,mode,notify is not None and frame==notify)
        before=dict(guard_state);guard_state,guard_flag=gate(guard_state,flag[0]);hold=guard_state['hold']
        used=int(flag[1] or (mode=='feedback' and guard_flag));guard_flags.append(guard_flag);used_flags.append(used)
        guard_state=observe_guard(guard_state,values['mic'][a:b],values['primary_echo'][a:b],values['primary_residual'][a:b],flag[0],flag[1])
        gr=guard_rows[frame];expected=dict(frame=frame,mode=int(mode=='feedback'),detected_dt=flag[1],guard=guard_flag,used_dt=used,
            armed_before=before['armed'],stable_before=before['stable'],hold_after_gate=hold,cme=guard_state['cme'],cre=guard_state['cre'],ratio=guard_state['ratio'],
            valid_me=guard_state['valid_me'],valid_re=guard_state['valid_re'],armed_after=guard_state['armed'],stable_after=guard_state['stable'])
        require(all(float(gr[k])==v if k not in ('cme','cre','ratio') else abs(float(gr[k])-v)<=1e-12 for k,v in expected.items()),'actual guard recurrence')
        gates.extend((flag[0],used));old=old_gates[2*frame:2*frame+2]
        disagreement['far']+=flag[0]!=old[0];disagreement['dt']+=flag[1]!=old[1];disagreement['either']+=tuple(old)!=flag
    bank=streak=from_bank=pos=remaining=mixed=0;last_switch=None;expected={k:[] for k in ('echo','residual')};events=[]
    for frame,(sel,tr) in enumerate(zip(selectors,transitions)):
        a,b=frame*160,(frame+1)*160;far,dt=gates[2*frame:2*frame+2];active=int(notify is not None and frame>=notify);before=bank
        pe=sum(v*v for v in values['primary_residual'][a:b]);se=sum(v*v for v in values['shadow_residual'][a:b])
        bank,streak,last_switch,change,hold=recurrence(bank,streak,last_switch,frame,50,active,far and not dt,pe,se)
        require([sel[k] for k in SELECT_FIELDS[:7]]==[str(frame),str(active),str(far),str(dt),str(bank),str(streak),str(change)] and
            float(sel['primary_energy'])==pe and float(sel['shadow_energy'])==se and int(sel['hold_remaining'])==hold,'actual selection')
        if not active:from_bank=pos=remaining=0
        elif change:
            require(not remaining,'transition overlap');from_bank=before;pos=0;remaining=320;events.append(dict(frame=frame,from_bank=before,to_bank=bank))
        first=last=1.0
        for i in range(a,b):
            alpha=pos/319.0 if remaining else 1.0
            if i==a:first=alpha
            last=alpha
            for k in expected:
                old=values[('shadow_' if from_bank else 'primary_')+k][i];new=values[('shadow_' if bank else 'primary_')+k][i]
                expected[k].append(mix(old,new,pos) if remaining else new)
            if remaining:pos+=1;remaining-=1;mixed+=1
        require([tr[k] for k in TRANS_FIELDS[:6]]==[str(frame),str(active),str(far),str(dt),str(bank),str(change)] and
            int(tr['remaining_after_frame'])==remaining and float(tr['alpha_first'])==first and float(tr['alpha_last'])==last,'actual transition')
    for k in expected:require((directory/(k+'.f32le')).read_bytes()==encoded(expected[k]),'actual exact mix')
    algebra={}
    for label in ('selected','primary','shadow'):
        first=notify*160 if label=='shadow' and notify is not None else n if label=='shadow' else 0
        if first==n:continue
        prefix='' if label=='selected' else label+'_'
        algebra[label]=max(abs(values[prefix+'echo'][i]+values[prefix+'residual'][i]-values['mic'][i]) for i in range(first,n));require(algebra[label]<=1e-6,'mic algebra')
    fixed=dict(frames=n//160,samples=n,primary_calls=n//160,shadow_calls=n//160-notify if notify is not None else 0,shadow_reset_calls=int(notify is not None),
        selector_calls=n//160,transition_calls=n//160,mixed_samples=mixed,remaining=remaining,switch_count=len(events),sync_calls=0,aec_state_bytes=33020,two_aec_state_bytes=66040,
        selector_state_bytes=20,transition_state_bytes=16,frame_buffer_bytes=5120,scoped_bytes=71264,activity_calls=n//160,activity_state_bytes=28,observer_calls=n//160,guard_state_bytes=40)
    require(all(type(v) is int for v in execution.values()) and execution==fixed and fixed['scoped_bytes']<=131072,'actual counts/resources')
    baseline=BASE/('future' if future else source['actual']['name']);equivalence={p:(directory/p).read_bytes()==bounded(baseline/p,4*1024*1024) for p in OUTPUTS[:-1]}
    if mode=='monitor':require(all(equivalence.values()),'monitor original12 byte equality')
    else:require(all(equivalence[k] for k in ('mic.f32le','reference.f32le','activity.csv')),'feedback actual input/Activity equality')
    d32_directory=D32/(mode+'-future' if future else mode+'-'+source['actual']['name'])
    d32_equivalence={p:(directory/p).read_bytes()==bounded(d32_directory/p,4*1024*1024) for p in OUTPUTS}
    if mode=='monitor' or notify is None:
        require(all(d32_equivalence.values()),'D32 all13 exact control')
    else:
        for p in OUTPUTS:
            a=(directory/p).read_bytes();b=bounded(d32_directory/p,4*1024*1024)
            require(a[:notify*160*4]==b[:notify*160*4] if p.endswith('.f32le') else a.splitlines()[:notify+1]==b.splitlines()[:notify+1],'D32 pre-notify all13')
    measurement=None;deltas=[];d32_deltas=[]
    if not future:
        if source['kind']=='return':
            for k in ('near','true_echo'):values[k]=floats(original/(k+'.f32le'),n)
        measurement=score(source,values);previous=source['actual']['observation']['measurement']
        for old,new in zip([previous['whole'],*previous['windows']],[measurement['whole'],*measurement['windows']]):
            require(old['sample_range']==new['sample_range'] and {k:v is None for k,v in old['channels'].items()}=={k:v is None for k,v in new['channels'].items()},'old ranges/null')
            d=dict(sample_range=old['sample_range'],selected_residual_rms_db_delta=new['channels']['selected']['residual']['rms_dbfs']-old['channels']['selected']['residual']['rms_dbfs'])
            if source['kind']=='return':d['selected_error_rms_db_delta']=new['channels']['selected']['error']['rms_dbfs']-old['channels']['selected']['error']['rms_dbfs']
            deltas.append(d)
        if mode=='monitor':require(measurement==previous,'monitor original score equality')
        previous32=source['d32'][mode]['observation']['measurement']
        for old,new in zip([previous32['whole'],*previous32['windows']],[measurement['whole'],*measurement['windows']]):
            require(old['sample_range']==new['sample_range'],'D32 unchanged score ranges')
            d=dict(sample_range=old['sample_range'],selected_residual_rms_db_delta=new['channels']['selected']['residual']['rms_dbfs']-old['channels']['selected']['residual']['rms_dbfs'])
            if source['kind']=='return':d['selected_error_rms_db_delta']=new['channels']['selected']['error']['rms_dbfs']-old['channels']['selected']['error']['rms_dbfs']
            d32_deltas.append(d)
    truth=None
    if source['kind']=='return' and not future:
        truth=[int(any(x!=0 for x in values['near'][f*160:(f+1)*160])) for f in range(n//160)]
    protection=None
    if truth is not None:
        intervals=[] 
        for f,present in enumerate(truth):
            if present:
                if intervals and intervals[-1][1]==f:intervals[-1][1]=f+1
                else:intervals.append([f,f+1])
        require(intervals==([[1000,1200],[1600,1800]] if any(truth) else []),'known near intervals')
        protection=dict(near_intervals=[dict(frame_range=[a,b],used_dt_frames=sum(used_flags[a:b]),first_used_dt_delay=next((i for i,v in enumerate(used_flags[a:b]) if v),None)) for a,b in intervals],
            echo_guard_frames_800_2000=sum(guard_flags[800:2000]) if not intervals else None)
    return dict(d32_file_equivalence=d32_equivalence,d32_deltas=d32_deltas,protection=protection,guard_frames=sum(guard_flags),used_dt_frames=sum(used_flags),events=events,measurement=measurement,algebra_max_abs_error=algebra,external_gate_disagreement=disagreement,baseline_file_equivalence=equivalence,deltas=deltas)


def candidate_checks(cases):
    main = [c for c in cases if c['mode'] == 'feedback' and c['source_label'] is None]
    near = [c for c in main if c['kind'] == 'return' and c['observation']['protection']['near_intervals']]
    echo = [c for c in main if c['kind'] == 'return' and not c['observation']['protection']['near_intervals']]
    field = [c for c in main if c['kind'] == 'field']
    require((len(near), len(echo), len(field)) == (8, 4, 32), 'candidate role counts')
    conditions = dict(
        near_coverage=all(w['used_dt_frames'] >= 180 for c in near for w in c['observation']['protection']['near_intervals']),
        static_near_onset=all(w['first_used_dt_delay'] is not None and w['first_used_dt_delay'] <= 2 for c in near if c['source_case'].startswith('A-') for w in c['observation']['protection']['near_intervals']),
        echo_no_false_guard=all(c['observation']['protection']['echo_guard_frames_800_2000'] == 0 for c in echo),
        original_return_error=all(d['selected_error_rms_db_delta'] <= .5 for c in near + echo for d in c['observation']['deltas']),
        field_switch_count=all(c['execution_summary']['switch_count'] <= c['baseline_switch_count'] for c in field))
    return dict(conditions=conditions, accepted=all(conditions.values()), role_counts=dict(near=8, echo=4, field=32),
                scope='frozen development engineering only; not independent acoustic or shipping authority')


def run(root, output, created):
    sources = preflight(root)
    require(output.is_absolute() and output == output.resolve() and output.parent == Path('/tmp') and not output.exists(), 'fresh direct /tmp output')
    own = [Path(__file__).resolve(), PLAN, C, HEADER, TEST, ROOT / 'tools/codex_assets/device_activity.py',
           ROOT / 'tools/codex_assets/device_dwell.py', ROOT / 'tools/codex_assets/device_transition.py',
           D18 / 'build/CMakeFiles/audio_pipeline.dir/flags.make', D18 / 'build/libaudio_pipeline.a']
    own.extend(C.parent / name for name in ('device_field_d26.c', 'device_dwell_selector_d27.h', 'device_shadow_selector_d24.h', 'device_transition_d28.h'))
    initial = {str(p): sha(bounded(p, 4 * 1024 * 1024)) for p in own}; inputs = {}
    for s in sources:
        original, mic, ref, _, _, _ = input_info(s)
        paths = [mic, ref, original / ('gates.bin' if s['kind'] == 'field' else 'selector.csv')]
        if s['kind'] == 'return':
            paths.extend(original / (k + '.f32le') for k in ('near', 'true_echo'))
        for p in paths:
            inputs[str(p)] = sha(bounded(p, 4 * 1024 * 1024))
    output.mkdir(); created.append(output)
    flags = (D18 / 'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
    definitions = [line.split('=', 1)[1].split() for line in flags.splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions) == 1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]), 'definitions')
    logged(output, 'compile', ['cc', *FLAGS, '-ffp-contract=off', *definitions[0], '-I', str(D18 / 'source/src'), '-I', str(D18 / 'source/include'),
           '-I', str(D18 / 'build/generated'), str(C), str(D18 / 'build/libaudio_pipeline.a'), '-lm', '-lpthread', '-o', str(output / 'runner')], ROOT)
    runner_sha = sha((output / 'runner').read_bytes())
    logged(output, 'self-test', [str(output / 'runner'), '--self-test'], ROOT)
    logged(output, 'argc-invalid', [str(output / 'runner'), 'invalid'], ROOT, expected=2)
    for label, frames, notify, future, mode in [('frames', 'bad', 'none', 'normal', 'monitor'), ('notify', '1', '1', 'normal', 'monitor'),
          ('future', '1', 'none', 'future', 'monitor'), ('mode', '1', 'none', 'bad', 'monitor'), ('feedback', '1', 'none', 'normal', 'bad')]:
        directory = output / ('invalid-preserve-' + label); directory.mkdir()
        sentinels = {p: b'D33_SENTINEL ' + p.encode() for p in OUTPUTS}
        for name, data in sentinels.items():
            (directory / name).write_bytes(data)
        logged(output, 'invalid-preserve-' + label, [str(output / 'runner'), 'missing', 'missing', frames, notify, str(directory), future, mode], ROOT, expected=2)
        require({p.name: p.read_bytes() for p in directory.iterdir()} == sentinels, 'invalid output preservation')
        require(read_json(output / ('command-invalid-preserve-' + label + '.json'))['stderr'] ==
                'D33_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0 activity_calls=0 observer_calls=0\n', 'invalid zero calls')
    anchor = next(s for s in sources if s['kind'] == 'field' and s['case']['name'] == 'case-07-used0-shadow')
    jobs = [(s, False, None) for s in sources] + [(anchor, False, 'repeat'), (anchor, True, 'future')]; cases = []
    for mode in ('monitor', 'feedback'):
        for s, future, label in jobs:
            original, _, _, _, _, notify = input_info(s)
            name = mode + '-' + (label or s['kind'] + '-' + s['case']['name']); directory = output / name; directory.mkdir()
            execution = strict_json(logged(output, name, runner_command(output / 'runner', s, directory, future, mode), ROOT).encode())
            observation = observe(directory, s, future, execution, mode)
            cases.append(dict(name=name, mode=mode, kind=s['kind'], source_case=s['case']['name'], source_label=label,
                              source_directory=str(original), future=future, notify_frame=notify, execution_summary=execution, observation=observation,
                              baseline_switch_count=s['actual']['execution_summary']['switch_count']))
            print('D33_CASE_PASS', name, flush=True)
        normal = output / (mode + '-field-case-07-used0-shadow'); notify = anchor['case']['notify_frame']
        for p in OUTPUTS:
            a = (normal / p).read_bytes(); b = (output / (mode + '-future') / p).read_bytes()
            require(a == (output / (mode + '-repeat') / p).read_bytes(), 'repeat all13')
            require(a[:notify * 160 * 4] == b[:notify * 160 * 4] if p.endswith('.f32le') else a.splitlines()[:notify + 1] == b.splitlines()[:notify + 1], 'future all13 prefixes')
    preflight(root)
    require(initial == {p: sha(bounded(Path(p), 4 * 1024 * 1024)) for p in initial} and
            inputs == {p: sha(bounded(Path(p), 4 * 1024 * 1024)) for p in inputs} and sha((output / 'runner').read_bytes()) == runner_sha, 'source/input/runner drift')
    acceptance = candidate_checks(cases)
    dump(output / 'result.json', dict(experiment='FE_DEVICE_GUARD_INVALIDATION_D33', executions=92, frames=252972,
         data_role='disclosed-development-and-synthetic-engineering', research_algorithm_changed=True, shipping_algorithm_changed=False,
         decision='GUARD_INVALIDATION_DEVELOPMENT_CANDIDATE_ONLY' if acceptance['accepted'] else 'GUARD_INVALIDATION_DEVELOPMENT_REJECTED',
         promotion_allowed=False, shipping_approved=False, cases=cases, acceptance=acceptance,
         resource_budget=dict(scoped_bytes=71264, guard_state_bytes=40, budget_bytes=131072, b0_arena_bytes=50000, b0_changed=False, target_resource_qualified=False)))
    dump(output / 'binding.json', dict(source_files=initial, input_files=inputs, d32_hashes=D32_HASHES, baseline_hashes=HASHES, observation_hashes=OBS_HASHES,
         library_sha256=LIB_SHA, runner_sha256=runner_sha, source_start_end_equal=True, input_start_end_equal=True,
         artifacts={str(p.relative_to(output)): sha(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}))
    print('D33_MEASUREMENT_PASS', 'CANDIDATE_ONLY' if acceptance['accepted'] else 'CANDIDATE_REJECTED', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True); parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv); created = []
    try:
        if args.dry_run:
            print('D33_PREFLIGHT_PASS', len(preflight(args.root)), 'sources; writes=False')
        else:
            run(args.root, args.output, created)
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, subprocess.TimeoutExpired) as error:
        if created == [args.output]:
            dump(args.output / 'measurement-invalid.json', dict(decision='MEASUREMENT_INVALID', error=str(error)))
        print('device_guard_invalidation:', error, file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())

