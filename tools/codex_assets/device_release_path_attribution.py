"""D46 fixed return-path attribution from frozen D45 outputs; no DSP."""
import argparse
import array
import csv
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = Path('/tmp/audio-fe-device-post-ns-protection-d45-20261011')
OUTPUT = Path('/tmp/audio-fe-device-release-path-attribution-d46-20261012')
EXPERIMENT = 'FE_DEVICE_RELEASE_PATH_ATTRIBUTION_D46'
PHASES = ((0, 1000), (1000, 1200), (1200, 1210), (1210, 1600),
          (1600, 1800), (1800, 1810), (1810, 2000))
FRAMES, FRAME_SIZE, SAMPLES = 2000, 160, 320000
FILE_LIMIT, ROOT_LIMIT, FREE_MIN = 4 * 1024**2, 16 * 1024**2, 512 * 1024**2
TIME_LIMIT = 180.0
POWER_FIELDS = ('frame', 'far', 'dt', 'count_before', 'valid_bins',
                'noise_dominant_bins', 'positive_floor_bins', 'would_raise_bins',
                'raised_bins', 'q_mean', 'echo_sum', 'residual_sum',
                'innovation_sum', 'noise_sum', 'excess_sum', 'floor_mean',
                'floor2_residual_sum', 'post_would_raise_bins')
INTEGER_FIELDS = POWER_FIELDS[:9] + (POWER_FIELDS[-1],)
SOURCE_PINS = {
    BASE / 'result.json': '0d9dbf01b21510216df648d323c501166a039a5b45d44c93d2699b8eabc4e8de',
    BASE / 'binding.json': 'bb0fbb8b9942e2b9ca5dbecf9a53ac1f13f38d40c7bbb574d5a438506d00cff8',
    Path('/tmp/audio-device-d45-review-snapshot-v1.json'): 'a19d6269921530b6d8890dfa4eded1340a7d9e86c1991376f9ba035a6eae21cc',
    REPO / 'docs/research/frontend-evolution-v1/DEVICE_POST_NS_PROTECTION_D45_CLOSEOUT.zh-CN.md': 'ea6556b133296c9ca296d3f9f205930ca0f5bf0fcbe0542a5aae7d711014608f',
    REPO / 'tests/validation/frontend_evolution/device_return_d25.c': '079c0bc34b605d855ce728cceeb8656204cbf86192bdeaa48724454a9e4eaeab',
    REPO / 'tools/codex_assets/device_return.py': '26f28c5cf83fe5882d18bd2b86c7c2670b26494c20131c98556cb7c9567e02a0',
    REPO / 'docs/research/frontend-evolution-v1/DEVICE_RELEASE_PATH_ATTRIBUTION_D46_PLAN.zh-CN.md': 'b442e58a8cbe0a31a5b4c67fa14e5d20c98951641db667978c41b7f519e97366',
    REPO / 'docs/research/frontend-evolution-v1/DEVICE_RELEASE_PATH_ATTRIBUTION_D46_PLAN_REVIEW.zh-CN.md': '520a4bf5099558994c2ad2390c90a2e37854cea74fd633e657cf69e1d2e626f9',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded(path):
    require(path.is_file() and not path.is_symlink(), 'regular input required: ' + str(path))
    require(path.stat().st_size <= FILE_LIMIT, 'input file budget: ' + str(path))
    return path.read_bytes()


def digest(path):
    return hashlib.sha256(bounded(path)).hexdigest()


def load(path):
    return json.loads(bounded(path).decode('utf-8'))


def validate_output(path):
    require(path.is_absolute() and path == OUTPUT, 'fixed new /tmp output root required')
    require(not any(p.is_symlink() for p in (path,) + tuple(path.parents)), 'output symlink rejected')
    require(not path.exists() and path.resolve() == path, 'existing or indirect root rejected')


def case_names():
    return tuple(sorted('return-%s-r%d-%s-shadow' % (shape, offset, condition)
                        for shape in ('A', 'ABA') for offset in (16, 20)
                        for condition in ('echo', 'dt', 'unguarded')))


def select_pairs(result):
    rows = [r for r in result['cases'] if r['kind'] == 'return' and not r['future']]
    wanted = {(mode, arm, source) for mode in ('candidate', 'monitor')
              for arm in ('primary', 'selected') for source in case_names()}
    actual = [(r['mode'], r['arm'], r['source_case']) for r in rows]
    require(len(actual) == 48 and set(actual) == wanted, 'fixed unique return set required')
    for r in rows:
        require(r['name'] == '-'.join((r['mode'], r['arm'], r['source_case'])), 'case name identity')
        s = r['execution_summary']
        require(s['frames'] == FRAMES and s['samples'] == SAMPLES, 'fixed frame/sample count')
    return tuple((arm, source) for arm in ('primary', 'selected') for source in case_names())


def preflight():
    locks = {}

    def lock(path, expected):
        require(digest(path) == expected, 'input SHA drift: ' + str(path))
        key = str(path)
        require(key not in locks or locks[key] == expected, 'conflicting source identity')
        locks[key] = expected

    for path, expected in SOURCE_PINS.items():
        lock(path, expected)
    snapshot = load(Path('/tmp/audio-device-d45-review-snapshot-v1.json'))
    require(len(snapshot['files']) == 47, 'D45 snapshot coverage')
    for name, expected in snapshot['files'].items():
        lock(Path(name), expected)
    for path in (Path(__file__).resolve(), REPO / 'tests/validation/frontend_evolution/test_device_release_path_attribution.py'):
        lock(path, digest(path))
    result, binding = load(BASE / 'result.json'), load(BASE / 'binding.json')
    require(result['decision'] == 'DEVELOPMENT_REJECTED' and result['promotion_allowed'] is False
            and result['shipping_approved'] is False, 'D45 refusal preserved')
    require(binding['source_input_start_end_equal'] is True, 'D45 source binding')
    pairs = select_pairs(result)
    consumed = []
    for arm, source in pairs:
        for mode in ('candidate', 'monitor'):
            name = '-'.join((mode, arm, source))
            for leaf in ('ns.f32le', 'final.f32le', 'power.csv'):
                relative = name + '/' + leaf
                path = BASE / relative
                lock(path, binding['artifacts'][relative])
                if leaf.endswith('.f32le'):
                    require(path.stat().st_size == SAMPLES * 4, 'PCM sample length')
                consumed.append(str(path))
    require(len(consumed) == len(set(consumed)) == 144, '96 PCM and 48 power files required')
    require(shutil.disk_usage('/tmp').free >= FREE_MIN, 'minimum /tmp free space')
    return locks, pairs, consumed


def pcm(path):
    raw = bounded(path)
    require(len(raw) == SAMPLES * 4, 'PCM length')
    values = array.array('f')
    require(values.itemsize == 4, 'binary32 host representation')
    values.frombytes(raw)
    if sys.byteorder != 'little':
        values.byteswap()
    require(all(math.isfinite(x) for x in values), 'nonfinite PCM')
    return values


def alignment(first, last):
    require(isinstance(first, int) and isinstance(last, int) and 0 <= first < last <= FRAMES,
            'frame range')
    a, requested_end = first * FRAME_SIZE, last * FRAME_SIZE
    b = min(requested_end, SAMPLES - FRAME_SIZE)
    return dict(frame_range=[first, last], original_input_range=[a, requested_end],
                effective_input_range=[a, b], output_range=[a + FRAME_SIZE, b + FRAME_SIZE],
                samples=b - a, tail_truncated_samples=requested_end - b)


def energies(candidate, monitor, first, last):
    require(len(candidate) == len(monitor) and 0 <= first < last <= len(candidate), 'energy bounds')
    ec = em = ed = pc = pm = 0.0
    for index in range(first, last):
        c, m = float(candidate[index]), float(monitor[index])
        require(math.isfinite(c) and math.isfinite(m), 'nonfinite sample')
        ec += c * c
        em += m * m
        diff = c - m
        ed += diff * diff
        pc = max(pc, abs(c))
        pm = max(pm, abs(m))
    return dict(candidate_energy=ec, monitor_energy=em, difference_energy=ed,
                energy_delta=ec - em, candidate_peak=pc, monitor_peak=pm,
                candidate_zero=ec == 0.0, monitor_zero=em == 0.0,
                signal_energy_delta_db=10.0 * math.log10(ec / em) if ec > 0.0 and em > 0.0 else None)


def close_number(actual, expected):
    return actual == 0.0 if expected == 0.0 else abs(actual - expected) <= max(1e-24, 1e-12 * abs(expected))


def check_partition(segments, whole):
    for stage in ('ns', 'final'):
        for field in ('candidate_energy', 'monitor_energy', 'difference_energy'):
            require(close_number(sum(s['stages'][stage][field] for s in segments), whole[stage][field]),
                    'segment energy partition: ' + stage + '/' + field)
        for field in ('candidate_peak', 'monitor_peak'):
            require(max(s['stages'][stage][field] for s in segments) == whole[stage][field], 'peak partition')


def power(path):
    bounded(path)
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(tuple(reader.fieldnames or ()) == POWER_FIELDS, '18 field power schema')
        rows = list(reader)
    require(len(rows) == FRAMES, 'power frame count')
    previous_count = 0
    for frame, row in enumerate(rows):
        require(set(row) == set(POWER_FIELDS) and all(v is not None for v in row.values()), 'power row width')
        for key, value in row.items():
            number = int(value) if key in INTEGER_FIELDS else float(value)
            require(math.isfinite(number), 'nonfinite power')
            if key in INTEGER_FIELDS:
                upper = FRAMES - 1 if key == 'frame' else 1 if key in ('far', 'dt') else 10 if key == 'count_before' else 257
                require(0 <= number <= upper, 'power integer range')
        require(int(row['frame']) == frame, 'power frame order')
        count = int(row['count_before'])
        active = bool(int(row['far']) and not int(row['dt']))
        require(count == previous_count, 'power count-before recurrence')
        previous_count = min(10, count + 1) if active else 0
        valid = int(row['valid_bins'])
        require(valid == 0 or (active and count == 10), 'power warmup/inactive valid')
        require(all(int(row[key]) <= valid for key in POWER_FIELDS[4:9] + (POWER_FIELDS[-1],)),
                'power aggregate count bound')
        numbers = {key: float(row[key]) for key in POWER_FIELDS[9:-1]}
        require(all(value >= 0.0 for value in numbers.values()), 'negative power aggregate')
        require(numbers['q_mean'] <= 1.0 and numbers['floor_mean'] <= 1.0, 'power mean range')
        require(numbers['innovation_sum'] <= numbers['residual_sum'] * (1.0 + 1e-12),
                'power innovation range')
        require(numbers['excess_sum'] <= numbers['innovation_sum'] * (1.0 + 1e-12),
                'power excess range')
        if valid == 0:
            require(all(value == 0.0 for value in numbers.values()), 'empty power aggregate exact zero')
    return rows


def paired_power(candidate, monitor):
    require(len(candidate) == len(monitor) == FRAMES, 'paired power length')
    for c, m in zip(candidate, monitor):
        require({k: v for k, v in c.items() if k != 'raised_bins'} ==
                {k: v for k, v in m.items() if k != 'raised_bins'}, 'power mode projection')
        require(int(m['raised_bins']) == 0 and int(c['raised_bins']) == int(c['post_would_raise_bins']),
                'actual protection count')


def power_segment(rows, first, last):
    subset = rows[first:last]
    return dict(frame_range=[first, last], raised_frames=sum(int(r['raised_bins']) > 0 for r in subset),
                raised_bins=sum(int(r['raised_bins']) for r in subset),
                positive_floor_frames=sum(int(r['positive_floor_bins']) > 0 for r in subset),
                positive_floor_bins=sum(int(r['positive_floor_bins']) for r in subset))


def deadline(started):
    require(time.monotonic() - started <= TIME_LIMIT, 'D46 180 second budget exceeded')


def emit(path, value):
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    require(len(data) <= FILE_LIMIT, 'output file budget')
    with path.open('xb') as stream:
        stream.write(data)


def run(output, started):
    validate_output(output)
    locks, pairs, consumed = preflight()
    deadline(started)
    output.mkdir(mode=0o700)
    try:
        emit(output / 'intent.json', dict(experiment=EXPERIMENT, source_sha256=locks,
             invocation_argv=sys.argv, executable=sys.executable, cwd=str(Path.cwd()), requested_at_ns=time.time_ns()))
        records = []
        for arm, source in pairs:
            names = {mode: '-'.join((mode, arm, source)) for mode in ('candidate', 'monitor')}
            cpower, mpower = (power(BASE / names[mode] / 'power.csv') for mode in ('candidate', 'monitor'))
            paired_power(cpower, mpower)
            waves = {stage: tuple(pcm(BASE / names[mode] / (stage + '.f32le'))
                                 for mode in ('candidate', 'monitor')) for stage in ('ns', 'final')}
            segments = []
            for first, last in PHASES:
                coordinates = alignment(first, last)
                a, b = coordinates['output_range']
                segments.append(dict(coordinates=coordinates, power=power_segment(cpower, first, last),
                                     stages={stage: energies(c, m, a, b) for stage, (c, m) in waves.items()}))
            whole = {stage: energies(c, m, FRAME_SIZE, SAMPLES) for stage, (c, m) in waves.items()}
            check_partition(segments, whole)
            require(sum(s['coordinates']['samples'] for s in segments) == SAMPLES - FRAME_SIZE, 'complete aligned range')
            records.append(dict(arm=arm, source_case=source, segments=segments,
                                whole_coordinates=alignment(0, FRAMES), whole=whole))
            deadline(started)
        require(all(digest(Path(p)) == h for p, h in locks.items()), 'source start/end drift')
        deadline(started)
        result = dict(experiment=EXPERIMENT, status='MEASUREMENT_VALID_ATTRIBUTION_ONLY',
                      measurement_only=True, algorithm_changed=False, promotion_allowed=False, shipping_approved=False,
                      data_role='development-and-synthetic-engineering', dsp_executions=0,
                      pairs=24, pair_segments=168, stage_segments=336, paired_power_frames=FRAMES * 24,
                      power_input_frames=FRAMES * 48, consumed_pcm_files=96, consumed_power_files=48,
                      source_input_start_end_equal=True, records=records, elapsed_seconds=time.monotonic() - started)
        emit(output / 'result.json', result)
        artifacts = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
        emit(output / 'binding.json', dict(experiment=EXPERIMENT, locked_files=locks, consumed_files=consumed,
             source_input_start_end_equal=True, artifacts=artifacts, promotion_allowed=False, shipping_approved=False))
        require(sum(p.stat().st_size for p in output.iterdir() if p.is_file()) <= ROOT_LIMIT, 'D46 root budget')
        deadline(started)
        return dict(status=result['status'], pairs=24, pair_segments=168, stage_segments=336,
                    result_sha256=digest(output / 'result.json'), binding_sha256=digest(output / 'binding.json'))
    except Exception as error:
        target = output / 'measurement-invalid.json'
        if not target.exists():
            emit(target, dict(experiment=EXPERIMENT, status='MEASUREMENT_INVALID_REPLAN',
                 error_type=type(error).__name__, error=str(error), elapsed_seconds=time.monotonic() - started,
                 promotion_allowed=False, shipping_approved=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=OUTPUT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--run', action='store_true', help='execute the unique fixed attribution operation')
    group.add_argument('--dry-run', action='store_true', help='read input identities without writing (default)')
    args = parser.parse_args()
    started = time.monotonic()
    try:
        validate_output(args.output_root)
        if args.run:
            value = run(args.output_root, started)
        else:
            locks, pairs, consumed = preflight()
            deadline(started)
            value = dict(status='DRY_RUN', writes=False, dsp_executions=0, pairs=len(pairs),
                         pair_segments=168, stage_segments=336, consumed_files=len(consumed), locked_files=len(locks))
        print(json.dumps(value, ensure_ascii=False), flush=True)
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError) as error:
        print('D46_REFUSED: ' + str(error), file=sys.stderr, flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
