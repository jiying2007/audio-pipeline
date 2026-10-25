#!/usr/bin/env python3
"""Offline protocol tests: real Git, explicit fake HTTP/jobs/ZIPs, no live authority."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REL = ".github/program/dechorate_governance_v2.py"


def imported(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str, data: bytes | None = None) -> str:
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    result = subprocess.run(["git", "-c", "safe.directory=" + str(root), *args], cwd=root,
                            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, timeout=45, check=False)
    if result.returncode:
        raise AssertionError("offline Git operation failed: " + args[0] + ": " + result.stderr.decode()[:600])
    return result.stdout.decode().strip()


def rulesets(M):
    # Actual API shape includes non-UTC offsets. Public responses omit bypass.
    main = {"id": 21804005, "name": "audio-pipeline-main", "target": "branch",
            "source_type": "Repository", "source": M.REPO, "enforcement": "active",
            "bypass_actors": [], "current_user_can_bypass": "never",
            "node_id": "offline-main-ruleset",
            "created_at": "2026-08-29T21:46:28.760+08:00",
            "updated_at": "2026-08-29T21:46:28.815+08:00",
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                      {"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"],
                       "required_review_thread_resolution": True, "required_approving_review_count": 0}},
                      {"type": "required_status_checks", "parameters": {
                       "strict_required_status_checks_policy": True, "do_not_enforce_on_create": False,
                       "required_status_checks": [{"context": "summary", "integration_id": 15368}]}}]}
    tag = {"id": 21804006, "name": "offline-tags", "target": "tag", "enforcement": "active",
           "bypass_actors": [], "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
           "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}]}
    return [main, tag]


class Metadata:
    """Only network boundaries are fixtures; source and Git operations are real."""
    def __init__(self, M, base, head, merge, pr_head, push=False):
        self.M = M
        self.token = "OFFLINE_METADATA_FIXTURE_NOT_A_CREDENTIAL"
        self.repo = {"id": M.REPO_ID, "full_name": M.REPO}
        self.rules = rulesets(M)
        self.main = head if push else base
        author = {"id": 99900001, "login": "offline-fixture", "type": "User"}
        self.pr = {"number": 833, "draft": False, "state": "closed" if push else "open",
                   "merged": push, "merged_at": "2026-10-24T14:59:00Z" if push else None,
                   "merge_commit_sha": head if push else merge, "user": author,
                   "base": {"ref": "main", "sha": base, "repo": self.repo},
                   "head": {"ref": "offline-dechorate", "sha": pr_head, "repo": self.repo}}
        self.records = {}
        self.latest = {7001: 1, 8001: 1, 8002: 1}
        for attempt, started, updated in ((1, "15:00:00", "15:01:00"), (2, "15:04:00", "15:05:00")):
            self.records[7001, attempt] = self.run(7001, attempt, head, "push" if push else "pull_request",
                "main" if push else "offline-dechorate", M.SCIENCE_WORKFLOW, M.SCIENCE_NAME, 111, started, updated)
        for number, started, updated in ((8001, "15:02:00", "15:03:00"), (8002, "15:06:00", "15:07:00")):
            self.records[number, 1] = self.run(number, 1, self.main, "workflow_run", "main",
                M.PRODUCER, M.PRODUCER_NAME, 222, started, updated)
        self.artifacts = {7001: [], 8001: [], 8002: []}
        self.archives = {}
        self.job_mutation = None
        self.next_artifact = 9000

    def __deepcopy__(self, memo):
        result = object.__new__(type(self))
        memo[id(self)] = result
        result.__dict__ = {key: value if key == "M" else copy.deepcopy(value, memo)
                           for key, value in self.__dict__.items()}
        return result

    def run(self, number, attempt, head, event, branch, path, name, workflow, started, updated):
        # Actual /attempts/2 metadata can be created seconds AFTER run_started_at.
        # This observed API shape is not proof of execution ordering.
        created = "15:04:02" if number == 7001 and attempt == 2 else started
        return {"id": number, "run_attempt": attempt, "head_sha": head, "event": event,
                "head_branch": branch, "path": path, "name": name, "workflow_id": workflow,
                "repository": self.repo, "head_repository": self.repo, "status": "in_progress", "conclusion": None,
                "created_at": "2026-10-24T" + created + "Z", "run_started_at": "2026-10-24T" + started + "Z",
                "updated_at": "2026-10-24T" + updated + "Z"}

    def complete(self, number, attempt, conclusion):
        self.records[number, attempt].update(status="completed", conclusion=conclusion)

    def public_ruleset(self):
        result = copy.deepcopy(self.rules[0])
        result.pop("bypass_actors", None)
        result.pop("current_user_can_bypass", None)
        return result

    def governance(self, *_args, **_kwargs):
        return copy.deepcopy(self.rules), {"enabled": True}, dict(self.repo, default_branch="main", delete_branch_on_merge=True)

    def add_artifact(self, number, attempt, receipt, filename, name):
        stream = io.BytesIO()
        raw = self.M.encoded(receipt)
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(filename, raw)
            archive.writestr(filename + ".sha256", self.M.sha(raw) + "  " + filename + "\n")
        data = stream.getvalue()
        self.next_artifact += 1
        record = self.records[number, attempt]
        metadata = {"id": self.next_artifact, "name": name, "expired": False,
                    "size_in_bytes": len(data), "digest": "sha256:" + self.M.sha(data),
                    "workflow_run": {"id": number, "head_sha": record["head_sha"], "head_branch": record["head_branch"]}}
        self.artifacts[number].append(metadata)
        self.archives[self.next_artifact] = data

    def archive(self, artifact_id):
        return self.archives[artifact_id]

    def reseal(self, number, mutate):
        old = self.artifacts[number].pop()
        filename = "source-range.json" if number == 7001 else "observation.json"
        value = self.M.zip_receipt(self.archives[old["id"]], old, filename)
        mutate(value)
        attempt = int(value["scope"]["github_run_attempt"]) if number == 7001 else 1
        self.add_artifact(number, attempt, value, filename, old["name"])

    def get(self, path):
        M = self.M
        if path == "git/ref/heads/main":
            result = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.main}}
        elif path == "pulls/833":
            result = self.pr
        elif path.startswith("commits/"):
            result = [self.pr]
        elif path.startswith("actions/workflows/"):
            if "/runs?" in path:
                result = {"workflow_runs": [self.records[8001, 1], self.records[8002, 1]]}
            else:
                producer = path.endswith(Path(M.PRODUCER).name)
                result = {"id": 222 if producer else 111, "state": "active",
                          "path": M.PRODUCER if producer else M.SCIENCE_WORKFLOW,
                          "name": M.PRODUCER_NAME if producer else M.SCIENCE_NAME}
        elif path.endswith("/artifacts?per_page=100"):
            items = self.artifacts[int(path.split("/")[2])]
            result = {"total_count": len(items), "artifacts": items}
        elif "/jobs?" in path:
            number, attempt = int(path.split("/")[2]), int(path.split("/")[4])
            record = self.records[number, attempt]
            first, producer = number == 7001 and attempt == 1, number != 7001
            names = (["Validate protected producer context", "Collect authenticated governance observation", "Preserve authenticated observation"]
                     if producer else [M.source.BIND_STEP, "Preserve the independent source-range decision",
                     *json.loads((ROOT / M.LEGACY_PLAN).read_text())["original_scientific_step_sha256"]])
            steps = []
            for name in names:
                conclusion = "success"
                if first and name == M.source.BIND_STEP:
                    conclusion = "failure"
                elif first and name not in (M.source.BIND_STEP, "Preserve the independent source-range decision", "Check out exact source"):
                    conclusion = "skipped"
                steps.append({"name": name, "status": "completed", "conclusion": conclusion,
                              "started_at": record["run_started_at"], "completed_at": record["updated_at"]})
            job = {"id": number * 10 + attempt, "name": "observe" if producer else "diagnostic", "status": "completed",
                   "run_id": number, "run_attempt": attempt, "head_sha": record["head_sha"], "workflow_name": record["name"],
                   "conclusion": "failure" if first else "success", "started_at": record["run_started_at"],
                   "completed_at": record["updated_at"], "steps": steps}
            if self.job_mutation:
                self.job_mutation(job)
            result = {"total_count": 1, "jobs": [job]}
        else:
            parts = path.split("/")
            number = int(parts[2])
            attempt = int(parts[4]) if len(parts) == 5 else self.latest[number]
            result = self.records.get((number, attempt), dict(self.records[number, 1], run_attempt=attempt))
        return copy.deepcopy(result)


class Protocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="dechorate-v2-offline-")
        cls.area = Path(cls.temp.name) / "repo"
        git(Path(cls.temp.name), "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(cls.area))
        git(cls.area, "config", "user.email", "offline@example.invalid")
        git(cls.area, "config", "user.name", "Offline Protocol Fixture")
        git(cls.area, "checkout", "--quiet", "--detach", "5187c5e59526d4047b3965b44c770ab21edbde9f")
        model = imported(ROOT / REL, "v2_source_for_fixture")
        # The protected M2 prerequisite now uses a different, separately
        # registered 2026-10-24 source closure. Materialize BOTH complete
        # closures in this disposable real-Git fixture; a missing file is
        # rejected by the production validator, not supplied by a fake.
        frozen_sources = tuple(dict.fromkeys(
            (*model.CLOSURE, *model.source.M2_SOURCE_FILES)))
        for name in frozen_sources:
            target = cls.area / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        git(cls.area, "add", *frozen_sources)
        git(cls.area, "commit", "--quiet", "-m", "offline protocol source fixture; not protected main")
        cls.base = git(cls.area, "rev-parse", "HEAD")
        cls.M = imported(cls.area / REL, "v2_offline_actual_source")
        anchor = git(cls.area, "show", cls.M.source.SCIENCE_ANCHOR + ":" + cls.M.SCIENCE_WORKFLOW) + "\n"
        body = cls.M.source.workflow_templates(anchor)[cls.M.source.V2_PROFILE + ":original-pins"]
        (cls.area / cls.M.SCIENCE_WORKFLOW).write_text(body)
        git(cls.area, "add", cls.M.SCIENCE_WORKFLOW)
        git(cls.area, "commit", "--quiet", "-m", "offline workflow-only consumer fixture")
        cls.head = git(cls.area, "rev-parse", "HEAD")
        tree = git(cls.area, "rev-parse", cls.head + "^{tree}")
        cls.merge = git(cls.area, "commit-tree", tree, "-p", cls.base, "-p", cls.head, "-m", "offline PR event")
        cls.push = git(cls.area, "commit-tree", tree, "-p", cls.base, "-m", "offline squash event")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        git(self.area, "checkout", "--quiet", "--detach", self.base)

    def case(self, push=False):
        M = self.M
        api = Metadata(M, self.base, self.push if push else self.head, self.push if push else self.merge, self.head, push)
        outer = self
        class LocalGit(M.source.Git):
            def run(self, args, **kwargs):
                if args[0] == "fetch":
                    return b""  # Exact fixture Git objects already exist locally.
                if args[0] == "ls-remote":
                    revision = api.main if args[2] == "refs/heads/main" else api.pr["head"]["sha"]
                    return (revision + "\t" + args[2] + "\n").encode()
                return super().run(args, **kwargs)
        engine = LocalGit(self.area)
        if push:
            event = {"repository": api.repo, "ref": "refs/heads/main", "created": False, "deleted": False,
                     "forced": False, "before": self.base, "after": self.push, "head_commit": {"id": self.push}}
            env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": self.push}
        else:
            event = {"repository": api.repo, "number": 833, "action": "synchronize", "pull_request": copy.deepcopy(api.pr)}
            env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/833/merge", "GITHUB_SHA": self.merge,
                   "GITHUB_BASE_REF": "main", "GITHUB_HEAD_REF": "offline-dechorate"}
        env.update(GITHUB_REPOSITORY=M.REPO, GITHUB_RUN_ID="7001", GITHUB_RUN_ATTEMPT="1",
                   GITHUB_WORKFLOW_REF=M.REPO + "/" + M.SCIENCE_WORKFLOW + "@" + env["GITHUB_REF"])
        return api, engine, event, env

    def producer_env(self, api, number):
        return {"GITHUB_EVENT_NAME": "workflow_run", "GITHUB_REPOSITORY": self.M.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": api.main, "GITHUB_WORKFLOW_SHA": api.main,
                "GITHUB_WORKFLOW_REF": self.M.REPO + "/" + self.M.PRODUCER + "@refs/heads/main",
                "GITHUB_RUN_ID": str(number), "GITHUB_RUN_ATTEMPT": "1"}

    def pre_pair(self, push=False):
        M = self.M
        api, engine, event, env = self.case(push)
        with mock.patch.object(M, "now", return_value="2026-10-24T15:00:30Z"):
            first, code = M.consume(event, env, engine, api)
        self.assertEqual(code, 1)
        self.assertEqual(first["decision"], "PENDING_AUTHENTICATED_PRE")
        api.add_artifact(7001, 1, first, "source-range.json", "dechorate-event-source-range-7001-1")
        api.complete(7001, 1, "failure")
        git(self.area, "checkout", "--quiet", "--detach", api.main)
        producer_env = self.producer_env(api, 8001)
        completion = {"action": "completed", "repository": api.repo, "workflow_run": api.get("actions/runs/7001/attempts/1")}
        context = M.preflight(completion, producer_env, engine, api)
        with mock.patch.object(M, "now", side_effect=["2026-10-24T15:02:01Z", "2026-10-24T15:02:02Z"]):
            pre = M.acquire(context, producer_env, engine, api, api.governance)
        api.add_artifact(8001, 1, pre, "observation.json", "dechorate-governance-v2-7001-1-8001")
        api.complete(8001, 1, "success")
        git(self.area, "checkout", "--quiet", "--detach", self.base)
        return api, engine, event, env, first, pre

    def full_chain(self, push=False):
        M = self.M
        api, engine, event, env, first, pre = self.pre_pair(push)
        api.latest[7001] = 2
        env["GITHUB_RUN_ATTEMPT"] = "2"
        with mock.patch.object(M, "now", return_value="2026-10-24T15:04:30Z"):
            second, code = M.consume(event, env, engine, api)
        self.assertEqual(code, 0)
        self.assertFalse(second["governance_post_qualified"])
        api.add_artifact(7001, 2, second, "source-range.json", "dechorate-event-source-range-7001-2")
        api.complete(7001, 2, "success")
        git(self.area, "checkout", "--quiet", "--detach", api.main)
        producer_env = self.producer_env(api, 8002)
        completion = {"action": "completed", "repository": api.repo, "workflow_run": api.get("actions/runs/7001/attempts/2")}
        context = M.preflight(completion, producer_env, engine, api)
        with mock.patch.object(M, "now", side_effect=["2026-10-24T15:06:01Z", "2026-10-24T15:06:02Z"]):
            post = M.acquire(context, producer_env, engine, api, api.governance)
        api.add_artifact(8002, 1, post, "observation.json", "dechorate-governance-v2-7001-2-8002")
        api.complete(8002, 1, "success")
        return api, engine

    def test_real_git_pr_and_push_full_protocol_controls(self):
        for push in (False, True):
            with self.subTest(push=push):
                git(self.area, "checkout", "--quiet", "--detach", self.base)
                api, engine = self.full_chain(push)
                result = self.M.verify(api, engine, 7001)
                self.assertGreater(self.M.instant(api.records[7001, 2]["created_at"]),
                                   self.M.instant(api.records[7001, 2]["run_started_at"]))
                self.assertEqual(result["decision"], "DECHORATE_GOVERNANCE_PROTOCOL_VERIFIED_NO_PRODUCTION_ADMISSION")
                self.assertTrue(result["governance_post_qualified"])
                self.assertTrue(all(result[k] is False for k in self.M.FALSE_FLAGS))

    def test_anonymous_omission_is_public_only_and_never_zero_bypass(self):
        M = self.M
        actual_shape = rulesets(M)[0]
        public = copy.deepcopy(actual_shape)
        del public["bypass_actors"]
        del public["current_user_can_bypass"]
        self.assertEqual(M.public_projection(public), M.public_projection(actual_shape))
        self.assertEqual(M.instant(actual_shape["updated_at"]).isoformat(), "2026-08-29T13:46:28.815000+00:00")
        with self.assertRaises(M.source.Denied):
            M.source.validate_ruleset(public)

    def test_bad_bypass_values_are_rejected(self):
        for bad in (None, False, 0, {}, [{"actor_id": 999}]):
            with self.subTest(value=type(bad).__name__):
                item = rulesets(self.M)[0]
                item["bypass_actors"] = bad
                with self.assertRaises((self.M.Denied, self.M.source.Denied)):
                    self.M.public_projection(item)

    def test_producer_identity_and_budget_negatives(self):
        api, _, _, _ = self.case()
        positive = self.producer_env(api, 8001)
        self.M.producer_environment(positive)
        for field, value in (("GITHUB_EVENT_NAME", "pull_request_target"), ("GITHUB_REPOSITORY", "fork/repo"),
                             ("GITHUB_REF", "refs/heads/attacker"), ("GITHUB_WORKFLOW_SHA", "f"*40),
                             ("GITHUB_WORKFLOW_REF", "wrong"), ("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_RUN_ID", "01")):
            with self.subTest(field=field), self.assertRaises(self.M.Denied):
                self.M.producer_environment(dict(positive, **{field: value}))

    def test_old_negative_receipt_and_source_mutations_rejected(self):
        api, engine, event, env = self.case()
        with self.assertRaises(self.M.Denied):
            self.M.validate_challenge({"decision":"ORIGINAL_RESEARCH_GUARDS_REQUIRED","reason":"MAIN_RULESET_IDENTITY_OR_BYPASS_DRIFT"}, engine)
        with mock.patch.object(self.M, "now", return_value="2026-10-24T15:00:30Z"):
            value = self.M.challenge(event, env, engine, api)
        for mutate in (lambda x:x["scope"].__setitem__("github_run_attempt", "3"),
                       lambda x:x["scope"].__setitem__("base_sha", self.head),
                       lambda x:x["scope"].__setitem__("event_commit_sha", self.head),
                       lambda x:x["source_lock"].pop(self.M.GOVERNANCE),
                       lambda x:x.__setitem__("production_admission_enabled", True)):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises((self.M.Denied,self.M.source.Denied)):
                self.M.validate_challenge(changed,engine)

    def test_actual_producer_and_zip_authority_negatives(self):
        api, engine = self.full_chain()
        original = copy.deepcopy(api)
        mutations = (
            lambda a:a.records[8001,1].__setitem__("head_sha","f"*40),
            lambda a:a.records[8001,1].__setitem__("event","pull_request"),
            lambda a:a.records[8001,1].__setitem__("workflow_id",333),
            lambda a:a.records[8001,1].__setitem__("conclusion","failure"),
            lambda a:a.records[8001,1].__setitem__("status","in_progress"),
            lambda a:a.artifacts[8001][0].__setitem__("digest","sha256:"+"0"*64),
            lambda a:a.artifacts[8001][0]["workflow_run"].__setitem__("id",8002),
            lambda a:a.artifacts[8001][0].__setitem__("expired",True),
            lambda a:a.records[7001,1].__setitem__("conclusion","cancelled"),
            lambda a:a.latest.__setitem__(7001,3),
            lambda a:a.latest.__setitem__(8001,2),
            lambda a:a.records[7001,2].__setitem__("run_started_at","2026-10-24T15:02:00Z"),
            lambda a:setattr(a,"main","f"*40),
            lambda a:a.rules[0].__setitem__("updated_at","2026-10-24T15:08:00Z"),
        )
        for index, mutate in enumerate(mutations):
            changed=copy.deepcopy(original)
            mutate(changed)
            with self.subTest(index=index), self.assertRaises((self.M.Denied,self.M.source.Denied)):
                self.M.verify(changed,engine,7001)

    def test_missing_actual_acquisition_step_is_rejected(self):
        api,engine=self.full_chain()
        def mutate(job):
            if job["name"]=="observe":
                job["steps"][1]["conclusion"]="skipped"
        api.job_mutation=mutate
        with self.assertRaises(self.M.Denied):
            self.M.verify(api,engine,7001)

    def test_job_run_attempt_source_and_step_status_are_independently_bound(self):
        api, engine = self.full_chain()
        for field, value in (("run_id", 9001), ("run_attempt", 2), ("head_sha", "f" * 40),
                             ("workflow_name", "Untrusted duplicate name")):
            for job_name in ("observe", "diagnostic"):
                changed = copy.deepcopy(api)
                def mutate(job, field=field, value=value, job_name=job_name):
                    if job["name"] == job_name:
                        job[field] = value
                changed.job_mutation = mutate
                with self.subTest(field=field, job=job_name), self.assertRaisesRegex(self.M.Denied, "ACTUAL_JOB_RUN_ATTEMPT_SOURCE_DRIFT"):
                    self.M.verify(changed, engine, 7001)
        changed = copy.deepcopy(api)
        changed.job_mutation = lambda job: job["steps"][0].__setitem__("status", "in_progress")
        with self.assertRaisesRegex(self.M.Denied, "REQUIRED_ACTUAL_STEP_NOT_SUCCESS"):
            self.M.verify(changed, engine, 7001)
        changed = copy.deepcopy(api)
        def copied_old_job(job):
            if job["run_id"] == 7001 and job["run_attempt"] == 2:
                job["started_at"] = "2026-10-24T15:00:00Z"
                job["completed_at"] = "2026-10-24T15:01:00Z"
        changed.job_mutation = copied_old_job
        with self.assertRaisesRegex(self.M.Denied, "ACTUAL_JOB_INTERVAL_DRIFT"):
            self.M.verify(changed, engine, 7001)

    def test_resealed_observations_cannot_escape_actual_job_intervals(self):
        api, engine = self.full_chain()
        for number, field, value in (
            (8001, "acquisition_started_at_utc", "2026-10-24T15:01:59Z"),
            (8001, "acquisition_finished_at_utc", "2026-10-24T15:03:01Z"),
            (8001, "acquisition_finished_at_utc", "2026-10-24T23:02:03+08:00"),
            (8002, "acquisition_started_at_utc", "2026-10-24T15:04:59Z"),
        ):
            changed = copy.deepcopy(api)
            changed.reseal(number, lambda receipt, field=field, value=value: receipt.__setitem__(field, value))
            with self.subTest(number=number, field=field, value=value), self.assertRaises(self.M.Denied):
                self.M.verify(changed, engine, 7001)
        # Fractional local time inside the same second as API completion is
        # valid; it must not be mistaken for a finish after the actual step.
        changed = copy.deepcopy(api)
        changed.reseal(8002, lambda receipt: receipt.__setitem__("acquisition_finished_at_utc", "2026-10-24T15:07:00.450000+00:00"))
        self.assertTrue(self.M.verify(changed, engine, 7001)["governance_post_qualified"])
        changed = copy.deepcopy(api)
        changed.records[7001, 2]["run_started_at"] = "2026-10-24T15:03:00Z"
        with self.assertRaises(self.M.Denied):
            self.M.verify(changed, engine, 7001)

    def test_resealed_consumer_cannot_replace_git_and_science_proofs(self):
        api, engine = self.full_chain()
        for field in ("current_event", "frozen_source", "public_source"):
            changed = copy.deepcopy(api)
            changed.reseal(7001, lambda receipt, field=field: receipt.__setitem__(field, {}))
            with self.subTest(field=field), self.assertRaisesRegex(self.M.Denied, "SECOND_CONSUMER_CHAIN_DRIFT"):
                self.M.verify(changed, engine, 7001)

    def test_private_bypass_refusal_retains_count_and_hash_without_actor_identity(self):
        M = self.M
        api, engine, event, env, first, pre = self.pre_pair()
        api.records[8001, 1].update(status="in_progress", conclusion=None)
        producer_env = self.producer_env(api, 8001)
        completion = {"action": "completed", "repository": api.repo, "workflow_run": api.get("actions/runs/7001/attempts/1")}
        context = M.preflight(completion, producer_env, engine, api)
        secret_actor = {"actor_id": 918273645, "actor_type": "Team", "bypass_mode": "always"}
        api.rules[0]["bypass_actors"] = [secret_actor]
        with self.assertRaises(M.PrivateBypassRefused) as caught:
            M.acquire(context, producer_env, engine, api, api.governance)
        redacted = {"ruleset_id": 21804005, "actor_count": 1, "bypass_state": "nonempty_redacted"}
        expected = [dict(redacted, redacted_observation_sha256=M.sha(M.encoded(redacted)))]
        self.assertEqual(caught.exception.observations, expected)
        output = Path(self.temp.name) / "redacted-private-bypass.json"
        context_path = Path(self.temp.name) / "redacted-context.json"
        context_path.write_bytes(M.encoded(context))
        argv = [str(M.ROOT / REL), "acquire", "--context", str(context_path), "--output", str(output)]
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {"GH_TOKEN": "OFFLINE_GOVERNANCE", "REPOSITORY_METADATA_TOKEN": "OFFLINE_METADATA"}), \
                mock.patch.object(M, "acquire", side_effect=caught.exception), mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
            self.assertEqual(M.main(), 1)
        result = json.loads(output.read_bytes())
        self.assertEqual(result["refused_bypass_observations"], expected)
        self.assertNotIn(str(secret_actor["actor_id"]), output.read_text() + printed.getvalue())
        self.assertNotIn(M.sha(M.encoded([secret_actor])), output.read_text() + printed.getvalue())
        self.assertNotIn("OFFLINE_GOVERNANCE", output.read_text() + printed.getvalue())

    def test_acquisition_runtime_error_preserves_sanitized_refusal(self):
        M = self.M
        output = Path(self.temp.name) / "malformed-authenticated-response.json"
        context_path = Path(self.temp.name) / "runtime-error-context.json"
        context_path.write_text("{}\n")
        argv = [str(M.ROOT / REL), "acquire", "--context", str(context_path), "--output", str(output)]
        with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {"GH_TOKEN": "OFFLINE", "REPOSITORY_METADATA_TOKEN": "OFFLINE"}), \
                mock.patch.object(M, "acquire", side_effect=RuntimeError("opaque private exception contents")), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as printed:
            self.assertEqual(M.main(), 1)
        result = json.loads(output.read_bytes())
        self.assertEqual(result["reason"], "PROTOCOL_INPUT_OR_ACQUISITION_REJECTED")
        self.assertNotIn("private exception", output.read_text() + printed.getvalue())

    def test_artifact_subprocess_has_streamed_size_time_and_credential_bounds(self):
        M = self.M
        with tempfile.TemporaryDirectory(prefix="offline-artifact-process-") as temporary:
            executable = Path(temporary) / "gh"
            executable.write_text("#!" + sys.executable + "\n" +
                "import os, sys, time\n"
                "assert os.environ['GH_TOKEN'] == 'OFFLINE_READ_ONLY'\n"
                "assert 'REPOSITORY_GOVERNANCE_TOKEN' not in os.environ\n"
                "mode = os.environ['OFFLINE_ARCHIVE_MODE']\n"
                "if mode == 'stall': time.sleep(60)\n"
                "elif mode == 'oversize':\n"
                "    while True: os.write(1, b'x' * 8192)\n"
                "else: os.write(1, b'offline bounded archive')\n")
            executable.chmod(0o755)
            actual_popen, actual_read = M.subprocess.Popen, M.os.read
            for mode in ("ok", "oversize", "stall"):
                created, byte_counts = [], []
                def start(*args, **kwargs):
                    process = actual_popen(*args, **kwargs)
                    created.append(process)
                    return process
                def read(fd, cap):
                    raw = actual_read(fd, cap)
                    if created and fd == created[0].stdout.fileno():
                        byte_counts.append(len(raw))
                    return raw
                environment = {"PATH": temporary, "OFFLINE_ARCHIVE_MODE": mode,
                               "GH_TOKEN": "OFFLINE_PRIVILEGED_NOT_INHERITED",
                               "REPOSITORY_GOVERNANCE_TOKEN": "OFFLINE_PRIVILEGED_REMOVED"}
                with mock.patch.dict(os.environ, environment), mock.patch.object(M.subprocess, "Popen", side_effect=start), \
                        mock.patch.object(M.os, "read", side_effect=read), mock.patch.object(M, "ARTIFACT_DOWNLOAD_SECONDS", 0.2):
                    started = time.monotonic()
                    if mode == "ok":
                        self.assertEqual(M.API("OFFLINE_READ_ONLY").archive(1), b"offline bounded archive")
                    else:
                        reason = "ARTIFACT_DOWNLOAD_SIZE_BOUND" if mode == "oversize" else "ARTIFACT_DOWNLOAD_DEADLINE"
                        with self.assertRaisesRegex(M.Denied, reason):
                            M.API("OFFLINE_READ_ONLY").archive(1)
                    self.assertLess(time.monotonic() - started, 2)
                self.assertIsNotNone(created[0].poll())
                self.assertLessEqual(sum(byte_counts), M.MAX_ZIP + 1)

    def test_zip_extra_duplicate_traversal_and_symlink_rejected(self):
        M=self.M
        for extra in ("extra.txt","observation.json","../observation.json","symlink"):
            stream=io.BytesIO()
            with warnings.catch_warnings(), zipfile.ZipFile(stream,"w") as archive:
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("observation.json",b"{}\n")
                archive.writestr("observation.json.sha256",M.sha(b"{}\n")+"  observation.json\n")
                if extra=="symlink":
                    info=zipfile.ZipInfo(extra);info.create_system=3;info.external_attr=0o120777<<16
                    archive.writestr(info,"outside")
                else:
                    archive.writestr(extra,"bad")
            raw=stream.getvalue()
            metadata={"id":1,"expired":False,"size_in_bytes":len(raw),"digest":"sha256:"+M.sha(raw)}
            with self.subTest(extra=extra),self.assertRaises(M.Denied):
                M.zip_receipt(raw,metadata,"observation.json")

    def test_existing_negative_receipt_cannot_be_overwritten(self):
        path=Path(self.temp.name)/"preserved-failure.json"
        self.M.write_new(path,dict(self.M.envelope("REJECTED","ORIGINAL_RESEARCH_GUARDS_REQUIRED"),reason="OFFLINE_NEGATIVE"))
        raw=path.read_bytes()
        with self.assertRaises(self.M.Denied):
            self.M.write_new(path,self.M.envelope("PRE","false-positive"))
        self.assertEqual(path.read_bytes(),raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
