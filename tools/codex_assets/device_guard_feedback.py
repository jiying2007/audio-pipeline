"""D34 frozen three-arm guard diagnostic; never a candidate or DSP runner."""
from __future__ import annotations
import argparse
import array
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_GUARD_FEEDBACK_D34_PLAN.zh-CN.md'
TEST = ROOT / 'tests/validation/frontend_evolution/test_device_guard_feedback.py'
AMEND = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_GUARD_FEEDBACK_D34_AMENDMENT.zh-CN.md'
BASES = {
    'd30': (Path('/tmp/audio-fe-device-activity-d30-20261011'), 'e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d', '2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956'),
    'd32': (Path('/tmp/audio-fe-device-causal-guard-d32-20261011'), 'a9e8d6f1120c420361d10daae103f207679638439da4ff65d01fa621af8b477a', 'd6a49352c331734bd4015b2c2e56ba3fa0a1f4c36a957b968566ae0d03ce80fe'),
    'd33': (Path('/tmp/audio-fe-device-guard-invalidation-d33-20261011'), '09cc3b8156436c033adf353d03a9db5079a660c14ab89a574b8238f84596af72', 'fe9d21710ed6a2ca35ed9b7b7eba8579ea64d46d57ed8cf4012cda4d3cb0cf79'),
}
ARMS = ('d32_monitor', 'd32_feedback', 'd33_feedback')
FIELDS = ('frame', 'mode', 'detected_dt', 'guard', 'used_dt', 'armed_before', 'stable_before', 'hold_after_gate', 'cme', 'cre', 'ratio', 'valid_me', 'valid_re', 'armed_after', 'stable_after')
FLOAT_FIELDS = ('cme', 'cre', 'ratio')
OUTPUT_FIELDS = tuple(k for k in FIELDS if k not in ('frame', 'mode')) + ('potential_dt',)
REVIEW = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_GUARD_INVALIDATION_D33_REVIEW.zh-CN.md'
REVIEW_SHA = 'edb6bd437e5c850f7f61824da2a91231e94704d9d5bb2a6170270ca11d3c9536'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON ' + value)
    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def intervals(flags):
    result = []
    for i, flag in enumerate(flags):
        require(flag in (0, 1), 'binary intervals')
        if flag:
            if result and result[-1][1] == i:
                result[-1][1] = i + 1
            else:
                result.append([i, i + 1])
    return result


def summary(flags, start=0, end=None):
    if end is None:
        end = len(flags)
    require(0 <= start <= end <= len(flags), 'summary range')
    runs = [[a + start, b + start] for a, b in intervals(flags[start:end])]
    return dict(frame_range=[start, end], count=sum(b - a for a, b in runs),
                first_delay=runs[0][0] - start if runs else None, intervals=runs,
                longest_run=max((b - a for a, b in runs), default=0))


def parsed_rows(path, frames):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == list(FIELDS), 'guard schema')
        rows = []
        for i, row in enumerate(reader):
            require(set(row) == set(FIELDS) and None not in row.values(), 'guard row shape')
            value = {k: float(row[k]) if k in FLOAT_FIELDS else int(row[k]) for k in FIELDS}
            require(value['frame'] == i and all(math.isfinite(v) for v in value.values()), 'guard frame/finite')
            for key in ('mode', 'detected_dt', 'guard', 'used_dt', 'armed_before', 'valid_me', 'valid_re', 'armed_after'):
                require(value[key] in (0, 1), 'guard binary')
            require(0 <= value['stable_before'] <= 100 and 0 <= value['stable_after'] <= 100 and 0 <= value['hold_after_gate'] <= 3, 'guard counters')
            rows.append(value)
    require(len(rows) == frames, 'guard frame count')
    return rows


def activity(path, frames):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == frames and all(r['frame'] == str(i) for i, r in enumerate(rows)), 'Activity frame count')
    flags = [(int(r['far']), int(r['dt'])) for r in rows]
    require(all(a in (0, 1) and b in (0, 1) for a, b in flags), 'Activity binary')
    return flags


def recurrence(rows, flags, feedback, notify, invalidate):
    state = dict(cme=0., cre=0., ratio=0., valid_me=0, valid_re=0, stable=0, armed=0, hold=0)
    for frame, (row, (far, dt)) in enumerate(zip(rows, flags)):
        if invalidate and frame == notify:
            state = dict(cme=0., cre=0., ratio=0., valid_me=0, valid_re=0, stable=0, armed=0, hold=0)
        require(row['mode'] == int(feedback) and row['detected_dt'] == dt and row['armed_before'] == state['armed'] and row['stable_before'] == state['stable'], 'guard before state')
        if not far:
            state = dict(cme=0., cre=0., ratio=0., valid_me=0, valid_re=0, stable=0, armed=0, hold=0)
        onset = far and state['armed'] and state['valid_me'] and state['valid_re'] and .2 < state['cme'] < .9 and state['cre'] < .1 and state['ratio'] > .2
        state['hold'] = 3 if onset else max(0, state['hold'] - 1)
        guard = int(state['hold'] > 0)
        require(row['guard'] == guard and row['hold_after_gate'] == state['hold'] and row['used_dt'] == int(dt or (feedback and guard)), 'guard gate/actual usage')
        for key in FLOAT_FIELDS + ('valid_me', 'valid_re'):
            state[key] = row[key]
        require((-1. <= row['cme'] <= 1. + 1e-12) and (-1. <= row['cre'] <= 1. + 1e-12) and row['ratio'] >= -1., 'feature bounds')
        require((row['valid_me'] or row['cme'] == -1.) and (row['valid_re'] or row['cre'] == -1.), 'invalid sentinel')
        stable = far and not dt and state['valid_me'] and state['cme'] > .95 and 0 <= state['ratio'] < .05
        state['stable'] = min(100, state['stable'] + 1) if stable else 0
        if state['stable'] == 100:
            state['armed'] = 1
        require(row['stable_after'] == state['stable'] and row['armed_after'] == state['armed'], 'guard observer recurrence')
        row['potential_dt'] = int(dt or guard)


def near_truth(path, frames):
    require(path.stat().st_size == frames * 640, 'near trace length')
    values = array.array('f')
    require(values.itemsize == 4, 'Float32 array')
    values.frombytes(path.read_bytes())
    if sys.byteorder != 'little':
        values.byteswap()
    require(all(math.isfinite(v) for v in values), 'near finite')
    return [int(any(v != 0. for v in values[i:i + 160])) for i in range(0, len(values), 160)]


def arm_summary(rows, windows, near):
    masks = {k: [r[k] for r in rows] for k in ('guard', 'used_dt', 'potential_dt')}
    def counts(a, b):
        return {k: summary(v, a, b) for k, v in masks.items()}
    result = dict(whole=counts(0, len(rows)), near_intervals=None, original_windows=[])
    if near is not None:
        runs = intervals(near)
        require(runs in ([], [[1000, 1200], [1600, 1800]]), 'known near intervals')
        result['near_intervals'] = [dict(frame_range=[a, b], counts=counts(a, b)) for a, b in runs]
        result['trigger_800_2000'] = counts(800, 2000)
        result['pure_echo_false_guard'] = summary(masks['guard'], 800, 2000) if not runs else None
    for window in windows:
        a, b = window['sample_range']
        start, end = (a + 159) // 160, b // 160
        require(0 <= start <= end <= len(rows), 'original window bounds')
        result['original_windows'].append(dict(sample_range=[a, b], complete_frame_range=[start, end], discarded_boundary_samples=b - a - (end - start) * 160, counts=counts(start, end)))
    return result


def differences(a, b):
    require(len(a) == len(b), 'paired length')
    return {k: summary([int(x[k] != y[k]) for x, y in zip(a, b)]) for k in OUTPUT_FIELDS}


def case_mapping(members, mode):
    prefix = mode + '-'
    require(all(c['name'].startswith(prefix) for c in members), 'case mode prefix')
    mapping = {c['name'][len(prefix):]: c for c in members}
    require(len(mapping) == len(members), 'duplicate case name')
    return mapping


def preflight(output):
    require(output.is_absolute() and output == output.resolve() and output.parent == Path('/tmp') and not output.exists(), 'fresh direct /tmp output required')
    locked = {}
    results = {}
    for label, (base, result_sha, binding_sha) in BASES.items():
        for name, expected in (('result.json', result_sha), ('binding.json', binding_sha)):
            p = base / name
            require(sha(p) == expected, 'base identity ' + label + '/' + name)
            locked[str(p)] = expected
        binding = read_json(base / 'binding.json')
        for group in ('source_files', 'input_files', 'artifacts'):
            for name, expected in binding[group].items():
                p = base / name if group == 'artifacts' else Path(name)
                require(p.is_file() and sha(p) == expected, 'dependency drift ' + str(p))
                require(str(p) not in locked or locked[str(p)] == expected, 'conflicting dependency')
                locked[str(p)] = expected
        results[label] = read_json(base / 'result.json')
    require(sha(REVIEW) == REVIEW_SHA, 'D33 reviewed identity')
    locked[str(REVIEW)] = REVIEW_SHA
    cases = results['d30']['cases']
    require(len(cases) == 46 and len({c['name'] for c in cases}) == 46 and sum(c['execution_summary']['frames'] for c in cases) == 126486, 'D30 exact cases/frames')
    index = {}
    for arm in ARMS:
        base_label, mode = arm.split('_')
        members = [c for c in results[base_label]['cases'] if c['mode'] == mode]
        mapping = case_mapping(members, mode)
        require(len(members) == len(mapping) == 46 and set(mapping) == {c['name'] for c in cases}, 'exact paired case set')
        index[arm] = mapping
    require(sum(c['source_label'] is None and c['kind'] == 'field' for c in index[ARMS[0]].values()) == 32 and sum(c['kind'] == 'return' for c in index[ARMS[0]].values()) == 12, 'roles')
    for case in cases:
        members = [index[a][case['name']] for a in ARMS]
        require(all(m['execution_summary']['frames'] == case['execution_summary']['frames'] and m['future'] == case['future'] and m['kind'] == case['kind'] for m in members), 'paired metadata')
        for k in ('source_case', 'source_directory', 'source_label', 'notify_frame'):
            require(all(m[k] == members[0][k] for m in members), 'paired source/notify')
        for name in ('mic.f32le', 'reference.f32le', 'activity.csv'):
            hashes = [sha(BASES[a.split('_')[0]][0] / m['name'] / name) for a, m in zip(ARMS, members)]
            require(len(set(hashes)) == 1, 'paired input/Activity ' + name)
        if case['kind'] == 'return':
            p = Path(members[0]['source_directory']) / 'near.f32le'
            locked[str(p)] = sha(p)
    sources = {str(p): sha(p) for p in (Path(__file__).resolve(), PLAN, AMEND, TEST)}
    return cases, index, locked, sources


def dump(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def run(output, cases, index, locked, sources):
    output.mkdir()
    observations = []
    for case in cases:
        name = case['name']
        require(Path(name).name == name and name not in ('.', '..'), 'case path')
        frames = case['execution_summary']['frames']
        rows = {}
        for arm in ARMS:
            member = index[arm][name]
            base = BASES[arm.split('_')[0]][0] / member['name']
            rows[arm] = parsed_rows(base / 'guard.csv', frames)
            recurrence(rows[arm], activity(base / 'activity.csv', frames), arm != 'd32_monitor', member['notify_frame'], arm == 'd33_feedback')
        with (output / (name + '.csv')).open('x', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(('frame', *(a + '_' + k for a in ARMS for k in OUTPUT_FIELDS)))
            for i in range(frames):
                writer.writerow((i, *(format(rows[a][i][k], '.17g') if k in FLOAT_FIELDS else rows[a][i][k] for a in ARMS for k in OUTPUT_FIELDS)))
        diagnostic = None
        if not case['future']:
            measurement = case['observation']['measurement']
            windows = [measurement['whole'], *measurement['windows']]
            near = near_truth(Path(index[ARMS[0]][name]['source_directory']) / 'near.f32le', frames) if case['kind'] == 'return' else None
            diagnostic = dict(arms={a: arm_summary(rows[a], windows, near) for a in ARMS},
                              differences={a + '__' + b: differences(rows[a], rows[b]) for a, b in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2]))})
        observations.append(dict(name=name, kind=case['kind'], future=case['future'], frames=frames,
                                 notify_frame=index[ARMS[0]][name]['notify_frame'], diagnostic=diagnostic))
        print(name, frames, flush=True)
    normal = (output / 'field-case-07-used0-shadow.csv').read_bytes().splitlines()
    require(normal == (output / 'repeat.csv').read_bytes().splitlines(), 'repeat exact all arms')
    require(normal[:1248] == (output / 'future.csv').read_bytes().splitlines()[:1248], 'future prefix exact all arms')
    require(all(sha(Path(p)) == h for p, h in {**locked, **sources}.items()), 'end source/input drift')
    result = dict(experiment='FE_DEVICE_GUARD_FEEDBACK_D34', decision='GUARD_FEEDBACK_DIAGNOSTIC_NO_PROMOTION',
                  promotion_allowed=False, shipping_approved=False, dsp_executions=0, cases=observations,
                  case_arms=138, source_frames=126486, state_frames=379458,
                  data_role='inspected development and synthetic engineering; adaptive reuse',
                  monitor_potential_is_not_actual=True, future_summarized=False, source_input_start_end_equal=True)
    dump(output / 'result.json', result)
    artifacts = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    dump(output / 'binding.json', dict(input_files=locked, source_files=sources, artifacts=artifacts))
    print('RESULT_SHA256', sha(output / 'result.json'), flush=True)
    print('BINDING_SHA256', sha(output / 'binding.json'), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        cases, index, locked, sources = preflight(args.output_root)
        if args.dry_run:
            print(json.dumps(dict(cases=46, case_arms=138, state_frames=379458, writes=False, dsp_executions=0)))
        else:
            run(args.output_root, cases, index, locked, sources)
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        print('DIAGNOSTIC_INVALID:', error, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
