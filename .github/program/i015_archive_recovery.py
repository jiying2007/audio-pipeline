#!/usr/bin/env python3
"""Refresh only the exact I015 archive PR; delegate all closure gates unchanged."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def require(condition, message):
    if not condition:
        raise ValueError(message)


def refresh_archive(api, frozen, main, load_files):
    """Merge verified main into an exact data-only PR, never merge it to main."""
    branch = frozen['archive_branch']
    prs = api.collection(f'pulls?state=all&head={api.repo.split("/")[0]}:{branch}&base=main&per_page=100')
    require(len(prs) <= 1, 'ambiguous archive PR history')
    if not prs:
        return None
    pr = api.api(f"pulls/{prs[0]['number']}")
    if pr['state'] != 'open':
        return None  # The existing finalizer owns terminal-state validation.
    require(pr['base']['ref'] == 'main' and pr['base']['repo']['id'] == frozen['repository_id']
            and pr['head']['ref'] == branch and pr['head']['repo']['id'] == frozen['repository_id'],
            'archive recovery identity drift')
    require(pr['draft'] is False, 'archive recovery stopped for draft PR')
    sha = pr['head']['sha']
    comparison = api.api(f'compare/{main}...{sha}')
    if comparison['merge_base_commit']['sha'] == main:
        return None
    require(comparison['behind_by'] > 0 and comparison['ahead_by'] > 0,
            'archive recovery has unexpected ancestry')
    files = load_files()
    changed = api.collection(f"pulls/{pr['number']}/files?per_page=100")
    require(len(changed) == len(files) and {item['filename'] for item in changed} == set(files),
            'archive recovery path drift')
    for item in changed:
        value = files[item['filename']]
        blob = hashlib.sha1(b'blob ' + str(len(value)).encode() + b'\0' + value).hexdigest()
        require(item['status'] == 'added' and item['sha'] == blob, 'archive recovery content drift')
    if pr['mergeable'] is not True:
        return {'status': 'WAITING_ARCHIVE_MERGEABILITY', 'pr': pr['number'], 'head': sha}
    require(api.main() == main, 'main moved before archive refresh')
    # GitHub performs a normal merge from the base branch, with a head CAS.
    # New head/base must pass the original finalizer gates on a subsequent event.
    api.api(f"pulls/{pr['number']}/update-branch", writer=True, method='PUT',
            payload={'expected_head_sha': sha})
    return {'status': 'ARCHIVE_BRANCH_UPDATE_REQUESTED', 'pr': pr['number'],
            'previous_head': sha, 'verified_base': main}


def attempt_refresh(f, frozen, out):
    require(os.environ.get('GITHUB_REPOSITORY') == frozen['repository'], 'foreign executing repository')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'recovery requires trusted main')
    kind = os.environ['GITHUB_EVENT_NAME']
    require(kind in {'push', 'workflow_run', 'workflow_dispatch'}, 'untrusted recovery event')
    if kind == 'workflow_run':
        trigger = f.parse(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())['workflow_run']
        require(trigger['path'] in frozen['required_pr_workflows']
                and trigger['head_repository']['id'] == frozen['repository_id'], 'untrusted recovery trigger')
        if trigger['conclusion'] != 'success' or trigger['head_branch'] not in {'main', frozen['archive_branch']}:
            return {'status': 'IGNORED_TRIGGER'}
    api = f.GitHub(frozen)
    main = api.main()
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=f.ROOT, text=True).strip()
    require(checkout == main, 'checkout is no longer live main')
    if not api.checks_ready(main, main=True):
        return {'status': 'WAITING_EXACT_MAIN_GATES', 'main': main}
    if (f.ROOT / frozen['closure_path']).exists():
        return None
    return refresh_archive(api, frozen, main, lambda: f.collect(api, frozen, out))


def main():
    import i015_finalize as f

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        result = attempt_refresh(f, f.parse(f.MANIFEST.read_bytes()), args.output)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        result = {'status': 'BLOCKED', 'error': str(exc)}
        (args.output / 'status.json').write_bytes(f.encoded(result))
        print(json.dumps(result))
        raise SystemExit(1) from None
    if result is None:
        f.main()
    else:
        (args.output / 'status.json').write_bytes(f.encoded(result))
        print(json.dumps(result))


if __name__ == '__main__':
    main()
