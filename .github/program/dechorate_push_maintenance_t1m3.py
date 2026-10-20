#!/usr/bin/env python3
"""Dormant T1-M3 exact merged-714 push maintenance consumer.

The checked-in registry is PENDING. No workflow calls this helper. A future
separately protected registry and workflow-only integration must preserve the
original science. A positive is a nonmeasurement disposition, never an acoustic
PASS. Candidate Git objects and artifact JSON are data, never imported code.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import types
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
SELF = ".github/program/dechorate_push_maintenance_t1m3.py"
REGISTRY = ".github/program/dechorate_push_maintenance_t1m3.json"
SOURCE = ".github/program/dechorate_event_source_t1m3.py"
SOURCE_CONTRACT = ".github/program/dechorate_event_source_t1m3.json"
M1 = ".github/program/workflow_pin_only_actual_tree_t1m1.py"
T0 = ".github/program/workflow_pin_only_scope.py"
WITNESS = ".github/program/workflow_pin_only_bot714_20261020.json"
M2 = ".github/program/workflow_pin_pr_consumer.py"
M2_FILES = (M1, T0, WITNESS, M2)
REPO = "jiying2007/audio-pipeline"
REPO_ID = 1347377137
BOT = {"login": "dependabot[bot]", "id": 49699333, "type": "Bot"}
BOT_REF = "dependabot/github_actions/actions-non-major-5b90254856"
WORKFLOW = ".github/workflows/research-dechorate-ground-truth-diagnostic-v1.yml"
WORKFLOWS = (
    ".github/workflows/pcr02-aec-real-tail-confirmation.yml",
    ".github/workflows/pcr02-dsp-counterfactuals.yml",
    WORKFLOW,
)
SCIENCE_JOBS = {
    WORKFLOWS[0]: {"confirm"},
    WORKFLOWS[1]: {"contracts", "bf-geometry", "aec-tail", "ns-vad"},
    WORKFLOWS[2]: {"diagnostic"},
}
POSITIVE = "SCIENCE_NOT_EXECUTED_NON_MEASUREMENT_MAIN_PUSH"
NEGATIVE = "ORIGINAL_RESEARCH_GUARDS_REQUIRED"
REVIEW = "2026-10-20"
PROFILE = "EXACT_SOURCE_BINDING_WITH_DIRECT_PR_M2_AND_MAIN_PUSH_M3"
MAX_JSON = 150_000
MAX_ZIP = 65_536
MAX_RECEIPT = 16_000
CLI_SECONDS = 240
SHA = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


class Denied(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Denied(code)


def oid(value):
    need(type(value) is str and SHA.fullmatch(value) is not None and value != "0" * 40,
         "FULL_NONZERO_COMMIT_OID_REQUIRED")
    return value


def positive_id(value):
    need(type(value) is int and 0 < value < 10**19, "CANONICAL_INTEGER_ID_REQUIRED")
    return value


def actor(value):
    need(type(value) is dict and type(value.get("login")) is str and
         re.fullmatch(r"[A-Za-z0-9_\[\]-]{1,100}", value["login"]) is not None and
         value.get("type") in ("User", "Bot"), "ACTOR_IDENTITY_MISSING")
    return {"login": value["login"], "id": positive_id(value.get("id")), "type": value["type"]}


def same_repo(value):
    return (type(value) is dict and value.get("full_name") == REPO and
            type(value.get("id")) is int and value["id"] == REPO_ID)


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def no_constant(_value):
    raise Denied("NONFINITE_JSON_CONSTANT")


def parse_json(raw, *, object_only=True, maximum=MAX_JSON):
    need(type(raw) is bytes and 0 < len(raw) <= maximum, "JSON_SIZE_BOUND")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs, parse_constant=no_constant)
    need(not object_only or type(value) is dict, "JSON_OBJECT_REQUIRED")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def bootstrap_git(root, args):
    """Minimal pre-import Git read; the qualified source helper owns later IO."""
    forbidden = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_DIR", "GIT_WORK_TREE",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                 "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE")
    need(not any(os.environ.get(key) for key in forbidden), "EXTERNAL_GIT_CONTEXT_NOT_TRUSTED")
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
               GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(["git", "--no-replace-objects", "-c", "safe.directory=" + str(root),
            "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "credential.helper=",
            *args], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Denied("GIT_BOOTSTRAP_IO_OR_TIMEOUT") from None
    need(done.returncode == 0 and len(done.stdout) < MAX_JSON and len(done.stderr) < MAX_JSON,
         "GIT_BOOTSTRAP_FAILED_OR_OVERSIZED")
    return done.stdout


def protected_local(root, base, path, read):
    entry = read(["ls-tree", base, "--", path]).decode("ascii")
    match = re.fullmatch(r"100644 blob ([0-9a-f]{40})\t" + re.escape(path) + r"\n", entry)
    need(match is not None, "PROTECTED_SOURCE_MODE_OR_TYPE_DRIFT")
    raw = read(["show", base + ":" + path])
    local = root / path
    need(local.resolve() == local and local.is_file() and not local.is_symlink() and
         local.stat().st_size == len(raw), "EXECUTED_SOURCE_NOT_EXACT_PROTECTED_BASE")
    with local.open("rb") as stream:
        need(stream.read(len(raw) + 1) == raw, "EXECUTED_SOURCE_NOT_EXACT_PROTECTED_BASE")
    need(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == match[1],
         "PROTECTED_SOURCE_GIT_BLOB_DRIFT")
    return raw, {"mode": "100644", "git_blob": match[1], "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()}


def compiled_module(root, path, raw):
    # Compile the already checked protected blob, not a second filesystem read.
    module = types.ModuleType("protected_" + Path(path).stem)
    module.__file__ = str(root / path)
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


def load_protected(root, base, *, supplied_git=None):
    root = root.resolve()
    read = (lambda args: supplied_git.run(args)) if supplied_git else (
        lambda args: bootstrap_git(root, args))
    need(read(["rev-parse", "HEAD"]).decode().strip() == base,
         "POLICY_CHECKOUT_NOT_EXACT_PUSH_BEFORE")
    raws, identities = {}, {}
    for path in (SELF, REGISTRY, SOURCE, SOURCE_CONTRACT, *M2_FILES):
        raws[path], identities[path] = protected_local(root, base, path, read)
    need(Path(__file__).read_bytes() == raws[SELF], "EXECUTED_PUSH_HELPER_NOT_PROTECTED_BASE")
    source = compiled_module(root, SOURCE, raws[SOURCE])
    git = supplied_git or source.Git(root)
    source.repository_context(git)
    contract, _ = source.verify_policy_source(git, base)
    registry = parse_json(raws[REGISTRY])
    need(registry.get("schema_version") == 1 and registry.get("review_id") == REVIEW and
         registry.get("implementation_stage") == "DORMANT_FINAL_PUSH_SOURCE" and
         registry.get("repository") == REPO and registry.get("repository_id") == REPO_ID and
         registry.get("bot_pull_request") == 714 and registry.get("bot_author") == BOT and
         registry.get("bot_head_ref") == BOT_REF and registry.get("workflow") == WORKFLOW and
         registry.get("scientific_experiment_executed") is False and
         registry.get("action_supply_chain_attested") is False and
         type(registry.get("m2_runtime_source")) is dict and
         set(registry["m2_runtime_source"]) == set(M2_FILES), "PUSH_SOURCE_REGISTRY_DRIFT")
    need({path: identities[path] for path in M2_FILES} == registry["m2_runtime_source"],
         "M2_RUNTIME_SOURCE_CLOSURE_DRIFT")
    modules = {path: compiled_module(root, path, raws[path]) for path in (M1, T0, M2)}
    m1, t0, m2 = (modules[path] for path in (M1, T0, M2))
    # Only the IO adapter changes. The protected actual/expected algorithms and
    # line review remain the same shared functions used by M1 and M2.
    def t0_git(args, *, max_bytes=MAX_JSON):
        need(args and args[0] == "git", "NON_GIT_CLASSIFIER_IO_DENIED")
        return git.run(args[1:], cap=max_bytes)
    t0.command = t0_git
    witness = parse_json(raws[WITNESS])
    witness_digest = m1.canonical_witness_digest(t0, witness, review=REVIEW)
    return source, git, contract, registry, identities, m1, t0, m2, witness_digest


def push_scope(source, event, env):
    need(env.get("GITHUB_EVENT_NAME") == "push", "DIRECT_MAIN_PUSH_REQUIRED")
    scope = source.event_range(event, env)
    sender = actor(event.get("sender"))
    need(env.get("GITHUB_ACTOR") == sender["login"] and
         env.get("GITHUB_ACTOR_ID") == str(sender["id"]), "PUSH_SENDER_ENVIRONMENT_DRIFT")
    need(type(env.get("GITHUB_TRIGGERING_ACTOR")) is str and
         re.fullmatch(r"[A-Za-z0-9_\[\]-]{1,100}", env["GITHUB_TRIGGERING_ACTOR"]) is not None,
         "PUSH_TRIGGERING_ACTOR_MISSING")
    return scope, sender


def run_identity(run, *, run_id, attempt, workflow, head, event, branch, status, conclusion):
    need(type(run) is dict and positive_id(run.get("id")) == run_id and
         positive_id(run.get("run_attempt")) == attempt and
         same_repo(run.get("repository")) and same_repo(run.get("head_repository")) and
         run.get("path") == workflow and run.get("head_sha") == head and
         run.get("event") == event and run.get("head_branch") == branch and
         run.get("status") == status and run.get("conclusion") == conclusion,
         "RUN_EXECUTION_IDENTITY_DRIFT")
    # The mutable pull_requests association is deliberately never consulted.
    return {"id": run_id, "run_attempt": attempt, "workflow_id": positive_id(run.get("workflow_id")),
            "run_number": positive_id(run.get("run_number")), "path": workflow, "head_sha": head,
            "event": event, "head_branch": branch, "status": status, "conclusion": conclusion,
            "actor": actor(run.get("actor")), "triggering_actor": actor(run.get("triggering_actor"))}


def merged_bot(source, git, pr, scope, event):
    identity = source.pr_identity(pr, scope, event, git)
    need(identity["number"] == 714 and actor(pr.get("user")) == BOT and
         pr.get("head", {}).get("ref") == BOT_REF, "MERGED_PR_NOT_EXACT_DEPENDABOT_714")
    before, after = scope["base_sha"], scope["head_sha"]
    for sha in (before, after, identity["head_sha"]):
        need(git.sha(["rev-parse", sha + "^{commit}"]) == sha, "SOURCE_OBJECT_NOT_A_COMMIT")
    need(git.run(["rev-list", "--parents", "-n", "1", after]).decode().split() == [after, before],
         "PUSH_NOT_EXACT_SINGLE_PARENT_SQUASH")
    identity.update(merged_by=actor(pr.get("merged_by")), merged_at=pr["merged_at"],
                    head_ref=BOT_REF, draft=False, merged=True)
    return identity


def current_snapshot(source, git, api, scope, event, env, sender, *, fetch):
    # Reuse source-range's live ruleset, two transports for current main, exact
    # associated PR, same-repository tree and current event-run verification.
    class OnePass:
        def __init__(self):
            self.values = {}
        def get(self, path):
            if path not in self.values:
                self.values[path] = api.get(path)
            return self.values[path]
    current_api = OnePass()  # Never shared with the independent second snapshot.
    checked = source.snapshot(current_api, git, scope, event, fetch=fetch)
    pr = current_api.get("pulls/714")
    identity = merged_bot(source, git, pr, scope, event)
    need(checked["pr"]["number"] == 714 and checked["pr"]["head_sha"] == identity["head_sha"],
         "AMBIGUOUS_OR_CHANGED_PUSH_PR_SOURCE")
    run = current_api.get("actions/runs/" + scope["github_run_id"])
    current = run_identity(run, run_id=int(scope["github_run_id"]),
        attempt=int(scope["github_run_attempt"]), workflow=WORKFLOW, head=scope["head_sha"],
        event="push", branch="main", status="in_progress", conclusion=None)
    exact = current_api.get("actions/runs/" + scope["github_run_id"] + "/attempts/" + scope["github_run_attempt"])
    need(run_identity(exact, run_id=current["id"], attempt=current["run_attempt"], workflow=WORKFLOW,
                      head=scope["head_sha"], event="push", branch="main", status="in_progress",
                      conclusion=None) == current, "CURRENT_RUN_ATTEMPT_READBACK_DRIFT")
    need(sender == current["actor"] == identity["merged_by"] and
         current["triggering_actor"]["login"] == env["GITHUB_TRIGGERING_ACTOR"],
         "PUSH_MERGER_SENDER_OR_TRIGGERING_ACTOR_DRIFT")
    checked.update(pr=identity, run=current)
    return checked


def reviewed_transition(git, before, bot_head, after, m1, t0, identities, witness_digest):
    actual = t0.classify_repo(before, bot_head, review=REVIEW)
    expected = t0.expected_repo(before, review=REVIEW)
    m1.actual_matches_expected(actual, expected)
    pushed = t0.classify_repo(before, after, review=REVIEW)
    m1.actual_matches_expected(pushed, expected)
    need(git.sha(["rev-parse", bot_head + "^{tree}"]) == git.sha(["rev-parse", after + "^{tree}"]),
         "PUSH_TREE_NOT_REVIEWED_PR_TREE")
    return {"actual_base_tree": git.sha(["rev-parse", before + "^{tree}"]),
            "actual_bot_tree": git.sha(["rev-parse", bot_head + "^{tree}"]),
            "actual_merge_base": before, "review_id": REVIEW,
            "file_count": actual["files_checked"], "pin_replacements": actual["replacements"],
            "pin_diff_sha256": actual["pin_diff_sha256"],
            "expected_current_base_pin_diff_sha256": expected["pin_diff_sha256"],
            "frozen_witness_content_diff_sha256": witness_digest,
            "historical_witness_matches_current_diff": witness_digest == actual["pin_diff_sha256"],
            "bot_patch_witness_sha256": identities[WITNESS]["sha256"],
            "trusted_classifier_sha256": identities[T0]["sha256"],
            "trusted_qualifier_sha256": identities[M1]["sha256"],
            "trusted_classifier_git_blob": identities[T0]["git_blob"]}


def prerequisite_snapshot(registry, api, git, before, *, fetch):
    registration = registry.get("m2_qualification")
    need(type(registration) is dict and registration.get("status") == "COMPLETE",
         "M2_QUALIFICATION_REGISTRY_PENDING")
    anchor = oid(registration.get("protected_main_sha"))
    need(git.sha(["merge-base", anchor, before]) == anchor, "M2_QUALIFICATION_NOT_MAIN_ANCESTOR")
    integrations = registration.get("integration_prs")
    need(type(integrations) is dict and set(integrations) == set(WORKFLOWS),
         "THREE_INDEPENDENT_M2_INTEGRATIONS_REQUIRED")
    result, numbers, merged_shas = {}, set(), set()
    for workflow in WORKFLOWS:
        row = integrations[workflow]
        need(type(row) is dict, "M2_INTEGRATION_REGISTRATION_MISSING")
        number = positive_id(row.get("number"))
        merged, head = oid(row.get("merged_sha")), oid(row.get("head_sha"))
        need(number != 714 and number not in numbers and merged not in merged_shas,
             "M2_INTEGRATIONS_NOT_DISTINCT")
        numbers.add(number); merged_shas.add(merged)
        pr = api.get("pulls/" + str(number))
        need(type(pr) is dict and type(pr.get("number")) is int and pr["number"] == number and
             pr.get("state") == "closed" and pr.get("merged") is True and pr.get("draft") is False and
             pr.get("merge_commit_sha") == merged and actor(pr.get("user"))["type"] == "User" and
             same_repo(pr.get("base", {}).get("repo")) and same_repo(pr.get("head", {}).get("repo")) and
             pr["base"].get("ref") == "main" and pr["head"].get("sha") == head,
             "M2_INTEGRATION_MERGE_PROVENANCE_DRIFT")
        base = oid(pr["base"].get("sha"))
        # A squash keeps the integration tree on main, not its original PR
        # head commit. A normal full main checkout need not contain that head.
        # Retrieve only these already bound same-repository object identities;
        # never execute candidate source or rely on a shared object cache.
        if fetch:
            git.run(["fetch", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
                     "https://github.com/" + REPO + ".git", *sorted({base, merged, head})], cap=8192)
        need(git.run(["rev-list", "--parents", "-n", "1", merged]).decode().split() == [merged, base] and
             git.sha(["rev-parse", merged + "^{tree}"]) == git.sha(["rev-parse", head + "^{tree}"]) and
             git.sha(["merge-base", merged, anchor]) == merged,
             "M2_INTEGRATION_GIT_LINEAGE_DRIFT")
        changed = git.run(["diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                           "--name-only", base, head]).decode().splitlines()
        need(changed == [workflow], "M2_INTEGRATION_NOT_INDEPENDENT_WORKFLOW_ONLY")
        # Later maintenance must not silently inherit an altered PCR consumer.
        # dEchorate's separately preregistered fourth exact profile is checked
        # by frozen_science; its workflow-only change is the explicit exception.
        if workflow != WORKFLOW:
            need(git.regular_blob(anchor, workflow) == git.regular_blob(before, workflow),
                 "M2_QUALIFIED_PCR_WORKFLOW_CHANGED")
        result[workflow] = {"number": number, "merged_sha": merged, "head_sha": head,
                            "base_sha": base, "author": actor(pr["user"])}
    runs = {}
    for name, path, event in (("verify", ".github/workflows/verify.yml", "push"),
                              ("release", ".github/workflows/release.yml", "workflow_run")):
        selected = registration.get(name)
        need(type(selected) is dict, "M2_MAIN_GATE_REGISTRATION_MISSING")
        rid, attempt = positive_id(selected.get("run_id")), positive_id(selected.get("run_attempt"))
        run = api.get("actions/runs/" + str(rid))
        runs[name] = run_identity(run, run_id=rid, attempt=attempt, workflow=path,
                                  head=anchor, event=event, branch="main", status="completed", conclusion="success")
        exact = api.get("actions/runs/" + str(rid) + "/attempts/" + str(attempt))
        need(run_identity(exact, run_id=rid, attempt=attempt, workflow=path, head=anchor,
                          event=event, branch="main", status="completed", conclusion="success") == runs[name],
             "M2_MAIN_GATE_ATTEMPT_DRIFT")
    need(runs["verify"]["id"] != runs["release"]["id"], "M2_MAIN_GATES_NOT_DISTINCT")
    return {"protected_main_sha": anchor, "integration_prs": result, "main_runs": runs}


def selected_m2_run(api, workflow, head):
    filename = Path(workflow).name
    listing = api.get("actions/workflows/" + filename + "/runs?event=pull_request&head_sha=" + head + "&per_page=100")
    need(type(listing) is dict and type(listing.get("total_count")) is int and
         type(listing.get("workflow_runs")) is list and
         0 < listing["total_count"] == len(listing["workflow_runs"]) < 100,
         "COMPLETE_BOUNDED_DIRECT_M2_RUN_LIST_REQUIRED")
    numbers, seen = [], set()
    for row in listing["workflow_runs"]:
        need(type(row) is dict and row.get("path") == workflow and row.get("head_sha") == head and
             row.get("event") == "pull_request" and same_repo(row.get("repository")) and
             same_repo(row.get("head_repository")), "DIRECT_M2_RUN_LIST_SOURCE_DRIFT")
        number, rid = positive_id(row.get("run_number")), positive_id(row.get("id"))
        need(number not in seen, "AMBIGUOUS_DIRECT_M2_RUN_NUMBER")
        seen.add(number); numbers.append((number, rid, positive_id(row.get("run_attempt"))))
    _, rid, attempt = max(numbers)
    path = "actions/runs/" + str(rid)
    run = api.get(path)
    result = run_identity(run, run_id=rid, attempt=attempt, workflow=workflow, head=head,
                          event="pull_request", branch=BOT_REF, status="completed", conclusion="success")
    exact = api.get(path + "/attempts/" + str(attempt))
    # The fixed Bot is the PR author, not necessarily the person who triggered
    # synchronize or a rerun. Preserve the actual execution actors and require
    # exact current/attempt identity and a stable independent second readback.
    need(run_identity(exact, run_id=rid, attempt=attempt, workflow=workflow, head=head,
                      event="pull_request", branch=BOT_REF, status="completed", conclusion="success") == result and
         result["run_number"] == max(numbers)[0],
         "DIRECT_M2_ACTOR_OR_ATTEMPT_DRIFT")
    return result


def m2_jobs(api, selected):
    rid, attempt, workflow = (selected[key] for key in ("id", "run_attempt", "path"))
    listing = api.get("actions/runs/" + str(rid) + "/attempts/" + str(attempt) + "/jobs?per_page=100")
    need(type(listing) is dict and type(listing.get("total_count")) is int and
         type(listing.get("jobs")) is list and 1 < listing["total_count"] == len(listing["jobs"]) < 100,
         "COMPLETE_M2_JOB_ATTEMPT_REQUIRED")
    names, ids, result = set(), set(), []
    for job in listing["jobs"]:
        need(type(job) is dict and type(job.get("name")) is str and job["name"] not in names and
             positive_id(job.get("run_id")) == rid and positive_id(job.get("run_attempt")) == attempt and
             job.get("head_sha") == selected["head_sha"] and job.get("status") == "completed",
             "M2_JOB_EXECUTION_IDENTITY_DRIFT")
        jid = positive_id(job.get("id")); names.add(job["name"])
        need(jid not in ids and job.get("conclusion") == ("success" if job["name"] == "maintenance" else "skipped"),
             "M2_JOB_NOT_EXPLICIT_NONMEASUREMENT")
        ids.add(jid)
        result.append({"id": jid, "name": job["name"], "conclusion": job["conclusion"]})
    need({"maintenance", *SCIENCE_JOBS[workflow]} <= names, "M2_EXPECTED_JOBS_MISSING")
    return sorted(result, key=lambda row: row["name"])


def m2_artifact(api, selected):
    rid, workflow = selected["id"], selected["path"]
    name = "workflow-pin-maintenance-" + Path(workflow).stem + "-" + str(rid)
    listing = api.get("actions/runs/" + str(rid) + "/artifacts?per_page=100")
    need(type(listing) is dict and type(listing.get("total_count")) is int and
         type(listing.get("artifacts")) is list and
         0 < listing["total_count"] == len(listing["artifacts"]) < 100 and
         all(type(row) is dict for row in listing["artifacts"]), "COMPLETE_M2_ARTIFACT_LIST_REQUIRED")
    matches = [row for row in listing["artifacts"] if row.get("name") == name]
    need(len(matches) == 1, "UNIQUE_M2_ORIGINAL_ARTIFACT_REQUIRED")
    artifact = matches[0]
    aid, size = positive_id(artifact.get("id")), positive_id(artifact.get("size_in_bytes"))
    sha = artifact.get("digest")
    need(size <= MAX_ZIP and artifact.get("expired") is False and type(sha) is str and
         re.fullmatch(r"sha256:[0-9a-f]{64}", sha) is not None, "M2_ARTIFACT_DIGEST_OR_AVAILABILITY_DRIFT")
    provenance = artifact.get("workflow_run")
    need(type(provenance) is dict and positive_id(provenance.get("id")) == rid and
         type(provenance.get("repository_id")) is int and provenance["repository_id"] == REPO_ID and
         type(provenance.get("head_repository_id")) is int and provenance["head_repository_id"] == REPO_ID and
         provenance.get("head_branch") == BOT_REF and provenance.get("head_sha") == selected["head_sha"],
         "M2_ARTIFACT_WORKFLOW_RUN_IDENTITY_DRIFT")
    return {"id": aid, "name": name, "size_in_bytes": size, "sha256": sha[7:],
            "workflow_run": {key: provenance[key] for key in
                             ("id", "repository_id", "head_repository_id", "head_branch", "head_sha")}}


def original_receipt(raw, artifact):
    need(type(raw) is bytes and 0 < len(raw) == artifact["size_in_bytes"] <= MAX_ZIP and
         hashlib.sha256(raw).hexdigest() == artifact["sha256"], "M2_ORIGINAL_ZIP_DIGEST_OR_SIZE_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            need(len(members) == 1 and not archive.comment, "M2_ZIP_MEMBER_SET_DRIFT")
            member = members[0]
            mode = member.external_attr >> 16
            need(member.filename == "maintenance.json" and not member.is_dir() and
                 member.header_offset == 0 and 0 < member.file_size <= MAX_RECEIPT and
                 member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and
                 not member.flag_bits & 1 and stat.S_IFMT(mode) in (0, stat.S_IFREG) and
                 not mode & 0o111, "M2_ZIP_RECEIPT_TYPE_OR_BOUND_DRIFT")
            body = archive.read(member)
    except (zipfile.BadZipFile, zlib.error, RuntimeError, EOFError, NotImplementedError):
        raise Denied("M2_ORIGINAL_ZIP_INVALID") from None
    return parse_json(body, maximum=MAX_RECEIPT), hashlib.sha256(body).hexdigest()


def bind_m2_receipt(git, receipt, run, before, head, identities, transition, m1, m2):
    need(type(receipt.get("schema_version")) is int and receipt["schema_version"] == 1 and
         receipt.get("decision") == m2.POSITIVE and receipt.get("reason") == "EXACT_DIRECT_PR_APPROVED_PIN_MAINTENANCE" and
         receipt.get("skip_measurement") is True and receipt.get("automated_bypass_enabled") is True and
         receipt.get("scientific_experiment_executed") is False and receipt.get("acoustic_pass") is False and
         receipt.get("action_supply_chain_attested") is False and receipt.get("workflow") == run["path"] and
         receipt.get("event") == "pull_request" and receipt.get("base_sha") == before and
         receipt.get("head_sha") == head and receipt.get("consumer_sha256") == identities[M2]["sha256"] and
         positive_id(receipt.get("run_id")) == run["id"] and
         positive_id(receipt.get("run_attempt")) == run["run_attempt"], "M2_RECEIPT_RUN_SOURCE_OR_DECISION_DRIFT")
    observation = receipt.get("m1")
    need(type(observation) is dict, "M1_RECEIPT_MISSING")
    m2.bind_m1(observation, before, head, m1)
    need(all(observation.get(key) == value and type(observation.get(key)) is type(value)
             for key, value in transition.items()), "M1_RECEIPT_NOT_CURRENT_REVIEWED_GIT_PROOF")
    need(observation.get("ssc305_or_physical_hil_qualified") is False and
         observation.get("public_sdk_3x_admitted") is False, "M1_RECEIPT_AUTHORITY_DRIFT")
    merge = oid(receipt.get("event_merge_sha"))
    git.run(["fetch", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
             "https://github.com/" + REPO + ".git", merge], cap=8192)
    need(git.run(["rev-list", "--parents", "-n", "1", merge]).decode().split() == [merge, before, head] and
         git.sha(["rev-parse", merge + "^{tree}"]) == transition["actual_bot_tree"],
         "M2_ORIGINAL_EVENT_MERGE_PARENT_OR_TREE_DRIFT")
    return merge


def m2_snapshot(api, git, before, head, identities, transition, m1, m2, *, read_archives):
    result, used_runs, used_artifacts, used_digests = {}, set(), set(), set()
    for workflow in WORKFLOWS:
        run = selected_m2_run(api, workflow, head)
        jobs = m2_jobs(api, run)
        artifact = m2_artifact(api, run)
        need(run["id"] not in used_runs and artifact["id"] not in used_artifacts and
             artifact["sha256"] not in used_digests, "THREE_DISTINCT_DIRECT_M2_ORIGINALS_REQUIRED")
        used_runs.add(run["id"]); used_artifacts.add(artifact["id"]); used_digests.add(artifact["sha256"])
        row = {"run": run, "jobs": jobs, "artifact": artifact}
        if read_archives:
            receipt, receipt_sha = original_receipt(api.archive(artifact["id"]), artifact)
            row["receipt_sha256"] = receipt_sha
            row["event_merge_sha"] = bind_m2_receipt(git, receipt, run, before, head, identities,
                                                       transition, m1, m2)
        result[workflow] = row
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicEvidence:
    """Bounded read-only public metadata and digest-bound original ZIPs.

    The public resolver supplies only an Azure redirect; API digest and exact
    run/artifact metadata are the authority. No token or signed URL is emitted.
    """
    def __init__(self):
        self.opener = urllib.request.build_opener(NoRedirect)

    def get(self, path):
        allowed = (r"(?:git/ref/heads/main|rulesets/21804005|pulls/[1-9][0-9]{0,18}|"
            r"commits/[0-9a-f]{40}/pulls\?per_page=100|"
            r"actions/runs/[1-9][0-9]{0,18}(?:/attempts/[1-9][0-9]{0,18}(?:/jobs\?per_page=100)?|/artifacts\?per_page=100)?|"
            r"actions/workflows/(?:pcr02-aec-real-tail-confirmation|pcr02-dsp-counterfactuals|research-dechorate-ground-truth-diagnostic-v1)\.yml/runs\?event=pull_request&head_sha=[0-9a-f]{40}&per_page=100)")
        need(type(path) is str and re.fullmatch(allowed, path) is not None, "UNREVIEWED_PUBLIC_API_PATH")
        url = "https://api.github.com/repos/" + REPO + "/" + path
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
            "User-Agent": "audio-pipeline-t1-m3-push/1", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with self.opener.open(request, timeout=15) as response:
                need(response.status == 200 and response.url == url, "PUBLIC_METADATA_STATUS_OR_REDIRECT")
                raw = response.read(MAX_JSON + 1)
        except (OSError, urllib.error.URLError, TimeoutError):
            raise Denied("PUBLIC_METADATA_UNAVAILABLE") from None
        return parse_json(raw, object_only=False)

    def archive(self, artifact_id):
        url = "https://nightly.link/" + REPO + "/actions/artifacts/" + str(positive_id(artifact_id)) + ".zip"
        request = urllib.request.Request(url, headers={"User-Agent": "audio-pipeline-t1-m3-push/1"})
        try:
            with self.opener.open(request, timeout=15):
                raise Denied("PUBLIC_ARTIFACT_REDIRECT_REQUIRED")
        except urllib.error.HTTPError as exc:
            need(exc.code in (301, 302, 303, 307, 308), "PUBLIC_ARTIFACT_RESOLVER_UNAVAILABLE")
            location = exc.headers.get("Location", "")
        except (OSError, urllib.error.URLError, TimeoutError):
            raise Denied("PUBLIC_ARTIFACT_RESOLVER_UNAVAILABLE") from None
        target = urllib.parse.urlsplit(location)
        need(target.scheme == "https" and target.username is None and target.password is None and
             target.port in (None, 443) and not target.fragment and type(target.hostname) is str and
             re.fullmatch(r"[a-z0-9-]+\.blob\.core\.windows\.net", target.hostname) is not None,
             "ORIGINAL_ARTIFACT_STORAGE_REDIRECT_NOT_ADMITTED")
        request = urllib.request.Request(location, headers={"User-Agent": "audio-pipeline-t1-m3-push/1"})
        try:
            with self.opener.open(request, timeout=15) as response:
                need(response.status == 200 and response.url == location, "ORIGINAL_ARTIFACT_STORAGE_RESPONSE_DRIFT")
                raw = response.read(MAX_ZIP + 1)
        except (OSError, urllib.error.URLError, TimeoutError):
            raise Denied("ORIGINAL_M2_ARCHIVE_UNAVAILABLE") from None
        need(0 < len(raw) <= MAX_ZIP, "ORIGINAL_M2_ARCHIVE_SIZE_BOUND")
        return raw


def evaluate(event, env, api, *, root=ROOT, supplied_git=None, live=False):
    result = {"schema_version": 1, "decision": NEGATIVE, "skip_measurement": False,
              "maintenance_push_admitted": False, "automated_bypass_enabled": False,
              "scientific_experiment_executed": False, "acoustic_pass": False,
              "corpus_materialized_or_verified": False, "action_supply_chain_attested": False,
              "workflow": WORKFLOW, "implementation_stage": "DORMANT_FINAL_PUSH_SOURCE",
              "m2_qualification": "PENDING", "live_public_metadata_checked": False,
              "evidence_role": "live-public-readback" if live else "offline-engineering-fixture"}
    try:
        need(type(event) is dict and env.get("GITHUB_EVENT_NAME") == "push", "DIRECT_MAIN_PUSH_REQUIRED")
        base = oid(event.get("before"))
        source, git, contract, registry, identities, m1, t0, m2, frozen_digest = load_protected(
            root, base, supplied_git=supplied_git)
        scope, sender = push_scope(source, event, env)
        result.update(run_id=int(scope["github_run_id"]), run_attempt=int(scope["github_run_attempt"]),
                      before_sha=base, after_sha=scope["head_sha"])
        # Missing actual qualification stops before public network access.
        need(type(registry.get("m2_qualification")) is dict and
             registry["m2_qualification"].get("status") == "COMPLETE", "M2_QUALIFICATION_REGISTRY_PENDING")
        first = current_snapshot(source, git, api, scope, event, env, sender, fetch=True)
        prerequisites = prerequisite_snapshot(registry, api, git, base, fetch=True)
        head = first["pr"]["head_sha"]
        science = source.frozen_science(git, base, base, contract)
        need(science["workflow_execution_profiles"]["base"].startswith(PROFILE + ":"),
             "EXACT_PROTECTED_M3_WORKFLOW_TEMPLATE_REQUIRED")
        transition = reviewed_transition(git, base, head, scope["head_sha"], m1, t0, identities, frozen_digest)
        evidence = m2_snapshot(api, git, base, head, identities, transition, m1, m2, read_archives=True)
        evidence_after = m2_snapshot(api, git, base, head, identities, transition, m1, m2, read_archives=False)
        need({key: {k: v for k, v in row.items() if k not in ("receipt_sha256", "event_merge_sha")}
              for key, row in evidence.items()} == evidence_after, "M2_RUN_OR_ARTIFACT_MOVED_DURING_READBACK")
        need(prerequisite_snapshot(registry, api, git, base, fetch=False) == prerequisites,
             "M2_PREREQUISITE_READBACK_DRIFT")
        last = current_snapshot(source, git, api, scope, event, env, sender, fetch=False)
        need(first == last, "PUSH_SOURCE_RULESET_OR_RUN_MOVED_DURING_READBACK")
        result.update(decision=POSITIVE, skip_measurement=True, maintenance_push_admitted=True,
                      automated_bypass_enabled=True, reason="EXACT_MERGED_714_PIN_ONLY_PUSH_WITH_THREE_DIRECT_M2_ORIGINALS",
                      m2_qualification="COMPLETE", protected_sources=identities, source_snapshot=last,
                      frozen_science=science, reviewed_transition=transition, m2_originals=evidence,
                      qualified_m2_prerequisites=prerequisites, live_public_metadata_checked=live)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc)
        result.update(decision=NEGATIVE, skip_measurement=False, maintenance_push_admitted=False,
                      automated_bypass_enabled=False, live_public_metadata_checked=False,
                      reason=reason if re.fullmatch(r"[A-Z0-9_]{1,100}", reason) else "PUSH_SOURCE_OR_EVIDENCE_NOT_ADMITTED")
    return result


def write_receipt(path, result):
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    need(len(raw) <= MAX_RECEIPT, "PUSH_RECEIPT_SIZE_BOUND")
    seal = path.with_name(path.name + ".sha256")
    need(not path.exists() and not path.is_symlink() and not seal.exists() and not seal.is_symlink(),
         "EXISTING_RECEIPT_MUST_BE_PRESERVED")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    sha = hashlib.sha256(raw).hexdigest()
    with seal.open("x", encoding="ascii") as stream:
        stream.write(sha + "  " + path.name + "\n")
    return sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--summary-file", type=Path)
    args = parser.parse_args()
    def deadline(_signum, _frame):
        raise Denied("PUSH_QUALIFICATION_WALL_BUDGET_EXHAUSTED")
    signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, CLI_SECONDS)
    try:
        need(args.event_file.is_file() and not args.event_file.is_symlink() and
             0 < args.event_file.stat().st_size <= MAX_JSON, "REGULAR_BOUNDED_EVENT_FILE_REQUIRED")
        with args.event_file.open("rb") as stream:
            event = parse_json(stream.read(MAX_JSON + 1))
        result = evaluate(event, dict(os.environ), PublicEvidence(), live=True)
    except (ValueError, OSError, UnicodeError):
        result = {"schema_version": 1, "decision": NEGATIVE, "skip_measurement": False,
                  "maintenance_push_admitted": False, "automated_bypass_enabled": False,
                  "scientific_experiment_executed": False, "acoustic_pass": False,
                  "reason": "PUSH_EVENT_NOT_ADMITTED"}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        sha = write_receipt(args.receipt, result)
        for path in (args.github_output, args.summary_file):
            if path is not None:
                need(path.is_file() and not path.is_symlink(), "REGULAR_GITHUB_RESULT_FILE_REQUIRED")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write("skip_measurement=" + ("true" if result["skip_measurement"] else "false") + "\n")
        if args.summary_file:
            with args.summary_file.open("a", encoding="utf-8") as stream:
                stream.write("## dEchorate push dependency scope\n\n" + result["decision"] +
                             "\n\nThe original corpus was not run by this helper.\n")
    except (ValueError, OSError):
        print("PUSH_RECEIPT_WRITE_FAILED_PREVIOUS_EVIDENCE_PRESERVED", file=sys.stderr)
        return 2
    print(json.dumps({"decision": result["decision"], "reason": result["reason"],
                      "skip_measurement": result["skip_measurement"], "receipt_sha256": sha,
                      "scientific_experiment_executed": False}, sort_keys=True))
    return 0  # A negative requests original science; failed admission never suppresses it.


if __name__ == "__main__":
    raise SystemExit(main())
