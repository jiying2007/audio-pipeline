#!/bin/sh
# One offline documentation/assurance gate for docs-only and full verification.
# I010 is terminal: validate the current registry, never require retired live inputs.
set -eu

# A3_R1_SOURCE_SCOPE_GUARD_BEGIN
# This phase uses only actual event/local Git and never grants A3 execution.
if [ "${1:-}" != --f1-scope-only ]; then
  if [ -n "${GITHUB_EVENT_NAME:-}" ]; then
    python3 -I - <<'PY_A3_PROTECTED_BASE'
#!/usr/bin/env python3
"""FE09 A3 R1 protected-base source admission.

The local scope phase has no HTTP client and grants no experiment authority.
The first implementation checkpoint installs this source-only bootstrap.  Its
offline controls inspect in-memory source/metadata; they never run a C target.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from typing import Any


IDENTITY = "FE09-A3-F0-LIVE-SOURCE-ROLL-33-49-R1"
REPOSITORY = "jiying2007/audio-pipeline"
REPOSITORY_ID = 1347377137
BRANCH = "research/fe09-a3-f0-live-roll-20261024"
SCIENTIFIC_BASE = "7138b17acd6246cc779efa7597d25771ddfc8c7a"
GUARD = "tests/validation/frontend_evolution/fe09_a3_f0_source_admission.py"
DOC_ROOT = "docs/research/frontend-evolution-v1/FE09_A3_F0_LIVE_ROLL_PREREGISTRATION_R1_20261024"
SOURCE_PREFIX = "tests/validation/frontend_evolution/fe09_a3_f0_"
HOOKS = (".github/workflows/verify.yml", ".github/workflows/quality.yml",
         ".github/scripts/verify-docs-gate.sh")
SOURCE_FILES = (
    "fe09_a3_f0_original_validator.c", "fe09_a3_f0_live_roll.h",
    "fe09_a3_f0_live_roll.c", "fe09_a3_f0_live_roll_test.c",
    "fe09_a3_f0_live_roll_qualification.py", "fe09_a3_f0_source_admission.py",
)
BOOTSTRAP = "SOURCE_METADATA_ONLY_BOOTSTRAP_NO_A3_EXECUTION"
UNRELATED = "SOURCE_METADATA_ONLY_UNRELATED"
REQUIRED = "A3_REQUIRED_FOR_PROVIDER_ADMISSION"
DENIED = "SOURCE_SCOPE_DENIED"
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FILE_CAP = 1048576
DIFF_CAP = 2097152
STDERR_CAP = 65536
COMMAND_NS = 5_000_000_000
CLEANUP_RESERVE_NS = 250_000_000


class AdmissionError(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(reason + (": " + detail if detail else ""))


def require(condition: bool, reason: str, detail: str = "") -> None:
    if not condition:
        raise AdmissionError(reason, detail)


def strict_int(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def oid(value: Any) -> str:
    require(isinstance(value, str) and SHA1.fullmatch(value) is not None and value != "0" * 40,
            "GIT_OBJECT_ID_INVALID")
    return value


def strict_json(raw: bytes, cap: int = FILE_CAP) -> Any:
    require(len(raw) <= cap, "METADATA_BODY_BOUND_EXCEEDED")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "JSON_DUPLICATE_KEY", key)
            result[key] = value
        return result
    def constant(value: str) -> Any:
        raise AdmissionError("JSON_NONFINITE_NUMBER", value)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdmissionError("JSON_INVALID", type(exc).__name__) from exc


def safe_path(value: Any) -> str:
    require(isinstance(value, str) and bool(value) and not value.startswith("/"),
            "SOURCE_PATH_INVALID")
    require(not any(x in value for x in ("\x00", "\r", "\n", "\\")),
            "SOURCE_PATH_INVALID")
    require(all(part not in ("", ".", "..") for part in value.split("/")),
            "SOURCE_PATH_INVALID")
    return value


def read_regular(path: Path, cap: int) -> bytes:
    """Reject a link/oversize object before allocating or reading its payload."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AdmissionError("SOURCE_FILE_UNAVAILABLE", str(path)) from exc
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode), "SOURCE_FILE_NOT_REGULAR", str(path))
        require(0 <= first.st_size <= cap, "SOURCE_FILE_BOUND_EXCEEDED", str(path))
        chunks = bytearray()
        while len(chunks) <= cap:
            part = os.read(fd, min(65536, cap + 1 - len(chunks)))
            if not part:
                break
            require(len(chunks) + len(part) <= cap, "SOURCE_FILE_BOUND_EXCEEDED", str(path))
            chunks.extend(part)
        last = os.fstat(fd)
        require(len(chunks) <= cap, "SOURCE_FILE_BOUND_EXCEEDED", str(path))
        require((first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns) ==
                (last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns) and
                len(chunks) == first.st_size, "SOURCE_FILE_CHANGED_DURING_READ", str(path))
        return bytes(chunks)
    finally:
        os.close(fd)


@dataclasses.dataclass(frozen=True)
class DurationBudget:
    """The admitted duration is retained exactly; no float deadline subtraction."""
    start_ns: int
    duration_ns: int

    @classmethod
    def start(cls, duration_ns: int) -> "DurationBudget":
        require(strict_int(duration_ns, 1), "TIME_BUDGET_INVALID")
        return cls(time.monotonic_ns(), duration_ns)

    def remaining_ns(self, now_ns: int | None = None) -> int:
        now = time.monotonic_ns() if now_ns is None else now_ns
        require(strict_int(now) and now >= self.start_ns, "MONOTONIC_CLOCK_INVALID")
        return max(0, self.duration_ns - (now - self.start_ns))

    def receipt(self, now_ns: int | None = None) -> dict[str, int]:
        now = time.monotonic_ns() if now_ns is None else now_ns
        return {"start_monotonic_ns": self.start_ns,
                "admitted_duration_ns": self.duration_ns,
                "elapsed_ns": now - self.start_ns,
                "remaining_ns": self.remaining_ns(now)}


def local_git_environment() -> dict[str, str]:
    # Never inherit GIT_CONFIG_PARAMETERS, alternates, tracing, replacement,
    # protocol overrides or a candidate-controlled global configuration.
    result = {key: value for key, value in os.environ.items()
              if not key.startswith("GIT_") and key not in ("GH_TOKEN", "GITHUB_TOKEN")}
    result.update({"GIT_ALLOW_PROTOCOL": "", "GIT_NO_LAZY_FETCH": "1",
                   "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
                   "GIT_LITERAL_PATHSPECS": "1", "GIT_OPTIONAL_LOCKS": "0",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_CONFIG_SYSTEM": os.devnull, "GIT_PAGER": "cat",
                   "LC_ALL": "C"})
    return result


def _reap_owned(proc: subprocess.Popen[bytes], budget: DurationBudget) -> None:
    # Do not reap the leader with poll() before addressing its owned session.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    left = budget.remaining_ns()
    try:
        proc.wait(timeout=left / 1_000_000_000)
    except subprocess.TimeoutExpired as exc:
        raise AdmissionError("GIT_CHILD_LIFECYCLE_INCOMPLETE") from exc
    require(budget.remaining_ns() > 0, "GIT_COMMAND_WHOLE_OPERATION_TIMEOUT")


def bounded_git(root: Path, args: tuple[str, ...], cap: int) -> bytes:
    """No transport/lazy fetch; output is bounded during acquisition, not after."""
    require(strict_int(cap, 1) and cap <= DIFF_CAP, "GIT_OUTPUT_BOUND_INVALID")
    require(bool(args) and args[0] in ("rev-parse", "cat-file", "ls-tree", "diff"),
            "GIT_COMMAND_NOT_READ_ONLY")
    if args[0] == "diff":
        require(all(flag in args for flag in ("--no-renames", "--no-ext-diff", "--no-textconv")),
                "SOURCE_SCOPE_DIFF_INCOMPLETE")
    budget = DurationBudget.start(COMMAND_NS)
    command = ["git", "--no-lazy-fetch", "--no-replace-objects", "--no-pager",
               "-c", "protocol.allow=never", "-c", "core.fsmonitor=false",
               "-c", "core.hooksPath=/dev/null", "-c", "core.attributesFile=/dev/null",
               "-c", "diff.external=", "-c", "safe.directory=" + str(root), *args]
    proc = subprocess.Popen(command, cwd=root, env=local_git_environment(),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    assert proc.stdout is not None and proc.stderr is not None
    streams = {proc.stdout.fileno(): (bytearray(), cap),
               proc.stderr.fileno(): (bytearray(), STDERR_CAP)}
    stdout = streams[proc.stdout.fileno()][0]
    stderr = streams[proc.stderr.fileno()][0]
    selector = selectors.DefaultSelector()
    try:
        for fd in streams:
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ)
        while selector.get_map():
            left = budget.remaining_ns()
            require(left > CLEANUP_RESERVE_NS, "GIT_COMMAND_WHOLE_OPERATION_TIMEOUT")
            for key, _ in selector.select(min(0.05, (left - CLEANUP_RESERVE_NS) / 1e9)):
                output, limit = streams[key.fd]
                try:
                    part = os.read(key.fd, min(65536, limit + 1 - len(output)))
                except BlockingIOError:
                    continue
                if not part:
                    selector.unregister(key.fd)
                    continue
                require(len(output) + len(part) <= limit, "GIT_OUTPUT_BOUND_EXCEEDED")
                output.extend(part)
        left = budget.remaining_ns()
        require(left > CLEANUP_RESERVE_NS, "GIT_COMMAND_WHOLE_OPERATION_TIMEOUT")
        try:
            proc.wait(timeout=(left - CLEANUP_RESERVE_NS) / 1e9)
        except subprocess.TimeoutExpired as exc:
            raise AdmissionError("GIT_COMMAND_WHOLE_OPERATION_TIMEOUT") from exc
        require(proc.returncode == 0, "GIT_OBJECT_READ_FAILED",
                bytes(stderr[:512]).decode("utf-8", errors="replace"))
        require(budget.remaining_ns() > 0, "GIT_COMMAND_WHOLE_OPERATION_TIMEOUT")
        return bytes(stdout)
    except BaseException:
        _reap_owned(proc, budget)
        raise
    finally:
        selector.close()
        proc.stdout.close()
        proc.stderr.close()


@dataclasses.dataclass(frozen=True)
class TreeEntry:
    mode: str
    blob: str


class GitObjects:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)

    def run(self, *args: str, cap: int = FILE_CAP) -> bytes:
        return bounded_git(self.root, tuple(args), cap)

    def head(self) -> str:
        return oid(self.run("rev-parse", "--verify", "HEAD", cap=128).decode().strip())

    def commit(self, commit: str) -> tuple[str, tuple[str, ...]]:
        raw = self.run("cat-file", "commit", oid(commit), cap=65536)
        actual = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(actual == commit, "GIT_COMMIT_IDENTITY_MISMATCH")
        header = raw.split(b"\n\n", 1)[0]
        trees = [line[5:].decode("ascii") for line in header.splitlines() if line.startswith(b"tree ")]
        parents = tuple(oid(line[7:].decode("ascii")) for line in header.splitlines() if line.startswith(b"parent "))
        require(len(trees) == 1, "GIT_COMMIT_HEADER_INVALID")
        return oid(trees[0]), parents

    def entry(self, commit: str, path: str) -> TreeEntry | None:
        path = safe_path(path)
        raw = self.run("ls-tree", "-z", oid(commit), "--", path, cap=FILE_CAP)
        if not raw:
            return None
        require(raw.endswith(b"\0") and raw.count(b"\0") == 1, "GIT_TREE_ENTRY_INVALID")
        meta, actual = raw[:-1].split(b"\t", 1)
        mode, kind, object_id = meta.decode("ascii").split()
        require(actual == path.encode() and kind == "blob", "GIT_TREE_ENTRY_INVALID")
        return TreeEntry(mode, oid(object_id))

    def blob(self, commit: str, path: str, required: bool = True) -> bytes | None:
        entry = self.entry(commit, path)
        if entry is None:
            require(not required, "SOURCE_FILE_MISSING", path)
            return None
        require(entry.mode == "100644", "SOURCE_FILE_MODE_INVALID", path)
        size_raw = self.run("cat-file", "-s", entry.blob, cap=64)
        require(re.fullmatch(rb"(?:0|[1-9][0-9]*)\n", size_raw) is not None,
                "GIT_BLOB_SIZE_INVALID")
        size = int(size_raw)
        require(size <= FILE_CAP, "SOURCE_FILE_BOUND_EXCEEDED", path)
        raw = self.run("cat-file", "blob", entry.blob, cap=FILE_CAP)
        require(len(raw) == size, "GIT_BLOB_SIZE_MISMATCH")
        actual = hashlib.sha1(b"blob " + str(size).encode() + b"\0" + raw).hexdigest()
        require(actual == entry.blob, "GIT_BLOB_IDENTITY_MISMATCH")
        return raw

    def changed_paths(self, base: str, head: str) -> tuple[str, ...]:
        # --no-renames makes a protected rename-away remain an explicit deletion.
        raw = self.run("diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                       "--name-status", "-z", oid(base), oid(head), "--", cap=DIFF_CAP)
        if not raw:
            return ()
        require(raw.endswith(b"\0"), "SOURCE_SCOPE_DIFF_INCOMPLETE")
        values = raw[:-1].split(b"\0")
        require(len(values) % 2 == 0, "SOURCE_SCOPE_DIFF_INCOMPLETE")
        result: list[str] = []
        for index in range(0, len(values), 2):
            require(values[index] in (b"A", b"D", b"M", b"T"), "SOURCE_SCOPE_DIFF_INCOMPLETE")
            try:
                path = safe_path(values[index + 1].decode("utf-8"))
            except UnicodeError as exc:
                raise AdmissionError("SOURCE_SCOPE_DIFF_INCOMPLETE") from exc
            require(path not in result, "SOURCE_SCOPE_DIFF_INCOMPLETE")
            result.append(path)
        return tuple(result)


def local_source(event: dict[str, Any], env: dict[str, str], head: str,
                 parents: tuple[str, ...]) -> dict[str, str]:
    require(isinstance(event, dict), "EVENT_METADATA_INVALID")
    repo = event.get("repository", {})
    require(isinstance(repo, dict) and type(repo.get("id")) is int and
            repo["id"] == REPOSITORY_ID and repo.get("full_name") == REPOSITORY,
            "REPOSITORY_IDENTITY_DRIFT")
    require(env.get("GITHUB_REPOSITORY") == REPOSITORY and
            env.get("GITHUB_REPOSITORY_ID") == str(REPOSITORY_ID), "REPOSITORY_IDENTITY_DRIFT")
    require(env.get("GITHUB_RUN_ATTEMPT") == "1", "RUN_ATTEMPT_NOT_REGISTERED")
    require(env.get("GITHUB_SHA") == head, "RUN_HEAD_BINDING_DRIFT")
    kind = env.get("GITHUB_EVENT_NAME", "")
    if kind == "pull_request":
        pr = event.get("pull_request", {})
        require(isinstance(pr, dict), "PR_SOURCE_IDENTITY_DRIFT")
        base, candidate = pr.get("base", {}), pr.get("head", {})
        require(isinstance(base, dict) and isinstance(candidate, dict), "PR_SOURCE_IDENTITY_DRIFT")
        b, c = oid(base.get("sha")), oid(candidate.get("sha"))
        require(base.get("ref") == "main" and env.get("GITHUB_BASE_REF") == "main",
                "PR_SOURCE_IDENTITY_DRIFT")
        for side in (base, candidate):
            r = side.get("repo", {})
            require(isinstance(r, dict) and type(r.get("id")) is int and
                    r["id"] == REPOSITORY_ID and r.get("full_name") == REPOSITORY,
                    "PR_SOURCE_IDENTITY_DRIFT")
        require(parents == (b, c), "PR_TEST_MERGE_RELATION_DRIFT")
        require(pr.get("draft") is False and pr.get("state") == "open", "PR_SOURCE_IDENTITY_DRIFT")
        require(candidate.get("ref") == env.get("GITHUB_HEAD_REF"), "PR_SOURCE_IDENTITY_DRIFT")
        return {"event": kind, "B": b, "C": c, "checkout": head, "head_ref": candidate["ref"]}
    require(kind == "push" and event.get("ref") == "refs/heads/main" and
            env.get("GITHUB_REF") == "refs/heads/main", "EVENT_NOT_REGISTERED")
    require(event.get("after") == head and event.get("deleted") is False,
            "RUN_HEAD_BINDING_DRIFT")
    require(len(parents) == 1 and event.get("before") == parents[0], "MAIN_SQUASH_PARENT_DRIFT")
    # A local source phase cannot yet assert C or the merged PR branch.
    return {"event": kind, "B": parents[0], "C": "", "checkout": head, "head_ref": ""}



import runpy
import tempfile

def emit_bootstrap(source, changed):
    receipt = {"schema_version":1,"experiment_id":IDENTITY,"phase":"LOCAL_SOURCE_SCOPE_ONLY",
               "disposition":BOOTSTRAP,"a3_required":False,"actual_local_source":source,
               "changed_paths":list(changed),"api_requests":0,"HTTP_helper_starts":0,
               "scientific_C_target_starts":0,"DSP_frames":0,"scientific_execution_admitted":False,
               "provider_lineage_and_external_freeze_still_required":True}
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        fd = os.open(output, os.O_WRONLY | os.O_APPEND | getattr(os,"O_NOFOLLOW",0))
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_size <= STDERR_CAP,"GITHUB_OUTPUT_FILE_INVALID")
            raw = ("a3_required=false\na3_disposition="+BOOTSTRAP+"\ndisposition="+BOOTSTRAP+"\n").encode()
            require(os.write(fd,raw)==len(raw),"GITHUB_OUTPUT_WRITE_INCOMPLETE")
        finally:
            os.close(fd)
    print(json.dumps(receipt,sort_keys=True))

try:
    root = Path(os.environ["GITHUB_WORKSPACE"]).resolve(strict=True)
    event_path = Path(os.environ["GITHUB_EVENT_PATH"])
    git = GitObjects(root)
    head = git.head()
    _, parents = git.commit(head)
    source = local_source(strict_json(read_regular(event_path,FILE_CAP)),dict(os.environ),head,parents)
    protected_entry = git.entry(source["B"],GUARD)
    require(protected_entry is None or protected_entry.mode == "100644","PROTECTED_POLICY_MODE_DRIFT")
    protected = git.blob(source["B"],GUARD,required=False)
    if protected is None:
        emit_bootstrap(source,git.changed_paths(source["B"],head))
    else:
        # The candidate file is never imported to decide its own authority.
        with tempfile.TemporaryDirectory(prefix="a3-protected-base-",dir=os.environ["RUNNER_TEMP"]) as tmp:
            path = Path(tmp)/"protected_a3_guard.py"
            path.write_bytes(protected)
            sys.argv=[str(path),"--source-scope","--root",str(root),"--event",str(event_path)]
            if os.environ.get("GITHUB_OUTPUT"):
                sys.argv.extend(["--github-output",os.environ["GITHUB_OUTPUT"]])
            runpy.run_path(str(path),run_name="__main__")
except (AdmissionError,OSError,KeyError,UnicodeError) as exc:
    print("A3_PROTECTED_SOURCE_SCOPE_DENIED",getattr(exc,"reason",type(exc).__name__),file=sys.stderr)
    raise SystemExit(2)
PY_A3_PROTECTED_BASE
  elif [ "${GITHUB_ACTIONS:-false}" = true ] || [ "${1:-}" = --a3-scope-only ]; then
    echo 'A3_ACTUAL_EVENT_REQUIRED' >&2
    exit 1
  fi
  if [ "${1:-}" = --a3-scope-only ]; then
    exit 0
  fi
fi
# A3_R1_SOURCE_SCOPE_GUARD_END
python3 -I tests/validation/frontend_evolution/fe09_a3_f0_source_admission.py --self-test

python3 tests/validation/frontend_evolution/test_contracts.py
python3 scripts/ci_impact.py --self-test
python3 tests/validation/test_immutable_whitespace.py
python3 tests/validation/frontend_evolution/test_device_capture.py
python3 scripts/github_governance.py --self-test
python3 scripts/resource_baseline.py --self-test
python3 scripts/docs_consistency.py --self-test
python3 tests/test_ci_evidence_transport.py
python3 scripts/research_registry.py --self-test
python3 scripts/prepare_release.py --self-test
python3 scripts/release_manifest.py --self-test
python3 scripts/post_release_status.py --self-test
python3 scripts/qualification_fingerprint.py --self-test
python3 .github/research/continuous-optimization/hosted-validation/public_candidate_pair.py --source-root . --self-test
python3 .github/program/acoustic_terminal_registry.py --self-test
python3 .github/program/acoustic_terminal_registry.py --check
python3 tests/validation/i010_ns_vad_observation.py --self-test
python3 tests/validation/i010_apply_vad_pre_ns_candidate.py --self-test
python3 tests/validation/i010_vad_pre_ns_candidate.py --self-test
python3 .github/research/continuous-optimization/source_candidate_authority_v2.py --self-test
python3 .github/research/continuous-optimization/source_candidate_execution_v2_contract.py --self-test --check
python3 -m json.tool .github/research/evidence-index.json >/dev/null
python3 -m json.tool .github/research/qualification-policy.json >/dev/null
python3 scripts/docs_consistency.py
python3 tests/validation/frontend_evolution/test_libfvad_reference.py
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
python3 tests/validation/frontend_evolution/test_speech_spatial.py
python3 tests/validation/frontend_evolution/doa_observability_a0.py --self-test
python3 tests/validation/frontend_evolution/doa_gccphat_a1.py --self-test
python3 tests/validation/frontend_evolution/realman_source_metadata_d0.py --self-test
python3 tests/validation/frontend_evolution/realman_val_csv_d1.py self-test
python3 tests/validation/frontend_evolution/realman_scene_tree_d2_s0.py self-test
python3 tests/validation/frontend_evolution/realman_single_archive_d2_s1.py self-test
python3 tests/validation/frontend_evolution/realman_flac_quartets_d2_s2.py self-test
python3 tests/validation/frontend_evolution/realman_flac_decoder_toolchain_d2_t0.py self-test
python3 tests/validation/frontend_evolution/realman_pcm_reference_d2_s3r.py self-test
python3 tests/validation/frontend_evolution/realman_timebase_authority_d2_s4.py self-test
python3 tests/validation/frontend_evolution/realman_pypdf_toolchain_d2_s5_t0.py self-test
python3 tests/validation/frontend_evolution/realman_paper_clock_witness_d2_s5r.py self-test
python3 tests/validation/frontend_evolution/realman_gym_lag_diagnostic_d2_s6.py self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --self-test
python3 tests/validation/frontend_evolution/fe09_array_abi_contract_r1.py --check
# Bind the reviewed patch-maintenance bytes, then run both original preflights
# and their negatives on exact reconstructed historical source copies.
python3 tests/validation/frontend_evolution/fe09_runtime_maintenance_rebind.py --self-test --check
python3 tests/validation/frontend_evolution/fe09_b1a_ingress_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b1b0_src_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b1b1_single_bf_qualification.py --self-test
# Preserve six original scientific self-tests and verify the versioned
# historical/current source boundary plus its independent receipt negatives.
python3 tests/validation/frontend_evolution/fe09_runtime_source_boundary.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b0_capture_only_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s0_owner_spsc_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2b_b1s1_source_chunks_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t2c0_quiescent_fallback_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s0_resource_census_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s1_compact_handoff_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2a_atomic_spool_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b0_manifest_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1a_immutable_root_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1bf0_seq17_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba1_anchor_root_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py --self-test
python3 tests/validation/frontend_evolution/test_fe09_same_run_artifact_visibility.py
python3 tests/validation/frontend_evolution/test_speech_download_retry.py
python3 tests/validation/frontend_evolution/test_speech_source_stage_budget.py
python3 tests/validation/frontend_evolution/test_speech_source_recovery.py
python3 tests/validation/frontend_evolution/speech_pinned_snapshot.py --self-test
python3 .github/program/workflow_pin_only_scope.py --self-test
python3 .github/program/workflow_pin_only_replay_t1.py --self-test
python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --self-test
python3 .github/program/workflow_pin_pr_consumer.py --self-test
python3 .github/program/test_dechorate_event_source_t1m3.py --self-test
# Live GitHub bot Git-object probe only when this very qualifier is modified
# in a PR. Avoid an external network dependency for unrelated Verify runs.
if [ "${GITHUB_EVENT_NAME:-}" = pull_request ]; then
  test "${GITHUB_BASE_REF:-}" = main
  # A pull_request checkout may expose only refs/pull/<n>/merge, not origin/main.
  # Its first immutable parent is the checked-out protected PR base tree.
  set -- $(git -c "safe.directory=$PWD" rev-list --parents -n 1 HEAD)
  test "$#" -eq 3
  case "$2" in
    *[!0123456789abcdef]*|'') echo 'M1_PR_BASE_OID_MALFORMED' >&2; exit 1 ;;
  esac
  test "${#2}" -eq 40
  changed_t1m1=$(git -c "safe.directory=$PWD" diff --name-only "$2...HEAD" -- \
    .github/program/workflow_pin_only_actual_tree_t1m1.py)
  if [ "$changed_t1m1" = .github/program/workflow_pin_only_actual_tree_t1m1.py ]; then
    python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --probe-real --review 2026-10-20
  fi
fi
