#!/usr/bin/env python3
"""Replay retired governance tests from one fixed Git commit, never live admission.

Requires an existing full-history checkout. No fetch, credentials, live observer,
Release API, policy re-signing or experimental retry is provided by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "tests/fixtures/archived-governance.json"
COMMIT = "e504368662f41d0a731f7ca777f4d62af7f92754"
TREE = "e720700b4f4f83f242eeab8d137b61276371f937"
TESTS = (
    (".github/program/test_pr833_metadata_observation_d1.py", ("", "-O", "-OO"), ()),
    (".github/program/test_dechorate_event_source_t1m3.py", ("",), ("--self-test",)),
    (".github/program/test_dechorate_governance_v2.py", ("",), ()),
    (".github/program/test_dechorate_consumer_receipt.py", ("", "-O", "-OO"), ()),
)


def clean_environment(home):
    # Do not pass tokens, proxy settings, GH config, Python injection, SSH agents,
    # Actions context or Git overrides to historical source or its subprocesses.
    return {
        "PATH": os.environ.get("PATH", os.defpath), "HOME": str(home),
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "file",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def run(command, cwd, env, deadline, capture=False):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("historical test deadline exhausted")
    # A timeout only terminates the process group created by this invocation.
    with subprocess.Popen(
        command, cwd=str(cwd), env=env, start_new_session=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    ) as child:
        try:
            stdout, stderr = child.communicate(timeout=remaining)
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            raise
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode, command, stdout, stderr)
        return stdout.decode("utf-8").strip() if capture else None


def git(root, env, deadline, *args):
    return run(["git", "-c", "safe.directory=" + str(root), "-c",
                "core.hooksPath=" + os.devnull, *args], root, env, deadline, True)


def load_manifest(root):
    value = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if value.get("historical_commit") != COMMIT or value.get("historical_tree") != TREE:
        raise ValueError("historical source identity changed")
    paths = value.get("retired_paths")
    if not isinstance(paths, dict) or len(paths) != 11:
        raise ValueError("historical source roster changed")
    for name, digest in paths.items():
        parts = Path(name).parts
        if (not parts or Path(name).is_absolute() or ".." in parts
                or Path(name).as_posix() != name or not isinstance(digest, str)
                or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("invalid historical source entry")
    for name, _, _ in TESTS:
        if name not in paths:
            raise ValueError("historical test missing from roster")
    if paths.get("scripts/github_governance.py") != (
            "c292105f27126e643f8984bd0ecb52faf7beac83ddeffff9413b97a68893c4fa"):
        raise ValueError("historical governance bytes changed")
    return value


def verify_archive(archive, manifest):
    for name, expected in manifest["retired_paths"].items():
        path = archive / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("historical source missing or aliased: " + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("historical source byte mismatch: " + name)


def replay(root):
    if os.name != "posix":
        raise ValueError("historical offline Git regressions require a POSIX test host")
    manifest = load_manifest(root)
    deadline = time.monotonic() + 900
    with tempfile.TemporaryDirectory(prefix="archived-governance-tests-") as temp:
        area = Path(temp)
        home = area / "home"
        home.mkdir()
        env = clean_environment(home)
        actual_tree = git(root, env, deadline, "rev-parse", "--verify", COMMIT + "^{tree}")
        if actual_tree != TREE:
            raise ValueError("exact historical Git tree unavailable; use a full-history checkout")
        archive = area / "source"
        git(root, env, deadline, "clone", "--quiet", "--shared", "--no-checkout",
            "--local", str(root), str(archive))
        git(archive, env, deadline, "checkout", "--quiet", "--detach", COMMIT)
        if git(archive, env, deadline, "rev-parse", "HEAD") != COMMIT:
            raise ValueError("archive checkout is not the fixed historical commit")
        verify_archive(archive, manifest)
        # Old tests explicitly mock external HTTP. Make accidental gh CLI use
        # fail even if a host has an authenticated GitHub configuration.
        blocked = area / "bin"
        blocked.mkdir()
        gh = blocked / "gh"
        gh.write_text("#!/bin/sh\necho 'live GitHub CLI is retired in archive tests' >&2\nexit 97\n")
        gh.chmod(0o700)
        env["PATH"] = str(blocked) + os.pathsep + env["PATH"]
        completed = []
        for name, modes, extra in TESTS:
            for mode in modes:
                command = [sys.executable, "-B"] + ([mode] if mode else [])
                command += [str(archive / name), *extra]
                run(command, archive, env, deadline)
                completed.append({"test": name, "mode": mode or "normal"})
        verify_archive(archive, manifest)
        git(archive, env, deadline, "diff", "--exit-code", "HEAD", "--")
    return {"scope": "historical-offline-regression-only", "commit": COMMIT,
            "tree": TREE, "completed": completed, "live_observation_performed": False,
            "scientific_experiment_executed": False, "current_admission_granted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # No user-supplied source, command, endpoint or live mode.
    try:
        result = replay(ROOT)
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as error:
        print("archived governance regression failed: " + type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
