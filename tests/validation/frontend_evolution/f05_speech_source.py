#!/usr/bin/env python3
"""F05 fixed source preparation. No scoring, listening, tuning or data-role promotion."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import tarfile
import time
import urllib.request

from contracts import ROOT, hex_digest, load_json, require, sha256
from speech_source import flac_info, NOTICES, PATTERN

PLAN = ROOT / '.github/research/frontend-evolution-v1/f05-speech-source-v1.json'
STATUS = 'SOURCE_PREPARED_RESERVED_VALIDATION_NOT_BLIND'
ARCHIVE = {
    'url': 'https://www.openslr.org/resources/12/dev-clean.tar.gz',
    'bytes': 337926286,
    'sha256': '76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3',
    'official_md5': '42e2234ba48799c1f50f24a7926300a1',
}
EXCLUDED = [84, 174, 251, 422, 652, 777, 1272, 1462, 1673, 1919, 1988, 1993, 2035, 2078, 2086, 2277]
SELECTED = [2412, 2428, 2803, 2902, 3000, 3081, 3170, 3536]
# speech_source imports libfvad_reference; these existing transitive imports are
# byte-bound as well. No evaluator, VAD or processor function is called here.
CONTROLS = (
    '.github/research/frontend-evolution-v1/f05-speech-source-v1.json',
    'tests/validation/frontend_evolution/f05_speech_source.py',
    'tests/validation/frontend_evolution/speech_source.py',
    'tests/validation/frontend_evolution/libfvad_reference.py',
    'tests/validation/frontend_evolution/contracts.py',
    'validation/tools/run_validation.py',
    'validation/tools/run_validation_engine.py',
    'validation/tools/authority.py',
    'validation/tools/render_corr_exact.py',
    'validation/tools/stage_profile_support.py',
)
ATTRIBUTION = (
    'LibriSpeech (c) 2014 Vassil Panayotov. Corpus authors: Vassil Panayotov, '
    'Daniel Povey, Guoguo Chen and Sanjeev Khudanpur; recordings derived from LibriVox.\n'
    'Source: https://www.openslr.org/12/\n'
    'CC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n'
    'Original LICENSE.TXT, README.TXT and SPEAKERS.TXT are retained. No endorsement.\n'
    'Changes: lossless native FLAC-to-S16LE decoding; predefined first-4-second '
    'excerpts from numeric-order utterance concatenations. Each source span is recorded.\n'
    'A concatenation may cross original utterance boundaries; it is not one continuous '
    'recording, a real array recording, or sufficient validation coverage.\n'
    'All originals, full PCM and excerpts: reserved validation, visible-scope separated, '
    'NOT_BLIND; no training, optimizer selection, promotion or acoustic execution '
    'authorized by this source-only contract.\n'
)


def save_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def safe_local(path: Path) -> Path:
    require('..' not in path.parts, 'parent path components forbidden')
    path = path.absolute()
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'symlink path forbidden')
    return path


def validate_plan(plan: dict) -> None:
    require(type(plan.get('schema_version')) is int and plan['schema_version'] == 1 and
            plan.get('study_id') == 'F05-SPEECH-SOURCE-V1', 'wrong F05 contract')
    require(plan['archive'] == ARCHIVE and type(plan['archive']['bytes']) is int, 'unregistered source archive')
    require(plan['exposure_review']['excluded_speakers'] == EXCLUDED and
            all(type(v) is int for v in plan['exposure_review']['excluded_speakers']), 'exposure exclusions changed')
    selection = plan['selection']
    require(selection['expected_speakers'] == SELECTED and selection['utterances_per_speaker'] == 4, 'selection drift')
    require(selection['roster'] == sorted(set(selection['roster'])) and len(selection['roster']) == 40 and
            all(type(v) is int for v in selection['roster'] + selection['expected_speakers']), 'invalid roster')
    require(sorted(set(selection['roster']) - set(EXCLUDED))[:8] == SELECTED, 'selection is not exclusion then numeric order')
    require((selection['sample_rate_hz'], selection['channels'], selection['sample_bits'], selection['window_frames']) ==
            (16000, 1, 16, 64000) and selection['quality_selection'] is False, 'format/window/selection drift')
    role = plan['role']
    require(role['name'] == 'reserved-validation-visible-scope-separated' and role['blind_status'] == 'NOT_BLIND', 'role drift')
    for field in ('universal_independence_established', 'training_allowed', 'optimizer_selection_allowed',
                  'promotion_allowed', 'acoustic_execution_allowed_by_this_contract'):
        require(role[field] is False, 'source preparation cannot authorize ' + field)
    expected = dict(transport_attempts=1, download_wall_seconds=600, prepare_wall_seconds=300,
                    verify_wall_seconds=300, decode_wall_seconds_total=180, decode_wall_seconds_per_file=20,
                    archive_members=10000, expanded_bytes=1073741824, member_bytes=5000000,
                    notice_bytes=2000000, output_bytes=268435456, output_files=100,
                    native_seconds_per_file=60, decoded_files=32, native_audio_seconds_maximum=1920,
                    window_audio_seconds=32, acoustic_runs=0, listening_sessions=0, parameter_searches=0)
    require(plan['budgets'] == expected and all(type(v) is int for v in plan['budgets'].values()), 'budget drift')
    require(set(plan['notices_sha256']) == set(NOTICES) and
            all(hex_digest(v) for v in plan['notices_sha256'].values()), 'missing notice locks')
    require(set(plan['rights_review']) == {'code', 'dependencies', 'weights', 'data', 'redistribution'} and
            all(isinstance(v, str) and v.strip() for v in plan['rights_review'].values()), 'five rights reviews required')
    require(plan['success_status'] == STATUS and plan['shipping_authority'] is False, 'status/authority drift')


def read_plan(expected: str) -> dict:
    require(hex_digest(expected) and file_hash(PLAN) == expected, 'frozen plan SHA256 mismatch')
    plan = load_json(PLAN)
    validate_plan(plan)
    return plan


def code_identity(revision: str, *, require_head: bool = True) -> dict:
    require(hex_digest(revision, 40), 'exact execution commit required')
    def git(*args: str) -> bytes:
        return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True, timeout=15).stdout
    require(git('rev-parse', revision + '^{commit}').decode().strip() == revision, 'not an exact commit')
    if require_head:
        require(git('rev-parse', 'HEAD').decode().strip() == revision, 'execution HEAD differs from frozen revision')
    git('merge-base', '--is-ancestor', '4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba', revision)
    files = {}
    for name in CONTROLS:
        data = safe_local(ROOT / name).read_bytes()
        require(data == git('show', revision + ':' + name), 'execution control bytes differ from Git: ' + name)
        files[name] = sha256(data)
    return {'commit': revision, 'tree': git('rev-parse', revision + '^{tree}').decode().strip(), 'files_sha256': files}


@contextmanager
def wall_limit(seconds: int, label: str):
    """Hard Linux wall timer, including blocking transport, tar reads and cleanup."""
    require(type(seconds) is int and seconds > 0, 'invalid wall budget')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'nested wall timers forbidden')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_number, _frame):
        raise TimeoutError(label + ' wall budget exhausted')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def check_archive(archive: Path, spec: dict) -> dict:
    archive = safe_local(archive)
    require(archive.is_file() and archive.stat().st_size == spec['bytes'], 'archive byte count mismatch')
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            sha.update(block); md5.update(block)
    require(sha.hexdigest() == spec['sha256'] and md5.hexdigest() == spec['official_md5'], 'archive digest mismatch')
    return dict(spec)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('source redirect forbidden; no alternate endpoint')


def fetch_archive(archive: Path, spec: dict, opener=None) -> dict:
    """One exact-byte transport attempt; failed prefix is retained, never reused."""
    archive = safe_local(archive)
    require(not archive.exists() and archive.parent.is_dir(), 'archive download destination must be fresh')
    opener = opener or urllib.request.build_opener(NoRedirect())
    start = time.monotonic()
    with opener.open(spec['url'], timeout=30) as response, archive.open('xb') as stream:
        require(response.status == 200 and response.geturl() == spec['url'], 'unexpected source status/URL')
        length = response.headers.get('Content-Length')
        require(length is None or int(length) == spec['bytes'], 'unexpected content length')
        count = 0
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            count += len(block)
            require(count <= spec['bytes'], 'download byte bound exceeded')
            stream.write(block)
    verified = check_archive(archive, spec)
    return {'mode': 'downloaded', 'attempts': 1, 'wall_seconds': time.monotonic() - start, 'archive': verified}


def safe_member(member: tarfile.TarInfo, budget: dict) -> None:
    name, path = member.name, PurePosixPath(member.name)
    require(bool(name) and bool(path.parts) and not path.is_absolute() and '..' not in path.parts and '\\' not in name and
            '\0' not in name and path.as_posix() == name.rstrip('/') and path.parts[0] == 'LibriSpeech', 'unsafe archive path')
    require(member.isdir() or member.isreg(), 'links/special archive members forbidden')
    require(type(member.size) is int and 0 <= member.size <= budget['member_bytes'], 'archive member byte bound')
    require(not member.isdir() or member.size == 0, 'directory with payload')


def select_members(names: list[str], plan: dict) -> list[tuple[int, list[str]]]:
    require(len(names) == len(set(names)), 'duplicate archive paths')
    speakers = {}
    identities = set()
    for name in names:
        match = PATTERN.fullmatch(name)
        require(not name.endswith('.flac') or match is not None, 'unrecognized FLAC identity')
        if match is None:
            continue
        sp, chapter, sp2, chapter2, utterance = map(int, match.groups())
        canonical = f'LibriSpeech/dev-clean/{sp}/{chapter}/{sp}-{chapter}-{utterance:04d}.flac'
        require((sp, chapter) == (sp2, chapter2) and name == canonical, 'member identity mismatch/alias')
        identity = (sp, chapter, utterance)
        require(identity not in identities, 'duplicate numeric utterance identity')
        identities.add(identity)
        speakers.setdefault(sp, []).append((chapter, utterance, name))
    require(sorted(speakers) == plan['selection']['roster'], 'archive speaker roster mismatch')
    selected = sorted(set(speakers) - set(plan['exposure_review']['excluded_speakers']))[:8]
    require(selected == plan['selection']['expected_speakers'], 'selected speaker set mismatch')
    result = []
    for speaker in selected:
        rows = sorted(speakers[speaker])
        require(len(rows) >= 4, 'fewer than four source utterances; no replacement')
        result.append((speaker, [row[2] for row in rows[:4]]))
    return result


def native_metadata(data: bytes) -> dict:
    rate, channels, bits, frames = flac_info(data)  # Unchanged old safe native reader.
    digest = data[26:42].hex()
    require(digest != '0' * 32, 'FLAC has no native PCM MD5; no fallback')
    return {'rate': rate, 'channels': channels, 'bits': bits, 'frames': frames, 'native_pcm_md5': digest}


def archive_snapshot(archive: Path, plan: dict, output: Path | None = None) -> dict:
    """Read fixed metadata and selected original bytes; never tar.extract/all."""
    budget = plan['budgets']
    with tarfile.open(archive, 'r:gz') as tf:
        by_name, members, expanded = {}, [], 0
        for member in tf:
            safe_member(member, budget)
            require(member.name not in by_name, 'duplicate archive paths')
            by_name[member.name] = member
            expanded += member.size
            require(len(by_name) <= budget['archive_members'] and expanded <= budget['expanded_bytes'], 'archive expansion bound')
            members.append({'path': member.name, 'kind': 'file' if member.isreg() else 'directory', 'bytes': member.size})
        chosen = select_members(list(by_name), plan)
        def read_member(name: str, limit: int) -> bytes:
            member = by_name.get(name)
            require(member is not None and member.isreg() and 0 < member.size <= limit, 'missing/invalid member: ' + name)
            stream = tf.extractfile(member)
            require(stream is not None, 'missing member stream')
            with stream:
                data = stream.read(limit + 1)
            require(len(data) == member.size, 'short or oversized member')
            return data
        for name, expected in plan['notices_sha256'].items():
            data = read_member(name, budget['notice_bytes'])
            require(sha256(data) == expected, 'original notice digest mismatch: ' + name)
            if name.endswith('/SPEAKERS.TXT'):
                roster = []
                for line in data.decode('utf-8').splitlines():
                    fields = [part.strip() for part in line.split('|')]
                    if len(fields) >= 3 and fields[0].isdigit() and fields[2] == 'dev-clean':
                        roster.append(int(fields[0]))
                require(sorted(roster) == plan['selection']['roster'], 'official notice roster mismatch')
            if output is not None:
                (output / Path(name).name).write_bytes(data)
        selected = []
        for speaker, names in chosen:
            originals = []
            for name in names:
                data = read_member(name, budget['member_bytes'])
                metadata = native_metadata(data)
                path = 'flac/' + Path(name).name
                if output is not None:
                    (output / path).parent.mkdir(exist_ok=True)
                    (output / path).write_bytes(data)
                originals.append({'member': name, 'file': path, 'bytes': len(data), 'sha256': sha256(data), **metadata})
            selected.append({'speaker': speaker, 'originals': originals})
    return {'schema_version': 1, 'study_id': plan['study_id'], 'archive': plan['archive'],
            'members': members, 'expanded_bytes': expanded, 'selection': selected,
            'selection_inputs': plan['selection']['selection_inputs'], 'quality_selection': False}


def window_bytes(originals: list[dict], pcm_by_member: dict[str, bytes], frames: int) -> tuple[bytes, list[dict]]:
    remaining, offset, chunks, spans = frames, 0, [], []
    for original in originals:
        pcm = pcm_by_member[original['member']]
        require(len(pcm) == original['frames'] * 2, 'complete PCM frame count mismatch')
        require(hashlib.md5(pcm).hexdigest() == original['native_pcm_md5'], 'native FLAC PCM MD5 mismatch')
        take = min(remaining, original['frames'])
        if take:
            chunks.append(pcm[:take * 2])
            spans.append({'member': original['member'], 'source_frames': [0, take],
                          'window_frames': [offset, offset + take], 'range_convention': 'zero-based-half-open'})
            offset += take
            remaining -= take
    require(remaining == 0, 'selected utterances shorter than window; no padding/reselection')
    return b''.join(chunks), spans


def source_rows(directory: Path, metadata: dict, plan: dict, *, create_windows: bool) -> list[dict]:
    rows = []
    for selected in metadata['selection']:
        originals, pcm_by_member = [], {}
        for original in selected['originals']:
            flac = safe_local(directory / original['file']).read_bytes()
            require(sha256(flac) == original['sha256'] and native_metadata(flac) ==
                    {key: original[key] for key in ('rate', 'channels', 'bits', 'frames', 'native_pcm_md5')}, 'original FLAC drift')
            pcm_file = 'pcm/' + Path(original['member']).stem + '.s16'
            pcm = safe_local(directory / pcm_file).read_bytes()
            pcm_by_member[original['member']] = pcm
            originals.append({**original, 'pcm_file': pcm_file, 'pcm_sha256': sha256(pcm), 'pcm_bytes': len(pcm)})
        window, spans = window_bytes(originals, pcm_by_member, plan['selection']['window_frames'])
        name = f"windows/speaker-{selected['speaker']}.s16"
        if create_windows:
            (directory / name).parent.mkdir(exist_ok=True)
            (directory / name).write_bytes(window)
        require(safe_local(directory / name).read_bytes() == window, 'window is not exact declared source prefix')
        rows.append({'speaker': selected['speaker'], 'role': plan['role'], 'originals': originals,
                     'window_file': name, 'window_frames': len(window) // 2, 'window_sha256': sha256(window),
                     'window_source_spans': spans, 'crosses_original_utterances': len(spans) > 1,
                     'window_is_validation_coverage_claim': False})
    return rows


def manifest(directory: Path, budget: dict) -> dict:
    files, total = {}, 0
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'symlink in prepared source')
        if path.is_dir():
            continue
        require(path.is_file(), 'special file in prepared source')
        if path.relative_to(directory).as_posix() == 'source-receipt.json':
            continue
        total += path.stat().st_size
        require(total <= budget['output_bytes'] and len(files) < budget['output_files'], 'prepared output bound')
        files[path.relative_to(directory).as_posix()] = file_hash(path)
    return files


def expected_paths(metadata: dict) -> set[str]:
    names = {'contract.json', 'selection.json', 'ATTRIBUTION.txt', 'decoder-version.txt', 'decoder-license.txt', 'transport.json'}
    names.update(Path(name).name for name in NOTICES)
    for selected in metadata['selection']:
        names.add(f"windows/speaker-{selected['speaker']}.s16")
        for original in selected['originals']:
            names.update((original['file'], 'pcm/' + Path(original['member']).stem + '.s16'))
    return names


def validate_assets(directory: Path, metadata: dict, plan: dict, receipt: dict) -> None:
    require(receipt['status'] == STATUS and receipt['role'] == plan['role'], 'source status/role mismatch')
    require(receipt['study_id'] == plan['study_id'] and receipt['archive'] == plan['archive'], 'source identity mismatch')
    require(file_hash(directory / 'contract.json') == receipt['plan_sha256'] == file_hash(PLAN), 'contract bytes mismatch')
    require(load_json(directory / 'selection.json') == metadata, 'saved metadata selection drift')
    require((directory / 'ATTRIBUTION.txt').read_text(encoding='utf-8') == ATTRIBUTION, 'attribution drift')
    for name, digest in plan['notices_sha256'].items():
        require(file_hash(directory / Path(name).name) == digest, 'original notice drift')
    transport = load_json(directory / 'transport.json')
    require((transport['mode'], transport['attempts']) in (('provided', 0), ('downloaded', 1)) and
            transport['archive'] == plan['archive'] and type(transport['wall_seconds']) in (int, float) and
            math.isfinite(transport['wall_seconds']) and
            0 <= transport['wall_seconds'] <= plan['budgets']['download_wall_seconds'], 'invalid transport receipt')
    rows = source_rows(directory, metadata, plan, create_windows=False)
    require(rows == receipt['sources'], 'source PCM/span receipt mismatch')
    files = manifest(directory, plan['budgets'])
    require(set(files) == expected_paths(metadata) and files == receipt['files_sha256'], 'prepared file closure mismatch')
    require(all(type(receipt[key]) is int and receipt[key] == 0
                for key in ('acoustic_runs', 'listening_sessions', 'parameter_searches')) and
            receipt['shipping_authority'] is False, 'unexpected research execution')
    for key, bound in (('prepare_wall_seconds', 300), ('decode_wall_seconds', 180)):
        value = receipt[key]
        require(type(value) in (int, float) and math.isfinite(value) and 0 < value <= bound, 'invalid elapsed budget')
    require(receipt['decoded_files'] == 32 and receipt['full_pcm_is_main_asset'] is True, 'incomplete main source assets')
    decoder = receipt['decoder']
    require(Path(decoder['executable']).is_absolute() and hex_digest(decoder['sha256']) and
            decoder['decode_wall_seconds'] == receipt['decode_wall_seconds'], 'invalid decoder identity/budget')
    original_directory = Path(receipt['preparation_directory'])
    require(original_directory.is_absolute(), 'missing actual preparation directory')
    commands = [decode_command(decoder['executable'], original_directory / original['file'])
                for selected in metadata['selection'] for original in selected['originals']]
    require(decoder['commands'] == commands, 'decoder command is not fixed native lossless decode')
    timings = decoder['file_wall_seconds']
    require([row['member'] for row in timings] ==
            [original['member'] for selected in metadata['selection'] for original in selected['originals']],
            'missing/misordered decoder timings')
    require(all(type(row['seconds']) in (int, float) and math.isfinite(row['seconds']) and
                0 < row['seconds'] <= plan['budgets']['decode_wall_seconds_per_file'] for row in timings),
            'per-file decode wall budget exceeded')
    require(math.fsum(row['seconds'] for row in timings) == decoder['decode_wall_seconds'], 'decode timing sum mismatch')


def decode_command(executable: str, flac: Path) -> list[str]:
    return [executable, '-nostdin', '-v', 'error', '-threads', '1', '-i', str(flac),
            '-map', '0:a:0', '-threads', '1', '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:1']


def decode_sources(directory: Path, metadata: dict, plan: dict, decoder: str) -> dict:
    executable = shutil.which(decoder)
    require(executable is not None, 'installed FFmpeg decoder missing; no installation/fallback')
    executable = str(Path(executable).resolve())
    digest = file_hash(Path(executable))
    for flag, name in (('-version', 'decoder-version.txt'), ('-L', 'decoder-license.txt')):
        run = subprocess.run([executable, flag], check=True, capture_output=True, timeout=10)
        data = run.stdout + run.stderr
        require(0 < len(data) <= 65536, 'invalid decoder identity/license output')
        require(flag != '-version' or run.stdout.startswith(b'ffmpeg version '), 'decoder is not identified as FFmpeg')
        (directory / name).write_bytes(data)
    commands, timings, elapsed = [], [], 0.0
    for selected in metadata['selection']:
        for original in selected['originals']:
            require(elapsed < plan['budgets']['decode_wall_seconds_total'], 'total decode budget exhausted')
            command = decode_command(executable, directory / original['file'])
            before = time.monotonic()
            run = subprocess.run(command, check=True, capture_output=True,
                                 timeout=min(plan['budgets']['decode_wall_seconds_per_file'],
                                             plan['budgets']['decode_wall_seconds_total'] - elapsed))
            spent = time.monotonic() - before
            require(spent <= plan['budgets']['decode_wall_seconds_per_file'], 'per-file decode budget exceeded')
            timings.append({'member': original['member'], 'seconds': spent})
            elapsed = math.fsum(row['seconds'] for row in timings)
            require(elapsed <= plan['budgets']['decode_wall_seconds_total'], 'total decode budget exceeded')
            require(len(run.stdout) == original['frames'] * 2 and
                    hashlib.md5(run.stdout).hexdigest() == original['native_pcm_md5'],
                    'lossless decode mismatch: ' + original['member'] + '; actual_bytes=' + str(len(run.stdout)) +
                    '; actual_pcm_sha256=' + sha256(run.stdout) + '; actual_pcm_md5=' + hashlib.md5(run.stdout).hexdigest())
            path = directory / 'pcm' / (Path(original['member']).stem + '.s16')
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(run.stdout)
            commands.append(command)
    require(file_hash(Path(executable)) == digest, 'decoder executable changed during preparation')
    return {'executable': executable, 'sha256': digest, 'commands': commands,
            'file_wall_seconds': timings, 'decode_wall_seconds': elapsed}


def prepare(archive: Path, output: Path, plan: dict, controls: dict, decoder: str, start: float) -> dict:
    check_archive(archive, plan['archive'])
    metadata = archive_snapshot(archive, plan, output)
    save_json(output / 'selection.json', metadata)  # Freeze metadata BEFORE decoder.
    decoder_record = decode_sources(output, metadata, plan, decoder)
    rows = source_rows(output, metadata, plan, create_windows=True)
    (output / 'ATTRIBUTION.txt').write_text(ATTRIBUTION, encoding='utf-8')
    require(check_archive(archive, plan['archive']) == metadata['archive'], 'archive changed during preparation')
    require(archive_snapshot(archive, plan) == metadata, 'original source metadata changed')
    require(code_identity(controls['commit']) == controls, 'execution controls changed')
    receipt = {'schema_version': 1, 'study_id': plan['study_id'], 'status': STATUS, 'archive': plan['archive'],
               'plan_sha256': file_hash(PLAN), 'controls': controls, 'role': plan['role'],
               'exposure_review': plan['exposure_review'], 'rights_review': plan['rights_review'],
               'sources': rows, 'decoder': decoder_record, 'preparation_directory': str(output),
               'decoded_files': len(decoder_record['commands']),
               'decode_wall_seconds': decoder_record['decode_wall_seconds'], 'prepare_wall_seconds': time.monotonic() - start,
               'files_sha256': manifest(output, plan['budgets']), 'full_pcm_is_main_asset': True,
               'acoustic_runs': 0, 'listening_sessions': 0, 'parameter_searches': 0, 'shipping_authority': False}
    validate_assets(output, metadata, plan, receipt)
    require(code_identity(controls['commit']) == controls, 'late execution controls changed')
    receipt['prepare_wall_seconds'] = time.monotonic() - start
    require(receipt['prepare_wall_seconds'] <= plan['budgets']['prepare_wall_seconds'], 'late preparation budget exceeded')
    save_json(output / 'source-receipt.json', receipt)
    return receipt


def verify(archive: Path, directory: Path, plan: dict, revision: str) -> dict:
    directory = safe_local(directory)
    receipt = load_json(directory / 'source-receipt.json')
    require(receipt['schema_version'] == 1 and receipt['controls']['commit'] == revision, 'receipt revision/schema mismatch')
    require(code_identity(revision, require_head=False) == receipt['controls'], 'source controls mismatch')
    require(receipt['exposure_review'] == plan['exposure_review'] and receipt['rights_review'] == plan['rights_review'], 'review scope drift')
    check_archive(archive, plan['archive'])
    metadata = archive_snapshot(archive, plan)
    validate_assets(directory, metadata, plan, receipt)
    return {'schema_version': 1, 'status': 'VERIFIED_SOURCE_ONLY_NOT_ACOUSTIC_EVIDENCE', 'study_id': plan['study_id'],
            'code_revision': revision, 'source_receipt_sha256': file_hash(directory / 'source-receipt.json'),
            'speakers': [row['speaker'] for row in receipt['sources']], 'original_files': 32, 'decoder_invocations': 0,
            'role': plan['role'], 'acoustic_runs': 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('acquire', 'prepare', 'verify'))
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Fresh directory; existing source directory for verify')
    parser.add_argument('--code-revision', required=True, help='Reviewed, publicly frozen exact source commit')
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--decoder', default='ffmpeg', help='Already installed FFmpeg; no package installation')
    args = parser.parse_args()
    owned, output = False, args.output
    try:
        plan = read_plan(args.plan_sha256)
        archive, output = safe_local(args.archive), safe_local(args.output)
        require(output != archive and output not in archive.parents and archive not in output.parents, 'archive/output overlap')
        if args.command == 'verify':
            with wall_limit(plan['budgets']['verify_wall_seconds'], 'verify'):
                result = verify(archive, output, plan, args.code_revision)
        else:
            controls = code_identity(args.code_revision)
            require(not output.exists() and ROOT not in output.parents, 'prepared output must be fresh and outside checkout')
            if args.command == 'acquire':
                require(not archive.exists(), 'acquire archive must be fresh')
            output.mkdir(parents=True)
            owned = True
            (output / 'contract.json').write_bytes(PLAN.read_bytes())
            if args.command == 'acquire':
                with wall_limit(plan['budgets']['download_wall_seconds'], 'download'):
                    transport = fetch_archive(archive, plan['archive'])
            else:
                transport = {'mode': 'provided', 'attempts': 0, 'wall_seconds': 0, 'archive': plan['archive']}
            save_json(output / 'transport.json', transport)
            start = time.monotonic()
            with wall_limit(plan['budgets']['prepare_wall_seconds'], 'prepare'):
                result = prepare(archive, output, plan, controls, args.decoder, start)
        print(json.dumps({key: result[key] for key in ('status', 'study_id')}, sort_keys=True))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        if owned:
            (output / 'source-receipt.json').unlink(missing_ok=True)
            failure = {'schema_version': 1, 'status': 'FAIL_SOURCE_PREPARATION',
                       'reason': type(error).__name__ + ': ' + str(error), 'code_revision': args.code_revision,
                       'plan_sha256': args.plan_sha256, 'no_fallback': True, 'acoustic_runs': 0}
            if isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
                stderr, stdout = error.stderr or b'', error.stdout or b''
                failure['child_process'] = {'command': error.cmd, 'returncode': getattr(error, 'returncode', None),
                    'timeout': getattr(error, 'timeout', None), 'stdout_bytes': len(stdout), 'stdout_sha256': sha256(stdout),
                    'stderr_bytes': len(stderr), 'stderr_sha256': sha256(stderr),
                    'stderr_tail': stderr[-65536:].decode('utf-8', errors='replace'), 'stderr_tail_limit': 65536}
            save_json(output / 'source-failure.json', failure)
        print(json.dumps({'status': 'FAIL_SOURCE_PREPARATION', 'reason': type(error).__name__ + ': ' + str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
