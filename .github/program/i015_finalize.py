#!/usr/bin/env python3
"""Finalize the already-consumed I015 run. Never execute research or artifact code."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / '.github/program/i015-finalization.json'
AUTHORITY = 'RESEARCH_DIAGNOSTIC_ONLY'
LANES = {'shipping', 'no_upstream', 'blend_only', 'guard_only'}
FALSE_FLAGS = ('lane_selected', 'guard_change_selected', 'blend_change_selected',
               'vad_mapping_selected', 'vad_threshold_selected')
MARKER = '<!-- i015-finalization:35994848668 -->'
MAX_BYTES = 2_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse(data):
    def invalid(value):
        raise ValueError('non-finite JSON value: ' + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def integer(value):
    return type(value) is int and value >= 0


def close(a, b):
    return type(a) in (int, float) and math.isfinite(a) and math.isclose(a, b, abs_tol=1e-12)


def validate_metrics(row):
    require(integer(row['frames']) and row['frames'] > 0, 'invalid frame count')
    require(set(row['lane_metrics']) == LANES, 'lane set changed')
    populations = set()
    for metric in row['lane_metrics'].values():
        for key in ('speech_frames', 'speech_active', 'noise_frames', 'noise_active'):
            require(integer(metric[key]), 'non-integer frame count')
        speech, noise = metric['speech_frames'], metric['noise_frames']
        require(speech > 0 and noise > 0 and speech + noise == row['frames'], 'geometry mismatch')
        require(metric['speech_active'] <= speech and metric['noise_active'] <= noise, 'count overflow')
        require(close(metric['recall'], metric['speech_active'] / speech), 'recall mismatch')
        require(close(metric['false_positive_rate'], metric['noise_active'] / noise), 'FPR mismatch')
        auc = metric['probability_auc']
        require(type(auc) in (float, int) and math.isfinite(auc) and 0 <= auc <= 1, 'invalid AUC')
        populations.add((speech, noise))
    require(len(populations) == 1, 'different lane populations')
    ship, base = (row['lane_metrics'][k] for k in ('shipping', 'no_upstream'))
    for key in ('rescued_speech_frames', 'lost_speech_frames', 'added_noise_active_frames',
                'removed_noise_active_frames', 'shipping_vs_no_upstream_active_diff_frames'):
        require(integer(row[key]), 'invalid difference count')
    require(ship['speech_active'] - base['speech_active'] ==
            row['rescued_speech_frames'] - row['lost_speech_frames'], 'speech delta mismatch')
    require(ship['noise_active'] - base['noise_active'] ==
            row['added_noise_active_frames'] - row['removed_noise_active_frames'], 'noise delta mismatch')
    require(row['shipping_vs_no_upstream_active_diff_frames'] == sum(row[k] for k in
            ('rescued_speech_frames', 'lost_speech_frames', 'added_noise_active_frames',
             'removed_noise_active_frames')), 'active difference mismatch')
    for prefix, total in (('rescued_speech', 'rescued_speech_frames'),
                          ('added_noise', 'added_noise_active_frames')):
        attr = row[prefix + '_attribution']
        require(all(integer(v) for v in attr.values()), 'invalid attribution count')
        require(sum(attr[k] for k in ('blend_only_exclusive', 'guard_only_exclusive',
                    'both_single_lanes_active', 'interaction_only')) == row[total], 'attribution partition mismatch')
        for lane in ('blend_only', 'guard_only'):
            require(attr[lane + '_active'] == attr[lane + '_exclusive'] + attr['both_single_lanes_active'],
                    'overlapping attribution mismatch')
    for field, metric in (('shipping_recall_gain_over_no_upstream', 'recall'),
                          ('shipping_fpr_change_vs_no_upstream', 'false_positive_rate'),
                          ('shipping_probability_auc_gain_over_no_upstream', 'probability_auc')):
        require(close(row[field], ship[metric] - base[metric]), 'metric delta mismatch')


def validate_sum(combined, parts):
    validate_metrics(combined)
    for key, value in combined.items():
        if type(value) is int:
            require(value == sum(p[key] for p in parts), 'aggregate count mismatch: ' + key)
        elif key.endswith('_attribution'):
            for name, count in value.items():
                require(count == sum(p[key][name] for p in parts), 'aggregate attribution mismatch')
    for lane in LANES:
        for key in ('speech_frames', 'speech_active', 'noise_frames', 'noise_active'):
            require(combined['lane_metrics'][lane][key] ==
                    sum(p['lane_metrics'][lane][key] for p in parts), 'aggregate population mismatch')
    # Pooled AUC is NOT an average of the partition AUCs. Do not claim to recompute it.


def verify_members(members, frozen):
    expected = frozen['member_sha256']
    require(set(members) == set(expected), 'archive membership changed')
    for name, data in members.items():
        require(digest(data) == expected[name], 'member digest mismatch: ' + name)
    sums = {}
    for line in members['SHA256SUMS'].decode('ascii').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        require(match is not None, 'invalid SHA256SUMS line')
        sha, name = match.groups()
        require(name not in sums, 'duplicate SHA256SUMS entry')
        sums[name] = sha
    require(set(sums) == set(members) - {'SHA256SUMS'}, 'incomplete internal manifest')
    require(all(digest(members[n]) == sha for n, sha in sums.items()), 'internal digest mismatch')
    source, infra = frozen['source_base_sha'], frozen['diagnostic_infrastructure_sha']
    require(members['source-base-revision.txt'].decode().strip() == source, 'wrong source')
    require(members['diagnostic-infra-revision.txt'].decode().strip() == infra, 'wrong infrastructure')
    build = dict(line.split('=', 1) for line in members['build-info.txt'].decode().splitlines())
    require(build['source_revision'] == source and build['ns_estimator'] == 'EMA'
            and build['fast_math'] == '0', 'wrong build identity')
    contract, result, summary = (parse(members[n]) for n in ('contract.json', 'result.json', 'summary.json'))
    require(contract['fresh_diagnostic_authority']['seeds'] == frozen['fresh_seeds'], 'contract seeds changed')
    require(contract['source_base_sha'] == source and contract['authority'] == AUTHORITY, 'contract binding mismatch')
    require(all(v is False for v in contract['authority_boundary'].values()), 'contract authority escalation')
    require(result['authority'] == AUTHORITY and result['investigation_id'] == frozen['investigation_id'], 'wrong authority')
    require(result['source_base_sha'] == source and result['fresh_seeds'] == frozen['fresh_seeds'], 'result binding mismatch')
    require(result['decision'] == 'VAD_UPSTREAM_CONSUMPTION_DECOMPOSED_REVIEW_REQUIRED', 'unreviewed decision')
    require(result['input_violations'] == [] and result['shipping_source_changed'] is False, 'invalid input/source change')
    for key in ('candidate_budget_consumed', 'confirmation_budget_consumed'):
        require(type(result[key]) is int and result[key] == 0, 'research budget changed')
    require(all(result['interpretation'][k] is False for k in FALSE_FLAGS), 'selection authority escalation')
    mirror = result['shipping_mirror']
    require(type(mirror['active_mismatch_frames']) is int and mirror['active_mismatch_frames'] == 0
            and type(mirror['probability_mismatch_frames']) is int and mirror['probability_mismatch_frames'] == 0
            and close(mirror['max_probability_delta'], 0), 'shipping mirror mismatch')
    parts = result['partitions']
    require([p['seed'] for p in parts] == frozen['fresh_seeds'], 'partition seeds changed')
    for part in parts:
        for domain in ('stationary', 'nonstationary'):
            validate_metrics(part[domain])
        validate_sum(part['summary'], [part['stationary'], part['nonstationary']])
    for domain in ('stationary', 'nonstationary'):
        validate_sum(result['combined_' + domain], [p[domain] for p in parts])
    n = result['combined_nonstationary']
    expected_summary = {
        'active_diff_frames': n['shipping_vs_no_upstream_active_diff_frames'],
        'added_noise_active_frames': n['added_noise_active_frames'],
        'rescued_speech_frames': n['rescued_speech_frames'],
        'decision': result['decision'], 'fresh_seeds': result['fresh_seeds'],
        'mirror_active_mismatches': mirror['active_mismatch_frames'],
        'mirror_max_delta': mirror['max_probability_delta'],
    }
    for lane in LANES:
        expected_summary[lane + '_recall'] = n['lane_metrics'][lane]['recall']
    for lane in ('shipping', 'no_upstream'):
        expected_summary[lane + '_fpr'] = n['lane_metrics'][lane]['false_positive_rate']
    require(summary == expected_summary, 'stdout summary mismatch')
    return result


def read_zip(data, frozen):
    require(len(data) == frozen['artifact_size_bytes'] and len(data) <= MAX_BYTES, 'ZIP size mismatch')
    require(digest(data) == frozen['artifact_sha256'], 'ZIP digest mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.infolist()
        names = [entry.filename for entry in info]
        require(len(names) == len(set(names)), 'duplicate ZIP members')
        require(set(names) == set(frozen['member_sha256']), 'unexpected ZIP member')
        require(sum(e.file_size for e in info) <= MAX_BYTES, 'ZIP expansion budget exceeded')
        for entry in info:
            require(re.fullmatch(r'[A-Za-z0-9_.-]+', entry.filename) is not None
                    and entry.filename not in {'.', '..'}, 'unsafe archive path')
            require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr >> 16)
                    and not entry.flag_bits & 1, 'non-regular/encrypted archive entry')
        members = {name: archive.read(name) for name in names}
    verify_members(members, frozen)
    return members


def render(members, frozen):
    result = verify_members(members, frozen)
    closure = {
        'schema_version': 1, 'investigation_id': frozen['investigation_id'],
        'status': 'CLOSED_DIAGNOSTIC_ONLY', 'authority': AUTHORITY,
        'source_base_sha': frozen['source_base_sha'],
        'diagnostic_infrastructure_sha': frozen['diagnostic_infrastructure_sha'],
        'decision': result['decision'], 'reviewed_decision': frozen['reviewed_decision'],
        'reviewed_interpretation': frozen['reviewed_interpretation'],
        'authoritative_execution': {k: frozen[k] for k in ('run_id', 'run_attempt', 'artifact_id',
            'artifact_name', 'artifact_sha256', 'artifact_size_bytes', 'member_sha256')},
        'fresh_authority': {'seeds': frozen['fresh_seeds'], 'diagnostic_execution_consumed': 1,
            'candidate_budget_consumed': 0, 'confirmation_budget_consumed': 0, 'rerun_allowed': False},
        'shipping_mirror': result['shipping_mirror'],
        'summary': {k: result[k] for k in ('combined_nonstationary', 'combined_stationary')},
        'original_result_path': frozen['archive_root'] + '/result.json',
        'verification_limits': frozen['verification_limits'],
        'authority_boundary': {k: False for k in ('lane_selected', 'guard_change_selected',
            'blend_change_selected', 'vad_threshold_selected', 'source_candidate_selected',
            'shipping_source_changed', 'hil_authority', 'product_certification_authority', 'release_authority')},
    }
    files = {frozen['archive_root'] + '/' + name: value for name, value in members.items()}
    files[frozen['closure_path']] = encoded(closure)
    files[frozen['archive_note_path']] = (
        '# I015 diagnostic closure\n\n'
        + frozen['reviewed_interpretation'] + '\n\n'
        + 'Canonical record: `' + frozen['closure_path'] + '`.\n\n'
        + 'Original text evidence: `' + frozen['archive_root'] + '/`.\n\n'
        + 'Run `' + str(frozen['run_id']) + '`, attempt 1; artifact `'
        + str(frozen['artifact_id']) + '`, ZIP SHA256 `' + frozen['artifact_sha256'] + '`.\n\n'
        + 'The one diagnostic execution is consumed. No rerun, lane selection, parameter '
        + 'tuning, shipping change, HIL, Product Certification or release is authorized.\n'
    ).encode()
    return files


def gh_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class GitHub:
    def __init__(self, frozen):
        self.repo = frozen['repository']

    def api(self, path, *, payload=None, method=None, writer=False, pages=False, binary=False):
        env = os.environ.copy()
        if writer:
            require(bool(env.get('GH_WRITE_TOKEN')), 'BLOCKED_AUTOMATION_CREDENTIAL: no publishing token')
            env['GH_TOKEN'] = env['GH_WRITE_TOKEN']
        args = ['gh', 'api', '--hostname', 'github.com']
        if pages:
            args += ['--paginate', '--slurp']
        if method or payload is not None:
            args += ['--method', method or 'POST']
        args += ['repos/' + self.repo + '/' + path]
        if payload is not None:
            args += ['--input', '-']
        try:
            process = subprocess.run(args, input=encoded(payload) if payload is not None else None,
                                     env=env, capture_output=True, timeout=90, check=True)
        except subprocess.CalledProcessError as exc:
            # Never publish raw stderr/stdout: they can contain credentials or
            # signed download URLs. Expose only bounded, allowlisted diagnostics.
            stderr = (exc.stderr or b'').decode('utf-8', errors='replace')
            match = re.search(r'\(HTTP ([1-5][0-9]{2})\)', stderr)
            status = int(match.group(1)) if match else None
            category = 'API_REQUEST_FAILED'
            known = {
                'Resource not accessible by personal access token': 'TOKEN_PERMISSION_DENIED',
                'Resource not accessible by integration': 'INTEGRATION_PERMISSION_DENIED',
                'Bad credentials': 'INVALID_CREDENTIAL',
                'Not Found': 'RESOURCE_NOT_FOUND',
                'Validation Failed': 'INVALID_REQUEST',
                'API rate limit exceeded': 'RATE_LIMITED',
            }
            try:
                body = parse((exc.stdout or b'')[:16384])
                if isinstance(body, dict):
                    category = known.get(body.get('message'), category)
            except (ValueError, TypeError, UnicodeDecodeError):
                pass
            raise ValueError('GitHub API request failed: ' + json.dumps({
                'method': method or ('POST' if payload is not None else 'GET'),
                'path': path[:256], 'http_status': status, 'category': category,
            }, sort_keys=True)) from None
        return process.stdout if binary else parse(process.stdout)

    def collection(self, path, key=None):
        return [item for page in self.api(path, pages=True) for item in (page[key] if key else page)]

    def main(self):
        return self.api('git/ref/heads/main')['object']['sha']

    def review_ready(self, number, sha, base):
        query = """query($owner:String!,$name:String!,$number:Int!) {
          repository(owner:$owner,name:$name) { pullRequest(number:$number) {
            headRefOid baseRefOid isDraft mergeStateStatus reviewDecision
            reviewThreads(first:100) { nodes { isResolved } pageInfo { hasNextPage } }
          } }
        }"""
        owner, name = self.repo.split('/')
        data = subprocess.check_output([
            'gh', 'api', '--hostname', 'github.com', 'graphql', '-f', 'query=' + query,
            '-f', 'owner=' + owner, '-f', 'name=' + name, '-F', 'number=' + str(number),
        ], timeout=90)
        response = parse(data)
        require(not response.get('errors'), 'review-state query failed')
        pr = response['data']['repository']['pullRequest']
        require(pr['headRefOid'] == sha and pr['baseRefOid'] == base, 'review identity drift')
        threads = pr['reviewThreads']
        return (pr['isDraft'] is False and pr['mergeStateStatus'] == 'CLEAN'
                and pr['reviewDecision'] in {None, 'APPROVED'}
                and threads['pageInfo']['hasNextPage'] is False
                and all(t['isResolved'] is True for t in threads['nodes']))

    def checks_ready(self, sha, *, main=False):
        if main:
            # Do not wait on this finalizer's own in-progress check, or Release.
            runs = self.collection(f'actions/runs?event=push&head_sha={sha}&per_page=100', 'workflow_runs')
            verifies = [r for r in runs if r['path'] == '.github/workflows/verify.yml'
                        and r['head_sha'] == sha and r['head_branch'] == 'main']
            if not verifies:
                return False
            latest = max(verifies, key=lambda r: r['id'])
            if latest['status'] != 'completed' or latest['conclusion'] != 'success':
                return False
            checks = self.collection(f'commits/{sha}/check-runs?check_name=summary&filter=latest&per_page=100', 'check_runs')
            return any(c['head_sha'] == sha and c['name'] == 'summary' and c['app']['id'] == 15368
                       and c['status'] == 'completed' and c['conclusion'] == 'success'
                       and f"/actions/runs/{latest['id']}/" in c['details_url'] for c in checks)
        checks = self.collection(f'commits/{sha}/check-runs?filter=latest&per_page=100', 'check_runs')
        summaries = [c for c in checks if c['name'] == 'summary' and c['app']['id'] == 15368]
        if not summaries or any(c['head_sha'] != sha or c['status'] != 'completed'
                                or c['conclusion'] != 'success' for c in summaries):
            return False
        if any(c['status'] != 'completed' or c['conclusion'] not in {'success', 'skipped'} for c in checks):
            return False
        statuses = self.api(f'commits/{sha}/status')['statuses']
        return all(s['state'] == 'success' for s in statuses)


def validate_run(run, frozen):
    require(run['id'] == frozen['run_id'] and run['workflow_id'] == frozen['workflow_id'], 'wrong source run')
    require(run['path'] == frozen['workflow_path'] and run['event'] == 'workflow_dispatch'
            and run['head_branch'] == 'main' and run['head_sha'] == frozen['diagnostic_infrastructure_sha'], 'untrusted run lineage')
    require(run['head_repository']['id'] == frozen['repository_id']
            and run['repository']['id'] == frozen['repository_id'], 'foreign repository')
    require(run['run_attempt'] == 1 and run['status'] == 'completed'
            and run['conclusion'] == 'success', 'non-authoritative run attempt')


def collect(api, frozen, out):
    run = api.api(f"actions/runs/{frozen['run_id']}")
    validate_run(run, frozen)
    artifacts = api.collection(f"actions/runs/{frozen['run_id']}/artifacts?per_page=100", 'artifacts')
    found = [a for a in artifacts if a['id'] == frozen['artifact_id']]
    require(len(found) == 1, 'missing or ambiguous original artifact')
    a = found[0]
    require(a['name'] == frozen['artifact_name'] and a['expired'] is False
            and a['digest'] == 'sha256:' + frozen['artifact_sha256']
            and a['size_in_bytes'] == frozen['artifact_size_bytes'], 'artifact receipt mismatch')
    require(a['workflow_run']['id'] == frozen['run_id']
            and a['workflow_run']['head_sha'] == frozen['diagnostic_infrastructure_sha'], 'artifact run binding mismatch')
    data = api.api(f"actions/artifacts/{frozen['artifact_id']}/zip", binary=True)
    members = read_zip(data, frozen)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'original-evidence.zip').write_bytes(data)
    (out / 'source-run.json').write_bytes(encoded(run))
    (out / 'source-artifact.json').write_bytes(encoded(a))
    return render(members, frozen)


def expected_diff(files, changed):
    require(len(changed) == len(files) and {f['filename'] for f in changed} == set(files), 'archive PR path drift')
    require(all(f['status'] == 'added' and f['sha'] == gh_blob(files[f['filename']])
                for f in changed), 'archive PR content drift')


def pr_ready(api, pr, frozen, main, files):
    require(pr['base']['ref'] == 'main' and pr['base']['sha'] == main
            and pr['head']['ref'] == frozen['archive_branch']
            and pr['head']['repo']['id'] == frozen['repository_id'], 'archive PR identity/base drift')
    sha = pr['head']['sha']
    changed = api.collection(f"pulls/{pr['number']}/files?per_page=100")
    expected_diff(files, changed)
    comparison = api.api(f'compare/{main}...{sha}')
    require(comparison['merge_base_commit']['sha'] == main, 'stale archive PR base')
    if pr['draft'] or pr['mergeable'] is not True or pr['mergeable_state'] != 'clean':
        return False
    if not api.checks_ready(sha) or not api.review_ready(pr['number'], sha, main):
        return False
    runs = api.collection(f'actions/runs?event=pull_request&head_sha={sha}&per_page=100', 'workflow_runs')
    for path in frozen['required_pr_workflows']:
        matching = [r for r in runs if r['path'] == path and r['head_sha'] == sha
                    and any(p['number'] == pr['number'] and p['base']['sha'] == main
                            and p['head']['sha'] == sha for p in r['pull_requests'])]
        if not matching:
            return False
        latest = max(matching, key=lambda r: r['id'])
        if latest['status'] != 'completed' or latest['conclusion'] != 'success':
            return False
    return True


def publish_or_merge(api, frozen, files, main):
    branch = frozen['archive_branch']
    prs = api.collection(f'pulls?state=all&head={api.repo.split("/")[0]}:{branch}&base=main&per_page=100')
    require(len(prs) <= 1, 'ambiguous archive PR history')
    if prs:
        pr = api.api(f"pulls/{prs[0]['number']}")
        require(pr['state'] == 'open', 'archive PR closed; do not recreate or overwrite')
        if not pr_ready(api, pr, frozen, main, files):
            return {'status': 'WAITING_EXACT_PR_GATES', 'pr': pr['number'], 'head': pr['head']['sha']}
        require(api.main() == main, 'main moved before merge')
        merged = api.api(f"pulls/{pr['number']}/merge", writer=True, method='PUT',
                         payload={'merge_method': 'squash', 'sha': pr['head']['sha']})
        require(merged.get('merged') is True, 'protected merge rejected')
        return {'status': 'MERGED_WAITING_MAIN_VERIFY', 'pr': pr['number'], 'merge_sha': merged['sha']}
    require(api.main() == main, 'main moved before archive creation')
    base = api.api(f'git/commits/{main}')
    tree = api.api('git/trees', writer=True, payload={
        'base_tree': base['tree']['sha'], 'tree': [
            {'path': name, 'mode': '100644', 'type': 'blob', 'content': data.decode('utf-8')}
            for name, data in sorted(files.items())]})
    refs = api.api('git/matching-refs/heads/' + branch)
    exact = [r for r in refs if r['ref'] == 'refs/heads/' + branch]
    require(len(exact) <= 1, 'ambiguous archive branch')
    if exact:
        commit = api.api('git/commits/' + exact[0]['object']['sha'])
        require(commit['tree']['sha'] == tree['sha'] and [p['sha'] for p in commit['parents']] == [main],
                'existing archive branch drift; never force-push')
    else:
        commit = api.api('git/commits', writer=True, payload={
            'message': 'research(i015): archive verified one-shot evidence',
            'tree': tree['sha'], 'parents': [main]})
        api.api('git/refs', writer=True, payload={'ref': 'refs/heads/' + branch, 'sha': commit['sha']})
    pr = api.api('pulls', writer=True, payload={
        'title': 'research(i015): close verified upstream-consumption decomposition',
        'head': branch, 'base': 'main',
        'body': MARKER + '\n\nDeterministic archive of existing run `' + str(frozen['run_id']) +
                '`, artifact `' + str(frozen['artifact_id']) + '`. No research rerun.\n\n' +
                frozen['reviewed_interpretation'] + '\n\nAll original text members and their hashes are preserved. '
                'Candidate/confirmation consumption remains zero. This PR has no shipping, HIL, '
                'Product Certification or release authority. Merge only after exact-head/base applicable gates.'})
    return {'status': 'ARCHIVE_PR_CREATED', 'pr': pr['number'], 'head': commit['sha']}


def finalize_main(api, frozen, main, files):
    # The checkout is always trusted main. Never fetch or execute PR-head code here.
    for name, expected in files.items():
        require((ROOT / name).is_file() and (ROOT / name).read_bytes() == expected, 'committed archive drift: ' + name)
    lineage = api.collection(f'commits/{main}/pulls?per_page=100')
    eligible = [p for p in lineage if p.get('merged_at') and p['merge_commit_sha'] == main
                and p['head']['ref'] == frozen['archive_branch'] and p['base']['ref'] == 'main']
    require(len(eligible) == 1, 'no exact merged archive PR lineage')
    body = (MARKER + '\n\n### I015 CLOSED_DIAGNOSTIC_ONLY\n\n'
            f"Original run `{frozen['run_id']}`, artifact `{frozen['artifact_id']}`; "
            f"ZIP SHA256 `{frozen['artifact_sha256']}`. All nine internal hashes verified.\n\n"
            f"Archive PR #{eligible[0]['number']} merged at `{main}`; exact-main Verify/summary passed. "
            'Original text evidence is retained in Git and remains available after artifact expiry.\n\n'
            + frozen['reviewed_interpretation'] + '\n\nNo experiment was rerun; no lane, constant, seed, '
            'shipping, HIL, Product Certification or release authority changed.')
    comments = api.collection(f"issues/{frozen['tracking_pr']}/comments?per_page=100")
    marked = [c for c in comments if c['body'].startswith(MARKER) and c['user']['login'] == 'github-actions[bot]']
    require(len(marked) <= 1, 'duplicate finalization receipts')
    if not marked:
        api.api(f"issues/{frozen['tracking_pr']}/comments", payload={'body': body})
    elif marked[0]['body'] != body:
        # An existing receipt is immutable; do not silently replace its identity.
        raise ValueError('existing finalization receipt differs')
    return {'status': 'CLOSED_DIAGNOSTIC_ONLY', 'archive_pr': eligible[0]['number'], 'verified_main': main}


def reconcile(frozen, out):
    require(os.environ.get('GITHUB_REPOSITORY') == frozen['repository'], 'foreign executing repository')
    require(os.environ.get('GITHUB_REF') == 'refs/heads/main', 'finalizer must run on trusted main')
    event = parse(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    kind = os.environ['GITHUB_EVENT_NAME']
    require(kind in {'push', 'workflow_run', 'workflow_dispatch'}, 'untrusted event')
    if kind == 'workflow_run':
        trigger = event['workflow_run']
        require(trigger['path'] in frozen['required_pr_workflows']
                and trigger['head_repository']['id'] == frozen['repository_id'], 'untrusted trigger')
        if trigger['conclusion'] != 'success' or trigger['head_branch'] not in {'main', frozen['archive_branch']}:
            return {'status': 'IGNORED_TRIGGER'}
    api = GitHub(frozen)
    main = api.main()
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(checkout == main, 'checkout is no longer live main')
    if not api.checks_ready(main, main=True):
        return {'status': 'WAITING_EXACT_MAIN_GATES', 'main': main}
    closure = ROOT / frozen['closure_path']
    if closure.exists():
        members = {n: (ROOT / frozen['archive_root'] / n).read_bytes() for n in frozen['member_sha256']}
        files = render(members, frozen)
        # Later unrelated main updates must not rewrite the original closure receipt.
        if kind == 'workflow_run' and event['workflow_run']['head_sha'] != main:
            return {'status': 'IGNORED_STALE_TRIGGER'}
        existing = api.collection(f"issues/{frozen['tracking_pr']}/comments?per_page=100")
        if any(c['body'].startswith(MARKER) and c['user']['login'] == 'github-actions[bot]' for c in existing):
            for name, value in files.items():
                require((ROOT / name).read_bytes() == value, 'closed archive drift')
            return {'status': 'ALREADY_CLOSED_NOOP'}
        return finalize_main(api, frozen, main, files)
    files = collect(api, frozen, out)
    (out / 'proposed-closure.json').write_bytes(files[frozen['closure_path']])
    return publish_or_merge(api, frozen, files, main)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, help='Offline verification only; no GitHub writes')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    frozen = parse(MANIFEST.read_bytes())
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        if args.zip:
            files = render(read_zip(args.zip.read_bytes(), frozen), frozen)
            (args.output / 'proposed-closure.json').write_bytes(files[frozen['closure_path']])
            result = {'status': 'VERIFIED_ORIGINAL_EVIDENCE', 'members_verified': 9,
                      'artifact_sha256': frozen['artifact_sha256'], 'github_writes': False}
        else:
            result = reconcile(frozen, args.output)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile,
            subprocess.SubprocessError) as exc:
        result = {'status': 'BLOCKED', 'error': str(exc)}
        (args.output / 'status.json').write_bytes(encoded(result))
        print(json.dumps(result))
        raise SystemExit(1) from exc
    (args.output / 'status.json').write_bytes(encoded(result))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
