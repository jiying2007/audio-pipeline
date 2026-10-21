"""D20 first-divergence analysis of frozen D19 development traces, no DSP replay."""
from __future__ import annotations

import argparse
from array import array
import csv
import io
import math
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, safe_file, sha, summary
from tools.codex_assets.device_exact_reference import dump, read_json
from tools.codex_assets.device_replay import metric_rows
from tools.codex_assets.device_stages import FIELDS, STAGES, preflight as previous_preflight

BASE = Path('/tmp/audio-fe-device-stages-d19-r1-20261011')
HASHES = {'result.json': '31998072bdb2e2836ee87722e776919e442fe836ffee48537006579910e9cd84',
          'binding.json': '47d4a0fe0c8e1c0a2eafb02262efd6abc449f0c6a5004557c75650356fded2a0'}
PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_TIMING_D20_PLAN.zh-CN.md'


def preflight(root):
    _, captures, _ = previous_preflight(root)
    for name, expected in HASHES.items():
        require(sha(bounded(BASE / name, 4 * 1024 * 1024)) == expected, 'D19 dependency drift')
    binding = read_json(BASE / 'binding.json')
    for name, expected in binding['artifacts'].items():
        require(sha(bounded(safe_file(BASE, name), 16 * 1024 * 1024)) == expected, 'D19 artifact drift: ' + name)
    for name, expected in binding['source_files'].items():
        path = Path(name) if Path(name).is_absolute() else safe_file(ROOT, name)
        require(sha(bounded(path, 4 * 1024 * 1024)) == expected, 'D19 dependency drift: ' + name)
    require([c['case_id'] for c in read_json(BASE / 'result.json')['cases']] == [c['case_id'] for c in captures],
            'D19 case order drift')
    return captures


def differing_ranges(left, right):
    require(len(left) == len(right), 'paired length mismatch')
    ranges, start = [], None
    for index in range(len(left) + 1):
        differs = index < len(left) and left[index] != right[index]
        if differs and start is None:
            start = index
        if not differs and start is not None:
            ranges.append([start, index])
            start = None
    return dict(count=sum(b - a for a, b in ranges), first=ranges[0][0] if ranges else None,
                last=ranges[-1][1] - 1 if ranges else None, ranges_half_open=ranges)


def trace_difference(left, right, samples, offset=0):
    a, b = bounded(left, 4 * 1024 * 1024), bounded(right, 4 * 1024 * 1024)
    require(len(a) == len(b) == samples * 4, 'float trace length')
    for data in (a, b):
        values = array('f'); values.frombytes(data)
        if sys.byteorder != 'little':
            values.byteswap()
        require(all(math.isfinite(x) for x in values), 'nonfinite trace')
    first, count = None, 0
    for i in range(samples):
        if a[i * 4:i * 4 + 4] != b[i * 4:i * 4 + 4]:
            if first is None:
                first = i
            count += 1
    event = None if first is None else dict(sample=first, frame=first // 160, frame_offset=first % 160,
                                          replay_seconds=first / 16000, latency_paired_input_sample=first - offset)
    return dict(first=event, mismatched_samples=count, byte_equal=count == 0, offset_samples=offset)


def controls(path, metrics):
    reader = csv.DictReader(io.StringIO(bounded(path, 1024 * 1024).decode('ascii')))
    require(reader.fieldnames == FIELDS, 'control schema')
    result = []
    flags = ('far', 'dt', 'frequency_enabled', 'frequency_active', 'agc_allow')
    for i, row in enumerate(reader):
        require(set(row) == set(FIELDS) and row['frame'] == str(i), 'control sequence/schema')
        require(all(row[k] in ('0', '1') for k in flags), 'control flag')
        parsed = {k: int(row[k]) if k in flags or k == 'frame' else float(row[k]) for k in FIELDS}
        require(all(math.isfinite(v) for v in parsed.values()), 'control finite')
        require(i < len(metrics) and parsed['far'] == metrics[i]['far_end_active'] and
                parsed['dt'] == metrics[i]['double_talk_active'], 'control/metrics mismatch')
        require(parsed['frequency_enabled'] == 1 and parsed['agc_allow'] == int(not(parsed['far'] and not parsed['dt'])),
                'control policy')
        result.append(parsed)
    require(len(result) == len(metrics), 'control count')
    return result


def relationship(output_frame, gate_frame):
    if output_frame is None:
        return 'no-output-difference'
    if gate_frame is None:
        return 'no-gate-difference'
    return 'before' if gate_frame < output_frame else 'after' if gate_frame > output_frame else 'same-frame'


def analyze(captures):
    cases = []
    for index, c in enumerate(captures):
        directory = BASE / ('case-' + str(index + 1).zfill(2))
        n = summary(c)['replay_samples']
        rows = {mode: controls(directory / mode / 'control.csv', metric_rows(directory / (mode + '.jsonl'), n))
                for mode in ('fixed1', 'used0')}
        traces = {'reference': trace_difference(directory / 'fixed1.reference.f32le', directory / 'used0.reference.f32le', n)}
        for name in STAGES:
            traces[name] = trace_difference(directory / 'fixed1' / (name + '.f32le'),
                directory / 'used0' / (name + '.f32le'), n, 160 if name in ('ns_output', 'agc_output') else 0)
        require(traces['aec_input']['byte_equal'], 'AEC input control')
        zero = not any(c['raw'].samples[::2])
        require(not zero or all(t['byte_equal'] for t in traces.values()), 'zero reference control')
        differences = {key: differing_ranges([row[key] for row in rows['fixed1']], [row[key] for row in rows['used0']])
                       for key in FIELDS[1:]}
        eligible = {mode: [int(row['far'] and not row['dt']) for row in values] for mode, values in rows.items()}
        differences['gate_eligible'] = differing_ranges(eligible['fixed1'], eligible['used0'])
        differences['far_dt_pair'] = differing_ranges([(row['far'], row['dt']) for row in rows['fixed1']],
                                                     [(row['far'], row['dt']) for row in rows['used0']])
        first = traces['aec_residual']['first']
        frame = first['frame'] if first else None
        cases.append(dict(case_id=c['case_id'], scene=c['session']['scene'],
                          samples=n, zero_reference=zero, traces=traces, controls=differences,
                          gate_relative_to_aec=relationship(frame, differences['gate_eligible']['first']),
                          far_dt_relative_to_aec=relationship(frame, differences['far_dt_pair']['first']),
                          flags_at_first_aec_difference=None if frame is None else
                          {mode: rows[mode][frame] for mode in rows}))
    require(sum(c['zero_reference'] for c in cases) == 8, 'zero control count')
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    created = False
    try:
        captures = preflight(args.root)
        if args.dry_run:
            print('D20_PREFLIGHT_PASS', len(captures), 'cases; writes=False')
            return 0
        require(not args.output.exists() and not args.output.is_symlink() and Path('/tmp') in args.output.resolve().parents,
                'new /tmp output required')
        sources = [Path(__file__).resolve(), PLAN, ROOT / 'tools/codex_assets/device_capture.py',
                   ROOT / 'tools/codex_assets/device_exact_reference.py', ROOT / 'tools/codex_assets/device_replay.py',
                   ROOT / 'tools/codex_assets/device_stages.py', ROOT / 'tools/codex_assets/device_alignment.py']
        initial = {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in sources}
        args.output.mkdir()
        created = True
        cases = analyze(captures)
        preflight(args.root)
        require(initial == {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in sources}, 'analysis source drift')
        result = dict(experiment='FE_DEVICE_TIMING_D20', decision='TIMING_DIAGNOSTIC_NO_PROMOTION',
                      data_role='development', dsp_executions=0, promotion_allowed=False, shipping_approved=False,
                      cases=cases, relationships={name: sum(c['gate_relative_to_aec'] == name for c in cases)
                        for name in ('before', 'same-frame', 'after', 'no-gate-difference', 'no-output-difference')})
        dump(args.output / 'result.json', result)
        dump(args.output / 'binding.json', dict(source_files=initial, d19_hashes=HASHES,
             inherited_library_sha256=read_json(BASE / 'binding.json')['measurement_library_sha256'],
             new_compilation=False, dsp_executions=0,
             source_start_end_equal=True, input_start_end_equal=True,
             artifacts={'result.json': sha((args.output / 'result.json').read_bytes())}))
        print('D20_TIMING_PASS', result['relationships'])
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        if created:
            dump(args.output / 'measurement-invalid.json', dict(decision='MEASUREMENT_INVALID', error=str(error)))
        print('device_timing: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
