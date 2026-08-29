#!/usr/bin/env python3
"""Fail-closed readiness contract for trusted self-hosted runner roles.

This tool validates only runner/environment prerequisites. It never converts
infrastructure readiness into acoustic, HIL, performance or product-certified
evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Callable

SCHEMA_VERSION = 1
ROLES = (
    "audio-validation",
    "audio-builder",
    "audio-target",
    "certification-archive",
)
ROLE_COMMANDS = {
    "audio-validation": ("python3", "cmake", "cc", "git", "git-lfs"),
    "audio-builder": ("python3", "cmake", "git", "sha256sum", "tar"),
    "audio-target": ("python3", "git", "sha256sum"),
    "certification-archive": ("python3", "git", "sha256sum"),
}


def _check(check_id: str, ok: bool, detail: str) -> dict:
    return {"id": check_id, "ok": bool(ok), "detail": detail}


def _path_check(check_id: str, raw: str | None, kind: str, *, required: bool) -> dict:
    if not raw:
        return _check(check_id, not required, "not supplied" if not required else "required path not supplied")
    path = Path(raw)
    exists = path.exists()
    if kind == "file":
        ok = exists and path.is_file() and os.access(path, os.R_OK)
        detail = f"readable file: {path}" if ok else f"missing/unreadable file: {path}"
    elif kind == "dir":
        ok = exists and path.is_dir() and os.access(path, os.R_OK | os.X_OK)
        detail = f"readable directory: {path}" if ok else f"missing/unreadable directory: {path}"
    elif kind == "exec":
        ok = exists and path.is_file() and os.access(path, os.X_OK)
        detail = f"executable: {path}" if ok else f"missing/non-executable file: {path}"
    elif kind == "readable":
        ok = exists and os.access(path, os.R_OK)
        detail = f"readable path: {path}" if ok else f"missing/unreadable path: {path}"
    elif kind == "writable":
        ok = exists and os.access(path, os.W_OK | (os.X_OK if path.is_dir() else 0))
        detail = f"writable path: {path}" if ok else f"missing/non-writable path: {path}"
    else:
        raise ValueError(f"unknown path kind: {kind}")
    return _check(check_id, ok, detail)


def evaluate(
    args: argparse.Namespace,
    *,
    which: Callable[[str], str | None] = shutil.which,
    system_name: str | None = None,
) -> dict:
    checks: list[dict] = []
    current_system = system_name or platform.system()
    checks.append(_check("os-linux", current_system == "Linux", f"system={current_system}"))

    commands = list(ROLE_COMMANDS[args.role]) + list(args.require_command or [])
    seen: set[str] = set()
    for command in commands:
        if command in seen:
            continue
        seen.add(command)
        resolved = which(command)
        checks.append(_check(f"command:{command}", resolved is not None, resolved or "not found in PATH"))

    if args.role == "audio-validation":
        checks.append(_path_check("validation:data-root", args.data_root, "dir", required=True))
        checks.append(_path_check("validation:seal", args.seal, "file", required=True))
        checks.append(_path_check("validation:dns-data-root", args.dns_data_root, "dir", required=False))
    elif args.role == "audio-builder":
        checks.append(_path_check("builder:shipping-cc", args.shipping_cc, "exec", required=True))
        checks.append(_path_check("builder:shipping-sysroot", args.shipping_sysroot, "dir", required=True))
        checks.append(_path_check("builder:shipping-toolchain-root", args.shipping_toolchain_root, "dir", required=True))
    elif args.role == "audio-target":
        checks.append(_path_check("target:board-manifest", args.board_manifest, "file", required=False))
        checks.append(_path_check("target:corpus-manifest", args.corpus_manifest, "file", required=False))
        checks.append(_path_check("target:acoustic-json", args.acoustic_json, "file", required=False))
        checks.append(_path_check("target:farend-file", args.farend_file, "file", required=False))
        checks.append(_path_check("target:power-input", args.power_input, "readable", required=False))
    elif args.role == "certification-archive":
        checks.append(_path_check("archive:command", args.archive_command, "exec", required=True))

    for index, writable in enumerate(args.writable_path or []):
        checks.append(_path_check(f"writable:{index}", writable, "writable", required=True))

    failures = [item for item in checks if not item["ok"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "role": args.role,
        "classification": "READY" if not failures else "NOT_READY",
        "runner": {
            "name": os.environ.get("RUNNER_NAME") or None,
            "arch": os.environ.get("RUNNER_ARCH") or platform.machine(),
            "os": current_system,
        },
        "checks": checks,
        "failure_count": len(failures),
    }


def write_report(report: dict, output: Path | None) -> None:
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(text, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(json.dumps({"classification": report["classification"], "role": report["role"], "output": str(output)}, sort_keys=True))


def _namespace(role: str, **overrides: object) -> argparse.Namespace:
    values = {
        "role": role,
        "require_command": [],
        "data_root": None,
        "seal": None,
        "dns_data_root": None,
        "shipping_cc": None,
        "shipping_sysroot": None,
        "shipping_toolchain_root": None,
        "board_manifest": None,
        "corpus_manifest": None,
        "acoustic_json": None,
        "farend_file": None,
        "power_input": None,
        "archive_command": None,
        "writable_path": [],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def self_test() -> None:
    assert set(ROLE_COMMANDS) == set(ROLES)
    assert "git-lfs" in ROLE_COMMANDS["audio-validation"]
    assert "cmake" in ROLE_COMMANDS["audio-builder"]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = root / "data"
        data.mkdir()
        seal = data / "datasets.seal.json"
        seal.write_text("{}\n", encoding="utf-8")
        cc = root / "shipping-cc"
        cc.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cc.chmod(cc.stat().st_mode | stat.S_IXUSR)
        sysroot = root / "sysroot"
        toolchain = root / "toolchain"
        sysroot.mkdir()
        toolchain.mkdir()
        archive = root / "archive"
        archive.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        archive.chmod(archive.stat().st_mode | stat.S_IXUSR)

        fake_which = lambda command: f"/fake/{command}"
        validation = evaluate(
            _namespace("audio-validation", data_root=str(data), seal=str(seal), writable_path=[str(data)]),
            which=fake_which,
            system_name="Linux",
        )
        assert validation["classification"] == "READY", validation

        builder = evaluate(
            _namespace(
                "audio-builder",
                shipping_cc=str(cc),
                shipping_sysroot=str(sysroot),
                shipping_toolchain_root=str(toolchain),
            ),
            which=fake_which,
            system_name="Linux",
        )
        assert builder["classification"] == "READY", builder

        archive_report = evaluate(
            _namespace("certification-archive", archive_command=str(archive)),
            which=fake_which,
            system_name="Linux",
        )
        assert archive_report["classification"] == "READY", archive_report

        missing = evaluate(
            _namespace("audio-validation", data_root=str(root / "missing"), seal=str(seal)),
            which=fake_which,
            system_name="Linux",
        )
        assert missing["classification"] == "NOT_READY"
        assert missing["failure_count"] == 1

        wrong_os = evaluate(
            _namespace("audio-target"), which=fake_which, system_name="Windows"
        )
        assert wrong_os["classification"] == "NOT_READY"

    print("self-hosted runner preflight self-test: OK")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--role", choices=ROLES)
    result.add_argument("--output", type=Path)
    result.add_argument("--require-command", action="append", default=[])
    result.add_argument("--writable-path", action="append", default=[])

    result.add_argument("--data-root")
    result.add_argument("--seal")
    result.add_argument("--dns-data-root")

    result.add_argument("--shipping-cc")
    result.add_argument("--shipping-sysroot")
    result.add_argument("--shipping-toolchain-root")

    result.add_argument("--board-manifest")
    result.add_argument("--corpus-manifest")
    result.add_argument("--acoustic-json")
    result.add_argument("--farend-file")
    result.add_argument("--power-input")

    result.add_argument("--archive-command", default="/usr/local/bin/audio-pipeline-cert-archive")
    result.add_argument("--self-test", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.role:
        raise SystemExit("--role is required unless --self-test is used")
    report = evaluate(args)
    write_report(report, args.output)
    if report["classification"] != "READY":
        for item in report["checks"]:
            if not item["ok"]:
                print(f"RUNNER_NOT_READY: {item['id']}: {item['detail']}", file=os.sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
