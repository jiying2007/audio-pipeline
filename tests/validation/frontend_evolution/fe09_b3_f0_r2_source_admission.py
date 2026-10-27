#!/usr/bin/env python3
"""Independent FE09 B3/F0 forward-source R2 identity gate. NO DSP execution.

Only the previously protected, exact source profiles are accepted. This gate
does not change the immutable R1 collector or qualify any R2 B3/F0 results.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PLAN = Path("docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/PREREGISTRATION.json")
LOCK = Path("docs/research/frontend-evolution-v1/FE09_B3_F0_PREREGISTRATION_20261024/source-lock.json")
FROZEN = Path("docs/research/frontend-evolution-v1/FE09_B3_F0_PREREGISTRATION_20261024")
PLAN_BLOB = "7ed23487462d0a011a06255d1886eccfec385a63"
LOCK_SHA256 = "32bd625ee640bf60310bcdc9980a5f8a41711300aee66f029fbf65c98a9bb49d"
FREEZE_BASE = "81ee559848e1e30e3dd2eb4d03b0b479b9bd971e"
ORIGINAL_GATE_ROLES = {"unchanged_public_build_snapshot_superset": 56,
                       "unchanged_private_compiled_dependency": 10,
                       "authority_or_reference_snapshot_not_executed": 11}
EXECUTABLE_ROLES = set(ORIGINAL_GATE_ROLES) - {"authority_or_reference_snapshot_not_executed"}
CMAKE = "CMakeLists.txt"
RUNTIME = "src/platform/linux/ap_runtime.c"
PC_CORE = "cmake/audio-pipeline.pc.in"
PC_RUNTIME = "cmake/audio-pipeline-runtime.pc.in"
ORIGINAL_BUILD = {
    CMAKE: "3659b13659baaac99fd6e7e56fcb45cba243955c",
    RUNTIME: "7124a9c04d46f4d907c3d9831b3d4aa35ab8414e",
    PC_CORE: "b59e0a0d22c2ace435a0d9a87495e22afefac0e7",
    PC_RUNTIME: "802d2bcb7e81418072fbd510f4889fdcc051915e",
}
SOURCE_PROFILES = {
    "2.3.57": {
        CMAKE: "1d1e7f7bbf29d8e95b61fc135a0c93de3193256a",
        RUNTIME: "519cf2732289af74c0285d3bbff4cae556bc7d07",
    },
    "2.3.58": {
        CMAKE: "231cf6085b2b6f7a962433327075d629e16b330e",
        RUNTIME: "519cf2732289af74c0285d3bbff4cae556bc7d07",
        PC_CORE: "50ced32c570a23a6fe1f2d3af4284d4a27f04096",
        PC_RUNTIME: "b06489e6c60654eee0ad05874fe582b1ea411d50",
    },
}
PATCH_BLOBS = {
    "2.3.57": "7e5fe35b78ff44950c0941c8bec34f71ce5b1e15",
    "2.3.58": "dade779a6293c7c9bd72e48611710abe3d2d8f0c",
}
# Original unmodified source/library experiment boundaries.
SOURCE_CONTROLS = {
    "tests/validation/frontend_evolution/fe09_b3_f0_qualification.py":
        "f6be51a0831ab96ef1284d706a6f1d167b538b51",
    "tests/validation/frontend_evolution/fe09_b3_f0_deadline_r1_qualification.py":
        "54dab4274df8044dbbd23bf05ef169bd21123c74",
    "tests/validation/frontend_evolution/fe09_t3s3_f0_call_resource_qualification.py":
        "e22cc4f0eede6e844b985e0bece8e9dcbf2e02cd",
    "tests/validation/frontend_evolution/fe09_b3_f0_build/CMakeLists.txt":
        "07f67abbb802010b05ccf634d5c358fee31dc526",
}
IMMUTABLE_INPUT_DIGESTS = {
    "test-contract.json": "74e7294b1433207d222f9732326b68b33303c1ef63c8b6001283963419117284",
    "input-fixture-lock.independent.json": "9e8cdd3c2889cd071ccfa92e8358de9f15fa371f1e4fc136e6be566ab0765d27",
    "source-lock-gate-selection.json": "cca7a798ad09f2b272d73409067cbecc57f6225d90890e492066a1e077dd1dca",
}

class Reject(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Reject(reason)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git(*args: str, input_bytes: bytes | None = None, cwd: Path = ROOT) -> bytes:
    command = ["git", "-c", "safe.directory=" + str(ROOT), *args]
    done = subprocess.run(command, cwd=cwd, input=input_bytes, capture_output=True,
                          timeout=30, check=False)
    need(done.returncode == 0, "GIT_OBJECT_OR_PATCH_READ_FAILED:" + " ".join(args[:2]))
    return done.stdout


def safe_path(path: str) -> Path:
    value = PurePosixPath(path)
    need(bool(value.parts) and bool(path) and not value.is_absolute() and ".." not in value.parts and
         "\\" not in path and path == value.as_posix() and
         all(part not in (".", "") for part in value.parts), "SOURCE_PATH_INVALID")
    return ROOT / path


def worktree_bytes(name: str) -> bytes:
    path = safe_path(name)
    need(path.is_file() and not path.is_symlink(), "MISSING_OR_SYMLINK_SOURCE:" + name)
    return path.read_bytes()


def committed_bytes(name: str, ref: str = "HEAD") -> bytes:
    safe_path(name)
    actual = git("show", ref + ":" + name)
    if ref == "HEAD":
        need(actual == worktree_bytes(name), "UNCOMMITTED_SOURCE:" + name)
    return actual


def unique_object(items):
    result = {}
    for key, value in items:
        need(key not in result, "DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def sealed_json(payload: bytes) -> dict:
    item = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda c: (_ for _ in ()).throw(Reject("NONFINITE_JSON")))
    need(type(item) is dict, "JSON_ROOT_OBJECT_REQUIRED")
    return item


def load_contract() -> tuple[dict, dict]:
    plan_bytes = worktree_bytes(PLAN.as_posix())
    need(git_blob(plan_bytes) == PLAN_BLOB, "R2_PREREGISTRATION_BLOB_CHANGED")
    plan = sealed_json(plan_bytes)
    lock_bytes = worktree_bytes(LOCK.as_posix())
    need(sha256(lock_bytes) == LOCK_SHA256, "R1_SOURCE_LOCK_CHANGED")
    lock = sealed_json(lock_bytes)
    need(plan["identity"] == "FE09-B3-F0-FORWARD-SOURCE-R2-PREREGISTRATION" and
         plan["status"] == "SOURCE_IDENTITY_PREREGISTERED_NOT_EXECUTED" and
         plan["frozen_predecessor"]["source_lock_sha256"] == LOCK_SHA256 and
         plan["frozen_predecessor"]["baseline_commit"] == FREEZE_BASE and
         plan["frozen_predecessor"]["locked_member_count"] == 77 and
         plan["frozen_predecessor"]["executable_member_count"] == 66,
         "R2_PREREGISTERED_ANCESTRY_DRIFT")
    need(plan.get("new_b3_execution_performed") is False and
         plan.get("new_f0_execution_performed") is False and
         plan.get("quality_thresholds_relaxed") is False and
         plan.get("source_lock_rewritten") is False and
         all(value is False for value in plan["promotion"].values()),
         "R2_NONPROMOTION_DRIFT")
    need(plan["frozen_predecessor"]["original_current_build_blobs"] == ORIGINAL_BUILD,
         "R2_HISTORICAL_BUILD_BLOBS_CHANGED")
    profiles = plan["reviewed_profiles"]
    need(set(profiles) == set(SOURCE_PROFILES), "R2_PROFILE_SET_DRIFT")
    for version, wanted in SOURCE_PROFILES.items():
        item = profiles[version]
        need(item["cmake_git_blob"] == wanted[CMAKE] and
             item["runtime_git_blob"] == wanted[RUNTIME] and
             item["forward_patch_git_blob"] == PATCH_BLOBS[version] and
             item["candidate_pr"] == (850 if version == "2.3.57" else 851) and
             item["candidate_promoted"] is False and
             item["additional_locked_member_git_blobs"] ==
             {k: v for k, v in wanted.items() if k in (PC_CORE, PC_RUNTIME)},
             "R2_PROTECTED_PROFILE_IDENTITY_DRIFT:" + version)
    return plan, lock


def frozen_rows(lock: dict) -> list[dict]:
    need(lock["baseline_commit"] == FREEZE_BASE and
         lock["file_count"] == 77 and
         lock["git_tree_sha1"] == "c9054175dccee024ecf2a87a8323d96699c38249",
         "R1_LOCK_BASE_OR_TREE_DRIFT")
    rows = lock["files"]
    need(type(rows) is list and len(rows) == 77 and
         Counter(row["role"] for row in rows) == ORIGINAL_GATE_ROLES,
         "R1_LOCK_ROLE_COVERAGE")
    names = [row["path"] for row in rows]
    need(len(set(names)) == len(names), "R1_LOCK_DUPLICATE_SOURCE")
    for row in rows:
        safe_path(row["path"])
        need(bool(re.fullmatch(r"[0-9a-f]{40}", row["git_blob_sha1"])),
             "R1_LOCK_MALFORMED_GIT_BLOB")
        need(type(row["bytes"]) is int and row["bytes"] > 0 and
             bool(re.fullmatch(r"[0-9a-f]{64}", row["sha256"])),
             "R1_LOCK_MALFORMED_FILE")
    return rows


def verify_member(data: bytes, entry: dict, expected_blob: str) -> None:
    need(git_blob(data) == expected_blob, "LOCKED_EXECUTABLE_SOURCE_CHANGED:" + entry["path"])
    if expected_blob == entry["git_blob_sha1"]:
        need((len(data), sha256(data)) == (entry["bytes"], entry["sha256"]),
             "R1_SOURCE_BYTE_OR_SHA_DRIFT:" + entry["path"])


def check_source_set(rows: list[dict], read_current, exceptions: dict[str, str]) -> tuple[int, int]:
    frozen = {entry["path"]: entry for entry in rows}
    need(set(exceptions).issubset(frozen) and
         all(frozen[name]["role"] in EXECUTABLE_ROLES for name in exceptions),
         "R2_UNREGISTERED_SOURCE_EXCEPTION")
    checked = 0
    for entry in rows:
        if entry["role"] not in EXECUTABLE_ROLES:
            continue
        data = read_current(entry["path"])
        verify_member(data, entry, exceptions.get(entry["path"], entry["git_blob_sha1"]))
        checked += 1
    need(checked == 66, "R2_LOCKED_SOURCE_COVERAGE_INCOMPLETE")
    return checked, len(exceptions)


def version_from_cmake(data: bytes) -> str:
    found = re.search(rb"(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$", data)
    need(found is not None, "R2_CMAKE_VERSION_UNRECOGNIZED")
    version = found.group(1).decode()
    need(version in ("2.3.56", *SOURCE_PROFILES), "R2_VERSION_NOT_REGISTERED")
    return version


def original_frozen_bytes(entry: dict) -> bytes:
    data = committed_bytes(entry["path"], FREEZE_BASE)
    verify_member(data, entry, entry["git_blob_sha1"])
    return data


def verified_patch(version: str) -> bytes:
    encoded = worktree_bytes("tests/validation/frontend_evolution/fe09_maintenance_forward_" +
                             version.replace(".", "_") + ".patch.b64")
    need(encoded.endswith(b"\n") and encoded.count(b"\n") == 1,
         "R2_REGISTERED_PATCH_ENCODING")
    try:
        raw = base64.b64decode(encoded[:-1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise Reject("R2_REGISTERED_PATCH_BASE64_INVALID") from exc
    need(git_blob(raw) == PATCH_BLOBS[version], "R2_REGISTERED_PATCH_BLOB_DRIFT")
    return raw


def replay_registered_patch(version: str, frozen: dict[str, bytes]) -> None:
    with tempfile.TemporaryDirectory(prefix="fe09-r2-source-patch-") as tmp:
        directory = Path(tmp)
        for path in (CMAKE, RUNTIME):
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(frozen[path])
        patch = verified_patch(version)
        # Construct forward bytes from original preimage, then prove exact
        # reversibility. No binaries, DSP frames or executed experiment.
        for args in (("apply", "--check", "--unidiff-zero", "-"),
                     ("apply", "--unidiff-zero", "-")):
            git(*args, input_bytes=patch, cwd=directory)
        for path in (CMAKE, RUNTIME):
            need(git_blob((directory / path).read_bytes()) == SOURCE_PROFILES[version][path],
                 "R2_FORWARD_PATCH_NOT_EXACT:" + path)
        for args in (("apply", "--reverse", "--check", "--unidiff-zero", "-"),
                     ("apply", "--reverse", "--unidiff-zero", "-")):
            git(*args, input_bytes=patch, cwd=directory)
        for path in (CMAKE, RUNTIME):
            need((directory / path).read_bytes() == frozen[path],
                 "R2_FORWARD_PATCH_NOT_REVERSIBLE:" + path)


def verify_pkgconfig_deltas(frozen: dict[str, bytes]) -> None:
    old = b"prefix=${pcfiledir}/../.."
    new = b"prefix=${pcfiledir}/@AP_PC_PREFIX_REL@"
    for path in (PC_CORE, PC_RUNTIME):
        data = frozen[path]
        need(data.count(old) == 1, "R2_PKGCONFIG_ORIGINAL_TEMPLATE_DRIFT:" + path)
        replacement = data.replace(old, new)
        need(git_blob(replacement) == SOURCE_PROFILES["2.3.58"][path],
             "R2_PKGCONFIG_CHANGED_BEYOND_PREFIX:" + path)


def verify_compiler_source_boundaries() -> None:
    for path, expected in SOURCE_CONTROLS.items():
        need(git_blob(committed_bytes(path)) == expected,
             "R2_ORIGINAL_EXPERIMENT_OR_PRIVATE_CMAKE_CHANGED:" + path)
    for path, expected in IMMUTABLE_INPUT_DIGESTS.items():
        need(sha256(committed_bytes((FROZEN / path).as_posix())) == expected,
             "R2_INPUT_OR_TEST_OR_SELECTION_CONTRACT_CHANGED:" + path)
    build = committed_bytes("tests/validation/frontend_evolution/fe09_b3_f0_build/CMakeLists.txt")
    need(all(token in build for token in (
        b'add_subdirectory("${AP_REPO_ROOT}"',
        b'set(AP_ENABLE_LINUX_RUNTIME OFF',
        b'set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)',
        b'set_target_properties(audio_pipeline PROPERTIES UNITY_BUILD OFF')),
         "R2_PRIVATE_ACTUAL_LIBRARY_BUILD_LINKAGE_DRIFT")


def source_check(execution_source: str | None = None) -> dict:
    revision = git("rev-parse", "HEAD").decode().strip()
    need(re.fullmatch(r"[0-9a-f]{40}", revision) is not None and
         (execution_source is None or execution_source == revision),
         "R2_CURRENT_CHECKOUT_IDENTITY_MISMATCH")
    # This is an exact committed-source qualification, not an untracked-build
    # cleanup or a replacement for target resource/acoustic measurements.
    need(not git("status", "--porcelain", "--untracked-files=no").strip(),
         "R2_TRACKED_WORKTREE_NOT_CLEAN")
    plan, lock = load_contract()
    need(committed_bytes(PLAN.as_posix()) == worktree_bytes(PLAN.as_posix()) and
         committed_bytes(LOCK.as_posix()) == worktree_bytes(LOCK.as_posix()),
         "R2_PLAN_OR_R1_LOCK_NOT_COMMITTED")
    rows = frozen_rows(lock)
    locked = {row["path"]: row for row in rows}
    need(all(name in locked for name in ORIGINAL_BUILD), "R2_BUILD_MEMBERS_MISSING")
    baseline = {}
    for row in rows:
        # The 11 reference-only entries are still verified against their
        # historical snapshot, but not misrepresented as live DSP inputs.
        source = original_frozen_bytes(row)
        if row["path"] in ORIGINAL_BUILD:
            baseline[row["path"]] = source
    need(set(baseline) == set(ORIGINAL_BUILD) and
         all(git_blob(baseline[path]) == blob for path, blob in ORIGINAL_BUILD.items()),
         "R2_FROZEN_PUBLIC_BUILD_PREIMAGE_DRIFT")
    version = version_from_cmake(committed_bytes(CMAKE))
    exceptions = SOURCE_PROFILES.get(version, {})
    checked, exception_count = check_source_set(rows, lambda name: committed_bytes(name), exceptions)
    for versioned in SOURCE_PROFILES:
        replay_registered_patch(versioned, baseline)
    verify_pkgconfig_deltas(baseline)
    verify_compiler_source_boundaries()
    return {"schema_version": 1,
            "status": ("R2_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION"
                       if version != "2.3.56" else
                       "R2_T1_FROZEN_PREDECESSOR_VERIFIED_NOT_AN_R2_RESULT"),
            "execution_source": revision, "candidate_version": version,
            "original_r1_lock_sha256": LOCK_SHA256,
            "immutable_source_members": 77,
            "source_gated_members": checked, "source_gated_exceptions": exception_count,
            "source_gated_baseline_members": checked - exception_count,
            "r2_preregistration_blob": PLAN_BLOB,
            "forward_patch_preimages_verified": 2,
            "two_pkgconfig_templates_reviewed": True,
            "science_executed": False, "shipping_authority": False,
            "ssc305_hil_qualified": False, "four_mic_public_sdk": False}


def self_test() -> dict:
    # Construct independent miniature tamper controls; do not consume R1 or
    # R2 execution archives and do not fork any DSP process.
    entry = {"path": "source.c", "role": "unchanged_private_compiled_dependency",
             "bytes": 4, "git_blob_sha1": git_blob(b"abc\n"),
             "sha256": sha256(b"abc\n")}
    count = 0
    verify_member(b"abc\n", entry, entry["git_blob_sha1"])
    for bytes_value, expected in ((b"abd\n", entry["git_blob_sha1"]),
                                  (b"abc", entry["git_blob_sha1"]),
                                  (b"abc\n", git_blob(b"abd\n"))):
        try:
            verify_member(bytes_value, entry, expected)
        except Reject:
            count += 1
        else:
            raise Reject("R2_NEGATIVE_ACCEPTED_MUTATED_SOURCE")
    for invalid in ("3.0.0", "2.3.59", "2.3.56-rc"):
        try:
            version_from_cmake(("project(audio_pipeline VERSION " + invalid +
                                " LANGUAGES C)\n").encode())
        except Reject:
            count += 1
        else:
            raise Reject("R2_NEGATIVE_ACCEPTED_UNREGISTERED_VERSION")
    for path in ("../secrets", "/tmp/source", "sub\\name", "x/../y", "."):
        try:
            safe_path(path)
        except Reject:
            count += 1
        else:
            raise Reject("R2_NEGATIVE_ACCEPTED_UNSAFE_PATH")
    try:
        sealed_json(b'{"status":1,"status":2}')
    except Reject:
        count += 1
    else:
        raise Reject("R2_NEGATIVE_ACCEPTED_DUPLICATE_JSON")
    try:
        sealed_json(b'{"x":NaN}')
    except Reject:
        count += 1
    else:
        raise Reject("R2_NEGATIVE_ACCEPTED_NONFINITE_JSON")
    need(count == 13, "R2_SOURCE_NEGATIVE_MATRIX_INCOMPLETE")
    return {"status": "R2_T1_OFFLINE_SOURCE_NEGATIVES_PASS",
            "rejected": count, "dsp_executed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    if not args.self_test and not args.check:
        parser.error("select --self-test or --check")
    try:
        if args.self_test:
            print(json.dumps(self_test(), sort_keys=True))
        if args.check:
            print(json.dumps(source_check(args.execution_source), sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        print("R2_T1_SOURCE_REJECTED:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
