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
                "status": "in_progress", "run_started_at": "2026-10-22T06:00:00Z",
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
                            self.listing(last, total=101, page=2)])

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
                self.check([self.response(self.run_record()), self.response(payload, page=1)])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
