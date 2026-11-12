#!/usr/bin/env python3
"""Inspect one immutable failed D8 artifact; no repository imports or execution."""
import time
STARTED = time.monotonic()
import os
import sys
import resource

sys.dont_write_bytecode = True
DEADLINE = STARTED + 300.0
LIMIT_REQUESTS = {"AS": 268435456, "NOFILE": 32, "CORE": 0, "FSIZE": 543037811}
ACTUAL_LIMITS = {}
for _name, _requested in LIMIT_REQUESTS.items():
    _key = getattr(resource, "RLIMIT_" + _name)
    _soft, _hard = resource.getrlimit(_key)
    _effective = min(v for v in (_soft, _hard, _requested) if v != resource.RLIM_INFINITY)
    resource.setrlimit(_key, (_effective, _effective))
    if resource.getrlimit(_key) != (_effective, _effective):
        os._exit(125)
    ACTUAL_LIMITS[_name] = {"inherited_soft": _soft, "inherited_hard": _hard,
                            "requested": _requested, "effective": _effective}

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = "jiying2007/audio-pipeline"
BRANCH = "refs/heads/diagnostic/d8-attempt-43121241713"
RUN = 43121241713
ATTEMPT = 1
HEAD = "4a86ad099010ae1aead149414091b88be73c7f3e"
ARTIFACT = 13900578432
ARTIFACT_NAME = "frontend-research-dualmic-broadside-output-d8-43121241713-attempt-1"
ARCHIVE_BYTES = 543037811
ARCHIVE_SHA = "d2744826ec842956b55610a7f33e905c1a17483f9d0c2b52fef7987356737ca5"
ROOT = Path("/tmp/ap-d8-receipt-inspection")
ARCHIVE = ROOT / "archive.zip"
REPORT_PATH = ROOT / "report.json"
REPORT_LIMIT = 25165824
JOINT_LIMIT = 568203635
CONSOLE_LIMIT = 524288
JSON_LIMIT = 1048576
SELECTED_LIMIT = 16777216
CENTRAL_LIMIT = 4194304
ENTRY_LIMIT = 4096
UNCOMPRESSED_LIMIT = 1073741824
REGULAR_ENTRIES = 1842
PHASES = ("admission", "baseline-build", "candidate-build", "run", "analysis", "verify", "negative")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
COMMAND = re.compile(r"result/(" + "|".join(PHASES) + r")-logs/([A-Za-z0-9_.-]{1,128})\.command\.json\Z")
INVENTORY = re.compile(r"build/tool-inventories/([0-9a-f]{64})\.json\Z")
OWN_WRITTEN = 0
SELECTED_READ = 0
ROOT_OWNED = False
REPORT = {"schema_version": 1, "status": "DIAGNOSTIC_INVALID", "inspection_complete": False,
          "DSP_executed": False, "builds_executed": False, "models_executed": False,
          "promotion_allowed": False, "source_artifact_modified": False,
          "limits": ACTUAL_LIMITS, "receipts": [], "inventory_observations": []}

class Invalid(Exception):
    pass

class RecordInvalid(Exception):
    pass

def check():
    left = DEADLINE - time.monotonic()
    if left <= 0:
        os._exit(124)  # No timeout report, cleanup, implicit flush, or grace.
    return left

def need(value, reason):
    if not value:
        raise Invalid(reason)

def schema(value, reason):
    if not value:
        raise RecordInvalid(reason)

def integer(value, minimum=0, maximum=None):
    return type(value) is int and value >= minimum and (maximum is None or value <= maximum)

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def encode(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")

def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise RecordInvalid("JSON_DUPLICATE_KEY")
        value[key] = item
    return value

def no_constant(_value):
    raise RecordInvalid("JSON_NONFINITE")

def parse(raw):
    value = json.loads(raw, object_pairs_hook=no_duplicates, parse_constant=no_constant)
    return value

def safe_name(name, *, directory=False):
    need(type(name) is str and 0 < len(name.encode("utf-8")) <= 1024 and
         "\x00" not in name and "\\" not in name, "ZIP_MEMBER_NAME")
    bare = name[:-1] if directory and name.endswith("/") else name
    pure = PurePosixPath(bare)
    need(bare and not pure.is_absolute() and pure.as_posix() == bare and
         all(part not in ("", ".", "..") for part in bare.split("/")), "ZIP_MEMBER_NAME")
    return bare

def owned_write(file, block, current, maximum):
    global OWN_WRITTEN
    check()
    need(current + len(block) <= maximum and OWN_WRITTEN + len(block) <= JOINT_LIMIT,
         "OWN_WRITE_CAP")
    view = memoryview(block)
    while view:
        check()
        count = file.write(view)
        need(type(count) is int and 0 < count <= len(view), "SHORT_WRITE")
        current += count
        OWN_WRITTEN += count
        view = view[count:]
    return current

def at(file, offset, count):
    check()
    need(integer(offset) and integer(count, 0, CENTRAL_LIMIT) and
         offset + count <= ARCHIVE_BYTES, "ZIP_METADATA_RANGE")
    file.seek(offset)
    value = file.read(count)
    check()
    need(len(value) == count, "ZIP_METADATA_SHORT_READ")
    return value

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

def api_request(path, token, *, redirect=False):
    check()
    need(path.startswith("/repos/" + REPOSITORY + "/") and "?" not in path and
         "\n" not in path, "API_PATH")
    request = urllib.request.Request("https://api.github.com" + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "fixed-d8-receipt-inspector"})
    try:
        response = OPENER.open(request, timeout=min(30.0, check()))
    except urllib.error.HTTPError as error:
        if redirect and error.code == 302:
            location = error.headers.get("Location", "")
            error.close()
            check()
            return location
        code = error.code
        error.close()
        raise Invalid("API_HTTP_STATUS_" + str(code)) from None
    need(not redirect and response.status == 200, "API_STATUS")
    raw = response.read(JSON_LIMIT + 1)
    response.close()
    check()
    need(len(raw) <= JSON_LIMIT, "API_JSON_CAP")
    try:
        value = parse(raw)
    except (ValueError, UnicodeError, RecordInvalid):
        raise Invalid("API_JSON_INVALID") from None
    need(type(value) is dict, "API_JSON_SCHEMA")
    return value

def identities(token):
    run = api_request("/repos/" + REPOSITORY + "/actions/runs/" + str(RUN), token)
    artifact = api_request("/repos/" + REPOSITORY + "/actions/artifacts/" + str(ARTIFACT), token)
    need(type(run.get("repository")) is dict and run["repository"].get("full_name") == REPOSITORY and
         type(run.get("id")) is int and run["id"] == RUN and type(run.get("run_attempt")) is int and run["run_attempt"] == ATTEMPT and
         run.get("head_sha") == HEAD and run.get("status") == "completed" and
         run.get("conclusion") == "failure", "RUN_IDENTITY")
    bound = artifact.get("workflow_run")
    need(type(bound) is dict and bound.get("id") == RUN and bound.get("head_sha") == HEAD and
         type(artifact.get("id")) is int and artifact["id"] == ARTIFACT and artifact.get("name") == ARTIFACT_NAME and
         type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] == ARCHIVE_BYTES and
         artifact.get("digest") == "sha256:" + ARCHIVE_SHA and artifact.get("expired") is False,
         "ARTIFACT_IDENTITY")
    REPORT["source"] = {"repository": REPOSITORY, "run_id": RUN, "attempt": ATTEMPT, "head_sha": HEAD,
        "run_status": run["status"], "run_conclusion": run["conclusion"], "artifact_id": ARTIFACT,
        "artifact_name": ARTIFACT_NAME, "archive_bytes": ARCHIVE_BYTES, "archive_sha256": ARCHIVE_SHA,
        "expired": False}
    # Never retain or print API bodies, Authorization, signed URLs or network exceptions.
    return api_request("/repos/" + REPOSITORY + "/actions/artifacts/" + str(ARTIFACT) + "/zip",
                       token, redirect=True)

def download(location):
    parts = urllib.parse.urlsplit(location)
    need(parts.scheme == "https" and parts.hostname is not None and
         parts.hostname.endswith(".blob.core.windows.net") and parts.hostname != ".blob.core.windows.net" and
         parts.username is None and parts.password is None and parts.port in (None, 443) and
         not parts.fragment, "BLOB_DESTINATION")
    request = urllib.request.Request(location, headers={"User-Agent": "fixed-d8-receipt-inspector",
                                                        "Accept": "application/octet-stream"})
    try:
        response = OPENER.open(request, timeout=min(30.0, check()))
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        raise Invalid("BLOB_HTTP_STATUS_" + str(code)) from None
    need(response.status == 200 and response.headers.get("Content-Encoding", "identity") == "identity",
         "BLOB_RESPONSE")
    length = response.headers.get("Content-Length")
    need(length is None or length == str(ARCHIVE_BYTES), "BLOB_CONTENT_LENGTH")
    total, digest = 0, hashlib.sha256()
    with ARCHIVE.open("xb", buffering=0) as file:
        while True:
            check()
            block = response.read(min(1048576, ARCHIVE_BYTES - total + 1))
            check()
            if not block:
                break
            total = owned_write(file, block, total, ARCHIVE_BYTES)
            digest.update(block)
    response.close()
    check()
    need(total == ARCHIVE_BYTES and digest.hexdigest() == ARCHIVE_SHA, "ARCHIVE_IDENTITY")
    REPORT["archive_verified_before_zip"] = True


def central_bounds(file):
    tail_length = min(65557, ARCHIVE_BYTES)
    tail = at(file, ARCHIVE_BYTES - tail_length, tail_length)
    found = tail.rfind(b"PK\x05\x06")
    need(found >= 0 and len(tail) - found >= 22, "ZIP_EOCD")
    signature, disk, central_disk, disk_count, count, size, offset, comment = struct.unpack(
        "<4s4H2IH", tail[found:found + 22])
    eocd = ARCHIVE_BYTES - tail_length + found
    need(found + 22 + comment == len(tail) and disk == central_disk == 0, "ZIP_MULTIDISK_OR_TAIL")
    boundary = eocd
    if count == 65535 or disk_count == 65535 or size == 0xffffffff or offset == 0xffffffff:
        locator = at(file, eocd - 20, 20)
        sig, record_disk, record_offset, disks = struct.unpack("<4sIQI", locator)
        need(sig == b"PK\x06\x07" and record_disk == 0 and disks == 1, "ZIP64_LOCATOR")
        record = at(file, record_offset, 56)
        fields = struct.unpack("<4sQ2H2I4Q", record)
        need(fields[0] == b"PK\x06\x06" and 44 <= fields[1] <= 65536 and
             fields[4] == fields[5] == 0 and record_offset + 12 + fields[1] == eocd - 20,
             "ZIP64_EOCD")
        disk_count, count, size, offset = fields[6:]
        boundary = record_offset
    need(disk_count == count and 0 < count <= ENTRY_LIMIT and 0 < size <= CENTRAL_LIMIT and
         offset + size == boundary, "ZIP_CENTRAL_BOUND")
    return {"entries": count, "size": size, "offset": offset, "boundary": boundary}

def local_record(file, item, central_offset):
    header = at(file, item.header_offset, 30)
    fields = struct.unpack("<4s5H3I2H", header)
    signature, _version, flags, method, _mtime, _mdate, crc, compressed, size, namelen, extralen = fields
    need(signature == b"PK\x03\x04" and flags == item.flag_bits and method == item.compress_type and
         0 < namelen <= 1024, "ZIP_LOCAL_HEADER")
    name_raw = at(file, item.header_offset + 30, namelen)
    try:
        name = name_raw.decode("utf-8" if flags & 2048 else "cp437")
    except UnicodeError:
        raise Invalid("ZIP_LOCAL_NAME") from None
    need(name == item.orig_filename, "ZIP_LOCAL_NAME")
    extra = at(file, item.header_offset + 30 + namelen, extralen)
    zip64 = size == 0xffffffff or compressed == 0xffffffff
    pos, extended = 0, None
    while pos < len(extra):
        need(pos + 4 <= len(extra), "ZIP_LOCAL_EXTRA")
        kind, length = struct.unpack("<HH", extra[pos:pos + 4])
        pos += 4
        need(pos + length <= len(extra), "ZIP_LOCAL_EXTRA")
        if kind == 1:
            need(extended is None, "ZIP_LOCAL_EXTRA")
            extended = extra[pos:pos + length]
        pos += length
    if zip64:
        need(extended is not None, "ZIP_LOCAL_ZIP64")
        position = 0
        if size == 0xffffffff:
            need(position + 8 <= len(extended), "ZIP_LOCAL_ZIP64")
            size = struct.unpack("<Q", extended[position:position + 8])[0]
            position += 8
        if compressed == 0xffffffff:
            need(position + 8 <= len(extended), "ZIP_LOCAL_ZIP64")
            compressed = struct.unpack("<Q", extended[position:position + 8])[0]
    start = item.header_offset + 30 + namelen + extralen
    end = start + item.compress_size
    need(end <= central_offset, "ZIP_LOCAL_RANGE")
    if flags & 8:
        need(crc in (0, item.CRC) and compressed in (0, item.compress_size) and
             size in (0, item.file_size), "ZIP_LOCAL_DESCRIPTOR_HEADER")
        count = 24 if zip64 else 16
        raw = at(file, end, count)
        prefix = 4 if raw[:4] == b"PK\x07\x08" else 0
        width = 20 if zip64 else 12
        values = struct.unpack("<IQQ" if zip64 else "<III", raw[prefix:prefix + width])
        need(values == (item.CRC, item.compress_size, item.file_size), "ZIP_DATA_DESCRIPTOR")
        end += prefix + width
    else:
        need((crc, compressed, size) == (item.CRC, item.compress_size, item.file_size),
             "ZIP_LOCAL_IDENTITY")
    need(0 <= item.header_offset < end <= central_offset, "ZIP_LOCAL_RANGE")
    return (item.header_offset, end)

def validate_zip(file, archive, central):
    items = archive.infolist()
    need(len(items) == central["entries"] and len(items) <= ENTRY_LIMIT, "ZIP_ENTRY_COUNT")
    members, intervals, total, regular = {}, [], 0, 0
    for item in items:
        check()
        directory = item.is_dir()
        name = safe_name(item.orig_filename, directory=directory)
        need(item.filename == item.orig_filename and name not in members, "ZIP_DUPLICATE_NAME")
        mode = (item.external_attr >> 16) & 0xffff
        kind = stat.S_IFMT(mode)
        need(not item.flag_bits & (1 | 64) and
             item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
             "ZIP_ENCRYPTION_OR_COMPRESSION")
        need((directory and kind in (0, stat.S_IFDIR) and item.file_size == 0) or
             (not directory and kind in (0, stat.S_IFREG)), "ZIP_MEMBER_TYPE")
        need(integer(item.file_size, 0, UNCOMPRESSED_LIMIT) and
             integer(item.compress_size, 0, ARCHIVE_BYTES), "ZIP_MEMBER_SIZE")
        total += item.file_size
        need(total <= UNCOMPRESSED_LIMIT, "ZIP_TOTAL_SIZE")
        regular += not directory
        members[name] = item
        intervals.append(local_record(file, item, central["offset"]))
    need(regular == REGULAR_ENTRIES, "ZIP_REGULAR_COUNT")
    for name in members:
        parent = PurePosixPath(name).parent
        while str(parent) != ".":
            if str(parent) in members:
                need(members[str(parent)].is_dir(), "ZIP_FILE_PARENT")
            parent = parent.parent
    intervals.sort()
    need(all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])),
         "ZIP_LOCAL_OVERLAP")
    REPORT["zip_metadata"] = {"total_entries": len(items), "regular_entries": regular,
        "uncompressed_bytes": total, "central_directory_bytes": central["size"],
        "normalized_unique_names": True, "regular_or_directory_only": True,
        "unencrypted_store_or_deflate": True, "local_headers_checked": True,
        "nonoverlapping_local_records": True, "no_extraction": True, "nested_archives_opened": False}
    return members

def metadata(item):
    return {"bytes": item.file_size, "compressed_bytes": item.compress_size, "crc32": item.CRC}

def member_read(archive, item, maximum=JSON_LIMIT):
    global SELECTED_READ
    check()
    need(item.file_size <= maximum and SELECTED_READ + item.file_size <= SELECTED_LIMIT, "SELECTED_JSON_CAP")
    with archive.open(item, "r") as stream:
        raw = stream.read(item.file_size + 1)
    check()
    need(len(raw) == item.file_size, "SELECTED_JSON_LENGTH")
    SELECTED_READ += len(raw)
    return raw


BASE_ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/tmp/ap-dualmic-d8/toolchain/home",
    "TMPDIR": "/tmp/ap-dualmic-d8/toolchain/tmp", "TMP": "/tmp/ap-dualmic-d8/toolchain/tmp",
    "TEMP": "/tmp/ap-dualmic-d8/toolchain/tmp", "LC_ALL": "C", "LANG": "C", "TZ": "UTC",
    "PYTHONDONTWRITEBYTECODE": "1", "XDG_CONFIG_HOME": "/tmp/ap-dualmic-d8/toolchain/home/config",
    "XDG_CACHE_HOME": "/tmp/ap-dualmic-d8/toolchain/home/cache",
    "XDG_DATA_HOME": "/tmp/ap-dualmic-d8/toolchain/home/data",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ATTR_NOSYSTEM": "1",
    "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
KEYS = {
 "phase": {"experiment","phase","status","budget_seconds","commands","first_failure","root_started",
           "root_deadline","phase_deadline","supervisor_limits","worker_limits","elapsed_seconds","elapsed_scope"},
 "command": {"argv","cwd","timeout_seconds","deadline","phase_deadline","root_deadline","status","returncode",
     "timed_out","lifecycle","environment","stdout_limit","stderr_limit","requested_limits","scientific",
     "free_space","worker_pgid","tool_inventory_before","effective_limits","tool_inventory_after",
     "elapsed_seconds","stdout","stderr","reason"},
 "admission": {"experiment","status","DSP_executed","models_executed","promotion_allowed","freeze",
     "source_revision","artifact","member_count","uncompressed_bytes","original_D2_readback_exact",
     "case_count","frames","samples","elapsed_seconds","budget_seconds","elapsed_scope","failure_type","failure_reason"},
 "first_failure": {"experiment","status","phase","target","first_failure","promotion_allowed","type","reason"},
 "run_index": {"experiment","source","completed","cases","forms","status"}
}
SECRET_KEY = re.compile(r"(?i)(^|_)(authorization|password|passwd|token|secret|cookie|signed_url|download_url)($|_)")
SECRET_TEXT = re.compile(r"(?i)(https?://|github_pat_|gh[pousr]_[A-Za-z0-9]|bearer\s|password=|token=)")

def safe_values(value):
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        schema(depth <= 32 and nodes <= 200000, "SCHEMA_COMPLEXITY")
        if type(item) is dict:
            for key, nested in item.items():
                schema(type(key) is str and len(key) <= 1024 and SECRET_KEY.search(key) is None,
                       "SCHEMA_UNSAFE_FIELD")
                pending.append((nested, depth + 1))
        elif type(item) is list:
            pending.extend((nested, depth + 1) for nested in item)
        elif type(item) is str:
            schema(len(item) <= 8192 and SECRET_TEXT.search(item) is None, "SCHEMA_UNSAFE_VALUE")
        elif type(item) is float:
            schema(math.isfinite(item), "JSON_NONFINITE")
        else:
            schema(item is None or type(item) in (int, bool), "SCHEMA_VALUE_TYPE")

def receipt_schema(value, kind, name):
    schema(type(value) is dict and set(value) <= KEYS[kind], "SCHEMA_TOP_LEVEL")
    safe_values(value)
    schema(type(value.get("status")) is str, "SCHEMA_STATUS")
    if kind == "phase":
        expected = name[len("result/"):-len("-phase.json")]
        schema(value.get("phase") == expected and value["status"] in ("PASS","FAIL") and
               type(value.get("commands")) is list and
               all(type(p) is str and COMMAND.fullmatch("result/" + p) and
                   p.startswith(expected + "-logs/") for p in value["commands"]) and
               value.get("budget_seconds") == 300, "SCHEMA_PHASE")
    elif kind == "command":
        schema(value["status"] in ("PASS","FAIL") and value.get("lifecycle") in ("PENDING","TERMINAL") and
               type(value.get("argv")) is list and len(value["argv"]) <= 512 and
               all(type(s) is str and len(s) <= 1024 for s in value["argv"]) and
               type(value.get("environment")) is dict, "SCHEMA_COMMAND")
        env = value["environment"]
        schema(set(BASE_ENV) <= set(env) <= set(BASE_ENV) | {
            "AP_D1_STAGE_DIR","AP_D8_STAGE_DIR","AP_D8_EXPECTED_FRAMES"} and
            all(env[k] == expected for k, expected in BASE_ENV.items()), "SCHEMA_ENVIRONMENT")
        for key, ending in (("AP_D1_STAGE_DIR","-d1"),("AP_D8_STAGE_DIR","-upstream")):
            if key in env:
                schema(env[key] in {"/tmp/ap-dualmic-d8/result/scratch/current/" + arm + ending
                                   for arm in ("baseline","candidate")}, "SCHEMA_ENVIRONMENT")
        if "AP_D8_EXPECTED_FRAMES" in env:
            frames = env["AP_D8_EXPECTED_FRAMES"]
            schema(type(frames) is str and re.fullmatch(r"[0-9]{3}", frames) is not None and
                   529 <= int(frames) <= 629, "SCHEMA_ENVIRONMENT")
    elif kind == "admission":
        schema(value.get("experiment") == "FE-DUALMIC-ZERO-D3-INPUT" and
               value["status"] in ("INPUT_ADMITTED_NO_DSP_EXECUTION","FAIL"), "SCHEMA_ADMISSION")
    elif kind == "run_index":
        schema(value.get("experiment") == "FE-DUALMIC-BROADSIDE-OUTPUT-D8" and
               type(value.get("completed")) is list and type(value.get("cases")) is list and
               type(value.get("source")) is dict, "SCHEMA_RUN_INDEX")
    for key in ("deadline","phase_deadline","root_deadline","root_started","timeout_seconds","elapsed_seconds"):
        if key in value:
            schema(finite(value[key]), "SCHEMA_TIMESTAMP")
    if "returncode" in value:
        schema(value["returncode"] is None or type(value["returncode"]) is int, "SCHEMA_RETURNCODE")
    return value

def read_receipt(archive, members, name, kind):
    if name not in members:
        return {"path": name, "presence": "ABSENT", "kind": kind}
    item = members[name]
    need(not item.is_dir(), "SELECTED_MEMBER_TYPE")
    cap = 65536 if kind == "command" and name.startswith("result/run-logs/") else JSON_LIMIT
    raw = member_read(archive, item, cap)
    record = {"path": name, "presence": "PRESENT", "kind": kind,
              "raw_bytes": len(raw), "raw_sha256": hashlib.sha256(raw).hexdigest()}
    try:
        value = parse(raw)
        receipt_schema(value, kind, name)
        record.update(parse_status="VALID_JSON", schema_status="KNOWN_NONSECRET_D8_FIELDS", value=value)
    except json.JSONDecodeError as error:
        record.update(parse_status="INVALID_JSON", schema_status="NOT_EVALUATED",
                      reason="JSON_SYNTAX", error_position=error.pos, error_line=error.lineno,
                      error_column=error.colno)
    except (UnicodeError, ValueError, RecursionError):
        record.update(parse_status="INVALID_JSON", schema_status="NOT_EVALUATED", reason="JSON_ENCODING_OR_NUMBER_OR_DEPTH")
    except RecordInvalid as error:
        reason = error.args[0]
        record.update(parse_status="INVALID_OR_SCHEMA_REJECTED", schema_status="REJECTED", reason=reason)
    return record

def command_start(record):
    value = record.get("value")
    if type(value) is not dict or record["kind"] != "command":
        return None
    deadline, timeout = value.get("deadline"), value.get("timeout_seconds")
    if not finite(deadline) or not finite(timeout) or not 0 < timeout <= 30:
        return None
    started = deadline - timeout
    return started if finite(started) else None

def lifecycle(record):
    value = record.get("value", {})
    row = {key: record[key] for key in ("path","presence","raw_bytes","raw_sha256","parse_status","schema_status")
           if key in record}
    row["observed_start"] = command_start(record)
    for key in ("status","lifecycle","returncode","timed_out","deadline","phase_deadline",
                "root_deadline","timeout_seconds","elapsed_seconds"):
        if key in value:
            row[key] = value[key]
    if "reason" in record:
        row["receipt_issue"] = record["reason"]
    return row

def latest_receipts(records):
    commands = [record for record in records if record["kind"] == "command"]
    timed = [(command_start(record), record) for record in commands if command_start(record) is not None]
    timed.sort(key=lambda pair: (pair[0], pair[1]["path"]))
    selected = [record for _, record in timed[-2:]]
    missing = [record["path"] for record in commands if command_start(record) is None]
    tie = bool(timed and len(timed) > 2 and timed[-3][0] == timed[-2][0])
    all_ties = any(left[0] == right[0] for left, right in zip(timed, timed[1:]))
    result = {"basis": "finite original deadline minus timeout_seconds only",
              "selected_known_timed_receipts": [r["path"] for r in selected],
              "missing_or_invalid_timing": missing, "ties_anywhere": all_ties,
              "tie_at_selection_boundary": tie, "chronology_ambiguous": bool(missing or all_ties),
              "tie_breaker": "path is only deterministic selection/display, never time evidence",
              "culprit_inferred": False}
    return selected, result

def read_inventory(archive, members, reference):
    relative = reference.get("path") if type(reference) is dict else None
    match = INVENTORY.fullmatch(relative) if type(relative) is str else None
    if not match or set(reference) != {"path","bytes","sha256"} or not integer(reference.get("bytes")) or \
            reference.get("sha256") != match.group(1):
        return {"status": "INVALID_REFERENCE"}
    name = "result/" + relative
    output = {"path": name, "expected": reference}
    if name not in members:
        return {**output, "status": "ABSENT"}
    item = members[name]
    if item.file_size > JSON_LIMIT or SELECTED_READ + item.file_size > SELECTED_LIMIT:
        return {**output, "status": "NOT_READ_CAP", "metadata": metadata(item)}
    raw = member_read(archive, item)
    output.update(raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
    if len(raw) != reference["bytes"] or output["raw_sha256"] != reference["sha256"]:
        return {**output, "status": "RAW_IDENTITY_MISMATCH"}
    try:
        value = parse(raw)
        schema(type(value) is dict and set(value) == {"files","directories"} and
               type(value["files"]) is dict and type(value["directories"]) is list, "INVENTORY_SCHEMA")
        safe_values(value)
        total, roots = 0, {}
        for name, identity in value["files"].items():
            safe_name(name)
            schema(type(identity) is dict and set(identity) == {"bytes","sha256"} and
                   integer(identity["bytes"], 0, 16777216) and
                   type(identity["sha256"]) is str and HEX64.fullmatch(identity["sha256"]) is not None,
                   "INVENTORY_SCHEMA")
            total += identity["bytes"]
            root = name.split("/", 1)[0]
            row = roots.setdefault(root, {"files": 0, "bytes": 0})
            row["files"] += 1
            row["bytes"] += identity["bytes"]
        schema(total <= 134217728 and len(value["directories"]) == len(set(value["directories"])),
               "INVENTORY_SCHEMA")
        for name in value["directories"]:
            safe_name(name)
        output.update(status="IDENTITY_AND_SCHEMA_CHECKED", logical_bytes=total,
                      file_count=len(value["files"]), directory_count=len(value["directories"]),
                      root_totals=roots, values_scope="summary only; not binaries or source bodies")
    except (ValueError, UnicodeError, RecordInvalid, Invalid, RecursionError, TypeError):
        output["status"] = "PARSE_OR_SCHEMA_REJECTED"
    return output


PROGRESS_FILES = ("result/input-binding.json","result/build/build.json","result/run-index.json",
    "result/report.json","result/seal.json","result/readback.json","result/negative-tests.json",
    "result/summary.json","result/completion.json","result/first-failure.json")
CAVEATS = [
    "This is receipt inspection only, never a DSP/build result or promotion.",
    "A phase starts with status FAIL and first_failure null; that is pending, not a diagnosed failure.",
    "A pending command is appended in memory before its receipt is written; the phase command list can lag.",
    "A command receipt is written before logs and Popen; missing effective_limits cannot prove no child ran.",
    "Command PASS is persisted before capture read and COMMAND_END acknowledgement.",
    "Phase PASS is persisted before its finalizer and phase-end or finish acknowledgement.",
    "run-index.json is terminal, not incremental. retention.json precedes its moves and discards.",
    "Only finite deadline minus timeout_seconds orders commands; filenames and ZIP timestamps do not.",
    "Missing or tied start times make chronology ambiguous. Latest known receipt is not a claimed culprit.",
    "Worker stdout is piped and buffered; no admission console line does not prove no admission or DSP occurred.",
    "Timeout termination intentionally does not flush, run finally cleanup or write a terminal timeout receipt.",
    "ZIP metadata presence and partial bytes do not establish scientific validity."
]

def inspect(archive, members):
    fixed = [("result/" + phase + "-phase.json", "phase") for phase in PHASES]
    fixed += [("input/admission.json", "admission"), ("result/first-failure.json", "first_failure"),
              ("result/run-index.json", "run_index")]
    command_names = sorted(name for name, item in members.items() if COMMAND.fullmatch(name) and not item.is_dir())
    need(len(command_names) <= 512, "COMMAND_RECEIPT_COUNT")
    selected = fixed + [(name, "command") for name in command_names]
    total = 0
    for name, kind in selected:
        if name in members:
            maximum = 65536 if kind == "command" and name.startswith("result/run-logs/") else JSON_LIMIT
            need(not members[name].is_dir() and members[name].file_size <= maximum, "SELECTED_JSON_CAP")
            total += members[name].file_size
    need(total <= SELECTED_LIMIT, "SELECTED_JSON_AGGREGATE")
    REPORT["selection"] = {"fixed_paths": [name for name, _ in fixed], "command_paths": command_names,
        "command_count": len(command_names), "all_matching_commands_selected": True,
        "scientific_member_cap": 65536, "other_json_member_cap": JSON_LIMIT,
        "aggregate_json_cap": SELECTED_LIMIT}
    for name, kind in selected:
        REPORT["receipts"].append(read_receipt(archive, members, name, kind))
    latest, chronology = latest_receipts(REPORT["receipts"])
    REPORT["chronology"] = chronology
    references, invalid_refs = {}, []
    for record in latest:
        for key in ("tool_inventory_before", "tool_inventory_after"):
            ref = record["value"].get(key)
            if ref is None:
                continue
            if type(ref) is dict and type(ref.get("path")) is str:
                identity = encode(ref)
                references.setdefault(identity, ref)
            else:
                invalid_refs.append({"command": record["path"], "field": key, "status": "INVALID_REFERENCE"})
    REPORT["inventory_observations"].extend(invalid_refs)
    for reference in references.values():
        REPORT["inventory_observations"].append(read_inventory(archive, members, reference))
    REPORT["inventory_selection_scope"] = "only before/after references of the latest two known timed command receipts"
    REPORT["progress_metadata"] = {name: ({"presence": "PRESENT", **metadata(members[name])}
        if name in members else {"presence": "ABSENT"}) for name in PROGRESS_FILES}
    REPORT["retention_metadata"] = {name: metadata(item) for name, item in members.items()
        if re.fullmatch(r"result/cases/[^/]+/[^/]+/retention\.json", name) and not item.is_dir()}
    REPORT["scratch_metadata"] = {name: metadata(item) for name, item in members.items()
        if name.startswith("result/scratch/current/") and not item.is_dir()}
    REPORT["selected_json_bytes_read"] = SELECTED_READ
    REPORT["receipt_issue_count"] = sum(record.get("presence") == "PRESENT" and "value" not in record
                                      for record in REPORT["receipts"])
    REPORT["absence_count"] = sum(record["presence"] == "ABSENT" for record in REPORT["receipts"])
    REPORT["caveats"] = CAVEATS

def console_projection(report_identity):
    phases = []
    for record in REPORT["receipts"]:
        if record["kind"] != "phase":
            continue
        row = {key: record[key] for key in ("path","presence","raw_bytes","raw_sha256",
                                           "parse_status","schema_status","reason") if key in record}
        value = record.get("value", {})
        for key in ("phase","status","budget_seconds","root_started","root_deadline","phase_deadline",
                    "elapsed_seconds","elapsed_scope"):
            if key in value:
                row[key] = value[key]
        row["saved_commands_count"] = len(value.get("commands", []))
        row["last_saved_command"] = value.get("commands", [None])[-1] if value.get("commands") else None
        failure = value.get("first_failure")
        if type(failure) is dict:
            row["first_failure_summary"] = {key: failure[key] for key in ("stage","type","reason") if key in failure}
        else:
            row["first_failure_summary"] = None
        phases.append(row)
    latest = set(REPORT["chronology"]["selected_known_timed_receipts"])
    projections = []
    for record in REPORT["receipts"]:
        if record["path"] not in latest:
            continue
        value = record["value"]
        projections.append({"path": record["path"], "raw_bytes": record["raw_bytes"],
            "raw_sha256": record["raw_sha256"], "value_projection": {
                key: value[key] for key in ("status","lifecycle","returncode","reason","timed_out",
                "timeout_seconds","deadline","phase_deadline","root_deadline","elapsed_seconds",
                "requested_limits","effective_limits","tool_inventory_before","tool_inventory_after",
                "stdout","stderr","free_space") if key in value},
            "projection_excludes_argv_and_environment": True,
            "complete_checked_value": "report.json receipts entry with matching path"})
    result = {"status": REPORT["status"], "inspection_complete": True, "DSP_executed": False,
        "builds_executed": False, "promotion_allowed": False, "source": REPORT["source"],
        "report": report_identity, "zip_metadata": REPORT["zip_metadata"], "phases": phases,
        "lifecycle_row_order": "path order for display only, not chronological inference",
        "all_command_lifecycles": [lifecycle(record) for record in REPORT["receipts"] if record["kind"] == "command"],
        "chronology": REPORT["chronology"], "latest_receipt_projections": projections,
        "inventory_observations": REPORT["inventory_observations"],
        "progress_metadata": REPORT["progress_metadata"], "receipt_issue_count": REPORT["receipt_issue_count"],
        "absence_count": REPORT["absence_count"], "caveats": CAVEATS}
    return result

def report_write():
    check()
    need({p.name for p in ROOT.iterdir()} == {"archive.zip"}, "OWN_ROOT_FILES")
    REPORT["elapsed_seconds"] = time.monotonic() - STARTED
    REPORT["elapsed_scope"] = "through serialization setup; same deadline covers write, readback and console"
    REPORT["output_bounds"] = {"archive_bytes": ARCHIVE_BYTES, "report_bytes_cap": REPORT_LIMIT,
        "joint_write_cap": JOINT_LIMIT, "console_bytes_cap": CONSOLE_LIMIT,
        "exact_files": ["archive.zip","report.json"], "upload_scope": "report.json only after successful inspection"}
    raw = encode(REPORT)
    check()
    need(len(raw) <= REPORT_LIMIT and OWN_WRITTEN + len(raw) <= JOINT_LIMIT, "REPORT_CAP")
    identity = {"file": "report.json", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    console = encode(console_projection(identity))
    need(len(console) <= CONSOLE_LIMIT, "CONSOLE_CAP")
    with REPORT_PATH.open("xb", buffering=0) as file:
        position = 0
        while position < len(raw):
            end = min(position + 65536, len(raw))
            position = owned_write(file, raw[position:end], position, REPORT_LIMIT)
    check()
    actual, count = hashlib.sha256(), 0
    with REPORT_PATH.open("rb") as file:
        while True:
            check()
            block = file.read(1048576)
            if not block:
                break
            count += len(block)
            actual.update(block)
    check()
    need(count == identity["bytes"] and actual.hexdigest() == identity["sha256"] and
         {p.name for p in ROOT.iterdir()} == {"archive.zip","report.json"}, "REPORT_READBACK")
    write_console(console)

def write_console(raw):
    need(len(raw) <= CONSOLE_LIMIT, "CONSOLE_CAP")
    view = memoryview(raw)
    while view:
        check()
        count = os.write(1, view[:65536])
        need(count > 0, "CONSOLE_WRITE")
        view = view[count:]

def main():
    global ROOT_OWNED
    check()
    need(os.environ.get("GITHUB_ACTIONS") == "true" and
         os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and
         os.environ.get("GITHUB_EVENT_NAME") == "push" and os.environ.get("GITHUB_REF") == BRANCH and
         os.environ.get("GITHUB_RUN_ATTEMPT") == "1" and
         re.fullmatch(r"[0-9a-f]{40}", os.environ.get("GITHUB_SHA", "")) is not None, "EXECUTION_CONTEXT")
    need(os.getuid() != 0 and os.getuid() == os.geteuid() and os.getgid() == os.getegid(),
         "UNPRIVILEGED_REQUIRED")
    token = os.environ.get("GH_TOKEN", "")
    need(re.fullmatch(r"[A-Za-z0-9_.-]{1,4096}", token) is not None, "READ_TOKEN_REQUIRED")
    need(ROOT.parent.resolve(strict=True) == ROOT.parent and not os.path.lexists(ROOT), "NEW_OWN_ROOT_REQUIRED")
    ROOT.mkdir(mode=0o700)
    ROOT_OWNED = True
    REPORT["execution"] = {"repository": REPOSITORY, "ref": BRANCH, "event": "push",
                          "diagnostic_commit": os.environ["GITHUB_SHA"], "attempt": 1}
    location = identities(token)
    download(location)
    token = location = None
    with ARCHIVE.open("rb") as file:
        central = central_bounds(file)
        with zipfile.ZipFile(file, "r") as archive:
            members = validate_zip(file, archive, central)
            inspect(archive, members)
    check()
    REPORT.update(status="DIAGNOSTIC_RECEIPTS_ONLY_NO_DSP", inspection_complete=True,
                  receipt_values_scope="complete parsed values only after known nonsecret schema checks",
                  damaged_receipts_scope="raw byte count and SHA plus parse/schema status; no unknown value disclosure")
    report_write()
    check()
    return 0

if __name__ == "__main__":
    try:
        code = main()
    except Invalid as error:
        check()
        failure = {"status": "DIAGNOSTIC_INVALID", "inspection_complete": False,
                   "reason": error.args[0], "DSP_executed": False, "builds_executed": False,
                   "promotion_allowed": False, "failure_prefix_preserved": ROOT_OWNED,
                   "report_upload_allowed": False}
        write_console(encode(failure))
        code = 1
    except (urllib.error.URLError, TimeoutError, OSError):
        check()
        write_console(encode({"status": "DIAGNOSTIC_INVALID", "reason": "NETWORK_OR_IO_ERROR",
                             "DSP_executed": False, "builds_executed": False,
                             "promotion_allowed": False, "report_upload_allowed": False}))
        code = 1
    except (Exception, KeyboardInterrupt):
        check()
        write_console(encode({"status": "DIAGNOSTIC_INVALID", "reason": "PARSER_OR_RESOURCE_ERROR",
                             "DSP_executed": False, "builds_executed": False,
                             "promotion_allowed": False, "report_upload_allowed": False}))
        code = 1
    os._exit(code)
