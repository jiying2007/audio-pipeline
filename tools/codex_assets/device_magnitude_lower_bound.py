"""D49 bounded C implementation qualification, before the formal matrix.

This entry point does not select candidates or create a formal experiment root.
The inherited D48 scorer and the D49 matrix still require separate review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.codex_assets import device_noise_conditioned_protection as d42
from tools.codex_assets.device_capture import ROOT

DIRECTORY = ROOT / 'tests/validation/frontend_evolution'
C = DIRECTORY / 'device_magnitude_lower_bound_d49.c'
NS = DIRECTORY / 'device_magnitude_lower_bound_ns_d49.c'
HEADER = C.with_suffix('.h')
PRIVATE_ROOT = Path('/tmp/audio-device-d49-c-selftest-v1')
FROZEN_SOURCES = {
    DIRECTORY / 'device_current_innovation_d47.c': 'ca1ba081b344e6554473328510fbaf15c56d9b2657dee06b9ce9b5d7f328b733',
    DIRECTORY / 'device_current_innovation_ns_d47.c': '8dd2db9027d972aac3f6ea7f75a8bbd84c9e8c2eef6b0ab09b24aa9f7234916a',
    DIRECTORY / 'device_current_innovation_d47.h': '28c0520df7a9c3932fff32e0c9a8f4a0bb6eba08bdbcecd404f05103ae031d59',
    ROOT / 'tools/codex_assets/device_current_measurement.py': '27b5ae3e00d9e74e2cbbc1c8b37a185119d493e295243236ff1b1e936a6c3fed',
}


def digest(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4*1024*1024:
        raise ValueError('regular bounded source required: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest():
    for path, expected in FROZEN_SOURCES.items():
        if digest(path) != expected:
            raise ValueError('frozen predecessor drift: ' + str(path))
    paths = [*FROZEN_SOURCES, C, NS, HEADER, Path(__file__).resolve(),
             DIRECTORY / 'test_device_magnitude_lower_bound.py',
             d42.D18 / 'build/libaudio_pipeline.a',
             d42.D18 / 'build/CMakeFiles/audio_pipeline.dir/flags.make']
    # The archive has its own historical size contract, not a source-file cap.
    result = {str(p): digest(p) for p in paths if p.suffix != '.a'}
    archive = d42.D18 / 'build/libaudio_pipeline.a'
    if archive.is_symlink() or not archive.is_file():
        raise ValueError('regular historical archive required')
    with archive.open('rb') as stream:
        h = hashlib.sha256()
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    result[str(archive)] = h.hexdigest()
    return result


def compile_command(output):
    flags = (d42.D18 / 'build/CMakeFiles/audio_pipeline.dir/flags.make').read_text()
    defines = [s.split('=', 1)[1].split() for s in flags.splitlines()
               if s.startswith('C_DEFINES =')]
    if len(defines) != 1 or not all(x.startswith('-DAP_BUILD_') for x in defines[0]):
        raise ValueError('original build defines')
    return ['rtk', 'cc', *d42.FLAGS, '-ffp-contract=off', *defines[0],
            '-I', str(d42.D18 / 'source/src'), '-I', str(d42.D18 / 'source/include'),
            '-I', str(d42.D18 / 'build/generated'), str(C), str(NS),
            str(d42.D18 / 'build/libaudio_pipeline.a'), '-lm', '-lpthread',
            '-o', str(output / 'runner')]


def write_exclusive(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def run_child(command, timeout_seconds=120):
    """Bound the process group and preserve every attempted command's outcome."""
    started = time.monotonic()
    result = dict(command=command, cwd=str(ROOT), pid=None, child_started=False,
                  exit_code=None, terminal=None, timed_out=False, stdout='', stderr='')
    decode = lambda b: b.decode('utf-8', errors='replace') if isinstance(b, bytes) else b or ''
    try:
        child = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True)
    except OSError as exc:
        result.update(error=type(exc).__name__ + ': ' + str(exc),
                      elapsed_seconds=time.monotonic()-started)
        return result
    result.update(pid=child.pid, child_started=True, terminal=False)
    cleanup_seconds = min(5.0, timeout_seconds/4)
    try:
        stdout, stderr = child.communicate(timeout=timeout_seconds-cleanup_seconds)
        result.update(exit_code=child.returncode, terminal=True,
                      stdout=decode(stdout), stderr=decode(stderr))
    except subprocess.TimeoutExpired as exc:
        result.update(timed_out=True, stdout=decode(exc.stdout), stderr=decode(exc.stderr))
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as kill_error:
            result['kill_error'] = type(kill_error).__name__ + ': ' + str(kill_error)
        remaining = timeout_seconds-(time.monotonic()-started)
        if remaining > 0:
            try:
                stdout, stderr = child.communicate(timeout=remaining)
                result.update(exit_code=child.returncode, terminal=True,
                              stdout=decode(stdout), stderr=decode(stderr))
            except subprocess.TimeoutExpired as wait_error:
                result.update(stdout=decode(wait_error.stdout), stderr=decode(wait_error.stderr))
        # A missing observed terminal status is kept unknown, never assumed success.
    result['elapsed_seconds'] = time.monotonic()-started
    return result


def qualify(output):
    if (output != PRIVATE_ROOT or not output.is_absolute() or output.exists() or
            any(p.is_symlink() for p in (output, *output.parents))):
        raise ValueError('fixed absent private root required')
    before = source_manifest()
    commands = [compile_command(output), ['rtk', str(output / 'runner'), '--self-test'],
                ['rtk', str(output / 'runner'), 'invalid']]
    output.mkdir()
    write_exclusive(output / 'intent.json', dict(source_sha256=before, commands=commands,
                    cwd=str(ROOT), experiment='FE_DEVICE_MAGNITUDE_LOWER_BOUND_D49',
                    formal_matrix=False, timeout_seconds=120))
    started = time.monotonic()
    receipt = dict(status='FAILED', commands=[], formal_matrix=False,
                   promotion_allowed=False, shipping_approved=False)
    try:
        for index, (command, expected) in enumerate(zip(commands, (0, 0, 2))):
            item = run_child(command)
            receipt['commands'].append(item)
            if item['terminal'] is not True or item['timed_out'] or item['exit_code'] != expected:
                raise ValueError('unexpected child exit at command ' + str(index))
            if index == 1 and 'D49_SELF_TEST_PASS' not in item['stdout']:
                raise ValueError('missing actual self-test terminal marker')
        after = source_manifest()
        if before != after:
            raise ValueError('source identity changed during qualification')
        receipt.update(status='C_IMPLEMENTATION_SELF_TEST_VERIFIED',
                       source_sha256_start=before, source_sha256_end=after,
                       source_end_verified=True, runner_sha256=digest(output / 'runner'))
    except Exception as exc:
        receipt['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic() - started
        write_exclusive(output / 'receipt.json', receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--dry-run', action='store_true')
    choice.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps(dict(read_only=True, persisted=False, formal_matrix=False,
                              commands=[compile_command(PRIVATE_ROOT)],
                              source_sha256=source_manifest()), sort_keys=True))
    else:
        print(json.dumps(qualify(PRIVATE_ROOT), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
