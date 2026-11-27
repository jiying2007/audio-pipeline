#!/usr/bin/env python3
"""Exact validation-maintenance 2.3.66 source admission; no DSP or inherited result."""
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
DOCS = "docs/research/frontend-evolution-v1/VALIDATION_2366_SOURCE_R11_20261128/"
SELF = REL + "fe09_b3_f0_r11_source_admission.py"
PREVIOUS = 'tests/validation/frontend_evolution/fe09_b3_f0_r10_source_admission.py'
PREVIOUS_BLOB = 'a00b115bbfe2039c4fd90bf441d3d90cc6c87004'
PLAN = DOCS + "PREREGISTRATION.json"
PLAN_BLOB = '112fc291bf476b59a9e746498d55f05ce85ff022'
DELTA = 'tests/validation/frontend_evolution/fe09_b3_f0_r11_source_delta_2_3_66.patch.b64'
STATUS = "R11_T1_EXACT_SOURCE_IDENTITY_VERIFIED_NO_DSP_EXECUTION"
VERSION = '2.3.66'
# Filled once from the committed implementation proposal, before source review.
SOURCE_PROFILES = {'2.3.66': {'CMakeLists.txt': '692a93ce37da7daf8548190467eb69dca2769105', 'cmake/audio-pipeline-runtime.pc.in': '079ee9edf1fb9e13bfa0936355556b48ca408155', 'cmake/audio-pipeline.pc.in': '29fbd3746b65e54c438e375815a44f076f3b255c', 'include/audio_pipeline/audio_modules.h': '62ed567bae76258b51a72794bc036bda13c0b826', 'include/audio_pipeline/audio_runtime.h': 'ad72e40b5b343aee4589ee50dfd07fe1a85e0ea9', 'src/core/ap_pipeline.c': '9bbd0fd15fcec7b9624f5bc69b550db91e789167', 'src/frontend/ap_beamformer.c': 'cb9f5c3a0f8d2c910eff62e9599f866b444de3c3', 'src/frontend/ap_frontend.h': '0026d060ed79b1501314a95a94e7b02480a6adf2', 'src/modules/ap_beamformer_module.c': 'c55cca0d5352b6d27066ea4a447ccaa583109411', 'src/modules/ap_resampler_module.c': '3edc2730f7641ff7242e2666492c993e6b068439', 'src/platform/linux/ap_runtime.c': 'c8e4edfd0ac398b7830ba4d849e2c756a87c61f2', 'src/sync/ap_sync.c': '417fdb1e996d2c8ad64af0548dd57e73c37567c0', 'src/sync/ap_sync.h': '4ca32de066b10c510ffb81d5f460d5a430bf5f8a'}}
PATHS = frozenset(SOURCE_PROFILES[VERSION])
VALIDATION_TOOLS = ('validation/tools/authority.py', 'validation/tools/run_validation.py', 'validation/tools/tuning_iteration_engine.py', 'tests/validation/test_authority_binding.py', 'validation/research-authority.json', 'scripts/validation_reproducer.py', 'tests/validation/test_validation_reproducer.py', 'validation/tools/run_validation_engine.py', 'validation/tools/stage_profile_support.py')


class Reject(ValueError):
    pass


def need(value, reason: str) -> None:
    if not value:
        raise Reject(reason)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def identity(data: bytes) -> dict:
    return {"git_blob_sha1": git_blob(data), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def bounded(path: str) -> bytes:
    relative = Path(path)
    need(not relative.is_absolute() and ".." not in relative.parts, "R11_UNSAFE_PATH")
    target = ROOT / relative
    need(target.is_file() and not target.is_symlink() and
         0 < target.stat().st_size < 262144, "R11_SOURCE_BOUND:" + path)
    return target.read_bytes()


need(git_blob(bounded(PREVIOUS)) == PREVIOUS_BLOB, "R11_PREVIOUS_HELPER_DRIFT")
import fe09_b3_f0_r10_source_admission as previous  # noqa: E402

legacy = previous.legacy
F0_LOCK_SHA256 = previous.F0_LOCK_SHA256


def registration(raw: bytes | None = None) -> dict:
    raw = bounded(PLAN) if raw is None else raw
    need(git_blob(raw) == PLAN_BLOB, "R11_PREREGISTRATION_DRIFT")
    plan = legacy.sealed_json(raw)
    need(plan["identity"] == "FE09-VALIDATION-2366-SOURCE-R11" and
         plan["candidate_version"] == VERSION and
         plan["source_authority"] == "INDEPENDENT_PROTECTED_SOURCE_REVIEW_BEFORE_PROTECTED_SOURCE_MERGE" and
         plan["reviewed_source_blobs"] == SOURCE_PROFILES[VERSION] and
         len(PATHS) == plan["source_delta"]["members"] and
         plan["source_delta"]["path"] == DELTA and
         plan["source_delta"]["reverse_must_recover_original_bytes"] is True,
         "R11_SOURCE_SCOPE_DRIFT")
    need(set(plan["reviewed_source"]) == PATHS and
         all(plan["reviewed_source"][p]["after"]["git_blob_sha1"] ==
             SOURCE_PROFILES[VERSION][p] for p in PATHS), "R11_REVIEWED_BYTES_DRIFT")
    for path, expected in plan["preserved_source_pins"].items():
        need(git_blob(bounded(path)) == expected, "R11_HISTORICAL_SOURCE_CHANGED:" + path)
    old = previous.registration()
    need(plan["scientific_contract"] == old["scientific_contract"] and
         plan["b3_lock_sha256"] == legacy.LOCK_SHA256 and
         plan["f0_lock_sha256"] == F0_LOCK_SHA256 and
         all(value is False for value in plan["promotion"].values()) and
         plan["dsp_runs_performed_by_source_gate"] == 0 and
         plan["quality_thresholds_or_budgets_relaxed"] is False,
         "R11_SCIENCE_OR_NONPROMOTION_DRIFT")
    need(set(plan["validation_tool_source"]) == set(VALIDATION_TOOLS),
         "R11_VALIDATION_TOOL_SCOPE_DRIFT")
    return plan


def verify_validation_tools(read_current, plan):
    for path in VALIDATION_TOOLS:
        need(identity(read_current(path)) == plan["validation_tool_source"][path],
             "R11_VALIDATION_TOOL_SOURCE_DRIFT:" + path)


def historical_inputs(plan: dict):
    rows, f0_rows, frozen = previous.historical_inputs(previous.registration())
    # Replay R10 independently; the R10 gate still rejects the new version bytes.
    previous.prove_delta(previous.registration(), frozen)
    live = {r["path"] for r in rows if r["role"] in legacy.EXECUTABLE_ROLES}
    need(PATHS <= live and len(live) == 66 and len(rows) == 77 and len(f0_rows) == 88,
         "R11_ORIGINAL_SOURCE_PARTITION")
    for path in PATHS:
        need(identity(frozen[path]) == plan["reviewed_source"][path]["before"],
             "R11_ORIGINAL_BYTES_CHANGED:" + path)
    return rows, f0_rows, frozen


def decode_delta(encoded: bytes, plan: dict) -> bytes:
    need(encoded.endswith(b"\n") and encoded.count(b"\n") == 1, "R11_DELTA_ENCODING")
    try:
        delta = base64.b64decode(encoded[:-1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise Reject("R11_DELTA_ENCODING") from exc
    need(identity(delta) == {k: plan["source_delta"][k] for k in identity(delta)},
         "R11_DELTA_IDENTITY")
    return delta


def delta_scope(delta: bytes, directory: Path) -> None:
    result = subprocess.run(["git", "apply", "--numstat", "-"], input=delta,
                            cwd=directory, capture_output=True, timeout=30, check=False)
    need(result.returncode == 0, "R11_DELTA_INVENTORY")
    paths = [line.split("\t")[-1] for line in result.stdout.decode().splitlines()]
    need(len(paths) == len(PATHS) and set(paths) == PATHS, "R11_DELTA_SCOPE")


def prove_delta(plan: dict, frozen: dict[str, bytes]) -> dict[str, bytes]:
    delta = decode_delta(bounded(DELTA), plan)
    with tempfile.TemporaryDirectory(prefix="fe09-r11-source-") as tmp:
        directory = Path(tmp)
        delta_scope(delta, directory)
        for path in PATHS:
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(frozen[path])
        for flags in (("--check",), ()):
            legacy.git("apply", *flags, "--unidiff-zero", "-", input_bytes=delta, cwd=directory)
        forward = {p: (directory / p).read_bytes() for p in PATHS}
        for path, data in forward.items():
            need(identity(data) == plan["reviewed_source"][path]["after"],
                 "R11_FORWARD_BYTES_CHANGED:" + path)
        for flags in (("--reverse", "--check"), ("--reverse",)):
            legacy.git("apply", *flags, "--unidiff-zero", "-", input_bytes=delta, cwd=directory)
        need(all((directory / p).read_bytes() == frozen[p] for p in PATHS),
             "R11_DELTA_NOT_REVERSIBLE")
    prior = previous.prove_delta(previous.registration(), frozen)
    changed = {"CMakeLists.txt"}
    need(all(prior[p] == forward[p] for p in PATHS - changed),
         "R11_UNRELATED_SOURCE_CHANGED")
    need(all(prior[p] != forward[p] for p in changed), "R11_EXPECTED_DELTA_MISSING")
    return forward


def verify_current(rows, f0_rows, read_current, plan: dict) -> None:
    need(legacy.check_source_set(rows, read_current, SOURCE_PROFILES[VERSION]) ==
         (66, len(PATHS)), "R11_CURRENT_SOURCE_COVERAGE")
    for row in f0_rows:
        path = row["path"]
        expected = (plan["reviewed_source"][path]["after"] if path in PATHS else
                    {k: row[k] for k in ("git_blob_sha1", "bytes", "sha256")})
        need(identity(read_current(path)) == expected, "R11_F0_SOURCE_DRIFT:" + path)


def version_from_cmake(data: bytes) -> str:
    match = re.search(rb"(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$", data)
    need(match is not None and match.group(1) == VERSION.encode(), "R11_VERSION_NOT_REGISTERED")
    return VERSION


def execution_identity(requested, actual: str, clean: bool) -> None:
    need(re.fullmatch(r"[0-9a-f]{40}", actual) is not None and
         (requested is None or requested == actual), "R11_CURRENT_CHECKOUT_MISMATCH")
    need(clean, "R11_DIRTY_TRACKED_WORKTREE")


def source_check(execution_source: str | None = None) -> dict:
    revision = legacy.git("rev-parse", "HEAD").decode().strip()
    execution_identity(execution_source, revision,
                       not legacy.git("status", "--porcelain", "--untracked-files=no").strip())
    version_from_cmake(legacy.committed_bytes("CMakeLists.txt"))
    plan = registration()
    for path in (SELF, PLAN, DELTA, DOCS + "README.md", *plan["preserved_source_pins"]):
        legacy.committed_bytes(path)
    rows, f0_rows, frozen = historical_inputs(plan)
    forward = prove_delta(plan, frozen)
    need(all(legacy.committed_bytes(p) == forward[p] for p in PATHS), "R11_CURRENT_DELTA_MISMATCH")
    verify_current(rows, f0_rows, legacy.committed_bytes, plan)
    verify_validation_tools(legacy.committed_bytes, plan)
    return {"schema_version": 1, "status": STATUS, "execution_source": revision,
            "execution_tree": legacy.git("rev-parse", "HEAD^{tree}").decode().strip(),
            "candidate_version": VERSION, "immutable_source_members": 77,
            "source_gated_members": 66, "source_gated_exceptions": len(PATHS),
            "source_gated_baseline_members": 66 - len(PATHS), "historical_reference_members": 11,
            "f0_lock_members": 88, "f0_shared_live_members": 66, "f0_additional_members": 22,
            "f0_additional_member_exceptions": 0, "f0_unchanged_current_members": 88 - len(PATHS),
            "original_r1_lock_sha256": legacy.LOCK_SHA256,
            "original_f0_lock_sha256": F0_LOCK_SHA256,
            "r11_preregistration_blob": PLAN_BLOB,
            "source_delta_blob": plan["source_delta"]["git_blob_sha1"],
            "source_delta_members_verified": len(PATHS),
            "reviewed_source_blobs": SOURCE_PROFILES[VERSION],
            "validation_tool_source": plan["validation_tool_source"],
            "science_executed": False, "r1_or_r2_result_inherited": False,
            "r3_result_inherited": False, "r4_result_inherited": False, "r5_result_inherited": False, "r6_result_inherited": False, "r7_result_inherited": False, "r8_result_inherited": False, "r9_result_inherited": False, "r10_result_inherited": False,
            "shipping_authority": False, "ssc305_hil_qualified": False, "four_mic_public_sdk": False}


def source_check_current(execution_source=None) -> dict:
    registration()
    data = legacy.committed_bytes("CMakeLists.txt")
    match = re.search(rb"(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$", data)
    need(match is not None, "R11_VERSION_NOT_PARSED")
    if match.group(1) == VERSION.encode():
        return source_check(execution_source)
    return previous.source_check_current(execution_source)


def self_test() -> dict:
    plan = registration()
    old = previous.self_test()
    need(old["new_source_negatives"] == 32 and old["science_executed"] is False,
         "R11_PREVIOUS_NEGATIVES_CHANGED")
    rows, f0_rows, frozen = historical_inputs(plan)
    candidate = {**frozen, **prove_delta(plan, frozen)}
    verify_current(rows, f0_rows, candidate.__getitem__, plan)
    version_from_cmake(candidate["CMakeLists.txt"])
    rejected = 0

    def reject(action):
        nonlocal rejected
        try:
            action()
        except (Reject, legacy.Reject):
            rejected += 1
        else:
            raise Reject("R11_NEGATIVE_ACCEPTED")

    for path in sorted(PATHS | {"src/core/ap_pipeline_query.c", "tests/validation/frontend_evolution/array_native.c",
                              "tests/validation/frontend_evolution/fe09_b3_f0_build/CMakeLists.txt"}):
        changed = {**candidate, path: candidate[path] + b"\n"}
        reject(lambda values=changed: verify_current(rows, f0_rows, values.__getitem__, plan))
    prior = previous.prove_delta(previous.registration(), frozen)
    try:
        previous.verify_current(rows, f0_rows, candidate.__getitem__, previous.registration())
    except (previous.Reject, legacy.Reject):
        rejected += 1
    else:
        raise Reject("R11_PREVIOUS_GATE_ACCEPTED_CORRECTED_SOURCE")
    for version in ("2.3.65", "2.3.67", "3.0.0", "2.3.66-rc"):
        reject(lambda v=version: version_from_cmake(
            ("project(audio_pipeline VERSION " + v + " LANGUAGES C)\n").encode()))
    reject(lambda: execution_identity("2" * 40, "1" * 40, True))
    reject(lambda: execution_identity(None, "not-a-sha", True))
    reject(lambda: execution_identity(None, "1" * 40, False))
    encoded = bounded(DELTA)
    delta = decode_delta(encoded, plan)
    for value in (encoded + b"\n", b"!" + encoded[1:], base64.b64encode(delta + b"\n") + b"\n"):
        reject(lambda v=value: decode_delta(v, plan))
    with tempfile.TemporaryDirectory(prefix="fe09-r11-negative-") as tmp:
        directory = Path(tmp)
        blocks = delta.split(b"diff --git ")[1:]
        missing = b"".join(b"diff --git " + b for b in blocks
                           if not b.startswith(b"a/src/sync/ap_sync.c "))
        for value in (delta.replace(b"src/sync/ap_sync.c", b"src/sync/unregistered.c"),
                      missing, delta + delta, b"invalid patch\n"):
            reject(lambda v=value: delta_scope(v, directory))
    reject(lambda: registration(bounded(PLAN) + b" "))
    tools = {path: bounded(path) for path in VALIDATION_TOOLS}
    verify_validation_tools(tools.__getitem__, plan)
    for path in VALIDATION_TOOLS:
        changed = dict(tools, **{path: tools[path] + b"\n"})
        reject(lambda values=changed: verify_validation_tools(values.__getitem__, plan))
    need(rejected == len(PATHS) + 19 + len(VALIDATION_TOOLS) == plan["new_source_negative_cases"],
         "R11_NEGATIVE_COVERAGE")
    return {"status": "R11_SOURCE_ONLY_SELF_TEST_PASS", "new_source_negatives": rejected,
            "preserved_r10_source_negatives": 32, "reviewed_source_members": len(PATHS),
            "science_executed": False, "thresholds_or_budgets_relaxed": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--check", action="store_true")
    checks.add_argument("--check-current", action="store_true")
    parser.add_argument("--execution-source")
    args = parser.parse_args()
    if not (args.self_test or args.check or args.check_current):
        parser.error("select --self-test, --check or --check-current")
    try:
        if args.self_test:
            print(json.dumps(self_test(), sort_keys=True))
        if args.check or args.check_current:
            action = source_check_current if args.check_current else source_check
            print(json.dumps(action(args.execution_source), sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as error:
        print("R11_SOURCE_REJECTED:" + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
