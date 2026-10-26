#!/usr/bin/env python3
"""Independent exact-source R2 T2 review. Offline only, ZERO B3/F0 DSP runs."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

# This immutable lineage is bound to source Git objects, not dynamically
# chosen by the R2 executor being checked. A change must be reviewed in a new
# protected source-registration PR before any subsequent science execution.
SOURCES = {
    "b3": {
        "parent": "fe09_b3_f0_deadline_r1_qualification.py",
        "parent_blob": "54dab4274df8044dbbd23bf05ef169bd21123c74",
        "forward": "fe09_b3_f0_deadline_r2_qualification.py",
        "forward_blob": "6de327ae6be30adc3870ac7a19dd506da19c2a38",
        "changed_functions": {"source_preflight", "self_test", "main"},
        "changed_assignments": {"COLLECTOR_IDENTITY", "QUALIFIED", "LOCAL", "INCONCLUSIVE",
                                "FAILED", "BLOCKED", "OWN_FILES"},
        "minimum_unchanged_functions": 35,
    },
    "f0": {
        "parent": "fe09_t3s3_f0_call_resource_qualification.py",
        "parent_blob": "e22cc4f0eede6e844b985e0bece8e9dcbf2e02cd",
        "forward": "fe09_t3s3_f0_call_resource_r2_qualification.py",
        "forward_blob": "52554d4dcc8550231bd2b5b44e97e53754db9b22",
        "changed_functions": {"check_locked_rows", "source_record", "self_test", "main"},
        "changed_assignments": {"IDENTITY", "DECISION", "PARTIAL", "FAILED", "OWN"},
        "minimum_unchanged_functions": 28,
    },
}


class Reject(ValueError):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise Reject(code)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def source_file(name: str, blob: str) -> str:
    need(name == Path(name).name and name.endswith(".py"), "UNTRUSTED_SOURCE_PATH")
    path = HERE / name
    need(path.is_file() and not path.is_symlink() and
         path.stat().st_size < 100000, "BOUND_SOURCE_REQUIRED:" + name)
    data = path.read_bytes()
    need(git_blob(data) == blob, "BOUND_SOURCE_GIT_BLOB_CHANGED:" + name)
    return data.decode("utf-8")


def source_nodes(contents: str) -> tuple[dict, dict, dict]:
    doc = ast.parse(contents)
    functions = {node.name: ast.get_source_segment(contents, node)
                 for node in doc.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    classes = {node.name: ast.get_source_segment(contents, node)
               for node in doc.body if isinstance(node, ast.ClassDef)}
    assignments = {}
    for node in doc.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        for name in names:
            need(name not in assignments, "DUPLICATE_TOP_LEVEL_ASSIGNMENT:" + name)
            assignments[name] = ast.get_source_segment(contents, node)
    need(bool(functions) and bool(assignments), "EMPTY_OR_INVALID_SCIENCE_SOURCE")
    return functions, classes, assignments


def check_source_derivation(parent: str, forward: str, profile: dict) -> dict:
    old_fn, old_cls, old_vars = source_nodes(parent)
    new_fn, new_cls, new_vars = source_nodes(forward)
    need(set(old_fn) == set(new_fn), "FUNCTION_SURFACE_CHANGED")
    need(set(old_cls) == set(new_cls) and old_cls == new_cls,
         "UNREVIEWED_CLASS_OR_BUDGET_CHANGED")
    need(set(old_vars) == set(new_vars), "GLOBAL_ASSIGNMENT_SURFACE_CHANGED")
    changed = profile["changed_functions"]
    need(set(changed).issubset(old_fn), "REVIEWED_FUNCTION_SET_MISSING")
    checked = 0
    for name in sorted(old_fn):
        if name in changed:
            continue
        need(old_fn[name] == new_fn[name], "SCIENCE_IMPLEMENTATION_CHANGED:" + name)
        checked += 1
    need(checked >= profile["minimum_unchanged_functions"],
         "IMMUTABLE_FUNCTION_COVERAGE_INSUFFICIENT")
    for name in sorted(old_vars):
        if name not in profile["changed_assignments"]:
            need(old_vars[name] == new_vars[name],
                 "UNREVIEWED_GLOBAL_IDENTITY_OR_BUDGET_CHANGED:" + name)
    need("forward_source.source_check(" in forward and
         "forward_source.self_test()" in forward,
         "INDEPENDENT_FORWARD_SOURCE_GATE_MISSING")
    return {"unchanged_function_bodies": checked,
            "reviewed_admission_or_receipt_functions": sorted(changed),
            "unmodified_classes": len(old_cls),
            "source_names_exact": True}


def self_test() -> dict:
    # R2-T1 itself is protected-main code; a T2 candidate cannot rewrite its
    # source gate and simultaneously bless a substituted R2 implementation.
    source_file("fe09_b3_f0_r2_source_admission.py",
                "6b9e9e5e3e044aa586420be3b3aadd229a90b67f")
    result = {}
    for name, profile in SOURCES.items():
        original = source_file(profile["parent"], profile["parent_blob"])
        forward = source_file(profile["forward"], profile["forward_blob"])
        result[name] = check_source_derivation(original, forward, profile)
    negative_count = 0
    b3 = SOURCES["b3"]
    original = source_file(b3["parent"], b3["parent_blob"])
    forward = source_file(b3["forward"], b3["forward_blob"])
    need("def schedule() -> list[dict]:\n" in forward and
         "FRAMES = 600" in forward, "FROZEN_NEGATIVE_FIXTURE_CHANGED")
    # These mutate real scientific source *in memory only*, never a Git blob,
    # build input, executable, response threshold or retained artifact.
    mutations = [
        (forward.replace("def schedule() -> list[dict]:\n",
                         "def schedule() -> list[dict]:\n    pass\n", 1),
         "SCIENCE_IMPLEMENTATION_CHANGED:schedule"),
        (forward.replace("FRAMES = 600", "FRAMES = 601", 1),
         "UNREVIEWED_GLOBAL_IDENTITY_OR_BUDGET_CHANGED:FRAMES"),
    ]
    for changed, reason in mutations:
        try:
            check_source_derivation(original, changed, b3)
        except Reject as exc:
            need(str(exc) == reason, "WRONG_NEGATIVE_REJECTION:" + str(exc))
            negative_count += 1
        else:
            raise Reject("R2_T2_MUTATED_SCIENCE_FALSE_ACCEPTED")
    need(negative_count == 2, "T2_SOURCE_NEGATIVES_INCOMPLETE")
    return {"status": "R2_T2_SOURCE_DERIVATION_SELF_TEST_PASS",
            "b3": result["b3"], "f0": result["f0"],
            "negative_science_mutations_rejected": negative_count,
            "dsp_executed": False, "shipping_authority": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("--self-test is required")
    try:
        print(json.dumps(self_test(), sort_keys=True))
        return 0
    except (Reject, ValueError, OSError, SyntaxError) as exc:
        print("R2_T2_SOURCE_DERIVATION_REJECTED:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
