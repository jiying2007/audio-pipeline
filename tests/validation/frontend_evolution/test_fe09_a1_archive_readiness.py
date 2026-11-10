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
NAME = policy.A1_PREFIX + str(RUN)
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
        return policy.check_a1_archive_ready(REPO, RUN, ARTIFACT, NAME, 'fake-token',
                    opener=self.opener, pause=self.pause, **kwargs)

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
            with self.assertRaisesRegex(policy.NotAdmitted, '^A1_ARCHIVE_NETWORK_OR_TLS_FAILURE$'):
                self.check([error])
            self.pause.assert_not_called()
        with self.assertRaisesRegex(policy.NotAdmitted, '^A1_ARCHIVE_REDIRECT_FOLLOWED$'):
            self.check([response(url=SECRET)])

    def test_default_opener_blocks_redirect_and_non_a1_never_probes(self):
        client = Mock()
        client.open.return_value = response()
        with patch.object(policy.urllib.request, 'build_opener', return_value=client) as build:
            self.assertEqual(policy.check_a1_archive_ready(REPO, RUN, ARTIFACT, NAME, 'fake'), 1)
        self.assertIsInstance(build.call_args.args[0], policy.NoRedirect)
        for name in (policy.T3S1_PREFIX + str(RUN), NAME + '-attempt-1', NAME + '4'):
            opener = Mock()
            with self.assertRaises(policy.NotAdmitted):
                policy.check_a1_archive_ready(REPO, RUN, ARTIFACT, name, 'fake', opener=opener)
            opener.assert_not_called()

    def test_cli_identity_must_succeed_before_archive_probe(self):
        args = ['visibility', '--artifact-id', str(ARTIFACT), '--run-id', str(RUN),
                '--artifact-name', NAME, '--a1-archive-ready']
        with patch('sys.argv', args), patch.object(policy, 'check_visibility',
                side_effect=policy.NotAdmitted('IDENTITY_FAILURE')), \
                patch.object(policy, 'check_a1_archive_ready') as probe:
            with self.assertRaisesRegex(SystemExit, 'IDENTITY_FAILURE'):
                policy.main()
        probe.assert_not_called()

    def test_cli_default_skips_probe_and_opt_in_follows_identity(self):
        base = ['visibility', '--artifact-id', str(ARTIFACT), '--run-id', str(RUN),
                '--artifact-name', NAME]
        for enabled in (False, True):
            order = []
            def identity(*args, **kwargs):
                order.append('identity')
                return 2, 'sha256:' + 'a' * 64
            def ready(*args, **kwargs):
                order.append('archive')
                return 1
            with patch('sys.argv', base + (['--a1-archive-ready'] if enabled else [])), \
                 patch('sys.stdout', io.StringIO()), \
                 patch.dict(policy.os.environ, {'GITHUB_REPOSITORY': REPO, 'GH_TOKEN': 'fake'}), \
                 patch.object(policy, 'check_visibility', side_effect=identity), \
                 patch.object(policy, 'check_a1_archive_ready', side_effect=ready) as probe:
                policy.main()
            self.assertEqual(order, ['identity', 'archive'] if enabled else ['identity'])
            if enabled:
                probe.assert_called_once_with(REPO, RUN, ARTIFACT, NAME, 'fake')
            else:
                probe.assert_not_called()

    def test_workflow_opt_in_only_a1_and_downloader_remains(self):
        workflow = (Path(__file__).resolve().parents[3] / '.github/workflows/quality.yml').read_text()
        self.assertEqual(workflow.count('--a1-archive-ready'), 1)
        stage = workflow.split('  frontend-s3-t3s2b1ba1:\n')[1].split('\n  frontend-s3-t3s2b1ba2:')[0]
        self.assertLess(stage.index('--a1-archive-ready'), stage.index('uses: actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131'))
        for required in ('timeout-minutes: 30', '--negative-readback',
                         'FE09_A1_SAME_RUN_ORIGINAL_MEMBERS_INDEPENDENT_READBACK_PASS'):
            self.assertIn(required, stage)
        self.assertNotIn('continue-on-error:', stage)


if __name__ == '__main__':
    unittest.main(verbosity=2)
