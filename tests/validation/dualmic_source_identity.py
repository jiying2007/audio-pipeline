#!/usr/bin/env python3
"""Bind dual-mic host integrations to reviewed R7/R9 public source bytes.

This is an identity adapter, not a new FE09 collector or historical replay.
It uses only current-tree objects, including in a depth-one CI checkout.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "docs/research/frontend-evolution-v1/"
LOCK = PREFIX + "FE09_B3_F0_PREREGISTRATION_20261024/source-lock.json"
LOCK_SHA256 = "32bd625ee640bf60310bcdc9980a5f8a41711300aee66f029fbf65c98a9bb49d"
PROFILES = {
    "2.3.63": (PREFIX + "DUALMIC_2363_SOURCE_R7_20261106/PREREGISTRATION.json",
               "3486635106f865a069b4241515db7bb00ac84a38fa7f5059305d11e27db3fb87"),
    "2.3.64": (PREFIX + "DUALMIC_2364_SOURCE_R9_20261110/PREREGISTRATION.json",
               "73a177bd3d96e1a158ac8d0a89045616482761ed8a574053b49705b9095011a7"),
}
BOUND_SOURCES = (
    "tests/validation/dualmic_source_identity.py",
    "tests/validation/test_dualmic_source_identity.py",
    PREFIX + "DUALMIC_NONDEVICE_2364_SOURCE_MIGRATION.zh-CN.md",
    LOCK, *(path for path, _ in PROFILES.values()),
)


class Rejected(ValueError):
    pass


def need(value, reason):
    if not value:
        raise Rejected(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def registered_sources(version, read_bytes):
    need(type(version) is str and version in PROFILES, "unregistered DSP source version")
    lock = read_bytes(LOCK)
    path, expected = PROFILES[version]
    plan = read_bytes(path)
    need(digest(lock) == LOCK_SHA256, "original public source lock changed")
    need(digest(plan) == expected, "reviewed source registration changed")
    rows = json.loads(lock)["files"]
    result = {row["path"]: {k: row[k] for k in ("bytes", "sha256", "git_blob_sha1")}
              for row in rows if row["role"] == "unchanged_public_build_snapshot_superset"}
    registration = json.loads(plan)
    need(len(result) == 56 and registration["candidate_version"] == version,
         "public source registration scope changed")
    reviewed = registration["reviewed_source"]
    need(len(reviewed) == 13 and set(reviewed) <= set(result), "reviewed source delta changed")
    result.update({name: row["after"] for name, row in reviewed.items()})
    return result


def verify_build(version, revision, *, root=ROOT):
    """Reject mixed, dirty, unknown-version or old-R8 source; return identity only."""
    need(type(revision) is str and re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
         "exact source revision required")

    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, check=False,
                                capture_output=True, timeout=30)
        need(result.returncode == 0, "source Git read failed: " + " ".join(args[:2]))
        return result.stdout

    def read_bytes(name):
        path = root / name
        need(path.is_file() and not path.is_symlink(), "missing or unsafe source: " + name)
        return path.read_bytes()

    need(git("rev-parse", "HEAD").decode().strip() == revision, "current source revision mismatch")
    tree = {}
    for row in git("ls-tree", "-r", "-z", revision).split(b"\0"):
        if row:
            info, name = row.split(b"\t", 1)
            mode, kind, blob = info.decode().split()
            tree[name.decode()] = (mode, kind, blob)
    expected = registered_sources(version, read_bytes)
    public_paths = {p for p in expected if p.startswith(("src/", "include/"))}
    need({p for p in tree if p.startswith(("src/", "include/"))} == public_paths,
         "public source membership changed")
    working_paths = set()
    for directory in (root / "src", root / "include"):
        need(directory.is_dir() and not directory.is_symlink(), "unsafe public source directory")
        for path in directory.rglob("*"):
            need(not path.is_symlink(), "unsafe public source path")
            if path.is_file():
                working_paths.add(path.relative_to(root).as_posix())
    need(working_paths == public_paths, "working public source membership changed")
    for name in (*BOUND_SOURCES, *expected):
        data = read_bytes(name)
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        need(name in tree and tree[name][0] in ("100644", "100755")
             and tree[name][1:] == ("blob", blob), "uncommitted source: " + name)
        if name in expected:
            row = expected[name]
            need(len(data) == row["bytes"] and digest(data) == row["sha256"]
                 and blob == row["git_blob_sha1"], "unreviewed public source: " + name)
    match = re.fullmatch(rb"project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)",
                         read_bytes("CMakeLists.txt").splitlines()[1])
    need(match is not None and match[1].decode() == version, "binary/source version mismatch")
    return {"version": version, "source_revision": revision,
            "registration_sha256": PROFILES[version][1], "public_source_members": len(expected),
            "historical_result_inherited": False}
