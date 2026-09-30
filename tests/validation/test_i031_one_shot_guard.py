#!/usr/bin/env python3
"""Exercise I031 one-shot authority and joint-coherent aggregation boundaries."""

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
WORKFLOW=ROOT/"tests/validation/data/i031-consumed-workflow.yml"
CONTRACT=ROOT/".github/research/continuous-optimization/development-v4/i031-ns-upstream-joint-coherent-donor-aggregation-v1.json"
EVALUATOR=ROOT/"tests/validation/i031_ns_upstream_joint_coherent_donor_aggregation.py"
I030_EVALUATOR=ROOT/"tests/validation/i030_ns_upstream_donor_joint_residual_stability_decomposition.py"
MATERIALIZE="Materialize fresh I031 donor and target public-development-v3 partitions"
EVALUATE="Evaluate candidate-zero joint-coherent donor aggregation"
CURRENT={"id":31,"run_attempt":1}
PRIOR={"id":21,"run_attempt":1}


def guard_source() -> str:
    text=WORKFLOW.read_text(encoding="utf-8")
    block=text.split("      - name: Enforce one-shot I031 diagnostic execution\n",1)[1]
    block=block.split("      - name: Bind frozen I031 inputs and unchanged shipping source\n",1)[0]
    return textwrap.dedent(
        block.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    )


def step(name=EVALUATE,conclusion="success",status="completed"):
    return {"name":name,"status":status,"conclusion":conclusion}


def function_node(path: Path,name: str) -> ast.FunctionDef:
    tree=ast.parse(path.read_text(encoding="utf-8"))
    funcs=[
        node for node in tree.body
        if isinstance(node,ast.FunctionDef) and node.name==name
    ]
    if len(funcs)!=1:
        raise AssertionError(f"expected exactly one {name} in {path}")
    return funcs[0]


def normalized_function_dump(
    path: Path,
    name: str,
    *,
    normalized_name: str | None=None,
    drop_leading_require: bool=False,
) -> str:
    node=function_node(path,name)
    body=list(node.body)
    if drop_leading_require:
        first=body[0]
        if not (
            isinstance(first,ast.Expr)
            and isinstance(first.value,ast.Call)
            and isinstance(first.value.func,ast.Name)
            and first.value.func.id=="require"
        ):
            raise AssertionError(f"{name} missing leading require")
        body=body[1:]
    clone=ast.FunctionDef(
        name=normalized_name or name,
        args=node.args,
        body=body,
        decorator_list=node.decorator_list,
        returns=node.returns,
        type_comment=node.type_comment,
    )
    return ast.dump(clone,include_attributes=False)


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
    raise AssertionError(f"missing assignment: {name}")


class I031GuardTests(unittest.TestCase):
    def execute(self,*,runs=None,jobs=None,attempt="1",api_error=False):
        if runs is None:
            runs=[{"workflow_runs":[CURRENT]}]
        if jobs is None:
            jobs={}
        env={
            "GITHUB_REPOSITORY":"owner/repo",
            "GITHUB_RUN_ID":"31",
            "GITHUB_RUN_ATTEMPT":attempt,
            "GITHUB_REF":"refs/heads/main",
            "WORKFLOW_FILE":"research-i031-ns-upstream-joint-coherent-donor-aggregation-v1.yml",
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
            "jobs":{(21,1):[{"jobs":[{"steps":steps}]}]},
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
        jobs={(21,1):[{"jobs":[]},{"jobs":[{"steps":[step(EVALUATE)]}]}]}
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
        guard="      - name: Enforce one-shot I031 diagnostic execution\n"
        self.assertLess(text.index(guard),text.index(f"      - name: {MATERIALIZE}\n"))
        self.assertLess(text.index(guard),text.index(f"      - name: {EVALUATE}\n"))
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        for seed in (
            c["fresh_diagnostic_authority"]["donor_seeds"]
            + c["fresh_diagnostic_authority"]["target_seeds"]
        ):
            self.assertNotIn(str(seed),text)

    def test_contract_freezes_single_operator_and_zero_candidate_authority(self):
        c=json.loads(CONTRACT.read_text(encoding="utf-8"))
        a=c["fresh_diagnostic_authority"]
        self.assertTrue(set(a["donor_seeds"]).isdisjoint(a["target_seeds"]))
        self.assertEqual(a["candidate_limit"],0)
        self.assertEqual(a["confirmation_limit"],0)

        frozen=c["frozen_donor_selection"]
        self.assertEqual(frozen["donor_select_k"],3)
        self.assertTrue(frozen["must_remain_ast_equivalent_to_i030"])
        self.assertFalse(frozen["may_change_k"])
        self.assertFalse(frozen["may_change_matching_rule"])
        self.assertFalse(frozen["may_change_negative_control_map"])

        control=c["frozen_control_aggregation"]
        self.assertEqual(control["id"],"independent-component-median-v1")
        self.assertFalse(control["may_change"])

        op=c["joint_coherent_operator"]
        self.assertEqual(op["id"],"observed-frame-medoid-locator-v1")
        self.assertEqual(op["operator_count"],1)
        self.assertEqual(op["expected_pooled_frame_count"],24)
        self.assertTrue(op["preserves_observed_joint_identity"])
        self.assertFalse(op["search_across_operators"])
        self.assertEqual(
            op["deterministic_tie_break"],
            ["seed-bound donor case_key","frame_index"],
        )
        self.assertEqual(op["maximum_algebraic_inconsistency"],1e-6)

        h=c["directional_hypothesis"]
        self.assertEqual(h["primary_metric"],"gap_absolute_error")
        self.assertEqual(h["maximum_one_sided_sign_test_p"],0.01)
        self.assertTrue(
            all(value is False for value in c["authority_boundary"].values())
        )

    def test_i030_donor_rule_is_ast_equivalent(self):
        for name in ("scenario_group","compatibility_score","select_donors"):
            self.assertEqual(
                normalized_function_dump(I030_EVALUATOR,name),
                normalized_function_dump(EVALUATOR,name),
            )
        self.assertEqual(
            assigned_literal(I030_EVALUATOR,"DONOR_SELECT_K"),
            assigned_literal(EVALUATOR,"DONOR_SELECT_K"),
        )
        self.assertEqual(
            assigned_literal(I030_EVALUATOR,"NEGATIVE_DOMAIN"),
            assigned_literal(EVALUATOR,"NEGATIVE_DOMAIN"),
        )

    def test_control_aggregation_is_i030_equivalent(self):
        self.assertEqual(
            normalized_function_dump(
                I030_EVALUATOR,
                "aggregate_reference",
                normalized_name="frozen_control",
                drop_leading_require=True,
            ),
            normalized_function_dump(
                EVALUATOR,
                "control_aggregate",
                normalized_name="frozen_control",
                drop_leading_require=True,
            ),
        )

    def test_joint_operator_is_unique_observed_frame_l1_medoid_locator(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        tree=ast.parse(text)
        funcs=[
            node for node in tree.body
            if isinstance(node,ast.FunctionDef)
            and node.name=="joint_coherent_aggregate"
        ]
        self.assertEqual(len(funcs),1)
        block=ast.get_source_segment(text,funcs[0])
        self.assertIsNotNone(block)
        for token in (
            "DONOR_SELECT_K*REFERENCE_COUNT",
            'center={',
            'abs(frame["mean"]-center["mean"])',
            'abs(frame["concentration"]-center["concentration"])',
            'abs(frame["gap"]-center["gap"])',
            'frame["case_key"]',
            'frame["frame_index"]',
            '"selected_from_observed_pool":True',
            '"pooled_frame_count":len(pooled)',
        ):
            self.assertIn(token,block)
        self.assertNotIn("weight",block.lower())
        self.assertNotIn("candidate",block.lower())

    def test_evaluator_has_no_operator_search_or_component_counterfactual(self):
        text=EVALUATOR.read_text(encoding="utf-8")
        for forbidden in (
            "mean_cf",
            "concentration_cf",
            "noise_rescue_fraction",
            "speech_preservation_fraction",
            "operator_candidates",
            "aggregation_candidates",
            "operator_sweep",
        ):
            self.assertNotIn(forbidden,text)

    def test_dispatch_binds_i030_closure_and_shipping_sources(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "i030_closure_blob_sha",
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
