#!/usr/bin/env python3
"""Independent exact R5 collector derivation review; source and metadata only.

No compiler, DSP process, measured receipt or shipping qualification is created.
The corrected R2 F0 parent is the T3-reviewed 065cce object, not the obsolete
pre-T3 object retained by the immutable historical T2 review.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
R2_DOCS = "docs/research/frontend-evolution-v1/FE09_B3_F0_FORWARD_SOURCE_R2_20261025/"
R5_GATE = REL + "fe09_b3_f0_r5_source_admission.py"
R5_GATE_BLOB = "1839ca3271e7006abcf4c132a12fb7b1683a3696"
DRIVER = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1"
HISTORICAL_PINS = {
    REL + "fe09_b3_f0_r2_source_admission.py":
        "6b9e9e5e3e044aa586420be3b3aadd229a90b67f",
    REL + "fe09_b3_f0_r2_t2_derivation_contract.py":
        "d0965732f7656dcc1c782e3813c6c32d5d9af2f5",
    REL + "fe09_t3s3_f0_r2_t3_timing_identity_contract.py":
        "e07ba55b9e2836aea2beb55d7dec855d9d7667f8",
    REL + "fe09_b3_f0_deadline_r1_qualification.py":
        "54dab4274df8044dbbd23bf05ef169bd21123c74",
    REL + "fe09_t3s3_f0_call_resource_qualification.py":
        "e22cc4f0eede6e844b985e0bece8e9dcbf2e02cd",
    REL + "fe09_b3_f0_qualification.py":
        "f6be51a0831ab96ef1284d706a6f1d167b538b51",
    REL + "fe09_t3s3_f0_call_resource_probe.c":
        "01e26892f18e5c64a7c74448817ed6c22e693bd7",
    R2_DOCS + "PREREGISTRATION.json": "7ed23487462d0a011a06255d1886eccfec385a63",
    R2_DOCS + "T2_EXECUTOR_SOURCE_REVIEW.json": "824e719aa30ce72130cf7f465eada1707280942f",
    R2_DOCS + "T3_TIMING_IDENTITY_SOURCE_REVIEW.json": "cb8c172e50db4928e4053102218783f51e42b702",
    "docs/research/frontend-evolution-v1/FE09_B3_F0_PREREGISTRATION_20261024/source-lock.json":
        "a509554e38e1c5db5daeb6623da1b9201169a55d",
    "docs/research/frontend-evolution-v1/FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/source-lock.json":
        "54278f28e9e61c2714d0fc0581b9f6e915c9f368",
}
SOURCES = {
    "b3": {
        "parent": "fe09_b3_f0_deadline_r2_qualification.py",
        "parent_blob": "d94fa5ffc568945a5ee2a92d2f8761ec7df0c91c",
        "forward": "fe09_b3_f0_deadline_r5_qualification.py",
        "forward_blob": "43e69899c83e59bb8e3c7f9336664128795e0e9c",
        "metadata_functions": {"source_preflight", "self_test", "main"},
        "unchanged_functions": 39,
        "unchanged_classes": 3,
        "own_assignment": "OWN_FILES",
        "identities": {
            "COLLECTOR_IDENTITY": "FE09-B3-F0-C4-16K-RENDER-PAP-FORWARD-SOURCE-R5",
            "QUALIFIED": "FE09_B3_F0_FORWARD_SOURCE_R5_C4_16K_RENDER_PAP_FINITE_RESEARCH_NO_PROMOTION",
            "LOCAL": "FE09_B3_F0_FORWARD_SOURCE_R5_LOCAL_PARTIAL_TARGETS_NO_FULL_QUALIFICATION",
            "INCONCLUSIVE": "FE09_B3_F0_FORWARD_SOURCE_R5_FIXED_COVERAGE_INCONCLUSIVE",
            "FAILED": "FE09_B3_F0_FORWARD_SOURCE_R5_COMPOSITION_REJECTED_WITH_EVIDENCE",
            "BLOCKED": "FE09_B3_F0_FORWARD_SOURCE_R5_EXECUTION_BLOCKED",
        },
    },
    "f0": {
        "parent": "fe09_t3s3_f0_call_resource_r2_qualification.py",
        "parent_blob": "065cce6349842876b01ec3e410e2958bfa55eeab",
        "forward": "fe09_t3s3_f0_call_resource_r5_qualification.py",
        "forward_blob": "2d8c9c62cb7586f5c534c08a0ea7341b782c8528",
        "metadata_functions": {"source_record", "self_test", "main"},
        "unchanged_functions": 33,
        "unchanged_classes": 1,
        "own_assignment": "OWN",
        "identities": {
            "IDENTITY": "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-FORWARD-SOURCE-R5",
            "DECISION": "FE09_T3S3_F0_FORWARD_SOURCE_R5_ACTUAL_CALL_RESOURCE_NO_DEVICE_PROMOTION",
            "PARTIAL": "FE09_T3S3_F0_FORWARD_SOURCE_R5_LOCAL_PARTIAL_NO_PROMOTION",
            "FAILED": "FE09_T3S3_F0_FORWARD_SOURCE_R5_RESOURCE_REJECTED_WITH_EVIDENCE",
        },
    },
}


class Rejected(ValueError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise Rejected(reason)


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def check_blob(raw: bytes, expected: str, path: str) -> None:
    need(git_blob(raw) == expected, "BOUND_SOURCE_GIT_BLOB_CHANGED:" + path)


def pinned(path: str, expected: str) -> bytes:
    rel = Path(path)
    need(not rel.is_absolute() and ".." not in rel.parts, "UNSAFE_PINNED_PATH")
    file = ROOT / rel
    need(file.is_file() and not file.is_symlink() and
         0 < file.stat().st_size < 100000, "BOUND_SOURCE_REQUIRED:" + path)
    raw = file.read_bytes()
    check_blob(raw, expected, path)
    return raw


def assigned_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for item in node.elts for name in assigned_names(item)]
    return []


def source_tree(source: str) -> ast.Module:
    tree = ast.parse(source)
    bindings = set()
    for node in tree.body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [name for target in targets for name in assigned_names(target)]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [item.asname or item.name.split(".")[0] for item in node.names]
        for name in names:
            need(name not in bindings, "DUPLICATE_TOP_LEVEL_BINDING:" + name)
            bindings.add(name)
    return tree


def function_header(node: ast.AST) -> str:
    header = copy.deepcopy(node)
    header.body = []
    # Defaults, annotations and decorators can execute at definition time.
    # They remain exact even for the three reviewed metadata-only functions.
    return ast.dump(header, include_attributes=False)


def check_source_derivation(parent: str, forward: str, profile: dict) -> dict:
    old = source_tree(parent)
    new = source_tree(forward)
    need(len(old.body) == len(new.body), "TOP_LEVEL_STATEMENT_COUNT_CHANGED")
    functions, classes, globals_seen = set(), set(), set()
    preserved_functions = 0
    source_gate_imports = 0
    for index, (lhs, rhs) in enumerate(zip(old.body, new.body)):
        need(type(lhs) is type(rhs), "TOP_LEVEL_STATEMENT_KIND_CHANGED:" + str(index))
        before = ast.get_source_segment(parent, lhs)
        after = ast.get_source_segment(forward, rhs)
        if index == 0 and isinstance(lhs, ast.Expr):
            need(isinstance(lhs.value, ast.Constant) and isinstance(lhs.value.value, str) and
                 isinstance(rhs.value, ast.Constant) and isinstance(rhs.value.value, str),
                 "MODULE_DOCUMENTATION_REPLACED_BY_EXECUTION")
            continue
        if isinstance(lhs, (ast.FunctionDef, ast.AsyncFunctionDef)):
            need(lhs.name == rhs.name, "FUNCTION_ORDER_OR_SURFACE_CHANGED")
            functions.add(lhs.name)
            need(function_header(lhs) == function_header(rhs),
                 "FUNCTION_DEFINITION_EXECUTION_CHANGED:" + lhs.name)
            if lhs.name not in profile["metadata_functions"]:
                need(before == after, "SCIENCE_IMPLEMENTATION_CHANGED:" + lhs.name)
                preserved_functions += 1
        elif isinstance(lhs, ast.ClassDef):
            need(lhs.name == rhs.name and before == after and
                 ast.dump(lhs) == ast.dump(rhs), "CLASS_OR_BUDGET_CHANGED:" + lhs.name)
            classes.add(lhs.name)
        elif isinstance(lhs, (ast.Assign, ast.AnnAssign)):
            targets = lhs.targets if isinstance(lhs, ast.Assign) else [lhs.target]
            new_targets = rhs.targets if isinstance(rhs, ast.Assign) else [rhs.target]
            need([ast.dump(t) for t in targets] == [ast.dump(t) for t in new_targets],
                 "GLOBAL_ASSIGNMENT_SURFACE_CHANGED")
            names = [name for target in targets for name in assigned_names(target)]
            globals_seen.update(names)
            name = names[0] if len(names) == 1 else ",".join(names)
            if name in profile["identities"]:
                need(isinstance(rhs, ast.Assign) and len(rhs.targets) == 1 and
                     isinstance(rhs.targets[0], ast.Name) and
                     isinstance(rhs.value, ast.Constant) and
                     rhs.value.value == profile["identities"][name],
                     "R5_RECEIPT_NAMESPACE_CHANGED:" + name)
            elif name == profile["own_assignment"]:
                suffix = (' + [HERE / name for name in (\n    "' + profile["forward"] +
                          '", "fe09_b3_f0_r5_source_admission.py",\n'
                          '    "fe09_b3_f0_r5_source_delta_2_3_61.patch.b64")]')
                need(after == before + suffix, "REVIEWED_PROVENANCE_EXPRESSION_CHANGED")
            else:
                need(before == after, "GLOBAL_IDENTITY_OR_BUDGET_CHANGED:" + name)
        elif isinstance(lhs, (ast.Import, ast.ImportFrom)):
            if before == "import fe09_b3_f0_r2_source_admission as forward_source":
                need(after == "import fe09_b3_f0_r5_source_admission as forward_source",
                     "EXACT_R5_SOURCE_GATE_IMPORT_REQUIRED")
                source_gate_imports += 1
            else:
                need(before == after, "UNREVIEWED_TOP_LEVEL_IMPORT_CHANGED")
        else:
            # In particular, __main__ and any other executable top-level code
            # are included. A function-only allowlist would miss these nodes.
            need(before == after and ast.dump(lhs) == ast.dump(rhs),
                 "UNREVIEWED_TOP_LEVEL_EXECUTION_CHANGED")
    need(profile["metadata_functions"].issubset(functions) and
         set(profile["identities"]).issubset(globals_seen), "REVIEWED_SOURCE_SURFACE_MISSING")
    need(preserved_functions == profile["unchanged_functions"] and
         len(classes) == profile["unchanged_classes"], "EXACT_DERIVATION_COVERAGE_CHANGED")
    need(source_gate_imports == 1, "EXACTLY_ONE_R5_SOURCE_GATE_IMPORT_REQUIRED")
    return {"unchanged_function_bodies": preserved_functions,
            "unchanged_classes": len(classes),
            "reviewed_metadata_functions": sorted(profile["metadata_functions"]),
            "ordered_top_level_statements": len(old.body),
            "definition_time_execution_unchanged": True,
            "new_receipt_namespace": "R5"}


def verify_sources() -> dict:
    # Pins are owned by this independent review, never supplied by a collector.
    # Reading/AST-checking these files does not grant DSP execution authority.
    for path, expected in HISTORICAL_PINS.items():
        pinned(path, expected)
    pinned(R5_GATE, R5_GATE_BLOB)
    reports = {}
    for kind, profile in SOURCES.items():
        parent = pinned(REL + profile["parent"], profile["parent_blob"]).decode("utf-8")
        forward = pinned(REL + profile["forward"], profile["forward_blob"]).decode("utf-8")
        reports[kind] = check_source_derivation(parent, forward, profile)
    return {"status": "R5_SOURCE_DERIVATION_VERIFIED_NO_DSP_EXECUTION",
            "b3": reports["b3"], "f0": reports["f0"],
            "historical_source_pins": len(HISTORICAL_PINS),
            "corrected_t3_f0_parent": SOURCES["f0"]["parent_blob"],
            "science_executed": False, "shipping_authority": False}


def replace_once(source: str, before: str, after: str) -> str:
    need(source.count(before) == 1, "NEGATIVE_FIXTURE_SITE_NOT_UNIQUE:" + before)
    return source.replace(before, after, 1)


def expect_rejection(action, reason: str, name: str) -> None:
    try:
        action()
    except Rejected as exc:
        need(str(exc) == reason, "WRONG_NEGATIVE_REJECTION:" + name + ":" + str(exc))
    else:
        raise Rejected("INVALID_SOURCE_OR_METADATA_ACCEPTED:" + name)


def derivation_negatives(texts: dict) -> int:
    b3, f0 = texts["b3"][1], texts["f0"][1]
    fixtures = [
        ("b3", "schedule-body", replace_once(b3, "def schedule() -> list[dict]:\n",
             "def schedule() -> list[dict]:\n    pass\n"), "SCIENCE_IMPLEMENTATION_CHANGED:schedule"),
        ("b3", "frames", replace_once(b3, "FRAMES = 600", "FRAMES = 601"),
         "GLOBAL_IDENTITY_OR_BUDGET_CHANGED:FRAMES"),
        ("b3", "budget-class", replace_once(b3, "class Budget:\n", "class Budget:\n    pass\n"),
         "CLASS_OR_BUDGET_CHANGED:Budget"),
        ("b3", "collect", replace_once(b3, "def collect(args: argparse.Namespace) -> int:\n",
             "def collect(args: argparse.Namespace) -> int:\n    pass\n"), "SCIENCE_IMPLEMENTATION_CHANGED:collect"),
        ("b3", "extra-top-level-call", b3 + "\nprint('unreviewed')\n", "TOP_LEVEL_STATEMENT_COUNT_CHANGED"),
        ("b3", "extra-import", b3 + "\nimport socket\n", "TOP_LEVEL_STATEMENT_COUNT_CHANGED"),
        ("b3", "changed-import", replace_once(b3, "import time\n", "import time as timer\n"),
         "UNREVIEWED_TOP_LEVEL_IMPORT_CHANGED"),
        ("b3", "extra-global", b3 + "\nUNREVIEWED = 1\n", "TOP_LEVEL_STATEMENT_COUNT_CHANGED"),
        ("b3", "extra-function", b3 + "\ndef unreviewed():\n    return None\n",
         "TOP_LEVEL_STATEMENT_COUNT_CHANGED"),
        ("b3", "duplicate-function", b3 + "\ndef schedule():\n    return []\n",
         "DUPLICATE_TOP_LEVEL_BINDING:schedule"),
        ("b3", "metadata-default", replace_once(b3,
             "def source_preflight(execution_source: str, require_committed: bool = True)",
             "def source_preflight(execution_source: str, require_committed: bool = False)"),
         "FUNCTION_DEFINITION_EXECUTION_CHANGED:source_preflight"),
        ("b3", "metadata-decorator", replace_once(b3, "def self_test() -> None:\n",
             "@print\ndef self_test() -> None:\n"), "FUNCTION_DEFINITION_EXECUTION_CHANGED:self_test"),
        ("b3", "old-r2-receipt", replace_once(b3,
             'COLLECTOR_IDENTITY = "FE09-B3-F0-C4-16K-RENDER-PAP-FORWARD-SOURCE-R5"',
             'COLLECTOR_IDENTITY = "FE09-B3-F0-C4-16K-RENDER-PAP-FORWARD-SOURCE-R2"'),
         "R5_RECEIPT_NAMESPACE_CHANGED:COLLECTOR_IDENTITY"),
        ("b3", "unknown-provenance", replace_once(b3,
             '    "fe09_b3_f0_r5_source_delta_2_3_61.patch.b64")]',
             '    "fe09_b3_f0_r5_source_delta_2_3_61.patch.b64", "unreviewed.py")]'),
         "REVIEWED_PROVENANCE_EXPRESSION_CHANGED"),
        ("b3", "main-execution", replace_once(b3, "    raise SystemExit(main())\n",
             "    raise SystemExit(0)\n"), "UNREVIEWED_TOP_LEVEL_EXECUTION_CHANGED"),
        ("f0", "timing-identity-regression", replace_once(f0,
             'data["id"] == "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1"', 'data["id"] == IDENTITY'),
         "SCIENCE_IMPLEMENTATION_CHANGED:validate_timing"),
        ("f0", "percentile", replace_once(f0, '"p99_ns": ordered[593]', '"p99_ns": ordered[594]'),
         "SCIENCE_IMPLEMENTATION_CHANGED:statistics"),
        ("f0", "budget-class", replace_once(f0, "self.limit = 180.0", "self.limit = 181.0"),
         "CLASS_OR_BUDGET_CHANGED:Budget"),
        ("f0", "sanitizer-relaxation", replace_once(f0, "detect_leaks=1:abort_on_error=1",
             "detect_leaks=0:abort_on_error=1"), "GLOBAL_IDENTITY_OR_BUDGET_CHANGED:RUNTIME_ENV"),
        ("f0", "old-r2-receipt", replace_once(f0,
             'IDENTITY = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-FORWARD-SOURCE-R5"',
             'IDENTITY = "FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-FORWARD-SOURCE-R2"'),
         "R5_RECEIPT_NAMESPACE_CHANGED:IDENTITY"),
        ("f0", "verify", replace_once(f0,
             "def verify(output: Path, source: str, require_full: bool = True) -> dict:\n",
             "def verify(output: Path, source: str, require_full: bool = True) -> dict:\n    pass\n"),
         "SCIENCE_IMPLEMENTATION_CHANGED:verify"),
    ]
    for kind, name, changed, reason in fixtures:
        expect_rejection(lambda: check_source_derivation(texts[kind][0], changed, SOURCES[kind]),
                         reason, name)
    # A reviewed metadata-function whitelist does not grant arbitrary changes:
    # the complete collector is additionally bound to its independent Git pin.
    changed = replace_once(b3, "def self_test() -> None:\n", "def self_test() -> None:\n    pass\n")
    path = REL + SOURCES["b3"]["forward"]
    expect_rejection(lambda: check_blob(changed.encode(), SOURCES["b3"]["forward_blob"], path),
                     "BOUND_SOURCE_GIT_BLOB_CHANGED:" + path, "metadata-body-exact-pin")
    return len(fixtures) + 1


def selected_functions(source: str, names: set[str], scope: dict) -> dict:
    nodes = [node for node in source_tree(source).body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    need({node.name for node in nodes} == names, "METADATA_VALIDATOR_FUNCTIONS_MISSING")
    # Only exact pinned, unchanged pure validation functions are compiled here.
    # Collect/build/run functions and the source module's top-level code are not.
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])),
                 "<pinned-r5-metadata-validator>", "exec"), scope)
    return scope


def b3_identity_negatives(source: str) -> int:
    scope = {"need": need, "IDENTITY": "FE09-B3-F0-C4-16K-RENDER-PAP-V1",
             "COLLECTOR_IDENTITY": SOURCES["b3"]["identities"]["COLLECTOR_IDENTITY"],
             "ROLE": "D0_FIRST_PARTY_DISCLOSED_SYNTHETIC_ENGINEERING",
             "PROMOTIONS": {key: False for key in ("public_sdk", "acoustic_superiority",
                            "physical_clock", "ssc305", "full_resource_budget", "shipping")}}
    selected_functions(source, {"validate_case_identity", "validate_collector_identity"}, scope)
    case = {"schema_version": 1, "id": scope["IDENTITY"], "source_role": scope["ROLE"]}
    receipt = {"id": scope["COLLECTOR_IDENTITY"], "execution_source": "1" * 40,
               "source_role": scope["ROLE"], "promotion": copy.deepcopy(scope["PROMOTIONS"])}
    scope["validate_case_identity"](case)
    scope["validate_collector_identity"](receipt, "1" * 40)
    trials = [
        ("old-r2-receipt", lambda r: r.update(id=r["id"].replace("-R5", "-R2"))),
        ("old-r3-receipt", lambda r: r.update(id=r["id"].replace("-R5", "-R3"))),
        ("old-r4-receipt", lambda r: r.update(id=r["id"].replace("-R5", "-R4"))),
        ("driver-as-receipt", lambda r: r.update(id=scope["IDENTITY"])),
        ("wrong-source", lambda r: r.update(execution_source="2" * 40)),
        ("shipping-promotion", lambda r: r["promotion"].update(shipping=True)),
    ]
    for name, mutate in trials:
        changed = copy.deepcopy(receipt)
        mutate(changed)
        expect_rejection(lambda: scope["validate_collector_identity"](changed, "1" * 40),
                         "RETAINED_SOURCE_OR_AUTHORITY", "b3-" + name)
    changed = {**case, "id": scope["COLLECTOR_IDENTITY"]}
    expect_rejection(lambda: scope["validate_case_identity"](changed),
                     "CASE_IDENTITY_OR_SOURCE_ROLE", "b3-receipt-as-driver")
    return len(trials) + 1


def f0_identity_negatives(source: str) -> int:
    scope = selected_functions(source, {"duration", "statistics", "validate_timing"}, {"need": need})
    call = {"calls": 1, "status": 0, "cpu_ns": 100, "wall_ns": 200}
    sample = {"schema_version": 1, "id": DRIVER, "case": "ALL_P", "failed": 0,
              "completed_frames": 600, "clock_cpu": "CLOCK_THREAD_CPUTIME_ID",
              "clock_wall": "CLOCK_MONOTONIC", "cpu_resolution_ns": 1,
              "wall_resolution_ns": 1, "timing_storage_bytes": 32768, "bind": call,
              "frames": [{"seq": n, "event": 1, "capture": call, "render": call, "worker": call}
                         for n in range(1, 601)]}
    fn = scope["validate_timing"]
    result = fn(sample, "ALL_P")
    need(result["combined_cpu_ns"]["sum_ns"] == 180000 and
         result["combined_wall_ns"]["sum_ns"] == 360000, "ORIGINAL_DRIVER_CONTROL_REJECTED")
    receipt_id = SOURCES["f0"]["identities"]["IDENTITY"]
    trials = [
        ("r5-receipt-as-driver", lambda d: d.update(id=receipt_id), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("r2-receipt-as-driver", lambda d: d.update(id=receipt_id.replace("-R5", "-R2")), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("r3-receipt-as-driver", lambda d: d.update(id=receipt_id.replace("-R5", "-R3")), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("r4-receipt-as-driver", lambda d: d.update(id=receipt_id.replace("-R5", "-R4")), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("unknown-driver", lambda d: d.update(id="unreviewed"), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("wrong-case", lambda d: d.update(case="PAP"), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("short-run", lambda d: d.update(completed_frames=599), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("failed-run", lambda d: d.update(failed=1), "TIMING_RUN_IDENTITY_OR_COMPLETENESS"),
        ("missing-frame", lambda d: d["frames"].pop(), "TIMING_FRAME_COUNT"),
        ("frame-order", lambda d: d["frames"][0].update(seq=2), "TIMING_FRAME_OR_RENDER_ORDER"),
        ("negative-ns", lambda d: d["frames"][0]["worker"].update(cpu_ns=-1), "NONNEGATIVE_INTEGER_DURATION"),
        ("clock-authority", lambda d: d.update(clock_cpu="CLOCK_PROCESS_CPUTIME_ID"), "TIMING_CLOCK_AUTHORITY"),
    ]
    for name, mutate, reason in trials:
        changed = copy.deepcopy(sample)
        mutate(changed)
        expect_rejection(lambda: fn(changed, "ALL_P"), reason, "f0-" + name)
    # Exercise the actual, unchanged receipt-authority expression without
    # importing the collector, opening an artifact, or invoking a source gate.
    verify = next(node for node in source_tree(source).body
                  if isinstance(node, ast.FunctionDef) and node.name == "verify")
    checks = [node for node in verify.body if isinstance(node, ast.Expr) and
              isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and
              node.value.func.id == "need" and len(node.value.args) == 2 and
              isinstance(node.value.args[1], ast.Constant) and
              node.value.args[1].value == "RETAINED_SOURCE_OR_AUTHORITY"]
    need(len(checks) == 1, "F0_RECEIPT_AUTHORITY_CHECK_MISSING")
    expression = compile(ast.fix_missing_locations(ast.Expression(body=checks[0].value.args[0])),
                         "<pinned-r5-receipt-authority>", "eval")
    plan = {"promotion": {"shipping": False}, "unmeasured": ["device"]}
    receipt = {"id": receipt_id, "source": {"synthetic_control": True},
               "predecessor": {"synthetic_control": True}, "promotion": plan["promotion"],
               "unmeasured": plan["unmeasured"], "failure": None}
    authority = {"r": receipt, "IDENTITY": receipt_id, "source": "1" * 40,
                 "source_record": lambda _: {"synthetic_control": True},
                 "predecessor": lambda: {"synthetic_control": True}, "plan": plan}
    need(eval(expression, authority), "F0_R5_RECEIPT_CONTROL_REJECTED")
    for wrong in (receipt_id.replace("-R5", "-R2"), receipt_id.replace("-R5", "-R3"),
                  receipt_id.replace("-R5", "-R4"), DRIVER):
        authority["r"] = {**receipt, "id": wrong}
        need(eval(expression, authority) is False, "F0_WRONG_RECEIPT_IDENTITY_ACCEPTED")
    return len(trials) + 4


def self_test() -> dict:
    result = verify_sources()
    texts = {kind: (pinned(REL + spec["parent"], spec["parent_blob"]).decode("utf-8"),
                    pinned(REL + spec["forward"], spec["forward_blob"]).decode("utf-8"))
             for kind, spec in SOURCES.items()}
    result["negative_source_mutations_rejected"] = derivation_negatives(texts)
    result["negative_b3_identity_controls_rejected"] = b3_identity_negatives(texts["b3"][1])
    result["negative_f0_identity_and_timing_controls_rejected"] = f0_identity_negatives(texts["f0"][1])
    need(result["negative_source_mutations_rejected"] == 22 and
         result["negative_b3_identity_controls_rejected"] == 7 and
         result["negative_f0_identity_and_timing_controls_rejected"] == 16,
         "SOURCE_OR_METADATA_NEGATIVE_COVERAGE_CHANGED")
    result["status"] = "R5_SOURCE_DERIVATION_SELF_TEST_PASS_NO_DSP_EXECUTION"
    result["synthetic_metadata_controls_only"] = True
    result["dsp_frames_executed"] = 0
    result["scientific_evidence_created"] = False
    result["thresholds_or_budgets_relaxed"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(self_test() if args.self_test else verify_sources(), sort_keys=True))
        return 0
    except (Rejected, OSError, ValueError, SyntaxError, KeyError, TypeError) as exc:
        print("R5_SOURCE_DERIVATION_REJECTED:" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
