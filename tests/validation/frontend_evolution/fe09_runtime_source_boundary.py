#!/usr/bin/env python3
"""Versioned current-source admission for six unchanged FE09 research runners.

Only three read-only historical identity functions see the reconstructed old
Runtime. The original target compilers, source paths, scientific validators,
source_head and execution SHA always use the actual current worktree. The
original runners remain byte-for-byte available for their historical sources.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import functools
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import fe09_runtime_maintenance_rebind as maintenance

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = "e3672ffe16e4c9d42a100e7712b9bbd3d8338545"
RUNTIME = "src/platform/linux/ap_runtime.c"
STAGES = {
    "s1": "fe09_b2s1_private_queue_qualification",
    "s2": "fe09_b2s2_private_apd_qualification",
    "s3": "fe09_b2s3_threaded_qualification",
    "t1": "fe09_b2s3_t1_source_wrap_qualification",
    "t2f0": "fe09_b2s3_t2_f0_feasibility_qualification",
    "t2a": "fe09_b2s3_t2a_controlled_restart_qualification",
}
HISTORICAL_RUNTIME_FIELDS = {
    "s1": ("b2_s0_source_sha256",),
    "s2": ("s1_b2s0_git_source_sha256", "protected_unchanged_sha256"),
    "s3": ("frozen_s1_s2_source_sha256",),
    "t1": ("t0_s1_s2_source_sha256",),
    "t2f0": ("t1_upstream_s1_s2_sha256",),
    "t2a": ("t1_upstream_s1_s2_sha256",),
}
DECISION = "FE09_CURRENT_RESEARCH_EXECUTION_WITH_EXACT_HISTORICAL_RUNTIME_IDENTITY_V1"


class BoundaryError(ValueError):
    pass


def need(value: object, reason: str) -> None:
    if not value:
        raise BoundaryError(reason)


def raw(path: Path) -> bytes:
    need(path.is_file() and not path.is_symlink() and
         0 < path.stat().st_size < 16 * 1024 * 1024,
         "BOUNDARY_MISSING_OR_OVERSIZED_SOURCE_" + path.name)
    return path.read_bytes()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "-c", "safe.directory=" + str(root),
                                    *args], cwd=root, text=True, timeout=30).strip()


def original(relative: str) -> bytes:
    return subprocess.check_output(["git", "-c", "safe.directory=" + str(ROOT),
                                    "show", BASE + ":" + relative],
                                   cwd=ROOT, timeout=30)


def dependency_closure(paths: tuple[Path, ...]) -> set[Path]:
    """Follow actual local includes; generated build header stays in old recipe."""
    found = {p.resolve() for p in paths}
    todo = list(found)
    while todo:
        path = todo.pop()
        for name in re.findall(r'^\s*#\s*include\s*"([^"\n]+)"',
                               raw(path).decode("utf-8"), re.M):
            if name == "audio_pipeline/audio_pipeline_build.h":
                continue
            candidates = (path.parent / name, ROOT / "src" / name,
                          ROOT / "include" / name, HERE / name)
            target = next((p.resolve() for p in candidates if p.is_file()), None)
            need(target is not None and target.is_relative_to(ROOT),
                 "UNBOUND_COMPILE_DEPENDENCY_" + name)
            if target not in found:
                found.add(target)
                todo.append(target)
    return found


def modules() -> dict:
    answer = {key: importlib.import_module(name) for key, name in STAGES.items()}
    for module in answer.values():
        path = Path(module.__file__).resolve()
        need(path.parent == HERE and raw(path) == original(path.relative_to(ROOT).as_posix()),
             "ORIGINAL_QUALIFIER_CHANGED_" + path.name)
    return answer


def compile_sources(stage: str, loaded: dict) -> tuple[Path, ...]:
    module = loaded[stage]
    if stage == "s1":
        return module.CFILES
    if stage == "s2":
        return (module.SOURCE, module.FIXTURE)
    return module.SOURCES


def assert_execution_source(source: str, current: str) -> None:
    need(re.fullmatch(r"[0-9a-f]{40}", source) is not None and
         source == current == git("rev-parse", "HEAD"),
         "CURRENT_EXECUTION_HEAD_REQUIRED_NOT_HISTORICAL_VIEW")
    if os.environ.get("GITHUB_SHA"):
        need(os.environ["GITHUB_SHA"] == source, "GITHUB_SHA_IS_NOT_ACTUAL_WORKTREE_HEAD")


@contextlib.contextmanager
def admitted(stage: str, *, require_committed_execution: bool = False):
    """No global read/hash/process monkeypatches; only named historical calls."""
    need(stage in STAGES, "UNKNOWN_MAINTENANCE_RESEARCH_STAGE")
    loaded = modules()
    s0, s2, s3 = maintenance.recorder, loaded["s2"], loaded["s3"]
    current = git("rev-parse", "HEAD")
    assert_execution_source(current, current)
    checked = maintenance.verify(historical_self_tests=False)
    need(checked["execution_source_commit"] == current and
         checked["historical_source_is_current_source"] is False and
         checked["shipping_src_changed"] is True,
         "EXACT_CURRENT_MAINTENANCE_ADMISSION_REQUIRED")
    patch = maintenance.raw_file(maintenance.PATCH)
    item = maintenance.policy(maintenance.raw_file(maintenance.POLICY), patch)
    need(item["base"] == BASE, "HISTORICAL_VIEW_BASE_DRIFT")
    sources = maintenance.read_sources(ROOT, item)
    historical_paths = set(s2.LEGACY) | set(s2.FROZEN_S1) | set(s3.PRIOR_SOURCE_PATHS)
    for relative in historical_paths:
        content = raw(ROOT / relative)
        if relative != RUNTIME:
            need(content == original(relative), "HISTORICAL_INPUT_CHANGED_" + relative)
        sources[relative] = content.decode("utf-8")
    compiled = compile_sources(stage, loaded)
    closure = dependency_closure(compiled)
    need(ROOT / RUNTIME not in closure and
         not ({p.relative_to(ROOT).as_posix() for p in closure} & maintenance.CHANGED),
         "SHIPPING_MAINTENANCE_SOURCE_IS_ACTUAL_COMPILE_INPUT")
    frozen = set(closure) | {Path(m.__file__).resolve() for m in loaded.values()}
    for path in frozen:
        need(raw(path) == original(path.relative_to(ROOT).as_posix()),
             "ACTUAL_RESEARCH_COMPILE_INPUT_CHANGED_" + path.name)
    live_pins = {p: sha(raw(p)) for p in frozen}
    live_pins.update({ROOT / p: sha(text.encode("utf-8")) for p, text in sources.items()})
    live_pins.update({ROOT / p: sha(raw(ROOT / p))
                      for p in item["historical_contract_sha256"]})
    live_pins.update({p: sha(raw(p)) for p in
                     (Path(__file__), Path(maintenance.__file__), maintenance.POLICY,
                      maintenance.PATCH)})
    if require_committed_execution:
        for path in live_pins:
            relative = path.relative_to(ROOT).as_posix()
            committed = subprocess.check_output(
                ["git", "-c", "safe.directory=" + str(ROOT), "show", current + ":" + relative],
                cwd=ROOT, timeout=30)
            need(committed == raw(path), "EXECUTION_SOURCE_NOT_COMMITTED_AT_HEAD_" + relative)

    def check_live() -> None:
        assert_execution_source(current, current)
        for path, wanted in live_pins.items():
            need(sha(raw(path)) == wanted, "CURRENT_BOUND_SOURCE_CHANGED_" + path.name)
        maintenance.check_current(maintenance.read_sources(ROOT, item), item)

    with tempfile.TemporaryDirectory(prefix="fe09-readonly-source-history-") as directory:
        history = Path(directory)
        maintenance.reconstruct(history, sources, item, patch)
        # These Git objects retain their real immutable identities. In
        # particular, this partial historical view's HEAD is never current.
        subprocess.run(["git", "init", "--quiet", str(history)], check=True,
                       capture_output=True, timeout=30)
        objects = Path(git("rev-parse", "--git-path", "objects"))
        if not objects.is_absolute():
            objects = (ROOT / objects).resolve()
        (history / ".git/objects/info/alternates").write_text(str(objects) + "\n")
        (history / ".git/HEAD").write_text(BASE + "\n", encoding="ascii")
        historical_pins = {p: sha(raw(history / p)) for p in sources}
        need(raw(history / RUNTIME) == original(RUNTIME), "HISTORICAL_RUNTIME_RECONSTRUCTION_DRIFT")
        for relative in sources:
            (history / relative).chmod(0o444)

        def check_history() -> None:
            need(git("rev-parse", "HEAD", root=history) == BASE and BASE != current,
                 "HISTORICAL_VIEW_MUST_NOT_IMPERSONATE_EXECUTING_HEAD")
            for relative, wanted in historical_pins.items():
                need(sha(raw(history / relative)) == wanted,
                     "HISTORICAL_READONLY_SOURCE_CHANGED_" + relative)

        original_functions = ((s0, "check_sources"), (s2, "frozen_source_identity"),
                              (s3, "old_sources"))
        saved = [(module, name, getattr(module, name)) for module, name in original_functions]
        invocation_names: set[str] = set()

        def bind_function(module, name, function):
            @functools.wraps(function)
            def read_history(*args, **kwargs):
                check_live()
                check_history()
                previous = module.ROOT
                need(previous == ROOT, "HISTORICAL_ROOT_SCOPE_REENTRY")
                try:
                    module.ROOT = history
                    result = function(*args, **kwargs)
                    invocation_names.add(module.__name__ + "." + name)
                finally:
                    module.ROOT = previous
                check_live()
                check_history()
                return result
            return read_history

        for module, name, function in saved:
            setattr(module, name, bind_function(module, name, function))
        target = loaded[stage]
        old_identity = target.identity
        ledger = {
            "schema_version": 1, "decision": DECISION, "stage_entry": stage,
            "execution_source_commit": current,
            "maintenance_version": item["maintenance_version"],
            "active_current_version": checked["active_current_version"],
            "registered_forward_patch_blob": checked["registered_forward_patch_blob"],
            "maintenance_policy_sha256": maintenance.POLICY_SHA256,
            "maintenance_checker_sha256": sha(raw(Path(maintenance.__file__))),
            "adapter_sha256": sha(raw(Path(__file__))),
            "inverse_patch_sha256": item["patch_sha256"],
            "current_runtime_sha256": sha(raw(ROOT / RUNTIME)),
            "historical_runtime_sha256": historical_pins[RUNTIME],
            "current_runtime_git_blob": maintenance.major.git_blob(raw(ROOT / RUNTIME)),
            "historical_runtime_git_blob": item["source_bindings"][RUNTIME]["before_blob"],
            "historical_view_source_commit": BASE,
            "historical_runtime_identity_fields": list(HISTORICAL_RUNTIME_FIELDS[stage]),
            "historical_identity_fields_are_current_runtime": False,
            "actual_compile_sources_from_current_worktree": True,
            "exact_head_execution_inputs_verified": require_committed_execution,
            "shipping_runtime_in_compile_dependency_closure": False,
            "shipping_src_changed": True,
            "original_scientific_schema_and_thresholds_changed": False,
            "compiled_source_sha256": {p.relative_to(ROOT).as_posix(): sha(raw(p))
                                        for p in sorted(closure)},
        }

        @functools.wraps(old_identity)
        def identity(source: str) -> dict:
            assert_execution_source(source, current)
            record = old_identity(source)
            for field in HISTORICAL_RUNTIME_FIELDS[stage]:
                need(record.get(field, {}).get(RUNTIME) == historical_pins[RUNTIME],
                     "HISTORICAL_RUNTIME_FIELD_NOT_EXPLICITLY_CLASSIFIED_" + field)
            check_live()
            need(all(m.ROOT == ROOT and m.HERE == HERE for m in loaded.values()) and
                 s0.ROOT == ROOT and target.tools.source_head() == current,
                 "ACTUAL_COMPILE_OR_EXECUTION_ROOT_WAS_REDIRECTED")
            record["source_admission"] = copy.deepcopy(ledger)
            if "shipping_src_changed" in record:
                need(record["shipping_src_changed"] is False,
                     "HISTORICAL_S1_NONPROMOTION_FIELD_CHANGED")
                record["shipping_src_changed"] = True
            return record

        target.identity = identity
        try:
            check_history()
            yield target, ledger, history, invocation_names
            check_live()
            check_history()
        finally:
            target.identity = old_identity
            for module, name, function in saved:
                setattr(module, name, function)
            need(all(m.ROOT == ROOT for m in loaded.values()) and s0.ROOT == ROOT,
                 "HISTORICAL_IDENTITY_SCOPE_NOT_RESTORED")


def write_negative_receipt(path: Path, record: dict) -> None:
    path.mkdir()
    (path / "receipt.json").write_text(json.dumps(record, sort_keys=True) + "\n")
    (path / "collect.log").write_text("NEGATIVE METADATA FIXTURE; NO TARGET EXECUTION\n")
    (path / "verify.log").write_text("NEGATIVE METADATA FIXTURE; NOT A QUALIFICATION\n")
    (path / "SHA256SUMS").write_text("".join(
        f"{sha(raw(path / name))}  {name}\n" for name in
        ("receipt.json", "collect.log", "verify.log")))


def self_test() -> None:
    negative_count = 0

    def reject(function, marker: str) -> None:
        nonlocal negative_count
        try:
            function()
        except (ValueError, maintenance.major.GateFailure) as error:
            need(marker in str(error), "BOUNDARY_WRONG_REJECTION_" + str(error))
            negative_count += 1
        else:
            raise BoundaryError("BOUNDARY_NEGATIVE_FALSE_ADMISSION_" + marker)

    for stage in STAGES:
        with admitted(stage) as (module, ledger, history, names):
            module.self_test()
            current = git("rev-parse", "HEAD")
            good = module.identity(current)
            need(good["source_admission"] == ledger and
                 ledger["current_runtime_sha256"] != ledger["historical_runtime_sha256"],
                 "HISTORICAL_AND_CURRENT_RUNTIME_NOT_DISTINGUISHED")
            need(len(names) == (1 if stage == "s1" else 2 if stage == "s2" else 3),
                 "HISTORICAL_BOUNDARY_COVERAGE_DRIFT")
            reject(lambda: module.identity(BASE), "CURRENT_EXECUTION_HEAD_REQUIRED")
            mutations = [("source_admission", None)]
            for key, value in (
                ("current_runtime_sha256", ledger["historical_runtime_sha256"]),
                ("historical_runtime_sha256", ledger["current_runtime_sha256"]),
                ("adapter_sha256", "0" * 64),
                ("execution_source_commit", BASE),
                ("historical_view_source_commit", current),
                ("historical_identity_fields_are_current_runtime", True),
                ("shipping_runtime_in_compile_dependency_closure", True),
                ("shipping_src_changed", False),
            ):
                changed = copy.deepcopy(ledger)
                changed[key] = value
                mutations.append(("source_admission", changed))
            if stage == "s1":
                need(good["shipping_src_changed"] is True, "CURRENT_S1_SHIPPING_CHANGE_HIDDEN")
                mutations.append(("shipping_src_changed", False))
            with tempfile.TemporaryDirectory(prefix="fe09-boundary-negative-") as tmp:
                for index, (key, value) in enumerate(mutations):
                    wrong = copy.deepcopy(good)
                    if value is None:
                        del wrong[key]
                    else:
                        wrong[key] = value
                    output = Path(tmp) / str(index)
                    write_negative_receipt(output, wrong)
                    verifier = module.verified_output if stage == "s2" else module.verify_output
                    reject(lambda out=output: verifier(out, current), key)
            head = history / ".git/HEAD"
            head.write_text(current + "\n", encoding="ascii")
            try:
                reject(lambda: module.identity(current), "HISTORICAL_VIEW_MUST_NOT_IMPERSONATE")
            finally:
                head.write_text(BASE + "\n", encoding="ascii")
    need(negative_count == 67, "INCOMPLETE_BOUNDARY_NEGATIVES")
    print(f"FE09_RUNTIME_SOURCE_BOUNDARY_SELF_TEST_PASS stages=6 boundaries=3 negatives={negative_count}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in STAGES:
        stage = sys.argv[1]
        forwarded = sys.argv[2:]
        # The development-only self-test has no qualification output. Every
        # collection/readback spelling (including argparse abbreviations)
        # requires that all inputs really belong to the declared Git HEAD.
        with admitted(stage, require_committed_execution=forwarded != ["--self-test"]) as (module, _, _, _):
            sys.argv = [str(Path(module.__file__)), *forwarded]
            module.main()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if not arguments.self_test:
        parser.error("use --self-test or one of: " + ", ".join(STAGES))
    self_test()


if __name__ == "__main__":
    main()
