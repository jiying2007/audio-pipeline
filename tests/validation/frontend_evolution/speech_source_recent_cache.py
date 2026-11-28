"""Bounded recovery transport for previously admitted offset-0 FE03 source.

A live artifact digest is transport integrity, NOT corpus authority. The
caller must apply the unchanged independent source_check to the extracted
original members; no previous score or other corpus is admitted here.
"""
from __future__ import annotations

import re
import time

REPO_ID = 1347377137
VERIFY_WORKFLOW_ID = 345001523
RUNS_LIMIT = 20
ARTIFACTS_LIMIT = 10
MAX_ZIP_BYTES = 256 * 1024 * 1024
RUNS_ENDPOINT = (
    "/actions/runs?branch=main&event=push&status=success&per_page=20"
)
FIELDS = {"run_id", "run_number", "main_sha", "artifact_id",
          "artifact_name", "zip_bytes", "zip_sha256"}


class RecoveryError(ValueError):
    """Only fixed policy reason codes are exposed."""


def need(condition, reason):
    if not condition:
        raise RecoveryError(reason)


def positive_int(value):
    return type(value) is int and value > 0


def digest(value, width):
    return (type(value) is str and re.fullmatch("[0-9a-f]{" + str(width) + "}", value)
            is not None and value != "0" * width)


def same_repo(value):
    return type(value) is dict and type(value.get("id")) is int and value["id"] == REPO_ID


def run_identity(run):
    need(type(run) is dict and positive_int(run.get("id")) and
         positive_int(run.get("run_number")) and
         run.get("workflow_id") == VERIFY_WORKFLOW_ID and
         run.get("path") == ".github/workflows/verify.yml" and
         run.get("name") == "Verify" and run.get("head_branch") == "main" and
         run.get("event") == "push" and run.get("status") == "completed" and
         run.get("conclusion") == "success" and digest(run.get("head_sha"), 40) and
         same_repo(run.get("repository")) and same_repo(run.get("head_repository")),
         "RECENT_CACHE_RUN_IDENTITY_REJECTED")
    return {"run_id": run["id"], "run_number": run["run_number"], "main_sha": run["head_sha"]}


def artifact_identity(artifact, run):
    origin = artifact.get("workflow_run") if type(artifact) is dict else None
    name = "frontend-speech-" + str(run["run_id"])
    value = artifact.get("digest") if type(artifact) is dict else None
    need(type(origin) is dict and positive_int(artifact.get("id")) and
         artifact.get("name") == name and artifact.get("expired") is False and
         positive_int(artifact.get("size_in_bytes")) and
         artifact["size_in_bytes"] <= MAX_ZIP_BYTES and
         type(value) is str and value.startswith("sha256:") and digest(value[7:], 64) and
         origin.get("id") == run["run_id"] and origin.get("head_sha") == run["main_sha"] and
         origin.get("head_branch") == "main" and origin.get("repository_id") == REPO_ID and
         origin.get("head_repository_id") == REPO_ID,
         "RECENT_CACHE_ARTIFACT_IDENTITY_REJECTED")
    return {**run, "artifact_id": artifact["id"], "artifact_name": name,
            "zip_bytes": artifact["size_in_bytes"], "zip_sha256": value[7:]}


def validate_origin(origin):
    need(type(origin) is dict and set(origin) == FIELDS and
         all(positive_int(origin[key]) for key in ("run_id", "run_number", "artifact_id", "zip_bytes")) and
         origin["zip_bytes"] <= MAX_ZIP_BYTES and digest(origin["main_sha"], 40) and
         digest(origin["zip_sha256"], 64) and
         origin["artifact_name"] == "frontend-speech-" + str(origin["run_id"]),
         "RECENT_CACHE_RECEIPT_ORIGIN_REJECTED")
    return origin


def discover(api, deadline, commit, original_run):
    """At most one selected successor, no artifact search by score or source data."""
    need(digest(commit, 40) and positive_int(original_run), "RECENT_CACHE_BAD_EXECUTION_IDENTITY")
    need(time.monotonic() < deadline, "RECENT_CACHE_DEADLINE")
    listing = api(RUNS_ENDPOINT, deadline, "RECENT_RUNS")
    rows = listing.get("workflow_runs") if type(listing) is dict else None
    need(type(rows) is list and len(rows) <= RUNS_LIMIT, "RECENT_CACHE_RUN_LIST_REJECTED")
    candidates = []
    for row in rows:
        need(type(row) is dict, "RECENT_CACHE_RUN_LIST_REJECTED")
        if row.get("workflow_id") != VERIFY_WORKFLOW_ID:
            continue
        identity = run_identity(row)
        if identity["run_id"] != original_run and identity["main_sha"] != commit:
            candidates.append(identity)
    need(candidates and len({r["run_id"] for r in candidates}) == len(candidates) and
         len({r["run_number"] for r in candidates}) == len(candidates),
         "RECENT_CACHE_NO_UNIQUE_SUCCESSOR")
    chosen = max(candidates, key=lambda row: row["run_number"])
    run = api("/actions/runs/" + str(chosen["run_id"]), deadline, "RECENT_RUN")
    need(run_identity(run) == chosen, "RECENT_CACHE_RUN_CHANGED")
    name = "frontend-speech-" + str(chosen["run_id"])
    listing = api("/actions/runs/" + str(chosen["run_id"]) +
                  "/artifacts?name=" + name + "&per_page=10", deadline, "RECENT_ARTIFACTS")
    rows = listing.get("artifacts") if type(listing) is dict else None
    need(type(rows) is list and len(rows) == 1 and listing.get("total_count") == 1,
         "RECENT_CACHE_NO_UNIQUE_ARTIFACT")
    origin = artifact_identity(rows[0], chosen)
    artifact = api("/actions/artifacts/" + str(origin["artifact_id"]), deadline, "RECENT_ARTIFACT")
    need(artifact_identity(artifact, chosen) == origin, "RECENT_CACHE_ARTIFACT_CHANGED")
    need(time.monotonic() < deadline, "RECENT_CACHE_DEADLINE")
    return validate_origin(origin)
