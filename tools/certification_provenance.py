#!/usr/bin/env python3
"""Create and verify shipping binary/toolchain provenance across builder and DUT."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

VERSION = "1.0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha256(root: Path) -> str:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    h = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            h.update(b"L\0" + rel + b"\0" + os.readlink(path).encode() + b"\0")
        elif path.is_file():
            h.update(b"F\0" + rel + b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    h.update(chunk)
            h.update(b"\0")
        elif path.is_dir():
            h.update(b"D\0" + rel + b"\0")
    return h.hexdigest()


def compiler_version(path: Path) -> str:
    return subprocess.check_output([str(path), "--version"], text=True, stderr=subprocess.STDOUT).splitlines()[0]


def binary_map(paths: list[Path]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        if resolved.name in result:
            raise ValueError(f"duplicate binary name: {resolved.name}")
        result[resolved.name] = sha256(resolved)
    if not result:
        raise ValueError("at least one binary is required")
    return result


def snapshot(args: argparse.Namespace) -> dict:
    if args.stage not in {"build", "deployed", "executed"}:
        raise ValueError("invalid stage")
    doc = {
        "schema_version": 1,
        "collector_version": VERSION,
        "stage": args.stage,
        "source_revision": args.revision,
        "runner_name": args.runner_name,
        "runner_arch": args.runner_arch,
        "binary_sha256": binary_map(args.binary),
    }
    if args.stage == "build":
        if not all((args.compiler, args.sysroot, args.toolchain_root, args.cflags is not None)):
            raise ValueError("build snapshot requires compiler, sysroot, toolchain root and cflags")
        compiler = args.compiler.resolve()
        sysroot = args.sysroot.resolve()
        toolchain = args.toolchain_root.resolve()
        doc["toolchain"] = {
            "compiler_path": str(compiler),
            "compiler_sha256": sha256(compiler),
            "compiler_version": compiler_version(compiler),
            "sysroot_path": str(sysroot),
            "sysroot_sha256": tree_sha256(sysroot),
            "toolchain_root_path": str(toolchain),
            "toolchain_root_sha256": tree_sha256(toolchain),
            "cflags": args.cflags,
        }
    return doc


def verify(build: dict, deployed: dict, executed: dict) -> dict:
    stages = ((build, "build"), (deployed, "deployed"), (executed, "executed"))
    for doc, stage in stages:
        if doc.get("schema_version") != 1 or doc.get("stage") != stage:
            raise ValueError(f"invalid {stage} snapshot")
    revisions = {doc.get("source_revision") for doc, _ in stages}
    if len(revisions) != 1:
        raise ValueError("source revisions differ across build/deploy/execute")
    hashes = [doc.get("binary_sha256") for doc, _ in stages]
    if not (hashes[0] == hashes[1] == hashes[2]):
        raise ValueError("build/deployed/executed binary SHA-256 maps differ")
    if build.get("runner_name") == deployed.get("runner_name"):
        raise ValueError("shipping builder and DUT must be different runners")
    if deployed.get("runner_name") != executed.get("runner_name"):
        raise ValueError("deployed and executed snapshots must come from the same DUT")
    toolchain = build.get("toolchain")
    if not isinstance(toolchain, dict):
        raise ValueError("build snapshot is missing toolchain identity")
    return {
        "schema_version": 1,
        "collector_version": VERSION,
        "source_revision": next(iter(revisions)),
        "builder_runner": build["runner_name"],
        "dut_runner": deployed["runner_name"],
        "binary_sha256": hashes[0],
        "toolchain": toolchain,
        "result": "PASS",
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-provenance-") as temporary:
        root = Path(temporary)
        binary = root / "ap_bench"
        binary.write_bytes(b"binary")
        toolchain = root / "tc"
        sysroot = toolchain / "sysroot"
        sysroot.mkdir(parents=True)
        (sysroot / "libc.so").write_bytes(b"libc")
        compiler = toolchain / "cc"
        compiler.write_text("#!/bin/sh\necho test-cc 1.0\n", encoding="utf-8")
        compiler.chmod(0o755)
        common = {
            "schema_version": 1,
            "collector_version": VERSION,
            "source_revision": "a" * 40,
            "runner_arch": "X64",
            "binary_sha256": {"ap_bench": sha256(binary)},
        }
        build = {**common, "stage": "build", "runner_name": "builder", "toolchain": {"compiler_sha256": "b" * 64}}
        deployed = {**common, "stage": "deployed", "runner_name": "dut"}
        executed = {**common, "stage": "executed", "runner_name": "dut"}
        assert verify(build, deployed, executed)["result"] == "PASS"
        assert len(tree_sha256(toolchain)) == 64
    print("certification provenance self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    snap = sub.add_parser("snapshot")
    snap.add_argument("--stage", required=True, choices=["build", "deployed", "executed"])
    snap.add_argument("--revision", required=True)
    snap.add_argument("--runner-name", required=True)
    snap.add_argument("--runner-arch", required=True)
    snap.add_argument("--binary", action="append", type=Path, required=True)
    snap.add_argument("--compiler", type=Path)
    snap.add_argument("--sysroot", type=Path)
    snap.add_argument("--toolchain-root", type=Path)
    snap.add_argument("--cflags")
    snap.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("--build", type=Path, required=True)
    check.add_argument("--deployed", type=Path, required=True)
    check.add_argument("--executed", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.command == "snapshot":
        result = snapshot(args)
        output = args.output
    elif args.command == "verify":
        result = verify(
            json.loads(args.build.read_text(encoding="utf-8")),
            json.loads(args.deployed.read_text(encoding="utf-8")),
            json.loads(args.executed.read_text(encoding="utf-8")),
        )
        output = args.output
    else:
        parser.error("snapshot or verify is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
