"""Bounded public-API replay of locked development captures, never qualification."""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import (DECISION, PLAN, ROOT, PCM, arm_set, bounded, capture,
                                               intake, levels, plan, require, safe_file, sha, strict_json, summary)

RUNNER_SOURCE = ROOT / 'tests/validation/frontend_evolution/device_capture_runner.c'
FLAGS = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow', '-pedantic']
METRIC_FIELDS = {'frame', 'algorithmic_latency_ms', 'vad_probability', 'vad_active', 'far_end_active',
                 'double_talk_active', 'erle_db', 'erle_valid', 'aec_converged', 'estimated_delay_ms',
                 'delay_error_samples', 'delay_jumps', 'reference_sample_slips', 'aec_resets'}
CONFIG_FIELDS = {'profile', 'io_sample_rate_hz', 'internal_sample_rate_hz', 'mic_channels', 'mic_spacing_mm',
                 'aec_filter_ms', 'max_delay_ms', 'initial_delay_ms', 'aec_mu', 'aec_adapt_stride', 'ns_floor',
                 'agc_target_dbfs', 'limiter_dbfs', 'resource_class', 'stages', 'enable_delay_tracking',
                 'enable_clock_drift_compensation'}


def json_bytes(v) -> bytes:
    return (json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def write_json(path: Path, value) -> None:
    path.write_bytes(json_bytes(value))


def source_identity() -> dict:
    files = [ROOT / 'CMakeLists.txt', RUNNER_SOURCE, Path(__file__), Path(__file__).with_name('device_capture.py')]
    for directory in ('src', 'include', 'cmake'):
        files.extend(p for p in (ROOT / directory).rglob('*') if p.is_file())
    result = {}
    for p in sorted(set(files)):
        relative = str(p.relative_to(ROOT))
        p = safe_file(ROOT, relative)
        result[relative] = sha(bounded(p, 4 * 1024 * 1024))
    return result


def commands(output: Path) -> list[list[str]]:
    build = output / 'build'
    return [
        ['cmake', '-S', str(ROOT), '-B', str(build), '-DAP_BUILD_TESTS=OFF', '-DAP_BUILD_BENCH=OFF',
         '-DAP_BUILD_ALSA_EXAMPLE=OFF', '-DAP_STRICT_WARNINGS=ON'],
        ['cmake', '--build', str(build), '--target', 'ap_process_pcm', 'ap_build_info_dump', '-j', '2'],
        ['cc', *FLAGS, '-I', str(ROOT / 'include'), '-I', str(build / 'generated'), str(RUNNER_SOURCE),
         str(build / 'libaudio_pipeline.a'), '-lm', '-lpthread', '-o', str(output / 'runner')]
    ]


def run_logged(cmd: list[str], directory: Path, number: int, timeout: int = 300) -> str:
    limit = 1024 * 1024

    def record(stdout, stderr, exit_code, timed_out=False, execution_error=None):
        # TimeoutExpired may carry bytes even when text=True was requested.
        stdout = stdout.decode('utf-8', errors='replace') if isinstance(stdout, bytes) else stdout or ''
        stderr = stderr.decode('utf-8', errors='replace') if isinstance(stderr, bytes) else stderr or ''
        exceeded = len(stdout) + len(stderr) > limit
        kept_stdout = stdout[:limit]
        kept_stderr = stderr[:limit - len(kept_stdout)]
        write_json(directory / f'command-{number:03d}.json', dict(
            command=cmd, exit_code=exit_code, timeout_seconds=timeout, timed_out=timed_out,
            execution_error=execution_error, output_truncated=exceeded,
            stdout_characters=len(stdout), stderr_characters=len(stderr),
            stdout=kept_stdout, stderr=kept_stderr))
        return exceeded

    try:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        record(error.stdout, error.stderr, None, timed_out=True)
        raise
    except OSError as error:
        record('', '', None, execution_error=str(error))
        raise
    exceeded = record(result.stdout, result.stderr, result.returncode)
    require(not exceeded, 'command output exceeds bound; see command receipt')
    require(result.returncode == 0, f'command failed: {cmd[0]} exit={result.returncode}; see command receipt')
    return result.stdout


def check_config(config: dict, mode: str, default: dict) -> None:
    require(set(config) == CONFIG_FIELDS and set(default) == CONFIG_FIELDS, 'config fields drift')
    require(config['profile'] == default['profile'] == 'CALL' and config['io_sample_rate_hz'] == 16000 and
            config['mic_channels'] == 2, 'config geometry/profile drift')
    require(all(type(v) in (int, float) and math.isfinite(v) for k, v in config.items() if k != 'profile'),
            'invalid config numeric type')
    for k in CONFIG_FIELDS - {'profile', 'mic_spacing_mm', 'aec_mu', 'ns_floor', 'agc_target_dbfs', 'limiter_dbfs'}:
        require(type(config[k]) is int, 'integer config field required')
    expected = dict(default)
    if mode in ('tracked1', 'tracked1-no-drift', 'fixed1'):
        expected['initial_delay_ms'] = 1
        if mode in ('tracked1-no-drift', 'fixed1'):
            expected['enable_clock_drift_compensation'] = 0
        if mode == 'fixed1':
            expected['enable_delay_tracking'] = 0
    elif mode in ('bf-isolated', 'agc-isolated', 'ns-isolated'):
        expected['stages'] = {'bf-isolated': 2, 'ns-isolated': 160, 'agc-isolated': 64}[mode]
        expected['enable_delay_tracking'] = expected['enable_clock_drift_compensation'] = 0
    else:
        require(mode in ('default', 'sync-default-control'), 'unknown replay arm')
    require(config == expected, 'unregistered config change')
    require(default['initial_delay_ms'] == 40 and default['enable_delay_tracking'] == 1 and
            default['enable_clock_drift_compensation'] == 1 and default['stages'] == 255,
            'default baseline drift: new experiment required')


def metric_rows(path: Path, samples: int) -> list[dict]:
    data = bounded(path, 4 * 1024 * 1024)
    lines = data.splitlines()
    require(len(lines) == samples // 160, 'metric row count mismatch')
    rows = [strict_json(line) for line in lines]
    for i, r in enumerate(rows):
        require(set(r) == METRIC_FIELDS and type(r['frame']) is int and r['frame'] == i,
                'metric schema/index mismatch')
        require(all(type(v) in (int, float) and math.isfinite(v) for v in r.values()), 'nonfinite/invalid metrics')
        for k in ('vad_active', 'far_end_active', 'double_talk_active', 'erle_valid', 'aec_converged'):
            require(type(r[k]) is int and r[k] in (0, 1), 'invalid metric flag')
        for k in ('algorithmic_latency_ms', 'estimated_delay_ms', 'delay_jumps', 'reference_sample_slips', 'aec_resets'):
            require(type(r[k]) is int and 0 <= r[k] <= 1000000, 'invalid metric integer')
        require(0 <= r['vad_probability'] <= 1, 'invalid VAD probability')
    require(len({r['algorithmic_latency_ms'] for r in rows}) == 1, 'latency changed within arm')
    return rows


def pcm_file(path: Path, samples: int) -> PCM:
    data = bounded(path, 3 * 1024 * 1024)
    require(len(data) == samples * 2, 'output length mismatch')
    values = array('h'); values.frombytes(data)
    if sys.byteorder != 'little':
        values.byteswap()
    return PCM(data, 1, samples, values, sha(data))


def arm_status(entry: dict, samples: int, config_digest: str) -> None:
    require(entry.get('status') == 'success' and type(entry.get('exit_code')) is int and entry['exit_code'] == 0 and
            type(entry.get('samples')) is int and entry['samples'] == samples and
            entry.get('config_sha256') == config_digest, 'failed/stale output contract')


def window(c: dict, lo: int, hi: int, count: int, latency: int) -> tuple[int, int]:
    # Map scene monotonic time via captured PTS and per-file offsets, including startup.
    first, last = None, None
    for row in c['stage']:
        start_us = row['input_pts_us'] - c['scene_start']
        a = max(0, min(256, math.ceil((lo * 1000000 - start_us) * 16000 / 1000000)))
        b = max(0, min(256, math.ceil((hi * 1000000 - start_us) * 16000 / 1000000)))
        if a < b:
            require(row['output_valid'] == 1, 'invalid output in diagnostic window')
            start, end = row['file_sample_offset'] + a, row['file_sample_offset'] + b
            if first is None:
                first = start
            last = end
    require(first is not None and last is not None and first < last and last + latency <= count,
            'diagnostic window missing or beyond latency-paired prefix')
    return first, last


def measure(c: dict, y: PCM, metrics: list[dict], p: dict) -> dict:
    latency = metrics[0]['algorithmic_latency_ms'] * 16
    rows = []
    for lo, hi in p['primary_windows_seconds']:
        first, last = window(c, lo, hi, y.frames, latency)
        rows.append(dict(scene_time_s=[lo, hi], input_sample_range=[first, last],
                         output_sample_range=[first + latency, last + latency],
                         input=levels(c['mic'], first, last), output=levels(y, first + latency, last + latency)))
    return dict(whole_output=levels(y), windows=rows, algorithmic_latency_ms=latency // 16,
                estimated_delay_ms=sorted({r['estimated_delay_ms'] for r in metrics}),
                final_counters={k: metrics[-1][k] for k in ('delay_jumps', 'reference_sample_slips', 'aec_resets')},
                vad_active_fraction_whole_including_startup=sum(r['vad_active'] for r in metrics) / len(metrics),
                quality_authority='diagnostic-no-clean-target-no-FPR-FAR-ERLE-claim')


def binding(root: Path, path: Path) -> dict:
    return dict(path=str(path.relative_to(root)), sha256=sha(bounded(path, 64 * 1024 * 1024)), bytes=path.stat().st_size)


def verify_binding(root: Path, record: dict, maximum: int = 64 * 1024 * 1024) -> Path:
    require(set(record) == {'path', 'sha256', 'bytes'} and type(record['bytes']) is int and
            0 < record['bytes'] <= maximum, 'invalid file binding')
    p = safe_file(root, record['path'])
    data = bounded(p, maximum)
    require(len(data) == record['bytes'] and sha(data) == record['sha256'], 'evidence bytes/hash mismatch')
    return p


def verify(receipt: Path, capture_root: Path, plan_path: Path = PLAN) -> dict:
    r = strict_json(bounded(receipt, 4 * 1024 * 1024)); root = receipt.parent
    p, captures = intake(capture_root, plan_path)
    require(r.get('schema_version') == 1 and type(r['schema_version']) is int and
            r.get('status') == 'LOCAL_DIAGNOSTIC_COMPLETE' and r.get('decision') == DECISION and
            r.get('data_role') == 'development' and r.get('promotion_allowed') is False and
            r.get('hil_pass') is False and r.get('product_certified') is False, 'receipt authority/status')
    require(r.get('plan_sha256') == sha(bounded(plan_path, 65536)) and
            r.get('input_lock_sha256') == p['input_lock_sha256'] and r.get('source_files') == source_identity(),
            'plan/input/source identity mismatch')
    for record in r['build_files'].values():
        verify_binding(root, record)
    require(set(r['build_files']) == {'runner', 'library', 'cache', 'build_info'}, 'build identity set')
    require(set(r['configurations']) == set(arm for c in captures for arm in arm_set(c['session']['scene'])),
            'config set mismatch')
    configs = {}
    for mode, record in r['configurations'].items():
        path = verify_binding(root, record, 65536)
        configs[mode] = strict_json(bounded(path, 65536))
    for mode, cfg in configs.items():
        check_config(cfg, mode, configs['default'])
    expected = {c['case_id']: c for c in captures}
    require(isinstance(r.get('cases'), list) and len(r['cases']) == len(expected) and
            {row['case_id'] for row in r['cases']} == set(expected), 'missing/extra/duplicate cases')
    count = 0
    for case in r['cases']:
        c = expected[case['case_id']]
        require(case['intake'] == summary(c) and set(case['arms']) == set(arm_set(c['session']['scene'])),
                'case input/arm mismatch')
        n = summary(c)['replay_samples']
        require(set(case['adapted_inputs']) == {'mic', 'render'}, 'adapted input set mismatch')
        mic = bounded(verify_binding(root, case['adapted_inputs']['mic']), 3 * 1024 * 1024)
        render = bounded(verify_binding(root, case['adapted_inputs']['render']), 3 * 1024 * 1024)
        raw = array('h', c['raw'].samples[:n * 2:2])
        if sys.byteorder != 'little':
            raw.byteswap()
        require(mic == c['mic'].data[:n * 4] and render == raw.tobytes(), 'adapted input bytes mismatch')
        for mode, e in case['arms'].items():
            arm_status(e, n, r['configurations'][mode]['sha256'])
            y = pcm_file(verify_binding(root, e['output'], 3 * 1024 * 1024), n)
            metrics = metric_rows(verify_binding(root, e['metrics'], 4 * 1024 * 1024), n)
            require(e['measurement'] == measure(c, y, metrics, p), 'measurement does not match actual evidence')
            count += 1
        if 'sync-default-control' in case['arms']:
            require(case['arms']['default']['output']['sha256'] == case['arms']['sync-default-control']['output']['sha256'],
                    'default control mismatch')
        if c['session']['scene'] == 'quiet':
            require(case['arms']['default']['output']['sha256'] == case['arms']['fixed1']['output']['sha256'],
                    'zero-reference control mismatch')
    require(count == p['fixed_execution_count'] == 70, 'fixed execution count mismatch')
    first = r['cases'][0]
    require(set(r['repeats']) == {'default', 'bf-isolated'}, 'repeat control set')
    for mode, e in r['repeats'].items():
        require(type(e.get('exit_code')) is int and e['exit_code'] == 0, 'repeat failed')
        for role in ('output', 'metrics'):
            verify_binding(root, e[role], 4 * 1024 * 1024)
            require(e[role]['sha256'] == first['arms'][mode][role]['sha256'], 'repeat nondeterminism')
    return dict(status='RECEIPT_CONTRACT_PASS', cases=len(captures), fixed_executions=count,
                repeats=2, decision=DECISION, receipt_sha256=sha(receipt.read_bytes()))


def execute(capture_root: Path, output: Path, plan_path: Path = PLAN, dry_run: bool = False) -> dict:
    output = output.resolve(); capture_root = capture_root.resolve()
    require(not output.exists() and ROOT not in output.parents and output != ROOT and
            capture_root not in output.parents and output != capture_root, 'output must be new and outside source/input')
    p, captures = intake(capture_root, plan_path)
    source = source_identity()
    preflight = dict(status='PLANNED', writes=False, processor_executions=0, decision=DECISION,
                     fixed_executions=70, repeats=2, plan_sha256=sha(bounded(plan_path, 65536)),
                     source_files=source, input_cases=[summary(c) for c in captures], build_commands=commands(output))
    if dry_run:
        return preflight
    output.mkdir(parents=True, exist_ok=False)
    try:
        write_json(output / 'preflight.json', preflight)
        for i, cmd in enumerate(commands(output)):
            run_logged(cmd, output, i, 900)
        runner = output / 'runner'; configs_dir = output / 'config'; configs_dir.mkdir()
        configurations, descriptors = {}, {}
        modes = sorted(set(arm for c in captures for arm in arm_set(c['session']['scene'])))
        for i, mode in enumerate(modes, 10):
            text = run_logged([str(runner), '--describe', mode], output, i)
            cfg = strict_json(text.encode()); descriptors[mode] = cfg
            write_json(configs_dir / (mode + '.json'), cfg)
            configurations[mode] = binding(output, configs_dir / (mode + '.json'))
        for mode, cfg in descriptors.items():
            check_config(cfg, mode, descriptors['default'])
        info = run_logged([str(output / 'build/ap_build_info_dump')], output, 30)
        (output / 'build-info.txt').write_text(info)
        r = dict(schema_version=1, status='LOCAL_DIAGNOSTIC_COMPLETE', decision=DECISION,
                 data_role='development', promotion_allowed=False, hil_pass=False, product_certified=False,
                 plan_sha256=preflight['plan_sha256'], input_lock_sha256=p['input_lock_sha256'], source_files=source,
                 configurations=configurations, cases=[], repeats={},
                 build_files={k: binding(output, path) for k, path in
                              (('runner', runner), ('library', output / 'build/libaudio_pipeline.a'),
                               ('cache', output / 'build/CMakeCache.txt'), ('build_info', output / 'build-info.txt'))})
        for number, c in enumerate(captures, 1):
            d = output / f'case-{number:02d}'; d.mkdir()
            brief = summary(c); n = brief['replay_samples']
            (d / 'mic.pcm').write_bytes(c['mic'].data[:n * 4])
            raw = array('h', c['raw'].samples[:n * 2:2])
            if sys.byteorder != 'little':
                raw.byteswap()
            (d / 'render.pcm').write_bytes(raw.tobytes())
            case = dict(case_id=c['case_id'], intake=brief, arms={},
                        adapted_inputs={k: binding(output, d / (k + '.pcm')) for k in ('mic', 'render')})
            for mode in brief['arms']:
                ypath, mpath = d / (mode + '.pcm'), d / (mode + '.jsonl')
                run_logged([str(runner), mode, str(d / 'mic.pcm'), str(d / 'render.pcm'), str(ypath), str(mpath)],
                           d, len(case['arms']))
                y = pcm_file(ypath, n); m = metric_rows(mpath, n)
                case['arms'][mode] = dict(status='success', exit_code=0, samples=n,
                    config_sha256=configurations[mode]['sha256'], output=binding(output, ypath),
                    metrics=binding(output, mpath), measurement=measure(c, y, m, p))
            if number == 1:
                for i, mode in enumerate(('default', 'bf-isolated'), 20):
                    ypath, mpath = d / (mode + '-repeat.pcm'), d / (mode + '-repeat.jsonl')
                    run_logged([str(runner), mode, str(d / 'mic.pcm'), str(d / 'render.pcm'), str(ypath), str(mpath)], d, i)
                    r['repeats'][mode] = dict(exit_code=0, output=binding(output, ypath), metrics=binding(output, mpath))
            r['cases'].append(case)
            print(json.dumps(dict(case=number, scene=c['session']['scene'], arms=len(case['arms']),
                                  status='replayed')), flush=True)
        require(source_identity() == source, 'source changed during build/replay')
        staged = output / 'receipt.partial.json'; write_json(staged, r)
        verdict = verify(staged, capture_root, plan_path)
        staged.replace(output / 'receipt.json')
        write_json(output / 'verification.json', {**verdict, 'receipt_sha256': sha((output / 'receipt.json').read_bytes())})
        return verdict
    except Exception as exc:
        write_json(output / 'failure.json', dict(status='FAILED_NO_SUCCESS_RECEIPT', error=str(exc),
                                               decision=DECISION, promotion_allowed=False))
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('run', 'verify'):
        item = sub.add_parser(name)
        item.add_argument('--root', type=Path, required=True)
        item.add_argument('--plan', type=Path, default=PLAN)
        if name == 'run':
            item.add_argument('--output', type=Path, required=True)
            item.add_argument('--dry-run', action='store_true')
        else:
            item.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = execute(args.root, args.output, args.plan, args.dry_run) if args.command == 'run' else verify(
            args.receipt, args.root, args.plan)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print('device_replay: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
