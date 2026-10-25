#!/usr/bin/env python3
"""FE09 F1 R1 source bootstrap and bounded, pure metadata validators.

This module does not start the F1 launcher, engineering fixtures or DSP targets.
Source admission and workflow scheduling are not external execution approval.
The protected-base copy of this module is the policy oracle for later changes.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time


EXPERIMENT = "FE09-T3S3-F1-TARGET-LIFETIME-AND-IMAGE-RSS-R1"
REGISTERED_BRANCH = "research/fe09-t3s3-f1-rss-20261024"
REPOSITORY = "jiying2007/audio-pipeline"
REPOSITORY_ID = 1347377137
D = "92a7546a75cfe0d8aca132c7ee5996dcf0005c74"
REG = "docs/research/frontend-evolution-v1/FE09_T3S3_F1_RSS_PREREGISTRATION_R1_20261024"
SOURCE = "tests/validation/frontend_evolution/fe09_t3s3_f1_rss_qualification.py"
HERE = "tests/validation/frontend_evolution/"
IMPLEMENTATION = tuple(HERE + name for name in (
    "fe09_t3s3_f1_rss_launcher.c", "fe09_t3s3_f1_rss_observer.c",
    "fe09_t3s3_f1_rss_qualification.py", "fe09_t3s3_f1_build/CMakeLists.txt",
    "test_fe09_t3s3_f1_rss_qualification.py", "fe09_t3s3_f1_rss_fixture.c"))
HOOKS = (".github/workflows/verify.yml", ".github/workflows/quality.yml",
         ".github/scripts/verify-docs-gate.sh")
DOC_DIGESTS = {
    "README.md": "a44011a7f105470c959d1009aaa8b1c44d5e1e03412576c1d4fe3d31b8579190",
    "test-contract.json": "9c5592803292ecf0c42be88a1e8f3afd2256ae24bb3e98c2d515a94b87555d6e",
    "source-lock.json": "c2e4454f960bcb70e84184effd335f53a2245145d6bced77c0dbb5ed35144575",
    "EXECUTION_BASELINE.json": "bf01d6a3bd8e2b022dc18eb50173366cba748d6489ea02a0c1f5e3844fa88d9e",
    "negative-controls.json": "f5b9d27f0492fd4322b3d4cb6df9f7af8e9fbe340d3013edd31621e993e3bfea",
}
FIVE_READ = dict.fromkeys(("contents", "packages", "actions", "issues", "pull-requests"), "read")
SOURCE_ONLY = "SOURCE_METADATA_ONLY"
OUT_OF_SCOPE = "F1_SOURCE_METADATA_ONLY_OUT_OF_SCOPE"
COMPLETE = "FE09_T3S3_F1_R1_COMPLETE_RSS_OBSERVATION_NO_DEVICE_PROMOTION"
SCIENCE_EXECUTION_ENABLED = False
METADATA_BYTES = 2 * 1024 * 1024
GIT_SECONDS = 5


class Rejected(ValueError):
    """A named first violated admission predicate, never an asserted PASS."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(reason + (": " + detail if detail else ""))


def require(condition: bool, reason: str, detail: str = "") -> None:
    if not condition:
        raise Rejected(reason, detail)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes, cap: int = METADATA_BYTES) -> object:
    require(type(raw) is bytes and len(raw) <= cap, "F1R1_SERIALIZED_BYTES_LIMIT")

    def pairs(items: list[tuple[str, object]]) -> dict:
        value = {}
        for key, item in items:
            require(key not in value, "F1R1_DUPLICATE_JSON_KEY", key)
            value[key] = item
        return value

    def bad_constant(value: str) -> object:
        raise Rejected("F1R1_NONFINITE_NUMBER", value)

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=bad_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Rejected("F1R1_INVALID_JSON", str(exc)) from exc


def integer(value: object, low: int = 0, high: int = (1 << 63) - 1) -> bool:
    return type(value) is int and low <= value <= high


def finite(value: object, low: float = 0) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= low


def strict_UTC_seconds(value: object) -> int:
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None,
            "F1R1_STRICT_UTC_TIMESTAMP")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise Rejected("F1R1_STRICT_UTC_TIMESTAMP") from exc
    return calendar.timegm(parsed.timetuple())


def stage_admission(original_job_deadline_epoch_ns: int,
                    stage_started_epoch_ns: int, stage_started_monotonic_ns: int) -> dict:
    """Save the admitted integer duration itself; never subtract big floats."""
    require(all(integer(n) for n in (original_job_deadline_epoch_ns,
                                     stage_started_epoch_ns, stage_started_monotonic_ns)),
            "F1R1_STRICT_INTEGER_TIME")
    effective_ns = min(180_000_000_000,
                       original_job_deadline_epoch_ns - stage_started_epoch_ns - 60_000_000_000)
    require(effective_ns == 180_000_000_000, "INSUFFICIENT_F1_STAGE_WINDOW")
    return {"stage_started_epoch_ns": stage_started_epoch_ns,
            "stage_started_monotonic_ns": stage_started_monotonic_ns,
            "admitted_stage_duration_ns": effective_ns,
            "stage_deadline_monotonic_ns": stage_started_monotonic_ns + effective_ns,
            "original_job_deadline_epoch_ns": original_job_deadline_epoch_ns,
            "archive_reserve_ns": 60_000_000_000}


def enforce_deadline(started_ns: int, finished_ns: int, duration_ns: int,
                     reason: str) -> None:
    require(all(integer(n) for n in (started_ns, finished_ns, duration_ns)) and
            started_ns <= finished_ns <= started_ns + duration_ns, reason)


def engineering_deadlines(started_ns: int, enclosing_deadline_ns: int) -> dict:
    require(integer(started_ns) and integer(enclosing_deadline_ns) and
            enclosing_deadline_ns - started_ns >= 1_000_000_000,
            "F1R1_ENGINEERING_FULL_WINDOW_REQUIRED")
    return {"invocation_started_monotonic_ns": started_ns,
            "work_deadline_monotonic_ns": started_ns + 800_000_000,
            "final_deadline_monotonic_ns": started_ns + 1_000_000_000,
            "admitted_invocation_duration_ns": 1_000_000_000,
            "cleanup_reserve_ns": 200_000_000}


def validate_engineering_completion(record: dict) -> None:
    require(record["admitted_invocation_duration_ns"] == 1_000_000_000 and
            record["work_deadline_monotonic_ns"] == record["invocation_started_monotonic_ns"] + 800_000_000 and
            record["final_deadline_monotonic_ns"] == record["invocation_started_monotonic_ns"] + 1_000_000_000 and
            record["cleanup_reserve_ns"] == 200_000_000,
            "F1R1_ENGINEERING_CLOCK_RESTART")
    enforce_deadline(record["invocation_started_monotonic_ns"], record["encoding_finished_monotonic_ns"],
                     1_000_000_000, "F1R1_ENGINEERING_INVOCATION_LIMIT")
    require(record["owned_child_reaped"] is True, "F1R1_ENGINEERING_OWNED_REAP_REQUIRED")
    if record["fixture"] == "P04":
        require(record["timeout_trigger_monotonic_ns"] >= record["work_deadline_monotonic_ns"] and
                record["timeout_trigger_monotonic_ns"] <= record["reap_finished_monotonic_ns"] <= record["encoding_finished_monotonic_ns"] and
                record["signal_number"] == 9 and record["reason"] == "F1R1_ENGINEERING_INVOCATION_TIMEOUT",
                "F1R1_ENGINEERING_EXPECTED_OUTCOME")


WIRE_COMMON = ("v", "phase", "nonce", "ordinal", "pid", "ppid", "monotonic_ns")
WIRE_FIELDS = {
    "PREEXEC": set(WIRE_COMMON + ("rss_kib",)),
    "ENTRY": set(WIRE_COMMON),
    "RETURN": set(WIRE_COMMON + ("return_code",)),
    "ACK": {"v", "phase", "for_phase", "nonce", "ordinal", "child_pid", "launcher_pid", "monotonic_ns"},
}


def validate_wire(raw: bytes) -> dict:
    require(type(raw) is bytes and len(raw) <= 256, "F1R1_WIRE_BYTES_LIMIT")
    require(raw.endswith(b"\n") and b"\n" not in raw[:-1] and b"\r" not in raw and
            raw.isascii() and not any(byte in raw[:-1] for byte in (9, 11, 12, 32)),
            "F1R1_WIRE_ASCII_LF_FRAME")
    try:
        record = strict_json(raw, 256)
    except Rejected as exc:
        if exc.reason == "F1R1_DUPLICATE_JSON_KEY":
            raise Rejected("F1R1_WIRE_DUPLICATE_JSON_KEY") from exc
        raise
    require(type(record) is dict and record.get("phase") in WIRE_FIELDS,
            "F1R1_WIRE_FIELD_SET")
    phase = record["phase"]
    require(set(record) == WIRE_FIELDS[phase], "F1R1_WIRE_FIELD_SET")
    require(type(record["v"]) is int and record["v"] == 1 and
            integer(record["ordinal"], 1, 36) and integer(record["monotonic_ns"]) and
            type(record["nonce"]) is str and re.fullmatch("[0-9a-f]{64}", record["nonce"]),
            "F1R1_WIRE_FIELD_TYPES")
    pids = ("child_pid", "launcher_pid") if phase == "ACK" else ("pid", "ppid")
    require(all(integer(record[k], 1, (1 << 31) - 1) for k in pids), "F1R1_STRICT_INTEGER_PID")
    if phase == "ACK":
        require(record["for_phase"] in ("PREEXEC", "ENTRY", "RETURN"), "F1R1_WIRE_FIELD_SET")
    if phase == "PREEXEC":
        require(integer(record["rss_kib"]), "F1R1_WIRE_FIELD_TYPES")
    if phase == "RETURN":
        require(integer(record["return_code"], -(1 << 31), (1 << 31) - 1), "F1R1_WIRE_FIELD_TYPES")
    return record


def parse_proc_status(raw: bytes) -> dict:
    require(type(raw) is bytes and len(raw) <= 8192, "F1R1_PROC_STATUS_BYTES_LIMIT")
    required = {"Pid", "PPid", "NSpid", "VmHWM", "VmRSS", "Threads"}
    values = {}
    for line in raw.decode("utf-8", errors="strict").splitlines():
        name, sep, value = line.partition(":")
        if name not in required:
            continue
        require(sep == ":" and name not in values, "F1R1_DUPLICATE_PROC_FIELD", name)
        values[name] = value.strip()
    require(set(values) == required, "F1R1_REQUIRED_PROC_FIELDS")
    parsed = {}
    for name in ("Pid", "PPid", "Threads"):
        require(re.fullmatch("[0-9]+", values[name]) is not None, "F1R1_STRICT_INTEGER_PID")
        parsed[name] = int(values[name])
        require(integer(parsed[name], 1, (1 << 31) - 1), "F1R1_STRICT_INTEGER_PID")
    parts = values["NSpid"].split()
    require(parts and all(re.fullmatch("[0-9]+", p) and integer(int(p), 1, (1 << 31) - 1) for p in parts),
            "F1R1_PID_NAMESPACE_IDENTITY")
    parsed["NSpid"] = [int(p) for p in parts]
    parsed["namespace_mapping_sha256"] = sha(json.dumps(parsed["NSpid"], separators=(",", ":")).encode("ascii"))
    for name in ("VmHWM", "VmRSS"):
        match = re.fullmatch(r"([0-9]+)\s+kB", values[name])
        require(match is not None, "F1R1_PROC_UNIT")
        parsed[name + "_kib"] = int(match[1])
        require(integer(parsed[name + "_kib"]), "F1R1_PROC_COUNTER_RANGE")
        parsed[name + "_bytes"] = parsed[name + "_kib"] * 1024
    return parsed


def parse_proc_stat(raw: bytes) -> dict:
    require(type(raw) is bytes and len(raw) <= 1536, "F1R1_RAW_STAT_BYTES_LIMIT")
    text = raw.decode("utf-8", errors="strict")
    left, right = text.find("("), text.rfind(") ")
    require(left > 0 and right > left, "F1R1_RAW_STAT_FIELDS")
    pid_text = text[:left].strip()
    fields = text[right + 2:].split()
    require(re.fullmatch("[0-9]+", pid_text) is not None and len(fields) >= 20 and
            re.fullmatch("[0-9]+", fields[1]) is not None and
            re.fullmatch("[0-9]+", fields[19]) is not None,
            "F1R1_RAW_STAT_FIELDS")
    pid, ppid, ticks = int(pid_text), int(fields[1]), int(fields[19])
    require(integer(pid, 1, (1 << 31) - 1) and integer(ppid, 1, (1 << 31) - 1) and integer(ticks),
            "F1R1_STRICT_INTEGER_PID")
    return {"pid": pid, "ppid": ppid, "start_ticks": ticks, "comm": text[left + 1:right]}


def validate_wire_sequence(messages: list[bytes], observations: dict,
                           *, nonce: str, ordinal: int, child_pid: int, launcher_pid: int) -> list[dict]:
    require(len(messages) == 6, "F1R1_CHECKPOINT_COVERAGE")
    rows = [validate_wire(raw) for raw in messages]
    previous = -1
    for index, phase in enumerate(("PREEXEC", "ENTRY", "RETURN")):
        child, ack = rows[2 * index:2 * index + 2]
        require(child["phase"] == phase and ack["phase"] == "ACK" and ack["for_phase"] == phase,
                "F1R1_CHECKPOINT_ORDER")
        require(child["ordinal"] == ordinal and ack["ordinal"] == ordinal, "F1R1_CASE_ORDINAL")
        require(child["nonce"] == nonce and ack["nonce"] == nonce and
                child["pid"] == ack["child_pid"] == child_pid and
                child["ppid"] == ack["launcher_pid"] == launcher_pid, "F1R1_ACK_BINDING")
        start, end = observations[phase]
        require(integer(start) and integer(end) and start <= end, "F1R1_OBSERVATION_INTERVAL")
        require(previous <= child["monotonic_ns"] <= start, "F1R1_CHECKPOINT_ORDER")
        require(end <= ack["monotonic_ns"], "F1R1_OBSERVATION_BEFORE_ACK")
        previous = ack["monotonic_ns"]
    return rows


def validate_schema(value: object, schema: dict) -> None:
    """Strict registered schema subset; no external references or coercions."""
    if "const" in schema:
        expected = schema["const"]
        require(type(value) is type(expected) and value == expected, "F1R1_FREEZE_SCHEMA")
    kind = schema.get("type")
    if kind == "object":
        require(type(value) is dict and set(value) == set(schema["required"]) and
                schema["additionalProperties"] is False, "F1R1_FREEZE_SCHEMA")
        for key, rule in schema["properties"].items():
            validate_schema(value[key], rule)
    elif kind == "string":
        require(type(value) is str, "F1R1_FREEZE_SCHEMA")
    elif kind == "integer":
        require(type(value) is int, "F1R1_FREEZE_SCHEMA")
    if "pattern" in schema:
        require(type(value) is str and re.fullmatch(schema["pattern"], value), "F1R1_FREEZE_SCHEMA")


def actual_provider_C(event: str, run: dict, association: list[dict] | None,
                      detail: dict, git_role: dict, *,
                      association_has_next_page: bool | None = None) -> dict:
    """Pure provider/Git binding, always before inspecting an approval body.

    Acquisition is deliberately absent from bootstrap. These arguments are only
    observations after a future bounded real acquisition, or labelled templates.
    """
    require(event in ("pull_request", "push"), "F1R1_EVENT_SCOPE_NO_SCIENCE")
    require(run.get("event") == event and oid(run.get("head_sha")), "F1R1_RUN_EVENT_SOURCE")
    if event == "push":
        source = run["head_sha"]
        require(type(association) is list and len(association) <= 100,
                "F1R1_MAIN_PROVIDER_ASSOCIATION_REQUIRED")
        require(association_has_next_page is False, "F1R1_COMPLETE_MAIN_PR_ASSOCIATION")
        require(all(integer(p.get("id"), 1) and integer(p.get("number"), 1) for p in association) and
                len({p["id"] for p in association}) == len(association) and
                len({p["number"] for p in association}) == len(association),
                "F1R1_UNIQUE_MAIN_PR_ASSOCIATION")
        matches = [p for p in association if p.get("merge_commit_sha") == source and
                   p.get("head", {}).get("ref") == REGISTERED_BRANCH and
                   p.get("base", {}).get("ref") == "main"]
        require(len(matches) == 1, "F1R1_UNIQUE_MAIN_PR_ASSOCIATION")
        selected = matches[0]
        require(detail.get("id") == selected["id"] and detail.get("number") == selected["number"] and
                detail.get("head", {}).get("sha") == selected.get("head", {}).get("sha"),
                "F1R1_MAIN_PROVIDER_ASSOCIATION_REQUIRED")
        require(detail.get("merged") is True and type(detail.get("merged_at")) is str and
                detail.get("merge_commit_sha") == source, "F1R1_ACTUAL_MERGED_PR_REQUIRED")
        strict_UTC_seconds(detail["merged_at"])
        require(git_role.get("S") == source and len(git_role.get("S_parents", [])) == 1,
                "F1R1_IMMUTABLE_MAIN_PARENT_B")
        base = git_role["S_parents"][0]
        candidate = detail.get("head", {}).get("sha")
        require(git_role.get("S_tree") == git_role.get("C_tree") and oid(git_role.get("C_tree")),
                "F1R1_FULL_TREE_EQUALITY")
    else:
        candidate = run["head_sha"]
        require(detail.get("head", {}).get("sha") == candidate, "F1R1_RUN_PR_ASSOCIATION")
        selected = [p for p in run.get("pull_requests", []) if p.get("number") == detail.get("number")]
        require(len(selected) == 1 and selected[0].get("head", {}).get("sha") == candidate,
                "F1R1_RUN_PR_ASSOCIATION")
        base = detail.get("base", {}).get("sha")
        require(git_role.get("M_parents") == [base, candidate], "F1R1_EXACT_PR_MERGE_PARENTS")
        require(git_role.get("M_tree") == git_role.get("C_tree") and oid(git_role.get("C_tree")),
                "F1R1_FULL_TREE_EQUALITY")
    require(oid(candidate) and oid(base), "F1R1_SOURCE_OID_REQUIRED")
    for side in ("head", "base"):
        repo_id = detail.get(side, {}).get("repo", {}).get("id")
        require(type(repo_id) is int and repo_id == REPOSITORY_ID, "F1R1_SAME_REPOSITORY_SCOPE")
    require(detail["head"].get("ref") == REGISTERED_BRANCH and detail["base"].get("ref") == "main",
            "F1R1_REGISTERED_BRANCH_SCOPE")
    require(oid(git_role.get("B_tree")), "F1R1_SOURCE_OID_REQUIRED")
    return {"C": candidate, "B": base, "C_tree": git_role["C_tree"], "B_tree": git_role["B_tree"],
            "PR_number": detail["number"], "actual_C_derived_before_freeze": True}


def validate_freeze_sweep(sweep: dict, *, schema: dict, source: dict,
                          expected_digests: dict, original_run_created_at: str) -> dict:
    """Complete issue/count/list/direct/issue readback; never does HTTP."""
    require(source.get("actual_C_derived_before_freeze") is True and oid(source.get("C")) and oid(source.get("B")),
            "F1R1_MAIN_PROVIDER_ASSOCIATION_REQUIRED")
    expected_user = {"login": "jiying2007", "id": 33591504, "type": "User"}
    expected_url = "https://api.github.com/repos/" + REPOSITORY + "/issues/845"
    repository = sweep["repository"]
    require(type(repository.get("id")) is int and repository["id"] == REPOSITORY_ID and
            repository.get("full_name") == REPOSITORY, "F1R1_FREEZE_REPOSITORY_IDENTITY")

    def exact_author(user: object) -> bool:
        return type(user) is dict and all(type(user.get(k)) is type(v) and user.get(k) == v
                                          for k, v in expected_user.items())

    for key in ("issue_before", "issue_after"):
        issue = sweep[key]
        require("pull_request" not in issue, "F1R1_FREEZE_ISSUE_NOT_PR")
        require(type(issue.get("id")) is int and issue["id"] == 6015285792 and
                issue.get("node_id") == "I_kwDOUE9X8c8AAAABZon6IA" and
                type(issue.get("number")) is int and issue["number"] == 845 and
                issue.get("created_at") == "2026-10-24T16:50:18Z" and
                issue.get("url") == expected_url and
                issue.get("repository_url") == "https://api.github.com/repos/" + REPOSITORY and
                exact_author(issue.get("user")), "F1R1_FREEZE_ISSUE_IDENTITY")
    comments = sweep["comments"]
    require(type(comments) is list and len(comments) <= 100 and
            integer(sweep["issue_before"].get("comments")) and
            sweep["issue_before"]["comments"] == len(comments) == sweep["issue_after"].get("comments") and
            type(sweep["issue_after"].get("comments")) is int and sweep.get("comments_has_next_page") is False,
            "F1R1_COMPLETE_COMMENT_LIST")
    require(all(integer(c.get("id"), 1) for c in comments) and len({c["id"] for c in comments}) == len(comments),
            "F1R1_COMPLETE_COMMENT_LIST")
    def parse_body(raw: bytes) -> dict:
        require(len(raw) <= 16384, "F1R1_FREEZE_BODY_BYTES_LIMIT")
        parsed = strict_json(raw, 16384)
        require(type(parsed) is dict, "F1R1_FREEZE_SCHEMA")
        require(parsed.get("experiment_id") == EXPERIMENT, "F1R1_EXACT_EXPERIMENT_IDENTITY")
        require(parsed.get("decision") == "F1_R1_APPROVE_EXACT_SOURCE_FOR_REGISTERED_PR_AND_MAIN_FIRST_EXECUTION",
                "F1R1_EXACT_EXECUTION_DECISION")
        validate_schema(parsed, schema)
        strict_UTC_seconds(parsed["reviewed_at_utc"])
        return parsed
    matching = []
    for comment in comments:
        if not exact_author(comment.get("user")):
            continue
        body = comment.get("body")
        require(type(body) is str, "F1R1_FREEZE_SCHEMA")
        if not body.lstrip().startswith("{"):
            continue
        raw = body.encode("utf-8")
        parsed = parse_body(raw)
        if parsed["source"]["reviewed_head_C"] == source["C"]:
            matching.append((comment, parsed, raw))
    require(matching, "F1R1_UNIQUE_MATCHING_C_FREEZE")
    require(len(matching) == 1, "F1R1_DUPLICATE_C_FREEZE")
    selected, listed_body, listed_raw = matching[0]
    direct = sweep["selected_comment"]
    require(exact_author(direct.get("user")), "F1R1_FREEZE_AUTHOR_IDENTITY")
    require(direct.get("issue_url") == expected_url and selected.get("issue_url") == expected_url,
            "F1R1_COMMENT_ISSUE_ASSOCIATION")
    require(type(selected.get("node_id")) is str and selected["node_id"], "F1R1_FIXED_COMMENT_IDENTITY")
    require(type(direct.get("body")) is str, "F1R1_FREEZE_SCHEMA")
    raw = direct["body"].encode("utf-8")
    body = parse_body(raw)
    created = strict_UTC_seconds(direct.get("created_at"))
    updated = strict_UTC_seconds(direct.get("updated_at"))
    reviewed = strict_UTC_seconds(body["reviewed_at_utc"])
    require(created == updated, "F1R1_FREEZE_COMMENT_EDITED")
    require(reviewed <= created, "F1R1_REVIEW_TIMESTAMP")
    require(created < strict_UTC_seconds(original_run_created_at), "F1R1_FREEZE_NOT_BEFORE_ORIGINAL_RUN")
    expected_source = {"reviewed_head_C": source["C"], "protected_base_B": source["B"],
                       "reviewed_tree_C": source["C_tree"], "protected_base_tree_B": source["B_tree"]}
    require(all(body["source"][k] == v for k, v in expected_source.items()), "F1R1_EXTERNAL_SOURCE_IDENTITY")
    require(body["digests"] == expected_digests, "F1R1_EXTERNAL_SOURCE_DIGEST")
    for key in ("id", "node_id", "created_at", "updated_at", "body"):
        require(type(direct.get(key)) is type(selected.get(key)) and direct.get(key) == selected.get(key),
                "F1R1_PRE_POST_FREEZE_STABILITY")
    require(body == listed_body and raw == listed_raw, "F1R1_PRE_POST_FREEZE_STABILITY")
    return {"id": selected["id"], "node_id": selected["node_id"],
            "author": expected_user, "issue_url": expected_url,
            "created_at": selected["created_at"], "updated_at": selected["updated_at"],
            "body": raw, "body_sha256": sha(raw), "source": expected_source}


def validate_freeze_pair(pre: dict, post: dict) -> None:
    require(pre == post, "F1R1_PRE_POST_FREEZE_STABILITY")


def oid(value: object) -> bool:
    return type(value) is str and re.fullmatch("[0-9a-f]{40}", value) is not None and value != "0" * 40


def bounded_file(path: Path, cap: int = METADATA_BYTES) -> bytes:
    require(not path.is_symlink() and path.is_file(), "F1R1_REGULAR_FILE_REQUIRED", str(path))
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    require(len(raw) <= cap, "F1R1_SERIALIZED_BYTES_LIMIT", str(path))
    return raw


def git(root: Path, *args: str, cap: int = METADATA_BYTES, allow_missing: bool = False) -> bytes | None:
    # Only bounded local object/diff reads are used, never fetch or network.
    try:
        p = subprocess.run(["git", "-c", f"safe.directory={root}", "-C", str(root), *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=GIT_SECONDS, check=False,
                           env={k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")})
    except subprocess.TimeoutExpired as exc:
        raise Rejected("F1R1_SOURCE_METADATA_DEADLINE") from exc
    require(len(p.stdout) <= cap and len(p.stderr) <= 65536, "F1R1_SOURCE_METADATA_BYTES_LIMIT")
    if p.returncode != 0:
        if allow_missing and p.returncode == 128:
            return None
        raise Rejected("F1R1_SOURCE_GIT_READ_FAILED", " ".join(args[:2]))
    return p.stdout


def object_bytes(root: Path, revision: str, path: str, *, missing: bool = False) -> bytes | None:
    require(oid(revision), "F1R1_SOURCE_OID_REQUIRED")
    require(path and not path.startswith("/") and ".." not in Path(path).parts,
            "F1R1_SOURCE_PATH_ESCAPE")
    raw = git(root, "show", f"{revision}:{path}", allow_missing=missing)
    if raw is None:
        # Distinguish a genuinely missing member from an unreadable revision.
        git(root, "cat-file", "-e", revision + "^{commit}")
        listing = git(root, "ls-tree", revision, "--", path)
        require(listing == b"", "F1R1_SOURCE_GIT_READ_FAILED", path)
        return None
    listing = git(root, "ls-tree", revision, "--", path)
    require(listing is not None and listing.startswith(b"100644 blob "),
            "F1R1_SOURCE_FILE_MODE", path)
    return raw


def parse_event(event_name: str, event: dict, checkout: str,
                parents: list[str]) -> dict:
    """Bind event roles; main merged-PR authority intentionally remains pending."""
    require(type(event) is dict, "F1R1_EVENT_OBJECT_REQUIRED")
    repository = event.get("repository", {})
    require(repository.get("full_name") == REPOSITORY and
            type(repository.get("id")) is int and repository["id"] == REPOSITORY_ID,
            "F1R1_SAME_REPOSITORY_SCOPE")
    require(oid(checkout) and all(oid(x) for x in parents), "F1R1_SOURCE_OID_REQUIRED")
    if event_name == "pull_request":
        pr = event.get("pull_request", {})
        head, base = pr.get("head", {}), pr.get("base", {})
        require(oid(head.get("sha")) and oid(base.get("sha")), "F1R1_SOURCE_OID_REQUIRED")
        require(parents == [base["sha"], head["sha"]], "F1R1_EXACT_PR_MERGE_PARENTS")
        same_repo = all(type(x.get("repo", {}).get("id")) is int and
                        x["repo"]["id"] == REPOSITORY_ID for x in (head, base))
        registered = same_repo and head.get("ref") == REGISTERED_BRANCH and base.get("ref") == "main"
        return {"event": event_name, "B": base["sha"], "C": head["sha"],
                "checkout": checkout, "registered_candidate": registered,
                "branch": head.get("ref"), "same_repository": same_repo,
                "provider_merged_PR_authority": False}
    if event_name == "push":
        require(event.get("ref") == "refs/heads/main" and event.get("after") == checkout,
                "F1R1_MAIN_EVENT_SOURCE")
        require(parents == [event.get("before")], "F1R1_IMMUTABLE_MAIN_PARENT_B")
        return {"event": event_name, "B": parents[0], "S": checkout,
                "checkout": checkout, "registered_candidate": False,
                "branch": "main", "same_repository": True,
                "provider_merged_PR_authority": False}
    require(event_name == "workflow_dispatch", "F1R1_EVENT_SCOPE_NO_SCIENCE")
    require(len(parents) == 1, "F1R1_SOURCE_RANGE_REQUIRED")
    return {"event": event_name, "B": parents[0], "checkout": checkout,
            "registered_candidate": False, "branch": None,
            "same_repository": True, "provider_merged_PR_authority": False}


def evaluate_scope(*, event: dict, changed: set[str], protected: set[str],
                   base_guard_present: bool, guard_origin: str | None,
                   execution_ready: bool, originals_match: bool = True) -> dict:
    """Pure scheduling decision, with no provider/source execution approval."""
    require(originals_match, "F1R1_FROZEN_F0_SOURCE_CHANGED")
    touches = sorted(changed & protected)
    if not base_guard_present:
        require(guard_origin is None, "F1R1_BOOTSTRAP_METADATA_ONLY")
        require(not execution_ready, "F1R1_BOOTSTRAP_ZERO_F1_PROCESSES")
        return {"disposition": SOURCE_ONLY, "f1_required": False,
                "bootstrap": True, "protected_changes": touches}
    require(guard_origin == event["B"], "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED")
    if event["event"] == "pull_request":
        require(not touches or event["registered_candidate"],
                "F1_OUT_OF_SCOPE_PROTECTED_CHANGE")
        required = event["registered_candidate"] and execution_ready
        if touches and event["registered_candidate"] and not execution_ready:
            # Source preparation remains explicit, never a completed science run.
            return {"disposition": SOURCE_ONLY, "f1_required": False,
                    "bootstrap": False, "protected_changes": touches}
    elif event["event"] == "push":
        # Local guard cannot invent the PR association; force the real job when
        # execution-ready protected inputs change. That job must derive S->PR.
        require(not touches or execution_ready, "F1_OUT_OF_SCOPE_PROTECTED_CHANGE")
        required = bool(touches) and execution_ready
    else:
        require(not touches, "F1_OUT_OF_SCOPE_PROTECTED_CHANGE")
        required = False
    return {"disposition": "F1_PROVIDER_ADMISSION_REQUIRED" if required else OUT_OF_SCOPE,
            "f1_required": bool(required), "bootstrap": False,
            "protected_changes": touches}


def validate_routing(view: dict) -> None:
    """Pure, independent expected-policy checks used by metadata controls."""
    require(view["candidate_protected_paths"] == view["protected_B_paths"],
            "F1R1_PROTECTED_BASE_POLICY_REQUIRED")
    for route, reason in (("fast_docs", "F1R1_GUARD_REQUIRED_ON_FAST_DOCS"),
                          ("fast_code", "F1R1_GUARD_REQUIRED_ON_FAST_CODE")):
        require(view[route].count("F1_R1_SOURCE_SCOPE_GUARD") == 1, reason)
    require(view["caller_permissions"] == FIVE_READ, "F1R1_FIVE_READ_CALLER_PERMISSIONS")
    require(view["child_permissions"] == FIVE_READ, "F1R1_FIVE_READ_CHILD_PERMISSIONS")
    require(view["top_permissions"] == {k: "read" for k in ("contents", "packages", "actions")},
            "F1R1_PERMISSION_CHANGE_SCOPE")
    require(not view["continue_on_error"], "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")
    require(view["guard_source"] == view["B"], "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED")
    require(view["B_main_closed"], "F1R1_PROTECTED_GUARD_BASE_CLOSURE_REQUIRED")
    require(view["bootstrap_launchers"] == 0, "F1R1_BOOTSTRAP_ZERO_F1_PROCESSES")
    if view["docs_only_execution_C"]:
        require(all(view[k] for k in ("f1_required", "caller_called", "run_f1",
                                      "child_selected", "summary_expect_quality",
                                      "summary_checks_disposition")),
                "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")


def workflow_projection(raw: bytes, workflow: str) -> bytes:
    """Conservative exact projection: an unrecognised structure fails closed.

    Existing unrelated job bodies may change. Shared header/impact/fast paths,
    quality caller, summary and F1 child stay byte-exact for unrelated changes.
    """
    text = raw.decode("utf-8")
    require(text.count("\njobs:\n") == 1, "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED")
    header, jobs = text.split("\njobs:\n", 1)
    matches = list(re.finditer(r"^  ([A-Za-z0-9_-]+):\s*$", jobs, re.M))
    require(matches and matches[0].start() == 0, "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED")
    names = [m.group(1) for m in matches]
    require(len(names) == len(set(names)), "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED")
    selected = {"impact", "fast-docs", "fast-code", "fast-gate", "quality", "summary"} if workflow == "verify" else {"frontend-rss-f1"}
    require(selected <= set(names), "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED")
    blocks = []
    for index, match in enumerate(matches):
        if match.group(1) in selected:
            end = matches[index + 1].start() if index + 1 < len(matches) else len(jobs)
            blocks.append(jobs[match.start():end])
    return (header + "\njobs:\n" + "".join(blocks)).encode()


def yaml_block(text: str, key: str, indent: int) -> str:
    """Read a canonical plain mapping block, rejecting missing/duplicate keys.

    Only reviewed workflow spelling is admitted at security-relevant locations.
    This is not a general YAML loader or an alias/merge-key interpreter.
    """
    matches = list(re.finditer(r"^" + " " * indent + re.escape(key) + r":\s*$", text, re.M))
    require(len(matches) == 1, "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED", key)
    start = text.find("\n", matches[0].start()) + 1
    rest = text[start:]
    end = re.search(r"^(?: {0," + str(indent) + r"})[^ #\n]", rest, re.M)
    return rest[:end.start()] if end else rest


def yaml_scalar(text: str, key: str, indent: int) -> str:
    matches = re.findall(r"^" + " " * indent + re.escape(key) + r": ([^\n]+)$", text, re.M)
    require(len(matches) == 1, "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED", key)
    return matches[0]


def permission_block(text: str, indent: int) -> dict:
    block = yaml_block(text, "permissions", indent)
    result = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(" " * (indent + 2) + r"([a-z-]+): (read|write|none)", line)
        require(match is not None and match[1] not in result,
                "F1R1_READ_ONLY_PERMISSION_SCOPE")
        result[match[1]] = match[2]
    return result


def validate_actual_routes(root: Path) -> dict:
    verify = bounded_file(root / HOOKS[0]).decode("utf-8")
    quality = bounded_file(root / HOOKS[1]).decode("utf-8")
    entry = bounded_file(root / HOOKS[2]).decode("utf-8")
    # Require canonical protected mappings, so apparent tokens in comments or
    # unrelated jobs do not satisfy the actual caller/child route.
    caller = yaml_block(verify, "quality", 2)
    child = yaml_block(quality, "frontend-rss-f1", 2)
    require(permission_block(verify, 0) == {k: "read" for k in ("contents", "packages", "actions")} and
            permission_block(quality, 0) == {k: "read" for k in ("contents", "packages", "actions")},
            "F1R1_PERMISSION_CHANGE_SCOPE")
    require(permission_block(caller, 4) == FIVE_READ, "F1R1_FIVE_READ_CALLER_PERMISSIONS")
    require(permission_block(child, 4) == FIVE_READ, "F1R1_FIVE_READ_CHILD_PERMISSIONS")
    require(yaml_scalar(caller, "needs", 4) == "[impact, fast-gate]" and
            yaml_scalar(caller, "if", 4) == "always() && needs.fast-gate.result == 'success' && (needs.impact.outputs.run_quality == 'true' || needs.impact.outputs.f1_required == 'true')",
            "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")
    calls = yaml_block(caller, "with", 4)
    require(yaml_scalar(calls, "run_f1", 6) == "${{ needs.impact.outputs.f1_required == 'true' }}" and
            yaml_scalar(calls, "run_extended", 6) == "${{ needs.impact.outputs.run_extended == 'true' }}",
            "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")
    require(yaml_scalar(child, "if", 4) == "inputs.run_extended || inputs.run_f1" and
            not re.search(r"^    continue-on-error:", child, re.M),
            "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")
    impact = yaml_block(verify, "impact", 2)
    require(yaml_scalar(yaml_block(impact, "outputs", 4), "f1_required", 6) == "${{ steps.f1_scope.outputs.f1_required }}" and
            impact.count("        id: f1_scope\n") == 1 and
            impact.count("        run: sh .github/scripts/verify-docs-gate.sh --f1-scope-only\n") == 1,
            "F1R1_GUARD_OUTPUT_REQUIRED")
    for name, reason in (("fast-docs", "F1R1_GUARD_REQUIRED_ON_FAST_DOCS"),
                         ("fast-code", "F1R1_GUARD_REQUIRED_ON_FAST_CODE")):
        require(yaml_block(verify, name, 2).count("          sh .github/scripts/verify-docs-gate.sh\n") == 1, reason)
    require("--guard-origin" in entry and "base + ':' + source" in entry and
            "F1_R1_SOURCE_SCOPE_GUARD" in entry and "'source-guard'" in entry,
            "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED")
    summary = yaml_block(verify, "summary", 2)
    require(yaml_scalar(summary, "EXPECT_QUALITY", 10) == "${{ needs.impact.outputs.run_quality == 'true' || needs.impact.outputs.f1_required == 'true' }}" and
            yaml_scalar(summary, "F1_REQUIRED", 10) == "${{ needs.impact.outputs.f1_required }}" and
            yaml_scalar(summary, "F1_DISPOSITION", 10) == "${{ needs.quality.outputs.f1_disposition }}" and
            'test "$F1_DISPOSITION" = ' + COMPLETE in summary,
            "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")
    call = yaml_block(quality, "workflow_call", 2)
    input_rule = yaml_block(yaml_block(call, "inputs", 4), "run_f1", 6)
    require(yaml_scalar(input_rule, "type", 8) == "boolean" and
            yaml_scalar(input_rule, "default", 8) == "false", "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")
    output_rule = yaml_block(yaml_block(call, "outputs", 4), "f1_disposition", 6)
    require(yaml_scalar(output_rule, "value", 8) == "${{ jobs.frontend-rss-f1.outputs.disposition }}" and
            yaml_scalar(yaml_block(child, "outputs", 4), "disposition", 6) == "${{ steps.f1_source.outputs.disposition }}",
            "F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")
    return {"actual_caller_and_child_five_read": True, "actual_docs_only_route_complete": True,
            "actual_summary_requires_F1_receipt": True,
            "hook_sha256": {name: sha(bounded_file(root / name)) for name in HOOKS}}


def effective_protected_diff(root: Path, base: str, head: str, changed: set[str],
                             protected: set[str]) -> set[str]:
    result = set(changed)
    for name, kind in ((HOOKS[0], "verify"), (HOOKS[1], "quality")):
        if name in changed:
            before = object_bytes(root, base, name)
            after = object_bytes(root, head, name)
            if workflow_projection(before, kind) == workflow_projection(after, kind):
                result.remove(name)
    # The shared shell entry has executable top-level effects; no permissive
    # line-filter is a proof of its noninterference.
    return result & protected


def source_guard(root: Path, event_name: str, event: dict,
                 guard_origin: str | None) -> dict:
    started = time.monotonic_ns()
    checkout = git(root, "rev-parse", "HEAD").decode().strip()
    parents = git(root, "show", "-s", "--format=%P", checkout).decode().split()
    roles = parse_event(event_name, event, checkout, parents)
    base = roles["B"]
    head = roles.get("C", checkout)
    actual_base_guard = object_bytes(root, base, SOURCE, missing=True)
    present = actual_base_guard is not None
    require((guard_origin is None and not present) or (guard_origin == base and present),
            "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED")
    if present:
        require(bounded_file(Path(__file__).resolve()) == actual_base_guard,
                "F1R1_ACTUAL_PROTECTED_B_GUARD_REQUIRED", "executed bytes differ from B")
    if event_name == "pull_request":
        require(git(root, "rev-parse", checkout + "^{tree}") == git(root, "rev-parse", head + "^{tree}"),
                "F1R1_FULL_TREE_EQUALITY")
    policy_raw = object_bytes(root, base, REG + "/source-lock.json", missing=True)
    if policy_raw is None:
        require(not present, "F1R1_PROTECTED_BASE_POLICY_REQUIRED")
        policy_raw = bounded_file(root / REG / "source-lock.json")
        require(sha(policy_raw) == DOC_DIGESTS["source-lock.json"], "F1R1_BOOTSTRAP_DESIGN_IDENTITY")
    policy = strict_json(policy_raw)
    originals = [r for r in policy["files"] if r["role"].startswith("IMMUTABLE_ORIGINAL")]
    require(len(originals) == 96 and len({r["path"] for r in originals}) == 96,
            "F1R1_PROTECTED_BASE_POLICY_REQUIRED")
    for row in originals:
        raw = object_bytes(root, head, row["path"])
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"],
                "F1R1_FROZEN_F0_SOURCE_CHANGED", row["path"])
        require(bounded_file(root / row["path"]) == raw, "F1R1_SOURCE_WORKTREE_DRIFT", row["path"])
    contract_raw = bounded_file(root / REG / "test-contract.json")
    contract = strict_json(contract_raw)
    execution_ready = contract.get("document_state") == "PROTOCOL_REVIEWED_EXTERNAL_COMMENT_REQUIRED_AT_RUNTIME"
    if not execution_ready:
        for filename, expected in DOC_DIGESTS.items():
            require(sha(bounded_file(root / REG / filename)) == expected,
                    "F1R1_BOOTSTRAP_DESIGN_IDENTITY", filename)
    require(contract.get("id") == EXPERIMENT, "F1R1_EXPERIMENT_IDENTITY")
    changed_raw = git(root, "diff", "--name-only", "-z", base, head, "--")
    changed = {p.decode("utf-8") for p in changed_raw.split(b"\0") if p}
    protected = {r["path"] for r in policy["files"]} | {REG + "/" + n for n in DOC_DIGESTS} | set(IMPLEMENTATION) | set(HOOKS)
    if present and not roles["registered_candidate"]:
        touched = effective_protected_diff(root, base, head, changed, protected)
        changed = (changed - protected) | touched
    decision = evaluate_scope(event=roles, changed=changed, protected=protected,
                              base_guard_present=present, guard_origin=guard_origin,
                              execution_ready=execution_ready)
    routes = validate_actual_routes(root)
    require(time.monotonic_ns() - started <= 60_000_000_000, "F1R1_SOURCE_METADATA_DEADLINE")
    return {"schema_version": 1, "experiment_id": EXPERIMENT, **decision,
            "event_source": roles, "protected_B_guard_present": present,
            "guard_source_commit": guard_origin,
            "guard_sha256": sha(actual_base_guard) if present else None,
            "policy_sha256": sha(policy_raw), "immutable_originals_checked": 96,
            "routing": routes,
            "execution_authorized": False, "provider_authority_acquired": False,
            "HTTP_requests": 0, "F1_launcher_processes": 0,
            "engineering_fixture_processes": 0, "DSP_targets": 0, "DSP_frames": 0,
            "metadata_elapsed_ns": time.monotonic_ns() - started}


def bootstrap_receipt(root: Path, *, f1_required: bool) -> dict:
    # This explicit, compiled-in admission gate stays false throughout bootstrap.
    require(not SCIENCE_EXECUTION_ENABLED, "F1R1_BOOTSTRAP_EXECUTION_GATE_CHANGED")
    require(not f1_required, "F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP")
    routes = validate_actual_routes(root)
    for filename, expected in DOC_DIGESTS.items():
        require(sha(bounded_file(root / REG / filename)) == expected,
                "F1R1_BOOTSTRAP_DESIGN_IDENTITY", filename)
    lock = strict_json(bounded_file(root / REG / "source-lock.json"))
    originals = [row for row in lock["files"] if row["role"].startswith("IMMUTABLE_ORIGINAL")]
    require(len(originals) == 96, "F1R1_FROZEN_F0_SOURCE_CHANGED")
    for row in originals:
        raw = bounded_file(root / row["path"])
        require(len(raw) == row["bytes"] and sha(raw) == row["sha256"],
                "F1R1_FROZEN_F0_SOURCE_CHANGED", row["path"])
    implemented = []
    for relative in IMPLEMENTATION + HOOKS:
        path = root / relative
        if path.exists():
            raw = bounded_file(path)
            implemented.append({"path": relative, "bytes": len(raw), "sha256": sha(raw)})
    return {"schema_version": 1, "experiment_id": EXPERIMENT,
            "disposition": SOURCE_ONLY, "science_execution_enabled": False,
            "execution_authorized": False, "HTTP_requests": 0,
            "F1_launcher_processes": 0, "engineering_fixture_processes": 0,
            "DSP_targets": 0, "DSP_frames": 0, "immutable_originals_checked": 96,
            "routing": routes,
            "implemented_source_bytes": implemented,
            "registered_negative_controls": 178,
            "registered_controls_qualification_run": False,
            "engineering_fixtures_run": False,
            "remaining": ["complete implementation review", "guarded B own main closure",
                          "final actual C source lock", "root external freeze", "live PRE/POST"]}


def write_result(path: Path, value: dict) -> None:
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    require(len(raw) <= METADATA_BYTES, "F1R1_SERIALIZED_BYTES_LIMIT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("source-guard", "bootstrap-receipt", "collect"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--event", type=Path)
    parser.add_argument("--event-name", choices=("pull_request", "push", "workflow_dispatch"))
    parser.add_argument("--guard-origin")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--f1-required", choices=("true", "false"), default="false")
    args = parser.parse_args()
    try:
        if args.command == "collect":
            raise Rejected("F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP")
        if args.command == "source-guard":
            require(args.event is not None and args.event_name is not None,
                    "F1R1_ACTUAL_EVENT_REQUIRED")
            result = source_guard(args.root.resolve(), args.event_name,
                                  strict_json(bounded_file(args.event)), args.guard_origin)
        else:
            result = bootstrap_receipt(args.root.resolve(), f1_required=args.f1_required == "true")
        write_result(args.output, result)
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write("f1_required=" + str(result.get("f1_required", False)).lower() + "\n")
                stream.write("disposition=" + result["disposition"] + "\n")
        print(json.dumps({"disposition": result["disposition"], "execution_authorized": False}))
        return 0
    except (Rejected, OSError, ValueError, KeyError, TypeError) as exc:
        reason = exc.reason if isinstance(exc, Rejected) else "F1R1_METADATA_INPUT_REJECTED"
        write_result(args.output, {"schema_version": 1, "experiment_id": EXPERIMENT,
                                  "disposition": "F1_R1_SOURCE_REJECTED", "reason": reason,
                                  "detail": str(exc), "execution_authorized": False,
                                  "HTTP_requests": 0, "F1_launcher_processes": 0,
                                  "engineering_fixture_processes": 0, "DSP_targets": 0,
                                  "DSP_frames": 0})
        print(reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
