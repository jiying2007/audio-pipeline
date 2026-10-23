#!/usr/bin/env python3
"""Bounded same-run GitHub Artifact visibility witness before pinned download.

GitHub artifact listing can briefly lag upload finalization. This tool does
NOT download, validate PCM, waive failure, or replace actions/download-artifact.
The immutable same-run id/name/source check plus downstream full 4-member
SHA256/negative/source checks remain mandatory. Read-only GitHub API ONLY.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
import time
import urllib.error
import urllib.request

MAX_ATTEMPTS = 8
SLEEP_SECONDS = 2
API_URL = "https://api.github.com"
A1_PREFIX = "frontend-fe09-t3s2b1ba1-anchor-"
T3S1_PREFIX = "frontend-fe09-t3s1-compact-handoff-"
# A1's new 100-row REST response has its own finite metadata cap. Existing
# single-entity/run metadata stays at 64 KiB; scientific files are unaffected.
A1_LIST_RESPONSE_CAP = 256 * 1024


class NotAdmitted(ValueError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def need(condition: object, reason: str) -> None:
    if not condition:
        raise NotAdmitted(reason)


def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise NotAdmitted("ARTIFACT_METADATA_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def checked_args(repo: str, run_id: int, artifact_id: int,
                 artifact_name: str, token: str) -> None:
    need(type(repo) is str and
         re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) is not None and
         type(run_id) is int and 0 < run_id < 2 ** 63 and
         type(artifact_id) is int and 0 < artifact_id < 2 ** 63 and
         type(artifact_name) is str and
         re.fullmatch(r"(?:frontend-fe09-t2b-b1s0-owner-spsc|frontend-fe09-t2b-b1s1-source-apx3|frontend-fe09-t3s2b1ba1-anchor|frontend-fe09-t3s1-compact-handoff)-[0-9]+",
                      artifact_name) is not None and
         artifact_name.endswith("-" + str(run_id)) and
         type(token) is str and 0 < len(token) <= 2048,
         "ARTIFACT_VISIBILITY_UNTRUSTED_ARGS")


def verify_metadata(metadata: dict, *,
                    name: str, run_id: int, artifact_id: int) -> str:
    need(type(metadata) is dict and
         type(metadata.get("id")) is int and
         metadata["id"] == artifact_id and
         type(metadata.get("name")) is str and metadata["name"] == name and
         metadata.get("expired") is False and
         type(metadata.get("size_in_bytes")) is int and
         0 < metadata["size_in_bytes"] <= 1048576 and
         type(metadata.get("workflow_run")) is dict and
         type(metadata["workflow_run"].get("id")) is int and
         metadata["workflow_run"]["id"] == run_id,
         "ARTIFACT_WRONG_RUN_NAME_ID_SIZE_OR_EXPIRATION")
    digest = metadata.get("digest")
    need(type(digest) is str and
         re.fullmatch(r"sha256:[a-f0-9]{64}", digest) is not None,
         "ARTIFACT_UPLOAD_SHA256_DIGEST_MISSING")
    return digest


def utc_timestamp(value: object) -> datetime:
    need(type(value) is str and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value),
        "ARTIFACT_ATTEMPT_TIMESTAMP_INVALID")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def verify_run_identity(payload, *, repo, run_id, run_attempt, run_head_sha):
    """Preserve the ordered run predicate; emit only fixed refusal fields.

    Do not include response values: this diagnostic must be safe even when a
    response contains credentials, arbitrary strings or malformed containers.
    Identity conflicts still fail immediately, without retry or enumeration.
    """
    reason = "A1_RUN_ATTEMPT_REPOSITORY_OR_HEAD_MISMATCH:"
    need(type(payload) is dict, reason + "PAYLOAD_TYPE")
    need(type(payload.get("id")) is int and payload["id"] == run_id,
         reason + "ID")
    need(type(payload.get("run_attempt")) is int and
         payload["run_attempt"] == run_attempt, reason + "RUN_ATTEMPT")
    need(payload.get("head_sha") == run_head_sha, reason + "HEAD_SHA")
    need(payload.get("status") == "in_progress", reason + "STATUS")
    need(type(payload.get("repository")) is dict, reason + "REPOSITORY_TYPE")
    need(payload["repository"].get("full_name") == repo,
         reason + "REPOSITORY_FULL_NAME")
    need(type(payload["repository"].get("id")) is int and
         payload["repository"]["id"] > 0, reason + "REPOSITORY_ID")
    need(type(payload.get("head_repository")) is dict,
         reason + "HEAD_REPOSITORY_TYPE")
    need(type(payload["head_repository"].get("id")) is int and
         payload["head_repository"]["id"] > 0, reason + "HEAD_REPOSITORY_ID")


def check_a1_visibility(repo, run_id, artifact_id, artifact_name, token, *,
                        run_attempt, run_head_sha, execution_source,
                        opener, pause, attempts, delay_seconds):
    """Witness the pinned v7 REST enumeration, never the separate Twirp view.

    The run-attempt lookup and EVERY list page share the existing eight-request
    ceiling. A missing item can consume another request after the same 2s pause;
    pagination never resets the budget. No scientific command is run here.
    """
    need(type(run_attempt) is int and 0 < run_attempt < 2 ** 63 and
         all(type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value)
             for value in (run_head_sha, execution_source)),
         "A1_EXACT_ATTEMPT_AND_SOURCE_REQUIRED")
    run = None
    rows, total, page = [], None, 1
    for attempt in range(1, attempts + 1):
        endpoint = (f"{API_URL}/repos/{repo}/actions/runs/{run_id}/attempts/{run_attempt}"
                    if run is None else
                    f"{API_URL}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100&page={page}")
        request = urllib.request.Request(endpoint, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "audio-pipeline-same-run-readback-gate",
        })
        try:
            with opener(request, timeout=10) as response:
                need(response.status == 200 and response.url == endpoint,
                     "ARTIFACT_API_REDIRECT_OR_STATUS_DRIFT")
                cap = 65536 if run is None else A1_LIST_RESPONSE_CAP
                data = response.read(cap + 1)
                need(0 < len(data) <= cap, "ARTIFACT_METADATA_EMPTY_OR_OVERSIZE")
                payload = json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
            if run is None:
                verify_run_identity(payload, repo=repo, run_id=run_id,
                                    run_attempt=run_attempt, run_head_sha=run_head_sha)
                references = payload.get("referenced_workflows")
                expected = f"{repo}/.github/workflows/quality.yml@{execution_source}"
                need(type(references) is list,
                     "A1_EXECUTION_SOURCE_NOT_IN_ACTUAL_QUALITY_WORKFLOW")
                quality = [ref for ref in references if type(ref) is dict and
                           type(ref.get("path")) is str and ref["path"].startswith(
                               f"{repo}/.github/workflows/quality.yml@")]
                need(len(quality) == 1 and quality[0]["path"] == expected and
                     quality[0].get("sha") == execution_source,
                     "A1_EXECUTION_SOURCE_NOT_IN_ACTUAL_QUALITY_WORKFLOW")
                utc_timestamp(payload.get("run_started_at"))
                run = payload
                continue
            need(type(payload) is dict and type(payload.get("total_count")) is int and
                 0 <= payload["total_count"] <= 1000 and
                 type(payload.get("artifacts")) is list and
                 len(payload["artifacts"]) <= 100,
                 "A1_ARTIFACT_LIST_SCHEMA_OR_BOUND_INVALID")
            if total is None:
                total = payload["total_count"]
            need(payload["total_count"] == total and
                 len(payload["artifacts"]) == min(100, max(0, total - 100 * (page - 1))),
                 "A1_ARTIFACT_LIST_INCOMPLETE_OR_CHANGED")
            rows.extend(payload["artifacts"])
            need(all(type(row) is dict and type(row.get("id")) is int and
                     0 < row["id"] < 2 ** 63 and type(row.get("name")) is str
                     for row in rows) and len({row["id"] for row in rows}) == len(rows),
                 "A1_ARTIFACT_LIST_DUPLICATE_OR_INVALID_ID")
            if len(rows) < total:
                page += 1
                continue
            matches = [row for row in rows
                       if row["id"] == artifact_id or row["name"] == artifact_name]
            if matches:
                need(len(matches) == 1, "A1_ARTIFACT_NAME_OR_ID_NOT_UNIQUE")
                artifact = matches[0]
                digest = verify_metadata(artifact, name=artifact_name,
                                         run_id=run_id, artifact_id=artifact_id)
                source = artifact["workflow_run"]
                need(source.get("head_sha") == run_head_sha and
                     type(source.get("repository_id")) is int and
                     source.get("repository_id") == run["repository"]["id"] and
                     type(source.get("head_repository_id")) is int and
                     source.get("head_repository_id") == run["head_repository"]["id"] and
                     utc_timestamp(artifact.get("created_at")) >=
                     utc_timestamp(run["run_started_at"]),
                     "A1_ARTIFACT_WRONG_SOURCE_OR_PREVIOUS_ATTEMPT")
                return attempt, digest
            rows, total, page = [], None, 1
        except urllib.error.HTTPError as error:
            if error.code not in (404, 502, 503):
                raise NotAdmitted("ARTIFACT_METADATA_HTTP_HARD_FAILURE_" + str(error.code)) from None
            rows, total, page = [], None, 1
        except (urllib.error.URLError, TimeoutError) as error:
            raise NotAdmitted("ARTIFACT_METADATA_NETWORK_OR_TLS_FAILURE_" +
                              type(error).__name__) from None
        if attempt < attempts:
            pause(delay_seconds)
    raise NotAdmitted("ARTIFACT_NOT_VISIBLE_WITHIN_BOUNDED_SAME_RUN_RETRY")


def check_visibility(repo: str, run_id: int, artifact_id: int,
                     artifact_name: str, token: str, *,
                     opener=None, pause=None, attempts: int = MAX_ATTEMPTS,
                     delay_seconds: int = SLEEP_SECONDS,
                     run_attempt=None, run_head_sha=None,
                     execution_source=None) -> tuple[int, str]:
    checked_args(repo, run_id, artifact_id, artifact_name, token)
    need(type(attempts) is int and 1 <= attempts <= MAX_ATTEMPTS and
         type(delay_seconds) is int and 0 <= delay_seconds <= SLEEP_SECONDS,
         "UNBOUNDED_VISIBILITY_RETRY")
    if opener is None:
        opener = (urllib.request.build_opener(NoRedirect()).open
                  if artifact_name.startswith((A1_PREFIX, T3S1_PREFIX)) else urllib.request.urlopen)
    if pause is None:
        pause = time.sleep
    # Only the observed T3-S1 failure joins A1's unchanged REST identity gate.
    if artifact_name.startswith((A1_PREFIX, T3S1_PREFIX)):
        return check_a1_visibility(
            repo, run_id, artifact_id, artifact_name, token,
            run_attempt=run_attempt, run_head_sha=run_head_sha,
            execution_source=execution_source, opener=opener, pause=pause,
            attempts=attempts, delay_seconds=delay_seconds)
    need(run_attempt is None and run_head_sha is None and execution_source is None,
         "A1_IDENTITY_FLAGS_ON_OTHER_STAGE")
    endpoint = f"{API_URL}/repos/{repo}/actions/artifacts/{artifact_id}"
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            endpoint, headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "audio-pipeline-same-run-readback-gate",
            })
        try:
            with opener(request, timeout=10) as response:
                need(response.status == 200 and
                     response.url == endpoint,
                     "ARTIFACT_API_REDIRECT_OR_STATUS_DRIFT")
                data = response.read(65537)
                need(0 < len(data) <= 65536,
                     "ARTIFACT_METADATA_EMPTY_OR_OVERSIZE")
                payload = json.loads(data.decode("utf-8"),
                                     object_pairs_hook=reject_duplicates)
                return attempt, verify_metadata(
                    payload, name=artifact_name, run_id=run_id,
                    artifact_id=artifact_id)
        except urllib.error.HTTPError as error:
            # Temporary absence is the ONLY permitted missing-state retry;
            # permanently missing artifact must leave mandatory job RED.
            if error.code not in (404, 502, 503):
                raise NotAdmitted("ARTIFACT_METADATA_HTTP_HARD_FAILURE_" +
                                  str(error.code)) from None
            if attempt == attempts:
                raise NotAdmitted(
                    "ARTIFACT_NOT_VISIBLE_WITHIN_BOUNDED_SAME_RUN_RETRY"
                ) from None
            pause(delay_seconds)
        except (urllib.error.URLError, TimeoutError) as error:
            # Unknown network/TLS/certificate problem is not an acceptable
            # artifact absence witness; fail closed, never switch mirrors.
            raise NotAdmitted(
                "ARTIFACT_METADATA_NETWORK_OR_TLS_FAILURE_" +
                type(error).__name__) from None
    raise NotAdmitted("ARTIFACT_VISIBILITY_UNREACHABLE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--run-attempt", type=int)
    parser.add_argument("--run-head-sha")
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    try:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GH_TOKEN", "")
        attempt, digest = check_visibility(
            repo, args.run_id, args.artifact_id,
            args.artifact_name, token, run_attempt=args.run_attempt,
            run_head_sha=args.run_head_sha, execution_source=args.execution_source)
    except (NotAdmitted, ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit("FE09_ARTIFACT_VISIBILITY_NOT_ADMITTED: " +
                         str(error)) from None
    # No token or URL value is emitted in output.
    print("FE09_EXACT_RUN_ARTIFACT_VISIBLE_BEFORE_PINNED_DOWNLOAD",
          args.run_id, args.artifact_id, "attempt=" + str(attempt), digest)
    if args.artifact_name.startswith(A1_PREFIX):
        print("FE09_A1_REST_LIST_RUN_ATTEMPT_SOURCE_BOUND",
              args.run_attempt, args.run_head_sha, args.execution_source)
    elif args.artifact_name.startswith(T3S1_PREFIX):
        print("FE09_T3S1_REST_LIST_RUN_ATTEMPT_SOURCE_BOUND",
              args.run_attempt, args.run_head_sha, args.execution_source)


if __name__ == "__main__":
    main()
