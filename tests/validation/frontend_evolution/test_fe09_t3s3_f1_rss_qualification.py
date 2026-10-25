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

    def test_integer_stage_budget_at_large_epoch(self):
        epoch = 1_792_876_123_987_654_321
        mono = 987_654_321_987_654
        row = F1.stage_admission(epoch + 240_000_000_000, epoch, mono)
        self.assertEqual(row["admitted_stage_duration_ns"], 180_000_000_000)
        self.assertEqual(row["stage_deadline_monotonic_ns"], mono + 180_000_000_000)
        self.reject("INSUFFICIENT_F1_STAGE_WINDOW", F1.stage_admission,
                    epoch + 240_000_000_000 - 1, epoch, mono)

    def test_deadline_never_adds_float_epsilon(self):
        origin = 999_999_123_456_789
        F1.enforce_deadline(origin, origin + 180_000_000_000, 180_000_000_000, "late")
        self.reject("late", F1.enforce_deadline, origin, origin + 180_000_000_001, 180_000_000_000, "late")

    def test_engineering_work_cleanup_model_only(self):
        origin = 123_456_789
        row = F1.engineering_deadlines(origin, origin + 1_000_000_000)
        row.update(fixture="P04", timeout_trigger_monotonic_ns=origin + 800_000_000,
                   reap_finished_monotonic_ns=origin + 850_000_000,
                   encoding_finished_monotonic_ns=origin + 900_000_000,
                   owned_child_reaped=True, signal_number=9,
                   reason="F1R1_ENGINEERING_INVOCATION_TIMEOUT")
        F1.validate_engineering_completion(row)
        late = dict(row, encoding_finished_monotonic_ns=origin + 1_000_000_001)
        self.reject("F1R1_ENGINEERING_INVOCATION_LIMIT", F1.validate_engineering_completion, late)
        self.reject("F1R1_ENGINEERING_FULL_WINDOW_REQUIRED", F1.engineering_deadlines,
                    origin, origin + 999_999_999)

    def test_real_calendar_parse(self):
        self.assertIsInstance(F1.strict_UTC_seconds("2026-10-24T16:50:18Z"), int)
        self.reject("F1R1_STRICT_UTC_TIMESTAMP", F1.strict_UTC_seconds, "2026-02-30T00:00:00Z")

    @staticmethod
    def wire(phase="ENTRY", **extra):
        value = dict(v=1, phase=phase, nonce="a" * 64, ordinal=1, pid=123,
                     ppid=122, monotonic_ns=1)
        value.update(extra)
        return (json.dumps(value, separators=(",", ":")) + "\n").encode()

    def test_wire_positive_and_exact_limits(self):
        self.assertEqual(F1.validate_wire(self.wire())["phase"], "ENTRY")
        self.reject("F1R1_WIRE_BYTES_LIMIT", F1.validate_wire, b"x" * 256 + b"\n")
        self.reject("F1R1_WIRE_ASCII_LF_FRAME", F1.validate_wire, self.wire()[:-1] + b"\r\n")

    def test_wire_duplicate_and_extra_fields(self):
        raw = self.wire().replace(b'{', b'{"nonce":"' + b'a' * 64 + b'",', 1)
        self.assertLessEqual(len(raw), 256)
        self.reject("F1R1_WIRE_DUPLICATE_JSON_KEY", F1.validate_wire, raw)
        self.reject("F1R1_WIRE_FIELD_SET", F1.validate_wire, self.wire(override=1))
        self.reject("F1R1_STRICT_INTEGER_PID", F1.validate_wire, self.wire(pid=True))

    def test_original_status_singleton_units_and_boundaries(self):
        raw = b"Name:\tfixture\nPid:\t123\nPPid:\t122\nNSpid:\t123\nVmHWM:\t9 kB\nVmRSS:\t8 kB\nThreads:\t1\n"
        parsed = F1.parse_proc_status(raw)
        self.assertEqual(parsed["VmHWM_bytes"], 9216)
        self.assertEqual(parsed["namespace_mapping_sha256"], F1.sha(b"[123]"))
        self.reject("F1R1_REQUIRED_PROC_FIELDS", F1.parse_proc_status, raw.replace(b"VmHWM:\t9 kB\n", b""))
        self.reject("F1R1_DUPLICATE_PROC_FIELD", F1.parse_proc_status, raw + b"VmRSS:\t8 kB\n")
        self.reject("F1R1_PROC_UNIT", F1.parse_proc_status, raw.replace(b"9 kB", b"9 MB"))
        self.reject("F1R1_PROC_STATUS_BYTES_LIMIT", F1.parse_proc_status, b"x" * 8193)

    def test_original_stat_comm_with_spaces_and_parentheses(self):
        fields = ["S", "122"] + ["0"] * 17 + ["456"] + ["0"] * 5
        raw = ("123 (a name ) and ( more) " + " ".join(fields) + "\n").encode()
        value = F1.parse_proc_stat(raw)
        self.assertEqual((value["pid"], value["ppid"], value["start_ticks"]), (123, 122, 456))
        self.assertEqual(value["comm"], "a name ) and ( more")
        self.reject("F1R1_RAW_STAT_BYTES_LIMIT", F1.parse_proc_stat, b"x" * 1537)

    def test_wire_sequence_and_observation_before_ack(self):
        messages, observed = [], {}
        for i, phase in enumerate(("PREEXEC", "ENTRY", "RETURN")):
            extra = {"rss_kib": 0} if phase == "PREEXEC" else {"return_code": 0} if phase == "RETURN" else {}
            messages.append(self.wire(phase, monotonic_ns=i * 10 + 1, **extra))
            ack = dict(v=1, phase="ACK", for_phase=phase, nonce="a" * 64,
                       ordinal=1, child_pid=123, launcher_pid=122, monotonic_ns=i * 10 + 4)
            messages.append((json.dumps(ack, separators=(",", ":")) + "\n").encode())
            observed[phase] = (i * 10 + 2, i * 10 + 3)
        F1.validate_wire_sequence(messages, observed, nonce="a" * 64, ordinal=1, child_pid=123, launcher_pid=122)
        bad = dict(observed, ENTRY=(12, 15))
        self.reject("F1R1_OBSERVATION_BEFORE_ACK", F1.validate_wire_sequence,
                    messages, bad, nonce="a" * 64, ordinal=1, child_pid=123, launcher_pid=122)

    @staticmethod
    def freeze_template():
        # Explicit synthetic provider template; it is never live authority.
        root = MODULE.resolve().parents[3]
        contract = json.loads((root / F1.REG / "test-contract.json").read_text())
        schema = contract["external_freeze"]["body_schema"]
        def expand(rule):
            if "const" in rule:
                return copy.deepcopy(rule["const"])
            if rule.get("type") == "object":
                return {key: expand(value) for key, value in rule["properties"].items()}
            return "a" * 64
        body = expand(schema)
        body["source"].update(protected_base_B=B, protected_base_tree_B="4" * 40,
                              reviewed_head_C=C, reviewed_tree_C="5" * 40)
        body["reviewed_at_utc"] = "2026-10-24T17:00:00Z"
        user = {"login": "jiying2007", "id": 33591504, "type": "User"}
        url = "https://api.github.com/repos/" + F1.REPOSITORY + "/issues/845"
        comment = dict(id=101, node_id="SYNTHETIC_COMMENT_101", user=user,
                       issue_url=url, created_at="2026-10-24T17:00:01Z",
                       updated_at="2026-10-24T17:00:01Z", body=json.dumps(body))
        other_body = copy.deepcopy(body)
        other_body["source"]["reviewed_head_C"] = "6" * 40
        other = dict(comment, id=102, node_id="SYNTHETIC_COMMENT_102", body=json.dumps(other_body))
        issue = dict(id=6015285792, number=845, node_id="I_kwDOUE9X8c8AAAABZon6IA",
                     created_at="2026-10-24T16:50:18Z", user=user, url=url,
                     repository_url="https://api.github.com/repos/" + F1.REPOSITORY, comments=2)
        sweep = dict(repository=dict(id=F1.REPOSITORY_ID, full_name=F1.REPOSITORY),
                     issue_before=copy.deepcopy(issue), issue_after=copy.deepcopy(issue),
                     comments=[comment, other], selected_comment=copy.deepcopy(comment),
                     comments_has_next_page=False)
        args = dict(schema=schema, source=dict(C=C, B=B, C_tree="5" * 40, B_tree="4" * 40,
                                               actual_C_derived_before_freeze=True),
                    expected_digests=body["digests"], original_run_created_at="2026-10-24T17:00:02Z")
        return sweep, args

    def test_freeze_complete_counted_sweep_template(self):
        sweep, args = self.freeze_template()
        record = F1.validate_freeze_sweep(sweep, **args)
        self.assertEqual(record["id"], 101)
        self.assertEqual(record["body_sha256"], F1.sha(sweep["selected_comment"]["body"].encode()))
        F1.validate_freeze_pair(record, copy.deepcopy(record))

    def test_freeze_complete_list_and_POST_duplicate(self):
        sweep, args = self.freeze_template()
        F1.validate_freeze_sweep(sweep, **args)
        for kind in ("wrong_count", "next_page", "duplicate_C"):
            bad = copy.deepcopy(sweep)
            if kind == "wrong_count":
                bad["issue_after"]["comments"] += 1
                reason = "F1R1_COMPLETE_COMMENT_LIST"
            elif kind == "next_page":
                bad["comments_has_next_page"] = True
                reason = "F1R1_COMPLETE_COMMENT_LIST"
            else:
                body = json.loads(bad["comments"][1]["body"])
                body["source"]["reviewed_head_C"] = C
                bad["comments"][1]["body"] = json.dumps(body)
                reason = "F1R1_DUPLICATE_C_FREEZE"
            with self.subTest(mutation=kind):
                self.reject(reason, F1.validate_freeze_sweep, bad, **args)

    def test_freeze_same_tree_other_C_not_selected(self):
        sweep, args = self.freeze_template()
        body = json.loads(sweep["comments"][0]["body"])
        body["source"]["reviewed_head_C"] = "0" * 40
        sweep["comments"][0]["body"] = json.dumps(body)
        self.reject("F1R1_UNIQUE_MATCHING_C_FREEZE", F1.validate_freeze_sweep, sweep, **args)

    def test_freeze_creation_edit_and_equal_second(self):
        sweep, args = self.freeze_template()
        F1.validate_freeze_sweep(sweep, **args)
        changed = copy.deepcopy(sweep)
        changed["selected_comment"]["updated_at"] = "2026-10-24T17:00:02Z"
        self.reject("F1R1_FREEZE_COMMENT_EDITED", F1.validate_freeze_sweep, changed, **args)
        equal = dict(args, original_run_created_at="2026-10-24T17:00:01Z")
        self.reject("F1R1_FREEZE_NOT_BEFORE_ORIGINAL_RUN", F1.validate_freeze_sweep, sweep, **equal)

    def test_freeze_direct_record_mutation_predicates(self):
        sweep, args = self.freeze_template()
        F1.validate_freeze_sweep(sweep, **args)
        cases = [
            ("reviewed_at_utc", "2026-02-30T00:00:00Z", "F1R1_STRICT_UTC_TIMESTAMP"),
            ("reviewed_at_utc", "2026-10-24T17:00:02Z", "F1R1_REVIEW_TIMESTAMP"),
            ("reviewed_at_utc", "2026-10-24T16:59:59Z", "F1R1_PRE_POST_FREEZE_STABILITY"),
            ("decision", "GENERAL_REVIEW_LOOKS_GOOD", "F1R1_EXACT_EXECUTION_DECISION"),
            ("experiment_id", "OLD_F1", "F1R1_EXACT_EXPERIMENT_IDENTITY"),
        ]
        for field, value, reason in cases:
            with self.subTest(field=field, value=value):
                bad = copy.deepcopy(sweep)
                body = json.loads(bad["selected_comment"]["body"])
                body[field] = value
                bad["selected_comment"]["body"] = json.dumps(body)
                self.reject(reason, F1.validate_freeze_sweep, bad, **args)

    def test_freeze_direct_author_and_source_digest(self):
        sweep, args = self.freeze_template()
        bad = copy.deepcopy(sweep)
        bad["selected_comment"]["user"]["id"] += 1
        self.reject("F1R1_FREEZE_AUTHOR_IDENTITY", F1.validate_freeze_sweep, bad, **args)
        bad = copy.deepcopy(sweep)
        body = json.loads(bad["selected_comment"]["body"])
        body["digests"]["source_lock_sha256"] = "b" * 64
        bad["selected_comment"]["body"] = json.dumps(body)
        self.reject("F1R1_EXTERNAL_SOURCE_DIGEST", F1.validate_freeze_sweep, bad, **args)

    def test_main_actual_PR_before_freeze_and_immutable_B(self):
        S = "7" * 40
        detail = dict(id=9001, number=9001, head=pr_event()["pull_request"]["head"],
                      base=dict(pr_event()["pull_request"]["base"], sha="8" * 40),
                      merged=True, merged_at="2026-10-24T18:00:00Z", merge_commit_sha=S)
        run = dict(event="push", head_sha=S)
        graph = dict(S=S, S_parents=[B], S_tree="5" * 40, C_tree="5" * 40, B_tree="4" * 40)
        actual = F1.actual_provider_C("push", run, [detail], detail, graph)
        self.assertEqual((actual["C"], actual["B"]), (C, B))
        self.assertNotEqual(actual["B"], detail["base"]["sha"])
        self.reject("F1R1_MAIN_PROVIDER_ASSOCIATION_REQUIRED", F1.actual_provider_C,
                    "push", run, None, detail, graph)
        second = dict(detail, id=9002, number=9002)
        self.reject("F1R1_UNIQUE_MAIN_PR_ASSOCIATION", F1.actual_provider_C,
                    "push", run, [detail, second], detail, graph)


if __name__ == "__main__":
    unittest.main(verbosity=2)
