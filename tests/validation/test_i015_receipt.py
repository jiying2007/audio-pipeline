#!/usr/bin/env python3
"""Receipt retries use historical archive lineage, not a fabricated current merge."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('receipt_finalizer', ROOT / '.github/program/i015_finalize.py')
f = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(f)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = {'evidence/result.json': b'original receipt\n'}
        for name, data in self.files.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        self.patch = patch.object(f, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.archive, self.current = 'a' * 40, 'b' * 40
        self.frozen = {'archive_branch': 'automation/i015-evidence-35994848668',
                       'repository_id': 1, 'run_id': 35994848668, 'artifact_id': 10805915721,
                       'artifact_sha256': 'd' * 64, 'reviewed_interpretation': 'diagnostic only',
                       'tracking_pr': 406}
        self.pr = {'number': 411, 'state': 'closed', 'merged': True, 'merged_at': '2026-09-24T15:50:52Z',
                   'head': {'ref': self.frozen['archive_branch'], 'repo': {'id': 1}},
                   'base': {'ref': 'main', 'repo': {'id': 1}}, 'merge_commit_sha': self.archive}
        self.lineage = [{'number': 411}]
        self.changes = [{'filename': p, 'sha': f.gh_blob(data), 'status': 'added'}
                        for p, data in self.files.items()]
        self.comments = []
        self.comparison = {'merge_base_commit': {'sha': self.archive}}
        self.api = Mock()
        self.api.repo = 'owner/repo'
        self.api.main.return_value = self.current
        self.api.checks_ready.return_value = True
        self.api.collection.side_effect = self.collection
        self.api.api.side_effect = self.request

    def collection(self, path):
        if path.startswith('pulls?state=closed&head=owner:'):
            return self.lineage
        if path == 'pulls/411/files?per_page=100':
            return self.changes
        if path == 'issues/406/comments?per_page=100':
            return self.comments
        raise AssertionError(path)

    def request(self, path, **kwargs):
        if path == 'pulls/411':
            return self.pr
        if path == f'compare/{self.archive}...{self.current}':
            return self.comparison
        if path == 'issues/406/comments':
            # Preserve the actual GitHub Actions bot identity, not the PAT user.
            self.assertNotIn('writer', kwargs)
            self.comments.append({'body': kwargs['payload']['body'],
                                  'user': {'login': 'github-actions[bot]'}})
            return {'id': 123}
        raise AssertionError(path)

    def run_receipt(self):
        return f.finalize_main(self.api, self.frozen, self.current, self.files)

    def writes(self):
        return [call for call in self.api.api.call_args_list if 'payload' in call.kwargs]

    def test_delayed_receipt_binds_original_merge_and_current_main(self):
        result = self.run_receipt()
        self.assertEqual(result['archive_merge_sha'], self.archive)
        self.assertEqual(result['verified_main'], self.current)
        self.assertEqual(result['status'], 'CLOSED_DIAGNOSTIC_ONLY')
        self.assertEqual(len(self.writes()), 1)
        body = self.comments[0]['body']
        self.assertIn('merged at `' + self.archive + '`', body)
        self.assertIn('verified main `' + self.current + '`', body)
        self.assertNotIn('merged at `' + self.current + '`', body)
        self.assertEqual([call.args[0] for call in self.api.checks_ready.call_args_list],
                         [self.archive, self.current])

    def test_same_sha_normal_completion(self):
        self.current = self.archive
        self.api.main.return_value = self.current
        self.assertEqual(self.run_receipt()['status'], 'CLOSED_DIAGNOSTIC_ONLY')

    def test_duplicate_event_does_not_duplicate_receipt(self):
        self.run_receipt()
        self.run_receipt()
        self.assertEqual(len(self.writes()), 1)

    def test_missing_and_ambiguous_lineage_stop(self):
        for rows in ([], [{'number': 411}, {'number': 412}]):
            self.lineage = rows
            with self.assertRaisesRegex(ValueError, 'unique'):
                self.run_receipt()
        self.assertFalse(self.writes())

    def test_closed_unmerged_pr_is_not_authority(self):
        self.pr['merged'] = False
        with self.assertRaisesRegex(ValueError, 'invalid merged'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_foreign_repository_stops(self):
        self.pr['head']['repo']['id'] = 2
        with self.assertRaisesRegex(ValueError, 'invalid merged'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_unrelated_merge_is_not_an_ancestor(self):
        self.comparison['merge_base_commit']['sha'] = 'c' * 40
        with self.assertRaisesRegex(ValueError, 'ancestor'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_unverified_archive_or_current_main_cannot_publish(self):
        for pending in (self.archive, self.current):
            self.api.checks_ready.side_effect = lambda sha, **kw: sha != pending
            self.assertEqual(self.run_receipt()['status'], 'WAITING_RECEIPT_MAIN_GATES')
        self.assertFalse(self.writes())

    def test_original_pr_file_drift_stops(self):
        self.changes[0]['sha'] = 'c' * 40
        with self.assertRaisesRegex(ValueError, 'content drift'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_current_committed_evidence_drift_stops(self):
        (self.root / 'evidence/result.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'committed archive drift'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_live_main_moves_before_post(self):
        self.api.main.return_value = 'c' * 40
        with self.assertRaisesRegex(ValueError, 'main moved'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_existing_receipt_is_not_rewritten(self):
        self.comments.append({'body': f.MARKER + ' different', 'user': {'login': 'github-actions[bot]'}})
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.run_receipt()
        self.assertFalse(self.writes())

    def test_receipt_write_permission_is_job_scoped(self):
        workflow = (ROOT / '.github/workflows/i015-evidence-finalization.yml').read_text()
        global_part, jobs = workflow.split('\njobs:\n', 1)
        self.assertIn('  pull-requests: read', global_part)
        job_permissions = jobs.split('    permissions:\n', 1)[1].split('    steps:', 1)[0]
        self.assertIn('      pull-requests: write', job_permissions)
        self.assertIn('      issues: write', job_permissions)
        self.assertIn('      contents: read', job_permissions)
        self.assertIn('      actions: read', job_permissions)
        contract = (ROOT / '.github/workflows/i015-evidence-finalization-contract.yml').read_text()
        self.assertNotIn('pull-requests: write', contract)
        self.assertNotIn('issues: write', contract)


if __name__ == '__main__':
    unittest.main()
