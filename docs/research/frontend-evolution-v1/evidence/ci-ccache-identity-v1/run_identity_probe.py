#!/usr/bin/env python3
"""Bounded actual-CMake identity probe; no ccache or DSP execution."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--cmake", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    started = time.monotonic()
    if args.phase == "before":
        output.mkdir(parents=True, exist_ok=False)
        summary = {"budget_seconds": 300, "elapsed_seconds": 0.0, "cases": [],
                   "actual_ccache_invoked": False,
                   "not_run": ["actual_ccache", "remote_Actions", "DSP", "physical_SSC305"]}
    else:
        summary = json.loads((output / "summary.json").read_text())
        assert len(summary["cases"]) == 2
    prior_elapsed = summary["elapsed_seconds"]

    def remaining():
        available = 300 - prior_elapsed - (time.monotonic() - started)
        if available <= 0:
            raise TimeoutError("frozen 300 second measurement budget exhausted")
        return available

    def run(command, check=True):
        return subprocess.run(command, cwd=source, capture_output=True,
                              timeout=remaining(), check=check)

    def git(*arguments):
        return run(["git", *arguments]).stdout.decode().strip()

    def persist():
        summary["elapsed_seconds"] = prior_elapsed + time.monotonic() - started
        write_json(output / "summary.json", summary)

    def case(name, dirty):
        destination = output / name
        destination.mkdir()
        head = git("rev-parse", "HEAD")
        expected = head + ("-dirty" if dirty else "")
        status = run(["git", "status", "--porcelain"])
        (destination / "git-status-before.txt").write_bytes(status.stdout)
        ignored = run(["git", "check-ignore", "-v", "--", ".ccache/identity-probe.txt"], check=False)
        (destination / "git-check-ignore-cache.txt").write_bytes(ignored.stdout + ignored.stderr)
        (destination / "tracked-diff.patch").write_bytes(run(["git", "diff", "--", "src", "include", "CMakeLists.txt"]).stdout)
        build = args.build_root.resolve() / name
        assert not build.exists(), "each configuration must use a fresh build directory"
        command = [str(args.cmake.resolve()), "-S", str(source), "-B", str(build),
                   "-DCMAKE_BUILD_TYPE=Release", "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON"]
        write_json(destination / "command.json", command)
        config_started = time.monotonic()
        completed = run(command, check=False)
        (destination / "configure.stdout.txt").write_bytes(completed.stdout)
        (destination / "configure.stderr.txt").write_bytes(completed.stderr)
        generated = build / "generated/audio_pipeline/audio_pipeline_build.h"
        observed = None
        if generated.exists():
            shutil.copyfile(generated, destination / "audio_pipeline_build.h")
            match = re.search(r'^#define AP_BUILD_SOURCE_REVISION "([^"]+)"$', generated.read_text(), re.M)
            observed = match.group(1) if match else None
        (destination / "git-status-after.txt").write_bytes(run(["git", "status", "--porcelain"]).stdout)
        record = {"case": name, "head": head, "expected_source_revision": expected,
                  "observed_source_revision": observed,
                  "strict_40hex_revision_equality": observed == head,
                  "cmake_exit_code": completed.returncode,
                  "configure_elapsed_seconds": time.monotonic() - config_started,
                  "cache_check_ignore_exit_code": ignored.returncode,
                  "source_files_sha256": {str(p): digest(source / p) for p in
                      (Path(".gitignore"), Path("CMakeLists.txt"), Path("src/ap_build_info.c"))}}
        record["passed"] = completed.returncode == 0 and observed == expected
        write_json(destination / "observation.json", record)
        summary["cases"].append(record)
        persist()
        print(json.dumps({key: record[key] for key in
            ("case", "head", "observed_source_revision", "strict_40hex_revision_equality", "passed")}), flush=True)
        assert record["passed"], "CMake did not satisfy the frozen identity expectation"
        return record

    cache = source / ".ccache/identity-probe.txt"
    untracked = source / "src/ci_identity_untracked_probe.c"
    tracked = source / "src/ap_build_info.c"
    if args.phase == "before":
        assert git("status", "--porcelain") == ""
        assert not cache.exists() and not untracked.exists()
        version = run([str(args.cmake.resolve()), "--version"])
        (output / "cmake-version.txt").write_bytes(version.stdout)
        case("before-clean", False)
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(b"Artificial cache-presence probe; no ccache invocation.\n")
        summary["cache_probe_sha256"] = digest(cache)
        observed = case("before-cache", True)
        assert observed["cache_check_ignore_exit_code"] == 1
        summary["result"] = "AWAITING_CANDIDATE"
    else:
        assert cache.exists() and digest(cache) == summary["cache_probe_sha256"]
        assert git("status", "--porcelain") == ""
        observed = case("after-cache", False)
        assert observed["cache_check_ignore_exit_code"] == 0
        original = tracked.read_bytes()
        assert not untracked.exists()
        try:
            untracked.write_bytes(b"/* Untracked source probe outside the cache. */\n")
            untracked_ignore = run(["git", "check-ignore", "-v", "--", "src/ci_identity_untracked_probe.c"], check=False)
            assert untracked_ignore.returncode == 1
            case("after-untracked-source", True)
            untracked.unlink()
            tracked.write_bytes(original + b"\n/* Tracked source modification probe; restored after configure. */\n")
            case("after-tracked-source", True)
        finally:
            tracked.write_bytes(original)
            if untracked.exists():
                untracked.unlink()
            cache.unlink()
            cache.parent.rmdir()
        assert git("status", "--porcelain") == ""
        (output / "final-git-status.txt").write_bytes(run(["git", "status", "--porcelain"]).stdout)
        summary["result"] = "PASS" if len(summary["cases"]) == 5 and all(c["passed"] for c in summary["cases"]) else "FAIL"
    persist()
    remaining()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
