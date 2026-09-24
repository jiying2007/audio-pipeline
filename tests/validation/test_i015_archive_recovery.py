#!/usr/bin/env python3
"""Metadata-only tests: no audio, probe, workflow dispatch or real GitHub writes."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('archive_recovery', ROOT / '.github/program/i015_archive_recovery.py')
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.frozen = {'repository': 'owner/repo', 'repository_id': 1,
                       'archive_branch': 'automation/i015-evidence-35994848668',
                       'closure_path': 'closure.json', 'required_pr_workflows': ['verify.yml']}
        self.base, self.head = 'a' * 40, 'b' * 40
        self.pr = {'number': 411, 'state': 'open', 'draft': False, 'mergeable': True,
                   'base': {'ref': 'main', 'repo': {'id': 1}},
                   'head': {'ref': self.frozen['archive_branch'], 'sha': self.head, 'repo': {'id': 1}}}
        self.files = {'archive/result.json': b'original receipt\n'}
        value = self.files['archive/result.json']
        self.changes = [{'filename': 'archive/result.json', 'status': 'added',
                         'sha': hashlib.sha1(b'blob ' + str(len(value)).encode() + b'\0' + value).hexdigest()}]
        self.comparison = {'merge_base_commit': {'sha': 'c' * 40}, 'behind_by': 1, 'ahead_by': 1}
        self.api = Mock()
        self.api.repo = 'owner/repo'
        self.api.main.return_value = self.base
        self.api.api.side_effect = lambda path, **kwargs: (
            self.pr if path == 'pulls/411' else self.comparison if path.startswith('compare/') else {})
        self.api.collection.side_effect = lambda path: self.changes if '/files?' in path else [{'number': 411}]
        self.load = Mock(return_value=self.files)

    def run_refresh(self):
        return r.refresh_archive(self.api, self.frozen, self.base, self.load)

    def writes(self):
        return [call for call in self.api.api.call_args_list if call.kwargs.get('writer')]

    def test_stale_exact_archive_updates_branch_once_not_main(self):
        self.assertEqual(self.run_refresh()['status'], 'ARCHIVE_BRANCH_UPDATE_REQUESTED')
        self.assertEqual(len(self.writes()), 1)
        call = self.writes()[0]
        self.assertEqual(call.args, ('pulls/411/update-branch',))
        self.assertEqual(call.kwargs, {'writer': True, 'method': 'PUT', 'payload': {'expected_head_sha': self.head}})

    def test_no_archive_pr_delegates_creation(self):
        self.api.collection.side_effect = None
        self.api.collection.return_value = []
        self.assertIsNone(self.run_refresh())
        self.assertFalse(self.writes())
        self.load.assert_not_called()

    def test_current_base_delegates_original_gates(self):
        self.comparison['merge_base_commit']['sha'] = self.base
        self.assertIsNone(self.run_refresh())
        self.assertFalse(self.writes())
        self.load.assert_not_called()

    def test_closed_pr_is_not_recreated(self):
        self.pr['state'] = 'closed'
        self.assertIsNone(self.run_refresh())
        self.assertFalse(self.writes())

    def test_draft_stops(self):
        self.pr['draft'] = True
        with self.assertRaisesRegex(ValueError, 'draft'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_foreign_pr_and_wrong_branch_stop(self):
        original = copy.deepcopy(self.pr)
        for section, key, value in [('head', 'repo', {'id': 2}), ('base', 'repo', {'id': 2}),
                                    ('head', 'ref', 'unrelated'), ('base', 'ref', 'other')]:
            self.pr = copy.deepcopy(original)
            self.pr[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaisesRegex(ValueError, 'identity'):
                self.run_refresh()
        self.assertFalse(self.writes())

    def test_path_drift_stops(self):
        self.changes.append({'filename': 'src/extra.c', 'status': 'added', 'sha': 'd' * 40})
        with self.assertRaisesRegex(ValueError, 'path drift'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_hash_drift_stops(self):
        self.changes[0]['sha'] = 'd' * 40
        with self.assertRaisesRegex(ValueError, 'content drift'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_modified_instead_of_added_stops(self):
        self.changes[0]['status'] = 'modified'
        with self.assertRaisesRegex(ValueError, 'content drift'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_main_drift_stops(self):
        self.api.main.return_value = 'e' * 40
        with self.assertRaisesRegex(ValueError, 'main moved'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_conflict_or_unknown_mergeability_waits_without_writes(self):
        for value in (False, None):
            self.pr['mergeable'] = value
            self.assertEqual(self.run_refresh()['status'], 'WAITING_ARCHIVE_MERGEABILITY')
        self.assertFalse(self.writes())

    def test_unexpected_ancestry_stops(self):
        self.comparison['behind_by'] = 0
        with self.assertRaisesRegex(ValueError, 'ancestry'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_ambiguous_history_stops(self):
        self.api.collection.side_effect = None
        self.api.collection.return_value = [{'number': 411}, {'number': 412}]
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            self.run_refresh()
        self.assertFalse(self.writes())

    def test_unverified_main_cannot_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            facade = SimpleNamespace(ROOT=Path(tmp), GitHub=Mock(return_value=self.api))
            self.api.checks_ready.return_value = False
            env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_REF': 'refs/heads/main',
                   'GITHUB_EVENT_NAME': 'workflow_dispatch'}
            with patch.dict(os.environ, env, clear=True), patch.object(r.subprocess, 'check_output', return_value=self.base):
                status = r.attempt_refresh(facade, self.frozen, Path(tmp))
            self.assertEqual(status['status'], 'WAITING_EXACT_MAIN_GATES')
            self.api.collection.assert_not_called()
            self.assertFalse(self.writes())

    def test_pr_event_and_foreign_ref_stop_before_api(self):
        for ref, event in [('refs/pull/411/merge', 'pull_request'), ('refs/heads/main', 'pull_request')]:
            facade = SimpleNamespace(GitHub=Mock())
            env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_REF': ref, 'GITHUB_EVENT_NAME': event}
            with patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
                r.attempt_refresh(facade, self.frozen, Path('.'))
            facade.GitHub.assert_not_called()


if __name__ == '__main__':
    unittest.main()
