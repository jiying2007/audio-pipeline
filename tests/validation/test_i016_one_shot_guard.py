#!/usr/bin/env python3
"""Exercise the active I016 one-shot guard without running research or fresh audio."""

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


WORKFLOW = Path(__file__).resolve().parents[2] / (
    ".github/workflows/research-i016-vad-local-evidence-gated-blend-v1.yml"
)
GENERATE = "Generate preregistered fresh development partitions"
EVALUATE = "Evaluate the single gated-blend candidate"
CURRENT = {"id": 20, "run_attempt": 1}
PRIOR = {"id": 10, "run_attempt": 1}


def guard_source() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split(
        "      - name: Enforce single I016 development execution\n", 1
    )[1]
    block = block.split("      - name: Bind exact shipping source\n", 1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    )


def step(name=EVALUATE, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion}


class GuardTests(unittest.TestCase):
    def execute(self, *, runs=None, jobs=None, attempt="1", api_error=False):
        if runs is None:
            runs = [{"workflow_runs": [CURRENT]}]
        if jobs is None:
            jobs = {}
        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "20",
            "GITHUB_REF": "refs/heads/main",
        }
        if attempt is not None:
            env["GITHUB_RUN_ATTEMPT"] = attempt

        def api(args, **kwargs):
            if api_error:
                raise subprocess.CalledProcessError(1, args)
            endpoint = args[-1]
            if "/workflows/" in endpoint:
                pages = runs
            else:
                match = re.search(r"/runs/(\d+)/attempts/(\d+)/jobs\?", endpoint)
                self.assertIsNotNone(match, endpoint)
                run_id = int(match.group(1))
                attempt_id = int(match.group(2))
                pages = jobs.get((run_id, attempt_id), [{"jobs": []}])
            return json.dumps(pages if "--slurp" in args else pages[0])

        with (
            patch.dict(os.environ, env, clear=True),
            patch("subprocess.check_output", side_effect=api),
            redirect_stdout(io.StringIO()),
        ):
            exec(compile(guard_source(), str(WORKFLOW), "exec"), {})

    def history(self, steps, *, attempt_count=1):
        pages = [{"jobs": [{"steps": steps}]}]
        return {
            "runs": [
                {
                    "workflow_runs": [
                        CURRENT,
                        dict(PRIOR, run_attempt=attempt_count),
                    ]
                }
            ],
            "jobs": {(10, 1): pages},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_current_run_rerun_blocked_before_api(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt="2", api_error=True)

    def test_missing_attempt_fails_closed(self):
        with self.assertRaises((KeyError, SystemExit)):
            self.execute(attempt=None)

    def test_prior_successful_generation_blocks(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(GENERATE), step(EVALUATE)]))

    def test_prior_failed_or_cancelled_generation_blocks(self):
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion), self.assertRaises(SystemExit):
                self.execute(**self.history([step(GENERATE, conclusion)]))

    def test_prior_running_generation_blocks(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(GENERATE, None, "in_progress")]))

    def test_evaluation_without_visible_generation_still_blocks(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(EVALUATE)]))

    def test_pre_fresh_guard_failure_allows_new_dispatch(self):
        self.execute(**self.history([
            step("Enforce single I016 development execution", "failure"),
            step(GENERATE, "skipped"),
            step(EVALUATE, "skipped"),
        ]))

    def test_pre_fresh_build_failure_allows_new_dispatch(self):
        self.execute(**self.history([
            step("Build exact source and causal probe", "failure"),
            step(GENERATE, "skipped"),
            step(EVALUATE, "skipped"),
        ]))

    def test_skipped_fresh_steps_do_not_consume(self):
        self.execute(**self.history([
            step(GENERATE, "skipped"),
            step(EVALUATE, "skipped"),
        ]))

    def test_later_run_page_cannot_hide_consumption(self):
        data = self.history([step(GENERATE)])
        data["runs"] = [
            {"workflow_runs": [CURRENT]},
            {"workflow_runs": [PRIOR]},
        ]
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_later_job_page_cannot_hide_consumption(self):
        data = self.history([step(EVALUATE)])
        data["jobs"] = {
            (10, 1): [
                {"jobs": []},
                {"jobs": [{"steps": [step(EVALUATE)]}]},
            ]
        }
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_earlier_attempt_cannot_be_hidden(self):
        data = self.history([step(GENERATE)], attempt_count=2)
        data["jobs"] = {
            (10, 1): [{"jobs": [{"steps": [step(GENERATE)]}]}],
            (10, 2): [{"jobs": [{"steps": [step(GENERATE, "skipped")]}]}],
        }
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_missing_current_run_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{"workflow_runs": []}])

    def test_invalid_historical_attempt_count_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([], attempt_count=0))

    def test_api_failure_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_guard_precedes_fresh_steps(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        guard = text.index("      - name: Enforce single I016 development execution\n")
        for name in (GENERATE, EVALUATE):
            self.assertLess(guard, text.index(f"      - name: {name}\n"))
        self.assertIn("if: github.event_name == 'workflow_dispatch'", text)
        self.assertIn("test \"$GITHUB_REF\" = refs/heads/main", text)


if __name__ == "__main__":
    unittest.main()
