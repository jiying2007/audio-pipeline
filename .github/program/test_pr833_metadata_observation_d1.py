#!/usr/bin/env python3
"""Offline controls for the PR833 observer; no live provider or DSP execution."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import unittest
from unittest import mock
import urllib.error

SPEC = importlib.util.spec_from_file_location(
    "pr833_observer", Path(__file__).with_name("pr833_metadata_observation_d1.py"))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
SENTINEL = "DO_NOT_LOG_PRIVATE_SENTINEL"


def fixture():
    repo = {"full_name": M.REPO, "id": M.REPO_ID}
    return {"number": 833, "state": "open", "merged": False, "draft": False,
            "user": {"login": "jiying2007", "id": 33591504, "type": "User"},
            "base": {"sha": "a" * 40, "ref": "main", "repo": repo},
            "head": {"sha": "b" * 40, "ref": M.HEAD_REF, "repo": repo},
            "merge_commit_sha": "c" * 40, "mergeable": None, "body": SENTINEL}


def wanted():
    return M.expected_identity("a" * 40, "b" * 40, "c" * 40)


def source():
    return {"commit": "1" * 40, "tree": "2" * 40, "observer_sha256": "3" * 64,
            "legacy_sha256": M.LEGACY_SHA256}


class ObservationTests(unittest.TestCase):
    def request(self, *, data=None, raw=None, error=None, status=200, headers=None,
                url=M.URL, read_error=None, output=None, source_check=source):
        payload = raw if raw is not None else json.dumps(fixture() if data is None else data).encode()
        calls, reads, closed = [], [], []

        class Response:
            def __init__(self):
                self.status, self.url, self.headers = status, url, headers or {}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                closed.append(True)
            def read(self, size):
                reads.append(size)
                if read_error is not None:
                    raise read_error
                return payload[:size]

        def opening(req, timeout):
            calls.append(req)
            self.assertEqual(req.full_url, M.URL)
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(timeout, M.TIMEOUT)
            self.assertFalse(any(k.lower() == "authorization" for k in req.headers))
            if error is not None:
                raise error
            return Response()

        if output is None:
            report, saved = M.observe(wanted(), opening)
        else:
            report = M.capture(wanted(), output, opener=opening, source_check=source_check)
            saved = (output / "response.body").read_bytes()
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(n == M.MAX_BYTES + 1 for n in reads))
        self.assertEqual(report["request"]["attempts"], 1)
        self.assertEqual(report["request"]["redirects_allowed"], 0)
        self.assertTrue(report["observation_only"])
        for key in M.DENIALS:
            self.assertIs(report[key], False)
        self.assertNotIn(SENTINEL, json.dumps(report))
        self.assertEqual(report["body_bytes"], len(saved))
        self.assertEqual(report["body_sha256"], hashlib.sha256(saved).hexdigest())
        if error is None:
            self.assertEqual(closed, [True])
        return report, saved

    def test_valid_observation_retains_exact_noncanonical_json_bytes(self):
        raw = b' \n ' + json.dumps(fixture(), indent=2).encode() + b'\n\t'
        report, saved = self.request(raw=raw)
        self.assertEqual(report["outcome"], "OBSERVED_MATCH")
        self.assertEqual(saved, raw)
        self.assertTrue(report["body_complete"])

    def test_missing_and_explicit_null_are_distinct_and_unavailable(self):
        for kind in ("MISSING", "NULL"):
            data = fixture()
            if kind == "MISSING":
                del data["merge_commit_sha"]
            else:
                data["merge_commit_sha"] = None
            report, _ = self.request(data=data)
            self.assertEqual(report["outcome"], "MERGE_IDENTITY_UNAVAILABLE")
            self.assertEqual(report["observed_identity"]["merge_field_kind"], kind)
            self.assertIsNone(report["observed_identity"]["merge_sha"])

    def test_invalid_merge_types_are_visible_not_accepted(self):
        for value in (True, False, 7, [], {}, 1.25):
            with self.subTest(value=value):
                report, _ = self.request(data={**fixture(), "merge_commit_sha": value})
                self.assertEqual(report["outcome"], "MERGE_IDENTITY_INVALID")
                self.assertEqual(report["observed_identity"]["merge_field_kind"], "WRONG_TYPE")

    def test_zero_malformed_and_untrusted_strings_are_not_leaked(self):
        for value, kind in (("0" * 40, "ZERO_OID"), (SENTINEL, "INVALID_STRING"),
                            ("A" * 40, "INVALID_STRING"), ("a" * 39, "INVALID_STRING"),
                            ("c" * 40 + "\n", "INVALID_STRING")):
            report, _ = self.request(data={**fixture(), "merge_commit_sha": value})
            self.assertEqual(report["outcome"], "MERGE_IDENTITY_INVALID")
            self.assertEqual(report["observed_identity"]["merge_field_kind"], kind)

    def test_base_head_and_merge_mismatch(self):
        for field in M.FIELDS:
            data = fixture()
            if field == "merge_sha":
                data["merge_commit_sha"] = "d" * 40
            else:
                data[field.split("_")[0]]["sha"] = "d" * 40
            report, _ = self.request(data=data)
            self.assertEqual(report["outcome"], "IDENTITY_MISMATCH")

    def test_open_unmerged_nondraft_required(self):
        for field, value in (("state", "closed"), ("merged", True), ("draft", True),
                             ("merged", None), ("draft", None)):
            report, _ = self.request(data={**fixture(), field: value})
            self.assertEqual(report["outcome"], "PR_STATE_MISMATCH")

    def test_repository_author_and_branch_identity(self):
        changes = (("number", 714), ("number", True), ("user.id", True),
                   ("user.id", 2), ("user.login", "someone"), ("user.type", "Bot"),
                   ("head.ref", "other"), ("base.ref", "other"),
                   ("head.repo.id", 2), ("base.repo.full_name", "other/repository"),
                   ("head.sha", "0" * 40), ("base.sha", SENTINEL))
        for path, value in changes:
            data = copy.deepcopy(fixture())
            parent = data
            parts = path.split(".")
            for part in parts[:-1]:
                parent = parent[part]
            parent[parts[-1]] = value
            report, _ = self.request(data=data)
            self.assertEqual(report["outcome"], "METADATA_INVALID", path)

    def test_mergeable_types_are_separate_observations(self):
        for value, kind in ((None, "NULL"), (True, "TRUE"), (False, "FALSE"),
                            (SENTINEL, "WRONG_TYPE")):
            report, _ = self.request(data={**fixture(), "mergeable": value})
            self.assertEqual(report["observed_identity"]["mergeable_kind"], kind)
        data = fixture()
        del data["mergeable"]
        report, _ = self.request(data=data)
        self.assertEqual(report["observed_identity"]["mergeable_kind"], "MISSING")

    def test_invalid_json_raw_bytes_are_preserved(self):
        for raw in (b"", b"\xff", b"[]", b"null", b"true", b'{"number":833,"number":833}',
                    b'{"number":833,"bad":NaN}', b'{"number":833,"bad":Infinity}',
                    b'[' * 1100 + b']' * 1100, b'<html>error</html>'):
            report, saved = self.request(raw=raw)
            self.assertEqual(report["outcome"], "METADATA_INVALID")
            self.assertEqual(raw, saved)

    def test_exponent_overflow_is_rejected_and_raw_bytes_retained(self):
        prefix = json.dumps(fixture()).encode()[:-1]
        for number in (b"1e999", b"-1e999", b"1e309", b"-1.8e308"):
            for suffix in (number, b'{"nested":[' + number + b']}'):
                raw = prefix + b',"unexpected":' + suffix + b'}'
                report, saved = self.request(raw=raw)
                self.assertEqual(report["outcome"], "METADATA_INVALID")
                self.assertEqual(saved, raw)
        for number in (b"1.7e308", b"-1.7e308", b"1e-300", b"0.125"):
            raw = prefix + b',"unexpected":' + number + b'}'
            report, saved = self.request(raw=raw)
            self.assertEqual(report["outcome"], "OBSERVED_MATCH")
            self.assertEqual(saved, raw)

    def test_exact_byte_cap_is_accepted(self):
        raw = json.dumps(fixture()).encode()
        raw += b" " * (M.MAX_BYTES - len(raw))
        report, saved = self.request(raw=raw)
        self.assertEqual(report["outcome"], "OBSERVED_MATCH")
        self.assertEqual(len(saved), M.MAX_BYTES)

    def test_oversize_keeps_only_bounded_prefix_and_is_incomplete(self):
        report, saved = self.request(raw=b"x" * (M.MAX_BYTES + 20))
        self.assertEqual(report["outcome"], "BODY_TOO_LARGE")
        self.assertEqual(len(saved), M.MAX_BYTES + 1)
        self.assertFalse(report["body_complete"])

    def test_short_content_length_response_is_incomplete(self):
        raw = json.dumps(fixture()).encode()
        report, saved = self.request(raw=raw, headers={"Content-Length": str(len(raw) + 1)})
        self.assertEqual(report["outcome"], "PARTIAL_BODY")
        self.assertFalse(report["body_complete"])
        self.assertEqual(saved, raw)

    def test_incomplete_read_retains_partial_bytes(self):
        raw = b'{"partial":'
        report, saved = self.request(read_error=http.client.IncompleteRead(raw, 100))
        self.assertEqual(report["outcome"], "PARTIAL_BODY")
        self.assertFalse(report["body_complete"])
        self.assertEqual(saved, raw)

    def test_http_errors_preserve_body_but_never_log_it(self):
        for code in (302, 403, 404, 429, 500):
            body = SENTINEL.encode()
            error = urllib.error.HTTPError(M.URL, code, SENTINEL,
                                           {"Location": SENTINEL}, io.BytesIO(body))
            report, raw = self.request(error=error)
            self.assertEqual(report["outcome"], "HTTP_ERROR")
            self.assertEqual(report["http_status"], code)
            self.assertEqual(raw, body)

    def test_response_url_change_is_refused(self):
        report, saved = self.request(url="https://example.invalid/" + SENTINEL)
        self.assertEqual(report["outcome"], "TRANSPORT_INVALID")
        self.assertEqual(saved, b"")
        self.assertFalse(report["body_complete"])

    def test_invalid_status_is_refused(self):
        for status in (True, "200", 99, 600):
            report, _ = self.request(status=status)
            self.assertEqual(report["outcome"], "TRANSPORT_INVALID")

    def test_network_error_types_no_retry(self):
        for error, outcome in ((TimeoutError(SENTINEL), "TIMEOUT"),
            (ssl.SSLError(SENTINEL), "TLS_ERROR"),
            (socket.gaierror(SENTINEL), "DNS_ERROR"),
            (urllib.error.URLError(TimeoutError(SENTINEL)), "TIMEOUT"),
            (urllib.error.URLError(ssl.SSLError(SENTINEL)), "TLS_ERROR"),
            (urllib.error.URLError(socket.gaierror(SENTINEL)), "DNS_ERROR"),
            (urllib.error.URLError(OSError(SENTINEL)), "NETWORK_ERROR"),
            (OSError(SENTINEL), "NETWORK_ERROR"),
            (http.client.RemoteDisconnected(SENTINEL), "NETWORK_ERROR")):
            report, raw = self.request(error=error)
            self.assertEqual(report["outcome"], outcome)
            self.assertFalse(report["body_complete"])
            self.assertFalse(report["body_received"])
            self.assertEqual(raw, b"")

    def test_read_timeout_no_false_complete_body(self):
        report, raw = self.request(read_error=TimeoutError(SENTINEL))
        self.assertEqual(report["outcome"], "TIMEOUT")
        self.assertFalse(report["body_complete"])
        self.assertEqual(raw, b"")

    def test_only_safe_headers_are_serialized(self):
        headers = {"Authorization": SENTINEL, "Set-Cookie": SENTINEL,
                   "X-GitHub-Request-Id": SENTINEL, "Retry-After": "1\n" + SENTINEL,
                   "Content-Length": "-1", "X-RateLimit-Remaining": "99999999999"}
        report, _ = self.request(headers=headers)
        self.assertTrue(all(v is None for v in report["headers"].values()))
        self.assertEqual(M.safe_headers({"X-RateLimit-Remaining": "0", "Retry-After": "20",
                                        "Content-Length": "123", "X-GitHub-Request-Id": "ABCD:1234"}),
                         {"rate_limit_remaining": 0, "retry_after_seconds": 20,
                          "content_length": 123, "github_request_id": "ABCD:1234"})

    def test_redirect_handler_does_not_redirect(self):
        self.assertIsNone(M.NoRedirect().redirect_request(None, None, 302, "", {}, SENTINEL))

    def test_invalid_expected_context_makes_no_request(self):
        opener = mock.Mock(side_effect=AssertionError("unexpected network"))
        for value in ("0" * 40, "a" * 39, True, None, "A" * 40):
            with self.assertRaises(ValueError):
                M.observe({**wanted(), "base_sha": value}, opener)
        for context in ({}, [], {**wanted(), "extra": "x"}):
            with self.assertRaises(ValueError):
                M.observe(context, opener)
        opener.assert_not_called()

    def test_four_files_are_exactly_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence"
            report, raw = self.request(output=path)
            self.assertEqual(set(p.name for p in path.iterdir()), set(M.FILES))
            self.assertEqual(json.loads((path / "receipt.json").read_text()), report)
            for name in ("response.body", "receipt.json"):
                content = (path / name).read_bytes()
                self.assertEqual((path / (name + ".sha256")).read_text(),
                                 hashlib.sha256(content).hexdigest() + "  " + name + "\n")
            self.assertIn(SENTINEL.encode(), raw)
            self.assertTrue(report["source_unchanged_after_observation"])

    def test_existing_directory_and_symlink_spend_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "existing"
            path.mkdir()
            keep = path / "keep"
            keep.write_bytes(b"original")
            link = Path(tmp) / "alias"
            link.symlink_to(path, target_is_directory=True)
            for target in (path, link):
                opener = mock.Mock(side_effect=AssertionError("unexpected network"))
                with self.assertRaises(FileExistsError):
                    M.capture(wanted(), target, opener=opener, source_check=source)
                opener.assert_not_called()
                self.assertEqual(keep.read_bytes(), b"original")

    def test_missing_parent_and_bad_source_spend_no_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            opener = mock.Mock(side_effect=AssertionError("unexpected network"))
            with self.assertRaises(FileNotFoundError):
                M.capture(wanted(), Path(tmp) / "missing" / "out", opener=opener, source_check=source)
            with self.assertRaises(ValueError):
                M.capture(wanted(), Path(tmp) / "out", opener=opener,
                          source_check=mock.Mock(side_effect=ValueError(SENTINEL)))
            opener.assert_not_called()

    def test_source_change_after_request_is_retained_and_nonaccepting(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = mock.Mock(side_effect=[source(), {**source(), "tree": "4" * 40}])
            report, _ = self.request(output=Path(tmp) / "out", source_check=check)
            self.assertEqual(report["outcome"], "SOURCE_CHANGED_DURING_OBSERVATION")
            self.assertFalse(report["source_unchanged_after_observation"])

    def test_post_source_error_is_retained_and_nonaccepting(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = mock.Mock(side_effect=[source(), ValueError(SENTINEL)])
            report, _ = self.request(output=Path(tmp) / "out", source_check=check)
            self.assertEqual(report["outcome"], "SOURCE_CHANGED_DURING_OBSERVATION")

    def test_raw_and_receipt_write_errors_cannot_return_success(self):
        for failed in ("response.body", "response.body.sha256", "receipt.json", "receipt.json.sha256"):
            with tempfile.TemporaryDirectory() as tmp:
                original_open = Path.open
                def opening(path, *args, **kwargs):
                    if path.name == failed:
                        raise OSError(SENTINEL)
                    return original_open(path, *args, **kwargs)
                with mock.patch.object(Path, "open", opening), self.assertRaises(OSError):
                    self.request(output=Path(tmp) / "out")
                if failed != "response.body":
                    self.assertTrue((Path(tmp) / "out" / "response.body").exists())

    def test_short_write_and_close_failure_cannot_return_success(self):
        for failed, kind in (("response.body", "short"), ("response.body", "close"),
                             ("receipt.json", "short"), ("receipt.json", "close")):
            with tempfile.TemporaryDirectory() as tmp:
                original_open = Path.open
                class FailedStream:
                    def __init__(self, stream):
                        self.stream = stream
                    def __enter__(self):
                        return self
                    def write(self, value):
                        if kind == "short":
                            return self.stream.write(value[:-1])
                        return self.stream.write(value)
                    def __exit__(self, *args):
                        self.stream.close()
                        if kind == "close":
                            raise OSError(SENTINEL)
                        return False
                def opening(path, *args, **kwargs):
                    stream = original_open(path, *args, **kwargs)
                    return FailedStream(stream) if path.name == failed else stream
                with mock.patch.object(Path, "open", opening), self.assertRaises((OSError, ValueError)):
                    self.request(output=Path(tmp) / "out")

    def test_invalid_capture_context_precedes_source_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            checker, opener = mock.Mock(), mock.Mock()
            with self.assertRaises(ValueError):
                M.capture({**wanted(), "extra": SENTINEL}, Path(tmp) / "out",
                          opener=opener, source_check=checker)
            checker.assert_not_called()
            opener.assert_not_called()
            self.assertFalse((Path(tmp) / "out").exists())

    def test_cli_never_logs_raw_or_exception_text(self):
        args = ["--expected-base", "a" * 40, "--expected-head", "b" * 40,
                "--expected-merge", "c" * 40, "--output", "unused"]
        for error in (OSError(SENTINEL), ValueError(SENTINEL)):
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(M, "capture", side_effect=error), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(M.main(args), 2)
            self.assertNotIn(SENTINEL, out.getvalue() + err.getvalue())
        report, _ = self.request()
        with mock.patch.object(M, "capture", return_value=report), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(M.main(args), 0)
        self.assertNotIn(SENTINEL, out.getvalue())
        report["outcome"] = "MERGE_IDENTITY_UNAVAILABLE"
        with mock.patch.object(M, "capture", return_value=report), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(M.main(args), 2)


class SourceTests(unittest.TestCase):
    def test_source_byte_comparison_rejects_mutation(self):
        legacy = b"offline fixture, not production source"
        with mock.patch.object(M, "LEGACY_SHA256", hashlib.sha256(legacy).hexdigest()):
            M.verify_source_bytes(b"self", b"self", legacy)
            for current, committed, old in ((b"", b"", legacy), (b"changed", b"self", legacy),
                                            (b"self", b"self", legacy + b"\n")):
                with self.assertRaises(ValueError):
                    M.verify_source_bytes(current, committed, old)

    def test_source_git_identity_with_real_local_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = b"local Git fixture; not the frozen production helper\n"
            for rel, data in ((M.SELF, b"# observer fixture\n"), (M.LEGACY, legacy)):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)
            git("init", "-q")
            git("config", "user.name", "offline-fixture")
            git("config", "user.email", "offline@example.invalid")
            git("add", ".")
            git("commit", "-qm", "offline fixture")
            with mock.patch.object(M, "ROOT", root), mock.patch.object(M, "LEGACY_SHA256", hashlib.sha256(legacy).hexdigest()):
                value = M.source_identity()
                self.assertEqual(value["commit"], git("rev-parse", "HEAD").decode().strip())
                self.assertEqual(value["tree"], git("rev-parse", "HEAD^{tree}").decode().strip())
                (root / M.SELF).write_text("modified\n")
                with self.assertRaises(ValueError):
                    M.source_identity()
                git("checkout", "--", M.SELF)
                (root / M.LEGACY).write_bytes(legacy + b"changed")
                with self.assertRaises(ValueError):
                    M.source_identity()

    def test_external_git_context_refused_before_git_execution(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": SENTINEL}), mock.patch.object(M.subprocess, "check_output") as run:
            with self.assertRaises(ValueError):
                M.source_identity()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
