#!/usr/bin/env python3
"""Exercise I034 one-shot authority and fixed temporal-response boundaries."""

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
WORKFLOW=ROOT/"tests/validation/data/i034-consumed-workflow.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i034-ns-vad-noise-state-temporal-response-decomposition-v1.json"
EVALUATOR=ROOT/"tests/validation/i034_ns_vad_noise_state_temporal_response_decomposition.py"
BASE_EVALUATOR=ROOT/"tests/validation/i033_ns_vad_causal_noise_delta_alignment.py"
PROBE=ROOT/"tests/validation/i033_ns_vad_causal_noise_delta_probe.c"
MATERIALIZE="Materialize fresh I034 target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero NS/VAD temporal response decomposition"
CURRENT={"id":34,"run_attempt":1}
PRIOR={"id":24,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I034 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I034 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I034GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"34",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":
                "research-i034-ns-vad-noise-state-temporal-response-decomposition-v1.yml",
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
            "jobs":{(24,1):[{"jobs":[{"steps":steps}]}]},
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
            step("Build frozen I033 observation probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(24,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I034 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["target_seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_is_target_only_fixed_horizon_zero_candidate(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        a=c["fresh_diagnostic_authority"]
        self.assertEqual(len(a["target_seeds"]),6)
        self.assertEqual(len(set(a["target_seeds"])),6)
        self.assertNotIn("donor_seeds",a)
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)

        temporal=c["fixed_temporal_response_semantics"]
        self.assertEqual(temporal["reference_horizons"],[1,2,4,8])
        self.assertTrue(temporal["cumulative_median_through_horizon"])
        self.assertFalse(temporal["best_horizon_selection_allowed"])
        self.assertTrue(all(
            value is False for value in c["authority_boundary"].values()
        ))

    def test_evaluator_uses_fixed_cumulative_horizons_only(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        tree=ast.parse(text)
        self.assertIn("HORIZONS=(1,2,4,8)",text)
        self.assertIn("prefix=later[:horizon]",text)
        self.assertIn("statistics.median(",text)
        self.assertIn('"alignment_abs_error_db":abs(ns_delta-local_delta)',text)
        self.assertIn("base.analyze_case(",text)
        for forbidden in (
            "argmin",
            "tracker_alpha_candidates",
            "mapping_candidates",
            "threshold_candidates",
            "select_donors",
            "def source_candidate",
        ):
            self.assertNotIn(forbidden,text)
        funcs={
            n.name for n in tree.body if isinstance(n,ast.FunctionDef)
        }
        self.assertIn("cumulative_horizon_row",funcs)
        self.assertIn("horizon_summary",funcs)

    def test_frozen_i033_probe_and_extractor_are_reused(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            c["diagnostic_inputs"]["probe_path"],
            "tests/validation/i033_ns_vad_causal_noise_delta_probe.c",
        )
        self.assertEqual(
            c["diagnostic_inputs"]["causal_extractor_path"],
            "tests/validation/i033_ns_vad_causal_noise_delta_alignment.py",
        )
        probe=PROBE.read_text(encoding="utf-8")
        self.assertIn("post_ns_rms_dbfs",probe)
        base=BASE_EVALUATOR.read_text(encoding="utf-8")
        self.assertIn("def analyze_case(",base)

    def test_dispatch_binds_i033_closure_and_all_inputs(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i033_closure_blob_sha",
            "dataset_lock_git_blob_sha",
            "builder_git_blob_sha",
            "probe_git_blob_sha",
            "causal_extractor_git_blob_sha",
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

    def test_packaging_uses_real_newlines_not_literal_backslash_n(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("printf '%s\\n' \"$rc\"",text)
        self.assertIn("-printf '%f\\n'",text)
        self.assertIn("+'\\n')",text)
        self.assertNotIn("printf '%s\\\\n' \"$rc\"",text)
        self.assertNotIn("-printf '%f\\\\n'",text)
        self.assertNotIn("+'\\\\n')",text)


if __name__=="__main__":
    unittest.main()
