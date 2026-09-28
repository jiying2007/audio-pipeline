#!/usr/bin/env python3
"""Exercise I024 one-shot authority and frozen feature-separability boundaries."""

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

ROOT=Path(__file__).resolve().parents[2]
WORKFLOW=ROOT/".github/workflows/research-i024-vad-disagreement-feature-separability-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i024-vad-disagreement-feature-separability-v1.json"
MATERIALIZE="Materialize fresh public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero feature separability"
CURRENT={"id":24,"run_attempt":1}
PRIOR={"id":14,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I024 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen diagnostic inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE, conclusion="success", status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I024GuardTests(unittest.TestCase):
    def execute(self, *, runs=None, jobs=None, attempt="1", api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"24",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i024-vad-disagreement-feature-separability-v1.yml",
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
            "jobs":{(14,1):[{"jobs":[{"steps":steps}]}]},
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

    def test_failed_or_cancelled_consuming_step_still_consumes(self):
        for conclusion in ("failure","cancelled"):
            with self.subTest(conclusion=conclusion),self.assertRaises(SystemExit):
                self.execute(**self.history([step(MATERIALIZE,conclusion)]))

    def test_pre_materialization_failure_does_not_consume(self):
        self.execute(**self.history([
            step("Build frozen shared shipping-mirror probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(14,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
        with self.assertRaises(SystemExit):
            self.execute(runs=runs,jobs=jobs)

    def test_missing_current_run_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{"workflow_runs":[]}])

    def test_api_failure_fails_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_workflow_is_manual_only_and_contract_owned(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertNotIn("\n  push:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'",text)
        self.assertLess(
            text.index("      - name: Enforce one-shot I024 diagnostic execution\n"),
            text.index(f"      - name: {MATERIALIZE}\n"),
        )
        self.assertLess(
            text.index("      - name: Enforce one-shot I024 diagnostic execution\n"),
            text.index(f"      - name: {EVALUATE}\n"),
        )
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_has_zero_selection_authority(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        seeds=c["fresh_diagnostic_authority"]["seeds"]
        self.assertEqual(len(seeds),3)
        self.assertEqual(len(set(seeds)),3)
        self.assertTrue(all(type(seed) is int and seed > 0 for seed in seeds))
        self.assertEqual(c["fresh_diagnostic_authority"]["candidate_limit"],0)
        self.assertEqual(c["fresh_diagnostic_authority"]["confirmation_limit"],0)
        self.assertFalse(c["separability_statistics"]["model_fitting"])
        self.assertFalse(c["separability_statistics"]["feature_selection"])
        self.assertFalse(c["separability_statistics"]["threshold_search"])
        self.assertFalse(c["feature_registry"]["temporal_context"]["future_frames_used"])
        self.assertTrue(all(value is False for value in c["authority_boundary"].values()))

    def test_feature_registry_is_closed(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            set(c["feature_registry"]["numeric_features"]),
            {
                "upstream_margin","ratio_db","crest_db","raw_probability",
                "pre_blend_probability","shipping_probability","pre_hangover",
                "upstream_margin_mean3","upstream_margin_min3","ratio_db_mean3",
                "pre_blend_probability_mean3","disagreement_run_length",
            },
        )
        self.assertEqual(
            c["feature_registry"]["categorical_features"],
            ["noise_update_kind"],
        )
        self.assertEqual(c["feature_registry"]["temporal_context"]["window_frames"],3)

    def test_dispatch_binds_git_blobs_and_shipping_source(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("dataset_lock_git_blob_sha",text)
        self.assertIn("builder_git_blob_sha",text)
        self.assertIn("probe_git_blob_sha",text)
        self.assertIn("evaluator_git_blob_sha",text)
        self.assertIn('git diff --exit-code "$SOURCE_BASE"...HEAD --',text)
        self.assertNotIn('git rev-parse HEAD^1',text)


if __name__=="__main__":
    unittest.main()
