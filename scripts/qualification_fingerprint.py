#!/usr/bin/env python3
"""Build a deterministic exact-bytes qualification fingerprint from policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

DEFAULT_POLICY = Path('.github/research/qualification-policy.json')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_policy(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('qualification policy schema_version must be 1')
    files = data.get('fingerprint_files')
    if not isinstance(files, list) or not files or any(not isinstance(item, str) or not item for item in files):
        raise ValueError('fingerprint_files must be a non-empty string list')
    if len(files) != len(set(files)):
        raise ValueError('fingerprint_files must be unique')
    return data


def resolve_files(root: Path, policy: dict) -> list[tuple[str, Path]]:
    resolved: list[tuple[str, Path]] = []
    for rel in policy['fingerprint_files']:
        candidate = Path(rel)
        if candidate.is_absolute() or '..' in candidate.parts:
            raise ValueError(f'unsafe fingerprint path: {rel}')
        full = root / candidate
        if not full.is_file():
            raise ValueError(f'fingerprint file missing: {rel}')
        resolved.append((candidate.as_posix(), full))
    return resolved


def build(root: Path, policy_path: Path) -> dict:
    policy = load_policy(policy_path)
    rows = []
    digest = hashlib.sha256()
    for rel, path in resolve_files(root, policy):
        file_sha = sha256_file(path)
        rows.append({'path': rel, 'sha256': file_sha})
        digest.update(rel.encode('utf-8'))
        digest.update(b'\0')
        digest.update(file_sha.encode('ascii'))
        digest.update(b'\n')
    return {
        'schema_version': 1,
        'mode': policy.get('mode'),
        'qualification': policy.get('qualification'),
        'fingerprint': digest.hexdigest(),
        'files': rows,
        'policy_sha256': sha256_file(policy_path),
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'a').write_text('alpha\n', encoding='utf-8')
        (root / 'b').write_text('beta\n', encoding='utf-8')
        policy = root / 'policy.json'
        policy.write_text(json.dumps({
            'schema_version': 1,
            'mode': 'one-way',
            'qualification': 'test',
            'fingerprint_files': ['a', 'b'],
        }), encoding='utf-8')
        first = build(root, policy)
        second = build(root, policy)
        assert first['fingerprint'] == second['fingerprint']
        (root / 'b').write_text('changed\n', encoding='utf-8')
        assert build(root, policy)['fingerprint'] != first['fingerprint']
        bad = root / 'bad.json'
        bad.write_text(json.dumps({'schema_version': 1, 'fingerprint_files': ['../x']}), encoding='utf-8')
        try:
            build(root, bad)
        except ValueError as exc:
            assert 'unsafe fingerprint path' in str(exc)
        else:
            raise AssertionError('unsafe path was accepted')
    print('qualification fingerprint self-test: OK')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--policy', type=Path, default=DEFAULT_POLICY)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    root = args.root.resolve()
    policy = args.policy if args.policy.is_absolute() else root / args.policy
    result = build(root, policy)
    rendered = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as handle:
            handle.write(f"fingerprint={result['fingerprint']}\n")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
