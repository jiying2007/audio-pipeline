"""Strict whitespace checking with protected-base immutable import identities.

An ordinary clean diff always uses Git's strict result. Exceptions require an
already registered, byte-identical base policy and checker, complete Git blob
identities and exact diagnostic bytes. No working-tree content grants authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

POLICY = ".github/research/frontend-evolution-v1/immutable-whitespace-v1.json"
HELPER = "tools/codex_assets/immutable_whitespace.py"
ROOT = Path(__file__).resolve().parents[2]


def clean_env() -> dict:
    # Neither caller Git config injection nor system/global attributes grant
    # archive authority. Normal PATH/toolchain selection remains explicit.
    return {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_ATTR_NOSYSTEM": "1"}


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "color.ui=false", "-c", "core.quotePath=false",
         "-c", "core.whitespace=blank-at-eol,blank-at-eof,space-before-tab",
         *args], cwd=root, env=clean_env(),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def output(root: Path, *args: str) -> bytes:
    proc = git(root, *args)
    if proc.returncode or proc.stderr:
        raise ValueError("Git operation failed: " + repr(args))
    return proc.stdout


def blob(root: Path, ref: str, path: str, mode: str = "100644") -> bytes:
    entry = output(root, "ls-tree", "-z", ref, "--", path)
    if not entry.startswith((mode + " blob ").encode()) or entry.count(b"\0") != 1:
        raise ValueError("expected one ordinary " + mode + " Git blob: " + path)
    if entry.split(b"\t", 1)[1][:-1].decode() != path:
        raise ValueError("Git path identity mismatch")
    return output(root, "show", ref + ":" + path)


def no_duplicates(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate policy key")
        result[key] = value
    return result


def records(raw: bytes) -> dict:
    policy = json.loads(raw, object_pairs_hook=no_duplicates)
    if set(policy) != {"schema_version", "scope", "files"} or policy["schema_version"] != 1:
        raise ValueError("invalid policy schema")
    if policy["scope"] != "immutable-historical-import-only" or not policy["files"]:
        raise ValueError("invalid policy scope")
    for path, item in policy["files"].items():
        if (not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                or PurePosixPath(path).is_absolute() or ".." in path.split("/")
                or "//" in path or path.endswith("/") or path in {POLICY, HELPER}):
            raise ValueError("invalid policy path")
        if (set(item) != {"sha256", "mode", "diagnostics_sha256", "warnings"}
                or item["mode"] not in {"100644", "100755"} or type(item["warnings"]) is not int
                or item["warnings"] < 1
                or any(not isinstance(item[k], str) or not re.fullmatch(r"[a-f0-9]{64}", item[k])
                       for k in ("sha256", "diagnostics_sha256"))):
            raise ValueError("invalid immutable identity")
    return policy["files"]


def diff_check(root: Path, span: str, paths: list[str] | None = None):
    left, right = span.split("...")
    left = output(root, "rev-parse", "--verify", left + "^{commit}").decode().strip()
    right = output(root, "rev-parse", "--verify", right + "^{commit}").decode().strip()
    span = left + "..." + right
    args = ["diff", "--no-ext-diff", "--no-renames", "--check", span]
    if paths is not None:
        args += ["--", *paths]
    # A fresh bare object view has no worktree/index/info/global attributes.
    # It shares read-only objects, never repository config or executable hooks.
    common = output(root, "rev-parse", "--git-common-dir").decode().strip()
    objects = (root / common / "objects").resolve()
    with tempfile.TemporaryDirectory(prefix="immutable-diff-") as temp:
        view = Path(temp)
        output(view, "init", "--bare", "--template=", "--quiet")
        proc = subprocess.run(
            ["git", "-c", "color.ui=false", "-c", "core.quotePath=false",
             "-c", "core.whitespace=blank-at-eol,blank-at-eof,space-before-tab", *args],
            cwd=view, env={**clean_env(), "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(objects)},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    if proc.returncode not in {0, 2} or proc.stderr:
        raise ValueError("unexpected git diff --check failure: " + repr(proc.stderr))
    if (proc.returncode == 0) != (proc.stdout == b""):
        raise ValueError("unexpected git diff --check output")
    return proc


def check(root: Path, base: str, head: str) -> dict:
    # Resolve caller inputs to exact commits before using revision expressions.
    base = output(root, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    head = output(root, "rev-parse", "--verify", head + "^{commit}").decode().strip()
    span = base + "..." + head
    full = diff_check(root, span)
    if full.returncode == 0:
        return {"status": "STRICT_PASS", "exceptions": 0, "original_exit": 0}
    before = blob(root, base, POLICY)
    if before != blob(root, head, POLICY) or blob(root, base, HELPER) != blob(root, head, HELPER):
        raise ValueError("policy/checker cannot change in an excepted import")
    registered = records(before)
    names = output(root, "diff", "--name-only", "--no-renames", "-z", span).decode().split("\0")[:-1]
    admitted = []
    expected_diagnostics = []
    for path in names:
        item = registered.get(path)
        if item is None:
            continue
        raw = blob(root, head, path, item["mode"])
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("immutable blob changed: " + path)
        # An exception is solely for first import, never modification/rename.
        change = output(root, "diff", "--name-status", "--no-renames", span, "--", path)
        # Rename detection must inspect the whole diff, not only one path.
        renames = output(root, "diff", "--name-status", "--find-renames", span).decode().splitlines()
        incoming_rename = any(line.startswith("R") and line.split("\t")[-1] == path for line in renames)
        if change != ("A\t" + path + "\n").encode() or incoming_rename:
            raise ValueError("exception requires an added original path: " + path)
        diagnostic = diff_check(root, span, [path])
        if diagnostic.returncode != 2 or hashlib.sha256(diagnostic.stdout).hexdigest() != item["diagnostics_sha256"]:
            raise ValueError("immutable diagnostic changed: " + path)
        count = len(re.findall(rb"^" + re.escape(path.encode()) + rb":\d+: (?:trailing whitespace\.|new blank line at EOF\.)$", diagnostic.stdout, re.M))
        if count != item["warnings"]:
            raise ValueError("immutable warning type/count changed")
        admitted.append(path)
        expected_diagnostics.append(diagnostic.stdout)
    if not admitted or full.stdout != b"".join(expected_diagnostics):
        raise ValueError("unregistered or reordered whitespace diagnostics")
    remainder = [path for path in names if path not in admitted]
    if remainder and diff_check(root, span, remainder).returncode:
        raise ValueError("strict remainder failed")
    return {"status": "IMMUTABLE_IMPORT_VERIFIED", "exceptions": len(admitted),
            "warnings": sum(registered[p]["warnings"] for p in admitted),
            "strict_remaining_paths": len(remainder), "original_exit": 2}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.root, args.base, args.head), sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, "immutable whitespace check rejected: " + str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
