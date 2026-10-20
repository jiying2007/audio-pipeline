#!/usr/bin/env python3
"""T1-M3 dormant dEchorate source/event proof; never a measurement skip.

Execute this first-party file from the exact event base checkout. Read the
candidate only as Git objects. A positive binds unchanged historical science to
the current PR base/head or single-parent main push before/after. It neither
executes the experiment nor admits Actions maintenance on push. The scientific
workflow consumer and every maintenance consumer require separate qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SELF = ".github/program/dechorate_event_source_t1m3.py"
CONTRACT = ".github/program/dechorate_event_source_t1m3.json"
REPO = "jiying2007/audio-pipeline"
REPO_ID = 1347377137
REMOTE = "https://github.com/" + REPO + ".git"
WORKFLOW = ".github/workflows/research-dechorate-ground-truth-diagnostic-v1.yml"
SCIENCE = ".github/research/continuous-optimization/dechorate_ground_truth_diagnostic_v1.py"
MANIFEST = ".github/research/continuous-optimization/development-v3/dechorate-ground-truth-diagnostic-v1.json"
QUALIFICATION = ".github/research/continuous-optimization/development-v3/dechorate-source-qualification-v1.json"
FROZEN_BASE = "cb85d2bbffa2e1ac6d6f0a48a66619062b726cc0"
SCIENCE_ANCHOR = "7e8f26ba6d7330624091291d9e1336e5ff9c09dc"
QUALIFICATION_BASE = "b9ea9e5518198f302a457531d1380472a35f3153"
POSITIVE = "T1_M3_FROZEN_SCIENCE_EVENT_RANGE_QUALIFIED_NO_EXPERIMENT_RESULT"
NEGATIVE = "ORIGINAL_RESEARCH_GUARDS_REQUIRED"
SHA = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
MAX_BYTES = 150_000
MAX_RECEIPT_BYTES = 16_000
BIND_STEP = "Bind diagnostic to exact source and research-only scope"
UPLOAD_OLD = "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
UPLOAD_NEW = "cf430e030ddbb5b0abf93d22962f4752f3646cd9"
M2_PROFILE = "EXACT_SOURCE_BINDING_WITH_DIRECT_PR_M2"
M2_SOURCE_FILES = (
    ".github/program/workflow_pin_pr_consumer.py",
    ".github/program/workflow_pin_only_actual_tree_t1m1.py",
    ".github/program/workflow_pin_only_scope.py",
    ".github/program/workflow_pin_only_bot714_20261020.json",
)
# These are reviewable literal templates, not a general YAML interpreter or
# an editable shell slot. No candidate-supplied token is interpolated here.
SOURCE_BIND_TEMPLATE = r'''      - name: Bind diagnostic to exact source and research-only scope
        env:
          EXPECTED_SHA: ${{ github.event.pull_request.head.sha || github.sha }}
        run: |
          set -euo pipefail
          test "$(git -c "safe.directory=$PWD" rev-parse HEAD)" = "$EXPECTED_SHA"
          python3 - <<'PY'
          import json,os,re,subprocess,sys
          from pathlib import Path
          event_file=Path(os.environ['GITHUB_EVENT_PATH']).resolve()
          event=json.loads(event_file.read_text())
          kind=os.environ['GITHUB_EVENT_NAME']
          assert kind in ('pull_request','push')
          base=event['pull_request']['base']['sha'] if kind=='pull_request' else event['before']
          assert type(base) is str and re.fullmatch(r'[0-9a-f]{40}',base) and base!='0'*40
          run_id=os.environ['GITHUB_RUN_ID']
          attempt=os.environ['GITHUB_RUN_ATTEMPT']
          assert re.fullmatch(r'[1-9][0-9]{0,18}',run_id) and re.fullmatch(r'[1-9][0-9]{0,18}',attempt)
          policy=Path(os.environ['RUNNER_TEMP'])/('dechorate-source-policy-'+run_id+'-'+attempt)
          assert not policy.exists() and not policy.is_symlink()
          subprocess.run(['git','-c','safe.directory='+str(Path.cwd()),'-c','core.hooksPath=/dev/null',
              'worktree','add','--detach',str(policy),base],check=True)
          receipt=Path.cwd()/'dechorate-ground-truth-v1-out'/'source-range.json'
          subprocess.run([sys.executable,str(policy/'.github/program/dechorate_event_source_t1m3.py'),
              '--event-file',str(event_file),'--receipt',str(receipt)],check=True)
          PY
'''
SOURCE_RECEIPT_TEMPLATE = '''      - name: Preserve the independent source-range decision
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
        with:
          name: dechorate-event-source-range-${{ github.run_id }}
          path: |
            dechorate-ground-truth-v1-out/source-range.json
            dechorate-ground-truth-v1-out/source-range.json.sha256
          if-no-files-found: error
          retention-days: 30
'''
M2_JOB_TEMPLATE = r'''  maintenance:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    outputs:
      skip_measurement: ${{ steps.scope.outputs.skip_measurement }}
    steps:
      - name: Check out the exact protected PR base
        uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
        with:
          ref: ${{ github.event.pull_request.base.sha }}
          fetch-depth: 0
          persist-credentials: false
          path: trusted-policy
      - name: Qualify direct PR maintenance from protected source
        id: scope
        working-directory: trusted-policy
        shell: bash
        run: |
          set -euo pipefail
          mkdir ../pin-maintenance
          python3 .github/program/workflow_pin_pr_consumer.py \
            --workflow .github/workflows/research-dechorate-ground-truth-diagnostic-v1.yml \
            --event-file "$GITHUB_EVENT_PATH" \
            --receipt ../pin-maintenance/maintenance.json \
            --github-output "$GITHUB_OUTPUT" --summary-file "$GITHUB_STEP_SUMMARY"
      - name: Preserve the nonmeasurement decision
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: workflow-pin-maintenance-research-dechorate-ground-truth-diagnostic-v1-${{ github.run_id }}
          path: pin-maintenance/maintenance.json
          if-no-files-found: error
          retention-days: 30

'''
M2_DIAGNOSTIC_CONDITION = (
    "    needs: maintenance\n"
    "    if: ${{ !cancelled() && !(needs.maintenance.result == 'success' && "
    "needs.maintenance.outputs.skip_measurement == 'true') }}\n"
)
SCIENTIFIC_STEPS = (
    "Check out exact source",
    "Validate code provenance and diagnostic authority",
    "Materialize exact frozen SOFA microset",
    "Install pinned schema reader and run self-test",
    "Run fixed-geometry RIR ground-truth diagnostic",
    "Enforce evidence shape without deriving a boundary",
    "Seal research evidence",
)


class Denied(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Denied(code)


def strict_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def no_constant(_value: str):
    raise Denied("NONFINITE_JSON_CONSTANT")


def json_object(raw: bytes) -> dict:
    need(0 < len(raw) <= MAX_BYTES, "JSON_SIZE_BOUND")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs,
                        parse_constant=no_constant)
    need(type(result) is dict, "JSON_OBJECT_REQUIRED")
    return result


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def oid(value: object) -> str:
    need(type(value) is str and SHA.fullmatch(value) is not None and
         value != "0" * 40, "FULL_NONZERO_COMMIT_OID_REQUIRED")
    return value


def same_repo(value: object) -> bool:
    return (type(value) is dict and value.get("full_name") == REPO and
            type(value.get("id")) is int and value["id"] == REPO_ID)


class Git:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def run(self, args: list[str], *, cap: int = MAX_BYTES) -> bytes:
        need(0 < len(args) <= 20 and all(type(a) is str for a in args), "GIT_ARGUMENT_BOUND")
        # Git object reads must not be redirected by caller-provided config,
        # alternate object databases, replacement refs, or credential helpers.
        forbidden = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_DIR",
                     "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                     "GIT_NAMESPACE", "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE")
        need(not any(os.environ.get(k) for k in forbidden), "EXTERNAL_GIT_CONTEXT_NOT_TRUSTED")
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                   GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0")
        command = ["git", "--no-replace-objects", "-c", "safe.directory=" + str(self.root),
                   "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                   "-c", "credential.helper=", *args]
        try:
            p = subprocess.run(command, cwd=self.root, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=45, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise Denied("GIT_IO_OR_TIMEOUT") from None
        need(p.returncode == 0 and len(p.stdout) < cap and len(p.stderr) < cap,
             "GIT_COMMAND_FAILED_OR_OVERSIZED")
        return p.stdout

    def sha(self, args: list[str]) -> str:
        return oid(self.run(args, cap=4096).decode("ascii").strip())

    def regular_blob(self, revision: str, path: str) -> tuple[str, bytes]:
        oid(revision)
        entry = self.run(["ls-tree", revision, "--", path], cap=4096).decode("ascii")
        match = re.fullmatch(r"100644 blob ([0-9a-f]{40})\t" + re.escape(path) + r"\n", entry)
        need(match is not None, "SOURCE_BLOB_MODE_OR_TYPE_DRIFT")
        raw = self.run(["show", revision + ":" + path])
        need(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() ==
             match[1], "SOURCE_GIT_BLOB_IDENTITY_DRIFT")
        return match[1], raw


def repository_context(git: Git) -> None:
    need(os.name == "posix" and sys.platform == "linux", "UNQUALIFIED_PLATFORM")
    need(git.run(["rev-parse", "--is-shallow-repository"]).strip() == b"false",
         "INCOMPLETE_GIT_HISTORY")
    grafts = git.run(["rev-parse", "--git-path", "info/grafts"]).decode().strip()
    location = Path(grafts) if Path(grafts).is_absolute() else git.root / grafts
    need(not location.exists(), "GRAFTED_GIT_HISTORY_NOT_TRUSTED")


def verify_policy_source(git: Git, base: str) -> tuple[dict, dict]:
    need(git.sha(["rev-parse", "HEAD"]) == base, "POLICY_CHECKOUT_NOT_EXACT_EVENT_BASE")
    hashes = {}
    for path in (SELF, CONTRACT):
        blob, raw = git.regular_blob(base, path)
        local = git.root / path
        need(local.is_file() and not local.is_symlink() and local.read_bytes() == raw,
             "UNPROTECTED_SOURCE_HELPER_OR_CONTRACT")
        if path == SELF:
            need(Path(__file__).read_bytes() == raw, "EXECUTED_HELPER_NOT_PROTECTED_BASE_BYTES")
        hashes[path] = {"git_blob": blob, "sha256": hashlib.sha256(raw).hexdigest()}
    contract = json_object((git.root / CONTRACT).read_bytes())
    need(contract.get("schema_version") == 1 and
         contract.get("implementation_stage") == "DORMANT_SOURCE_AND_EVENT_RANGE_ONLY" and
         contract.get("historical_base_sha") == FROZEN_BASE and
         contract.get("science_anchor_sha") == SCIENCE_ANCHOR and
         contract.get("source_qualification_ancestor_sha") == QUALIFICATION_BASE and
         contract.get("workflow") == WORKFLOW and
         contract.get("allow_current_science_scope_paths") == [WORKFLOW] and
         contract.get("maintenance_push_admission_enabled") is False and
         contract.get("scientific_experiment_executed") is False,
         "FROZEN_SOURCE_CONTRACT_DRIFT")
    return contract, hashes


def event_range(event: dict, env: dict) -> dict:
    need(same_repo(event.get("repository")) and env.get("GITHUB_REPOSITORY") == REPO,
         "UNTRUSTED_EVENT_REPOSITORY")
    kind = env.get("GITHUB_EVENT_NAME")
    need(kind in ("pull_request", "push"), "UNQUALIFIED_EVENT_KIND")
    if kind == "pull_request":
        number = event.get("number")
        need(type(number) is int and 0 < number < 1_000_000 and
             event.get("action") in ("opened", "reopened", "synchronize"), "UNTRUSTED_PR_EVENT")
        pr = event.get("pull_request")
        need(type(pr) is dict and type(pr.get("number")) is int and pr["number"] == number and
             pr.get("state") == "open" and pr.get("draft") is False, "NON_OPEN_DIRECT_PR")
        before, after = pr.get("base", {}), pr.get("head", {})
        need(same_repo(before.get("repo")) and same_repo(after.get("repo")) and
             before.get("ref") == "main" and type(after.get("ref")) is str and
             0 < len(after["ref"]) < 200 and
             env.get("GITHUB_BASE_REF") == "main" and env.get("GITHUB_HEAD_REF") == after["ref"],
             "PR_REPOSITORY_OR_BRANCH_DRIFT")
        base, head = oid(before.get("sha")), oid(after.get("sha"))
        ref = "refs/pull/" + str(number) + "/merge"
        event_commit = oid(env.get("GITHUB_SHA"))
    else:
        need(event.get("ref") == "refs/heads/main" and
             all(event.get(key) is False for key in ("created", "deleted", "forced")),
             "PUSH_NOT_EXISTING_NONFORCED_MAIN")
        base, head = oid(event.get("before")), oid(event.get("after"))
        need(oid(env.get("GITHUB_SHA")) == head and
             type(event.get("head_commit")) is dict and event["head_commit"].get("id") == head,
             "PUSH_AFTER_NOT_EVENT_COMMIT")
        number, ref, event_commit = 0, "refs/heads/main", head
    need(base != head, "EMPTY_CURRENT_EVENT_RANGE")
    need(env.get("GITHUB_REF") == ref and
         env.get("GITHUB_WORKFLOW_REF") == REPO + "/" + WORKFLOW + "@" + ref,
         "REUSABLE_OR_UNEXPECTED_WORKFLOW_CONTEXT")
    ids = {}
    for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = env.get(name, "")
        need(type(value) is str and re.fullmatch(r"[1-9][0-9]{0,18}", value), "RUN_SCOPED_IDENTITY_REQUIRED")
        ids[name.lower()] = value
    return {"event": kind, "base_sha": base, "head_sha": head,
            "event_commit_sha": event_commit, "pr_number": number, **ids}


def scientific_step(text: str, name: str) -> bytes:
    blocks = re.findall(r"(?ms)^      - name: " + re.escape(name) +
                        r"\n.*?(?=^      - (?:name:|uses:)|\Z)", text)
    need(len(blocks) == 1, "ORIGINAL_SCIENTIFIC_STEP_MISSING_OR_DUPLICATED")
    return (blocks[0].rstrip() + "\n").encode()


def workflow_templates(anchor: str) -> dict[str, str]:
    """Six exact bodies: three execution profiles, each old or reviewed new pins.

    The protected registration permits only the complete October 20 upload
    transition. It does not authorize arbitrary uses, partial updates, mutable
    Bind shell, job overrides, YAML aliases, extra jobs or reordered steps.
    """
    old_bind = scientific_step(anchor, BIND_STEP).decode()
    need(anchor.count(old_bind) == 1 and anchor.count("jobs:\n  diagnostic:\n") == 1,
         "ORIGINAL_WORKFLOW_TEMPLATE_STRUCTURE_DRIFT")
    repaired = anchor.replace(old_bind, SOURCE_BIND_TEMPLATE + "\n" + SOURCE_RECEIPT_TEMPLATE, 1)
    gated = repaired.replace("jobs:\n  diagnostic:\n",
        "jobs:\n" + M2_JOB_TEMPLATE + "  diagnostic:\n" + M2_DIAGNOSTIC_CONDITION, 1)
    variants = {"ORIGINAL_FROZEN_WORKFLOW": anchor,
                "EXACT_PROTECTED_SOURCE_BINDING": repaired, M2_PROFILE: gated}
    result = {}
    for profile, text in variants.items():
        need(UPLOAD_OLD in text and UPLOAD_NEW not in text, "ORIGINAL_UPLOAD_PIN_DRIFT")
        result[profile + ":original-pins"] = text
        result[profile + ":reviewed-2026-10-20-pins"] = text.replace(
            "uses: actions/upload-artifact@" + UPLOAD_OLD,
            "uses: actions/upload-artifact@" + UPLOAD_NEW).replace(
                " # v7.0.1\n", " # v7.0.2\n")
    return result


def protected_m2_closure(git: Git, base: str, contract: dict) -> dict:
    registered = contract.get("preregistered_m2_source_closure")
    need(type(registered) is dict and registered.get("review_id") == "2026-10-20" and
         registered.get("source_review_commit") == "a42427693484409f9954125dada37d5db6c6f51e" and
         registered.get("actual_m1_prerequisite_observed_by_this_helper") is False and
         registered.get("protected_main_closure_observed_by_this_helper") is False and
         type(registered.get("files")) is dict and set(registered["files"]) == set(M2_SOURCE_FILES),
         "M2_SOURCE_PREREGISTRATION_DRIFT")
    observed = {}
    for path in M2_SOURCE_FILES:
        try:
            blob, raw = git.regular_blob(base, path)
        except Denied:
            raise Denied("M2_SOURCE_NOT_IN_PROTECTED_EVENT_BASE") from None
        actual = {"mode": "100644", "git_blob": blob, "bytes": len(raw),
                  "sha256": hashlib.sha256(raw).hexdigest()}
        need(actual == registered["files"][path], "M2_PROTECTED_SOURCE_CLOSURE_DRIFT")
        observed[path] = actual
    # This is source identity only. The exact M2 job must invoke its original
    # consumer, which requires a real M1 live_probe before any skip=true. The
    # protected-main Verify/Release and independent M1 qualification remain
    # prerequisites of the separate governed workflow-hookup stage.
    return {"files": observed, "actual_m1_prerequisite_observed_by_this_helper": False,
            "protected_main_closure_observed_by_this_helper": False,
            "independent_hookup_prerequisites_still_required": True}


def workflow_profile(text: str, variants: dict[str, str]) -> str:
    # Only leading unindented ASCII comments / blank lines are inert. YAML
    # parsers can treat NEL/U+2028/U+2029 as line boundaries inside a regex's
    # apparent comment; never normalize away those or other control characters.
    # The entire executable body, including Bind and every job field, is exact.
    body = re.sub(r"\A(?:#[\t\x20-\x7e]*\n|\n)*", "", text)
    matches = [name for name, template in variants.items() if body == template]
    need(len(matches) == 1, "WORKFLOW_EXECUTION_TEMPLATE_NOT_PREREGISTERED")
    return matches[0]


def frozen_science(git: Git, base: str, head: str, contract: dict) -> dict:
    # Historical ancestry remains source evidence. It never defines the set of
    # files attributed to this event, which is checked separately below.
    for left, right in ((QUALIFICATION_BASE, FROZEN_BASE), (FROZEN_BASE, SCIENCE_ANCHOR),
                        (SCIENCE_ANCHOR, base), (base, head)):
        need(git.sha(["merge-base", left, right]) == left, "FROZEN_SOURCE_ANCESTRY_DRIFT")
    need(type(contract.get("files")) is dict and
         set(contract["files"]) == {SCIENCE, MANIFEST, QUALIFICATION}, "SCIENCE_FILE_SET_DRIFT")
    original = {}
    for path in (SCIENCE, MANIFEST, QUALIFICATION):
        blob, raw = git.regular_blob(SCIENCE_ANCHOR, path)
        expected = {"mode": "100644", "git_blob": blob, "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest()}
        need(contract["files"][path] == expected, "FROZEN_GIT_IDENTITY_MAP_DRIFT")
        for revision in (base, head):
            actual_blob, actual_raw = git.regular_blob(revision, path)
            need(actual_blob == blob and actual_raw == raw, "SCIENTIFIC_SOURCE_OR_MANIFEST_CHANGED")
        original[path] = expected
    manifest = json_object(git.regular_blob(head, MANIFEST)[1])
    qualification = json_object(git.regular_blob(head, QUALIFICATION)[1])
    need(manifest["schema_version"] == 1 and manifest["authority"] == "DIAGNOSTIC_ONLY" and
         manifest["candidate_budget"] == 0 and manifest["base_main_sha"] == FROZEN_BASE and
         manifest["predecessor_qualification"] == contract["predecessor_qualification"] and
         qualification["authority"] == "SOURCE_QUALIFICATION_ONLY" and
         qualification["candidate_budget"] == 0 and
         qualification["predecessor_closure"] == contract["predecessor_closure"],
         "ORIGINAL_AUTHORITY_OR_PREDECESSOR_DRIFT")
    inventory = qualification["inventory_protocol"]
    need(inventory["inventory_frozen"] is True and inventory["expected_unique_room_count"] == 11 and
         inventory["expected_selected_objects"] == contract["frozen_corpus_inventory"] and
         inventory["expected_selected_fingerprint_sha256"] == contract["microset_fingerprint_sha256"] and
         manifest["source"]["official_code_revision"] == contract["official_code_revision"] and
         manifest["source"]["official_code_blobs"] == contract["official_code_blobs"],
         "ORIGINAL_CORPUS_OR_UPSTREAM_SOURCE_IDENTITY_DRIFT")
    expected_steps = contract.get("original_scientific_step_sha256")
    need(type(expected_steps) is dict and set(expected_steps) == set(SCIENTIFIC_STEPS),
         "ORIGINAL_SCIENTIFIC_STEP_SET_DRIFT")
    anchor_workflow = git.regular_blob(SCIENCE_ANCHOR, WORKFLOW)[1].decode("utf-8")
    variants = workflow_templates(anchor_workflow)
    need(contract.get("workflow_execution_template_sha256") == {
        name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in variants.items()},
         "WORKFLOW_EXECUTION_TEMPLATE_REGISTRATION_DRIFT")
    profiles = {}
    for revision in (base, head):
        text = git.regular_blob(revision, WORKFLOW)[1].decode("utf-8")
        permissions = re.findall(r"(?ms)^permissions:\n.*?(?=^\S|\Z)", text)
        need(len(permissions) == 1 and permissions[0].strip() == "permissions:\n  contents: read",
             "WORKFLOW_TOKEN_PERMISSION_DRIFT")
        for name in SCIENTIFIC_STEPS:
            frozen = scientific_step(anchor_workflow, name)
            need(hashlib.sha256(frozen).hexdigest() == expected_steps[name] and
                 scientific_step(text, name) == frozen, "ORIGINAL_SCIENTIFIC_STEP_BODY_DRIFT")
        profiles[revision] = workflow_profile(text, variants)
    m2_source = (protected_m2_closure(git, base, contract) if any(
        name.startswith(M2_PROFILE + ":") for name in profiles.values()) else None)
    return {"historical_base_sha": FROZEN_BASE, "science_anchor_sha": SCIENCE_ANCHOR,
            "source_qualification_ancestor_sha": QUALIFICATION_BASE, "files": original,
            "predecessor_qualification": manifest["predecessor_qualification"],
            "corpus_inventory_sha256": digest(inventory["expected_selected_objects"]),
            "microset_fingerprint_sha256": contract["microset_fingerprint_sha256"],
            "original_scientific_steps": len(SCIENTIFIC_STEPS),
            "workflow_execution_profiles": {"base": profiles[base], "head": profiles[head]},
            "protected_m2_source_identity": m2_source}


def current_scope(git: Git, scope: dict) -> dict:
    base, head, event_commit = (scope[k] for k in ("base_sha", "head_sha", "event_commit_sha"))
    for revision in (base, head, event_commit):
        need(git.sha(["rev-parse", revision + "^{commit}"]) == revision, "EVENT_OBJECT_NOT_A_COMMIT")
    need(git.sha(["merge-base", base, head]) == base, "EVENT_BASE_NOT_HEAD_ANCESTOR")
    parents = git.run(["rev-list", "--parents", "-n", "1", event_commit]).decode().split()
    if scope["event"] == "pull_request":
        need(parents == [event_commit, base, head], "PR_EVENT_MERGE_PARENT_DRIFT")
        need(git.sha(["rev-parse", event_commit + "^{tree}"]) ==
             git.sha(["rev-parse", head + "^{tree}"]), "PR_EVENT_MERGE_TREE_DRIFT")
    else:
        need(parents == [head, base], "PUSH_NOT_EXACT_SINGLE_PARENT_TRANSITION")
    # Two exact endpoints: not origin/main (which can move), and not the old
    # research base. No rename/copy/status framing may hide an extra path.
    raw = git.run(["diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                   "--raw", "--abbrev=40", "-z", base, head])
    parts = raw.decode("utf-8").split("\0")
    need(len(parts) == 3 and parts[-1] == "" and parts[1] == WORKFLOW and
         re.fullmatch(r":100644 100644 [0-9a-f]{40} [0-9a-f]{40} M", parts[0]) is not None,
         "CURRENT_EVENT_NOT_ONLY_EXISTING_DIAGNOSTIC_WORKFLOW")
    return {"semantics": "exact-event-two-endpoint-diff", "changed_paths": [WORKFLOW],
            "raw_diff_sha256": hashlib.sha256(raw).hexdigest(),
            "base_tree": git.sha(["rev-parse", base + "^{tree}"]),
            "head_tree": git.sha(["rev-parse", head + "^{tree}"])}


def validate_ruleset(ruleset: dict) -> str:
    need(type(ruleset) is dict and type(ruleset.get("id")) is int and
         ruleset["id"] == 21804005 and ruleset.get("target") == "branch" and
         ruleset.get("source_type") == "Repository" and ruleset.get("source") == REPO and
         ruleset.get("enforcement") == "active" and ruleset.get("bypass_actors") == [] and
         ruleset.get("conditions") == {"ref_name": {"exclude": [], "include": ["refs/heads/main"]}},
         "MAIN_RULESET_IDENTITY_OR_BYPASS_DRIFT")
    rules = ruleset.get("rules")
    need(type(rules) is list and len(rules) == 4 and all(type(r) is dict for r in rules),
         "MAIN_RULESET_RULE_SET_DRIFT")
    index = {rule.get("type"): rule for rule in rules}
    need(set(index) == {"deletion", "non_fast_forward", "pull_request", "required_status_checks"},
         "MAIN_RULESET_RULE_SET_DRIFT")
    pr = index["pull_request"].get("parameters", {})
    status = index["required_status_checks"].get("parameters", {})
    need(pr.get("allowed_merge_methods") == ["squash"] and
         pr.get("required_review_thread_resolution") is True and
         type(pr.get("required_approving_review_count")) is int and
         pr["required_approving_review_count"] == 0 and
         status.get("strict_required_status_checks_policy") is True and
         status.get("do_not_enforce_on_create") is False and
         status.get("required_status_checks") == [{"context": "summary", "integration_id": 15368}],
         "STRICT_MAIN_MERGE_POLICY_DRIFT")
    return digest(ruleset)


def pr_identity(pr: dict, scope: dict, event: dict, git: Git) -> dict:
    need(type(pr) is dict and type(pr.get("number")) is int and 0 < pr["number"] < 1_000_000 and
         pr.get("draft") is False, "PR_PROVENANCE_MISSING")
    base, head, user = pr.get("base", {}), pr.get("head", {}), pr.get("user", {})
    need(same_repo(base.get("repo")) and same_repo(head.get("repo")) and base.get("ref") == "main" and
         oid(base.get("sha")) == scope["base_sha"] and type(user) is dict and
         type(user.get("id")) is int and user["id"] > 0 and user.get("type") in ("User", "Bot") and
         type(user.get("login")) is str and re.fullmatch(r"[A-Za-z0-9_\[\]-]{1,100}", user["login"]),
         "PR_PROVENANCE_REPOSITORY_BASE_OR_AUTHOR_DRIFT")
    h = oid(head.get("sha"))
    if scope["event"] == "pull_request":
        original = event["pull_request"]
        need(pr["number"] == scope["pr_number"] and pr.get("state") == "open" and
             pr.get("merged") is False and h == scope["head_sha"] and
             pr.get("merge_commit_sha") == scope["event_commit_sha"] and
             head.get("ref") == original["head"]["ref"] and
             all(user.get(k) == original.get("user", {}).get(k) for k in ("login", "id", "type")),
             "LIVE_PR_SOURCE_OR_EVENT_METADATA_DRIFT")
    else:
        need(pr.get("state") == "closed" and pr.get("merged") is True and
             type(pr.get("merged_at")) is str and bool(pr["merged_at"]) and
             pr.get("merge_commit_sha") == scope["head_sha"], "PUSH_NOT_ASSOCIATED_MERGED_PR")
        need(git.sha(["merge-base", scope["base_sha"], h]) == scope["base_sha"] and
             git.sha(["rev-parse", h + "^{tree}"]) == git.sha(["rev-parse", scope["head_sha"] + "^{tree}"]),
             "MERGED_PR_HEAD_NOT_PUSH_TREE")
    return {"number": pr["number"], "base_sha": scope["base_sha"], "head_sha": h,
            "merge_commit_sha": pr.get("merge_commit_sha"), "state": pr["state"],
            "user": {k: user[k] for k in ("login", "id", "type")}}


class PublicGitHub:
    """Only bounded public GETs. No credentials, mutations or signed URLs."""
    def get(self, path: str):
        need(re.fullmatch(r"(?:git/ref/heads/main|rulesets/21804005|pulls/[0-9]+|actions/runs/[0-9]+|commits/[0-9a-f]{40}/pulls\?per_page=100)", path)
             is not None, "UNREVIEWED_API_PATH")
        url = "https://api.github.com/repos/" + REPO + "/" + path
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
            "User-Agent": "audio-pipeline-t1-m3-source/1", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                need(response.status == 200 and response.url == url, "PUBLIC_METADATA_STATUS_OR_REDIRECT")
                raw = response.read(MAX_BYTES + 1)
        except (OSError, urllib.error.URLError, TimeoutError):
            raise Denied("PUBLIC_SOURCE_METADATA_UNAVAILABLE") from None
        need(0 < len(raw) <= MAX_BYTES, "PUBLIC_METADATA_SIZE_BOUND")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs, parse_constant=no_constant)


def snapshot(api, git: Git, scope: dict, event: dict, *, fetch: bool) -> dict:
    ref = api.get("git/ref/heads/main")
    need(type(ref) is dict and ref.get("ref") == "refs/heads/main" and
         ref.get("object", {}).get("type") == "commit", "LIVE_MAIN_REF_IDENTITY_DRIFT")
    main = oid(ref["object"].get("sha"))
    expected_main = scope["base_sha"] if scope["event"] == "pull_request" else scope["head_sha"]
    need(main == expected_main, "MAIN_MOVED_OUTSIDE_CURRENT_EVENT")
    remote = git.run(["ls-remote", REMOTE, "refs/heads/main"], cap=4096).decode("ascii")
    need(remote == main + "\trefs/heads/main\n", "PUBLIC_API_AND_GIT_MAIN_REF_DIFFER")
    rules_hash = validate_ruleset(api.get("rulesets/21804005"))
    if scope["event"] == "pull_request":
        number = scope["pr_number"]
    else:
        associated = api.get("commits/" + scope["head_sha"] + "/pulls?per_page=100")
        need(type(associated) is list and 0 < len(associated) < 100 and
             all(type(p) is dict for p in associated), "PUSH_PR_ASSOCIATION_UNAVAILABLE")
        matches = [p for p in associated if p.get("merge_commit_sha") == scope["head_sha"] and
                   p.get("merged_at") is not None]
        need(len(matches) == 1 and type(matches[0].get("number")) is int,
             "AMBIGUOUS_MERGED_PUSH_PR")
        number = matches[0]["number"]
    need(type(number) is int and 0 < number < 1_000_000, "INVALID_PR_SOURCE_NUMBER")
    pr = api.get("pulls/" + str(number))
    need(type(pr) is dict and type(pr.get("number")) is int and pr["number"] == number,
         "PUBLIC_PR_ENDPOINT_IDENTITY_DRIFT")
    if fetch:
        revisions = sorted({scope["base_sha"], scope["head_sha"], scope["event_commit_sha"],
                            oid(pr.get("head", {}).get("sha"))})
        git.run(["fetch", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
                 REMOTE, *revisions], cap=8192)
    identity = pr_identity(pr, scope, event, git)
    if scope["event"] == "pull_request":
        pull_ref = "refs/pull/" + str(number) + "/head"
        actual = git.run(["ls-remote", REMOTE, pull_ref], cap=4096).decode("ascii")
        need(actual == scope["head_sha"] + "\t" + pull_ref + "\n", "LIVE_PR_HEAD_REF_DRIFT")
    run = api.get("actions/runs/" + scope["github_run_id"])
    # run.pull_requests[*].head/base are NOT immutable: the old red run
    # 38512536044 now exposes the rebased PR refs in that array. Bind the run's
    # own head_sha plus this event's independently verified Git endpoints.
    need(type(run) is dict and type(run.get("id")) is int and
         run["id"] == int(scope["github_run_id"]) and
         type(run.get("run_attempt")) is int and run["run_attempt"] == int(scope["github_run_attempt"]) and
         same_repo(run.get("repository")) and same_repo(run.get("head_repository")) and
         run.get("event") == scope["event"] and run.get("path") == WORKFLOW and
         run.get("head_sha") == scope["head_sha"] and
         run.get("head_branch") == (pr["head"]["ref"] if scope["event"] == "pull_request" else "main") and
         run.get("status") == "in_progress" and run.get("conclusion") is None,
         "CURRENT_RUN_IDENTITY_OR_EXECUTION_CONTEXT_DRIFT")
    return {"current_main_sha": main, "ruleset_id": 21804005,
            "ruleset_sha256": rules_hash, "pr": identity,
            "run": {key: run[key] for key in ("id", "run_attempt", "event", "path", "head_sha", "head_branch")}}


def evaluate(event: dict, env: dict, git: Git, api, *, live: bool = False) -> dict:
    result = {"schema_version": 1, "decision": NEGATIVE, "source_range_qualified": False,
              "implementation_stage": "DORMANT_SOURCE_AND_EVENT_RANGE_ONLY", "workflow": WORKFLOW,
              "scientific_experiment_executed": False, "acoustic_pass": False,
              "corpus_materialized_or_verified": False, "skip_measurement": False,
              "automated_bypass_enabled": False, "maintenance_push_admitted": False,
              "workflow_hookup_admitted": False, "m1_m2_prerequisites_closed": False,
              "live_public_metadata_checked": False,
              "evidence_role": "live-source-observation" if live else "offline-engineering-fixture"}
    try:
        repository_context(git)
        scope = event_range(event, env)
        contract, policy_hashes = verify_policy_source(git, scope["base_sha"])
        before = snapshot(api, git, scope, event, fetch=True)
        current = current_scope(git, scope)
        frozen = frozen_science(git, scope["base_sha"], scope["head_sha"], contract)
        after = snapshot(api, git, scope, event, fetch=False)
        need(before == after, "SOURCE_OR_RULESET_MOVED_DURING_QUALIFICATION")
        result.update(decision=POSITIVE, source_range_qualified=True,
                      reason="UNCHANGED_ORIGINAL_SCIENCE_EXACT_CURRENT_EVENT_SCOPE",
                      event=scope, current_event=current, frozen_source=frozen,
                      protected_policy=policy_hashes, public_source=after,
                      live_public_metadata_checked=live)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, AttributeError) as exc:
        reason = str(exc)
        result.update(decision=NEGATIVE, source_range_qualified=False,
                      reason=reason if re.fullmatch(r"[A-Z0-9_]{1,100}", reason) else "SOURCE_OR_EVENT_NOT_ADMITTED")
    return result


def write_receipt(path: Path, result: dict) -> str:
    raw = (json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    need(len(raw) <= MAX_RECEIPT_BYTES, "SOURCE_RECEIPT_SIZE_BOUND")
    need(not path.exists() and not path.is_symlink(), "EXISTING_RECEIPT_MUST_BE_PRESERVED")
    seal = path.with_name(path.name + ".sha256")
    need(not seal.exists() and not seal.is_symlink(), "EXISTING_RECEIPT_SEAL_MUST_BE_PRESERVED")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    sha = hashlib.sha256(raw).hexdigest()
    with seal.open("x", encoding="ascii") as stream:
        stream.write(sha + "  " + path.name + "\n")
    return sha


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-file", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        need(args.event_file.is_file() and not args.event_file.is_symlink() and
             0 < args.event_file.stat().st_size <= MAX_BYTES, "BOUNDED_REGULAR_EVENT_FILE_REQUIRED")
        event = json_object(args.event_file.read_bytes())
    except (ValueError, OSError, UnicodeError) as exc:
        event = {}
        invalid_reason = str(exc)
    else:
        invalid_reason = None
    result = evaluate(event, dict(os.environ), Git(ROOT), PublicGitHub(), live=True)
    if invalid_reason:
        result.update(decision=NEGATIVE, source_range_qualified=False,
                      reason=invalid_reason if re.fullmatch(r"[A-Z0-9_]{1,100}", invalid_reason) else "INVALID_EVENT_JSON")
    try:
        sha = write_receipt(args.receipt, result)
    except (ValueError, OSError):
        print("SOURCE_RECEIPT_WRITE_FAILED_PREVIOUS_EVIDENCE_PRESERVED", file=sys.stderr)
        return 2
    print(json.dumps({"decision": result["decision"], "reason": result["reason"],
                      "receipt_sha256": sha, "scientific_experiment_executed": False,
                      "skip_measurement": False}, sort_keys=True))
    return 0 if result["source_range_qualified"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
