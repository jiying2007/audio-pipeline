"""Strict app_audio_test v2 intake for disclosed development diagnostics only."""
from __future__ import annotations

import argparse
from array import array
import csv
from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / '.github/research/frontend-evolution-v1/device-capture-d3.json'
ROLES = ('session.json', 'frames.csv', 'events.csv', 'mic.wav', 'ref_raw.wav', 'ref_used.wav', 'output.wav')
FRAME_FIELDS = ('mono_us', 'input_pts_us', 'epoch', 'stage', 'seq', 'file_sample_offset', 'samples', 'output_valid')
SCENES = ('quiet', 'near', 'far', 'double-talk', 'motion', 'near-motion', 'far-motion', 'double-talk-motion')
DECISION = 'DEVICE_CAPTURE_DIAGNOSTIC_NO_PROMOTION'


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and '\\' not in relative, 'invalid relative path')
    parts = PurePosixPath(relative).parts
    require(parts and not relative.startswith('/') and all(p not in ('.', '..') for p in relative.split('/')),
            'unsafe relative path')
    root = root.resolve()
    p = root
    for component in parts:
        p = p / component
        require(not p.is_symlink(), 'symlink evidence path')
    require(root in p.resolve().parents and p.is_file(), 'missing or escaped file')
    return p


def bounded(path: Path, limit: int) -> bytes:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, 'missing/oversized/symlink file')
    with path.open('rb') as f:
        data = f.read(limit + 1)
    require(len(data) <= limit, 'file grew beyond bound')
    return data


def strict_json(data: bytes) -> dict:
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def reject(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    value = json.loads(data, object_pairs_hook=pairs, parse_constant=reject)
    require(isinstance(value, dict), 'JSON object required')
    return value


def integer(value, lo: int, hi: int, name: str) -> int:
    require(type(value) is int and lo <= value <= hi, 'invalid integer: ' + name)
    return value


@dataclass
class PCM:
    data: bytes
    channels: int
    frames: int
    samples: array
    file_sha256: str


def wav(path: Path, channels: int | None = None) -> PCM:
    b = bounded(path, 8 * 1024 * 1024)
    require(len(b) >= 44 and b[:4] == b'RIFF' and b[8:12] == b'WAVE', 'invalid RIFF/WAVE')
    require(struct.unpack_from('<I', b, 4)[0] + 8 == len(b), 'RIFF size mismatch')
    pos, fmt, audio, chunks = 12, None, None, 0
    while pos < len(b):
        require(pos + 8 <= len(b) and chunks < 64, 'invalid WAV chunk header/count')
        tag, size = b[pos:pos + 4], struct.unpack_from('<I', b, pos + 4)[0]
        end = pos + 8 + size
        require(end + (size & 1) <= len(b), 'truncated WAV chunk')
        if tag == b'fmt ':
            require(fmt is None and size in (16, 18), 'duplicate/unsupported WAV fmt')
            fmt = struct.unpack_from('<HHIIHH', b, pos + 8)
            if size == 18:
                require(b[end - 2:end] == b'\x00\x00', 'unsupported WAV extension')
        elif tag == b'data':
            require(audio is None, 'duplicate WAV data')
            audio = b[pos + 8:end]
        pos = end + (size & 1); chunks += 1
    require(fmt is not None and audio is not None, 'missing WAV fmt/data')
    encoding, ch, rate, byte_rate, align, bits = fmt
    require(encoding == 1 and ch in (1, 2) and rate == 16000 and bits == 16 and
            align == ch * 2 and byte_rate == rate * align, 'invalid PCM16/16k geometry')
    require(channels is None or channels == ch, 'wrong channel count')
    require(len(audio) % align == 0 and 0 < len(audio) // align <= 1200000, 'partial/invalid WAV samples')
    samples = array('h'); samples.frombytes(audio)
    if sys.byteorder != 'little':
        samples.byteswap()
    return PCM(audio, ch, len(audio) // align, samples, sha(b))


def csv_rows(data: bytes, fields: tuple, numeric: tuple) -> list[dict]:
    reader = csv.DictReader(io.StringIO(data.decode('utf-8'), newline=''))
    require(reader.fieldnames == list(fields), 'invalid CSV header')
    rows = []
    for row in reader:
        require(len(rows) < 40000 and set(row) == set(fields) and all(v is not None for v in row.values()),
                'CSV shape/count')
        for k in numeric:
            require(re.fullmatch(r'-?[0-9]{1,20}', row[k]) is not None, 'invalid CSV integer')
            row[k] = int(row[k])
        rows.append(row)
    require(rows, 'empty CSV')
    return rows


def levels(pcm: PCM, start: int = 0, stop: int | None = None) -> list[dict]:
    stop = pcm.frames if stop is None else stop
    require(0 <= start < stop <= pcm.frames, 'level window out of range')
    result = []
    for channel in range(pcm.channels):
        samples = pcm.samples[start * pcm.channels + channel:stop * pcm.channels:pcm.channels]
        n = len(samples); energy = sum(v * v for v in samples)
        rms = math.sqrt(energy / n); peak = max(abs(v) for v in samples)
        result.append(dict(samples=n, rms_dbfs=None if not energy else 20 * math.log10(rms / 32768),
                           peak_dbfs=None if not peak else 20 * math.log10(peak / 32768),
                           dc_counts=sum(samples) / n, rail_samples=sum(v in (-32768, 32767) for v in samples)))
    return result


def capture(directory: Path) -> dict:
    require(not directory.is_symlink(), 'symlink capture root')
    files = {name: safe_file(directory, name) for name in ROLES}
    blobs = {k: bounded(p, 65536 if k == 'session.json' else 4 * 1024 * 1024 if k.endswith('.csv')
                       else 8 * 1024 * 1024) for k, p in files.items()}
    identity = {k: sha(v) for k, v in blobs.items()}
    s = strict_json(blobs['session.json'])
    require(type(s.get('schema_version')) is int and s['schema_version'] == 2 and s.get('complete') is True,
            'incomplete/unsupported session')
    for k in ('frame_validation', 'discontinuities', 'execution', 'cleanup', 'capture_error', 'deadline_misses'):
        integer(s.get(k), 0, 0, k)
    for k, expected in (('sample_rate', 16000), ('pcm_bits', 16), ('raw_ref_channels', 2)):
        integer(s.get(k), expected, expected, k)
    integer(s.get('seconds'), 20, 60, 'seconds')
    integer(s.get('active_profile'), 1, 2, 'active_profile')
    integer(s.get('requested_profile'), 1, 2, 'requested_profile')
    require(s['requested_profile'] == s['active_profile'] and s.get('scene') in SCENES, 'profile/scene mismatch')
    require(s.get('near_activity') == 'human-not-verified' and s.get('acoustic_verdict') == 'pending',
            'this intake admits only unqualified disclosed captures')
    integer(s.get('ref_delay_samples'), 0, 1600, 'ref_delay_samples')
    mic, raw, ref, output = (wav(files[name], ch) for name, ch in
                             (('mic.wav', 2), ('ref_raw.wav', 2), ('ref_used.wav', 1), ('output.wav', 1)))
    require(all(p.file_sha256 == identity[name] for p, name in
                ((mic, 'mic.wav'), (raw, 'ref_raw.wav'), (ref, 'ref_used.wav'), (output, 'output.wav'))),
            'WAV changed while loading')
    frames = csv_rows(blobs['frames.csv'], FRAME_FIELDS, FRAME_FIELDS)
    events = csv_rows(blobs['events.csv'], ('mono_us', 'event', 'value'), ('mono_us', 'value'))
    starts = [e['mono_us'] for e in events if e['event'] == 'scene_start']
    ends = [e['mono_us'] for e in events if e['event'] == 'scene_end']
    require(len(starts) == len(ends) == 1 and ends[0] - starts[0] >= s['seconds'] * 1000000 - 32000,
            'scene bounds/duration')
    require(all(e['mono_us'] >= 0 for e in events), 'negative event timestamp')
    require(all(r['stage'] in (0, 1) and r['epoch'] >= 0 and r['mono_us'] >= 0 and r['input_pts_us'] >= 0
                and r['output_valid'] in (0, 1) for r in frames), 'frame domain')
    require(len({r['epoch'] for r in frames}) == 1, 'epoch discontinuity')
    stage = [[r for r in frames if r['stage'] == i] for i in (0, 1)]
    for i, rows in enumerate(stage):
        hop = (128, 256)[i]
        require(rows and all(r['samples'] == hop and r['seq'] == j + 1 and r['file_sample_offset'] == j * hop
                            for j, r in enumerate(rows)), 'sequence/sample-offset gap')
        require(all(abs(b['input_pts_us'] - a['input_pts_us'] - hop * 1000000 // 16000) <= 2000
                    for a, b in zip(rows, rows[1:])), 'PTS gap')
    integer(s.get('frame_count'), len(frames), len(frames), 'frame_count')
    integer(s.get('input_samples'), mic.frames, mic.frames, 'input_samples')
    integer(s.get('output_samples'), output.frames, output.frames, 'output_samples')
    require(mic.frames == raw.frames == len(stage[0]) * 128 and
            ref.frames == output.frames == len(stage[1]) * 256 and mic.frames - ref.frames in (0, 128),
            'input/output counts or unpaired tail')
    require(all(r['input_pts_us'] == stage[0][2 * j]['input_pts_us'] for j, r in enumerate(stage[1])),
            'input/output PTS mismatch')
    require(all(r['output_valid'] == 1 for r in stage[1] if starts[0] <= r['input_pts_us'] < ends[0] - 32000),
            'invalid formal-scene output')
    require(stage[1][0]['input_pts_us'] <= starts[0] + 32000 and
            stage[1][-1]['input_pts_us'] + 16000 >= ends[0] - 32000, 'scene coverage')
    delay = s['ref_delay_samples']
    require(all(value == (0 if j < delay else raw.samples[(j - delay) * 2])
                for j, value in enumerate(ref.samples)), 'used reference mismatch')
    require(all(sha(bounded(files[k], 8 * 1024 * 1024)) == v for k, v in identity.items()), 'input mutation')
    return dict(session=s, mic=mic, raw=raw, ref=ref, output=output, stage=stage[1], events=events,
                scene_start=starts[0], scene_end=ends[0], input_sha256=identity)


def arm_set(scene: str) -> list[str]:
    require(scene in SCENES, 'unknown scene')
    arms = ['default', 'bf-isolated']
    if scene in ('far', 'far-motion'):
        arms += ['sync-default-control', 'tracked1', 'fixed1', 'tracked1-no-drift']
    elif scene in ('double-talk', 'double-talk-motion'):
        arms += ['tracked1', 'fixed1', 'tracked1-no-drift']
    if scene == 'quiet':
        arms += ['fixed1']
    if scene in ('quiet', 'motion'):
        arms += ['agc-isolated', 'ns-isolated']
    return arms


def plan(path: Path = PLAN) -> tuple[dict, dict]:
    p = strict_json(bounded(path, 65536))
    require(p.get('schema_version') == 1 and type(p['schema_version']) is int and
            p.get('experiment') == 'FE-DEVICE-CAPTURE-INTEGRATION-D3' and p.get('decision') == DECISION and
            p.get('data_role') == 'development' and p.get('promotion_allowed') is False and
            p.get('training_allowed') is False, 'research authority drift')
    for k, v in (('sample_rate', 16000), ('microphone_channels', 2), ('raw_reference_channels', 2),
                 ('capture_hop', 128), ('algorithm_hop', 256), ('replay_hop', 160),
                 ('reference_delay_diagnostic_ms', 1), ('fixed_execution_count', 70)):
        integer(p.get(k), v, v, k)
    require(p.get('source_base') == '572b0e34a8a8e5663397ce16e378209ba9058d4d' and
            p.get('reference') == 'ref_raw.channel0' and
            p.get('tail_policy') == 'paired-prefix-then-full-160-frames-no-padding' and
            p.get('primary_windows_seconds') == [[4, 6], [10, 12], [19, 21]] and
            p.get('window_authority') == 'schedule-diagnostic-not-speech-labels', 'measurement contract drift')
    require(p.get('input_lock') == 'device-capture-d0-input-lock.json' and
            p.get('input_lock_sha256') == 'c63b37feff15d7eac6932c92c1ddaa99a1a6efa5d338feb0c2ec2d28443fa285',
            'input authority drift')
    lock_bytes = bounded(safe_file(path.parent, p['input_lock']), 65536)
    require(sha(lock_bytes) == p['input_lock_sha256'], 'input lock drift')
    lock = strict_json(lock_bytes)
    require(len(lock) == 119 and all(isinstance(k, str) and k.startswith('tests/audio/') and
                                   re.fullmatch('[0-9a-f]{64}', v or '') for k, v in lock.items()), 'invalid input lock')
    expected = sorted(k[len('tests/audio/'):-len('/session.json')] for k in lock if k.endswith('/session.json'))
    require(isinstance(p.get('cases'), list) and p['cases'] == expected and len(set(expected)) == 16,
            'exact case set required')
    return p, lock


def intake(root: Path, plan_path: Path = PLAN) -> tuple[dict, list[dict]]:
    require(not root.is_symlink() and root.is_dir(), 'invalid capture root')
    p, lock = plan(plan_path)
    names = {str(f.relative_to(root)) for f in root.rglob('*') if f.is_file() or f.is_symlink()}
    expected = {k[len('tests/audio/'):] for k in lock}
    require(names == expected, 'extra/missing input files')
    for k, digest in lock.items():
        require(sha(bounded(safe_file(root, k[len('tests/audio/'):]), 8 * 1024 * 1024)) == digest, 'input lock mismatch: ' + k)
    captures = [dict(case_id=case, **capture(root / case)) for case in p['cases']]
    require(sum(len(arm_set(c['session']['scene'])) for c in captures) == 70, 'execution set drift')
    return p, captures


def summary(c: dict) -> dict:
    n = c['ref'].frames; full = n // 160 * 160
    motors = {}
    for side in ('left', 'right'):
        values = [r['value'] for r in c['events'] if r['event'] == f'motor_{side}_native_rpm']
        motors[side] = None if not values else dict(count=len(values), min=min(values), max=max(values),
                                                  nonzero=sum(v != 0 for v in values))
    return dict(case_id=c['case_id'], scene=c['session']['scene'], active_profile=c['session']['active_profile'],
                input_sha256=c['input_sha256'], paired_samples=n, replay_samples=full,
                unpaired_raw_tail=c['mic'].frames - n, replay_tail=n - full, render='ref_raw.channel0',
                ref_delay_samples=c['session']['ref_delay_samples'], arms=arm_set(c['session']['scene']),
                motor_feedback=motors, near_activity=c['session']['near_activity'], acoustic_verdict='pending')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, default=PLAN)
    parser.add_argument('--dry-run', action='store_true', help='validate/hash all inputs without writing or processing')
    args = parser.parse_args(argv)
    try:
        p, captures = intake(args.root, args.plan)
        print(json.dumps(dict(status='INPUT_CONTRACT_PASS', decision=p['decision'], writes=False,
                              data_role=p['data_role'], cases=[summary(c) for c in captures]),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, csv.Error, struct.error) as exc:
        print('device_capture: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
