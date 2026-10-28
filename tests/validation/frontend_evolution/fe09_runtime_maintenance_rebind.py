#!/usr/bin/env python3
"""Exact v2.3.56 maintenance binding plus unchanged historical FE09 preflights.

Current files are admitted only by the reviewed after-blob identities. A pinned
inverse patch reconstructs the old bytes in a disposable copy, where the old
preflights still enforce their original complete source hashes and negatives.
Neither the old source nor its preflight is presented as current execution.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import io
import json
import re
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
# Only the reviewed 2.3.59 audit candidate adds this one historical header.
# The original policy and the 2.3.57/2.3.58 three-source registrations stay exact.
AUDIT_2_3_59_PATHS = frozenset({
    "CMakeLists.txt", "docs/API_CONTRACT.md",
    "include/audio_pipeline/audio_runtime.h", "src/platform/linux/ap_runtime.c",
})

# Registrations are intentionally in this separately protected-main qualifier,
# not in either source candidate PR. Every byte of the post-v2.3.56 current
# CMake/runtime sources and the forward delta is pre-registered, but the
# registration does NOT promote the untested shipping implementation.
FORWARD_MAINTENANCE = {
    "2.3.57": {
        "blobs": {
            "CMakeLists.txt": "1d1e7f7bbf29d8e95b61fc135a0c93de3193256a",
            "src/platform/linux/ap_runtime.c": "519cf2732289af74c0285d3bbff4cae556bc7d07",
            "docs/API_CONTRACT.md": "821c07424e420cecc0bf64e67f237c7a9a131502",
        },
        "patch": "fe09_maintenance_forward_2_3_57.patch.b64",
        "patch_blob": "7e5fe35b78ff44950c0941c8bec34f71ce5b1e15",
    },
    "2.3.58": {
        "blobs": {
            "CMakeLists.txt": "231cf6085b2b6f7a962433327075d629e16b330e",
            "src/platform/linux/ap_runtime.c": "519cf2732289af74c0285d3bbff4cae556bc7d07",
            "docs/API_CONTRACT.md": "821c07424e420cecc0bf64e67f237c7a9a131502",
        },
        "patch": "fe09_maintenance_forward_2_3_58.patch.b64",
        "patch_blob": "dade779a6293c7c9bd72e48611710abe3d2d8f0c",
    },
    "2.3.59": {
        "blobs": {
            "CMakeLists.txt": "cc9003ac8618cdd02823991a090a9a8be044dc1a",
            "docs/API_CONTRACT.md": "1d33a03b627ea93dc0746410c103172dc31432e3",
            "include/audio_pipeline/audio_runtime.h": "ad72e40b5b343aee4589ee50dfd07fe1a85e0ea9",
            "src/platform/linux/ap_runtime.c": "b6c36e195c1ac967e450a1e32506e0b6859a581b",
        },
        "patch": "fe09_maintenance_forward_2_3_59.patch.b64",
        "patch_blob": "07f10884864da801750b43e876732896df436f79",
    },
}



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


def current_registered_paths(version: str) -> frozenset[str]:
    return AUDIT_2_3_59_PATHS if version == "2.3.59" else frozenset(CHANGED)


def frozen_maintenance_blob(path: str, item: dict) -> str:
    if path in CHANGED:
        return item["source_bindings"][path]["after_blob"]
    need(path == "include/audio_pipeline/audio_runtime.h", "REGISTERED_SOURCE_SCOPE_DRIFT")
    return major.BLOBS[path]


def decode_registered_forward_patch(version: str, encoded: bytes) -> bytes:
    need(version in FORWARD_MAINTENANCE, "UNREGISTERED_FORWARD_MAINTENANCE_VERSION")
    registration = FORWARD_MAINTENANCE[version]
    need(encoded.endswith(b"\n") and b"\n" not in encoded[:-1],
         "REGISTERED_FORWARD_ENCODING_INVALID_" + version)
    try:
        patch = base64.b64decode(encoded[:-1], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RebindError("REGISTERED_FORWARD_ENCODING_INVALID_" + version) from exc
    need(major.git_blob(patch) == registration["patch_blob"],
         "REGISTERED_FORWARD_PATCH_DRIFT_" + version)
    return patch


def registered_forward_patch(version: str) -> bytes:
    registration = FORWARD_MAINTENANCE[version]
    return decode_registered_forward_patch(version, raw_file(HERE / registration["patch"]))


def check_forward_patch_scope(version: str, patch: bytes, destination: Path) -> None:
    need(version in FORWARD_MAINTENANCE, "UNREGISTERED_FORWARD_MAINTENANCE_VERSION")
    expected = (AUDIT_2_3_59_PATHS if version == "2.3.59" else
                frozenset({"CMakeLists.txt", "src/platform/linux/ap_runtime.c"}))
    inventory = subprocess.run(["git", "apply", "--numstat", "-"],
                               input=patch, cwd=destination, capture_output=True,
                               timeout=20, check=False)
    need(inventory.returncode == 0, "REGISTERED_FORWARD_INVENTORY_INVALID")
    paths = [line.split("\t")[-1] for line in inventory.stdout.decode("utf-8").splitlines()]
    need(len(paths) == len(expected) and set(paths) == expected,
         "REGISTERED_FORWARD_PATCH_SCOPE_DRIFT")


def current_maintenance_version(src: dict[str, str], item: dict) -> str:
    match = re.search(r"(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$",
                      src["CMakeLists.txt"])
    need(match is not None, "CURRENT_VERSION_NOT_PARSED")
    version = match.group(1)
    if version == item["maintenance_version"]:
        wanted = {path: binding["after_blob"]
                  for path, binding in item["source_bindings"].items()}
    else:
        need(version in FORWARD_MAINTENANCE, "UNREGISTERED_FORWARD_MAINTENANCE_VERSION")
        wanted = FORWARD_MAINTENANCE[version]["blobs"]
        registered_forward_patch(version)
    need(set(wanted) == current_registered_paths(version), "REGISTERED_SOURCE_SCOPE_DRIFT")
    for path in sorted(current_registered_paths(version)):
        need(major.git_blob(src[path].encode("utf-8")) == wanted[path],
             "CURRENT_MAINTENANCE_SOURCE_DRIFT_" + path)
    for path in sorted(CHANGED):
        need(item["source_bindings"][path]["before_blob"] == major.BLOBS[path],
             "HISTORICAL_BINDING_DRIFT")
    return version


def check_current(src: dict[str, str], item: dict) -> dict[str, str]:
    version = current_maintenance_version(src, item)
    for name, path, needle in major.PROBES:
        if name == "CMAKE_MAJOR_TWO":
            needle = f"project(audio_pipeline VERSION {version} LANGUAGES C)"
        need(src[path].count(needle) == 1, "CURRENT_ARCHITECTURE_DRIFT_" + name)
    for path, anchors in recorder.ANCHORS.items():
        need(all(anchor in src[path] for anchor in anchors),
             "CURRENT_RECORDER_ANCHOR_DRIFT_" + path)
    # The original 2.3.56 contract/policy/patch and research-source hashes
    # stay immutable; only exact pre-registered patches normalize newer 2.x
    # reviewed source bytes in a disposable historical reconstruction.
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
    version = current_maintenance_version(src, item)
    for path, content in src.items():
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if version in FORWARD_MAINTENANCE:
        forward = registered_forward_patch(version)
        check_forward_patch_scope(version, forward, destination)
        for options in (("--reverse", "--check", "--unidiff-zero"),
                        ("--reverse", "--unidiff-zero")):
            result = subprocess.run(["git", "apply", *options, "-"], input=forward,
                                    cwd=destination, capture_output=True, timeout=20,
                                    check=False)
            need(result.returncode == 0, "REGISTERED_FORWARD_INVERSE_FAILED")
        for path in current_registered_paths(version):
            need(major.git_blob(raw_file(destination / path)) ==
                 frozen_maintenance_blob(path, item),
                 "REGISTERED_FORWARD_NOT_FROZEN_PREIMAGE_" + path)
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
    version = current_maintenance_version(src, item)
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
        "active_current_version": version,
        "registered_forward_patch_blob": (
            FORWARD_MAINTENANCE[version]["patch_blob"]
            if version in FORWARD_MAINTENANCE else None),
        "current_registered_blobs": {path: major.git_blob(src[path].encode("utf-8"))
                                     for path in sorted(current_registered_paths(version))},
        "execution_source_commit": subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(ROOT), "rev-parse", "HEAD"],
            cwd=ROOT, text=True, timeout=20).strip(),
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
    audit_rejected = 0

    def reject(fn, reason: str | None = None, *, audit: bool = False) -> None:
        nonlocal rejected, audit_rejected
        try:
            fn()
        except (RebindError, major.GateFailure, recorder.GateError) as error:
            need(reason is None or str(error) == reason, "WRONG_MAINTENANCE_REJECTION")
            if audit:
                audit_rejected += 1
            else:
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
    changed["CMakeLists.txt"] = re.sub(r"VERSION 2\.3\.[0-9]+", "VERSION 3.0.0",
                                             changed["CMakeLists.txt"], count=1)
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
    # Independently exercise all future candidate registrations from the
    # complete frozen 2.3.56 image, with no candidate source execution.
    with tempfile.TemporaryDirectory(prefix="fe09-forward-registry-") as directory:
        temp = Path(directory)
        version = current_maintenance_version(src, item)
        frozen = temp / "frozen"
        frozen.mkdir()
        for path, content in src.items():
            target = frozen / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        if version in FORWARD_MAINTENANCE:
            delta = registered_forward_patch(version)
            result = subprocess.run(["git", "apply", "--reverse", "--unidiff-zero", "-"],
                                    input=delta, cwd=frozen, capture_output=True,
                                    timeout=20, check=False)
            need(result.returncode == 0, "REGISTERED_CURRENT_CANNOT_NORMALIZE")
        clean = {path: raw_file(frozen / path).decode("utf-8") for path in src}
        for path in current_registered_paths(version):
            need(major.git_blob(clean[path].encode("utf-8")) ==
                 frozen_maintenance_blob(path, item),
                 "ORIGINAL_MAINTENANCE_SOURCE_NOT_RECOVERED_" + path)
        for candidate_version in sorted(FORWARD_MAINTENANCE):
            case_root = temp / candidate_version
            case_root.mkdir()
            for path, content in clean.items():
                target = case_root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            delta = registered_forward_patch(candidate_version)
            result = subprocess.run(["git", "apply", "--unidiff-zero", "-"],
                                    input=delta, cwd=case_root, capture_output=True,
                                    timeout=20, check=False)
            need(result.returncode == 0, "REGISTERED_FORWARD_PATCH_INVALID")
            candidate = {path: raw_file(case_root / path).decode("utf-8") for path in clean}
            need(current_maintenance_version(candidate, item) == candidate_version,
                 "REGISTERED_FORWARD_CANDIDATE_IDENTITY_MISMATCH")
            check_current(candidate, item)
            reconstructed = temp / ("historical-" + candidate_version)
            reconstructed.mkdir()
            reconstruct(reconstructed, candidate, item, patch)
            for path, binding in item["source_bindings"].items():
                need(major.git_blob(raw_file(reconstructed / path)) == binding["before_blob"],
                     "REGISTERED_FORWARD_HISTORICAL_RECONSTRUCTION_DRIFT")
            for path, digest in major.BLOBS.items():
                need(major.git_blob(raw_file(reconstructed / path)) == digest,
                     "REGISTERED_FORWARD_HISTORICAL_SOURCE_DRIFT_" + path)
            changed = {**candidate, "src/platform/linux/ap_runtime.c":
                       candidate["src/platform/linux/ap_runtime.c"] + "\n"}
            reject(lambda bad=changed: check_current(bad, item),
                   "CURRENT_MAINTENANCE_SOURCE_DRIFT_src/platform/linux/ap_runtime.c",
                   audit=candidate_version == "2.3.59")
            if candidate_version == "2.3.59":
                for path in sorted(AUDIT_2_3_59_PATHS - {"src/platform/linux/ap_runtime.c"}):
                    changed = {**candidate, path: candidate[path] + "\n"}
                    reject(lambda bad=changed: check_current(bad, item),
                           "CURRENT_MAINTENANCE_SOURCE_DRIFT_" + path, audit=True)
                changed = {**candidate, "CMakeLists.txt": candidate["CMakeLists.txt"].replace(
                    "VERSION 2.3.59", "VERSION 2.3.60", 1)}
                reject(lambda: check_current(changed, item),
                       "UNREGISTERED_FORWARD_MAINTENANCE_VERSION", audit=True)
                encoded = raw_file(HERE / FORWARD_MAINTENANCE[candidate_version]["patch"])
                reject(lambda: decode_registered_forward_patch("2.3.59", encoded + b"\n"),
                       "REGISTERED_FORWARD_ENCODING_INVALID_2.3.59", audit=True)
                reject(lambda: decode_registered_forward_patch("2.3.59", b"!" + encoded[1:]),
                       "REGISTERED_FORWARD_ENCODING_INVALID_2.3.59", audit=True)
                corrupt = base64.b64encode(delta + b"\n") + b"\n"
                reject(lambda: decode_registered_forward_patch("2.3.59", corrupt),
                       "REGISTERED_FORWARD_PATCH_DRIFT_2.3.59", audit=True)
                wrong_path = delta.replace(b"include/audio_pipeline/audio_runtime.h",
                                           b"include/audio_pipeline/unregistered.h")
                reject(lambda: check_forward_patch_scope("2.3.59", wrong_path, case_root),
                       "REGISTERED_FORWARD_PATCH_SCOPE_DRIFT", audit=True)
                blocks = delta.split(b"diff --git ")[1:]
                missing_path = b"".join(b"diff --git " + block for block in blocks
                                        if not block.startswith(
                                            b"a/include/audio_pipeline/audio_runtime.h "))
                reject(lambda: check_forward_patch_scope("2.3.59", missing_path, case_root),
                       "REGISTERED_FORWARD_PATCH_SCOPE_DRIFT", audit=True)
                reject(lambda: check_forward_patch_scope("2.3.59", delta + delta, case_root),
                       "REGISTERED_FORWARD_PATCH_SCOPE_DRIFT", audit=True)
                reject(lambda: check_forward_patch_scope("2.3.59", b"invalid patch\n", case_root),
                       "REGISTERED_FORWARD_INVENTORY_INVALID", audit=True)
    need(rejected == 16, "MAINTENANCE_NEGATIVES_INCOMPLETE")
    need(audit_rejected == 12, "AUDIT_2_3_59_NEGATIVES_INCOMPLETE")
    print("FE09_EXACT_MAINTENANCE_REBIND_SELF_TEST_PASS negatives=16 "
          "audit2359_negatives=12 preregistered=3")


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
