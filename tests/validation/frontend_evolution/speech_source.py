#!/usr/bin/env python3
"""Bounded public-speech acquisition; not an acoustic score or data admission."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from contracts import ROOT, require, sha256
from libfvad_reference import write_json

PLAN = ROOT / '.github/research/frontend-evolution-v1/speech-spatial-v1.json'
URL = 'https://www.openslr.org/resources/12/dev-clean.tar.gz'
MD5 = '42e2234ba48799c1f50f24a7926300a1'
MAX_ARCHIVE = 400_000_000
PATTERN = re.compile(r'LibriSpeech/dev-clean/(\d+)/(\d+)/(\d+)-(\d+)-(\d+)\.flac')
NOTICES = ('LibriSpeech/LICENSE.TXT', 'LibriSpeech/README.TXT', 'LibriSpeech/SPEAKERS.TXT')


def flac_info(data: bytes) -> tuple[int, int, int, int]:
    require(len(data) >= 42 and data[:4] == b'fLaC', 'not native FLAC')
    require(data[4] & 127 == 0 and int.from_bytes(data[5:8], 'big') == 34, 'missing STREAMINFO')
    value = int.from_bytes(data[18:26], 'big')
    rate, channels, bits, frames = value >> 44, ((value >> 41) & 7) + 1, ((value >> 36) & 31) + 1, value & ((1 << 36) - 1)
    require((rate, channels, bits) == (16000, 1, 16) and 0 < frames <= 16000 * 60, 'unexpected audio format/duration')
    return rate, channels, bits, frames


def select_members(names: list[str]) -> list[tuple[int, list[str]]]:
    require(len(names) == len(set(names)), 'duplicate archive paths')
    speakers: dict[int, list[tuple[int, int, str]]] = {}
    for name in names:
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in name, 'unsafe archive path')
        match = PATTERN.fullmatch(name)
        if match:
            sp, chapter, sp2, chapter2, utterance = map(int, match.groups())
            require((sp, chapter) == (sp2, chapter2), 'member identity mismatch')
            speakers.setdefault(sp, []).append((chapter, utterance, name))
    selected = sorted(speakers)[:8]
    require(len(selected) == 8, 'need eight distinct speakers')
    result = []
    for sp in selected:
        rows = sorted(speakers[sp])
        require(len(rows) >= 4 and len({(c, u) for c, u, _ in rows}) == len(rows), 'missing/duplicate utterances')
        result.append((sp, [name for _, _, name in rows[:4]]))
    return result


def acquire(archive: Path, output: Path, decoder: str = 'ffmpeg') -> dict:
    require(not output.exists(), 'source output must be fresh')
    require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size <= MAX_ARCHIVE, 'invalid archive')
    md5, sha = hashlib.md5(), hashlib.sha256()
    with archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            md5.update(block); sha.update(block)
    require(md5.hexdigest() == MD5, 'official archive MD5 mismatch')
    executable = shutil.which(decoder)
    require(executable is not None, 'FFmpeg lossless decoder unavailable; no fallback')
    executable = str(Path(executable).resolve())
    version = subprocess.run([executable, '-version'], check=True, capture_output=True, timeout=10).stdout.decode()
    with tarfile.open(archive, 'r:gz') as tf:
        members = tf.getmembers()
        require(len(members) <= 10000, 'archive member bound')
        require(all(m.isdir() or m.isreg() for m in members), 'links/special members forbidden')
        chosen = select_members([m.name for m in members])
        by_name = {m.name: m for m in members}
        require(all(n in by_name for n in NOTICES), 'corpus notices absent')
        output.mkdir(parents=True)
        rows = []
        for name in NOTICES:
            require(by_name[name].isreg() and by_name[name].size <= 2_000_000, 'invalid notice')
            data = tf.extractfile(by_name[name]).read()
            (output / Path(name).name).write_bytes(data)
        for ordinal, (speaker, names) in enumerate(chosen):
            joined = bytearray(); original = []
            for name in names:
                m = by_name[name]
                require(m.isreg() and 0 < m.size <= 5_000_000, 'invalid FLAC member')
                data = tf.extractfile(m).read()
                rate, channels, bits, frames = flac_info(data)
                flac = output / 'flac' / Path(name).name
                flac.parent.mkdir(exist_ok=True); flac.write_bytes(data)
                pcm = subprocess.run([executable, '-nostdin', '-v', 'error', '-i', str(flac),
                       '-map', '0:a:0', '-f', 's16le', '-acodec', 'pcm_s16le', '-'],
                       check=True, capture_output=True, timeout=30).stdout
                require(len(pcm) == frames * 2, 'lossless PCM frame mismatch')
                joined.extend(pcm)
                original.append({'member': name, 'flac_sha256': sha256(data), 'frames': frames,
                                 'pcm_sha256': sha256(pcm)})
            require(len(joined) >= 128000, 'selected utterances shorter than 4 seconds; no reselection/padding')
            window = bytes(joined[:128000])
            path = output / f'speaker-{speaker}.s16'
            path.write_bytes(window)
            rows.append({'speaker': speaker, 'pair_index': ordinal // 2, 'position': 'target' if ordinal % 2 == 0 else 'interferer',
                         'role': 'development-diagnostic' if ordinal < 4 else 'speaker-disjoint-confirmation-diagnostic',
                         'originals': original, 'window_file': path.name, 'window_frames': 64000, 'window_sha256': sha256(window)})
    attribution = ('LibriSpeech, Vassil Panayotov, Daniel Povey, Guoguo Chen and Sanjeev Khudanpur; '
                   'recordings derived from LibriVox. Source: https://www.openslr.org/12/\n'
                   'CC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n'
                   'Original corpus LICENSE.TXT/README.TXT/SPEAKERS.TXT are retained. No endorsement.\n'
                   'Changes: lossless FLAC decode; numeric-order utterance concatenation; first 4s excerpts. '
                   'Later spatial mixtures are synthetic research derivatives, not original array recordings.\n')
    (output / 'ATTRIBUTION.txt').write_text(attribution)
    (output / 'decoder-version.txt').write_text(version)
    files = {p.relative_to(output).as_posix(): sha256(p.read_bytes()) for p in sorted(output.rglob('*')) if p.is_file()}
    record = {'schema_version': 1, 'source_id': 'librispeech-dev-clean-fe03', 'url': URL,
              'archive_md5': md5.hexdigest(), 'archive_sha256': sha.hexdigest(), 'archive_bytes': archive.stat().st_size,
              'plan_sha256': sha256(PLAN.read_bytes()), 'decoder_path': executable,
              'decoder_sha256': sha256(Path(executable).read_bytes()), 'speaker_selection': rows,
              'files_sha256': files, 'status': 'SOURCE_ONLY_NOT_ACOUSTIC_EVIDENCE', 'shipping_authority': False}
    write_json(output / 'source-receipt.json', record)
    return record


def download(archive: Path) -> None:
    require(not archive.exists(), 'download destination exists')
    try:
        with urllib.request.urlopen(URL, timeout=60) as response, archive.open('xb') as stream:
            require(response.status == 200 and response.url == URL, 'unexpected source redirect/status')
            count = 0
            while True:
                block = response.read(1 << 20)
                if not block: break
                count += len(block); require(count <= MAX_ARCHIVE, 'archive download bound')
                stream.write(block)
    except Exception:
        archive.unlink(missing_ok=True)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archive', type=Path)
    args = parser.parse_args()
    existed = args.output.exists()
    try:
        require(not existed, 'source output must be fresh')
        if args.archive:
            result = acquire(args.archive, args.output)
        else:
            with tempfile.TemporaryDirectory(prefix='fe-speech-source-') as tmp:
                path = Path(tmp) / 'dev-clean.tar.gz'; download(path); result = acquire(path, args.output)
        print(json.dumps({'status': result['status'], 'archive_sha256': result['archive_sha256'],
                          'speakers': [r['speaker'] for r in result['speaker_selection']]}))
    except Exception as error:
        if not existed:
            args.output.mkdir(parents=True, exist_ok=True)
            write_json(args.output / 'source-failure.json', {'status': 'DATA_OR_INFRASTRUCTURE_FAILURE',
                       'error': str(error), 'shipping_authority': False})
        raise
