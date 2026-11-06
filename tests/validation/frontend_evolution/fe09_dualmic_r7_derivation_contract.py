#!/usr/bin/env python3
"""Source-only review of 2.3.63 identity derivatives; never execute DSP."""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
PLAN = "docs/research/frontend-evolution-v1/DUALMIC_2363_SOURCE_R7_20261106/DERIVATION.json"
PLAN_BLOB = 'cd217fa5df80fedc933ff502a4881579178b3059'

# These are literal receipt identities, not permission to edit build_only().
# Both the source pair and the one initial status dictionary entry are fixed.
LITERAL_IDENTITY_FUNCTIONS = {
    "F1 build": {
        "parent_path": "tests/validation/frontend_evolution/fe09_f1_r3_build.py",
        "child_path": "tests/validation/frontend_evolution/fe09_f1_r4_build.py",
        "rules": [{"function": "build_only", "assignment": "report", "key": "status",
                   "before": "F1_R3_T1_BUILD_REJECTED", "after": "F1_R4_T1_BUILD_REJECTED",
                   "occurrences": 1}],
    },
    "A3 static": {
        "parent_path": "tests/validation/frontend_evolution/fe09_a3_r3_static_build.py",
        "child_path": "tests/validation/frontend_evolution/fe09_a3_r4_static_build.py",
        "rules": [{"function": "build_only", "assignment": "receipt", "key": "status",
                   "before": "A3_R3_T1_STATIC_BUILD_REJECTED",
                   "after": "A3_R4_T1_STATIC_BUILD_REJECTED", "occurrences": 1}],
    },
}


class Rejected(ValueError):
    pass


def need(value, reason: str) -> None:
    if not value:
        raise Rejected(reason)


def blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def literal_identity_rules(kind: str, parent_path: str, child_path: str) -> list:
    record = LITERAL_IDENTITY_FUNCTIONS.get(kind)
    if record is None:
        return []
    need((parent_path, child_path) == (record["parent_path"], record["child_path"]),
         "R7_LITERAL_IDENTITY_PAIR_DRIFT")
    return copy.deepcopy(record["rules"])


def initial_status_literal(function: ast.FunctionDef, rule: dict) -> ast.Constant:
    assignments = [node for node in function.body if isinstance(node, ast.Assign) and
                   len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and
                   node.targets[0].id == rule["assignment"]]
    reason = "R7_LITERAL_IDENTITY_SITE_DRIFT:" + function.name
    need(len(assignments) == 1 and isinstance(assignments[0].value, ast.Dict), reason)
    dictionary = assignments[0].value
    values = [value for key, value in zip(dictionary.keys, dictionary.values)
              if isinstance(key, ast.Constant) and key.value == rule["key"]]
    need(len(values) == 1 and isinstance(values[0], ast.Constant) and
         isinstance(values[0].value, str), reason)
    return values[0]


def function_source_region(source: str, function: ast.FunctionDef) -> str:
    # AST end positions omit a trailing comment, including one after return.
    # Include complete lines through the next top-level node so such bytes do
    # not become an accidental escape hatch for a registered replacement.
    nodes = ast.parse(source).body
    positions = [index for index, node in enumerate(nodes)
                 if isinstance(node, ast.FunctionDef) and node.name == function.name and
                 node.lineno == function.lineno]
    need(len(positions) == 1, "R7_LITERAL_IDENTITY_FUNCTION_BOUNDARY")
    index = positions[0]
    lines = source.splitlines(keepends=True)
    start = min([function.lineno] + [node.lineno for node in function.decorator_list]) - 1
    stop = len(lines)
    if index + 1 < len(nodes):
        following = nodes[index + 1]
        stop = min([following.lineno] +
                   [node.lineno for node in getattr(following, "decorator_list", ())]) - 1
    return "".join(lines[start:stop])


def verify_literal_identity_function(parent: str, child: str, old: ast.FunctionDef,
                                     new: ast.FunctionDef, rule: dict) -> None:
    reason = "R7_LITERAL_IDENTITY_FUNCTION_CHANGED:" + rule["function"]
    need(old.name == new.name == rule["function"] and rule["occurrences"] == 1, reason)
    old_literal = initial_status_literal(old, rule)
    new_literal = initial_status_literal(new, rule)
    need(old_literal.value == rule["before"] and new_literal.value == rule["after"], reason)
    expected = copy.deepcopy(old)
    initial_status_literal(expected, rule).value = rule["after"]
    need(ast.dump(expected, include_attributes=False) == ast.dump(new, include_attributes=False),
         reason)
    # Preserve all remaining function bytes, including comments, whitespace,
    # quoting and numeric spelling. The one source token must be unambiguous.
    before_token = ast.get_source_segment(parent, old_literal)
    before_function = function_source_region(parent, old)
    after_function = function_source_region(child, new)
    need(before_token.count(rule["before"]) == 1 and
         before_function.count(before_token) == 1, reason)
    after_token = before_token.replace(rule["before"], rule["after"], 1)
    need(ast.get_source_segment(child, new_literal) == after_token and
         before_function.replace(before_token, after_token, 1) == after_function, reason)


def read(path: str) -> bytes:
    rel = Path(path)
    need(not rel.is_absolute() and ".." not in rel.parts, "R7_UNSAFE_SOURCE_PATH")
    target = ROOT / rel
    need(target.is_file() and not target.is_symlink() and
         0 < target.stat().st_size < 262144, "R7_SOURCE_FILE_BOUND:" + path)
    return target.read_bytes()


def pinned(path: str, value: dict) -> bytes:
    raw = read(path)
    need(blob(raw) == value["git_blob_sha1"] and len(raw) == value["bytes"] and
         hashlib.sha256(raw).hexdigest() == value["sha256"], "R7_SOURCE_PIN_DRIFT:" + path)
    return raw


def plan_record() -> dict:
    raw = read(PLAN)
    need(blob(raw) == PLAN_BLOB, "R7_DERIVATION_PLAN_DRIFT")
    value = json.loads(raw)
    need(value["identity"] == "FE09-DUALMIC-2363-IDENTITY-DERIVATION-V1" and
         value["science_executed"] is False and
         value["quality_thresholds_or_budgets_relaxed"] is False and
         len(value["pairs"]) == 5 and value["identity_only_functions"] == 2,
         "R7_DERIVATION_SCOPE")
    return value


def verify_pair(parent: str, child: str, profile: dict) -> dict:
    rules = literal_identity_rules(profile["kind"], profile["parent_path"], profile["child_path"])
    need(profile["literal_identity_functions"] == rules and
         profile["identity_only_functions"] == len(rules), "R7_LITERAL_IDENTITY_SCOPE_DRIFT")
    need("build_only" not in profile["metadata_functions"],
         "R7_LITERAL_IDENTITY_METADATA_ESCALATION")
    by_name = {rule["function"]: rule for rule in rules}
    expected = parent
    for item in profile["replacements"]:
        need(expected.count(item["before"]) == item["occurrences"] and
             item["occurrences"] > 0, "R7_TRANSFORM_SITE_COUNT")
        expected = expected.replace(item["before"], item["after"])
    need(child == expected, "R7_NOT_EXACT_SOURCE_DERIVATION")
    old, new = ast.parse(parent), ast.parse(child)
    need(len(old.body) == len(new.body), "R7_TOP_LEVEL_SURFACE_CHANGED")
    preserved_functions = preserved_classes = identity_functions = 0
    changed = set()
    for a, b in zip(old.body, new.body):
        need(type(a) is type(b), "R7_TOP_LEVEL_KIND_CHANGED")
        if isinstance(a, ast.FunctionDef) and a.name in by_name:
            verify_literal_identity_function(parent, child, a, b, by_name[a.name])
            identity_functions += 1
            changed.add("literal_identity_function:" + a.name)
            continue
        if ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False):
            if isinstance(a, ast.FunctionDef):
                # Also preserve literal source, including numeric spellings.
                need(ast.get_source_segment(parent, a) == ast.get_source_segment(child, b),
                     "R7_UNCHANGED_FUNCTION_BYTES_CHANGED:" + a.name)
                preserved_functions += 1
            elif isinstance(a, ast.ClassDef):
                need(ast.get_source_segment(parent, a) == ast.get_source_segment(child, b),
                     "R7_PROCESS_OR_BUDGET_CLASS_CHANGED:" + a.name)
                preserved_classes += 1
            continue
        if isinstance(a, ast.FunctionDef):
            need(a.name == b.name and a.name in profile["metadata_functions"],
                 "R7_SCIENCE_FUNCTION_CHANGED:" + a.name)
            changed.add("function:" + a.name)
        elif isinstance(a, ast.Assign):
            need(len(a.targets) == len(b.targets) == 1 and
                 isinstance(a.targets[0], ast.Name) and isinstance(b.targets[0], ast.Name) and
                 a.targets[0].id == b.targets[0].id and
                 a.targets[0].id in profile["identity_assignments"],
                 "R7_NONIDENTITY_CONSTANT_CHANGED")
            changed.add("assignment:" + a.targets[0].id)
        elif isinstance(a, (ast.Import, ast.ImportFrom)):
            need(ast.get_source_segment(parent, a) in profile["identity_imports"],
                 "R7_NONIDENTITY_IMPORT_CHANGED")
            changed.add("import:" + ast.get_source_segment(parent, a))
        else:
            need(isinstance(a, ast.Expr) and isinstance(a.value, ast.Constant) and
                 isinstance(a.value.value, str) and old.body[0] is a,
                 "R7_EXECUTABLE_TOP_LEVEL_CHANGED")
            changed.add("docstring")
    need(sorted(changed) == profile["changed_nodes"] and
         preserved_functions == profile["unchanged_functions"] and
         identity_functions == profile["identity_only_functions"] and
         preserved_classes == profile["unchanged_classes"], "R7_DERIVATION_COVERAGE")
    return {"kind": profile["kind"], "unchanged_functions": preserved_functions,
            "unchanged_classes": preserved_classes, "identity_only_functions": identity_functions,
            "changed_identity_nodes": sorted(changed)}


def verify_sources() -> dict:
    plan = plan_record()
    for path, identity in plan["dependencies"].items():
        pinned(path, identity)
    import fe09_dualmic_r6_derivation_contract as historical
    old = historical.verify_sources()
    reports = []
    for pair in plan["pairs"]:
        parent = pinned(pair["parent_path"], pair["parent_identity"]).decode()
        child = pinned(pair["child_path"], pair["child_identity"]).decode()
        reports.append(verify_pair(parent, child, pair))
    need(sum(report["identity_only_functions"] for report in reports) ==
         plan["identity_only_functions"], "R7_LITERAL_IDENTITY_TOTAL_DRIFT")
    return {"status": "R7_EXACT_IDENTITY_DERIVATION_VERIFIED_NO_DSP", "pairs": reports,
            "identity_only_functions": plan["identity_only_functions"],
            "preserved_r6_review": old["status"], "science_executed": False,
            "quality_thresholds_or_budgets_relaxed": False}


def literal_function_negatives(parent: str, child: str, profile: dict) -> int:
    """An exact transform table must not authorize edits to build logic."""
    count = 0
    for rule in profile["literal_identity_functions"]:
        function = next(node for node in ast.parse(child).body
                        if isinstance(node, ast.FunctionDef) and node.name == rule["function"])
        before = ast.get_source_segment(child, function)
        line = before.index("\n")
        for insertion in ("    pass\n", "    if True:\n        return {}\n"):
            after = before[:line + 1] + insertion + before[line + 1:]
            wrong = child.replace(before, after, 1)
            expanded = dict(profile, replacements=[*profile["replacements"],
                            {"before": before, "after": after, "occurrences": 1}])
            try:
                verify_pair(parent, wrong, expanded)
            except Rejected as error:
                need(str(error) == "R7_LITERAL_IDENTITY_FUNCTION_CHANGED:" + function.name,
                     "R7_WRONG_LITERAL_FUNCTION_NEGATIVE")
                count += 1
            else:
                raise Rejected("R7_LITERAL_FUNCTION_MUTATION_ACCEPTED")
    return count


def method_self_test() -> dict:
    """Small constructed sources only: no plan, build tools or DSP execution."""
    negatives = 0
    for kind, record in LITERAL_IDENTITY_FUNCTIONS.items():
        rule = record["rules"][0]
        parent = ('def build_only(root, output):\n'
                  '    # preserve the bounded build body\n'
                  '    ' + rule["assignment"] + ' = {"status": "' + rule["before"] + '"}\n'
                  '    deadline = 480\n'
                  '    return ' + rule["assignment"] + '\n')
        child = parent.replace(rule["before"], rule["after"])
        profile = {"kind": kind, "parent_path": record["parent_path"],
                   "child_path": record["child_path"], "metadata_functions": [],
                   "identity_assignments": [], "identity_imports": [],
                   "literal_identity_functions": copy.deepcopy(record["rules"]),
                   "identity_only_functions": 1, "unchanged_functions": 0, "unchanged_classes": 0,
                   "changed_nodes": ["literal_identity_function:build_only"],
                   "replacements": [{"before": rule["before"], "after": rule["after"],
                                     "occurrences": 1}]}
        need(verify_pair(parent, child, profile)["identity_only_functions"] == 1,
             "R7_LITERAL_METHOD_POSITIVE")
        negatives += literal_function_negatives(parent, child, profile)
        # Also reject a changed budget or even a comment when explicitly
        # enumerated by a mistaken exact replacement table.
        for before, after in (("deadline = 480", "deadline = 481"),
                              ("# preserve the bounded build body", "# changed comment"),
                              ("    return " + rule["assignment"] + "\n",
                               "    return " + rule["assignment"] +
                               "\n    # changed trailing comment\n")):
            expanded = dict(profile, replacements=[*profile["replacements"],
                            {"before": before, "after": after, "occurrences": 1}])
            try:
                verify_pair(parent, child.replace(before, after), expanded)
            except Rejected as error:
                need(str(error) == "R7_LITERAL_IDENTITY_FUNCTION_CHANGED:build_only",
                     "R7_WRONG_LITERAL_BYTES_NEGATIVE")
                negatives += 1
            else:
                raise Rejected("R7_LITERAL_NONSTATUS_MUTATION_ACCEPTED")
        try:
            verify_pair(parent, child, dict(profile, metadata_functions=["build_only"]))
        except Rejected as error:
            need(str(error) == "R7_LITERAL_IDENTITY_METADATA_ESCALATION",
                 "R7_WRONG_METADATA_ESCALATION_NEGATIVE")
            negatives += 1
        else:
            raise Rejected("R7_LITERAL_METADATA_ESCALATION_ACCEPTED")
    need(negatives == 12, "R7_LITERAL_METHOD_NEGATIVE_COVERAGE")
    return {"status": "R7_LITERAL_IDENTITY_METHOD_SELF_TEST_PASS_NO_DSP",
            "constructed_source_pairs": 2, "negative_cases": negatives,
            "registered_sources_verified": False, "science_executed": False}


def self_test() -> dict:
    result = verify_sources()
    count = 0
    for pair in plan_record()["pairs"]:
        parent = read(pair["parent_path"]).decode()
        child = read(pair["child_path"]).decode()
        for wrong in (parent, child + "\nimport socket\n", child + "\n# unregistered change\n"):
            try:
                verify_pair(parent, wrong, pair)
            except Rejected as error:
                need(str(error) == "R7_NOT_EXACT_SOURCE_DERIVATION", "R7_WRONG_NEGATIVE_REASON")
                count += 1
            else:
                raise Rejected("R7_SOURCE_MUTATION_ACCEPTED")
        # Prove the semantic guard still rejects a scientific/process change
        # even when an erroneous transform list were to describe that change.
        tree = ast.parse(child)
        literal_names = {rule["function"] for rule in pair["literal_identity_functions"]}
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and
                        n.name not in pair["metadata_functions"] and n.name not in literal_names)
        before = ast.get_source_segment(child, function)
        line = before.index("\n")
        after = before[:line + 1] + "    pass\n" + before[line + 1:]
        wrong = child.replace(before, after, 1)
        expanded = dict(pair, replacements=[*pair["replacements"],
                        {"before": before, "after": after, "occurrences": 1}])
        try:
            verify_pair(parent, wrong, expanded)
        except Rejected as error:
            need(str(error) == "R7_SCIENCE_FUNCTION_CHANGED:" + function.name,
                 "R7_WRONG_SCIENCE_NEGATIVE")
            count += 1
        else:
            raise Rejected("R7_SCIENCE_MUTATION_ACCEPTED")
        count += literal_function_negatives(parent, child, pair)
    need(count == 24, "R7_SOURCE_NEGATIVE_COVERAGE")
    result.update(status="R7_DERIVATION_SELF_TEST_PASS_NO_DSP", new_source_negatives=count)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--method-self-test", action="store_true")
    args = parser.parse_args()
    try:
        result = (method_self_test() if args.method_self_test else
                  self_test() if args.self_test else verify_sources())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, SyntaxError) as error:
        print("R7_DERIVATION_REJECTED:" + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
