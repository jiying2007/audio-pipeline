#!/usr/bin/env python3
"""#825 finite retirement: real parent-controlled exec/kill/recovery evidence.

The coordinator retains metadata and digests, never a retired PCM backup.
Offline contract checks and resealed evidence controls are not target execution.
"""
from __future__ import annotations

import argparse
import ast
import base64
import copy
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
import zipfile
import zlib

import fe09_b2s3_t3s2b1ba1_anchor_root_qualification as a1

ROOT = a1.ROOT
HERE = a1.HERE
PREFIX = 'fe09_b2s3_t3s2b1ba2_'
SOURCE_C = HERE / (PREFIX + 'finite_retirement.c')
SOURCE_H = HERE / (PREFIX + 'finite_retirement.h')
TEST = HERE / (PREFIX + 'finite_retirement_test.c')
LOCK = HERE / (PREFIX + 'frozen_inputs.json')
CONTRACT = HERE / (PREFIX + 'test_contract.json')
DOC = HERE / 'FE09_T3S2B1B_A2_F0_FINITE_RETIREMENT.md'
OWN = (SOURCE_C, SOURCE_H, TEST, Path(__file__).resolve(), DOC, LOCK, CONTRACT)
SOURCES = (*a1.SOURCES[:-1], SOURCE_C, TEST)
BASE = 'c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef'
CHECKPOINT = 'f90f6bd73c13c997b0bb85decf1545c632878982'
LOCK_SHA = 'df0801d5b32a9629bb54ce5f6db027039ea0f2101600a9ca8a1f7b1752ace73c'
CONTRACT_SHA = 'a0a957394425a3b2bf9d79c8762204e496867b8c386efe894e7e85a3af6dd67e'
DECISION = 'FE09_A2F0_FINITE_PREFIX_RETIREMENT_AND_ANCHORED_HOSTED_PROCESS_RECOVERY_ONLY'
FAILURE = 'FE09_A2F0_NOT_ADMITTED'
MARKER = 'FE09_A2F0_ORIGINAL_MULTIPROCESS_FOUR_TARGET_READBACK_PASS\n'
TARGETS = ('native', 'sanitized', 'arm', 'tsan')
MEMBERS = ('SHA256SUMS', 'receipt.json', 'collect.log', 'verify.log')
FALSE = ('original_ack_created', 'retired_pcm_reverified_after_delete',
         'hosted_checkpoint_committed_on_read', 'continuous_rolling_qualified',
         'cold_system_boot_authority_qualified', 'physical_powerloss_qualified',
         'ssc305_hardware_qualified', 'whole_device_memory_qualified',
         'ten_ms_product_qualified', 'public_sdk_installed')
SANITIZER_ENVIRONMENT = {
    'sanitized': {'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1',
                  'UBSAN_OPTIONS': 'halt_on_error=1'},
    'tsan': {'TSAN_OPTIONS': 'halt_on_error=1:exitcode=66'},
    'native': {}, 'arm': {},
}
LIMITS = {'SHA256SUMS': 512, 'receipt.json': 4 * 1024 * 1024,
          'collect.log': 16 * 1024 * 1024, 'verify.log': 1024 * 1024}
CHILD_CAP = 65536
FIXTURE_CAP = 1048576
COLLECT_SECONDS = 1500
SUITE_SECONDS = 540
TOOL_SECONDS = 120
BUILD_HEADER = ('#ifndef AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n'
                '#define AUDIO_PIPELINE_AUDIO_PIPELINE_BUILD_H\n'
                '#define AP_BUILD_RESAMPLER_BANDLIMITED 1\n#endif\n')
RECORD_NAME = re.compile(r'fa0-([0-9a-f]{8})-([0-9a-f]{16})-([0-9a-f]{16})-([0-9a-f]{64})-([0-9a-f]{64})\.bin\Z')
TRANSPORT = 'zlib-rfc1950-base64-v1'
EXPANDED_LOG_CAP = 256 * 1024 * 1024
TRACE_BLOCK_TARGET = 65536
TRACE_RECORD_CAP = 1024 * 1024


class NotAdmitted(ValueError):
    pass


def need(value: object, reason: str) -> None:
    if not value:
        raise NotAdmitted(reason)


def strict_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def constant(_value):
        raise NotAdmitted('NONFINITE_JSON')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None and value != '0' * 64


def packed(data: bytes) -> dict:
    """Lossless engineering transport; caps always count uncompressed bytes."""
    return {'codec': TRANSPORT, 'bytes': len(data), 'sha256': sha(data),
            'data': base64.b64encode(zlib.compress(data, 9)).decode('ascii')}


def unpacked(value: dict, cap: int) -> bytes:
    need(type(value) is dict and set(value) == {'codec', 'bytes', 'sha256', 'data'} and
         value['codec'] == TRANSPORT and type(value['bytes']) is int and
         0 <= value['bytes'] <= cap and is_sha(value['sha256']) and
         type(value['data']) is str and len(value['data']) <= (cap + 1024) * 2,
         'INVALID_BOUNDED_LOSSLESS_TRANSPORT')
    compressed = base64.b64decode(value['data'], validate=True)
    decoder = zlib.decompressobj()
    content = decoder.decompress(compressed, value['bytes'] + 1)
    need(len(content) == value['bytes'] and decoder.eof and not decoder.unused_data and
         not decoder.unconsumed_tail and sha(content) == value['sha256'],
         'LOSSLESS_TRANSPORT_LENGTH_DIGEST_OR_TRAILING_DATA_MISMATCH')
    return content


def compiler_report(data: bytes) -> dict:
    """Keep every compiler byte inside the outer trace's expansion budget."""
    return {'encoding': 'utf-8', 'bytes': len(data), 'sha256': sha(data),
            'text': data.decode('utf-8')}


def compiler_report_bytes(value: dict, cap: int) -> bytes:
    need(type(value) is dict and set(value) == {'encoding', 'bytes', 'sha256', 'text'} and
         value['encoding'] == 'utf-8' and type(value['bytes']) is int and
         0 < value['bytes'] <= cap and is_sha(value['sha256']) and
         type(value['text']) is str and len(value['text']) <= cap,
         'INVALID_BOUNDED_COMPILER_REPORT')
    content = value['text'].encode('utf-8')
    need(len(content) == value['bytes'] and sha(content) == value['sha256'],
         'COMPILER_REPORT_LENGTH_OR_DIGEST_MISMATCH')
    return content


def raw(path: Path, cap: int = 16 * 1024 * 1024) -> bytes:
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= cap,
         'MISSING_OR_OVERSIZED_' + path.name)
    return path.read_bytes()


def digest(path: Path) -> str:
    return sha(raw(path, 128 * 1024 * 1024))


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def source_git(*args: str, deadline: float | None = None) -> bytes:
    """Read only a bounded Git object id, under the collector's same deadline."""
    need(len(args) == 3 and args[:2] == ('rev-parse', '--verify'),
         'SOURCE_GIT_REQUIRES_BOUNDED_OBJECT_METADATA')
    started = time.monotonic()
    need(deadline is None or started < deadline, 'FIXED_BUDGET_EXCEEDED')
    tool_deadline = min(started + 30, deadline) if deadline is not None else started + 30
    env = dict(os.environ)
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GIT_NO_LAZY_FETCH'] = '1'
    process = None
    selector = selectors.DefaultSelector()
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    try:
        process = subprocess.Popen(['git', '-c', 'safe.directory=' + str(ROOT), *args],
                                   cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   close_fds=True, start_new_session=True, bufsize=0)
        for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = tool_deadline - time.monotonic()
            need(remaining > 0, 'FIXED_BUDGET_EXCEEDED')
            for key, _mask in selector.select(min(remaining, 0.1)):
                room = CHILD_CAP - len(buffers[key.data])
                chunk = os.read(key.fileobj.fileno(), min(8192, room + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(chunk[:room])
                need(len(chunk) <= room, 'SOURCE_GIT_' + key.data.upper() + '_STREAM_LIMIT')
        remaining = tool_deadline - time.monotonic()
        need(remaining > 0, 'FIXED_BUDGET_EXCEEDED')
        code = process.wait(timeout=remaining)
        need(time.monotonic() <= tool_deadline and
             (deadline is None or time.monotonic() <= deadline), 'FIXED_BUDGET_EXCEEDED')
        need(code == 0 and not buffers['stderr'], 'SOURCE_GIT_OBJECT_QUERY_FAILED_' + args[-1])
        answer = bytes(buffers['stdout'])
        need(re.fullmatch(rb'[0-9a-f]{40}\n', answer) is not None, 'SOURCE_GIT_OBJECT_ID_NOT_EXACT_40_HEX')
        return answer
    finally:
        try:
            if process is not None:
                try:
                    if process.returncode is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=3)
                finally:
                    for stream in (process.stdout, process.stderr):
                        if stream is not None and not stream.closed:
                            stream.close()
        finally:
            selector.close()


def contract() -> dict:
    contents = raw(CONTRACT, 1024 * 1024)
    need(sha(contents) == CONTRACT_SHA, 'FROZEN_TEST_CONTRACT_CHANGED')
    result = strict_json(contents.decode())
    need(result['targets'] == list(TARGETS) and result['repetitions_per_target'] == 2 and
         result['positive_profiles'] == 48 and len(result['crash_points_per_profile']) == 57,
         'FROZEN_CASE_CONTRACT_INVALID')
    return result


def pins() -> dict:
    data = raw(LOCK)
    need(sha(data) == LOCK_SHA, 'FROZEN_ORIGINAL_INPUT_LOCK_CHANGED')
    value = strict_json(data.decode())
    need(value['qualified_a1_main'] == BASE and value['input_count'] == 81 and
         len(value['inputs']) == 81, 'FROZEN_A1_PREREQUISITE_CHANGED')
    for name, expected in value['inputs'].items():
        path = ROOT / name
        need(not Path(name).is_absolute() and '..' not in Path(name).parts,
             'FROZEN_INPUT_PATH_ESCAPE')
        content = raw(path)
        need(expected == {'bytes': len(content), 'git_blob_sha1': blob(content),
                          'sha256': sha(content)}, 'FROZEN_ORIGINAL_INPUT_CHANGED_' + name)
    contract()
    return value['inputs']


def identity(source: str, *, deadline: float | None = None) -> dict:
    need(deadline is None or time.monotonic() < deadline, 'FIXED_BUDGET_EXCEEDED')
    need(type(source) is str and re.fullmatch(r'[0-9a-f]{40}', source) is not None and
         source_git('rev-parse', '--verify', 'HEAD', deadline=deadline).decode().strip() == source,
         'ACTUAL_EXECUTION_GIT_HEAD_REQUIRED')
    if os.environ.get('GITHUB_SHA'):
        need(os.environ['GITHUB_SHA'] == source, 'GITHUB_CHECKOUT_IDENTITY_MISMATCH')
    frozen = pins()
    own = {}
    for path in (*OWN, *(ROOT / name for name in frozen)):
        data = raw(path)
        name = relative(path)
        need(source_git('rev-parse', '--verify', source + ':' + name, deadline=deadline).decode().strip() == blob(data),
             'UNCOMMITTED_EXECUTION_INPUT_' + name)
        if path in OWN:
            own[name] = {'bytes': len(data), 'git_blob_sha1': blob(data), 'sha256': sha(data)}
    need(deadline is None or time.monotonic() < deadline, 'FIXED_BUDGET_EXCEEDED')
    return {'schema_version': 2, 'stage': 'FE09_T3_S2_B1B_A2_F0_FINITE_PREFIX_RETIREMENT',
            'preregistration': 'https://github.com/jiying2007/audio-pipeline/issues/825',
            'preregistration_checkpoint': CHECKPOINT, 'source_commit': source,
            'protected_a1_main': BASE, 'source_lock_sha256': LOCK_SHA,
            'test_contract_sha256': CONTRACT_SHA, 'frozen_original_inputs': frozen,
            'own_source_identity': own, 'compile_source_closure': [relative(p) for p in SOURCES],
            'source_role': 'first-party-synthetic-disclosed-engineering-fixture'}


def profiles() -> list[dict]:
    return [{'index': (((scene * 3 + rate_index) * 2 + render) * 2 + k - 1),
             'scene': scene, 'rate': rate, 'mics': (1, 2, 4, 4)[scene],
             'render': render, 'k': k,
             'name': f'{("C1", "C2", "C4_ULA", "C4_UCA")[scene]}_{rate}_render_{("disabled", "enabled")[render]}_K{k}'}
            for scene in range(4) for rate_index, rate in enumerate((16000, 32000, 48000))
            for render in (0, 1) for k in (1, 2)]


def compile_plan(target: str, execution_root: Path, directory: Path):
    compiler = 'arm-linux-gnueabihf-gcc' if target == 'arm' else 'cc'
    flags = [compiler, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
             '-ffp-contract=off', '-fno-fast-math', '-pthread',
             '-DAP_BUILD_RESAMPLER_BANDLIMITED=1', '-I' + str(directory / 'include'),
             '-I' + str(execution_root / 'src'), '-I' + str(execution_root / HERE.relative_to(ROOT))]
    if target in ('sanitized', 'tsan'):
        flags += ['-O1', '-g', '-fsanitize=thread' if target == 'tsan' else '-fsanitize=address,undefined',
                  '-fno-omit-frame-pointer']
    arm_flags = ['-march=armv7-a', '-mfpu=neon-vfpv4', '-mfloat-abi=hard']
    if target == 'arm':
        flags += arm_flags
    exceptions = (a1.a0.f0.b0.s2a.s1.s0.c0.b1.b1.b0.b1.SOURCE_C,
                  a1.a0.f0.b0.s2a.s1.s0.c0.b1.b1.b0.b1.ARRAY_C)
    commands, objects = [], []
    for index, path in enumerate(SOURCES):
        obj = directory / f'{target}-{index}.o'
        warnings = [] if path in exceptions else ['-Wconversion', '-Wshadow', '-Wpedantic']
        accounting = ['-fstack-usage']
        if path == SOURCE_C:
            accounting.append('-fcallgraph-info=su')
        commands.append(flags + warnings + accounting +
                        ['-c', str(execution_root / path.relative_to(ROOT)), '-o', str(obj)])
        objects.append(str(obj))
    executable = directory / (target + '.elf')
    link = [compiler, *objects, '-pthread', '-lm', '-o', str(executable)]
    if target == 'sanitized':
        link += ['-fsanitize=address,undefined']
    if target == 'tsan':
        link += ['-fsanitize=thread']
    if target == 'arm':
        link += arm_flags
    launcher = ['qemu-arm', '-L', '/usr/arm-linux-gnueabihf', str(executable)] if target == 'arm' else [str(executable)]
    return commands, link, launcher


class Trace:
    """Stream an exact bounded log, reserving room to label a failure prefix."""
    def __init__(self, path: Path):
        self.path = path
        self.file = path.open('xb')
        self.size = 0
        self.serial = 0
        self.failed = False
        self.buffer = bytearray()
        self.block_index = 0
        self.expanded_bytes = 0

    def block(self) -> None:
        if not self.buffer:
            return
        record = canonical({'kind': 'trace_block', 'index': self.block_index,
                            'payload': packed(bytes(self.buffer))}) + b'\n'
        need(self.size + len(record) <= LIMITS['collect.log'] - 2048, 'COLLECT_LOG_STREAM_LIMIT')
        self.file.write(record)
        self.file.flush()
        self.size += len(record)
        self.buffer.clear()
        self.block_index += 1

    def emit(self, kind: str, **values) -> None:
        record = canonical({'kind': kind, **values}) + b'\n'
        need(len(record) <= TRACE_RECORD_CAP and
             self.expanded_bytes + len(record) <= EXPANDED_LOG_CAP, 'TRACE_EXPANSION_BUDGET_EXCEEDED')
        if self.buffer and len(self.buffer) + len(record) > TRACE_BLOCK_TARGET:
            self.block()
        self.buffer.extend(record)
        self.expanded_bytes += len(record)
        if len(self.buffer) >= TRACE_BLOCK_TARGET:
            self.block()

    def failure(self, error: BaseException) -> None:
        if self.failed:
            return
        self.failed = True
        try:
            self.block()
        except NotAdmitted:
            # The encoded cap retains a bounded prefix, never a false complete trace.
            self.buffer.clear()
        record = canonical({'kind': 'failure_prefix', 'complete': False,
                            'error_type': type(error).__name__, 'reason': str(error)[:500]}) + b'\n'
        if self.size + len(record) <= LIMITS['collect.log']:
            self.file.write(record)
            self.file.flush()
            self.size += len(record)

    def close(self):
        self.block()
        self.file.close()


class Child:
    """One fresh exec, two independently capped streams, no implicit retries."""
    def __init__(self, command: list[str], environment: dict, deadline: float,
                 trace: Trace, context: dict, *, json_lines: bool = True):
        need(time.monotonic() < deadline, 'FIXED_BUDGET_EXCEEDED')
        self.trace, self.deadline, self.json_lines = trace, deadline, json_lines
        self.serial = trace.serial
        trace.serial += 1
        self.started = time.monotonic()
        self.started_ns = time.monotonic_ns()
        env = dict(os.environ)
        # Inherited detector settings cannot override the registered target plan.
        for key in ('ASAN_OPTIONS', 'UBSAN_OPTIONS', 'TSAN_OPTIONS', 'LSAN_OPTIONS'):
            env.pop(key, None)
        env.update(environment)
        self.selector = selectors.DefaultSelector()
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.pending = bytearray()
        self.queue = deque()
        self.stdout_count = 0
        self.eof = set()
        self.waited = False
        self.context = context
        self.process = None
        try:
            self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            close_fds=True, start_new_session=True, bufsize=0)
            for stream, name in ((self.process.stdout, 'stdout'), (self.process.stderr, 'stderr')):
                os.set_blocking(stream.fileno(), False)
                self.selector.register(stream, selectors.EVENT_READ, name)
            trace.emit('launch', serial=self.serial, command=command, environment=environment,
                       close_fds=True, fresh_exec=True, pid=self.process.pid,
                       start_monotonic_ns=self.started_ns,
                       deadline_monotonic_ns=int(deadline * 1_000_000_000), **context)
        except BaseException:
            if self.process is not None:
                self.abort()
            else:
                self.selector.close()
            raise

    def pump(self) -> None:
        remaining = self.deadline - time.monotonic()
        need(remaining > 0, 'FIXED_BUDGET_EXCEEDED')
        events = self.selector.select(min(remaining, 0.2))
        for key, _mask in events:
            chunk = os.read(key.fileobj.fileno(), CHILD_CAP + 1)
            if not chunk:
                self.eof.add(key.data)
                self.selector.unregister(key.fileobj)
                continue
            if key.data == 'stderr':
                room = CHILD_CAP - len(self.stderr)
                self.stderr.extend(chunk[:max(0, room)])
                need(len(chunk) <= room, 'CHILD_STDERR_STREAM_LIMIT')
            else:
                room = CHILD_CAP - self.stdout_count
                accepted = chunk[:max(0, room)]
                self.stdout_count += len(accepted)
                self.stdout.extend(accepted)
                if len(chunk) > room:
                    raise NotAdmitted('CHILD_STDOUT_STREAM_LIMIT')
                if self.json_lines:
                    while b'\n' in self.stdout:
                        line, _separator, rest = self.stdout.partition(b'\n')
                        self.stdout = bytearray(rest)
                        self.queue.append(bytes(line) + b'\n')

    def next(self) -> dict:
        while not self.queue:
            need('stdout' not in self.eof, 'INCOMPLETE_CHILD_JSONL_PROTOCOL')
            self.pump()
        line = self.queue.popleft()
        self.pending.extend(line)
        value = strict_json(line.decode('utf-8'))
        need(type(value) is dict and type(value.get('e')) is str, 'CHILD_EVENT_SCHEMA_DRIFT')
        return value

    def flush(self) -> None:
        if self.pending:
            self.trace.emit('stdout', serial=self.serial,
                            raw_b64=base64.b64encode(self.pending).decode('ascii'))
            self.pending.clear()

    def send(self, text: str) -> None:
        need(text.endswith('\n') and len(text) < 1024, 'INVALID_PARENT_CONTROL_MESSAGE')
        self.flush()
        self.trace.emit('send', serial=self.serial, text=text, monotonic_ns=time.monotonic_ns())
        self.process.stdin.write(text.encode('ascii'))
        self.process.stdin.flush()

    def kill(self) -> None:
        self.flush()
        self.trace.emit('kill', serial=self.serial, signal=signal.SIGKILL,
                        reason='registered-crash', monotonic_ns=time.monotonic_ns())
        os.killpg(self.process.pid, signal.SIGKILL)

    def wait_owned(self, deadline: float) -> int:
        need(hasattr(os, 'wait4'), 'ACTUAL_OWNED_CHILD_RUSAGE_UNAVAILABLE')
        while True:
            need(time.monotonic() < deadline, 'FIXED_BUDGET_EXCEEDED')
            pid, status, usage = os.wait4(self.process.pid, os.WNOHANG)
            if pid:
                need(pid == self.process.pid, 'WAIT_REAPED_DIFFERENT_CHILD')
                code = os.waitstatus_to_exitcode(status)
                self.process.returncode = code
                self.waited = True
                self.wait4_usage = {'returned_owned_pid': pid, 'raw_wait_status': status,
                                    'maximum_rss_bytes': usage.ru_maxrss * 1024,
                                    'user_cpu_ns': int(usage.ru_utime * 1_000_000_000),
                                    'system_cpu_ns': int(usage.ru_stime * 1_000_000_000),
                                    'minor_page_faults': usage.ru_minflt, 'major_page_faults': usage.ru_majflt,
                                    'scope': 'owned-child-entire-lifetime-including-fork-exec-transition'}
                return code
            time.sleep(min(0.005, max(0.0, deadline - time.monotonic())))

    def close_streams(self) -> None:
        """Idempotent cleanup also applies after a successful kernel wait."""
        try:
            self.selector.close()
        finally:
            if self.process is not None:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    if stream and not stream.closed:
                        stream.close()

    def finish(self, expected: int = 0) -> dict:
        self.process.stdin.close()
        while len(self.eof) != 2:
            self.pump()
        if self.json_lines:
            need(not self.queue and not self.stdout, 'UNEXPECTED_CHILD_OUTPUT_AFTER_FINAL_EVENT')
        else:
            self.pending.extend(self.stdout)
            self.stdout.clear()
        self.flush()
        remaining = self.deadline - time.monotonic()
        need(remaining > 0, 'FIXED_BUDGET_EXCEEDED')
        code = self.wait_owned(self.deadline)
        observed = {'serial': self.serial, 'exit_or_signal': code,
                    'elapsed_ns': time.monotonic_ns() - self.started_ns,
                    'stdout_bytes': self.stdout_count, 'stderr_bytes': len(self.stderr),
                    'stderr_b64': base64.b64encode(self.stderr).decode('ascii'),
                    'owned_child_wait4': self.wait4_usage,
                    'wait_monotonic_ns': time.monotonic_ns()}
        try:
            self.trace.emit('wait', **observed)
            if hasattr(self, 'runtime'):
                runtime_wait_observation(self.runtime, self.wait4_usage)
        finally:
            self.close_streams()
        need(code == expected, 'ACTUAL_CHILD_EXIT_MISMATCH_' + str(code))
        need(not self.stderr, 'ACTUAL_CHILD_STDERR_DIAGNOSTIC')
        return observed

    def abort(self) -> None:
        if self.waited:
            self.close_streams()
            return
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            code = self.wait_owned(time.monotonic() + 3)
            # Reaped child cannot write again; bounded nonblocking drains retain late diagnostics.
            for stream, name in ((self.process.stdout, 'stdout'), (self.process.stderr, 'stderr')):
                if stream is None or stream.closed:
                    continue
                os.set_blocking(stream.fileno(), False)
                while True:
                    try:
                        chunk = os.read(stream.fileno(), 8192)
                    except (BlockingIOError, OSError):
                        break
                    if not chunk:
                        break
                    if name == 'stderr':
                        room = max(0, CHILD_CAP - len(self.stderr))
                        self.stderr.extend(chunk[:room])
                    else:
                        room = max(0, CHILD_CAP - self.stdout_count)
                        self.stdout.extend(chunk[:room])
                        self.stdout_count += min(len(chunk), room)
            while self.queue:
                self.pending.extend(self.queue.popleft())
            self.pending.extend(self.stdout)
            self.stdout.clear()
            try:
                self.flush()
                self.trace.emit('abort_wait', serial=self.serial, exit_or_signal=code,
                                reason='failure-cleanup-not-registered-crash',
                                owned_child_wait4=self.wait4_usage,
                                stderr_prefix_b64=base64.b64encode(self.stderr).decode('ascii'))
            except Exception:
                pass
        finally:
            self.close_streams()


def observe(root: Path) -> dict:
    """Independently hash actual files; retain no raw original record/PCM bytes."""
    need(root.is_dir() and not root.is_symlink(), 'PARENT_FIXTURE_ROOT_UNAVAILABLE')
    need(set(p.name for p in root.iterdir()) <= {'data', 'a1', 'control', 'legacy', 'helper'},
         'UNREGISTERED_FIXTURE_BACKUP_DIRECTORY')
    records, directories, roots, all_files = [], {}, {}, []
    control_metadata = {}
    inode_sizes, inode_allocations = {}, {}
    total = 0
    for role in ('data', 'a1', 'control', 'legacy', 'helper'):
        directory = root / role
        if not directory.exists():
            directories[role] = None
            roots[role] = []
            continue
        dstat = directory.lstat()
        need(stat.S_ISDIR(dstat.st_mode) and not directory.is_symlink(), 'PARENT_DIRECTORY_NOT_REGULAR')
        directories[role] = [dstat.st_dev, dstat.st_ino, stat.S_IMODE(dstat.st_mode), dstat.st_uid]
        entries = []
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            before = path.lstat()
            kind = 'f' if stat.S_ISREG(before.st_mode) else ('l' if stat.S_ISLNK(before.st_mode) else 's')
            content_hash = None
            total += before.st_size if kind == 'f' else 0
            if kind == 'f':
                inode_sizes[(before.st_dev, before.st_ino)] = before.st_size
                inode_allocations[(before.st_dev, before.st_ino)] = before.st_blocks * 512
            need(total <= FIXTURE_CAP, 'FIXTURE_DISK_BUDGET_EXCEEDED')
            if kind == 'f':
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    opened = os.fstat(fd)
                    need((opened.st_dev, opened.st_ino, opened.st_size) ==
                         (before.st_dev, before.st_ino, before.st_size), 'PARENT_FILE_CHANGED_DURING_OPEN')
                    hashed = hashlib.sha256()
                    consumed = 0
                    metadata = bytearray() if role == 'control' and before.st_size <= 8192 else None
                    while True:
                        chunk = os.read(fd, 8192)
                        if not chunk:
                            break
                        consumed += len(chunk)
                        need(consumed <= FIXTURE_CAP, 'PARENT_FILE_READ_LIMIT')
                        hashed.update(chunk)
                        if metadata is not None:
                            metadata.extend(chunk)
                    del chunk
                    after = os.fstat(fd)
                    need(consumed == before.st_size and
                         (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) ==
                         (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
                         'PARENT_FILE_CHANGED_DURING_READ')
                    content_hash = hashed.hexdigest()
                    if metadata is not None and len(metadata) >= 192:
                        header = bytes(metadata[:192])
                        zeroed = metadata[:120] + b'\0' * 32 + metadata[152:]
                        control_metadata[path.name] = {
                            'header_b64': base64.b64encode(header).decode('ascii'),
                            'body_sha256': sha(bytes(metadata[192:])),
                            'zeroed_self_field_sha256': sha(bytes(zeroed)),
                            'computed_final_name': f'fpr1-{int.from_bytes(header[32:36], "little"):08x}-'
                            f'{int.from_bytes(header[40:48], "little"):016x}-{header[120:152].hex()}.bin'}
                        del metadata, zeroed, header
                finally:
                    os.close(fd)
            item = [path.name, kind, before.st_size, stat.S_IMODE(before.st_mode),
                    before.st_uid, before.st_nlink, before.st_dev, before.st_ino, content_hash]
            entries.append(item)
            all_files.append([role, *item])
            if role == 'data':
                match = RECORD_NAME.fullmatch(path.name)
                sequence = int(match[3], 16) if match else None
                records.append((sequence, item))
        roots[role] = entries
    present = sorted(sequence for sequence, _item in records if sequence is not None)
    need(len(present) == len(set(present)), 'PARENT_DUPLICATE_ORIGINAL_SEQUENCE')
    data_content = [[item[0], item[2], item[8]] for _seq, item in records]
    retained = [[seq, item[0], item[2], item[8]] for seq, item in records if seq is not None and 17 <= seq <= 32]
    retired = [[seq, item[0], item[2], item[8]] for seq, item in records if seq is not None and 1 <= seq <= 16]
    root_entries = {}
    for role in ('a1', 'control'):
        root_entries[role] = [
            {'role': 'part' if item[0].endswith('.part') else ('final' if item[0].endswith('.bin') else 'unknown'),
             'name': item[0], 'name_sha256': sha(item[0].encode()), 'kind': item[1], 'bytes': item[2],
             'mode': item[3], 'uid': item[4], 'nlink': item[5], 'dev': item[6],
             'ino': item[7], 'sha256': item[8],
             'fpr_metadata': control_metadata.get(item[0]) if role == 'control' else None}
            for item in roots[role]]
    # Content digests deliberately exclude host inode identity for scientific comparison.
    return {'directories': directories, 'present': present,
            'missing': [seq for seq in range(1, 33) if seq not in present],
            'extra_data_entries': sum(seq is None for seq, _item in records),
            'data_sha256': sha(canonical(data_content)), 'retained_sha256': sha(canonical(retained)),
            'retired_sha256': sha(canonical(retired)),
            'namespace_sha256': sha(canonical(all_files)),
            'data_namespace_sha256': sha(canonical(roots['data'])),
            'a1_namespace_sha256': sha(canonical(roots['a1'])),
            'control_namespace_sha256': sha(canonical(roots['control'])),
            'roots': root_entries, 'fixture_logical_bytes': total,
            'fixture_inode_bytes': sum(inode_sizes.values()),
            'host_filesystem_allocated_bytes': sum(inode_allocations.values()),
            'data_logical_bytes': sum(item[2] for _seq, item in records if item[1] == 'f'),
            'retained_logical_bytes': sum(item[2] for seq, item in records
                                          if seq is not None and 17 <= seq <= 32 and item[1] == 'f'),
            'helper_entries': len(roots['helper']), 'legacy_entries': len(roots['legacy']),
            'helper_content_sha256': sha(canonical([[x[0], x[2], x[8]] for x in roots['helper']]))}


def snapshot(child: Child, root: Path, phase: str) -> dict:
    child.flush()
    value = observe(root)
    child.trace.emit('observe', serial=child.serial, phase=phase, snapshot=value,
                     monotonic_ns=time.monotonic_ns())
    return value


def check_anchor(event: dict, before: dict) -> str:
    need(set(event) >= {'e', 'a', 'h', 'o'} and event['e'] == 'anchor' and
         type(event['a']) is list and len(event['a']) == 8 and
         all(type(x) is int and x > 0 for x in event['a']) and is_sha(event['h']),
         'INVALID_EXTERNAL_ANCHOR_EVENT')
    need(event['o'] == [32, 32, 32], 'ORIGINAL_SOURCE_NOT_STOPPED_AT32')
    actual = [number for role in ('data', 'a1', 'control') for number in before['directories'][role][:2]]
    need(event['a'][2:] == actual and len({tuple(actual[i:i + 2]) for i in (0, 2, 4)}) == 3 and
         len({actual[i] for i in (0, 2, 4)}) == 1, 'PARENT_ANCHOR_DIRECTORY_BINDING_MISMATCH')
    need(before['missing'] == [] and before['extra_data_entries'] == 0 and
         before['helper_entries'] == 0 and before['legacy_entries'] == 0,
         'PARENT_ORIGINAL_COMPLETE_SOURCE_REQUIRED')
    return 'ACK ' + ' '.join(str(value) for value in [*event['a'], event['h']]) + '\n'


def validate_snapshot(value: dict) -> None:
    need(type(value) is dict and type(value.get('present')) is list and
         type(value.get('missing')) is list and
         value['present'] == sorted(set(value['present'])) and
         value['missing'] == [x for x in range(1, 33) if x not in value['present']] and
         all(type(x) is int and 1 <= x <= 32 for x in value['present']),
         'PARENT_NAMESPACE_OBSERVATION_INVALID')
    for key in ('data_sha256', 'retained_sha256', 'retired_sha256', 'namespace_sha256',
                'data_namespace_sha256', 'a1_namespace_sha256', 'control_namespace_sha256',
                'helper_content_sha256'):
        need(is_sha(value.get(key)), 'PARENT_OBSERVATION_DIGEST_MISSING')
    need(type(value.get('fixture_logical_bytes')) is int and
         0 < value['fixture_logical_bytes'] <= FIXTURE_CAP and
         type(value.get('fixture_inode_bytes')) is int and
         0 < value['fixture_inode_bytes'] <= value['fixture_logical_bytes'],
         'FIXED_BUDGET_EXCEEDED')
    need(set(value['directories']) == {'data', 'a1', 'control', 'legacy', 'helper'},
         'PARENT_DIRECTORY_SET_MISMATCH')
    for role in ('data', 'a1', 'control'):
        fields = value['directories'][role]
        need(type(fields) is list and len(fields) == 4 and
             all(type(x) is int and x >= 0 for x in fields), 'PARENT_DIRECTORY_IDENTITY_MISSING')
    for entries in value['roots'].values():
        need(type(entries) is list and len(entries) <= 8, 'PARENT_ROOT_NAMESPACE_UNBOUNDED')
        for entry in entries:
            need(entry['role'] in ('part', 'final', 'unknown') and
                 type(entry.get('name')) is str and len(entry['name']) <= 256 and
                 sha(entry['name'].encode()) == entry['name_sha256'] and
                 type(entry['bytes']) is int and 0 <= entry['bytes'] <= FIXTURE_CAP and
                 type(entry['nlink']) is int and entry['nlink'] > 0,
                 'PARENT_ROOT_ENTRY_OBSERVATION_INVALID')
            if entry.get('fpr_metadata') is not None:
                observed = entry['fpr_metadata']
                need(type(observed) is dict and len(base64.b64decode(observed['header_b64'], validate=True)) == 192 and
                     is_sha(observed['body_sha256']) and is_sha(observed['zeroed_self_field_sha256']),
                     'PARENT_CHECKPOINT_METADATA_OBSERVATION_INVALID')


def control_state(snapshot_value: dict) -> str:
    entries = snapshot_value['roots']['control']
    if not entries:
        return 'empty'
    if len(entries) == 1 and entries[0]['role'] == 'part' and entries[0]['nlink'] == 1:
        return {0: 'part_empty', 2384: 'part_2384_bytes', 4768: 'part_complete'}.get(entries[0]['bytes'], 'part_other')
    if len(entries) == 1 and entries[0]['role'] == 'final' and entries[0]['nlink'] == 1:
        return 'final_only'
    if (len(entries) == 2 and {entry['role'] for entry in entries} == {'part', 'final'} and
        all(entry['nlink'] == 2 and entry['bytes'] == 4768 for entry in entries) and
        (entries[0]['dev'], entries[0]['ino']) == (entries[1]['dev'], entries[1]['ino'])):
        return 'part_and_final_same_inode'
    return 'other'


def same_roots(left: dict, right: dict, *, control: bool = True) -> bool:
    roles = ('a1', 'control') if control else ('a1',)
    return all(left['roots'][role] == right['roots'][role] for role in roles)


def check_crash_snapshot(value: dict, original: dict, point: dict) -> None:
    validate_snapshot(value)
    expected = point['control_namespace']
    entries = value['roots']['control']
    actual = sorted((e['role'], e['bytes'], e['nlink']) for e in entries)
    wanted = sorted((e['role'], e['bytes'], e['nlink']) for e in expected['entries'])
    same_inode = (len(entries) == 2 and
                  (entries[0]['dev'], entries[0]['ino']) == (entries[1]['dev'], entries[1]['ino']))
    need(actual == wanted and same_inode == expected['part_and_final_same_inode'] and
         value['missing'] == point['expected_missing_sequences'] and
         value['present'] == point['expected_present_original_sequences'] and
         value['retained_sha256'] == original['retained_sha256'] and
         value['roots']['a1'] == original['roots']['a1'] and
         value['directories'] == original['directories'] and
         value['extra_data_entries'] == 0 and value['helper_entries'] == 0,
         'REGISTERED_CRASH_ORACLE_MISMATCH')
    need(len(value['roots']['a1']) == 1 and value['roots']['a1'][0]['bytes'] == 1376 and
         value['roots']['a1'][0]['nlink'] == 1, 'REGISTERED_CRASH_ORACLE_MISMATCH')


def io_counts(events: list[dict]) -> tuple[int, int, list[dict]]:
    unlinks = syncs = 0
    injected = []
    for event in events:
        if event['e'] == 'io':
            values = event.get('v')
            need(type(values) is list and len(values) == 7 and
                 all(type(x) is int for x in values), 'RAW_CRITICAL_IO_EVENT_INVALID')
            _phase, operation, role, _sequence, called, actual, _reported = values
            if operation == 9 and role == 4 and called == 1 and actual == 0:
                unlinks += 1
            if operation == 7 and role == 1 and called == 1 and actual == 0:
                syncs += 1
        elif event['e'] == 'inj':
            need(type(event.get('v')) is list and len(event['v']) == 17 and
                 all(type(x) is int for x in event['v']), 'RAW_INJECTED_IO_EVENT_INVALID')
            injected.append(event)
    return unlinks, syncs, injected


def check_common_result(value: dict, events: list[dict], *, fresh: bool) -> None:
    need(type(value.get('rc')) is int and value['rc'] in (0, -1) and
         type(value.get('c')) is str and re.fullmatch(r'[A-Z0-9_]{1,120}', value['c']) and
         (value.get('k') is None or type(value['k']) is int and 0 <= value['k'] <= 16) and
         type(value.get('u')) is int and 0 <= value['u'] <= 16 and
         type(value.get('commit')) is bool and type(value.get('m')) is int and
         0 < value['m'] <= 65536, 'ACTUAL_RUNTIME_RESULT_SCHEMA_OR_RESOURCE_FAILURE')
    need(type(value.get('io')) is list and len(value['io']) == 4 and
         all(type(x) is int and x >= 0 for x in value['io']) and is_sha(value.get('d')),
         'ACTUAL_IO_AUDIT_MISSING')
    unlinks, syncs, injected = io_counts(events)
    need(value['io'][1:] == [unlinks, syncs, len(injected)] and value['u'] == unlinks,
         'RECEIPT_IO_COUNTS_NOT_DERIVED_FROM_RAW_EVENTS')
    need(type(value.get('v')) is list and len(value['v']) == 4 and value['v'][3] == 0,
         'INVENTED_RUNTIME_SOURCE_ACK')
    if fresh:
        need(value.get('o') is None and value.get('f') == [0, 0, 0, 0, 0],
             'FRESH_RECOVERY_HAS_SOURCE_OWNER_OR_ACK_AUTHORITY')
    else:
        need(value.get('o') == [32, 32, 32], 'LIVE_ORIGINAL_OWNER_CHANGED')
    if value['rc'] == 0:
        need(value['c'] == 'OK' and value['v'][0] == 16 and
             type(value.get('b')) is list and len(value['b']) == 2 and
             all(type(x) is int and 0 < x <= FIXTURE_CAP for x in value['b']) and
             is_sha(value.get('h')), 'INCOMPLETE_ACTUAL_RETAINED_REPLAY')
        for key in ('cf', 'rf'):
            need(type(value.get(key)) is list and len(value[key]) == 16 and
                 all(type(x) is int and 0 <= x < 2**64 for x in value[key]),
                 'ORIGINAL_RETAINED_PCM_FNV_WITNESS_MISSING')


def read_until(child, expected: str, *, stop_point: int = 0) -> tuple[dict, list[dict]]:
    events = []
    while True:
        value = child.next()
        events.append(value)
        if value['e'] == expected:
            return value, events
        if value['e'] == 'p':
            need(type(value.get('p')) is int and 1 <= value['p'] <= 57,
                 'UNREGISTERED_CRASH_POINT')
            if stop_point and value['p'] == stop_point:
                return value, events
        else:
            need(value['e'] in ('io', 'inj', 'old'), 'UNEXPECTED_CHILD_PROTOCOL_EVENT')


class Cursor:
    def __init__(self, data: bytes):
        need(0 < len(data) <= LIMITS['collect.log'], 'FIXED_BUDGET_EXCEEDED')
        self.events = []
        self.offset = 0
        self.expanded_bytes = 0
        self.serials = set()
        self.last_monotonic_ns = 0
        for index, line in enumerate(data.decode('utf-8').splitlines()):
            block = strict_json(line)
            need(type(block) is dict and set(block) == {'kind', 'index', 'payload'} and
                 block['kind'] == 'trace_block' and block['index'] == index,
                 'NONCONTIGUOUS_OR_INCOMPLETE_RAW_TRACE_BLOCK')
            plain = self.expand(block['payload'], TRACE_RECORD_CAP)
            need(plain.endswith(b'\n'), 'INCOMPLETE_RAW_TRACE_BLOCK')
            self.events.extend(strict_json(record) for record in plain.decode('utf-8').splitlines())

    def expand(self, value: dict, cap: int) -> bytes:
        content = unpacked(value, cap)
        self.expanded_bytes += len(content)
        need(self.expanded_bytes <= EXPANDED_LOG_CAP, 'TOTAL_EXPANDED_TRACE_LIMIT')
        return content

    def take(self, kind: str, reason: str = 'UNREGISTERED_RETRY_OR_INCOMPLETE_INVOCATION_TRACE') -> dict:
        need(self.offset < len(self.events), reason)
        value = self.events[self.offset]
        self.offset += 1
        need(type(value) is dict and value.get('kind') == kind, reason)
        clock_key = {'collection': 'start_monotonic_ns', 'suite_start': 'start_monotonic_ns',
                     'launch': 'start_monotonic_ns', 'send': 'monotonic_ns', 'kill': 'monotonic_ns',
                     'observe': 'monotonic_ns', 'wait': 'wait_monotonic_ns',
                     'suite_end': 'end_monotonic_ns', 'collection_end': 'end_monotonic_ns'}.get(kind)
        if clock_key is not None:
            instant = value.get(clock_key)
            need(type(instant) is int and instant >= self.last_monotonic_ns,
                 'FIXED_BUDGET_EXCEEDED')
            self.last_monotonic_ns = instant
        return value

    def peek(self) -> dict | None:
        return self.events[self.offset] if self.offset < len(self.events) else None


class ReplayChild:
    """Consume raw events in the same protocol, never execute or trust totals."""
    def __init__(self, cursor: Cursor, command: list[str], environment: dict,
                 context: dict, deadline_ns: int, *, json_lines: bool = True):
        self.cursor, self.queue, self.json_lines = cursor, deque(), json_lines
        launch = cursor.take('launch')
        need(all(launch.get(key) == value for key, value in context.items()),
             'UNREGISTERED_RETRY_OR_INCOMPLETE_INVOCATION_TRACE')
        need(launch.get('fresh_exec') is True and launch.get('close_fds') is True,
             'FRESH_TARGET_EXEC_REQUIRED')
        need(launch.get('environment') == environment, 'SANITIZER_ENVIRONMENT_MISMATCH')
        need(launch.get('command') == command, 'TARGET_LAUNCHER_OR_ELF_MISMATCH')
        need(type(launch.get('pid')) is int and launch['pid'] > 0 and
             type(launch.get('start_monotonic_ns')) is int and
             type(launch.get('deadline_monotonic_ns')) is int and
             launch['start_monotonic_ns'] < launch['deadline_monotonic_ns'] <= deadline_ns,
             'FIXED_BUDGET_EXCEEDED')
        self.launch, self.serial = launch, launch['serial']
        need(type(self.serial) is int and self.serial == len(cursor.serials) and
             self.serial not in cursor.serials, 'UNREGISTERED_RETRY_OR_INCOMPLETE_INVOCATION_TRACE')
        cursor.serials.add(self.serial)
        self.total = 0
        self.killed = False
        self.waited = False
        self.context = context

    def next(self) -> dict:
        if not self.queue:
            value = self.cursor.take('stdout', 'INCOMPLETE_RECOVERY_PROTOCOL')
            need(value.get('serial') == self.serial and type(value.get('raw_b64')) is str and
                 len(value['raw_b64']) <= CHILD_CAP * 2,
                 'ORIGINAL_CHILD_STREAM_IDENTITY_MISMATCH')
            raw_lines = base64.b64decode(value['raw_b64'], validate=True)
            self.total += len(raw_lines)
            need(self.total <= CHILD_CAP and raw_lines.endswith(b'\n'), 'FIXED_BUDGET_EXCEEDED')
            self.queue.extend(raw_lines.decode().splitlines())
        result = strict_json(self.queue.popleft())
        need(type(result) is dict and type(result.get('e')) is str, 'CHILD_EVENT_SCHEMA_DRIFT')
        return result

    def flush(self):
        need(not self.queue, 'UNEXPECTED_CHILD_OUTPUT_AT_PARENT_BARRIER')

    def send(self, text: str):
        self.flush()
        value = self.cursor.take('send', 'INCOMPLETE_RECOVERY_PROTOCOL')
        need(value.get('serial') == self.serial and value.get('text') == text,
             'INCOMPLETE_RECOVERY_PROTOCOL')

    def kill(self):
        self.flush()
        value = self.cursor.take('kill', 'ACTUAL_CRASH_TERMINATION_UNPROVEN')
        need(value.get('serial') == self.serial and value.get('signal') == 9 and
             value.get('reason') == 'registered-crash', 'ACTUAL_CRASH_TERMINATION_UNPROVEN')
        self.killed = True

    def finish(self, expected: int = 0) -> dict:
        self.flush()
        value = self.cursor.take('wait', 'ACTUAL_CRASH_TERMINATION_UNPROVEN' if expected == -9 else
                                 'UNREGISTERED_RETRY_OR_INCOMPLETE_INVOCATION_TRACE')
        need(value.get('serial') == self.serial and type(value.get('exit_or_signal')) is int and
             value['exit_or_signal'] == expected and (expected != -9 or self.killed),
             'ACTUAL_CRASH_TERMINATION_UNPROVEN' if expected == -9 else 'ACTUAL_CHILD_EXIT_MISMATCH')
        need(value.get('stdout_bytes') == self.total and value.get('stderr_bytes') == 0 and
             value.get('stderr_b64') == '', 'ORIGINAL_CHILD_STREAM_OR_SANITIZER_DIAGNOSTIC')
        need(type(value.get('wait_monotonic_ns')) is int and
             self.launch['start_monotonic_ns'] <= value['wait_monotonic_ns'] <= self.launch['deadline_monotonic_ns'] and
             type(value.get('elapsed_ns')) is int and value['elapsed_ns'] >= 0,
             'FIXED_BUDGET_EXCEEDED')
        usage = value.get('owned_child_wait4')
        need(type(usage) is dict and usage.get('returned_owned_pid') == self.launch['pid'] and
             type(usage.get('raw_wait_status')) is int and
             os.waitstatus_to_exitcode(usage['raw_wait_status']) == expected,
             'ACTUAL_OWNED_CHILD_WAIT_OR_RUSAGE_MISSING')
        if hasattr(self, 'runtime'):
            runtime_wait_observation(self.runtime, usage)
        self.waited = True
        return value

    def abort(self):
        pass


class LiveRuntime:
    def __init__(self, trace: Trace, launcher: list[str], binary_sha: str,
                 target: str, repetition: int, deadline: float):
        self.trace, self.launcher, self.binary_sha = trace, launcher, binary_sha
        self.target, self.repetition, self.deadline = target, repetition, deadline
        self.active = None
        self.starts = 0
        self.resources = None
        self.fixture_sizes = None
        self.maximum_fixture_logical_bytes = 0
        self.maximum_fixture_allocated_bytes = 0
        self.maximum_observed_process_rss_bytes = 0

    def begin(self, case_id: str, profile: int | None) -> Path:
        root = Path(tempfile.mkdtemp(prefix='fe09-a2-', dir='/tmp'))
        self.trace.emit('case', target=self.target, repetition=self.repetition,
                         case_id=case_id, profile=profile, fixture_root=str(root))
        return root

    def start(self, role: str, root: Path, profile: int | None, case_id: str,
              arguments: list[str]):
        need(digest(Path(self.launcher[-1])) == self.binary_sha, 'ACTUAL_LAUNCHED_ELF_BYTES_CHANGED')
        context = {'role': role, 'target': self.target, 'repetition': self.repetition,
                   'profile': profile, 'case_id': case_id, 'fixture_root': str(root),
                   'elf_sha256': self.binary_sha}
        self.active = Child(self.launcher + arguments, SANITIZER_ENVIRONMENT[self.target],
                            self.deadline, self.trace, context)
        self.starts += 1
        self.active.runtime = self
        return self.active

    def observe(self, child: Child, root: Path, phase: str):
        value = snapshot(child, root, phase)
        runtime_observation(self, value)
        return value

    def cleanup(self, root: Path):
        need(self.active is None or self.active.waited, 'FIXTURE_CLEANUP_WITH_LIVE_CHILD')
        self.trace.emit('cleanup', fixture_root=str(root), role='test-only-after-observation')
        shutil.rmtree(root)
        need(time.monotonic() <= self.deadline, 'FIXED_BUDGET_EXCEEDED')


class ReplayRuntime:
    def __init__(self, cursor: Cursor, launcher: list[str], binary_sha: str,
                 target: str, repetition: int, deadline_ns: int):
        self.cursor, self.launcher, self.binary_sha = cursor, launcher, binary_sha
        self.target, self.repetition, self.deadline_ns = target, repetition, deadline_ns
        self.starts = 0
        self.resources = None
        self.fixture_sizes = None
        self.maximum_fixture_logical_bytes = 0
        self.maximum_fixture_allocated_bytes = 0
        self.maximum_observed_process_rss_bytes = 0

    def begin(self, case_id: str, profile: int | None) -> Path:
        value = self.cursor.take('case', 'EXACT_CASE_SET_MISMATCH')
        need(value.get('target') == self.target and value.get('repetition') == self.repetition and
             value.get('case_id') == case_id and value.get('profile') == profile,
             'EXACT_CASE_SET_MISMATCH')
        root = Path(value['fixture_root'])
        need(root.is_absolute() and str(root).startswith('/tmp/fe09-a2-') and
             '..' not in root.parts and len(str(root)) < 120, 'UNSAFE_RECORDED_FIXTURE_ROOT')
        return root

    def start(self, role: str, root: Path, profile: int | None, case_id: str,
              arguments: list[str]):
        context = {'role': role, 'target': self.target, 'repetition': self.repetition,
                   'profile': profile, 'case_id': case_id, 'fixture_root': str(root),
                   'elf_sha256': self.binary_sha}
        self.starts += 1
        child = ReplayChild(self.cursor, self.launcher + arguments,
                            SANITIZER_ENVIRONMENT[self.target], context, self.deadline_ns)
        child.runtime = self
        return child

    def observe(self, child: ReplayChild, _root: Path, phase: str):
        child.flush()
        value = self.cursor.take('observe', 'INCOMPLETE_RECOVERY_PROTOCOL')
        need(value.get('serial') == child.serial and value.get('phase') == phase,
             'INCOMPLETE_RECOVERY_PROTOCOL')
        observation = value['snapshot']
        validate_snapshot(observation)
        runtime_observation(self, observation)
        return observation

    def cleanup(self, root: Path):
        value = self.cursor.take('cleanup')
        need(value == {'kind': 'cleanup', 'fixture_root': str(root),
                       'role': 'test-only-after-observation'}, 'FIXTURE_CLEANUP_UNPROVEN')


def semantic_result(value: dict) -> dict:
    """Exclude actual host identities, addresses, runtime and instrumentation size."""
    return {key: value[key] for key in ('rc', 'c', 'k', 'u', 'commit', 'v', 'b', 'h', 'cf', 'rf')
            if key in value}


def runtime_observation(runtime, value: dict) -> None:
    runtime.maximum_fixture_logical_bytes = max(runtime.maximum_fixture_logical_bytes, value['fixture_logical_bytes'])
    runtime.maximum_fixture_allocated_bytes = max(runtime.maximum_fixture_allocated_bytes,
                                                   value['host_filesystem_allocated_bytes'])


def runtime_wait_observation(runtime, usage: dict) -> None:
    need(usage.get('scope') == 'owned-child-entire-lifetime-including-fork-exec-transition' and
         all(type(usage.get(key)) is int and usage[key] >= 0 for key in
             ('maximum_rss_bytes', 'user_cpu_ns', 'system_cpu_ns', 'minor_page_faults', 'major_page_faults')) and
         usage['maximum_rss_bytes'] > 0, 'ACTUAL_OWNED_CHILD_RUSAGE_UNAVAILABLE')
    runtime.maximum_observed_process_rss_bytes = max(runtime.maximum_observed_process_rss_bytes,
                                                      usage['maximum_rss_bytes'])


def runtime_resources(runtime, event: dict) -> int:
    values, fixtures = event.get('r'), event.get('z')
    need(type(values) is list and len(values) == 6 and all(type(x) is int and x > 0 for x in values) and
         values[0] == 32768 and values[1] <= values[0] and values[4:] == [12288, 8192] and
         type(fixtures) is list and len(fixtures) == 4 and all(type(x) is int and x > 0 for x in fixtures),
         'ACTUAL_ABI_AND_WORKSPACE_SIZE_OBSERVATION_MISSING')
    amount = sum(values[index] for index in (0, 2, 3, 4, 5))
    need(amount <= 65536, 'A2_EXPLICIT_STATE_AND_WORK_LIMIT_EXCEEDED')
    if runtime.resources is None:
        runtime.resources, runtime.fixture_sizes = values, fixtures
    need(runtime.resources == values and runtime.fixture_sizes == fixtures,
         'SAME_ELF_RESOURCE_ABI_CHANGED_ACROSS_EXEC')
    return amount


def run_pair(runtime, profile: int, point: dict | None) -> dict:
    case_id = point['id'] if point else 'positive'
    stop = int(case_id[1:]) if point else 0
    root = runtime.begin(case_id, profile)
    child = None
    try:
        child = runtime.start('transaction', root, profile, case_id,
                              ['transaction', str(root), str(profile), str(stop)])
        anchor, anchor_events = read_until(child, 'anchor')
        need(len(anchor_events) == 1, 'TRANSACTION_RAN_BEFORE_PARENT_ANCHOR_CONFIRMATION')
        resource_bytes = runtime_resources(runtime, anchor)
        original = runtime.observe(child, root, 'original-before-ack')
        command = check_anchor(anchor, original)
        need(anchor['a'][0] == 301 + profiles()[profile]['mics'] and
             anchor['a'][1] == 1234509876, 'FIXED_ORIGINAL_SOURCE_PROFILE_MISMATCH')
        child.send(command)
        completed, transaction_events = read_until(child, 'td', stop_point=stop)
        barriers = [e['p'] for e in transaction_events if e['e'] == 'p']
        need(barriers == list(range(1, (stop if stop else 57) + 1)),
             'REGISTERED_CRASH_CONTROL_FLOW_NOT_OBSERVED')
        stopped = runtime.observe(child, root, 'transaction-final' if not point else 'before-registered-kill')
        if point:
            need(completed['e'] == 'p' and completed['p'] == stop,
                 'ACTUAL_CRASH_TERMINATION_UNPROVEN')
            check_crash_snapshot(stopped, original, point)
            child.kill()
            child.finish(-signal.SIGKILL)
        else:
            check_common_result(completed, transaction_events, fresh=False)
            need(completed['m'] == resource_bytes, 'RUNTIME_RESOURCE_SUM_MISMATCH')
            need(completed['rc'] == 0 and completed['k'] == 16 and
                 completed['u'] == 16 and completed['commit'] is True,
                 'NORMAL_FINITE_RETIREMENT_NOT_COMPLETE')
            old = [e for e in transaction_events if e['e'] == 'old']
            need(len(old) == 1 and old[0].get('a0') == 1 and old[0].get('a1') == 1 and
                 old[0].get('pre') == [32, 32, 32] and old[0].get('post') == [32, 32, 32] and
                 completed.get('old') == [1, 1], 'REAL_P0_BOUND_OLD_READER_REJECTION_MISSING')
            need(stopped['missing'] == list(range(1, 17)) and
                 stopped['retained_sha256'] == original['retained_sha256'] and
                 same_roots(stopped, original, control=False) and
                 control_state(stopped) == 'final_only' and
                 stopped['roots']['control'][0]['sha256'] == anchor['h'] and
                 completed['h'] == anchor['h'] and
                 completed['b'] == [original['data_logical_bytes'], original['retained_logical_bytes']],
                 'NORMAL_PARENT_FINAL_OBSERVATION_MISMATCH')
            child.finish(0)
        # finish() observes actual wait before this second process is created.
        child = runtime.start('recovery', root, profile, case_id,
                              ['recovery', str(root), *[str(x) for x in anchor['a']], anchor['h']])
        read_result, read_events = read_until(child, 'rd')
        check_common_result(read_result, read_events, fresh=True)
        need(read_result['m'] == resource_bytes, 'RUNTIME_RESOURCE_SUM_MISMATCH')
        after_read = runtime.observe(child, root, 'read-only-before-resume')
        need(after_read == stopped and read_result['u'] == 0 and read_result['commit'] is False,
             'READONLY_RECOVERY_CHANGED_NAMESPACE_OR_CLAIMED_COMMIT')
        readable = not point or stop >= 6
        expected_k = point['expected_k'] if point else 16
        if readable:
            need(read_result['rc'] == 0 and read_result['k'] == expected_k and
                 read_result['h'] == anchor['h'], 'REGISTERED_CRASH_ORACLE_MISMATCH')
        else:
            need(read_result['rc'] == -1 and read_result['k'] is None and
                 read_result['c'] == ('MISSING_CONTROL_ROOT' if stop == 1 else
                                      'ORPHAN_OR_UNKNOWN_CONTROL_TEMP'),
                 'REGISTERED_CRASH_ORACLE_MISMATCH')
        child.send('RESUME\n')
        resumed, resume_events = read_until(child, 'rs')
        check_common_result(resumed, resume_events, fresh=True)
        need(resumed['m'] == resource_bytes, 'RUNTIME_RESOURCE_SUM_MISMATCH')
        need(resumed.get('rb') == [3, 1, 1, 1] and resumed.get('pc') == [0, 1],
             'INCOMPLETE_RECOVERY_PROTOCOL')
        after_resume = runtime.observe(child, root, 'resume-result')
        if readable:
            need(resumed['rc'] == 0 and resumed['k'] == 16 and resumed['commit'] is True and
                 resumed['u'] == 16 - expected_k and after_resume['missing'] == list(range(1, 17)) and
                 after_resume['retained_sha256'] == original['retained_sha256'] and
                 same_roots(stopped, after_resume) and after_resume['directories'] == original['directories'] and
                 after_resume['extra_data_entries'] == 0 and after_resume['helper_entries'] == 0 and
                 resumed['h'] == anchor['h'] and resumed['b'] ==
                 [original['data_logical_bytes'], original['retained_logical_bytes']],
                 'REGISTERED_CRASH_ORACLE_MISMATCH')
        else:
            need(resumed['rc'] == -1 and resumed['k'] is None and resumed['u'] == 0 and
                 resumed['commit'] is False and after_resume == stopped and
                 resumed['c'] == ('MISSING_CONTROL_ROOT' if stop == 1 else
                                  'ORPHAN_OR_UNKNOWN_CONTROL_TEMP'),
                 'REGISTERED_CRASH_ORACLE_MISMATCH')
        child.finish(0)
        result = {'case_id': case_id, 'profile': profile, 'original_data_sha256': original['data_sha256'],
                  'original_retained_sha256': original['retained_sha256'],
                  'fpr1_raw_sha256': anchor['h'], 'read': semantic_result(read_result),
                  'resume': semantic_result(resumed), 'final_missing': after_resume['missing']}
        if not point:
            result['transaction'] = semantic_result(completed)
        runtime.cleanup(root)
        return result
    except BaseException:
        if child is not None:
            child.abort()
        if isinstance(runtime, LiveRuntime):
            try:
                runtime.trace.emit('failed_case_observation', fixture_root=str(root), snapshot=observe(root))
            except Exception:
                pass
            try:
                runtime.trace.emit('failure_cleanup', fixture_root=str(root), role='test-only-failure-cleanup')
            except Exception:
                pass
            shutil.rmtree(root, ignore_errors=True)
        raise


def check_injection(case: dict, events: list[dict]) -> None:
    number = int(case['id'][1:])
    _unlinks, _syncs, injected = io_counts(events)
    if number not in (108, 114) and not 121 <= number <= 144:
        need(not injected, 'UNREGISTERED_SYNTHETIC_IO_INJECTION')
        return
    need(injected and all(e['v'][8] == number for e in injected), 'REGISTERED_IO_INJECTION_UNOBSERVED')
    value = injected[-1]['v']
    if number == 108:
        need(value[1] == 2 and value[7] == 1 and value[9] == value[10] == 0 and
             value[14] == (value[13] ^ 1) and value[15] == value[16],
             'CROSS_DEVICE_STAT_MUTATION_NOT_PROVEN')
        return
    if number == 114:
        need(value[1] == 2 and value[3] == 9 and value[7] == 1 and value[9] == value[10] == 0 and
             value[16] == (1 if value[15] == 0 else 0) and value[13] == value[14],
             'FOREIGN_UID_STAT_MUTATION_NOT_PROVEN')
        return
    spec = case['mutation_target']
    operations = {'openat': 1, 'fstat': 2, 'read': 5, 'write': 6, 'fsync': 7,
                  'linkat': 8, 'unlinkat': 9, 'close': 10, 'readdir': 11}
    need(value[1] == operations[spec['syscall']] and value[5] == spec['matching_occurrence'],
         'REGISTERED_IO_OPERATION_OR_ORDINAL_MISMATCH')
    if number in (131, 138):
        need(value[7] == 1 and value[9] == 0 and value[10] == -1 and
             len(injected) == 1, 'REAL_CLOSE_ONCE_ERROR_NOT_PROVEN')
    else:
        need(value[7] == 0, 'INJECTED_SYSCALL_UNEXPECTEDLY_EXECUTED')
    errors = {'EIO': 5, 'EROFS': 30, 'ENOSPC': 28, 'EMFILE': 24, 'ENOENT': 2}
    if spec['injected_errno_or_return'] == 'EOF':
        need(value[10] == 0 and value[12] == 0, 'REGISTERED_EOF_NOT_OBSERVED')
    else:
        need(value[10] == -1 and value[12] == errors[spec['injected_errno_or_return']],
             'REGISTERED_ERRNO_NOT_OBSERVED')
    if number in (124, 130, 137):
        amount = 100 if number == 137 else 2384
        need(len(injected) == 2 and injected[0]['v'][5] == 1 and
             injected[0]['v'][7] == 1 and injected[0]['v'][9] == amount and
             injected[0]['v'][10] == amount, 'REAL_PARTIAL_PROGRESS_NOT_OBSERVED')
    if number == 141:
        successful = [e['v'][3] for e in events if e['e'] == 'io' and
                      e['v'][1:3] == [9, 4] and e['v'][4:6] == [1, 0]]
        need(successful == [9], 'PARTIAL_RETIREMENT_SEQ09_SIDE_EFFECT_NOT_PROVEN')


def negative_check(case: dict, nb: dict, nr: dict, result: dict, events: list[dict],
                   original: dict, injected: dict, after: dict) -> dict:
    number = int(case['id'][1:])
    for item in (original, injected, after):
        validate_snapshot(item)
    need(original['missing'] == [] and original['extra_data_entries'] == 0 and
         original['helper_entries'] == 0 and nb.get('o') == [32, 32, 32],
         'ORIGINAL_NEGATIVE_FIXTURE_NOT_INDEPENDENTLY_OBSERVED')
    expected_error = ('EXTERNAL_CHECKPOINT_RAW_DIGEST_MISMATCH' if number == 3 else case['expected_rejection'])
    need(result.get('rc') == -1 and result.get('c') == expected_error and
         result.get('commit') is False and result.get('u') == case['allowed_new_unlinks'],
         'REGISTERED_TARGET_C_REJECTION_NOT_OBSERVED_' + case['id'])
    observed = case['failure_receipt_observation']
    need(result.get('k') == observed['reported_prefix'] and
         (result.get('k') is not None) == observed['observed_prefix_known'],
         'FAILED_RUNTIME_PREFIX_KNOWLEDGE_FABRICATED_' + case['id'])
    need(after['missing'] == case['expected_missing_sequences'] and
         len(set(after['missing']) - set(injected['missing'])) == case['allowed_new_unlinks'] and
         not (set(injected['missing']) - set(after['missing'])),
         'PARENT_NEGATIVE_MISSING_SET_OR_SIDE_EFFECT_MISMATCH_' + case['id'])
    if case['namespace_unchanged_from_pre_call']:
        need(after['namespace_sha256'] == injected['namespace_sha256'] and
             after['directories'] == injected['directories'], 'NEGATIVE_CALL_CHANGED_NAMESPACE_' + case['id'])
    if case['retained_bytes_unchanged_from_pre_call']:
        need(after['retained_sha256'] == injected['retained_sha256'], 'NEGATIVE_CALL_CHANGED_RETAINED_BYTES')
    if case['root_bytes_unchanged_from_pre_call']:
        need(same_roots(after, injected, control=case.get('expected_control_namespace_after_call') is None or
                        case['namespace_unchanged_from_pre_call']), 'NEGATIVE_CALL_CHANGED_ORIGINAL_ROOT')
    need(nr.get('o') == result.get('o') and result.get('o') is not None,
         'NEGATIVE_CALL_CHANGED_LIVE_SOURCE_OWNER')
    if number != 146:
        need(nr.get('o') == [32, 32, 32], 'UNREGISTERED_SOURCE_OWNER_MUTATION')
    else:
        need(nr.get('o') == [32, 31, 32], 'UNDRAINED_SOURCE_MUTATION_NOT_OBSERVED')
    expected_control = case.get('expected_control_namespace_after_call')
    if expected_control is not None:
        aliases = {'part_0_bytes': 'part_empty', 'part_4768_bytes': 'part_complete',
                   'part_plus_final_same_inode_nlink2': 'part_and_final_same_inode'}
        need(control_state(after) == aliases.get(expected_control, expected_control),
             'REGISTERED_PARTIAL_PUBLICATION_STATE_MISMATCH')
    unlinks, syncs, injection_events = io_counts(events)
    need(type(result.get('io')) is list and len(result['io']) == 4 and
         all(type(x) is int and x >= 0 for x in result['io']) and
         result['io'][1:] == [unlinks, syncs, len(injection_events)] and unlinks == result['u'] and
         result.get('ack') == 0, 'NEGATIVE_UNLINK_COUNT_NOT_FROM_RAW_IO_OR_ACK_INVENTED')
    check_injection(case, events)
    if number in (3, 24):
        need(is_sha(nb.get('ah')) and is_sha(nr.get('ah')) and nb.get('a') == nr.get('a') and
             type(nb.get('a')) is list and len(nb['a']) == 8 and
             len(original['roots']['control']) == len(injected['roots']['control']) == 1,
             'EXTERNAL_DIGEST_MUTATION_PROVENANCE_MISSING')
        old_hash = original['roots']['control'][0]['sha256']
        new_hash = injected['roots']['control'][0]['sha256']
        need(nb['ah'] == old_hash and original['roots']['a1'] == injected['roots']['a1'],
             'EXTERNAL_DIGEST_CLEAN_CONTROL_NOT_ORIGINAL')
        if number == 3:
            mutated = f'{int(nb["ah"][:2], 16) ^ 1:02x}' + nb['ah'][2:]
            need(nr['ah'] == mutated and old_hash == new_hash and
                 original['namespace_sha256'] == injected['namespace_sha256'],
                 'N003_CALLER_DIGEST_ONLY_XOR1_NOT_PROVEN')
        else:
            need(nr['ah'] == nb['ah'] and new_hash != old_hash,
                 'N024_FIXED_CALLER_RESEALED_CHECKPOINT_NOT_PROVEN')
            old_entry, new_entry = original['roots']['control'][0], injected['roots']['control'][0]
            old_meta, new_meta = old_entry.get('fpr_metadata'), new_entry.get('fpr_metadata')
            need(type(old_meta) is dict and type(new_meta) is dict,
                 'N024_INDEPENDENT_CHECKPOINT_METADATA_MISSING')
            old_header = bytearray(base64.b64decode(old_meta['header_b64'], validate=True))
            new_header = bytearray(base64.b64decode(new_meta['header_b64'], validate=True))
            need(old_entry['bytes'] == new_entry['bytes'] == 4768 and
                 old_meta['body_sha256'] == new_meta['body_sha256'] and
                 old_header[176] == 0 and new_header[176] == 1 and
                 old_header[120:152].hex() == old_meta['zeroed_self_field_sha256'] and
                 new_header[120:152].hex() == new_meta['zeroed_self_field_sha256'] and
                 old_entry['name'] == old_meta['computed_final_name'] and
                 new_entry['name'] == new_meta['computed_final_name'] and
                 old_entry['name'] != new_entry['name'], 'N024_CONTROLLED_SELF_RESEAL_OR_CANONICAL_NAME_UNPROVEN')
            old_header[120:152] = new_header[120:152] = b'\0' * 32
            old_header[176] = 1
            need(old_header == new_header and original['data_sha256'] == injected['data_sha256'],
                 'N024_NON_TARGET_CHECKPOINT_OR_SOURCE_BYTES_CHANGED')
    if 89 <= number <= 104 or 161 <= number <= 164:
        need(result.get('v') == ([1, 1, 1, 0] if number <= 104 else [1, 1, 1, 1]),
             'ORIGINAL_CODEC_AND_OLD_A0_SEMANTIC_CONTROL_MISSING')
    if number in (1, 153):
        need('x' in nr and nr['x'] is None, 'ACTUAL_NULL_ANCHOR_MUTATION_NOT_PROVEN')
    if number == 2:
        need(nr.get('ah') == '0' * 64, 'ACTUAL_ZERO_DIGEST_MUTATION_NOT_PROVEN')
    if number in (4, 23):
        need(is_sha(nr.get('ah')) and len(injected['roots']['control']) == 1 and
             nr['ah'] != injected['roots']['control'][0]['sha256'],
             'ACTUAL_ANCHOR_MUTATION_WITNESS_MISSING')
        old_hash = original['roots']['control'][0]['sha256']
        expected = (f'{int(old_hash[:2], 16) ^ 1:02x}' + old_hash[2:] if number == 4 else
                    base64.b64decode(injected['roots']['control'][0]['fpr_metadata']['header_b64'],
                                     validate=True)[120:152].hex())
        need(nr['ah'] == expected and original['namespace_sha256'] == injected['namespace_sha256'],
             'EXACT_CALLER_ANCHOR_MUTATION_NOT_INDEPENDENTLY_PROVEN')
    if 105 <= number <= 107:
        x = nr.get('x')
        need(type(x) is list and len(x) == 3 and all(type(v) is int and v >= 0 for v in x) and
             x[((0, 1), (0, 2), (1, 2))[number - 105][0]] ==
             x[((0, 1), (0, 2), (1, 2))[number - 105][1]],
             'ACTUAL_DIRECTORY_ALIAS_NOT_PROVEN')
    if 109 <= number <= 111:
        x = nr.get('x')
        need(type(x) is list and len(x) == 4 and all(type(v) is int and v >= 0 for v in x) and
             x[2:] == injected['directories']['helper'][:2] and
             x[2:] != injected['directories'][('data', 'a1', 'control')[number - 109]][:2],
             'ACTUAL_BOUND_FD_REPLACEMENT_NOT_PROVEN')
    if number in (108, 114) or 121 <= number <= 144:
        need(nr.get('x') == number, 'ACTUAL_IO_FAULT_INSTALLATION_NOT_PROVEN')
    if 145 <= number <= 152:
        expected = [1, 32, 32, 32, 17, 32, 32, 1234509876, 16, 16, 0]
        changes = {145: (0, 0), 146: (2, 31), 147: (3, 0), 148: (3, 33),
                   149: (4, 1), 150: (4, 18), 151: (7, 1234509877), 152: (10, 1)}
        index, value = changes[number]
        expected[index] = value
        if number == 149:
            expected[5] = 16
        need(nr.get('x') == expected, 'ACTUAL_REQUEST_MUTATION_NOT_PROVEN')
    return {'case_id': case['id'], 'registered_expected_rejection': case['expected_rejection'],
            'runtime_error': result['c'], 'runtime_observed_prefix': result['k'],
            'candidate_new_unlinks': result['u'], 'parent_missing': after['missing'],
            'original_data_sha256': original['data_sha256'],
            'post_injection_data_sha256': injected['data_sha256'],
            'post_call_data_sha256': after['data_sha256'],
            'retained_sha256': after['retained_sha256'], 'actual_injected_events': len(injection_events)}


def run_negative_batch(runtime, cases: list[dict]) -> list[dict]:
    root = runtime.begin('negative-batch', None)
    child = runtime.start('negative-batch', root, None, 'negative-batch', ['negative-batch', str(root)])
    results = []
    try:
        for case in cases:
            number = int(case['id'][1:])
            profile = 47 if case['fixture_profile'].startswith('C4_UCA') else 0
            nb, pre_events = read_until(child, 'nb')
            need(len(pre_events) == 1 and nb.get('n') == number and nb.get('q') == profile,
                 'EXACT_CASE_SET_MISMATCH')
            original = runtime.observe(child, root, case['id'] + '-original')
            child.send('MUTATE\n')
            nr, mutation_events = read_until(child, 'nr')
            need(nr.get('n') == number and len(mutation_events) == 1,
                 'NEGATIVE_MUTATION_PROTOCOL_DRIFT')
            injected = runtime.observe(child, root, case['id'] + '-post-injection')
            child.send('RUN\n')
            result, events = read_until(child, 'nd')
            need(result.get('n') == number, 'EXACT_CASE_SET_MISMATCH')
            after = runtime.observe(child, root, case['id'] + '-post-call')
            results.append(negative_check(case, nb, nr, result, events, original, injected, after))
            child.send('CONTINUE\n')
        done = child.next()
        need(done.get('e') == 'nb_done' and done.get('count') == 157 and
             type(done.get('m')) is int and 0 < done['m'] <= 65536 and is_sha(done.get('d')),
             'INCOMPLETE_REAL_NEGATIVE_BATCH')
        need(done['m'] == runtime_resources(runtime, done), 'RUNTIME_RESOURCE_SUM_MISMATCH')
        child.finish(0)
        runtime.cleanup(root)
        return results
    except BaseException:
        child.abort()
        if isinstance(runtime, LiveRuntime):
            try:
                runtime.trace.emit('failed_case_observation', fixture_root=str(root), snapshot=observe(root))
            except Exception:
                pass
            shutil.rmtree(root, ignore_errors=True)
        raise


def run_suite(runtime, registered: dict) -> dict:
    scientific = []
    for profile in range(48):
        scientific.append(run_pair(runtime, profile, None))
    for profile in (0, 47):
        for point in registered['crash_points_per_profile']:
            scientific.append(run_pair(runtime, profile, point))
    negatives = [case for case in registered['negative_cases'] if case['layer'] == 'target_c']
    need(len(negatives) == 157, 'FROZEN_NEGATIVE_CASE_SET_MISMATCH')
    scientific.extend(run_negative_batch(runtime, negatives))
    need(runtime.starts == 325 and len(scientific) == 319, 'EXACT_CASE_SET_MISMATCH')
    return {'positive_profiles': 48, 'crash_scenarios': 114, 'target_c_negative_cases': 157,
            'logical_cases': len(scientific), 'process_starts': runtime.starts,
            'scientific_sha256': sha(canonical(scientific)), 'actual_abi_resource_sizes': runtime.resources,
            'actual_nested_fixture_type_sizes': runtime.fixture_sizes,
            'maximum_fixture_logical_bytes': runtime.maximum_fixture_logical_bytes,
            'maximum_fixture_host_allocated_bytes': runtime.maximum_fixture_allocated_bytes,
            'maximum_observed_host_process_rss_bytes': runtime.maximum_observed_process_rss_bytes}


def binary_identity(path: Path, *, elf_target: str | None = None) -> dict:
    resolved = path.resolve(strict=True)
    data = raw(resolved, 128 * 1024 * 1024)
    result = {'path': str(resolved), 'bytes': len(data), 'sha256': sha(data)}
    if elf_target is not None:
        need(data[:4] == b'\x7fELF' and data[5] == 1 and len(data) >= 64,
             'TARGET_ELF_HEADER_INVALID')
        machine = int.from_bytes(data[18:20], 'little')
        need((data[4], machine) == ((1, 40) if elf_target == 'arm' else (2, 62)),
             'TARGET_ELF_ARCHITECTURE_MISMATCH')
        result.update(elf_class=data[4], elf_machine=machine)
    return result


def tool_identity(name: str) -> dict:
    path = shutil.which(name)
    need(path is not None, 'REQUIRED_REAL_TOOL_UNAVAILABLE_' + name)
    return {'command': name, **binary_identity(Path(path))}


def tool_run(trace: Trace, command: list[str], target: str, tag: str,
             collect_deadline: float) -> bytes:
    child = None
    try:
        child = Child(command, {}, min(time.monotonic() + TOOL_SECONDS, collect_deadline),
                      trace, {'role': 'tool', 'target': target, 'tag': tag}, json_lines=False)
        while len(child.eof) != 2:
            child.pump()
        output = bytes(child.stdout)
        child.finish(0)
        return output
    except BaseException:
        if child is not None:
            child.abort()
        raise


def tool_replay(cursor: Cursor, command: list[str], target: str, tag: str,
                collect_deadline_ns: int, *, reason: str = 'EXACT_BUILD_COMMAND_MISMATCH') -> bytes:
    upcoming = cursor.peek()
    need(upcoming is not None and upcoming.get('command') == command, reason)
    child = ReplayChild(cursor, command, {}, {'role': 'tool', 'target': target, 'tag': tag},
                        collect_deadline_ns, json_lines=False)
    need(child.launch['deadline_monotonic_ns'] - child.launch['start_monotonic_ns'] <=
         TOOL_SECONDS * 1_000_000_000, 'FIXED_BUDGET_EXCEEDED')
    output = bytearray()
    while cursor.peek() is not None and cursor.peek().get('kind') == 'stdout':
        event = cursor.take('stdout')
        need(event.get('serial') == child.serial and type(event.get('raw_b64')) is str and
             len(event['raw_b64']) <= CHILD_CAP * 2, 'ORIGINAL_TOOL_STREAM_IDENTITY_MISMATCH')
        output.extend(base64.b64decode(event['raw_b64'], validate=True))
        need(len(output) <= CHILD_CAP, 'FIXED_BUDGET_EXCEEDED')
    child.total = len(output)
    child.finish(0)
    return bytes(output)


def source_readonly_bound(source: bytes) -> dict:
    # Every occurrence, including duplicate strings and #include names, gets a NUL.
    # This deliberately exceeds merged functional literals. Instrumentation strings
    # generated by GCC are reported separately in the actual section inventory.
    text = source.decode('utf-8')
    tokens = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*', re.S)
    cleaned = tokens.sub(lambda m: '' if m[0].startswith(('/*', '//')) else m[0], text)
    literals = re.findall(r'"(?:\\.|[^"\\])*"', cleaned)
    sizes = [len(ast.literal_eval(literal).encode('utf-8')) + 1 for literal in literals]
    # Only the three pointers in changed[] are additional static payload in this module.
    static_declarations = re.findall(r'static\s+const\s+char\s+(?:\*\s*const\s+)?(\w+)\s*\[([^]]*)\]\s*=', cleaned)
    need(sorted(static_declarations) == [('changed', '3'), ('hex', ''), ('hex', '')],
         'A2_STATIC_PAYLOAD_DECLARATION_REQUIRES_NEW_AUDIT')
    macro_count = len(re.findall(r'\bPRI[duxXio](?:32|64)\b', cleaned))
    macro_reserve = 8 * macro_count  # Larger than each supported integer format expansion.
    total = sum(sizes) + 3 * 8 + macro_reserve
    need(total <= 8192, 'A2_FUNCTIONAL_READONLY_RESERVE_EXCEEDED')
    return {'source_sha256': sha(source), 'literal_occurrences': len(sizes),
            'unmerged_literal_bytes_including_nuls': sum(sizes),
            'static_pointer_table_max_bytes': 24, 'integer_format_macro_reserve_bytes': macro_reserve,
            'functional_payload_upper_bound_bytes': total, 'readonly_reserve_bytes': 8192}


def parse_stack_usage(data: bytes) -> list[dict]:
    values = []
    for line in data.decode('utf-8').splitlines():
        columns = line.split('\t')
        need(len(columns) == 3 and columns[1].isdigit(), 'UNPARSEABLE_COMPILER_STACK_USAGE')
        values.append({'location': columns[0], 'bytes': int(columns[1]), 'kind': columns[2]})
    need(values, 'EMPTY_COMPILER_STACK_USAGE')
    return values


def callgraph_bound(data: bytes, execution_root: Path) -> dict:
    text = data.decode('utf-8')
    frames, labels, edges = {}, {}, {}
    string = r'"(?:\\.|[^"\\])*"'
    for match in re.finditer(r'node:\s*\{([^}]*)\}', text):
        fields = match[1]
        title = re.search(r'title:\s*(' + string + r')', fields)
        label = re.search(r'label:\s*(' + string + r')', fields)
        need(title is not None and label is not None, 'UNPARSEABLE_COMPILER_CALLGRAPH_NODE')
        key, description = json.loads(title[1]), json.loads(label[1])
        amount = re.search(r'\n(\d+) bytes \(([^)]+)\)', description)
        if amount:
            need(str(execution_root / SOURCE_C.relative_to(ROOT)) in description and
                 amount[2] in ('static', 'dynamic,bounded'), 'UNBOUNDED_OR_FOREIGN_A2_STACK_NODE')
            need(key not in frames, 'DUPLICATE_A2_CALLGRAPH_NODE')
            frames[key], labels[key], edges[key] = int(amount[1]), description.split('\n')[0], []
    need(frames, 'ACTUAL_A2_COMPILER_CALLGRAPH_MISSING')
    external = set()
    for match in re.finditer(r'edge:\s*\{([^}]*)\}', text):
        source = re.search(r'sourcename:\s*(' + string + r')', match[1])
        target = re.search(r'targetname:\s*(' + string + r')', match[1])
        need(source is not None and target is not None, 'UNPARSEABLE_COMPILER_CALLGRAPH_EDGE')
        start, end = json.loads(source[1]), json.loads(target[1])
        if start in frames:
            if end in frames:
                edges[start].append(end)
            else:
                external.add(end)
    done, active = {}, set()
    def longest(node):
        need(node not in active, 'RECURSIVE_A2_CALLGRAPH_UNQUALIFIED')
        if node in done:
            return done[node]
        active.add(node)
        suffix = max((longest(child) for child in edges[node]), default=(0, []), key=lambda x: x[0])
        active.remove(node)
        done[node] = (frames[node] + suffix[0], [labels[node], *suffix[1]])
        return done[node]
    size, path = max((longest(node) for node in frames), key=lambda x: x[0])
    callbacks = [longest(key)[0] for key in frames if labels[key] == 'pcm']
    need(len(callbacks) == 1, 'ORIGINAL_CODEC_CALLBACK_STACK_EDGE_UNPROVEN')
    conservative = size + callbacks[0]
    need(conservative <= 12288, 'A2_LOCAL_STACK_RESERVE_EXCEEDED')
    return {'maximum_new_module_direct_chain_bytes': size, 'maximum_new_module_direct_chain': path,
            'indirect_original_codec_pcm_callback_bound_bytes': callbacks[0],
            'conservative_new_module_stack_bound_bytes': conservative, 'local_stack_reserve_bytes': 12288,
            'new_module_frames_sum_bytes': sum(frames.values()), 'defined_frames': len(frames),
            'external_callees_excluded_from_new_module_budget': sorted(external), 'acyclic': True}


def section_sizes(data: bytes) -> dict:
    result = {}
    for line in data.decode('utf-8').splitlines():
        columns = line.split()
        if len(columns) == 3 and columns[0].startswith('.') and columns[1].isdigit() and columns[2].isdigit():
            need(columns[0] not in result, 'DUPLICATE_OBJECT_SECTION')
            result[columns[0]] = int(columns[1])
    need('.text' in result and '.data' in result and '.bss' in result,
         'ACTUAL_OBJECT_SECTION_INVENTORY_MISSING')
    return result


def resource_report(payload: dict, size_output: bytes, target: str, execution_root: Path) -> dict:
    need(payload.get('target') == target and payload.get('core_index') == SOURCES.index(SOURCE_C),
         'A2_RESOURCE_OBJECT_IDENTITY_MISMATCH')
    raw_su = payload['stack_usage']
    need(set(raw_su) == {str(index) for index in range(len(SOURCES))}, 'ACTUAL_SOURCE_STACK_CLOSURE_INCOMPLETE')
    stacks = {index: parse_stack_usage(compiler_report_bytes(value, 256 * 1024))
              for index, value in raw_su.items()}
    core = stacks[str(SOURCES.index(SOURCE_C))]
    need(all(v['kind'] in ('static', 'dynamic,bounded') for v in core), 'UNBOUNDED_A2_COMPILER_STACK_USAGE')
    graph = callgraph_bound(compiler_report_bytes(payload['callgraph'], TRACE_RECORD_CAP), execution_root)
    sections = section_sizes(size_output)
    ro = sum(value for key, value in sections.items() if
             key.startswith(('.rodata', '.data.rel.ro', '.srodata', '.rdata', '.gnu.linkonce.r')))
    if target != 'sanitized':
        need(ro <= 8192 and sections['.data'] == sections['.bss'] == 0,
             'A2_FUNCTIONAL_STATIC_SECTION_RESERVE_EXCEEDED')
    literal = source_readonly_bound(raw(SOURCE_C))
    other = {relative(SOURCES[int(index)]): {'maximum_reported_frame_bytes': max(v['bytes'] for v in frames),
                                              'sum_reported_frames_bytes': sum(v['bytes'] for v in frames),
                                              'frame_count': len(frames),
                                              'dynamic_or_unbounded': [v for v in frames if v['kind'] != 'static']}
             for index, frames in stacks.items() if int(index) != SOURCES.index(SOURCE_C)}
    return {'new_core_stack': graph, 'new_core_raw_section_bytes': sections,
            'actual_readonly_and_relro_section_bytes': ro, 'functional_readonly_source_bound': literal,
            'sanitizer_generated_sections_included_above': target == 'sanitized',
            'instrumented_elf_total_is_not_a2_explicit_state_budget': True,
            'workspace_reserved_bytes': 32768,
            'actual_workspace_used_owner_and_receipt_sizes_are_in_suite_raw_events': True,
            'resource_limit_bytes': 65536, 'old_modules_and_fixture_stacks_separate': other,
            'hosted_measurement_is_not_whole_device_memory': True}


def build_target(trace: Trace, target: str, directory: Path, collect_deadline: float) -> dict:
    commands, link, launcher = compile_plan(target, ROOT, directory)
    compiler = tool_identity(commands[0][0])
    size_name = 'arm-linux-gnueabihf-size' if target == 'arm' else 'size'
    size_tool = tool_identity(size_name)
    qemu = tool_identity('qemu-arm') if target == 'arm' else None
    trace.emit('build_start', target=target, compiler=compiler, size_tool=size_tool, qemu=qemu)
    version = tool_run(trace, [compiler['command'], '--version'], target, 'compiler-version', collect_deadline)
    need(version.strip(), 'COMPILER_VERSION_UNOBSERVED')
    if target == 'arm':
        qemu_version = tool_run(trace, ['qemu-arm', '--version'], target, 'qemu-version', collect_deadline)
        need(qemu_version.strip() and Path('/usr/arm-linux-gnueabihf').is_dir(),
             'REAL_ARM_SYSROOT_OR_QEMU_UNAVAILABLE')
    else:
        qemu_version = b''
    for index, command in enumerate(commands):
        tool_run(trace, command, target, 'compile-' + str(index), collect_deadline)
    tool_run(trace, link, target, 'link', collect_deadline)
    executable = directory / (target + '.elf')
    binary = binary_identity(executable, elf_target=target)
    core_index = SOURCES.index(SOURCE_C)
    core_object = directory / f'{target}-{core_index}.o'
    sizes = tool_run(trace, [size_name, '-A', str(core_object)], target, 'core-size', collect_deadline)
    payload = {'target': target, 'core_index': core_index,
               'core_object': binary_identity(core_object),
               'stack_usage': {str(index): compiler_report(raw(directory / f'{target}-{index}.su', 256 * 1024))
                               for index in range(len(SOURCES))},
               'callgraph': compiler_report(raw(directory / f'{target}-{core_index}.ci', TRACE_RECORD_CAP))}
    trace.emit('resource_evidence', **payload)
    accounting = resource_report(payload, sizes, target, ROOT)
    result = {'compiler': compiler, 'compiler_version_sha256': sha(version), 'size_tool': size_tool,
              'qemu': qemu, 'qemu_version_sha256': sha(qemu_version) if qemu else None,
              'elf': binary, 'launcher': launcher, 'compile_commands': commands, 'link_command': link,
              'resource_accounting': accounting}
    trace.emit('build_end', target=target, result=result)
    return result


def build_replay(cursor: Cursor, target: str, execution_root: Path, directory: Path,
                 collect_deadline_ns: int) -> dict:
    start = cursor.take('build_start')
    need(start.get('target') == target, 'FOUR_TARGET_SET_INCOMPLETE')
    commands, link, launcher = compile_plan(target, execution_root, directory)
    for key, command in (('compiler', commands[0][0]),
                         ('size_tool', 'arm-linux-gnueabihf-size' if target == 'arm' else 'size')):
        entry = start[key]
        need(entry['command'] == command and Path(entry['path']).is_absolute() and
             type(entry['bytes']) is int and entry['bytes'] > 0 and is_sha(entry['sha256']),
             'ACTUAL_TOOL_BINARY_IDENTITY_MISSING')
    version = tool_replay(cursor, [commands[0][0], '--version'], target, 'compiler-version', collect_deadline_ns)
    need(version.strip(), 'COMPILER_VERSION_UNOBSERVED')
    qemu_version = b''
    if target == 'arm':
        need(type(start.get('qemu')) is dict and start['qemu']['command'] == 'qemu-arm' and
             is_sha(start['qemu']['sha256']), 'TARGET_LAUNCHER_OR_ELF_MISMATCH')
        qemu_version = tool_replay(cursor, ['qemu-arm', '--version'], target, 'qemu-version', collect_deadline_ns)
    else:
        need(start.get('qemu') is None, 'TARGET_LAUNCHER_OR_ELF_MISMATCH')
    for index, command in enumerate(commands):
        tool_replay(cursor, command, target, 'compile-' + str(index), collect_deadline_ns,
                    reason='SANITIZER_COMPILE_PLAN_MISMATCH' if target in ('sanitized', 'tsan') else 'EXACT_BUILD_COMMAND_MISMATCH')
    tool_replay(cursor, link, target, 'link', collect_deadline_ns,
                reason='SANITIZER_LINK_PLAN_MISMATCH' if target in ('sanitized', 'tsan') else 'EXACT_BUILD_COMMAND_MISMATCH')
    core_index = SOURCES.index(SOURCE_C)
    sizes = tool_replay(cursor, [start['size_tool']['command'], '-A', str(directory / f'{target}-{core_index}.o')],
                        target, 'core-size', collect_deadline_ns)
    resource_event = cursor.take('resource_evidence')
    accounting = resource_report(resource_event, sizes, target, execution_root)
    end = cursor.take('build_end')
    need(end.get('target') == target, 'FOUR_TARGET_SET_INCOMPLETE')
    binary = end['result']['elf']
    need(binary.get('path') == str(directory / (target + '.elf')) and
         is_sha(binary.get('sha256')) and type(binary.get('bytes')) is int and binary['bytes'] > 0 and
         (binary.get('elf_class'), binary.get('elf_machine')) == ((1, 40) if target == 'arm' else (2, 62)),
         'TARGET_LAUNCHER_OR_ELF_MISMATCH')
    expected = {'compiler': start['compiler'], 'compiler_version_sha256': sha(version),
                'size_tool': start['size_tool'], 'qemu': start['qemu'],
                'qemu_version_sha256': sha(qemu_version) if target == 'arm' else None,
                'elf': binary, 'launcher': launcher, 'compile_commands': commands, 'link_command': link,
                'resource_accounting': accounting}
    need(end['result'] == expected, 'BUILD_SUMMARY_NOT_DERIVED_FROM_ORIGINAL_TRACE')
    return expected


def transport_contract() -> dict:
    return {'codec': TRANSPORT, 'block_target_bytes': TRACE_BLOCK_TARGET,
            'maximum_record_or_block_plain_bytes': TRACE_RECORD_CAP,
            'maximum_total_plain_trace_bytes': EXPANDED_LOG_CAP,
            'child_uncompressed_stdout_bytes': CHILD_CAP, 'child_uncompressed_stderr_bytes': CHILD_CAP,
            'collect_log_encoded_bytes': LIMITS['collect.log'], 'zlib_level': 9,
            'compiler_reports': 'complete-raw-utf8-within-outer-trace-budget',
            'ordered_contiguous_block_indices': True, 'trailing_or_concatenated_streams_allowed': False,
            'preserves_every_record_and_raw_child_byte': True}


def seal(directory: Path, receipt: dict, verification: bytes) -> None:
    content = canonical(receipt) + b'\n'
    need(len(content) <= LIMITS['receipt.json'] and len(verification) <= LIMITS['verify.log'],
         'FIXED_BUDGET_EXCEEDED')
    (directory / 'receipt.json').write_bytes(content)
    (directory / 'verify.log').write_bytes(verification)
    manifest = ''.join(f'{sha(raw(directory / name, LIMITS[name]))}  {name}\n'
                       for name in ('receipt.json', 'collect.log', 'verify.log')).encode('ascii')
    need(len(manifest) <= LIMITS['SHA256SUMS'], 'FIXED_BUDGET_EXCEEDED')
    (directory / 'SHA256SUMS').write_bytes(manifest)


def original_members(directory: Path) -> dict[str, bytes]:
    need(directory.is_dir() and not directory.is_symlink() and
         {path.name for path in directory.iterdir()} == set(MEMBERS), 'EXACT_FOUR_MEMBER_BUNDLE_REQUIRED')
    values = {name: raw(directory / name, LIMITS[name]) for name in MEMBERS}
    expected = ''.join(f'{sha(values[name])}  {name}\n'
                       for name in ('receipt.json', 'collect.log', 'verify.log')).encode('ascii')
    need(values['SHA256SUMS'] == expected, 'ORIGINAL_FOUR_MEMBER_DIGEST_MISMATCH')
    # ZIP_STORED is an upper bound for the governed uploaded four small members.
    # Includes per-entry local/central headers plus EOCD, without retaining a second artifact.
    maximum_stored_zip = sum(len(data) + 30 + len(name) + 46 + len(name)
                             for name, data in values.items()) + 22
    need(maximum_stored_zip <= 32 * 1024 * 1024, 'FIXED_BUDGET_EXCEEDED')
    return values


def check_receipt_authority(receipt: dict) -> None:
    mapped = {'hosted_checkpoint_committed_on_read': 'EVIDENCE_READONLY_RECOVERY_MISLABELED_AS_COMMIT',
              'original_ack_created': 'EVIDENCE_INVENTED_ORIGINAL_ACK_IN_RECEIPT',
              'continuous_rolling_qualified': 'EVIDENCE_CONTINUOUS_ROLLING_CLAIM_IN_RECEIPT',
              'physical_powerloss_qualified': 'EVIDENCE_PHYSICAL_POWERLOSS_CLAIM_IN_RECEIPT',
              'retired_pcm_reverified_after_delete': 'EVIDENCE_CLAIM_RETIRED_PCM_REVERIFIED_AFTER_DELETION'}
    for name, rejection in mapped.items():
        need(receipt.get(name) is False, rejection)
    need(all(receipt.get(name) is False for name in FALSE), 'UNQUALIFIED_AUTHORITY_CLAIM')


def check_declared_source(receipt: dict, expected: dict) -> None:
    need(receipt.get('source_commit') == expected['source_commit'], 'CURRENT_EXECUTION_SOURCE_MISMATCH')
    declared = receipt.get('frozen_original_inputs')
    need(type(declared) is dict, 'FROZEN_ORIGINAL_SOURCE_OR_COMPILE_CLOSURE_MISMATCH')
    for filename, reason in (
        ('fe09_b2s3_t3s2b1ba0_finite_outboard.c', 'EVIDENCE_MODIFIED_OLD_A0_TO_ACCEPT_MISSING_PREFIX'),
        ('fe09_b2s3_t3s2b1ba1_anchor_root.c', 'EVIDENCE_MODIFIED_OLD_A1_TO_ACCEPT_MISSING_PREFIX')):
        name = relative(HERE / filename)
        need(declared.get(name) == expected['frozen_original_inputs'][name], reason)
    need(declared == expected['frozen_original_inputs'] and
         receipt.get('compile_source_closure') == expected['compile_source_closure'],
         'FROZEN_ORIGINAL_SOURCE_OR_COMPILE_CLOSURE_MISMATCH')
    need(all(receipt.get(key) == value for key, value in expected.items()),
         'CURRENT_IMPLEMENTATION_SOURCE_OR_PREREGISTRATION_MISMATCH')


def verify_values(values: dict[str, bytes], expected: dict) -> dict:
    receipt = strict_json(values['receipt.json'].decode('utf-8'))
    need(type(receipt) is dict, 'INVALID_RECEIPT_SCHEMA')
    check_receipt_authority(receipt)
    check_declared_source(receipt, expected)
    need(receipt.get('decision') == DECISION and receipt.get('actual_targets_complete') is True and
         receipt.get('finite_prefix_retirement_completed') is True and
         receipt.get('retired_original_files') == receipt.get('retained_original_files') == 16,
         'FINITE_RETIREMENT_NOT_ADMITTED')
    need(receipt.get('target_order') == list(TARGETS) and
         set(receipt.get('builds', {})) == set(TARGETS) and
         set(receipt.get('suite_results', {})) == set(TARGETS), 'FOUR_TARGET_SET_INCOMPLETE')
    need(receipt.get('repetitions_per_target') == 2 and
         all(type(receipt['suite_results'][target]) is list and len(receipt['suite_results'][target]) == 2
             for target in TARGETS), 'SECOND_REAL_SUITE_MISSING')
    need(type(receipt.get('collect_elapsed_ns')) is int and
         0 < receipt['collect_elapsed_ns'] <= COLLECT_SECONDS * 1_000_000_000,
         'FIXED_BUDGET_EXCEEDED')
    need(values['verify.log'] == MARKER.encode(), 'ORIGINAL_VERIFICATION_MARKER_MISSING')
    cursor = Cursor(values['collect.log'])
    header = cursor.take('collection')
    need(header.get('source_commit') == expected['source_commit'], 'CURRENT_EXECUTION_SOURCE_MISMATCH')
    need(header.get('identity') == expected, 'CURRENT_IMPLEMENTATION_SOURCE_OR_PREREGISTRATION_MISMATCH')
    need(header.get('transport') == transport_contract(), 'UNREGISTERED_TRACE_TRANSPORT')
    need(receipt.get('transport') == header['transport'], 'UNREGISTERED_TRACE_TRANSPORT')
    execution_root, build_directory = Path(header['execution_root']), Path(header['build_directory'])
    need(execution_root.is_absolute() and build_directory.is_absolute() and
         '..' not in execution_root.parts and '..' not in build_directory.parts and
         str(build_directory).startswith('/tmp/fe09-a2-build-') and
         header.get('generated_build_header_sha256') == sha(BUILD_HEADER.encode()),
         'UNREGISTERED_EXECUTION_BUILD_DIRECTORY_OR_HEADER')
    start_ns, deadline_ns = header['start_monotonic_ns'], header['deadline_monotonic_ns']
    need(type(start_ns) is int and type(deadline_ns) is int and start_ns > 0 and
         0 < deadline_ns - start_ns <= COLLECT_SECONDS * 1_000_000_000,
         'FIXED_BUDGET_EXCEEDED')
    suite_identity = None
    actual_builds, actual_suites = {}, {}
    previous_end = start_ns
    registered = contract()
    for target in TARGETS:
        built = build_replay(cursor, target, execution_root, build_directory, deadline_ns)
        actual_builds[target] = built
        actual_suites[target] = []
        for repetition in (1, 2):
            begin = cursor.take('suite_start', 'SECOND_REAL_SUITE_MISSING')
            need(begin.get('target') == target and begin.get('repetition') == repetition,
                 'SECOND_REAL_SUITE_MISSING')
            suite_start, suite_deadline = begin['start_monotonic_ns'], begin['deadline_monotonic_ns']
            need(type(suite_start) is int and type(suite_deadline) is int and
                 previous_end <= suite_start < suite_deadline <= deadline_ns and
                 suite_deadline - suite_start <= SUITE_SECONDS * 1_000_000_000,
                 'FIXED_BUDGET_EXCEEDED')
            runtime = ReplayRuntime(cursor, built['launcher'], built['elf']['sha256'],
                                    target, repetition, suite_deadline)
            result = run_suite(runtime, registered)
            end = cursor.take('suite_end')
            need(end.get('target') == target and end.get('repetition') == repetition and
                 end.get('result') == result, 'SUITE_SUMMARY_NOT_DERIVED_FROM_RAW_TRACE')
            previous_end = end['end_monotonic_ns']
            need(type(previous_end) is int and suite_start < previous_end <= suite_deadline and
                 end.get('elapsed_ns') == previous_end - suite_start,
                 'FIXED_BUDGET_EXCEEDED')
            need(result['maximum_observed_host_process_rss_bytes'] > 0,
                 'REAL_FIXTURE_PROCESS_RSS_UNOBSERVED')
            if suite_identity is None:
                suite_identity = result['scientific_sha256']
            need(result['scientific_sha256'] == suite_identity,
                 'REAL_REPETITION_OR_CROSS_TARGET_SCIENTIFIC_RESULT_DRIFT')
            actual_suites[target].append({**result, 'elapsed_ns': end['elapsed_ns']})
    end = cursor.take('collection_end')
    need(end.get('decision') == DECISION and type(end.get('end_monotonic_ns')) is int and
         previous_end <= end['end_monotonic_ns'] <= deadline_ns and
         end.get('elapsed_ns') == end['end_monotonic_ns'] - start_ns and
         end['elapsed_ns'] == receipt['collect_elapsed_ns'], 'FIXED_BUDGET_EXCEEDED')
    need(cursor.peek() is None, 'UNREGISTERED_RETRY_OR_INCOMPLETE_INVOCATION_TRACE')
    need(receipt['builds'] == actual_builds and receipt['suite_results'] == actual_suites and
         receipt.get('scientific_sha256') == suite_identity and
         receipt.get('actual_target_process_starts') == 2600 and
         receipt.get('actual_target_logical_cases') == 2552,
         'RECEIPT_NOT_DERIVED_FROM_RAW_MULTIPROCESS_TRACE')
    need(receipt.get('host_resource_usage') == end.get('host_resource_usage') and
         type(end.get('host_resource_usage')) is dict and
         end['host_resource_usage']['scope'] == 'whole-collector-and-all-reaped-compiler-fixture-qemu-children',
         'HOST_RESOURCE_ATTRIBUTION_MISSING')
    return {'decision': DECISION, 'source_commit': expected['source_commit'],
            'actual_targets_complete': True, 'actual_target_process_starts': 2600,
            'actual_target_logical_cases': 2552, 'raw_trace_records': len(cursor.events),
            'expanded_trace_bytes': cursor.expanded_bytes,
            'scientific_sha256': suite_identity, 'original_four_member_sha256':
            {name: sha(data) for name, data in values.items()}}


def verify(directory: Path, source: str) -> dict:
    return verify_values(original_members(directory), identity(source))


def host_usage() -> dict:
    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'scope': 'whole-collector-and-all-reaped-compiler-fixture-qemu-children',
            'collector_maximum_rss_bytes': own.ru_maxrss * 1024,
            'maximum_reaped_child_rss_bytes': children.ru_maxrss * 1024,
            'collector_user_seconds': own.ru_utime, 'collector_system_seconds': own.ru_stime,
            'children_user_seconds': children.ru_utime, 'children_system_seconds': children.ru_stime,
            'rss_is_not_a2_explicit_state_or_whole_device_qualification': True}


def collect(directory: Path, source: str) -> dict:
    started = time.monotonic_ns()
    deadline_ns = started + COLLECT_SECONDS * 1_000_000_000
    deadline = deadline_ns / 1_000_000_000
    need(not directory.exists(), 'OUTPUT_ALREADY_EXISTS_PRESERVE_ORIGINAL_EVIDENCE')
    directory.mkdir(parents=True, mode=0o700)
    trace = Trace(directory / 'collect.log')
    receipt = {name: False for name in FALSE}
    receipt.update(decision=FAILURE, source_commit=source, actual_targets_complete=False,
                   finite_prefix_retirement_completed=False, builds={}, suite_results={})
    build_directory = None
    try:
        expected = identity(source, deadline=deadline)
        receipt.update(expected)
        build_directory = Path(tempfile.mkdtemp(prefix='fe09-a2-build-', dir='/tmp'))
        generated = build_directory / 'include/audio_pipeline/audio_pipeline_build.h'
        generated.parent.mkdir(parents=True)
        generated.write_text(BUILD_HEADER)
        trace.emit('collection', source_commit=source, identity=expected, execution_root=str(ROOT),
                   build_directory=str(build_directory), start_monotonic_ns=started,
                   deadline_monotonic_ns=deadline_ns, transport=transport_contract(),
                   generated_build_header_sha256=sha(BUILD_HEADER.encode()))
        registered = contract()
        scientific = None
        for target in TARGETS:
            built = build_target(trace, target, build_directory, deadline)
            receipt['builds'][target] = built
            receipt['suite_results'][target] = []
            for repetition in (1, 2):
                suite_start = time.monotonic_ns()
                suite_deadline = min(suite_start + SUITE_SECONDS * 1_000_000_000, deadline_ns)
                trace.emit('suite_start', target=target, repetition=repetition,
                           start_monotonic_ns=suite_start, deadline_monotonic_ns=suite_deadline)
                runtime = LiveRuntime(trace, built['launcher'], built['elf']['sha256'],
                                      target, repetition, suite_deadline / 1_000_000_000)
                result = run_suite(runtime, registered)
                suite_end = time.monotonic_ns()
                need(suite_end <= suite_deadline, 'FIXED_BUDGET_EXCEEDED')
                if scientific is None:
                    scientific = result['scientific_sha256']
                need(result['scientific_sha256'] == scientific,
                     'REAL_REPETITION_OR_CROSS_TARGET_SCIENTIFIC_RESULT_DRIFT')
                trace.emit('suite_end', target=target, repetition=repetition, result=result,
                           end_monotonic_ns=suite_end, elapsed_ns=suite_end - suite_start)
                receipt['suite_results'][target].append({**result, 'elapsed_ns': suite_end - suite_start})
        # Re-read exact source bytes after every real child, before admitting a bundle.
        need(identity(source, deadline=deadline) == expected, 'EXECUTION_SOURCE_CHANGED_DURING_COLLECTION')
        # Successful cleanup is part of the same fixed collection budget.
        shutil.rmtree(build_directory)
        build_directory = None
        completed = time.monotonic_ns()
        need(completed <= deadline_ns, 'FIXED_BUDGET_EXCEEDED')
        usage = host_usage()
        trace.emit('collection_end', decision=DECISION, end_monotonic_ns=completed,
                   elapsed_ns=completed - started, host_resource_usage=usage)
        trace.close()
        receipt.update(decision=DECISION, actual_targets_complete=True,
                       finite_prefix_retirement_completed=True, target_order=list(TARGETS),
                       repetitions_per_target=2, retained_original_files=16, retired_original_files=16,
                       actual_target_process_starts=2600, actual_target_logical_cases=2552,
                       scientific_sha256=scientific, collect_elapsed_ns=completed - started,
                       host_resource_usage=usage, transport=transport_contract())
        seal(directory, receipt, MARKER.encode())
        need(time.monotonic_ns() <= deadline_ns, 'FIXED_BUDGET_EXCEEDED')
        return receipt
    except BaseException as error:
        if not trace.file.closed:
            trace.failure(error)
            trace.close()
        receipt.update(decision=FAILURE, actual_targets_complete=False,
                       finite_prefix_retirement_completed=False,
                       collect_elapsed_ns=time.monotonic_ns() - started,
                       failure={'type': type(error).__name__, 'reason': str(error)[:1000]},
                       host_resource_usage=host_usage())
        seal(directory, receipt, (FAILURE + '\n' + str(error)[:2000] + '\n').encode())
        raise
    finally:
        if build_directory is not None:
            shutil.rmtree(build_directory, ignore_errors=True)


def encode_events(path: Path, events: list[dict]) -> None:
    trace = Trace(path)
    try:
        for event in events:
            trace.emit(event['kind'], **{key: value for key, value in event.items() if key != 'kind'})
    finally:
        trace.close()


def first_launch(events: list[dict], target: str, role: str, case_id: str,
                 profile: int = 0) -> dict:
    return next(event for event in events if event.get('kind') == 'launch' and
                event.get('target') == target and event.get('repetition') == 1 and
                event.get('role') == role and event.get('case_id') == case_id and
                event.get('profile') == profile)


def without_span(events: list[dict], start_kind: str, end_kind: str,
                 target: str, repetition: int | None = None) -> list[dict]:
    selected, active = [], False
    matched = 0
    for event in events:
        if (event.get('kind') == start_kind and event.get('target') == target and
            (repetition is None or event.get('repetition') == repetition)):
            need(not active, 'NESTED_NEGATIVE_COPY_TRACE_SPAN')
            active = True
            matched += 1
        if not active:
            selected.append(event)
        if active and event.get('kind') == end_kind and event.get('target') == target:
            active = False
    need(matched > 0 and not active, 'NEGATIVE_COPY_TARGET_SPAN_NOT_FOUND')
    return selected


def mutate_evidence(control_id: str, receipt: dict, events: list[dict], registered: dict) -> list[dict]:
    if control_id.startswith('N'):
        case = next(case for case in registered['negative_cases'] if case['id'] == control_id)
        target = case['mutation_target']
        if case['layer'] == 'python_receipt_readback':
            need(receipt[target['field']] is False and target['value'] is True,
                 'NEGATIVE_RECEIPT_PRECONDITION_NOT_ORIGINAL')
            receipt[target['field']] = True
        else:
            need(case['layer'] == 'python_source_lock_readback', 'WRONG_PYTHON_NEGATIVE_LAYER')
            entry = receipt['frozen_original_inputs'][target['path']]
            need(is_sha(entry['sha256']), 'NEGATIVE_SOURCE_PRECONDITION_NOT_ORIGINAL')
            entry['sha256'] = '0' * 64
        return events
    if control_id == 'E01':
        receipt['source_commit'] = '0' * 40
        events[0]['source_commit'] = '0' * 40
    elif control_id == 'E02':
        codec = relative(HERE / 'fe09_b2s2_private_apd.c')
        alternate = relative(HERE / 'alternate_apx3_codec.c')
        receipt['frozen_original_inputs'][alternate] = receipt['frozen_original_inputs'].pop(codec)
        receipt['frozen_original_inputs'][alternate]['sha256'] = '0' * 64
        receipt['compile_source_closure'] = [alternate if name == codec else name
                                             for name in receipt['compile_source_closure']]
    elif control_id == 'E03':
        receipt['target_order'].remove('arm')
        del receipt['builds']['arm'], receipt['suite_results']['arm']
        events = without_span(events, 'build_start', 'build_end', 'arm')
        events = without_span(events, 'suite_start', 'suite_end', 'arm')
    elif control_id == 'E04':
        receipt['suite_results']['tsan'].pop()
        events = without_span(events, 'suite_start', 'suite_end', 'tsan', 2)
    elif control_id in ('E05', 'E06'):
        target, flag = ('sanitized', '-fsanitize=address,undefined') if control_id == 'E05' else (
            'tsan', '-fsanitize=thread')
        for event in events:
            if event.get('target') != target:
                continue
            if event.get('kind') == 'launch' and event.get('role') == 'tool' and (
                event.get('tag', '').startswith('compile-') if control_id == 'E05' else event.get('tag') == 'link'):
                need(flag in event['command'], 'NEGATIVE_BUILD_PRECONDITION_NOT_ORIGINAL')
                event['command'].remove(flag)
            if event.get('kind') == 'build_end':
                plan = event['result']['compile_commands'] if control_id == 'E05' else [event['result']['link_command']]
                for command in plan:
                    command.remove(flag)
        plan = receipt['builds'][target]['compile_commands'] if control_id == 'E05' else [receipt['builds'][target]['link_command']]
        for command in plan:
            command.remove(flag)
    elif control_id == 'E07':
        first_launch(events, 'sanitized', 'transaction', 'positive')['environment']['ASAN_OPTIONS'] = 'detect_leaks=0:halt_on_error=1'
    elif control_id == 'E08':
        launch = first_launch(events, 'arm', 'transaction', 'positive')
        launch['command'] = [receipt['builds']['native']['elf']['path'], *launch['command'][4:]]
    elif control_id == 'E09':
        launch = first_launch(events, 'native', 'recovery', 'positive')
        launch['fresh_exec'] = False
        launch['replacement'] = 'in-process-owner-rebind'
    elif control_id == 'E10':
        serial = first_launch(events, 'native', 'transaction', 'P10')['serial']
        events = [event for event in events if not (event.get('serial') == serial and event['kind'] in ('kill', 'wait'))]
    elif control_id == 'E11':
        serial = first_launch(events, 'native', 'transaction', 'P05')['serial']
        event = next(event for event in events if event.get('serial') == serial and
                     event['kind'] == 'observe' and event['phase'] == 'before-registered-kill')
        original = event['snapshot']['roots']['control']
        need(len(original) == 2 and all(entry['nlink'] == 2 for entry in original),
             'NEGATIVE_CRASH_PRECONDITION_NOT_ORIGINAL')
        final = copy.deepcopy(next(entry for entry in original if entry['role'] == 'final'))
        final['nlink'] = 1
        event['snapshot']['roots']['control'] = [final]
    elif control_id == 'E12':
        serial = first_launch(events, 'native', 'recovery', 'P06')['serial']
        events = [event for event in events if not (event.get('serial') == serial and
                   event['kind'] == 'send' and event['text'] == 'RESUME\n')]
    elif control_id == 'E13':
        launch = first_launch(events, 'tsan', 'transaction', 'positive')
        index = next(index for index, event in enumerate(events) if event is launch)
        retry = copy.deepcopy(launch)
        retry['role'] = 'unregistered-startup-retry'
        events.insert(index, retry)
    elif control_id == 'E14':
        receipt['collect_elapsed_ns'] = 1501 * 1_000_000_000
        events[-1]['elapsed_ns'] = receipt['collect_elapsed_ns']
    elif control_id == 'E15':
        changed = False
        for event in events:
            if (event.get('target') == 'native' and event.get('repetition') == 1 and
                event.get('profile') == 0 and event.get('case_id') == 'P11'):
                event['case_id'] = 'P10'
                changed = True
        need(changed, 'NEGATIVE_CASE_PRECONDITION_NOT_ORIGINAL')
    else:
        raise NotAdmitted('UNREGISTERED_EVIDENCE_CONTROL_' + control_id)
    return events


def negative_readback(directory: Path, source: str) -> dict:
    expected = identity(source)
    originals = original_members(directory)
    original_result = verify_values(originals, expected)
    original_hashes = {name: sha(data) for name, data in originals.items()}
    registered = contract()
    controls = [case for case in registered['negative_cases'] if case['layer'].startswith('python_')]
    controls.extend(registered['evidence_integrity_controls'])
    need(len(controls) == 22 and {case['id'] for case in controls} ==
         {*(f'N{number:03d}' for number in range(154, 161)), *(f'E{number:02d}' for number in range(1, 16))},
         'EXACT_PYTHON_EVIDENCE_CONTROL_SET_MISMATCH')
    results = []
    for case in controls:
        copy_directory = Path(tempfile.mkdtemp(prefix='fe09-a2-evidence-' + case['id'] + '-', dir='/tmp'))
        receipt = strict_json(originals['receipt.json'].decode())
        events = Cursor(originals['collect.log']).events
        mutated = mutate_evidence(case['id'], receipt, events, registered)
        encode_events(copy_directory / 'collect.log', mutated)
        seal(copy_directory, receipt, originals['verify.log'])
        caught = None
        try:
            verify_values(original_members(copy_directory), expected)
        except NotAdmitted as error:
            caught = str(error)
        need(caught == case['expected_rejection'],
             f"EVIDENCE_CONTROL_WRONG_REJECTION_{case['id']}_expected={case['expected_rejection']}_actual={caught}_copy={copy_directory}")
        results.append({'id': case['id'], 'actual_rejection': caught,
                        'mutation_layer': case['layer'], 'resealed_four_member_copy': True,
                        'mutated_receipt_sha256': sha(raw(copy_directory / 'receipt.json', LIMITS['receipt.json'])),
                        'mutated_collect_log_sha256': sha(raw(copy_directory / 'collect.log', LIMITS['collect.log']))})
        shutil.rmtree(copy_directory)
    need({name: sha(data) for name, data in original_members(directory).items()} == original_hashes and
         identity(source) == expected, 'ORIGINAL_BUNDLE_OR_EXECUTION_SOURCE_CHANGED_DURING_CONTROLS')
    return {'decision': 'FE09_A2F0_REAL_ORIGINAL_BUNDLE_EVIDENCE_CONTROLS_PASS',
            'original_verified_first': original_result, 'original_unchanged': True,
            'python_receipt_controls': 5, 'python_source_controls': 2, 'python_integrity_controls': 15,
            'target_c_executions_created_by_evidence_controls': 0, 'controls': results}


def self_test() -> dict:
    frozen, registered = pins(), contract()
    need(len(profiles()) == 48 and [profile['index'] for profile in profiles()] == list(range(48)),
         'PROFILE_ENUMERATION_DRIFT')
    need([point['id'] for point in registered['crash_points_per_profile']] ==
         [f'P{number:02d}' for number in range(1, 58)], 'CRASH_ENUMERATION_DRIFT')
    target_negatives = [case for case in registered['negative_cases'] if case['layer'] == 'target_c']
    need([case['id'] for case in target_negatives] ==
         [*(f'N{number:03d}' for number in range(1, 154)), *(f'N{number:03d}' for number in range(161, 165))],
         'TARGET_NEGATIVE_ENUMERATION_DRIFT')
    need(len(SOURCES) == 22 and all(relative(path) in frozen for path in SOURCES[:-2]),
         'COMPILE_CLOSURE_NOT_ORIGINAL_PLUS_NEW_A2')
    readonly = source_readonly_bound(raw(SOURCE_C))
    sample = b'bounded transport only; this is not target runtime evidence\x00\n' * 17
    encoded = packed(sample)
    need(unpacked(encoded, len(sample)) == sample, 'LOSSLESS_TRANSPORT_SELF_TEST_FAILED')
    controls = 0
    for change in ('length', 'digest', 'trailing', 'concatenated', 'cap'):
        mutant = copy.deepcopy(encoded)
        if change == 'length':
            mutant['bytes'] += 1
        elif change == 'digest':
            mutant['sha256'] = '1' * 64
        elif change in ('trailing', 'concatenated'):
            suffix = b'extra' if change == 'trailing' else zlib.compress(b'another-stream')
            mutant['data'] = base64.b64encode(base64.b64decode(mutant['data']) + suffix).decode()
        try:
            unpacked(mutant, len(sample) - 1 if change == 'cap' else len(sample) + 1)
        except NotAdmitted:
            controls += 1
    need(controls == 5, 'LOSSLESS_TRANSPORT_REJECTION_SELF_TEST_FAILED')
    return {'decision': 'FE09_A2F0_STATIC_CONTRACT_SELF_TEST_ONLY', 'frozen_inputs_checked': 81,
            'positive_profiles': 48, 'registered_crash_points': 57, 'registered_target_c_negative_ids': 157,
            'targets_executed': 0, 'runtime_qualified': False, 'lossless_codec_negative_checks': controls,
            'transport': transport_contract(), 'functional_readonly_source_bound': readonly}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--self-test', action='store_true')
    modes.add_argument('--collect', action='store_true')
    modes.add_argument('--verify', action='store_true')
    modes.add_argument('--negative-readback', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execution-source')
    args = parser.parse_args()
    try:
        if args.self_test:
            result = self_test()
        else:
            need(args.output is not None and args.execution_source is not None,
                 'OUTPUT_AND_EXACT_EXECUTION_SOURCE_REQUIRED')
            directory = args.output.resolve()
            if args.collect:
                result = collect(directory, args.execution_source)
            elif args.verify:
                result = verify(directory, args.execution_source)
            else:
                result = negative_readback(directory, args.execution_source)
        print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
        return 0
    except (NotAdmitted, OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError,
            KeyError, TypeError, StopIteration, ValueError, zlib.error) as error:
        print(json.dumps({'decision': FAILURE, 'error_type': type(error).__name__, 'reason': str(error)},
                         sort_keys=True, separators=(',', ':')), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
