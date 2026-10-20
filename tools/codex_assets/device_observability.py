"""D31 frozen-trace observation, never a detector or acoustic evaluator."""
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
BASE = Path('/tmp/audio-fe-device-activity-d30-20261011')
HASHES = {'result.json': 'e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d',
          'binding.json': '2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956'}
PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_OBSERVABILITY_D31_PLAN.zh-CN.md'
AMEND = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_OBSERVABILITY_D31_AMENDMENT.zh-CN.md'
TEST = ROOT / 'tests/validation/frontend_evolution/test_device_observability.py'
CHANNELS = ('mic', 'reference', 'primary_echo', 'primary_residual', 'echo', 'residual')
PAIRS = (('mic', 'reference'), ('mic', 'primary_echo'), ('primary_residual', 'reference'),
         ('residual', 'reference'), ('primary_residual', 'primary_echo'), ('residual', 'echo'))
FEATURES = tuple(a + '_' + b + '_cos2' for a, b in PAIRS) + ('primary_residual_mic_power_ratio', 'residual_mic_power_ratio')


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
        d = {}
        for key, value in items:
            require(key not in d, 'duplicate JSON key')
            d[key] = value
        return d
    def invalid(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def frame_features(values):
    require(set(values) == set(CHANNELS), 'six trace channels required')
    require(all(len(v) == 160 and all(math.isfinite(x) for x in v) for v in values.values()), 'finite 160-sample frame')
    energy = {k: sum(x * x for x in v) for k, v in values.items()}
    result = {}
    for a, b in PAIRS:
        denominator = energy[a] * energy[b]
        cross = sum(x * y for x, y in zip(values[a], values[b]))
        value = cross * cross / denominator if denominator else None
        require(value is None or math.isfinite(value) and 0 <= value <= 1 + 1e-12, 'normalized inner product bound')
        result[a + '_' + b + '_cos2'] = value
    for k in ('primary_residual', 'residual'):
        value = energy[k] / energy['mic'] if energy['mic'] else None
        require(value is None or math.isfinite(value) and value >= 0, 'power ratio bound')
        result[k + '_mic_power_ratio'] = value
    return result


def summary(values):
    valid = sorted(v for v in values if v is not None)
    require(all(math.isfinite(v) for v in valid), 'finite summary')
    result = dict(valid=len(valid), null=len(values) - len(valid))
    result.update({k: None for k in ('min', 'max', 'p10', 'p50', 'p90')})
    if valid:
        result.update(min=valid[0], max=valid[-1])
        for name, percentile in (('p10', 10), ('p50', 50), ('p90', 90)):
            result[name] = valid[(len(valid) * percentile + 99) // 100 - 1]
    return result


def window_summary(rows, original):
    a, b = original['sample_range']
    start, end = (a + 159) // 160, b // 160
    require(0 <= start <= end <= len(rows), 'window bounds')
    return dict(sample_range=[a, b], complete_frame_range=[start, end],
                observed_sample_range=[start * 160, end * 160],
                discarded_boundary_samples=(b - a) - (end - start) * 160,
                near_present=original.get('near_present'),
                features={k: summary([r[k] for r in rows[start:end]]) for k in FEATURES})


def preflight(output):
    require(output.is_absolute() and output == output.resolve(), 'canonical absolute output')
    require(output.parent == Path('/tmp') and not output.exists(), 'fresh direct /tmp output required')
    require(output not in (BASE, ROOT), 'input/repository output denied')
    locked = {}
    for name, expected in HASHES.items():
        path = BASE / name
        require(sha(path) == expected, 'D30 identity: ' + name)
        locked[str(path)] = expected
    binding = read_json(BASE / 'binding.json')
    for group in ('source_files', 'input_files', 'artifacts'):
        for name, expected in binding[group].items():
            path = BASE / name if group == 'artifacts' else Path(name)
            require(path.is_file() and sha(path) == expected, 'D30 dependency drift: ' + name)
            locked[str(path)] = expected
    cases = read_json(BASE / 'result.json')['cases']
    require(len(cases) == 46 and len({c['name'] for c in cases}) == 46, 'exact case set')
    require(sum(c['execution_summary']['frames'] for c in cases) == 126486, 'frame contract')
    source = {str(p): sha(p) for p in (Path(__file__).resolve(), PLAN, AMEND, TEST)}
    return cases, locked, source


def floats(path, count):
    require(path.stat().st_size == count * 4, 'trace size')
    values = array.array('f')
    require(values.itemsize == 4, 'Float32 array')
    values.frombytes(path.read_bytes())
    if sys.byteorder != 'little':
        values.byteswap()
    require(all(math.isfinite(v) for v in values), 'finite trace')
    return values


def dump(path, value):
    require(not path.exists(), 'no overwrite')
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def run(output, cases, locked, source):
    output.mkdir()
    observations = []
    frames = 0
    for case in cases:
        name = case['name']
        require(Path(name).name == name and name not in ('.', '..'), 'case path')
        count = case['execution_summary']['samples']
        require(count == case['execution_summary']['frames'] * 160, 'frame sample count')
        traces = {k: floats(BASE / name / (k + '.f32le'), count) for k in CHANNELS}
        rows = [frame_features({k: v[i:i + 160] for k, v in traces.items()}) for i in range(0, count, 160)]
        with (output / (name + '.csv')).open('x', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerow(('frame', *FEATURES))
            for i, row in enumerate(rows):
                writer.writerow((i, *('' if row[k] is None else format(row[k], '.17g') for k in FEATURES)))
        windows = None
        if not case['future']:
            measurement = case['observation']['measurement']
            windows = [window_summary(rows, w) for w in [measurement['whole'], *measurement['windows']]]
        observations.append(dict(name=name, kind=case['kind'], future=case['future'], frames=len(rows), windows=windows))
        frames += len(rows)
        print(name, len(rows), flush=True)
        del traces, rows
    normal = (output / 'field-case-07-used0-shadow.csv').read_bytes()
    require(normal == (output / 'repeat.csv').read_bytes(), 'repeat exact features')
    require(normal.splitlines()[:1248] == (output / 'future.csv').read_bytes().splitlines()[:1248], 'future prefix exact features')
    require(all(sha(Path(p)) == h for p, h in {**locked, **source}.items()), 'input/source end drift')
    result = dict(experiment='FE_DEVICE_OBSERVABILITY_D31', decision='NEAR_PATH_OBSERVABILITY_DIAGNOSTIC_NO_PROMOTION',
                  promotion_allowed=False, shipping_approved=False, dsp_executions=0,
                  frames=frames, cases=observations, input_start_end_equal=True, source_start_end_equal=True)
    dump(output / 'result.json', result)
    artifacts = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    dump(output / 'binding.json', dict(input_files=locked, source_files=source, artifacts=artifacts))
    print('RESULT_SHA256', sha(output / 'result.json'), flush=True)
    print('BINDING_SHA256', sha(output / 'binding.json'), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        cases, locked, source = preflight(args.output_root)
        if args.dry_run:
            print(json.dumps(dict(cases=len(cases), frames=126486, writes=False, dsp_executions=0)))
        else:
            run(args.output_root, cases, locked, source)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('MEASUREMENT_INVALID:', error, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
