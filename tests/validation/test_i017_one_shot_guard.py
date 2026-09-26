#!/usr/bin/env python3
"""Exercise the active I017 one-shot guard without running research or fresh audio."""

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
    ".github/workflows/research-i017-vad-state-persistence-decomposition-v1.yml"
)
GENERATE = "Generate preregistered fresh I017 partitions"
DIAGNOSE = "Run fresh I017 VAD state-persistence decomposition"
CURRENT = {"id": 20, "run_attempt": 1}
PRIOR = {"id": 10, "run_attempt": 1}


def guard_source() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    block = text.split(
        "      - name: Enforce one-shot I017 diagnostic execution\n", 1
    )[1]
    block = block.split("      - name: Bind exact shipping source\n", 1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    )


def step(name=DIAGNOSE, conclusion="success", status="completed"):
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
            "GITHUB_RUN_ATTEMPT": attempt,
            "GITHUB_REF": "refs/heads/main",
        }

        def api(args, **kwargs):
            if api_error:
                raise subprocess.CalledProcessError(1, args)
            endpoint = args[-1]
            if "/workflows/" in endpoint:
                pages = runs
            else:
                match = re.search(r"/runs/(\d+)/attempts/(\d+)/jobs\?", endpoint)
                self.assertIsNotNone(match, endpoint)
                pages = jobs.get((int(match.group(1)), int(match.group(2))), [{"jobs": []}])
            return json.dumps(pages if "--slurp" in args else pages[0])

        with (
            patch.dict(os.environ, env, clear=True),
            patch("subprocess.check_output", side_effect=api),
            redirect_stdout(io.StringIO()),
        ):
            exec(compile(guard_source(), str(WORKFLOW), "exec"), {})

    def history(self, steps, attempts=1):
        return {
            "runs": [{"workflow_runs": [CURRENT, dict(PRIOR, run_attempt=attempts)]}],
            "jobs": {(10, 1): [{"jobs": [{"steps": steps}]}]},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_rerun_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt="2")

    def test_prior_generation_blocks(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(GENERATE)]))

    def test_prior_diagnosis_blocks(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([step(DIAGNOSE)]))

    def test_failed_or_cancelled_fresh_step_blocks(self):
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion), self.assertRaises(SystemExit):
                self.execute(**self.history([step(GENERATE, conclusion)]))

    def test_pre_fresh_failure_allows_new_dispatch(self):
        self.execute(**self.history([
            step("Build exact source and diagnostic probe", "failure"),
            step(GENERATE, "skipped"),
            step(DIAGNOSE, "skipped"),
        ]))

    def test_skipped_fresh_steps_do_not_consume(self):
        self.execute(**self.history([step(GENERATE, "skipped"), step(DIAGNOSE, "skipped")]))

    def test_later_run_page_cannot_hide_consumption(self):
        data = self.history([step(GENERATE)])
        data["runs"] = [{"workflow_runs": [CURRENT]}, {"workflow_runs": [PRIOR]}]
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_later_job_page_cannot_hide_consumption(self):
        data = self.history([step(DIAGNOSE)])
        data["jobs"] = {(10, 1): [{"jobs": []}, {"jobs": [{"steps": [step(DIAGNOSE)]}]}]}
        with self.assertRaises(SystemExit):
            self.execute(**data)

    def test_missing_current_run_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{"workflow_runs": []}])

    def test_invalid_attempt_count_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(**self.history([], attempts=0))

    def test_api_failure_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_guard_precedes_fresh_steps(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        guard = text.index("      - name: Enforce one-shot I017 diagnostic execution\n")
        self.assertLess(guard, text.index(f"      - name: {GENERATE}\n"))
        self.assertLess(guard, text.index(f"      - name: {DIAGNOSE}\n"))
        self.assertIn("if: github.event_name == 'workflow_dispatch'", text)


if __name__ == "__main__":
    unittest.main()
