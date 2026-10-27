#!/usr/bin/env python3
"""Offline engineering qualification on real local Git objects, not hosted CI.

Only HTTP/ref retrieval is replaced. Every ancestry, tree, blob, mode and raw
event-range operation executes real Git against a disposable clone of the real
repository history. Clean PR and squash-push controls must pass before mutants.
No original corpus, runner, M1/M2 positive or scientific result is simulated.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("m3_under_test", HERE / "dechorate_event_source_t1m3.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
BASELINE = "b80d819a486cb973e6a60b4fdf259803d45ec3f0"


def git(root: Path, *args: str, data: bytes | None = None) -> str:
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    p = subprocess.run(["git", "-c", "safe.directory=" + str(root), *args], cwd=root,
                       input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env=env, check=False, timeout=45)
    if p.returncode:
        raise RuntimeError("local Git fixture failed: " + args[0])
    return p.stdout.decode().strip()


def ruleset() -> dict:
    return {"id": 21804005, "target": "branch", "source_type": "Repository", "source": M.REPO,
            "enforcement": "active", "bypass_actors": [],
            "conditions": {"ref_name": {"exclude": [], "include": ["refs/heads/main"]}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                      {"type": "pull_request", "parameters": {
                          "allowed_merge_methods": ["squash"], "required_review_thread_resolution": True,
                          "required_approving_review_count": 0}},
                      {"type": "required_status_checks", "parameters": {
                          "strict_required_status_checks_policy": True, "do_not_enforce_on_create": False,
                          "required_status_checks": [{"context": "summary", "integration_id": 15368}]}}]}


class LocalNetworkGit(M.Git):
    def __init__(self, root, model):
        super().__init__(root)
        self.model = model
        self.object_commands = 0
        self.replaced_network_calls = 0

    def run(self, args, **kwargs):
        if args[0] == "fetch":
            self.replaced_network_calls += 1
            return b""  # All exact fixture objects are already in this clone.
        if args[0] == "ls-remote":
            self.replaced_network_calls += 1
            ref = args[2]
            sha = self.model["main"] if ref == "refs/heads/main" else self.model["pr"]["head"]["sha"]
            return (sha + "\t" + ref + "\n").encode()
        self.object_commands += 1
        return super().run(args, **kwargs)


class OfflineMetadata:
    def __init__(self, model):
        self.model = model
        self.main_reads = 0

    def get(self, path):
        if path == "git/ref/heads/main":
            self.main_reads += 1
            if self.main_reads == 2 and self.model.get("on_second"):
                self.model["on_second"](self.model)
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.model["main"]}}
        if path == "rulesets/21804005":
            return copy.deepcopy(self.model["ruleset"])
        if path.startswith("actions/runs/"):
            return copy.deepcopy(self.model["run"])
        if path.startswith("commits/"):
            return copy.deepcopy(self.model["associated"])
        if path.startswith("pulls/"):
            return copy.deepcopy(self.model["pr"])
        raise AssertionError("unexpected local metadata path")


def model_for(root: Path, base: str, head: str, *, push: bool = False) -> tuple[dict, dict, dict]:
    tree = git(root, "rev-parse", head + "^{tree}")
    event_sha = git(root, "commit-tree", tree, "-p", base,
                   *([] if push else ["-p", head]), "-m", "M3 local engineering event")
    repo = {"id": M.REPO_ID, "full_name": M.REPO}
    author = {"id": 99900001, "login": "offline-fixture", "type": "User"}
    pr = {"number": 999001, "draft": False, "state": "closed" if push else "open",
          "merged": push, "merged_at": "2026-10-20T00:00:00Z" if push else None,
          "merge_commit_sha": event_sha, "user": author,
          "base": {"ref": "main", "sha": base, "repo": repo},
          "head": {"ref": "local-m3-fixture", "sha": head, "repo": repo}}
    env = {"GITHUB_REPOSITORY": M.REPO, "GITHUB_SHA": event_sha,
           "GITHUB_RUN_ID": "99900001", "GITHUB_RUN_ATTEMPT": "1"}
    if push:
        event = {"repository": repo, "ref": "refs/heads/main", "before": base, "after": event_sha,
                 "created": False, "deleted": False, "forced": False, "head_commit": {"id": event_sha}}
        env.update(GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main")
    else:
        event = {"repository": repo, "number": pr["number"], "action": "synchronize",
                 "pull_request": copy.deepcopy(pr)}
        env.update(GITHUB_EVENT_NAME="pull_request", GITHUB_REF="refs/pull/999001/merge",
                   GITHUB_BASE_REF="main", GITHUB_HEAD_REF="local-m3-fixture")
    env["GITHUB_WORKFLOW_REF"] = M.REPO + "/" + M.WORKFLOW + "@" + env["GITHUB_REF"]
    model = {"main": event_sha if push else base, "pr": pr, "ruleset": ruleset(),
             "associated": [copy.deepcopy(pr)],
             "run": {"id": 99900001, "run_attempt": 1, "repository": repo, "head_repository": repo,
                     "event": "push" if push else "pull_request", "path": M.WORKFLOW,
                     "head_sha": event_sha if push else head,
                     "head_branch": "main" if push else "local-m3-fixture",
                     "status": "in_progress", "conclusion": None}}
    return event, env, model


def run_suite() -> dict:
    failures = []
    positives = []
    v2_controls = []
    counts = {"actual_git_commands": 0, "offline_network_replacements": 0}
    with tempfile.TemporaryDirectory(prefix="t1-m3-real-git-") as temporary:
        area = Path(temporary) / "repo"
        git(Path(temporary), "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(area))
        git(area, "config", "user.email", "offline@example.invalid")
        git(area, "config", "user.name", "M3 Offline Engineering Fixture")
        git(area, "checkout", "--quiet", "--detach", BASELINE)
        for path in (M.SELF, M.CONTRACT):
            (area / path).write_bytes((ROOT / path).read_bytes())
        git(area, "add", M.SELF, M.CONTRACT)
        git(area, "commit", "--quiet", "-m", "local engineering protected-policy fixture")
        base = git(area, "rev-parse", "HEAD")
        original_workflow = (area / M.WORKFLOW).read_text()
        original_science = (area / M.SCIENCE).read_text()

        def changed(parent: str, changes: dict, *, modes: dict | None = None) -> str:
            git(area, "reset", "--hard", parent)
            for name, value in changes.items():
                path = area / name
                if path.exists() or path.is_symlink():
                    path.unlink()
                if value is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if (modes or {}).get(name) == "symlink":
                        path.symlink_to(value)
                    else:
                        path.write_text(value)
                        if (modes or {}).get(name) == "executable":
                            path.chmod(0o755)
            git(area, "add", "--all")
            tree = git(area, "write-tree")
            sha = git(area, "commit-tree", tree, "-p", parent, "-m", "local engineering mutant")
            git(area, "reset", "--hard", base)
            return sha

        head = changed(base, {M.WORKFLOW: "# Current-event-only engineering fixture.\n" + original_workflow})
        pr_case = model_for(area, base, head)
        push_case = model_for(area, base, head, push=True)

        def observe(case, *, checkout=base):
            event, env, metadata = copy.deepcopy(case)
            git(area, "reset", "--hard", checkout)
            engine = LocalNetworkGit(area, metadata)
            result = M.evaluate(event, env, engine, OfflineMetadata(metadata))
            counts["actual_git_commands"] += engine.object_commands
            counts["offline_network_replacements"] += engine.replaced_network_calls
            return result

        def positive(name, case, *, checkout=base):
            result = observe(case, checkout=checkout)
            assert result["decision"] == M.POSITIVE and result["source_range_qualified"] is True, (name, result)
            assert all(result[key] is False for key in ("skip_measurement", "maintenance_push_admitted",
                       "automated_bypass_enabled", "scientific_experiment_executed", "acoustic_pass",
                       "corpus_materialized_or_verified", "live_public_metadata_checked",
                       "workflow_hookup_admitted", "m1_m2_prerequisites_closed"))
            prerequisite = result["frozen_source"]["protected_m2_source_identity"]
            if prerequisite is not None:
                assert prerequisite["actual_m1_prerequisite_observed_by_this_helper"] is False
                assert prerequisite["protected_main_closure_observed_by_this_helper"] is False
                assert prerequisite["independent_hookup_prerequisites_still_required"] is True
            positives.append({"name": name, "result": result})

        def negative(name, case, expected, *, checkout=base):
            result = observe(case, checkout=checkout)
            assert result["decision"] == M.NEGATIVE and result["source_range_qualified"] is False, (name, result)
            assert result["reason"] in expected, (name, result["reason"], expected)
            assert result["skip_measurement"] is False and result["scientific_experiment_executed"] is False
            failures.append({"name": name, "reason": result["reason"]})

        positive("clean_direct_pr_actual_two_parent_event", pr_case)
        positive("clean_main_push_actual_single_parent_squash", push_case)
        historical = git(area, "diff", "--name-only", M.FROZEN_BASE + "..." + head).splitlines()
        assert set(historical) - {M.SCIENCE, M.MANIFEST, M.WORKFLOW}
        assert len(historical) > 3  # Old guard actually rejects the clean control.
        templates = M.workflow_templates(original_workflow)
        for profile in ("EXACT_PROTECTED_SOURCE_BINDING:original-pins",
                        "ORIGINAL_FROZEN_WORKFLOW:reviewed-2026-10-20-pins",
                        "EXACT_PROTECTED_SOURCE_BINDING:reviewed-2026-10-20-pins"):
            repaired_head = changed(base, {M.WORKFLOW: templates[profile]})
            positive("exact_template_pr_" + profile, model_for(area, base, repaired_head))
        repaired_head = changed(base, {M.WORKFLOW: templates["EXACT_PROTECTED_SOURCE_BINDING:original-pins"]})
        positive("exact_source_binding_main_push", model_for(area, base, repaired_head, push=True))

        # This source profile is usable only after its exact first-party M2/M1
        # bytes are in the protected event base. Copy real frozen Git blobs into
        # an explicitly local engineering source fixture; never invent M1/M2
        # admission, protected-main Verify/Release, or scientific execution.
        contract = json.loads((ROOT / M.CONTRACT).read_bytes())
        gated = templates[M.M2_PROFILE + ":original-pins"]
        unprotected_head = changed(base, {M.WORKFLOW: gated})
        negative("exact_m2_template_missing_protected_source", model_for(area, base, unprotected_head),
                 {"M2_SOURCE_NOT_IN_PROTECTED_EVENT_BASE", "M2_PROTECTED_SOURCE_CLOSURE_DRIFT"})
        closure = contract["preregistered_m2_source_closure"]["files"]
        source_copies = {path: M.Git(area).run(["cat-file", "blob", identity["git_blob"]]).decode()
                         for path, identity in closure.items()}
        for path, raw in source_copies.items():
            assert hashlib.sha256(raw.encode()).hexdigest() == closure[path]["sha256"]
        m2_base = changed(base, source_copies)
        for pins in ("original-pins", "reviewed-2026-10-20-pins"):
            profile = M.M2_PROFILE + ":" + pins
            gated_head = changed(m2_base, {M.WORKFLOW: templates[profile]})
            positive("exact_m2_source_template_pr_" + pins, model_for(area, m2_base, gated_head), checkout=m2_base)
            positive("exact_m2_source_template_push_" + pins,
                     model_for(area, m2_base, gated_head, push=True), checkout=m2_base)
        # Preserve the earlier source registration as historical evidence, but
        # never accept it (or a mixture of its real blobs) as the current core.
        historical_closures = contract["historical_m2_source_closures"]
        assert len(historical_closures) == 1 and historical_closures[0]["review_id"] == "2026-10-20"
        previous = historical_closures[0]
        assert previous["source_review_commit"] == "a42427693484409f9954125dada37d5db6c6f51e"
        old_copies = {path: M.Git(area).run(["cat-file", "blob", identity["git_blob"]]).decode()
                      for path, identity in previous["files"].items()}
        for path, raw in old_copies.items():
            assert hashlib.sha256(raw.encode()).hexdigest() == previous["files"][path]["sha256"]
        for name, registration in (
                ("previous_registration", previous),
                ("previous_source_commit", dict(contract["preregistered_m2_source_closure"],
                                               source_review_commit=previous["source_review_commit"]))):
            old_contract = dict(contract, preregistered_m2_source_closure=registration)
            old_base = changed(m2_base, {M.CONTRACT: json.dumps(old_contract, sort_keys=True, indent=2) + "\n"})
            old_head = changed(old_base, {M.WORKFLOW: gated})
            negative("m2_reject_" + name, model_for(area, old_base, old_head),
                     {"M2_SOURCE_PREREGISTRATION_DRIFT"}, checkout=old_base)
        old_base = changed(m2_base, dict(old_copies,
            **{".github/program/workflow_pin_only_bot714_20261024.json": None}))
        old_head = changed(old_base, {M.WORKFLOW: gated})
        negative("m2_previous_complete_core_not_current", model_for(area, old_base, old_head),
                 {"M2_PROTECTED_SOURCE_CLOSURE_DRIFT"}, checkout=old_base)
        for path in M.M2_SOURCE_FILES:
            old_path = path.replace("_20261024.json", "_20261020.json")
            if old_copies[old_path] == source_copies[path]:
                continue
            mixed_base = changed(m2_base, {path: old_copies[old_path]})
            mixed_head = changed(mixed_base, {M.WORKFLOW: gated})
            negative("m2_previous_blob_mixed_" + Path(path).name,
                     model_for(area, mixed_base, mixed_head), {"M2_PROTECTED_SOURCE_CLOSURE_DRIFT"},
                     checkout=mixed_base)
        for path in M.M2_SOURCE_FILES:
            corrupt_base = changed(m2_base, {path: source_copies[path] + "\n"})
            corrupt_head = changed(corrupt_base, {M.WORKFLOW: gated})
            negative("m2_base_source_bytes_" + Path(path).name,
                     model_for(area, corrupt_base, corrupt_head), {"M2_PROTECTED_SOURCE_CLOSURE_DRIFT"},
                     checkout=corrupt_base)
        for mode in ("executable", "symlink"):
            path = M.M2_SOURCE_FILES[0]
            value = source_copies[path] if mode == "executable" else "workflow_pin_only_actual_tree_t1m1.py"
            corrupt_base = changed(m2_base, {path: value}, modes={path: mode})
            corrupt_head = changed(corrupt_base, {M.WORKFLOW: gated})
            negative("m2_base_consumer_" + mode, model_for(area, corrupt_base, corrupt_head),
                     {"M2_SOURCE_NOT_IN_PROTECTED_EVENT_BASE"}, checkout=corrupt_base)

        # Register a complete v2 consumer without weakening any old template.
        # These controls establish frozen source/template identity only. The
        # separate transport suite acquires explicitly offline API fixtures.
        prior_contract = json.loads(git(area, "show", "5187c5e59526d4047b3965b44c770ab21edbde9f:" + M.CONTRACT))
        assert all(contract["workflow_execution_template_sha256"][key] == value
                   for key, value in prior_contract["workflow_execution_template_sha256"].items())
        v2 = templates[M.V2_PROFILE + ":original-pins"]
        missing_v2 = changed(m2_base, {M.WORKFLOW: v2})
        negative("v2_missing_protected_transport_source", model_for(area, m2_base, missing_v2),
                 {"SOURCE_BLOB_MODE_OR_TYPE_DRIFT"}, checkout=m2_base)
        v2_copies = {path: (ROOT / path).read_text() for path in M.V2_SOURCE_FILES}
        v2_base = changed(m2_base, v2_copies)
        for pins in ("original-pins", "reviewed-2026-10-20-pins"):
            v2_head = changed(v2_base, {M.WORKFLOW: templates[M.V2_PROFILE + ":" + pins]})
            frozen = M.frozen_science(M.Git(area), v2_base, v2_head, contract)
            assert frozen["workflow_execution_profiles"]["head"] == M.V2_PROFILE + ":" + pins
            assert set(frozen["protected_v2_source_identity"]) == set(M.V2_SOURCE_FILES)
            assert frozen["original_scientific_steps"] == 7
            v2_controls.append({"profile": M.V2_PROFILE + ":" + pins,
                                "source_only_frozen_identity": True,
                                "authenticated_governance_or_measurement_claimed": False})
        for name, candidate in (
            ("v2_no_actions_read", v2.replace("  actions: read\n", "", 1)),
            ("v2_privileged_token_in_consumer", v2.replace("${{ github.token }}", "${{ secrets.REPOSITORY_GOVERNANCE_TOKEN }}", 1)),
            ("v2_old_helper_substitution", v2.replace("dechorate_governance_v2.py'),'consumer'", "dechorate_event_source_t1m3.py'),'consumer'", 1)),
            ("v2_attemptless_artifact", v2.replace("dechorate-event-source-range-${{ github.run_id }}-${{ github.run_attempt }}", "dechorate-event-source-range-${{ github.run_id }}", 1)),
        ):
            assert candidate != v2
            mutant = changed(v2_base, {M.WORKFLOW: candidate})
            negative(name, model_for(area, v2_base, mutant), {"WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"},
                     checkout=v2_base)

        # The fixed Bind program actually creates its exact base worktree and
        # preserves a negative source receipt. A deliberately invalid repository
        # event is denied before any network retrieval, so this integration test
        # cannot fabricate a real hosted source observation.
        git(area, "reset", "--hard", head)
        bind_event, bind_env, _ = copy.deepcopy(pr_case)
        bind_event["repository"]["full_name"] = "offline/not-the-authorized-repository"
        bind_event_path = Path(temporary) / "bind-denied-event.json"
        bind_event_path.write_text(json.dumps(bind_event))
        bind_env.update(os.environ)
        bind_env.update(pr_case[1], GITHUB_EVENT_PATH=str(bind_event_path),
                        RUNNER_TEMP=temporary, EXPECTED_SHA=head)
        shell = "\n".join(line[10:] for line in M.SOURCE_BIND_TEMPLATE.split("        run: |\n", 1)[1].splitlines()) + "\n"
        bound = subprocess.run(["bash", "-c", shell], cwd=area, env=bind_env,
                               capture_output=True, timeout=60, check=False)
        assert bound.returncode != 0, "fixed Bind must propagate the real helper denial"
        bound_receipt = area / "dechorate-ground-truth-v1-out/source-range.json"
        bound_result = json.loads(bound_receipt.read_bytes())
        assert bound_result["reason"] == "UNTRUSTED_EVENT_REPOSITORY" and bound_result["skip_measurement"] is False
        assert bound_receipt.with_name(bound_receipt.name + ".sha256").read_text().startswith(
            hashlib.sha256(bound_receipt.read_bytes()).hexdigest())
        failures.append({"name": "fixed_bind_real_worktree_and_denial_receipt", "reason": bound_result["reason"]})

        for kind in ("workflow_call", "workflow_dispatch", "pull_request_target", "repository_dispatch"):
            case = copy.deepcopy(pr_case)
            case[1]["GITHUB_EVENT_NAME"] = kind
            negative("non_direct_" + kind, case, {"UNQUALIFIED_EVENT_KIND"})
        for key, value, reason in (
            ("GITHUB_SHA", "a" * 7, "FULL_NONZERO_COMMIT_OID_REQUIRED"),
            ("GITHUB_HEAD_REF", "stale-head", "PR_REPOSITORY_OR_BRANCH_DRIFT"),
            ("GITHUB_WORKFLOW_REF", M.REPO + "/.github/workflows/pcr02-dsp-counterfactuals.yml@refs/pull/999001/merge",
             "REUSABLE_OR_UNEXPECTED_WORKFLOW_CONTEXT"),
            ("GITHUB_RUN_ID", "", "RUN_SCOPED_IDENTITY_REQUIRED"),
        ):
            case = copy.deepcopy(pr_case)
            case[1][key] = value
            negative("pr_context_" + key.lower(), case, {reason})
        for key in ("created", "deleted", "forced"):
            case = copy.deepcopy(push_case)
            case[0][key] = True
            negative("push_" + key, case, {"PUSH_NOT_EXISTING_NONFORCED_MAIN"})
        for key, value, reason in (
            ("before", "0" * 40, "FULL_NONZERO_COMMIT_OID_REQUIRED"),
            ("before", "main", "FULL_NONZERO_COMMIT_OID_REQUIRED"),
            ("after", base, "PUSH_AFTER_NOT_EVENT_COMMIT"),
            ("ref", "refs/heads/other", "PUSH_NOT_EXISTING_NONFORCED_MAIN"),
        ):
            case = copy.deepcopy(push_case)
            case[0][key] = value
            negative("push_event_" + key + "_" + value[:8], case, {reason})
        case = copy.deepcopy(pr_case)
        case[0]["repository"]["id"] = True
        negative("boolean_repository_identity", case, {"UNTRUSTED_EVENT_REPOSITORY"})
        case = copy.deepcopy(pr_case)
        case[0]["pull_request"]["head"]["repo"]["full_name"] = "fork/audio-pipeline"
        negative("fork_pr_event", case, {"PR_REPOSITORY_OR_BRANCH_DRIFT", "UNTRUSTED_EVENT_REPOSITORY"})
        case = copy.deepcopy(pr_case)
        case[2]["pr"]["user"]["id"] += 1
        negative("same_login_spoofed_live_author_id", case, {"LIVE_PR_SOURCE_OR_EVENT_METADATA_DRIFT"})
        case = copy.deepcopy(pr_case)
        case[2]["on_second"] = lambda x: x.__setitem__("main", head)
        negative("main_moves_after_positive_first_snapshot", case, {"MAIN_MOVED_OUTSIDE_CURRENT_EVENT"})
        case = copy.deepcopy(pr_case)
        case[2]["on_second"] = lambda x: x["pr"]["head"].__setitem__("sha", base)
        negative("pr_head_moves_after_first_snapshot", case, {"LIVE_PR_SOURCE_OR_EVENT_METADATA_DRIFT"})
        for key, value in (("id", 99900002), ("run_attempt", 2), ("head_sha", base),
                           ("event", "workflow_dispatch"), ("path", ".github/workflows/pcr02-dsp-counterfactuals.yml"),
                           ("status", "completed"), ("conclusion", "success")):
            case = copy.deepcopy(pr_case)
            case[2]["run"][key] = value
            negative("run_identity_" + key, case, {"CURRENT_RUN_IDENTITY_OR_EXECUTION_CONTEXT_DRIFT"})

        for name, change, modes, reason in (
            ("mixed_c_source", {"src/m3_mixed.c": "/* engineering negative */\n"}, None,
             "CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW"),
            ("workflow_executable", {}, {M.WORKFLOW: "executable"},
             "CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW"),
            ("workflow_symlink", {M.WORKFLOW: "../program/dechorate_event_source_t1m3.py"}, {M.WORKFLOW: "symlink"},
             "CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW"),
            ("workflow_deleted", {M.WORKFLOW: None}, None,
             "CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW"),
            ("workflow_renamed", {M.WORKFLOW: None, ".github/workflows/m3-renamed.yml": original_workflow}, None,
             "CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW"),
            ("permission_write", {M.WORKFLOW: original_workflow.replace("contents: read", "contents: write")}, None,
             "WORKFLOW_TOKEN_PERMISSION_DRIFT"),
            ("unreviewed_scientific_checkout", {M.WORKFLOW: original_workflow.replace(
                "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09", "actions/checkout@" + "9" * 40)}, None,
             "ORIGINAL_SCIENTIFIC_STEP_BODY_DRIFT"),
            ("scientific_run_changed", {M.WORKFLOW: original_workflow.replace("--self-test\n", "--help\n")}, None,
             "ORIGINAL_SCIENTIFIC_STEP_BODY_DRIFT"),
            ("scientific_step_removed", {M.WORKFLOW: original_workflow.replace("      - name: Run fixed-geometry RIR ground-truth diagnostic",
                                                                                 "      - name: Removed scientific execution")}, None,
             "ORIGINAL_SCIENTIFIC_STEP_MISSING_OR_DUPLICATED"),
            ("job_permissions_override", {M.WORKFLOW: original_workflow.replace("  diagnostic:\n", "  diagnostic:\n    permissions:\n      contents: write\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_if_false", {M.WORKFLOW: original_workflow.replace("  diagnostic:\n", "  diagnostic:\n    if: false\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_continue_on_error", {M.WORKFLOW: original_workflow.replace("  diagnostic:\n", "  diagnostic:\n    continue-on-error: true\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_runner_changed", {M.WORKFLOW: original_workflow.replace("runs-on: ubuntu-24.04", "runs-on: self-hosted", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_timeout_changed", {M.WORKFLOW: original_workflow.replace("timeout-minutes: 30", "timeout-minutes: 1", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_defaults_override", {M.WORKFLOW: original_workflow.replace("  diagnostic:\n", "  diagnostic:\n    defaults:\n      run:\n        shell: bash {0}\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_environment_override", {M.WORKFLOW: original_workflow.replace("  diagnostic:\n", "  diagnostic:\n    env:\n      BASH_ENV: /tmp/override\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("job_container_override", {M.WORKFLOW: original_workflow.replace("  diagnostic:\n", "  diagnostic:\n    container: ubuntu:latest\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("bind_rewrites_scientific_source", {M.WORKFLOW: original_workflow.replace("          set -euo pipefail\n", "          set -euo pipefail\n          printf 'changed' > " + M.SCIENCE + "\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("bind_forges_source_receipt", {M.WORKFLOW: original_workflow.replace("          set -euo pipefail\n", "          set -euo pipefail\n          printf 'forged' > source-range.json\n", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("unreviewed_upload_pin", {M.WORKFLOW: original_workflow.replace(M.UPLOAD_OLD, "1" * 40)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
            ("extra_executable_step", {M.WORKFLOW: original_workflow.replace("      - name: Bind diagnostic", "      - name: Injected\n        run: echo changed\n\n      - name: Bind diagnostic", 1)}, None,
             "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"),
        ):
            source = {M.WORKFLOW: "# current-event mutant\n" + original_workflow}
            source.update(change)
            mutated = changed(base, source, modes=modes)
            negative(name, model_for(area, base, mutated), {reason})

        for name, candidate in (
            ("m2_gate_if_false", gated.replace(M.M2_DIAGNOSTIC_CONDITION, "    needs: maintenance\n    if: false\n", 1)),
            ("m2_gate_ignores_success", gated.replace("needs.maintenance.result == 'success' && ", "", 1)),
            ("m2_maintenance_accepts_push", gated.replace("if: github.event_name == 'pull_request'", "if: github.event_name == 'push'", 1)),
            ("m2_consumer_from_candidate_head", gated.replace("ref: ${{ github.event.pull_request.base.sha }}", "ref: ${{ github.event.pull_request.head.sha }}", 1)),
            ("m2_partial_upload_transition", gated.replace(
                "uses: actions/upload-artifact@" + M.UPLOAD_OLD + " # v7.0.1",
                "uses: actions/upload-artifact@" + M.UPLOAD_NEW + " # v7.0.2", 1)),
            ("source_bind_arbitrary_shell", gated.replace("          python3 - <<'PY'\n", "          echo injected\n          python3 - <<'PY'\n", 1)),
        ):
            mutant = changed(m2_base, {M.WORKFLOW: candidate})
            negative(name, model_for(area, m2_base, mutant), {"WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"},
                     checkout=m2_base)

        for label, separator in (("nel", "\u0085"), ("line_separator", "\u2028"), ("paragraph_separator", "\u2029")):
            prefix = "# apparent comment" + separator + "env:" + separator + \
                     "  BASH_ENV: /tmp/unexecuted-review-only" + separator + "# comment\n"
            mutant = changed(base, {M.WORKFLOW: prefix + original_workflow})
            negative("yaml_unicode_comment_" + label, model_for(area, base, mutant),
                     {"WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED"})

        git(area, "reset", "--hard", base)
        git(area, "update-index", "--cacheinfo", "160000," + head + "," + M.WORKFLOW)
        link_tree = git(area, "write-tree")
        gitlink = git(area, "commit-tree", link_tree, "-p", base, "-m", "actual gitlink mode negative")
        git(area, "reset", "--hard", base)
        negative("workflow_submodule_gitlink", model_for(area, base, gitlink),
                 {"CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW"})

        for path, name in ((M.SCIENCE, "inherited_science_edit"), (M.MANIFEST, "inherited_experiment_manifest_edit"),
                           (M.QUALIFICATION, "inherited_source_manifest_edit")):
            original = git(area, "show", base + ":" + path) + "\n"
            # The corruption is IN THE NEW BASE, not in the event diff. A
            # one-workflow range alone would falsely pass these three cases.
            altered_base = changed(base, {path: original + "\n"})
            altered_head = changed(altered_base, {M.WORKFLOW: "# bounded current event\n" + original_workflow})
            negative(name, model_for(area, altered_base, altered_head),
                     {"SCIENTIFIC_SOURCE_OR_MANIFEST_CHANGED"}, checkout=altered_base)

        for name, parents, tree, reason in (
            ("pr_wrong_parent_order", [head, base], git(area, "rev-parse", head + "^{tree}"), "PR_EVENT_MERGE_PARENT_DRIFT"),
            ("pr_single_parent", [base], git(area, "rev-parse", head + "^{tree}"), "PR_EVENT_MERGE_PARENT_DRIFT"),
            ("pr_wrong_merge_tree", [base, head], git(area, "rev-parse", base + "^{tree}"), "PR_EVENT_MERGE_TREE_DRIFT"),
        ):
            argv = ["commit-tree", tree]
            for parent in parents:
                argv.extend(["-p", parent])
            forged = git(area, *argv, "-m", "malformed engineering PR event")
            case = copy.deepcopy(pr_case)
            case[1]["GITHUB_SHA"] = forged
            case[2]["pr"]["merge_commit_sha"] = forged
            negative(name, case, {reason})
        tag_data = ("object " + pr_case[1]["GITHUB_SHA"] + "\ntype commit\ntag m3-local-fixture\n"
                    "tagger Local Fixture <offline@example.invalid> 1 +0000\n\nnot a commit event\n").encode()
        tag = git(area, "mktag", data=tag_data)
        case = copy.deepcopy(pr_case)
        case[1]["GITHUB_SHA"] = tag
        case[2]["pr"]["merge_commit_sha"] = tag
        negative("annotated_tag_as_event_commit", case, {"EVENT_OBJECT_NOT_A_COMMIT"})
        case = copy.deepcopy(pr_case)
        absent = "1" * 40
        case[0]["pull_request"]["head"]["sha"] = absent
        case[2]["pr"]["head"]["sha"] = absent
        case[2]["run"]["head_sha"] = absent
        negative("missing_full_git_object", case, {"GIT_COMMAND_FAILED_OR_OVERSIZED"})
        case = copy.deepcopy(push_case)
        wrong_push = pr_case[1]["GITHUB_SHA"]
        case[0].update(after=wrong_push, head_commit={"id": wrong_push})
        case[1]["GITHUB_SHA"] = wrong_push
        case[2]["main"] = wrong_push
        case[2]["pr"]["merge_commit_sha"] = wrong_push
        case[2]["associated"][0]["merge_commit_sha"] = wrong_push
        case[2]["run"]["head_sha"] = wrong_push
        negative("push_two_parent_merge", case, {"PUSH_NOT_EXACT_SINGLE_PARENT_TRANSITION"})
        case = copy.deepcopy(push_case)
        later = git(area, "commit-tree", git(area, "rev-parse", head + "^{tree}"),
                    "-p", head, "-m", "two commits since pushed before")
        case[0].update(after=later, head_commit={"id": later})
        case[1]["GITHUB_SHA"] = later
        case[2]["main"] = later
        case[2]["pr"]["merge_commit_sha"] = later
        case[2]["associated"][0]["merge_commit_sha"] = later
        case[2]["run"]["head_sha"] = later
        negative("push_before_not_direct_parent", case, {"PUSH_NOT_EXACT_SINGLE_PARENT_TRANSITION"})
        case = copy.deepcopy(push_case)
        case[2]["pr"]["head"]["sha"] = base
        negative("push_tree_not_actual_merged_pr_tree", case, {"MERGED_PR_HEAD_NOT_PUSH_TREE"})
        for key, value, reason in (("merged", False, "PUSH_NOT_ASSOCIATED_MERGED_PR"),
                                    ("state", "open", "PUSH_NOT_ASSOCIATED_MERGED_PR")):
            case = copy.deepcopy(push_case)
            case[2]["pr"][key] = value
            negative("push_pr_" + key, case, {reason})
        case = copy.deepcopy(push_case)
        case[2]["associated"].append(copy.deepcopy(case[2]["associated"][0]))
        negative("ambiguous_push_pr", case, {"AMBIGUOUS_MERGED_PUSH_PR"})

        for key, value in (("enforcement", "disabled"), ("bypass_actors", [{"actor_id": 1}])):
            case = copy.deepcopy(pr_case)
            case[2]["ruleset"][key] = value
            negative("ruleset_" + key, case, {"MAIN_RULESET_IDENTITY_OR_BYPASS_DRIFT"})
        case = copy.deepcopy(pr_case)
        case[2]["ruleset"]["rules"][3]["parameters"]["strict_required_status_checks_policy"] = False
        negative("non_strict_summary_policy", case, {"STRICT_MAIN_MERGE_POLICY_DRIFT"})
        case = copy.deepcopy(pr_case)
        case[2]["ruleset"]["rules"][3]["parameters"]["required_status_checks"][0]["integration_id"] = 1
        negative("spoofed_summary_application", case, {"STRICT_MAIN_MERGE_POLICY_DRIFT"})

        for path in (M.SELF, M.CONTRACT):
            git(area, "reset", "--hard", base)
            target = area / path
            target.write_bytes(target.read_bytes() + b"\n")
            event, env, metadata = copy.deepcopy(pr_case)
            engine = LocalNetworkGit(area, metadata)
            result = M.evaluate(event, env, engine, OfflineMetadata(metadata))
            assert result["reason"] == "UNPROTECTED_SOURCE_HELPER_OR_CONTRACT", result
            failures.append({"name": "uncommitted_override_" + Path(path).name, "reason": result["reason"]})
        git(area, "reset", "--hard", base)
        shallow = area / ".git/shallow"
        shallow.write_text(base + "\n")
        try:
            event, env, metadata = copy.deepcopy(pr_case)
            engine = LocalNetworkGit(area, metadata)
            result = M.evaluate(event, env, engine, OfflineMetadata(metadata))
            assert result["reason"] == "INCOMPLETE_GIT_HISTORY", result
            failures.append({"name": "actual_shallow_git_boundary", "reason": result["reason"]})
        finally:
            shallow.unlink()
        positive("clean_control_after_all_git_mutants", pr_case)

        # A negative receipt must survive a second invocation; no silent
        # overwrite turns an old failure into a new success.
        event_file = Path(temporary) / "duplicate-event.json"
        event_file.write_text('{"repository": {}, "repository": {}}')
        receipt_file = Path(temporary) / "negative.json"
        command = [sys.executable, str(HERE / "dechorate_event_source_t1m3.py"),
                   "--event-file", str(event_file), "--receipt", str(receipt_file)]
        first = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=45, check=False)
        assert first.returncode == 1, first.stderr
        received = json.loads(receipt_file.read_text())
        assert received["reason"] == "DUPLICATE_JSON_KEY" and received["source_range_qualified"] is False
        raw = receipt_file.read_bytes()
        assert receipt_file.with_name(receipt_file.name + ".sha256").read_text().startswith(hashlib.sha256(raw).hexdigest())
        second = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=45, check=False)
        assert second.returncode == 2 and receipt_file.read_bytes() == raw
        failures.append({"name": "real_cli_duplicate_json", "reason": received["reason"]})
        failures.append({"name": "real_cli_existing_failure_receipt", "reason": "PREVIOUS_RECEIPT_PRESERVED"})

    return {"schema_version": 1, "decision": "T1_M3_OFFLINE_REAL_GIT_SOURCE_RANGE_TESTS_PASS",
            "source_base_sha": BASELINE, "helper_sha256": hashlib.sha256((ROOT / M.SELF).read_bytes()).hexdigest(),
            "contract_sha256": hashlib.sha256((ROOT / M.CONTRACT).read_bytes()).hexdigest(),
            "nonvacuous_controls": positives, "v2_complete_template_source_controls": v2_controls,
            "old_guard_changed_path_count": len(historical),
            "old_guard_would_reject_clean_control": True, "negative_count": len(failures), "negatives": failures,
            "execution": counts, "metadata_role": "offline engineering fixtures only",
            "public_event_observed": False, "scientific_experiment_executed": False,
            "maintenance_push_admitted": False, "shipping_or_physical_authority": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not (args.output or args.self_test):
        parser.error("--self-test or --output is required")
    result = run_suite()
    # The full test record contains both positive receipts and every negative.
    # It is not the <=16,000-byte workflow source receipt consumed by a gate.
    raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
    assert len(raw) < 100_000
    sha = hashlib.sha256(raw).hexdigest()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(raw)
        with args.output.with_name(args.output.name + ".sha256").open("x") as stream:
            stream.write(sha + "  " + args.output.name + "\n")
    print(json.dumps({"decision": result["decision"], "negative_count": result["negative_count"],
                      "controls": len(result["nonvacuous_controls"]), "receipt_sha256": sha,
                      "scientific_experiment_executed": False}, sort_keys=True))


if __name__ == "__main__":
    main()
