"""D18 fixed captured-reference coordinates, never shipping or acoustic authority."""
from __future__ import annotations

import argparse
from array import array
import json
from pathlib import Path
import shutil
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, PLAN, bounded, intake, require, sha, strict_json, summary
from tools.codex_assets.device_replay import FLAGS, measure, metric_rows, pcm_file, verify_binding
from tools.codex_assets.device_alignment import s16_bytes, shifted

LIB_SHA = '4a748de3501241ff66787c8fdb4ccf445126ae49b1be3c4420b7e15e1ffb1170'
RECEIPT_SHA = '2a1ed561e142a991b9c5679b35df0e44f12ab32ecc6e3e67c42e4582377f85f2'
D17 = Path('/tmp/audio-fe-device-alignment-d17-20261011')
D17_HASHES = {'result.json': '8d587b8975abb7311b480fa5688f04901af582b02e0e919e07f71dbd9e50bb06',
              'binding.json': '400b7963fe0d16485496405ededaa1ede4f41e6c6d9874ab7dc4819f9924cb8e'}
RUNNER = ROOT / 'tests/validation/frontend_evolution/device_exact_reference_d18.c'
REPEATS = {'vocaltest_rpm240/runs/run-2908630469-2466', 'vocaltest_rpm480/runs/run-4874838670-2672'}


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def read_json(path, maximum=4 * 1024 * 1024):
    return strict_json(bounded(path, maximum))


def logged(output, name, command, cwd, expected=0, timeout=120):
    path = output / ('command-' + name + '.json')
    require(not path.exists(), 'command receipt already exists')
    r = subprocess.run(['rtk', *command], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    dump(path, dict(command=['rtk', *command], cwd=str(cwd), exit_code=r.returncode,
                    stdout=r.stdout, stderr=r.stderr))
    require(r.returncode == expected, 'command failed: ' + name + ': ' + r.stderr[-1000:])
    print(name, 'exit', r.returncode, flush=True)
    return r.stdout


def preflight(root, base):
    require(all(sha(bounded(D17 / n, 4 * 1024 * 1024)) == v for n, v in D17_HASHES.items()), 'D17 dependency drift')
    receipt = base / 'replay/receipt.json'
    require(sha(bounded(receipt, 4 * 1024 * 1024)) == RECEIPT_SHA, 'D16 receipt drift')
    old = read_json(receipt)
    require(sha(bounded(base / 'build/libaudio_pipeline.a', 4 * 1024 * 1024)) == LIB_SHA, 'D16 library drift')
    require(all(sha(bounded(base / 'source' / n, 4 * 1024 * 1024)) == v
                for n, v in old['source_files'].items()), 'D16 source drift')
    p, captures = intake(root)
    records = {c['case_id']: c for c in old['cases']}
    require(len(records) == len(old['cases']) == len(captures) == 16, 'case cardinality')
    require(set(records) == {c['case_id'] for c in captures}, 'case set')
    for c in captures:
        require(records[c['case_id']]['intake'] == summary(c) and c['session']['ref_delay_samples'] == 20,
                'input/capture coordinate drift')
    old_fixed = read_json(verify_binding(base / 'replay', old['configurations']['fixed1'], 65536))
    return p, captures, old, old_fixed


def run(root, base, output):
    p, captures, old, old_fixed = preflight(root, base)
    require(not output.exists() and not output.is_symlink() and
            Path('/tmp') in output.resolve().parents, 'new /tmp output required')
    sources = [RUNNER, Path(__file__), ROOT / 'tools/codex_assets/device_capture.py',
               ROOT / 'tools/codex_assets/device_replay.py', ROOT / 'tools/codex_assets/device_alignment.py',
               ROOT / 'docs/research/frontend-evolution-v1/DEVICE_EXACT_REFERENCE_D18_PLAN.zh-CN.md',
               ROOT / 'docs/research/frontend-evolution-v1/DEVICE_EXACT_REFERENCE_D18_AMENDMENT.zh-CN.md', PLAN,
               ROOT / '.github/research/frontend-evolution-v1/device-capture-d0-input-lock.json',
               D17 / 'result.json', D17 / 'binding.json', base / 'replay/receipt.json']
    initial = {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in sources}
    output.mkdir()
    source, build = output / 'source', output / 'build'
    shutil.copytree(base / 'source', source)
    sync = source / 'src/sync/ap_sync.c'
    original = sync.read_bytes()
    needle = b'int ap_sync_get_reference(ap_sync_state_t *s, uint32_t frame_samples, float *out) {'
    require(original.count(needle) == 1, 'definition not unique')
    sync.write_bytes(original.replace(needle, needle.replace(b'ap_sync_get_reference(', b'ap_sync_get_reference_d18_real(')))
    require([n for n, v in old['source_files'].items() if sha(bounded(source / n, 4 * 1024 * 1024)) != v]
            == ['src/sync/ap_sync.c'], 'unexpected measurement source change')
    logged(output, 'configure', ['cmake', '-S', str(source), '-B', str(build), '-DAP_BUILD_TESTS=ON',
           '-DAP_BUILD_BENCH=OFF', '-DAP_STRICT_WARNINGS=ON'], ROOT, timeout=300)
    logged(output, 'build', ['cmake', '--build', str(build), '--target', 'audio_pipeline', '-j', '2'], ROOT, timeout=300)
    header = 'generated/audio_pipeline/audio_pipeline_build.h'
    require((build / header).read_bytes() == (base / 'build' / header).read_bytes(), 'generated header drift')
    common = ['cc', *FLAGS, '-I', str(source / 'src'), '-I', str(source / 'include'), '-I', str(build / 'generated')]
    for label, observing, library in (('observe', 1, build / 'libaudio_pipeline.a'),
                                     ('plain', 0, base / 'build/libaudio_pipeline.a')):
        logged(output, label + '-compile', common + ['-DD18_OBSERVER=' + str(observing), str(RUNNER),
               str(library), '-lm', '-lpthread', '-o', str(output / label)], ROOT)
        require('3200 samples PASS' in logged(output, label + '-known', [str(output / label), '--self-test'], ROOT),
                'known-answer marker missing')
        logged(output, label + '-invalid', [str(output / label), 'invalid'], ROOT, expected=2)
    cfg = {}
    for mode in ('fixed1', 'used0'):
        cfg[mode] = strict_json(logged(output, mode + '-describe', [str(output / 'observe'), '--describe', mode], ROOT).encode())
        expected = dict(old_fixed)
        if mode == 'used0':
            expected['initial_delay_ms'] = 0
        require(cfg[mode] == expected, 'unregistered config difference')
        dump(output / (mode + '-config.json'), cfg[mode])
    records = {c['case_id']: c for c in old['cases']}
    cases = []
    repeat_count = fixed_controls = zero_controls = 0
    for index, c in enumerate(captures):
        directory = output / ('case-' + str(index + 1).zfill(2))
        directory.mkdir()
        n = summary(c)['replay_samples']
        raw = c['raw'].samples[::2]
        (directory / 'mic.pcm').write_bytes(c['mic'].data[:n * 4])
        (directory / 'raw.pcm').write_bytes(s16_bytes(raw[:n]))
        (directory / 'used.pcm').write_bytes(c['ref'].data[:n * 2])
        require(c['ref'].data[:n * 2] == s16_bytes(shifted(raw, 20)[:n]), 'used coordinate mismatch')
        measurements, rows = {}, {}
        for mode, render in (('fixed1', 'raw'), ('used0', 'used')):
            stem = directory / mode
            cmd = [mode, str(directory / 'mic.pcm'), str(directory / (render + '.pcm')),
                   str(stem.with_suffix('.pcm')), str(stem.with_suffix('.jsonl'))]
            result = strict_json(logged(output, str(index + 1) + '-' + mode,
                     [str(output / 'observe'), *cmd, str(stem.with_suffix('.reference.f32le'))], ROOT).encode())
            require(result == dict(frames=n // 160, render_underruns=1 if mode == 'fixed1' else 0), 'frame/startup summary')
            expected_s16 = shifted(raw, 16)[:n] if mode == 'fixed1' else c['ref'].samples[:n]
            floats = array('f', (value / 32768.0 for value in expected_s16))
            if sys.byteorder != 'little':
                floats.byteswap()
            require(stem.with_suffix('.reference.f32le').read_bytes() == floats.tobytes(), 'actual reference mismatch')
            rows[mode] = metric_rows(stem.with_suffix('.jsonl'), n)
            require(all(all(row[k] == 0 for k in ('delay_jumps', 'reference_sample_slips', 'aec_resets'))
                        for row in rows[mode]), 'fixed coordinate counter event')
            measurements[mode] = dict(summary=result, measurement=measure(c, pcm_file(stem.with_suffix('.pcm'), n), rows[mode], p))
            if mode == 'fixed1' and 'fixed1' in records[c['case_id']]['arms']:
                previous = records[c['case_id']]['arms']['fixed1']
                require(stem.with_suffix('.pcm').read_bytes() == verify_binding(base / 'replay', previous['output']).read_bytes()
                        and stem.with_suffix('.jsonl').read_bytes() == verify_binding(base / 'replay', previous['metrics']).read_bytes(),
                        'old fixed1 byte equivalence failed')
                fixed_controls += 1
            if c['case_id'] in REPEATS:
                repeat_cmd = [mode, cmd[1], cmd[2], str(directory / (mode + '-repeat.pcm')),
                              str(directory / (mode + '-repeat.jsonl'))]
                repeated = strict_json(logged(output, str(index + 1) + '-' + mode + '-repeat',
                          [str(output / 'plain'), *repeat_cmd], ROOT).encode())
                require(repeated == result and (directory / (mode + '-repeat.pcm')).read_bytes() == stem.with_suffix('.pcm').read_bytes()
                        and (directory / (mode + '-repeat.jsonl')).read_bytes() == stem.with_suffix('.jsonl').read_bytes(),
                        'original-library observer neutrality failed')
                repeat_count += 1
        left = (directory / 'fixed1.pcm').read_bytes()
        right = (directory / 'used0.pcm').read_bytes()
        if not any(raw):
            require(left == right, 'zero-reference output changed')
            require(all({k: v for k, v in a.items() if k != 'estimated_delay_ms'} ==
                        {k: v for k, v in b.items() if k != 'estimated_delay_ms'}
                        for a, b in zip(rows['fixed1'], rows['used0'])), 'zero-reference JSONL fields changed')
            zero_controls += 1
        a, b = array('h'), array('h')
        a.frombytes(left); b.frombytes(right)
        require(len(a) == len(b) == n, 'PCM sample count')
        cases.append(dict(case_id=c['case_id'], intake=summary(c), arms=measurements, pcm_byte_equal=left == right,
                          pcm_mismatched_samples=sum(x != y for x, y in zip(a, b))))
    require((fixed_controls, zero_controls, repeat_count) == (10, 8, 4), 'control execution set')
    preflight(root, base)
    require(initial == {str(f): sha(bounded(f, 4 * 1024 * 1024)) for f in sources}, 'measurement tool/source drift')
    result = dict(experiment='FE_DEVICE_EXACT_REFERENCE_D18', decision='EXACT_REFERENCE_DIAGNOSTIC_NO_PROMOTION',
                  promotion_allowed=False, shipping_approved=False, data_role='development', algorithm_changed=False,
                  executions=36, fixed1_controls=fixed_controls, zero_controls=zero_controls, original_library_repeats=repeat_count,
                  cases=cases)
    dump(output / 'result.json', result)
    artifacts = {str(f.relative_to(output)): sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}
    dump(output / 'binding.json', dict(source_files=initial, artifacts=artifacts, original_library_sha256=LIB_SHA,
         measurement_library_sha256=sha((build / 'libaudio_pipeline.a').read_bytes()), original_receipt_sha256=RECEIPT_SHA,
         original_sources=old['source_files'], measurement_sources={n: sha((source / n).read_bytes()) for n in old['source_files']},
         source_start_end_equal=True, input_start_end_equal=True))
    print(json.dumps(dict(decision=result['decision'], executions=36, result_sha256=sha((output / 'result.json').read_bytes()),
                         binding_sha256=sha((output / 'binding.json').read_bytes()))), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            _, cases, _, _ = preflight(args.root, args.base)
            print(json.dumps(dict(status='D18_PREFLIGHT_PASS', cases=len(cases), writes=False)))
        else:
            run(args.root, args.base, args.output)
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print('device_exact_reference: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
