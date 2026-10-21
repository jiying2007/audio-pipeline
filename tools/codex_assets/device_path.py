"""D21 standalone frozen MDF known-path engineering experiment, no promotion."""
from __future__ import annotations

import argparse
from array import array
import csv
import io
import math
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, safe_file, sha, strict_json
from tools.codex_assets.device_exact_reference import D17, dump, logged, read_json
from tools.codex_assets.device_replay import FLAGS
from tools.codex_assets.device_stages import D18
from tools.codex_assets.device_timing import preflight as previous_preflight

PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_PATH_D21_PLAN.zh-CN.md'
RUNNER = ROOT / 'tests/validation/frontend_evolution/device_path_d21.c'
D20_BASE = Path('/tmp/audio-fe-device-timing-d20-r1-20261011')
D20_HASHES = {'result.json': '66126f7b6ea71347a2cdd9a18ec72f1ac5b33a96a0a5b9d6e402da1823f65180',
              'binding.json': 'eca1f9ac9d4276a6184a389e5eca46d8dbb99892c0a007044c8d667b62aa6c21'}
WINDOWS = ((0, 2), (4, 6), (10, 12), (18, 20))
FIELDS = ['frame', 'runtime_stride', 'steady_frames', 'adapt_phase', 'constrain_partition', 'x_head', 'x_power_total', 'weight_l2']
TRACES = ('mic', 'reference', 'echo', 'residual')
CASES = [(f'p{path}-r{offset}', path, offset, 'normal') for path in (32, 48, 64) for offset in (16, 20)] + [
    (mode, 48, 16, mode) for mode in ('disabled', 'hold', 'zero')] + [('repeat', 48, 20, 'normal'), ('future', 48, 20, 'future')]


def preflight(root):
    previous_preflight(root)
    for name, expected in D20_HASHES.items():
        require(sha(bounded(D20_BASE / name, 4 * 1024 * 1024)) == expected, 'D20 dependency drift')
    binding = read_json(D20_BASE / 'binding.json')
    for name, expected in binding['source_files'].items():
        require(sha(bounded(Path(name), 4 * 1024 * 1024)) == expected, 'D20 source drift')
    require(read_json(D18 / 'fixed1-config.json')['aec_filter_ms'] == 96 and
            read_json(D18 / 'fixed1-config.json')['aec_adapt_stride'] == 2 and
            read_json(D18 / 'fixed1-config.json')['aec_mu'] == 0.219999999, 'AEC CALL config drift')


def raw_signal(future=False):
    state, values = 0x12345678, array('f')
    for i in range(320000):
        state = (state ^ (state << 13)) & 0xffffffff
        state = (state ^ (state >> 17)) & 0xffffffff
        state = (state ^ (state << 5)) & 0xffffffff
        value = ((state & 65535) - 32768) / 262144
        values.append(-value if future and i >= 160000 else value)
    return values


def encoded(values):
    values = array('f', values)
    if sys.byteorder != 'little':
        values.byteswap()
    return values.tobytes()


def signal(path):
    data = bounded(path, 2 * 1024 * 1024)
    require(len(data) == 320000 * 4, 'trace length')
    values = array('f'); values.frombytes(data)
    if sys.byteorder != 'little':
        values.byteswap()
    require(all(math.isfinite(x) for x in values), 'nonfinite trace')
    return values


def stats(mic, residual, first, last):
    a, b = mic[first:last], residual[first:last]
    require(a and len(a) == len(b) == last - first, 'measurement range')
    x, y = math.fsum(v * v for v in a) / len(a), math.fsum(v * v for v in b) / len(b)
    require(x > 0, 'empty echo energy')
    return dict(samples=len(a), mic_rms_dbfs=20 * math.log10(max(math.sqrt(x), 1e-12)),
                residual_rms_dbfs=20 * math.log10(max(math.sqrt(y), 1e-12)),
                mic_peak=max(abs(v) for v in a), residual_peak=max(abs(v) for v in b),
                known_echo_erle_db=10 * math.log10(x / max(y, 1e-20)))


def measure(directory, path, offset, mode):
    values = {name: signal(directory / (name + '.f32le')) for name in TRACES}
    raw = raw_signal(mode == 'future')
    require((directory / 'mic.f32le').read_bytes() == encoded([0.0] * path + [0.5 * v for v in raw[:-path]]), 'known mic construction')
    ref = [0.0] * 320000 if mode == 'zero' else [0.0] * offset + list(raw[:-offset])
    require((directory / 'reference.f32le').read_bytes() == encoded(ref), 'known reference construction')
    error = max(abs(a - (b + c)) for a, b, c in zip(values['mic'], values['echo'], values['residual']))
    require(error <= 1e-6, 'AEC identity')
    reader = csv.DictReader(io.StringIO(bounded(directory / 'state.csv', 1024 * 1024).decode('ascii')))
    require(reader.fieldnames == FIELDS, 'state schema')
    rows = list(reader)
    require(len(rows) == 2000, 'state frame count')
    for i, row in enumerate(rows):
        require(set(row) == set(FIELDS) and row['frame'] == str(i) and all(math.isfinite(float(v)) for v in row.values()), 'state finite/sequence')
        require(row['runtime_stride'] == '2' and row['adapt_phase'] in ('0', '1') and
                0 <= int(row['constrain_partition']) < 48 and 0 <= int(row['x_head']) < 48 and
                0 <= int(row['steady_frames']) <= 50 and float(row['x_power_total']) >= 0 and float(row['weight_l2']) >= 0, 'state range')
    if mode in ('disabled', 'hold', 'zero'):
        require(not any(values['echo']) and values['residual'] == values['mic'] and
                all(float(row['weight_l2']) == 0 for row in rows), 'negative output/weight')
    return dict(arithmetic_max_abs_error=error, whole=stats(values['mic'], values['residual'], 0, 320000),
                windows=[dict(seconds=[a, b], sample_range=[a * 16000, b * 16000],
                              **stats(values['mic'], values['residual'], a * 16000, b * 16000)) for a, b in WINDOWS],
                final_state=rows[-1])


def run(root, output, created):
    preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents, 'new /tmp output required')
    sources = [Path(__file__).resolve(), PLAN, RUNNER, ROOT / 'tools/codex_assets/device_capture.py',
               ROOT / 'tools/codex_assets/device_exact_reference.py', ROOT / 'tools/codex_assets/device_replay.py',
               ROOT / 'tools/codex_assets/device_stages.py', ROOT / 'tools/codex_assets/device_timing.py',
               ROOT / 'tools/codex_assets/device_alignment.py', D18 / 'build/libaudio_pipeline.a',
               D18 / 'build/generated/audio_pipeline/audio_pipeline_build.h', D18 / 'build/CMakeFiles/audio_pipeline.dir/flags.make']
    initial = {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in sources}
    output.mkdir(); created.append(output)
    definitions = [line.split('=', 1)[1].split() for line in sources[-1].read_text().splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions) == 1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]), 'build definitions')
    logged(output, 'compile', ['cc', *FLAGS, *definitions[0], '-I', str(D18 / 'source/src'), '-I', str(D18 / 'source/include'),
           '-I', str(D18 / 'build/generated'), str(RUNNER), str(D18 / 'build/libaudio_pipeline.a'), '-lm', '-lpthread',
           '-o', str(output / 'runner')], ROOT)
    executable_hash = sha((output / 'runner').read_bytes())
    logged(output, 'invalid', [str(output / 'runner'), 'invalid'], ROOT, expected=2)
    cases = []
    for name, path, offset, mode in CASES:
        directory = output / name; directory.mkdir()
        result = strict_json(logged(output, name, [str(output / 'runner'), str(path), str(offset), mode, str(directory)], ROOT).encode())
        require(result == dict(frames=2000, samples=320000, sync_calls=0), 'execution summary')
        cases.append(dict(name=name, path_delay=path, reference_offset=offset, mode=mode, measurement=measure(directory, path, offset, mode)))
    for name in [n + '.f32le' for n in TRACES] + ['state.csv']:
        original = (output / 'p48-r20' / name).read_bytes()
        require(original == (output / 'repeat' / name).read_bytes(), 'repeat equivalence')
        future = (output / 'future' / name).read_bytes()
        require(original[:160000 * 4] == future[:160000 * 4] if name.endswith('.f32le') else
                original.splitlines()[:1001] == future.splitlines()[:1001], 'future prefix causality')
    preflight(root)
    require(initial == {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in sources} and executable_hash == sha((output / 'runner').read_bytes()), 'experiment identity drift')
    pairs = []
    records = {c['name']: c for c in cases}
    for path in (32, 48, 64):
        require((output / f'p{path}-r16/mic.f32le').read_bytes() == (output / f'p{path}-r20/mic.f32le').read_bytes(), 'paired mic drift')
        a, b = records[f'p{path}-r16']['measurement'], records[f'p{path}-r20']['measurement']
        difference = lambda x, y: {key: y[key] - x[key] for key in ('residual_rms_dbfs', 'known_echo_erle_db')}
        pairs.append(dict(path_delay=path, whole=difference(a['whole'], b['whole']),
                          windows=[dict(seconds=x['seconds'], **difference(x, y)) for x, y in zip(a['windows'], b['windows'])]))
    dump(output / 'result.json', dict(experiment='FE_DEVICE_PATH_D21', decision='KNOWN_PATH_COORDINATE_DIAGNOSTIC_NO_PROMOTION',
         data_role='synthetic-engineering', executions=11, promotion_allowed=False, shipping_approved=False,
         algorithm_changed=False, cases=cases, offset20_minus_offset16=pairs))
    dump(output / 'binding.json', dict(source_files=initial, runner_sha256=executable_hash, d20_hashes=D20_HASHES,
         source_start_end_equal=True, input_start_end_equal=True, library_sha256=initial[str(D18 / 'build/libaudio_pipeline.a')],
         artifacts={str(f.relative_to(output)): sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}))
    print('D21_KNOWN_PATH_PASS 11 executions', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv); created = []
    try:
        if args.dry_run:
            preflight(args.root)
            print('D21_PREFLIGHT_PASS 11 registered executions; writes=False')
        else:
            run(args.root, args.output, created)
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        if created == [args.output]:
            dump(args.output / 'measurement-invalid.json', dict(decision='MEASUREMENT_INVALID', error=str(error)))
        print('device_path: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
