#!/usr/bin/env python3
"""Exercise I035 one-shot authority and update-regime boundaries."""

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
WORKFLOW=ROOT/".github/workflows/research-i035-ns-noise-tracker-update-regime-decomposition-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i035-ns-noise-tracker-update-regime-decomposition-v1.json"
EVALUATOR=ROOT/"tests/validation/i035_ns_noise_tracker_update_regime_decomposition.py"
PROBE=ROOT/"tests/validation/i035_ns_noise_tracker_update_regime_probe.c"
TRACKER=ROOT/"src/enhance/ap_noise_tracker.c"
MATERIALIZE="Materialize fresh I035 target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero NS tracker update-regime decomposition"
CURRENT={"id":35,"run_attempt":1}
PRIOR={"id":25,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I035 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I035 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I035GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"35",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":
                "research-i035-ns-noise-tracker-update-regime-decomposition-v1.yml",
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
            "jobs":{(25,1):[{"jobs":[{"steps":steps}]}]},
        }

    def test_first_dispatch_allowed(self):
        self.execute()

    def test_rerun_blocked(self):
        with self.assertRaises(SystemExit):
            self.execute(attempt="2")

    def test_consuming_steps_are_one_shot_even_on_failure(self):
        for name in (MATERIALIZE,EVALUATE):
            for conclusion in ("success","failure","cancelled"):
                with (
                    self.subTest(name=name,conclusion=conclusion),
                    self.assertRaises(SystemExit),
                ):
                    self.execute(**self.history([step(name,conclusion)]))

    def test_pre_materialization_failure_does_not_consume(self):
        self.execute(**self.history([
            step("Build I035 update-regime probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(25,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I035 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["target_seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_freezes_shipping_tracker_mechanism(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        m=c["fixed_tracker_mechanism"]
        self.assertEqual(m["slow_update_speech_probability_threshold"],0.35)
        self.assertEqual(m["slow_alpha"],0.995)
        self.assertEqual(m["fast_alpha"],0.92)
        self.assertTrue(m["parameters_are_observed_not_changed"])
        self.assertEqual(c["fixed_horizons"],[1,2,4,8])
        a=c["fresh_diagnostic_authority"]
        self.assertEqual(len(a["target_seeds"]),6)
        self.assertEqual(len(set(a["target_seeds"])),6)
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)
        self.assertTrue(all(
            value is False for value in c["authority_boundary"].values()
        ))

    def test_probe_reuses_shipping_tracker_and_accounts_slow_fast_contribution(self):
        text=PROBE.read_text(encoding="utf-8")
        tracker=TRACKER.read_text(encoding="utf-8")
        for token in (
            "ap_noise_tracker_update(&mirror_tracker",
            "speech > TRACKER_SLOW_UPDATE_SPEECH_THRESHOLD",
            "slow_update_abs_contribution_fraction",
            "fast_update_abs_contribution_fraction",
            "slow_signed_update_fraction_of_previous_noise",
            "fast_signed_update_fraction_of_previous_noise",
            "total_abs_update_fraction_of_previous_noise",
        ):
            self.assertIn(token,text)
        self.assertIn("speech > 0.35f ? 0.995f : 0.92f",tracker)
        self.assertNotIn("ap_noise_tracker_update(",text.split(
            "static void mirror_upstream_components",1)[0])

    def test_evaluator_is_descriptive_and_has_no_parameter_search(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        tree=ast.parse(text)
        for token in (
            "HORIZONS=(1,2,4,8)",
            "spearman_slow_update_bin_fraction_vs_response_deficit",
            "spearman_fast_update_abs_contribution_fraction_vs_response_deficit",
            "slow_exposure_quartiles",
            "fast_abs_contribution_quartiles",
            "response_deficit_db",
        ):
            self.assertIn(token,text)
        for forbidden in (
            "alpha_candidates",
            "threshold_candidates",
            "mapping_candidates",
            "select_donors",
            "def source_candidate",
            "argmin",
            "argmax",
        ):
            self.assertNotIn(forbidden,text)
        funcs={
            n.name for n in tree.body if isinstance(n,ast.FunctionDef)
        }
        self.assertIn("quartile_review",funcs)
        self.assertIn("horizon_review",funcs)
        self.assertIn("analyze_case",funcs)

    def test_dispatch_binds_i034_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i034_closure_blob_sha",
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

    def test_packaging_uses_real_newlines(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("printf '%s\\n' \"$rc\"",text)
        self.assertIn("-printf '%f\\n'",text)
        self.assertIn("+'\\n')",text)
        self.assertNotIn("printf '%s\\\\n' \"$rc\"",text)
        self.assertNotIn("-printf '%f\\\\n'",text)
        self.assertNotIn("+'\\\\n')",text)


if __name__=="__main__":
    unittest.main()
