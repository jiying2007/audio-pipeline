#!/usr/bin/env python3
"""Exercise the frozen historical I015 guard; never run research or fresh audio."""

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import textwrap
import unittest
from unittest.mock import patch


# Consumed workflow blob from 72db70f76a9ef2fffb767709d9aa289814207bae.
# This data fixture is outside the active workflow directory.
WORKFLOW = Path(__file__).resolve().parent / 'data/i015-consumed-workflow.yml'
HISTORY_BLOB = '1bf5717bf4bb02f3847606a6d7cba7c61bde70f1'
GENERATE = 'Generate preregistered fresh I015 partitions'
DIAGNOSE = 'Run fresh I015 VAD upstream consumption decomposition'
CURRENT = {'id': 20, 'run_attempt': 1}
PRIOR = {'id': 10, 'run_attempt': 1}


def guard_source():
    data = WORKFLOW.read_bytes()
    if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != HISTORY_BLOB:
        raise ValueError('historical I015 workflow fixture drift')
    text = data.decode('utf-8')
    block = text.split('      - name: Enforce one-shot I015 diagnostic execution\n', 1)[1]
    block = block.split('      - name: Bind exact frozen source\n', 1)[0]
    return textwrap.dedent(block.split("python3 - <<'PY'\n", 1)[1]
                          .split('\n          PY', 1)[0])


def step(name=DIAGNOSE, conclusion='success', status='completed'):
    return {'name': name, 'status': status, 'conclusion': conclusion}


class GuardTests(unittest.TestCase):
    def execute(self, *, runs=None, jobs=None, attempt='1', api_error=False):
        if runs is None:
            runs = [{'workflow_runs': [CURRENT]}]
        if jobs is None:
            jobs = {}
        env = {'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_RUN_ID': '20'}
        if attempt is not None:
            env['GITHUB_RUN_ATTEMPT'] = attempt

        def api(args, **kwargs):
            if api_error:
                raise subprocess.CalledProcessError(1, args)
            endpoint = args[-1]
            if '/workflows/' in endpoint:
                pages = runs
            else:
                match = re.search(r'/runs/(\d+)/(?:attempts/(\d+)/)?jobs\?', endpoint)
                self.assertIsNotNone(match, endpoint)
                run_id = int(match.group(1))
                attempt_id = int(match.group(2) or 0)
                pages = jobs.get((run_id, attempt_id), [{'jobs': []}])
            return json.dumps(pages if '--slurp' in args else pages[0])

        with patch.dict(os.environ, env, clear=True), \
                patch('subprocess.check_output', side_effect=api), \
                redirect_stdout(io.StringIO()):
            exec(compile(guard_source(), str(WORKFLOW), 'exec'), {})

    def history(self, steps, *, attempt_count=1):
        pages = [{'jobs': [{'steps': steps}]}]
        return {
            'runs': [{'workflow_runs': [CURRENT, dict(PRIOR, run_attempt=attempt_count)]}],
            'jobs': {(10, 0): pages, (10, 1): pages},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_current_run_rerun_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt='2', api_error=True)

    def test_missing_attempt_fails_closed(self):
        with self.assertRaises((KeyError, SystemExit)):
            self.execute(attempt=None)

    def test_prior_success_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step()]))

    def test_prior_unsuccessful_or_running_diagnosis_blocked(self):
        for conclusion, status in [('failure', 'completed'), ('cancelled', 'completed'),
                                   (None, 'in_progress')]:
            with self.subTest(conclusion=conclusion), self.assertRaises(SystemExit):
                self.execute(**self.history([step(conclusion=conclusion, status=status)]))

    def test_generation_without_diagnosis_blocks(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(GENERATE), step(conclusion='skipped')]))

    def test_unsuccessful_generation_blocks(self):
        for conclusion in ['failure', 'cancelled']:
            with self.subTest(conclusion=conclusion), self.assertRaises(SystemExit):
                self.execute(**self.history([step(GENERATE, conclusion)]))

    def test_pre_fresh_infrastructure_failure_can_use_new_dispatch(self):
        self.execute(**self.history([step('Build exact source library and I015 probe',
                                         'failure')]))

    def test_skipped_fresh_steps_do_not_consume_authority(self):
        self.execute(**self.history([step(GENERATE, 'skipped'), step(conclusion='skipped')]))

    def test_earlier_attempt_cannot_be_hidden_by_latest_attempt(self):
        data = self.history([step()], attempt_count=2)
        skipped = [{'jobs': [{'steps': [step(conclusion='skipped')]}]}]
        data['jobs'][(10, 0)] = skipped
        data['jobs'][(10, 2)] = skipped
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_later_run_page_cannot_hide_consumption(self):
        data = self.history([step()])
        data['runs'] = [{'workflow_runs': [CURRENT]}, {'workflow_runs': [PRIOR]}]
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_later_job_page_cannot_hide_consumption(self):
        data = self.history([step()])
        pages = [{'jobs': []}, {'jobs': [{'steps': [step()]}]}]
        data['jobs'] = {(10, 0): pages, (10, 1): pages}
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_missing_current_run_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{'workflow_runs': []}])

    def test_missing_run_collection_fails_closed(self):
        with self.assertRaises((KeyError, SystemExit)):
            self.execute(runs=[{}])

    def test_missing_job_collection_fails_closed(self):
        data = self.history([])
        data['jobs'] = {(10, 0): [{}], (10, 1): [{}]}
        with self.assertRaises((KeyError, SystemExit)):
            self.execute(**data)

    def test_invalid_historical_attempt_count_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([], attempt_count=0))

    def test_api_failure_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_guard_precedes_all_fresh_steps(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        guard = text.index('      - name: Enforce one-shot I015 diagnostic execution\n')
        for name in (GENERATE, DIAGNOSE):
            self.assertLess(guard, text.index(f'      - name: {name}\n'))
        self.assertIn("if: github.event_name == 'workflow_dispatch'", text)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', text)


if __name__ == '__main__':
    unittest.main()
