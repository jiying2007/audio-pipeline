#!/usr/bin/env python3
"""Exercise I028 one-shot authority and temporal-readiness boundaries."""

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
WORKFLOW=ROOT/".github/workflows/research-i028-ns-upstream-reference-readiness-temporal-decomposition-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i028-ns-upstream-reference-readiness-temporal-decomposition-v1.json"
EVALUATOR=ROOT/"tests/validation/i028_ns_upstream_reference_readiness_temporal_decomposition.py"
MATERIALIZE="Materialize fresh public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero reference-readiness temporal decomposition"
CURRENT={"id":28,"run_attempt":1}
PRIOR={"id":18,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I028 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen temporal-readiness inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I028GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"28",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i028-ns-upstream-reference-readiness-temporal-decomposition-v1.yml",
        }

        def api(args,**kwargs):
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

    def history(self,steps,attempts=1):
        return {
            "runs":[{"workflow_runs":[CURRENT,dict(PRIOR,run_attempt=attempts)]}],
            "jobs":{(18,1):[{"jobs":[{"steps":steps}]}]},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_rerun_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt="2")

    def test_consuming_steps_are_one_shot_even_on_failure(self):
        for name in (MATERIALIZE,EVALUATE):
            for conclusion in ("success","failure","cancelled"):
                with self.subTest(name=name,conclusion=conclusion),self.assertRaises(SystemExit):
                    self.execute(**self.history([step(name,conclusion)]))

    def test_pre_materialization_failure_does_not_consume(self):
        self.execute(**self.history([
            step("Build frozen I025 dual-mirror probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(18,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
        with self.assertRaises(SystemExit):
            self.execute(runs=runs,jobs=jobs)

    def test_missing_current_or_api_failure_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.execute(runs=[{"workflow_runs":[]}])
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(api_error=True)

    def test_workflow_is_manual_only_and_guard_precedes_consumption(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertNotIn("\n  push:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn("if: github.event_name == 'workflow_dispatch'",text)
        guard="      - name: Enforce one-shot I028 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_is_fixed_temporal_diagnostic_only(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(c["authority"],"CANDIDATE_ZERO_DIAGNOSTIC_ONLY")
        self.assertEqual(c["readiness_boundary"]["prior_reference_frames"],8)
        self.assertTrue(c["readiness_boundary"]["fixed_observation_boundary"])
        self.assertFalse(c["readiness_boundary"]["alternative_thresholds_evaluated"])
        self.assertFalse(c["readiness_boundary"]["threshold_selection"])
        self.assertFalse(c["diagnostic_readout"]["component_counterfactual"])
        self.assertFalse(c["diagnostic_readout"]["component_mapping_selection"])
        self.assertFalse(c["diagnostic_readout"]["threshold_search"])
        self.assertFalse(c["diagnostic_readout"]["candidate_selection"])
        self.assertTrue(c["diagnostic_readout"]["target_prior_reference_count"])
        self.assertTrue(c["diagnostic_readout"]["target_frame_index_from_warmup"])
        self.assertTrue(c["diagnostic_readout"]["target_frames_until_first_ready"])
        self.assertTrue(c["diagnostic_readout"]["reference_interarrival_summary"])
        self.assertTrue(c["diagnostic_gates"]["all_raw_targets_represented_exactly_once"])
        self.assertEqual(c["fresh_diagnostic_authority"]["candidate_limit"],0)
        self.assertEqual(c["fresh_diagnostic_authority"]["confirmation_limit"],0)
        self.assertTrue(all(value is False for value in c["authority_boundary"].values()))

    def test_evaluator_records_every_target_without_component_counterfactual(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        for token in (
            '"target_receipts":target_receipts',
            '"frame_index_from_warmup":frame_index',
            '"prior_reference_count":prior_reference_count',
            '"ready_at_target":prior_reference_count>=REFERENCE_READY_COUNT',
            '"frames_until_ready"',
            '"median_reference_interarrival_frames"',
            '"all_raw_targets_represented_exactly_once"',
            '"future_readiness_timestamp_retrospective_diagnostic_only":True',
        ):
            self.assertIn(token,text)
        for forbidden in (
            "mean_cf",
            "concentration_cf",
            "noise_rescue_fraction",
            "speech_preservation_fraction",
        ):
            self.assertNotIn(forbidden,text)

    def test_dispatch_binds_i027_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i027_closure_blob_sha",
            "dataset_lock_git_blob_sha",
            "builder_git_blob_sha",
            "probe_git_blob_sha",
            "evaluator_git_blob_sha",
        ):
            self.assertIn(token,text)
        self.assertNotIn("i026_closure_blob_sha",text)
        for path in (
            "src/enhance/ap_noise_tracker.c",
            "src/enhance/ap_noise_tracker.h",
            "src/enhance/ap_ns.c",
            "src/enhance/ap_vad.c",
        ):
            self.assertIn(path,text)
        self.assertIn('git diff --exit-code "$SOURCE_BASE"...HEAD --',text)


if __name__=="__main__":
    unittest.main()
