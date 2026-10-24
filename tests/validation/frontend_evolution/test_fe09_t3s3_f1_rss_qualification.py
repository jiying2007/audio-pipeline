#!/usr/bin/env python3
"""Pure in-process F1 bootstrap/scheduling controls; no process or HTTP fixtures.

These tests establish only metadata predicates. They do not claim execution of
the planned178 full-evidence negatives or any real launcher/HTTP lifecycle.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name("fe09_t3s3_f1_rss_qualification.py")
SPEC = importlib.util.spec_from_file_location("fe09_f1_metadata", MODULE)
F1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(F1)
B, C, M = "1" * 40, "2" * 40, "3" * 40


def pr_event(branch=F1.REGISTERED_BRANCH):
    return {"repository": {"id": F1.REPOSITORY_ID, "full_name": F1.REPOSITORY},
            "pull_request": {"head": {"sha": C, "ref": branch,
                                      "repo": {"id": F1.REPOSITORY_ID}},
                             "base": {"sha": B, "ref": "main",
                                      "repo": {"id": F1.REPOSITORY_ID}}}}


def routing():
    paths = ["frozen/original.c", F1.SOURCE]
    return {"candidate_protected_paths": paths[:], "protected_B_paths": paths[:],
            "fast_docs": ["F1_R1_SOURCE_SCOPE_GUARD"],
            "fast_code": ["F1_R1_SOURCE_SCOPE_GUARD"],
            "caller_permissions": dict(F1.FIVE_READ),
            "child_permissions": dict(F1.FIVE_READ),
            "top_permissions": dict.fromkeys(("contents", "packages", "actions"), "read"),
            "continue_on_error": False, "guard_source": B, "B": B,
            "B_main_closed": True, "bootstrap_launchers": 0,
            "docs_only_execution_C": True, "f1_required": True,
            "caller_called": True, "run_f1": True, "child_selected": True,
            "summary_expect_quality": True, "summary_checks_disposition": True}


class MetadataTests(unittest.TestCase):
    def reject(self, reason, callback, *args, **kwargs):
        with self.assertRaises(F1.Rejected) as error:
            callback(*args, **kwargs)
        self.assertEqual(error.exception.reason, reason)

    def test_bootstrap_execution_gate_is_false(self):
        self.assertIs(F1.SCIENCE_EXECUTION_ENABLED, False)

    def test_strict_json_positive(self):
        self.assertEqual(F1.strict_json(b'{"a":1}'), {"a": 1})

    def test_duplicate_keys_rejected(self):
        self.reject("F1R1_DUPLICATE_JSON_KEY", F1.strict_json, b'{"a":1,"a":2}')

    def test_nonfinite_rejected(self):
        self.reject("F1R1_NONFINITE_NUMBER", F1.strict_json, b'{"a":NaN}')

    def test_size_before_parse(self):
        self.reject("F1R1_SERIALIZED_BYTES_LIMIT", F1.strict_json, b'x' * 257, 256)

    def test_booleans_not_numbers(self):
        self.assertFalse(F1.integer(True))
        self.assertFalse(F1.finite(False))
        self.assertTrue(F1.integer(0))

    def test_actual_PR_role_positive(self):
        roles = F1.parse_event("pull_request", pr_event(), M, [B, C])
        self.assertEqual((roles["B"], roles["C"], roles["checkout"]), (B, C, M))
        self.assertFalse(roles["provider_merged_PR_authority"])

    def test_PR_parents_reversed(self):
        self.reject("F1R1_EXACT_PR_MERGE_PARENTS", F1.parse_event,
                    "pull_request", pr_event(), M, [C, B])

    def test_main_immutable_parent(self):
        event = {"repository": pr_event()["repository"], "ref": "refs/heads/main",
                 "before": B, "after": M}
        self.assertEqual(F1.parse_event("push", event, M, [B])["B"], B)
        self.reject("F1R1_IMMUTABLE_MAIN_PARENT_B", F1.parse_event,
                    "push", event, M, [C])

    def test_fork_spelling_not_registered(self):
        event = pr_event()
        event["pull_request"]["head"]["repo"]["id"] += 1
        self.assertFalse(F1.parse_event("pull_request", event, M, [B, C])["registered_candidate"])

    def scope(self, *, registered=True, guard=True, ready=True, changed=True, origin=B):
        roles = F1.parse_event("pull_request", pr_event(F1.REGISTERED_BRANCH if registered else "unrelated"), M, [B, C])
        return F1.evaluate_scope(event=roles, changed={F1.REG + "/EXECUTION_BASELINE.json"} if changed else set(),
                                 protected={F1.REG + "/EXECUTION_BASELINE.json"},
                                 base_guard_present=guard, guard_origin=origin,
                                 execution_ready=ready)

    def test_bootstrap_zero_process_disposition(self):
        result = self.scope(guard=False, ready=False, origin=None)
        self.assertEqual(result["disposition"], F1.SOURCE_ONLY)
        self.assertFalse(result["f1_required"])

    def test_bootstrap_invented_guard(self):
        self.reject("F1R1_BOOTSTRAP_METADATA_ONLY", self.scope, guard=False, ready=False)

    def test_bootstrap_execution_attempt(self):
        self.reject("F1R1_BOOTSTRAP_ZERO_F1_PROCESSES", self.scope, guard=False, origin=None)

    def test_candidate_is_not_protected_guard(self):
        self.reject("F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED", self.scope, origin=C)

    def test_docs_only_final_C_forces_real_job(self):
        result = self.scope()
        self.assertTrue(result["f1_required"])
        self.assertEqual(result["disposition"], "F1_PROVIDER_ADMISSION_REQUIRED")

    def test_unrelated_protected_change_rejected(self):
        self.reject("F1_OUT_OF_SCOPE_PROTECTED_CHANGE", self.scope, registered=False)

    def test_unrelated_proven_no_change_source_only(self):
        result = self.scope(registered=False, changed=False)
        self.assertEqual(result["disposition"], F1.OUT_OF_SCOPE)
        self.assertFalse(result["f1_required"])

    def test_routing_positive(self):
        F1.validate_routing(routing())

    def mutation(self, key, value, reason):
        positive = routing()
        F1.validate_routing(positive)
        bad = copy.deepcopy(positive)
        bad[key] = value
        self.reject(reason, F1.validate_routing, bad)

    def test_candidate_pathset_cannot_approve_removal(self):
        self.mutation("candidate_protected_paths", [F1.SOURCE], "F1R1_PROTECTED_BASE_POLICY_REQUIRED")

    def test_fast_docs_call_required(self):
        self.mutation("fast_docs", [], "F1R1_GUARD_REQUIRED_ON_FAST_DOCS")

    def test_fast_code_call_required(self):
        self.mutation("fast_code", [], "F1R1_GUARD_REQUIRED_ON_FAST_CODE")

    def test_caller_all_five_reads(self):
        bad = dict(F1.FIVE_READ)
        del bad["issues"]
        self.mutation("caller_permissions", bad, "F1R1_FIVE_READ_CALLER_PERMISSIONS")

    def test_child_all_five_reads(self):
        bad = dict(F1.FIVE_READ)
        del bad["actions"]
        self.mutation("child_permissions", bad, "F1R1_FIVE_READ_CHILD_PERMISSIONS")

    def test_no_top_scope_expansion(self):
        self.mutation("top_permissions", dict(F1.FIVE_READ), "F1R1_PERMISSION_CHANGE_SCOPE")

    def test_no_ignored_F1_failure(self):
        self.mutation("continue_on_error", True, "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")

    def test_actual_B_guard_source(self):
        self.mutation("guard_source", C, "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED")

    def test_guarded_B_must_close_own_main(self):
        self.mutation("B_main_closed", False, "F1R1_PROTECTED_GUARD_BASE_CLOSURE_REQUIRED")

    def test_bootstrap_no_launcher(self):
        self.mutation("bootstrap_launchers", 1, "F1R1_BOOTSTRAP_ZERO_F1_PROCESSES")

    def test_each_docs_dispatch_link_required(self):
        for key in ("f1_required", "caller_called", "run_f1", "child_selected",
                    "summary_expect_quality", "summary_checks_disposition"):
            with self.subTest(link=key):
                self.mutation(key, False, "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")

    def test_shared_hook_projection_is_conservative(self):
        raw = b'name: Quality\n\njobs:\n  frontend-rss-f1:\n    run: source-only\n  other:\n    run: a\n'
        changed = raw.replace(b'run: a', b'run: b')
        self.assertEqual(F1.workflow_projection(raw, "quality"), F1.workflow_projection(changed, "quality"))
        touched = raw.replace(b'run: source-only', b'run: no-guard')
        self.assertNotEqual(F1.workflow_projection(raw, "quality"), F1.workflow_projection(touched, "quality"))

    def test_duplicate_workflow_job_rejected(self):
        raw = b'jobs:\n  frontend-rss-f1:\n    run: x\n  frontend-rss-f1:\n    run: y\n'
        self.reject("F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED", F1.workflow_projection, raw, "quality")

    def test_actual_YAML_route_positive_and_single_mutations(self):
        root = MODULE.resolve().parents[3]
        originals = {str(root / name): (root / name).read_bytes() for name in F1.HOOKS}
        with patch.object(F1, "bounded_file", side_effect=lambda p: originals[str(p)]):
            F1.validate_actual_routes(root)
        cases = [
            (F1.HOOKS[0], b" || needs.impact.outputs.f1_required == 'true')", b")", "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1"),
            (F1.HOOKS[0], b"      run_f1: ${{ needs.impact.outputs.f1_required == 'true' }}", b"      run_f1: false", "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1"),
            (F1.HOOKS[1], b"    if: inputs.run_extended || inputs.run_f1", b"    if: inputs.run_extended", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
            (F1.HOOKS[0], b"          EXPECT_QUALITY: ${{ needs.impact.outputs.run_quality == 'true' || needs.impact.outputs.f1_required == 'true' }}", b"          EXPECT_QUALITY: ${{ needs.impact.outputs.run_quality }}", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
            (F1.HOOKS[0], b"          F1_DISPOSITION: ${{ needs.quality.outputs.f1_disposition }}", b"          F1_DISPOSITION: made-up", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
            (F1.HOOKS[1], b"        value: ${{ jobs.frontend-rss-f1.outputs.disposition }}", b"        value: SOURCE_METADATA_ONLY", "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION"),
        ]
        for name, old, new, reason in cases:
            with self.subTest(field=old.decode()):
                self.assertEqual(originals[str(root / name)].count(old), 1)
                mutated = dict(originals)
                mutated[str(root / name)] = mutated[str(root / name)].replace(old, new, 1)
                with patch.object(F1, "bounded_file", side_effect=lambda p: mutated[str(p)]):
                    self.reject(reason, F1.validate_actual_routes, root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
