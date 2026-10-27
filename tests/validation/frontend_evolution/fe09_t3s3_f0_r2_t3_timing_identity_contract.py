#!/usr/bin/env python3
"""Independently preregister the R2 F0 timing-driver identity bridge, without DSP."""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
R2 = REL + "fe09_t3s3_f0_call_resource_r2_qualification.py"
R1 = REL + "fe09_t3s3_f0_call_resource_qualification.py"
PROBE = REL + "fe09_t3s3_f0_call_resource_probe.c"
T2 = REL + "fe09_b3_f0_r2_t2_derivation_contract.py"
MANIFEST = "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/T2_EXECUTOR_SOURCE_REVIEW.json"
REVIEW = "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/T3_TIMING_IDENTITY_SOURCE_REVIEW.json"
BASE = "6ed740697b0454a74054feb562637e2aee5129f0"
R1_BLOB = "e22cc4f0eede6e844b985e0bece8e9dcbf2e02cd"
R2_BLOB = "8ac87edbbd89289ec4b6fc2739af6460a6fd01d0"
R2_CORRECTED_BLOB = "065cce6349842876b01ec3e410e2958bfa55eeab"
PROBE_BLOB = "01e26892f18e5c64a7c74448817ed6c22e693bd7"
T2_BLOB = "d0965732f7656dcc1c782e3813c6c32d5d9af2f5"
T2_MANIFEST_BLOB = "824e719aa30ce72130cf7f465eada1707280942f"
DRIVER = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1"
RECEIPT = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-FORWARD-SOURCE-R2"
BEFORE = 'data["schema_version"] == 1 and data["id"] == IDENTITY and data["case"] == case and'
AFTER = 'data["schema_version"] == 1 and data["id"] == "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1" and data["case"] == case and'


class Rejected(ValueError):
    pass


def need(ok: bool, why: str) -> None:
    if not ok:
        raise Rejected(why)


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\\0" + raw).hexdigest()


def pinned(path: str, expected: str) -> bytes:
    file = ROOT / path
    need(file.is_file() and not file.is_symlink(), "SOURCE_MISSING:" + path)
    raw = file.read_bytes()
    need(blob(raw) == expected, "PROTECTED_SOURCE_DRIFT:" + path)
    return raw


def original_source() -> bytes:
    result = subprocess.run(["git", "-c", f"safe.directory={ROOT}", "show",
                             BASE + ":" + R2], cwd=ROOT, check=True,
                            capture_output=True, timeout=15)
    need(blob(result.stdout) == R2_BLOB, "HISTORICAL_R2_SOURCE_CHANGED")
    return result.stdout


def expected_source(before: bytes) -> bytes:
    need(before.count(BEFORE.encode()) == 1, "ONE_REVIEWED_METADATA_SITE_REQUIRED")
    after = before.replace(BEFORE.encode(), AFTER.encode(), 1)
    need(blob(after) == R2_CORRECTED_BLOB, "T3_CORRECTION_SOURCE_OBJECT_DRIFT")
    return after


def validate_review() -> None:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            need(key not in out, "DUPLICATE_REVIEW_KEY")
            out[key] = value
        return out
    review = json.loads((ROOT / REVIEW).read_text(), object_pairs_hook=unique)
    need(review == {
        "identity": "FE09-F0-R2-T3-TIMING-DRIVER-IDENTITY-BRIDGE",
        "authority": "SOURCE_ONLY_BEFORE_R2_F0_REEXECUTION",
        "protected_predecessor_main": BASE,
        "original_f0_python_blob": R2_BLOB,
        "reviewed_f0_python_blob": R2_CORRECTED_BLOB,
        "original_probe_c_blob": PROBE_BLOB,
        "original_r1_python_blob": R1_BLOB,
        "original_t2_verifier_blob": T2_BLOB,
        "original_t2_manifest_blob": T2_MANIFEST_BLOB,
        "observed_timing_driver_id": DRIVER,
        "r2_collector_receipt_id": RECEIPT,
        "changed_function": "validate_timing",
        "changed_statement": "driver ID comparison only; all other source bytes identical",
        "runtime_dsp_source_changed": False,
        "r1_source_or_evidence_changed": False,
        "timing_budget_or_frame_count_relaxed": False,
        "historical_failed_artifacts_retained": {
            "850": {"id": 12715125160, "zip_sha256": "ca7161a1382739651c3a5968a25c9edbc690fca5121b4916320459e1d0618f27"},
            "851": {"id": 12714824044, "zip_sha256": "08d6a40f0c002ed8dbbb02d513bd73b8a6e8f9ae163252f5999925ac6a99c2d7"}
        },
        "accepted_r2_f0_science_executions": 0,
        "product_or_hardware_qualified": False,
        "production_promotion_authorized": False,
    }, "T3_SOURCE_REVIEW_MANIFEST_DRIFT")


def validate_frozen_source(before: str, after: str) -> None:
    original = ast.parse(before)
    patched = ast.parse(after)
    def named(tree):
        return {x.name: ast.get_source_segment(before if tree is original else after, x)
                for x in tree.body if isinstance(x, (ast.FunctionDef, ast.ClassDef))}
    lhs, rhs = named(original), named(patched)
    need(lhs.keys() == rhs.keys(), "SOURCE_FUNCTION_SURFACE_CHANGED")
    changed = {x for x in lhs if lhs[x] != rhs[x]}
    need(changed == {"validate_timing"}, "UNREVIEWED_SCIENCE_FUNCTION_CHANGE")
    need(before.replace(BEFORE, AFTER, 1) == after, "UNREGISTERED_NONMETADATA_CHANGE")
    need(before.count(BEFORE) == 1 and AFTER in after and BEFORE not in after,
         "T3_IDENTITY_PATCH_SHAPE")
    need("IDENTITY = \"" + RECEIPT + "\"" in after,
         "R2_RECEIPT_IDENTITY_NOT_PRESERVED")


def timing_identity_negatives(source: str) -> None:
    names = {"duration", "statistics", "validate_timing"}
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    need({n.name for n in nodes} == names, "TIMING_VALIDATOR_MISSING")
    scope = {"need": need}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 "<reviewed-f0-timing-validator>", "exec"), scope)
    fn = scope["validate_timing"]
    call = {"calls": 1, "status": 0, "cpu_ns": 100, "wall_ns": 200}
    sample = {"schema_version": 1, "id": DRIVER, "case": "ALL_P",
              "failed": 0, "completed_frames": 600,
              "clock_cpu": "CLOCK_THREAD_CPUTIME_ID", "clock_wall": "CLOCK_MONOTONIC",
              "cpu_resolution_ns": 1, "wall_resolution_ns": 1, "timing_storage_bytes": 32768,
              "bind": call, "frames": [
                  {"seq": n, "event": 1, "capture": call, "render": call, "worker": call}
                  for n in range(1, 601)]}
    result = fn(sample, "ALL_P")
    need(result["combined_cpu_ns"]["sum_ns"] == 180000 and
         result["combined_wall_ns"]["sum_ns"] == 360000,
         "VALID_ORIGINAL_C_DRIVER_TIMING_NOT_ACCEPTED")
    trials = [
        ("collector-identity", lambda d: d.update(id=RECEIPT), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("unknown-identity", lambda d: d.update(id="unreviewed"), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("wrong-case", lambda d: d.update(case="PAP"), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("short-run", lambda d: d.update(completed_frames=599), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("failed-run", lambda d: d.update(failed=1), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("missing-frame", lambda d: d["frames"].pop(), "TIMING_FRAME_COUNT"),
        ("frame-order", lambda d: d["frames"][0].update(seq=2), "TIMING_FRAME_OR_RENDER_ORDER"),
        ("negative-ns", lambda d: d["frames"][0]["worker"].update(cpu_ns=-1), "NONNEGATIVE_INTEGER_DURATION"),
    ]
    for name, mutate, expected in trials:
        changed = copy.deepcopy(sample)
        mutate(changed)
        try:
            fn(changed, "ALL_P")
        except Rejected as exc:
            need(str(exc) == expected, "WRONG_T3_NEGATIVE_REASON:" + name)
        else:
            raise Rejected("INVALID_TIMING_WAS_ACCEPTED:" + name)


def self_test() -> dict:
    validate_review()
    pinned(R1, R1_BLOB)
    pinned(PROBE, PROBE_BLOB)
    pinned(T2, T2_BLOB)
    pinned(MANIFEST, T2_MANIFEST_BLOB)
    before = original_source()
    after = expected_source(before)
    validate_frozen_source(before.decode(), after.decode())
    current = (ROOT / R2).read_bytes()
    need(blob(current) in (R2_BLOB, R2_CORRECTED_BLOB) and
         current in (before, after), "UNREGISTERED_R2_F0_EXECUTOR")
    if current == before:
        result = subprocess.run([sys.executable, str(ROOT / T2), "--self-test"],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        need(result.returncode == 0 and
             "R2_T2_SOURCE_DERIVATION_SELF_TEST_PASS" in result.stdout,
             "ORIGINAL_T2_SOURCE_REVIEW_REGRESSION")
    timing_identity_negatives(after.decode())
    return {"status": "T3_ORIGINAL_C_TIMING_IDENTITY_SOURCE_REVIEW_PASS_NO_DSP",
            "stage": "PREREGISTERED" if current == before else "EXACT_REVIEWED_CORRECTION",
            "original_t2_source_and_manifest_preserved": True,
            "changed_functions": ["validate_timing"],
            "negative_cases": 8, "dsp_executed": False,
            "resource_thresholds_relaxed": False, "shipping_promotion": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("--self-test required")
    try:
        print(json.dumps(self_test(), sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError, subprocess.SubprocessError, SyntaxError, KeyError) as exc:
        print("T3_TIMING_SOURCE_REVIEW_REJECTED:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
