#!/usr/bin/env python3
"""Exercise I029 one-shot authority and independent-donor diagnostic boundaries."""

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
WORKFLOW=ROOT/".github/workflows/research-i029-ns-upstream-independent-donor-reference-feasibility-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i029-ns-upstream-independent-donor-reference-feasibility-v1.json"
EVALUATOR=ROOT/"tests/validation/i029_ns_upstream_independent_donor_reference_feasibility.py"
MATERIALIZE="Materialize fresh donor and target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero independent donor reference feasibility"
CURRENT={"id":29,"run_attempt":1}
PRIOR={"id":19,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I029 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen donor inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I029GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"29",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i029-ns-upstream-independent-donor-reference-feasibility-v1.yml",
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
            "jobs":{(19,1):[{"jobs":[{"steps":steps}]}]},
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
        jobs={(19,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I029 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in (
            c["fresh_diagnostic_authority"]["donor_seeds"]
            + c["fresh_diagnostic_authority"]["target_seeds"]
        ):
            self.assertNotIn(str(seed),text)

    def test_contract_has_disjoint_zero_candidate_authority(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        a=c["fresh_diagnostic_authority"]
        donor=a["donor_seeds"]
        target=a["target_seeds"]
        self.assertEqual(len(donor),3)
        self.assertEqual(len(target),3)
        self.assertTrue(set(donor).isdisjoint(target))
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)
        self.assertEqual(c["reference_semantics"]["readiness_reference_frames"],8)
        self.assertEqual(c["reference_semantics"]["donor_select_k"],3)
        self.assertFalse(
            c["reference_semantics"]["same_target_future_frames_in_donor_reference"])
        self.assertFalse(
            c["donor_target_separation"]["donor_selection_may_use_target_outputs"])
        self.assertEqual(
            c["populations"]["primary_directional_population"],
            "target cases with at least one pre-ready oracle-speech disagreement target under the unchanged eight-reference observation boundary",
        )
        self.assertEqual(c["directional_hypothesis"]["primary_metric"],"gap")
        self.assertEqual(
            c["directional_hypothesis"]["maximum_one_sided_sign_test_p"],0.01)
        self.assertTrue(
            all(value is False for value in c["authority_boundary"].values())
        )

    def test_evaluator_uses_seed_bound_case_identity_and_metadata_only_selection(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        for token in (
            '"case_key":f"{seed}:{case_id}"',
            'donor_ids={r["metadata"]["case_key"]',
            'target_ids={r["metadata"]["case_key"]',
            "compatibility_score(target_meta,record[\"metadata\"])",
            '"primary_population":"target cases with at least one pre-ready speech target"',
            'minimum_primary_pre_ready_speech_paired_cases',
            'minimum_cafeteria_paired_cases',
        ):
            self.assertIn(token,text)
        self.assertIn(
            'target["raw_targets"]["pre_ready_speech"]>0',
            text,
        )
        for forbidden in (
            "mean_cf",
            "concentration_cf",
            "noise_rescue_fraction",
            "speech_preservation_fraction",
        ):
            self.assertNotIn(forbidden,text)

    def test_negative_control_is_fixed_and_donor_selection_ignores_target_outputs(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            c["negative_control"]["domain_map"],
            {
                "kitchen":"traffic",
                "traffic":"living",
                "living":"office",
                "office":"cafeteria",
                "cafeteria":"bus",
                "bus":"field",
                "field":"kitchen",
            },
        )
        evaluator=EVALUATOR.read_text(encoding="utf-8")
        score=evaluator.split("def compatibility_score(",1)[1].split(
            "\ndef sign_test_one_sided",1)[0]
        for forbidden in (
            "raw_targets",
            "first_ready_reference",
            "mirror_gap",
            "upstream_probability",
        ):
            self.assertNotIn(forbidden,score)

    def test_dispatch_binds_i028_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i028_closure_blob_sha",
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
