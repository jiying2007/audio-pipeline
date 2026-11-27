#!/usr/bin/env python3
"""Fetch one saved ZIP for the two observed B2-S2 / BA2 readback failures.

This is transport admission only. The original scientific reader remains
mandatory. Run identity, every listing page, the archive redirect and its blob
GET share eight HTTP requests, ten seconds each, and a 94-second total clock.
No signed URL or token is retained, and no token crosses the GitHub API host.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from fe09_same_run_artifact_visibility import (
    A1_LIST_RESPONSE_CAP, API_URL, MAX_ATTEMPTS, NoRedirect, NotAdmitted,
    SLEEP_SECONDS, need, reject_duplicates, utc_timestamp, verify_run_identity,
)

REQUEST_SECONDS = 10
TOTAL_SECONDS = MAX_ATTEMPTS * REQUEST_SECONDS + (MAX_ATTEMPTS - 1) * SLEEP_SECONDS
MEMBERS = ("SHA256SUMS", "receipt.json", "collect.log", "verify.log")
STAGES = {
    "b2s2": {"prefix": "frontend-fe09-b2s2-private-apd-", "attempt_name": True,
             "zip_cap": 64 * 1024, "expanded_cap": 1024 * 1024},
    "ba2": {"prefix": "frontend-fe09-t3s2b1ba2-retirement-", "attempt_name": False,
            "zip_cap": 8 * 1024 * 1024, "expanded_cap": 16 * 1024 * 1024},
}


class TransientHTTP(Exception):
    """Only 404/502/503, before any accepted response body, may consume a retry."""


class Budget:
    def __init__(self, *, clock=time.monotonic, pause=time.sleep, alarms=True):
        self.clock, self.pause, self.alarms = clock, pause, alarms
        self.started = clock()
        self.deadline = self.started + TOTAL_SECONDS
        self.request_deadline = None
        self.events = []

    def check(self):
        now = self.clock()
        need(now < self.deadline, "ARCHIVE_TOTAL_WALL_BUDGET_EXCEEDED")
        need(self.request_deadline is None or now < self.request_deadline,
             "ARCHIVE_REQUEST_WALL_BUDGET_EXCEEDED")

    def _alarm(self, _number, _frame):
        reason = ("ARCHIVE_TOTAL_WALL_BUDGET_EXCEEDED"
                  if self.clock() >= self.deadline else
                  "ARCHIVE_REQUEST_WALL_BUDGET_EXCEEDED")
        raise NotAdmitted(reason)

    def arm(self):
        self.check()
        if self.alarms:
            deadline = min(self.deadline, self.request_deadline or self.deadline)
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, deadline - self.clock()))

    def __enter__(self):
        if self.alarms:
            need(hasattr(signal, "setitimer") and
                 signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0),
                 "ARCHIVE_HARD_WALL_TIMER_UNAVAILABLE")
            self.old_handler = signal.signal(signal.SIGALRM, self._alarm)
        self.arm()
        return self

    def __exit__(self, *_args):
        if self.alarms:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self.old_handler)

    @contextmanager
    def request(self, kind):
        self.check()
        need(len(self.events) < MAX_ATTEMPTS, "ARCHIVE_SHARED_HTTP_BUDGET_EXHAUSTED")
        started = self.clock()
        event = {"number": len(self.events) + 1, "kind": kind,
                 "status": None, "body_bytes": 0, "outcome": "FAILED"}
        self.events.append(event)
        self.request_deadline = started + REQUEST_SECONDS
        self.arm()
        try:
            yield event
            self.check()
            event["outcome"] = "RESPONSE_ACCEPTED"
        finally:
            event["elapsed_seconds"] = round(max(0.0, self.clock() - started), 6)
            self.request_deadline = None
            self.arm()

    def retry(self):
        self.check()
        need(len(self.events) < MAX_ATTEMPTS, "ARCHIVE_SHARED_HTTP_BUDGET_EXHAUSTED")
        self.pause(SLEEP_SECONDS)
        self.check()


def checked_contract(stage, repo, run_id, artifact_id, artifact_name, token,
                     run_attempt, run_head_sha, execution_source):
    need(type(stage) is str and stage in STAGES, "ARCHIVE_STAGE_NOT_ADMITTED")
    contract = STAGES[stage]
    need(type(repo) is str and len(repo) <= 201 and
         re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)
         and all(part not in (".", "..") for part in repo.split("/"))
         and all(type(value) is int and 0 < value < 2 ** 63
                 for value in (run_id, artifact_id, run_attempt))
         and all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
                 for value in (run_head_sha, execution_source))
         and type(token) is str and 0 < len(token) <= 2048
         and not any(ord(c) <= 32 or ord(c) == 127 for c in token),
         "ARCHIVE_UNTRUSTED_IDENTITY_ARGS")
    name = contract["prefix"] + str(run_id)
    if contract["attempt_name"]:
        name += "-attempt-" + str(run_attempt)
    need(type(artifact_name) is str and artifact_name == name,
         "ARCHIVE_STAGE_NAME_OR_ATTEMPT_MISMATCH")
    return contract


def fresh_path(value):
    path = Path(value)
    need(".." not in path.parts, "ARCHIVE_OUTPUT_PARENT_TRAVERSAL")
    path = Path(os.path.abspath(str(path)))
    need(not os.path.lexists(str(path)), "ARCHIVE_OUTPUT_ALREADY_EXISTS")
    for parent in path.parents:
        need(parent.is_dir() and not parent.is_symlink(),
             "ARCHIVE_OUTPUT_PARENT_MISSING_OR_SYMLINK")
    return path


def new_binary(path):
    return os.fdopen(os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                            os.O_NOFOLLOW, 0o600), "wb")


def api_request(endpoint, token):
    target = urllib.parse.urlsplit(endpoint)
    need(target.scheme == "https" and target.netloc == "api.github.com",
         "ARCHIVE_TOKEN_DESTINATION_INVALID")
    return urllib.request.Request(endpoint, headers={
        "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "audio-pipeline-two-stage-original-zip-readback",
    })


@contextmanager
def response_for(request, kind, budget, opener):
    with budget.request(kind) as event:
        response = None
        try:
            try:
                response = opener(request, timeout=REQUEST_SECONDS)
            except urllib.error.HTTPError as error:
                response = error
            need(response.url == request.full_url, "ARCHIVE_UNEXPECTED_REDIRECT_FOLLOWED")
            status = response.code if isinstance(response, urllib.error.HTTPError) else response.status
            need(type(status) is int, "ARCHIVE_HTTP_STATUS_INVALID")
            event["status"] = status
            if status in (404, 502, 503):
                raise TransientHTTP()
            need(status == (302 if kind == "archive" else 200),
                 "ARCHIVE_HTTP_HARD_FAILURE_" + str(status))
            yield response, event
        except (urllib.error.URLError, TimeoutError):
            raise NotAdmitted("ARCHIVE_NETWORK_OR_TLS_FAILURE") from None
        finally:
            if response is not None:
                response.close()


def read_metadata(endpoint, token, kind, cap, budget, opener):
    with response_for(api_request(endpoint, token), kind, budget, opener) as (response, event):
        data = bytearray()
        while len(data) <= cap:
            budget.check()
            chunk = response.read(min(65536, cap + 1 - len(data)))
            budget.check()
            if not chunk:
                break
            data.extend(chunk)
            event["body_bytes"] += len(chunk)
        need(0 < len(data) <= cap, "ARCHIVE_METADATA_EMPTY_OR_OVERSIZE")
        return json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)


def verify_target(artifact, run, *, run_id, artifact_id, artifact_name,
                  run_head_sha, contract):
    # BA2 has its own measured cap. Never rewrite metadata to bypass the old
    # helper's unchanged 1 MiB predicate, or add BA2 to its name allowlist.
    need(type(artifact) is dict and type(artifact.get("id")) is int and
         artifact["id"] == artifact_id and artifact.get("name") == artifact_name and
         artifact.get("expired") is False and
         type(artifact.get("size_in_bytes")) is int and
         0 < artifact["size_in_bytes"] <= contract["zip_cap"] and
         type(artifact.get("digest")) is str and
         re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"]),
         "ARCHIVE_WRONG_ID_NAME_SIZE_EXPIRATION_OR_DIGEST")
    source = artifact.get("workflow_run")
    need(type(source) is dict and type(source.get("id")) is int and
         source["id"] == run_id and source.get("head_sha") == run_head_sha and
         type(source.get("repository_id")) is int and
         source["repository_id"] == run["repository"]["id"] and
         type(source.get("head_repository_id")) is int and
         source["head_repository_id"] == run["head_repository"]["id"] and
         utc_timestamp(artifact.get("created_at")) >= utc_timestamp(run["run_started_at"]),
         "ARCHIVE_WRONG_SOURCE_OR_PREVIOUS_ATTEMPT")


def admitted_metadata(repo, run_id, artifact_id, artifact_name, token, *,
                      run_attempt, run_head_sha, execution_source, contract,
                      budget, opener):
    run = None
    rows, total, page = [], None, 1
    while True:
        endpoint = (f"{API_URL}/repos/{repo}/actions/runs/{run_id}/attempts/{run_attempt}"
                    if run is None else
                    f"{API_URL}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100&page={page}")
        try:
            payload = read_metadata(endpoint, token, "run" if run is None else "list",
                                    65536 if run is None else A1_LIST_RESPONSE_CAP,
                                    budget, opener)
        except TransientHTTP:
            rows, total, page = [], None, 1
            budget.retry()
            continue
        if run is None:
            verify_run_identity(payload, repo=repo, run_id=run_id,
                                run_attempt=run_attempt, run_head_sha=run_head_sha)
            references = payload.get("referenced_workflows")
            need(type(references) is list, "ARCHIVE_QUALITY_EXECUTION_SOURCE_MISMATCH")
            quality = [ref for ref in references if type(ref) is dict and
                       type(ref.get("path")) is str and ref["path"].startswith(
                           f"{repo}/.github/workflows/quality.yml@")]
            need(len(quality) == 1 and quality[0]["path"] ==
                 f"{repo}/.github/workflows/quality.yml@{execution_source}" and
                 quality[0].get("sha") == execution_source,
                 "ARCHIVE_QUALITY_EXECUTION_SOURCE_MISMATCH")
            utc_timestamp(payload.get("run_started_at"))
            run = payload
            continue
        need(type(payload) is dict and type(payload.get("total_count")) is int and
             0 <= payload["total_count"] <= 1000 and
             type(payload.get("artifacts")) is list and len(payload["artifacts"]) <= 100,
             "ARCHIVE_LIST_SCHEMA_OR_BOUND_INVALID")
        if total is None:
            total = payload["total_count"]
        complete_page = (payload["total_count"] == total and len(payload["artifacts"]) ==
                         min(100, max(0, total - 100 * (page - 1))))
        rows.extend(payload["artifacts"])
        need(all(type(row) is dict and type(row.get("id")) is int and
                 0 < row["id"] < 2 ** 63 and type(row.get("name")) is str for row in rows)
             and len({row["id"] for row in rows}) == len(rows),
             "ARCHIVE_LIST_DUPLICATE_OR_INVALID_ID")
        matches = [row for row in rows if row["id"] == artifact_id or row["name"] == artifact_name]
        if matches:
            need(len(matches) == 1, "ARCHIVE_NAME_OR_ID_NOT_UNIQUE")
            verify_target(matches[0], run, run_id=run_id, artifact_id=artifact_id,
                          artifact_name=artifact_name, run_head_sha=run_head_sha,
                          contract=contract)
        if not complete_page:
            rows, total, page = [], None, 1
            budget.retry()
        elif len(rows) < total:
            page += 1
        elif matches:
            return run, matches[0]
        else:
            rows, total, page = [], None, 1
            budget.retry()


def checked_location(location):
    try:
        target = urllib.parse.urlsplit(location)
        valid = (type(location) is str and 0 < len(location) <= 16384 and
                 not any(ord(c) <= 32 or ord(c) == 127 for c in location) and
                 target.scheme == "https" and target.username is None and
                 target.password is None and target.port in (None, 443) and
                 not target.fragment and type(target.hostname) is str and
                 re.fullmatch(r"productionresultssa[0-9]+\.blob\.core\.windows\.net",
                              target.hostname) is not None)
    except (TypeError, ValueError):
        valid = False
    need(valid, "ARCHIVE_BLOB_REDIRECT_NOT_ADMITTED")
    return target.hostname


def acquire_zip(repo, artifact_id, token, metadata, evidence, budget, opener):
    endpoint = f"{API_URL}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    while True:
        try:
            with response_for(api_request(endpoint, token), "archive", budget, opener) as (response, _):
                location = response.headers.get("Location", "")
                host = checked_location(location)
            # Deliberately construct a fresh request without Authorization.
            request = urllib.request.Request(location, headers={
                "User-Agent": "audio-pipeline-two-stage-original-zip-readback"})
            with response_for(request, "blob", budget, opener) as (response, event):
                size = metadata["size_in_bytes"]
                length = response.headers.get("Content-Length")
                need(length is None or (re.fullmatch(r"[0-9]+", length) and int(length) == size),
                     "ARCHIVE_CONTENT_LENGTH_MISMATCH")
                partial = evidence / "original.zip.partial"
                digest, count = hashlib.sha256(), 0
                with new_binary(partial) as handle:
                    while count <= size:
                        budget.check()
                        chunk = response.read(min(65536, size + 1 - count))
                        budget.check()
                        if not chunk:
                            break
                        event["body_bytes"] += len(chunk)
                        # Keep a bounded failed prefix; never write an extra byte
                        # past the exact admitted compressed size.
                        handle.write(chunk[:max(0, size - count)])
                        digest.update(chunk)
                        count += len(chunk)
                        need(count <= size, "ARCHIVE_BODY_OVERSIZE")
                    handle.flush()
                need(count == size, "ARCHIVE_BODY_SIZE_MISMATCH")
                need("sha256:" + digest.hexdigest() == metadata["digest"],
                     "ARCHIVE_BODY_SHA256_MISMATCH")
                budget.check()
            archive = evidence / "original.zip"
            need(not os.path.lexists(str(archive)), "ARCHIVE_ORIGINAL_ZIP_ALREADY_EXISTS")
            partial.rename(archive)
            return archive, host
        except TransientHTTP:
            # A blob 404 consumes its own request. Restart at the authenticated
            # endpoint to obtain a fresh short-lived URL, without a new budget.
            budget.retry()


def extract_checked(archive, output, contract, budget):
    content = {}
    with zipfile.ZipFile(str(archive), "r") as zipped:
        infos = zipped.infolist()
        need(len(infos) == len(MEMBERS) and {info.filename for info in infos} == set(MEMBERS),
             "ARCHIVE_MEMBER_SET_OR_DUPLICATE")
        need(sum(info.file_size for info in infos) <= contract["expanded_cap"],
             "ARCHIVE_EXPANDED_SIZE_CAP")
        for info in infos:
            budget.check()
            mode = info.external_attr >> 16
            need(info.orig_filename == info.filename and not info.is_dir() and
                 not (info.external_attr & 0x10) and
                 stat.S_IFMT(mode) in (0, stat.S_IFREG) and
                 not (info.flag_bits & ~0x808) and
                 info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) and
                 0 < info.file_size <= contract["expanded_cap"],
                 "ARCHIVE_MEMBER_TYPE_FLAGS_COMPRESSION_OR_SIZE")
            data = bytearray()
            with zipped.open(info, "r") as member:
                while len(data) <= info.file_size:
                    budget.check()
                    chunk = member.read(min(65536, info.file_size + 1 - len(data)))
                    budget.check()
                    if not chunk:
                        break
                    data.extend(chunk)
            need(len(data) == info.file_size, "ARCHIVE_MEMBER_SIZE_MISMATCH")
            content[info.filename] = bytes(data)
    # CRC and all four names/types/bounds pass before creating reader inputs.
    output.mkdir(mode=0o700)
    result = {}
    for name in MEMBERS:
        budget.check()
        with new_binary(output / name) as handle:
            handle.write(content[name])
        result[name] = {"size_bytes": len(content[name]),
                        "sha256": hashlib.sha256(content[name]).hexdigest()}
    budget.check()
    return result


def safe_error(error):
    if isinstance(error, NotAdmitted) and re.fullmatch(r"[A-Z0-9_:]{1,160}", str(error)):
        return str(error)
    return "ARCHIVE_FAILURE_" + type(error).__name__


def write_report(evidence, report):
    pending = evidence / "transport.json.pending"
    # Only our own fixed-name pending receipt can exist after a timed write.
    if pending.exists():
        need(pending.is_file() and not pending.is_symlink(), "ARCHIVE_REPORT_PATH_CHANGED")
        pending.unlink()
    with new_binary(pending) as handle:
        handle.write((json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8"))
    pending.replace(evidence / "transport.json")


def download_artifact(*, stage, repo, run_id, artifact_id, artifact_name, token,
                      run_attempt, run_head_sha, execution_source, output, evidence,
                      opener=None, clock=time.monotonic, pause=time.sleep, alarms=True):
    budget = Budget(clock=clock, pause=pause, alarms=alarms)
    report = {"schema_version": 1, "status": "FAILED", "requests": budget.events,
              "budget": {"http_requests": MAX_ATTEMPTS, "request_seconds": REQUEST_SECONDS,
                         "total_seconds": TOTAL_SECONDS, "retry_pause_seconds": SLEEP_SECONDS}}
    evidence_path = None
    try:
        with budget:
            contract = checked_contract(stage, repo, run_id, artifact_id, artifact_name,
                                        token, run_attempt, run_head_sha, execution_source)
            output_path, candidate = fresh_path(output), fresh_path(evidence)
            need(output_path != candidate and output_path not in candidate.parents and
                 candidate not in output_path.parents, "ARCHIVE_OUTPUT_PATHS_OVERLAP")
            candidate.mkdir(mode=0o700)
            evidence_path = candidate
            report["identity"] = {"stage": stage, "repository": repo, "run_id": run_id,
                                  "run_attempt": run_attempt, "run_head_sha": run_head_sha,
                                  "execution_source": execution_source, "artifact_id": artifact_id,
                                  "artifact_name": artifact_name}
            report["caps"] = {"zip_bytes": contract["zip_cap"],
                              "expanded_bytes": contract["expanded_cap"]}
            write_report(evidence_path, report)
            if opener is None:
                opener = urllib.request.build_opener(NoRedirect()).open
            run, metadata = admitted_metadata(
                repo, run_id, artifact_id, artifact_name, token, run_attempt=run_attempt,
                run_head_sha=run_head_sha, execution_source=execution_source,
                contract=contract, budget=budget, opener=opener)
            report["artifact"] = {key: metadata[key] for key in
                                  ("id", "name", "size_in_bytes", "digest", "created_at")}
            report["run_started_at"] = run["run_started_at"]
            report["repository_id"] = run["repository"]["id"]
            report["head_repository_id"] = run["head_repository"]["id"]
            archive, host = acquire_zip(repo, artifact_id, token, metadata,
                                        evidence_path, budget, opener)
            report["blob_host"] = host
            report["members"] = extract_checked(archive, output_path, contract, budget)
            budget.check()
            report["status"] = "PASS_TRANSPORT_ONLY"
            report["elapsed_seconds"] = round(clock() - budget.started, 6)
            write_report(evidence_path, report)
            budget.check()
            return report
    except Exception as error:
        # After a hard stop only a small failure receipt is finalized. No new
        # HTTP, archive read, extraction or scientific work can resume here.
        report["status"] = "FAILED"
        report["error"] = safe_error(error)
        report["elapsed_seconds"] = round(max(0.0, clock() - budget.started), 6)
        if evidence_path is not None:
            write_report(evidence_path, report)
        raise NotAdmitted(report["error"]) from None


def positive_id(value):
    if (type(value) is not str or not re.fullmatch(r"[1-9][0-9]{0,18}", value)
            or int(value) >= 2 ** 63):
        raise argparse.ArgumentTypeError("ARCHIVE_ID_NOT_CANONICAL_POSITIVE_INT64")
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=sorted(STAGES), required=True)
    parser.add_argument("--repository", dest="repo", required=True)
    parser.add_argument("--artifact-id", required=True, type=positive_id)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--run-id", required=True, type=positive_id)
    parser.add_argument("--run-attempt", required=True, type=positive_id)
    parser.add_argument("--run-head-sha", required=True)
    parser.add_argument("--execution-source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    try:
        report = download_artifact(token=os.environ.get("GH_TOKEN", ""), **vars(args))
    except NotAdmitted as error:
        raise SystemExit("FE09_ORIGINAL_ZIP_NOT_ADMITTED: " + str(error)) from None
    print("FE09_ORIGINAL_ZIP_TRANSPORT_ONLY_PASS", args.stage, args.run_id,
          args.artifact_id, "requests=" + str(len(report["requests"])),
          report["artifact"]["digest"])


if __name__ == "__main__":
    main()
