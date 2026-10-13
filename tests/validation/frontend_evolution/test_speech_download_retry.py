#!/usr/bin/env python3
"""Deterministic, offline LibriSpeech transport retry/failure preservation tests."""
from __future__ import annotations

import http.client
from pathlib import Path
import ssl
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import speech_source as source


class FakeResponse:
    def __init__(self, body: bytes, *, url: str = source.URL,
                 status: int = 200, fail_read: BaseException | None = None):
        self.body, self.url, self.status = body, url, status
        self.fail_read = fail_read
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, count: int) -> bytes:
        assert count == 1 << 20
        self.calls += 1
        if self.fail_read is not None and self.calls == 2:
            raise self.fail_read
        if self.calls == 1:
            return self.body[:3] if self.fail_read is not None else self.body
        return b""


class TransportRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="speech-retry-unit-")
        self.file = Path(self.temp.name) / "archive.tar.gz"

    def tearDown(self):
        self.temp.cleanup()

    def test_same_url_fresh_retry_after_partial_timeout(self):
        body = b"immutable-source-bytes"
        first = FakeResponse(body, fail_read=TimeoutError("read timeout"))
        second = FakeResponse(body)
        with patch.object(source.urllib.request, "urlopen",
                          side_effect=[first, second]) as opened:
            source.download(self.file)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(self.file.read_bytes(), body)
        self.assertEqual(opened.call_args.kwargs["timeout"], 60)
        self.assertEqual(opened.call_args.args, (source.URL,))

    def test_wrapped_connection_reset_retries_once(self):
        body = b"identical-public-source"
        with patch.object(source.urllib.request, "urlopen",
                          side_effect=[urllib.error.URLError(
                              ConnectionResetError("reset")), FakeResponse(body)]) as opened:
            source.download(self.file)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(self.file.read_bytes(), body)

    def test_remote_disconnect_and_incomplete_read_are_bounded(self):
        for error in (
            http.client.IncompleteRead(b"abc", 10),
            http.client.RemoteDisconnected("connection closed"),
            ssl.SSLEOFError(8, "unexpected EOF"),
        ):
            with self.subTest(error=type(error).__name__):
                self.file.unlink(missing_ok=True)
                with patch.object(source.urllib.request, "urlopen",
                                  side_effect=[FakeResponse(b"abcd", fail_read=error),
                                               FakeResponse(b"ok")]) as opened:
                    source.download(self.file)
                self.assertEqual(opened.call_count, 2)
                self.assertEqual(self.file.read_bytes(), b"ok")

    def test_exhausted_transient_failures_remove_partial_bytes(self):
        self.assertEqual(source.MAX_TRANSPORT_ATTEMPTS, 3)
        items = [FakeResponse(b"partial", fail_read=TimeoutError("timeout"))
                 for _ in range(source.MAX_TRANSPORT_ATTEMPTS)]
        with patch.object(source.urllib.request, "urlopen",
                          side_effect=items) as opened:
            with self.assertRaises(TimeoutError):
                source.download(self.file)
        self.assertEqual(opened.call_count, source.MAX_TRANSPORT_ATTEMPTS)
        self.assertFalse(self.file.exists())

    def test_forbidden_http_error_no_retry(self):
        for code in (403, 404, 500):
            with self.subTest(http=code):
                with patch.object(source.urllib.request, "urlopen",
                    side_effect=urllib.error.HTTPError(
                        source.URL, code, "disallowed", None, None)) as opened:
                    with self.assertRaises(urllib.error.HTTPError):
                        source.download(self.file)
                self.assertEqual(opened.call_count, 1)
                self.assertFalse(self.file.exists())

    def test_certificate_failure_no_retry(self):
        reason = ssl.SSLCertVerificationError(1, "certificate verify failed")
        with patch.object(source.urllib.request, "urlopen",
                          side_effect=urllib.error.URLError(reason)) as opened:
            with self.assertRaises(urllib.error.URLError):
                source.download(self.file)
        self.assertEqual(opened.call_count, 1)
        self.assertFalse(self.file.exists())

    def test_unexpected_redirect_or_status_no_retry(self):
        for response in (
            FakeResponse(b"wrong", url="https://unapproved.invalid/data"),
            FakeResponse(b"wrong", status=206),
        ):
            with self.subTest(status=response.status, url=response.url):
                with patch.object(source.urllib.request, "urlopen",
                                  return_value=response) as opened:
                    with self.assertRaises(Exception):
                        source.download(self.file)
                self.assertEqual(opened.call_count, 1)
                self.assertFalse(self.file.exists())

    def test_oversized_response_no_retry_and_no_file(self):
        with patch.object(source, "MAX_ARCHIVE", 4), patch.object(
            source.urllib.request, "urlopen", return_value=FakeResponse(b"abcde")
        ) as opened:
            with self.assertRaises(Exception):
                source.download(self.file)
        self.assertEqual(opened.call_count, 1)
        self.assertFalse(self.file.exists())

    def test_existing_destination_never_overwritten(self):
        self.file.write_bytes(b"prior-evidence")
        with patch.object(source.urllib.request, "urlopen") as opened:
            with self.assertRaises(Exception):
                source.download(self.file)
        opened.assert_not_called()
        self.assertEqual(self.file.read_bytes(), b"prior-evidence")


if __name__ == "__main__":
    unittest.main(verbosity=2)
