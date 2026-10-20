#!/usr/bin/env python3
"""Exact v2.3.56 maintenance binding plus unchanged historical FE09 preflights.

Current files are admitted only by the reviewed after-blob identities. A pinned
inverse patch reconstructs the old bytes in a disposable copy, where the old
preflights still enforce their original complete source hashes and negatives.
Neither the old source nor its preflight is presented as current execution.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile

import fe09_major_migration_preflight_r2b0 as major
import fe09_r2b2_runtime_recorder_preflight_s0 as recorder

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
POLICY = HERE / "fe09_runtime_maintenance_2_3_56.json"
PATCH = HERE / "fe09_runtime_maintenance_2_3_56.patch"
POLICY_SHA256 = "7de30e6b288f76fdc3f7df5680a40ffb6a1134c43354a6b3e2f6556cb4a35f6c"
CHANGED = {"CMakeLists.txt", "docs/API_CONTRACT.md", "src/platform/linux/ap_runtime.c"}


class RebindError(ValueError):
    pass


def need(condition: bool, code: str) -> None:
    if not condition:
        raise RebindError(code)


def raw_file(path: Path) -> bytes:
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size < 262144,
         "MISSING_OR_UNBOUNDED_FILE")
    return path.read_bytes()


def policy(raw: bytes, patch: bytes) -> dict:
    need(hashlib.sha256(raw).hexdigest() == POLICY_SHA256, "MAINTENANCE_POLICY_DRIFT")
    item = major.strict_json(raw.decode("utf-8"))
    need(set(item["source_bindings"]) == CHANGED and
         hashlib.sha256(patch).hexdigest() == item["patch_sha256"],
         "INVERSE_PATCH_OR_SOURCE_SET_DRIFT")
    return item


def read_sources(root: Path, item: dict) -> dict[str, str]:
    for path, digest in item["historical_contract_sha256"].items():
        need(hashlib.sha256(raw_file(root / path)).hexdigest() == digest,
             "HISTORICAL_CONTRACT_CHANGED_" + path)
    paths = set(major.BLOBS) | set(recorder.SOURCE_PATHS) | {major.CONTRACT, major.ADR}
    return {path: raw_file(root / path).decode("utf-8") for path in paths}


def check_current(src: dict[str, str], item: dict) -> dict[str, str]:
    for path, binding in item["source_bindings"].items():
        need(major.git_blob(src[path].encode("utf-8")) == binding["after_blob"],
             "CURRENT_MAINTENANCE_SOURCE_DRIFT_" + path)
        need(binding["before_blob"] == major.BLOBS[path], "HISTORICAL_BINDING_DRIFT")
    for name, path, needle in major.PROBES:
        if name == "CMAKE_MAJOR_TWO":
            needle = "project(audio_pipeline VERSION 2.3.56 LANGUAGES C)"
        need(src[path].count(needle) == 1, "CURRENT_ARCHITECTURE_DRIFT_" + name)
    for path, anchors in recorder.ANCHORS.items():
        need(all(anchor in src[path] for anchor in anchors),
             "CURRENT_RECORDER_ANCHOR_DRIFT_" + path)
    # Exact hashes of every other file are still checked by the original
    # preflights on this same copy, after reversing only the three bound paths.
    return {path: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for path, content in sorted(src.items())}


def reconstruct(destination: Path, src: dict[str, str], item: dict, patch: bytes) -> None:
    check_current(src, item)
    need(hashlib.sha256(patch).hexdigest() == item["patch_sha256"], "INVERSE_PATCH_DRIFT")
    inventory = subprocess.run(["git", "apply", "--numstat", "-"], input=patch,
                               cwd=destination, capture_output=True, timeout=20, check=False)
    need(inventory.returncode == 0, "INVERSE_PATCH_INVENTORY_INVALID")
    paths = [line.split("\t")[-1] for line in inventory.stdout.decode("utf-8").splitlines()]
    need(len(paths) == len(CHANGED) and set(paths) == CHANGED,
         "INVERSE_PATCH_UNAUTHORIZED_PATH")
    for path, content in src.items():
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    for arguments in (("--reverse", "--check", "--unidiff-zero"),
                      ("--reverse", "--unidiff-zero")):
        completed = subprocess.run(["git", "apply", *arguments, "-"], input=patch,
                                   cwd=destination, capture_output=True, timeout=20,
                                   check=False)
        need(completed.returncode == 0, "HISTORICAL_RECONSTRUCTION_FAILED")
    for path, binding in item["source_bindings"].items():
        need(major.git_blob(raw_file(destination / path)) == binding["before_blob"],
             "RECONSTRUCTED_HISTORICAL_BLOB_MISMATCH_" + path)


def verify(*, historical_self_tests: bool) -> dict:
    patch = raw_file(PATCH)
    item = policy(raw_file(POLICY), patch)
    src = read_sources(ROOT, item)
    current_hashes = check_current(src, item)
    with tempfile.TemporaryDirectory(prefix="fe09-maintenance-history-") as directory:
        historical = Path(directory)
        reconstruct(historical, src, item, patch)
        previous_major_root, previous_recorder_root = major.ROOT, recorder.ROOT
        try:
            major.ROOT = historical
            recorder.ROOT = historical
            # The unchanged recorder contract remains read from its original,
            # separately pinned path; only its source tree is the old snapshot.
            with contextlib.redirect_stdout(io.StringIO()) as historical_log:
                if historical_self_tests:
                    major.self_test()
                    recorder.self_test()
                original_major = major.run_check(historical)
                with contextlib.redirect_stdout(io.StringIO()) as receipt:
                    recorder.check()
                original_recorder = json.loads(receipt.getvalue())
        finally:
            major.ROOT, recorder.ROOT = previous_major_root, previous_recorder_root
    return {
        "schema_version": 1, "decision": item["decision"],
        "maintenance_version": item["maintenance_version"],
        "execution_source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=20).strip(),
        "maintenance_checker_sha256": hashlib.sha256(raw_file(Path(__file__))).hexdigest(),
        "current_source_sha256": current_hashes,
        "current_architecture_probes": len(major.PROBES),
        "current_recorder_source_files": len(recorder.SOURCE_PATHS),
        "maintenance_policy_sha256": POLICY_SHA256,
        "inverse_patch_sha256": item["patch_sha256"],
        "historical_preflight_results": {"r2b0": original_major, "r2b2_s0": original_recorder},
        "historical_self_tests_executed": historical_self_tests,
        "historical_self_test_log": historical_log.getvalue().splitlines(),
        "historical_source_is_current_source": False,
        "shipping_src_changed": True,
        "public_c4_enabled": False, "shipping_or_hil_qualification": False,
    }


def self_test() -> None:
    patch, raw = raw_file(PATCH), raw_file(POLICY)
    item = policy(raw, patch)
    src = read_sources(ROOT, item)
    rejected = 0

    def reject(fn, reason: str | None = None) -> None:
        nonlocal rejected
        try:
            fn()
        except (RebindError, major.GateFailure, recorder.GateError) as error:
            need(reason is None or str(error) == reason, "WRONG_MAINTENANCE_REJECTION")
            rejected += 1
        else:
            raise RebindError("MAINTENANCE_NEGATIVE_FALSE_ACCEPT")

    for path in CHANGED:
        changed = {**src, path: src[path] + "\n"}
        reject(lambda source=changed: check_current(source, item),
               "CURRENT_MAINTENANCE_SOURCE_DRIFT_" + path)
    reject(lambda: policy(raw + b" ", patch), "MAINTENANCE_POLICY_DRIFT")
    reject(lambda: policy(raw, patch + b"\n"), "INVERSE_PATCH_OR_SOURCE_SET_DRIFT")
    reject(lambda: policy(raw, patch + b"\ndiff --git a/extra b/extra\n"),
           "INVERSE_PATCH_OR_SOURCE_SET_DRIFT")
    changed = dict(src)
    changed["CMakeLists.txt"] = changed["CMakeLists.txt"].replace("VERSION 2.3.56", "VERSION 3.0.0")
    reject(lambda: check_current(changed, item))
    changed = dict(src)
    changed["include/audio_pipeline/audio_types.h"] = changed[
        "include/audio_pipeline/audio_types.h"].replace("AP_MAX_MIC_CHANNELS 2u", "AP_MAX_MIC_CHANNELS 4u")
    reject(lambda: check_current(changed, item))
    # Even an unrelated single-byte edit in an unbound source must retain the
    # old full-blob failure, beyond the visible architecture anchors.
    changed = dict(src)
    changed["src/frontend/ap_resampler.c"] += "\n"
    with tempfile.TemporaryDirectory(prefix="fe09-maintenance-negative-") as directory:
        historical = Path(directory)
        reconstruct(historical, changed, item, patch)
        reject(lambda: major.run_check(historical), "SOURCE_BLOB_DRIFT_src/frontend/ap_resampler.c")
    with tempfile.TemporaryDirectory(prefix="fe09-maintenance-contract-negative-") as directory:
        current = Path(directory)
        files = dict(src)
        files.update({path: raw_file(ROOT / path).decode("utf-8")
                      for path in item["historical_contract_sha256"]})
        for path, content in files.items():
            target = current / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        for path in item["historical_contract_sha256"]:
            target = current / path
            target.write_text(files[path] + "\n", encoding="utf-8")
            reject(lambda: read_sources(current, item), "HISTORICAL_CONTRACT_CHANGED_" + path)
            target.write_text(files[path], encoding="utf-8")
    need(rejected == 14, "MAINTENANCE_NEGATIVES_INCOMPLETE")
    print("FE09_EXACT_MAINTENANCE_REBIND_SELF_TEST_PASS negatives=14")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.self_test and not args.check:
        parser.error("--self-test and/or --check is required")
    if args.self_test:
        self_test()
    if args.check:
        print(json.dumps(verify(historical_self_tests=True), sort_keys=True))


if __name__ == "__main__":
    main()
