#!/usr/bin/env python3
"""Acquire immutable original A/C artifacts; no DSP, models or regenerated data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / 'docs/research/frontend-evolution-v1/dualmic-stages-d1-source-lock.json'
LOCK_SHA256 = '3f19ef5a04d18411fc0c3b7b62dcb42a30bd1a4645ee2a6afb26af4f9b54c3bf'


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


def remaining(start, budget):
    value = budget - (time.monotonic() - start)
    need(value > 0, 'SOURCE_BUDGET_EXCEEDED')
    return min(value, 30.0)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_get(url, token, start, budget):
    need(url.startswith('https://api.github.com/repos/jiying2007/audio-pipeline/'), 'API outside locked repository')
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'audio-pipeline-FE-DUALMIC-STAGES-D1',
    })
    return urllib.request.build_opener(NoRedirect()).open(req, timeout=remaining(start, budget))


def api_json(url, token, start, budget):
    with api_get(url, token, start, budget) as response:
        data = response.read(4 * 1024 * 1024 + 1)
    need(len(data) <= 4 * 1024 * 1024, 'API response bound')
    return json.loads(data)


def fetch_zip(artifact_id, path, limit, token, start, budget):
    url = f'https://api.github.com/repos/jiying2007/audio-pipeline/actions/artifacts/{artifact_id}/zip'
    try:
        response = api_get(url, token, start, budget)
    except urllib.error.HTTPError as error:
        need(error.code in (301, 302, 303, 307, 308), 'artifact API rejected: HTTP ' + str(error.code))
        location = error.headers.get('Location', '')
        error.close()
        parsed = urllib.parse.urlparse(location)
        host = parsed.hostname or ''
        need(parsed.scheme == 'https' and not parsed.username and not parsed.password and
             (host.endswith('.blob.core.windows.net') or host.endswith('.githubusercontent.com') or
              host.endswith('.actions.githubusercontent.com')), 'unexpected artifact redirect origin')
        # Never forward the GitHub token to artifact storage or another redirect.
        response = urllib.request.build_opener(NoRedirect()).open(
            urllib.request.Request(location, headers={'User-Agent': 'audio-pipeline-D1'}),
            timeout=remaining(start, budget))
    count = 0
    with response, path.open('xb') as stream:
        while True:
            remaining(start, budget)
            block = response.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            need(count <= limit, 'ZIP exceeds locked size')
            stream.write(block)
    need(count == limit, 'ZIP size differs from original')


def validate_extract(path, target, spec, lock, start, budget):
    need(not target.exists() and not target.is_symlink(), 'new extraction directory required')
    need(path.stat().st_size == spec['zip_bytes'] and digest(path) == spec['sha256'], 'original ZIP hash/size mismatch')
    total = 0
    members = set()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        need(len(infos) == spec['members'] and len(infos) <= lock['max_members'], 'original member count mismatch')
        for item in infos:
            relative = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            need(not relative.is_absolute() and bool(relative.parts) and
                 not any(part in ('..', '.') for part in relative.parts) and
                 '\\' not in item.filename and ':' not in item.filename and
                 item.filename not in members and not stat.S_ISLNK(mode) and
                 not (item.flag_bits & 1) and not item.is_dir(), 'unsafe/duplicate/non-file ZIP member')
            need(not mode or stat.S_IFMT(mode) in (0, stat.S_IFREG), 'special ZIP member')
            total += item.file_size
            need(total <= lock['max_uncompressed_bytes'], 'uncompressed byte bound')
            members.add(item.filename)
        target.mkdir()
        hashes = {}
        for item in infos:
            remaining(start, budget)
            destination = target.joinpath(*PurePosixPath(item.filename).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            count = 0
            with archive.open(item) as src, destination.open('xb') as dst:
                while True:
                    remaining(start, budget)
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    count += len(block)
                    need(count <= item.file_size, 'member exceeds declared size')
                    h.update(block)
                    dst.write(block)
            need(count == item.file_size, 'member truncated')
            hashes[item.filename] = h.hexdigest()
    return dict(members=len(members), uncompressed_bytes=total, member_hashes=hashes)


def acquire(output):
    started = time.monotonic()
    need(not output.exists() and not output.is_symlink(), 'new source output required')
    need(digest(LOCK) == LOCK_SHA256, 'frozen source lock changed')
    lock = json.loads(LOCK.read_text())
    budget = lock['source_budget_seconds']
    token = os.environ.get('GH_TOKEN')
    need(bool(token), 'GH_TOKEN required for original Actions artifact read')
    output.mkdir(parents=True)
    (output / 'source-lock.json').write_bytes(LOCK.read_bytes())
    receipt = dict(schema_version=1, experiment=lock['experiment'], status='FAIL',
                   run_id=lock['run_id'], run_attempt=lock['run_attempt'], base_sha=lock['base_sha'],
                   lock_sha256=LOCK_SHA256, budget_seconds=budget, artifacts=[])
    try:
        api = 'https://api.github.com/repos/' + lock['repository']
        run = api_json(api + f"/actions/runs/{lock['run_id']}", token, started, budget)
        need(run['head_sha'] == lock['base_sha'] and run['run_attempt'] == lock['run_attempt'] and
             run['status'] == 'completed' and run['conclusion'] == 'success', 'original run identity/result mismatch')
        listing = api_json(api + f"/actions/runs/{lock['run_id']}/artifacts?per_page=100", token, started, budget)
        need(listing['total_count'] <= 100, 'artifact listing requires a new bounded contract')
        for spec in lock['artifacts']:
            selected = [a for a in listing['artifacts'] if a['id'] == spec['artifact_id']]
            need(len(selected) == 1, 'original artifact absent')
            item = selected[0]
            need(item['name'] == spec['name'] and item['size_in_bytes'] == spec['zip_bytes'] and
                 item['digest'] == 'sha256:' + spec['sha256'] and not item['expired'] and
                 item['workflow_run']['head_sha'] == lock['base_sha'] and
                 item['workflow_run']['id'] == lock['run_id'], 'artifact metadata binding mismatch')
            path = output / (spec['key'] + '.zip')
            fetch_zip(spec['artifact_id'], path, spec['zip_bytes'], token, started, budget)
            verified = validate_extract(path, output / spec['key'], spec, lock, started, budget)
            receipt['artifacts'].append({**spec, **verified})
            receipt['elapsed_seconds'] = time.monotonic() - started
            dump(output / 'acquisition.json', receipt)
        remaining(started, budget)
        receipt['status'] = 'PASS'
        receipt['elapsed_seconds'] = time.monotonic() - started
        dump(output / 'acquisition.json', receipt)
        remaining(started, budget)
        print(json.dumps({k: receipt[k] for k in ('experiment', 'status', 'elapsed_seconds', 'run_id')}))
    except Exception as error:
        # URLs may include signed credentials: do not serialize exception strings.
        receipt['status'] = 'FAIL'
        receipt['failure_type'] = type(error).__name__
        receipt['failure_reason'] = str(error) if isinstance(error, ValueError) else 'source acquisition failed; no fallback'
        receipt['elapsed_seconds'] = time.monotonic() - started
        dump(output / 'acquisition.json', receipt)
        raise ValueError(receipt['failure_reason']) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        acquire(args.output.resolve())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print('D1 source: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
