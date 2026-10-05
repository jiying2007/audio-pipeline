#!/usr/bin/env python3
"""Pinned libfvad byte admission and reference execution, never a shipping gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from contracts import ROOT, load_json, require, sha256, verified_file

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight'])
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = source_preflight(args.source.resolve(), args.output.resolve())
        print(json.dumps({k: v for k, v in result.items() if k != 'files_sha256'}, sort_keys=True))
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(f'libfvad reference failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
