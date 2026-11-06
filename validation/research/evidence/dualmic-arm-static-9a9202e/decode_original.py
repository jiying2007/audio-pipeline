#!/usr/bin/env python3
"""Verify stored transport and reconstruct the original 24-member snapshot."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath


def checked_path(root, name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name:
        raise ValueError('unsafe manifest path')
    return root / name


def check_bytes(data, record, name):
    if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('identity mismatch: ' + name)


def decode(data):
    if not data.endswith(b'\n') or data.count(b'\n') != 1:
        raise ValueError('base64 transport must be one line plus LF')
    return base64.b64decode(data[:-1], validate=True)


def verify(root):
    physical = json.loads((root / 'artifact-manifest.json').read_text())['files']
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
              and p != root / 'artifact-manifest.json' and '__pycache__' not in p.parts}
    if actual != set(physical):
        raise ValueError('physical member set mismatch')
    for name, record in physical.items():
        check_bytes(checked_path(root, name).read_bytes(), record, name)
    receipt = json.loads((root / 'transport-receipt.json').read_text())
    archived = checked_path(root, receipt['original_manifest']['path']).read_bytes()
    check_bytes(archived, receipt['original_manifest'], 'original artifact manifest')
    logical = json.loads(archived)['files']
    if len(logical) != 24 or set(receipt['encoded_members']) != {
            'original/base-size.log', 'original/candidate-size.log'}:
        raise ValueError('unexpected original snapshot geometry')
    restored = {}
    for name, record in logical.items():
        if name in receipt['encoded_members']:
            data = decode(checked_path(root, receipt['encoded_members'][name]).read_bytes())
        else:
            data = checked_path(root, name).read_bytes()
        check_bytes(data, record, name)
        restored[name] = data
    failure = receipt['failed_verify']['decoded_log']
    check_bytes(decode(checked_path(root, failure['encoded_path']).read_bytes()), failure, 'original CI log text')
    return archived, restored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New directory for original decoded snapshot')
    args = parser.parse_args()
    archived, restored = verify(Path(__file__).resolve().parent)
    if args.output is not None:
        args.output.mkdir(parents=True, exist_ok=False)
        for name, data in restored.items():
            destination = checked_path(args.output, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (args.output / 'artifact-manifest.json').write_bytes(archived)
    print(json.dumps({'result': 'ORIGINAL_BYTES_VERIFIED', 'original_members': len(restored),
                      'original_manifest_preserved': True, 'reconstructed': args.output is not None}, sort_keys=True))


if __name__ == '__main__':
    main()
