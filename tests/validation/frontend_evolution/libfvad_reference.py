#!/usr/bin/env python3
"""Pinned libfvad byte admission and reference execution, never a shipping gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
from pathlib import Path
import sys

from contracts import (ROOT, B0, FrameContract, admit_execution, check_outputs,
                       hex_digest, load_json, require, sha256, verified_file)

LOCK = ROOT / '.github/research/frontend-evolution-v1/libfvad-source-lock.json'


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def source_preflight(source: Path, output: Path) -> dict:
    """Copy ONLY verified compile inputs to a clean directory; execute nothing."""
    lock = load_json(LOCK)
    expected = lock['git_blob_sha1']
    require(lock['upstream_commit'] == '532ab666c20d3cfda38bca63abbb0f152706c369', 'unexpected source pin')
    require(not output.exists(), 'refuse to reuse source/evidence directory')
    actual = {p.relative_to(source).as_posix() for part in ('src', 'include')
              for p in (source / part).rglob('*') if p.suffix in ('.c', '.h')}
    require(actual == {name for name in expected if name.endswith(('.c', '.h'))}, 'source/header set mismatch')
    inputs = {}
    for name, wanted in expected.items():
        path = verified_file(source, name)
        data = path.read_bytes()
        require(git_blob(data) == wanted, f'upstream blob mismatch: {name}')
        inputs[name] = data
    output.mkdir(parents=True)
    for name, data in inputs.items():
        path = output / 'upstream' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    hashes = {name: sha256(data) for name, data in sorted(inputs.items())}
    materialized = sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode())
    record = {'schema_version': 1, 'source_id': 'libfvad',
              'source_commit': lock['upstream_commit'], 'files_sha256': hashes,
              'materialized_source_sha256': materialized, 'source_lock_sha256': sha256(LOCK.read_bytes()),
              'status': 'SOURCE_BYTES_VERIFIED_NOT_EXECUTED', 'scope': lock['scope'],
              'rights_review': lock['rights_review'], 'shipping_authority': False}
    write_json(output / 'source-receipt.json', record)
    return record


PLAN = ROOT / '.github/research/frontend-evolution-v1/libfvad-reference-v1.json'
ADMISSION = ROOT / '.github/research/frontend-evolution-v1/libfvad-admission.json'
CATALOG = ROOT / '.github/research/frontend-evolution-v1/sources.json'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'validation/tools'))
import run_validation
from run_validation_engine import vad_stats


def git_tree(path: Path) -> str:
    """Recompute exact Git tree without filters, index, checkout or credentials."""
    def object_hash(kind: bytes, data: bytes) -> bytes:
        return hashlib.sha1(kind + b' ' + str(len(data)).encode() + b'\0' + data).digest()
    def visit(directory: Path) -> bytes:
        entries = []
        for child in directory.iterdir():
            mode = child.lstat().st_mode
            require(not stat.S_ISLNK(mode), 'symlink in baseline tree')
            name = os.fsencode(child.name)
            if stat.S_ISDIR(mode):
                entries.append((name + b'/', b'40000 ' + name + b'\0' + visit(child)))
            else:
                require(stat.S_ISREG(mode), 'special baseline file')
                permission = b'100755' if mode & 0o111 else b'100644'
                entries.append((name, permission + b' ' + name + b'\0' + object_hash(b'blob', child.read_bytes())))
        return object_hash(b'tree', b''.join(data for _, data in sorted(entries)))
    return visit(path).hex()


def check_admission(record: dict) -> dict:
    source = admit_execution(load_json(CATALOG), 'libfvad')
    require(source['admission_receipt_sha256'] == sha256(ADMISSION.read_bytes()), 'admission receipt changed')
    reviewed = load_json(ADMISSION)
    require(reviewed['admission']['decision'] == 'EXECUTION_ADMITTED_MINIMAL_REFERENCE_ONLY', 'not admitted')
    for key in ('files_sha256', 'source_commit', 'materialized_source_sha256', 'source_lock_sha256', 'scope'):
        require(record[key] == reviewed[key], f'materialized admission mismatch: {key}')
    require(record['materialized_source_sha256'] == source['materialized_source_sha256'], 'catalog source mismatch')
    require(record['source_commit'] == source['commit'], 'catalog revision mismatch')
    return source


def strict_trace(path: Path, count: int, mode: int | None = None) -> list[dict]:
    rows = []
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate trace key')
            result[key] = value
        return result
    for i, line in enumerate(path.read_text().splitlines()):
        row = json.loads(line, object_pairs_hook=pairs)
        require(isinstance(row, dict) and type(row.get('frame')) is int and row['frame'] == i, 'frame index drift')
        require(type(row.get('vad_active')) is int and row['vad_active'] in (0, 1), 'invalid VAD decision')
        require(all(type(v) in (int, float) and math.isfinite(v) for v in row.values()), 'non-finite/non-numeric trace')
        if mode is not None:
            require(type(row.get('mode')) is int and row['mode'] == mode, 'mode drift')
            require(type(row.get('decision_available_after_samples')) is int and
                    row['decision_available_after_samples'] == (i + 1) * 160, 'decision availability drift')
        rows.append(row)
    require(len(rows) == count and count > 0, 'trace/label frame count mismatch')
    return rows


def checked_stats(labels: list[int], rows: list[dict]) -> dict:
    require(len(labels) == len(rows) and bool(labels), 'label/trace length mismatch')
    require(all(type(x) is int and x in (0, 1) for x in labels), 'invalid labels')
    require(all(type(r.get('vad_active')) is int and r['vad_active'] in (0, 1) for r in rows), 'invalid decisions')
    stats = vad_stats(labels, rows)  # One canonical metric; no duplicated formula.
    return {'frames': len(labels), 'positive_frames': sum(labels),
            'negative_frames': len(labels) - sum(labels), **stats}


def select_mode(baseline: dict, modes: dict[int, dict]) -> int | None:
    require(set(modes) == {0, 1, 2, 3}, 'four preregistered modes required')
    for result in [baseline, *modes.values()]:
        require(result['positive_frames'] > 0 and result['negative_frames'] > 0, 'calibration needs both classes')
        for key in ('recall', 'false_positive_rate'):
            require(type(result[key]) in (float, int) and math.isfinite(result[key]) and 0 <= result[key] <= 1, 'invalid metric')
    feasible = [m for m, r in modes.items() if r['recall'] >= baseline['recall']]
    return min(feasible, key=lambda m: (modes[m]['false_positive_rate'], m)) if feasible else None


def process_env(home: Path) -> dict:
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LC_ALL': 'C', 'HOME': str(home),
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}


def run_logged(command: list, log: Path, timeout: int = 120) -> None:
    # No inherited tokens, credentials, preload or PYTHONPATH for external builds.
    env = process_env(log.parent)
    with log.open('w') as stream:
        result = subprocess.run(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT,
                                env=env, cwd=ROOT, timeout=timeout, check=False)
    require(result.returncode == 0, f'command failed ({result.returncode}): {command[0]}; see {log}')


def execute_case(binary: Path, mode: int | None, mic: Path, labels: list[int], dest: Path,
                 identity: dict) -> tuple[dict, list[dict]]:
    dest.mkdir(parents=True, exist_ok=False)
    data = mic.read_bytes()
    require(len(data) == len(labels) * 320 and bool(labels), 'input/label sample count mismatch')
    output, trace = dest / 'output.pcm', dest / 'trace.jsonl'
    if mode is None:
        command = [binary, '--sample-rate', '16000', '--mic-channels', '1', '--capture-only',
                   '--capture-profile', 'vad-isolated', '--metrics-jsonl', trace, mic, output]
    else:
        command = [binary, mode, mic, output, trace]
    run_logged(command, dest / 'process.log', 30)
    rows = strict_trace(trace, len(labels), mode)
    key = dest.name
    receipt = {'case_id': key, 'exit_code': 0, 'status': 'SUCCESS', 'identity': identity,
               'input_sha256': sha256(data), 'output_path': 'output.pcm',
               'output_sha256': sha256(output.read_bytes()), 'trace_sha256': sha256(trace.read_bytes())}
    expected = {key: {'input_sha256': sha256(data), 'output_samples': len(data) // 2,
                      'require_nonzero': any(x[0] for x in struct.iter_unpack('<h', data))}}
    check_outputs(expected, [receipt], dest, FrameContract(16000, 1, 0, 160, (0,)), identity)
    require(output.read_bytes() == data, 'VAD-only adapter changed audio samples')
    write_json(dest / 'receipt.json', receipt)
    return checked_stats(labels, rows), rows


def probe_adapter(binary: Path, output: Path, label: str = 'adapter-tests') -> dict:
    probe = output / label; probe.mkdir()
    run_logged([binary, '--self-test'], probe / 'self-test.log')
    x = [((i * 193) % 10000) - 5000 for i in range(160 * 20)]
    a = struct.pack('<%dh' % len(x), *x)
    b = a[:160 * 10 * 2] + bytes(160 * 10 * 2)
    traces = []
    for name, payload in (('a', a), ('b', b)):
        mic = probe / (name + '.pcm'); mic.write_bytes(payload)
        target, trace = probe / (name + '-out.pcm'), probe / (name + '.jsonl')
        run_logged([binary, 2, mic, target, trace], probe / (name + '.log'))
        require(target.read_bytes() == payload, 'adapter transparency failed')
        traces.append(strict_trace(trace, 20, 2))
    require(traces[0][:10] == traces[1][:10], 'VAD prefix depends on future frames')
    for name, payload, mode in (('empty', b'', '0'), ('partial', a[:-1], '0'), ('mode', a, '4')):
        mic = probe / (name + '.pcm'); mic.write_bytes(payload)
        result = subprocess.run([str(binary), mode, str(mic), str(probe / (name + '-out.pcm')),
                                 str(probe / (name + '.jsonl'))], capture_output=True, timeout=10, env=process_env(probe))
        require(result.returncode != 0, 'invalid adapter input accepted')
        (probe / (name + '.log')).write_bytes(result.stderr)
    return {'reset_rate_mode_replay': 'PASS', 'transparent_pcm': 'PASS',
            'stable_prefix_frames': 10, 'negative_cli_cases': 3,
            'limits': 'finite cases; decisions are available after the full 10 ms frame'}


def seal_output(root: Path, report: dict) -> None:
    files = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in sorted(root.rglob('*'))
             if p.is_file() and p.relative_to(root).as_posix() not in ('manifest.json', 'SHA256SUMS')}
    write_json(root / 'manifest.json', {'schema_version': 1, 'files': files,
                                       'experiment_id': report['experiment_id'], 'shipping_authority': False})
    (root / 'SHA256SUMS').write_text(''.join(f'{sha256(p.read_bytes())}  {p.relative_to(root).as_posix()}\n'
        for p in sorted(root.rglob('*')) if p.is_file() and p != root / 'SHA256SUMS'))


def verify_output(root: Path, execution_source: str | None = None) -> dict:
    require(not (root / 'failure.json').exists(), 'failed evidence cannot pass')
    require(all(not p.is_symlink() for p in root.rglob('*')), 'symlink evidence forbidden')
    manifest = load_json(root / 'manifest.json')
    actual = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in root.rglob('*')
              if p.is_file() and p.relative_to(root).as_posix() not in ('manifest.json', 'SHA256SUMS')}
    require(actual == manifest['files'] and bool(actual), 'evidence file set/hash mismatch')
    sums = {}
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        require(name not in sums, 'duplicate checksum')
        sums[name] = digest
    require(sums == {**actual, 'manifest.json': sha256((root / 'manifest.json').read_bytes())}, 'checksum set mismatch')
    report = load_json(root / 'result.json')
    if execution_source is not None:
        require(hex_digest(execution_source, 40) and report['execution_source_revision'] == execution_source, 'stale execution SHA')
    require(report['status'] == 'REFERENCE_EXECUTION_PASS' and report['shipping_authority'] is False, 'wrong authority')
    plan = load_json(root / 'experiment.json')
    require(plan == load_json(PLAN), 'experiment contract drift')
    require(plan['baseline_source'] == B0 and plan['shipping_authority'] is False, 'invalid experiment identity')
    record = load_json(root / 'source-receipt.json')
    reviewed = load_json(root / 'admission.json')
    require((root / 'admission.json').read_bytes() == ADMISSION.read_bytes(), 'unreviewed admission receipt')
    require((root / 'source-lock.json').read_bytes() == LOCK.read_bytes(), 'source lock drift')
    check_admission(record)
    require(report['experiment_id'] == plan['experiment_id'] and report['authority'] == plan['authority']
            and report['dataset_role'] == plan['dataset_role'], 'report authority mismatch')
    expected_sources = {'b0': B0, 'libfvad': reviewed['source_commit']}
    cfg_digest = sha256((root / 'experiment.json').read_bytes())
    evaluator_digest = sha256((ROOT / 'validation/tools/run_validation_engine.py').read_bytes())
    for name, source_sha in expected_sources.items():
        identity = report['identities'][name]
        require(identity['source_sha'] == source_sha and identity['config_sha256'] == cfg_digest
                and identity['evaluator_sha256'] == evaluator_digest, 'reference identity mismatch')
    require(report['b0_build_info'].get('AP_BUILD_SOURCE_REVISION') == B0, 'baseline build identity mismatch')
    for name, digest in report['control_files_sha256'].items():
        require(sha256(verified_file(ROOT, name).read_bytes()) == digest, 'control code drift')
    require(record['files_sha256'] == reviewed['files_sha256'] and
            record['materialized_source_sha256'] == reviewed['materialized_source_sha256'], 'source receipt mismatch')
    for name, digest in record['files_sha256'].items():
        require(sha256(verified_file(root / 'upstream', name).read_bytes()) == digest, 'upstream bytes changed')
    for name, filename in (('b0', 'b0-process-pcm'), ('libfvad', 'libfvad-runner')):
        require(report['identities'][name]['processor_sha256'] == sha256((root / filename).read_bytes()), 'binary mismatch')
    selection = load_json(root / 'frozen-selection.json')
    require(selection == report['calibration']['selection'] and report['frozen_selection_sha256'] ==
            sha256((root / 'frozen-selection.json').read_bytes()), 'frozen selection mismatch')
    chosen = selection['mode']
    cfg_sha = sha256((root / 'experiment.json').read_bytes())
    expected_directories = set()
    def recompute(section, seeds, modes):
        rows = report[section]['cases']
        expected_cases = {(seed, case) for seed in seeds for case in plan['case_ids']}
        require(len(rows) == len(expected_cases) and {(r['seed'], r['case_id']) for r in rows} == expected_cases,
                'missing/duplicate/extra cases')
        pooled = {m: ([], []) for m in [None, *modes]}
        for row in rows:
            directory = root / 'cases' / str(row['seed']) / row['case_id']
            expected_directories.add(directory)
            labels = [int(x) for x in (directory / 'vad.labels').read_text().splitlines()]
            data = (directory / 'mic.pcm').read_bytes()
            require(len(data) == len(labels) * 320, 'input/label size mismatch')
            expected_arms = {'b0', *[f'libfvad-{m}' for m in modes]}
            require(set(row['arms']) == expected_arms, 'arm set mismatch')
            require({p.name for p in directory.iterdir() if p.is_dir()} == expected_arms, 'unexpected arm directory')
            for mode in [None, *modes]:
                name = 'b0' if mode is None else f'libfvad-{mode}'
                dest = directory / name
                trace = strict_trace(dest / 'trace.jsonl', len(labels), mode)
                identity = dict(report['identities']['b0' if mode is None else 'libfvad'])
                identity['config_sha256'] = sha256(json.dumps({'plan': cfg_sha, 'mode': mode}, sort_keys=True).encode())
                receipt = load_json(dest / 'receipt.json')
                expected = {name: {'input_sha256': sha256(data), 'output_samples': len(data) // 2,
                                   'require_nonzero': any(x[0] for x in struct.iter_unpack('<h', data))}}
                check_outputs(expected, [receipt], dest, FrameContract(16000, 1, 0, 160, (0,)), identity)
                require(receipt['trace_sha256'] == sha256((dest / 'trace.jsonl').read_bytes()), 'trace receipt mismatch')
                require((dest / 'output.pcm').read_bytes() == data, 'VAD audio transparency changed')
                require(checked_stats(labels, trace) == row['arms'][name], 'stored metric mismatch')
                pooled[mode][0].extend(labels); pooled[mode][1].extend(trace)
        return {m: checked_stats(*values) for m, values in pooled.items()}
    totals = recompute('calibration', [plan['calibration_seed']], plan['modes'])
    require(totals[None] == selection['b0'] and
            {str(m): totals[m] for m in plan['modes']} == selection['modes'], 'calibration totals mismatch')
    require(select_mode(totals[None], {m: totals[m] for m in plan['modes']}) == chosen, 'selection rule violated')
    totals = recompute('evaluation', plan['evaluation_seeds'], [chosen] if chosen is not None else [])
    require({('b0' if m is None else f'libfvad-{m}'): v for m, v in totals.items()} == report['evaluation']['totals'],
            'evaluation totals mismatch')
    require({p.parent for p in (root / 'cases').glob('*/*/mic.pcm')} == expected_directories, 'extra case directory')
    expected_decision = 'NO_PROMOTION_D0_REFERENCE_ONLY' if chosen is not None else plan['unmatched']
    require(report['decision'] == expected_decision, 'unqualified promotion decision')
    return {'status': 'EVIDENCE_VERIFIED', 'files': len(actual), 'decision': report['decision']}


def compare(source: Path, baseline: Path, output: Path, execution_source: str | None = None) -> dict:
    plan = load_json(PLAN)
    if execution_source is not None:
        require(hex_digest(execution_source, 40), 'full execution SHA required')
        observed = subprocess.check_output(['git', '-c', f'safe.directory={ROOT}', 'rev-parse', 'HEAD'],
                                           cwd=ROOT, text=True).strip()
        require(observed == execution_source, 'execution checkout SHA mismatch')
        subprocess.run(['git', '-c', f'safe.directory={ROOT}', 'diff', '--exit-code', 'HEAD', '--',
                        'tests/validation/frontend_evolution', '.github/research/frontend-evolution-v1',
                        'validation/tools', 'validation/authority.json'], cwd=ROOT, check=True)
    require(plan['baseline_source'] == B0 and plan['sample_rate_hz'] == 16000 and plan['hop_samples'] == 160, 'plan geometry drift')
    require(plan['authority'] == 'REGRESSION_ADAPTER_QUALIFICATION_NO_PROMOTION', 'wrong experiment authority')
    require(git_tree(baseline) == plan['baseline_tree'], 'baseline source tree mismatch')
    record = source_preflight(source, output)
    admitted = check_admission(record)
    for src, name in ((PLAN, 'experiment.json'), (ADMISSION, 'admission.json'), (LOCK, 'source-lock.json')):
        shutil.copy2(src, output / name)
    cc = shutil.which('cc'); require(cc is not None, 'C compiler required')
    upstream = output / 'upstream'
    sources = [upstream / n for n in sorted(record['files_sha256']) if n.endswith('.c')]
    runner = output / 'libfvad-runner'
    run_logged([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Wpedantic', '-Werror',
                '-I' + str(upstream / 'include'), '-I' + str(upstream / 'src'),
                HERE / 'libfvad_runner.c', *sources, '-o', runner], output / 'libfvad-build.log')
    run_logged([cc, '--version'], output / 'compiler.txt')
    adapter_tests = {'native': probe_adapter(runner, output)}
    sanitized = output / 'libfvad-runner-sanitized'
    run_logged([cc, '-std=c11', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-I' + str(upstream / 'include'), '-I' + str(upstream / 'src'),
                HERE / 'libfvad_runner.c', *sources, '-o', sanitized], output / 'libfvad-sanitizer-build.log')
    adapter_tests['sanitized'] = probe_adapter(sanitized, output, 'sanitizer-adapter-tests')
    cfg_sha = sha256(PLAN.read_bytes())
    evaluator = ROOT / 'validation/tools/run_validation_engine.py'
    identities = {'libfvad': {'source_sha': admitted['commit'], 'config_sha256': cfg_sha,
                             'processor_sha256': sha256(runner.read_bytes()), 'evaluator_sha256': sha256(evaluator.read_bytes())}}
    with tempfile.TemporaryDirectory(prefix='fe-libfvad-build-') as tmp:
        build = Path(tmp) / 'b0-build'
        run_logged(['cmake', '-S', baseline, '-B', build, '-DCMAKE_BUILD_TYPE=Release',
                    '-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG', '-DAP_SIMD_BACKEND=SCALAR',
                    '-DAP_BUILD_TESTS=OFF', '-DAP_BUILD_BENCH=OFF', '-DAP_ENABLE_LINUX_RUNTIME=OFF',
                    '-DAP_BUILD_SOURCE_REVISION=' + B0], output / 'baseline-configure.log')
        run_logged(['cmake', '--build', build, '--target', 'ap_process_pcm', '--parallel', '2'], output / 'baseline-build.log')
        b0 = output / 'b0-process-pcm'; shutil.copy2(build / 'ap_process_pcm', b0)
        shutil.copy2(build / 'generated/audio_pipeline/audio_pipeline_build.h', output / 'b0-build.h')
        shutil.copy2(build / 'CMakeCache.txt', output / 'b0-CMakeCache.txt')
        identities['b0'] = {'source_sha': B0, 'config_sha256': cfg_sha,
                             'processor_sha256': sha256(b0.read_bytes()), 'evaluator_sha256': sha256(evaluator.read_bytes())}
        b0_build_info = dict(re.findall(r'^#define (AP_BUILD_[A-Z_]+) "([^\"]*)"$',
                                          (output / 'b0-build.h').read_text(), re.MULTILINE))
        require(b0_build_info['AP_BUILD_SOURCE_REVISION'] == B0, 'baseline build revision mismatch')
        report = {'schema_version': 1, 'experiment_id': plan['experiment_id'], 'shipping_authority': False,
                  'authority': plan['authority'], 'execution_source_revision': execution_source,
                  'execution_kind': 'exact-workflow-checkout' if execution_source else 'uncommitted-local-reproduction',
                  'identities': identities, 'adapter_tests': adapter_tests, 'b0_build_info': b0_build_info,
                  'build_flags': {'libfvad': ['-std=c11', '-O2', '-Wall', '-Wextra', '-Wpedantic', '-Werror'],
                                  'b0': ['Release', '-O2 -DNDEBUG', 'SCALAR', 'LINUX_RUNTIME=OFF']},
                  'dataset_role': plan['dataset_role'], 'calibration': {'cases': []}, 'evaluation': {'cases': []},
                  'control_files_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in
                                          (Path(__file__), HERE / 'libfvad_runner.c', HERE / 'contracts.py', PLAN, ADMISSION, LOCK, CATALOG,
                                           ROOT / 'validation/tools/build_validation_corpus.py', evaluator,
                                           ROOT / 'validation/tools/run_validation.py', ROOT / 'validation/authority.json')},
                  'limits': plan['evidence_limits']}
        def collect(seed, modes, section):
            generated = Path(tmp) / str(seed)
            run_logged([sys.executable, ROOT / 'validation/tools/build_validation_corpus.py',
                        '--output', generated, '--seed', seed], output / f'generator-{seed}.log')
            corpus = load_json(generated / 'corpus.json')
            run_validation.validate_corpus_shape(corpus, run_validation.load_authority())
            require(corpus['tier'] == 'regression', 'non-regression data forbidden in this smoke')
            cases = {c['case_id']: c for c in corpus['cases']}
            pooled = {m: ([], []) for m in [None, *modes]}
            for case_id in plan['case_ids']:
                case = cases[case_id]
                require(case['mic_channels'] == 1 and case['sample_rate_hz'] == 16000, 'case input drift')
                rows = (generated / case['vad_labels']).read_text().splitlines()
                require(all(x in ('0', '1') for x in rows), 'invalid label file')
                labels = list(map(int, rows))
                dest = output / 'cases' / str(seed) / case_id; dest.mkdir(parents=True)
                mic = dest / 'mic.pcm'; shutil.copy2(generated / case['mic_audio'], mic)
                shutil.copy2(generated / case['vad_labels'], dest / 'vad.labels')
                write_json(dest / 'case.json', {'source_case': case, 'source_corpus_sha256': sha256((generated / 'corpus.json').read_bytes()),
                                               'execution_profile': 'vad-isolated-same-raw-input',
                                               'experiment_role': section + '-D0-replay'})
                results = {'seed': seed, 'case_id': case_id, 'arms': {}}
                for mode in [None, *modes]:
                    name = 'b0' if mode is None else f'libfvad-{mode}'
                    identity = dict(identities['b0' if mode is None else 'libfvad'])
                    identity['config_sha256'] = sha256(json.dumps({'plan': cfg_sha, 'mode': mode}, sort_keys=True).encode())
                    metrics, trace = execute_case(b0 if mode is None else runner, mode, mic, labels, dest / name, identity)
                    pooled[mode][0].extend(labels); pooled[mode][1].extend(trace)
                    results['arms'][name] = metrics
                report[section]['cases'].append(results)
            return pooled
        calibration = collect(plan['calibration_seed'], plan['modes'], 'calibration')
        totals = {m: checked_stats(*items) for m, items in calibration.items()}
        chosen = select_mode(totals[None], {m: totals[m] for m in plan['modes']})
        frozen = {'mode': chosen, 'b0': totals[None], 'modes': {str(m): totals[m] for m in plan['modes']},
                  'decision': 'RECALL_FLOOR_MATCH' if chosen is not None else plan['unmatched']}
        write_json(output / 'frozen-selection.json', frozen)  # Written before any evaluation execution.
        selection_digest = sha256((output / 'frozen-selection.json').read_bytes())
        report['calibration']['selection'] = frozen
        combined = {m: ([], []) for m in ([None, chosen] if chosen is not None else [None])}
        for seed in plan['evaluation_seeds']:
            pooled = collect(seed, [chosen] if chosen is not None else [], 'evaluation')
            for m, (labels, trace) in pooled.items():
                combined[m][0].extend(labels); combined[m][1].extend(trace)
        require(sha256((output / 'frozen-selection.json').read_bytes()) == selection_digest, 'selection changed after evaluation')
        report['evaluation']['totals'] = {('b0' if m is None else f'libfvad-{m}'): checked_stats(*v) for m, v in combined.items()}
        report['decision'] = 'NO_PROMOTION_D0_REFERENCE_ONLY' if chosen is not None else plan['unmatched']
        report['status'] = 'REFERENCE_EXECUTION_PASS'
        report['frozen_selection_sha256'] = selection_digest
        write_json(output / 'result.json', report)
    seal_output(output, report)
    verify_output(output, execution_source)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'compare', 'verify'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execution-source')
    args = parser.parse_args()
    try:
        if args.command == 'verify':
            result = verify_output(args.output.resolve(), args.execution_source)
        elif args.command == 'preflight':
            require(args.source is not None, '--source required')
            result = source_preflight(args.source.resolve(), args.output.resolve())
        else:
            require(args.source is not None and args.baseline is not None, '--source/--baseline required')
            result = compare(args.source.resolve(), args.baseline.resolve(), args.output.resolve(), args.execution_source)
        print(json.dumps({k: v for k, v in result.items() if k not in ('files_sha256', 'calibration', 'evaluation')}, sort_keys=True))
        return 0
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(f'libfvad reference failed: {exc}', file=sys.stderr)
        if args.output.is_dir():
            write_json(args.output / 'failure.json', {'status': 'FAIL', 'error': str(exc), 'shipping_authority': False})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
