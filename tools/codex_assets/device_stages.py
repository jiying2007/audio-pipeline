"""D19 same-state stage diagnostics; development data, no promotion authority."""
from __future__ import annotations

import argparse
from array import array
import csv
import io
import math
from pathlib import Path
import shutil
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, safe_file, sha, summary
from tools.codex_assets.device_exact_reference import dump, logged, preflight as original_preflight, read_json
from tools.codex_assets.device_replay import FLAGS, metric_rows, window

D18 = Path('/tmp/audio-fe-device-exact-reference-d18-20261011')
D16 = Path('/tmp/audio-fe-device-anchor-d16-r1-20261011')
HASHES = {'result.json': '369c8c484b107c549449a93d92bfa82e464f0163fefce55377d2096b1caa47be',
          'binding.json': 'ab41fbe3d970b11ff4a001cfdcf4bd2c2f1d6a4032c36a1da0511526943c2da2'}
RUNNER = ROOT / 'tests/validation/frontend_evolution/device_stages_d19.c'
PLAN = ROOT / 'docs/research/frontend-evolution-v1/DEVICE_STAGES_D19_PLAN.zh-CN.md'
STAGES = ('aec_input', 'echo', 'aec_residual', 'ns_output', 'agc_output')
RENAMES = {'src/aec/ap_aec_mdf.c': 'ap_aec_backend_process', 'src/enhance/ap_ns.c': 'ap_ns_process',
           'src/enhance/ap_agc.c': 'ap_agc_process_controlled', 'src/enhance/ap_res.c': 'ap_res_process'}
FIELDS = ['frame', 'far', 'dt', 'frequency_enabled', 'frequency_active', 'res_gain', 'agc_allow',
          'gain_before', 'gain_after']


def preflight(root):
    p, captures, _, _ = original_preflight(root, D16)
    for name, expected in HASHES.items():
        require(sha(bounded(D18 / name, 4 * 1024 * 1024)) == expected, 'D18 dependency drift')
    binding = read_json(D18 / 'binding.json')
    for name, expected in binding['artifacts'].items():
        require(sha(bounded(safe_file(D18, name), 16 * 1024 * 1024)) == expected, 'D18 artifact drift: ' + name)
    result = read_json(D18 / 'result.json')
    require([c['case_id'] for c in result['cases']] == [c['case_id'] for c in captures], 'D18 case order drift')
    require(all(a['intake'] == summary(b) for a, b in zip(result['cases'], captures)), 'D18 intake drift')
    return p, captures, binding


def floats(path, n):
    data = bounded(path, 4 * 1024 * 1024)
    require(len(data) == n * 4, 'stage length mismatch')
    values = array('f'); values.frombytes(data)
    if sys.byteorder != 'little':
        values.byteswap()
    require(all(math.isfinite(x) for x in values), 'nonfinite stage')
    return values


def energy(values, first, last):
    require(0 <= first < last <= len(values), 'energy range')
    part = values[first:last]
    return dict(samples=len(part), rms_dbfs=20 * math.log10(max(math.sqrt(math.fsum(x * x for x in part) / len(part)), 1e-12)),
                peak=max(abs(x) for x in part))


def stages(directory, c, p, n, metrics):
    values = {name: floats(directory / (name + '.f32le'), n) for name in STAGES}
    error = max(abs(a - (b + d)) for a, b, d in zip(values['aec_input'], values['echo'], values['aec_residual']))
    require(error <= 1e-6, 'AEC arithmetic identity')
    rows = list(csv.DictReader(io.StringIO(bounded(directory / 'control.csv', 1024 * 1024).decode('ascii'))))
    require(len(rows) == n // 160 and list(rows[0]) == FIELDS, 'control schema/count')
    for i, row in enumerate(rows):
        require(all(math.isfinite(float(v)) for v in row.values()), 'control finite')
        require(row['frame'] == str(i), 'control sequence')
        require(all(row[k] in ('0', '1') for k in FIELDS[1:5] + ['agc_allow']), 'control flags')
        require(int(row['far']) == metrics[i]['far_end_active'] and int(row['dt']) == metrics[i]['double_talk_active'],
                'control/metric flags')
        require(row['frequency_enabled'] == '1' and int(row['agc_allow']) ==
                int(not (int(row['far']) and not int(row['dt']))), 'control policy')
    measures = {}
    for name, signal in values.items():
        offset = 160 if name in ('ns_output', 'agc_output') else 0
        windows = []
        for lo, hi in p['primary_windows_seconds']:
            first, last = window(c, lo, hi, n, offset)
            windows.append(dict(scene_time_s=[lo, hi], sample_range=[first + offset, last + offset],
                                **energy(signal, first + offset, last + offset)))
        measures[name] = dict(offset_samples=offset, whole=energy(signal, 0, n), windows=windows)
    return dict(stages=measures, arithmetic_max_abs_error=error,
                frames=len(rows), standalone_res_calls=0,
                frequency_active_frames=sum(int(r['frequency_active']) for r in rows),
                agc_increase_allowed_frames=sum(int(r['agc_allow']) for r in rows),
                agc_energy_change_db=dict(whole=measures['agc_output']['whole']['rms_dbfs'] - measures['ns_output']['whole']['rms_dbfs'],
                  windows=[a['rms_dbfs'] - b['rms_dbfs'] for a, b in zip(measures['agc_output']['windows'], measures['ns_output']['windows'])]))


def run(root, output, created):
    p, captures, old = preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,
            'new /tmp output required')
    dependencies = [RUNNER, PLAN, Path(__file__), ROOT / 'tools/codex_assets/device_capture.py',
                    ROOT / 'tools/codex_assets/device_replay.py', ROOT / 'tools/codex_assets/device_alignment.py',
                    ROOT / 'tools/codex_assets/device_exact_reference.py', D18 / 'result.json', D18 / 'binding.json']
    initial = {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in dependencies}
    output.mkdir()
    created.append(output)
    source, build = output / 'source', output / 'build'
    shutil.copytree(D18 / 'source', source)
    for name, function in RENAMES.items():
        path = source / name
        data = path.read_bytes()
        needle = (('float ' if function == 'ap_res_process' else 'void ') + function + '(').encode()
        require(data.count(needle) == 1, 'unique definition required')
        path.write_bytes(data.replace(needle, needle.replace((function + '(').encode(), (function + '_d19_real(').encode())))
    changed = {n for n, v in old['measurement_sources'].items() if sha((source / n).read_bytes()) != v}
    require(changed == set(RENAMES), 'unexpected measurement source change')
    logged(output, 'configure', ['cmake', '-S', str(source), '-B', str(build), '-DAP_BUILD_TESTS=ON',
           '-DAP_BUILD_BENCH=OFF', '-DAP_STRICT_WARNINGS=ON'], ROOT, timeout=300)
    logged(output, 'build', ['cmake', '--build', str(build), '--target', 'audio_pipeline', '-j', '2'], ROOT, timeout=300)
    header = 'generated/audio_pipeline/audio_pipeline_build.h'
    require((build / header).read_bytes() == (D18 / 'build' / header).read_bytes(), 'generated header drift')
    flags_make = (build / 'CMakeFiles/audio_pipeline.dir/flags.make').read_text()
    definitions = [line.split('=', 1)[1].split() for line in flags_make.splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions) == 1 and definitions[0] and all(x.startswith('-DAP_BUILD_') for x in definitions[0]),
            'build definitions missing or unexpected')
    logged(output, 'compile', ['cc', *FLAGS, *definitions[0], '-DD18_OBSERVER=1', '-I', str(source / 'src'),
           '-I', str(source / 'include'), '-I', str(build / 'generated'), str(RUNNER),
           str(build / 'libaudio_pipeline.a'), '-lm', '-lpthread', '-o', str(output / 'observe')], ROOT)
    executable_lock = {name: sha((output / name).read_bytes()) for name in ('observe', 'build/libaudio_pipeline.a', header.replace('generated/', 'build/generated/', 1))}
    require('3200 samples PASS' in logged(output, 'known', [str(output / 'observe'), '--self-test'], ROOT), 'known answers')
    logged(output, 'invalid', [str(output / 'observe'), 'invalid'], ROOT, expected=2)
    for mode in ('fixed1', 'used0'):
        description = logged(output, mode + '-describe', [str(output / 'observe'), '--describe', mode], ROOT)
        require(read_json(D18 / (mode + '-config.json')) == read_json_bytes(description), 'config drift')
        shutil.copyfile(D18 / (mode + '-config.json'), output / (mode + '-config.json'))
    cases, zeros = [], 0
    for index, c in enumerate(captures):
        relative = 'case-' + str(index + 1).zfill(2)
        directory, previous = output / relative, D18 / relative
        directory.mkdir()
        n = summary(c)['replay_samples']
        arms = {}
        for mode, render in (('fixed1', 'raw'), ('used0', 'used')):
            stage_dir = directory / mode
            stage_dir.mkdir()
            stem = directory / mode
            result = read_json_bytes(logged(output, relative + '-' + mode, [str(output / 'observe'), mode,
                str(previous / 'mic.pcm'), str(previous / (render + '.pcm')), str(stem.with_suffix('.pcm')),
                str(stem.with_suffix('.jsonl')), str(stem.with_suffix('.reference.f32le')), str(stage_dir)], ROOT))
            require(result == dict(frames=n // 160, render_underruns=1 if mode == 'fixed1' else 0), 'frame/startup drift')
            for suffix in ('.pcm', '.jsonl', '.reference.f32le'):
                require(stem.with_suffix(suffix).read_bytes() == (previous / (mode + suffix)).read_bytes(), 'D18 byte equivalence')
            arms[mode] = dict(summary=result, **stages(stage_dir, c, p, n, metric_rows(stem.with_suffix('.jsonl'), n)))
        zero = not any(c['raw'].samples[::2])
        if zero:
            require(all((directory / 'fixed1' / (name + '.f32le')).read_bytes() ==
                        (directory / 'used0' / (name + '.f32le')).read_bytes() for name in STAGES), 'zero stage control')
            zeros += 1
        deltas = {}
        for name in STAGES:
            a, b = arms['fixed1']['stages'][name], arms['used0']['stages'][name]
            deltas[name] = dict(whole=b['whole']['rms_dbfs'] - a['whole']['rms_dbfs'],
                               windows=[y['rms_dbfs'] - x['rms_dbfs'] for x, y in zip(a['windows'], b['windows'])],
                               byte_equal=(directory / 'fixed1' / (name + '.f32le')).read_bytes() ==
                                          (directory / 'used0' / (name + '.f32le')).read_bytes())
        cases.append(dict(case_id=c['case_id'], intake=summary(c), zero_reference=zero, arms=arms, deltas=deltas))
    require(zeros == 8, 'zero control cardinality')
    preflight(root)
    require(executable_lock == {name: sha((output / name).read_bytes()) for name in executable_lock},
            'measurement executable/library/header drift')
    require(initial == {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in dependencies}, 'measurement dependency drift')
    measured_sources = {n: sha((source / n).read_bytes()) for n in old['measurement_sources']}
    for name, function in RENAMES.items():
        data = (source / name).read_bytes()
        require(data.replace((function + '_d19_real(').encode(), (function + '(').encode()) ==
                (D18 / 'source' / name).read_bytes(), 'function body drift')
    require({n for n, v in measured_sources.items() if v != old['measurement_sources'][n]} == set(RENAMES), 'end source drift')
    result = dict(experiment='FE_DEVICE_STAGES_D19', decision='SAME_STATE_STAGE_DIAGNOSTIC_NO_PROMOTION',
                  executions=32, zero_controls=zeros, d18_byte_equal_arms=32, promotion_allowed=False,
                  shipping_approved=False, algorithm_changed=False, data_role='development', cases=cases)
    dump(output / 'result.json', result)
    dump(output / 'binding.json', dict(source_files=initial, d18_hashes=HASHES,
         d18_measurement_library_sha256=old['measurement_library_sha256'],
         measurement_library_sha256=sha((build / 'libaudio_pipeline.a').read_bytes()),
         executable_start_end=executable_lock,
         original_sources=old['measurement_sources'], measurement_sources=measured_sources,
         source_start_end_equal=True, input_start_end_equal=True,
         artifacts={str(f.relative_to(output)): sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}))
    print(result['decision'], '32 arms PASS', flush=True)


def read_json_bytes(value):
    from tools.codex_assets.device_capture import strict_json
    return strict_json(value.encode())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    created = []
    try:
        if args.dry_run:
            _, cases, _ = preflight(args.root)
            print('D19_PREFLIGHT_PASS', len(cases), 'cases; writes=False')
        else:
            run(args.root, args.output, created)
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        if created == [args.output]:
            failure = args.output / 'measurement-invalid.json'
            if not failure.exists():
                dump(failure, dict(decision='MEASUREMENT_INVALID', error=str(error)))
        print('device_stages: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
