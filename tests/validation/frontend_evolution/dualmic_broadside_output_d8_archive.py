#!/usr/bin/env python3
"""Validate the closed D8 console archive without executing the experiment.

This rechecks archived scalar predicates and source bindings. It does not read
artifact members, recompute audio metrics, or reproduce the scientific run.
"""
import time
STARTED = time.monotonic()
import os
import sys
import resource
sys.dont_write_bytecode = True

LIMITS = {"AS": 268435456, "CPU": 60, "NOFILE": 64, "FSIZE": 0, "CORE": 0}
ACTUAL_LIMITS = {}
for _name, _requested in LIMITS.items():
    _key = getattr(resource, "RLIMIT_" + _name)
    _soft, _hard = resource.getrlimit(_key)
    _effective = min(v for v in (_soft, _hard, _requested) if v != resource.RLIM_INFINITY)
    try:
        resource.setrlimit(_key, (_effective, _effective))
        if resource.getrlimit(_key) != (_effective, _effective):
            os._exit(125)
    except (OSError, ValueError):
        os._exit(125)
    ACTUAL_LIMITS[_name] = {"requested": _requested, "soft": _effective, "hard": _effective,
                            "inherited_soft": _soft, "inherited_hard": _hard}

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess

EXPERIMENT = "FE-DUALMIC-BROADSIDE-OUTPUT-D8"
EXECUTION_SHA = "0fe59e3c852f2150f717ee9dbb92ace517f2816b"
EXECUTION_TREE = "82b482bbdaffd333774ac06efef77fbfeb0f8217"
FREEZE = "8e3f92af6c4b0d3205a6903e8de31e55c0225a9e"
REPOSITORY = "jiying2007/audio-pipeline"
DOC = "docs/research/frontend-evolution-v1/"
PREFIX = "tests/validation/frontend_evolution/"
PLAN_PATH = DOC + "DUALMIC_BROADSIDE_OUTPUT_D8_PLAN.zh-CN.md"
LOCK_PATH = DOC + "dualmic-broadside-output-d8-input-lock.json"
EXPORT_PATH = DOC + "dualmic-broadside-output-d8-result-export.json"
MANIFEST_PATH = DOC + "dualmic-broadside-output-d8-terminal-lock.json"
IMPLEMENTATION_PATH = DOC + "DUALMIC_BROADSIDE_OUTPUT_D8_IMPLEMENTATION.zh-CN.md"
RESULT_PATH = DOC + "DUALMIC_BROADSIDE_OUTPUT_D8_RESULT.zh-CN.md"
CHECKER_PATH = PREFIX + "dualmic_broadside_output_d8_archive.py"
WORKFLOW_PATH = ".github/workflows/frontend-research.yml"
MANIFEST_BYTES = 3199
MANIFEST_SHA256 = "98048e1bddb4767833146fa2cba7082f9b9f63881b6630405e1935e8ea535f40"
FILTERED_TREE_ROWS = 3009
FILTERED_TREE_BYTES = 375717
FILTERED_TREE_SHA256 = "90648716e8e2acdcc8b665b7bcb11a3d13b3cd7332fc8ed11f060e95c20b0c21"
EXPORT_BYTES = 967201
EXPORT_SHA256 = "095a7e4b27e04d53b9316872a633f5a569477031aedf4c744fe06e5cc6bde8c2"
EXPORT_GIT_BLOB = "e7a6c475fc952cecaa937071ffe2a67a9a651797"
UNCHANGED_D8 = {
    PLAN_PATH: "71a0dea3a65029c23aced80238c791b98d6ec5fc",
    LOCK_PATH: "90f397672547abd0a02f87e0d428963d34e834c1",
    PREFIX + "dualmic_broadside_output_d8.c": "6fd37fdbb64f9f5aa80105e88aa5f967b9a57be9",
    PREFIX + "dualmic_broadside_output_d8.py": "ab97d1610d8b1f3d6e5ae65719566c4781f44a20",
    PREFIX + "dualmic_broadside_output_d8_build.py": "fcddd6cbe0c8eb71700c9ca8aedcbed66be12054",
    PREFIX + "dualmic_broadside_output_d8_supervise.py": "77b09cb9d613b1ba73807a53fff9f8704e176ef6",
    PREFIX + "test_dualmic_broadside_output_d8.py": "b783368f5d67e112cee7e006d86e59d8eed7f53b",
}
CHANGED_PATHS = frozenset((IMPLEMENTATION_PATH, RESULT_PATH, EXPORT_PATH,
                           MANIFEST_PATH, CHECKER_PATH, WORKFLOW_PATH))
REPORTED_FILES = {
    "report": {"bytes": 16809218, "sha256": "441e56d739bd5473c0d58be6cbc4191aed6f03a40081f9809412deb25ed7d32a"},
    "negatives": {"bytes": 459310, "sha256": "d30286fda74c3ba36b85e2efbc65216b472018b9cc783087b8843851b83b55b9"},
    "completion": {"bytes": 595883, "sha256": "b27b658abb280e884b745b7cd877d25d119ca8784182392a77639849c178112b"},
}
TOTALS = {"cases": 60, "frames": 35916, "samples": 5746560, "windows": 362,
          "reference_cases": 32, "primary_cases": 16, "resets": 8}
ARMS = ("baseline", "candidate")
DEADLINE = STARTED + 120.0
ACTIVE_DEADLINE = DEADLINE
GROUP = None
ROOT = Path(__file__).absolute().parents[3]
READ_BYTES = 0
READ_LIMIT = 16777216
FILE_LIMIT = 2097152
GIT_BYTES = 0
GIT_TOTAL_LIMIT = 4194304
STDOUT_STARTED = False

def expire(signum=None, frame=None):
    # Only the existing GNU timeout group is used. No subgroup or grace period.
    # Delivery is at the first scheduled handler/wake, subject to kernel latency.
    if GROUP is not None:
        try:
            os.killpg(GROUP, signal.SIGKILL)
        except OSError:
            pass
    os._exit(124)

def check():
    if time.monotonic() >= ACTIVE_DEADLINE:
        expire()

def need(value, reason):
    check()
    if not value:
        raise ValueError(reason)

def arm(deadline):
    global ACTIVE_DEADLINE
    ACTIVE_DEADLINE = min(deadline, DEADLINE)
    left = ACTIVE_DEADLINE - time.monotonic()
    if left <= 0:
        expire()
    signal.setitimer(signal.ITIMER_REAL, left)

def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False

def strict_json(raw):
    need(type(raw) is bytes and len(raw) <= FILE_LIMIT, "D8_ARCHIVE_JSON_BOUND")
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "D8_ARCHIVE_DUPLICATE_KEY")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("D8_ARCHIVE_NONFINITE")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("D8_ARCHIVE_JSON_INVALID") from None
    pending, nodes = [(result, 0)], 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        need(nodes <= 200000 and depth <= 32, "D8_ARCHIVE_JSON_COMPLEXITY")
        if type(value) is dict:
            need(all(type(key) is str and len(key) <= 1024 for key in value), "D8_ARCHIVE_JSON_SCHEMA")
            pending.extend((item, depth + 1) for item in value.values())
        elif type(value) is list:
            pending.extend((item, depth + 1) for item in value)
        elif type(value) in (int, float):
            need(finite_number(value), "D8_ARCHIVE_NONFINITE")
        else:
            need(value is None or type(value) in (str, bool), "D8_ARCHIVE_JSON_SCHEMA")
            if type(value) is str:
                need(len(value) <= 8192, "D8_ARCHIVE_JSON_STRING")
    return result

def git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()

def descriptor(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def relative_path(name):
    need(type(name) is str and 0 < len(name) <= 512 and
         not name.startswith("/") and "\\" not in name and "\0" not in name and
         all(part not in ("", ".", "..") for part in name.split("/")) and
         PurePosixPath(name).as_posix() == name, "D8_ARCHIVE_PATH")
    return name

def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)

def read_file(name):
    global READ_BYTES
    check()
    path = ROOT / relative_path(name)
    need(path.absolute() == path.resolve(strict=True), "D8_ARCHIVE_SOURCE_SYMLINK")
    before = path.stat(follow_symlinks=False)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
         0 <= before.st_size <= FILE_LIMIT, "D8_ARCHIVE_SOURCE_FILE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        need(file_identity(before) == file_identity(opened), "D8_ARCHIVE_SOURCE_CHANGED")
        data = bytearray()
        while True:
            check()
            block = os.read(fd, 65536)
            if not block:
                break
            need(len(data) + len(block) <= before.st_size and
                 READ_BYTES + len(block) <= READ_LIMIT, "D8_ARCHIVE_READ_BOUND")
            READ_BYTES += len(block)
            data += block
        need(len(data) == before.st_size and file_identity(before) == file_identity(os.fstat(fd)) ==
             file_identity(path.stat(follow_symlinks=False)), "D8_ARCHIVE_SOURCE_CHANGED")
        return bytes(data), before.st_mode
    finally:
        os.close(fd)

def git(*arguments, stdout_limit=1048576):
    """Fixed local Git builtins, never a shell, hook, transport, or repository import."""
    global GIT_BYTES
    check()
    need(arguments and arguments[0] in ("rev-parse", "ls-tree"),
         "D8_ARCHIVE_GIT_COMMAND")
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C", "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "", "GIT_NO_LAZY_FETCH": "1",
        "XDG_CONFIG_HOME": "/nonexistent", "PYTHONDONTWRITEBYTECODE": "1"}
    argv = ["/usr/bin/git", "--no-pager", "--no-optional-locks",
        "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
        "-c", "core.untrackedCache=false", "-c", "protocol.allow=never",
        "-c", "protocol.file.allow=never", "-c", "protocol.http.allow=never",
        "-c", "protocol.https.allow=never", "-c", "protocol.ssh.allow=never",
        "-C", str(ROOT), *arguments]
    deadline = min(DEADLINE, time.monotonic() + 30.0)
    arm(deadline)  # armed before Popen and through pipe EOF and reaping
    process = None
    output, error = bytearray(), bytearray()
    try:
        process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
        need(os.getpgid(process.pid) == GROUP, "D8_ARCHIVE_CHILD_GROUP")
        with selectors.DefaultSelector() as selector:
            for stream, target, limit in ((process.stdout, output, stdout_limit),
                                          (process.stderr, error, 65536)):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, (target, limit))
            while selector.get_map() or process.poll() is None:
                check()
                for key, _ in selector.select(min(0.05, max(0.0, deadline - time.monotonic()))):
                    check()
                    block = os.read(key.fd, 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    target, limit = key.data
                    need(len(target) + len(block) <= limit and
                         GIT_BYTES + len(block) <= GIT_TOTAL_LIMIT, "D8_ARCHIVE_GIT_OUTPUT_BOUND")
                    GIT_BYTES += len(block)
                    target += block  # only after both bounds
            check()
            code = process.wait()
            need(code == 0 and not error, "D8_ARCHIVE_GIT_FAILED")
    except Exception:
        # Ordinary failures may stop/reap the known local builtin while its
        # earlier timer is still armed. Expiry never returns to this block.
        check()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
    check()
    arm(DEADLINE)
    return bytes(output)

def keys(value, expected, reason):
    need(type(value) is dict and set(value) == set(expected), reason)

def typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(typed_equal(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right

def bind_export(raw):
    need(len(raw) == EXPORT_BYTES and raw.endswith(b"\n") and
         hashlib.sha256(raw).hexdigest() == EXPORT_SHA256 and git_blob(raw) == EXPORT_GIT_BLOB,
         "D8_ARCHIVE_EXPORT_IDENTITY")
    return strict_json(raw)

def validate_manifest(value, exported):
    reason = "D8_ARCHIVE_MANIFEST"
    keys(value, ("schema_version", "experiment", "closure", "scientific_terminal",
        "measurement_valid", "execution", "artifact", "console_export", "decoded_job_log",
        "reported_files", "totals", "source_contract", "evidence_scope"), reason)
    need(type(value["schema_version"]) is int and value["schema_version"] == 1 and
         value["experiment"] == EXPERIMENT and value["closure"] == "CLOSED_NO_ADVANCE" and
         value["scientific_terminal"] == "NO_ADVANCE" and value["measurement_valid"] is True, reason)
    execution = {"repository": REPOSITORY, "head": EXECUTION_SHA, "tree": EXECUTION_TREE,
        "run_id": 43135999005, "job_id": 130911420512, "run_attempt": 1,
        "event": "pull_request", "run_number": 33, "workflow": WORKFLOW_PATH,
        "run_url": "https://github.com/jiying2007/audio-pipeline/actions/runs/43135999005"}
    artifact = {"id": 13907504634,
        "name": "frontend-research-dualmic-broadside-output-d8-43135999005-attempt-1",
        "bytes": 629265247, "sha256": "ed302fc060dba6ee29c62de6583c579c678da984497f3cfe1c10d5efb08f5057",
        "uploaded_files": 3832, "expires_at": "2027-02-10T01:39:29Z",
        "url": "https://github.com/jiying2007/audio-pipeline/actions/runs/43135999005/artifacts/13907504634"}
    need(typed_equal(value["execution"], execution) and typed_equal(value["artifact"], artifact), reason)
    export = value["console_export"]
    keys(export, ("path", "bytes", "sha256", "git_blob", "representation"), reason)
    need(typed_equal({key: export[key] for key in ("path", "bytes", "sha256", "git_blob")},
         {"path": EXPORT_PATH, "bytes": EXPORT_BYTES, "sha256": EXPORT_SHA256, "git_blob": EXPORT_GIT_BLOB}), reason)
    log = value["decoded_job_log"]
    keys(log, ("bytes", "sha256", "representation"), reason)
    need(type(log["bytes"]) is int and log["bytes"] == 1003432 and
         log["sha256"] == "9fde04b745095cd27b293b13f6dbd8b675d11265a432ae020fd6962aec5a0130", reason)
    need(typed_equal(value["reported_files"], REPORTED_FILES) and
         typed_equal(value["reported_files"], {key: exported[key] for key in REPORTED_FILES}) and
         typed_equal(value["totals"], TOTALS), reason)
    need(typed_equal(value["source_contract"], {"freeze": FREEZE, "plan_path": PLAN_PATH,
                                               "lock_path": LOCK_PATH}), reason)
    scope = value["evidence_scope"]
    scope_flags = {"console_projection_read": True,
        "actual_artifact_members_opened_by_archive_author": False,
        "independent_binary_recomputation": False,
        "negative_and_completion_values_in_projection": False,
        "archival_validation_is_reproduction": False, "promotion_allowed": False}
    keys(scope, (*scope_flags, "completion_evidence", "reopening"), reason)
    need(all(scope[key] is expected for key, expected in scope_flags.items()), reason)
    # These human explanations are bounded text, never identity authorities.
    for text in (export["representation"], log["representation"],
                 scope["completion_evidence"], scope["reopening"]):
        need(type(text) is str and 0 < len(text) <= 2048 and "\0" not in text, reason)
    return True

def parse_tree(raw):
    need(type(raw) is bytes and raw.endswith(b"\0"), "D8_ARCHIVE_GIT_TREE")
    records = raw.split(b"\0")[:-1]
    need(0 < len(records) <= 4096, "D8_ARCHIVE_GIT_TREE")
    result = {}
    for item in records:
        need(item and b"\t" in item, "D8_ARCHIVE_GIT_TREE")
        meta, encoded = item.split(b"\t", 1)
        try:
            mode, kind, oid = meta.decode("ascii").split(" ")
            name = encoded.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            raise ValueError("D8_ARCHIVE_GIT_TREE") from None
        relative_path(name)
        need(name not in result and re.fullmatch(r"[0-9a-f]{40}", oid) is not None and
             (kind == "blob" and mode in ("100644", "100755") or kind == "tree" and mode == "040000"),
             "D8_ARCHIVE_GIT_TREE")
        result[name] = {"mode": mode, "type": kind, "git_object": oid}
    return result

def check_tree_equivalence(current):
    need(len(current) == FILTERED_TREE_ROWS + 6 and CHANGED_PATHS <= set(current) and
         all(current[name]["type"] == "blob" and current[name]["mode"] == "100644"
             for name in CHANGED_PATHS), "D8_ARCHIVE_CHANGED_PATHS")
    rows = [[name, row["mode"], row["type"], row["git_object"] if row["type"] == "blob" else None]
            for name, row in sorted(current.items()) if name not in CHANGED_PATHS]
    raw = (json.dumps(rows, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    need(len(rows) == FILTERED_TREE_ROWS and len(raw) == FILTERED_TREE_BYTES and
         hashlib.sha256(raw).hexdigest() == FILTERED_TREE_SHA256, "D8_ARCHIVE_TREE_EQUIVALENCE")
    return True

def tree_equivalence_controls(current):
    check_tree_equivalence(current)
    records = []
    for label, name, field, replacement, expected in (
        ("source-object", PLAN_PATH, "git_object", "0" * 40, "D8_ARCHIVE_TREE_EQUIVALENCE"),
        ("directory-mode", "src", "mode", "040001", "D8_ARCHIVE_TREE_EQUIVALENCE"),
        ("allowed-mode", CHECKER_PATH, "mode", "100755", "D8_ARCHIVE_CHANGED_PATHS"),
    ):
        mutant = dict(current)
        mutant[name] = dict(current[name])
        mutant[name][field] = replacement
        try:
            check_tree_equivalence(mutant)
        except ValueError as error:
            need(str(error) == expected, "D8_ARCHIVE_CONTROL_WRONG_REASON")
        else:
            need(False, "D8_ARCHIVE_CONTROL_ACCEPTED")
        check_tree_equivalence(current)
        records.append({"label": label, "expected_reason": expected, "observed_reason": expected})
    return {"status": "PASS", "controls": len(records), "records": records,
            "scope": "in-memory current-tree equivalence predicates, not Git mutation or DSP"}

def check_file_binding(raw, mode, entry, expected_blob, expected_descriptor=None):
    need(entry["type"] == "blob" and entry["git_object"] == expected_blob and
         git_blob(raw) == expected_blob and bool(mode & 0o111) == (entry["mode"] == "100755"),
         "D8_ARCHIVE_SOURCE_BINDING")
    if expected_descriptor is not None:
        need(typed_equal(descriptor(raw), expected_descriptor), "D8_ARCHIVE_SOURCE_BINDING")
    return True

def validate_sources(lock, validation_head, preloaded):
    need(git("rev-parse", "--verify", "HEAD", stdout_limit=128).decode("ascii").strip() == validation_head,
         "D8_ARCHIVE_VALIDATION_HEAD")
    current_tree = git("rev-parse", "--verify", "HEAD^{tree}", stdout_limit=128).decode("ascii").strip()
    need(re.fullmatch(r"[0-9a-f]{40}", current_tree) is not None, "D8_ARCHIVE_GIT_TREE")
    current = parse_tree(git("ls-tree", "-r", "-t", "-z", "--full-tree", "HEAD"))
    check_tree_equivalence(current)
    tree_controls = tree_equivalence_controls(current)
    production, helpers, roots = (lock[key] for key in
        ("production_files", "frozen_helper_files", "unchanged_production_objects"))
    need(len(production) == 65 and len(helpers) == 35 and len(roots) == 10 and
         not (set(production) & set(helpers)) and
         not ((set(production) | set(helpers)) & set(UNCHANGED_D8)), "D8_ARCHIVE_SOURCE_COUNTS")
    names = sorted(set(production) | set(helpers) | set(UNCHANGED_D8))
    need(len(names) == 107 and set(names) <= set(current), "D8_ARCHIVE_SOURCE_COUNTS")
    need(set(roots) <= set(current) and all(current[name]["type"] == row["type"] and
         current[name]["git_object"] == row["git_object"] for name, row in roots.items()),
         "D8_ARCHIVE_PRODUCTION_ROOTS")
    bindings = {**production, **helpers}
    for name in names:
        check()
        relative_path(name)
        raw, mode = preloaded[name] if name in preloaded else read_file(name)
        if name in UNCHANGED_D8:
            expected_blob, expected_descriptor = UNCHANGED_D8[name], None
        else:
            record = bindings[name]
            expected_blob = record["git_blob"]
            expected_descriptor = {key: record[key] for key in ("bytes", "sha256")}
            if "git_mode" in record:
                need(current[name]["mode"] == record["git_mode"], "D8_ARCHIVE_SOURCE_BINDING")
        check_file_binding(raw, mode, current[name], expected_blob, expected_descriptor)
    changed_bytes = {}
    for name in sorted(CHANGED_PATHS):
        raw, mode = preloaded[name] if name in preloaded else read_file(name)
        check_file_binding(raw, mode, current[name], current[name]["git_object"])
        changed_bytes[name] = raw
    historical_workflow = original_workflow(changed_bytes[WORKFLOW_PATH])
    need(git_blob(historical_workflow) == "bd6f25ec4d328b0d270051cba7c602e984de4d5e" and
         archive_workflow(historical_workflow) == changed_bytes[WORKFLOW_PATH],
         "D8_ARCHIVE_WORKFLOW_ROUTING")
    return {"validation_head": validation_head, "validation_tree": current_tree,
        "execution_head": EXECUTION_SHA, "execution_tree": EXECUTION_TREE,
        "execution_identity_scope": "independently reviewed first-valid metadata; no runtime ancestry assertion",
        "production_files": 65, "helper_files": 35, "unchanged_D8_files": 7,
        "production_root_objects": 10, "permitted_changed_paths": sorted(CHANGED_PATHS),
        "filtered_tree": {"rows": FILTERED_TREE_ROWS, "bytes": FILTERED_TREE_BYTES,
            "sha256": FILTERED_TREE_SHA256, "directory_rows": 200, "blob_rows": 2809,
            "representation": "sorted [path,mode,type,blob-SHA-or-null-for-tree], compact ASCII JSON plus LF"},
        "tree_controls": tree_controls,
        "historical_jobs_and_dormant_science_job_byte_unchanged": True}

ARCHIVE_JOB = "\n  dualmic-broadside-output-d8-archive:\n    name: Validate archived D8 NO_ADVANCE evidence (no DSP)\n    needs: scope\n    if: needs.scope.outputs.d8_archive == 'true'\n    permissions:\n      contents: read\n    runs-on: ubuntu-24.04\n    timeout-minutes: 3\n    env:\n      VALIDATION_SHA: ${{ github.event.pull_request.head.sha || github.sha }}\n      PYTHONDONTWRITEBYTECODE: '1'\n    steps:\n      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5\n        with:\n          fetch-depth: 0\n          persist-credentials: false\n          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n      - name: Validate immutable console archive and local source bindings only\n        shell: bash\n        run: |\n          exec /usr/bin/timeout --signal=KILL 120s /usr/bin/python3 -I -B \\\n            tests/validation/frontend_evolution/dualmic_broadside_output_d8_archive.py \\\n            --expected-head \"$VALIDATION_SHA\"\n"

def archive_workflow(original):
    """Exact minimal transform; all historical selectors and jobs are untouched."""
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("D8_ARCHIVE_WORKFLOW_ROUTING") from None
    def replace_once(before, after):
        nonlocal text
        need(text.count(before) == 1, "D8_ARCHIVE_WORKFLOW_ROUTING")
        text = text.replace(before, after, 1)
    replace_once("      d8: \u0024{{ steps.select.outputs.d8 }}\n",
                 "      d8: \u0024{{ steps.select.outputs.d8 }}\n"
                 "      d8_archive: \u0024{{ steps.select.outputs.d8_archive }}\n")
    replace_once("        type: choice\n",
        "        description: D8 validates the closed NO_ADVANCE archive only; it never runs DSP\n"
        "        type: choice\n")
    replace_once("          # D8-only selection exits before historical selectors see the appended lane.\n",
        "          # Closed D8 selections validate archived evidence; no fallback to science.\n"
        "          with open(os.environ['GITHUB_OUTPUT'], 'a') as out:\n"
        "              out.write('d8=false\\nd8_archive=false\\n')\n")
    replace_once(
        "              if d8 and any(not (any(token in p for token in d8_tokens) or p == '.github/workflows/frontend-research.yml')\n"
        "                            for p in d8_paths):\n"
        "                  raise SystemExit('D8_REQUIRES_SEPARATE_RESEARCH_CHANGE')\n", "")
    replace_once("d7=false\\nd8=true\\n')", "d7=false\\nd8=false\\nd8_archive=true\\n')")
    need(text.endswith("\n"), "D8_ARCHIVE_WORKFLOW_ROUTING")
    return (text + ARCHIVE_JOB).encode("utf-8")


def original_workflow(current):
    """Invert only the declared routing patch, then authenticate the original."""
    try:
        text = current.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("D8_ARCHIVE_WORKFLOW_ROUTING") from None
    need(text.endswith(ARCHIVE_JOB) and text.count(ARCHIVE_JOB) == 1, "D8_ARCHIVE_WORKFLOW_ROUTING")
    text = text[:-len(ARCHIVE_JOB)]
    def replace_once(before, after):
        nonlocal text
        need(text.count(before) == 1, "D8_ARCHIVE_WORKFLOW_ROUTING")
        text = text.replace(before, after, 1)
    replace_once("d7=false\\nd8=false\\nd8_archive=true\\n')", "d7=false\\nd8=true\\n')")
    replace_once("          if d8:\n",
        "              if d8 and any(not (any(token in p for token in d8_tokens) or p == '.github/workflows/frontend-research.yml')\n"
        "                            for p in d8_paths):\n"
        "                  raise SystemExit('D8_REQUIRES_SEPARATE_RESEARCH_CHANGE')\n"
        "          if d8:\n")
    replace_once(
        "          # Closed D8 selections validate archived evidence; no fallback to science.\n"
        "          with open(os.environ['GITHUB_OUTPUT'], 'a') as out:\n"
        "              out.write('d8=false\\nd8_archive=false\\n')\n",
        "          # D8-only selection exits before historical selectors see the appended lane.\n")
    replace_once(
        "        description: D8 validates the closed NO_ADVANCE archive only; it never runs DSP\n"
        "        type: choice\n", "        type: choice\n")
    replace_once(
        "      d8: \u0024{{ steps.select.outputs.d8 }}\n"
        "      d8_archive: \u0024{{ steps.select.outputs.d8_archive }}\n",
        "      d8: \u0024{{ steps.select.outputs.d8 }}\n")
    original = text.encode("utf-8")
    need(git_blob(original) == "bd6f25ec4d328b0d270051cba7c602e984de4d5e" and
         archive_workflow(original) == current, "D8_ARCHIVE_WORKFLOW_ROUTING")
    return original

# Pure, read-only validation of the authenticated printed D8 export.
# No repository imports, waveform access, DSP, or binary/receipt audit.
_EV_ARMS = ("baseline", "candidate")
_EV_SOURCE = "0fe59e3c852f2150f717ee9dbb92ace517f2816b"
_EV_FREEZE = "8e3f92af6c4b0d3205a6903e8de31e55c0225a9e"
_EV_EXPERIMENT = "FE-DUALMIC-BROADSIDE-OUTPUT-D8"


def _ev_same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return set(a) == set(b) and all(_ev_same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(_ev_same(x, y) for x, y in zip(a, b))
    return a == b


def _ev_clone(value):
    if type(value) is dict:
        return {key: _ev_clone(item) for key, item in value.items()}
    if type(value) is list:
        return [_ev_clone(item) for item in value]
    return value


def _ev_schema(value, keys, require, reason="D8_EXPORT_SCHEMA"):
    require(type(value) is dict and set(value) == set(keys), reason)


def _ev_number(value, require):
    require(type(value) in (int, float), "D8_EXPORT_NUMBER")
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        require(False, "D8_EXPORT_NUMBER")
        return
    require(-float("inf") < converted < float("inf"), "D8_EXPORT_NUMBER")


def _ev_span(value, expected, require):
    require(type(value) is list and len(value) == 2 and
            all(type(x) is int for x in value) and value == expected, "D8_EXPORT_GEOMETRY")


def validate_export_values(export, original_lock, require):
    """Validate printed values only; original_lock is the full authenticated R3 lock."""
    _ev_schema(export, ("D8_RESULT", "report", "negatives", "completion"), require)
    for name in ("report", "negatives", "completion"):
        descriptor = export[name]
        _ev_schema(descriptor, ("bytes", "sha256"), require, "D8_EXPORT_DESCRIPTOR")
        require(type(descriptor["bytes"]) is int and 0 < descriptor["bytes"] <= 536870912 and
                type(descriptor["sha256"]) is str and len(descriptor["sha256"]) == 64 and
                all(x in "0123456789abcdef" for x in descriptor["sha256"]), "D8_EXPORT_DESCRIPTOR")
    result = export["D8_RESULT"]
    _ev_schema(result, ("all16_primary_common_deltas", "cases", "experiment", "freeze",
        "full_AGC_events_and_states", "independent_binary_audit_completed", "interpretation",
        "measurement_valid", "promotion_allowed", "source", "status", "totals"), require)
    require(result["source"] == _EV_SOURCE and result["experiment"] == _EV_EXPERIMENT and
            result["freeze"] == _EV_FREEZE, "D8_EXPORT_SOURCE")
    require(result["measurement_valid"] is True and result["promotion_allowed"] is False and
            result["status"] == "NO_ADVANCE" and result["independent_binary_audit_completed"] is False,
            "D8_EXPORT_STATUS")
    require(result["full_AGC_events_and_states"] ==
            "retained in report.json and actual binary evidence", "D8_EXPORT_SCOPE")
    interpretation = {
        "HPF_raw_clean_damage_claim": False,
        "material_screen": "each16 common delta>=1dB, conservative finite research allocation",
        "one_preregistered_total_effect": True, "perceptual_or_statistical_claim": False,
        "primary_endpoint": "deliveredS16/32768 canonicalfixed160 SI-SDR",
        "scope": "four correlated recorded pairs with disclosed synthetic broadside propagation"}
    require(_ev_same(result["interpretation"], interpretation), "D8_EXPORT_SCOPE")
    require(type(original_lock) is dict and original_lock.get("experiment") == _EV_EXPERIMENT,
            "D8_EXPORT_CATALOG")
    entries = original_lock["original_d2_case_input_lock"]["cases"]
    require(type(entries) is list and len(entries) == 60 and type(result["cases"]) is list and
            len(result["cases"]) == 60, "D8_EXPORT_CATALOG")
    catalogs = [entry["catalog"] for entry in entries]
    require(len({case["key"] for case in catalogs}) == 60, "D8_EXPORT_CATALOG")
    totals = {"cases": 60, "frames": 0, "samples": 0, "windows": 0,
              "reference_cases": 0, "primary_cases": 0, "resets": 0}
    counts = {kind: {"total": 0, "failed": 0} for kind in
              ("primary", "near", "projection", "energy", "recovery", "counts")}
    failures = {"near_common": 0, "near_windows": 0, "projection_common": 0,
                "projection_windows": 0, "energy_cases": 0}
    energy_by_scenario = {"far-only": 0, "path-change": 0, "render-gap": 0, "C": 0}
    primary_values, recovery_failures = [], []
    scored_windows = null_windows = exact_flags = curve_rows = 0
    projection_above_floor = True
    cases_passed = 0

    for entry, catalog, case in zip(entries, catalogs, result["cases"]):
        _ev_schema(case, ("key", "group", "profile", "scenario", "frames", "samples", "capture_only",
            "final_s16", "scoring", "scoring_method", "projection", "recovery", "clip_counts",
            "near_silent_exact", "screens", "agc_counts"), require)
        for key in ("key", "group", "profile", "scenario", "frames", "samples", "capture_only"):
            require(_ev_same(case[key], catalog[key]), "D8_EXPORT_CATALOG")
        n, frames = case["samples"], case["frames"]
        require(type(n) is int and type(frames) is int and 529 <= frames <= 629 and n == 160 * frames,
                "D8_EXPORT_GEOMETRY")
        end = n - 160
        windows = [[first, min(first + 16000, end)] for first in range(0, end, 16000)]
        spans = [[0, end]] + windows
        has_reference = entry["clean_near"] is not None
        require(has_reference == (catalog["inputs"]["clean_near"] is not None), "D8_EXPORT_CATALOG")
        near = case["group"] == "A" and case["scenario"] in (
            "near-only", "silent-render", "doubletalk-nominal", "doubletalk-weak")
        require(has_reference is near, "D8_EXPORT_CATALOG")
        primary = near and case["scenario"] in ("doubletalk-nominal", "doubletalk-weak")
        far = case["group"] == "A" and case["scenario"] in ("far-only", "path-change", "render-gap")
        # This is the authenticated snapshot's declared null pattern, checked
        # against catalog placement. It does NOT remeasure reference energy.
        if has_reference:
            dimensions = catalog["dimensions"]
            require(dimensions["near_start_sample"] == 24000 and
                    dimensions["source_window_samples"] == 64000 and n == 96000,
                    "D8_EXPORT_CATALOG")
            applies = [True] + [False, True, True, True, True, True]
        else:
            applies = [False] * len(spans)
        require(len(applies) == len(spans), "D8_EXPORT_APPLICABILITY")
        totals["frames"] += frames
        totals["samples"] += n
        totals["windows"] += len(windows)
        totals["reference_cases"] += int(has_reference)
        totals["primary_cases"] += int(primary)
        totals["resets"] += sum(event["kind"] == "cli_discontinuity" for event in catalog["input_events"])
        scored_windows += sum(applies[1:])
        null_windows += len(windows) - sum(applies[1:])

        policy = case["scoring_method"]
        _ev_schema(policy, ("canonical", "lag_search", "offset_samples", "near_min_delta_db",
            "primary_min_delta_db", "projection_min_exclusive_db"), require, "D8_EXPORT_POLICY")
        require(policy["canonical"] == "si_sdr_span" and policy["lag_search"] is False and
                type(policy["offset_samples"]) is int and policy["offset_samples"] == 160,
                "D8_EXPORT_POLICY")
        for key, expected in (("near_min_delta_db", 0), ("primary_min_delta_db", 1),
                              ("projection_min_exclusive_db", -120)):
            _ev_number(policy[key], require)
            require(policy[key] == expected, "D8_EXPORT_POLICY")

        final = case["final_s16"]
        _ev_schema(final, _EV_ARMS, require)
        arm_spans = {}
        for arm in _EV_ARMS:
            lane = final[arm]
            _ev_schema(lane, ("present", "offset_samples", "common", "one_second_windows",
                              "native_whole_buffer_energy"), require)
            require(lane["present"] is True and type(lane["offset_samples"]) is int and
                    lane["offset_samples"] == 160, "D8_EXPORT_GEOMETRY")
            require(type(lane["one_second_windows"]) is list and
                    len(lane["one_second_windows"]) == len(windows), "D8_EXPORT_GEOMETRY")
            arm_spans[arm] = [lane["common"]] + lane["one_second_windows"]
            for row, span, applicable in zip(arm_spans[arm], spans, applies):
                _ev_schema(row, ("near_si_sdr_db", "near_si_sdr_null_reason", "peak",
                    "physical_sample_range", "rms_dbfs", "samples", "signal_sample_range"), require)
                _ev_span(row["physical_sample_range"], span, require)
                _ev_span(row["signal_sample_range"], [span[0] + 160, span[1] + 160], require)
                require(type(row["samples"]) is int and row["samples"] == span[1] - span[0],
                        "D8_EXPORT_GEOMETRY")
                if applicable:
                    _ev_number(row["near_si_sdr_db"], require)
                    require(row["near_si_sdr_null_reason"] is None, "D8_EXPORT_NULL")
                else:
                    reason = ("zero_energy_reference_or_short_span" if has_reference else
                        "C_has_no_admitted_clean_near_reference" if case["group"] == "C"
                        else "no_clean_near_reference")
                    require(row["near_si_sdr_db"] is None and row["near_si_sdr_null_reason"] == reason,
                            "D8_EXPORT_NULL")
                for key in ("rms_dbfs", "peak"):
                    _ev_number(row[key], require)
                require(-240 <= row["rms_dbfs"] <= 0 and 0 <= row["peak"] <= 1, "D8_EXPORT_NUMBER")
            whole = lane["native_whole_buffer_energy"]
            _ev_schema(whole, ("peak", "rms_dbfs", "samples"), require)
            require(type(whole["samples"]) is int and whole["samples"] == n, "D8_EXPORT_GEOMETRY")
            _ev_number(whole["peak"], require)
            _ev_number(whole["rms_dbfs"], require)
            require(0 <= whole["peak"] <= 1 and -240 <= whole["rms_dbfs"] <= 0, "D8_EXPORT_NUMBER")

        _ev_schema(case["scoring"], ("common", "windows"), require)
        _ev_schema(case["projection"], ("common", "windows"), require)
        require(type(case["scoring"]["windows"]) is list and
                type(case["projection"]["windows"]) is list and
                len(case["scoring"]["windows"]) == len(case["projection"]["windows"]) == len(windows),
                "D8_EXPORT_GEOMETRY")
        scores = [case["scoring"]["common"]] + case["scoring"]["windows"]
        gains = [case["projection"]["common"]] + case["projection"]["windows"]
        for index, (score, gain, span, applicable) in enumerate(zip(scores, gains, spans, applies)):
            _ev_schema(score, ("applicable", "delta_si_sdr_db", "physical_sample_range"), require)
            _ev_span(score["physical_sample_range"], span, require)
            require(score["applicable"] is applicable, "D8_EXPORT_APPLICABILITY")
            _ev_schema(gain, _EV_ARMS, require)
            if applicable:
                _ev_number(score["delta_si_sdr_db"], require)
                delta = arm_spans["candidate"][index]["near_si_sdr_db"] - arm_spans["baseline"][index]["near_si_sdr_db"]
                require(score["delta_si_sdr_db"] == delta, "D8_EXPORT_DELTA")
                for arm in _EV_ARMS:
                    _ev_number(gain[arm], require)
                    projection_above_floor = projection_above_floor and gain[arm] > -120
            else:
                require(score["delta_si_sdr_db"] is None and
                        all(gain[arm] is None for arm in _EV_ARMS), "D8_EXPORT_NULL")

        _ev_schema(case["clip_counts"], _EV_ARMS, require)
        _ev_schema(case["agc_counts"], _EV_ARMS, require)
        for arm in _EV_ARMS:
            clip = case["clip_counts"][arm]
            require(type(clip) is int and 0 <= clip <= n, "D8_EXPORT_COUNT")
            agc = case["agc_counts"][arm]
            _ev_schema(agc, ("clamped_samples", "output_gate_frames", "peak_limit_frames",
                            "target_gate_frames"), require, "D8_EXPORT_COUNT")
            for key, value in agc.items():
                require(type(value) is int and 0 <= value <= (n if key == "clamped_samples" else frames),
                        "D8_EXPORT_COUNT")
            require(clip == 0 and agc["clamped_samples"] == 0, "D8_EXPORT_COUNT")

        _ev_schema(case["recovery"], _EV_ARMS, require)
        for arm in _EV_ARMS:
            recovery = case["recovery"][arm]
            if not far:
                require(_ev_same(recovery, {"curve": [], "convergence_ms": None, "recovery_ms": None,
                    "final_level": None, "reason": "not_applicable"}), "D8_EXPORT_RECOVERY")
                continue
            _ev_schema(recovery, ("curve", "convergence_ms", "recovery_ms", "final_level",
                                  "semantics", "recovery_required"), require, "D8_EXPORT_RECOVERY")
            required = case["scenario"] != "far-only"
            require(recovery["recovery_required"] is required and recovery["semantics"] ==
                "unchanged own-tail-relative3dB/three-window settling; not absolute quality",
                "D8_EXPORT_RECOVERY")
            curve = recovery["curve"]
            # Counts/coordinates are the fixed authenticated export's shape,
            # not a recomputation of echo-energy windows from source PCM.
            expected_length = 410 if case["scenario"] == "path-change" else 407
            require(type(curve) is list and len(curve) == expected_length, "D8_EXPORT_CURVE")
            for index, point in enumerate(curve):
                require(type(point) is list and len(point) == 2 and type(point[0]) is int and
                        point[0] == index * 160 and point[0] + 1600 <= end, "D8_EXPORT_CURVE")
                _ev_number(point[1], require)
            curve_rows += len(curve)
            _ev_number(recovery["final_level"], require)
            for key in ("convergence_ms", "recovery_ms"):
                value = recovery[key]
                if key == "recovery_ms" and not required:
                    require(value is None, "D8_EXPORT_RECOVERY")
                else:
                    _ev_number(value, require)
                    require(0 <= value <= n / 16 and value % 10 == 0, "D8_EXPORT_RECOVERY")
        if far:
            require([x[0] for x in case["recovery"]["baseline"]["curve"]] ==
                    [x[0] for x in case["recovery"]["candidate"]["curve"]], "D8_EXPORT_CURVE")

        exact = case["group"] == "A" and case["scenario"] in ("near-only", "silent-render")
        require(case["near_silent_exact"] is (True if exact else None), "D8_EXPORT_EXACT_FLAG")
        if exact:
            exact_flags += 1
            for field in ("final_s16", "projection", "recovery", "clip_counts", "agc_counts"):
                if field == "projection":
                    require(all(_ev_same(gain["baseline"], gain["candidate"]) for gain in gains),
                            "D8_EXPORT_EXACT_FLAG")
                else:
                    require(_ev_same(case[field]["baseline"], case[field]["candidate"]), "D8_EXPORT_EXACT_FLAG")

        checks, vetoes = [], []
        energy_failed = False
        def add(label, kind, values, passed):
            nonlocal energy_failed
            checks.append({"label": label, "kind": kind, "values": values, "passed": passed})
            counts[kind]["total"] += 1
            if not passed:
                vetoes.append(label)
                counts[kind]["failed"] += 1
                if kind in ("near", "projection"):
                    failures[kind + ("_common" if label.endswith(":common") else "_windows")] += 1
                if kind == "energy":
                    energy_failed = True
                    energy_by_scenario["C" if case["group"] == "C" else case["scenario"]] += 1
                if kind == "recovery":
                    recovery_failures.append({"key": case["key"], "label": label, **values})
        if primary:
            delta = scores[0]["delta_si_sdr_db"]
            primary_values.append({"key": case["key"], "delta_si_sdr_db": delta})
            add("primary_common_at_least1dB", "primary", {"delta": delta}, delta >= 1)
        for index, (score, gain) in enumerate(zip(scores, gains)):
            if score["applicable"]:
                label = "common" if index == 0 else str(index - 1)
                delta = score["delta_si_sdr_db"]
                add("near_nonregression:" + label, "near", {"delta": delta}, delta >= 0)
                values = {**gain, "required": True}
                add("anti_collapse:" + label, "projection", values,
                    gain["baseline"] > -120 and gain["candidate"] > -120 and
                    gain["candidate"] >= gain["baseline"])
        if far or case["group"] == "C":
            pairs = [("common", final["baseline"]["common"], final["candidate"]["common"])]
            pairs += [(str(i), a, b) for i, (a, b) in enumerate(zip(
                final["baseline"]["one_second_windows"], final["candidate"]["one_second_windows"]))]
            pairs.append(("native_whole", final["baseline"]["native_whole_buffer_energy"],
                          final["candidate"]["native_whole_buffer_energy"]))
            for label, baseline, candidate in pairs:
                for metric in ("rms_dbfs", "peak"):
                    values = {"baseline": baseline[metric], "candidate": candidate[metric]}
                    add("energy:" + label + ":" + metric, "energy", values,
                        values["candidate"] <= values["baseline"])
        add("S16_clip_count", "counts", dict(case["clip_counts"]),
            case["clip_counts"]["candidate"] <= case["clip_counts"]["baseline"])
        clamps = {arm: case["agc_counts"][arm]["clamped_samples"] for arm in _EV_ARMS}
        add("AGC_terminal_clamps", "counts", clamps, clamps["candidate"] <= clamps["baseline"])
        if far:
            for label, field in (("convergence", "convergence_ms"), ("post_event_recovery", "recovery_ms")):
                if label == "post_event_recovery" and case["scenario"] == "far-only":
                    continue
                values = {arm: case["recovery"][arm][field] for arm in _EV_ARMS}
                add(label, "recovery", {**values, "required": True},
                    values["candidate"] <= values["baseline"])
        _ev_schema(case["screens"], ("primary", "passed", "vetoes", "checks"), require)
        require(case["screens"]["primary"] is primary, "D8_EXPORT_SCREEN_ROW")
        require(_ev_same(case["screens"]["checks"], checks), "D8_EXPORT_SCREEN_ROW")
        require(_ev_same(case["screens"]["vetoes"], vetoes), "D8_EXPORT_SCREEN_VETO")
        require(case["screens"]["passed"] is (not vetoes), "D8_EXPORT_SCREEN_DECISION")
        failures["energy_cases"] += int(energy_failed)
        cases_passed += int(not vetoes)

    expected_totals = {"cases": 60, "frames": 35916, "samples": 5746560, "windows": 362,
                      "reference_cases": 32, "primary_cases": 16, "resets": 8}
    require(_ev_same(totals, expected_totals) and _ev_same(result["totals"], expected_totals),
            "D8_EXPORT_TOTALS")
    expected_counts = {"primary": {"total": 16, "failed": 16}, "near": {"total": 192, "failed": 44},
        "projection": {"total": 192, "failed": 56}, "energy": {"total": 452, "failed": 87},
        "recovery": {"total": 40, "failed": 1}, "counts": {"total": 120, "failed": 0}}
    require(_ev_same(counts, expected_counts) and sum(x["total"] for x in counts.values()) == 1012,
            "D8_EXPORT_SCREEN_TOTALS")
    require(failures == {"near_common": 8, "near_windows": 36, "projection_common": 9,
                         "projection_windows": 47, "energy_cases": 19} and
            energy_by_scenario == {"far-only": 28, "path-change": 24, "render-gap": 14, "C": 21},
            "D8_EXPORT_SCREEN_TOTALS")
    require(scored_windows == 160 and null_windows == 202 and exact_flags == 16 and
            projection_above_floor and cases_passed == 25, "D8_EXPORT_TOTALS")
    require(_ev_same(result["all16_primary_common_deltas"], primary_values), "D8_EXPORT_PRIMARY")
    deltas = [row["delta_si_sdr_db"] for row in primary_values]
    require(sum(x < 0 for x in deltas) == 8 and sum(x > 0 for x in deltas) == 8 and
            min(deltas) == -0.06166039635015785 and max(deltas) == 0.24423234536933425,
            "D8_EXPORT_PRIMARY")
    require(recovery_failures == [{"key": "A/pair-0-path-change-call", "label": "post_event_recovery",
                                  "baseline": 540, "candidate": 550, "required": True}],
            "D8_EXPORT_RECOVERY")
    return {"status": "PRINTED_EXPORT_CONSISTENT", "measurement_status": "NO_ADVANCE",
        "promotion_allowed": False, "totals": totals, "screens": counts, "failures": failures,
        "energy_failures_by_scenario": energy_by_scenario, "all16_primary_common_deltas": primary_values,
        "scored_windows": scored_windows, "null_windows": null_windows, "curve_rows": curve_rows,
        "near_silent_export_flags": exact_flags, "cases_passed": cases_passed,
        "reference_energy_remeasured": False, "raw_audio_or_DSP_reproduced": False,
        "recovery_curve_or_settling_recomputed": False, "binary_or_receipt_contents_audited": False,
        "scope": "authenticated printed snapshot; exact catalog/geometry/null-pattern consistency and scalar screens"}


def semantic_controls(export, original_lock, require):
    """One bounded in-memory mutant at a time. No files, processes, DSP, or old76 rerun."""
    baseline = _ev_clone(export)
    lock_before = _ev_clone(original_lock)
    pristine_summary = validate_export_values(export, original_lock, require)
    cases = export["D8_RESULT"]["cases"]
    primary = next(i for i, case in enumerate(cases) if case["scenario"] == "doubletalk-nominal")
    far = next(i for i, case in enumerate(cases) if case["scenario"] == "far-only")
    start = ["D8_RESULT", "cases"]
    plans = [
        ("physical-span", start + [0, "final_s16", "baseline", "common", "physical_sample_range", 1],
         "set", 95839, "D8_EXPORT_GEOMETRY"),
        ("output-offset", start + [0, "final_s16", "candidate", "offset_samples"],
         "set", 159, "D8_EXPORT_GEOMETRY"),
        ("omit-null-window", start + [0, "scoring", "windows"],
         "pop_first", None, "D8_EXPORT_GEOMETRY"),
        ("omit-scored-window", start + [0, "scoring", "windows"],
         "pop_last", None, "D8_EXPORT_GEOMETRY"),
        ("null-to-zero", start + [0, "final_s16", "baseline", "one_second_windows", 0, "near_si_sdr_db"],
         "set", 0.0, "D8_EXPORT_NULL"),
        ("applicability", start + [0, "scoring", "windows", 0, "applicable"],
         "set", True, "D8_EXPORT_APPLICABILITY"),
        ("delta", start + [primary, "scoring", "common", "delta_si_sdr_db"],
         "add", 0.125, "D8_EXPORT_DELTA"),
        ("primary-threshold", start + [0, "scoring_method", "primary_min_delta_db"],
         "set", 0.999999, "D8_EXPORT_POLICY"),
        ("projection-threshold", start + [0, "scoring_method", "projection_min_exclusive_db"],
         "set", -121.0, "D8_EXPORT_POLICY"),
        ("screen-value", start + [0, "screens", "checks", 0, "values", "delta"],
         "set", 1.0, "D8_EXPORT_SCREEN_ROW"),
        ("screen-decision", start + [0, "screens", "checks", 0, "passed"],
         "set", False, "D8_EXPORT_SCREEN_ROW"),
        ("screen-order", start + [0, "screens", "checks"],
         "swap_first", None, "D8_EXPORT_SCREEN_ROW"),
        ("omit-veto", start + [primary, "screens", "vetoes"],
         "pop_first", None, "D8_EXPORT_SCREEN_VETO"),
        ("case-decision", start + [primary, "screens", "passed"],
         "set", True, "D8_EXPORT_SCREEN_DECISION"),
        ("case-order", start, "swap_first", None, "D8_EXPORT_CATALOG"),
        ("nonfinite-level", start + [0, "final_s16", "candidate", "common", "rms_dbfs"],
         "set", float("nan"), "D8_EXPORT_NUMBER"),
        ("overflow-integer", start + [0, "final_s16", "candidate", "common", "rms_dbfs"],
         "set", 1 << 4096, "D8_EXPORT_NUMBER"),
        ("boolean-count", start + [0, "clip_counts", "candidate"],
         "set", False, "D8_EXPORT_COUNT"),
        ("missing-curve-point", start + [far, "recovery", "baseline", "curve"],
         "pop_last", None, "D8_EXPORT_CURVE"),
        ("exact-flag", start + [0, "near_silent_exact"],
         "set", False, "D8_EXPORT_EXACT_FLAG"),
        ("source", ["D8_RESULT", "source"], "set", "0" * 40, "D8_EXPORT_SOURCE"),
        ("descriptor-shape", ["report", "bytes"], "set", -1, "D8_EXPORT_DESCRIPTOR"),
    ]
    records = []
    for label, path, operation, replacement, expected in plans:
        require(_ev_same(export, baseline) and _ev_same(original_lock, lock_before),
                "D8_EXPORT_CONTROL_IMMUTABILITY")
        # Accept the pristine snapshot with the exact same semantic validator
        # before making this one isolated change. No alias-preserving deepcopy.
        mutant = _ev_clone(export)
        validate_export_values(mutant, original_lock, require)
        parent = mutant
        for part in path[:-1]:
            parent = parent[part]
        key = path[-1]
        if operation == "set":
            parent[key] = replacement
        elif operation == "add":
            parent[key] += replacement
        elif operation == "pop_first":
            parent[key].pop(0)
        elif operation == "pop_last":
            parent[key].pop()
        elif operation == "swap_first":
            parent[key][0], parent[key][1] = parent[key][1], parent[key][0]
        else:
            require(False, "D8_EXPORT_CONTROL_OPERATION")
        require(not _ev_same(mutant, baseline), "D8_EXPORT_CONTROL_NO_MUTATION")
        try:
            validate_export_values(mutant, original_lock, require)
        except ValueError as error:
            require(str(error) == expected, "D8_EXPORT_CONTROL_WRONG_REASON")
        else:
            require(False, "D8_EXPORT_CONTROL_ACCEPTED")
        del mutant
        require(_ev_same(export, baseline) and _ev_same(original_lock, lock_before),
                "D8_EXPORT_CONTROL_IMMUTABILITY")
        records.append({"label": label, "expected_reason": expected, "observed_reason": expected})
    require(validate_export_values(export, original_lock, require) == pristine_summary,
            "D8_EXPORT_CONTROL_IMMUTABILITY")
    return {"status": "PASS", "controls": len(records), "records": records,
            "scope": "pure printed-export semantics; one in-memory mutant at a time",
            "historical_76_tests_rerun": False, "DSP_executed": False,
            "descriptor_byte_hash_and_duplicate_key_controls_owned_by_parser": True}

def validate_reported_descriptors(exported):
    need(typed_equal({name: exported.get(name) for name in REPORTED_FILES}, REPORTED_FILES),
         "D8_ARCHIVE_REPORTED_DESCRIPTOR")
    return True

def parser_binding_controls(raw_export, exported, manifest):
    """Small in-memory controls, not historical scientific negative reruns."""
    records = []
    def rejection(label, expected, action):
        try:
            action()
        except ValueError as error:
            need(str(error) == expected, "D8_ARCHIVE_CONTROL_WRONG_REASON")
        else:
            need(False, "D8_ARCHIVE_CONTROL_ACCEPTED")
        records.append({"label": label, "expected_reason": expected, "observed_reason": expected})
    need(strict_json(b'{"a":1,"b":[null,true,0.5]}') == {"a": 1, "b": [None, True, 0.5]},
         "D8_ARCHIVE_CONTROL_PRISTINE")
    for label, sample, reason in (
        ("duplicate-root", b'{"a":1,"a":2}', "D8_ARCHIVE_DUPLICATE_KEY"),
        ("duplicate-nested", b'{"a":{"b":1,"b":2}}', "D8_ARCHIVE_DUPLICATE_KEY"),
        ("NaN", b'{"a":NaN}', "D8_ARCHIVE_NONFINITE"),
        ("Infinity", b'{"a":Infinity}', "D8_ARCHIVE_NONFINITE"),
        ("negative-Infinity", b'{"a":-Infinity}', "D8_ARCHIVE_NONFINITE"),
        ("overflow-exponent", b'{"a":1e999}', "D8_ARCHIVE_NONFINITE"),
        ("truncated", b'{"a":', "D8_ARCHIVE_JSON_INVALID"),
    ):
        rejection(label, reason, lambda sample=sample: strict_json(sample))
    bind_export(raw_export)
    changed_raw = bytearray(raw_export)
    changed_raw[0] ^= 1
    rejection("one-export-byte", "D8_ARCHIVE_EXPORT_IDENTITY",
              lambda: bind_export(bytes(changed_raw)))
    del changed_raw
    rejection("missing-export-LF", "D8_ARCHIVE_EXPORT_IDENTITY",
              lambda: bind_export(raw_export[:-1]))
    validate_reported_descriptors(exported)
    altered = {key: dict(exported[key]) for key in REPORTED_FILES}
    altered["report"]["bytes"] += 1
    rejection("reported-size", "D8_ARCHIVE_REPORTED_DESCRIPTOR",
              lambda: validate_reported_descriptors(altered))
    altered["report"] = dict(exported["report"])
    altered["completion"]["sha256"] = "0" * 64
    rejection("reported-digest", "D8_ARCHIVE_REPORTED_DESCRIPTOR",
              lambda: validate_reported_descriptors(altered))
    sample = b"archive-source-binding\n"
    entry = {"mode": "100644", "type": "blob", "git_object": git_blob(sample)}
    need(check_file_binding(sample, 0o100644, entry, git_blob(sample), descriptor(sample)),
         "D8_ARCHIVE_CONTROL_PRISTINE")
    rejection("source-byte", "D8_ARCHIVE_SOURCE_BINDING",
        lambda: check_file_binding(sample + b"x", 0o100644, entry, git_blob(sample), descriptor(sample)))
    rejection("source-object", "D8_ARCHIVE_SOURCE_BINDING",
        lambda: check_file_binding(sample, 0o100644, entry, "0" * 40, descriptor(sample)))
    rejection("source-mode", "D8_ARCHIVE_SOURCE_BINDING",
        lambda: check_file_binding(sample, 0o100755, entry, git_blob(sample), descriptor(sample)))
    validate_manifest(manifest, exported)
    changed_manifest = dict(manifest)
    changed_manifest["execution"] = dict(manifest["execution"], head="0" * 40)
    rejection("execution-authority", "D8_ARCHIVE_MANIFEST",
              lambda: validate_manifest(changed_manifest, exported))
    changed_manifest = dict(manifest)
    changed_manifest["console_export"] = dict(manifest["console_export"], sha256="0" * 64)
    rejection("export-authority", "D8_ARCHIVE_MANIFEST",
              lambda: validate_manifest(changed_manifest, exported))
    changed_manifest = dict(manifest, measurement_valid=1)
    rejection("boolean-authority", "D8_ARCHIVE_MANIFEST",
              lambda: validate_manifest(changed_manifest, exported))
    need(git_blob(raw_export) == EXPORT_GIT_BLOB and
         typed_equal({name: exported[name] for name in REPORTED_FILES}, REPORTED_FILES),
         "D8_ARCHIVE_CONTROL_PRISTINE")
    validate_manifest(manifest, exported)
    return {"status": "PASS", "controls": len(records), "records": records,
            "scope": "in-memory strict JSON, immutable byte/hash, descriptor and source-authority predicates",
            "historical_76_tests_rerun": False, "DSP_executed": False}

def emit_once(value):
    global STDOUT_STARTED
    check()
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False) + "\n").encode("ascii")
    need(len(raw) <= 65536 and not STDOUT_STARTED, "D8_ARCHIVE_STDOUT_BOUND")
    os.set_blocking(1, False)
    with selectors.DefaultSelector() as selector:
        selector.register(1, selectors.EVENT_WRITE)
        offset = 0
        while offset < len(raw):
            check()
            if not selector.select(min(0.05, max(0.0, ACTIVE_DEADLINE - time.monotonic()))):
                continue
            check()
            STDOUT_STARTED = True
            try:
                sent = os.write(1, raw[offset:])
            except BlockingIOError:
                continue
            need(sent > 0, "D8_ARCHIVE_STDOUT")
            offset += sent
    check()

def main():
    need(len(sys.argv) == 3 and sys.argv[1] == "--expected-head" and
         re.fullmatch(r"[0-9a-f]{40}", sys.argv[2]) is not None, "D8_ARCHIVE_ARGUMENTS")
    validation_head = sys.argv[2]
    need(Path(__file__).absolute() == ROOT / CHECKER_PATH and ROOT == ROOT.resolve(strict=True),
         "D8_ARCHIVE_ROOT")
    preloaded = {}
    for name in (LOCK_PATH, EXPORT_PATH, MANIFEST_PATH):
        preloaded[name] = read_file(name)
    lock_raw = preloaded[LOCK_PATH][0]
    need(git_blob(lock_raw) == UNCHANGED_D8[LOCK_PATH], "D8_ARCHIVE_LOCK_IDENTITY")
    lock = strict_json(lock_raw)
    exported = bind_export(preloaded[EXPORT_PATH][0])
    validate_reported_descriptors(exported)
    manifest_raw = preloaded[MANIFEST_PATH][0]
    need(len(manifest_raw) == MANIFEST_BYTES and
         hashlib.sha256(manifest_raw).hexdigest() == MANIFEST_SHA256, "D8_ARCHIVE_MANIFEST_IDENTITY")
    manifest = strict_json(manifest_raw)
    validate_manifest(manifest, exported)
    sources = validate_sources(lock, validation_head, preloaded)
    summary = validate_export_values(exported, lock, need)
    parser_controls = parser_binding_controls(preloaded[EXPORT_PATH][0], exported, manifest)
    semantic_checks = semantic_controls(exported, lock, need)
    check()
    return {"status": "ARCHIVED_EVIDENCE_VALIDATED_NO_DSP", "experiment": EXPERIMENT,
        "scientific_terminal": "NO_ADVANCE", "measurement_valid_in_archived_run": True,
        "promotion_allowed": False, "source_bindings": sources,
        "console_export": {"path": EXPORT_PATH, "bytes": EXPORT_BYTES,
            "sha256": EXPORT_SHA256, "git_blob": EXPORT_GIT_BLOB},
        "reported_files_from_console_only": REPORTED_FILES, "projection_validation": summary,
        "archive_controls": {"parser_and_bindings": parser_controls, "semantics": semantic_checks},
        "resources": {"effective_limits": ACTUAL_LIMITS, "file_read_bytes": READ_BYTES,
            "file_read_limit": READ_LIMIT, "per_file_limit": FILE_LIMIT,
            "git_capture_bytes": GIT_BYTES, "git_capture_limit": GIT_TOTAL_LIMIT,
            "root_seconds": 120, "child_seconds_max": 30, "stdout_bytes_max": 65536,
            "elapsed_before_output_seconds": time.monotonic() - STARTED},
        "scope": {"correlated_recorded_pairs": 4,
            "synthetic_broadside_propagation_disclosed": True,
            "artifact_members_opened": False, "waveform_or_metric_recomputation": False,
            "negative_or_completion_receipt_contents_audited": False,
            "archival_validation_is_reproduction": False,
            "reference_energy_remeasured": False,
            "trigger_coverage": "existing D8 path/manual selectors only; not universal dependency monitoring",
            "reopening": "requires an explicit new user request and reviewed source change",
            "timing": "internal120s starts at Python STARTED; external GNU timeout120s starts earlier; "
                "both include output, with scheduling/signal/kernel latency",
            "evidence": "exact printed snapshot and descriptors, not independently reopened artifact members"}}

if __name__ == "__main__":
    # GNU timeout owns this existing process group; never create another group.
    # No Git is launched until both identity and the kill-only alarm are set.
    GROUP = os.getpgrp()
    if GROUP != os.getppid() or GROUP == os.getpid():
        os._exit(125)
    signal.signal(signal.SIGALRM, expire)
    arm(DEADLINE)
    try:
        report = main()
        emit_once(report)
        os._exit(0)
    except Exception as error:
        check()
        if STDOUT_STARTED:
            os._exit(1)  # do not append a second record after partial output
        reason = str(error) if type(error) is ValueError else "D8_ARCHIVE_INTERNAL"
        if re.fullmatch(r"D8_(?:ARCHIVE|EXPORT)_[A-Z0-9_]{1,80}", reason) is None:
            reason = "D8_ARCHIVE_INTERNAL"
        try:
            emit_once({"status": "ARCHIVE_VALIDATION_FAILED_NO_DSP", "reason": reason,
                       "promotion_allowed": False, "execution_head": EXECUTION_SHA})
        except Exception:
            check()
        os._exit(1)
