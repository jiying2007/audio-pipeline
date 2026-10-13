#!/usr/bin/env python3
"""Offline deterministic network-transport negatives for the frozen speech source.

No actual network requests, no LibriSpeech bytes, no scientific/audio metrics.
"""
from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import http.client

import speech_source


class FakeResponse:
    def __init__(self, chunks: list[bytes | Exception], *,
                 url: str = speech_source.URL, status: int = 200):
        self.chunks = list(chunks)
        self.url = url
        self.status = status
        self.index = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, count: int) -> bytes:
        if count != (1 << 20):
            raise AssertionError("stream size contract changed")
        if self.index >= len(self.chunks):
            return b""
        value = self.chunks[self.index]
        self.index += 1
        if isinstance(value, Exception):
            raise value
        return value


class DownloadTests(unittest.TestCase):
    def test_one_attempt_exact_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            with patch.object(speech_source.urllib.request, "urlopen",
                              return_value=FakeResponse([b"fixed bytes", b""])) as call:
                speech_source.download(path)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(call.call_args.args, (speech_source.URL,))
                self.assertEqual(call.call_args.kwargs, {"timeout": 60})
                self.assertEqual(path.read_bytes(), b"fixed bytes")

    def test_partial_timeout_retries_once_same_source_and_drops_old_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            responses = [
                FakeResponse([b"discard me", TimeoutError("truncated stream")]),
                FakeResponse([b"only second attempt", b""]),
            ]
            transcript = io.StringIO()
            with patch.object(speech_source.urllib.request, "urlopen",
                              side_effect=responses) as call:
                with redirect_stderr(transcript):
                    speech_source.download(path)
                self.assertEqual(call.call_count, 2)
                self.assertTrue(all(item.args == (speech_source.URL,) and
                                    item.kwargs == {"timeout": 60}
                                    for item in call.call_args_list))
                self.assertEqual(path.read_bytes(), b"only second attempt")
                self.assertIn("SPEECH_SOURCE_TRANSIENT_RETRY attempt=1/2",
                              transcript.getvalue())

    def test_two_timeouts_preserve_no_partial_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            responses = [
                FakeResponse([b"first", TimeoutError("timeout 1")]),
                FakeResponse([b"second", TimeoutError("timeout 2")]),
            ]
            with patch.object(speech_source.urllib.request, "urlopen",
                              side_effect=responses) as call:
                with redirect_stderr(io.StringIO()):
                    with self.assertRaisesRegex(TimeoutError, "timeout 2"):
                        speech_source.download(path)
                self.assertEqual(call.call_count, 2)
                self.assertFalse(path.exists())

    def test_urlerror_with_timeout_reason_is_bounded_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            responses = [
                urllib.error.URLError(TimeoutError("connect timeout")),
                FakeResponse([b"second", b""]),
            ]
            with patch.object(speech_source.urllib.request, "urlopen",
                              side_effect=responses) as call:
                with redirect_stderr(io.StringIO()):
                    speech_source.download(path)
                self.assertEqual(call.call_count, 2)
                self.assertEqual(path.read_bytes(), b"second")

    def test_incomplete_read_is_transient_but_requires_fresh_stream(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            failure = http.client.IncompleteRead(b"old bytes", 100)
            responses = [
                FakeResponse([b"old prefix", failure]),
                FakeResponse([b"new source", b""]),
            ]
            with patch.object(speech_source.urllib.request, "urlopen",
                              side_effect=responses) as call:
                with redirect_stderr(io.StringIO()):
                    speech_source.download(path)
                self.assertEqual(call.call_count, 2)
                self.assertEqual(path.read_bytes(), b"new source")

    def test_http_403_404_and_bad_urlerror_never_retry(self):
        for code in (403, 404):
            with self.subTest(code=code):
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "archive.tar.gz"
                    failure = urllib.error.HTTPError(
                        speech_source.URL, code, "denied", None, None)
                    with patch.object(speech_source.urllib.request, "urlopen",
                                      side_effect=failure) as call:
                        with self.assertRaises(urllib.error.HTTPError):
                            speech_source.download(path)
                        self.assertEqual(call.call_count, 1)
                        self.assertFalse(path.exists())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            with patch.object(speech_source.urllib.request, "urlopen",
                              side_effect=urllib.error.URLError("bad source")) as call:
                with self.assertRaises(urllib.error.URLError):
                    speech_source.download(path)
                self.assertEqual(call.call_count, 1)
                self.assertFalse(path.exists())

    def test_redirect_mismatch_no_retry_or_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            with patch.object(speech_source.urllib.request, "urlopen",
                              return_value=FakeResponse([b"bytes", b""],
                                                        url="https://other.test/file")) as call:
                with self.assertRaisesRegex(Exception, "redirect/status"):
                    speech_source.download(path)
                self.assertEqual(call.call_count, 1)
                self.assertFalse(path.exists())

    def test_oversize_rejected_no_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            with patch.object(speech_source, "MAX_ARCHIVE", 5):
                with patch.object(speech_source.urllib.request, "urlopen",
                                  return_value=FakeResponse([b"larger than five"])) as call:
                    with self.assertRaisesRegex(Exception, "archive download bound"):
                        speech_source.download(path)
                    self.assertEqual(call.call_count, 1)
                    self.assertFalse(path.exists())

    def test_existing_destination_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            path.write_bytes(b"frozen")
            with patch.object(speech_source.urllib.request, "urlopen") as call:
                with self.assertRaisesRegex(Exception, "download destination exists"):
                    speech_source.download(path)
                call.assert_not_called()
                self.assertEqual(path.read_bytes(), b"frozen")

    def test_value_error_no_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "archive.tar.gz"
            with patch.object(speech_source.urllib.request, "urlopen",
                              return_value=FakeResponse([b"prefix",
                                                         ValueError("decoder rule")])) as call:
                with self.assertRaisesRegex(ValueError, "decoder rule"):
                    speech_source.download(path)
                self.assertEqual(call.call_count, 1)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1)
    if not result.result.wasSuccessful():
        raise SystemExit(1)
    print("FE_SPEECH_SOURCE_TRANSIENT_RETRY_SELF_TEST_PASS")
