#!/usr/bin/env python3
"""Trusted-base PR-only consumer of independently reviewed M1 pin evidence.

A denial keeps every original research guard active. No push, dispatch, reusable
workflow call, failed science result or unprotected candidate policy may request
a measurement skip. The PR tree is only read as Git data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SELF = ".github/program/workflow_pin_pr_consumer.py"
M1_PATH = HERE / "workflow_pin_only_actual_tree_t1m1.py"
WORKFLOWS = (
    ".github/workflows/pcr02-aec-real-tail-confirmation.yml",
    ".github/workflows/pcr02-dsp-counterfactuals.yml",
    ".github/workflows/research-dechorate-ground-truth-diagnostic-v1.yml",
)
POSITIVE = "SCIENCE_NOT_EXECUTED_NON_MEASUREMENT_MAINTENANCE"
NEGATIVE = "ORIGINAL_RESEARCH_GUARDS_REQUIRED"
MAX_EVENT_BYTES = 150_000


class Denied(ValueError):
    pass


def need(condition: bool, code: str) -> None:
    if not condition:
        raise Denied(code)


def load_m1():
    spec = importlib.util.spec_from_file_location("protected_pr_consumer_m1", M1_PATH)
    need(spec is not None and spec.loader is not None, "M1_SOURCE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_identity(env: dict) -> dict:
    result = {}
    for name, field in (("GITHUB_RUN_ID", "run_id"),
                        ("GITHUB_RUN_ATTEMPT", "run_attempt")):
        value = env.get(name)
        need(type(value) is str and re.fullmatch(r"[1-9][0-9]{0,18}", value) is not None,
             "CANONICAL_RUN_IDENTITY_REQUIRED")
        result[field] = int(value)
    return result


def event_binding(event: dict, env: dict, workflow: str, m1) -> tuple[str, str, str]:
    need(os.name == "posix" and sys.platform == "linux", "UNQUALIFIED_PLATFORM")
    need(workflow in WORKFLOWS, "UNREVIEWED_WORKFLOW")
    need(env.get("GITHUB_EVENT_NAME") == "pull_request", "NON_PR_EVENT")
    need(env.get("GITHUB_REPOSITORY") == m1.REPO, "UNTRUSTED_EVENT_REPOSITORY")
    expected_ref = "refs/pull/" + str(m1.BOT_PR) + "/merge"
    need(env.get("GITHUB_REF") == expected_ref, "UNTRUSTED_PR_REF")
    # A reusable workflow inherits the CALLER github context. Requiring this
    # direct workflow file excludes PCR02's nested AEC workflow_call.
    need(env.get("GITHUB_WORKFLOW_REF") == m1.REPO + "/" + workflow + "@" + expected_ref,
         "REUSABLE_OR_UNEXPECTED_WORKFLOW_CONTEXT")
    run_identity(env)
    need(type(event) is dict and event.get("action") in ("opened", "reopened", "synchronize") and
         type(event.get("number")) is int and event["number"] == m1.BOT_PR and
         type(event.get("repository")) is dict and
         event["repository"].get("full_name") == m1.REPO and
         type(event.get("pull_request")) is dict, "UNTRUSTED_PR_EVENT")
    pr = event["pull_request"]
    base, head = pr.get("base", {}).get("sha"), pr.get("head", {}).get("sha")
    m1.snapshot_metadata(pr, base, head)
    need(env.get("GITHUB_BASE_REF") == "main" and env.get("GITHUB_HEAD_REF") == m1.BOT_REF,
         "EVENT_REF_CONTEXT_MISMATCH")
    merge = env.get("GITHUB_SHA", "")
    need(type(merge) is str and m1.SHA.fullmatch(merge) is not None,
         "INVALID_EVENT_MERGE_OID")
    return base, head, merge


def bind_m1(observed: dict, base: str, head: str, m1) -> None:
    need(type(observed) is dict and observed.get("decision") == m1.ADMITTED and
         observed.get("review_id") == m1.CURRENT_REVIEW and
         observed.get("protected_main_sha") == base and
         observed.get("bot_base_sha") == base and observed.get("bot_head_sha") == head and
         observed.get("actual_merge_base") == base and
         observed.get("actual_bot_git_tree_checked") is True and
         observed.get("automated_bypass_enabled") is False and
         observed.get("scientific_experiment_executed") is False and
         observed.get("action_supply_chain_attested") is False,
         "M1_NOT_CURRENT_EXACT_PR_AUTHORITY")
    for key in ("pin_diff_sha256", "trusted_classifier_sha256",
                "trusted_qualifier_sha256", "expected_current_base_pin_diff_sha256"):
        need(type(observed.get(key)) is str and m1.HEX64.fullmatch(observed[key]) is not None,
             "M1_RECEIPT_IDENTITY_MISSING")
    need(observed["pin_diff_sha256"] == observed["expected_current_base_pin_diff_sha256"],
         "M1_ACTUAL_EXPECTED_DIFF_MISMATCH")


def verify_consumer_source(base: str, m1) -> str:
    need(m1.git_sha(["rev-parse", "HEAD"]) == base, "CONSUMER_CHECKOUT_NOT_EXACT_BASE")
    raw = (ROOT / SELF).read_bytes()
    need(0 < len(raw) < MAX_EVENT_BYTES and not (ROOT / SELF).is_symlink() and
         raw == m1.git(["show", base + ":" + SELF]),
         "UNPROTECTED_CONSUMER_SOURCE")
    entry = m1.git(["ls-tree", base, "--", SELF]).decode("ascii")
    need(re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(SELF) + r"\n", entry)
         is not None, "CONSUMER_SOURCE_MODE_DRIFT")
    return hashlib.sha256(raw).hexdigest()


def bind_event_merge(base: str, head: str, merge: str, m1) -> None:
    m1.git(["fetch", "--no-tags", "--no-write-fetch-head",
            "--recurse-submodules=no", m1.GIT_REMOTE, merge], cap=8192)
    lineage = m1.git(["rev-list", "--parents", "-n", "1", merge]).decode("ascii").split()
    need(lineage == [merge, base, head], "EVENT_MERGE_PARENT_DRIFT")
    need(m1.git_sha(["rev-parse", merge + "^{tree}"]) ==
         m1.git_sha(["rev-parse", head + "^{tree}"]), "EVENT_MERGE_TREE_DRIFT")


def evaluate(event: dict, env: dict, workflow: str) -> dict:
    result = {"schema_version": 1, "decision": NEGATIVE, "skip_measurement": False,
              "workflow": workflow, "event": "pull_request" if env.get("GITHUB_EVENT_NAME") == "pull_request" else "other",
              "scientific_experiment_executed": False, "acoustic_pass": False,
              "action_supply_chain_attested": False, "automated_bypass_enabled": False}
    try:
        m1 = load_m1()
        base, head, merge = event_binding(event, env, workflow, m1)
        result.update(run_identity(env))
        source_hash = verify_consumer_source(base, m1)
        observed = m1.live_probe(review=m1.CURRENT_REVIEW)
        bind_m1(observed, base, head, m1)
        bind_event_merge(base, head, merge, m1)
        latest_base, latest_head = m1.remote_heads()
        need((latest_base, latest_head) == (base, head) and
             m1.snapshot_metadata(m1.fetch_public_bot_pr(), latest_base, latest_head) == (base, head),
             "SOURCE_MOVED_AFTER_EVENT_BINDING")
        result.update(decision=POSITIVE, skip_measurement=True,
                      automated_bypass_enabled=True,
                      reason="EXACT_DIRECT_PR_APPROVED_PIN_MAINTENANCE",
                      base_sha=base, head_sha=head, event_merge_sha=merge,
                      consumer_sha256=source_hash, m1=observed)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc)
        result["reason"] = reason if re.fullmatch(r"[A-Z0-9_]{1,100}", reason) else "SOURCE_OR_EVENT_NOT_ADMITTED"
    return result


def self_test() -> None:
    m1 = load_m1()
    base, head, merge = "a" * 40, "b" * 40, "c" * 40
    role = WORKFLOWS[0]
    model = {"number": m1.BOT_PR, "action": "synchronize",
             "repository": {"full_name": m1.REPO}, "pull_request": m1.fake_bot(base, head)}
    env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": m1.REPO,
           "GITHUB_REF": "refs/pull/714/merge", "GITHUB_BASE_REF": "main",
           "GITHUB_HEAD_REF": m1.BOT_REF, "GITHUB_SHA": merge,
           "GITHUB_RUN_ID": "7300001", "GITHUB_RUN_ATTEMPT": "2",
           "GITHUB_WORKFLOW_REF": m1.REPO + "/" + role + "@refs/pull/714/merge"}
    need(event_binding(model, env, role, m1) == (base, head, merge), "VALID_DIRECT_PR_EVENT_REJECTED")
    negatives = 0

    def deny_event(event, context, wanted=role):
        nonlocal negatives
        try:
            event_binding(event, context, wanted, m1)
        except (ValueError, TypeError, AttributeError):
            negatives += 1
            return
        raise Denied("FALSE_EVENT_ADMISSION")

    for kind in ("push", "workflow_dispatch", "workflow_call", "repository_dispatch", "", "pull_request_target"):
        deny_event(model, dict(env, GITHUB_EVENT_NAME=kind))
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        absent = dict(env)
        del absent[key]
        deny_event(model, absent)
        for value in (None, 0, True, "", "0", "01", "-1", "+1", " 1", "1 ",
                      "1\n", "1\r\n", "1.0", "1" * 20):
            deny_event(model, dict(env, **{key: value}))
    for key, value in (("GITHUB_REPOSITORY", "fork/repo"),
                       ("GITHUB_REF", "refs/heads/main"), ("GITHUB_BASE_REF", "dev"),
                       ("GITHUB_HEAD_REF", "attacker"), ("GITHUB_SHA", "short"),
                       ("GITHUB_WORKFLOW_REF", m1.REPO + "/" + WORKFLOWS[1] + "@refs/pull/714/merge")):
        deny_event(model, dict(env, **{key: value}))
    for mutate in (
        lambda e: e["pull_request"]["user"].__setitem__("id", 1),
        lambda e: e["pull_request"]["user"].__setitem__("login", "attacker"),
        lambda e: e["pull_request"]["head"]["repo"].__setitem__("full_name", "fork/repo"),
        lambda e: e.__setitem__("number", True),
        lambda e: e.__setitem__("action", "closed"),
    ):
        altered = copy.deepcopy(model)
        mutate(altered)
        deny_event(altered, env)
    good = {"decision": m1.ADMITTED, "review_id": m1.CURRENT_REVIEW,
            "protected_main_sha": base, "bot_base_sha": base, "bot_head_sha": head,
            "actual_merge_base": base, "actual_bot_git_tree_checked": True,
            "automated_bypass_enabled": False, "scientific_experiment_executed": False,
            "action_supply_chain_attested": False, "pin_diff_sha256": "d" * 64,
            "expected_current_base_pin_diff_sha256": "d" * 64,
            "trusted_classifier_sha256": "e" * 64, "trusted_qualifier_sha256": "f" * 64}
    bind_m1(good, base, head, m1)
    for key, value in (
        ("decision", m1.REJECTED), ("review_id", m1.HISTORICAL_REVIEW),
        ("protected_main_sha", "1" * 40), ("bot_head_sha", "2" * 40),
        ("actual_bot_git_tree_checked", False), ("automated_bypass_enabled", True),
        ("scientific_experiment_executed", True), ("trusted_classifier_sha256", ""),
        ("expected_current_base_pin_diff_sha256", "1" * 64),
    ):
        bad = dict(good, **{key: value})
        try:
            bind_m1(bad, base, head, m1)
        except Denied:
            negatives += 1
        else:
            raise Denied("FALSE_M1_RECEIPT_ADMISSION")
    # Test the real Git lineage/tree binder, with only network retrieval replaced
    # by a no-op: these actual objects are explicitly local engineering fixtures.
    with tempfile.TemporaryDirectory(prefix="pin-pr-merge-") as temp:
        area = Path(temp)
        original_git = m1.git
        def local_git(args, **kwargs):
            if args[0] == "fetch":
                return b""
            kwargs.pop("cwd", None)
            return original_git(args, cwd=area, **kwargs)
        m1.git = local_git
        m1.git(["init", "-q"])
        m1.git(["config", "user.email", "test@example.invalid"])
        m1.git(["config", "user.name", "Offline Fixture"])
        (area / "probe").write_text("base\n")
        policy_source = (ROOT / SELF).read_bytes()
        policy_copy = area / SELF
        policy_copy.parent.mkdir(parents=True)
        policy_copy.write_bytes(policy_source)
        m1.git(["add", "."]); m1.git(["commit", "-qm", "base"])
        b = m1.git_sha(["rev-parse", "HEAD"], cwd=area)
        (area / "probe").write_text("head\n")
        m1.git(["add", "."]); m1.git(["commit", "-qm", "head"])
        h = m1.git_sha(["rev-parse", "HEAD"], cwd=area)
        original_root = ROOT
        try:
            globals()["ROOT"] = area
            need(verify_consumer_source(h, m1) == hashlib.sha256(policy_source).hexdigest(),
                 "VALID_PROTECTED_CONSUMER_REJECTED")
            policy_copy.write_bytes(policy_source + b"\n# candidate alteration\n")
            try:
                verify_consumer_source(h, m1)
            except Denied:
                negatives += 1
            else:
                raise Denied("CANDIDATE_CONSUMER_OVERRIDE_ACCEPTED")
            policy_copy.write_bytes(policy_source)
        finally:
            globals()["ROOT"] = original_root
        tree = m1.git_sha(["rev-parse", h + "^{tree}"], cwd=area)
        merged = m1.git(["commit-tree", tree, "-p", b, "-p", h, "-m", "synthetic merge"]).decode().strip()
        bind_event_merge(b, h, merged, m1)
        # Exercise the public positive evaluator with real local Git parents,
        # tree and protected consumer bytes. Only public metadata is an explicit
        # offline fixture; this is no GitHub execution/admission receipt.
        from unittest import mock
        m1.git(["checkout", "-q", b])
        fixture_pr = m1.fake_bot(b, h)
        fixture_m1 = dict(good, protected_main_sha=b, bot_base_sha=b,
                          bot_head_sha=h, actual_merge_base=b)
        fixture_event = dict(model, pull_request=fixture_pr)
        fixture_env = dict(env, GITHUB_SHA=merged)
        with mock.patch.dict(globals(), ROOT=area, load_m1=lambda: m1), \
             mock.patch.multiple(m1, live_probe=lambda **kwargs: fixture_m1,
                                 remote_heads=lambda: (b, h),
                                 fetch_public_bot_pr=lambda: fixture_pr):
            current = evaluate(fixture_event, fixture_env, role)
            repeated = evaluate(fixture_event, dict(fixture_env, GITHUB_RUN_ATTEMPT="3"), role)
        need(current["decision"] == POSITIVE and current["skip_measurement"] is True and
             current["run_id"] == 7300001 and type(current["run_id"]) is int and
             current["run_attempt"] == 2 and type(current["run_attempt"]) is int and
             repeated["run_id"] == current["run_id"] and repeated["run_attempt"] == 3,
             "REAL_GIT_POSITIVE_RUN_RECEIPT_BINDING_FAILED")
        need(json.loads(json.dumps(current))["run_attempt"] != repeated["run_attempt"],
             "REPEATED_ATTEMPT_RECEIPT_NOT_DISTINCT")
        for wrong in (b, h):
            try:
                bind_event_merge(b, h, wrong, m1)
            except Denied:
                negatives += 1
            else:
                raise Denied("NONMERGE_EVENT_ACCEPTED")
        old_tree = m1.git_sha(["rev-parse", b + "^{tree}"], cwd=area)
        for argv in ((old_tree, "-p", b, "-p", h), (tree, "-p", h, "-p", b)):
            wrong = m1.git(["commit-tree", *argv, "-m", "invalid merge"]).decode().strip()
            try:
                bind_event_merge(b, h, wrong, m1)
            except Denied:
                negatives += 1
            else:
                raise Denied("WRONG_EVENT_TREE_OR_PARENT_ACCEPTED")
        m1.git = original_git
    declined = evaluate(model, dict(env, GITHUB_EVENT_NAME="push"), role)
    need(declined["decision"] == NEGATIVE and declined["skip_measurement"] is False and
         declined["scientific_experiment_executed"] is False,
         "NON_PR_EVENT_MAY_SKIP_MEASUREMENT")
    print("T1_M2_PR_CONSUMER_SELF_TEST_PASS negatives=" + str(negatives) +
          " actual_scientific_experiment_executed=false")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--workflow", choices=WORKFLOWS)
    parser.add_argument("--event-file", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--summary-file", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    need(args.workflow and args.event_file and args.receipt, "EVENT_AND_RECEIPT_REQUIRED")
    m1 = load_m1()
    try:
        need(args.event_file.is_file() and not args.event_file.is_symlink() and
             0 < args.event_file.stat().st_size <= MAX_EVENT_BYTES, "EVENT_FILE_INVALID")
        event = json.loads(args.event_file.read_text(encoding="utf-8"), object_pairs_hook=m1.strict_pairs)
        result = evaluate(event, dict(os.environ), args.workflow)
    except (ValueError, OSError, UnicodeError) as exc:
        result = {"schema_version": 1, "decision": NEGATIVE, "skip_measurement": False,
                  "scientific_experiment_executed": False, "acoustic_pass": False,
                  "reason": "EVENT_FILE_NOT_ADMITTED"}
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    need(len(raw.encode()) <= 16_000, "RECEIPT_BOUND_EXCEEDED")
    with args.receipt.open("x", encoding="utf-8") as target:
        target.write(raw)
    for path in (args.github_output, args.summary_file):
        if path is not None:
            need(path.is_file() and not path.is_symlink(), "INVALID_GITHUB_RESULT_FILE")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as target:
            target.write("skip_measurement=" + ("true" if result["skip_measurement"] else "false") + "\n")
    if args.summary_file:
        with args.summary_file.open("a", encoding="utf-8") as target:
            target.write("## Research dependency scope\n\n" + result["decision"] +
                         "\n\nThis receipt is not an acoustic result.\n")
    print(raw, end="")


if __name__ == "__main__":
    main()
