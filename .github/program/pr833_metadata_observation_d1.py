#!/usr/bin/env python3
"""One new public PR833 observation with sealed raw bytes; never admission.

No historical response is reconstructed. Normal CI exercises offline controls
only. A live invocation needs a separately approved observation context.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SELF = ".github/program/pr833_metadata_observation_d1.py"
LEGACY = ".github/program/dechorate_event_source_t1m3.py"
LEGACY_SHA256 = "c8a2bfdade22d33fb40155b440d80d960524adccdef10cf9131340bbb84a81f6"
REPO = "jiying2007/audio-pipeline"
REPO_ID = 1347377137
HEAD_REF = "codex/dechorate-source-m2-20261024"
URL = "https://api.github.com/repos/" + REPO + "/pulls/833"
MAX_BYTES = 150_000
MAX_RECEIPT = 16_000
TIMEOUT = 15
SHA = re.compile(r"[0-9a-f]{40}")
FIELDS = ("base_sha", "head_sha", "merge_sha")
DENIALS = ("admission_granted", "source_range_qualified", "skip_measurement",
           "scientific_experiment_executed", "historical_failed_request_reconstructed")
FILES = ("response.body", "response.body.sha256", "receipt.json", "receipt.json.sha256")


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def oid(value: object) -> bool:
    return type(value) is str and SHA.fullmatch(value) is not None and value != "0" * 40


def expected_identity(base: str, head: str, merge: str) -> dict:
    require(all(oid(v) for v in (base, head, merge)), "EXPECTED_NONZERO_OIDS_REQUIRED")
    return dict(zip(FIELDS, (base, head, merge)))


def strict_pairs(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def no_constant(_value: str):
    raise ValueError("NONFINITE_JSON")


def finite_float(value: str) -> float:
    number = float(value)
    require(math.isfinite(number), "NONFINITE_JSON_NUMBER")
    return number


def load_json(raw: bytes):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs,
                      parse_constant=no_constant, parse_float=finite_float)


def oid_field(data: dict, key: str) -> dict:
    if key not in data:
        kind = "MISSING"
    elif data[key] is None:
        kind = "NULL"
    elif type(data[key]) is not str:
        kind = "WRONG_TYPE"
    elif data[key] == "0" * 40:
        kind = "ZERO_OID"
    else:
        kind = "VALID_OID" if oid(data[key]) else "INVALID_STRING"
    return {"kind": kind, "value": data[key] if kind == "VALID_OID" else None}


def safe_headers(headers) -> dict:
    result = {}
    for key, field, maximum in (
        ("X-RateLimit-Remaining", "rate_limit_remaining", 100_000_000),
        ("Retry-After", "retry_after_seconds", 86_400),
        ("Content-Length", "content_length", 9_999_999_999),
    ):
        value = headers.get(key) if headers is not None else None
        result[field] = (int(value) if type(value) is str and
                         re.fullmatch(r"[0-9]{1,10}", value) and int(value) <= maximum else None)
    value = headers.get("X-GitHub-Request-Id") if headers is not None else None
    result["github_request_id"] = (value if type(value) is str and
                                    re.fullmatch(r"[0-9a-fA-F:]{4,100}", value) else None)
    return result


def metadata(raw: bytes, expected: dict) -> tuple[str, dict | None]:
    try:
        data = load_json(raw)
        require(type(data) is dict, "NOT_OBJECT")
        require(type(data.get("number")) is int and data["number"] == 833, "WRONG_PR")
        user = data.get("user")
        require(type(user) is dict and user.get("login") == "jiying2007" and
                type(user.get("id")) is int and user["id"] == 33591504 and
                user.get("type") == "User", "WRONG_AUTHOR")
        for side, ref in (("base", "main"), ("head", HEAD_REF)):
            item = data.get(side)
            require(type(item) is dict and item.get("ref") == ref, "WRONG_REF")
            repo = item.get("repo")
            require(type(repo) is dict and repo.get("full_name") == REPO and
                    type(repo.get("id")) is int and repo["id"] == REPO_ID and
                    oid(item.get("sha")), "WRONG_REPOSITORY_OR_OID")
        merge = oid_field(data, "merge_commit_sha")
        observed = {"base_sha": data["base"]["sha"], "head_sha": data["head"]["sha"],
                    "merge_sha": merge["value"], "merge_field_kind": merge["kind"]}
        value = data.get("mergeable")
        observed["mergeable_kind"] = ("MISSING" if "mergeable" not in data else
                                      "NULL" if value is None else
                                      "TRUE" if value is True else
                                      "FALSE" if value is False else "WRONG_TYPE")
        observed["open_unmerged_nondraft"] = (data.get("state") == "open" and
                                               data.get("merged") is False and
                                               data.get("draft") is False)
        if not observed["open_unmerged_nondraft"]:
            return "PR_STATE_MISMATCH", observed
        if any(observed[k] != expected[k] for k in ("base_sha", "head_sha")):
            return "IDENTITY_MISMATCH", observed
        if merge["kind"] in ("MISSING", "NULL"):
            return "MERGE_IDENTITY_UNAVAILABLE", observed
        if merge["kind"] != "VALID_OID":
            return "MERGE_IDENTITY_INVALID", observed
        return ("OBSERVED_MATCH" if observed["merge_sha"] == expected["merge_sha"]
                else "IDENTITY_MISMATCH"), observed
    except (ValueError, UnicodeError, KeyError, TypeError, RecursionError):
        return "METADATA_INVALID", None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def observe(expected: dict, opener=None) -> tuple[dict, bytes]:
    require(type(expected) is dict and set(expected) == set(FIELDS), "EXPECTED_CONTEXT_REQUIRED")
    expected_identity(*(expected[k] for k in FIELDS))
    report = {"schema_version": 1, "identity": "PR833_METADATA_OBSERVATION_D1",
              "observation_only": True, **dict.fromkeys(DENIALS, False),
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "request": {"url": URL, "authenticated": False, "attempts": 1,
                          "redirects_allowed": 0, "socket_timeout_seconds": TIMEOUT,
                          "read_limit_bytes": MAX_BYTES + 1},
              "expected_identity": dict(expected), "observed_identity": None,
              "http_status": None, "headers": safe_headers(None),
              "body_received": False, "body_complete": False, "outcome": "NETWORK_ERROR"}
    raw = b""
    request = urllib.request.Request(URL, headers={
        "Accept": "application/vnd.github+json", "Accept-Encoding": "identity",
        "User-Agent": "audio-pipeline-pr833-observation/1",
        "X-GitHub-Api-Version": "2022-11-28"})
    opening = opener if opener is not None else urllib.request.build_opener(
        urllib.request.ProxyHandler({}), NoRedirect()).open

    def receive(response):
        nonlocal raw
        require(response.url == URL, "UNEXPECTED_RESPONSE_URL")
        status = response.status
        require(type(status) is int and 100 <= status <= 599, "INVALID_HTTP_STATUS")
        report["http_status"] = status
        report["headers"] = safe_headers(response.headers)
        try:
            raw = response.read(MAX_BYTES + 1)
        except http.client.IncompleteRead as error:
            raw = error.partial[:MAX_BYTES + 1]
            report.update(body_received=True, outcome="PARTIAL_BODY")
            return
        require(type(raw) is bytes and len(raw) <= MAX_BYTES + 1, "INVALID_BODY_READER")
        report["body_received"] = True
        declared = report["headers"]["content_length"]
        if len(raw) > MAX_BYTES:
            report["outcome"] = "BODY_TOO_LARGE"
        elif declared is not None and declared != len(raw):
            report["outcome"] = "PARTIAL_BODY"
        else:
            report["body_complete"] = True
            if status != 200:
                report["outcome"] = "HTTP_ERROR"
            elif not raw:
                report["outcome"] = "METADATA_INVALID"
            else:
                report["outcome"], report["observed_identity"] = metadata(raw, expected)
    try:
        try:
            with opening(request, timeout=TIMEOUT) as response:
                receive(response)
        except urllib.error.HTTPError as error:
            try:
                receive(error)
            finally:
                error.close()
    except urllib.error.URLError as error:
        cause = error.reason
        report["outcome"] = ("TIMEOUT" if isinstance(cause, TimeoutError) else
                             "TLS_ERROR" if isinstance(cause, ssl.SSLError) else
                             "DNS_ERROR" if isinstance(cause, socket.gaierror) else "NETWORK_ERROR")
    except TimeoutError:
        report["outcome"] = "TIMEOUT"
    except ssl.SSLError:
        report["outcome"] = "TLS_ERROR"
    except socket.gaierror:
        report["outcome"] = "DNS_ERROR"
    except (OSError, http.client.HTTPException):
        report["outcome"] = "NETWORK_ERROR"
    except ValueError:
        report["outcome"] = "TRANSPORT_INVALID"
    if report["outcome"] in ("TIMEOUT", "TLS_ERROR", "DNS_ERROR", "NETWORK_ERROR", "TRANSPORT_INVALID"):
        report["body_complete"] = False
    report.update(body_bytes=len(raw), body_sha256=hashlib.sha256(raw).hexdigest(),
                  finished_at_utc=datetime.now(timezone.utc).isoformat())
    return report, raw


def verify_source_bytes(current: bytes, committed: bytes, legacy: bytes) -> None:
    require(bool(current) and current == committed, "OBSERVER_SOURCE_NOT_COMMITTED")
    require(hashlib.sha256(legacy).hexdigest() == LEGACY_SHA256, "FROZEN_SOURCE_HELPER_CHANGED")


def source_identity() -> dict:
    forbidden = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_DIR", "GIT_WORK_TREE",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
                 "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE")
    require(not any(os.environ.get(k) for k in forbidden), "EXTERNAL_GIT_CONTEXT_REFUSED")
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
               GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")

    def git(*args):
        raw = subprocess.check_output([
            "git", "--no-replace-objects", "-c", "safe.directory=" + str(ROOT),
            "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "protocol.allow=never", *args], cwd=ROOT, env=env,
            stderr=subprocess.PIPE, timeout=15)
        require(len(raw) <= MAX_BYTES, "SOURCE_READ_BOUND")
        return raw
    head = git("rev-parse", "HEAD").decode("ascii").strip()
    tree = git("rev-parse", "HEAD^{tree}").decode("ascii").strip()
    require(oid(head) and oid(tree) and not git("status", "--porcelain", "--untracked-files=no").strip(),
            "CLEAN_COMMITTED_OBSERVER_REQUIRED")
    for path in (SELF, LEGACY):
        entry = git("ls-tree", "HEAD", "--", path).decode("ascii")
        require(re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path) + r"\n", entry)
                is not None and not (ROOT / path).is_symlink(), "SOURCE_FILE_MODE_INVALID")
    current = (ROOT / SELF).read_bytes()
    legacy = (ROOT / LEGACY).read_bytes()
    require(legacy == git("show", "HEAD:" + LEGACY), "LEGACY_SOURCE_NOT_COMMITTED")
    verify_source_bytes(current, git("show", "HEAD:" + SELF), legacy)
    return {"commit": head, "tree": tree, "observer_sha256": hashlib.sha256(current).hexdigest(),
            "legacy_sha256": LEGACY_SHA256}


def capture(expected: dict, output: Path, *, opener=None, source_check=source_identity) -> dict:
    require(type(expected) is dict and set(expected) == set(FIELDS), "EXPECTED_CONTEXT_REQUIRED")
    expected_identity(*(expected[k] for k in FIELDS))
    source = source_check()
    # The caller supplies a trusted parent; a fresh private directory is never reused.
    output.mkdir(mode=0o700)
    report, raw = observe(expected, opener)
    with (output / FILES[0]).open("xb") as stream:
        require(stream.write(raw) == len(raw), "RAW_WRITE_INCOMPLETE")
    with (output / FILES[1]).open("x", encoding="ascii") as stream:
        seal = report["body_sha256"] + "  response.body\n"
        require(stream.write(seal) == len(seal), "RAW_SEAL_WRITE_INCOMPLETE")
    report["observer_source"] = source
    try:
        stable = source_check() == source
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        stable = False
    report["source_unchanged_after_observation"] = stable
    if not stable:
        report["outcome"] = "SOURCE_CHANGED_DURING_OBSERVATION"
    encoded = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(len(encoded) <= MAX_RECEIPT, "RECEIPT_SIZE_BOUND")
    with (output / FILES[2]).open("xb") as stream:
        require(stream.write(encoded) == len(encoded), "RECEIPT_WRITE_INCOMPLETE")
    with (output / FILES[3]).open("x", encoding="ascii") as stream:
        seal = hashlib.sha256(encoded).hexdigest() + "  receipt.json\n"
        require(stream.write(seal) == len(seal), "RECEIPT_SEAL_WRITE_INCOMPLETE")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-merge", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        expected = expected_identity(args.expected_base, args.expected_head, args.expected_merge)
        report = capture(expected, args.output)
        print(json.dumps({"outcome": report["outcome"], "http_status": report["http_status"],
                          "admission_granted": False, "body_sha256": report["body_sha256"]},
                         sort_keys=True))
        return 0 if report["outcome"] == "OBSERVED_MATCH" else 2
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        print("PR833_OBSERVATION_SOURCE_OR_EVIDENCE_FAILED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
