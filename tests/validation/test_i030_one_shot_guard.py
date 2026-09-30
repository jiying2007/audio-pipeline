#!/usr/bin/env python3
"""Exercise I030 one-shot authority and donor-stability diagnostic boundaries."""

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
WORKFLOW=ROOT/".github/workflows/research-i030-ns-upstream-donor-joint-residual-stability-decomposition-v1.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i030-ns-upstream-donor-joint-residual-stability-decomposition-v1.json"
EVALUATOR=ROOT/"tests/validation/i030_ns_upstream_donor_joint_residual_stability_decomposition.py"
I029_EVALUATOR=ROOT/"tests/validation/i029_ns_upstream_independent_donor_reference_feasibility.py"
MATERIALIZE="Materialize fresh I030 donor and target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero donor joint-residual stability decomposition"
CURRENT={"id":30,"run_attempt":1}
PRIOR={"id":20,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I030 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I030 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


class I030GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"30",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i030-ns-upstream-donor-joint-residual-stability-decomposition-v1.yml",
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
            "jobs":{(20,1):[{"jobs":[{"steps":steps}]}]},
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
        jobs={(20,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I030 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in (
            c["fresh_diagnostic_authority"]["donor_seeds"]
            + c["fresh_diagnostic_authority"]["target_seeds"]
        ):
            self.assertNotIn(str(seed),text)

    def test_contract_freezes_i029_rule_and_decomposition_only_authority(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        a=c["fresh_diagnostic_authority"]
        self.assertTrue(set(a["donor_seeds"]).isdisjoint(a["target_seeds"]))
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)

        rule=c["frozen_i029_donor_rule"]
        self.assertEqual(rule["donor_select_k"],3)
        self.assertTrue(rule["same_noise_domain_required"])
        self.assertFalse(rule["may_tune_rule"])
        self.assertFalse(rule["may_change_k"])
        self.assertFalse(rule["may_change_negative_control"])
        self.assertEqual(
            rule["negative_control_domain_map"],
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

        joint=c["joint_reference_semantics"]
        self.assertEqual(joint["readiness_reference_frames"],8)
        self.assertTrue(joint["preserve_joint_frames"])
        self.assertFalse(joint["same_target_future_frames_in_donor_reference"])

        slices=c["preregistered_slices"]
        self.assertEqual(slices["stress_noise_domains"],["bus","field"])
        self.assertEqual(
            slices["comparison_noise_domains"],["living","cafeteria"])
        self.assertEqual(slices["snr_db"],[-5,0,5,10,15])
        self.assertEqual(
            slices["gap_outcome"],["matched_better","matched_worse","tie"])

        self.assertTrue(
            all(value is False for value in c["authority_boundary"].values())
        )

    def test_evaluator_preserves_joint_frames_and_stability_metrics(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        for token in (
            '"frames":frames',
            '"mean":mean',
            '"concentration":concentration',
            '"gap":gap',
            "def selected_donor_stability",
            '"between_donor_mad":between',
            '"median_within_donor_mad":within',
            "def joint_alignment",
            '"gap_alignment_error"',
            '"gap_axis_projection"',
            '"common_mode_projection"',
            '"by_gap_outcome":by_gap_outcome',
            '"pre_ready_speech_by_gap_outcome":pre_ready_by_gap_outcome',
        ):
            self.assertIn(token,text)
        for forbidden in (
            "mean_cf",
            "concentration_cf",
            "noise_rescue_fraction",
            "speech_preservation_fraction",
        ):
            self.assertNotIn(forbidden,text)

    def test_matching_rule_is_i029_equivalent_and_metadata_only(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        score=text.split("def compatibility_score(",1)[1].split(
            "\ndef summarize_joint_frames",1)[0]
        for token in (
            "group_penalty",
            "reverb_penalty",
            "snr_missing_penalty",
            "snr_distance",
            "scenario_penalty",
            'donor["case_key"]',
        ):
            self.assertIn(token,score)
        for forbidden in (
            "raw_targets",
            "first_ready_joint_reference",
            "mirror_gap",
            "upstream_probability",
        ):
            self.assertNotIn(forbidden,score)

    def test_i029_matching_rule_is_ast_equivalent_and_negative_map_frozen(self):
        def function_dump(path: Path,name: str) -> str:
            tree=ast.parse(path.read_text(encoding="utf-8"))
            funcs=[
                node for node in tree.body
                if isinstance(node,ast.FunctionDef) and node.name==name
            ]
            self.assertEqual(len(funcs),1)
            node=funcs[0]
            node=ast.FunctionDef(
                name=node.name,
                args=node.args,
                body=[
                    item for item in node.body
                    if not (
                        isinstance(item,ast.Expr)
                        and isinstance(item.value,ast.Constant)
                        and isinstance(item.value.value,str)
                    )
                ],
                decorator_list=node.decorator_list,
                returns=node.returns,
                type_comment=node.type_comment,
            )
            return ast.dump(node,include_attributes=False)

        self.assertEqual(
            function_dump(I029_EVALUATOR,"scenario_group"),
            function_dump(EVALUATOR,"scenario_group"),
        )
        self.assertEqual(
            function_dump(I029_EVALUATOR,"compatibility_score"),
            function_dump(EVALUATOR,"compatibility_score"),
        )
        self.assertEqual(
            function_dump(I029_EVALUATOR,"select_donors"),
            function_dump(EVALUATOR,"select_donors"),
        )

        def assigned_literal(path: Path,name: str):
            tree=ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if (
                    isinstance(node,ast.Assign)
                    and any(
                        isinstance(target,ast.Name) and target.id==name
                        for target in node.targets
                    )
                ):
                    return ast.literal_eval(node.value)
            self.fail(f"missing assignment: {name}")

        self.assertEqual(
            assigned_literal(I029_EVALUATOR,"DONOR_SELECT_K"),
            assigned_literal(EVALUATOR,"DONOR_SELECT_K"),
        )
        self.assertEqual(
            assigned_literal(I029_EVALUATOR,"NEGATIVE_DOMAIN"),
            assigned_literal(EVALUATOR,"NEGATIVE_DOMAIN"),
        )

    def test_dispatch_binds_i029_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i029_closure_blob_sha",
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
