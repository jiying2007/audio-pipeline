#!/usr/bin/env python3
"""Fail-closed release metadata preparation for audio-pipeline."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

VERSION_TOKEN_RE = re.compile(
    r"(project\s*\([^)]*?\bVERSION\s+)([0-9]+\.[0-9]+\.[0-9]+)", re.S
)
CHANGELOG_HEADING_RE = re.compile(r"^#\s+([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)


def semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", value)
    if not match:
        raise ValueError(f"invalid SemVer: {value}")
    return tuple(int(item) for item in match.groups())


def cmake_version(text: str) -> str:
    match = VERSION_TOKEN_RE.search(text)
    if not match:
        raise ValueError("CMake project VERSION not found")
    return match.group(2)


def changelog_version(text: str) -> str:
    match = CHANGELOG_HEADING_RE.search(text)
    if not match:
        raise ValueError("CHANGELOG top version not found")
    return match.group(1)


def read_git_text(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True)


def check(root: Path, *, expect_version: str | None = None, base_ref: str | None = None) -> None:
    cmake = (root / "CMakeLists.txt").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    cver = cmake_version(cmake)
    hver = changelog_version(changelog)
    if cver != hver:
        raise ValueError(f"release metadata drift: CMake={cver} CHANGELOG={hver}")
    if expect_version and cver != expect_version:
        raise ValueError(f"unexpected release version: expected={expect_version} actual={cver}")
    if base_ref:
        base_cmake = read_git_text(base_ref, "CMakeLists.txt")
        base_changelog = read_git_text(base_ref, "CHANGELOG.md")
        base_version = cmake_version(base_cmake)
        marker = f"# {base_version}"
        pos = changelog.find(marker)
        if pos < 0:
            raise ValueError(f"head CHANGELOG no longer contains base release heading {marker}")
        if changelog[pos:] != base_changelog:
            raise ValueError("historical CHANGELOG content changed below the new release section")
        if semver(cver) <= semver(base_version):
            raise ValueError(f"release version did not advance: base={base_version} head={cver}")


def apply(root: Path, target: str, notes: str) -> None:
    semver(target)
    notes = notes.strip()
    if not notes or not all(line.startswith("- ") or not line.strip() for line in notes.splitlines()):
        raise ValueError("release notes must contain non-empty Markdown bullet lines")
    cmake_path = root / "CMakeLists.txt"
    changelog_path = root / "CHANGELOG.md"
    cmake = cmake_path.read_text(encoding="utf-8")
    changelog = changelog_path.read_text(encoding="utf-8")
    current = cmake_version(cmake)
    if changelog_version(changelog) != current:
        raise ValueError("current CMake/CHANGELOG versions already drift")
    if semver(target) <= semver(current):
        raise ValueError(f"target version must advance current version: {current} -> {target}")
    updated_cmake, count = VERSION_TOKEN_RE.subn(lambda m: m.group(1) + target, cmake, count=1)
    if count != 1:
        raise ValueError("expected exactly one CMake project VERSION token")
    updated_changelog = f"# {target}\n\n{notes}\n\n" + changelog
    cmake_path.write_text(updated_cmake, encoding="utf-8")
    changelog_path.write_text(updated_changelog, encoding="utf-8")
    check(root, expect_version=target)


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        root.joinpath("CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.16)\nproject(audio_pipeline VERSION 2.3.6 LANGUAGES C)\n",
            encoding="utf-8",
        )
        historical = "# 2.3.6\n\n- old\n\n# 2.3.5\n\n- older\n"
        root.joinpath("CHANGELOG.md").write_text(historical, encoding="utf-8")
        apply(root, "2.3.7", "- fix authority\n- preserve ABI")
        check(root, expect_version="2.3.7")
        assert root.joinpath("CHANGELOG.md").read_text(encoding="utf-8").endswith(historical)
        try:
            apply(root, "2.3.7", "- duplicate")
        except ValueError:
            pass
        else:
            raise AssertionError("non-advancing release version was accepted")
    print("prepare release self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--version")
    parser.add_argument("--notes-file", type=Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    root = args.root.resolve()
    if args.apply:
        if not args.version or not args.notes_file:
            parser.error("--apply requires --version and --notes-file")
        apply(root, args.version, args.notes_file.read_text(encoding="utf-8"))
    if args.check or not args.apply:
        check(root, expect_version=args.version, base_ref=args.base_ref)
    print("release metadata preparation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
