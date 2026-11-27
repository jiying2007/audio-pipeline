#!/usr/bin/env python3
"""Source-bound AP portable engineering; no real speech or candidate search.

The old AEC3 observer is deliberately imported without changing its bytes.
Only ``run`` compiles, and it is restricted to the frozen Actions host.
``verify`` is byte/semantic readback; ``engineering`` is an explicit bounded
synthetic recheck on a new host, never an automatic fallback or retry.
"""
from __future__ import annotations

import argparse
import array
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time

import webrtc_aec3_ci as previous
from contracts import ROOT, hex_digest, require, sha256

PLAN = ".github/research/frontend-evolution-v1/ap-current-portable-v1.json"
MODULE = "tests/validation/frontend_evolution/ap_current_ci.py"
TEST = "tests/validation/frontend_evolution/test_ap_current_ci.py"
WORKFLOW = previous.WORKFLOW
REFERENCE = "c7baccb8f72cda26128f3ff2bee772a382853d1f"
PREDECESSOR = "819849ee3ed6b269b8417ef8700eecfcf29f7958"
PREDECESSOR_SHA256 = "99b75e18c580baa36612cb904f146a85559cc19fb5309eb2939f715074e0237f"
MAIN_REFERENCE = "4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba"
JOB_MARKER = "\n  ap-current-portable:\n"
SCOPE_BLOCK = """          # AP_CURRENT_OUTER_SELECTOR_BEGIN
          import sys
          sys.path.insert(0, 'tests/validation/frontend_evolution')
          from ap_current_ci import select_workflow as select_ap_workflow
          if select_ap_workflow():
              raise SystemExit(0)
          # AP_CURRENT_OUTER_SELECTOR_END
"""
NAVIGATION = "docs/research/frontend-evolution-v1/README.md"
NAVIGATION_ENTRIES = (
    "[当前 AP 可搬移工程包：源码身份、双麦帧与宿主复验](AP_CURRENT_PORTABLE_V1.zh-CN.md)\n\n",
    "[F05 新八说话人双麦整链验证合同（128 例，尚未执行）](F05_DUALMIC_VALIDATION_V1.zh-CN.md)\n\n",
    "[F05 新八说话人双麦实际结果与独立回读](F05_DUALMIC_VALIDATION_20261128/README.zh-CN.md)\n\n",
)
RESULT_PATHS = (
    "docs/research/frontend-evolution-v1/F05_DUALMIC_VALIDATION_20261128/README.zh-CN.md",
    "docs/research/frontend-evolution-v1/F05_DUALMIC_VALIDATION_20261128/measurement-summary.json",
    "docs/research/frontend-evolution-v1/F05_DUALMIC_VALIDATION_20261128/independent-readback.json",
    "docs/research/frontend-evolution-v1/F05_DUALMIC_VALIDATION_20261128/primary-by-speaker.svg",
    "docs/research/frontend-evolution-v1/PLATFORM_IMPLEMENTATION_CLOSURE_20261128.zh-CN.md",
)
RESULT_DETECTION_PREFIXES = ("docs/research/frontend-evolution-v1/F05_DUALMIC_VALIDATION_20261128/",
                             "docs/research/frontend-evolution-v1/PLATFORM_IMPLEMENTATION_CLOSURE_")
VERIFY_LINES = (
    "          timeout 60s python3 -B tests/validation/frontend_evolution/test_ap_current_ci.py\n",
    "          timeout 60s python3 -B tests/validation/frontend_evolution/test_f05_dualmic_validation.py\n",
)
TEST_VIEW_OLD = "        cls.current = (ci.ROOT / ci.WORKFLOW).read_text()\n"
TEST_VIEW_NEW = ("        from ap_current_ci import predecessor_workflow\n"
                 "        cls.current = predecessor_workflow((ci.ROOT / ci.WORKFLOW).read_text())\n")
DOCS_LINES = (
    "python3 -B tests/validation/frontend_evolution/test_dechorate_rir_gap.py\n",
    "python3 tests/validation/frontend_evolution/test_fe09_same_run_artifact_download.py\n",
)
CONTROL_FILES = (MODULE, TEST, PLAN, WORKFLOW,
                 "tests/validation/frontend_evolution/webrtc_aec3_ci.py",
                 "tests/validation/frontend_evolution/webrtc_aec3_source.py",
                 "tests/validation/frontend_evolution/contracts.py",
                 "validation/tools/render_corr_exact.c",
                 "validation/tools/render_corr_exact.py",
                 "validation/tools/run_validation_engine.py")
PATHS = {"processor": "bin/ap_process_pcm", "build_info": "bin/ap_build_info_dump",
         "render_corr": "lib/librender_corr_exact.so",
         "build_receipt": "build/build-receipt.json", "engineering": "engineering/engineering.json"}
ELF_KEYS = ("processor", "build_info", "render_corr")
CORR_SOURCE = "validation/tools/render_corr_exact.c"
CORR_LOADER = "validation/tools/render_corr_exact.py"
CORR_ENGINE = "validation/tools/run_validation_engine.py"
CORR_PINS = {
    CORR_SOURCE: "19cbf9af3b3e36c5ca88546b4a6ab091af0292cbb2bffd69ac121eda70be90ac",
    CORR_LOADER: "0a2f720e5b1eb29f7f4174bcadc8bca0d88bc5d0e34b9b19337c13d683127a81",
    CORR_ENGINE: "9082b061e7e46aa1c48c82c0ec845524110e01e910aa51e5b83c2c9d9594789a",
}
CORR_FLAGS = ["-O3", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fno-fast-math",
              "-ffp-contract=off", "-fPIC", "-shared"]
CORR_ABI = {"symbol": "ap_validation_max_abs_corr", "result": "double",
            "arguments": ["const int16_t*", "size_t", "const int16_t*", "size_t", "int", "int*"],
            "sizes_bytes": {"int16_t": 2, "size_t": 8, "int": 4, "double": 8}}
_RENDER_BINDINGS = {}
LATENCY_MS = {"call": 10, "assistant": 10}
LATENCY_SAMPLES = {"call": 160, "assistant": 160}
TRACE_KEYS = {"frame", "algorithmic_latency_ms", "vad_probability", "vad_active",
              "far_end_active", "double_talk_active", "erle_db", "erle_valid",
              "aec_converged", "estimated_delay_ms", "delay_error_samples"}
BUILD_KEYS = {"version", "module_mask", "aec_backend", "ns_estimator", "simd_backend",
              "resampler_mode", "fast_math", "source_revision", "compiler_id",
              "compiler_version", "target_triple", "build_type", "config_digest"}
REGISTRIES = ("reviewed_integration", "reviewed_transport", "reviewed_transport_followup", "reviewed_ref_retention")


def json_value(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def read_json(path: Path) -> dict:
    return json_value(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


def plan() -> dict:
    return read_json(ROOT / PLAN)


def git_bytes(revision: str, path: str):
    require(hex_digest(revision, 40), "exact Git revision required")
    result = subprocess.run(["git", "-C", str(ROOT), "show", revision + ":" + path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if result.returncode:
        exists = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", revision + "^{commit}"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        require(exists.returncode == 0, "missing public source object: " + revision)
        return None
    return result.stdout


def digest_or_none(data):
    return None if data is None else sha256(data)


def predecessor_workflow(text: str) -> str:
    """Restore only the declared AP wiring, then prove the entire predecessor."""
    declaration = plan()["workflow"]
    frozen = git_bytes(PREDECESSOR, WORKFLOW)
    require(declaration["predecessor_public_revision"] == PREDECESSOR
            and declaration["predecessor_workflow_sha256"] == PREDECESSOR_SHA256
            and frozen is not None and sha256(frozen) == PREDECESSOR_SHA256,
            "AP_FROZEN_PUBLIC_PREDECESSOR_IDENTITY_CHANGED")
    if JOB_MARKER not in text:
        require(text.encode() == frozen,
                "AP_PREDECESSOR_WORKFLOW_CHANGED")
        return text
    require(text.count(JOB_MARKER) == 1 and text.count(SCOPE_BLOCK) == 1, "AP_DUPLICATE_OR_MISSING_WIRING")
    prefix, job = text.split(JOB_MARKER, 1)
    require(job == job_text().split(JOB_MARKER, 1)[1], "AP_JOB_CHANGED")
    for path in plan()["workflow"]["trigger_core_paths"]:
        line = "      - '" + path + "'\n"
        require(prefix.count(line) == 2, "AP_TRIGGER_MISSING_OR_DUPLICATE")
        prefix = prefix.replace(line, "")
    option = ", ap-current-portable]"
    output = "      ap: ${{ steps.select.outputs.ap }}\n"
    require(prefix.count(option) == 1 and prefix.count(output) == 1, "AP_SCOPE_OUTPUT_MISSING_OR_DUPLICATE")
    prefix = prefix.replace(option, "]").replace(output, "").replace(SCOPE_BLOCK, "")
    require(prefix.encode() == frozen,
            "AP_HISTORICAL_OR_AEC3_WORKFLOW_CHANGED")
    return prefix


def strip_exact(data: bytes, fragments: tuple) -> bytes:
    text = data.decode()
    for fragment in fragments:
        require(text.count(fragment) <= 1, "AP_DUPLICATE_SUPPORT_LINE")
        text = text.replace(fragment, "")
    return text.encode()


def validate_transition(path: str, before, after, configuration: dict) -> str:
    """Closed old→new registrations prevent later-main rollback acceptance."""
    require(after is not None, "AP_DELETION_NOT_REGISTERED: " + path)
    workflow = configuration["workflow"]
    require(workflow["reserved_result_paths"] == list(RESULT_PATHS), "reserved result paths changed")
    if path in RESULT_PATHS:
        require(before is None, "AP_PUBLISHED_RESULT_REWRITE_FORBIDDEN: " + path)
        return "support"
    if path in workflow["trigger_core_paths"]:
        return "ap"
    if path == WORKFLOW:
        predecessor_workflow(after.decode())
        require(before is not None, "AP_WORKFLOW_PREDECESSOR_MISSING")
        old = before.decode()
        require(old == git_bytes(MAIN_REFERENCE, path).decode() or
                predecessor_workflow(old) == git_bytes(PREDECESSOR, path).decode(),
                "AP_UNREGISTERED_WORKFLOW_PREDECESSOR")
        return "support"
    if path == "tests/validation/frontend_evolution/test_webrtc_aec3_ci.py":
        require(after.count(TEST_VIEW_NEW.encode()) == 1, "AP_TEST_VIEW_MISSING")
        after = after.replace(TEST_VIEW_NEW.encode(), TEST_VIEW_OLD.encode())
        if before is not None:
            before = before.replace(TEST_VIEW_NEW.encode(), TEST_VIEW_OLD.encode())
    elif path == previous.VERIFY_WORKFLOW:
        require(all(after.count(line.encode()) == 1 for line in VERIFY_LINES), "AP_TINY_WIRING_MISSING")
        after = strip_exact(after, VERIFY_LINES)
        if before is not None:
            before = strip_exact(before, VERIFY_LINES)
    elif path == NAVIGATION:
        after = strip_exact(after, NAVIGATION_ENTRIES)
        if before is not None:
            before = strip_exact(before, NAVIGATION_ENTRIES)
    elif path == ".github/scripts/verify-docs-gate.sh":
        require(before is not None, "AP_DOCS_GATE_PREDECESSOR_MISSING")
        for line in DOCS_LINES:
            require(after.count(line.encode()) >= before.count(line.encode()), "AP_REMOVED_EXISTING_TINY")
        baseline = git_bytes(MAIN_REFERENCE, path)
        require(strip_exact(before, DOCS_LINES) == strip_exact(after, DOCS_LINES) == strip_exact(baseline, DOCS_LINES),
                "AP_OTHER_DOCS_GATE_CHANGE")
        return "support"
    if before == after:
        # The only net change was one of the explicit view/tiny/navigation additions.
        require(path in (NAVIGATION, previous.VERIFY_WORKFLOW,
                         "tests/validation/frontend_evolution/test_webrtc_aec3_ci.py"),
                "AP_EMPTY_TRANSITION")
        return "support"
    for name in REGISTRIES:
        row = workflow[name]["files"].get(path)
        bases = {row["base_sha256"]} if row else set()
        if row and "main_base_sha256" in row:
            bases.add(row["main_base_sha256"])
        if row and digest_or_none(before) in bases and sha256(after) == row["sha256"]:
            return "aec3" if row["role"].startswith("reviewed_AEC3_method") else "support"
    raise ValueError("AP_UNREGISTERED_CHANGE_OR_ROLLBACK: " + path)


def select(event: str, selected: str, changes: dict, current: str) -> dict | None:
    configuration = plan()
    # Always validate the complete actual workflow before a view is used.
    predecessor_workflow(current)
    false = {name: "false" for name in previous.HISTORICAL_FLAGS}
    if event == "workflow_dispatch":
        if selected in ("ap-current-portable", "webrtc-aec3-engineering"):
            return dict(false, ap=str(selected == "ap-current-portable").lower(),
                        webrtc=str(selected == "webrtc-aec3-engineering").lower())
        return None
    require(event in ("pull_request", "push"), "AP_UNSUPPORTED_EVENT")
    if WORKFLOW in changes:
        require(changes[WORKFLOW][1] == current.encode(), "AP_ACTUAL_WORKFLOW_DIFF_MISMATCH")
    known = set(configuration["workflow"]["trigger_core_paths"])
    known.update(RESULT_PATHS)
    for name in REGISTRIES:
        known.update(configuration["workflow"][name]["files"])
    if not changes or not any(path in known or path.startswith(RESULT_DETECTION_PREFIXES) for path in changes):
        return None
    roles = [validate_transition(path, values[0], values[1], configuration)
             for path, values in changes.items()]
    ap = "ap" in roles
    aec3 = "aec3" in roles
    # Introduction of the frozen AEC3 job/source must not be hidden by AP dispatch.
    if WORKFLOW in changes:
        before = changes[WORKFLOW][0] or b""
        aec3 = aec3 or previous.JOB_MARKER.encode() not in before
        ap = ap or JOB_MARKER.encode() not in before
    return dict(false, ap=str(ap).lower(), webrtc=str(aec3).lower())


def select_workflow() -> bool:
    event = os.environ["EVENT_NAME"]
    changes = {}
    if event != "workflow_dispatch":
        base = os.environ["BASE_SHA"]
        require(hex_digest(base, 40) and base != "0" * 40, "AP_EXACT_BASE_REQUIRED")
        head = previous.git("rev-parse", "HEAD").strip()
        for path in previous.git("diff", "--name-only", base, "HEAD").splitlines():
            changes[path] = (git_bytes(base, path), git_bytes(head, path))
    result = select(event, os.environ.get("SELECTED_EXPERIMENT", ""), changes,
                    (ROOT / WORKFLOW).read_text())
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name, value in (result or {"ap": "false"}).items():
            output.write(name + "=" + value + "\n")
    return result is not None


def execution_environment() -> dict:
    environment = dict(os.environ, LC_ALL="C", PYTHONDONTWRITEBYTECODE="1")
    for name in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH", "CC", "CFLAGS", "CPPFLAGS",
                 "LDFLAGS", "CPATH", "C_INCLUDE_PATH", "LIBRARY_PATH", "CMAKE_TOOLCHAIN_FILE"):
        environment.pop(name, None)
    return environment


def file_map(root: Path, excluded: tuple = ()) -> dict:
    require(root.is_dir() and not root.is_symlink(), "regular directory required")
    result, total = {}, 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        require(all(not (Path(directory) / name).is_symlink() for name in dirs), "directory symlink forbidden")
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "link or special file forbidden")
            total += info.st_size
            require(total <= 64 * 1024 * 1024 and len(result) < 512, "engineering package bound exceeded")
            if relative not in excluded:
                result[relative] = sha256(path.read_bytes())
    return dict(sorted(result.items()))


def relative_file(root: Path, name: str) -> Path:
    p = PurePosixPath(name)
    require(isinstance(name, str) and name and str(p) == name and not p.is_absolute()
            and ".." not in p.parts and "." not in p.parts and "\\" not in name,
            "unsafe relative path")
    target = root / name
    require(not any(parent.is_symlink() for parent in [target] + list(target.parents)), "path symlink forbidden")
    require(target.is_file() and stat.S_ISREG(target.lstat().st_mode) and target.stat().st_nlink == 1,
            "regular unlinked file required: " + name)
    return target


def check_map(root: Path, files: dict, excluded: tuple = ()) -> None:
    require(isinstance(files, dict) and files and all(hex_digest(digest, 64) for digest in files.values()),
            "invalid file hash map")
    for name in files:
        relative_file(root, name)
    require(files == file_map(root, excluded), "complete file manifest mismatch")


def finite(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(item) for item in value.values())
    if isinstance(value, list):
        return all(finite(item) for item in value)
    return True


def trace_rows(path: Path, count: int) -> list:
    data = path.read_bytes()
    require(not data or data.endswith(b"\n"), "truncated frame trace")
    rows = [json_value(line) for line in data.splitlines()]
    require(len(rows) == count, "incomplete frame trace")
    for index, row in enumerate(rows):
        require(isinstance(row, dict) and set(row) == TRACE_KEYS and finite(row)
                and all(type(value) in (int, float) for value in row.values()), "invalid trace fields")
        require(all(type(row[key]) is int for key in TRACE_KEYS - {"vad_probability", "erle_db"}),
                "noninteger trace counter or flag")
        require(all(row[key] in (0, 1) for key in ("vad_active", "far_end_active", "double_talk_active",
                                                  "erle_valid", "aec_converged")), "invalid trace flag")
        require(type(row["frame"]) is int and type(row["algorithmic_latency_ms"]) is int
                and row["frame"] == index and row["algorithmic_latency_ms"] == 10,
                "frame index or declared latency mismatch")
    return rows


def build_info(data: bytes, revision: str) -> dict:
    pairs = [line.split("=", 1) for line in data.decode().splitlines()]
    require(all(len(pair) == 2 for pair in pairs) and len(pairs) == len(BUILD_KEYS), "invalid build-info output")
    result = dict(pairs)
    require(set(result) == BUILD_KEYS and result["source_revision"] == revision,
            "binary source identity mismatch")
    expected = {"version": "2.3.66", "aec_backend": "mdf", "ns_estimator": "ema",
                "simd_backend": "scalar", "resampler_mode": "bandlimited", "fast_math": "0",
                "build_type": "Release", "compiler_id": "GNU", "module_mask": "1023"}
    require(all(result[key].lower() == value.lower() for key, value in expected.items()), "binary build profile mismatch")
    require(hex_digest(result["config_digest"], 64) and result["compiler_version"] and result["target_triple"],
            "incomplete actual compiler/config identity")
    return result


def runtime_identity(paths: dict) -> dict:
    return {name: previous.runtime_identity(paths[name], execution_environment())
            for name in ELF_KEYS}


def normalize_runtime(value: dict) -> dict:
    result = {}
    require(set(value) == set(ELF_KEYS), "missing processor or validation-helper runtime identity")
    for binary in ELF_KEYS:
        result[binary] = normalize_render_corr_runtime(value[binary])
    return result


def normalize_render_corr_runtime(row: dict) -> dict:
    """Normalize one actual ldd observation, without asserting host equivalence."""
    require(set(row) == {"system", "machine", "release", "os_release_sha256", "libraries", "library_names"},
            "incomplete runtime identity")
    require(row["system"] == "Linux" and row["machine"] == "x86_64"
            and hex_digest(row["os_release_sha256"], 64), "unsupported runtime host")
    libraries = {name: row["libraries"][path] for name, path in row["library_names"].items()}
    require(libraries and all(hex_digest(item, 64) for item in libraries.values())
            and set(row["libraries"]) == set(row["library_names"].values()), "invalid runtime library identity")
    return {"system": row["system"], "machine": row["machine"], "release": row["release"],
            "os_release_sha256": row["os_release_sha256"], "libraries": libraries}


def controls(revision: str) -> dict:
    require(hex_digest(revision, 40), "exact public revision required")
    result = {}
    for name in CONTROL_FILES:
        data = git_bytes(revision, name)
        require(data is not None and (ROOT / name).read_bytes() == data, "loaded method differs from committed source: " + name)
        result[name] = sha256(data)
    return result


def correlation_sources() -> dict:
    require(plan()["render_correlation"]["source_pins"] == CORR_PINS, "canonical helper pins changed")
    for name, digest in CORR_PINS.items():
        require(sha256((ROOT / name).read_bytes()) == digest and
                git_bytes(MAIN_REFERENCE, name) == (ROOT / name).read_bytes(),
                "canonical helper/loader/engine source changed")
    directory = str(ROOT / "validation/tools")
    if directory not in sys.path:
        sys.path.insert(0, directory)
    module = importlib.import_module("render_corr_exact")
    engine = importlib.import_module("run_validation_engine")
    require(Path(module.__file__).resolve() == ROOT / CORR_LOADER
            and Path(module.SOURCE_PATH).resolve() == ROOT / CORR_SOURCE
            and Path(engine.__file__).resolve() == ROOT / CORR_ENGINE,
            "unexpected loaded canonical module path")
    return {"module": module, "engine": engine}


def reject_loader_pollution(current: dict, initial: bytes) -> None:
    names = ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH")
    original = {}
    for item in initial.split(b"\x00"):
        key, separator, value = item.partition(b"=")
        if separator and key.decode(errors="replace") in names:
            original[key.decode()] = value
    require(not any(current.get(name) or original.get(name) for name in names),
            "fresh clean Python required: loader pollution at process start or now")


def require_clean_parent() -> None:
    # /proc preserves the exec-time environment, so deleting os.environ entries
    # after startup cannot claim that an already-loaded preload was removed.
    path = Path("/proc/self/environ")
    require(path.is_file(), "Linux process-start environment observation required")
    with path.open("rb") as handle:
        initial = handle.read(1024 * 1024 + 1)
    require(len(initial) <= 1024 * 1024, "process environment observation bound exceeded")
    reject_loader_pollution(os.environ, initial)


def mapped_library_identity(library: Path, runtime: dict) -> dict:
    with Path("/proc/self/maps").open("rb") as handle:
        raw = handle.read(4 * 1024 * 1024 + 1)
    require(len(raw) <= 4 * 1024 * 1024, "mapped-library observation bound exceeded")
    wanted = dict(runtime["libraries"])
    wanted[str(library)] = sha256(library.read_bytes())
    mapped = {}
    for line in raw.decode().splitlines():
        parts = line.split(None, 5)
        if len(parts) != 6 or not parts[5].startswith("/"):
            continue
        path = parts[5]
        require(not (path.endswith(" (deleted)") and path[:-10] in wanted), "loaded helper dependency was deleted")
        resolved = str(Path(path).resolve())
        if resolved not in wanted:
            continue
        info = Path(resolved).stat()
        major, minor = (int(item, 16) for item in parts[3].split(":"))
        require(int(parts[4]) == info.st_ino and (major, minor) == (os.major(info.st_dev), os.minor(info.st_dev)),
                "loaded helper dependency differs from current file inode")
        require(sha256(Path(resolved).read_bytes()) == wanted[resolved], "loaded helper dependency byte mismatch")
        mapped[resolved] = {"sha256": wanted[resolved], "inode": info.st_ino, "device": [major, minor]}
    require(set(mapped) == set(wanted), "helper/runtime dependency not mapped in actual Python process")
    return mapped


def native_abi_types() -> list:
    require(ctypes.sizeof(ctypes.c_int16) == 2 and ctypes.sizeof(ctypes.c_size_t) == 8
            and ctypes.sizeof(ctypes.c_int) == 4 and ctypes.sizeof(ctypes.c_double) == 8,
            "unsupported exact helper ABI")
    return [ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t, ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]


def check_bound_state(module, entry: dict) -> None:
    require(module._NATIVE_TEMP is None and module._NATIVE_STATE is entry["state"]
            and os.getpid() == entry["pid"], "canonical native state changed or was auto-compiled")
    state = module._NATIVE_STATE
    require(state["library"] is entry["library"] and state["function"] is entry["function"]
            and state["library_path"] == entry["path"] and state["binary_sha256"] == entry["binding"]["binary_sha256"]
            and state["compiler"] == entry["binding"]["compiler"], "canonical native object/identity changed")
    require(state["function"].restype is ctypes.c_double and state["function"].argtypes == native_abi_types(),
            "canonical native ABI changed")
    require(module.exact_score is entry["exact_score"] and module.find_best_lag is entry["find_best_lag"]
            and module._load_native is entry["load_native"], "canonical native loader/functions replaced")
    require(sha256(entry["path"].read_bytes()) == entry["binding"]["binary_sha256"], "loaded native helper bytes changed")
    for name, digest in CORR_PINS.items():
        require(sha256((ROOT / name).read_bytes()) == digest, "canonical helper source changed during scoring")
    require_clean_parent()
    require(mapped_library_identity(entry["path"], entry["runtime"]) == entry["mapped"],
            "actual loaded math runtime changed")


def bind_verified_render_corr(root: Path, build: dict, paths: dict, module=None) -> dict:
    require_clean_parent()
    original = correlation_sources()["module"]
    require(module is None or module is original, "must bind the canonical singleton module")
    module = original
    path = paths["render_corr"].resolve()
    helper = build["render_correlation"]
    require(sha256(path.read_bytes()) == helper["binary_sha256"], "precompiled helper byte identity mismatch")
    binding = render_binding(build)
    require(module.SEARCH_ID == binding["search_id"], "canonical search identity changed")
    with module._NATIVE_LOCK:
        require(module._NATIVE_TEMP is None, "auto-compiled canonical helper state is forbidden")
        if module._NATIVE_STATE is not None:
            require(module in _RENDER_BINDINGS, "preexisting native state was not bound by this method")
            entry = _RENDER_BINDINGS[module]
            require(entry["path"] == path and entry["binding"] == binding, "another helper/path/source was already loaded")
            check_bound_state(module, entry)
            return dict(binding)
        require(module not in _RENDER_BINDINGS, "previously bound canonical state was cleared; no fallback is allowed")
        runtime = previous.runtime_identity(path, execution_environment())
        library = ctypes.CDLL(str(path))
        function = library.ap_validation_max_abs_corr
        function.restype = ctypes.c_double
        function.argtypes = native_abi_types()
        state = {"library": library, "function": function, "library_path": path,
                 "binary_sha256": binding["binary_sha256"], "compiler": binding["compiler"]}
        entry = {"state": state, "library": library, "function": function, "path": path, "binding": binding,
                 "runtime": runtime, "mapped": mapped_library_identity(path, runtime), "pid": os.getpid(),
                 "exact_score": module.exact_score, "find_best_lag": module.find_best_lag, "load_native": module._load_native}
        _RENDER_BINDINGS[module] = entry
        module._NATIVE_STATE = state
        check_bound_state(module, entry)
    return dict(binding)


def render_binding(build: dict) -> dict:
    helper = build["render_correlation"]
    return {"schema_version": 1, "status": "BOUND_PREBUILT_VALIDATION_HELPER", "code_revision": build["source_revision"],
               "search_id": "exact-all-integer-lags-stride4-v1", "library": PATHS["render_corr"],
               "binary_sha256": helper["binary_sha256"], "source_sha256": CORR_PINS[CORR_SOURCE],
               "loader_sha256": CORR_PINS[CORR_LOADER], "engine_sha256": CORR_PINS[CORR_ENGINE],
               "compiler": helper["compiler"], "abi": CORR_ABI, "local_compilation": False}


def bind_render_corr_native(root: Path, module=None) -> dict:
    verified = verify_bundle(root)
    return bind_verified_render_corr(root.resolve(), verified["build"], verified["paths"], module)


def guarded_max_abs_corr(module, normalized_corr):
    entry = _RENDER_BINDINGS[module]
    def max_abs_corr(a, b, sample_rate):
        # The unchanged cold loader cannot compile while this lock is held;
        # missing/replaced state is refused before the original exact_score.
        with module._NATIVE_LOCK:
            check_bound_state(module, entry)
            value = module.exact_score(normalized_corr, a, b, sample_rate)
            check_bound_state(module, entry)
            return value
    return max_abs_corr


def build_bound_max_abs_corr(root: Path, normalized_corr, module=None):
    bind_render_corr_native(root, module)
    original = correlation_sources()
    require(normalized_corr is original["engine"].normalized_corr, "original canonical normalized_corr required")
    return guarded_max_abs_corr(original["module"], normalized_corr)


def bound_math_runtime(module) -> dict:
    with module._NATIVE_LOCK:
        require(module in _RENDER_BINDINGS, "helper must be explicitly bound first")
        entry = _RENDER_BINDINGS[module]
        check_bound_state(module, entry)
        actual = previous.runtime_identity(entry["path"], execution_environment())
        require(actual == entry["runtime"], "math dependency identity changed after explicit load")
        return {"runtime_identity": actual, "parent_library_mappings": mapped_library_identity(entry["path"], actual),
                "helper_library_path": str(entry["path"]), "pid": os.getpid(),
                "loader_environment": "CLEAN_AT_START_AND_NOW"}


def render_corr_runtime_identity(root: Path, module=None) -> dict:
    bind_render_corr_native(root, module)
    return bound_math_runtime(correlation_sources()["module"])


def verify_render_corr_runtime(observed: dict, binding: dict, original_bundle: Path = None) -> dict:
    """Pure stored-observation closure check; no current-host existence checks."""
    normalized = normalize_render_corr_runtime(observed["runtime_identity"])
    require(observed["loader_environment"] == "CLEAN_AT_START_AND_NOW"
            and type(observed["pid"]) is int and observed["pid"] > 0, "math host observation mismatch")
    helper_path = observed["helper_library_path"]
    if original_bundle is not None:
        require(helper_path == str(original_bundle / PATHS["render_corr"]),
                "math helper path differs from original engineering bundle")
    require(binding["library"] == PATHS["render_corr"] and hex_digest(binding["binary_sha256"], 64)
            and helper_path.endswith("/" + binding["library"]), "invalid actual helper mapping path")
    expected = dict(observed["runtime_identity"]["libraries"])
    require(helper_path not in expected, "helper must be distinct from its dynamic dependencies")
    expected[helper_path] = binding["binary_sha256"]
    for name in expected:
        path = PurePosixPath(name)
        require(path.is_absolute() and not name.startswith("//") and str(path) == name and ".." not in path.parts and "\\" not in name,
                "noncanonical absolute math mapping path")
    mapped = observed["parent_library_mappings"]
    require(set(mapped) == set(expected) and all(mapped[name]["sha256"] == digest and
            type(mapped[name]["inode"]) is int and mapped[name]["inode"] > 0
            and isinstance(mapped[name]["device"], list) and len(mapped[name]["device"]) == 2
            and all(type(number) is int and number >= 0 for number in mapped[name]["device"])
            for name, digest in expected.items()), "actual parent helper/dependency mapping missing or changed")
    return normalized


def correlation_fixture_specs() -> list:
    state, signal = 20260904, []
    for _ in range(303):
        state = (1664525 * state + 1013904223) & 0xffffffff
        signal.append(int((state >> 8) % 24001) - 12000)
    delayed = [0] * 17 + signal
    return [{"id": "positive-17-unequal", "a": delayed, "b": signal, "expected_lag": 17},
            {"id": "negative-17-unequal", "a": signal, "b": delayed, "expected_lag": -17},
            {"id": "zero-energy", "a": [0] * 128, "b": [0] * 128, "expected_lag": 0},
            {"id": "less-than-64", "a": signal[:63], "b": signal[:59], "expected_lag": 0}]


def correlation_oracle(a: list, b: list, normalized_corr) -> tuple:
    require(len(a) <= 320 and len(b) <= 320, "engineering-only oracle sample bound exceeded")
    best, selected = 0.0, 0
    for lag in range(-1600, 1601):
        score = normalized_corr(a, b, lag, stride=4)
        if score > best:
            best, selected = score, lag
    return selected, best


def run_correlation_checks(root: Path, build: dict, paths: dict, output: Path) -> dict:
    started = time.monotonic()
    original = correlation_sources()
    module, engine = original["module"], original["engine"]
    binding = bind_verified_render_corr(root, build, paths, module)
    guarded = guarded_max_abs_corr(module, engine.normalized_corr)
    rows = []
    for spec in correlation_fixture_specs():
        with module._NATIVE_LOCK:
            check_bound_state(module, _RENDER_BINDINGS[module])
            lag, native = module.find_best_lag(spec["a"], spec["b"], 16000)
            check_bound_state(module, _RENDER_BINDINGS[module])
        canonical = guarded(spec["a"], spec["b"], 16000)
        oracle_lag, oracle = correlation_oracle(spec["a"], spec["b"], engine.normalized_corr)
        require(lag == oracle_lag == spec["expected_lag"] and abs(native - canonical) <= 1e-10
                and abs(canonical - oracle) <= 1e-10, "precompiled canonical correlation engineering mismatch")
        rows.append(dict(spec, sample_rate_hz=16000, a_sha256=sha256(pcm(spec["a"])), b_sha256=sha256(pcm(spec["b"])),
                         native_lag=lag, native_score=native, canonical_score=canonical,
                         oracle_lag=oracle_lag, oracle_score=oracle))
    value = {"schema_version": 1, "status": "PASS_MATH_HELPER_ENGINEERING_ONLY", "binding": binding,
             "checks": rows, "native_function_calls": 8, "oracle_lags_per_case": 3201,
             "audio_processor_calls": 0, "local_compilation": False, "actual_math_runtime": bound_math_runtime(module),
             "elapsed_seconds": time.monotonic() - started}
    write_json(output / "render-corr-checks.json", value)
    return value


def verify_correlation_checks(path: Path, build: dict, runtime: dict) -> dict:
    value = read_json(path)
    require(value.get("schema_version") == 1 and value.get("status") == "PASS_MATH_HELPER_ENGINEERING_ONLY"
            and value["binding"] == render_binding(build) and value["native_function_calls"] == 8
            and value["oracle_lags_per_case"] == 3201 and value["audio_processor_calls"] == 0
            and value["local_compilation"] is False and type(value["elapsed_seconds"]) in (int, float)
            and 0 <= value["elapsed_seconds"] <= 60,
            "canonical helper engineering schema/budget mismatch")
    normalized = correlation_sources()["engine"].normalized_corr
    specs = correlation_fixture_specs()
    require(len(value["checks"]) == len(specs), "missing canonical helper engineering case")
    for spec, row in zip(specs, value["checks"]):
        require(all(row[key] == data for key, data in spec.items()) and row["sample_rate_hz"] == 16000,
                "canonical helper synthetic inputs changed")
        require(row["a_sha256"] == sha256(pcm(spec["a"])) and row["b_sha256"] == sha256(pcm(spec["b"])),
                "canonical helper input SHA mismatch")
        lag, score = correlation_oracle(spec["a"], spec["b"], normalized)
        require(all(type(row[name]) is int for name in ("oracle_lag", "native_lag"))
                and all(type(row[name]) in (int, float) for name in ("oracle_score", "native_score", "canonical_score"))
                and row["oracle_lag"] == row["native_lag"] == lag == spec["expected_lag"]
                and finite(row) and row["oracle_score"] == score
                and abs(row["native_score"] - score) <= 1e-10 and abs(row["canonical_score"] - score) <= 1e-10,
                "canonical helper saved score/lag mismatch")
    observed = value["actual_math_runtime"]
    require(verify_render_corr_runtime(observed, value["binding"]) == normalize_render_corr_runtime(runtime),
            "math check and engineering host differ")
    return value


def pcm(values: list) -> bytes:
    result = array.array("h", values)
    if sys.byteorder != "little":
        result.byteswap()
    return result.tobytes()


def fixture_specs() -> list:
    """Frozen transport inputs only; no target signal or fitted delay exists."""
    signal, future = [], []
    state = 271828183
    for index in range(20 * 160):
        state = (1664525 * state + 1013904223) & 0xffffffff
        pair = [int((state >> 16) % 4097) - 2048, int((state >> 4) % 3073) - 1536]
        signal.extend(pair)
        future.extend(pair if index < 8 * 160 else [-pair[0], pair[1] // 2])
    impulse = [0] * (20 * 160 * 2)
    impulse[8 * 160 * 2:8 * 160 * 2 + 2] = [8192, 4096]
    inputs = {"zero": bytes(4 * 160 * 4), "impulse": pcm(impulse), "signal": pcm(signal),
              "repeat": pcm(signal), "prefix": pcm(signal[:8 * 160 * 2]), "future": pcm(future), "empty": b"",
              "partial-frame": bytes(161 * 4), "odd-byte": b"\x00", "channel-fragment": b"\x00\x00"}
    result = []
    for profile in ("call", "assistant"):
        for mode in ("capture-only", "full-zero-render"):
            for name, data in inputs.items():
                valid = name not in ("partial-frame", "odd-byte", "channel-fragment")
                frames = len(data) // (160 * 4)
                result.append({"id": profile + "-" + mode + "-" + name,
                               "profile": profile, "mode": mode, "case": name,
                               "mic": data, "render": bytes(frames * 160 * 2), "channels": 2,
                               "returncode": 0 if valid else 2, "output_frames": frames})
    for name, profile, channels in (("invalid-profile", "invalid", 2), ("invalid-channels", "call", 3)):
        result.append({"id": name, "profile": profile, "mode": "capture-only", "case": name,
                       "mic": bytes(160 * 4), "render": b"", "channels": channels,
                       "returncode": 2, "output_frames": 0})
    require(len(result) <= 48 and sum(len(row["mic"]) / 4 / 16000 for row in result) <= 5,
            "fixed engineering audio budget exceeded")
    return result


def audio_command(processor: Path, spec: dict, folder: Path) -> list:
    command = [str(processor), "--profile", spec["profile"], "--sample-rate", "16000", "--mic-channels",
               str(spec["channels"]), "--strict-capture-frames", "--metrics-jsonl", str(folder / "trace.jsonl")]
    if spec["mode"] == "capture-only":
        command += ["--capture-only", str(folder / "mic.pcm"), str(folder / "output.pcm")]
    else:
        command += [str(folder / "mic.pcm"), str(folder / "render.pcm"), str(folder / "output.pcm")]
    return command


def validate_audio_paths(mic: Path, render, output: Path, trace: Path) -> None:
    require(not output.exists() and not output.is_symlink() and not trace.exists() and not trace.is_symlink(),
            "fresh output and trace required")
    resolved = [path.resolve() for path in (mic, output, trace)]
    if render is not None:
        resolved.append(render.resolve())
    require(len(resolved) == len(set(resolved)), "input/output path alias")
    require(mic.is_file() and not mic.is_symlink(), "regular capture input required")
    if render is not None:
        require(render.is_file() and not render.is_symlink() and mic.stat().st_size % 4 == 0
                and render.stat().st_size == mic.stat().st_size // 2,
                "render must equal per-channel capture length before execution")


def invoke(command: list, directory: Path, deadline: float, limit: float = 10) -> dict:
    left = deadline - time.monotonic()
    require(left > 0, "AP wall budget exhausted before invocation")
    started = time.monotonic()
    started_utc = datetime.now(timezone.utc).isoformat()
    write_json(directory / "invocation-start.json", {"command": command, "started_utc": started_utc,
                                                     "timeout_seconds": min(left, limit)})
    timed_out = False
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        require(deadline - time.monotonic() > 0, "AP wall budget exhausted before process launch")
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=execution_environment(), start_new_session=True)
        try:
            code = process.wait(timeout=min(deadline - time.monotonic(), limit))
        except (subprocess.TimeoutExpired, TimeoutError):
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait(timeout=5)
    elapsed = time.monotonic() - started
    record = {"command": command, "returncode": code, "elapsed_seconds": elapsed,
              "started_utc": started_utc, "finished_utc": datetime.now(timezone.utc).isoformat(),
              "timed_out": timed_out}
    write_json(directory / "invocation-result.json", record)
    require(not timed_out, "AP process timeout; killed process group, original command/logs preserved")
    require(time.monotonic() < deadline, "AP wall budget exceeded after invocation")
    return record


def validate_invocation(record: dict, folder: Path) -> None:
    saved = read_json(folder / "invocation-result.json")
    require(saved == {key: value for key, value in record.items() if key not in ("id", "files")}
            and saved["timed_out"] is False, "invocation result contradicts report")
    start = read_json(folder / "invocation-start.json")
    require(start["command"] == record["command"] and start["started_utc"] == record["started_utc"]
            and datetime.fromisoformat(record["finished_utc"]) >= datetime.fromisoformat(record["started_utc"]),
            "invocation start/finish contradicts report")


@contextmanager
def wall_guard(deadline: float):
    """POSIX wall deadline includes admission/readback; nesting never extends it."""
    remaining = deadline - time.monotonic()
    require(remaining > 0, "AP wall budget exhausted before stage")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    entered = time.monotonic()
    def expired(signum, frame):
        raise TimeoutError("AP wall deadline reached; only failure preservation may continue")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(remaining, previous_timer[0]) if previous_timer[0] else remaining)
    try:
        yield
        require(time.monotonic() < deadline, "AP wall budget exhausted after stage")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            left = previous_timer[0] - (time.monotonic() - entered)
            if left > 0:
                signal.setitimer(signal.ITIMER_REAL, left, previous_timer[1])


def metadata_queries(paths: dict) -> list:
    return [("build-info", [str(paths["build_info"])]),
            ("default-call", [str(paths["processor"]), "--profile", "call", "--print-default-tuning"]),
            ("default-assistant", [str(paths["processor"]), "--profile", "assistant", "--print-default-tuning"]),
            ("default-implicit", [str(paths["processor"]), "--print-default-tuning"])]


def validate_tuning(raw: bytes) -> dict:
    value = json_value(raw)
    require(isinstance(value, dict) and set(value) == {"aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs"}
            and all(type(item) in (int, float) and math.isfinite(item) for item in value.values()),
            "invalid default tuning output")
    return value


def wrapper_checks(output: Path) -> list:
    folder = output / "wrapper"
    folder.mkdir()
    mic, render = folder / "mic.pcm", folder / "render.pcm"
    mic.write_bytes(bytes(160 * 4))
    render.write_bytes(bytes(159 * 2))
    checks = []
    for name, chosen_output, chosen_trace, chosen_render in (
            ("short-render", folder / "output.pcm", folder / "trace.jsonl", render),
            ("input-output-alias", mic, folder / "trace.jsonl", None),
            ("output-trace-alias", folder / "same", folder / "same", None)):
        try:
            validate_audio_paths(mic, chosen_render, chosen_output, chosen_trace)
        except ValueError as exc:
            checks.append({"id": name, "status": "REFUSED_BEFORE_EXECUTION", "error": str(exc)})
        else:
            raise ValueError("wrapper failed to refuse " + name)
    return checks


def semantic_engineering(root: Path, receipt: Path, binding: dict) -> dict:
    """Validate report semantics against fixed inputs, without running a binary."""
    report = read_json(receipt)
    folder = receipt.parent
    require(report.get("schema_version") == 1 and report.get("status") == "PASS_ENGINEERING_ONLY"
            and report.get("failures") == [] and not (folder / "failure.json").exists(), "engineering failed or incomplete")
    check_map(folder, report["files"], (receipt.name,))
    require(report["source_revision"] == binding["source_revision"]
            and report["controls"] == binding["controls"]
            and report["processor_sha256"] == binding["processor_sha256"]
            and report["build_info_sha256"] == binding["build_info_sha256"], "engineering source/binary binding mismatch")
    require(report["algorithmic_latency_ms"] == LATENCY_MS and report["algorithmic_latency_samples"] == LATENCY_SAMPLES,
            "frozen latency changed")
    require(report["render_corr_sha256"] == binding["render_correlation"]["binary_sha256"]
            and report["render_corr_checks_file"] == "render-corr-checks.json", "engineering math helper identity mismatch")
    helper_checks = verify_correlation_checks(folder / report["render_corr_checks_file"], binding,
                                              report["runtime_identity"]["render_corr"])
    require(type(report["elapsed_seconds"]) in (int, float) and 0 < report["elapsed_seconds"] <= 60
            and report["automatic_retries"] == 0 and report["real_speech_used"] is False
            and report["acoustic_acceptance"] is False and report["physical_target_measurement"] is False,
            "engineering budget or claim mismatch")
    normalize_runtime(report["runtime_identity"])
    require(report["runtime_identity"] == report["runtime_identity_after"], "runtime changed during engineering")
    old_folder = Path(report["execution_directory"])
    require(old_folder.is_absolute(), "missing original command directory")
    old_bundle = Path(report["bundle_directory"])
    require(old_bundle.is_absolute(), "missing original engineering bundle directory")
    verify_render_corr_runtime(helper_checks["actual_math_runtime"], helper_checks["binding"], old_bundle)
    executable = {key: Path(report["executables"][key]) for key in ("processor", "build_info")}
    require(all(path == old_bundle / PATHS[key] for key, path in executable.items()),
            "invalid engineering command binary")
    queries = metadata_queries(executable)
    require(len(report["metadata_queries"]) == 4, "metadata query budget mismatch")
    for record, (name, command) in zip(report["metadata_queries"], queries):
        require(record["id"] == name and record["command"] == command and record["returncode"] == 0
                and 0 <= record["elapsed_seconds"] <= 10, "metadata query mismatch")
        require(record["files"] == file_map(folder / "metadata" / name), "metadata file mismatch")
        validate_invocation(record, folder / "metadata" / name)
    info = build_info((folder / "metadata/build-info/stdout.log").read_bytes(), report["source_revision"])
    require(info == report["build_info"] == binding["build_info"], "embedded build identity changed")
    tuning = {key: validate_tuning((folder / ("metadata/default-" + key + "/stdout.log")).read_bytes())
              for key in ("call", "assistant", "implicit")}
    require(tuning["implicit"] == tuning["call"] and report["implicit_default_equals_call"] is True
            and report["default_tuning"] == {key: tuning[key] for key in ("call", "assistant")},
            "implicit/default tuning mismatch")
    specs = fixture_specs()
    require(len(report["calls"]) == len(specs), "engineering audio call count mismatch")
    require(math.fsum(row["elapsed_seconds"] for row in report["calls"] + report["metadata_queries"])
            + helper_checks["elapsed_seconds"] <= report["elapsed_seconds"],
            "process/helper elapsed sum exceeds actual engineering wall time")
    actual_requested = sum(len(row["mic"]) / 4 / 16000 for row in specs)
    require(report["requested_capture_audio_seconds"] == actual_requested <= 5,
            "engineering audio duration mismatch")
    for spec, record in zip(specs, report["calls"]):
        case = folder / "cases" / spec["id"]
        require(record["id"] == spec["id"] and record["command"] == audio_command(executable["processor"], spec, old_folder / "cases" / spec["id"])
                and record["returncode"] == spec["returncode"] and 0 <= record["elapsed_seconds"] <= 10,
                "engineering call identity/exit/budget mismatch")
        require((case / "mic.pcm").read_bytes() == spec["mic"] and (case / "render.pcm").read_bytes() == spec["render"],
                "fixed synthetic input changed")
        require(record["files"] == file_map(case), "engineering call file hash mismatch")
        validate_invocation(record, case)
        if (case / "output.pcm").exists():
            require((case / "output.pcm").stat().st_size == spec["output_frames"] * 160 * 2,
                    "output frame count mismatch")
        else:
            require(spec["returncode"] != 0 and spec["output_frames"] == 0, "missing successful output")
        if (case / "trace.jsonl").exists():
            trace_rows(case / "trace.jsonl", spec["output_frames"])
        else:
            require(spec["returncode"] != 0 and spec["output_frames"] == 0, "missing successful trace")
    for profile in ("call", "assistant"):
        for mode in ("capture-only", "full-zero-render"):
            prefix = profile + "-" + mode + "-"
            cases = {name: folder / "cases" / (prefix + name) for name in ("signal", "repeat", "prefix", "future", "zero")}
            for filename in ("output.pcm", "trace.jsonl"):
                signal = (cases["signal"] / filename).read_bytes()
                require(signal == (cases["repeat"] / filename).read_bytes(), "repeat is not byte identical")
                short = (cases["prefix"] / filename).read_bytes()
                require(signal.startswith(short) and (cases["future"] / filename).read_bytes().startswith(short),
                        "prefix continuity or future independence failed")
            require(not any((cases["zero"] / "output.pcm").read_bytes()), "zero transport changed")
    require([row["id"] for row in report["wrapper_checks"]] ==
            ["short-render", "input-output-alias", "output-trace-alias"]
            and all(row["status"] == "REFUSED_BEFORE_EXECUTION" for row in report["wrapper_checks"]),
            "missing wrapper rejection")
    require(report["checks"] == ["source-binary-runtime-identity", "default-presets", "strict-frame-count",
                                 "fixed-10ms-metadata", "repeat-and-prefix-continuity", "bounded-negative-inputs",
                                 "precompiled-canonical-render-correlation"],
            "engineering conclusion schema mismatch")
    return report


def engineering(root: Path, output: Path, initial: bool = False) -> dict:
    started = time.monotonic()
    deadline = started + 60
    preexisting = output.exists() or output.is_symlink()
    try:
        with wall_guard(deadline):
            return engineering_impl(root, output, initial, started, deadline)
    except Exception as exc:
        # This also covers expiration at context exit after the inner function
        # wrote its report. Preserve that original report and reject it explicitly.
        if not preexisting and output.is_dir() and not (output / "failure.json").exists():
            write_json(output / "failure.json", {"schema_version": 1, "status": "FAIL",
                                                 "error": str(exc), "elapsed_seconds": time.monotonic() - started})
        raise


def engineering_impl(root: Path, output: Path, initial: bool, started: float, deadline: float) -> dict:
    root, output = root.resolve(), output.absolute()
    if initial:
        binding, paths = verify_build(root)
    else:
        verified = verify_bundle(root)
        binding, paths = verified["build"], verified["paths"]
    require(not output.exists() and not output.is_symlink()
            and (initial or root not in output.parents), "fresh separate engineering output required")
    require(time.monotonic() < deadline, "engineering admission exhausted wall budget")
    output.mkdir(parents=True)
    report = {"schema_version": 1, "status": "FAIL", "source_revision": binding["source_revision"],
              "controls": controls(binding["source_revision"]), "failures": [], "calls": [], "metadata_queries": [],
              "processor_sha256": sha256(paths["processor"].read_bytes()),
              "build_info_sha256": sha256(paths["build_info"].read_bytes()),
              "render_corr_sha256": sha256(paths["render_corr"].read_bytes()),
              "render_corr_checks_file": "render-corr-checks.json",
              "executables": {key: str(paths[key]) for key in ("processor", "build_info")},
              "execution_directory": str(output), "bundle_directory": str(root), "algorithmic_latency_ms": LATENCY_MS,
              "algorithmic_latency_samples": LATENCY_SAMPLES, "automatic_retries": 0,
              "real_speech_used": False, "acoustic_acceptance": False, "physical_target_measurement": False}
    try:
        report["runtime_identity"] = runtime_identity(paths)
        normalize_runtime(report["runtime_identity"])
        run_correlation_checks(root, binding, paths, output)
        for name, command in metadata_queries(paths):
            directory = output / "metadata" / name
            directory.mkdir(parents=True)
            record = dict(invoke(command, directory, deadline), id=name)
            record["files"] = file_map(directory)
            report["metadata_queries"].append(record)
            require(record["returncode"] == 0, "metadata query failed: " + name)
        report["build_info"] = build_info((output / "metadata/build-info/stdout.log").read_bytes(), binding["source_revision"])
        report["default_tuning"] = {key: validate_tuning((output / ("metadata/default-" + key + "/stdout.log")).read_bytes())
                                    for key in ("call", "assistant")}
        report["implicit_default_equals_call"] = (validate_tuning((output / "metadata/default-implicit/stdout.log").read_bytes())
                                                  == report["default_tuning"]["call"])
        specs = fixture_specs()
        report["requested_capture_audio_seconds"] = sum(len(row["mic"]) / 4 / 16000 for row in specs)
        for spec in specs:
            directory = output / "cases" / spec["id"]
            directory.mkdir(parents=True)
            (directory / "mic.pcm").write_bytes(spec["mic"])
            (directory / "render.pcm").write_bytes(spec["render"])
            if spec["returncode"] == 0:
                validate_audio_paths(directory / "mic.pcm", None if spec["mode"] == "capture-only" else directory / "render.pcm",
                                     directory / "output.pcm", directory / "trace.jsonl")
            record = dict(invoke(audio_command(paths["processor"], spec, directory), directory, deadline), id=spec["id"])
            record["files"] = file_map(directory)
            report["calls"].append(record)
            require(record["returncode"] == spec["returncode"], "actual engineering exit mismatch: " + spec["id"])
        report["wrapper_checks"] = wrapper_checks(output)
        report["runtime_identity_after"] = runtime_identity(paths)
        require(report["runtime_identity"] == report["runtime_identity_after"], "actual runtime changed")
        require(controls(binding["source_revision"]) == report["controls"]
                and sha256(paths["processor"].read_bytes()) == report["processor_sha256"]
                and sha256(paths["build_info"].read_bytes()) == report["build_info_sha256"]
                and sha256(paths["render_corr"].read_bytes()) == report["render_corr_sha256"], "source or binary changed")
        report["elapsed_seconds"] = time.monotonic() - started
        require(report["elapsed_seconds"] <= 60, "engineering wall budget exceeded")
        report["checks"] = ["source-binary-runtime-identity", "default-presets", "strict-frame-count",
                            "fixed-10ms-metadata", "repeat-and-prefix-continuity", "bounded-negative-inputs",
                            "precompiled-canonical-render-correlation"]
        report["status"] = "PASS_ENGINEERING_ONLY"
        report["files"] = file_map(output)
        write_json(output / "engineering.json", report)
        semantic_engineering(root, output / "engineering.json", binding)
        require(time.monotonic() < deadline, "engineering verification exceeded wall budget")
        return report
    except Exception as exc:
        report["status"] = "FAIL"
        report["elapsed_seconds"] = time.monotonic() - started
        report["failures"].append(str(exc))
        write_json(output / "failure.json", report)
        raise


def verify_engineering(root: Path, receipt: Path) -> dict:
    binding, _ = verify_build(root.resolve())
    return semantic_engineering(root.resolve(), receipt.resolve(), binding)


def require_host_engineering(root: Path, receipt: Path = None) -> dict:
    verified = verify_bundle(root)
    chosen = verified["paths"]["engineering"] if receipt is None else receipt.resolve()
    report = verify_engineering(root, chosen)
    actual = runtime_identity(verified["paths"])
    require(normalize_runtime(actual) == normalize_runtime(report["runtime_identity"]),
            "current host differs; explicit bounded engineering recheck required")
    return {"engineering": report, "receipt": chosen, "runtime_identity": actual}


def cache_values(data: str) -> dict:
    values = {}
    for line in data.splitlines():
        match = re.match(r"([^#/:][^:=]*):[^=]+=(.*)$", line)
        if match:
            require(match.group(1) not in values, "duplicate CMake cache key")
            values[match.group(1)] = match.group(2)
    return values


def validate_elf_observation(text: str) -> None:
    require(re.search(r"Class:\s+ELF64", text) is not None and
            re.search(r"Machine:\s+Advanced Micro Devices X86-64", text) is not None,
            "ELF architecture differs from fixed x86_64 host")
    for line in text.splitlines():
        if "(RPATH)" in line or "(RUNPATH)" in line:
            match = re.search(r"\[([^]]*)\]", line)
            require(match is not None and all(not part.startswith("/") for part in match.group(1).split(":")),
                    "absolute runtime search path forbidden")


def verify_build(root: Path) -> tuple:
    require(root.is_dir() and not root.is_symlink() and not (root / "failure.json").exists(), "invalid bundle root")
    paths = {key: relative_file(root, name) for key, name in PATHS.items() if key != "engineering"}
    paths["engineering"] = root / PATHS["engineering"]
    build = read_json(paths["build_receipt"])
    configuration = plan()
    require(build.get("schema_version") == 1 and build.get("status") == "BUILT_AP_CURRENT_PORTABLE"
            and build.get("main_dsp_reference") == MAIN_REFERENCE, "invalid AP build receipt")
    revision = build["source_revision"]
    expected_controls = controls(revision)
    require(build["controls"] == expected_controls and build["source_tree"] == previous.git("rev-parse", revision + "^{tree}").strip(),
            "build source tree or method mismatch")
    pins = configuration["source"]["main_reference_files_sha256"]
    require(build["main_reference_files_sha256"] == pins and len(pins) == 59, "main DSP snapshot binding mismatch")
    correlation_sources()
    for name, expected in dict(pins, **expected_controls).items():
        data = relative_file(root, "source/" + name).read_bytes()
        require(sha256(data) == expected and data == git_bytes(revision, name), "source snapshot mismatch: " + name)
        if name in pins:
            require(data == git_bytes(MAIN_REFERENCE, name), "DSP differs from frozen main")
    require(relative_file(root, "licenses/audio-pipeline-LICENSE").read_bytes() == (root / "source/LICENSE").read_bytes(),
            "first-party license changed")
    require(build["processor_sha256"] == sha256(paths["processor"].read_bytes())
            and build["build_info_sha256"] == sha256(paths["build_info"].read_bytes()), "binary SHA mismatch")
    require(all(path.read_bytes()[:4] == b"\x7fELF" for key, path in paths.items() if key in ELF_KEYS),
            "actual ELF binary required")
    helper = build["render_correlation"]
    require(helper["source_pins"] == CORR_PINS and helper["abi"] == CORR_ABI
            and helper["flags"] == CORR_FLAGS and helper["library"] == PATHS["render_corr"]
            and helper["binary_sha256"] == sha256(paths["render_corr"].read_bytes())
            and helper["compiler"] == build["tools"]["gcc"]["version"].splitlines()[0].strip(),
            "precompiled canonical helper source/ABI/compiler mismatch")
    require(build["cmake_options"] == configuration["build"]["cmake_options"]
            and build["parallelism"] == 2 and build["generator"] == "Unix Makefiles", "build options changed")
    cache = cache_values(relative_file(root, "build/CMakeCache.txt").read_text())
    require(all(cache.get(name) == value for name, value in build["cmake_options"].items()), "actual CMake cache mismatch")
    require(cache.get("CMAKE_C_COMPILER") == build["tools"]["gcc"]["path"]
            and cache.get("AP_BUILD_SOURCE_REVISION") == "", "compiler or source override mismatch")
    require(build_info(relative_file(root, "build/identity/stdout.log").read_bytes(), revision) == build["build_info"],
            "build-info receipt disagrees with original stdout")
    require(build["original_build_directory_renamed"] is True and build["absolute_rpath_present"] is False
            and build["source_status_before"] == "" and build["source_status_after"] == "",
            "clean source or relocation check absent")
    require(build["runtime_identity"] == build["runtime_identity_after_relocation"], "relocation changed host dependencies")
    normalize_runtime(build["runtime_identity"])
    require(set(build["elf_observations"]) == set(ELF_KEYS), "missing actual ELF observations")
    for key, row in build["elf_observations"].items():
        folder = root / "build/elf" / key
        require(row["returncode"] == 0 and 0 <= row["elapsed_seconds"] <= 10
                and row["files"] == file_map(folder), "invalid actual ELF observation")
        require(row["command"][:3] == [build["tools"]["readelf"]["path"], "-h", "-d"]
                and Path(row["command"][3]).name == paths[key].name, "ELF observation command changed")
        validate_elf_observation((folder / "stdout.log").read_text())
        validate_invocation(row, folder)
    for row in build["tools"].values():
        require(Path(row["path"]).is_absolute() and hex_digest(row["sha256"], 64) and row["version"]
                and row["sha256"] == row["sha256_after"], "actual tool identity missing or changed")
    for name in ("configure", "compile", "render-corr", "identity"):
        row = build["commands"][name]
        require(row["returncode"] == 0 and 0 <= row["elapsed_seconds"] <= {"configure": 90, "compile": 240, "render-corr": 30, "identity": 10}[name],
                "build command failed or exceeded budget")
        require(row["files"] == file_map(root / "build" / name), "build command output mismatch")
        validate_invocation(row, root / "build" / name)
    require(Path(build["original_source_directory"]).is_absolute(), "original source directory missing")
    require(build["commands"]["configure"]["command"] == configure_command(
                Path(build["original_build_directory"]), build["tools"], Path(build["original_source_directory"])),
            "configure command changed")
    require(build["commands"]["compile"]["command"] == compile_command(Path(build["original_build_directory"]), build["tools"]),
            "compile command changed")
    require(build["commands"]["render-corr"]["command"] == render_corr_command(
                Path(build["original_build_directory"]), build["tools"], Path(build["original_source_directory"])),
            "canonical helper compile command changed")
    require(math.fsum(build["commands"][key]["elapsed_seconds"] for key in ("compile", "render-corr"))
            <= build["compile_stage_elapsed_seconds"] <= 240, "shared compile-stage budget changed")
    return build, paths


def verify_bundle(root: Path) -> dict:
    root = root.resolve()
    manifest = read_json(relative_file(root, "bundle.json"))
    require(manifest.get("schema_version") == 1 and manifest.get("kind") == "AP_CURRENT_PORTABLE_V1"
            and manifest.get("status") == "PASS_ENGINEERING_ONLY" and manifest.get("paths") == PATHS,
            "invalid portable bundle manifest")
    check_map(root, manifest["files"], ("bundle.json",))
    build, paths = verify_build(root)
    require(manifest["code_revision"] == build["source_revision"] and manifest["source_tree"] == build["source_tree"],
            "bundle source revision/tree mismatch")
    engineering_report = semantic_engineering(root, paths["engineering"], build)
    return {"manifest": manifest, "build": build, "engineering": engineering_report, "paths": paths}


def configure_command(directory: Path, tools: dict, source_root: Path = None) -> list:
    return [tools["cmake"]["path"], "-S", str(ROOT if source_root is None else source_root), "-B", str(directory), "-G", "Unix Makefiles",
            "-DCMAKE_C_COMPILER=" + tools["gcc"]["path"], "-DCMAKE_MAKE_PROGRAM=" + tools["make"]["path"]] + [
                "-D" + key + "=" + value for key, value in plan()["build"]["cmake_options"].items()]


def compile_command(directory: Path, tools: dict) -> list:
    return [tools["cmake"]["path"], "--build", str(directory), "--target", "ap_process_pcm", "ap_build_info_dump", "--parallel", "2"]


def render_corr_command(directory: Path, tools: dict, source_root: Path = None) -> list:
    root = ROOT if source_root is None else source_root
    return [tools["gcc"]["path"]] + CORR_FLAGS + [str(root / CORR_SOURCE), "-lm", "-o", str(directory / "librender_corr_exact.so")]


def tool_records(output: Path, deadline: float) -> dict:
    result = {}
    for name in ("gcc", "cmake", "make", "readelf", "ldd"):
        located = shutil.which(name)
        require(located is not None, "required installed tool missing: " + name)
        path = Path(located).resolve(strict=True)
        directory = output / name
        directory.mkdir(parents=True)
        observed = invoke([str(path), "--version"], directory, deadline)
        require(observed["returncode"] == 0, "tool version query failed")
        result[name] = {"path": str(path), "sha256": sha256(path.read_bytes()),
                        "version": (directory / "stdout.log").read_text(), "observation": observed}
    directory = output / "gcc-target"
    directory.mkdir()
    observed = invoke([result["gcc"]["path"], "-dumpmachine"], directory, deadline)
    require(observed["returncode"] == 0, "compiler target query failed")
    result["gcc"]["target_triple"] = (directory / "stdout.log").read_text().strip()
    return result


def save_system_notices(identity: dict, output: Path, deadline: float) -> dict:
    output.mkdir()
    result = {}
    # The system binaries are not redistributed. Preserve the installed package
    # copyright files when the host package database can identify them.
    paths = sorted({path for row in identity.values() for path in row["libraries"]})
    for index, path in enumerate(paths):
        left = min(10, deadline - time.monotonic())
        require(left > 0, "notice observation budget exhausted")
        query = subprocess.run(["dpkg-query", "-S", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=execution_environment(), timeout=left)
        record = {"library": path, "query_returncode": query.returncode,
                  "stdout": query.stdout.decode(errors="replace"), "stderr": query.stderr.decode(errors="replace"), "notices": []}
        if query.returncode == 0:
            for line in query.stdout.decode().splitlines():
                package = line.split(": ", 1)[0].split(":", 1)[0]
                require(re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", package) is not None, "unexpected system package name")
                copyright_path = Path("/usr/share/doc") / package / "copyright"
                if copyright_path.is_file() and copyright_path.stat().st_size <= 2 * 1024 * 1024:
                    target = output / (package + "-copyright")
                    data = copyright_path.read_bytes()
                    if not target.exists():
                        target.write_bytes(data)
                    require(target.read_bytes() == data, "system notice collision")
                    record["notices"].append({"file": target.name, "sha256": sha256(data)})
        result[str(index)] = record
    write_json(output / "observation.json", result)
    return result


def archive_readback(root: Path, target: Path) -> str:
    require(not target.exists(), "fresh package archive required")
    expected = file_map(root)
    with tarfile.open(target, "x:gz", format=tarfile.PAX_FORMAT) as archive:
        for name in expected:
            archive.add(root / name, arcname=name, recursive=False)
    require(target.stat().st_size <= 64 * 1024 * 1024, "compressed archive budget exceeded")
    observed = {}
    with tarfile.open(target, "r:gz") as archive:
        for member in archive.getmembers():
            require(member.isfile() and member.name in expected and member.name not in observed
                    and member.size <= 64 * 1024 * 1024, "unexpected archive member")
            stream = archive.extractfile(member)
            require(stream is not None, "missing archive bytes")
            observed[member.name] = sha256(stream.read())
    require(observed == expected, "archive independent readback mismatch")
    return sha256(target.read_bytes())


def run(expected: str, output: Path) -> dict:
    started = time.monotonic()
    deadline = started + 600
    preexisting = output.exists() or output.is_symlink()
    try:
        with wall_guard(deadline):
            return run_impl(expected, output, started, deadline)
    except Exception as exc:
        receipt = output / "ci-receipt.json"
        if not preexisting and receipt.is_file():
            value = read_json(receipt)
            if value.get("status") == "PASS_ENGINEERING_ONLY":
                value.update(status="FAIL", elapsed_seconds=time.monotonic() - started)
                value.setdefault("failures", []).append(str(exc))
                invalidate_success(output)
                receipt.rename(output / "ci-receipt-before-failure.json")
                write_json(receipt, value)
        raise


def invalidate_success(output: Path) -> None:
    """Revoke admissibility without discarding any already-created bytes."""
    archive = output / "ap-current-portable-bundle.tar.gz"
    if archive.exists():
        archive.rename(output / "ap-current-portable-failed-bundle.tar.gz")
    manifest = output / "bundle/bundle.json"
    if manifest.is_file():
        value = read_json(manifest)
        if value.get("status") == "PASS_ENGINEERING_ONLY":
            manifest.rename(manifest.with_name("bundle-manifest-before-failure.json"))
            value["status"] = "FAIL_BUNDLE_NOT_COMMITTED"
            write_json(manifest, value)


def run_impl(expected: str, output: Path, started: float, deadline: float) -> dict:
    output = output.absolute()
    require(not output.exists() and not output.is_symlink() and ROOT not in output.parents,
            "fresh CI output outside source required")
    output.mkdir(parents=True)
    result = {"schema_version": 1, "status": "FAIL", "code_revision": expected, "automatic_retries": 0,
              "acoustic_acceptance": False, "physical_target_measurement": False, "failures": []}
    bundle, build_dir = output / "bundle", output / "work/build"
    archive = output / "ap-current-portable-bundle.tar.gz"
    try:
        result["host"] = previous.assert_actions_host()
        require(previous.git("rev-parse", "HEAD").strip() == expected and hex_digest(expected, 40), "exact clean execution HEAD required")
        status_before = previous.git("status", "--porcelain", "--untracked-files=all")
        require(status_before == "", "source must be clean before build")
        actual_controls = controls(expected)
        configuration = plan()
        correlation_sources()
        source_pins = configuration["source"]["main_reference_files_sha256"]
        for name, digest in source_pins.items():
            data = (ROOT / name).read_bytes()
            require(sha256(data) == digest and data == git_bytes(expected, name) == git_bytes(MAIN_REFERENCE, name),
                    "source differs from main DSP pin: " + name)
        for directory in (bundle / "bin", bundle / "lib", bundle / "build", bundle / "licenses", build_dir.parent):
            directory.mkdir(parents=True)
        for name in dict(source_pins, **actual_controls):
            target = bundle / "source" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        (bundle / "licenses/audio-pipeline-LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
        tools = tool_records(bundle / "build/tools", deadline)
        command_records = {}
        directory = bundle / "build/configure"
        directory.mkdir()
        record = invoke(configure_command(build_dir, tools), directory, deadline, 90)
        record["files"] = file_map(directory)
        command_records["configure"] = record
        require(record["returncode"] == 0, "configure failed; preserve original logs")
        compile_started = time.monotonic()
        compile_deadline = min(deadline, compile_started + 240)
        with wall_guard(compile_deadline):
            for name, command, budget in (("compile", compile_command(build_dir, tools), 240),
                                          ("render-corr", render_corr_command(build_dir, tools), 30)):
                directory = bundle / "build" / name
                directory.mkdir()
                record = invoke(command, directory, compile_deadline, budget)
                record["files"] = file_map(directory)
                command_records[name] = record
                require(record["returncode"] == 0, name + " failed; preserve original logs")
        compile_elapsed = time.monotonic() - compile_started
        for key in ELF_KEYS:
            original = build_dir / PATHS[key].split("/")[-1]
            target = bundle / PATHS[key]
            require(original.is_file() and original.read_bytes()[:4] == b"\x7fELF", "compiled ELF missing")
            shutil.copyfile(original, target)
            target.chmod(0o755)
        paths = {key: bundle / name for key, name in PATHS.items()}
        for name in ("CMakeCache.txt", "compile_commands.json", "generated/audio_pipeline/audio_pipeline_build.h",
                     "libaudio_pipeline.a", "CMakeFiles/audio_pipeline.dir/flags.make",
                     "CMakeFiles/ap_process_pcm.dir/link.txt", "CMakeFiles/ap_build_info_dump.dir/link.txt"):
            original = build_dir / name
            require(original.is_file(), "build evidence missing: " + name)
            target = bundle / "build" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
        compiler_records = list((build_dir / "CMakeFiles").glob("*/CMakeCCompiler.cmake"))
        require(len(compiler_records) == 1, "ambiguous actual compiler record")
        (bundle / "build/CMakeCCompiler.cmake").write_bytes(compiler_records[0].read_bytes())
        before_runtime = runtime_identity(paths)
        elf_observations = {}
        for key in ELF_KEYS:
            directory = bundle / "build/elf" / key
            directory.mkdir(parents=True)
            observation = invoke([tools["readelf"]["path"], "-h", "-d", str(paths[key])], directory, deadline)
            observation["files"] = file_map(directory)
            require(observation["returncode"] == 0, "actual ELF inspection failed")
            validate_elf_observation((directory / "stdout.log").read_text())
            elf_observations[key] = observation
            for raw in before_runtime[key]["libraries"]:
                path = Path(raw)
                require(ROOT not in path.parents and output not in path.parents, "runtime depends on original source/build")
        build_dir.rename(build_dir.with_name("build-moved-before-engineering"))
        after_runtime = runtime_identity(paths)
        require(before_runtime == after_runtime, "relocation runtime identity changed")
        identity_dir = bundle / "build/identity"
        identity_dir.mkdir()
        record = invoke([str(paths["build_info"])], identity_dir, deadline)
        record["files"] = file_map(identity_dir)
        command_records["identity"] = record
        require(record["returncode"] == 0, "embedded identity query failed")
        info = build_info((identity_dir / "stdout.log").read_bytes(), expected)
        require(info["target_triple"] == tools["gcc"]["target_triple"], "embedded compiler target mismatch")
        notices = save_system_notices(after_runtime, bundle / "licenses/system", deadline)
        for row in tools.values():
            row["sha256_after"] = sha256(Path(row["path"]).read_bytes())
        status_after = previous.git("status", "--porcelain", "--untracked-files=all")
        require(status_after == status_before and controls(expected) == actual_controls, "source changed during build")
        built = {"schema_version": 1, "status": "BUILT_AP_CURRENT_PORTABLE", "source_revision": expected,
                 "source_tree": previous.git("rev-parse", "HEAD^{tree}").strip(), "main_dsp_reference": MAIN_REFERENCE,
                 "main_reference_files_sha256": source_pins, "controls": actual_controls,
                 "processor_sha256": sha256(paths["processor"].read_bytes()),
                 "build_info_sha256": sha256(paths["build_info"].read_bytes()), "build_info": info,
                 "render_correlation": {"source_pins": CORR_PINS, "abi": CORR_ABI, "flags": CORR_FLAGS,
                                        "library": PATHS["render_corr"], "binary_sha256": sha256(paths["render_corr"].read_bytes()),
                                        "compiler": tools["gcc"]["version"].splitlines()[0].strip()},
                 "compile_stage_elapsed_seconds": compile_elapsed,
                 "tools": tools, "commands": command_records, "cmake_options": configuration["build"]["cmake_options"],
                 "generator": "Unix Makefiles", "parallelism": 2, "runtime_identity": before_runtime,
                 "elf_observations": elf_observations,
                 "runtime_identity_after_relocation": after_runtime, "original_build_directory": str(build_dir),
                 "original_source_directory": str(ROOT),
                 "original_build_directory_renamed": True, "absolute_rpath_present": False,
                 "source_status_before": status_before, "source_status_after": status_after, "system_notices": notices}
        write_json(paths["build_receipt"], built)
        require(deadline - time.monotonic() >= 60, "insufficient remaining CI budget for fixed engineering")
        engineering(bundle, bundle / "engineering", initial=True)
        manifest = {"schema_version": 1, "kind": "AP_CURRENT_PORTABLE_V1", "status": "PASS_ENGINEERING_ONLY",
                    "code_revision": expected, "source_tree": built["source_tree"], "paths": PATHS,
                    "files": file_map(bundle)}
        write_json(bundle / "bundle.json", manifest)
        verify_bundle(bundle)
        digest = archive_readback(bundle, archive)
        verify_bundle(bundle)
        require(previous.git("status", "--porcelain", "--untracked-files=all") == ""
                and controls(expected) == actual_controls, "late source identity change")
        require(time.monotonic() < deadline, "CI wall budget exceeded")
        result.update(status="PASS_ENGINEERING_ONLY", elapsed_seconds=time.monotonic() - started,
                      source_tree=built["source_tree"], bundle_manifest_sha256=sha256((bundle / "bundle.json").read_bytes()),
                      archive_sha256=digest, archive_size_bytes=archive.stat().st_size)
        write_json(output / "ci-receipt.json", result)
        require(time.monotonic() < deadline, "final CI receipt exceeded wall budget")
        return result
    except Exception as exc:
        result["status"] = "FAIL"
        result["failures"].append(str(exc))
        result["elapsed_seconds"] = time.monotonic() - started
        invalidate_success(output)
        if (output / "ci-receipt.json").exists():
            (output / "ci-receipt.json").rename(output / "ci-receipt-before-failure.json")
        write_json(output / "ci-receipt.json", result)
        raise


def job_text() -> str:
    return """
  ap-current-portable:
    name: Current AP portable engineering (synthetic transport only)
    needs: scope
    if: needs.scope.outputs.ap == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 12
    env:
      EXECUTION_SHA: ${{ github.event.pull_request.head.sha || github.sha }}
      PYTHONDONTWRITEBYTECODE: '1'
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
        with:
          fetch-depth: 0
          persist-credentials: false
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
      - name: Preserve actual current source binaries and bounded engineering evidence
        shell: bash
        run: |
          set -euo pipefail
          timeout --signal=KILL 630s python3 -B \\
            tests/validation/frontend_evolution/ap_current_ci.py run \\
            --expected-head "$EXECUTION_SHA" --output "$RUNNER_TEMP/ap-current-portable"
      - name: Preserve the portable bundle or actual failed prefix
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: frontend-research-ap-current-portable-${{ github.run_id }}-attempt-${{ github.run_attempt }}
          path: |
            ${{ runner.temp }}/ap-current-portable/ap-current-portable*.tar.gz
            ${{ runner.temp }}/ap-current-portable/ci-receipt*.json
            ${{ runner.temp }}/ap-current-portable/bundle/
          include-hidden-files: true
          retention-days: 90
          if-no-files-found: error
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("run")
    create.add_argument("--expected-head", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    recheck = commands.add_parser("engineering")
    recheck.add_argument("--bundle", type=Path, required=True)
    recheck.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run(args.expected_head, args.output)
        elif args.command == "engineering":
            result = engineering(args.bundle, args.output)
        else:
            result = verify_bundle(args.bundle)["manifest"]
        print(json.dumps({"status": result["status"], "acoustic_acceptance": False}, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print("AP_CURRENT_PORTABLE_FAIL: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
