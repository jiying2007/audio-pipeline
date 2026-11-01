#!/usr/bin/env python3
"""A3-R2-T1: compile exact archived objects only; never link/run A3."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[3]
REL = "tests/validation/frontend_evolution/"
T0 = REL + "fe09_a3_r2_source_audit.py"
T0_BLOB = "d0dba25e0b01821577d21f02cb892336dd479548"
RUNNER = REL + "fe09_f1_r2_build.py"
RUNNER_BLOB = "a4f20160d024109ebc7cb1af7371c00f8acff82e"
ARCHIVE = "c4e9cb92af2fe42f09f09bcac0d0a814a511aab8"
ARCHIVE_FILES = {
    REL + "fe09_a3_f0_live_roll.c": "3b79ca0681afd77e48d85fa0646ccea4fa744d62",
    REL + "fe09_a3_f0_live_roll.h": "dff07def1aabcd2c1e3361e3f55f4050e4676cc1",
    REL + "fe09_a3_f0_original_validator.c": "3d9af35bd4323716e43bc6d82e552a267a5905af",
}
C_UNITS = (REL + "fe09_a3_f0_live_roll.c", REL + "fe09_a3_f0_original_validator.c")
MODES = ("native-gcc", "native-clang", "sanitized", "arm32")
STATUS = "A3_R2_T1_STATIC_OBJECTS_ONLY_NO_EXECUTION"
DENIALS = dict.fromkeys((
    "a3_worker_executed", "a3_dsp_executed", "source_admission_granted",
    "provider_qualified", "external_freeze_verified", "formal_controls_qualified",
    "rolling_33_49_qualified", "rss_measured", "public_sdk_qualified",
    "ssc305_hil_qualified", "shipping_authority"), False)
COMMON = ("-std=c11", "-O2", "-fno-fast-math", "-ffp-contract=off", "-fno-lto",
          "-fstack-usage", "-fno-common", "-Wall", "-Wextra", "-Wpedantic", "-Werror")
MAX_OBJECT = 4194304


class Rejected(ValueError):
    pass


def need(value: bool, reason: str) -> None:
    if not value:
        raise Rejected(reason)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pin_module(root: Path, name: str, expected: str):
    path = root / name
    need(path.resolve().is_relative_to(root.resolve()), "A3_PIN_PATH_UNSAFE")
    need(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), "A3_PIN_NOT_REGULAR")
    raw = path.read_bytes()
    need(len(raw) <= 1000000 and hashlib.sha1(b"blob " +
         str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected,
         "A3_PROTECTED_HELPER_DRIFT")
    module = types.ModuleType("a3_t1_pin_" + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def source_proof(root: Path, t0, runner) -> dict:
    report = t0.execute(root)
    need(report.get("status") == t0.STATUS and report.get("source_only") is True and
         report.get("source_comparison", {}).get("original_88_checked") == 88 and
         report["source_comparison"].get("registered_88_equal_current") is True and
         all(report.get(key) is False for key in t0.DENIALS),
         "A3_T0_SOURCE_AUDIT_REQUIRED")
    g = t0.GitReader(root)
    current = g.tree(report["execution_commit"])
    archive = g.tree(ARCHIVE)
    source_members = {}
    for path, expected in ARCHIVE_FILES.items():
        entry = current.get(path)
        need(entry == ("100644", expected) and archive.get(path) == entry,
             "A3_ORIGINAL_OBJECT_SOURCE_DRIFT")
        exact = g.blob(expected, t0.MAX_FILE)
        workpath = root / path
        need(workpath.resolve().is_relative_to(root.resolve()) and
             not workpath.is_symlink() and stat.S_ISREG(workpath.stat().st_mode),
             "A3_WORKTREE_SOURCE_UNSAFE")
        raw = runner.read_file(workpath, t0.MAX_FILE)
        need(raw == exact and runner.blob(raw) == expected,
             "A3_ARCHIVE_AND_WORKTREE_BYTES_DRIFT")
        source_members[path] = {"blob": expected, "sha256": sha256(raw), "bytes": len(raw)}
    return {"commit": report["execution_commit"], "tree": report["execution_tree"],
            "original_88_checked": 88, "registered_88_equal_current": True,
            "current_tree_is_original_tree":
                report["source_comparison"]["current_tree_is_original_tree"],
            "t0_pin": T0_BLOB, "process_helper_pin": RUNNER_BLOB,
            "archive": ARCHIVE, "original_a3_members": source_members}


def command(cc: str, mode: str, source: Path, destination: Path) -> list[str]:
    need(mode in MODES and source.name in
         ("fe09_a3_f0_live_roll.c", "fe09_a3_f0_original_validator.c") and
         source.suffix == ".c" and destination.suffix == ".o",
         "A3_COMPILE_SCOPE_REJECT")
    args = [cc, *COMMON]
    if mode == "sanitized":
        args += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    if mode == "arm32":
        args += ["-mcpu=cortex-a32", "-mfpu=neon-vfpv4", "-mfloat-abi=hard"]
    return [*args, "-c", str(source), "-o", str(destination)]


def object_info(raw: bytes, mode: str) -> dict:
    need(mode in MODES and 64 <= len(raw) <= MAX_OBJECT and
         raw[:4] == b"\x7fELF" and raw[5:7] == b"\x01\x01",
         "A3_ELF_HEADER_REJECT")
    cls, machine = (1, 40) if mode == "arm32" else (2, 62)
    need(raw[4] == cls and int.from_bytes(raw[16:18], "little") == 1 and
         int.from_bytes(raw[18:20], "little") == machine,
         "A3_RELOCATABLE_OBJECT_ARCH_REJECT")
    return {"bytes": len(raw), "sha256": sha256(raw),
            "elf_class": cls, "elf_machine": machine, "elf_type": 1}


def build_only(root: Path, output: Path) -> dict:
    t0 = pin_module(root, T0, T0_BLOB)
    runner = pin_module(root, RUNNER, RUNNER_BLOB)
    source = source_proof(root, t0, runner)
    out = runner.reserve_output(root, output)
    receipt = {"schema_version": 1, "status": "A3_R2_T1_STATIC_BUILD_REJECTED",
               "source": source, "a3_generated_executions": 0, **DENIALS,
               "modes": {}, "compilers": {}}
    deadline = time.monotonic() + 420
    try:
        names = ("gcc", "clang", "arm-linux-gnueabihf-gcc")
        tools = {}
        for name in names:
            path = shutil.which(name, path=runner.environment()["PATH"])
            need(path is not None and path.startswith(("/usr/bin/", "/bin/")),
                 "A3_REQUIRED_PINNED_COMPILER_MISSING")
            tools[name] = path
            raw = runner.read_file(Path(path).resolve())
            version = runner.run_tool([path, "--version"], root,
                                      out / (name + ".version.log"), deadline)
            receipt["compilers"][name] = {"path": path, "sha256": sha256(raw),
                                          "version_sha256": sha256(version)}
        for mode in MODES:
            directory = out / mode
            directory.mkdir(mode=0o700)
            name = ("clang" if mode == "native-clang" else
                    "arm-linux-gnueabihf-gcc" if mode == "arm32" else "gcc")
            observations = {}
            for unit in C_UNITS:
                src = root / unit
                obj = directory / (src.stem + ".o")
                argv = command(tools[name], mode, src, obj)
                data = runner.run_tool(argv, root,
                                       out / (mode + "." + src.stem + ".compile.log"),
                                       deadline)
                value = object_info(runner.read_file(obj, MAX_OBJECT), mode)
                value["object_name"] = obj.relative_to(out).as_posix()
                value["source_blob"] = ARCHIVE_FILES[unit]
                value["compile_argv"] = argv
                value["tool_log_sha256"] = sha256(data)
                observations[src.name] = value
            need(len(observations) == 2, "A3_OBJECT_COUNT_DRIFT")
            receipt["modes"][mode] = observations
        need(len(receipt["modes"]) == 4 and
             source_proof(root, t0, runner) == source, "A3_SOURCE_CHANGED_DURING_COMPILE")
        need(time.monotonic() <= deadline, "A3_STATIC_COMPILE_DEADLINE")
        receipt["status"] = STATUS
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        reason = str(exc)
        receipt["reason"] = (reason if isinstance(exc, Rejected) and
                             reason.isascii() and len(reason) < 120
                             else "A3_STATIC_OBJECT_BUILD_FAILED")
        runner.save(out / "receipt.json", runner.encoded(receipt))
        tails = {}
        for path in sorted(out.glob("*.log"))[:15]:
            with path.open("rb") as fp:
                fp.seek(max(0, path.stat().st_size - 4096))
                tails[path.name] = fp.read(4096).decode("utf-8", errors="replace")
        print(json.dumps({"rejected_receipt": receipt, "log_tails": tails},
                         sort_keys=True), file=sys.stderr)
        raise
    encoded = runner.encoded(receipt)
    runner.save(out / "receipt.json", encoded)
    runner.save(out / "receipt.json.sha256",
                (sha256(encoded) + "  receipt.json\n").encode())
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build_only(ROOT, args.output), sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, KeyError, TypeError):
        print(json.dumps({"status": "A3_R2_T1_STATIC_BUILD_REJECTED",
                          "a3_generated_executions": 0, **DENIALS}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
