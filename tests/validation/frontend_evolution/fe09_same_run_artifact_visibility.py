#!/usr/bin/env python3
"""Bounded same-run GitHub Artifact visibility witness before pinned download.

GitHub artifact listing can briefly lag upload finalization. This tool does
NOT download, validate PCM, waive failure, or replace actions/download-artifact.
The immutable same-run id/name/source check plus downstream full 4-member
SHA256/negative/source checks remain mandatory. Read-only GitHub API ONLY.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

MAX_ATTEMPTS = 8
SLEEP_SECONDS = 2
API_URL = "https://api.github.com"


class NotAdmitted(ValueError):
    pass


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
         re.fullmatch(r"(?:frontend-fe09-t2b-b1s0-owner-spsc|frontend-fe09-t2b-b1s1-source-apx3)-[0-9]+",
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


def check_visibility(repo: str, run_id: int, artifact_id: int,
                     artifact_name: str, token: str, *,
                     opener=None, pause=None, attempts: int = MAX_ATTEMPTS,
                     delay_seconds: int = SLEEP_SECONDS) -> tuple[int, str]:
    checked_args(repo, run_id, artifact_id, artifact_name, token)
    need(type(attempts) is int and 1 <= attempts <= MAX_ATTEMPTS and
         type(delay_seconds) is int and 0 <= delay_seconds <= SLEEP_SECONDS,
         "UNBOUNDED_VISIBILITY_RETRY")
    if opener is None:
        opener = urllib.request.urlopen
    if pause is None:
        pause = time.sleep
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
    args = parser.parse_args()
    try:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GH_TOKEN", "")
        attempt, digest = check_visibility(
            repo, args.run_id, args.artifact_id,
            args.artifact_name, token)
    except (NotAdmitted, ValueError, OSError, json.JSONDecodeError) as error:
        raise SystemExit("FE09_ARTIFACT_VISIBILITY_NOT_ADMITTED: " +
                         str(error)) from None
    # No token or URL value is emitted in output.
    print("FE09_EXACT_RUN_ARTIFACT_VISIBLE_BEFORE_PINNED_DOWNLOAD",
          args.run_id, args.artifact_id, "attempt=" + str(attempt), digest)


if __name__ == "__main__":
    main()
