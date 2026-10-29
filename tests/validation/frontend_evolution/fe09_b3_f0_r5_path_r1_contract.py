#!/usr/bin/env python3
"""Independent R5 provenance-path correction review. Metadata only; no DSP."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
PLAN = "docs/research/frontend-evolution-v1/FE09_B3_F0_R5_PATH_CORRECTION_R1_20261029/PREREGISTRATION.json"
PLAN_BLOB = "5ca0d8acfbb3cedd7f4bce6f061630af41d76102"
ACTUAL = "docs/research/frontend-evolution-v1/FE09_B3_F0_PCM_IO_SOURCE_R5_20261029/"
MISSING = "docs/research/frontend-evolution-v1/FE09_B3_F0_IO_SOURCE_R5_20261029/"


class Rejected(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise Rejected(reason)


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def bounded(path: str) -> bytes:
    rel = Path(path)
    need(not rel.is_absolute() and ".." not in rel.parts, "UNSAFE_SOURCE_PATH")
    target = ROOT / rel
    need(target.is_file() and not target.is_symlink() and
         0 < target.stat().st_size < 100000, "BOUND_SOURCE_REQUIRED:" + path)
    return target.read_bytes()


def check_identity(raw: bytes, expected: dict, path: str) -> None:
    need(blob(raw) == expected["git_blob_sha1"] and len(raw) == expected["bytes"] and
         hashlib.sha256(raw).hexdigest() == expected["sha256"],
         "SOURCE_IDENTITY_CHANGED:" + path)


def plan_record() -> dict:
    raw = bounded(PLAN)
    need(blob(raw) == PLAN_BLOB, "CORRECTION_PLAN_CHANGED")
    result = json.loads(raw)
    need(result["identity"] == "FE09-B3-F0-R5-PROVENANCE-PATH-R1" and
         result["candidate_cmake_blob"] == "754a5233998a79d4c1f9e86ae4628f6c5d046550",
         "CORRECTION_SCOPE_CHANGED")
    return result


def expected_source(parent: str, profile: dict) -> str:
    result = parent
    for item in profile["replacements"]:
        need(item["occurrences"] == 1 and
             result.count(item["before"]) == 1, "TRANSFORM_SITE_NOT_UNIQUE")
        result = result.replace(item["before"], item["after"], 1)
    return result


def literal_provenance(source: str, function: str) -> list[str]:
    tree = ast.parse(source)
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == function]
    need(len(functions) == 1, "SOURCE_FUNCTION_NOT_UNIQUE")
    paths = []
    for node in ast.walk(functions[0]):
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and
                isinstance(node.left, ast.Name) and node.left.id == "ROOT" and
                isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)):
            path = node.right.value
            rel = Path(path)
            need(not rel.is_absolute() and ".." not in rel.parts,
                 "UNSAFE_LITERAL_PROVENANCE_TARGET")
            target = ROOT / rel
            need(target.is_file() and not target.is_symlink(),
                 "MISSING_LITERAL_PROVENANCE_TARGET:" + path)
            paths.append(path)
    need(ACTUAL + "PREREGISTRATION.json" in paths and
         ACTUAL + "README.md" in paths, "ACTUAL_R5_DOCUMENTS_NOT_BOUND")
    return sorted(paths)


def verify_pair(parent: str, corrected: str, profile: dict) -> dict:
    need(corrected == expected_source(parent, profile),
         "CORRECTED_COLLECTOR_NOT_EXACT_DERIVATION")
    old, new = ast.parse(parent), ast.parse(corrected)
    need(len(old.body) == len(new.body), "TOP_LEVEL_SURFACE_CHANGED")
    metadata = {profile["source_function"], "self_test", "main"}
    preserved_functions = 0
    preserved_classes = 0
    for lhs, rhs in zip(old.body, new.body):
        need(type(lhs) is type(rhs), "TOP_LEVEL_KIND_CHANGED")
        if isinstance(lhs, ast.FunctionDef):
            need(lhs.name == rhs.name, "FUNCTION_ORDER_CHANGED")
            # The exact replacement list cannot change headers or add code
            # outside the explicitly reviewed metadata-function bodies.
            if lhs.name not in metadata:
                need(ast.get_source_segment(parent, lhs) ==
                     ast.get_source_segment(corrected, rhs),
                     "SCIENTIFIC_FUNCTION_CHANGED:" + lhs.name)
                preserved_functions += 1
        elif isinstance(lhs, ast.ClassDef):
            need(ast.get_source_segment(parent, lhs) ==
                 ast.get_source_segment(corrected, rhs), "BUDGET_OR_CLASS_CHANGED")
            preserved_classes += 1
    need(preserved_functions == profile["unchanged_scientific_functions"] and
         preserved_classes == profile["unchanged_classes"],
         "SCIENTIFIC_DERIVATION_COVERAGE_CHANGED")
    paths = literal_provenance(corrected, profile["source_function"])
    return {"kind": profile["kind"], "unchanged_scientific_functions": preserved_functions,
            "unchanged_classes": preserved_classes, "literal_provenance_files": paths,
            "corrected_collector_blob": profile["corrected_identity"]["git_blob_sha1"]}


def verify_sources() -> dict:
    plan = plan_record()
    review = plan["historical_review"]
    check_identity(bounded(review["path"]), review, review["path"])
    for row in plan["provenance"]:
        check_identity(bounded(row["path"]), row, row["path"])
    # This exact pinned historical module contains source/AST checks only.
    import fe09_b3_f0_r5_derivation_contract as historical
    historical_result = historical.verify_sources()
    reports = []
    for profile in plan["collectors"]:
        old = bounded(profile["parent_path"])
        new = bounded(profile["corrected_path"])
        check_identity(old, profile["parent_identity"], profile["parent_path"])
        check_identity(new, profile["corrected_identity"], profile["corrected_path"])
        reports.append(verify_pair(old.decode("utf-8"), new.decode("utf-8"), profile))
    return {"status": "R5_PATH_R1_EXACT_SOURCE_DERIVATION_VERIFIED_NO_DSP",
            "collectors": reports, "historical_r5_review": historical_result["status"],
            "new_receipt_namespace": "R5-PATH-R1", "dsp_frames": 0,
            "science_executed": False, "shipping_authority": False}


def replace_once(source: str, before: str, after: str) -> str:
    need(source.count(before) == 1, "NEGATIVE_SITE_NOT_UNIQUE")
    return source.replace(before, after, 1)


def expect_rejected(action, reason: str) -> None:
    try:
        action()
    except Rejected as error:
        need(str(error) == reason, "WRONG_NEGATIVE_REJECTION:" + str(error))
    else:
        raise Rejected("NEGATIVE_ACCEPTED:" + reason)


def self_test() -> dict:
    result = verify_sources()
    plan = plan_record()
    negatives = 0
    missing_targets = 0
    for profile in plan["collectors"]:
        old = bounded(profile["parent_path"]).decode("utf-8")
        new = bounded(profile["corrected_path"]).decode("utf-8")
        wrong_json = replace_once(new, ACTUAL + "PREREGISTRATION.json",
                                  MISSING + "PREREGISTRATION.json")
        wrong_readme = replace_once(new, ACTUAL + "README.md", MISSING + "README.md")
        first_namespace = profile["namespace_names"][0] + " = "
        before = next(line for line in old.splitlines() if line.startswith(first_namespace))
        after = next(line for line in new.splitlines() if line.startswith(first_namespace))
        old_namespace = replace_once(new, after, before)
        scientific_mutation = replace_once(
            new, "def schedule() -> list[dict]:\n",
            "def schedule() -> list[dict]:\n    pass\n")
        for mutated in (old, wrong_json, wrong_readme, old_namespace,
                        scientific_mutation, new + "\nimport socket\n"):
            expect_rejected(lambda value=mutated: verify_pair(old, value, profile),
                            "CORRECTED_COLLECTOR_NOT_EXACT_DERIVATION")
            negatives += 1
        for mutated, path in ((wrong_json, MISSING + "PREREGISTRATION.json"),
                              (wrong_readme, MISSING + "README.md")):
            expect_rejected(
                lambda value=mutated: literal_provenance(value, profile["source_function"]),
                "MISSING_LITERAL_PROVENANCE_TARGET:" + path)
            missing_targets += 1
    import fe09_b3_f0_r5_derivation_contract as historical
    previous = historical.self_test()
    old_negatives = (previous["negative_source_mutations_rejected"] +
                     previous["negative_b3_identity_controls_rejected"] +
                     previous["negative_f0_identity_and_timing_controls_rejected"])
    need(negatives == 12 and missing_targets == 4 and old_negatives == 45,
         "METADATA_NEGATIVE_COVERAGE_CHANGED")
    result.update(status="R5_PATH_R1_METADATA_SELF_TEST_PASS_NO_DSP",
                  new_source_mutations_rejected=negatives,
                  missing_literal_targets_rejected=missing_targets,
                  preserved_r5_derivation_negatives=old_negatives,
                  thresholds_or_budgets_relaxed=False)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(self_test() if args.self_test else verify_sources(), sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError, KeyError, TypeError, SyntaxError) as error:
        print("R5_PATH_R1_SOURCE_REVIEW_REJECTED:" + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
