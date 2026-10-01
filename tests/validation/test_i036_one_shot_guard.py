#!/usr/bin/env python3
"""Exercise I036 one-shot authority and aggregation-domain boundaries."""

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
WORKFLOW=ROOT/".github/workflows/research-i036-ns-noise-estimate-aggregation-domain-decomposition-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i036-ns-noise-estimate-aggregation-domain-decomposition-v1.json"
EVALUATOR=ROOT/"tests/validation/i036_ns_noise_estimate_aggregation_domain_decomposition.py"
PROBE=ROOT/"tests/validation/i036_ns_noise_estimate_aggregation_domain_probe.c"
SHIPPING_NS=ROOT/"src/enhance/ap_ns.c"
MATERIALIZE="Materialize fresh I036 target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero NS aggregation-domain decomposition"
CURRENT={"id":36,"run_attempt":1}
PRIOR={"id":26,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I036 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I036 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I036GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"36",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":
                "research-i036-ns-noise-estimate-aggregation-domain-decomposition-v1.yml",
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
            "jobs":{(26,1):[{"jobs":[{"steps":steps}]}]},
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
            step("Build I036 aggregation-domain probe","failure"),
            step(MATERIALIZE,"skipped"),
            step(EVALUATE,"skipped"),
        ]))

    def test_later_pages_cannot_hide_consumption(self):
        runs=[{"workflow_runs":[CURRENT]},{"workflow_runs":[PRIOR]}]
        jobs={(26,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I036 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in c["fresh_diagnostic_authority"]["target_seeds"]:
            self.assertNotIn(str(seed),text)

    def test_contract_freezes_shipping_partitions_and_zero_authority(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        p=c["fixed_spectral_partitions"]
        self.assertEqual(p["nfft"],512)
        self.assertEqual(p["low_bins"],{"first":0,"last":8,"count":9})
        self.assertEqual(p["speech_bins"],{"first":9,"last":223,"count":215})
        self.assertEqual(p["high_bins"],{"first":224,"last":256,"count":33})
        self.assertTrue(p["boundaries_are_fixed_not_searched"])
        self.assertEqual(c["fixed_horizons"],[1,2,4,8])
        a=c["fresh_diagnostic_authority"]
        self.assertEqual(len(a["target_seeds"]),6)
        self.assertEqual(len(set(a["target_seeds"])),6)
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)
        self.assertTrue(all(
            value is False for value in c["authority_boundary"].values()
        ))

    def test_probe_reuses_shipping_tracker_and_reconstructs_all_bin_aggregate(self):
        text=PROBE.read_text(encoding="utf-8")
        shipping=SHIPPING_NS.read_text(encoding="utf-8")
        for token in (
            "ap_noise_tracker_update(&mirror_tracker",
            "const uint32_t low_last = nfft / 64u",
            "const uint32_t high_first = nfft * 7u / 16u",
            "all_noise_rms_dbfs",
            "noise_rms_reconstruction_gap",
            "low_noise_energy_share",
            "speech_noise_energy_share",
            "high_noise_energy_share",
            "low_update_abs_contribution_fraction",
            "speech_update_abs_contribution_fraction",
            "high_update_abs_contribution_fraction",
        ):
            self.assertIn(token,text)
        self.assertIn(
            "if (k > nfft / 64u && k < nfft * 7u / 16u)",shipping)
        self.assertNotIn("band_candidates",text)

    def test_evaluator_is_fixed_partition_descriptive_only(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        tree=ast.parse(text)
        for token in (
            "HORIZONS=(1,2,4,8)",
            "speech_vs_all_alignment_improvement_db",
            "speech_response_deficit_db",
            "all_response_deficit_db",
            "speech_alignment_better_fraction",
            "max_noise_rms_reconstruction_gap_db",
        ):
            self.assertIn(token,text)
        for forbidden in (
            "band_candidates",
            "estimator_candidates",
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
        self.assertIn("horizon_review",funcs)
        self.assertIn("cumulative_horizon_row",funcs)
        self.assertIn("analyze_case",funcs)

    def test_dispatch_binds_i035_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i035_closure_blob_sha",
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
