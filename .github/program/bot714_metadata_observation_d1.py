#!/usr/bin/env python3
"""One bounded public PR #714 metadata observation; no admission authority.

This is a fresh diagnostic request, never the missing response from an earlier
M1 failure. It cannot change a maintenance receipt, workflow output or budget.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SELF = ".github/program/bot714_metadata_observation_d1.py"
M1 = ".github/program/workflow_pin_only_actual_tree_t1m1.py"
M1_SHA256 = "156c2f14f02c12fe11de83d52f4c3e54a84e2ebbb558b5dd387a023d547299dc"
REPO = "jiying2007/audio-pipeline"
BOT_REF = "dependabot/github_actions/actions-non-major-5b90254856"
URL = "https://api.github.com/repos/" + REPO + "/pulls/714"
MAX_BYTES = 150_000
TIMEOUT = 15
SHA = re.compile(r"[0-9a-f]{40}")
IDENTITY_FIELDS = ("base_sha", "head_sha", "merge_sha")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_METADATA_KEY")
        result[key] = value
    return result


def safe_headers(headers) -> dict:
    result = {}
    for header, field, ceiling in (
        ("X-RateLimit-Remaining", "rate_limit_remaining", 100_000_000),
        ("X-RateLimit-Reset", "rate_limit_reset_unix", 9_999_999_999),
        ("Retry-After", "retry_after_seconds", 86_400),
    ):
        value = headers.get(header) if headers is not None else None
        result[field] = (int(value) if type(value) is str and
                         re.fullmatch(r"[0-9]{1,10}", value) and int(value) <= ceiling else None)
    value = headers.get("X-GitHub-Request-Id") if headers is not None else None
    result["github_request_id"] = (value if type(value) is str and
                                    re.fullmatch(r"[0-9a-fA-F:]{4,100}", value) else None)
    return result


def expected_identity(base: str, head: str, merge: str) -> dict:
    values = (base, head, merge)
    if not all(type(value) is str and SHA.fullmatch(value) for value in values):
        raise ValueError("EXPECTED_PR_IDENTITY_REQUIRED")
    return dict(zip(IDENTITY_FIELDS, values))


def public_identity(data: dict) -> dict:
    if not (type(data) is dict and type(data.get("number")) is int and data["number"] == 714
            and data.get("state") in ("open", "closed") and type(data.get("user")) is dict
            and data["user"].get("login") == "dependabot[bot]"
            and data["user"].get("id") == 49699333 and data["user"].get("type") == "Bot"):
        raise ValueError("PUBLIC_PR_IDENTITY_INVALID")
    for side, ref in (("base", "main"), ("head", BOT_REF)):
        item = data.get(side)
        if not (type(item) is dict and item.get("ref") == ref and
                type(item.get("repo")) is dict and item["repo"].get("full_name") == REPO):
            raise ValueError("PUBLIC_PR_REPOSITORY_INVALID")
    return expected_identity(data["base"].get("sha"), data["head"].get("sha"),
                             data.get("merge_commit_sha"))


def observe(expected: dict, opener=None) -> dict:
    if type(expected) is not dict or set(expected) != set(IDENTITY_FIELDS):
        raise ValueError("EXPECTED_PR_IDENTITY_REQUIRED")
    expected_identity(*(expected.get(key) for key in IDENTITY_FIELDS))
    report = {
        "schema_version": 1,
        "identity": "BOT714_METADATA_OBSERVATION_D1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_only": True,
        "historical_failed_request_reconstructed": False,
        "admission_granted": False,
        "skip_measurement": False,
        "scientific_experiment_executed": False,
        "request": {"url": URL, "authenticated": False, "attempts": 1,
                    "redirects_allowed": 0, "timeout_seconds": TIMEOUT,
                    "maximum_accepted_response_bytes": MAX_BYTES,
                    "read_limit_bytes": MAX_BYTES + 1},
        "expected_identity": dict(expected),
        "observed_identity": None,
        "identity_matches": False,
        "http_status": None,
        "response_bytes": None,
        "headers": safe_headers(None),
        "outcome": "NETWORK_ERROR",
    }
    request = urllib.request.Request(URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "audio-pipeline-t1-m1-source-only/1",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    open_request = opener if opener is not None else urllib.request.build_opener(NoRedirect()).open
    body = None
    try:
        with open_request(request, timeout=TIMEOUT) as response:
            status = response.status
            report["http_status"] = status if type(status) is int and 100 <= status <= 599 else None
            report["headers"] = safe_headers(response.headers)
            if report["http_status"] != 200:
                report["outcome"] = "HTTP_ERROR"
            else:
                body = response.read(MAX_BYTES + 1)
                report["response_bytes"] = len(body)
                report["outcome"] = "METADATA_INVALID"
    except urllib.error.HTTPError as error:
        report["http_status"] = (error.code if type(error.code) is int and
                                  100 <= error.code <= 599 else None)
        report["headers"] = safe_headers(error.headers)
        report["outcome"] = "HTTP_ERROR"
        error.close()
    except urllib.error.URLError as error:
        cause = error.reason
        report["outcome"] = ("TIMEOUT" if isinstance(cause, TimeoutError) else
                             "TLS_ERROR" if isinstance(cause, ssl.SSLError) else
                             "DNS_ERROR" if isinstance(cause, socket.gaierror) else
                             "NETWORK_ERROR")
    except TimeoutError:
        report["outcome"] = "TIMEOUT"
    except ssl.SSLError:
        report["outcome"] = "TLS_ERROR"
    except OSError:
        report["outcome"] = "NETWORK_ERROR"
    if body is not None and 0 < len(body) <= MAX_BYTES:
        try:
            data = json.loads(body.decode("utf-8"), object_pairs_hook=strict_pairs)
            report["observed_identity"] = public_identity(data)
            report["identity_matches"] = report["observed_identity"] == expected
            report["outcome"] = "HTTP_OK" if report["identity_matches"] else "IDENTITY_MISMATCH"
        except (ValueError, UnicodeError, KeyError, TypeError):
            report["outcome"] = "METADATA_INVALID"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return report


def verify_source_bytes(current: bytes, committed: bytes, m1: bytes) -> None:
    if not current or current != committed:
        raise ValueError("OBSERVER_SOURCE_NOT_COMMITTED")
    if hashlib.sha256(m1).hexdigest() != M1_SHA256:
        raise ValueError("FROZEN_M1_SOURCE_CHANGED")


def source_identity() -> dict:
    def git(*args):
        return subprocess.check_output(["git", "-c", "safe.directory=" + str(ROOT), *args],
                                       cwd=ROOT, stderr=subprocess.PIPE, timeout=15)
    head = git("rev-parse", "HEAD").decode("ascii").strip()
    tree = git("rev-parse", "HEAD^{tree}").decode("ascii").strip()
    if not SHA.fullmatch(head) or not SHA.fullmatch(tree) or git(
            "status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("CLEAN_OBSERVER_CHECKOUT_REQUIRED")
    current = (ROOT / SELF).read_bytes()
    verify_source_bytes(current, git("show", "HEAD:" + SELF), (ROOT / M1).read_bytes())
    return {"commit": head, "tree": tree, "observer_sha256": hashlib.sha256(current).hexdigest(),
            "frozen_m1_sha256": M1_SHA256}


def self_test() -> None:
    if not __debug__:
        raise ValueError("SELF_TEST_ASSERTIONS_REQUIRED")
    wanted = expected_identity("a" * 40, "b" * 40, "c" * 40)
    fixture = {"number": 714, "state": "open",
               "user": {"login": "dependabot[bot]", "id": 49699333, "type": "Bot"},
               "base": {"sha": wanted["base_sha"], "ref": "main", "repo": {"full_name": REPO}},
               "head": {"sha": wanted["head_sha"], "ref": BOT_REF, "repo": {"full_name": REPO}},
               "merge_commit_sha": wanted["merge_sha"]}
    sentinel = "PRIVATE_DIAGNOSTIC_SENTINEL"
    reports = []

    def trial(outcome, *, raw=None, data=None, error=None, headers=None):
        calls = []
        payload = raw if raw is not None else json.dumps(fixture if data is None else data).encode()

        class Response:
            status = 200
            def __init__(self):
                self.headers = headers or {}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size):
                assert size == MAX_BYTES + 1
                return payload[:size]

        def opening(request, timeout):
            calls.append(request)
            assert request.full_url == URL and timeout == TIMEOUT
            assert not any(key.lower() == "authorization" for key in request.headers)
            if error is not None:
                raise error
            return Response()

        report = observe(wanted, opening)
        assert len(calls) == 1 and report["request"]["attempts"] == 1
        assert report["outcome"] == outcome, report
        assert report["observation_only"] is True
        for key in ("admission_granted", "skip_measurement", "scientific_experiment_executed",
                    "historical_failed_request_reconstructed"):
            assert report[key] is False
        assert sentinel not in json.dumps(report)
        reports.append(report)
        return report

    trial("HTTP_OK")
    for code, headers in ((403, {"X-RateLimit-Remaining": "0"}),
                          (429, {"Retry-After": "30"}), (302, {"Location": sentinel})):
        trial("HTTP_ERROR", error=urllib.error.HTTPError(sentinel, code, sentinel, headers, None))
    trial("TIMEOUT", error=TimeoutError(sentinel))
    trial("TIMEOUT", error=urllib.error.URLError(TimeoutError(sentinel)))
    trial("TLS_ERROR", error=urllib.error.URLError(ssl.SSLError(sentinel)))
    trial("DNS_ERROR", error=urllib.error.URLError(socket.gaierror(sentinel)))
    trial("NETWORK_ERROR", error=urllib.error.URLError(OSError(sentinel)))
    trial("NETWORK_ERROR", error=OSError(sentinel))
    for raw in (b"", b"x" * (MAX_BYTES + 1), b"\xff", sentinel.encode(),
                b'{"number":714,"number":714}'):
        trial("METADATA_INVALID", raw=raw)
    bad = copy.deepcopy(fixture)
    bad["base"]["sha"] = sentinel
    trial("METADATA_INVALID", data=bad)
    trial("METADATA_INVALID", data={**fixture, "number": 833})
    for field in IDENTITY_FIELDS:
        changed = copy.deepcopy(fixture)
        if field == "merge_sha":
            changed["merge_commit_sha"] = "d" * 40
        else:
            changed[field.split("_")[0]]["sha"] = "d" * 40
        trial("IDENTITY_MISMATCH", data=changed)
    trial("METADATA_INVALID", data={**fixture, "merge_commit_sha": None})
    poisoned = {"Authorization": sentinel, "Set-Cookie": sentinel,
                "X-RateLimit-Remaining": "1\n" + sentinel, "Retry-After": "9999999999",
                "X-RateLimit-Reset": "-1", "X-GitHub-Request-Id": sentinel}
    result = trial("HTTP_OK", headers=poisoned)
    assert all(value is None for value in result["headers"].values())
    assert len(reports) == 22
    clean = safe_headers({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1793240000",
                          "Retry-After": "30", "X-GitHub-Request-Id": "ABCD:1234:5678"})
    assert clean == {"rate_limit_remaining": 0, "rate_limit_reset_unix": 1793240000,
                     "retry_after_seconds": 30, "github_request_id": "ABCD:1234:5678"}
    m1 = (ROOT / M1).read_bytes()
    verify_source_bytes(b"observer", b"observer", m1)
    for current, committed, source in ((b"observer\n", b"observer", m1),
                                       (b"observer", b"observer", m1 + b"\n")):
        try:
            verify_source_bytes(current, committed, source)
        except ValueError:
            pass
        else:
            raise AssertionError("SOURCE_DRIFT_ACCEPTED")
    for context in ({**wanted, "unexpected": sentinel}, {**wanted, "base_sha": sentinel}):
        def never_open(*args, **kwargs):
            raise AssertionError("INVALID_CONTEXT_MADE_A_REQUEST")
        try:
            observe(context, never_open)
        except ValueError:
            pass
        else:
            raise AssertionError("INVALID_CONTEXT_ACCEPTED")
    assert NoRedirect().redirect_request(None, None, 302, "", {}, sentinel) is None
    print("BOT714_METADATA_OBSERVATION_D1_SELF_TEST_PASS observations=22 "
          "source_negatives=2 context_negatives=2 live_requests=0 redirects=0 "
          "admission_granted=false")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--observe", action="store_true")
    parser.add_argument("--expected-base")
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-merge")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required; existing evidence is never overwritten")
    try:
        expected = expected_identity(args.expected_base, args.expected_head, args.expected_merge)
        source = source_identity()
        # Reserve the evidence path before spending the single request.
        with args.output.open("x", encoding="utf-8") as target:
            report = observe(expected)
            report["observer_source"] = source
            text = json.dumps(report, sort_keys=True, indent=2) + "\n"
            print(text, end="")
            target.write(text)
        return 0 if report["outcome"] == "HTTP_OK" else 2
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        print("BOT714_OBSERVATION_SOURCE_OR_OUTPUT_PRECONDITION_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
