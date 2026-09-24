#!/usr/bin/env python3
"""Offline metadata-only negative tests. No audio generator, probe or fresh run."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('i015_finalize', ROOT / '.github/program/i015_finalize.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
FROZEN = f.parse((ROOT / '.github/program/i015-finalization.json').read_bytes())


def metrics(k=1):
    counts = {'no_upstream': (1, 0), 'shipping': (2, 1), 'blend_only': (2, 0), 'guard_only': (1, 1)}
    lanes = {name: {'speech_frames': 2*k, 'noise_frames': 2*k, 'speech_active': a*k,
                   'noise_active': b*k, 'recall': a/2, 'false_positive_rate': b/2,
                   'probability_auc': 0.5} for name, (a, b) in counts.items()}
    def attr(blend, guard):
        return {'blend_only_active': blend*k, 'guard_only_active': guard*k,
                'blend_only_exclusive': blend*k, 'guard_only_exclusive': guard*k,
                'both_single_lanes_active': 0, 'interaction_only': 0}
    return {'frames': 4*k, 'lane_metrics': lanes, 'rescued_speech_frames': k,
            'lost_speech_frames': 0, 'added_noise_active_frames': k, 'removed_noise_active_frames': 0,
            'shipping_vs_no_upstream_active_diff_frames': 2*k,
            'rescued_speech_attribution': attr(1, 0), 'added_noise_attribution': attr(0, 1),
            'shipping_recall_gain_over_no_upstream': 0.5, 'shipping_fpr_change_vs_no_upstream': 0.5,
            'shipping_probability_auc_gain_over_no_upstream': 0.0}


def fixture():
    frozen = copy.deepcopy(FROZEN)
    result = {'schema_version': 1, 'authority': f.AUTHORITY,
              'investigation_id': frozen['investigation_id'], 'source_base_sha': frozen['source_base_sha'],
              'fresh_seeds': frozen['fresh_seeds'], 'decision': 'VAD_UPSTREAM_CONSUMPTION_DECOMPOSED_REVIEW_REQUIRED',
              'input_violations': [], 'shipping_source_changed': False,
              'candidate_budget_consumed': 0, 'confirmation_budget_consumed': 0,
              'shipping_mirror': {'active_mismatch_frames': 0, 'probability_mismatch_frames': 0, 'max_probability_delta': 0.0},
              'interpretation': {key: False for key in f.FALSE_FLAGS},
              'partitions': [{'seed': seed, 'stationary': metrics(), 'nonstationary': metrics(), 'summary': metrics(2)}
                             for seed in frozen['fresh_seeds']],
              'combined_stationary': metrics(3), 'combined_nonstationary': metrics(3)}
    summary = {'active_diff_frames': 6, 'added_noise_active_frames': 3, 'rescued_speech_frames': 3,
               'decision': result['decision'], 'fresh_seeds': frozen['fresh_seeds'],
               'mirror_active_mismatches': 0, 'mirror_max_delta': 0.0,
               'no_upstream_fpr': 0.0, 'shipping_fpr': 0.5}
    for lane, value in result['combined_nonstationary']['lane_metrics'].items():
        summary[lane + '_recall'] = value['recall']
    contract = {'authority': f.AUTHORITY, 'source_base_sha': frozen['source_base_sha'],
                'fresh_diagnostic_authority': {'seeds': frozen['fresh_seeds']}, 'authority_boundary': {'shipping': False}}
    members = {name: b'fixture\n' for name in frozen['member_sha256']}
    members.update({'result.json': f.encoded(result), 'summary.json': f.encoded(summary),
                    'contract.json': f.encoded(contract),
                    'source-base-revision.txt': frozen['source_base_sha'].encode(),
                    'diagnostic-infra-revision.txt': frozen['diagnostic_infrastructure_sha'].encode(),
                    'build-info.txt': ('source_revision=' + frozen['source_base_sha'] + '\nns_estimator=EMA\nfast_math=0\n').encode()})
    return reseal(members, frozen)


def reseal(members, frozen):
    members['SHA256SUMS'] = ''.join(f.digest(v) + '  ' + k + '\n' for k, v in sorted(members.items())
                                    if k != 'SHA256SUMS').encode()
    frozen['member_sha256'] = {k: f.digest(v) for k, v in members.items()}
    return members, frozen


def packed(members, frozen, extra=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)
        if extra:
            archive.writestr(*extra)
    data = stream.getvalue()
    frozen['artifact_sha256'] = f.digest(data)
    frozen['artifact_size_bytes'] = len(data)
    return data


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.members, self.frozen = fixture()

    def mutate_result(self, mutation):
        result = f.parse(self.members['result.json']); mutation(result)
        self.members['result.json'] = f.encoded(result)
        reseal(self.members, self.frozen)

    def test_valid_archive_and_deterministic_render(self):
        data = packed(self.members, self.frozen)
        got = f.read_zip(data, self.frozen)
        self.assertEqual(f.render(got, self.frozen), f.render(got, self.frozen))
        self.assertEqual(len(f.render(got, self.frozen)), 12)

    def test_wrong_zip_digest(self):
        data = packed(self.members, self.frozen)
        with self.assertRaisesRegex(ValueError, 'digest'): f.read_zip(data[:-1] + b'x', self.frozen)

    def test_wrong_zip_size(self):
        data = packed(self.members, self.frozen)
        with self.assertRaisesRegex(ValueError, 'size'): f.read_zip(data + b'x', self.frozen)

    def test_duplicate_members(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            data = packed(self.members, self.frozen, ('result.json', b'{}'))
        with self.assertRaisesRegex(ValueError, 'duplicate'): f.read_zip(data, self.frozen)

    def test_unknown_members(self):
        data = packed(self.members, self.frozen, ('payload.sh', b'false'))
        with self.assertRaisesRegex(ValueError, 'unexpected'): f.read_zip(data, self.frozen)

    def test_path_traversal(self):
        self.members['../payload'] = self.members.pop('compiler.txt'); reseal(self.members, self.frozen)
        data = packed(self.members, self.frozen)
        with self.assertRaisesRegex(ValueError, 'unsafe'): f.read_zip(data, self.frozen)

    def test_symlink(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, value in self.members.items():
                entry = zipfile.ZipInfo(name)
                if name == 'compiler.txt': entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, value)
        data = stream.getvalue(); self.frozen.update(artifact_sha256=f.digest(data), artifact_size_bytes=len(data))
        with self.assertRaisesRegex(ValueError, 'non-regular'): f.read_zip(data, self.frozen)

    def test_member_digest_mismatch(self):
        self.members['result.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'member digest'): f.verify_members(self.members, self.frozen)

    def test_internal_manifest_missing_member(self):
        self.members['SHA256SUMS'] = self.members['SHA256SUMS'].split(b'\n', 1)[1]
        self.frozen['member_sha256']['SHA256SUMS'] = f.digest(self.members['SHA256SUMS'])
        with self.assertRaisesRegex(ValueError, 'incomplete'): f.verify_members(self.members, self.frozen)

    def test_duplicate_json_key(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'): f.parse(b'{"a": 1, "a": 2}')

    def test_nan_json(self):
        for bad in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(bad=bad), self.assertRaises(ValueError): f.parse('{"v":' + bad + '}')

    def test_wrong_source(self):
        self.mutate_result(lambda r: r.update(source_base_sha='0'*40))
        with self.assertRaisesRegex(ValueError, 'binding'): f.verify_members(self.members, self.frozen)

    def test_wrong_seeds(self):
        self.mutate_result(lambda r: r.update(fresh_seeds=[1, 2, 3]))
        with self.assertRaisesRegex(ValueError, 'binding'): f.verify_members(self.members, self.frozen)

    def test_authority_string_false_is_rejected(self):
        self.mutate_result(lambda r: r['interpretation'].update(lane_selected='false'))
        with self.assertRaisesRegex(ValueError, 'escalation'): f.verify_members(self.members, self.frozen)

    def test_boolean_budget_is_rejected(self):
        self.mutate_result(lambda r: r.update(candidate_budget_consumed=False))
        with self.assertRaisesRegex(ValueError, 'budget'): f.verify_members(self.members, self.frozen)

    def test_mirror_mismatch(self):
        self.mutate_result(lambda r: r['shipping_mirror'].update(active_mismatch_frames=1))
        with self.assertRaisesRegex(ValueError, 'mirror'): f.verify_members(self.members, self.frozen)

    def test_wrong_recall(self):
        row = metrics(); row['lane_metrics']['shipping']['recall'] = 0.4
        with self.assertRaisesRegex(ValueError, 'recall'): f.validate_metrics(row)

    def test_boolean_count(self):
        row = metrics(); row['frames'] = True
        with self.assertRaisesRegex(ValueError, 'count'): f.validate_metrics(row)

    def test_attribution_overlap_mismatch(self):
        row = metrics(); row['rescued_speech_attribution']['blend_only_active'] = 2
        with self.assertRaisesRegex(ValueError, 'overlapping'): f.validate_metrics(row)

    def test_attribution_partition_mismatch(self):
        row = metrics(); row['rescued_speech_attribution']['interaction_only'] = 1
        with self.assertRaisesRegex(ValueError, 'partition'): f.validate_metrics(row)

    def test_aggregate_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'aggregate'): f.validate_sum(metrics(3), [metrics(), metrics()])

    def test_summary_mismatch(self):
        self.members['summary.json'] = b'{}'; reseal(self.members, self.frozen)
        with self.assertRaisesRegex(ValueError, 'summary'): f.verify_members(self.members, self.frozen)

    def test_foreign_run_and_rerun_rejected(self):
        run = {'id': self.frozen['run_id'], 'workflow_id': self.frozen['workflow_id'],
               'path': self.frozen['workflow_path'], 'event': 'workflow_dispatch', 'head_branch': 'main',
               'head_sha': self.frozen['diagnostic_infrastructure_sha'],
               'head_repository': {'id': self.frozen['repository_id']},
               'repository': {'id': self.frozen['repository_id']}, 'run_attempt': 1,
               'status': 'completed', 'conclusion': 'success'}
        f.validate_run(run, self.frozen)
        for key, value in [('run_attempt', 2), ('event', 'pull_request'), ('head_branch', 'fork'), ('head_sha', 'a'*40)]:
            with self.subTest(key=key), self.assertRaises(ValueError): f.validate_run(dict(run, **{key: value}), self.frozen)

    def test_exact_path_and_blob_allowlist(self):
        files = {'x.json': b'{}'}
        good = [{'filename': 'x.json', 'status': 'added', 'sha': f.gh_blob(b'{}')}]
        f.expected_diff(files, good)
        for bad in (good + [{'filename': 'extra'}], [dict(good[0], sha='0'*40)], [dict(good[0], status='modified')]):
            with self.assertRaises(ValueError): f.expected_diff(files, bad)

    def test_missing_write_credential_fails_before_subprocess(self):
        with patch.dict(os.environ, {}, clear=True), patch('subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'BLOCKED_AUTOMATION_CREDENTIAL'):
                f.GitHub(self.frozen).api('git/trees', writer=True, payload={})
            run.assert_not_called()

    def test_api_permission_error_has_safe_http_diagnostic(self):
        error = f.subprocess.CalledProcessError(1, ['gh', 'api'],
            output=b'{"message":"Resource not accessible by personal access token"}',
            stderr=b'gh: denied (HTTP 403)')
        with patch.dict(os.environ, {'GH_WRITE_TOKEN': 'private-token'}, clear=True), \
                patch('subprocess.run', side_effect=error):
            with self.assertRaises(ValueError) as caught:
                f.GitHub(self.frozen).api('git/trees', payload={}, writer=True)
        message = str(caught.exception)
        self.assertIn('TOKEN_PERMISSION_DENIED', message)
        self.assertIn('403', message)
        self.assertIn('git/trees', message)
        self.assertNotIn('private-token', message)

    def test_api_error_does_not_echo_unknown_server_text(self):
        error = f.subprocess.CalledProcessError(1, ['gh', 'api'],
            output=b'{"message":"credential private-token https://host/?sig=secret"}',
            stderr=b'private-token https://host/?sig=secret (HTTP 422)')
        with patch('subprocess.run', side_effect=error):
            with self.assertRaises(ValueError) as caught:
                f.GitHub(self.frozen).api('git/trees', payload={})
        message = str(caught.exception)
        self.assertIn('422', message)
        self.assertIn('API_REQUEST_FAILED', message)
        self.assertNotIn('private-token', message)
        self.assertNotIn('sig=', message)

    def test_non_json_api_error_is_bounded_and_does_not_echo_stderr(self):
        error = f.subprocess.CalledProcessError(1, ['gh', 'api'],
            output=b'\xff', stderr=b'network failed: private-token')
        with patch('subprocess.run', side_effect=error):
            with self.assertRaises(ValueError) as caught:
                f.GitHub(self.frozen).api('actions/artifacts/1/zip', binary=True)
        self.assertIn('API_REQUEST_FAILED', str(caught.exception))
        self.assertNotIn('private-token', str(caught.exception))

    def test_closed_archive_pr_is_not_recreated(self):
        api = unittest.mock.Mock(); api.repo = self.frozen['repository']
        api.collection.return_value = [{'number': 7}]; api.api.return_value = {'state': 'closed'}
        with self.assertRaisesRegex(ValueError, 'closed'): f.publish_or_merge(api, self.frozen, {}, 'a'*40)
        self.assertEqual(api.api.call_count, 1)

    def test_waiting_pr_gates_does_not_merge(self):
        api = unittest.mock.Mock(); api.repo = self.frozen['repository']
        api.collection.return_value = [{'number': 7}]
        api.api.return_value = {'state': 'open', 'number': 7, 'head': {'sha': 'b'*40}}
        with patch.object(f, 'pr_ready', return_value=False):
            result = f.publish_or_merge(api, self.frozen, {}, 'a'*40)
        self.assertEqual(result['status'], 'WAITING_EXACT_PR_GATES'); self.assertEqual(api.api.call_count, 1)

    def test_main_movement_blocks_merge(self):
        api = unittest.mock.Mock(); api.repo = self.frozen['repository']
        api.collection.return_value = [{'number': 7}]
        api.api.return_value = {'state': 'open', 'number': 7, 'head': {'sha': 'b'*40}}
        api.main.return_value = 'c'*40
        with patch.object(f, 'pr_ready', return_value=True), self.assertRaisesRegex(ValueError, 'moved'):
            f.publish_or_merge(api, self.frozen, {}, 'a'*40)
        self.assertEqual(api.api.call_count, 1)

    def test_main_gate_does_not_wait_on_finalizer_itself(self):
        api = f.GitHub(self.frozen); sha = 'a'*40
        checks = [{'head_sha': sha, 'name': 'summary', 'app': {'id': 15368}, 'status': 'completed',
                   'conclusion': 'success', 'details_url': 'https://github.com/a/b/actions/runs/123/job/456'}]
        runs = [{'path': '.github/workflows/verify.yml', 'head_sha': sha, 'head_branch': 'main',
                 'id': 123, 'status': 'completed', 'conclusion': 'success'}]
        with patch.object(api, 'collection', side_effect=[runs, checks]): self.assertTrue(api.checks_ready(sha, main=True))
        checks[0]['details_url'] = 'https://github.com/a/b/actions/runs/999/job/456'
        with patch.object(api, 'collection', side_effect=[runs, checks]): self.assertFalse(api.checks_ready(sha, main=True))

    def test_review_gate_blocks_required_or_unresolved_review(self):
        api = f.GitHub(self.frozen)
        pr = {'headRefOid': 'b'*40, 'baseRefOid': 'a'*40, 'isDraft': False,
              'mergeStateStatus': 'CLEAN', 'reviewDecision': None,
              'reviewThreads': {'nodes': [], 'pageInfo': {'hasNextPage': False}}}
        def check(value):
            response = {'data': {'repository': {'pullRequest': value}}}
            with patch('subprocess.check_output', return_value=f.encoded(response)):
                return api.review_ready(7, 'b'*40, 'a'*40)
        self.assertTrue(check(pr))
        self.assertFalse(check(dict(pr, reviewDecision='REVIEW_REQUIRED')))
        self.assertFalse(check(dict(pr, reviewDecision='CHANGES_REQUESTED')))
        self.assertFalse(check(dict(pr, reviewThreads={'nodes': [{'isResolved': False}],
                                                     'pageInfo': {'hasNextPage': False}})))
        self.assertFalse(check(dict(pr, reviewThreads={'nodes': [], 'pageInfo': {'hasNextPage': True}})))
        with self.assertRaisesRegex(ValueError, 'drift'): check(dict(pr, headRefOid='c'*40))

    def test_existing_committed_archive_is_byte_exact(self):
        closure = ROOT / FROZEN['closure_path']
        if not closure.exists(): self.skipTest('canonical archive PR not yet materialized')
        members = {name: (ROOT / FROZEN['archive_root'] / name).read_bytes() for name in FROZEN['member_sha256']}
        for name, value in f.render(members, FROZEN).items(): self.assertEqual((ROOT / name).read_bytes(), value, name)

    def test_workflow_trust_and_no_self_trigger(self):
        text = (ROOT / '.github/workflows/i015-evidence-finalization.yml').read_text()
        self.assertNotIn('  pull_request:', text)
        self.assertIn('ref: main', text); self.assertIn('persist-credentials: false', text)
        self.assertNotIn('schedule:', text); self.assertNotIn('actions: write', text)
        self.assertNotIn('gh workflow run', text); self.assertNotIn('gh run rerun', text)
        workflows = text.split('    workflows: [', 1)[1].split(']', 1)[0].split(', ')
        self.assertNotIn('I015 Evidence Finalization', workflows)
        self.assertIn('I015 Evidence Finalization Contract', workflows)
        source = (ROOT / '.github/program/i015_finalize.py').read_text()
        self.assertNotIn("'/dispatches'", source); self.assertNotIn("'/rerun'", source)
        self.assertNotIn('force=True', source); self.assertNotIn('--admin', source)


if __name__ == '__main__':
    unittest.main()
