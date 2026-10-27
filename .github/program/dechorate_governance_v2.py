#!/usr/bin/env python3
"""Bounded dEchorate PRE/POST transport; no production or maintenance authority."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SELF = ".github/program/dechorate_governance_v2.py"
PLAN = ".github/program/dechorate_governance_v2.json"
PRODUCER = ".github/workflows/ci-dechorate-governance-evidence.yml"
PRODUCER_NAME = "dEchorate Governance Evidence V2"
LEGACY = ".github/program/dechorate_event_source_t1m3.py"
LEGACY_PLAN = ".github/program/dechorate_event_source_t1m3.json"
GOVERNANCE = "scripts/github_governance.py"
REPO = "jiying2007/audio-pipeline"
REPO_ID = 1347377137
PR_NUMBER = 833
IDENTITY = "DECHORATE_GOVERNANCE_TRANSPORT_V2_F0"
MAX_JSON = 96_000
MAX_ZIP = 180_000
ARTIFACT_DOWNLOAD_SECONDS = 45
SCIENCE_WORKFLOW = ".github/workflows/research-dechorate-ground-truth-diagnostic-v1.yml"
SCIENCE_NAME = "Research dEchorate Ground-Truth Diagnostic V1"
FALSE_FLAGS = ("production_admission_enabled", "scientific_experiment_executed",
               "acoustic_pass", "skip_measurement", "maintenance_push_admitted",
               "shipping_authority")
EXISTING = (LEGACY, LEGACY_PLAN, GOVERNANCE,
            ".github/program/workflow_pin_pr_consumer.py",
            ".github/program/workflow_pin_only_actual_tree_t1m1.py",
            ".github/program/workflow_pin_only_scope.py",
            ".github/program/workflow_pin_only_bot714_20261020.json")
CLOSURE = (SELF, PLAN, PRODUCER, *EXISTING)


# Two independently identified source closures: previous M2 is historical only.
# New V2 base must match *all* current protected-main-derived bytes; no subset
# may self-authorize a new source. Updating these requires a reviewed code delta.
FROZEN_PREVIOUS_DEPENDENCIES = {
    ".github/program/dechorate_event_source_t1m3.json": "d01181f971569a60579067b4c8a3ce428525570e6e451368bd08708eac43f928",
    ".github/program/dechorate_event_source_t1m3.py": "8002174cd3a5418fffb400da811dc35d684ee7a2293e2f8c25422838cd64cff3",
    ".github/program/workflow_pin_only_actual_tree_t1m1.py": "6d080c55e0334b96279f826e1615802cf1a8b58d57c1d9c8900900560d25ffd7",
    ".github/program/workflow_pin_only_bot714_20261020.json": "47ac0756f4989f619403f3689ce3fc305ec82469730da908559937ef03f86abb",
    ".github/program/workflow_pin_only_scope.py": "fcce117736d32a2cafd3c95fc93a27f906f40b64f632116cd90e8ba1759d68cb",
    ".github/program/workflow_pin_pr_consumer.py": "be63c093dac9125ac7c2603b69ea1c8211705eea1a8d143b110a3f0c01d5dab7",
    "scripts/github_governance.py": "c292105f27126e643f8984bd0ecb52faf7beac83ddeffff9413b97a68893c4fa"
}
CURRENT_REVIEWED_DEPENDENCIES = {
    ".github/program/dechorate_event_source_t1m3.py": "dfa8fe7730590a8cd8ce97392e7fd072763fec59b3bae53581cfed93f34c7300",
    ".github/program/dechorate_event_source_t1m3.json": "687f506a0c742aa600596a77781adffcc083524549cc04dee9808e6eb7bd165e",
    "scripts/github_governance.py": "c292105f27126e643f8984bd0ecb52faf7beac83ddeffff9413b97a68893c4fa",
    ".github/program/workflow_pin_pr_consumer.py": "be63c093dac9125ac7c2603b69ea1c8211705eea1a8d143b110a3f0c01d5dab7",
    ".github/program/workflow_pin_only_actual_tree_t1m1.py": "156c2f14f02c12fe11de83d52f4c3e54a84e2ebbb558b5dd387a023d547299dc",
    ".github/program/workflow_pin_only_scope.py": "257eaca86109021ea33e2dc3191fcc9326cbee361c22c9b0c6e88862f7f8f1db",
    ".github/program/workflow_pin_only_bot714_20261020.json": "47ac0756f4989f619403f3689ce3fc305ec82469730da908559937ef03f86abb"
}



class Denied(ValueError):
    pass


class PrivateBypassRefused(Denied):
    def __init__(self, observations: list[dict]):
        super().__init__("AUTHENTICATED_BYPASS_NOT_EMPTY_NOT_PUBLISHED")
        self.observations = observations


def need(value: bool, code: str) -> None:
    if not value:
        raise Denied(code)


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    need(spec is not None and spec.loader is not None, "PROTECTED_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source = load_module("dechorate_v2_protected_source", LEGACY)
governance = load_module("dechorate_v2_existing_governance", GOVERNANCE)


def encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parsed(raw: bytes) -> dict:
    need(0 < len(raw) <= MAX_JSON, "JSON_SIZE_BOUND")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=source.strict_pairs,
                        parse_constant=source.no_constant)
    need(type(result) is dict, "JSON_OBJECT_REQUIRED")
    return result


def integer(value: object) -> int:
    need(type(value) is int and 0 < value < 10**19, "CANONICAL_POSITIVE_INTEGER_REQUIRED")
    return value


def cli_integer(value: str) -> int:
    need(re.fullmatch(r"[1-9][0-9]{0,18}", value) is not None, "CANONICAL_INTEGER_TEXT_REQUIRED")
    return integer(int(value))


def instant(value: str) -> datetime:
    need(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", value)
         is not None, "OFFSET_TIMESTAMP_REQUIRED")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def utc_instant(value: str) -> datetime:
    need(type(value) is str and value.endswith(("Z", "+00:00")), "LOCAL_UTC_TIMESTAMP_REQUIRED")
    return instant(value)


def api_time_upper(value: str) -> datetime:
    """Exclusive end of the API timestamp's stated precision interval."""
    lower = instant(value)
    fraction = re.search(r"\.(\d+)(?:Z|[+-]\d\d:\d\d)$", value)
    return lower + timedelta(microseconds=10 ** (6 - len(fraction[1])) if fraction else 1_000_000)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def envelope(phase: str, decision: str) -> dict:
    return {"schema_version": 2, "candidate_id": IDENTITY, "phase": phase,
            "decision": decision, **{key: False for key in FALSE_FLAGS}}


def validate_envelope(value: dict, phase: str) -> None:
    need(value.get("schema_version") == 2 and value.get("candidate_id") == IDENTITY and
         value.get("phase") == phase and all(value.get(key) is False for key in FALSE_FLAGS),
         "PROTOCOL_ENVELOPE_OR_AUTHORITY_DRIFT")


def write_new(path: Path, value: dict) -> None:
    raw = encoded(value)
    need(len(raw) <= MAX_JSON, "RECEIPT_SIZE_BOUND")
    seal = path.with_name(path.name + ".sha256")
    need(not path.exists() and not path.is_symlink() and not seal.exists() and not seal.is_symlink(),
         "PREVIOUS_EVIDENCE_MUST_BE_PRESERVED")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    with seal.open("x", encoding="ascii") as stream:
        stream.write(sha(raw) + "  " + path.name + "\n")


def plan() -> dict:
    value = parsed((ROOT / PLAN).read_bytes())
    need(value.get("candidate_id") == IDENTITY and value.get("schema_version") == 2 and
         value.get("production_admission_enabled") is False and
         value.get("canonical_pr") == PR_NUMBER and
         value.get("consumer_attempts") == {"pull_request": [1, 2], "push": [1, 2]} and
         value.get("producer_attempts") == [1] and
         value.get("execution_closure") == list(CLOSURE) and
         set(value.get("existing_dependencies", {})) == set(EXISTING) and
         set(value.get("historical_existing_dependencies", {})) == set(EXISTING) and
         value["historical_existing_dependencies"] == FROZEN_PREVIOUS_DEPENDENCIES and
         value["existing_dependencies"] == CURRENT_REVIEWED_DEPENDENCIES and
         value.get("scientific_experiment_executed") is False and
         value.get("forward_review_scope", "").startswith("source-only:"), "FROZEN_PLAN_DRIFT")
    return value


def lock_at(git, revision: str) -> dict:
    source.oid(revision)
    result = {}
    for name in CLOSURE:
        blob, raw = git.regular_blob(revision, name)
        result[name] = {"mode": "100644", "git_blob": blob, "bytes": len(raw), "sha256": sha(raw)}
    return result


def local_source(git, revision: str) -> dict:
    source.repository_context(git)
    need(git.sha(["rev-parse", "HEAD"]) == revision, "EXECUTION_CHECKOUT_NOT_EXACT_SOURCE")
    result = lock_at(git, revision)
    need(Path(__file__).resolve() == git.root / SELF, "EXECUTED_TRANSPORT_PATH_DRIFT")
    for name, item in result.items():
        path = git.root / name
        need(path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == item["sha256"],
             "UNPROTECTED_EXECUTION_SOURCE")
    registered = plan()
    for name in EXISTING:
        need(result[name]["sha256"] == registered["existing_dependencies"][name],
             "EXISTING_EXECUTION_DEPENDENCY_DRIFT")
    return result


def producer_source(scope: dict) -> str:
    need(scope.get("event") in ("pull_request", "push"), "UNSUPPORTED_CONSUMER_EVENT")
    return source.oid(scope["base_sha"] if scope["event"] == "pull_request" else scope["head_sha"])


def stable_scope(scope: dict) -> dict:
    need(set(scope) == {"event", "base_sha", "head_sha", "event_commit_sha", "pr_number",
                        "github_run_id", "github_run_attempt"}, "CHALLENGE_SCOPE_SCHEMA_DRIFT")
    need(scope["event"] in ("pull_request", "push") and
         cli_integer(scope["github_run_attempt"]) in (1, 2) and
         type(scope["pr_number"]) is int and
         scope["pr_number"] == (PR_NUMBER if scope["event"] == "pull_request" else 0),
         "CANONICAL_CONSUMER_OR_ATTEMPT_REQUIRED")
    for key in ("base_sha", "head_sha", "event_commit_sha"):
        source.oid(scope[key])
    cli_integer(scope["github_run_id"])
    return {key: value for key, value in scope.items() if key != "github_run_attempt"}


def public_projection(value: dict) -> dict:
    """A public comparison only: no result from here attests zero bypass."""
    need(type(value) is dict and value.get("id") == 21804005 and value.get("target") == "branch" and
         value.get("source_type") == "Repository" and value.get("source") == REPO and
         value.get("enforcement") == "active" and
         value.get("conditions") == {"ref_name": {"exclude": [], "include": ["refs/heads/main"]}},
         "PUBLIC_RULESET_IDENTITY_DRIFT")
    if "bypass_actors" in value:
        need(type(value["bypass_actors"]) is list and value["bypass_actors"] == [],
             "VISIBLE_BYPASS_LIST_NOT_EMPTY")
    # Reuse the existing structural policy on an explicitly non-authoritative
    # projection. The original object is never completed with default fields,
    # and this function cannot return a full-governance or source qualification.
    projection = {key: value[key] for key in ("id", "name", "target", "source_type", "source",
                  "enforcement", "conditions", "rules", "node_id", "created_at", "updated_at")}
    structural = dict(projection, bypass_actors=[])
    source.validate_ruleset(structural)
    instant(projection["created_at"])
    instant(projection["updated_at"])
    return projection


class API:
    """Fixed same-repository GETs only; credentials never appear in arguments."""
    def __init__(self, token: str | None = None):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", os.environ.get("GH_TOKEN"))

    def get(self, path: str):
        allowed = (r"(?:git/ref/heads/main|pulls/833|commits/[0-9a-f]{40}/pulls\?per_page=100|"
                   r"actions/runs/[0-9]+(?:/attempts/[12])?(?:/jobs\?per_page=100|/artifacts\?per_page=100)?|"
                   r"actions/workflows/(?:ci-dechorate-governance-evidence|research-dechorate-ground-truth-diagnostic-v1)\.yml"
                   r"(?:/runs\?event=workflow_run&branch=main&per_page=100)?)")
        need(re.fullmatch(allowed, path) is not None, "UNREVIEWED_METADATA_PATH")
        result = governance._gh_json(["repos/" + REPO + "/" + path], token=self.token)
        need(len(encoded(result)) <= 1_000_000, "METADATA_RESPONSE_SIZE_BOUND")
        return result

    def public_ruleset(self) -> dict:
        url = "https://api.github.com/repos/" + REPO + "/rulesets/21804005"
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
            "User-Agent": "audio-pipeline-dechorate-governance-v2", "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=15) as response:
            need(response.status == 200 and response.url == url, "PUBLIC_RULESET_RESPONSE_DRIFT")
            return parsed(response.read(MAX_JSON + 1))

    def archive(self, artifact_id: int) -> bytes:
        command = ["gh", "api", "repos/" + REPO + "/actions/artifacts/" + str(integer(artifact_id)) + "/zip"]
        environment = dict(os.environ)
        environment.pop("REPOSITORY_GOVERNANCE_TOKEN", None)
        if self.token:
            environment["GH_TOKEN"] = self.token
        process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        data = bytearray()
        deadline = time.monotonic() + ARTIFACT_DOWNLOAD_SECONDS
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    need(remaining > 0, "ARTIFACT_DOWNLOAD_DEADLINE")
                    ready = selector.select(remaining)
                    need(bool(ready), "ARTIFACT_DOWNLOAD_DEADLINE")
                    chunk = os.read(process.stdout.fileno(), min(8192, MAX_ZIP + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    need(len(data) <= MAX_ZIP, "ARTIFACT_DOWNLOAD_SIZE_BOUND")
            need(process.wait(timeout=max(0.001, deadline-time.monotonic())) == 0 and bool(data),
                 "ARTIFACT_DOWNLOAD_FAILED_OR_EMPTY")
            return bytes(data)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            process.stdout.close()


def workflow_id(api, path: str, name: str) -> int:
    record = api.get("actions/workflows/" + Path(path).name)
    need(type(record) is dict and record.get("path") == path and record.get("name") == name and
         record.get("state") == "active", "WORKFLOW_API_IDENTITY_DRIFT")
    return integer(record.get("id"))


def run_record(api, run_id: int, attempt: int, *, producer: bool = False, completed: bool = True) -> dict:
    need(attempt in ((1,) if producer else (1, 2)), "ATTEMPT_BUDGET_EXCEEDED")
    value = api.get(f"actions/runs/{integer(run_id)}/attempts/{attempt}")
    path, name = (PRODUCER, PRODUCER_NAME) if producer else (SCIENCE_WORKFLOW, SCIENCE_NAME)
    need(type(value) is dict and value.get("id") == run_id and value.get("run_attempt") == attempt and
         source.same_repo(value.get("repository")) and source.same_repo(value.get("head_repository")) and
         value.get("path") == path and value.get("name") == name and
         value.get("workflow_id") == workflow_id(api, path, name) and
         value.get("event") in (("workflow_run",) if producer else ("pull_request", "push")),
         "ACTUAL_RUN_IDENTITY_DRIFT")
    if completed:
        need(value.get("status") == "completed", "ACTUAL_RUN_NOT_COMPLETED")
    else:
        need(value.get("status") == "in_progress" and value.get("conclusion") is None,
             "CONSUMER_NOT_ACTUALLY_RUNNING")
    if producer:
        need(api.get(f"actions/runs/{run_id}").get("run_attempt") == 1,
             "PRODUCER_RERUN_OUTSIDE_FROZEN_BUDGET")
    return value


def target_snapshot(api, git, scope: dict, event: dict, *, completed: bool, fetch: bool) -> dict:
    stable_scope(scope)
    expected_main = producer_source(scope)
    ref = api.get("git/ref/heads/main")
    need(ref.get("ref") == "refs/heads/main" and ref.get("object", {}).get("type") == "commit" and
         ref["object"].get("sha") == expected_main, "LIVE_MAIN_OUTSIDE_EVENT")
    actual_ref = git.run(["ls-remote", source.REMOTE, "refs/heads/main"], cap=4096).decode("ascii")
    need(actual_ref == expected_main + "\trefs/heads/main\n", "API_GIT_MAIN_REF_DIFFER")
    pr = api.get("pulls/833")
    if fetch:
        revisions = sorted({scope["base_sha"], scope["head_sha"], scope["event_commit_sha"],
                            source.oid(pr.get("head", {}).get("sha"))})
        git.run(["fetch", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
                 source.REMOTE, *revisions], cap=8192)
    need(pr.get("number") == PR_NUMBER, "CANONICAL_PR_REQUIRED")
    identity = source.pr_identity(pr, scope, event, git)
    if scope["event"] == "push":
        associated = api.get("commits/" + scope["head_sha"] + "/pulls?per_page=100")
        need(type(associated) is list and len(associated) < 100, "PUSH_ASSOCIATION_BOUND")
        merged = [p for p in associated if p.get("merge_commit_sha") == scope["head_sha"] and p.get("merged_at")]
        need(len(merged) == 1 and merged[0].get("number") == PR_NUMBER, "PUSH_NOT_UNIQUE_MERGED_833")
    else:
        refname = "refs/pull/833/head"
        need(git.run(["ls-remote", source.REMOTE, refname], cap=4096).decode("ascii") ==
             scope["head_sha"] + "\t" + refname + "\n", "LIVE_PR_HEAD_REF_DRIFT")
    record = run_record(api, cli_integer(scope["github_run_id"]), cli_integer(scope["github_run_attempt"]),
                        completed=completed)
    need(record.get("event") == scope["event"] and record.get("head_sha") == scope["head_sha"] and
         record.get("head_branch") == (pr["head"]["ref"] if scope["event"] == "pull_request" else "main"),
         "RUN_EVENT_HEAD_DRIFT")
    closure = lock_at(git, scope["base_sha"])
    need(closure == lock_at(git, expected_main), "PROTOCOL_SOURCE_CHANGED_BETWEEN_BASE_AND_PRODUCER")
    return {"main_sha": expected_main, "pr": identity, "execution_closure": closure,
            "run": {key: record[key] for key in ("id", "run_attempt", "event", "path", "workflow_id",
                     "head_sha", "head_branch", "status", "conclusion", "run_started_at", "created_at")}}


def event_identity(event: dict, scope: dict) -> dict:
    if scope["event"] == "pull_request":
        pr = event["pull_request"]
        return {"pull_request": {"head": {"ref": pr["head"]["ref"]},
                                 "user": {key: pr["user"][key] for key in ("login", "id", "type")}}}
    return {}


def challenge(event: dict, env: dict, git, api) -> dict:
    scope = source.event_range(event, env)
    stable_scope(scope)
    closure = local_source(git, scope["base_sha"])
    contract, policy = source.verify_policy_source(git, scope["base_sha"])
    before = target_snapshot(api, git, scope, event, completed=False, fetch=True)
    first = public_projection(api.public_ruleset())
    current = source.current_scope(git, scope)
    frozen = source.frozen_science(git, scope["base_sha"], scope["head_sha"], contract)
    second = public_projection(api.public_ruleset())
    after = target_snapshot(api, git, scope, event, completed=False, fetch=False)
    need(before == after and first == second, "PUBLIC_SOURCE_MOVED_DURING_CHALLENGE")
    return dict(envelope("CHALLENGE", "PENDING_AUTHENTICATED_PRE"),
                scope=scope, event_identity=event_identity(event, scope), source_lock=closure,
                protected_policy=policy, current_event=current, frozen_source=frozen,
                public_source=after, public_ruleset=second, observed_at_utc=now(),
                source_range_qualified=False, governance_post_qualified=False)


def validate_challenge(value: dict, git) -> dict:
    validate_envelope(value, "CHALLENGE")
    need(value.get("decision") == "PENDING_AUTHENTICATED_PRE" and
         value.get("source_range_qualified") is False and value.get("governance_post_qualified") is False,
         "OLD_OR_NON_CHALLENGE_RECEIPT")
    scope = value["scope"]
    stable_scope(scope)
    need(scope["github_run_attempt"] == "1", "CHALLENGE_NOT_ATTEMPT_ONE")
    need(value.get("source_lock") == lock_at(git, scope["base_sha"]), "CHALLENGE_SOURCE_CLOSURE_DRIFT")
    need(value.get("public_source", {}).get("main_sha") == producer_source(scope) and
         value["public_source"].get("execution_closure") == value["source_lock"],
         "CHALLENGE_PUBLIC_SOURCE_DRIFT")
    contract = parsed(git.regular_blob(scope["base_sha"], LEGACY_PLAN)[1])
    need(value.get("current_event") == source.current_scope(git, scope) and
         value.get("frozen_source") == source.frozen_science(git, scope["base_sha"], scope["head_sha"], contract),
         "CHALLENGE_REAL_GIT_PROOF_DRIFT")
    public_projection(value["public_ruleset"])
    utc_instant(value["observed_at_utc"])
    return scope


def zip_receipt(raw: bytes, metadata: dict, filename: str) -> dict:
    need(type(metadata.get("id")) is int and metadata.get("expired") is False and
         type(metadata.get("size_in_bytes")) is int and 0 < metadata["size_in_bytes"] <= MAX_ZIP and
         len(raw) == metadata["size_in_bytes"] and metadata.get("digest") == "sha256:" + sha(raw),
         "ARTIFACT_ORIGINAL_ZIP_IDENTITY_DRIFT")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        names = [entry.filename for entry in members]
        need(len(names) == 2 and set(names) == {filename, filename + ".sha256"}, "ARTIFACT_MEMBER_SET_DRIFT")
        for entry in members:
            mode = entry.external_attr >> 16
            need(not entry.is_dir() and not entry.flag_bits & 1 and
                 (mode & 0o170000) in (0, 0o100000) and 0 < entry.file_size <= MAX_JSON,
                 "UNSAFE_ARTIFACT_MEMBER")
        content = archive.read(filename)
        need(archive.read(filename + ".sha256") == (sha(content) + "  " + filename + "\n").encode(),
             "ARTIFACT_INNER_SEAL_DRIFT")
    return parsed(content)


def artifact(api, record: dict, name: str, filename: str) -> tuple[dict, dict]:
    listed = api.get(f"actions/runs/{record['id']}/artifacts?per_page=100")
    need(type(listed) is dict and type(listed.get("total_count")) is int and listed["total_count"] < 100 and
         len(listed.get("artifacts", [])) == listed["total_count"], "COMPLETE_BOUNDED_ARTIFACT_LIST_REQUIRED")
    selected = [entry for entry in listed["artifacts"] if entry.get("name") == name]
    need(len(selected) == 1, "UNIQUE_ACTUAL_ARTIFACT_REQUIRED")
    item = selected[0]
    origin = item.get("workflow_run", {})
    need(origin.get("id") == record["id"] and origin.get("head_sha") == record["head_sha"] and
         origin.get("head_branch") == record["head_branch"], "ARTIFACT_ACTUAL_RUN_OR_SOURCE_DRIFT")
    raw = api.archive(integer(item.get("id")))
    receipt = zip_receipt(raw, item, filename)
    return receipt, {"id": item["id"], "name": name, "size_in_bytes": len(raw),
                     "zip_sha256": sha(raw), "canonical_json_sha256": sha(encoded(receipt)),
                     "producer_run_id": record["id"], "producer_run_attempt": record["run_attempt"]}


def consumer_receipt(api, run_id: int, attempt: int) -> tuple[dict, dict, dict]:
    record = run_record(api, run_id, attempt)
    name = f"dechorate-event-source-range-{run_id}-{attempt}"
    receipt, evidence = artifact(api, record, name, "source-range.json")
    need(receipt.get("scope", {}).get("github_run_id") == str(run_id) and
         receipt["scope"].get("github_run_attempt") == str(attempt), "CONSUMER_ARTIFACT_ATTEMPT_DRIFT")
    return receipt, evidence, record


def completed_steps(api, record: dict, *, producer: bool = False, first: bool = False) -> dict:
    need(record.get("status") == "completed" and
         record.get("conclusion") == ("failure" if first else "success"), "ACTUAL_RUN_NOT_EXPECTED_CONCLUSION")
    listing = api.get(f"actions/runs/{record['id']}/attempts/{record['run_attempt']}/jobs?per_page=100")
    need(type(listing.get("total_count")) is int and listing["total_count"] < 100 and
         len(listing.get("jobs", [])) == listing["total_count"], "COMPLETE_BOUNDED_JOB_LIST_REQUIRED")
    jobs = [job for job in listing["jobs"] if job.get("name") == ("observe" if producer else "diagnostic")]
    need(len(jobs) == 1, "UNIQUE_ACTUAL_JOB_REQUIRED")
    job = jobs[0]
    need(job.get("run_id") == record["id"] and job.get("run_attempt") == record["run_attempt"] and
         job.get("head_sha") == record["head_sha"] and job.get("workflow_name") == record["name"],
         "ACTUAL_JOB_RUN_ATTEMPT_SOURCE_DRIFT")
    need(job.get("status") == "completed" and job.get("conclusion") == ("failure" if first else "success"),
         "ACTUAL_JOB_NOT_EXPECTED_CONCLUSION")
    # GitHub may create an attempt record after its reported run start. Its
    # created_at is identity metadata, not a chronological predecessor.
    need(instant(record["run_started_at"]) <= instant(job["started_at"]) <=
         instant(job["completed_at"]) <= instant(record["updated_at"]), "ACTUAL_JOB_INTERVAL_DRIFT")
    steps = {step["name"]: step for step in job.get("steps", [])}
    need(len(steps) == len(job.get("steps", [])), "DUPLICATE_JOB_STEP_NAME")
    names = (["Validate protected producer context", "Collect authenticated governance observation",
              "Preserve authenticated observation"] if producer else
             [source.BIND_STEP, "Preserve the independent source-range decision"])
    for name in names:
        expected = "failure" if first and name == source.BIND_STEP else "success"
        need(steps.get(name, {}).get("status") == "completed" and
             steps[name].get("conclusion") == expected, "REQUIRED_ACTUAL_STEP_NOT_SUCCESS")
    if not producer:
        contract = parsed((ROOT / LEGACY_PLAN).read_bytes())
        for name in contract["original_scientific_step_sha256"]:
            expected = "skipped" if first and name != "Check out exact source" else "success"
            need(steps.get(name, {}).get("status") == "completed" and
                 steps[name].get("conclusion") == expected, "ORIGINAL_SCIENCE_STEP_EXECUTION_DRIFT")
    proof = {key: job[key] for key in ("run_id", "run_attempt", "head_sha", "workflow_name", "name",
                                     "conclusion", "started_at", "completed_at")}
    proof["id"] = integer(job.get("id"))
    if producer:
        acquisition = steps["Collect authenticated governance observation"]
        need(instant(job["started_at"]) <= instant(acquisition["started_at"]) <=
             instant(acquisition["completed_at"]) <= instant(job["completed_at"]),
             "ACTUAL_ACQUISITION_STEP_INTERVAL_DRIFT")
        proof["acquisition_step"] = {key: acquisition[key] for key in ("started_at", "completed_at")}
    return proof


def first_job(api, original: dict, record: dict) -> dict:
    proof = completed_steps(api, record, first=True)
    need(instant(proof["started_at"]) <= utc_instant(original["observed_at_utc"]) <
         api_time_upper(proof["completed_at"]), "CHALLENGE_OUTSIDE_ACTUAL_CONSUMER_JOB")
    return proof


def producer_environment(env: dict) -> tuple[int, str]:
    need(env.get("GITHUB_EVENT_NAME") == "workflow_run" and env.get("GITHUB_REPOSITORY") == REPO and
         env.get("GITHUB_REF") == "refs/heads/main" and
         env.get("GITHUB_WORKFLOW_REF") == REPO + "/" + PRODUCER + "@refs/heads/main",
         "UNTRUSTED_PRODUCER_EXECUTION_CONTEXT")
    revision = source.oid(env.get("GITHUB_SHA"))
    need(env.get("GITHUB_WORKFLOW_SHA") == revision and env.get("GITHUB_RUN_ATTEMPT") == "1",
         "PRODUCER_SOURCE_OR_ATTEMPT_DRIFT")
    return cli_integer(env.get("GITHUB_RUN_ID", "")), revision


def preflight(event: dict, env: dict, git, api) -> dict:
    own_id, revision = producer_environment(env)
    closure = local_source(git, revision)
    need(event.get("action") == "completed" and source.same_repo(event.get("repository")),
         "UNTRUSTED_COMPLETION_EVENT")
    target = event.get("workflow_run", {})
    target_id, attempt = integer(target.get("id")), integer(target.get("run_attempt"))
    need(attempt in (1, 2), "CONSUMER_ATTEMPT_BUDGET_EXCEEDED")
    actual = run_record(api, target_id, attempt)
    need(all(target.get(key) == actual.get(key) for key in
             ("id", "run_attempt", "path", "workflow_id", "event", "head_sha", "head_branch", "status", "conclusion")) and
         source.same_repo(target.get("repository")) and source.same_repo(target.get("head_repository")),
         "COMPLETION_PAYLOAD_API_DRIFT")
    original, original_proof, first_run = consumer_receipt(api, target_id, 1)
    scope = validate_challenge(original, git)
    need(revision == producer_source(scope), "PRODUCER_D_NOT_BOUND_CURRENT_SOURCE")
    first_job(api, original, first_run)
    own = run_record(api, own_id, 1, producer=True, completed=False)
    need(own.get("head_sha") == revision and own.get("head_branch") == "main", "PRODUCER_API_SOURCE_DRIFT")
    current_scope = dict(scope, github_run_attempt=str(attempt))
    current = target_snapshot(api, git, current_scope, original["event_identity"], completed=True, fetch=True)
    need(closure == original["source_lock"], "PRODUCER_CONSUMER_SOURCE_LOCK_DIFFER")
    need(current["pr"] == original["public_source"]["pr"], "ORIGINAL_PUBLIC_PR_IDENTITY_DRIFT")
    result = dict(envelope("CONTEXT", "PRODUCER_PREFLIGHT_ONLY_NO_ACQUISITION"),
                  phase_to_acquire="PRE" if attempt == 1 else "POST", scope=scope,
                  producer={"run_id": own_id, "run_attempt": 1, "source_sha": revision,
                            "workflow": PRODUCER, "workflow_id": own["workflow_id"]},
                  source_lock=closure, challenge=original, challenge_artifact=original_proof,
                  current_source=current)
    if attempt == 2:
        pre, proof, pre_run = find_observation(api, git, scope, "PRE")
        second, second_proof, second_run = consumer_receipt(api, target_id, 2)
        validate_consumer_second(second, original, pre, proof, second_run, pre_run)
        completed_steps(api, second_run)
        result.update(pre_observation_artifact=proof, consumer_second=second,
                      consumer_second_artifact=second_proof)
    return result


def acquire(context: dict, env: dict, git, api, fetch_governance=None) -> dict:
    validate_envelope(context, "CONTEXT")
    own_id, revision = producer_environment(env)
    need(context["producer"]["run_id"] == own_id and context["producer"]["source_sha"] == revision and
         context["source_lock"] == local_source(git, revision), "ACQUISITION_CONTEXT_SOURCE_DRIFT")
    scope = validate_challenge(context["challenge"], git)
    need(context["scope"] == scope and producer_source(scope) == revision, "ACQUISITION_TUPLE_DRIFT")
    phase = context["phase_to_acquire"]
    need(phase in ("PRE", "POST"), "UNKNOWN_ACQUISITION_PHASE")
    observed_scope = dict(scope, github_run_attempt="1" if phase == "PRE" else "2")
    started = now()
    before = target_snapshot(api, git, observed_scope, context["challenge"]["event_identity"], completed=True, fetch=False)
    public_before = public_projection(api.public_ruleset())
    fetcher = fetch_governance if fetch_governance is not None else governance.fetch_live
    rulesets, immutable, settings = fetcher(REPO, repository_metadata_token=api.token)
    selected = [r for r in rulesets if r.get("id") == 21804005 or
                (r.get("target") == "tag" and r.get("enforcement") == "active")]
    private = []
    for rule in selected:
        if type(rule.get("bypass_actors")) is list and rule["bypass_actors"]:
            redacted = {"ruleset_id": integer(rule.get("id")), "actor_count": len(rule["bypass_actors"]),
                        "bypass_state": "nonempty_redacted"}
            # Hash only the public refusal projection: a digest of a small
            # private actor list would disclose it through candidate guessing.
            private.append(dict(redacted, redacted_observation_sha256=sha(encoded(redacted))))
    if private:
        raise PrivateBypassRefused(private)
    audited = governance.audit(rulesets, immutable, settings)
    need(audited.get("result") == "PASS", "AUTHENTICATED_GOVERNANCE_AUDIT_REJECTED")
    main = [r for r in rulesets if r.get("id") == 21804005]
    need(len(main) == 1, "CANONICAL_RULESET_NOT_UNIQUE")
    source.validate_ruleset(main[0])
    # Only audited, explicit empty lists can enter a public artifact. Neither
    # the rejected object nor private actor identities are returned on failure.
    need(all(type(r.get("bypass_actors")) is list and r["bypass_actors"] == [] for r in selected),
         "PRIVATE_BYPASS_OBSERVATION_REJECTED_NOT_PUBLISHED")
    projected_settings = {key: settings[key] for key in ("id", "full_name", "default_branch", "delete_branch_on_merge")}
    need(projected_settings["id"] == REPO_ID and projected_settings["full_name"] == REPO and
         projected_settings["default_branch"] == "main", "AUTHENTICATED_REPOSITORY_IDENTITY_DRIFT")
    need(governance.audit(selected, immutable, projected_settings) == audited, "RETAINED_GOVERNANCE_PROJECTION_DRIFT")
    public_after = public_projection(api.public_ruleset())
    after = target_snapshot(api, git, observed_scope, context["challenge"]["event_identity"], completed=True, fetch=False)
    need(before == after and public_before == public_after == public_projection(main[0]) and
         public_before == context["challenge"]["public_ruleset"], "GOVERNANCE_OR_SOURCE_MOVED")
    observations = {"rulesets": selected, "immutable_releases": immutable,
                    "repository_projection": projected_settings}
    result = dict(envelope(phase, "AUTHENTICATED_OBSERVATION_PENDING_INDEPENDENT_ACQUISITION"),
                  scope=scope, target_consumer_attempt=2, producer=context["producer"],
                  source_lock=context["source_lock"], challenge_artifact=context["challenge_artifact"],
                  current_source=after, authenticated_observation=observations,
                  canonical_json_sha256=sha(encoded(observations)), governance_audit=audited,
                  public_ruleset_projection=public_after, acquisition_started_at_utc=started,
                  acquisition_finished_at_utc=now(), source_range_qualified=False,
                  governance_post_qualified=False)
    if phase == "POST":
        result.update(pre_observation_artifact=context["pre_observation_artifact"],
                      consumer_second_artifact=context["consumer_second_artifact"])
    return result


def validate_observation(value: dict, git, scope: dict, phase: str, record: dict) -> None:
    validate_envelope(value, phase)
    need(stable_scope(value["scope"]) == stable_scope(scope) and value["scope"]["github_run_attempt"] == "1" and
         value.get("target_consumer_attempt") == 2 and value.get("source_range_qualified") is False and
         value.get("governance_post_qualified") is False, "OBSERVATION_SCOPE_OR_AUTHORITY_DRIFT")
    revision = producer_source(scope)
    need(value.get("producer") == {"run_id": record["id"], "run_attempt": 1, "source_sha": revision,
          "workflow": PRODUCER, "workflow_id": record["workflow_id"]} and
         record.get("head_sha") == revision and record.get("head_branch") == "main" and
         record.get("conclusion") == "success", "ACTUAL_PRODUCER_SOURCE_DRIFT")
    need(value.get("source_lock") == lock_at(git, revision), "OBSERVATION_SOURCE_CLOSURE_DRIFT")
    observed = value["authenticated_observation"]
    need(value.get("canonical_json_sha256") == sha(encoded(observed)), "CANONICAL_OBSERVATION_HASH_DRIFT")
    audit = governance.audit(observed["rulesets"], observed["immutable_releases"], observed["repository_projection"])
    need(audit.get("result") == "PASS" and audit == value.get("governance_audit"), "INDEPENDENT_GOVERNANCE_AUDIT_REJECTED")
    main = [r for r in observed["rulesets"] if r.get("id") == 21804005]
    need(len(main) == 1, "OBSERVED_MAIN_RULESET_NOT_UNIQUE")
    source.validate_ruleset(main[0])
    need(public_projection(main[0]) == value.get("public_ruleset_projection"), "OBSERVATION_PUBLIC_PROJECTION_DRIFT")
    need(utc_instant(value["acquisition_started_at_utc"]) <= utc_instant(value["acquisition_finished_at_utc"]),
         "ACQUISITION_TIMESTAMP_ORDER_DRIFT")


def find_observation(api, git, scope: dict, phase: str) -> tuple[dict, dict, dict]:
    listed = api.get("actions/workflows/" + Path(PRODUCER).name + "/runs?event=workflow_run&branch=main&per_page=100")
    need(type(listed) is dict and type(listed.get("workflow_runs")) is list and
         len(listed["workflow_runs"]) < 100, "PRODUCER_DISCOVERY_PAGE_BOUND")
    matches = []
    target_attempt = 1 if phase == "PRE" else 2
    for candidate in listed["workflow_runs"]:
        if candidate.get("head_sha") != producer_source(scope) or candidate.get("status") != "completed" or candidate.get("conclusion") != "success":
            continue
        record = run_record(api, integer(candidate.get("id")), 1, producer=True)
        name = f"dechorate-governance-v2-{scope['github_run_id']}-{target_attempt}-{record['id']}"
        artifacts = api.get(f"actions/runs/{record['id']}/artifacts?per_page=100")
        if not any(item.get("name") == name for item in artifacts.get("artifacts", [])):
            continue
        value, proof = artifact(api, record, name, "observation.json")
        validate_observation(value, git, scope, phase, record)
        proof["job"] = completed_steps(api, record, producer=True)
        acquired = proof["job"]["acquisition_step"]
        need(instant(acquired["started_at"]) <= utc_instant(value["acquisition_started_at_utc"]) <=
             utc_instant(value["acquisition_finished_at_utc"]) < api_time_upper(acquired["completed_at"]),
             "ACQUISITION_OUTSIDE_ACTUAL_PRODUCER_STEP")
        matches.append((value, proof, record))
    need(len(matches) == 1, "UNIQUE_COMPLETED_AUTHENTIC_PRODUCER_REQUIRED")
    return matches[0]


def validate_consumer_second(value: dict, original: dict, pre: dict, pre_proof: dict,
                             record: dict, pre_run: dict) -> None:
    validate_envelope(value, "CONSUMER_SECOND")
    need(value.get("decision") == "SOURCE_PRE_QUALIFIED_PENDING_INDEPENDENT_POST" and
         value.get("source_range_qualified") is True and value.get("governance_post_qualified") is False and
         value.get("scope", {}).get("github_run_attempt") == "2" and
         stable_scope(value["scope"]) == stable_scope(original["scope"]) and
         value.get("pre_observation_artifact") == pre_proof and
         value.get("challenge_canonical_json_sha256") == sha(encoded(original)) and
         value.get("source_lock") == original.get("source_lock") and
         value.get("current_event") == original.get("current_event") and
         value.get("frozen_source") == original.get("frozen_source") and
         all(value.get("public_source", {}).get(key) == original["public_source"].get(key)
             for key in ("main_sha", "pr", "execution_closure")), "SECOND_CONSUMER_CHAIN_DRIFT")
    observed_run = value["public_source"]["run"]
    need(observed_run.get("status") == "in_progress" and observed_run.get("conclusion") is None and
         all(observed_run.get(key) == record.get(key) for key in
             ("id", "run_attempt", "event", "path", "workflow_id", "head_sha", "head_branch",
              "run_started_at", "created_at")), "SECOND_CONSUMER_OBSERVED_RUN_DRIFT")
    need(instant(record["run_started_at"]) >= api_time_upper(pre_proof["job"]["completed_at"]),
         "CONSUMER_STARTED_BEFORE_PRE_COMPLETED")


def consume(event: dict, env: dict, git, api) -> tuple[dict, int]:
    current = challenge(event, env, git, api)
    scope = current["scope"]
    if scope["github_run_attempt"] == "1":
        return current, 1
    original, original_proof, original_run = consumer_receipt(api, cli_integer(scope["github_run_id"]), 1)
    validate_challenge(original, git)
    first_job(api, original, original_run)
    need(stable_scope(scope) == stable_scope(original["scope"]) and
         current["source_lock"] == original["source_lock"] and current["public_ruleset"] == original["public_ruleset"],
         "RERUN_CHALLENGE_DRIFT")
    pre, pre_proof, pre_run = find_observation(api, git, scope, "PRE")
    need(pre["challenge_artifact"] == original_proof and
         pre["public_ruleset_projection"] == current["public_ruleset"], "PRE_NOT_THIS_ORIGINAL_CHALLENGE")
    result = dict(envelope("CONSUMER_SECOND", "SOURCE_PRE_QUALIFIED_PENDING_INDEPENDENT_POST"),
                  scope=scope, source_lock=current["source_lock"], current_event=current["current_event"],
                  frozen_source=current["frozen_source"], public_source=current["public_source"],
                  pre_observation_artifact=pre_proof, challenge_canonical_json_sha256=sha(encoded(original)),
                  source_range_qualified=True, governance_post_qualified=False)
    actual = run_record(api, cli_integer(scope["github_run_id"]), 2, completed=False)
    validate_consumer_second(result, original, pre, pre_proof, actual, pre_run)
    return result, 0


def verify(api, git, run_id: int) -> dict:
    original, first_proof, first = consumer_receipt(api, run_id, 1)
    scope = validate_challenge(original, git)
    local_source(git, producer_source(scope))
    first_job(api, original, first)
    pre, pre_proof, pre_run = find_observation(api, git, scope, "PRE")
    second, second_proof, second_run = consumer_receipt(api, run_id, 2)
    validate_consumer_second(second, original, pre, pre_proof, second_run, pre_run)
    second_job = completed_steps(api, second_run)
    need(second_run.get("conclusion") == "success", "MEASURED_CONSUMER_RUN_NOT_SUCCESS")
    post, post_proof, post_run = find_observation(api, git, scope, "POST")
    need(pre["challenge_artifact"] == first_proof == post["challenge_artifact"] and
         post["pre_observation_artifact"] == pre_proof and post["consumer_second_artifact"] == second_proof and
         pre["authenticated_observation"] == post["authenticated_observation"] and
         pre["public_ruleset_projection"] == post["public_ruleset_projection"] == original["public_ruleset"],
         "PRE_CONSUMER_POST_CLOSURE_DRIFT")
    need(utc_instant(post["acquisition_started_at_utc"]) >= api_time_upper(second_job["completed_at"]),
         "POST_PRECEDES_CONSUMER_COMPLETION")
    latest = api.get(f"actions/runs/{run_id}")
    need(latest.get("run_attempt") == 2, "LATER_CONSUMER_ATTEMPT_INVALIDATES_CLOSURE")
    current = target_snapshot(api, git, dict(scope, github_run_attempt="2"), original["event_identity"],
                              completed=True, fetch=True)
    need(public_projection(api.public_ruleset()) == post["public_ruleset_projection"], "LIVE_PUBLIC_RULESET_MOVED")
    return dict(envelope("VERIFIED", "DECHORATE_GOVERNANCE_PROTOCOL_VERIFIED_NO_PRODUCTION_ADMISSION"),
                scope=scope, source_lock=original["source_lock"], current_source=current,
                original_challenge_artifact=first_proof, pre_artifact=pre_proof,
                second_consumer_artifact=second_proof, post_artifact=post_proof,
                governance_post_qualified=True, source_range_qualified=True,
                consumer_original_scientific_steps_observed="success",
                observations_are_continuous_monitoring=False,
                acoustic_result_requires_existing_independent_evidence=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("preflight", "acquire", "consumer", "verify"):
        child = sub.add_parser(name)
        child.add_argument("--output", type=Path, required=True)
        if name in ("preflight", "consumer"):
            child.add_argument("--event-file", type=Path, required=True)
        if name == "acquire":
            child.add_argument("--context", type=Path, required=True)
        if name == "verify":
            child.add_argument("--consumer-run-id", required=True, type=cli_integer)
    args = parser.parse_args()
    output = args.output
    git = source.Git(ROOT)
    read_token = os.environ.get("REPOSITORY_METADATA_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    api = API(read_token)
    code = 0
    try:
        if args.operation in ("preflight", "consumer"):
            need(args.event_file.is_file() and not args.event_file.is_symlink(), "REGULAR_EVENT_REQUIRED")
            event = parsed(args.event_file.read_bytes())
        if args.operation == "preflight":
            result = preflight(event, dict(os.environ), git, api)
        elif args.operation == "acquire":
            need(bool(os.environ.get("GH_TOKEN")) and bool(os.environ.get("REPOSITORY_METADATA_TOKEN")),
                 "ISOLATED_GOVERNANCE_AND_METADATA_CREDENTIALS_REQUIRED")
            result = acquire(parsed(args.context.read_bytes()), dict(os.environ), git, api)
        elif args.operation == "consumer":
            need(not os.environ.get("REPOSITORY_GOVERNANCE_TOKEN") and not os.environ.get("REPOSITORY_METADATA_TOKEN"),
                 "GOVERNANCE_CREDENTIAL_FORBIDDEN_IN_CONSUMER")
            result, code = consume(event, dict(os.environ), git, api)
        else:
            result = verify(api, git, args.consumer_run_id)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RuntimeError, subprocess.SubprocessError,
            zipfile.BadZipFile) as exc:
        reason = str(exc)
        result = dict(envelope("REJECTED", "ORIGINAL_RESEARCH_GUARDS_REQUIRED"),
                      reason=reason if re.fullmatch(r"[A-Z0-9_]{1,100}", reason) else "PROTOCOL_INPUT_OR_ACQUISITION_REJECTED",
                      source_range_qualified=False, governance_post_qualified=False)
        if isinstance(exc, PrivateBypassRefused):
            result["refused_bypass_observations"] = exc.observations
        code = 1
    try:
        write_new(output, result)
    except (ValueError, OSError):
        print("PREVIOUS_EVIDENCE_PRESERVED_OR_WRITE_REJECTED", file=sys.stderr)
        return 2
    print(json.dumps({key: result.get(key) for key in ("candidate_id", "phase", "decision", "reason")}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
