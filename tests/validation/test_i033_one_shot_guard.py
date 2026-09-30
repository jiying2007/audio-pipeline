#!/usr/bin/env python3
"""Exercise I033 one-shot authority and causal delta boundaries."""

from contextlib import redirect_stdout
import ast
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
WORKFLOW=ROOT/".github/workflows/research-i033-ns-vad-causal-noise-delta-alignment-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i033-ns-vad-causal-noise-delta-alignment-v1.json"
EVALUATOR=ROOT/"tests/validation/i033_ns_vad_causal_noise_delta_alignment.py"
PROBE=ROOT/"tests/validation/i033_ns_vad_causal_noise_delta_probe.c"
MATERIALIZE="Materialize fresh I033 target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero NS/VAD causal noise-delta alignment"
CURRENT={"id":33,"run_attempt":1}
PRIOR={"id":23,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I033 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I033 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I033GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"33",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i033-ns-vad-causal-noise-delta-alignment-v1.yml",
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
            "jobs":{(23,1):[{"jobs":[{"steps":steps}]}]},
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
            step("Build I033 causal noise-delta probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(23,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I033 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["target_seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_is_target_only_and_zero_candidate_authority(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        a=c["fresh_diagnostic_authority"]
        self.assertEqual(len(a["target_seeds"]),6)
        self.assertEqual(len(set(a["target_seeds"])),6)
        self.assertNotIn("donor_seeds",a)
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)

        anchor=c["causal_anchor_semantics"]
        self.assertTrue(anchor["require_at_least_one_prior_reference"])
        self.assertTrue(anchor["anchor_and_target_are_causal"])
        self.assertTrue(anchor["same_anchor_for_ns_and_local_deltas"])
        self.assertFalse(anchor["may_use_future_frames_for_anchor_or_target"])

        benchmark=c["retrospective_benchmark_semantics"]
        self.assertTrue(benchmark["strictly_post_target"])
        self.assertEqual(benchmark["reference_frames"],8)

        h=c["delta_alignment_hypothesis"]
        self.assertEqual(h["maximum_median_absolute_delta_error_db"],3.0)
        self.assertEqual(h["maximum_p90_absolute_delta_error_db"],6.0)
        self.assertEqual(h["percentile_definition"],"nearest-rank")
        self.assertTrue(all(
            value is False for value in c["authority_boundary"].values()
        ))

    def test_probe_adds_only_diagnostic_local_observation_measure(self):
        text=PROBE.read_text(encoding="utf-8")
        for token in (
            "ap_ns_process(&ns_state",
            "(double)ns_result.noise_rms_dbfs",
            "frame_rms_dbfs(ns_output, FRAME)",
            "post_ns_rms_dbfs",
            "ap_module_vad_process(public_shipping_module, ns_output",
        ):
            self.assertIn(token,text)
        self.assertNotIn("normalize_gap",text)
        self.assertNotIn("apply_noise_scale_normalization",text)

    def test_evaluator_enforces_causal_anchor_target_and_future_benchmark(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        tree=ast.parse(text)
        analyze=ast.get_source_segment(
            text,
            next(
                n for n in tree.body
                if isinstance(n,ast.FunctionDef) and n.name=="analyze_case"
            ),
        )
        self.assertIsNotNone(analyze)
        for token in (
            "len(prior_references)<REFERENCE_COUNT",
            "anchor=prior_references[-1]",
            'local_index>first_pre_ready_target["local_frame_index"]',
            "len(later_references)<REFERENCE_COUNT",
            '"ns_noise_rms_dbfs"',
            '"post_ns_rms_dbfs"',
        ):
            self.assertIn(token,analyze)

        evaluate=ast.get_source_segment(
            text,
            next(
                n for n in tree.body
                if isinstance(n,ast.FunctionDef) and n.name=="evaluate"
            ),
        )
        self.assertIsNotNone(evaluate)
        for token in (
            'float(target["ns_noise_rms_dbfs"])',
            'float(anchor["ns_noise_rms_dbfs"])',
            'float(later["post_ns_rms_dbfs"])',
            'float(anchor["post_ns_rms_dbfs"])',
            '"delta_abs_error_db":abs(ns_delta-local_delta)',
        ):
            self.assertIn(token,evaluate)

    def test_no_donor_mapping_threshold_or_source_candidate_implementation(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        for forbidden in (
            "select_donors",
            "compatibility_score",
            "donor_by_domain",
            "joint_coherent_aggregate",
            "normalize_gap",
            "apply_noise_scale_normalization",
            "mapping_candidates",
            "threshold_candidates",
            "def source_candidate",
            "mean_cf",
            "concentration_cf",
        ):
            self.assertNotIn(forbidden,text)

    def test_dispatch_binds_i032_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i032_closure_blob_sha",
            "dataset_lock_git_blob_sha",
            "builder_git_blob_sha",
            "probe_git_blob_sha",
            "evaluator_git_blob_sha",
        ):
            self.assertIn(token,text)
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
