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
import urllib.error
import urllib.parse
import urllib.request


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
PROVIDER_EXECUTION_ENABLED = False
METADATA_BYTES = 2 * 1024 * 1024

API_ORIGIN = 'https://api.github.com'
API_PREFIX = '/repos/' + REPOSITORY
API_CATEGORY_RULES = {
    'original_job_response': (1, 2097152),
    'original_job_request_record': (1, 65536),
    'repository_responses': (2, 65536),
    'run_attempt_responses': (2, 131072),
    'issue_bracket_responses': (4, 65536),
    'complete_comment_list_responses': (2, 1048576),
    'selected_comment_responses': (2, 65536),
    'complete_main_PR_association_responses': (2, 1048576),
    'PR_detail_responses': (2, 262144),
    'all_non_job_request_and_header_records': (16, 8192),
}
API_ROUTE_CATEGORIES = {
    'jobs': 'original_job_response', 'repository': 'repository_responses',
    'run': 'run_attempt_responses', 'association': 'complete_main_PR_association_responses',
    'pr': 'PR_detail_responses', 'issue_before': 'issue_bracket_responses',
    'comments': 'complete_comment_list_responses', 'selected': 'selected_comment_responses',
    'issue_after': 'issue_bracket_responses',
}
API_HEADER_NAMES = frozenset(('content-type', 'content-length', 'content-encoding', 'link',
                              'date', 'etag', 'x-github-request-id', 'x-ratelimit-limit',
                              'x-ratelimit-remaining', 'x-ratelimit-reset', 'x-ratelimit-used',
                              'x-ratelimit-resource', 'x-github-api-version-selected'))


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


def science_deadlines(origin_ns: int, stage_deadline_ns: int, job_deadline_ns: int) -> dict:
    require(all(integer(value) for value in (origin_ns, stage_deadline_ns, job_deadline_ns)),
            'F1R1_STRICT_INTEGER_TIME')
    duration = min(30_000_000_000, stage_deadline_ns - origin_ns, job_deadline_ns - origin_ns)
    require(duration > 1_000_000_000, 'F1R1_SCIENCE_INVOCATION_WINDOW_REQUIRED')
    return {'invocation_started_monotonic_ns': origin_ns, 'admitted_duration_ns': duration,
            'work_deadline_monotonic_ns': origin_ns + duration - 1_000_000_000,
            'native_final_deadline_monotonic_ns': origin_ns + duration - 500_000_000,
            'invocation_deadline_monotonic_ns': origin_ns + duration,
            'native_cleanup_reserve_ns': 500_000_000, 'outer_cleanup_reserve_ns': 500_000_000}


def build_child_environment(temporary_directory: Path) -> dict:
    require(temporary_directory.is_absolute(), 'F1R1_CLEAN_CHILD_ENVIRONMENT')
    # Construct from the explicit allowlist; never copy-and-forget a private
    # variable from the API owner's environment into a compiler or launcher.
    return {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'LC_ALL': 'C', 'TZ': 'UTC', 'TMPDIR': str(temporary_directory)}


def launcher_child_environment() -> dict:
    return {'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
            'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1', 'LC_ALL': 'C', 'TZ': 'UTC'}


def validate_owned_group_cleanup(row: dict) -> None:
    require(integer(row.get('launcher_pid'), 1) and row.get('owned_process_group') == row['launcher_pid'],
            'F1R1_OWNED_GROUP_IDENTITY')
    times = ('invocation_started_monotonic_ns', 'group_SIGKILL_monotonic_ns', 'launcher_wait4_finished_monotonic_ns',
             'group_absent_observed_monotonic_ns', 'encoding_finished_monotonic_ns',
             'invocation_deadline_monotonic_ns')
    require(all(integer(row.get(key)) for key in times) and
            all(row[left] <= row[right] for left, right in zip(times, times[1:])),
            'F1R1_OWNED_GROUP_CLEANUP_ORDER')
    require(row.get('leader_wait_observation_consumed') is False and
            row.get('leader_unreaped_at_group_SIGKILL') is True and
            row.get('group_absent') is True and row.get('wait4_requested_pid') ==
            row.get('wait4_returned_pid') == row['launcher_pid'] and
            row.get('signals_after_leader_reap') == 0 and row.get('additional_descendant_proc_snapshots') == 0,
            'F1R1_OWNED_GROUP_CLEANUP_REQUIRED')
    observed = row.get('leader_observed_waitable_monotonic_ns')
    require(observed is None or integer(observed) and
            row['invocation_started_monotonic_ns'] <= observed <= row['launcher_wait4_finished_monotonic_ns'],
            'F1R1_OWNED_GROUP_CLEANUP_ORDER')
    require(row['invocation_deadline_monotonic_ns'] - row['invocation_started_monotonic_ns'] <= 30_000_000_000,
            'F1R1_SCIENCE_INVOCATION_LIMIT')


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


def compact_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def api_route(name: str, *, run_id: int, attempt: int, source_S: str | None = None,
              pr_number: int | None = None, comment_id: int | None = None) -> str:
    require(name in API_ROUTE_CATEGORIES and integer(run_id, 1) and integer(attempt, 1),
            'F1R1_CANONICAL_PROVIDER_ROUTE')
    if name == 'jobs':
        return f'{API_PREFIX}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100'
    if name == 'repository':
        return API_PREFIX
    if name == 'run':
        return f'{API_PREFIX}/actions/runs/{run_id}/attempts/{attempt}'
    if name == 'association':
        require(oid(source_S), 'F1R1_CANONICAL_PROVIDER_ROUTE')
        return f'{API_PREFIX}/commits/{source_S}/pulls?per_page=100&page=1'
    if name == 'pr':
        require(integer(pr_number, 1), 'F1R1_CANONICAL_PROVIDER_ROUTE')
        return f'{API_PREFIX}/pulls/{pr_number}'
    if name == 'comments':
        return f'{API_PREFIX}/issues/845/comments?per_page=100&page=1'
    if name == 'selected':
        require(integer(comment_id, 1), 'F1R1_CANONICAL_PROVIDER_ROUTE')
        return f'{API_PREFIX}/issues/comments/{comment_id}'
    return f'{API_PREFIX}/issues/845'


def validate_api_path(path: str) -> None:
    patterns = (
        re.escape(API_PREFIX),
        re.escape(API_PREFIX) + r'/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*',
        re.escape(API_PREFIX) + r'/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*/jobs\?per_page=100',
        re.escape(API_PREFIX) + r'/commits/[0-9a-f]{40}/pulls\?per_page=100&page=1',
        re.escape(API_PREFIX) + r'/pulls/[1-9][0-9]*',
        re.escape(API_PREFIX) + r'/issues/845',
        re.escape(API_PREFIX) + r'/issues/845/comments\?per_page=100&page=1',
        re.escape(API_PREFIX) + r'/issues/comments/[1-9][0-9]*',
    )
    require(type(path) is str and len(path) <= 512 and any(re.fullmatch(pattern, path) for pattern in patterns),
            'F1R1_CANONICAL_PROVIDER_ROUTE')


def api_request_window(start_ns: int, active_acquisition_ns: int,
                       stage_deadline_ns: int | None, job_deadline_ns: int | None) -> dict:
    require(integer(start_ns) and integer(active_acquisition_ns), 'F1R1_CONTROL_PLANE_TIME_BUDGET')
    limits = [5_000_000_000, 60_000_000_000 - active_acquisition_ns]
    for deadline in (stage_deadline_ns, job_deadline_ns):
        if deadline is not None:
            require(integer(deadline), 'F1R1_CONTROL_PLANE_TIME_BUDGET')
            limits.append(deadline - start_ns)
    duration = min(limits)
    require(duration > 500_000_000, 'F1R1_CONTROL_PLANE_TIME_BUDGET')
    return {'started_monotonic_ns': start_ns, 'admitted_duration_ns': duration,
            'work_deadline_monotonic_ns': start_ns + duration - 500_000_000,
            'deadline_monotonic_ns': start_ns + duration}


def api_headers_view(headers: list[list[str]]) -> dict[str, list[str]]:
    require(type(headers) is list and len(headers) <= 64 and len(compact_json(headers)) <= 4096,
            'F1R1_CONTROL_PLANE_METADATA_BYTES')
    result = {}
    for pair in headers:
        require(type(pair) is list and len(pair) == 2 and all(type(value) is str for value in pair),
                'F1R1_CONTROL_PLANE_HEADER_SCHEMA')
        key, value = pair
        require(key in API_HEADER_NAMES and not any(char in value for char in '\r\n\x00'),
                'F1R1_CONTROL_PLANE_CREDENTIALS')
        result.setdefault(key, []).append(value)
    for key in ('content-type', 'content-length', 'content-encoding'):
        require(len(result.get(key, [])) <= 1, 'F1R1_CONTROL_PLANE_HEADER_SCHEMA')
    return result


def api_has_next_page(headers: list[list[str]]) -> bool:
    values = api_headers_view(headers).get('link', [])
    next_page = False
    for value in values:
        for item in value.split(','):
            match = re.fullmatch(r'\s*<(https://api\.github\.com/[^<>\s]+)>;\s*rel="(first|prev|next|last)"\s*', item)
            require(match is not None, 'F1R1_COMPLETE_PROVIDER_PAGINATION')
            next_page = next_page or match[2] == 'next'
    return next_page


def validate_api_response(raw: bytes, record: dict, *, expected_path: str, cap: int) -> object:
    validate_api_path(expected_path)
    require(type(raw) is bytes and len(raw) <= cap, 'F1R1_CONTROL_PLANE_BODY_BYTES')
    require(record.get('method') == 'GET' and record.get('origin') == API_ORIGIN and
            record.get('path') == expected_path and record.get('response_final_origin') == API_ORIGIN and
            record.get('response_final_url') == API_ORIGIN + expected_path,
            'F1R1_CANONICAL_PROVIDER_ROUTE')
    require(type(record.get('http_status')) is int and record['http_status'] == 200,
            'F1R1_CONTROL_PLANE_HTTP_STATUS')
    require(record.get('headers_complete') is True, 'F1R1_CONTROL_PLANE_HEADER_SCHEMA')
    headers = api_headers_view(record.get('headers_without_credentials'))
    require(headers.get('content-encoding', ['identity']) == ['identity'],
            'F1R1_CONTROL_PLANE_CONTENT_ENCODING')
    content_type = headers.get('content-type', [''])[0].split(';', 1)[0].strip().lower()
    require(content_type in ('application/json', 'application/vnd.github+json'),
            'F1R1_CONTROL_PLANE_CONTENT_TYPE')
    if 'content-length' in headers:
        length = headers['content-length'][0]
        require(re.fullmatch(r'0|[1-9][0-9]*', length) is not None and int(length) == len(raw),
                'F1R1_CONTROL_PLANE_PARTIAL_RESPONSE')
    require(record.get('body_complete') is True and record.get('overflow') is False and
            integer(record.get('body_bytes')) and record['body_bytes'] == len(raw) and
            record.get('body_sha256') == sha(raw), 'F1R1_CONTROL_PLANE_PARTIAL_RESPONSE')
    return strict_json(raw, cap)


def validate_api_lifecycle(record: dict, *, final_reap: bool) -> int:
    required = ('started_monotonic_ns', 'finished_monotonic_ns', 'admitted_duration_ns',
                'deadline_monotonic_ns', 'worker_pid', 'worker_start_ticks')
    require(all(integer(record.get(key), 1) for key in required), 'F1R1_CONTROL_PLANE_LIFECYCLE')
    start, end, duration = (record[key] for key in ('started_monotonic_ns', 'finished_monotonic_ns', 'admitted_duration_ns'))
    require(0 <= end - start <= duration <= 5_000_000_000 and
            record['deadline_monotonic_ns'] == start + duration,
            'F1R1_CONTROL_PLANE_TIME_BUDGET')
    require(integer(record.get('started_epoch_ns')) and integer(record.get('finished_epoch_ns')) and
            record['started_epoch_ns'] <= record['finished_epoch_ns'], 'F1R1_CONTROL_PLANE_LIFECYCLE')
    reap = record.get('worker_exit_or_final_reap')
    require(type(reap) is dict, 'F1R1_CONTROL_PLANE_LIFECYCLE')
    if final_reap:
        require(reap.get('state') == 'OWNED_WORKER_REAPED' and
                reap.get('wait4_requested_pid') == record['worker_pid'] == reap.get('wait4_returned_pid') and
                integer(reap.get('finished_monotonic_ns')) and start <= reap['finished_monotonic_ns'] <= end and
                reap.get('raw_wait_status') == 0, 'F1R1_CONTROL_PLANE_LIFECYCLE')
    else:
        require(reap.get('state') == 'REUSED_PENDING_FINAL_REAP', 'F1R1_CONTROL_PLANE_LIFECYCLE')
    return end - start


class APIBudgetLedger:
    """Pure counted/byte/time admission; transport cannot invent a reset."""

    def __init__(self, event: str) -> None:
        require(event in ('pull_request', 'push'), 'F1R1_EVENT_SCOPE_NO_SCIENCE')
        sweep = ['repository', 'run'] + (['association'] if event == 'push' else [])
        sweep += ['pr', 'issue_before', 'comments', 'selected', 'issue_after']
        self.event = event
        self.plan = [('FIRST_JOB', 'jobs')] + [(phase, name) for phase in ('PRE', 'POST') for name in sweep]
        self.requests = []
        self.request_retained_sizes = []
        self.active_acquisition_ns = 0
        self.category_counts = {key: 0 for key in API_CATEGORY_RULES}
        self.category_bytes = {key: 0 for key in API_CATEGORY_RULES}
        self.retained_bytes = 0
        self.worker_keys = {}
        self.failed = False
        self.phase_records = []
        self.phase_open = False

    def next_request(self, phase: str, name: str, start_ns: int,
                     stage_deadline_ns: int | None = None,
                     job_deadline_ns: int | None = None) -> dict:
        require(not self.failed and len(self.requests) < len(self.plan) <= 17,
                'F1R1_CONTROL_PLANE_REQUEST_LIMIT')
        require((phase, name) == self.plan[len(self.requests)], 'F1R1_CONTROL_PLANE_REQUEST_ORDER')
        return {'request_ordinal': len(self.requests) + 1, 'phase': phase, 'route_name': name,
                **api_request_window(start_ns, self.active_acquisition_ns, stage_deadline_ns, job_deadline_ns)}

    def retain(self, category: str, raw: bytes) -> None:
        require(category in API_CATEGORY_RULES and type(raw) is bytes, 'F1R1_CONTROL_PLANE_METADATA_BYTES')
        max_count, cap = API_CATEGORY_RULES[category]
        require(self.category_counts[category] < max_count and len(raw) <= cap and
                self.category_bytes[category] + len(raw) <= max_count * cap and
                self.retained_bytes + len(raw) <= 8388608, 'F1R1_CONTROL_PLANE_METADATA_BYTES')
        self.category_counts[category] += 1
        self.category_bytes[category] += len(raw)
        self.retained_bytes += len(raw)

    def accept(self, name: str, raw: bytes, record: dict, *, expected_path: str) -> object:
        position = len(self.requests)
        require(position < len(self.plan) and (record.get('phase'), name) == self.plan[position] and
                record.get('request_ordinal') == position + 1,
                'F1R1_CONTROL_PLANE_REQUEST_ORDER')
        category = API_ROUTE_CATEGORIES[name]
        parsed = validate_api_response(raw, record, expected_path=expected_path, cap=API_CATEGORY_RULES[category][1])
        final = name == 'jobs' or position + 1 == len(self.plan)
        elapsed = validate_api_lifecycle(record, final_reap=final)
        require(self.active_acquisition_ns + elapsed <= 60_000_000_000,
                'F1R1_CONTROL_PLANE_TIME_BUDGET')
        owner = 'FIRST_JOB' if name == 'jobs' else 'COLLECTOR'
        key = (record['worker_pid'], record['worker_start_ticks'])
        require(owner not in self.worker_keys or self.worker_keys[owner] == key,
                'F1R1_CONTROL_PLANE_WORKER_LIMIT')
        if owner == 'COLLECTOR' and 'FIRST_JOB' in self.worker_keys:
            require(key != self.worker_keys['FIRST_JOB'], 'F1R1_CONTROL_PLANE_WORKER_LIMIT')
        metadata = compact_json(record) + b'\n'
        metadata_category = 'original_job_request_record' if name == 'jobs' else 'all_non_job_request_and_header_records'
        require(len(metadata) <= API_CATEGORY_RULES[metadata_category][1] and
                self.category_counts[category] < API_CATEGORY_RULES[category][0] and
                self.category_counts[metadata_category] < API_CATEGORY_RULES[metadata_category][0] and
                self.retained_bytes + len(raw) + len(metadata) <= 8388608,
                'F1R1_CONTROL_PLANE_METADATA_BYTES')
        self.retain(category, raw)
        self.retain(metadata_category, metadata)
        self.worker_keys[owner] = key
        self.active_acquisition_ns += elapsed
        self.requests.append(dict(record))
        self.request_retained_sizes.append((len(raw), len(metadata)))
        return parsed

    def failed_request(self, name: str, raw: bytes, record: dict) -> None:
        self.failed = True
        category = API_ROUTE_CATEGORIES[name]
        metadata_category = 'original_job_request_record' if name == 'jobs' else 'all_non_job_request_and_header_records'
        metadata = compact_json(record) + b'\n'
        require(len(raw) <= API_CATEGORY_RULES[category][1] and
                len(metadata) <= API_CATEGORY_RULES[metadata_category][1],
                'F1R1_CONTROL_PLANE_METADATA_BYTES')
        ordinal = record['request_ordinal']
        require(ordinal in (len(self.requests), len(self.requests) + 1) and ordinal > 0,
                'F1R1_CONTROL_PLANE_REQUEST_ORDER')
        if ordinal == len(self.requests):
            previous = self.requests[-1]
            charged = (previous['finished_monotonic_ns'] - previous['started_monotonic_ns'] +
                       previous.get('owner_post_response_elapsed_ns', 0))
            self.active_acquisition_ns += max(0, record['finished_monotonic_ns'] - record['started_monotonic_ns'] - charged)
            old_body, old_metadata = self.request_retained_sizes[-1]
            for key, old, new in ((category, old_body, len(raw)), (metadata_category, old_metadata, len(metadata))):
                self.category_bytes[key] += new - old
                self.retained_bytes += new - old
            self.requests[-1] = dict(record)
            self.request_retained_sizes[-1] = (len(raw), len(metadata))
        else:
            self.active_acquisition_ns += record['finished_monotonic_ns'] - record['started_monotonic_ns']
            self.retain(category, raw)
            self.retain(metadata_category, metadata)
            self.requests.append(dict(record))
            self.request_retained_sizes.append((len(raw), len(metadata)))
        require(self.retained_bytes <= 8388608, 'F1R1_CONTROL_PLANE_METADATA_BYTES')

    def complete(self) -> dict:
        require(not self.failed and len(self.requests) == len(self.plan) and len(self.worker_keys) == 2,
                'F1R1_CONTROL_PLANE_REQUEST_LIMIT')
        validate_api_lifecycle(self.requests[0], final_reap=True)
        validate_api_lifecycle(self.requests[-1], final_reap=True)
        return {'actual_GET_requests': len(self.requests), 'active_acquisition_ns': self.active_acquisition_ns,
                'category_counts': dict(self.category_counts), 'category_bytes': dict(self.category_bytes),
                'retained_category_bytes': self.retained_bytes, 'HTTP_helper_starts': 2,
                'both_helpers_reaped': True}


class APIPhaseMeter:
    """Charge the whole contiguous provider phase, excluding no validation.

    Request owners already charge their measured intervals. Each checkpoint
    adds only the remaining wall interval, so parsing, local graph reads,
    stability checks and failure cleanup are charged exactly once. Build and
    scientific work occur between closed PRE and POST phases.
    """

    def __init__(self, ledger: APIBudgetLedger, phase: str, *, started_ns: int,
                 stage_deadline_ns: int, job_deadline_ns: int) -> None:
        require(phase in ('PRE', 'POST', 'FINALIZE') and not ledger.phase_open,
                'F1R1_CONTROL_PLANE_PHASE_ORDER')
        require(all(integer(value) for value in
                    (started_ns, stage_deadline_ns, job_deadline_ns, ledger.active_acquisition_ns)),
                'F1R1_CONTROL_PLANE_TIME_BUDGET')
        remaining = 60_000_000_000 - ledger.active_acquisition_ns
        require(remaining > 0 and started_ns < min(stage_deadline_ns, job_deadline_ns),
                'F1R1_CONTROL_PLANE_TIME_BUDGET')
        self.ledger, self.phase = ledger, phase
        self.started_ns = self.cursor_ns = started_ns
        self.initial_charge_ns = self.accounted_ns = ledger.active_acquisition_ns
        self.deadline_ns = min(started_ns + remaining, stage_deadline_ns, job_deadline_ns)
        self.stage_deadline_ns, self.job_deadline_ns = stage_deadline_ns, job_deadline_ns
        self.overhead_ns = 0
        self.checkpoint_count = 0
        self.closed = False
        ledger.phase_open = True

    def checkpoint(self, now_ns: int | None = None) -> None:
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        require(not self.closed and integer(now_ns) and now_ns >= self.cursor_ns,
                'F1R1_CONTROL_PLANE_PHASE_ORDER')
        wall = now_ns - self.cursor_ns
        charged = self.ledger.active_acquisition_ns - self.accounted_ns
        require(0 <= charged <= wall, 'F1R1_CONTROL_PLANE_DOUBLE_CHARGE')
        overhead = wall - charged
        self.ledger.active_acquisition_ns += overhead
        self.overhead_ns += overhead
        self.cursor_ns, self.accounted_ns = now_ns, self.ledger.active_acquisition_ns
        self.checkpoint_count += 1
        require(self.ledger.active_acquisition_ns <= 60_000_000_000 and now_ns <= self.deadline_ns,
                'F1R1_CONTROL_PLANE_TIME_BUDGET')

    def close(self, *, failure: str | None = None, now_ns: int | None = None) -> dict:
        require(not self.closed, 'F1R1_CONTROL_PLANE_PHASE_ORDER')
        failure_to_raise = None
        try:
            self.checkpoint(now_ns)
        except Rejected as exc:
            failure = failure or exc.reason
            failure_to_raise = exc
        row = {'phase': self.phase, 'started_monotonic_ns': self.started_ns,
               'original_deadline_monotonic_ns': self.deadline_ns,
               'original_stage_deadline_monotonic_ns': self.stage_deadline_ns,
               'original_job_deadline_monotonic_ns': self.job_deadline_ns,
               'active_before_ns': self.initial_charge_ns, 'failure': failure,
               'measurement_cut': 'AFTER_PHASE_BOOKKEEPING_BEFORE_RETURN'}
        # Encode the bounded bookkeeping before the final measured cut. This
        # does not purport to measure the later global artifact sealing step.
        compact_json(row)
        self.ledger.phase_records.append(row)
        if now_ns is None:
            try:
                self.checkpoint()
            except Rejected as exc:
                failure_to_raise = failure_to_raise or exc
                row['failure'] = row['failure'] or exc.reason
        row.update(measurement_cut_monotonic_ns=self.cursor_ns,
                   elapsed_ns=self.cursor_ns - self.started_ns,
                   non_request_work_ns=self.overhead_ns,
                   active_after_ns=self.ledger.active_acquisition_ns,
                   checkpoint_count=self.checkpoint_count)
        self.closed = True
        self.ledger.phase_open = False
        if row['failure'] is not None:
            self.ledger.failed = True
        if failure_to_raise is not None:
            raise failure_to_raise
        return dict(row)


def original_job_conservative_charge(record: dict) -> int:
    """A final self-describing file cannot measure its own final write.

    Its explicit pre-encoding cut is retained, and the entire original
    admitted request allowance is charged. A later reader never substitutes
    that earlier cut for a measured whole first-operation completion.
    """
    duration = record.get('admitted_duration_ns')
    cut = record.get('first_operation_measurement_cut_monotonic_ns')
    require(integer(duration, 1, 5_000_000_000) and integer(cut) and
            record.get('first_operation_measurement_cut') == 'BEFORE_FINAL_ENVELOPE_ENCODING_AND_WRITE' and
            record.get('first_operation_charged_duration_ns') == duration and
            record['started_monotonic_ns'] <= record['finished_monotonic_ns'] <= cut <= record['deadline_monotonic_ns'] and
            record['deadline_monotonic_ns'] == record['started_monotonic_ns'] + duration,
            'F1R1_CONTROL_PLANE_MEASUREMENT_CUT')
    return duration


def provider_timestamp_ns(value: object) -> int:
    require(type(value) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)', value),
            'F1R1_ORIGINAL_JOB_TIMESTAMP')
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None, 'F1R1_ORIGINAL_JOB_TIMESTAMP')
        seconds = calendar.timegm(parsed.utctimetuple())
        match = re.search(r'\.(\d{1,9})(?:Z|[+-])', value)
        fractions = int(match[1].ljust(9, '0')) if match else 0
        return seconds * 1_000_000_000 + fractions
    except ValueError as exc:
        raise Rejected('F1R1_ORIGINAL_JOB_TIMESTAMP') from exc


def validate_original_jobs(jobs_body: dict, *, headers: list[list[str]], run_id: int,
                            attempt: int, expected_head: str) -> dict:
    require(type(jobs_body) is dict and type(jobs_body.get('jobs')) is list and
            integer(jobs_body.get('total_count'), 1) and
            0 < len(jobs_body['jobs']) == jobs_body['total_count'] <= 100 and
            api_has_next_page(headers) is False, 'F1R1_COMPLETE_ORIGINAL_JOBS')
    jobs = jobs_body['jobs']
    require(all(type(job) is dict and integer(job.get('id'), 1) for job in jobs) and
            len({job['id'] for job in jobs}) == len(jobs), 'F1R1_COMPLETE_ORIGINAL_JOBS')
    selected = [job for job in jobs if job.get('name') in ('frontend-rss-f1', 'quality / frontend-rss-f1')]
    require(len(selected) == 1, 'F1R1_UNIQUE_ORIGINAL_JOB')
    job = selected[0]
    require(integer(run_id, 1) and integer(attempt, 1) and oid(expected_head) and
            job.get('status') == 'in_progress' and type(job.get('run_id')) is int and
            job['run_id'] == run_id and type(job.get('run_attempt')) is int and
            job['run_attempt'] == attempt and job.get('head_sha') == expected_head,
            'F1R1_ORIGINAL_JOB_BINDING')
    started = provider_timestamp_ns(job.get('started_at'))
    return {'job_id': job['id'], 'job_name': job['name'], 'run_id': run_id, 'run_attempt': attempt,
            'head_sha': expected_head, 'started_at': job['started_at'], 'started_epoch_ns': started,
            'deadline_epoch_ns': started + 900_000_000_000,
            'job_seconds': 900, 'archive_reserve_seconds': 60}


def validate_actual_run(run: dict, *, run_id: int, attempt: int,
                         event: str, expected_head: str) -> dict:
    require(type(run) is dict and run.get('id') == run_id and type(run.get('id')) is int and
            run.get('run_attempt') == attempt and type(run.get('run_attempt')) is int and
            run.get('event') == event and run.get('head_sha') == expected_head,
            'F1R1_RUN_EVENT_SOURCE')
    require(run.get('path') == '.github/workflows/verify.yml' and
            run.get('repository', {}).get('id') == REPOSITORY_ID and
            type(run.get('repository', {}).get('id')) is int and
            run.get('repository', {}).get('full_name') == REPOSITORY,
            'F1R1_RUN_WORKFLOW_SOURCE')
    created = provider_timestamp_ns(run.get('created_at'))
    require(type(run.get('pull_requests')) is list and len(run['pull_requests']) <= 100,
            'F1R1_RUN_PR_ASSOCIATION')
    return {'run_id': run_id, 'run_attempt': attempt, 'event': event, 'head_sha': expected_head,
            'created_at': run['created_at'], 'created_epoch_ns': created,
            'workflow_path': run['path'], 'repository_id': REPOSITORY_ID}


def select_provider_PR(event: str, event_record: dict, run: dict,
                        association: list | None, *, association_has_next_page: bool | None) -> int:
    if event == 'pull_request':
        event_number = event_record.get('number')
        require(integer(event_number, 1) and type(run.get('pull_requests')) is list,
                'F1R1_RUN_PR_ASSOCIATION')
        rows = run['pull_requests']
        require(all(type(row) is dict and integer(row.get('number'), 1) for row in rows) and
                len({row['number'] for row in rows}) == len(rows), 'F1R1_RUN_PR_ASSOCIATION')
        selected = [row for row in rows if row['number'] == event_number and
                    row.get('head', {}).get('sha') == run.get('head_sha')]
        require(len(selected) == 1, 'F1R1_RUN_PR_ASSOCIATION')
        return selected[0]['number']
    require(event == 'push' and type(association) is list and len(association) <= 100 and
            association_has_next_page is False, 'F1R1_COMPLETE_MAIN_PR_ASSOCIATION')
    require(all(type(row) is dict and integer(row.get('id'), 1) and integer(row.get('number'), 1) for row in association) and
            len({row['id'] for row in association}) == len(association) and
            len({row['number'] for row in association}) == len(association),
            'F1R1_UNIQUE_MAIN_PR_ASSOCIATION')
    matches = [row for row in association if row.get('merge_commit_sha') == run.get('head_sha') and
               row.get('head', {}).get('ref') == REGISTERED_BRANCH and row.get('base', {}).get('ref') == 'main']
    require(len(matches) == 1, 'F1R1_UNIQUE_MAIN_PR_ASSOCIATION')
    return matches[0]['number']


def select_freeze_comment(comments: list, issue_before: dict, *, source: dict,
                           schema: dict, has_next_page: bool) -> int:
    """Selection from one complete original list, before the direct GET."""
    require(source.get('actual_C_derived_before_freeze') is True, 'F1R1_MAIN_PROVIDER_ASSOCIATION_REQUIRED')
    require(type(comments) is list and len(comments) <= 100 and has_next_page is False and
            type(issue_before.get('comments')) is int and issue_before['comments'] == len(comments),
            'F1R1_COMPLETE_COMMENT_LIST')
    require(all(type(row) is dict and integer(row.get('id'), 1) for row in comments) and
            len({row['id'] for row in comments}) == len(comments), 'F1R1_COMPLETE_COMMENT_LIST')
    selected = []
    for row in comments:
        user = row.get('user', {})
        if not (user.get('login') == 'jiying2007' and type(user.get('id')) is int and
                user['id'] == 33591504 and user.get('type') == 'User'):
            continue
        require(type(row.get('body')) is str, 'F1R1_FREEZE_SCHEMA')
        if not row['body'].lstrip().startswith('{'):
            continue
        parsed = strict_json(row['body'].encode(), 16384)
        validate_schema(parsed, schema)
        if parsed['source']['reviewed_head_C'] == source['C']:
            selected.append(row['id'])
    require(selected, 'F1R1_UNIQUE_MATCHING_C_FREEZE')
    require(len(selected) == 1, 'F1R1_DUPLICATE_C_FREEZE')
    return selected[0]


class _NoProviderRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_worker_main(command_fd: int, response_fd: int, token: str) -> None:
    """One owned metadata-only worker; never called by offline controls.

    DNS, socket and response reads may block only this process. The parent
    enforces the whole request deadline and reaps this exact child on failure.
    There is no retry or other process creation in this worker.
    """
    require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
            'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoProviderRedirect())

    def write_all(raw):
        view = memoryview(raw)
        while view:
            count = os.write(response_fd, view)
            if count <= 0:
                os._exit(2)
            view = view[count:]

    for unused_request in range(16):
        command = bytearray()
        while b'\n' not in command:
            piece = os.read(command_fd, min(1024, 1025 - len(command)))
            if not piece:
                os._exit(0 if not command else 2)
            if len(command) + len(piece) > 1024:
                os._exit(2)
            command.extend(piece)
        require(command[-1:] == b'\n' and command.count(b'\n') == 1, 'F1R1_HTTP_WORKER_PROTOCOL')
        request = strict_json(bytes(command), 1024)
        require(type(request) is dict and set(request) == {'path', 'cap', 'close_after_request'},
                'F1R1_HTTP_WORKER_PROTOCOL')
        path, cap = request['path'], request['cap']
        validate_api_path(path)
        require(integer(cap, 1) and cap <= 2097152 and type(request['close_after_request']) is bool,
                'F1R1_HTTP_WORKER_PROTOCOL')
        body = bytearray()
        meta = {'http_status': 0, 'response_final_origin': API_ORIGIN,
                'response_final_url': API_ORIGIN + path, 'headers_without_credentials': [],
                'headers_complete': False, 'body_complete': False, 'overflow': False,
                'worker_error_class': None}
        response = None
        try:
            outgoing = urllib.request.Request(API_ORIGIN + path, method='GET', headers={
                'Accept': 'application/vnd.github+json', 'Accept-Encoding': 'identity',
                'User-Agent': 'FE09-F1-R1-bounded-metadata',
                'X-GitHub-Api-Version': '2022-11-28', 'Authorization': 'Bearer ' + token})
            try:
                response = opener.open(outgoing, timeout=5)
            except urllib.error.HTTPError as exc:
                response = exc
            meta['http_status'] = response.status
            final_url = response.geturl()
            parsed_url = urllib.parse.urlsplit(final_url)
            meta['response_final_url'] = final_url
            meta['response_final_origin'] = parsed_url.scheme + '://' + parsed_url.netloc
            safe_headers = []
            for key, value in response.headers.items():
                lowered = key.lower()
                if lowered in API_HEADER_NAMES:
                    safe_headers.append([lowered, value])
                    # Bound before keeping another header value or reading body.
                    api_headers_view(safe_headers)
            meta['headers_without_credentials'] = safe_headers
            meta['headers_complete'] = True
            while True:
                piece = response.read(min(65536, cap - len(body) + 1))
                if not piece:
                    meta['body_complete'] = True
                    break
                remaining = cap - len(body)
                if len(piece) > remaining:
                    body.extend(piece[:remaining])
                    meta['overflow'] = True
                    break
                body.extend(piece)
        except BaseException as exc:
            # Exception text can include server-controlled/private data. Retain
            # only its type and the original bounded prefix already observed.
            meta['worker_error_class'] = type(exc).__name__[:128]
        finally:
            if response is not None:
                response.close()
        meta['body_bytes'] = len(body)
        meta['body_sha256'] = sha(bytes(body))
        envelope = compact_json(meta)
        require(len(envelope) <= 6144, 'F1R1_HTTP_WORKER_PROTOCOL')
        write_all(len(envelope).to_bytes(4, 'big') + len(body).to_bytes(4, 'big'))
        write_all(envelope)
        write_all(body)
        if request['close_after_request']:
            os._exit(0)
    os._exit(2)


class HTTPMetadataWorker:
    """At most one helper for this owner; source-only gates run before fork."""

    def __init__(self, token: str, ledger: APIBudgetLedger, output: Path) -> None:
        require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
                'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
        require(sys.flags.isolated == 1, 'F1R1_ISOLATED_PYTHON_REQUIRED')
        require(sys.platform == 'linux' and type(token) is str and 0 < len(token) <= 8192 and
                not any(char in token for char in '\r\n\x00'), 'F1R1_READ_TOKEN_REQUIRED')
        self._token = token
        self.ledger = ledger
        self.output = output
        self.pid = None
        self.start_ticks = None
        self.command_fd = None
        self.response_fd = None
        self.extra_fds = []
        self.fd_cleanup_errors = []
        self.closed = False
        self.failed = False
        self.reap_record = None
        self._partial_body = bytearray()

    def _start(self) -> None:
        require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
                'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
        require(self.pid is None and not self.closed and not self.failed,
                'F1R1_CONTROL_PLANE_WORKER_LIMIT')
        read_command, write_command = os.pipe2(os.O_CLOEXEC)
        try:
            read_response, write_response = os.pipe2(os.O_CLOEXEC)
        except BaseException:
            os.close(read_command)
            os.close(write_command)
            raise
        try:
            pid = os.fork()
        except BaseException:
            for fd in (read_command, write_command, read_response, write_response):
                os.close(fd)
            raise
        if pid == 0:
            try:
                os.close(write_command)
                os.close(read_response)
                # Preserve only the two owned protocol FDs. No credential or
                # checkout descriptor is carried to this worker accidentally.
                keep = sorted((read_command, write_response))
                lower = 3
                for fd in keep:
                    os.closerange(lower, fd)
                    lower = fd + 1
                os.closerange(lower, os.sysconf('SC_OPEN_MAX'))
                os.environ.clear()
                _http_worker_main(read_command, write_response, self._token)
            except BaseException:
                pass
            os._exit(2)
        # The first parent action records *every* owned resource. A close,
        # nonblocking setup or /proc parse failure below cannot orphan a PID
        # or leave the failure handler unaware of a pipe end.
        self.pid, self.command_fd, self.response_fd, self.extra_fds = (
            pid, write_command, read_response, [read_command, write_response])
        self._close_extra_fds()
        require(not self.fd_cleanup_errors, 'F1R1_CONTROL_PLANE_LIFECYCLE')
        for fd in (write_command, read_response):
            os.set_blocking(fd, False)
        stat = bounded_file(Path('/proc') / str(pid) / 'stat', 1536)
        self.start_ticks = parse_proc_stat(stat)['start_ticks']

    def _pipe(self, fd: int, *, data: bytes | None = None, size: int | None = None,
              deadline_ns: int, retain_body_prefix: bool = False) -> bytes:
        reading = data is None
        require((reading and integer(size) and size <= 2097152) or
                (not reading and type(data) is bytes and len(data) <= 1024),
                'F1R1_HTTP_WORKER_PROTOCOL')
        output = bytearray()
        if retain_body_prefix:
            self._partial_body = output
        offset = 0
        with selectors.DefaultSelector() as selector:
            selector.register(fd, selectors.EVENT_READ if reading else selectors.EVENT_WRITE)
            while (len(output) < size if reading else offset < len(data)):
                remaining = deadline_ns - time.monotonic_ns()
                require(remaining > 0, 'F1R1_CONTROL_PLANE_TIME_BUDGET')
                if not selector.select(remaining / 1_000_000_000):
                    continue
                try:
                    if reading:
                        piece = os.read(fd, min(65536, size - len(output)))
                        require(piece, 'F1R1_CONTROL_PLANE_PARTIAL_RESPONSE')
                        output.extend(piece)
                    else:
                        count = os.write(fd, data[offset:])
                        require(count > 0, 'F1R1_HTTP_WORKER_PROTOCOL')
                        offset += count
                except BlockingIOError:
                    continue
        return bytes(output)

    def _reap(self, deadline_ns: int, *, terminate: bool) -> dict:
        require(self.pid is not None and self.reap_record is None, 'F1R1_CONTROL_PLANE_LIFECYCLE')
        # Exact owned PID; never wait-any and never reuse a reaped PID to signal.
        if terminate:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        while True:
            waited, status, usage = os.wait4(self.pid, os.WNOHANG)
            if waited:
                require(waited == self.pid, 'F1R1_CONTROL_PLANE_LIFECYCLE')
                self.reap_record = {'state': 'OWNED_WORKER_REAPED',
                                    'wait4_requested_pid': self.pid, 'wait4_returned_pid': waited,
                                    'raw_wait_status': status, 'finished_monotonic_ns': time.monotonic_ns(),
                                    'owned_worker_terminated': terminate}
                self.closed = True
                self._token = ''
                require(self.reap_record['finished_monotonic_ns'] <= deadline_ns,
                        'F1R1_CONTROL_PLANE_TIME_BUDGET')
                return self.reap_record
            remaining = deadline_ns - time.monotonic_ns()
            require(remaining > 0, 'F1R1_CONTROL_PLANE_LIFECYCLE')
            time.sleep(min(0.001, remaining / 1_000_000_000))

    def _close_extra_fds(self) -> None:
        while self.extra_fds:
            fd = self.extra_fds.pop()
            try:
                os.close(fd)
            except OSError as exc:
                self.fd_cleanup_errors.append(type(exc).__name__)

    def _close_fds(self) -> None:
        self._close_extra_fds()
        for name in ('command_fd', 'response_fd'):
            fd = getattr(self, name)
            if fd is not None:
                setattr(self, name, None)
                try:
                    os.close(fd)
                except OSError as exc:
                    self.fd_cleanup_errors.append(type(exc).__name__)

    def abort_between_requests(self, *, stage_deadline_ns: int, job_deadline_ns: int) -> dict:
        """No new GET, worker, or reset; use only the still-existing budgets."""
        require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
                'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
        self.failed = self.ledger.failed = True
        if self.pid is None or self.reap_record is not None:
            return {'worker_created': self.pid is not None, 'reap': self.reap_record}
        started = time.monotonic_ns()
        remaining = min(500_000_000, stage_deadline_ns - started, job_deadline_ns - started,
                        60_000_000_000 - self.ledger.active_acquisition_ns)
        deadline = started + max(0, remaining)
        reason = None
        try:
            self._reap(deadline, terminate=True)
        except (Rejected, OSError) as exc:
            reason = exc.reason if isinstance(exc, Rejected) else 'F1R1_CONTROL_PLANE_LIFECYCLE'
        finally:
            self._close_fds()
        finished = time.monotonic_ns()
        self.ledger.active_acquisition_ns += finished - started
        self.terminal_cleanup = {'started_monotonic_ns': started, 'finished_monotonic_ns': finished,
                                 'original_stage_deadline_monotonic_ns': stage_deadline_ns,
                                 'original_job_deadline_monotonic_ns': job_deadline_ns,
                                 'cleanup_deadline_monotonic_ns': deadline,
                                 'admitted_duration_ns': max(0, remaining),
                                 'new_GET_requests': 0, 'new_worker_starts': 0,
                                 'worker_pid': self.pid, 'worker_start_ticks': self.start_ticks,
                                 'reap': self.reap_record, 'failure': reason,
                                 'within_existing_budgets': reason is None and finished <= deadline}
        return dict(self.terminal_cleanup)

    def get(self, phase: str, name: str, path: str, *, stage_deadline_ns: int | None,
            job_deadline_ns: int | None, close_after_request: bool = False,
            first_operation_origin: tuple[int, int] | None = None) -> object:
        require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
                'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
        require(not self.failed and not self.closed and not self.ledger.failed,
                'F1R1_CONTROL_PLANE_WORKER_LIMIT')
        if first_operation_origin is None:
            started, started_epoch = time.monotonic_ns(), time.time_ns()
        else:
            require(phase == 'FIRST_JOB' and name == 'jobs' and
                    type(first_operation_origin) is tuple and len(first_operation_origin) == 2 and
                    all(integer(value, 1) for value in first_operation_origin),
                    'F1R1_CONTROL_PLANE_MEASUREMENT_CUT')
            started, started_epoch = first_operation_origin
            require(started <= time.monotonic_ns() and started_epoch <= time.time_ns(),
                    'F1R1_CONTROL_PLANE_MEASUREMENT_CUT')
        validate_api_path(path)
        admission = self.ledger.next_request(phase, name, started, stage_deadline_ns, job_deadline_ns)
        cap = API_CATEGORY_RULES[API_ROUTE_CATEGORIES[name]][1]
        raw, record = b'', {}
        framing_complete = False
        command_sent = False
        self._partial_body = bytearray()
        try:
            require(time.monotonic_ns() < admission['work_deadline_monotonic_ns'],
                    'F1R1_CONTROL_PLANE_TIME_BUDGET')
            if self.pid is None:
                self._start()
            command = compact_json({'path': path, 'cap': cap, 'close_after_request': close_after_request}) + b'\n'
            self._pipe(self.command_fd, data=command, deadline_ns=admission['work_deadline_monotonic_ns'])
            command_sent = True
            prefix = self._pipe(self.response_fd, size=8, deadline_ns=admission['work_deadline_monotonic_ns'])
            metadata_size, body_size = int.from_bytes(prefix[:4], 'big'), int.from_bytes(prefix[4:], 'big')
            require(0 < metadata_size <= 6144 and body_size <= cap, 'F1R1_HTTP_WORKER_PROTOCOL')
            metadata = self._pipe(self.response_fd, size=metadata_size, deadline_ns=admission['work_deadline_monotonic_ns'])
            reply = strict_json(metadata, 6144)
            require(type(reply) is dict, 'F1R1_HTTP_WORKER_PROTOCOL')
            record = {**reply, **admission, 'method': 'GET', 'origin': API_ORIGIN, 'path': path,
                      'started_epoch_ns': started_epoch, 'worker_pid': self.pid,
                      'worker_start_ticks': self.start_ticks}
            raw = self._pipe(self.response_fd, size=body_size, deadline_ns=admission['work_deadline_monotonic_ns'],
                             retain_body_prefix=True)
            framing_complete = True
            parsed = validate_api_response(raw, record, expected_path=path, cap=cap)
            if close_after_request:
                record['worker_exit_or_final_reap'] = self._reap(admission['work_deadline_monotonic_ns'], terminate=False)
                self._close_fds()
                require(not self.fd_cleanup_errors, 'F1R1_CONTROL_PLANE_LIFECYCLE')
            else:
                record['worker_exit_or_final_reap'] = {'state': 'REUSED_PENDING_FINAL_REAP'}
            # Include strict parsing, complete framing, and exact final reap in
            # the same request. No socket-timeout-only success is possible.
            compact_json(record)
            record['finished_epoch_ns'] = time.time_ns()
            record['finished_monotonic_ns'] = time.monotonic_ns()
            self.ledger.accept(name, raw, record, expected_path=path)
            directory = self.output / f'{admission["request_ordinal"]:02d}-{phase}-{name}'
            directory.mkdir(parents=True, exist_ok=False)
            (directory / 'response.json').write_bytes(raw)
            (directory / 'request.json').write_bytes(compact_json(record) + b'\n')
            returned = time.monotonic_ns()
            extra = returned - record['finished_monotonic_ns']
            self.ledger.active_acquisition_ns += extra
            self.ledger.requests[-1]['owner_returned_monotonic_ns'] = returned
            self.ledger.requests[-1]['owner_post_response_elapsed_ns'] = extra
            require(returned <= admission['deadline_monotonic_ns'] and
                    self.ledger.active_acquisition_ns <= 60_000_000_000,
                    'F1R1_CONTROL_PLANE_TIME_BUDGET')
            # The additional persistence/accounting interval is explicit. It
            # is not reconstructed as a difference of floating timestamps.
            return parsed
        except BaseException as exc:
            self.failed = self.ledger.failed = True
            reason = exc.reason if isinstance(exc, Rejected) else 'F1R1_CONTROL_PLANE_REQUEST_FAILED'
            if self.pid is not None and self.reap_record is None:
                try:
                    self._reap(admission['deadline_monotonic_ns'], terminate=True)
                except (Rejected, OSError):
                    pass
            self._close_fds()
            if not framing_complete:
                raw = bytes(self._partial_body)
            failure = {**record, **admission, 'method': 'GET', 'origin': API_ORIGIN, 'path': path,
                       'reason': reason, 'started_epoch_ns': started_epoch,
                       'finished_epoch_ns': time.time_ns(), 'finished_monotonic_ns': time.monotonic_ns(),
                       'worker_pid': self.pid, 'worker_start_ticks': self.start_ticks,
                       'worker_exit_or_final_reap': self.reap_record,
                       'owned_FD_cleanup_errors': list(self.fd_cleanup_errors),
                       'worker_declared_body_bytes': record.get('body_bytes'),
                       'worker_declared_body_sha256': record.get('body_sha256'),
                       'body_bytes': len(raw), 'body_sha256': sha(raw),
                       'body_complete': framing_complete and record.get('body_complete', False),
                       'overflow': record.get('overflow', False),
                       'command_sent_to_worker': command_sent,
                       'charged_GET_attempt_count_including_failure': admission['request_ordinal'],
                       'request_qualification_complete': False}
            # Retain only bounded original bytes. A timeout never turns a
            # missing response into a fabricated successful provider object.
            directory = self.output / f'{admission["request_ordinal"]:02d}-{phase}-{name}'
            directory.mkdir(parents=True, exist_ok=True)
            (directory / 'response.json').write_bytes(raw[:cap])
            self.ledger.failed_request(name, raw, failure)
            failure_raw = compact_json(failure) + b'\n'
            require(len(failure_raw) <= (65536 if name == 'jobs' else 8192),
                    'F1R1_CONTROL_PLANE_METADATA_BYTES')
            (directory / 'request.json').write_bytes(failure_raw)
            raise Rejected(reason) from None


def oid(value: object) -> bool:
    return type(value) is str and re.fullmatch("[0-9a-f]{40}", value) is not None and value != "0" * 40


def git_object_digest(kind: str, raw: bytes) -> str:
    require(kind in ('commit', 'tree', 'blob') and type(raw) is bytes, 'F1R1_IMMUTABLE_GIT_OBJECT')
    return hashlib.sha1(kind.encode('ascii') + b' ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def parse_commit_object(raw: bytes, expected: str) -> dict:
    require(oid(expected) and type(raw) is bytes and len(raw) <= 65536 and
            git_object_digest('commit', raw) == expected, 'F1R1_IMMUTABLE_GIT_OBJECT')
    require(b'\n\n' in raw, 'F1R1_IMMUTABLE_GIT_OBJECT')
    header = raw.split(b'\n\n', 1)[0].splitlines()
    trees = [line[5:].decode('ascii', errors='strict') for line in header if line.startswith(b'tree ')]
    parents = [line[7:].decode('ascii', errors='strict') for line in header if line.startswith(b'parent ')]
    require(len(trees) == 1 and oid(trees[0]) and len(parents) <= 16 and
            all(oid(parent) for parent in parents) and len(parents) == len(set(parents)),
            'F1R1_IMMUTABLE_GIT_OBJECT')
    return {'commit': expected, 'tree': trees[0], 'parents': parents,
            'raw_bytes': len(raw), 'raw_sha256': sha(raw)}


def parse_tree_object(raw: bytes, expected: str) -> dict:
    require(oid(expected) and type(raw) is bytes and len(raw) <= METADATA_BYTES and
            git_object_digest('tree', raw) == expected, 'F1R1_IMMUTABLE_GIT_OBJECT')
    result, offset = {}, 0
    while offset < len(raw):
        space = raw.find(b' ', offset)
        nul = raw.find(b'\0', space + 1)
        require(space > offset and nul > space + 1 and nul + 21 <= len(raw),
                'F1R1_IMMUTABLE_GIT_OBJECT')
        mode = raw[offset:space].decode('ascii', errors='strict').zfill(6)
        name = raw[space + 1:nul].decode('utf-8', errors='strict')
        member = raw[nul + 1:nul + 21].hex()
        require(mode in ('040000', '100644', '100755', '120000', '160000') and
                name not in ('', '.', '..') and '/' not in name and name not in result and oid(member),
                'F1R1_IMMUTABLE_GIT_OBJECT')
        result[name] = {'mode': mode, 'oid': member}
        offset = nul + 21
    return result


class ImmutableGitObjects:
    """Read immutable graph bytes with hash verification and no demand fetch."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.commits = {}
        self.trees = {}
        self.read_deadline_ns = None

    def _read(self, *args: str, cap: int = METADATA_BYTES) -> bytes:
        if self.read_deadline_ns is None:
            return git(self.root, *args, cap=cap)
        duration = min(5_000_000_000, self.read_deadline_ns - time.monotonic_ns())
        try:
            raw, unused_stderr, observation = bounded_local_command(
                local_git_argv(self.root, args), env=local_metadata_environment(),
                stdout_cap=cap, duration_ns=duration)
        except LocalMetadataReadError as exc:
            raise Rejected(exc.reason) from exc
        require(observation['returncode'] == 0, 'F1R1_SOURCE_GIT_READ_FAILED')
        require(time.monotonic_ns() <= self.read_deadline_ns, 'F1R1_CONTROL_PLANE_TIME_BUDGET')
        return raw

    def commit(self, revision: str) -> dict:
        require(oid(revision), 'F1R1_SOURCE_OID_REQUIRED')
        if revision not in self.commits:
            require(len(self.commits) < 256, 'F1R1_SOURCE_METADATA_BYTES_LIMIT')
            self.commits[revision] = parse_commit_object(self._read('cat-file', 'commit', revision, cap=65536), revision)
        return dict(self.commits[revision])

    def member(self, revision: str, path: str) -> dict | None:
        require(type(path) is str and not path.startswith('/') and
                all(part not in ('', '.', '..') for part in path.split('/')), 'F1R1_SOURCE_PATH_ESCAPE')
        tree = self.commit(revision)['tree']
        parts = path.split('/')
        for index, part in enumerate(parts):
            if tree not in self.trees:
                require(len(self.trees) < 512, 'F1R1_SOURCE_METADATA_BYTES_LIMIT')
                self.trees[tree] = parse_tree_object(self._read('cat-file', 'tree', tree), tree)
            entry = self.trees[tree].get(part)
            if entry is None:
                return None
            if index + 1 == len(parts):
                return dict(entry)
            require(entry['mode'] == '040000', 'F1R1_SOURCE_FILE_MODE')
            tree = entry['oid']
        raise Rejected('F1R1_SOURCE_PATH_ESCAPE')

    def blob(self, revision: str, path: str) -> tuple[bytes, dict]:
        entry = self.member(revision, path)
        require(entry is not None and entry['mode'] == '100644', 'F1R1_SOURCE_FILE_MODE')
        raw = self._read('cat-file', 'blob', entry['oid'])
        require(git_object_digest('blob', raw) == entry['oid'], 'F1R1_IMMUTABLE_GIT_OBJECT')
        return raw, entry


def derive_provider_git_roles(objects: ImmutableGitObjects, event: str,
                              checkout: str, detail: dict, event_record: dict) -> dict:
    candidate = detail.get('head', {}).get('sha')
    C = objects.commit(candidate)
    actual = objects.commit(checkout)
    if event == 'push':
        require(event_record.get('after') == checkout and len(actual['parents']) == 1 and
                event_record.get('before') == actual['parents'][0], 'F1R1_IMMUTABLE_MAIN_PARENT_B')
        B = objects.commit(actual['parents'][0])
        return {'S': checkout, 'S_parents': actual['parents'], 'S_tree': actual['tree'],
                'C_tree': C['tree'], 'B_tree': B['tree']}
    require(event == 'pull_request' and len(actual['parents']) == 2 and
            event_record.get('pull_request', {}).get('head', {}).get('sha') == candidate and
            event_record.get('pull_request', {}).get('base', {}).get('sha') == actual['parents'][0],
            'F1R1_EXACT_PR_MERGE_PARENTS')
    B = objects.commit(actual['parents'][0])
    return {'M': checkout, 'M_parents': actual['parents'], 'M_tree': actual['tree'],
            'C_tree': C['tree'], 'B_tree': B['tree']}


def hosted_provider_context(environment: dict, event_record: dict) -> dict:
    require(environment.get('GITHUB_ACTIONS') == 'true' and
            environment.get('GITHUB_REPOSITORY') == REPOSITORY and
            environment.get('GITHUB_REPOSITORY_ID') == str(REPOSITORY_ID) and
            environment.get('GITHUB_JOB') == 'frontend-rss-f1', 'F1R1_ACTUAL_JOB_CONTEXT')
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        require(type(environment.get(key)) is str and re.fullmatch('[1-9][0-9]*', environment[key]),
                'F1R1_ACTUAL_JOB_CONTEXT')
    kind = environment.get('GITHUB_EVENT_NAME')
    require(kind in ('pull_request', 'push') and type(event_record) is dict and
            event_record.get('repository', {}).get('id') == REPOSITORY_ID and
            type(event_record.get('repository', {}).get('id')) is int and
            event_record.get('repository', {}).get('full_name') == REPOSITORY,
            'F1R1_EVENT_SCOPE_NO_SCIENCE')
    checkout = environment.get('GITHUB_SHA')
    require(oid(checkout), 'F1R1_SOURCE_OID_REQUIRED')
    if kind == 'pull_request':
        expected_head = event_record.get('pull_request', {}).get('head', {}).get('sha')
        require(integer(event_record.get('number'), 1) and
                environment.get('GITHUB_REF') == f'refs/pull/{event_record["number"]}/merge',
                'F1R1_RUN_PR_ASSOCIATION')
    else:
        expected_head = checkout
        require(environment.get('GITHUB_REF') == 'refs/heads/main' and
                event_record.get('ref') == 'refs/heads/main' and
                event_record.get('after') == checkout and event_record.get('deleted') is False,
                'F1R1_MAIN_EVENT_SOURCE')
    require(oid(expected_head), 'F1R1_SOURCE_OID_REQUIRED')
    return {'event': kind, 'run_id': int(environment['GITHUB_RUN_ID']),
            'run_attempt': int(environment['GITHUB_RUN_ATTEMPT']),
            'checkout': checkout, 'expected_provider_head': expected_head}


def capture_original_job(context: dict, *, token: str, output: Path) -> dict:
    require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
            'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
    origin = (time.monotonic_ns(), time.time_ns())
    ledger = APIBudgetLedger(context['event'])
    path = api_route('jobs', run_id=context['run_id'], attempt=context['run_attempt'])
    worker = HTTPMetadataWorker(token, ledger, output)
    body = worker.get('FIRST_JOB', 'jobs', path, stage_deadline_ns=None,
                      job_deadline_ns=None, close_after_request=True,
                      first_operation_origin=origin)
    record = ledger.requests[0]
    deadline = validate_original_jobs(body, headers=record['headers_without_credentials'],
                                      run_id=context['run_id'], attempt=context['run_attempt'],
                                      expected_head=context['expected_provider_head'])
    require(deadline['started_epoch_ns'] <= record['started_epoch_ns'] <= record['finished_epoch_ns'],
            'F1R1_ORIGINAL_JOB_BINDING')
    record['selected_job_id'] = deadline['job_id']
    record['original_job_deadline'] = deadline
    record['actual_context'] = dict(context)
    # The one original request envelope also carries its derived deadline;
    # there is no second uncounted raw Jobs metadata file or self-authored clock.
    compact_json(record)
    record['first_operation_measurement_cut'] = 'BEFORE_FINAL_ENVELOPE_ENCODING_AND_WRITE'
    record['first_operation_measurement_cut_monotonic_ns'] = time.monotonic_ns()
    record['first_operation_charged_duration_ns'] = record['admitted_duration_ns']
    charge = original_job_conservative_charge(record)
    # The full original allowance covers validation plus the following final
    # encoding/write. It is conservative accounting, not a measured endpoint.
    ledger.active_acquisition_ns = charge
    encoded = compact_json(record) + b'\n'
    require(len(encoded) <= 65536 and time.monotonic_ns() <= record['deadline_monotonic_ns'],
            'F1R1_CONTROL_PLANE_TIME_BUDGET')
    request_file = output / '01-FIRST_JOB-jobs' / 'request.json'
    request_file.write_bytes(encoded)
    require(time.monotonic_ns() <= record['deadline_monotonic_ns'], 'F1R1_CONTROL_PLANE_TIME_BUDGET')
    return {'deadline_file': str(request_file), 'API_observation_directory': str(output),
            'selected_original_job': deadline, 'HTTP_requests': 1, 'HTTP_helper_starts': 1,
            'HTTP_helper_reaped': True, 'F1_launcher_processes': 0, 'DSP_targets': 0,
            'first_operation_charged_duration_ns': charge}


def replay_original_job(directory: Path, context: dict, ledger: APIBudgetLedger) -> dict:
    raw = bounded_file(directory / '01-FIRST_JOB-jobs' / 'response.json', 2097152)
    record = strict_json(bounded_file(directory / '01-FIRST_JOB-jobs' / 'request.json', 65536), 65536)
    path = api_route('jobs', run_id=context['run_id'], attempt=context['run_attempt'])
    body = ledger.accept('jobs', raw, record, expected_path=path)
    deadline = validate_original_jobs(body, headers=record['headers_without_credentials'],
                                      run_id=context['run_id'], attempt=context['run_attempt'],
                                      expected_head=context['expected_provider_head'])
    require(record.get('actual_context') == context and record.get('original_job_deadline') == deadline and
            record.get('selected_job_id') == deadline['job_id'] and
            deadline['started_epoch_ns'] <= record['started_epoch_ns'], 'F1R1_ORIGINAL_JOB_BINDING')
    # Charge the complete original allowance, including final envelope write;
    # the explicit earlier measurement cut is never treated as a completion.
    duration = original_job_conservative_charge(record)
    ledger.active_acquisition_ns += duration - (record['finished_monotonic_ns'] - record['started_monotonic_ns'])
    return deadline


def provider_sweep_readback(context: dict, event_record: dict, read, graph,
                             *, schema: dict, expected_digests: dict) -> dict:
    """Same ordered validator for bounded live reads or explicit raw replay.

    Only the live wrapper below can supply an HTTP owner. This function never
    constructs a client, supplies a token or grants scientific execution.
    """
    def take(name, **ids):
        path = api_route(name, run_id=context['run_id'], attempt=context['run_attempt'], **ids)
        return read(name, path)
    repository, unused_headers = take('repository')
    require(type(repository) is dict and repository.get('id') == REPOSITORY_ID and
            type(repository.get('id')) is int and repository.get('full_name') == REPOSITORY,
            'F1R1_FREEZE_REPOSITORY_IDENTITY')
    run, unused_headers = take('run')
    run_identity = validate_actual_run(run, run_id=context['run_id'], attempt=context['run_attempt'],
                                       event=context['event'], expected_head=context['expected_provider_head'])
    association, association_next = None, None
    if context['event'] == 'push':
        association, association_headers = take('association', source_S=context['expected_provider_head'])
        association_next = api_has_next_page(association_headers)
    number = select_provider_PR(context['event'], event_record, run, association,
                                association_has_next_page=association_next)
    detail, unused_headers = take('pr', pr_number=number)
    require(type(detail) is dict and detail.get('number') == number and integer(detail.get('id'), 1),
            'F1R1_RUN_PR_ASSOCIATION')
    roles = graph(detail)
    source = actual_provider_C(context['event'], run, association, detail, roles,
                               association_has_next_page=association_next)
    # Actual C/B derive from original run/association/detail/Git before an
    # approval JSON is inspected, including on main after squash.
    issue_before, unused_headers = take('issue_before')
    comments, comment_headers = take('comments')
    no_next = api_has_next_page(comment_headers)
    selected_id = select_freeze_comment(comments, issue_before, source=source,
                                        schema=schema, has_next_page=no_next)
    selected, unused_headers = take('selected', comment_id=selected_id)
    issue_after, unused_headers = take('issue_after')
    sweep = {'repository': repository, 'issue_before': issue_before, 'comments': comments,
             'comments_has_next_page': no_next, 'selected_comment': selected, 'issue_after': issue_after}
    freeze = validate_freeze_sweep(sweep, schema=schema, source=source,
                                   expected_digests=expected_digests,
                                   original_run_created_at=run_identity['created_at'])
    authority = {'id': detail['id'], 'number': number, 'node_id': detail.get('node_id'),
                 'head_sha': detail['head']['sha'], 'head_ref': detail['head']['ref'],
                 'head_repository_id': detail['head']['repo']['id'],
                 'base_ref': detail['base']['ref'], 'base_repository_id': detail['base']['repo']['id']}
    if context['event'] == 'push':
        authority.update(merged=detail['merged'], merged_at=detail['merged_at'],
                         merge_commit_sha=detail['merge_commit_sha'])
    else:
        authority['base_sha'] = detail['base']['sha']
    return {'source': source, 'run_identity': run_identity, 'PR_authority': authority,
            'freeze_identity': freeze, 'scientific_execution_admitted': False}


def acquire_provider_sweep(worker: HTTPMetadataWorker, phase: str, context: dict,
                            event_record: dict, objects: ImmutableGitObjects, *, schema: dict,
                            expected_digests: dict, stage_deadline_ns: int,
                            job_deadline_ns: int, pre: dict | None = None) -> dict:
    require(PROVIDER_EXECUTION_ENABLED and SCIENCE_EXECUTION_ENABLED,
            'F1R1_EXECUTION_DISABLED_AT_BOOTSTRAP')
    require(phase in ('PRE', 'POST'), 'F1R1_CONTROL_PLANE_REQUEST_ORDER')
    require((phase == 'PRE' and pre is None) or (phase == 'POST' and type(pre) is dict),
            'F1R1_CONTROL_PLANE_PHASE_ORDER')
    meter = APIPhaseMeter(worker.ledger, phase, started_ns=time.monotonic_ns(),
                          stage_deadline_ns=stage_deadline_ns, job_deadline_ns=job_deadline_ns)
    def read(name, path):
        meter.checkpoint()
        parsed = worker.get(phase, name, path, stage_deadline_ns=stage_deadline_ns,
                            job_deadline_ns=job_deadline_ns,
                            close_after_request=phase == 'POST' and name == 'issue_after')
        meter.checkpoint()
        return parsed, worker.ledger.requests[-1]['headers_without_credentials']
    def graph(detail):
        meter.checkpoint()
        previous = objects.read_deadline_ns
        objects.read_deadline_ns = meter.deadline_ns
        try:
            return derive_provider_git_roles(objects, context['event'], context['checkout'], detail, event_record)
        finally:
            objects.read_deadline_ns = previous
            meter.checkpoint()
    failure = None
    try:
        result = provider_sweep_readback(context, event_record, read, graph,
                                        schema=schema, expected_digests=expected_digests)
        if phase == 'POST':
            validate_provider_sweep_pair(pre, result)
            worker.ledger.complete()
        compact_json(result)
        return result
    except BaseException as exc:
        failure = exc.reason if isinstance(exc, Rejected) else 'F1R1_CONTROL_PLANE_READBACK_FAILED'
        try:
            meter.checkpoint()
        finally:
            worker.abort_between_requests(stage_deadline_ns=stage_deadline_ns, job_deadline_ns=job_deadline_ns)
        raise
    finally:
        meter.close(failure=failure)


def validate_provider_sweep_pair(pre: dict, post: dict) -> None:
    require(pre == post, 'F1R1_PRE_POST_FREEZE_STABILITY')


def bounded_file(path: Path, cap: int = METADATA_BYTES) -> bytes:
    require(not path.is_symlink() and path.is_file(), "F1R1_REGULAR_FILE_REQUIRED", str(path))
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    require(len(raw) <= cap, "F1R1_SERIALIZED_BYTES_LIMIT", str(path))
    return raw


# F1_R1_LOCAL_GIT_READER_BEGIN
import selectors
import signal

LOCAL_METADATA_DEADLINE_NS = None


class LocalMetadataReadError(RuntimeError):
    def __init__(self, reason, observation=None):
        self.reason = reason
        self.observation = observation or {}
        super().__init__(reason)


def local_metadata_environment(source=None):
    """No inherited Git overrides, credentials, protocol or demand fetching."""
    source = os.environ if source is None else source
    env = {key: value for key, value in source.items()
           if not key.startswith('GIT_') and key not in ('GH_TOKEN', 'GITHUB_TOKEN')}
    env.update(GIT_ALLOW_PROTOCOL='', GIT_NO_LAZY_FETCH='1',
               GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0',
               GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1',
               GIT_CONFIG_SYSTEM='/dev/null', GIT_CONFIG_GLOBAL='/dev/null',
               GIT_LITERAL_PATHSPECS='1')
    return env


def local_git_argv(root, args):
    if not args or args[0] not in ('show', 'rev-parse', 'cat-file', 'ls-tree', 'diff'):
        raise LocalMetadataReadError('F1R1_SOURCE_GIT_COMMAND_NOT_READ_ONLY')
    if args[0] == 'diff' and not all(flag in args for flag in
                                  ('--no-renames', '--no-ext-diff', '--no-textconv')):
        raise LocalMetadataReadError('F1R1_COMPLETE_LOCAL_DIFF_REQUIRED')
    return ['git', '--no-pager', '--no-lazy-fetch', '--no-replace-objects',
            '-c', 'safe.directory=' + str(root), '-c', 'protocol.allow=never',
            '-c', 'core.fsmonitor=false', '-C', str(root), *args]


def local_metadata_deadlines(start_ns, duration_ns=5_000_000_000):
    # Save the admitted integer duration. Never reconstruct it by subtracting
    # large floating point timestamps. Cleanup is inside the same total limit.
    if type(start_ns) is not int or type(duration_ns) is not int or duration_ns < 500_000_001:
        raise LocalMetadataReadError('F1R1_SOURCE_METADATA_DEADLINE')
    return {'started_monotonic_ns': start_ns, 'admitted_duration_ns': duration_ns,
            'work_deadline_monotonic_ns': start_ns + duration_ns - 500_000_000,
            'final_deadline_monotonic_ns': start_ns + duration_ns}


def bounded_metadata_append(buffer, chunk, cap):
    # The sentinel byte is observed but is never retained in the bounded buffer.
    if len(buffer) + len(chunk) > cap:
        raise LocalMetadataReadError('F1R1_SOURCE_METADATA_BYTES_LIMIT')
    buffer.extend(chunk)


def bounded_local_command(argv, *, env, stdout_cap, stderr_cap=65536,
                          duration_ns=5_000_000_000):
    """Drain before cap, then kill/reap within one original monotonic deadline.

    A new session is owned by this call. The leader is not polled/reaped before
    an exceptional group kill, so its PID cannot be recycled before that kill.
    Late or unreaped cleanup is rejection, never a successful bounded read.
    """
    if any(type(cap) is not int or cap < 0 for cap in (stdout_cap, stderr_cap)):
        raise LocalMetadataReadError('F1R1_SOURCE_METADATA_BYTES_LIMIT')
    clock = local_metadata_deadlines(time.monotonic_ns(), duration_ns)
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    selector = selectors.DefaultSelector()
    process = None
    failure = None
    reaped = False
    returncode = None
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=env, close_fds=True, start_new_session=True)
        for stream, name, cap in ((process.stdout, 'stdout', stdout_cap),
                                  (process.stderr, 'stderr', stderr_cap)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, (name, cap))
        while selector.get_map():
            remaining = clock['work_deadline_monotonic_ns'] - time.monotonic_ns()
            if remaining <= 0:
                raise LocalMetadataReadError('F1R1_SOURCE_METADATA_DEADLINE')
            for key, unused_mask in selector.select(remaining / 1_000_000_000):
                name, cap = key.data
                try:
                    chunk = os.read(key.fileobj.fileno(), min(65536, cap - len(buffers[name]) + 1))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                bounded_metadata_append(buffers[name], chunk, cap)
        remaining = clock['work_deadline_monotonic_ns'] - time.monotonic_ns()
        if remaining <= 0:
            raise LocalMetadataReadError('F1R1_SOURCE_METADATA_DEADLINE')
        returncode = process.wait(timeout=remaining / 1_000_000_000)
        reaped = True
    except LocalMetadataReadError as exc:
        failure = exc.reason
    except subprocess.TimeoutExpired:
        failure = 'F1R1_SOURCE_METADATA_DEADLINE'
    except (OSError, ValueError):
        failure = 'F1R1_SOURCE_GIT_READ_FAILED'
    finally:
        # No communicate(), unbounded read(), implicit context-manager wait(),
        # retry, or new cleanup deadline is allowed here.
        if process is not None and not reaped:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                failure = failure or 'F1R1_SOURCE_METADATA_REAP_FAILED'
            remaining = clock['final_deadline_monotonic_ns'] - time.monotonic_ns()
            if remaining > 0:
                try:
                    returncode = process.wait(timeout=remaining / 1_000_000_000)
                    reaped = True
                except subprocess.TimeoutExpired:
                    failure = failure or 'F1R1_SOURCE_METADATA_REAP_FAILED'
            else:
                failure = failure or 'F1R1_SOURCE_METADATA_DEADLINE'
        selector.close()
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    stdout, stderr = bytes(buffers['stdout']), bytes(buffers['stderr'])
    finished = time.monotonic_ns()
    observation = {**clock, 'finished_monotonic_ns': finished,
                   'elapsed_ns': finished - clock['started_monotonic_ns'],
                   'owned_process_reaped': reaped, 'returncode': returncode,
                   'stdout_bytes_retained': len(buffers['stdout']),
                   'stderr_bytes_retained': len(buffers['stderr'])}
    if finished > clock['final_deadline_monotonic_ns'] or not reaped:
        failure = failure or 'F1R1_SOURCE_METADATA_DEADLINE'
    if failure:
        raise LocalMetadataReadError(failure, observation)
    return stdout, stderr, observation


def local_git_read(root, args, *, cap=2097152):
    duration = 5_000_000_000
    if LOCAL_METADATA_DEADLINE_NS is not None:
        duration = min(duration, LOCAL_METADATA_DEADLINE_NS - time.monotonic_ns())
    return bounded_local_command(local_git_argv(root, args),
                                 env=local_metadata_environment(), stdout_cap=cap,
                                 duration_ns=duration)
# F1_R1_LOCAL_GIT_READER_END


def git(root: Path, *args: str, cap: int = METADATA_BYTES, allow_missing: bool = False) -> bytes | None:
    try:
        stdout, unused_stderr, observation = local_git_read(root, args, cap=cap)
    except LocalMetadataReadError as exc:
        raise Rejected(exc.reason) from exc
    if observation['returncode'] != 0:
        if allow_missing and observation['returncode'] == 128:
            return None
        raise Rejected("F1R1_SOURCE_GIT_READ_FAILED", " ".join(args[:2]))
    return stdout


def parse_raw_diff(raw: bytes) -> list[dict]:
    """A complete no-renames tree diff keeps deletion paths and mode changes."""
    reason = "F1R1_COMPLETE_LOCAL_DIFF_REQUIRED"
    require(type(raw) is bytes and len(raw) <= METADATA_BYTES, reason)
    if not raw:
        return []
    fields = raw.split(b'\0')
    require(fields[-1] == b'' and len(fields) % 2 == 1, reason)
    modes = {'000000', '100644', '100755', '120000', '160000'}
    rows, paths = [], set()
    for index in range(0, len(fields) - 1, 2):
        match = re.fullmatch(rb':([0-7]{6}) ([0-7]{6}) ([0-9a-f]{40}) ([0-9a-f]{40}) ([ADMT])', fields[index])
        require(match is not None, reason)
        old_mode, new_mode, old_oid, new_oid, status = (part.decode('ascii') for part in match.groups())
        try:
            path = fields[index + 1].decode('utf-8')
        except UnicodeDecodeError as exc:
            raise Rejected(reason) from exc
        require(path and not path.startswith('/') and '..' not in Path(path).parts and path not in paths, reason)
        require(old_mode in modes and new_mode in modes, reason)
        require((status == 'A') == (old_mode == '000000') == (old_oid == '0' * 40) and
                (status == 'D') == (new_mode == '000000') == (new_oid == '0' * 40), reason)
        if status in ('M', 'T'):
            require((status == 'T') == (old_mode[:3] != new_mode[:3]), reason)
        paths.add(path)
        rows.append({'path': path, 'status': status, 'old_mode': old_mode,
                     'new_mode': new_mode, 'old_oid': old_oid, 'new_oid': new_oid})
    return rows


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
    # The one bootstrap exception ends when B contains its protected guard.
    # PR and its future main event must both reject unready protected changes.
    require(not touches or execution_ready, "F1_OUT_OF_SCOPE_PROTECTED_CHANGE")
    if event["event"] == "pull_request":
        require(not touches or event["registered_candidate"],
                "F1_OUT_OF_SCOPE_PROTECTED_CHANGE")
        required = event["registered_candidate"] and execution_ready
    elif event["event"] == "push":
        # Local guard cannot invent the PR association; force the real job when
        # execution-ready protected inputs change. That job must derive S->PR.
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


A3_IMPACT_STEP = """      - name: Classify A3 source scope from protected base
        id: a3_scope
        shell: bash
        run: sh .github/scripts/verify-docs-gate.sh --a3-scope-only
"""
A3_INPUT = """      run_a3:
        type: boolean
        required: false
        default: false
"""
A3_OUTPUT = """      a3_disposition:
        description: A3 source-only disposition or completely qualified finite experiment
        value: ${{ jobs.frontend-s3-t3s2b1ba3.outputs.disposition }}
"""
A3_SUMMARY = """          # A3_R1_SUMMARY_BEGIN
          case "$A3_REQUIRED" in
            true)
              test "$QUALITY_RESULT" = success
              test "$A3_DISPOSITION" = QUALIFIED_FINITE_A3_LIVE_ROLL_COMPLETE
              ;;
            false)
              case "$A3_DISPOSITION" in
                ''|SOURCE_METADATA_ONLY_UNRELATED|SOURCE_METADATA_ONLY_BOOTSTRAP_NO_A3_EXECUTION) ;;
                *) echo 'A3_UNEXPECTED_SOURCE_DISPOSITION' >&2; exit 1 ;;
              esac
              ;;
            *) echo 'A3_GUARD_OUTPUT_REQUIRED' >&2; exit 1 ;;
          esac
          # A3_R1_SUMMARY_END
"""
F1_SUMMARY = """          # F1_R1_SUMMARY_BEGIN
          case "$F1_REQUIRED" in true|false) ;; *) echo 'F1R1_GUARD_OUTPUT_REQUIRED' >&2; exit 1 ;; esac
          if [ "$F1_REQUIRED" = true ]; then
            test "$QUALITY_RESULT" = success
            test "$F1_DISPOSITION" = FE09_T3S3_F1_R1_COMPLETE_RSS_OBSERVATION_NO_DEVICE_PROMOTION
          else
            case "$F1_DISPOSITION" in
              ''|SOURCE_METADATA_ONLY|F1_SOURCE_METADATA_ONLY_OUT_OF_SCOPE) ;;
              *) echo 'F1R1_UNEXPECTED_SOURCE_DISPOSITION' >&2; exit 1 ;;
            esac
          fi
          # F1_R1_SUMMARY_END
"""
# This is one explicitly registered neighbouring loader, not an arbitrary
# marker-delimited shell exemption. Its complete bytes accompany the shared
# integration candidate for independent review; unknown versions fail closed.
A3_COMPAT_SHELL_SHA256 = "f8c4c4a14d5a05ef4f2632e89c901709dfd1fe814cbb7fee2ae7b64eb275edc1"
COMPAT_METADATA_LINES = frozenset((
    'python3 -I tests/validation/frontend_evolution/fe09_a3_f0_source_admission.py --self-test',
    'python3 -I tests/validation/frontend_evolution/fe09_a3_f0_live_roll_qualification.py --self-test',
    'python3 tests/validation/frontend_evolution/fe09_b3_f0_qualification.py --self-test',
))


def remove_optional_exact(text: str, key_pattern: str, expected: str) -> str:
    matches = list(re.finditer(key_pattern, text, re.M))
    if not matches:
        return text
    require(len(matches) == 1 and text.count(expected) == 1,
            "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED")
    return text.replace(expected, '', 1)


def quality_or_expression(value: str, *, caller: bool, reason: str) -> str:
    prefix = "always() && needs.fast-gate.result == 'success' && (" if caller else '${{ '
    suffix = ')' if caller else ' }}'
    require(value.startswith(prefix) and value.endswith(suffix), reason)
    terms = value[len(prefix):-len(suffix)].split(' || ')
    required = ("needs.impact.outputs.run_quality == 'true'",
                "needs.impact.outputs.f1_required == 'true'")
    allowed = {*required, "needs.impact.outputs.a3_required == 'true'"}
    require(len(terms) == len(set(terms)) and set(required) <= set(terms) <= allowed, reason)
    return prefix + ' || '.join(required) + suffix


def normalize_shared_job(name: str, block: str) -> str:
    """Only the registered A3 additions may disappear from F1's projection."""
    if name == 'impact':
        block = remove_optional_exact(block, r'^      a3_required:',
                                      '      a3_required: ${{ steps.a3_scope.outputs.a3_required }}\n')
        block = remove_optional_exact(block, r'^        id: a3_scope$', A3_IMPACT_STEP)
    elif name == 'quality':
        expression = yaml_scalar(block, 'if', 4)
        normalized = quality_or_expression(expression, caller=True,
                                            reason='F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1')
        block = block.replace('    if: ' + expression + '\n', '    if: ' + normalized + '\n', 1)
        block = remove_optional_exact(block, r'^      run_a3:',
                                      "      run_a3: ${{ needs.impact.outputs.a3_required == 'true' }}\n")
    elif name == 'summary':
        expression = yaml_scalar(block, 'EXPECT_QUALITY', 10)
        normalized = quality_or_expression(expression, caller=False,
                                            reason='F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION')
        block = block.replace('          EXPECT_QUALITY: ' + expression + '\n',
                              '          EXPECT_QUALITY: ' + normalized + '\n', 1)
        for key, expected in (
            ('A3_REQUIRED', '          A3_REQUIRED: ${{ needs.impact.outputs.a3_required }}\n'),
            ('A3_DISPOSITION', '          A3_DISPOSITION: ${{ needs.quality.outputs.a3_disposition }}\n')):
            block = remove_optional_exact(block, r'^          ' + key + ':', expected)
        if '# A3_R1_SUMMARY_BEGIN' in block:
            require(block.count(F1_SUMMARY) == 1 and block.count(A3_SUMMARY) == 1 and
                    block.index(A3_SUMMARY) > block.index(F1_SUMMARY) + len(F1_SUMMARY) - 1,
                    'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED')
        block = remove_optional_exact(block, r'^          # A3_R1_SUMMARY_BEGIN$', A3_SUMMARY)
    return block


def marked_block(text: str, name: str) -> tuple[str, str, str]:
    begin, end = '# ' + name + '_BEGIN\n', '# ' + name + '_END\n'
    require(text.count(begin) == 1 and text.count(end) == 1,
            'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED', name)
    start, stop = text.index(begin), text.index(end) + len(end)
    require(stop > start, 'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED', name)
    return text[:start], text[start:stop], text[stop:]


def shell_projection(raw: bytes) -> bytes:
    text = raw.decode('utf-8')
    before, owned, tail = marked_block(text, 'F1_R1_SOURCE_SCOPE_GUARD')
    require(owned.count('if [ "${1:-}" = --f1-scope-only ]; then\n  exit 0\nfi\n') == 1,
            'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED')
    require('A3_R1_SOURCE_SCOPE_GUARD' not in before + owned,
            'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED')
    if 'A3_R1_SOURCE_SCOPE_GUARD' in tail:
        prefix, a3, suffix = marked_block(tail, 'A3_R1_SOURCE_SCOPE_GUARD')
        require(not prefix.strip() and sha(a3.encode()) == A3_COMPAT_SHELL_SHA256,
                'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED', 'unreviewed A3 shell loader')
        tail = prefix + suffix
    counts = {line: tail.splitlines().count(line) for line in COMPAT_METADATA_LINES}
    require(all(count <= 1 for count in counts.values()), 'F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED')
    # Every remaining executable byte is retained, including the historical
    # gate. This does not accept arbitrary commands, env, traps or here-docs.
    normalized_tail = '\n'.join(line for line in tail.splitlines()
                                if line.strip() and line not in COMPAT_METADATA_LINES)
    return json.dumps({'prelude': before, 'f1_owned': owned, 'remaining_gate': normalized_tail},
                      sort_keys=True, separators=(',', ':')).encode()


def workflow_projection(raw: bytes, workflow: str) -> bytes:
    """Preserve shared globals and F1 routing; normalize exact A3 additions.

    Unrelated job bodies may change. Unknown shared keys, aliases, permissions,
    dispatch conditions or shell operations never gain an implicit exemption.
    """
    text = raw.decode("utf-8")
    require(text.count("\njobs:\n") == 1, "F1R1_HOOK_NONINTERFERENCE_PROOF_REQUIRED")
    header, jobs = text.split("\njobs:\n", 1)
    if workflow == 'quality':
        header = remove_optional_exact(header, r'^      run_a3:', A3_INPUT)
        header = remove_optional_exact(header, r'^      a3_disposition:', A3_OUTPUT)
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
            block = jobs[match.start():end]
            blocks.append(normalize_shared_job(match.group(1), block) if workflow == 'verify' else block)
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
    require(yaml_scalar(caller, "needs", 4) == "[impact, fast-gate]",
            "F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")
    quality_or_expression(yaml_scalar(caller, "if", 4), caller=True,
                          reason="F1R1_DOCS_ACTIVATION_MUST_SCHEDULE_F1")
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
    shell_projection(entry.encode())
    summary = yaml_block(verify, "summary", 2)
    quality_or_expression(yaml_scalar(summary, "EXPECT_QUALITY", 10), caller=False,
                          reason="F1R1_REQUIRED_QUALITY_RESULT_PROPAGATION")
    require(yaml_scalar(summary, "F1_REQUIRED", 10) == "${{ needs.impact.outputs.f1_required }}" and
            yaml_scalar(summary, "F1_DISPOSITION", 10) == "${{ needs.quality.outputs.f1_disposition }}" and
            summary.count(F1_SUMMARY) == 1,
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
    for name, kind in ((HOOKS[0], "verify"), (HOOKS[1], "quality"), (HOOKS[2], "entry")):
        if name in changed:
            before = object_bytes(root, base, name)
            after = object_bytes(root, head, name)
            projection = shell_projection if kind == 'entry' else lambda raw: workflow_projection(raw, kind)
            if projection(before) == projection(after):
                result.remove(name)
    return result & protected


def source_guard(root: Path, event_name: str, event: dict,
                 guard_origin: str | None) -> dict:
    global LOCAL_METADATA_DEADLINE_NS
    started = time.monotonic_ns()
    # Leave one second for the bounded receipt and the outer guard's cleanup.
    # Each Git PID must finish/reap before the outer 60-second owner can end.
    inherited = os.environ.get('FE_F1_SOURCE_METADATA_DEADLINE_NS')
    require(inherited is None or re.fullmatch(r'[0-9]{1,20}', inherited) is not None,
            'F1R1_SOURCE_METADATA_DEADLINE')
    LOCAL_METADATA_DEADLINE_NS = min(started + 59_000_000_000,
                                    int(inherited) if inherited is not None else started + 59_000_000_000)
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
    changed_raw = git(root, "diff", "--raw", "-z", "--no-abbrev", "--no-renames",
                      "--no-ext-diff", "--no-textconv", base, head, "--")
    diff_rows = parse_raw_diff(changed_raw)
    changed = {row['path'] for row in diff_rows}
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
            "complete_no_renames_diff_sha256": sha(changed_raw),
            "complete_no_renames_diff_records": len(diff_rows),
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
        require(sys.flags.isolated == 1, 'F1R1_ISOLATED_PYTHON_REQUIRED')
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
