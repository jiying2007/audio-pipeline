#!/usr/bin/env python3
"""One isolated patched AEC3 build and bounded selection engineering.

No speech is executed here. The immutable distribution admission, download,
tool, compiler, dependency, portability and process primitives are reused.
Pristine inputs and derived outputs remain separately identified.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

import webrtc_aec3_ci as previous
import webrtc_aec3_reference as reference
import webrtc_aec3_selection_source as selection
import webrtc_aec3_source as source
from contracts import ROOT, hex_digest, load_json, require, sha256

REL = "tests/validation/frontend_evolution/"
KIND = "webrtc-aec3-synthesis-selection-engineering-v1"
PATHS = {"runner": "bin/webrtc-aec3-selection-runner", "pristine": "pristine",
         "source_transform": "source-change/source-transform.json",
         "build_receipt": "build/build-receipt.json", "adapter_build": "build/runner-build.json",
         "engineering": "engineering/engineering.json"}
FIXTURE = REL + "test_webrtc_aec3_selection_adapter.py"
CONTROL_FILES = (
    REL + "webrtc_aec3_selection_ci.py", REL + "webrtc_aec3_selection_source.py", FIXTURE,
    REL + "test_webrtc_aec3_selection_source.py", REL + "webrtc_aec3_selection.py",
    REL + "test_webrtc_aec3_selection.py",
    REL + "webrtc_aec3_selection_scope.py", REL + "test_webrtc_aec3_selection_scope.py",
    REL + "webrtc_aec3_gain_control_audit.py", REL + "test_webrtc_aec3_gain_control_audit.py",
    ".github/research/frontend-evolution-v1/aec3-joint-gain-controlled-synthesis-v1.json",
    ".github/workflows/frontend-research.yml",
    ".github/research/frontend-evolution-v1/webrtc-aec3-synthesis-selection-v1.json",
    REL + "webrtc_aec3_runner.cc", REL + "webrtc_aec3_ci.py",
    REL + "webrtc_aec3_source.py", REL + "webrtc_aec3_reference.py",
    REL + "test_webrtc_aec3_adapter.py", REL + "test_webrtc_aec3_linear_tap_adapter.py",
    REL + "contracts.py", ".github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json",
    ".github/research/frontend-evolution-v1/webrtc-aec3-admission.json",
    ".github/research/frontend-evolution-v1/sources.json",
)
CI_SECONDS = 1200
ARCHIVE_NAME = "webrtc-aec3-selection-engineering-bundle.tar.gz"


def controls(expected: str) -> dict:
    require(hex_digest(expected, 40) and previous.git("rev-parse", "HEAD").strip() == expected,
            "selection exact committed HEAD required")
    result = {}
    for relative in CONTROL_FILES:
        actual = (ROOT / relative).read_bytes()
        require(reference.git_bytes(expected, relative) == actual, "uncommitted selection control: " + relative)
        result[relative] = sha256(actual)
    return result


def build_variant(prepared: Path, derived: Path, evidence: Path,
                  build_root: Path, meson: str, ninja: str, expected: str) -> dict:
    started = time.monotonic()
    plan = source.build_plan(prepared, build_root, meson)
    transform = selection.verify(prepared, evidence, derived)
    plan["setup"][3] = str(derived)
    plan["source_root"] = str(derived)
    deadline = started + plan["wall_seconds"]
    tools = {}
    for name, executable in (("meson", meson), ("ninja", ninja), ("cc", "cc"),
                             ("cxx", "c++"), ("pkg_config", "pkg-config")):
        path = shutil.which(executable)
        require(path is not None, "missing selection build tool: " + name)
        version = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT,
                                          timeout=previous.remaining(deadline, 10)).decode().strip()
        tools[name] = {"path": path, "version": version, "sha256": sha256(Path(path).read_bytes())}
    require(all(tools[name]["version"] == value for name, value in
                load_json(source.LOCK)["build_contract"]["tool_versions"].items()), "selection tool version mismatch")
    build_root.mkdir(parents=True)
    environment = {"PATH": os.pathsep.join(dict.fromkeys([str(Path(v["path"]).parent) for v in tools.values()] + [os.defpath])),
                   "LC_ALL": "C", "CC": tools["cc"]["path"], "CXX": tools["cxx"]["path"],
                   "NINJA": tools["ninja"]["path"], "PKG_CONFIG": tools["pkg_config"]["path"]}
    report = {**plan, "status": "FAIL", "code_revision": expected, "controls_sha256": controls(expected),
              "tools": tools, "source_transform_sha256": sha256(source.encoded(transform)), "steps": [],
              "acoustic_measurement": "NOT_RUN", "promotion_allowed": False, "pristine_upstream": False}
    try:
        for phase in ("setup", "compile"):
            code = source.run_logged(plan[phase], build_root / (phase + ".log"), environment, deadline)
            report["steps"].append({"phase": phase, "exit_code": code})
            require(code == 0, "selection source " + phase + " failed; original log retained")
        report["post_source_verification"] = selection.verify(prepared, evidence, derived)
        require(report["post_source_verification"] == transform, "source derivation changed during build")
        pc_dir = Path(plan["meson_build_dir"]) / "meson-uninstalled"
        pc_module = "webrtc-audio-processing-2-uninstalled"
        pc_env = dict(environment, PKG_CONFIG_PATH=str(pc_dir))
        cflags = subprocess.check_output([tools["pkg_config"]["path"], "--cflags", pc_module], env=pc_env,
                                        timeout=previous.remaining(deadline, 10)).decode().strip()
        libs = subprocess.check_output([tools["pkg_config"]["path"], "--libs", pc_module], env=pc_env,
                                      timeout=previous.remaining(deadline, 10)).decode().strip()
        libraries = source.built_shared_libraries(Path(plan["meson_build_dir"]))
        report["link"] = {"pkgconfig_dir": str(pc_dir), "pkgconfig_module": pc_module,
                          "pkgconfig_sha256": sha256((pc_dir / (pc_module + ".pc")).read_bytes()),
                          "cflags": shlex.split(cflags), "libs": shlex.split(libs),
                          "runtime_library_dirs": sorted({str(p.parent) for p in libraries}),
                          "libraries": [{"path": str(p), "size": p.stat().st_size, "sha256": sha256(p.read_bytes())}
                                        for p in libraries]}
        require(controls(expected) == report["controls_sha256"], "selection controls changed during build")
        previous.remaining(deadline, 1)
        report["status"] = "BUILT_SELECTION_DERIVATION_NO_SPEECH"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        report["logs"] = {p.name: sha256(p.read_bytes()) for p in build_root.glob("*.log")}
        source.write_json(build_root / "build-receipt.json", report)
    return report


def engineering_record(path: Path, binary_sha: str, build_sha: str, revision: str) -> dict:
    """Read every saved synthetic output/trace without invoking a native tool."""
    import test_webrtc_aec3_selection_adapter as fixture
    report = reference.read_json(path)
    require(report["status"] == "PASS_SELECTION_ENGINEERING_ONLY" and
            report["experiment_id"] == selection.EXPERIMENT and report["code_revision"] == revision and
            report["binary_sha256"] == binary_sha and report["build_receipt_sha256"] == build_sha and
            report["fixture_source_sha256"] == sha256((ROOT / FIXTURE).read_bytes()) and not report["failures"],
            "selection engineering identity")
    require(len(report["calls"]) == 14 and report["valid_processed_samples"] == 64000 and
            report["requested_capture_samples"] == 321280 and report["acoustic_acceptance"] is False and
            report["promotion_allowed"] is False and type(report["wall_seconds"]) in (int, float) and
            math.isfinite(report["wall_seconds"]) and 0 < report["wall_seconds"] <= 120,
            "selection engineering complete fixed budgets")
    fixture.verify_saved(path.parent, report)
    return report


def verify_bundle(root: Path) -> dict:
    """Pure original-byte/source/engineering readback; never SDK, build or ldd."""
    root = source.safe_path(root)
    manifest = reference.read_json(root / "bundle.json")
    require(manifest["kind"] == KIND and manifest["status"] == "PASS_SELECTION_ENGINEERING_ONLY" and
            manifest["paths"] == PATHS and set(manifest["controls_sha256"]) == set(CONTROL_FILES),
            "selection bundle contract")
    require(reference.file_set(root, ("bundle.json",)) == manifest["files"], "selection bundle members/hash drift")
    revision = manifest["code_revision"]
    require(hex_digest(revision, 40), "selection bundle revision")
    for relative, digest in manifest["controls_sha256"].items():
        require(sha256(reference.git_bytes(revision, relative)) == digest and
                sha256((ROOT / relative).read_bytes()) == digest, "exact selection reader/source required: " + relative)
    transform = selection.verify(root / PATHS["pristine"], root / "source-change")
    build = reference.read_json(root / PATHS["build_receipt"])
    adapter = reference.read_json(root / PATHS["adapter_build"])
    require(build["status"] == "BUILT_SELECTION_DERIVATION_NO_SPEECH" and build["code_revision"] == revision and
            build["controls_sha256"] == manifest["controls_sha256"] and build["parallel_jobs"] == 2 and
            0 < build["elapsed_seconds"] <= 600 and build["steps"] ==
            [{"phase": "setup", "exit_code": 0}, {"phase": "compile", "exit_code": 0}] and
            build["post_source_verification"] == transform and
            build["source_transform_sha256"] == sha256(source.encoded(transform)), "selection derived build binding")
    binary_sha = sha256((root / PATHS["runner"]).read_bytes())
    build_sha = sha256((root / PATHS["build_receipt"]).read_bytes())
    require(adapter["status"] == "BUILT_SELECTION_ADAPTER" and adapter["code_revision"] == revision and
            adapter["binary_sha256"] == binary_sha and adapter["build_receipt_sha256"] == build_sha and
            adapter["generated_runner_sha256"] == transform["changes"][selection.RUNNER]["modified_sha256"],
            "selection adapter binding")
    for relative, digest in adapter["runtime_libraries"].items():
        require(sha256((root / relative).read_bytes()) == digest, "selection research library bytes")
    engineering = engineering_record(root / PATHS["engineering"], binary_sha, build_sha, revision)
    require(engineering["runtime_identity"] == adapter["runtime_identity"], "selection native engineering runtime differs")
    return manifest


def execution_environment(root: Path) -> dict:
    return {"PATH": os.defpath, "LC_ALL": "C", "LD_LIBRARY_PATH": str((root / "bin/lib").resolve())}


def require_host_engineering(root: Path, path: Path) -> dict:
    manifest = verify_bundle(root)
    adapter = reference.read_json(root / PATHS["adapter_build"])
    report = engineering_record(path, adapter["binary_sha256"], adapter["build_receipt_sha256"], manifest["code_revision"])
    for relative, digest in adapter["runtime_libraries"].items():
        observed = report["runtime_identity"]
        resolved = str((root / relative).resolve())
        require(observed["library_names"].get(Path(relative).name) == resolved and
                observed["libraries"].get(resolved) == digest, "host engineering used wrong research library")
    return report


def host_engineering(root: Path, output: Path) -> dict:
    import test_webrtc_aec3_selection_adapter as fixture
    manifest = verify_bundle(root)
    report = fixture.run(root / PATHS["runner"], output, root / PATHS["build_receipt"],
                         manifest["code_revision"], execution_environment(root))
    require_host_engineering(root, output / "engineering.json")
    return report


def run(expected: str, output: Path) -> dict:
    output = source.safe_path(output)
    require(not output.exists() and source.separate(ROOT, output), "fresh selection CI output outside checkout")
    output.mkdir(parents=True)
    logs, work, bundle = output / "logs", output / "work", output / "bundle"
    for path in (logs, work, bundle):
        path.mkdir()
    started, deadline = time.monotonic(), time.monotonic() + CI_SECONDS
    report = {"schema_version": 1, "status": "FAIL", "code_revision": expected, "stages": [],
              "acoustic_measurement": "NOT_RUN", "promotion_allowed": False}
    try:
        report["host"] = previous.assert_actions_host()
        report["controls_sha256"] = controls(expected)
        lock = load_json(source.LOCK)
        archives = work / "archives"
        archives.mkdir()
        download_deadline = time.monotonic() + previous.remaining(deadline, 120)
        for spec in lock["archives"].values():
            previous.download(spec, archives / spec["filename"], download_deadline)
        venv, environment = previous.tools_environment(work, logs, lock, deadline)
        source.preflight(archives, bundle / PATHS["pristine"])
        from webrtc_aec3_gain_control_audit import audit_files
        aec3_root = bundle / PATHS["pristine"] / "source/webrtc/modules/audio_processing/aec3"
        mechanism_audit = audit_files(
            aec3_root / "echo_remover.cc",
            aec3_root / "suppression_filter.cc",
            aec3_root / "suppression_filter.h",
        )
        source.write_json(bundle / "source-mechanism-audit.json", mechanism_audit)
        report["source_mechanism_audit"] = mechanism_audit
        derived = work / "derived-source"
        selection.prepare(bundle / PATHS["pristine"], derived, bundle / "source-change")
        report["stages"].append("pristine-admission-and-exact-source-derivation")
        require(previous.remaining(deadline, 600) == 600, "insufficient selection source build budget")
        build_root = work / "build"
        built = build_variant(bundle / PATHS["pristine"], derived, bundle / "source-change", build_root,
                              str(venv / "bin/meson"), str(venv / "bin/ninja"), expected)
        evidence = bundle / "build"
        evidence.mkdir()
        for name in ("build-receipt.json", "setup.log", "compile.log"):
            shutil.copyfile(build_root / name, evidence / name)
        binary = bundle / PATHS["runner"]
        binary.parent.mkdir()
        runner_source = bundle / "source-change/modified" / selection.RUNNER
        compiler = built["tools"]["cxx"]
        args = [compiler["path"], "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"]
        args += previous.system_includes(built["link"]["cflags"])
        args += [str(runner_source)] + built["link"]["libs"] + ["-Wl,-rpath,$ORIGIN/lib", "-o", str(binary)]
        previous.command(args, logs / "adapter-compile.log", environment, deadline, 90)
        build_environment = dict(environment, LD_LIBRARY_PATH=os.pathsep.join(built["link"]["runtime_library_dirs"]))
        libraries, system = previous.copy_research_libraries(binary, build_root, bundle,
                                                            build_environment, built["link"]["libraries"])
        previous.no_absolute_rpath(binary, environment)
        for name in libraries:
            previous.no_absolute_rpath(bundle / name, environment)
        build_root.rename(work / "build-hidden-before-engineering")
        portable = execution_environment(bundle)
        identity = previous.runtime_identity(binary, portable)
        for name, digest in libraries.items():
            resolved = str((bundle / name).resolve())
            require(identity["library_names"].get(Path(name).name) == resolved and
                    identity["libraries"].get(resolved) == digest, "selection portable resolution")
        adapter = {"schema_version": 1, "status": "BUILT_SELECTION_ADAPTER", "code_revision": expected,
                   "binary_sha256": sha256(binary.read_bytes()), "generated_runner_sha256": sha256(runner_source.read_bytes()),
                   "build_receipt_sha256": sha256((bundle / PATHS["build_receipt"]).read_bytes()),
                   "command": args, "compiler": compiler, "runtime_libraries": libraries,
                   "system_libraries": system, "runtime_identity": identity}
        source.write_json(bundle / PATHS["adapter_build"], adapter)
        shutil.copyfile(logs / "adapter-compile.log", evidence / "adapter-compile.log")
        report["stages"].append("derived-library-and-adapter-built-once-and-relocated")
        import test_webrtc_aec3_selection_adapter as fixture
        fixture.run(binary, bundle / "engineering", bundle / PATHS["build_receipt"], expected, portable)
        require(controls(expected) == report["controls_sha256"], "selection controls changed after engineering")
        selection.verify(bundle / PATHS["pristine"], bundle / "source-change", derived)
        manifest = {"schema_version": 1, "kind": KIND, "status": "PASS_SELECTION_ENGINEERING_ONLY",
                    "code_revision": expected, "controls_sha256": report["controls_sha256"], "paths": PATHS,
                    "files": previous.manifest_files(bundle)}
        source.write_json(bundle / "bundle.json", manifest)
        verify_bundle(bundle)
        archive = output / ARCHIVE_NAME
        report["bundle_archive"] = {"path": archive.name, "sha256": previous.pack_bundle(bundle, archive),
                                    "size": archive.stat().st_size}
        previous.remaining(deadline, 1)
        report["stages"].append("selection-only-synthetic-engineering-and-pure-readback")
        report["status"] = "PASS_SELECTION_ENGINEERING_ONLY"
    except Exception as error:
        report["error"] = str(error)
        if (output / ARCHIVE_NAME).exists():
            (output / ARCHIVE_NAME).unlink()
        if (bundle / "bundle.json").exists():
            (bundle / "bundle.json").rename(bundle / "bundle-failed.json")
        for candidate in (work / "build", work / "build-hidden-before-engineering"):
            if candidate.is_dir():
                failed = output / "failed-build-evidence"
                failed.mkdir(exist_ok=True)
                for path in candidate.glob("*.log"):
                    shutil.copyfile(path, failed / path.name)
                if (candidate / "build-receipt.json").is_file():
                    shutil.copyfile(candidate / "build-receipt.json", failed / "build-receipt.json")
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        report["logs_sha256"] = {p.name: sha256(p.read_bytes()) for p in logs.glob("*.log")}
        source.write_json(output / "ci-receipt.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("run")
    item.add_argument("--expected-head", required=True)
    item.add_argument("--output", required=True, type=Path)
    item = sub.add_parser("verify")
    item.add_argument("--bundle", required=True, type=Path)
    item = sub.add_parser("host")
    item.add_argument("--bundle", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "run":
        result = run(args.expected_head, args.output)
    elif args.command == "host":
        result = host_engineering(args.bundle, args.output)
    else:
        result = verify_bundle(args.bundle)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
