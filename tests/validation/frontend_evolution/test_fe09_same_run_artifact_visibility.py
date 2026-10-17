#!/usr/bin/env python3
"""Offline deterministic exact-run artifact availability/negative-policy tests."""
from __future__ import annotations
import io
import json
import unittest
import urllib.error
from unittest.mock import Mock
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



if __name__ == "__main__":
    unittest.main(verbosity=2)
