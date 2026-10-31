#!/usr/bin/env python3
"""F1-R2-T1 build-only integration. Never execute a generated F1 image."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
SELF = REL + "fe09_f1_r2_build.py"
BRIDGE = REL + "fe09_f1_r2_source_bridge.py"
BRIDGE_BLOB = "1bebcaa5a13e85b817bf6776107fa0a92b0db249"
ARCHIVE = "9ac5a209b16210c7e514d57711f22c9b27354cb8"
SOURCES = {
    REL + "fe09_t3s3_f1_rss_launcher.c": "7059add3eb99d00ff0575c3e6e6cd4f1debf9ae8",
    REL + "fe09_t3s3_f1_rss_observer.c": "e03c8f711ae2af0a1c3f8d9401e28cf097ea38cf",
    REL + "fe09_t3s3_f1_rss_fixture.c": "ad994d6f7d15902c22aee76d4019e003b8e4f8cf",
    REL + "fe09_t3s3_f1_build/CMakeLists.txt": "95d9b43f634ed40520b537da71efc0aa25399e9b",
}
PLAIN, PROBE = "fe09_b3_f0_plain", "fe09_t3s3_f0_probe"
HELPERS = ("fe09_t3s3_f1_launcher", "fe09_t3s3_f1_fixture")
COMMON = ("array_native.c", "fe09_b1b0_src.c", "fe09_b2s3_t2b_b0_capture_only.c",
          "fe09_b2s3_t2b_b1s0_owner_spsc.c", "fe09_b3_f0_composition.c",
          "fe09_b3_f0_observer.c", "fe09_t3s3_f1_rss_observer.c")
DENIALS = dict.fromkeys(("f1_executed", "provider_authority_acquired", "measurement_qualified",
    "formal_controls_qualified", "full_f1_source_closure_qualified", "shipping_authority",
    "ssc305_hil_qualified"), False)
STATUS = "F1_R2_T1_BUILD_ONLY_NO_EXECUTION"
MAX_LOG, MAX_FILE = 1048576, 67108864


class Rejected(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise Rejected(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_file(path, cap=MAX_FILE):
    need(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), "REGULAR_FILE_REQUIRED")
    with path.open("rb") as stream:
        raw = stream.read(cap + 1)
    need(0 < len(raw) <= cap, "FILE_BYTES_BOUND")
    return raw


def save(path, raw):
    with path.open("xb") as stream:
        need(stream.write(raw) == len(raw), "EVIDENCE_SHORT_WRITE")


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def source_check(root):
    raw = read_file(root / BRIDGE, 262144)
    need(blob(raw) == BRIDGE_BLOB, "PROTECTED_T0_DRIFT")
    module = types.ModuleType("f1_build_protected_t0")
    module.__file__ = str(root / BRIDGE)
    # Compile the verified bytes, never use a possibly stale bytecode cache.
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    proof = module.check(root)
    need(proof["status"] == "F1_R2_T0_SOURCE_BRIDGE_VERIFIED_NO_EXECUTION" and
         all(proof.get(k) is False for k in module.DENIALS), "T0_SOURCE_PROOF_REQUIRED")
    git = module.Git(root)
    revision = proof["execution_source"]
    members = {}
    for path, expected in SOURCES.items():
        current = git.current(revision, path)
        need(blob(current) == expected and current == git.blob(ARCHIVE, path), "ARCHIVED_BUILD_SOURCE_DRIFT")
        members[path] = {"git_blob": expected, "sha256": sha(current), "bytes": len(current)}
    own = git.current(revision, SELF)
    return {"commit": revision, "tree": proof["execution_tree"], "t0_receipt_sha256": sha(encoded(proof)),
            "observer_sha256": sha(own), "archived_build_members": members}


def environment():
    # No inherited compiler flags/launchers, loader injection or provider token.
    return {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LC_ALL": "C", "TZ": "UTC"}


def run_tool(argv, cwd, log, deadline):
    """Bounded merged output; one owned process group, no retries."""
    end = min(deadline, time.monotonic() + 60)
    need(end - time.monotonic() > .5, "BUILD_STAGE_DEADLINE")
    data, reaped = bytearray(), False
    process = None
    error = None
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=environment(), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = end - .5 - time.monotonic()
                need(remaining > 0, "BUILD_TOOL_TIMEOUT")
                for key, _ in selector.select(remaining):
                    try:
                        chunk = os.read(key.fd, min(65536, MAX_LOG - len(data) + 1))
                    except BlockingIOError:
                        continue
                    need(len(data) + len(chunk) <= MAX_LOG, "BUILD_LOG_BOUND")
                    if chunk:
                        data.extend(chunk)
                    else:
                        selector.unregister(key.fd)
            remaining = end - .5 - time.monotonic()
            need(remaining > 0, "BUILD_TOOL_TIMEOUT")
            code = process.wait(timeout=remaining)
            reaped = True
            need(code == 0, "BUILD_TOOL_FAILED")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        error = exc
    finally:
        try:
            if process is not None and not reaped:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                remaining = end - time.monotonic()
                need(remaining > 0, "BUILD_CLEANUP_DEADLINE")
                process.wait(timeout=remaining)
                reaped = True
        finally:
            if process is not None:
                process.stdout.close()
            save(log, bytes(data))
    need(time.monotonic() <= end, "BUILD_TOOL_DEADLINE_EXCEEDED")
    if error is not None:
        raise error
    return bytes(data)


def targets(mode):
    need(mode in ("native", "sanitized", "arm32"), "UNKNOWN_BUILD_MODE")
    return (PLAIN, PROBE, *HELPERS) if mode == "native" else (PLAIN, PROBE)


def configure(root, build, mode, cmake, compiler):
    targets(mode)
    args = [cmake, "-S", str(root / (REL + "fe09_t3s3_f1_build")), "-B", str(build),
            "-G", "Unix Makefiles", "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
            "-DCMAKE_C_COMPILER=" + compiler, "-DB3_F0_SANITIZE=" + ("ON" if mode == "sanitized" else "OFF")]
    if mode == "arm32":
        args += ["-DCMAKE_SYSTEM_NAME=Linux", "-DCMAKE_SYSTEM_PROCESSOR=arm",
                 "-DCMAKE_C_FLAGS=-mcpu=cortex-a32 -mfpu=neon-vfpv4 -mfloat-abi=hard"]
    return args


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "DUPLICATE_COMPILE_DATABASE_KEY")
        result[key] = value
    return result


def audit_commands(raw, root, build, mode):
    rows = json.loads(raw.decode(), object_pairs_hook=pairs)
    need(type(rows) is list and 0 < len(rows) <= 1000, "COMPILE_DATABASE_REQUIRED")
    found = {t: [] for t in targets(mode)}
    for row in rows:
        need(type(row) is dict and type(row.get("command")) is str, "COMPILE_RECORD_INVALID")
        args = shlex.split(row["command"])
        need(args.count("-o") == 1 and args.index("-o") + 1 < len(args), "COMPILE_OUTPUT_REQUIRED")
        output = args[args.index("-o") + 1]
        for target in found:
            if "CMakeFiles/" + target + ".dir/" not in output:
                continue
            need(Path(row["directory"]).resolve().is_relative_to(build.resolve()), "BUILD_DIRECTORY_DRIFT")
            path = Path(row["file"]).resolve()
            need(path.is_relative_to(root.resolve()), "COMPILE_SOURCE_OUTSIDE_REPOSITORY")
            relative = path.relative_to(root.resolve()).as_posix()
            need(all(flag in args for flag in ("-ffp-contract=off", "-fno-fast-math", "-fno-lto",
                     "-fstack-usage", "-Wall", "-Wextra", "-Wpedantic", "-Werror")), "COMPILE_FLAGS_DRIFT")
            need("-ffast-math" not in args and not any(a.startswith("-flto") for a in args), "UNSAFE_NUMERICAL_FLAGS")
            need(("-fsanitize=address,undefined" in args) == (mode == "sanitized"), "SANITIZER_MODE_DRIFT")
            found[target].append(relative)
    for target, paths in found.items():
        if target in HELPERS:
            expected = {REL + "fe09_t3s3_f1_rss_" + target.rsplit("_", 1)[1] + ".c"}
        else:
            expected = {REL + p for p in COMMON}
            expected.add(REL + ("fe09_b3_f0_composition_test.c" if target == PLAIN else "fe09_t3s3_f0_call_resource_probe.c"))
        need(len(paths) == len(expected) and set(paths) == expected, "TARGET_TRANSLATION_UNITS_DRIFT")
    if mode != "native":
        need(not any(any("CMakeFiles/" + h + ".dir/" in r["command"] for h in HELPERS) for r in rows),
             "NATIVE_HELPERS_IN_OTHER_MODE")
    return found


def elf_header(raw, mode):
    targets(mode)
    need(len(raw) >= 64 and raw[:4] == b"\x7fELF" and raw[5] == 1 and raw[6] == 1, "ELF_HEADER_INVALID")
    expected_class, expected_machine = (1, 40) if mode == "arm32" else (2, 62)
    need(raw[4] == expected_class and int.from_bytes(raw[18:20], "little") == expected_machine and
         int.from_bytes(raw[16:18], "little") in (2, 3), "ELF_ARCHITECTURE_DRIFT")
    return {"class": expected_class, "machine": expected_machine, "bytes": len(raw), "sha256": sha(raw)}


def verify_symbols(raw, wrapped):
    names = {line.split()[-1] for line in raw.decode("ascii").splitlines() if line.split()}
    need("main" in names and (("__wrap_main" in names) == wrapped), "MAIN_WRAPPER_LINK_DRIFT")


def reserve_output(root, output):
    need(output.is_absolute(), "ABSOLUTE_OUTPUT_REQUIRED")
    parent = output.parent.resolve(strict=True)
    need(not parent.is_relative_to(root.resolve()), "BUILD_MUST_STAY_OUTSIDE_SOURCE")
    path = parent / output.name
    path.mkdir(mode=0o700)
    return path


def build_only(root, output):
    before = source_check(root)
    output = reserve_output(root, output)
    report = {"schema_version": 1, "status": "F1_R2_T1_BUILD_REJECTED", "source": before,
              "generated_target_executions": 0, **DENIALS, "tools": {}, "modes": {}}
    deadline = time.monotonic() + 480
    try:
        tools = {}
        for name in ("cmake", "gcc", "nm", "arm-linux-gnueabihf-gcc", "arm-linux-gnueabihf-nm"):
            executable = shutil.which(name, path=environment()["PATH"])
            need(executable is not None, "BUILD_TOOL_UNAVAILABLE")
            tools[name] = executable
            raw = read_file(Path(executable).resolve())
            version = run_tool([executable, "--version"], root, output / (name + ".version.log"), deadline)
            report["tools"][name] = {"path": executable, "sha256": sha(raw), "version_sha256": sha(version)}
        for mode in ("native", "sanitized", "arm32"):
            directory = output / mode
            cc = tools["arm-linux-gnueabihf-gcc" if mode == "arm32" else "gcc"]
            run_tool(configure(root, directory, mode, tools["cmake"], cc), root, output / (mode + ".configure.log"), deadline)
            run_tool([tools["cmake"], "--build", str(directory), "--parallel", "2", "--target", *targets(mode)],
                     root, output / (mode + ".build.log"), deadline)
            database = read_file(directory / "compile_commands.json", MAX_LOG)
            units = audit_commands(database, root, directory, mode)
            images = {}
            for target in targets(mode):
                path = directory / ("f0/b3/" + target if target == PLAIN else target)
                info = elf_header(read_file(path), mode)
                nm = tools["arm-linux-gnueabihf-nm" if mode == "arm32" else "nm"]
                symbols = run_tool([nm, "--defined-only", str(path)], root, output / (mode + "." + target + ".nm.log"), deadline)
                verify_symbols(symbols, target not in HELPERS)
                info["symbols_sha256"] = sha(symbols)
                info["path"] = path.relative_to(output).as_posix()
                images[target] = info
            report["modes"][mode] = {"compile_database_sha256": sha(database), "translation_units": units, "images": images}
        need(source_check(root) == before, "SOURCE_CHANGED_DURING_BUILD")
        need(time.monotonic() <= deadline, "BUILD_STAGE_DEADLINE")
        report["status"] = STATUS
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        reason = str(exc)
        report["reason"] = reason if reason.isascii() and reason.replace("_", "").isalnum() and len(reason) <= 100 else "BUILD_OR_EVIDENCE_UNAVAILABLE"
        save(output / "receipt.json", encoded(report))
        # CI retains the rejection and bounded diagnostic tails even when its
        # temporary build directory disappears. Tails are not complete logs.
        tails = {}
        for path in sorted(output.glob("*.log")):
            if len(tails) == 19:
                break
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 8192))
                tails[path.name] = stream.read(8192).decode("utf-8", errors="replace")
        print(json.dumps({"rejected_receipt": report, "diagnostic_log_tails": tails}, sort_keys=True), file=sys.stderr)
        raise
    save(output / "receipt.json", encoded(report))
    save(output / "receipt.json.sha256", (sha(encoded(report)) + "  receipt.json\n").encode())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build_only(ROOT, args.output)
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print(json.dumps({"status": "F1_R2_T1_BUILD_REJECTED", "generated_target_executions": 0, **DENIALS}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
