#!/usr/bin/env python3
"""Exercise I027 one-shot authority and reference-ready-component causal boundaries."""

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
WORKFLOW=ROOT/"tests/validation/data/i027-consumed-workflow.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i027-ns-upstream-reference-ready-component-counterfactual-v1.json"
EVALUATOR=ROOT/"tests/validation/i027_ns_upstream_reference_ready_component_counterfactual.py"
MATERIALIZE="Materialize fresh public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero reference-ready component counterfactual"
CURRENT={"id":26,"run_attempt":1}
PRIOR={"id":16,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I027 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen reference-ready inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE, conclusion="success", status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I027GuardTests(unittest.TestCase):
    def execute(self, *, runs=None, jobs=None, attempt="1", api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"26",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i027-ns-upstream-reference-ready-component-counterfactual-v1.yml",
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
            "jobs":{(16,1):[{"jobs":[{"steps":steps}]}]},
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
            step("Build frozen I025 dual-mirror probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(16,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
            text.index("      - name: Enforce one-shot I027 diagnostic execution\n"),
            text.index(f"      - name: {MATERIALIZE}\n"),
        )
        self.assertLess(
            text.index("      - name: Enforce one-shot I027 diagnostic execution\n"),
            text.index(f"      - name: {EVALUATE}\n"),
        )
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_has_zero_candidate_authority_and_coverage_gates(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        seeds=c["fresh_diagnostic_authority"]["seeds"]
        self.assertEqual(len(seeds),3)
        self.assertEqual(len(set(seeds)),3)
        self.assertTrue(all(type(seed) is int and seed > 0 for seed in seeds))
        self.assertEqual(c["fresh_diagnostic_authority"]["candidate_limit"],0)
        self.assertEqual(c["fresh_diagnostic_authority"]["confirmation_limit"],0)
        self.assertEqual(
            c["counterfactual_reference"]["reference_time_order"],
            "prior ordinary-noise frames only; future frames forbidden",
        )
        self.assertFalse(
            c["counterfactual_reference"][
                "excluded_targets_enter_counterfactual_denominator"
            ]
        )
        self.assertEqual(
            c["diagnostic_gates"]["minimum_global_eligible_fraction"],0.75)
        self.assertEqual(
            c["diagnostic_gates"][
                "minimum_per_noise_domain_eligible_fraction"],0.60)
        self.assertEqual(
            c["diagnostic_gates"][
                "secondary_slice_minimum_eligible_fraction"],0.50)
        self.assertEqual(
            set(c["coverage_slices"]["required_secondary"]),
            {"scenario","snr_db","reverb"},
        )
        self.assertFalse(c["readout"]["threshold_search"])
        self.assertFalse(c["readout"]["mapping_search"])
        self.assertFalse(c["readout"]["component_weight_search"])
        self.assertFalse(c["readout"]["candidate_selection"])
        self.assertTrue(
            all(value is False for value in c["authority_boundary"].values())
        )

    def test_evaluator_is_prior_only_and_excludes_pre_ready_denominators(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        block=text.split("def analyze_case(",1)[1].split("\ndef evaluate(",1)[0]
        self.assertIn("prior_reference_rows",block)
        self.assertIn(
            "if len(prior_reference_rows) < minimum_reference_frames:",
            block,
        )
        self.assertIn('result["excluded_noise_targets"] += 1',block)
        self.assertIn('result["excluded_speech_targets"] += 1',block)
        self.assertIn('result["noise_targets"] += 1',block)
        self.assertIn('result["speech_targets"] += 1',block)
        self.assertLess(
            block.index('result["excluded_noise_targets"] += 1'),
            block.index('result["noise_targets"] += 1'),
        )
        self.assertLess(
            block.index('result["excluded_speech_targets"] += 1'),
            block.index('result["speech_targets"] += 1'),
        )
        summary=text.split("def summary(",1)[1].split("\ndef slice_keys(",1)[0]
        self.assertIn(
            'acc["noise_mean_rescued"] / noise if noise else None',summary)
        self.assertIn(
            'acc["speech_mean_preserved"] / speech if speech else None',summary)
        self.assertNotIn(
            'acc["noise_mean_rescued"] / raw_noise',summary)
        self.assertIn(
            '"excluded_targets_enter_counterfactual_denominator": False',text)
        self.assertIn('"coverage_bias_guarded": True',text)

    def test_dispatch_binds_causal_inputs_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i026_closure_blob_sha",
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
        self.assertNotIn('git rev-parse HEAD^1',text)


if __name__=="__main__":
    unittest.main()
