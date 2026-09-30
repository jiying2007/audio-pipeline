#!/usr/bin/env python3
"""Exercise I032 one-shot authority and causal noise-scale boundaries."""

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
WORKFLOW=ROOT/".github/workflows/research-i032-ns-upstream-target-causal-noise-scale-observability-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i032-ns-upstream-target-causal-noise-scale-observability-v1.json"
EVALUATOR=ROOT/"tests/validation/i032_ns_upstream_target_causal_noise_scale_observability.py"
I031_EVALUATOR=ROOT/"tests/validation/i031_ns_upstream_joint_coherent_donor_aggregation.py"
PROBE=ROOT/"tests/validation/i025_ns_upstream_disagreement_noise_source_probe.c"
MATERIALIZE="Materialize fresh I032 donor and target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero target causal noise-scale observability"
CURRENT={"id":32,"run_attempt":1}
PRIOR={"id":22,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I032 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I032 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


def function_dump(path: Path,name: str) -> str:
    tree=ast.parse(path.read_text(encoding="utf-8"))
    funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    if len(funcs)!=1:
        raise AssertionError(f"expected one {name} in {path}")
    return ast.dump(funcs[0],include_attributes=False)


def assigned_literal(path: Path,name: str):
    tree=ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing assignment: {name}")


class I032GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"32",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i032-ns-upstream-target-causal-noise-scale-observability-v1.yml",
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
            "jobs":{(22,1):[{"jobs":[{"steps":steps}]}]},
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
        jobs={(22,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I032 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in (
            c["fresh_diagnostic_authority"]["donor_seeds"]
            + c["fresh_diagnostic_authority"]["target_seeds"]
        ):
            self.assertNotIn(str(seed),text)

    def test_i031_donor_selection_is_ast_equivalent(self):
        for name in ("scenario_group","compatibility_score","select_donors"):
            self.assertEqual(
                function_dump(I031_EVALUATOR,name),
                function_dump(EVALUATOR,name),
            )
        self.assertEqual(
            assigned_literal(I031_EVALUATOR,"DONOR_SELECT_K"),
            assigned_literal(EVALUATOR,"DONOR_SELECT_K"),
        )
        self.assertEqual(
            assigned_literal(I031_EVALUATOR,"NEGATIVE_DOMAIN"),
            assigned_literal(EVALUATOR,"NEGATIVE_DOMAIN"),
        )

    def test_frozen_control_is_component_median_only(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        node=ast.get_source_segment(
            text,
            next(
                n for n in ast.parse(text).body
                if isinstance(n,ast.FunctionDef) and n.name=="frozen_donor_control"
            ),
        )
        self.assertIsNotNone(node)
        self.assertIn('for key in ("mean","concentration","gap")',node)
        self.assertIn("statistics.median",node)
        self.assertNotIn("ns_noise_rms_dbfs",node)
        self.assertNotIn("weight",node.lower())

        noise=ast.get_source_segment(
            text,
            next(
                n for n in ast.parse(text).body
                if isinstance(n,ast.FunctionDef) and n.name=="frozen_donor_noise_scale"
            ),
        )
        self.assertIsNotNone(noise)
        self.assertIn('"ns_noise_rms_dbfs"',noise)
        self.assertIn("statistics.median",noise)

    def test_proxy_and_later_benchmark_are_causally_separated(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        analyze=ast.get_source_segment(
            text,
            next(
                n for n in ast.parse(text).body
                if isinstance(n,ast.FunctionDef) and n.name=="analyze_case"
            ),
        )
        self.assertIsNotNone(analyze)
        for token in (
            'noise_db=float(row["ns_noise_rms_dbfs"])',
            'label==1',
            'is_disagreement',
            'len(initial_refs)<REFERENCE_COUNT',
            '"ns_noise_rms_dbfs":noise_db',
            'local_index>first_pre_ready_target["local_frame_index"]',
            'len(later_refs)<REFERENCE_COUNT',
        ):
            self.assertIn(token,analyze)

        probe=PROBE.read_text(encoding="utf-8")
        self.assertIn("ns_noise_rms_dbfs",probe)
        self.assertIn("(double)ns_result.noise_rms_dbfs",probe)
        self.assertIn("ap_ns_process(&ns_state",probe)

    def test_engineering_bounds_and_descriptive_association_only(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        h=c["fidelity_hypothesis"]
        self.assertEqual(h["maximum_median_absolute_error_db"],3.0)
        self.assertEqual(h["maximum_p90_absolute_error_db"],6.0)
        self.assertEqual(h["percentile_definition"],"nearest-rank")
        assoc=c["descriptive_transfer_association"]
        self.assertEqual(assoc["authority"],"descriptive only")
        self.assertFalse(assoc["may_select_normalization_mapping"])
        self.assertFalse(assoc["may_select_candidate"])
        self.assertTrue(all(
            value is False for value in c["authority_boundary"].values()
        ))

    def test_no_joint_operator_or_normalization_mapping_implementation(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        for forbidden in (
            "joint_coherent_aggregate",
            "operator_sweep",
            "aggregation_candidates",
            "def normalize_gap",
            "def apply_noise_scale_normalization",
            "mapping_candidates",
            "mean_cf",
            "concentration_cf",
        ):
            self.assertNotIn(forbidden,text)

    def test_dispatch_binds_i031_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i031_closure_blob_sha",
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
