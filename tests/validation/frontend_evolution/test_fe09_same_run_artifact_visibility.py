#!/usr/bin/env python3
"""Offline deterministic exact-run artifact availability/negative-policy tests."""
from __future__ import annotations
import io
import json
import copy
import unittest
import urllib.error
from unittest.mock import Mock, patch
from pathlib import Path

import fe09_same_run_artifact_visibility as policy

REPO = "jiying2007/audio-pipeline"
RUN = 12345
ARTIFACT = 98765
NAME = "frontend-fe09-t2b-b1s0-owner-spsc-12345"
B1S1_NAME = "frontend-fe09-t2b-b1s1-source-apx3-12345"
DIGEST = "sha256:" + "a" * 64


class FakeResp:
    def __init__(self, metadata=None, *, raw=None, status=200, url=None):
        self.status = status
        self.url = url or (
            "https://api.github.com/repos/" + REPO +
            "/actions/artifacts/" + str(ARTIFACT)
        )
        self.data = (raw if raw is not None else json.dumps(metadata).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        assert n == 65537
        return self.data


def sample(name=NAME):
    return {
        "id": ARTIFACT, "name": name,
        "expired": False, "size_in_bytes": 5642,
        "digest": DIGEST,
        "workflow_run": {"id": RUN},
    }


def http_error(code: int):
    return urllib.error.HTTPError(
        "https://api.github.com/", code, "synthetic only", None, None)


class SameRunReadbackPolicyTests(unittest.TestCase):
    def check(self, values, *, artifact_name=NAME, attempts=8):
        values = iter(values)
        opened, paused = [], []
        def opener(request, timeout):
            opened.append((request, timeout))
            value = next(values)
            if isinstance(value, Exception):
                raise value
            return value
        got = policy.check_visibility(
            REPO, RUN, ARTIFACT, artifact_name, "fake-test-only-token",
            opener=opener, pause=paused.append,
            attempts=attempts, delay_seconds=0
        )
        return got, opened, paused

    def test_immediate_same_run_exact_artifact(self):
        (attempt, digest), opened, paused = self.check([FakeResp(sample())])
        self.assertEqual((attempt, digest), (1, DIGEST))
        self.assertEqual(len(opened), 1)
        self.assertEqual(paused, [])
        request, timeout = opened[0]
        self.assertEqual(timeout, 10)
        self.assertEqual(request.full_url,
                         "https://api.github.com/repos/" + REPO +
                         "/actions/artifacts/" + str(ARTIFACT))
        self.assertNotIn("fake-test-only-token", request.full_url)

    def test_transient_not_yet_visible_twice_then_exact_match(self):
        (attempt, digest), opened, paused = self.check(
            [http_error(404), http_error(404), FakeResp(sample())])
        self.assertEqual((attempt, digest), (3, DIGEST))
        self.assertEqual(len(opened), 3)
        self.assertEqual(paused, [0, 0])

    def test_transient_503_then_same_run_matches(self):
        (attempt, _), _, paused = self.check(
            [http_error(503), FakeResp(sample())])
        self.assertEqual(attempt, 2)
        self.assertEqual(paused, [0])

    def test_404_exhaustion_fails_closed_not_bypassed(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_VISIBLE"):
            self.check([http_error(404), http_error(404)], attempts=2)

    def test_http_403_401_429_do_not_retry(self):
        for code in (401, 403, 429):
            with self.subTest(code=code):
                with self.assertRaisesRegex(
                    policy.NotAdmitted, "HTTP_HARD_FAILURE"
                ):
                    self.check([http_error(code)], attempts=8)

    def test_wrong_id_name_run_expired_or_size_rejected(self):
        for key, value in (
            ("id", ARTIFACT + 1), ("name", NAME + "-spoof"),
            ("expired", True), ("size_in_bytes", 0),
            ("size_in_bytes", 1 << 21), ("digest", "sha256:bad"),
        ):
            with self.subTest(key=key, value=value):
                wrong = sample()
                wrong[key] = value
                with self.assertRaises(policy.NotAdmitted):
                    self.check([FakeResp(wrong)])
        wrong = sample()
        wrong["workflow_run"] = {"id": RUN - 1}
        with self.assertRaises(policy.NotAdmitted):
            self.check([FakeResp(wrong)])

    def test_bad_json_schema_duplicate_keys_and_oversize(self):
        payloads = (
            b'{"id":1,"id":1}',
            b'{not-json',
            b" " * 65537,
            b"",
        )
        for body in payloads:
            with self.subTest(payload_len=len(body)):
                with self.assertRaises(
                    (policy.NotAdmitted, ValueError, json.JSONDecodeError)
                ):
                    self.check([FakeResp(raw=body)])

    def test_redirection_to_noncanonical_source_rejected(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "REDIRECT"):
            self.check([FakeResp(sample(),
                                 url="https://example.invalid/spoof")])

    def test_unbounded_retry_and_false_identity_rejected(self):
        bad_calls = (
            (REPO, RUN, ARTIFACT, NAME + "-new", "token"),
            (REPO, RUN + 1, ARTIFACT, NAME, "token"),
            (REPO, RUN, 0, NAME, "token"),
            ("bad.repo", RUN, ARTIFACT, NAME, "token"),
            (REPO, RUN, ARTIFACT, NAME, ""),
        )
        for args in bad_calls:
            with self.subTest(args=args):
                with self.assertRaises(policy.NotAdmitted):
                    policy.check_visibility(*args, opener=Mock(
                        side_effect=AssertionError("network should not run")))
        with self.assertRaises(policy.NotAdmitted):
            policy.check_visibility(
                REPO, RUN, ARTIFACT, NAME, "token",
                attempts=9,
                opener=Mock(side_effect=AssertionError("network")))

    def test_b1s1_exact_identity_visible_immediately_and_after_404(self):
        observed = sample(B1S1_NAME)
        (attempt, digest), opened, paused = self.check(
            [FakeResp(observed)], artifact_name=B1S1_NAME)
        self.assertEqual((attempt, digest), (1, DIGEST))
        self.assertEqual(len(opened), 1)
        self.assertEqual(paused, [])
        (attempt, digest), opened, paused = self.check(
            [http_error(404), http_error(503), FakeResp(observed)],
            artifact_name=B1S1_NAME)
        self.assertEqual((attempt, digest), (3, DIGEST))
        self.assertEqual(len(opened), 3)
        self.assertEqual(paused, [0, 0])

    def test_b1s1_rejects_other_run_wrong_source_or_bad_digest(self):
        for field, altered in (
            ("id", ARTIFACT + 2),
            ("name", NAME),  # B1-S0 is not a B1-S1 run Artifact.
            ("name", B1S1_NAME + "-spoof"),
            ("digest", "sha256:bad"),
            ("expired", True),
            ("size_in_bytes", 0),
        ):
            with self.subTest(field=field, altered=altered):
                metadata = sample(B1S1_NAME)
                metadata[field] = altered
                with self.assertRaises(policy.NotAdmitted):
                    self.check([FakeResp(metadata)], artifact_name=B1S1_NAME)
        metadata = sample(B1S1_NAME)
        metadata["workflow_run"] = {"id": RUN + 1}
        with self.assertRaises(policy.NotAdmitted):
            self.check([FakeResp(metadata)], artifact_name=B1S1_NAME)
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_VISIBLE"):
            self.check([http_error(404), http_error(404)],
                       artifact_name=B1S1_NAME, attempts=2)
        with self.assertRaisesRegex(policy.NotAdmitted, "HTTP_HARD_FAILURE"):
            self.check([http_error(403)], artifact_name=B1S1_NAME)

    def test_b1s1_scope_cannot_be_forged_or_unbounded(self):
        for name in (
            "frontend-fe09-t2b-b1s1-source-apx3-12346",  # wrong run
            "frontend-fe09-t2b-b1s1-source-apx3-foo",
            "frontend-fe09-t2b-b1s0-owner-spsc-12345-extra",
            "frontend-fe09-other-stage-12345",
            "../frontend-fe09-t2b-b1s1-source-apx3-12345",
        ):
            with self.subTest(name=name):
                with self.assertRaises(policy.NotAdmitted):
                    self.check([FakeResp(sample(B1S1_NAME))],
                               artifact_name=name)
        with self.assertRaises(policy.NotAdmitted):
            policy.check_visibility(REPO, RUN, ARTIFACT, B1S1_NAME,
                "token", attempts=9,
                opener=Mock(side_effect=AssertionError("network should not run")))


    def test_b1s1_workflow_cannot_skip_mandatory_readback(self):
        quality = (Path(__file__).resolve().parents[3] /
                   ".github/workflows/quality.yml").read_text("utf-8")
        stage = quality.split("  frontend-s3-t2b-b1s1:\n", 1)[1].split(
            "\n  frontend-speech:", 1)[0]
        markers = [
            "id: fe09_b1s1\n",
            "id: fe09_b1s1_upload\n",
            "steps.fe09_b1s1_upload.outputs.artifact-id",
            "--artifact-name \"frontend-fe09-t2b-b1s1-source-apx3-$GITHUB_RUN_ID\"",
            "uses: actions/download-artifact@",
            "--verify --output fe09-b1s1-readback",
            "B1S1_ARTIFACT_FOUR_MEMBERS_DRIFT",
        ]
        offsets = [stage.index(marker) for marker in markers]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("if-no-files-found: error", stage)
        self.assertIn("retention-days: 30", stage)
        self.assertNotIn("continue-on-error:", stage)
        # Original B1-S0 reader must remain separately bound and pinned.
        previous = quality.split("  frontend-s3-t2b-b1s0:\n", 1)[1].split(
            "\n  frontend-s3-t2b-b1s1:", 1)[0]
        self.assertIn("steps.fe09_b1s0_upload.outputs.artifact-id", previous)
        self.assertIn("uses: actions/download-artifact@", previous)

class A1RestListVisibilityTests(unittest.TestCase):
    """Synthetic metadata only; no uploaded or scientific evidence is created."""
    NAME = "frontend-fe09-t3s2b1ba1-anchor-12345"
    HEAD = "b" * 40
    SOURCE = "c" * 40
    ATTEMPT = 2
    RUN_URL = f"https://api.github.com/repos/{REPO}/actions/runs/{RUN}/attempts/2"
    LIST_URL = f"https://api.github.com/repos/{REPO}/actions/runs/{RUN}/artifacts?per_page=100&page="

    def run_record(self):
        return {"id": RUN, "run_attempt": self.ATTEMPT, "head_sha": self.HEAD,
                "status": "in_progress", "conclusion": None,
                "run_started_at": "2026-10-22T06:00:00Z",
                "repository": {"full_name": REPO, "id": 100},
                "head_repository": {"id": 101},
                "referenced_workflows": [{
                    "path": f"{REPO}/.github/workflows/quality.yml@{self.SOURCE}",
                    "sha": self.SOURCE}]}

    def artifact(self):
        value = sample(self.NAME)
        value.update(created_at="2026-10-22T06:01:00Z", workflow_run={
            "id": RUN, "head_sha": self.HEAD,
            "repository_id": 100, "head_repository_id": 101})
        return value

    def response(self, payload=None, *, page=None, raw=None, url=None):
        class Response(FakeResp):
            def read(self, n):
                expected = 65537 if page is None else policy.A1_LIST_RESPONSE_CAP + 1
                assert n == expected
                return self.data[:n]
        return Response(payload, raw=raw,
                        url=url or (self.RUN_URL if page is None else self.LIST_URL + str(page)))

    def listing(self, rows=None, *, total=None, page=1):
        rows = [self.artifact()] if rows is None else rows
        return self.response({"total_count": len(rows) if total is None else total,
                              "artifacts": rows}, page=page)

    def check(self, replies, **changes):
        replies = iter(replies)
        self.opened, self.paused = [], []
        def opener(request, timeout):
            self.opened.append((request.full_url, timeout))
            value = next(replies)
            if isinstance(value, Exception):
                raise value
            return value
        params = dict(run_attempt=self.ATTEMPT, run_head_sha=self.HEAD,
                      execution_source=self.SOURCE, attempts=8, delay_seconds=2)
        params.update(changes)
        return policy.check_visibility(REPO, RUN, ARTIFACT, self.NAME,
            "fake-test-only-token", opener=opener, pause=self.paused.append, **params)

    def test_exact_attempt_and_actual_public_rest_list(self):
        result = self.check([self.response(self.run_record()), self.listing()])
        self.assertEqual(result, (2, DIGEST))
        self.assertEqual(self.opened, [(self.RUN_URL, 10), (self.LIST_URL + "1", 10)])
        self.assertEqual(self.paused, [])

    def test_missing_list_then_visible_within_shared_budget(self):
        result = self.check([http_error(404), self.response(self.run_record()),
                             self.listing([]), http_error(503), self.listing()])
        self.assertEqual(result, (5, DIGEST))
        self.assertEqual(self.paused, [2, 2, 2])
        self.assertEqual(len(self.opened), 5)

    def test_single_artifact_metadata_is_not_list_visibility(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "LIST_SCHEMA"):
            self.check([self.response(self.run_record()),
                        self.response(self.artifact(), page=1)])

    def test_absence_cannot_use_a_ninth_request_or_pause(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_VISIBLE"):
            self.check([self.response(self.run_record())] + [self.listing([])] * 7)
        self.assertEqual(len(self.opened), 8)
        self.assertEqual(self.paused, [2] * 6)
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_VISIBLE"):
            self.check([http_error(404)] * 8)
        self.assertEqual(len(self.opened), 8)
        self.assertEqual(self.paused, [2] * 7)

    def test_wrong_run_attempt_source_and_repository_fail_before_enumeration(self):
        mutations = [
            lambda x: x.update(id=RUN + 1), lambda x: x.update(run_attempt=1),
            lambda x: x.update(run_attempt=True), lambda x: x.update(head_sha="d" * 40),
            lambda x: x.update(status="completed"),
            lambda x: x["repository"].update(full_name="other/repository"),
            lambda x: x.update(referenced_workflows=[]),
            lambda x: x["referenced_workflows"][0].update(sha="d" * 40),
            lambda x: x["referenced_workflows"].append(copy.deepcopy(x["referenced_workflows"][0])),
        ]
        for mutate in mutations:
            value = self.run_record(); mutate(value)
            with self.subTest(value=value), self.assertRaises(policy.NotAdmitted):
                self.check([self.response(value)])
            self.assertEqual(len(self.opened), 1)

    def test_run_identity_fixed_fields_preserve_other_legacy_rejections(self):
        # Independent pre-diagnostic predicate checks unchanged refusals.
        # Queued/null admission and the new conclusion guard are tested below.
        # Fixtures are API metadata only, never scientific evidence.
        def legacy(p):
            return (type(p) is dict and type(p.get("id")) is int and
                    p["id"] == RUN and type(p.get("run_attempt")) is int and
                    p["run_attempt"] == self.ATTEMPT and
                    p.get("head_sha") == self.HEAD and
                    p.get("status") == "in_progress" and
                    type(p.get("repository")) is dict and
                    p["repository"].get("full_name") == REPO and
                    type(p["repository"].get("id")) is int and
                    p["repository"]["id"] > 0 and
                    type(p.get("head_repository")) is dict and
                    type(p["head_repository"].get("id")) is int and
                    p["head_repository"]["id"] > 0)

        cases = []
        for value in (None, [], "response-value-must-not-leak", 1, True):
            cases.append((value, "PAYLOAD_TYPE"))
        fields = (
            (("id",), (None, True, str(RUN), RUN + 1), "ID"),
            (("run_attempt",), (None, True, str(self.ATTEMPT), 0), "RUN_ATTEMPT"),
            (("head_sha",), (None, [], "response-value-must-not-leak"), "HEAD_SHA"),
            (("status",), (None, "completed", "waiting", []), "STATUS"),
            (("repository",), (None, [], "response-value-must-not-leak"), "REPOSITORY_TYPE"),
            (("repository", "full_name"), (None, [], "response-value-must-not-leak"),
             "REPOSITORY_FULL_NAME"),
            (("repository", "id"), (None, True, "100", 0, -1), "REPOSITORY_ID"),
            (("head_repository",), (None, [], "response-value-must-not-leak"),
             "HEAD_REPOSITORY_TYPE"),
            (("head_repository", "id"), (None, True, "101", 0, -1),
             "HEAD_REPOSITORY_ID"),
        )
        for path, values, field in fields:
            for value in values:
                record = self.run_record()
                target = record if len(path) == 1 else record[path[0]]
                target[path[-1]] = value
                cases.append((record, field))
            record = self.run_record()
            target = record if len(path) == 1 else record[path[0]]
            del target[path[-1]]
            cases.append((record, field))
        record = self.run_record()
        record.update(id=0, status="completed", repository=None)
        cases.append((record, "ID"))  # First failed field remains deterministic.
        for record, field in cases:
            with self.subTest(field=field, record=record):
                self.assertFalse(legacy(record))
                with self.assertRaises(policy.NotAdmitted) as caught:
                    self.check([self.response(record)])
                self.assertEqual(str(caught.exception),
                    "A1_RUN_ATTEMPT_REPOSITORY_OR_HEAD_MISMATCH:" + field)
                self.assertEqual(len(self.opened), 1)
                self.assertEqual(self.paused, [])
                if type(record) is dict and field != "STATUS":
                    queued = copy.deepcopy(record)
                    queued["status"] = "queued"
                    with self.assertRaises(policy.NotAdmitted) as caught:
                        self.check([self.response(queued)])
                    self.assertEqual(str(caught.exception),
                        "A1_RUN_ATTEMPT_REPOSITORY_OR_HEAD_MISMATCH:" + field)
                    self.assertEqual(len(self.opened), 1)
                    self.assertEqual(self.paused, [])
        for repo_id, head_id in ((1, 1), (100, 101), (2 ** 64, 2 ** 64)):
            record = self.run_record()
            record["repository"]["id"] = repo_id
            record["head_repository"]["id"] = head_id
            self.assertTrue(legacy(record))
            policy.verify_run_identity(record, repo=REPO, run_id=RUN,
                run_attempt=self.ATTEMPT, run_head_sha=self.HEAD)

    def test_nonterminal_scheduling_with_explicit_null_conclusion(self):
        for status in ("queued", "in_progress"):
            with self.subTest(status=status):
                record = self.run_record()
                record["status"] = status
                self.assertEqual(self.check([self.response(record), self.listing()]),
                                 (2, DIGEST))
                self.assertEqual(self.opened, [(self.RUN_URL, 10), (self.LIST_URL + "1", 10)])
                self.assertEqual(self.paused, [])
                for value in ("success", "failure", "cancelled", "", False, 0, [], {}):
                    record["conclusion"] = value
                    with self.subTest(conclusion=value), self.assertRaisesRegex(
                            policy.NotAdmitted, "MISMATCH:CONCLUSION$"):
                        self.check([self.response(record)])
                    self.assertEqual(len(self.opened), 1)
                    self.assertEqual(self.paused, [])
                del record["conclusion"]
                with self.assertRaisesRegex(policy.NotAdmitted, "MISMATCH:CONCLUSION$"):
                    self.check([self.response(record)])
                self.assertEqual(len(self.opened), 1)
                self.assertEqual(self.paused, [])
        for status in (None, True, 1, [], {}, "", "requested", "waiting", "pending",
                       "completed", "success", "failure", "cancelled", "unknown"):
            record = self.run_record()
            record["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(
                    policy.NotAdmitted, "MISMATCH:STATUS$"):
                self.check([self.response(record)])
            self.assertEqual(len(self.opened), 1)
            self.assertEqual(self.paused, [])

    def test_queued_scheduling_does_not_waive_execution_or_artifact_source(self):
        for mutate in (
            lambda x: x.update(referenced_workflows=[]),
            lambda x: x["referenced_workflows"][0].update(sha="d" * 40),
            lambda x: x.update(run_started_at="invalid"),
        ):
            record = self.run_record()
            record["status"] = "queued"
            mutate(record)
            with self.assertRaises(policy.NotAdmitted):
                self.check([self.response(record)])
            self.assertEqual(len(self.opened), 1)
            self.assertEqual(self.paused, [])
        for mutate in (
            lambda x: x.update(id=ARTIFACT + 1),
            lambda x: x.update(name="wrong-name"),
            lambda x: x.update(digest="sha256:bad"),
            lambda x: x.update(created_at="2026-10-22T05:59:59Z"),
            lambda x: x["workflow_run"].update(head_sha="d" * 40),
            lambda x: x["workflow_run"].update(repository_id=101),
            lambda x: x["workflow_run"].update(head_repository_id=100),
        ):
            record, artifact = self.run_record(), self.artifact()
            record["status"] = "queued"
            mutate(artifact)
            with self.assertRaises(policy.NotAdmitted):
                self.check([self.response(record), self.listing([artifact])])
            self.assertEqual(len(self.opened), 2)
            self.assertEqual(self.paused, [])

    def test_wrong_id_name_run_head_attempt_expiry_size_or_digest_rejected(self):
        mutations = [
            lambda x: x.update(id=ARTIFACT + 1), lambda x: x.update(name=NAME),
            lambda x: x.update(expired=True), lambda x: x.update(size_in_bytes=0),
            lambda x: x.update(size_in_bytes=1048577), lambda x: x.update(digest="sha256:bad"),
            lambda x: x.update(created_at="2026-10-22T05:59:59Z"),
            lambda x: x["workflow_run"].update(id=RUN - 1),
            lambda x: x["workflow_run"].update(head_sha="d" * 40),
            lambda x: x["workflow_run"].update(repository_id=101),
            lambda x: x["workflow_run"].update(head_repository_id=100),
        ]
        for mutate in mutations:
            value = self.artifact(); mutate(value)
            with self.subTest(value=value), self.assertRaises(policy.NotAdmitted):
                self.check([self.response(self.run_record()), self.listing([value])])

    def test_full_100_row_page_above_64k_has_a_separate_bounded_cap(self):
        rows = [{"id": i + 1, "name": "other-" + str(i), "padding": "x" * 750}
                for i in range(99)] + [self.artifact()]
        response = self.listing(rows)
        self.assertGreater(len(response.data), 65536)
        self.assertLess(len(response.data), policy.A1_LIST_RESPONSE_CAP)
        self.assertEqual(self.check([self.response(self.run_record()), response]), (2, DIGEST))
        for raw in (b"x" * (policy.A1_LIST_RESPONSE_CAP + 1),
                    b'{"total_count":0,"total_count":0,"artifacts":[]}'):
            with self.assertRaises(policy.NotAdmitted):
                self.check([self.response(self.run_record()), self.response(page=1, raw=raw)])
        with self.assertRaises(policy.NotAdmitted):
            self.check([self.response(raw=b"x" * 65537)])

    def test_pagination_requires_every_page_and_unique_name_and_id(self):
        first = [{"id": i + 1, "name": "other-" + str(i)} for i in range(100)]
        replies = [self.response(self.run_record()), self.listing(first, total=101),
                   self.listing([self.artifact()], total=101, page=2)]
        self.assertEqual(self.check(replies), (3, DIGEST))
        self.assertEqual(self.opened[-1], (self.LIST_URL + "2", 10))
        first[0] = self.artifact()
        conflicting = self.artifact(); conflicting["id"] += 1
        for last in ([conflicting], [self.artifact()], []):
            with self.assertRaises(policy.NotAdmitted):
                self.check([self.response(self.run_record()), self.listing(first, total=101),
                            self.listing(last, total=101, page=2)], attempts=3)

    def test_pagination_never_resets_eight_request_budget(self):
        replies = [self.response(self.run_record())]
        for page in range(1, 8):
            rows = [{"id": 100 * page + i, "name": f"other-{page}-{i}"} for i in range(100)]
            replies.append(self.listing(rows, total=800, page=page))
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_VISIBLE"):
            self.check(replies)
        self.assertEqual(len(self.opened), 8)
        self.assertEqual(self.paused, [])

    def test_bad_list_shape_bounds_and_duplicate_ids_fail_closed(self):
        for payload in ({"total_count": True, "artifacts": []},
                        {"total_count": 1001, "artifacts": []},
                        {"total_count": 1, "artifacts": []},
                        {"total_count": 2, "artifacts": [self.artifact()] * 2}):
            with self.subTest(payload=payload), self.assertRaises(policy.NotAdmitted):
                self.check([self.response(self.run_record()), self.response(payload, page=1)], attempts=2)

    def test_hard_http_network_and_redirect_fail_without_retry(self):
        for error in (http_error(401), http_error(403), http_error(429),
                      urllib.error.URLError("synthetic TLS failure"), TimeoutError()):
            with self.subTest(error=error), self.assertRaises(policy.NotAdmitted):
                self.check([error])
            self.assertEqual(len(self.opened), 1)
            self.assertEqual(self.paused, [])
        with self.assertRaisesRegex(policy.NotAdmitted, "REDIRECT"):
            self.check([self.response(self.run_record(), url="https://example.invalid/")])

    def test_a1_default_client_blocks_redirect_before_sending_credentials(self):
        client = Mock()
        client.open.side_effect = [self.response(self.run_record()), self.listing()]
        with patch.object(policy.urllib.request, "build_opener", return_value=client) as build:
            result = policy.check_visibility(REPO, RUN, ARTIFACT, self.NAME,
                "fake-test-only-token", run_attempt=2, run_head_sha=self.HEAD,
                execution_source=self.SOURCE, pause=Mock())
        self.assertEqual(result, (2, DIGEST))
        handler = build.call_args.args[0]
        self.assertIsNone(handler.redirect_request(None, None, 302, None, None,
                                                   "https://example.invalid/"))

    def test_identity_flags_and_budget_cannot_expand_stage_scope(self):
        for changed in ({"run_attempt": None}, {"execution_source": None},
                        {"run_head_sha": "bad"}, {"attempts": 9}, {"delay_seconds": 3}):
            with self.subTest(changed=changed), self.assertRaises(policy.NotAdmitted):
                self.check([], **changed)
            self.assertEqual(self.opened, [])
        with self.assertRaisesRegex(policy.NotAdmitted, "OTHER_STAGE"):
            policy.check_visibility(REPO, RUN, ARTIFACT, NAME, "fake-test-only-token",
                run_attempt=2, opener=Mock(side_effect=AssertionError("network")))

    def test_a1_workflow_keeps_pinned_download_and_scientific_readback(self):
        quality = (Path(__file__).resolve().parents[3] /
                   ".github/workflows/quality.yml").read_text("utf-8")
        stage = quality.split("  frontend-s3-t3s2b1ba1:\n", 1)[1].split(
            "\n  frontend-s3-t3s2b1ba2:", 1)[0]
        markers = ["id: fe09_t3s2b1ba1\n", "id: fe09_a1_upload\n",
                   "Witness exact A1 upload in the pinned downloader REST list",
                   '--run-attempt "$GITHUB_RUN_ATTEMPT" --run-head-sha "$RUN_HEAD_SHA"',
                   "uses: actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131",
                   "artifact-ids: ${{ steps.fe09_a1_upload.outputs.artifact-id }}",
                   "github-token: ${{ github.token }}", "repository: ${{ github.repository }}",
                   "run-id: ${{ github.run_id }}", "--verify --output fe09-t3s2b1ba1-readback",
                   "--negative-readback --output fe09-t3s2b1ba1-readback",
                   "FE09_A1_SAME_RUN_ORIGINAL_MEMBERS_INDEPENDENT_READBACK_PASS"]
        offsets = [stage.index(marker) for marker in markers]
        self.assertEqual(offsets, sorted(offsets))
        for required in ("timeout-minutes: 30", "retention-days: 30", "if-no-files-found: error",
                         "--collect --output fe09-t3s2b1ba1", 'receipt["repetitions_per_target"]==2'):
            self.assertIn(required, stage)
        self.assertNotIn("continue-on-error:", stage)


class T3S1RestListVisibilityTests(A1RestListVisibilityTests):
    """Replay the same bounded identity/refusal controls for the one new stage.

    Inherited metadata fixtures are synthetic and never qualify science.
    The original A1/B1 test classes and the shared REST implementation stay intact.
    """
    NAME = "frontend-fe09-t3s1-compact-handoff-12345"

    def test_a1_workflow_keeps_pinned_download_and_scientific_readback(self):
        super().test_a1_workflow_keeps_pinned_download_and_scientific_readback()
        quality = (Path(__file__).resolve().parents[3] /
                   ".github/workflows/quality.yml").read_text("utf-8")
        stage = quality.split("  frontend-s3-t3s1:\n", 1)[1].split(
            "\n  frontend-s3-t3s2a:", 1)[0]
        markers = ["id: fe09_t3s1\n", "id: fe09_t3s1_upload\n",
                   'name: frontend-fe09-t3s1-compact-handoff-${{ github.run_id }}-attempt-${{ github.run_attempt }}',
                   "Witness exact T3-S1 upload in the pinned downloader REST list",
                   'ARTIFACT_ID: ${{ steps.fe09_t3s1_upload.outputs.artifact-id }}',
                   'RUN_HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}',
                   '--artifact-name "frontend-fe09-t3s1-compact-handoff-$GITHUB_RUN_ID-attempt-$GITHUB_RUN_ATTEMPT"',
                   '--run-attempt "$GITHUB_RUN_ATTEMPT" --run-head-sha "$RUN_HEAD_SHA"',
                   '--execution-source "$GITHUB_SHA"',
                   "uses: actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131",
                   "artifact-ids: ${{ steps.fe09_t3s1_upload.outputs.artifact-id }}",
                   "github-token: ${{ github.token }}", "repository: ${{ github.repository }}",
                   "run-id: ${{ github.run_id }}", "--verify --output fe09-t3s1-readback",
                   "FE09_T3S1_EXACT_SOURCE_AND_OUTBOARD_READBACK_PASS"]
        # execution-source also appears in the unchanged collector; find each
        # marker after its predecessor so this checks the new transport order.
        cursor = 0
        for marker in markers:
            cursor = stage.index(marker, cursor) + len(marker)
        for required in ("timeout-minutes: 25", "retention-days: 30", "if-no-files-found: error",
                         "--collect --output fe09-t3s1", "--verify --output fe09-t3s1",
                         "{'SHA256SUMS', *names}", "r['device_memory_admitted'] is False"):
            self.assertIn(required, stage)
        self.assertEqual(stage.count("if: steps.fe09_t3s1.outcome == 'success'"), 3)
        self.assertNotIn('name: frontend-fe09-t3s1-compact-handoff-${{ github.run_id }}\n', stage)
        self.assertNotIn('--artifact-name "frontend-fe09-t3s1-compact-handoff-$GITHUB_RUN_ID"', stage)
        self.assertNotIn("overwrite:", stage)
        self.assertNotIn("continue-on-error:", stage)

    def test_only_exact_new_stage_name_is_admitted(self):
        for name in ("frontend-fe09-t3s0-resource-census-12345",
                     "frontend-fe09-t3s2a-12345",
                     "frontend-fe09-t3s2b1ba2-pending-12345",
                     "frontend-fe09-t3s1-compact-handoff-extra-12345",
                     "frontend-fe09-t3s1-compact-handoff-12346"):
            opener = Mock(side_effect=AssertionError("no API for invalid stage"))
            with self.subTest(name=name), self.assertRaisesRegex(policy.NotAdmitted, "UNTRUSTED_ARGS"):
                policy.check_visibility(REPO, RUN, ARTIFACT, name, "fake-test-only-token",
                    run_attempt=2, run_head_sha=self.HEAD, execution_source=self.SOURCE,
                    opener=opener, pause=Mock())
            opener.assert_not_called()

    def test_cli_source_bound_marker_is_stage_specific(self):
        for name, marker in ((A1RestListVisibilityTests.NAME, "FE09_A1_REST_LIST_RUN_ATTEMPT_SOURCE_BOUND"),
                             (self.NAME, "FE09_T3S1_REST_LIST_RUN_ATTEMPT_SOURCE_BOUND"),
                             (NAME, None), (B1S1_NAME, None)):
            args = ["visibility", "--artifact-id", str(ARTIFACT), "--run-id", str(RUN),
                    "--artifact-name", name]
            if marker is not None:
                args += ["--run-attempt", "2", "--run-head-sha", self.HEAD,
                         "--execution-source", self.SOURCE]
            output = io.StringIO()
            with self.subTest(name=name), patch("sys.argv", args), patch("sys.stdout", output), \
                 patch.dict(policy.os.environ, {"GITHUB_REPOSITORY": REPO,
                     "GH_TOKEN": "fake-test-only-token"}, clear=True), \
                 patch.object(policy, "check_visibility", return_value=(2, DIGEST)) as checked:
                policy.main()
            checked.assert_called_once_with(REPO, RUN, ARTIFACT, name, "fake-test-only-token",
                run_attempt=2 if marker is not None else None,
                run_head_sha=self.HEAD if marker is not None else None,
                execution_source=self.SOURCE if marker is not None else None)
            lines = output.getvalue().splitlines()
            self.assertIn("attempt=2", lines[0])  # HTTP request count, not the run attempt.
            self.assertEqual(len(lines), 2 if marker is not None else 1)
            if marker is not None:
                self.assertEqual(lines[1], f"{marker} 2 {self.HEAD} {self.SOURCE}")
            self.assertNotIn("fake-test-only-token", output.getvalue())
            self.assertNotIn("https://", output.getvalue())


class T3S1AttemptScopedVisibilityTests(T3S1RestListVisibilityTests):
    """Keep every legacy refusal while isolating each new T3-S1 upload attempt."""
    NAME = "frontend-fe09-t3s1-compact-handoff-12345-attempt-2"

    def previous_artifacts(self):
        rows = []
        for i, name in enumerate((T3S1RestListVisibilityTests.NAME,
                                  T3S1RestListVisibilityTests.NAME + "-attempt-1")):
            old = self.artifact()
            old.update(id=ARTIFACT + i + 1, name=name,
                       created_at="2026-10-22T05:59:59Z")
            rows.append(old)
        return rows

    def test_exact_positive_attempts_are_bound_to_the_run_endpoint(self):
        for attempt in (1, 2, 2 ** 63 - 1):
            name = T3S1RestListVisibilityTests.NAME + f"-attempt-{attempt}"
            record, artifact = self.run_record(), self.artifact()
            record["run_attempt"] = attempt
            artifact["name"] = name
            endpoint = f"https://api.github.com/repos/{REPO}/actions/runs/{RUN}/attempts/{attempt}"
            opener = Mock(side_effect=[self.response(record, url=endpoint),
                                       self.listing([artifact])])
            with self.subTest(attempt=attempt):
                self.assertEqual(policy.check_visibility(REPO, RUN, ARTIFACT, name,
                    "fake-test-only-token", run_attempt=attempt, run_head_sha=self.HEAD,
                    execution_source=self.SOURCE, opener=opener, pause=Mock()), (2, DIGEST))
            self.assertEqual(opener.call_count, 2)
            self.assertEqual(opener.call_args_list[0].args[0].full_url, endpoint)

    def test_previous_attempt_names_coexist_without_replacing_evidence(self):
        old = self.previous_artifacts()
        for rows in (old + [self.artifact()], [self.artifact()] + old):
            with self.subTest(rows=rows):
                self.assertEqual(self.check([self.response(self.run_record()),
                                            self.listing(rows)]), (2, DIGEST))
                self.assertEqual(len(self.opened), 2)
                self.assertEqual(self.paused, [])

    def test_previous_attempt_name_can_coexist_on_another_page(self):
        first = self.previous_artifacts() + [
            {"id": i + 1, "name": f"other-{i}"} for i in range(98)]
        self.assertEqual(self.check([self.response(self.run_record()),
            self.listing(first, total=101),
            self.listing([self.artifact()], total=101, page=2)]), (3, DIGEST))
        self.assertEqual(self.opened[-1], (self.LIST_URL + "2", 10))
        self.assertEqual(self.paused, [])

    def test_same_attempt_duplicate_name_still_rejected_even_if_old(self):
        for created_at in ("2026-10-22T05:59:59Z", "2026-10-22T06:01:00Z"):
            other = self.artifact()
            other.update(id=ARTIFACT + 3, created_at=created_at)
            with self.subTest(created_at=created_at), self.assertRaisesRegex(
                    policy.NotAdmitted, "A1_ARTIFACT_NAME_OR_ID_NOT_UNIQUE"):
                self.check([self.response(self.run_record()),
                            self.listing([self.artifact(), other])])
            self.assertEqual(len(self.opened), 2)
            self.assertEqual(self.paused, [])

    def test_previous_id_cannot_be_substituted_for_current_upload(self):
        # The current expected name with another ID must fail, not be selected.
        current = self.artifact()
        current["id"] += 3
        with self.assertRaisesRegex(policy.NotAdmitted, "WRONG_RUN_NAME_ID"):
            self.check([self.response(self.run_record()), self.listing([current])])
        self.assertEqual(len(self.opened), 2)
        self.assertEqual(self.paused, [])

    def test_expected_id_cannot_carry_a_legacy_or_other_attempt_name(self):
        for name in (T3S1RestListVisibilityTests.NAME,
                     T3S1RestListVisibilityTests.NAME + "-attempt-1",
                     T3S1RestListVisibilityTests.NAME + "-attempt-3",
                     A1RestListVisibilityTests.NAME + "-attempt-2"):
            wrong = self.artifact()
            wrong["name"] = name
            with self.subTest(name=name), self.assertRaisesRegex(
                    policy.NotAdmitted, "WRONG_RUN_NAME_ID"):
                self.check([self.response(self.run_record()), self.listing([wrong])])
            self.assertEqual(len(self.opened), 2)
            self.assertEqual(self.paused, [])

    def test_attempt_suffix_is_exact_and_exclusive_to_t3s1(self):
        names = (
            T3S1RestListVisibilityTests.NAME + "-attempt-1",
            T3S1RestListVisibilityTests.NAME + "-attempt-3",
            T3S1RestListVisibilityTests.NAME + "-attempt-02",
            T3S1RestListVisibilityTests.NAME + "-attempt-2-extra",
            T3S1RestListVisibilityTests.NAME + "-2",
            "frontend-fe09-t3s1-compact-handoff-12346-attempt-2",
            "frontend-fe09-t3s1-compact-handoff-extra-12345-attempt-2",
            "frontend-fe09-t3s1-compact-handoff-012345-attempt-2",
            NAME + "-attempt-2", B1S1_NAME + "-attempt-2",
            A1RestListVisibilityTests.NAME + "-attempt-2",
        )
        for name in names:
            opener = Mock(side_effect=AssertionError("no API for invalid name"))
            with self.subTest(name=name), self.assertRaisesRegex(
                    policy.NotAdmitted, "UNTRUSTED_ARGS"):
                policy.check_visibility(REPO, RUN, ARTIFACT, name, "fake-test-only-token",
                    run_attempt=2, run_head_sha=self.HEAD, execution_source=self.SOURCE,
                    opener=opener, pause=Mock())
            opener.assert_not_called()
        for attempt in (None, True, "2", 0, -1, 1, 3, 2 ** 63):
            with self.subTest(attempt=attempt), self.assertRaisesRegex(
                    policy.NotAdmitted, "UNTRUSTED_ARGS"):
                self.check([], run_attempt=attempt)
            self.assertEqual(self.opened, [])


class T2AAttemptVisibilityTests(A1RestListVisibilityTests):
    """Run all existing REST identity/refusal tests for the observed T2A failure."""
    NAME = "frontend-fe09-s3-t2a-controlled-restart-12345-attempt-2"
    STAGE = "t2a"
    PREFIX = "frontend-fe09-s3-t2a-controlled-restart-"
    TIMEOUT = 18
    MARKER = "FE09_S3_T2A_CONTROL_RESTART_READBACK_PASS"

    def test_attempt_names_and_prior_artifacts(self):
        old = self.artifact()
        old.update(id=ARTIFACT + 1, name=self.PREFIX + str(RUN),
                   created_at="2026-10-22T05:59:59Z")
        prior = copy.deepcopy(old)
        prior.update(id=ARTIFACT + 2, name=old["name"] + "-attempt-1")
        self.assertEqual(self.check([self.response(self.run_record()),
            self.listing([old, prior, self.artifact()])]), (2, DIGEST))
        duplicate = self.artifact()
        duplicate["id"] += 3
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_UNIQUE"):
            self.check([self.response(self.run_record()),
                        self.listing([duplicate, self.artifact()])])
        for suffix in ("", "-attempt-1", "-attempt-3", "-attempt-02",
                       "-attempt-2-extra"):
            name = self.PREFIX + str(RUN) + suffix
            opener = Mock(side_effect=AssertionError("invalid name must not use API"))
            with self.subTest(name=name), self.assertRaises(policy.NotAdmitted):
                policy.check_visibility(REPO, RUN, ARTIFACT, name, "fake-token",
                    run_attempt=2, run_head_sha=self.HEAD, execution_source=self.SOURCE,
                    opener=opener)
            opener.assert_not_called()
        for attempt in (None, True, "2", 0, -1, 1, 3, 2 ** 63):
            with self.subTest(attempt=attempt), self.assertRaises(policy.NotAdmitted):
                self.check([], run_attempt=attempt)
            self.assertEqual(self.opened, [])

    def test_observed_stage_keeps_original_readback(self):
        quality = (Path(__file__).resolve().parents[3] /
                   ".github/workflows/quality.yml").read_text("utf-8")
        stage = quality.split("  frontend-s3-" + self.STAGE + ":\n", 1)[1].split(
            "\n  frontend-", 1)[0]
        upload = "fe09_" + self.STAGE + "_upload"
        markers = ["id: fe09_" + self.STAGE + "\n", "id: " + upload + "\n",
                   "name: " + self.PREFIX + "${{ github.run_id }}-attempt-${{ github.run_attempt }}",
                   "Witness exact " + self.STAGE + " upload",
                   "ARTIFACT_ID: ${{ steps." + upload + ".outputs.artifact-id }}",
                   'RUN_HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}',
                   '--artifact-name "' + self.PREFIX + '$GITHUB_RUN_ID-attempt-$GITHUB_RUN_ATTEMPT"',
                   '--run-attempt "$GITHUB_RUN_ATTEMPT" --run-head-sha "$RUN_HEAD_SHA"',
                   '--execution-source "$GITHUB_SHA"',
                   "uses: actions/download-artifact@37930b1c2abaa49bbe596cd826c3c89aef350131",
                   "artifact-ids: ${{ steps." + upload + ".outputs.artifact-id }}",
                   "github-token: ${{ github.token }}", "repository: ${{ github.repository }}",
                   "run-id: ${{ github.run_id }}",
                   "--verify --output fe09-" + self.STAGE + "-readback", self.MARKER]
        cursor = 0
        for marker in markers:
            cursor = stage.index(marker, cursor) + len(marker)
        for required in ("timeout-minutes: " + str(self.TIMEOUT), "retention-days: 30",
                         "if-no-files-found: error", "--collect --output fe09-" + self.STAGE):
            self.assertIn(required, stage)
        self.assertEqual(stage.count("if: steps.fe09_" + self.STAGE + ".outcome == 'success'"), 3)
        self.assertNotIn("overwrite:", stage)
        self.assertNotIn("continue-on-error:", stage)


class RootAttemptVisibilityTests(T2AAttemptVisibilityTests):
    """The same full matrix independently exercises immutable-root transport."""
    NAME = "frontend-fe09-t3s2b1a-immutable-root-12345-attempt-2"
    STAGE = "t3s2b1a"
    PREFIX = "frontend-fe09-t3s2b1a-immutable-root-"
    TIMEOUT = 30
    MARKER = "FE09_T3S2B1A_SOURCE_IMMUTABLE_POSIX_READBACK_PASS"



class A1SnapshotRestartTests(unittest.TestCase):
    """Synthetic transport only: a restarted snapshot is never merged with old rows."""
    NAME = A1RestListVisibilityTests.NAME
    HEAD = A1RestListVisibilityTests.HEAD
    SOURCE = A1RestListVisibilityTests.SOURCE
    ATTEMPT = A1RestListVisibilityTests.ATTEMPT
    RUN_URL = A1RestListVisibilityTests.RUN_URL
    LIST_URL = A1RestListVisibilityTests.LIST_URL
    run_record = A1RestListVisibilityTests.run_record
    artifact = A1RestListVisibilityTests.artifact
    response = A1RestListVisibilityTests.response
    listing = A1RestListVisibilityTests.listing
    check = A1RestListVisibilityTests.check

    def test_partial_matching_row_is_not_success_until_complete_snapshot(self):
        got = self.check([self.response(self.run_record()),
                          self.listing(total=2), self.listing()])
        self.assertEqual(got, (3, DIGEST))
        self.assertEqual(self.opened, [(self.RUN_URL, 10),
            (self.LIST_URL + "1", 10), (self.LIST_URL + "1", 10)])
        self.assertEqual(self.paused, [2])

    def test_changed_total_restarts_page_one_and_discards_old_rows(self):
        first = [{"id": i + 1, "name": f"other-{i}"} for i in range(100)]
        first[0] = self.artifact()
        got = self.check([self.response(self.run_record()),
            self.listing(first, total=101), self.listing([], total=100, page=2),
            self.listing()])
        self.assertEqual(got, (4, DIGEST))
        self.assertEqual([url[-1] for url, _ in self.opened[1:]], ["1", "2", "1"])
        self.assertEqual(self.paused, [2])

    def test_stale_match_cannot_survive_restart(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "NOT_VISIBLE"):
            self.check([self.response(self.run_record()), self.listing(total=2),
                        self.listing([])], attempts=3)
        self.assertEqual(len(self.opened), 3)
        self.assertEqual(self.paused, [2])

    def test_incomplete_exhaustion_uses_existing_total_request_budget(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "LIST_INCOMPLETE_OR_CHANGED"):
            self.check([self.response(self.run_record())] + [self.listing(total=2)] * 7)
        self.assertEqual(len(self.opened), 8)
        self.assertEqual(self.paused, [2] * 6)

    def test_http_and_snapshot_retries_share_budget(self):
        with self.assertRaisesRegex(policy.NotAdmitted, "LIST_INCOMPLETE_OR_CHANGED"):
            self.check([http_error(503), self.response(self.run_record()),
                        self.listing(total=2)], attempts=3)
        self.assertEqual(len(self.opened), 3)
        self.assertEqual(self.paused, [2])

    def test_incomplete_snapshot_does_not_retry_observed_identity_conflict(self):
        for mutate in (lambda a: a.update(id=ARTIFACT + 1),
                       lambda a: a.update(name="wrong"),
                       lambda a: a.update(expired=True),
                       lambda a: a.update(digest="bad"),
                       lambda a: a.update(created_at="2026-10-22T05:59:59Z"),
                       lambda a: a["workflow_run"].update(head_sha="d" * 40)):
            artifact = self.artifact(); mutate(artifact)
            with self.assertRaises(policy.NotAdmitted):
                self.check([self.response(self.run_record()),
                            self.listing([artifact], total=2), self.listing()])
            self.assertEqual(len(self.opened), 2)
            self.assertEqual(self.paused, [])

    def test_incomplete_snapshot_does_not_retry_duplicates_or_invalid_rows(self):
        for rows in ([self.artifact()] * 2, [{"id": True, "name": "bad"}],
                     [None], [self.artifact(), dict(self.artifact(), id=ARTIFACT+1)]):
            with self.assertRaises(policy.NotAdmitted):
                self.check([self.response(self.run_record()),
                            self.listing(rows, total=3), self.listing()])
            self.assertEqual(len(self.opened), 2)
            self.assertEqual(self.paused, [])

    def test_other_rest_stages_remain_immediate_refusal(self):
        for name in (policy.T3S1_PREFIX + str(RUN),
                     *(f"{prefix}{RUN}-attempt-2" for prefix in policy.ATTEMPT_PREFIXES)):
            self.NAME = name
            with self.assertRaisesRegex(policy.NotAdmitted, "LIST_INCOMPLETE_OR_CHANGED"):
                self.check([self.response(self.run_record()), self.listing(total=2), self.listing()])
            self.assertEqual(len(self.opened), 2)
            self.assertEqual(self.paused, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
