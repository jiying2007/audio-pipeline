#!/usr/bin/env python3
"""Bounded Actions orchestration for the fixed AEC3 engineering reference.

Source admission/build belongs exclusively to webrtc_aec3_source. This module
selects the isolated workflow job, downloads pinned inputs, and assembles a
relocatable Ubuntu reference bundle after real binary engineering fixtures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request

import webrtc_aec3_source as source
from contracts import ROOT, hex_digest, load_json, require, sha256

BASELINE = "21448956f65916577d13082e9dc58f275f8fbb70"
WORKFLOW = ".github/workflows/frontend-research.yml"
VERIFY_WORKFLOW = ".github/workflows/verify.yml"
RUNNER = ROOT / "tests/validation/frontend_evolution/webrtc_aec3_runner.cc"
FIXTURES = ROOT / "tests/validation/frontend_evolution/test_webrtc_aec3_adapter.py"
MATRIX = "  matrix:\n"
JOB_MARKER = "\n  webrtc-aec3-engineering:\n"
HISTORICAL_FLAGS = ("d1", "d3", "d3_execute", "d4", "d5", "d6", "d7", "d8", "d8_archive")
SCOPE_BLOCK = """          # AEC3_OUTER_SELECTOR_BEGIN
          import sys
          sys.path.insert(0, 'tests/validation/frontend_evolution')
          from webrtc_aec3_ci import select_workflow
          if select_workflow():
              raise SystemExit(0)
          # AEC3_OUTER_SELECTOR_END
"""
TRIGGER_PATHS = (
    "tests/validation/frontend_evolution/webrtc_*",
    "tests/validation/frontend_evolution/test_webrtc_*",
    ".github/research/frontend-evolution-v1/webrtc-aec3-*.json",
    ".github/research/frontend-evolution-v1/sources.json",
    "docs/research/frontend-evolution-v1/WEBRTC_AEC3*",
)
VERIFY_COMMANDS = (
    "          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_source.py\n",
    "          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_ci.py\n",
    "          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_reference.py\n",
)
CI_SECONDS = 1050
NAVIGATION = "docs/research/frontend-evolution-v1/README.md"
NAVIGATION_ENTRY = "[长期科研平台运行手册：来源、数据、仿真、评估、复现与 AEC3](LONG_TERM_RESEARCH_PLATFORM.zh-CN.md)\n\n"


def git(*args: str) -> str:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    return subprocess.check_output(["git", "-C", str(ROOT), "-c", "core.fsmonitor=false", *args],
                                   env=env, stderr=subprocess.PIPE, timeout=30).decode()


def old_workflow(text: str) -> str:
    """Remove only this explicit outer wiring and appended job, not old code."""
    require(text.count(JOB_MARKER) <= 1 and text.count(SCOPE_BLOCK) <= 1, "AEC3_DUPLICATE_WIRING")
    text = text.split(JOB_MARKER, 1)[0]
    for path in TRIGGER_PATHS:
        text = text.replace("      - '" + path + "'\n", "")
    text = text.replace(", webrtc-aec3-engineering]", "]")
    text = text.replace("      webrtc: ${{ steps.select.outputs.webrtc }}\n", "")
    return text.replace(SCOPE_BLOCK, "")


def historical_jobs(text: str) -> str:
    require(len(re.findall(r"(?m)^  matrix:\n", text)) == 1, "AEC3_HISTORICAL_MATRIX_MISSING_OR_DUPLICATE")
    return MATRIX + text.split(MATRIX, 1)[1].split(JOB_MARKER, 1)[0]


def aec3_path(path: str) -> bool:
    return (re.fullmatch(r"tests/validation/frontend_evolution/(?:test_)?webrtc_[A-Za-z0-9_.-]+", path) is not None
            or re.fullmatch(r"\.github/research/frontend-evolution-v1/webrtc-aec3-[A-Za-z0-9_.-]+\.json", path) is not None
            or re.fullmatch(r"docs/research/frontend-evolution-v1/WEBRTC_AEC3[A-Za-z0-9_.-]*", path) is not None
            or path == ".github/research/frontend-evolution-v1/sources.json")


def select(event: str, selected: str, paths: list, current: str, prior: str, frozen: str) -> dict | None:
    """Pure selector; mixed historical work never falls back to an old job."""
    if event == "workflow_dispatch":
        wanted = selected == "webrtc-aec3-engineering"
    else:
        require(event in ("pull_request", "push"), "AEC3_UNSUPPORTED_EVENT")
        wanted = any(aec3_path(path) for path in paths)
        if WORKFLOW in paths:
            wanted = wanted or (JOB_MARKER in current and
                                current.split(JOB_MARKER, 1)[1] != prior.split(JOB_MARKER, 1)[-1])
            wanted = wanted or (old_workflow(current) == old_workflow(prior) and current != prior)
    if not wanted:
        return None
    require(current.count(JOB_MARKER) == 1, "AEC3_JOB_MISSING_OR_DUPLICATE")
    require(historical_jobs(current) == historical_jobs(frozen), "AEC3_HISTORICAL_JOBS_CHANGED")
    require(old_workflow(current) == frozen, "AEC3_HISTORICAL_SCOPE_CHANGED")
    if event != "workflow_dispatch":
        allowed_support = {WORKFLOW, VERIFY_WORKFLOW, NAVIGATION,
                           "docs/research/frontend-evolution-v1/LONG_TERM_RESEARCH_PLATFORM.zh-CN.md"}
        require(all(aec3_path(path) or path in allowed_support for path in paths),
                "AEC3_REQUIRES_SEPARATE_RESEARCH_CHANGE")
    return {**{name: "false" for name in HISTORICAL_FLAGS}, "webrtc": "true"}


def support_changes(paths: list, base: str) -> None:
    """Supporting registry/navigation edits must concern only this reference."""
    catalog = ".github/research/frontend-evolution-v1/sources.json"
    if catalog in paths:
        before = json.loads(git("show", base + ":" + catalog))
        after = load_json(ROOT / catalog)
        for item in (before, after):
            item["sources"] = [row for row in item["sources"] if row["id"] != "webrtc"]
        require(before == after, "AEC3_OTHER_SOURCE_CATALOG_CHANGED")
    if VERIFY_WORKFLOW in paths:
        before = git("show", base + ":" + VERIFY_WORKFLOW)
        after = (ROOT / VERIFY_WORKFLOW).read_text()
        for line in VERIFY_COMMANDS:
            before, after = before.replace(line, ""), after.replace(line, "")
        require(before == after, "AEC3_OTHER_VERIFY_JOB_CHANGED")
    if NAVIGATION in paths:
        before = git("show", base + ":" + NAVIGATION)
        after = (ROOT / NAVIGATION).read_text()
        require(before.count(NAVIGATION_ENTRY) <= 1 and after.count(NAVIGATION_ENTRY) == 1
                and before.replace(NAVIGATION_ENTRY, "") == after.replace(NAVIGATION_ENTRY, "")
                and after.startswith("# Frontend Evolution v1 / 双麦与四麦开放研究\n\n" + NAVIGATION_ENTRY),
                "AEC3_OTHER_RESEARCH_NAVIGATION_CHANGED")


def select_workflow() -> bool:
    event = os.environ["EVENT_NAME"]
    selected = os.environ.get("SELECTED_EXPERIMENT", "")
    current = (ROOT / WORKFLOW).read_text()
    frozen = git("show", BASELINE + ":" + WORKFLOW)
    paths, prior = [], current
    if event != "workflow_dispatch":
        base = os.environ["BASE_SHA"]
        require(hex_digest(base, 40) and base != "0" * 40, "AEC3_EXACT_BASE_REQUIRED")
        paths = git("diff", "--name-only", base, "HEAD").splitlines()
        prior = git("show", base + ":" + WORKFLOW)
    result = select(event, selected, paths, current, prior, frozen)
    if result is not None and event != "workflow_dispatch":
        support_changes(paths, base)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name, value in (result or {"webrtc": "false"}).items():
            output.write(name + "=" + value + "\n")
    return result is not None


def parse_libraries(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("linux-vdso.so"):
            continue
        require("not found" not in line, "unresolved runtime dependency")
        if "=>" in line:
            name, value = (part.strip() for part in line.split("=>", 1))
            path = value.split(" (", 1)[0]
        else:
            path = line.split(" (", 1)[0]
            name = Path(path).name
        require(re.fullmatch(r"[A-Za-z0-9_.+-]+", name) is not None and path.startswith("/")
                and name not in result, "invalid or duplicate runtime dependency")
        result[name] = path
    require(result, "empty dynamic dependency observation")
    return result


def runtime_identity(binary: Path, env: dict = None) -> dict:
    """Shared read-only host/library observation for fixtures and comparisons."""
    environment = dict(os.environ if env is None else env, LC_ALL="C")
    observed = subprocess.check_output(["ldd", str(binary)], env=environment,
                                       stderr=subprocess.STDOUT, timeout=10).decode()
    names, libraries = {}, {}
    for name, raw_path in parse_libraries(observed).items():
        path = Path(raw_path).resolve(strict=True)
        require(path.is_file() and path.stat().st_size <= 128 * 1024 * 1024, "invalid runtime library")
        names[name] = str(path)
        libraries[str(path)] = sha256(path.read_bytes())
    os_release = Path("/etc/os-release")
    require(os_release.is_file(), "missing host OS identity")
    return {"system": platform.system(), "machine": platform.machine(), "release": platform.release(),
            "os_release_sha256": sha256(os_release.read_bytes()), "libraries": libraries, "library_names": names}


def remaining(deadline: float, limit: float) -> float:
    left = deadline - time.monotonic()
    require(left > 0, "AEC3 orchestration budget exhausted")
    return min(left, limit)


def command(args: list, log: Path, env: dict, deadline: float, limit: float) -> None:
    code = source.run_logged(args, log, env, time.monotonic() + remaining(deadline, limit))
    require(code == 0, "command failed; inspect " + log.name)


def download(spec: dict, output: Path, deadline: float) -> None:
    require(not output.exists() and spec["url"].startswith("https://"), "fresh HTTPS archive download required")
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "audio-pipeline-fixed-research/1"})
    digest, count = hashlib.sha256(), 0
    with urllib.request.urlopen(request, timeout=remaining(deadline, 30)) as response, output.open("xb") as stream:
        require(response.geturl().startswith("https://"), "non-HTTPS archive redirect")
        reported = response.headers.get("Content-Length")
        require(reported is None or int(reported) == spec["size"], "archive Content-Length mismatch")
        while True:
            remaining(deadline, 30)
            block = response.read(min(65536, spec["size"] - count + 1))
            if not block:
                break
            count += len(block)
            require(count <= spec["size"], "archive download exceeded frozen size")
            stream.write(block)
            digest.update(block)
    require(count == spec["size"] and digest.hexdigest() == spec["sha256"], "archive download size/SHA256 mismatch")


def tools_environment(root: Path, logs: Path, lock: dict, deadline: float) -> tuple:
    venv, wheels = root / "venv", root / "wheels"
    wheels.mkdir()
    env = {"PATH": os.defpath, "LC_ALL": "C", "PIP_CONFIG_FILE": os.devnull,
           "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1"}
    command([sys.executable, "-m", "venv", str(venv)], logs / "venv.log", env, deadline, 30)
    requirements = root / "build-tool-requirements.txt"
    packages = lock["build_contract"]["tool_packages"]
    requirements.write_text("".join(name + "==" + spec["version"] + " --hash=sha256:" + spec["sha256"] + "\n"
                                      for name, spec in sorted(packages.items())))
    python = str(venv / "bin/python")
    command([python, "-m", "pip", "download", "--index-url", "https://pypi.org/simple", "--no-deps", "--only-binary=:all:",
             "--require-hashes", "--dest", str(wheels), "--requirement", str(requirements)],
            logs / "wheel-download.log", env, deadline, 90)
    require({path.name for path in wheels.iterdir()} == {spec["wheel"] for spec in packages.values()}, "unexpected tool wheel set")
    for spec in packages.values():
        path = wheels / spec["wheel"]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == spec["size"]
                and sha256(path.read_bytes()) == spec["sha256"], "tool wheel byte mismatch")
    command([python, "-m", "pip", "install", "--no-index", "--no-deps", "--require-hashes", "--find-links", str(wheels),
             "--requirement", str(requirements)], logs / "wheel-install.log", env, deadline, 30)
    env["PATH"] = str(venv / "bin") + os.pathsep + os.defpath
    return venv, env


def system_includes(flags: list) -> list:
    result, index = [], 0
    while index < len(flags):
        flag = flags[index]
        if flag == "-I":
            index += 1
            require(index < len(flags), "incomplete include flag")
            result.extend(["-isystem", flags[index]])
        elif flag.startswith("-I"):
            require(len(flag) > 2, "empty include flag")
            result.extend(["-isystem", flag[2:]])
        else:
            result.append(flag)
        index += 1
    return result


def no_absolute_rpath(path: Path, env: dict) -> None:
    text = subprocess.check_output(["readelf", "-d", str(path)], env=env, stderr=subprocess.STDOUT, timeout=10).decode()
    for line in text.splitlines():
        if "(RPATH)" in line or "(RUNPATH)" in line:
            match = re.search(r"\[([^]]*)\]", line)
            require(match is not None and all(not entry.startswith("/") for entry in match.group(1).split(":")),
                    "absolute runtime search path forbidden")


def copy_research_libraries(binary: Path, build_root: Path, bundle: Path, env: dict, declared: list) -> tuple:
    observed = runtime_identity(binary, env)
    for item in declared:
        resolved = str(Path(item["path"]).resolve(strict=True))
        require(observed["libraries"].get(resolved) == item["sha256"], "source-build runtime identity mismatch")
    library_dir = bundle / "bin/lib"
    library_dir.mkdir()
    hashes, system = {}, {}
    build_root = build_root.resolve()
    for name, raw_path in observed["library_names"].items():
        path = Path(raw_path)
        if build_root in path.parents:
            require(name.startswith(("libwebrtc-", "libabsl")), "unexpected research runtime dependency")
            target = library_dir / name
            require(not target.exists(), "runtime SONAME collision")
            shutil.copyfile(path, target)
            target.chmod(0o755)
            hashes[target.relative_to(bundle).as_posix()] = sha256(target.read_bytes())
        else:
            require(str(path).startswith(("/usr/lib/", "/lib/", "/lib64/")), "runtime dependency outside declared host/build roots")
            system[name] = {"resolved_path": str(path), "sha256": observed["libraries"][str(path)]}
    require(any(Path(name).name.startswith("libwebrtc-audio-processing-2.so") for name in hashes), "WebRTC runtime missing from bundle")
    return hashes, system


def manifest_files(root: Path) -> dict:
    result, total = {}, 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        require(all(not (Path(directory) / name).is_symlink() for name in dirs), "bundle directory symlink forbidden")
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            require(relative != "bundle.json", "bundle manifest must be created once")
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "bundle link/special file forbidden")
            total += info.st_size
            require(len(result) < 10000 and total <= 256 * 1024 * 1024, "bundle file/size bound exceeded")
            result[relative] = sha256(path.read_bytes())
    return result


def pack_bundle(bundle: Path, target: Path) -> str:
    require(not target.exists(), "fresh bundle archive required")
    with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(bundle.rglob("*")):
            require(not path.is_symlink(), "bundle symlink forbidden")
            if path.is_file():
                archive.add(path, arcname=path.relative_to(bundle).as_posix(), recursive=False)
    return sha256(target.read_bytes())


def invalidate_bundle(output: Path) -> None:
    """A failed late packaging step must leave no admissible success bundle."""
    archive = output / "webrtc-aec3-engineering-bundle.tar.gz"
    if archive.exists():
        archive.unlink()
    manifest = output / "bundle/bundle.json"
    if manifest.is_file():
        value = load_json(manifest)
        manifest.unlink()
        value["status"] = "FAIL_BUNDLE_NOT_COMMITTED"
        source.write_json(manifest, value)


def assert_actions_host() -> dict:
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Linux",
            "large reference builds are restricted to the Actions Linux job")
    require(platform.system() == "Linux" and platform.machine() == "x86_64", "fixed x86_64 Linux build profile required")
    values = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    require(values.get("ID", "").strip('"') == "ubuntu" and values.get("VERSION_ID", "").strip('"') == "24.04",
            "fixed Ubuntu 24.04 build profile required")
    return {"system": platform.system(), "machine": platform.machine(), "release": platform.release(),
            "os_release_sha256": sha256(Path("/etc/os-release").read_bytes())}


def committed_inputs(expected: str) -> dict:
    require(hex_digest(expected, 40) and git("rev-parse", "HEAD").strip() == expected, "exact execution HEAD required")
    result = {}
    for path in (Path(__file__).resolve(), RUNNER, FIXTURES):
        relative = path.relative_to(ROOT).as_posix()
        require(path.is_file(), "missing committed runner/fixture/orchestration input")
        expected_bytes = subprocess.check_output(["git", "-C", str(ROOT), "show", expected + ":" + relative], timeout=10)
        require(expected_bytes == path.read_bytes(), "uncommitted AEC3 input: " + relative)
        result[relative] = sha256(expected_bytes)
    return result


def run(expected: str, output: Path) -> dict:
    output = source.safe_path(output)
    require(not output.exists() and source.separate(ROOT, output), "fresh output outside checkout required")
    output.mkdir(parents=True)
    logs, work, bundle = output / "logs", output / "work", output / "bundle"
    for directory in (logs, work, bundle):
        directory.mkdir()
    started, deadline = time.monotonic(), time.monotonic() + CI_SECONDS
    result = {"schema_version": 1, "status": "FAIL", "code_revision": expected, "stages": [],
              "acoustic_acceptance": False, "training": "NOT_RUN", "physical_target_measurement": False}
    try:
        result["host"] = assert_actions_host()
        result["input_files_sha256"] = committed_inputs(expected)
        lock = load_json(source.LOCK)
        archives = work / "archives"
        archives.mkdir()
        download_deadline = time.monotonic() + remaining(deadline, 120)
        for spec in lock["archives"].values():
            download(spec, archives / spec["filename"], download_deadline)
        result["stages"].append("fixed-source-archives-downloaded-and-rehashed")
        venv, env = tools_environment(work, logs, lock, deadline)
        result["stages"].append("fixed-tool-wheels-rehashed-and-installed-offline")
        prepared = bundle / "prepared"
        source.preflight(archives, prepared)
        require(remaining(deadline, 600) == 600, "insufficient remaining budget for fixed source build")
        build_root = work / "build"
        built = source.build(prepared, build_root, str(venv / "bin/meson"), str(venv / "bin/ninja"))
        require(built["status"] == "BUILT_FIXED_REFERENCE_NO_ACOUSTIC_MEASUREMENT"
                and built["controls"]["commit"] == expected, "invalid source build receipt")
        result["stages"].append("fixed-source-built-and-reverified")
        build_evidence = bundle / "build"
        build_evidence.mkdir()
        for name in ("build-receipt.json", "setup.log", "compile.log"):
            shutil.copyfile(build_root / name, build_evidence / name)
        meson_log = build_root / "meson/meson-logs/meson-log.txt"
        if meson_log.is_file():
            shutil.copyfile(meson_log, build_evidence / "meson-log.txt")
        binary_dir = bundle / "bin"
        binary_dir.mkdir()
        binary = binary_dir / "webrtc-aec3-runner"
        compiler = built["tools"]["cxx"]
        compile_command = [compiler["path"], "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"]
        compile_command += system_includes(built["link"]["cflags"])
        compile_command += [str(RUNNER)] + built["link"]["libs"] + ["-Wl,-rpath,$ORIGIN/lib", "-o", str(binary)]
        command(compile_command, logs / "adapter-compile.log", env, deadline, 90)
        require(binary.is_file() and os.access(binary, os.X_OK), "adapter binary missing")
        build_env = dict(env, LD_LIBRARY_PATH=os.pathsep.join(built["link"]["runtime_library_dirs"]))
        runtime_hashes, system_libraries = copy_research_libraries(binary, build_root, bundle, build_env, built["link"]["libraries"])
        no_absolute_rpath(binary, env)
        for name in runtime_hashes:
            no_absolute_rpath(bundle / name, env)
        # Prove that neither absolute RUNPATH nor the original build can rescue a missing library.
        build_root.rename(work / "build-hidden-before-engineering")
        portable_env = dict(env, LD_LIBRARY_PATH=str(binary_dir / "lib"))
        observed = runtime_identity(binary, portable_env)
        for relative, digest in runtime_hashes.items():
            resolved = str((bundle / relative).resolve())
            require(observed["library_names"].get(Path(relative).name) == resolved
                    and observed["libraries"].get(resolved) == digest, "portable research library resolution mismatch")
        adapter = {"schema_version": 1, "status": "BUILT_ADAPTER", "code_revision": expected,
                   "runner_source_sha256": sha256(RUNNER.read_bytes()), "binary_sha256": sha256(binary.read_bytes()),
                   "orchestration_source_sha256": sha256(Path(__file__).read_bytes()),
                   "build_receipt_sha256": sha256((build_evidence / "build-receipt.json").read_bytes()),
                   "compiler": compiler, "command": compile_command, "runtime_libraries": runtime_hashes,
                   "system_libraries": system_libraries, "runtime_identity": observed,
                   "portability_scope": "original build directory removed; research libraries bundled; observed Ubuntu 24.04 host ABI; no cross-distribution claim"}
        source.write_json(build_evidence / "runner-build.json", adapter)
        shutil.copyfile(logs / "adapter-compile.log", build_evidence / "adapter-compile.log")
        result["stages"].append("adapter-built-and-portable-research-libraries-resolved")
        engineering = bundle / "engineering"
        command([sys.executable, "-B", str(FIXTURES), "--binary", str(binary), "--output", str(engineering),
                 "--build-receipt", str(build_evidence / "build-receipt.json"), "--code-revision", expected],
                logs / "engineering.log", portable_env, deadline, 125)
        report = load_json(engineering / "engineering.json")
        require(report["status"] == "PASS_ENGINEERING_ONLY" and report["code_revision"] == expected
                and report["binary_sha256"] == adapter["binary_sha256"]
                and report["fixture_source_sha256"] == sha256(FIXTURES.read_bytes())
                and report["runtime_identity_source_sha256"] == adapter["orchestration_source_sha256"]
                and report["build_receipt_sha256"] == adapter["build_receipt_sha256"], "engineering evidence identity mismatch")
        require(type(report["requested_capture_audio_seconds"]) in (int, float)
                and 0 < report["requested_capture_audio_seconds"] <= 10 and not report["failures"]
                and type(report["wall_seconds"]) in (int, float) and math.isfinite(report["wall_seconds"])
                and 0 < report["wall_seconds"] <= 120
                and report["acoustic_acceptance"] is False and report["promotion_authority"] is False,
                "engineering budget/scope failure")
        require(report.get("runtime_identity") == observed, "engineering runtime identity missing or changed")
        require(sha256(binary.read_bytes()) == adapter["binary_sha256"]
                and all(sha256((bundle / name).read_bytes()) == digest for name, digest in runtime_hashes.items()),
                "portable binary/library bytes changed during engineering")
        source.admitted(prepared)
        require(source.committed_controls() == built["controls"], "source-build controls changed during engineering")
        require(committed_inputs(expected) == result["input_files_sha256"], "orchestration inputs changed during execution")
        remaining(deadline, 1)
        paths = {"runner": "bin/webrtc-aec3-runner", "prepared": "prepared", "build_receipt": "build/build-receipt.json",
                 "adapter_build": "build/runner-build.json", "engineering": "engineering/engineering.json"}
        manifest = {"schema_version": 1, "status": "PASS_ENGINEERING_ONLY", "code_revision": expected,
                    "files": manifest_files(bundle), "paths": paths}
        source.write_json(bundle / "bundle.json", manifest)
        archive = output / "webrtc-aec3-engineering-bundle.tar.gz"
        result["bundle_archive"] = {"path": archive.name, "size": None, "sha256": pack_bundle(bundle, archive)}
        result["bundle_archive"]["size"] = archive.stat().st_size
        remaining(deadline, 1)
        result["stages"].append("real-portable-binary-engineering-passed-and-bundled")
        result["status"] = "PASS_ENGINEERING_ONLY"
    except Exception as error:
        result["error"] = str(error)
        invalidate_bundle(output)
        # Preserve only actual evidence from the failed prefix, never a substitute PASS.
        for candidate in (work / "build", work / "build-hidden-before-engineering"):
            if candidate.is_dir():
                failed = output / "failed-build-evidence"
                failed.mkdir(exist_ok=True)
                for path in candidate.glob("*.log"):
                    shutil.copyfile(path, failed / path.name)
                if (candidate / "build-receipt.json").is_file():
                    shutil.copyfile(candidate / "build-receipt.json", failed / "build-receipt.json")
                meson_log = candidate / "meson/meson-logs/meson-log.txt"
                if meson_log.is_file():
                    shutil.copyfile(meson_log, failed / "meson-log.txt")
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        result["log_sha256"] = {path.name: sha256(path.read_bytes()) for path in logs.glob("*.log")}
        try:
            source.write_json(output / "ci-receipt.json", result)
        except Exception:
            invalidate_bundle(output)
            raise
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    item = sub.add_parser("run")
    item.add_argument("--expected-head", required=True)
    item.add_argument("--output", type=Path, required=True)
    sub.add_parser("select")
    args = parser.parse_args()
    try:
        if args.command == "select":
            select_workflow()
        else:
            print(json.dumps(run(args.expected_head, args.output), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        print("webrtc-aec3-ci: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
