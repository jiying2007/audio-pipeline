#!/usr/bin/env python3
"""Exact 2.3.60 audit-source admission. Source/metadata only; never run DSP.

R1/R2/R3 plans, source locks, negative controls and results keep their identities.
This independent registration admits nine reviewed source changes, without
turning a historical scientific result into a result for the current source.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
GATE = REL + "fe09_b3_f0_r4_source_admission.py"
LEGACY_GATE = REL + "fe09_b3_f0_r2_source_admission.py"
LEGACY_GATE_BLOB = "6b9e9e5e3e044aa586420be3b3aadd229a90b67f"
DOCS = "docs/research/frontend-evolution-v1/FE09_B3_F0_IO_SOURCE_R4_20261029/"
PLAN = DOCS + "PREREGISTRATION.json"
PLAN_BLOB = "42cc99ed40be82dc16cb6003d5f0fa673b3d062c"
DELTA = REL + "fe09_b3_f0_r4_source_delta_2_3_60.patch.b64"
DELTA_BLOB = "a51bc4a45af47daca537a7efc527bcdf0cd16a36"
F0_LOCK = "docs/research/frontend-evolution-v1/FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/source-lock.json"
F0_LOCK_SHA256 = "16cd84381647bef1015fc8ef338bb9b10dd09ce4669248355ac4f48745d8a4ff"
F0_BASE = "5187c5e59526d4047b3965b44c770ab21edbde9f"
STATUS = "R4_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION"
SOURCE_PROFILES = {
    "2.3.60": {
        "CMakeLists.txt": "18697f24fb1cf896b114b3e4cd34ecc9a35ccd7d",
        "cmake/audio-pipeline-runtime.pc.in": "079ee9edf1fb9e13bfa0936355556b48ca408155",
        "cmake/audio-pipeline.pc.in": "29fbd3746b65e54c438e375815a44f076f3b255c",
        "include/audio_pipeline/audio_modules.h": "98f0dc8309d1be1f2b964bc165406fd555de3a7d",
        "include/audio_pipeline/audio_runtime.h": "ad72e40b5b343aee4589ee50dfd07fe1a85e0ea9",
        "src/modules/ap_beamformer_module.c": "c55cca0d5352b6d27066ea4a447ccaa583109411",
        "src/modules/ap_resampler_module.c": "3edc2730f7641ff7242e2666492c993e6b068439",
        "src/platform/linux/ap_runtime.c": "b6c36e195c1ac967e450a1e32506e0b6859a581b",
        "src/sync/ap_sync.c": "83b79caf78f03e9689416c8afbb1e04f444314e8",
    },
}
PATHS = frozenset(SOURCE_PROFILES["2.3.60"])


class Reject(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Reject(reason)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def identity(data: bytes) -> dict:
    return {"git_blob_sha1": git_blob(data), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def bounded(path: str) -> bytes:
    target = ROOT / path
    need(target.is_file() and not target.is_symlink() and
         0 < target.stat().st_size < 262144, "R4_MISSING_OR_UNBOUNDED_SOURCE:" + path)
    return target.read_bytes()


# Pin before importing or calling the old helpers. Its explicit 2.3.59
# rejection remains part of the original thirteen R2 negative controls.
need(git_blob(bounded(LEGACY_GATE)) == LEGACY_GATE_BLOB, "R4_ORIGINAL_R2_GATE_DRIFT")
import fe09_b3_f0_r2_source_admission as legacy  # noqa: E402


def registration(raw: bytes | None = None) -> dict:
    raw = bounded(PLAN) if raw is None else raw
    need(git_blob(raw) == PLAN_BLOB, "R4_PREREGISTRATION_BLOB_DRIFT")
    plan = legacy.sealed_json(raw)
    need(plan["identity"] == "FE09-B3-F0-IO-SOURCE-R4-PREREGISTRATION" and
         plan["status"] == "EXACT_2360_SOURCE_IDENTITY_PREREGISTERED_NO_EXECUTION" and
         plan["proposal_provenance"]["candidate_version"] == "2.3.60" and
         plan["proposal_provenance"]["head_is_proposal_provenance_not_required_ancestor"] is True,
         "R4_SOURCE_AUTHORITY_DRIFT")
    need(set(plan["reviewed_source"]) == PATHS and len(PATHS) == 9 and
         {path: row["after"]["git_blob_sha1"] for path, row in
          plan["reviewed_source"].items()} == SOURCE_PROFILES["2.3.60"],
         "R4_REVIEWED_SOURCE_SCOPE_DRIFT")
    need(plan["source_delta"]["path"] == DELTA and
         plan["source_delta"]["git_blob_sha1"] == DELTA_BLOB and
         plan["source_delta"]["members"] == 9 and
         plan["source_delta"]["reverse_must_recover_original_bytes"] is True,
         "R4_REGISTERED_DELTA_DRIFT")
    for path, expected in plan["legacy_source_pins"].items():
        need(git_blob(bounded(path)) == expected, "R4_LEGACY_SOURCE_CHANGED:" + path)
    old_plan, _ = legacy.load_contract()
    need(plan["scientific_contract"] == old_plan["experiment_contract"],
         "R4_FROZEN_SCIENTIFIC_CONTRACT_CHANGED")
    need(all(value is False for value in plan["promotion"].values()) and
         plan["execution_boundary"]["dsp_runs_performed_by_source_gate"] == 0 and
         plan["execution_boundary"]["r1_or_r2_result_inherited"] is False and
         plan["execution_boundary"]["r3_result_inherited"] is False and
         plan["execution_boundary"]["quality_thresholds_or_budgets_relaxed"] is False,
         "R4_NONPROMOTION_DRIFT")
    return plan


def historical_inputs(plan: dict) -> tuple[list[dict], list[dict], dict[str, bytes]]:
    _, lock = legacy.load_contract()
    rows = legacy.frozen_rows(lock)
    f0_raw = legacy.worktree_bytes(F0_LOCK)
    need(hashlib.sha256(f0_raw).hexdigest() == F0_LOCK_SHA256, "R4_F0_LOCK_DRIFT")
    f0 = legacy.sealed_json(f0_raw)
    f0_rows = f0["files"]
    need(f0["baseline"] == F0_BASE and f0["file_count"] == len(f0_rows) == 88,
         "R4_F0_MEMBER_COUNT_OR_BASE_DRIFT")
    by_path = {row["path"]: row for row in rows}
    f0_by_path = {row["path"]: row for row in f0_rows}
    live = {row["path"] for row in rows if row["role"] in legacy.EXECUTABLE_ROLES}
    need(len(f0_by_path) == 88 and len(live) == 66 and
         set(by_path) & set(f0_by_path) == live and
         len(set(f0_by_path) - set(by_path)) == 22 and PATHS <= live,
         "R4_SHARED_AND_F0_ONLY_MEMBER_SCOPE_DRIFT")
    frozen = {row["path"]: legacy.original_frozen_bytes(row) for row in rows}
    for row in f0_rows:
        data = legacy.committed_bytes(row["path"], F0_BASE)
        legacy.verify_member(data, row, row["git_blob_sha1"])
        if row["path"] in frozen:
            need(frozen[row["path"]] == data, "R4_B3_F0_SHARED_PREIMAGE_DRIFT:" + row["path"])
        frozen[row["path"]] = data
    for path in PATHS:
        need(identity(frozen[path]) == plan["reviewed_source"][path]["before"] and
             all(by_path[path][key] == f0_by_path[path][key] for key in
                 ("git_blob_sha1", "bytes", "sha256")),
             "R4_REVIEWED_BEFORE_IDENTITY_DRIFT:" + path)
    # Both old forward profiles, their exact packaging transformation and
    # original compiler/scientific source boundaries remain independently read.
    baseline = {path: frozen[path] for path in legacy.ORIGINAL_BUILD}
    for version in legacy.SOURCE_PROFILES:
        legacy.replay_registered_patch(version, baseline)
    legacy.verify_pkgconfig_deltas(baseline)
    legacy.verify_compiler_source_boundaries()
    return rows, f0_rows, frozen


def decode_delta(encoded: bytes, plan: dict) -> bytes:
    need(encoded.endswith(b"\n") and encoded.count(b"\n") == 1,
         "R4_DELTA_ENCODING_INVALID")
    try:
        delta = base64.b64decode(encoded[:-1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise Reject("R4_DELTA_ENCODING_INVALID") from exc
    need(identity(delta) == {key: plan["source_delta"][key]
                            for key in ("git_blob_sha1", "bytes", "sha256")},
         "R4_DELTA_IDENTITY_DRIFT")
    return delta


def delta_scope(delta: bytes, directory: Path) -> None:
    result = subprocess.run(["git", "apply", "--numstat", "-"], input=delta,
                            cwd=directory, capture_output=True, timeout=30, check=False)
    need(result.returncode == 0, "R4_DELTA_INVENTORY_INVALID")
    paths = [line.split("\t")[-1] for line in result.stdout.decode().splitlines()]
    need(len(paths) == 9 and set(paths) == PATHS, "R4_DELTA_SCOPE_DRIFT")


def prove_delta(plan: dict, frozen: dict[str, bytes]) -> dict[str, bytes]:
    delta = decode_delta(bounded(DELTA), plan)
    with tempfile.TemporaryDirectory(prefix="fe09-r4-source-proof-") as tmp:
        directory = Path(tmp)
        delta_scope(delta, directory)
        for path in PATHS:
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(frozen[path])
        for options in (("--check",), ()):
            legacy.git("apply", *options, "--unidiff-zero", "-", input_bytes=delta, cwd=directory)
        forward = {path: (directory / path).read_bytes() for path in PATHS}
        for path, data in forward.items():
            need(identity(data) == plan["reviewed_source"][path]["after"],
                 "R4_DELTA_AFTER_IDENTITY_DRIFT:" + path)
        for options in (("--reverse", "--check"), ("--reverse",)):
            legacy.git("apply", *options, "--unidiff-zero", "-", input_bytes=delta, cwd=directory)
        for path in PATHS:
            need((directory / path).read_bytes() == frozen[path],
                 "R4_DELTA_NOT_BYTE_REVERSIBLE:" + path)
    return forward


def verify_current(rows: list[dict], f0_rows: list[dict], read_current, plan: dict) -> None:
    count, exceptions = legacy.check_source_set(rows, read_current, SOURCE_PROFILES["2.3.60"])
    need((count, exceptions) == (66, 9), "R4_CURRENT_SOURCE_COVERAGE")
    for path in PATHS:
        need(identity(read_current(path)) == plan["reviewed_source"][path]["after"],
             "R4_CURRENT_AFTER_IDENTITY_DRIFT:" + path)
    # The shared 66 do not make the B3 77 a subset of F0's 88. All 22
    # additional F0 members remain exact, with no extra source exception.
    for row in f0_rows:
        expected = (plan["reviewed_source"][row["path"]]["after"] if row["path"] in PATHS
                    else {key: row[key] for key in ("git_blob_sha1", "bytes", "sha256")})
        need(identity(read_current(row["path"])) == expected,
             "R4_F0_CURRENT_SOURCE_DRIFT:" + row["path"])


def version_from_cmake(data: bytes) -> str:
    match = re.search(rb"(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$", data)
    need(match is not None and match.group(1) == b"2.3.60", "R4_VERSION_NOT_REGISTERED")
    return "2.3.60"


def execution_identity(requested: str | None, actual: str, clean: bool) -> None:
    need(re.fullmatch(r"[0-9a-f]{40}", actual) is not None and
         (requested is None or requested == actual), "R4_CURRENT_CHECKOUT_IDENTITY_MISMATCH")
    need(clean, "R4_TRACKED_WORKTREE_NOT_CLEAN")


def source_check(execution_source: str | None = None) -> dict:
    revision = legacy.git("rev-parse", "HEAD").decode().strip()
    execution_identity(execution_source, revision,
                       not legacy.git("status", "--porcelain", "--untracked-files=no").strip())
    version = version_from_cmake(legacy.committed_bytes("CMakeLists.txt"))
    plan = registration()
    for path in (GATE, PLAN, DELTA, DOCS + "README.md", *plan["legacy_source_pins"], F0_LOCK):
        legacy.committed_bytes(path)
    rows, f0_rows, frozen = historical_inputs(plan)
    reviewed = prove_delta(plan, frozen)
    for path in PATHS:
        need(legacy.committed_bytes(path) == reviewed[path],
             "R4_CURRENT_BYTES_DIFFER_FROM_REVIEWED_DELTA:" + path)
    verify_current(rows, f0_rows, legacy.committed_bytes, plan)
    return {"schema_version": 1, "status": STATUS, "execution_source": revision,
            "execution_tree": legacy.git("rev-parse", "HEAD^{tree}").decode().strip(),
            "candidate_version": version, "immutable_source_members": 77,
            "source_gated_members": 66, "source_gated_exceptions": 9,
            "source_gated_baseline_members": 57, "historical_reference_members": 11,
            "f0_lock_members": 88, "f0_shared_live_members": 66,
            "f0_additional_members": 22, "f0_additional_member_exceptions": 0,
            "f0_unchanged_current_members": 79, "original_r1_lock_sha256": legacy.LOCK_SHA256,
            "original_f0_lock_sha256": F0_LOCK_SHA256, "r4_preregistration_blob": PLAN_BLOB,
            "source_delta_blob": DELTA_BLOB, "source_delta_members_verified": 9,
            "legacy_forward_profiles_verified": 2,
            "reviewed_source_blobs": SOURCE_PROFILES[version],
            "original_r2_source_gate_blob": LEGACY_GATE_BLOB,
            "science_executed": False, "r1_or_r2_result_inherited": False,
            "r3_result_inherited": False,
            "shipping_authority": False, "ssc305_hil_qualified": False,
            "four_mic_public_sdk": False}


def source_check_current(execution_source: str | None = None) -> dict:
    registration()  # Bind the immutable R3 delegate before importing it.
    data = legacy.committed_bytes("CMakeLists.txt")
    match = re.search(rb"(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$", data)
    need(match is not None, "R4_CMAKE_VERSION_UNRECOGNIZED")
    if match.group(1) in (b"2.3.56", b"2.3.57", b"2.3.58"):
        # Preserve the original receipt and namespace without translating it.
        return legacy.source_check(execution_source)
    if match.group(1) == b"2.3.59":
        import fe09_b3_f0_r3_source_admission as previous
        return previous.source_check(execution_source)
    return source_check(execution_source)


def self_test() -> dict:
    plan = registration()
    original = legacy.self_test()
    need(original["rejected"] == 13 and original["dsp_executed"] is False,
         "R4_ORIGINAL_R2_NEGATIVES_CHANGED")
    import fe09_b3_f0_r3_source_admission as previous
    prior = previous.self_test()
    need(prior["new_source_negatives"] == 27 and prior["science_executed"] is False,
         "R4_ORIGINAL_R3_NEGATIVES_CHANGED")
    rows, f0_rows, frozen = historical_inputs(plan)
    forward = prove_delta(plan, frozen)
    candidate = {**frozen, **forward}
    verify_current(rows, f0_rows, candidate.__getitem__, plan)
    version_from_cmake(candidate["CMakeLists.txt"])
    rejected = 0

    def reject(action, reason: str | None = None) -> None:
        nonlocal rejected
        try:
            action()
        except (Reject, legacy.Reject) as error:
            need(reason is None or str(error) == reason, "R4_WRONG_NEGATIVE_REASON:" + str(error))
            rejected += 1
        else:
            raise Reject("R4_SOURCE_NEGATIVE_FALSE_ACCEPT")

    for path in sorted(PATHS):
        changed = {**candidate, path: candidate[path] + b"\n"}
        reject(lambda values=changed: verify_current(rows, f0_rows, values.__getitem__, plan),
               "LOCKED_EXECUTABLE_SOURCE_CHANGED:" + path)
    public = "src/core/ap_pipeline.c"
    private = next(row["path"] for row in rows if row["role"] == "unchanged_private_compiled_dependency")
    f0_only = "tests/validation/frontend_evolution/fe09_b3_f0_build/CMakeLists.txt"
    need(public not in PATHS and private not in PATHS and f0_only not in {r["path"] for r in rows},
         "R4_UNCHANGED_MEMBER_NEGATIVE_FIXTURE_DRIFT")
    for path in (public, private, f0_only):
        changed = {**candidate, path: candidate[path] + b"\n"}
        reject(lambda values=changed: verify_current(rows, f0_rows, values.__getitem__, plan))
    for version in ("2.3.59", "2.3.61", "3.0.0", "2.3.60-rc"):
        reject(lambda value=version: version_from_cmake(
            ("project(audio_pipeline VERSION " + value + " LANGUAGES C)\n").encode()),
            "R4_VERSION_NOT_REGISTERED")
    reject(lambda: execution_identity("2" * 40, "1" * 40, True),
           "R4_CURRENT_CHECKOUT_IDENTITY_MISMATCH")
    reject(lambda: execution_identity(None, "not-a-sha", True),
           "R4_CURRENT_CHECKOUT_IDENTITY_MISMATCH")
    reject(lambda: execution_identity(None, "1" * 40, False), "R4_TRACKED_WORKTREE_NOT_CLEAN")
    encoded = bounded(DELTA)
    delta = decode_delta(encoded, plan)
    reject(lambda: decode_delta(encoded + b"\n", plan), "R4_DELTA_ENCODING_INVALID")
    reject(lambda: decode_delta(b"!" + encoded[1:], plan), "R4_DELTA_ENCODING_INVALID")
    reject(lambda: decode_delta(base64.b64encode(delta + b"\n") + b"\n", plan),
           "R4_DELTA_IDENTITY_DRIFT")
    with tempfile.TemporaryDirectory(prefix="fe09-r4-negative-scope-") as tmp:
        directory = Path(tmp)
        wrong = delta.replace(b"src/sync/ap_sync.c", b"src/sync/unregistered.c")
        blocks = delta.split(b"diff --git ")[1:]
        missing = b"".join(b"diff --git " + block for block in blocks
                           if not block.startswith(b"a/src/sync/ap_sync.c "))
        for changed in (wrong, missing, delta + delta):
            reject(lambda value=changed: delta_scope(value, directory), "R4_DELTA_SCOPE_DRIFT")
        reject(lambda: delta_scope(b"invalid patch\n", directory), "R4_DELTA_INVENTORY_INVALID")
    reject(lambda: registration(bounded(PLAN) + b" "), "R4_PREREGISTRATION_BLOB_DRIFT")
    need(rejected == plan["source_only_controls"]["new_negative_cases"] == 27,
         "R4_SOURCE_NEGATIVE_MATRIX_INCOMPLETE")
    return {"status": "R4_T1_SOURCE_ONLY_SELF_TEST_PASS", "new_source_negatives": rejected,
            "preserved_r2_negatives": 13, "preserved_r3_negatives": 27,
            "reviewed_source_members": 9,
            "b3_members": 77, "shared_live_members": 66, "f0_members": 88,
            "f0_additional_members": 22, "science_executed": False,
            "shipping_authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--check", action="store_true", help="Require the exact R4 2.3.60 source")
    checks.add_argument("--check-current", action="store_true", help="Keep old versions on their unchanged R2/R3 admission")
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    if not (args.self_test or args.check or args.check_current):
        parser.error("select --self-test, --check or --check-current")
    try:
        if args.self_test:
            print(json.dumps(self_test(), sort_keys=True))
        if args.check or args.check_current:
            check = source_check_current if args.check_current else source_check
            print(json.dumps(check(args.execution_source), sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        print("R4_T1_SOURCE_REJECTED:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
