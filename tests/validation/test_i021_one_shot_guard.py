#!/usr/bin/env python3
"""Exercise the active I021 one-shot guard without consuming research data."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import subprocess
import textwrap
import unittest
from unittest.mock import patch

WORKFLOW=Path(__file__).resolve().parents[2]/".github/workflows/research-i021-vad-public-development-transfer-gap-v1.yml"
MATERIALIZE="Materialize fresh public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero public-development VAD transfer gap"
CURRENT={"id":21,"run_attempt":1}
PRIOR={"id":11,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I021 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind exact shipping source and trusted diagnostic infrastructure\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE, conclusion="success", status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class GuardTests(unittest.TestCase):
    def execute(self, *, runs=None, jobs=None, attempt="1", api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"21",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i021-vad-public-development-transfer-gap-v1.yml",
        }

        def api(args, **kwargs):
            if api_error:
                raise subprocess.CalledProcessError(1,args)
            endpoint=args[-1]
            if "/workflows/" in endpoint:
                pages=runs
            else:
                match=re.search(r"/runs/(\d+)/attempts/(\d+)/jobs\?",endpoint)
                self.assertIsNotNone(match,endpoint)
                pages=jobs.get(
                    (int(match.group(1)),int(match.group(2))),
                    [{"jobs":[]}],
                )
            return json.dumps(pages if "--slurp" in args else pages[0])

        with (
            patch.dict(os.environ,env,clear=True),
            patch("subprocess.check_output",side_effect=api),
            redirect_stdout(io.StringIO()),
        ):
            exec(compile(guard_source(),str(WORKFLOW),"exec"),{})

    def history(self, steps, attempts=1):
        return {
            "runs":[{"workflow_runs":[CURRENT,dict(PRIOR,run_attempt=attempts)]}],
            "jobs":{(11,1):[{"jobs":[{"steps":steps}]}]},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_rerun_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt="2")

    def test_prior_materialization_consumes_authority(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(MATERIALIZE)]))

    def test_prior_evaluation_consumes_authority(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(EVALUATE)]))

    def test_failed_or_cancelled_fresh_step_still_consumes(self):
        for conclusion in ("failure","cancelled"):
            with self.subTest(conclusion=conclusion),self.assertRaises(SystemExit):
                self.execute(**self.history([step(MATERIALIZE,conclusion)]))

    def test_pre_fresh_failure_allows_new_dispatch(self):
        self.execute(**self.history([
            step("Build exact shipping source and I021 probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_skipped_fresh_steps_do_not_consume(self):
        self.execute(**self.history([
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(11,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
        with self.assertRaises(SystemExit):
            self.execute(runs=runs,jobs=jobs)

    def test_missing_current_run_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{"workflow_runs":[]}])

    def test_invalid_prior_attempt_count_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([],attempts=0))

    def test_api_failure_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_seed_freshness_guard_uses_numeric_token_boundaries(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "pattern=rf'(^|[^0-9]){seed}([^0-9]|$)'",
            text,
        )
        self.assertIn(
            "assert result.returncode in (0,1), 'git grep freshness check failed'",
            text,
        )
        self.assertNotIn(
            "['git','grep','-n',str(seed),'--'",
            text,
        )

    def test_guard_precedes_fresh_steps_and_execution_is_manual_only(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        guard=text.index("      - name: Enforce one-shot I021 diagnostic execution\n")
        self.assertLess(guard,text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(guard,text.index(f"      - name: {EVALUATE}\n"))
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertNotIn("\n  push:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'",text)
        self.assertIn(
            'DIAGNOSTIC_BASE: aae3affeca0c5e2e4b00dc7350128d29284775ac',
            text,
        )
        self.assertIn(
            'test "$(git rev-parse HEAD^1)" = "$DIAGNOSTIC_BASE"',
            text,
        )


if __name__=="__main__":
    unittest.main()
