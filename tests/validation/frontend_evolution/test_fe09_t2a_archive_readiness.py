#!/usr/bin/env python3
"""Synthetic transport negatives, never scientific artifact evidence."""
import io
from pathlib import Path
import unittest
import urllib.error
from unittest.mock import Mock, patch

import fe09_same_run_artifact_visibility as policy

REPO = 'jiying2007/audio-pipeline'
RUN, ARTIFACT = 123, 456
ATTEMPT = 2
HEAD = "b" * 40
SOURCE = "c" * 40
NAME = policy.T2A_PREFIX + str(RUN) + "-attempt-2"
ENDPOINT = f'{policy.API_URL}/repos/{REPO}/actions/artifacts/{ARTIFACT}/zip'
SECRET = 'https://example.invalid/archive?sig=DO_NOT_LOG'


def response(code=302, location=SECRET, url=ENDPOINT):
    result = Mock(status=code, url=url, headers={'Location': location})
    result.read.side_effect = AssertionError('must not read archive')
    return result


class ReadinessTests(unittest.TestCase):
    def check(self, replies, **kwargs):
        self.opener = Mock(side_effect=replies)
        self.pause = Mock()
        return policy.check_t2a_archive_ready(REPO, RUN, ARTIFACT, NAME, 'fake-token',
                    opener=self.opener, pause=self.pause, run_attempt=ATTEMPT,
                    run_head_sha=HEAD, execution_source=SOURCE, **kwargs)

    def test_404_then_302_has_exact_endpoint_and_no_body_or_redirect_follow(self):
        first, ready = response(404), response()
        self.assertEqual(self.check([first, ready]), 2)
        self.pause.assert_called_once_with(2)
        for call in self.opener.call_args_list:
            self.assertEqual(call.args[0].full_url, ENDPOINT)
            self.assertEqual(call.args[0].get_method(), 'GET')
            self.assertEqual(call.args[0].get_header('Authorization'), 'Bearer fake-token')
            self.assertEqual(call.kwargs, {'timeout': 10})
        for reply in (first, ready):
            reply.read.assert_not_called()
            reply.close.assert_called_once()

    def test_urllib_no_follow_302_http_error_is_closed(self):
        body = io.BytesIO(b'never read')
        error = urllib.error.HTTPError(ENDPOINT, 302, 'Found', {'Location': SECRET}, body)
        self.assertEqual(self.check([error]), 1)
        self.assertTrue(body.closed)
        self.pause.assert_not_called()

    def test_persistent_404_fails_with_exact_bound(self):
        for status in (404, 502, 503):
            with self.subTest(status=status), self.assertRaisesRegex(policy.NotAdmitted, 'NOT_READY'):
                self.check([response(status) for _ in range(8)])
            self.assertEqual(self.opener.call_count, 8)
            self.assertEqual(self.pause.call_count, 7)

    def test_auth_and_unexpected_status_fail_immediately(self):
        for status in (200, 301, 303, 307, 308, 400, 401, 403, 410, 429, 500):
            with self.subTest(status=status), self.assertRaisesRegex(policy.NotAdmitted, 'HARD_FAILURE'):
                self.check([response(status)])
            self.assertEqual(self.opener.call_count, 1)
            self.pause.assert_not_called()

    def test_invalid_redirects_are_redacted_and_rejected(self):
        for location in ('', 'http://example.invalid/?sig=DO_NOT_LOG',
                         'https://user:DO_NOT_LOG@example.invalid/a',
                         'https://example.invalid:444/a', '//example.invalid/a',
                         'https://[invalid/?sig=DO_NOT_LOG', SECRET + '#fragment',
                         SECRET + '\n', 'https://example.invalid/' + 'x' * 16384):
            with self.subTest(location=location):
                with self.assertRaises(policy.NotAdmitted) as caught:
                    self.check([response(location=location)])
                self.assertNotIn('DO_NOT_LOG', str(caught.exception))
                self.assertNotIn('https://', str(caught.exception))
                self.pause.assert_not_called()

    def test_network_errors_and_followed_redirect_fail_without_leaking(self):
        for error in (urllib.error.URLError(SECRET), TimeoutError(SECRET)):
            with self.assertRaisesRegex(policy.NotAdmitted, '^T2A_ARCHIVE_NETWORK_OR_TLS_FAILURE$'):
                self.check([error])
            self.pause.assert_not_called()
        with self.assertRaisesRegex(policy.NotAdmitted, '^T2A_ARCHIVE_REDIRECT_FOLLOWED$'):
            self.check([response(url=SECRET)])

    def test_default_opener_blocks_redirect_and_non_t2a_never_probes(self):
        client = Mock()
        client.open.return_value = response()
        with patch.object(policy.urllib.request, 'build_opener', return_value=client) as build:
            self.assertEqual(policy.check_t2a_archive_ready(REPO, RUN, ARTIFACT, NAME, 'fake', run_attempt=ATTEMPT, run_head_sha=HEAD, execution_source=SOURCE), 1)
        self.assertIsInstance(build.call_args.args[0], policy.NoRedirect)
        for name in (policy.T3S1_PREFIX + str(RUN), NAME + '-attempt-1', NAME + '4',
                     policy.T2F0_PREFIX + str(RUN) + '-attempt-2',
                     policy.T2B0_PREFIX + str(RUN) + '-attempt-2'):
            opener = Mock()
            with self.assertRaises(policy.NotAdmitted):
                policy.check_t2a_archive_ready(REPO, RUN, ARTIFACT, name, 'fake', opener=opener, run_attempt=ATTEMPT, run_head_sha=HEAD, execution_source=SOURCE)
            opener.assert_not_called()

    def test_cli_identity_must_succeed_before_archive_probe(self):
        args = ['visibility', '--artifact-id', str(ARTIFACT), '--run-id', str(RUN),
                '--artifact-name', NAME, '--run-attempt', str(ATTEMPT),
                '--run-head-sha', HEAD, '--execution-source', SOURCE, '--t2a-archive-ready']
        with patch('sys.argv', args), patch.object(policy, 'check_visibility',
                side_effect=policy.NotAdmitted('IDENTITY_FAILURE')), \
                patch.object(policy, 'check_t2a_archive_ready') as probe:
            with self.assertRaisesRegex(SystemExit, 'IDENTITY_FAILURE'):
                policy.main()
        probe.assert_not_called()

    def test_cli_default_skips_probe_and_opt_in_follows_identity(self):
        base = ['visibility', '--artifact-id', str(ARTIFACT), '--run-id', str(RUN),
                '--artifact-name', NAME, '--run-attempt', str(ATTEMPT),
                '--run-head-sha', HEAD, '--execution-source', SOURCE]
        for enabled in (False, True):
            order = []
            def identity(*args, **kwargs):
                order.append('identity')
                return 2, 'sha256:' + 'a' * 64
            def ready(*args, **kwargs):
                order.append('archive')
                return 1
            with patch('sys.argv', base + (['--t2a-archive-ready'] if enabled else [])), \
                 patch('sys.stdout', io.StringIO()), \
                 patch.dict(policy.os.environ, {'GITHUB_REPOSITORY': REPO, 'GH_TOKEN': 'fake'}), \
                 patch.object(policy, 'check_visibility', side_effect=identity), \
                 patch.object(policy, 'check_t2a_archive_ready', side_effect=ready) as probe:
                policy.main()
            self.assertEqual(order, ['identity', 'archive'] if enabled else ['identity'])
            if enabled:
                probe.assert_called_once_with(REPO, RUN, ARTIFACT, NAME, 'fake', run_attempt=ATTEMPT, run_head_sha=HEAD, execution_source=SOURCE)
            else:
                probe.assert_not_called()

    def test_workflow_only_t2a_opt_in_preserves_download_and_rehash(self):
        # The historical probe/HTTP matrices above remain unchanged. Current
        # workflow admission consumes one saved ZIP, then the original reader.
        workflow = (Path(__file__).resolve().parents[3] / ".github/workflows/quality.yml").read_text("utf-8")
        block = workflow.split('  frontend-s3-t2a:\n', 1)[1].split("\n  frontend-", 1)[0]
        markers = (
            'id: fe09_t2a_upload\n',
            'name: frontend-fe09-s3-t2a-controlled-restart-${{ github.run_id }}-attempt-${{ github.run_attempt }}\n',
            'Save and admit the exact T2A original ZIP',
            'id: fe09_t2a_readback\n',
            'GH_TOKEN: ${{ github.token }}',
            'ARTIFACT_ID: ${{ steps.fe09_t2a_upload.outputs.artifact-id }}',
            'RUN_HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}',
            'python3 tests/validation/frontend_evolution/fe09_same_run_artifact_download.py',
            '--stage t2a --repository "$GITHUB_REPOSITORY"',
            '--artifact-id "$ARTIFACT_ID" --run-id "$GITHUB_RUN_ID"',
            '--artifact-name "frontend-fe09-s3-t2a-controlled-restart-$GITHUB_RUN_ID-attempt-$GITHUB_RUN_ATTEMPT"',
            '--run-attempt "$GITHUB_RUN_ATTEMPT" --run-head-sha "$RUN_HEAD_SHA"',
            '--execution-source "$GITHUB_SHA"',
            '--output fe09-t2a-readback --evidence fe09-t2a-transport',
            'path: fe09-t2a-transport/\n',
            '--verify --output fe09-t2a-readback',
            'FE09_S3_T2A_CONTROL_RESTART_READBACK_PASS',
        )

        def check(current):
            cursor = 0
            for required in markers:
                self.assertIn(required, current[cursor:])
                cursor = current.index(required, cursor) + len(required)
            self.assertEqual(current.count("fe09_same_run_artifact_download.py"), 1)
            self.assertNotIn("actions/download-artifact@", current)
            self.assertNotIn("python3 tests/validation/frontend_evolution/fe09_same_run_artifact_visibility.py", current)
            for flag in ("--a1-archive-ready", "--t2a-archive-ready", "--t2f0-archive-ready"):
                self.assertNotIn(flag, current)
            self.assertNotIn("continue-on-error", current)
            self.assertNotIn("overwrite:", current)
            self.assertEqual(current.count("if: steps.fe09_t2a.outcome == 'success'"), 2)
            self.assertIn("if: always() && (steps.fe09_t2a_readback.outcome == 'success' || steps.fe09_t2a_readback.outcome == 'failure')", current)
            self.assertIn('timeout-minutes: 18', current)
            self.assertIn('SHA256SUMS', current)
            self.assertIn('retention-days: 30', current)
            self.assertIn('if-no-files-found: error', current)

        check(block)
        start = block.index("Save and admit the exact ")
        for old, new in (
            ('ARTIFACT_ID: ${{ steps.fe09_t2a_upload.outputs.artifact-id }}', 'ARTIFACT_ID: wrong-upload'),
            ('--run-attempt "$GITHUB_RUN_ATTEMPT"', '--run-attempt "1"'),
            ('--execution-source "$GITHUB_SHA"', '--execution-source "wrong-source"'),
            ('fe09_same_run_artifact_download.py', 'fe09_same_run_artifact_download.py fe09_same_run_artifact_download.py'),
            ('--verify --output fe09-t2a-readback', '--verify --output wrong-reader'),
            ('--stage t2a --repository', '--a1-archive-ready --stage t2a --repository'),
            ('id: fe09_t2a_readback\n', 'id: fe09_t2a_readback\n        continue-on-error: true\n'),
        ):
            with self.subTest(mutation=old), self.assertRaises(AssertionError):
                check(block[:start] + block[start:].replace(old, new, 1))

    def test_bad_attempt_or_source_never_probes(self):
        for changes in ({'run_attempt': 1}, {'run_attempt': True}, {'run_attempt': None},
                        {'run_head_sha': 'd' * 39}, {'execution_source': None}):
            args = dict(run_attempt=ATTEMPT, run_head_sha=HEAD, execution_source=SOURCE)
            args.update(changes)
            opener = Mock()
            with self.assertRaises(policy.NotAdmitted):
                policy.check_t2a_archive_ready(REPO, RUN, ARTIFACT, NAME, 'fake', opener=opener, **args)
            opener.assert_not_called()

    def test_conflicting_flags_never_call_identity(self):
        for other in ('--a1-archive-ready', '--t2f0-archive-ready'):
            argv = ['visibility', '--artifact-id', str(ARTIFACT), '--run-id', str(RUN),
                    '--artifact-name', NAME, '--run-attempt', str(ATTEMPT),
                    other, '--t2a-archive-ready']
            with patch('sys.argv', argv), patch.object(policy, 'check_visibility') as identity:
                with self.assertRaisesRegex(SystemExit, 'FLAGS_CONFLICT'):
                    policy.main()
            identity.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
