#!/usr/bin/env python3
"""Real-Git/offline engineering tests; never actual M1/M2/science admission.

Repository objects, source bytes/modes, all Action differences and the actual
M2 evaluator execute locally. Only public metadata/ref retrieval and small ZIP
transport are explicitly engineering fixtures. The checked-in registry remains
PENDING. No real archive receipt, corpus or hosted execution is manufactured.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
P = load("push_under_test", ROOT / ".github/program/dechorate_push_maintenance_t1m3.py")
S = load("source_under_test", ROOT / P.SOURCE)
BASELINE = "2f2ca4c283e700b4b89c3ccb293040aa39c81a49"
REPO = {"id": P.REPO_ID, "full_name": P.REPO}
HUMAN = {"id": 99900001, "login": "offline-maintainer", "type": "User"}


def git(root, *args):
    result = subprocess.run(["git", "-c", "safe.directory=" + str(root), *args], cwd=root,
        env=dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null"),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=45)
    if result.returncode:
        raise RuntimeError("offline Git operation failed: " + args[0])
    return result.stdout.decode().strip()


def blob(raw):
    return {"mode": "100644", "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def rules():
    return {"id": 21804005, "target": "branch", "source_type": "Repository", "source": P.REPO,
            "enforcement": "active", "bypass_actors": [],
            "conditions": {"ref_name": {"exclude": [], "include": ["refs/heads/main"]}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                      {"type": "pull_request", "parameters": {"allowed_merge_methods": ["squash"],
                       "required_review_thread_resolution": True, "required_approving_review_count": 0}},
                      {"type": "required_status_checks", "parameters": {
                       "strict_required_status_checks_policy": True, "do_not_enforce_on_create": False,
                       "required_status_checks": [{"context": "summary", "integration_id": 15368}]}}]}


def run_record(rid, workflow, head, *, event="pull_request", attempt=2, current=False):
    return {"id": rid, "run_attempt": attempt, "run_number": rid, "workflow_id": rid // 10,
            "repository": copy.deepcopy(REPO), "head_repository": copy.deepcopy(REPO), "path": workflow, "head_sha": head,
            "event": event, "head_branch": P.BOT_REF if event == "pull_request" else "main",
            "status": "in_progress" if current else "completed", "conclusion": None if current else "success",
            "actor": copy.deepcopy(P.BOT if event == "pull_request" else HUMAN), "triggering_actor": copy.deepcopy(HUMAN),
            "pull_requests": []}


def archived(receipt, *, name="maintenance.json", extra=None, mode=stat.S_IFREG | 0o644):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(name); info.external_attr = mode << 16
        archive.writestr(info, json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode())
        if extra is not None:
            archive.writestr(extra, b"extra")
    return stream.getvalue()


class LocalGit(S.Git):
    def __init__(self, root, model):
        super().__init__(root); self.model = model; self.object_calls = 0
    def run(self, args, **kwargs):
        if args[0] == "fetch":
            return b""  # All exact local engineering objects already exist.
        if args[0] == "ls-remote":
            ref = args[2]
            sha = self.model["main"] if ref == "refs/heads/main" else self.model["pr"]["head"]["sha"]
            return (sha + "\t" + ref + "\n").encode()
        self.object_calls += 1
        return super().run(args, **kwargs)


class OfflineAPI:
    def __init__(self, model):
        self.model = model; self.counts = {}; self.archive_reads = 0
    def get(self, path):
        self.counts[path] = self.counts.get(path, 0) + 1
        if self.model.get("mutate"):
            self.model["mutate"](self.model, path, self.counts[path])
        m = self.model
        if path == "git/ref/heads/main":
            result = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": m["main"]}}
        elif path == "rulesets/21804005":
            result = m["rules"]
        elif path.startswith("commits/"):
            result = m["associated"]
        elif path.startswith("pulls/"):
            number = int(path.split("/")[1]); result = m["pr"] if number == 714 else m["prerequisite_prs"][number]
        elif path.startswith("actions/workflows/"):
            workflow = ".github/workflows/" + path.split("/")[2]
            run = m["m2"][workflow]["run"]
            result = {"total_count": 1, "workflow_runs": [run]}
        elif path.startswith("actions/runs/"):
            fields = path.split("/"); rid = int(fields[2])
            if rid == 999901:
                result = m["run"]
            elif rid in m["gate_runs"]:
                result = m["gate_runs"][rid]
            else:
                if not 999701 <= rid <= 999703:
                    raise P.Denied("OFFLINE_API_UNKNOWN_RUN")
                row = m["m2"][P.WORKFLOWS[rid - 999701]]
                if "jobs?" in path:
                    result = {"total_count": len(row["jobs"]), "jobs": row["jobs"]}
                elif "artifacts?" in path:
                    result = {"total_count": 1, "artifacts": [row["artifact"]]}
                else:
                    result = row["run"]
        else:
            raise AssertionError("unregistered offline API path: " + path)
        return copy.deepcopy(result)
    def archive(self, aid):
        self.archive_reads += 1
        return next(row["zip"] for row in self.model["m2"].values() if row["artifact"]["id"] == aid)


def merged_pr(number, base, head, merge, author):
    return {"number": number, "draft": False, "state": "closed", "merged": True,
            "merged_at": "2026-10-20T00:00:00Z", "merge_commit_sha": merge, "user": copy.deepcopy(author),
            "merged_by": copy.deepcopy(HUMAN), "base": {"ref": "main", "sha": base, "repo": copy.deepcopy(REPO)},
            "head": {"ref": P.BOT_REF if number == 714 else "offline-integration-" + str(number),
                     "sha": head, "repo": copy.deepcopy(REPO)}}


def run_suite():
    positives, negatives = [], []
    counts = {"actual_git_commands": 0, "offline_original_zip_reads": 0}
    with tempfile.TemporaryDirectory(prefix="t1-m3-push-engineering-") as temporary:
        area = Path(temporary) / "repo"
        git(Path(temporary), "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(area))
        git(area, "config", "user.email", "offline@example.invalid")
        git(area, "config", "user.name", "M3 Explicit Offline Fixture")
        git(area, "checkout", "--quiet", "--detach", BASELINE)
        for path in (P.SELF, P.REGISTRY, P.SOURCE, P.SOURCE_CONTRACT, *P.M2_FILES):
            (area / path).write_bytes((ROOT / path).read_bytes())
        git(area, "add", "."); git(area, "commit", "--quiet", "-m", "offline pending source")
        pending = git(area, "rev-parse", "HEAD")
        anchor_text = git(area, "show", S.SCIENCE_ANCHOR + ":" + P.WORKFLOW) + "\n"
        templates = S.workflow_templates(anchor_text)

        def changed(parent, changes, *, modes=None):
            git(area, "reset", "--hard", parent)
            for name, content in changes.items():
                path = area / name
                if path.exists() or path.is_symlink():
                    path.unlink()
                if content is None:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                if (modes or {}).get(name) == "symlink":
                    path.symlink_to(content)
                else:
                    path.write_bytes(content if type(content) is bytes else content.encode())
                    if (modes or {}).get(name) == "executable":
                        path.chmod(0o755)
            git(area, "add", "--all")
            return git(area, "commit-tree", git(area, "write-tree"), "-p", parent,
                       "-m", "offline actual Git mutation")

        # Existing fixed workflow-only hookups are source bytes, not claimed
        # real execution. Each local integration receives real independent
        # parent/head/squash objects and explicitly offline public metadata.
        # Reconstruct the fixed local hookup templates from reachable original
        # science and the reviewed M2 job. Never depend on an unmerged sibling
        # commit/blob accidentally cached in the developer's object database.
        originals = []
        for role in P.WORKFLOWS[:2]:
            raw = git(area, "show", BASELINE + ":" + role) + "\n"
            job = S.M2_JOB_TEMPLATE.replace(P.WORKFLOW, role).replace(
                Path(P.WORKFLOW).stem, Path(role).stem)
            raw = raw.replace("jobs:\n", "jobs:\n" + job, 1)
            for name in P.SCIENCE_JOBS[role]:
                raw = raw.replace("  " + name + ":\n", "  " + name + ":\n" + S.M2_DIAGNOSTIC_CONDITION, 1)
            if role == P.WORKFLOWS[1]:
                raw = raw.replace("    if: ${{ success() && needs.contracts.outputs.run_real_aec == 'true' }}\n",
                    "    # A failed/unused maintenance probe must not suppress the original science prerequisites.\n"
                    "    if: >-\n"
                    "      ${{ !cancelled() && needs.contracts.result == 'success' &&\n"
                    "          needs.bf-geometry.result == 'success' && needs.aec-tail.result == 'success' &&\n"
                    "          needs.ns-vad.result == 'success' && needs.contracts.outputs.run_real_aec == 'true' }}\n")
            originals.append(raw)
        originals.append(templates[S.M2_PROFILE + ":original-pins"])
        integrations, historical_prs = {}, {}
        current = pending
        for index, workflow in enumerate(P.WORKFLOWS):
            head = changed(current, {workflow: originals[index]})
            merge = git(area, "commit-tree", git(area, "rev-parse", head + "^{tree}"),
                        "-p", current, "-m", "offline independent M2 squash " + str(index))
            number = 999101 + index
            integrations[workflow] = {"number": number, "merged_sha": merge, "head_sha": head}
            historical_prs[number] = merged_pr(number, current, head, merge, HUMAN)
            current = merge
        anchor = current
        registry = json.loads((ROOT / P.REGISTRY).read_bytes())
        registry["m2_qualification"] = {"status": "COMPLETE", "protected_main_sha": anchor,
            "integration_prs": integrations, "verify": {"run_id": 999801, "run_attempt": 1},
            "release": {"run_id": 999802, "run_attempt": 1}}
        registry_raw = (json.dumps(registry, sort_keys=True, indent=2) + "\n").encode()
        contract = json.loads((ROOT / P.SOURCE_CONTRACT).read_bytes())
        contract["preregistered_final_push_source_closure"]["files"][P.REGISTRY] = blob(registry_raw)
        qualified_source = changed(anchor, {P.REGISTRY: registry_raw,
            P.SOURCE_CONTRACT: json.dumps(contract, sort_keys=True, indent=2) + "\n"})
        before = changed(qualified_source, {P.WORKFLOW: templates[P.PROFILE + ":original-pins"]})

        # Use the shared protected T0 lexical eligibility to construct the
        # complete reviewed candidate. The guard independently computes its
        # expected current-base matrix and actual full Git diff again.
        git(area, "reset", "--hard", before)
        t0 = load("fixture_t0", ROOT / P.T0)
        updates = {}
        for path in (area / ".github/workflows").glob("*.yml"):
            raw = path.read_text(); lines = raw.splitlines(keepends=True)
            eligible = t0._actual_step_uses_line_numbers(lines) - t0._yaml_literal_line_numbers(lines)
            for index in eligible:
                match = t0.USES.fullmatch(lines[index].rstrip("\r\n"))
                if match and match["action"] in t0.REVIEWED[P.REVIEW]:
                    old, new, _ = t0.REVIEWED[P.REVIEW][match["action"]]
                    if match["sha"] == old:
                        candidate = lines[index].replace(old, new)
                        if match["action"] == "actions/upload-artifact":
                            candidate = candidate.replace("# v7.0.1", "# v7.0.2")
                        assert t0.authorized_line(lines[index], candidate, review=P.REVIEW)
                        lines[index] = candidate
            if "".join(lines) != raw:
                updates[path.relative_to(area).as_posix()] = "".join(lines)
        bot_head = changed(before, updates)

        def case_for(head=bot_head, base=before, *, parents=None):
            tree = git(area, "rev-parse", head + "^{tree}")
            parent_args = [item for sha in (parents or [base]) for item in ("-p", sha)]
            after = git(area, "commit-tree", tree, *parent_args, "-m", "offline merged bot push")
            pr = merged_pr(714, base, head, after, P.BOT)
            event = {"repository": copy.deepcopy(REPO), "before": base, "after": after, "ref": "refs/heads/main",
                "created": False, "deleted": False, "forced": False, "head_commit": {"id": after}, "sender": copy.deepcopy(HUMAN)}
            env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": P.REPO, "GITHUB_SHA": after,
                "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "999901", "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_WORKFLOW_REF": P.REPO + "/" + P.WORKFLOW + "@refs/heads/main",
                "GITHUB_ACTOR": HUMAN["login"], "GITHUB_ACTOR_ID": str(HUMAN["id"]),
                "GITHUB_TRIGGERING_ACTOR": HUMAN["login"]}
            model = {"main": after, "pr": pr, "associated": [copy.deepcopy(pr)], "rules": rules(),
                "run": run_record(999901, P.WORKFLOW, after, event="push", current=True),
                "prerequisite_prs": historical_prs, "gate_runs": {
                    999801: run_record(999801, ".github/workflows/verify.yml", anchor, event="push", attempt=1),
                    999802: run_record(999802, ".github/workflows/release.yml", anchor, event="workflow_run", attempt=1)},
                "m2": {}}
            return event, env, model

        event, env, model = case_for()
        git(area, "reset", "--hard", before)
        engine = LocalGit(area, model)
        source, _, _, _, identities, m1, t0, m2, witness_hash = P.load_protected(area, before, supplied_git=engine)
        transition = P.reviewed_transition(engine, before, bot_head, event["after"], m1, t0, identities, witness_hash)
        synthetic = git(area, "commit-tree", transition["actual_bot_tree"], "-p", before,
                        "-p", bot_head, "-m", "offline original direct PR event")
        # Invoke actual M2 evaluate. Its open-PR M1 HTTP phase is replaced by
        # the real locally computed Git proof, with explicit offline metadata.
        original_m1 = m1.receipt(m1.ADMITTED, "ACTUAL_TRUSTED_GIT_PIN_SCOPE_ONLY", current_main=before,
            bot_base=before, bot_head=bot_head, actual_tree_checked=True, extra=transition)
        m1.git = lambda args, **kwargs: engine.run(args, cap=kwargs.get("cap", P.MAX_JSON))
        m1.git_sha = lambda args, **kwargs: engine.sha(args)
        m1.live_probe = lambda **kwargs: copy.deepcopy(original_m1)
        m1.remote_heads = lambda: (before, bot_head)
        open_pr = copy.deepcopy(model["pr"]); open_pr.update(state="open", merged=False, merged_at=None)
        open_pr["merge_commit_sha"] = synthetic
        m1.fetch_public_bot_pr = lambda: copy.deepcopy(open_pr)
        m2.load_m1 = lambda: m1
        for index, workflow in enumerate(P.WORKFLOWS):
            rid = 999701 + index; aid = 999601 + index
            pr_env = {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": P.REPO,
                "GITHUB_REF": "refs/pull/714/merge", "GITHUB_BASE_REF": "main", "GITHUB_HEAD_REF": P.BOT_REF,
                "GITHUB_SHA": synthetic, "GITHUB_RUN_ID": str(rid), "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_WORKFLOW_REF": P.REPO + "/" + workflow + "@refs/pull/714/merge"}
            receipt = m2.evaluate({"number": 714, "action": "synchronize", "repository": REPO,
                                   "pull_request": copy.deepcopy(open_pr)}, pr_env, workflow)
            assert receipt["decision"] == m2.POSITIVE, receipt
            raw = archived(receipt)
            job_names = ["maintenance", *sorted(P.SCIENCE_JOBS[workflow])]
            if workflow == P.WORKFLOWS[1]:
                job_names.append("real-aec-tail-confirmation / confirm")
            model["m2"][workflow] = {"run": run_record(rid, workflow, bot_head), "receipt": receipt,
                "jobs": [{"id": rid * 10 + j, "name": name, "run_id": rid, "run_attempt": 2,
                    "head_sha": bot_head, "status": "completed", "conclusion": "success" if name == "maintenance" else "skipped"}
                    for j, name in enumerate(job_names)], "zip": raw,
                "artifact": {"id": aid, "name": "workflow-pin-maintenance-" + Path(workflow).stem + "-" + str(rid),
                    "size_in_bytes": len(raw), "expired": False, "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "workflow_run": {"id": rid, "repository_id": P.REPO_ID, "head_repository_id": P.REPO_ID,
                                     "head_branch": P.BOT_REF, "head_sha": bot_head}}}
        control = (event, env, model)

        def observe(case, checkout=before):
            e, context, metadata = copy.deepcopy(case)
            git(area, "reset", "--hard", checkout)
            local, api = LocalGit(area, metadata), OfflineAPI(metadata)
            result = P.evaluate(e, context, api, root=area, supplied_git=local)
            counts["actual_git_commands"] += local.object_calls
            counts["offline_original_zip_reads"] += api.archive_reads
            return result, api
        def positive(name, case):
            result, api = observe(case)
            assert result["decision"] == P.POSITIVE and result["skip_measurement"] is True, (name, result)
            assert result["scientific_experiment_executed"] is False and result["acoustic_pass"] is False
            assert result["live_public_metadata_checked"] is False and result["evidence_role"] == "offline-engineering-fixture"
            assert api.archive_reads == 3 and api.counts["git/ref/heads/main"] == 2
            assert len(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()) <= P.MAX_RECEIPT
            positives.append({"name": name, "result": result})
        def negative(name, case, *, expected=None, checkout=before):
            result, _ = observe(case, checkout)
            assert result["decision"] == P.NEGATIVE and result["skip_measurement"] is False, (name, result)
            assert result["maintenance_push_admitted"] is False and result["scientific_experiment_executed"] is False
            assert expected is None or result["reason"] in expected, (name, result["reason"], expected)
            negatives.append({"name": name, "reason": result["reason"]})
        def mutated(name, mutate, expected=None):
            case = copy.deepcopy(control); mutate(*case); negative(name, case, expected=expected)
        def rewrite(row, receipt):
            row["receipt"] = receipt; row["zip"] = archived(receipt)
            row["artifact"].update(size_in_bytes=len(row["zip"]), digest="sha256:" + hashlib.sha256(row["zip"]).hexdigest())

        positive("complete_real_git_and_actual_m2_evaluator_three_original_fixture_zips", control)
        # Runtime object availability is different from test-source ancestry.
        # A fresh checkout containing only before and its ancestors has none of
        # the three historical, already-squashed integration PR head commits.
        # Exercise actual Git fetches, substituting only the public transport
        # with a local read-only mirror of these explicit engineering objects.
        historical_heads = sorted(row["head_sha"] for row in integrations.values())

        def missing_objects(root, revisions):
            absent = []
            for revision in revisions:
                try:
                    git(root, "cat-file", "-e", revision + "^{commit}")
                except RuntimeError:
                    absent.append(revision)
            return absent

        def before_only(label):
            fresh = Path(temporary) / label
            git(Path(temporary), "init", "--quiet", str(fresh))
            git(fresh, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", str(area), before)
            git(fresh, "checkout", "--quiet", "--detach", before)
            assert not (fresh / ".git/objects/info/alternates").exists()
            assert git(fresh, "rev-parse", "--is-shallow-repository") == "false"
            assert missing_objects(fresh, historical_heads) == historical_heads
            return fresh

        class ObjectMirrorGit(LocalGit):
            def __init__(self, root, metadata, mirror):
                super().__init__(root, metadata); self.mirror = mirror; self.fetches = []
            def run(self, args, **kwargs):
                if args[0] == "fetch":
                    canonical = "https://github.com/" + P.REPO + ".git"
                    assert args.count(canonical) == 1
                    self.fetches.append(list(args))
                    self.object_calls += 1
                    return S.Git.run(self, [str(self.mirror) if value == canonical else value
                                           for value in args], **kwargs)
                return super().run(args, **kwargs)

        def fresh_observation(label, mirror):
            fresh = before_only(label)
            e, v, metadata = copy.deepcopy(control)
            engine, api = ObjectMirrorGit(fresh, metadata, mirror), OfflineAPI(metadata)
            result = P.evaluate(e, v, api, root=fresh, supplied_git=engine)
            counts["actual_git_commands"] += engine.object_calls
            counts["offline_original_zip_reads"] += api.archive_reads
            return fresh, engine, api, result

        fresh, fetched, fresh_api, fresh_result = fresh_observation("fresh-before-only", area)
        assert fresh_result["decision"] == P.POSITIVE and fresh_result["skip_measurement"] is True, fresh_result
        assert fresh_result["live_public_metadata_checked"] is False and fresh_api.archive_reads == 3
        assert not missing_objects(fresh, historical_heads)
        historical_fetches = [args for args in fetched.fetches if set(args) & set(historical_heads)]
        assert len(historical_fetches) == 3
        assert sorted(sha for args in historical_fetches for sha in args if sha in historical_heads) == historical_heads
        positives.append({"name": "fresh_before_ancestor_checkout_fetches_three_squashed_pr_heads",
            "result": fresh_result, "initially_missing_historical_heads": historical_heads,
            "alternates": False, "shallow": False, "actual_object_fetches": fetched.fetches,
            "transport": "offline-local-Git-mirror"})

        unavailable = before_only("mirror-without-historical-heads")
        git(unavailable, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", str(area),
            event["after"], bot_head, synthetic)
        assert missing_objects(unavailable, historical_heads) == historical_heads
        _, _, failed_api, failed_result = fresh_observation("fresh-unavailable-heads", unavailable)
        assert failed_result["decision"] == P.NEGATIVE and failed_result["skip_measurement"] is False
        assert failed_result["reason"] == "GIT_COMMAND_FAILED_OR_OVERSIZED", failed_result
        assert failed_api.archive_reads == 0
        negatives.append({"name": "unavailable_historical_squash_heads_deny_before_artifact_reads",
                          "reason": failed_result["reason"]})

        # The final workflow-only human PR and its push still use the separate
        # source layer. This exact fourth profile grants source continuity only;
        # it cannot turn these non-Bot events into maintenance skips.
        source_tests = load("final_profile_source_fixture", ROOT / ".github/program/test_dechorate_event_source_t1m3.py")
        source_controls = []
        for is_push in (False, True):
            source_event, source_env, source_model = source_tests.model_for(
                area, qualified_source, before, push=is_push)
            git(area, "reset", "--hard", qualified_source)
            source_engine = source_tests.LocalNetworkGit(area, source_model)
            source_result = S.evaluate(source_event, source_env, source_engine, source_tests.OfflineMetadata(source_model))
            assert source_result["decision"] == S.POSITIVE, source_result
            assert source_result["skip_measurement"] is False and source_result["maintenance_push_admitted"] is False
            assert source_result["m1_m2_prerequisites_closed"] is False and source_result["scientific_experiment_executed"] is False
            assert source_result["frozen_source"]["workflow_execution_profiles"]["head"].startswith(P.PROFILE + ":")
            source_controls.append({"event": "push" if is_push else "pull_request", "result": source_result})
        dynamic = copy.deepcopy(control)
        def change_association(m, path, count):
            if count == 2 and path.startswith("actions/runs/"):
                m["run"]["pull_requests"] = [{"head": {"sha": "1" * 40}, "base": {"sha": "2" * 40}}]
                for row in m["m2"].values():
                    row["run"]["pull_requests"] = [{"head": {"sha": "3" * 40}}]
        dynamic[2]["mutate"] = change_association
        positive("mutable_pr_association_does_not_change_execution_sha_identity", dynamic)

        human_trigger = copy.deepcopy(control)
        git(area, "reset", "--hard", before)
        original_calls = engine.object_calls
        for workflow, row in human_trigger[2]["m2"].items():
            human_env = dict(pr_env, GITHUB_ACTOR=HUMAN["login"],
                GITHUB_ACTOR_ID=str(HUMAN["id"]), GITHUB_TRIGGERING_ACTOR=HUMAN["login"],
                GITHUB_RUN_ID=str(row["run"]["id"]),
                GITHUB_WORKFLOW_REF=P.REPO + "/" + workflow + "@refs/pull/714/merge")
            actual = m2.evaluate({"number": 714, "action": "synchronize", "repository": REPO,
                "sender": copy.deepcopy(HUMAN), "pull_request": copy.deepcopy(open_pr)}, human_env, workflow)
            assert actual["decision"] == m2.POSITIVE and actual == row["receipt"], actual
            row["run"]["actor"] = copy.deepcopy(HUMAN)
        counts["actual_git_commands"] += engine.object_calls - original_calls
        assert human_trigger[2]["pr"]["user"] == P.BOT
        positive("human_trigger_preserves_actual_m2_receipts_for_same_fixed_bot_author", human_trigger)

        pending_case = case_for(base=pending)
        negative("checked_in_registry_pending_never_admits", pending_case,
                 expected={"M2_QUALIFICATION_REGISTRY_PENDING"}, checkout=pending)
        for kind in ("pull_request", "workflow_call", "workflow_dispatch", "pull_request_target", ""):
            mutated("not_direct_push_" + kind, lambda e, v, m, kind=kind: v.update(GITHUB_EVENT_NAME=kind))
        for key, value in (("GITHUB_RUN_ID", "01"), ("GITHUB_RUN_ATTEMPT", "0"),
                           ("GITHUB_SHA", "f" * 7), ("GITHUB_REF", "refs/heads/other"),
                           ("GITHUB_REPOSITORY", "fork/repo"), ("GITHUB_ACTOR_ID", "1"),
                           ("GITHUB_WORKFLOW_REF", P.REPO + "/.github/workflows/pcr02-dsp-counterfactuals.yml@refs/heads/main")):
            mutated("event_environment_" + key, lambda e, v, m, k=key, val=value: v.__setitem__(k, val))
        for field in ("created", "deleted", "forced"):
            mutated("invalid_push_" + field, lambda e, v, m, f=field: e.__setitem__(f, True))
        mutated("zero_before", lambda e, v, m: e.update(before="0" * 40))
        for field, value in (("number", 715), ("merged", False), ("state", "open"), ("draft", True)):
            mutated("merged_bot_" + field, lambda e, v, m, f=field, val=value: m["pr"].__setitem__(f, val))
        for field, value in (("id", 1), ("type", "User"), ("login", "another-bot")):
            mutated("bot_author_" + field, lambda e, v, m, f=field, val=value: m["pr"]["user"].__setitem__(f, val))
        mutated("foreign_pr_head_repository", lambda e, v, m: m["pr"]["head"]["repo"].update(id=1))
        mutated("merger_identity_is_not_sender", lambda e, v, m: m["pr"]["merged_by"].update(id=1))
        mutated("ambiguous_merged_pr_association", lambda e, v, m: m["associated"].append(copy.deepcopy(m["pr"])))
        mutated("unknown_full_pr_head_object", lambda e, v, m: m["pr"]["head"].update(sha="f" * 40))
        mutated("qualified_main_verify_later_failure", lambda e, v, m: m["gate_runs"][999801].update(conclusion="failure"))
        mutated("qualified_main_release_wrong_execution_sha", lambda e, v, m: m["gate_runs"][999802].update(head_sha=before))
        mutated("registered_m2_integration_not_merged", lambda e, v, m: m["prerequisite_prs"][999101].update(merged=False))

        for path in (P.M1, P.T0, P.WITNESS, P.M2):
            bad_base = changed(before, {path: (ROOT / path).read_bytes() + b"\n"})
            negative("protected_runtime_blob_" + Path(path).name, case_for(base=bad_base),
                     expected={"M2_RUNTIME_SOURCE_CLOSURE_DRIFT"}, checkout=bad_base)
        for mode in ("executable", "symlink"):
            bad_base = changed(before, {P.M2: (ROOT / P.M2).read_bytes() if mode == "executable" else "workflow_pin_only_actual_tree_t1m1.py"},
                               modes={P.M2: mode})
            negative("protected_consumer_" + mode, case_for(base=bad_base),
                     expected={"PROTECTED_SOURCE_MODE_OR_TYPE_DRIFT"}, checkout=bad_base)
        altered_science = changed(before, {S.SCIENCE: (ROOT / S.SCIENCE).read_bytes() + b"\n"})
        bad_science_head = changed(altered_science, updates)
        bad_science_case = case_for(head=bad_science_head, base=altered_science)
        bad_science_case[2]["m2"] = copy.deepcopy(model["m2"])
        negative("original_scientific_source_changed_before_maintenance", bad_science_case,
                 expected={"SCIENTIFIC_SOURCE_OR_MANIFEST_CHANGED"}, checkout=altered_science)

        two_parent = case_for(parents=[before, bot_head]); two_parent[2]["m2"] = copy.deepcopy(model["m2"])
        negative("actual_two_parent_push_rejected", two_parent, expected={"PUSH_NOT_EXACT_SINGLE_PARENT_SQUASH"})
        for name, changes, modes in (
            ("mixed_c_source", {"src/audio_pipeline.c": "/* offline mixed code */\n"}, None),
            ("workflow_permissions", {P.WORKFLOW: updates[P.WORKFLOW].replace("  contents: read", "  contents: write")}, None),
            ("workflow_run_command", {P.WORKFLOW: updates[P.WORKFLOW].replace("          set -euo pipefail", "          echo altered", 1)}, None),
            ("unreviewed_action", {P.WORKFLOW: updates[P.WORKFLOW].replace(S.UPLOAD_NEW, "9" * 40)}, None),
            ("partial_current_base_transition", {P.WORKFLOW: templates[P.PROFILE + ":original-pins"]}, None),
            ("executable_workflow", {P.WORKFLOW: updates[P.WORKFLOW]}, {P.WORKFLOW: "executable"}),
            ("symlink_workflow", {P.WORKFLOW: "verify.yml"}, {P.WORKFLOW: "symlink"}),
            ("mixed_source_helper", {P.M2: (ROOT / P.M2).read_text() + "\n# changed\n"}, None),
        ):
            bad_head = changed(bot_head, changes, modes=modes)
            case = case_for(head=bad_head); case[2]["m2"] = copy.deepcopy(model["m2"])
            negative("actual_git_" + name, case)

        for field, value in (("id", 1), ("run_attempt", 3), ("workflow_id", 1), ("path", P.WORKFLOWS[0]),
                            ("head_sha", "1" * 40), ("head_branch", "other"), ("event", "workflow_dispatch"),
                            ("status", "completed"), ("conclusion", "success"), ("run_number", 1)):
            def mutate_run(e, v, m, field=field, value=value):
                def second(model, path, count):
                    if path == "git/ref/heads/main" and count == 2:
                        model["run"][field] = value
                m["mutate"] = second
            mutated("current_run_second_read_" + field, mutate_run)
        for name, effect in (
            ("main_ref", lambda m: m.update(main="1" * 40)),
            ("rules_bypass", lambda m: m["rules"].update(bypass_actors=[{"actor_id": 1}])),
            ("rules_strict", lambda m: m["rules"]["rules"][3]["parameters"].update(strict_required_status_checks_policy=False)),
            ("pr_author", lambda m: m["pr"]["user"].update(id=1)),
            ("pr_merger", lambda m: m["pr"]["merged_by"].update(id=1)),
        ):
            def mutate_second(e, v, m, effect=effect):
                m["mutate"] = lambda data, path, count: effect(data) if path == "git/ref/heads/main" and count == 2 else None
            mutated("second_read_" + name, mutate_second)

        role = P.WORKFLOWS[0]
        for identity in ("actor", "triggering_actor"):
            for field, value in (("id", 12345), ("login", "changed-triggerer"),
                                 ("type", "User" if identity == "actor" else "Bot")):
                def actor_second(e, v, m, identity=identity, field=field, value=value):
                    rid = m["m2"][role]["run"]["id"]
                    def second(data, path, count):
                        if path == "actions/runs/" + str(rid) and count == 2:
                            data["m2"][role]["run"][identity][field] = value
                    m["mutate"] = second
                mutated("direct_m2_second_read_" + identity + "_" + field, actor_second,
                        {"M2_RUN_OR_ARTIFACT_MOVED_DURING_READBACK"})
        for field, value in (("run_id", 999702), ("run_attempt", 1), ("run_attempt", "2"),
                            ("consumer_sha256", "1" * 64), ("base_sha", "2" * 40), ("head_sha", "3" * 40),
                            ("workflow", P.WORKFLOWS[1]), ("scientific_experiment_executed", True),
                            ("decision", "success"), ("event_merge_sha", before)):
            def change_receipt(e, v, m, field=field, value=value):
                row = m["m2"][role]; receipt = copy.deepcopy(row["receipt"]); receipt[field] = value; rewrite(row, receipt)
            mutated("m2_original_receipt_" + field + "_" + str(value)[:8], change_receipt)
        def rerun_old_receipt(e, v, m):
            row = m["m2"][role]; row["run"]["run_attempt"] = 3
            for job in row["jobs"]: job["run_attempt"] = 3
        mutated("old_attempt_original_cannot_become_current_rerun", rerun_old_receipt,
                {"M2_RECEIPT_RUN_SOURCE_OR_DECISION_DRIFT"})
        for field, value in (("id", 999702), ("head_sha", "1" * 40), ("repository_id", 1), ("head_repository_id", 1)):
            mutated("artifact_workflow_run_" + field,
                    lambda e, v, m, f=field, val=value: m["m2"][role]["artifact"]["workflow_run"].__setitem__(f, val))
        for field, value in (("event", "workflow_dispatch"), ("path", P.WORKFLOWS[1]),
                            ("head_sha", "1" * 40), ("status", "in_progress"), ("conclusion", "failure")):
            mutated("direct_m2_run_" + field,
                    lambda e, v, m, f=field, val=value: m["m2"][role]["run"].__setitem__(f, val))
        mutated("wrong_m2_execution_sha_not_rescued_by_dynamic_pr_array",
                lambda e, v, m: m["m2"][role]["run"].update(head_sha="1" * 40,
                    pull_requests=[{"head": {"sha": bot_head}, "base": {"sha": before}}]))
        mutated("m2_expected_science_job_missing", lambda e, v, m: m["m2"][role]["jobs"].pop())
        mutated("m2_science_job_success_cannot_be_skip_receipt", lambda e, v, m: m["m2"][role]["jobs"][1].update(conclusion="success"))
        mutated("m2_artifact_expired", lambda e, v, m: m["m2"][role]["artifact"].update(expired=True))
        mutated("m2_artifact_api_digest_mismatch", lambda e, v, m: m["m2"][role]["artifact"].update(digest="sha256:" + "0" * 64))
        def artifact_second(e, v, m):
            rid = m["m2"][role]["run"]["id"]
            m["mutate"] = lambda data, path, count: data["m2"][role]["artifact"].update(id=123) if path == "actions/runs/" + str(rid) + "/artifacts?per_page=100" and count == 2 else None
        mutated("artifact_changed_after_whole_zip_readback", artifact_second,
                {"M2_RUN_OR_ARTIFACT_MOVED_DURING_READBACK"})
        for field in ("pin_diff_sha256", "expected_current_base_pin_diff_sha256", "bot_patch_witness_sha256",
                      "trusted_classifier_sha256", "trusted_qualifier_sha256", "actual_bot_tree"):
            def m1_drift(e, v, m, field=field):
                row = m["m2"][role]; receipt = copy.deepcopy(row["receipt"])
                receipt["m1"][field] = "1" * len(receipt["m1"][field]); rewrite(row, receipt)
            mutated("m1_receipt_" + field, m1_drift)
        def missing_run_identity(e, v, m):
            row = m["m2"][role]; receipt = copy.deepcopy(row["receipt"])
            del receipt["run_id"]; rewrite(row, receipt)
        mutated("old_original_missing_run_identity", missing_run_identity)

        # Resealed unsafe ZIPs reach the real member parser after digest passes.
        for name, raw in (
            ("traversal", archived(model["m2"][role]["receipt"], name="../maintenance.json")),
            ("extra_member", archived(model["m2"][role]["receipt"], extra="extra.json")),
            ("symlink", archived(model["m2"][role]["receipt"], mode=stat.S_IFLNK | 0o644)),
            ("executable", archived(model["m2"][role]["receipt"], mode=stat.S_IFREG | 0o755)),
            ("malformed_zip", b"not a zip"),
        ):
            try:
                P.original_receipt(raw, {"size_in_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
            except ValueError as exc:
                negatives.append({"name": "resealed_zip_" + name, "reason": str(exc)})
            else:
                raise AssertionError("unsafe ZIP admitted: " + name)
        # Reusing a single ID under distinct names cannot supply three roles.
        duplicate = copy.deepcopy(model)
        duplicate["m2"][P.WORKFLOWS[1]]["artifact"]["id"] = duplicate["m2"][role]["artifact"]["id"]
        try:
            P.m2_snapshot(OfflineAPI(duplicate), engine, before, bot_head, identities, transition, m1, m2, read_archives=False)
        except ValueError as exc:
            assert str(exc) == "THREE_DISTINCT_DIRECT_M2_ORIGINALS_REQUIRED", exc
            negatives.append({"name": "same_original_artifact_id_cannot_supply_two_workflows", "reason": str(exc)})
        else:
            raise AssertionError("same artifact reused")
        duplicate = copy.deepcopy(model)
        duplicate["m2"][P.WORKFLOWS[1]]["artifact"]["digest"] = duplicate["m2"][role]["artifact"]["digest"]
        try:
            P.m2_snapshot(OfflineAPI(duplicate), engine, before, bot_head, identities, transition, m1, m2, read_archives=False)
        except ValueError as exc:
            assert str(exc) == "THREE_DISTINCT_DIRECT_M2_ORIGINALS_REQUIRED", exc
            negatives.append({"name": "same_original_zip_digest_cannot_supply_two_workflows", "reason": str(exc)})
        else:
            raise AssertionError("same ZIP reused")

        # Public CLI denial writes a real receipt/seal and cannot call network.
        git(area, "reset", "--hard", pending)
        receipt_path = Path(temporary) / "pending-result.json"
        event_path = Path(temporary) / "pending-event.json"
        event_path.write_text(json.dumps(pending_case[0]))
        output, summary = Path(temporary) / "output", Path(temporary) / "summary"
        output.touch(); summary.touch()
        cli = subprocess.run(["python3", str(area / P.SELF), "--event-file", str(event_path),
            "--receipt", str(receipt_path), "--github-output", str(output), "--summary-file", str(summary)],
            cwd=area, env=dict(os.environ, **pending_case[1]), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False)
        cli_result = json.loads(receipt_path.read_bytes())
        assert cli.returncode == 0 and cli_result["reason"] == "M2_QUALIFICATION_REGISTRY_PENDING", cli.stderr
        assert output.read_text() == "skip_measurement=false\n"
        assert receipt_path.with_name(receipt_path.name + ".sha256").read_text().startswith(hashlib.sha256(receipt_path.read_bytes()).hexdigest())
        negatives.append({"name": "actual_cli_pending_receipt_and_false_output", "reason": cli_result["reason"]})
        original_bytes = receipt_path.read_bytes()
        try:
            P.write_receipt(receipt_path, {"decision": "overwritten"})
        except ValueError as exc:
            assert str(exc) == "EXISTING_RECEIPT_MUST_BE_PRESERVED"
            assert receipt_path.read_bytes() == original_bytes
            negatives.append({"name": "existing_receipt_is_never_rewritten", "reason": str(exc)})
        else:
            raise AssertionError("old receipt overwritten")

    return {"schema_version": 1, "evidence_role": "offline-engineering-fixture",
            "actual_m1_m2_qualification": False, "actual_scientific_experiment_executed": False,
            "checked_in_registry_status": json.loads((ROOT / P.REGISTRY).read_bytes())["m2_qualification"]["status"],
            "actual_git_base": BASELINE, "helper_sha256": hashlib.sha256((ROOT / P.SELF).read_bytes()).hexdigest(),
            "nonvacuous_controls": positives, "final_template_source_only_controls": source_controls,
            "rejected_mutations": negatives, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_suite()
    raw = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    if args.output:
        with args.output.open("xb") as stream: stream.write(raw)
    print(json.dumps({"result": "T1_M3_PUSH_REAL_GIT_SELF_TEST_PASS", "positives": len(report["nonvacuous_controls"]),
        "negatives": len(report["rejected_mutations"]), "actual_git_commands": report["actual_git_commands"],
        "actual_m1_m2_qualification": False, "actual_scientific_experiment_executed": False,
        "report_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
