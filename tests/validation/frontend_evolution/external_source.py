#!/usr/bin/env python3
"""Pinned, minimal external baseline source/model preflight; never executes it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

from contracts import ROOT, admit_execution, load_json, require, sha256, verified_file
from libfvad_reference import write_json

LOCK = ROOT / '.github/research/frontend-evolution-v1/external-baselines-source-lock.json'
ADMISSION = ROOT / '.github/research/frontend-evolution-v1/external-baselines-admission.json'
CATALOG = ROOT / '.github/research/frontend-evolution-v1/sources.json'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def identity(files: dict) -> str:
    return sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())


def fetch(root: Path) -> dict:
    require(not root.exists(), 'fresh source output required')
    lock = load_json(LOCK)
    root.mkdir(parents=True)
    receipts = {}
    for source_id, source in lock['sources'].items():
        files = {}
        for row in source['files']:
            name = row['path']
            url = 'https://raw.githubusercontent.com/{}/{}/{}'.format(
                source['repo'], source['commit'], name)
            with urllib.request.urlopen(url, timeout=45) as response:
                data = response.read(row['bytes'] + 1)
            require(len(data) == row['bytes'] and git_blob(data) == row['git_blob_sha1'],
                    'pinned upstream byte mismatch: ' + source_id + '/' + name)
            path = root / source_id / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files[name] = sha256(data)
        receipts[source_id] = {'source_commit': source['commit'], 'files_sha256': files,
                               'materialized_source_sha256': identity(files)}
    receipt = {'schema_version': 1, 'shipping_authority': False,
               'status': 'SOURCE_BYTES_VERIFIED_NOT_EXECUTED',
               'source_lock_sha256': sha256(LOCK.read_bytes()), 'sources': receipts}
    write_json(root / 'source-receipt.json', receipt)
    return verify(root)


def verify(root: Path) -> dict:
    lock = load_json(LOCK)
    receipt = load_json(verified_file(root, 'source-receipt.json'))
    require(receipt['status'] == 'SOURCE_BYTES_VERIFIED_NOT_EXECUTED'
            and receipt['shipping_authority'] is False, 'source authority drift')
    require(receipt['source_lock_sha256'] == sha256(LOCK.read_bytes()), 'source lock drift')
    expected = {'source-receipt.json'}
    require(set(receipt['sources']) == set(lock['sources']), 'partial source receipt')
    for source_id, source in lock['sources'].items():
        files = {}
        for row in source['files']:
            name = source_id + '/' + row['path']
            data = verified_file(root, name).read_bytes()
            require(len(data) == row['bytes'] and git_blob(data) == row['git_blob_sha1'],
                    'source/model byte drift: ' + name)
            files[row['path']] = sha256(data)
            expected.add(name)
        require(receipt['sources'][source_id] == {
            'source_commit': source['commit'], 'files_sha256': files,
            'materialized_source_sha256': identity(files)}, 'source identity drift')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual == expected and all(not p.is_symlink() for p in root.rglob('*')),
            'unexpected source files/symlinks')
    return receipt


def admitted(root: Path, source_id: str) -> dict:
    receipt = verify(root)
    review = load_json(ADMISSION)
    source = admit_execution(load_json(CATALOG), source_id)
    require(review['decision'] == 'ADMITTED_LOCAL_FIXED_RESEARCH_ONLY'
            and review['shipping_authority'] is False, 'execution scope drift')
    require(review['source_lock_sha256'] == receipt['source_lock_sha256']
            and review['sources'][source_id] == receipt['sources'][source_id], 'unreviewed materialization')
    require(source['admission_receipt_sha256'] == sha256(ADMISSION.read_bytes())
            and source['materialized_source_sha256'] == receipt['sources'][source_id]['materialized_source_sha256']
            and source['commit'] == receipt['sources'][source_id]['source_commit'], 'catalog admission drift')
    return receipt['sources'][source_id]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    print(json.dumps(fetch(args.output) if args.fetch else verify(args.output), sort_keys=True))


if __name__ == '__main__':
    main()
