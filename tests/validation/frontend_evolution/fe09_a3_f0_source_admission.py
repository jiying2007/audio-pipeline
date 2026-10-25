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


def is_leaf_path(path: str) -> bool:
    return path.startswith(DOC_ROOT + "/") or path.startswith(SOURCE_PREFIX)


# Peer loader entries are filled only from the independently reviewable F1
# source checkpoint.  They are deliberately outside the embedded Git reader;
# neither leaf's shell digest depends on a digest of itself.
REVIEWED_F1_SHELL_SHA256: frozenset[str] = frozenset({
    "4ef6ea7e344e28bb167d24ec3be8e09f3f9eed7adbbf78bc1ed37a84f2f2e3e2",
})
F1_METADATA_COMMAND = "python3 -I tests/validation/frontend_evolution/test_fe09_t3s3_f1_rss_qualification.py\n"
F1_SCOPE_STEP = (
    "      - name: F1 protected-base source scope and mandatory routing\n"
    "        id: f1_scope\n"
    "        run: sh .github/scripts/verify-docs-gate.sh --f1-scope-only\n"
)
F1_SUMMARY_BLOCK = (
    "          # F1_R1_SUMMARY_BEGIN\n"
    "          case \"$F1_REQUIRED\" in true|false) ;; *) echo 'F1R1_GUARD_OUTPUT_REQUIRED' >&2; exit 1 ;; esac\n"
    "          if [ \"$F1_REQUIRED\" = true ]; then\n"
    "            test \"$QUALITY_RESULT\" = success\n"
    "            test \"$F1_DISPOSITION\" = FE09_T3S3_F1_R1_COMPLETE_RSS_OBSERVATION_NO_DEVICE_PROMOTION\n"
    "          else\n"
    "            case \"$F1_DISPOSITION\" in\n"
    "              ''|SOURCE_METADATA_ONLY|F1_SOURCE_METADATA_ONLY_OUT_OF_SCOPE) ;;\n"
    "              *) echo 'F1R1_UNEXPECTED_SOURCE_DISPOSITION' >&2; exit 1 ;;\n"
    "            esac\n"
    "          fi\n"
    "          # F1_R1_SUMMARY_END\n"
)


def yaml_mapping(text: str, indent: int) -> dict[str, str]:
    """Project canonical plain mappings, never interpreting YAML aliases.

    The exact relevant blocks are retained as bytes. This intentionally accepts
    less spelling than a general YAML parser; an unknown relevant shape denies.
    """
    lines = text.splitlines(keepends=True)
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        leading = len(line) - len(line.lstrip(" "))
        if leading == indent:
            match = re.fullmatch(r" *([A-Za-z_][A-Za-z0-9_-]*):(?:[^\n]*)\n?", line)
            require(match is not None, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
            name = match.group(1)
            require(name not in [key for _, key in starts], "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
            starts.append((index, name))
        elif leading < indent:
            raise AdmissionError("A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    require(bool(starts), "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    result: dict[str, str] = {}
    for index, (start, name) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(lines)
        result[name] = "".join(lines[start:end]).rstrip() + "\n"
    return result


def yaml_children(block: str, indent: int) -> dict[str, str]:
    first, _, rest = block.partition("\n")
    require(first.strip().endswith(":"), "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    return yaml_mapping(rest, indent)


def yaml_value(block: str) -> str:
    first, _, rest = block.partition("\n")
    require(not rest.strip(), "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    return first.split(":", 1)[1].strip()


def normalized_quality_expression(value: str, caller: bool) -> str:
    prefix = "always() && needs.fast-gate.result == 'success' && (" if caller else "${{ "
    suffix = ")" if caller else " }}"
    require(value.startswith(prefix) and value.endswith(suffix), "A3_REQUIRED_DISPATCH_MISSING")
    terms = value[len(prefix):-len(suffix)].split(" || ")
    a3 = "needs.impact.outputs.a3_required == 'true'"
    quality = "needs.impact.outputs.run_quality == 'true'"
    f1 = "needs.impact.outputs.f1_required == 'true'"
    require(len(terms) == len(set(terms)) and {a3, quality} <= set(terms) <= {a3, quality, f1},
            "A3_REQUIRED_DISPATCH_MISSING")
    return prefix + quality + " || " + a3 + suffix


def normalize_f1_verify_job(text: str, name: str) -> str:
    """Only registered peer syntax can disappear from the A3 projection."""
    exact_lines = (
        "      f1_required: ${{ steps.f1_scope.outputs.f1_required }}\n",
        "      run_f1: ${{ needs.impact.outputs.f1_required == 'true' }}\n",
        "          F1_REQUIRED: ${{ needs.impact.outputs.f1_required }}\n",
        "          F1_DISPOSITION: ${{ needs.quality.outputs.f1_disposition }}\n",
    )
    for item in exact_lines:
        require(text.count(item) <= 1, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
        text = text.replace(item, "")
    for item in (F1_SCOPE_STEP, F1_SUMMARY_BLOCK):
        require(text.count(item) <= 1, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
        text = text.replace(item, "")
    if name == "quality":
        fields = yaml_children(text, 4)
        require("if" in fields, "A3_REQUIRED_DISPATCH_MISSING")
        original = fields["if"]
        normalized = "    if: " + normalized_quality_expression(yaml_value(original), True) + "\n"
        text = text.replace(original, normalized, 1)
    if name == "summary":
        matches = list(re.finditer(r"^          EXPECT_QUALITY: ([^\n]+)$", text, re.M))
        require(len(matches) == 1, "A3_REQUIRED_DISPATCH_MISSING")
        old = matches[0].group(0)
        text = text.replace(old, "          EXPECT_QUALITY: " +
                            normalized_quality_expression(matches[0].group(1), False), 1)
    require(not re.search(r"f1_required|f1_scope|F1_REQUIRED|F1_DISPOSITION|run_f1|f1_disposition|F1_R1_SUMMARY", text),
            "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    return text.rstrip() + "\n"


def validate_a3_job_permissions(job: str) -> None:
    fields = yaml_children(job, 4)
    require("permissions" in fields and "secrets" not in fields and "secrets." not in job,
            "A3_PERMISSION_CLOSURE_DRIFT")
    permissions = yaml_children(fields["permissions"], 6)
    require(set(permissions) == set(FIVE_READ) and
            all(yaml_value(value) == "read" for value in permissions.values()),
            "A3_PERMISSION_CLOSURE_DRIFT")


def validate_verify_dispatch(jobs: dict[str, str]) -> None:
    impact = yaml_children(jobs["impact"], 4)
    require("outputs" in impact, "A3_REQUIRED_DISPATCH_MISSING")
    outputs = yaml_children(impact["outputs"], 6)
    require("a3_required" in outputs and
            yaml_value(outputs["a3_required"]) == "${{ steps.a3_scope.outputs.a3_required }}",
            "A3_REQUIRED_DISPATCH_MISSING")
    guard = "        run: sh .github/scripts/verify-docs-gate.sh --a3-scope-only\n"
    require(jobs["impact"].count(guard) == 1 and jobs["impact"].count("        id: a3_scope\n") == 1 and
            jobs["impact"].count("        id: impact\n") == 1 and
            jobs["impact"].index(guard) < jobs["impact"].index("        id: impact\n"),
            "A3_OWNED_CI_FRAGMENT_DRIFT")
    for name in ("fast-docs", "fast-code"):
        require(jobs[name].count("          sh .github/scripts/verify-docs-gate.sh\n") == 1,
                "A3_OWNED_CI_FRAGMENT_DRIFT")
    caller = yaml_children(jobs["quality"], 4)
    require("with" in caller and "uses" in caller and "needs" in caller and
            yaml_value(caller["uses"]) == "./.github/workflows/quality.yml" and
            yaml_value(caller["needs"]) == "[impact, fast-gate]", "A3_REQUIRED_DISPATCH_MISSING")
    inputs = yaml_children(caller["with"], 6)
    require("run_a3" in inputs and yaml_value(inputs["run_a3"]) == "${{ needs.impact.outputs.a3_required == 'true' }}",
            "A3_REQUIRED_DISPATCH_MISSING")
    for exact in ("          A3_REQUIRED: ${{ needs.impact.outputs.a3_required }}\n",
                  "          A3_DISPOSITION: ${{ needs.quality.outputs.a3_disposition }}\n",
                  "          # A3_R1_SUMMARY_BEGIN\n", "          # A3_R1_SUMMARY_END\n",
                  "              test \"$A3_DISPOSITION\" = QUALIFIED_FINITE_A3_LIVE_ROLL_COMPLETE\n"):
        require(jobs["summary"].count(exact) == 1, "A3_OWNED_CI_FRAGMENT_DRIFT")


def workflow_projection(raw: bytes, workflow: str) -> bytes:
    require(len(raw) <= FILE_CAP and b"\t" not in raw and b"\r" not in raw,
            "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    text = raw.decode("utf-8")
    require(not re.search(r"^\s*(?:<<:|[A-Za-z_][A-Za-z0-9_-]*:\s*[&*])", text, re.M),
            "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    top = yaml_mapping(text, 0)
    require("jobs" in top and "on" in top, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    jobs = yaml_children(top.pop("jobs"), 2)
    if workflow == "quality":
        triggers = yaml_children(top.pop("on"), 2)
        require(set(triggers) == {"workflow_call"}, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
        call = yaml_children(triggers["workflow_call"], 4)
        inputs = yaml_children(call.pop("inputs"), 6)
        outputs = yaml_children(call.pop("outputs"), 6)
        require({"run_a3", "run_extended"} <= set(inputs) and "a3_disposition" in outputs,
                "A3_REQUIRED_DISPATCH_MISSING")
        top["workflow_call_global"] = call
        top["owned_inputs"] = {key: inputs[key] for key in ("run_a3", "run_extended")}
        top["owned_outputs"] = {"a3_disposition": outputs["a3_disposition"]}
        require("frontend-s3-t3s2b1ba3" in jobs, "A3_REQUIRED_DISPATCH_MISSING")
        validate_a3_job_permissions(jobs["frontend-s3-t3s2b1ba3"])
        own_fields = yaml_children(jobs["frontend-s3-t3s2b1ba3"], 4)
        require("if" in own_fields and yaml_value(own_fields["if"]) == "inputs.run_extended || inputs.run_a3",
                "A3_OWNED_CI_FRAGMENT_DRIFT")
        top["owned_jobs"] = {"frontend-s3-t3s2b1ba3": jobs["frontend-s3-t3s2b1ba3"]}
    else:
        require(workflow == "verify", "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
        selected = ("impact", "fast-docs", "fast-code", "fast-gate", "quality", "summary")
        require(set(selected) <= set(jobs), "A3_REQUIRED_DISPATCH_MISSING")
        validate_a3_job_permissions(jobs["quality"])
        validate_verify_dispatch(jobs)
        top["owned_jobs"] = {key: normalize_f1_verify_job(jobs[key], key) for key in selected}
    return json.dumps(top, sort_keys=True, separators=(",", ":")).encode()


def shell_projection(raw: bytes) -> bytes:
    text = raw.decode("utf-8")
    begin = "# A3_R1_SOURCE_SCOPE_GUARD_BEGIN\n"
    end = "# A3_R1_SOURCE_SCOPE_GUARD_END\n"
    require(text.count(begin) == text.count(end) == 1, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    require(text.index(begin) < text.index(end), "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    fbegin = "# F1_R1_SOURCE_SCOPE_GUARD_BEGIN\n"
    fend = "# F1_R1_SOURCE_SCOPE_GUARD_END\n"
    require(text.count(fbegin) == text.count(fend) <= 1, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    if fbegin in text:
        start, stop = text.index(fbegin), text.index(fend) + len(fend)
        require(start < stop <= text.index(begin), "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
        foreign = text[start:stop]
        require(hashlib.sha256(foreign.encode()).hexdigest() in REVIEWED_F1_SHELL_SHA256,
                "A3_PEER_SHELL_NOT_REVIEWED")
        text = text[:start] + text[stop:]
    require(text.count(F1_METADATA_COMMAND) <= 1, "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    text = text.replace(F1_METADATA_COMMAND, "")
    start, stop = text.index(begin), text.index(end) + len(end)
    # Only blank boundaries outside the exact owned code are insignificant.
    # Never normalize whitespace inside Python/shell bodies or heredoc data.
    return json.dumps({"prefix": text[:start].rstrip("\n"),
                       "A3_owned_block": text[start:stop],
                       "suffix": text[stop:].lstrip("\n")},
                      sort_keys=True, separators=(",", ":")).encode()


def shared_hooks_unchanged(before: dict[str, bytes], after: dict[str, bytes]) -> bool:
    require(set(before) == set(after) == set(HOOKS), "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
    for path in HOOKS:
        project = (lambda value: workflow_projection(value, "verify" if path.endswith("verify.yml") else "quality")) if path.endswith(".yml") else shell_projection
        if project(before[path]) != project(after[path]):
            return False
    return True


def source_ready(lock: dict[str, Any], baseline: dict[str, Any]) -> bool:
    """Readiness requests provider admission; it never grants execution."""
    if not isinstance(lock, dict) or not isinstance(baseline, dict):
        return False
    if lock.get("id") != IDENTITY or baseline.get("id") != IDENTITY:
        return False
    base = baseline.get("integration_base")
    if not isinstance(base, dict) or not base or any(v is None for v in base.values()):
        return False
    if base.get("status") != "QUALIFIED_PROTECTED_BASE_WITH_GUARD":
        return False
    if not SHA1.fullmatch(str(base.get("commit", ""))) or not SHA1.fullmatch(str(base.get("tree", ""))):
        return False
    files = lock.get("pending_implementation_files", [])
    hooks = lock.get("pending_hookup_files", [])
    if not isinstance(files, list) or not isinstance(hooks, list) or len(files) != 6 or len(hooks) != 3:
        return False
    expected = {"tests/validation/frontend_evolution/" + name for name in SOURCE_FILES} | set(HOOKS)
    if not all(isinstance(row, dict) and isinstance(row.get("path"), str) for row in files + hooks):
        return False
    if {row["path"] for row in files + hooks} != expected:
        return False
    for row in files + hooks:
        if not isinstance(row, dict) or not strict_int(row.get("bytes"), 1):
            return False
        if not SHA256.fullmatch(str(row.get("sha256", ""))) or not SHA1.fullmatch(str(row.get("git_blob_sha1", ""))):
            return False
    # Document flags are never used as independent scientific approval.
    return lock.get("execution_admitted_by_this_file") is False


def classify_scope(source: dict[str, str], base_guard: bytes | None,
                   candidate_guard: bytes | None, changed: tuple[str, ...],
                   shared_unchanged: bool, ready: bool,
                   original_paths: tuple[str, ...] = ()) -> str:
    require(source.get("event") in ("pull_request", "push"), "EVENT_NOT_REGISTERED")
    if base_guard is None:
        return BOOTSTRAP
    require(candidate_guard == base_guard, "PROTECTED_POLICY_SOURCE_DRIFT")
    require(shared_unchanged, "A3_OWNED_CI_FRAGMENT_DRIFT")
    if not any(is_leaf_path(path) or path in original_paths for path in changed):
        return UNRELATED
    if source["event"] == "pull_request":
        require(source.get("head_ref") == BRANCH, "A3_SCOPE_OUTSIDE_REGISTERED_BRANCH")
    require(ready, "A3_SOURCE_NOT_READY")
    return REQUIRED


def scope_receipt(source: dict[str, str], disposition: str, changed: tuple[str, ...]) -> dict[str, Any]:
    return {"schema_version": 1, "experiment_id": IDENTITY, "phase": "LOCAL_SOURCE_SCOPE_ONLY",
            "disposition": disposition, "a3_required": disposition == REQUIRED,
            "actual_local_source": source, "changed_paths": list(changed),
            "api_requests": 0, "HTTP_helper_starts": 0, "scientific_C_target_starts": 0,
            "DSP_frames": 0, "scientific_execution_admitted": False,
            "provider_lineage_and_external_freeze_still_required": True}


def validate_scope_receipt(receipt: dict[str, Any], protected_original_paths: tuple[str, ...] = ()) -> None:
    require(receipt.get("phase") == "LOCAL_SOURCE_SCOPE_ONLY" and receipt.get("experiment_id") == IDENTITY,
            "SOURCE_SCOPE_DENIED")
    require(type(receipt.get("api_requests")) is int and receipt["api_requests"] == 0,
            "FAST_SCOPE_API_NOT_ALLOWED")
    require(type(receipt.get("HTTP_helper_starts")) is int and receipt["HTTP_helper_starts"] == 0,
            "SOURCE_ONLY_PROCESS_NOT_ALLOWED")
    require(receipt.get("scientific_execution_admitted") is False and
            type(receipt.get("scientific_C_target_starts")) is int and receipt["scientific_C_target_starts"] == 0 and
            type(receipt.get("DSP_frames")) is int and receipt["DSP_frames"] == 0,
            "METADATA_RESULT_FALSELY_PROMOTED")
    require(receipt.get("disposition") in (BOOTSTRAP, UNRELATED, REQUIRED) and
            type(receipt.get("a3_required")) is bool and
            receipt["a3_required"] == (receipt["disposition"] == REQUIRED), "A3_SCOPE_NOT_ENFORCED")
    changed = receipt.get("changed_paths")
    require(isinstance(changed, list) and all(isinstance(path, str) for path in changed),
            "SOURCE_SCOPE_DIFF_INCOMPLETE")
    if receipt["disposition"] == UNRELATED:
        require(not any(is_leaf_path(path) or path in protected_original_paths for path in changed),
                "UNRELATED_SCOPE_PROOF_FAILED")


def local_scope(root: Path, event_path: Path, env: dict[str, str],
                git_reader: GitObjects | None = None) -> dict[str, Any]:
    git = git_reader or GitObjects(root)
    head = git.head()
    _, parents = git.commit(head)
    event = strict_json(read_regular(event_path, FILE_CAP))
    source = local_source(event, env, head, parents)
    base_entry = git.entry(source["B"], GUARD)
    require(base_entry is None or base_entry.mode == "100644", "PROTECTED_POLICY_MODE_DRIFT")
    base_guard = git.blob(source["B"], GUARD, required=False)
    changed = git.changed_paths(source["B"], head)
    if base_guard is None:
        result = scope_receipt(source, BOOTSTRAP, changed)
        validate_scope_receipt(result)
        return result
    # A script invoked from the candidate tree may not impersonate the B copy.
    require(read_regular(Path(__file__), FILE_CAP) == base_guard, "PROTECTED_POLICY_SOURCE_DRIFT")
    candidate_guard = git.blob(head, GUARD, required=False)
    before = {path: git.blob(source["B"], path) or b"" for path in HOOKS}
    after = {path: git.blob(head, path) or b"" for path in HOOKS}
    shared_unchanged = shared_hooks_unchanged(before, after)
    protected_lock = strict_json(git.blob(source["B"], DOC_ROOT + "/source-lock.json") or b"")
    original_rows = protected_lock.get("known_immutable_files", [])
    require(isinstance(original_rows, list) and len(original_rows) == 88,
            "IMMUTABLE_SCIENTIFIC_SOURCE_CLOSURE_INVALID")
    original_paths = tuple(safe_path(row.get("path")) for row in original_rows if isinstance(row, dict))
    require(len(set(original_paths)) == 88, "IMMUTABLE_SCIENTIFIC_SOURCE_CLOSURE_INVALID")
    lock = strict_json(git.blob(head, DOC_ROOT + "/source-lock.json") or b"")
    baseline = strict_json(git.blob(head, DOC_ROOT + "/EXECUTION_BASELINE.json") or b"")
    decision = classify_scope(source, base_guard, candidate_guard, changed,
                              shared_unchanged, source_ready(lock, baseline), original_paths)
    result = scope_receipt(source, decision, changed)
    validate_scope_receipt(result, original_paths)
    return result


def write_github_outputs(path: Path | None, receipt: dict[str, Any]) -> None:
    if path is None:
        return
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= STDERR_CAP,
                "GITHUB_OUTPUT_FILE_INVALID")
        payload = ("a3_required=" + str(receipt["a3_required"]).lower() + "\n" +
                   "a3_disposition=" + receipt["disposition"] + "\n" +
                   "disposition=" + receipt["disposition"] + "\n").encode()
        require(os.write(fd, payload) == len(payload), "GITHUB_OUTPUT_WRITE_INCOMPLETE")
    finally:
        os.close(fd)


# Provider/experiment admission is separate from the local source dispatcher.
# These functions accept original decoded provider objects and actual local Git
# observations. Offline tests use explicitly labelled in-memory metadata seeds.
from datetime import datetime, timezone

ISSUE_NUMBER = 847
ISSUE_ID = 6018431984
ISSUE_NODE = "I_kwDOUE9X8c8AAAABZrn78A"
ISSUE_CREATED = "2026-10-24T22:45:25Z"
AUTHOR_ID = 33591504
FREEZE_KIND = "FE09_A3_F0_R1_EXECUTION_FREEZE"
API_PREFIX = "https://api.github.com/repos/" + REPOSITORY + "/"
ISSUE_URL = API_PREFIX + "issues/847"
FIVE_READ = {key: "read" for key in ("contents", "packages", "actions", "issues", "pull-requests")}
API_BODY_CAPS = (131072, 2097152, 16384, 524288, 524288, 65536, 1048576, 131072,
                 65536, 131072, 16384, 524288, 524288, 65536, 1048576, 131072, 65536)
API_LABELS = ("pre-run", "pre-jobs", "pre-main-ref", "pre-source-first", "pre-source-second",
              "pre-issue-before", "pre-comments", "pre-selected-comment", "pre-issue-after",
              "post-run", "post-main-ref", "post-source-first", "post-source-second",
              "post-issue-before", "post-comments", "post-selected-comment", "post-issue-after")
CONTROL_BYTES = 8388608
API_ACTIVE_NS = 60_000_000_000
FREEZE_CONSTANTS = {
    "schema_version": 1, "kind": FREEZE_KIND, "experiment_id": IDENTITY,
    "repository_id": REPOSITORY_ID, "repository_full_name": REPOSITORY,
    "issue_number": ISSUE_NUMBER, "issue_id": ISSUE_ID, "issue_node_id": ISSUE_NODE,
    "head_ref": BRANCH, "scientific_baseline_sha": SCIENTIFIC_BASE,
    "decision": "APPROVED_FOR_REGISTERED_FINITE_A3_EXECUTION",
    "allowed_events": ["pull_request", "push"], "allowed_run_attempts": [1],
}
FREEZE_GIT_FIELDS = ("integration_base_sha", "integration_base_tree", "candidate_sha", "candidate_tree")
FREEZE_DOC_FIELDS = {
    "source_lock_sha256": "source-lock.json", "test_contract_sha256": "test-contract.json",
    "execution_baseline_sha256": "EXECUTION_BASELINE.json",
    "admission_controls_sha256": "ADMISSION_NEGATIVE_CONTROLS.json", "readme_sha256": "README.md",
}
FREEZE_KEYS = set(FREEZE_CONSTANTS) | set(FREEZE_GIT_FIELDS) | set(FREEZE_DOC_FIELDS) | {"independent_review_report_sha256"}


def utc_ns(value: Any, reason: str = "STRICT_METADATA_SCHEMA_DRIFT") -> int:
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None,
            reason)
    try:
        delta = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    except ValueError as exc:
        raise AdmissionError(reason) from exc
    return (delta.days * 86400 + delta.seconds) * 1_000_000_000


def positive_id(value: Any, reason: str) -> int:
    require(type(value) is int and 0 < value < 2**63, reason)
    return value


def provider_repository(value: Any, reason: str = "REPOSITORY_IDENTITY_DRIFT") -> None:
    require(isinstance(value, dict) and type(value.get("id")) is int and
            value["id"] == REPOSITORY_ID and value.get("full_name") == REPOSITORY, reason)


def provider_owner(value: Any, reason: str) -> None:
    require(isinstance(value, dict) and type(value.get("id")) is int and value["id"] == AUTHOR_ID and
            value.get("login") == "jiying2007" and value.get("type") == "User", reason)


def no_next_link(headers: Any, reason: str) -> None:
    require(isinstance(headers, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()), reason)
    links = [value for key, value in headers.items() if key.lower() == "link"]
    require(len(links) <= 1, reason)
    if links:
        # A malformed Link value cannot be used as a completeness witness.
        for item in links[0].split(","):
            require(re.fullmatch(r'\s*<https://api\.github\.com/[^<>\r\n]+>;\s*rel="(?:prev|first|last|next)"\s*', item) is not None, reason)
            require('rel="next"' not in item, reason)


def validate_run(run: Any, actual: dict[str, Any]) -> None:
    require(isinstance(run, dict), "STRICT_METADATA_SCHEMA_DRIFT")
    provider_repository(run.get("repository"))
    provider_repository(run.get("head_repository"))
    require(positive_id(run.get("id"), "RUN_HEAD_BINDING_DRIFT") == actual["run_id"], "RUN_HEAD_BINDING_DRIFT")
    require(type(run.get("run_attempt")) is int and run["run_attempt"] == actual["attempt"] == 1,
            "RUN_ATTEMPT_NOT_REGISTERED")
    require(run.get("event") == actual["event"] and actual["event"] in ("pull_request", "push"),
            "EVENT_NOT_REGISTERED")
    require(run.get("head_sha") == actual["event_head"], "RUN_HEAD_BINDING_DRIFT")
    require(run.get("head_branch") == (BRANCH if actual["event"] == "pull_request" else "main"),
            "RUN_HEAD_BINDING_DRIFT")
    require(run.get("path") == ".github/workflows/verify.yml" and run.get("name") == "Verify",
            "RUN_WORKFLOW_BINDING_DRIFT")
    require(run.get("status") in ("queued", "in_progress", "completed") and
            run.get("conclusion") in (None, "success"), "ACTUAL_RUN_FAILED_OR_CANCELLED")
    utc_ns(run.get("created_at"))


def validate_jobs(jobs: Any, headers: dict[str, str], run_id: int) -> dict[str, Any]:
    reason = "ACTUAL_JOBS_PAGE_INCOMPLETE"
    require(isinstance(jobs, dict) and type(jobs.get("total_count")) is int and
            isinstance(jobs.get("jobs"), list), reason)
    values = jobs["jobs"]
    require(0 < jobs["total_count"] == len(values) <= 100, reason)
    no_next_link(headers, reason)
    ids: set[int] = set()
    selected: list[dict[str, Any]] = []
    for item in values:
        require(isinstance(item, dict), reason)
        job_id = positive_id(item.get("id"), reason)
        require(job_id not in ids and type(item.get("run_id")) is int and item["run_id"] == run_id, reason)
        ids.add(job_id)
        if item.get("name") in ("frontend-s3-t3s2b1ba3", "quality / frontend-s3-t3s2b1ba3"):
            selected.append(item)
    require(len(selected) == 1, "ACTUAL_A3_JOB_NOT_UNIQUE")
    job = selected[0]
    require(isinstance(job.get("steps"), list) and bool(job["steps"]), "ORIGINAL_JOB_DEADLINE_UNPROVEN")
    started: list[int] = []
    numbers: set[int] = set()
    for step in job["steps"]:
        require(isinstance(step, dict), "ORIGINAL_JOB_DEADLINE_UNPROVEN")
        number = positive_id(step.get("number"), "ORIGINAL_JOB_DEADLINE_UNPROVEN")
        require(number not in numbers, "ORIGINAL_JOB_DEADLINE_UNPROVEN")
        numbers.add(number)
        if step.get("started_at") is not None:
            started.append(utc_ns(step["started_at"], "ORIGINAL_JOB_DEADLINE_UNPROVEN"))
    require(bool(started), "ORIGINAL_JOB_DEADLINE_UNPROVEN")
    return {"job_id": job["id"], "job_name": job["name"], "earliest_step_epoch_ns": min(started),
            "original_job_deadline_epoch_ns": min(started) + 900_000_000_000}


def bind_collector_budget(job: dict[str, Any], stage_monotonic_ns: int, stage_epoch_ns: int) -> DurationBudget:
    require(strict_int(stage_monotonic_ns) and strict_int(stage_epoch_ns), "TIME_BUDGET_INVALID")
    admitted = min(600_000_000_000, job["original_job_deadline_epoch_ns"] - stage_epoch_ns - 300_000_000_000)
    require(admitted > 0, "A3_ENCLOSING_BUDGET_EXHAUSTED")
    return DurationBudget(stage_monotonic_ns, admitted)


def validate_associations(values: Any, headers: dict[str, str], *, role: str,
                          event_sha: str, event_pr_number: int | None) -> dict[str, Any]:
    reason = "ASSOCIATED_PR_LIST_INCOMPLETE"
    require(isinstance(values, list) and len(values) < 100, reason)
    no_next_link(headers, reason)
    ids: set[int] = set()
    candidates: list[dict[str, Any]] = []
    for item in values:
        require(isinstance(item, dict), reason)
        key = positive_id(item.get("id"), reason)
        number = positive_id(item.get("number"), reason)
        require(key not in ids, "ASSOCIATED_PR_NOT_UNIQUE")
        ids.add(key)
        head, base = item.get("head", {}), item.get("base", {})
        require(isinstance(head, dict) and isinstance(base, dict), reason)
        provider_repository(base.get("repo"), reason)
        require(isinstance(head.get("repo"), dict) and type(head["repo"].get("id")) is int,
                reason)
        registered = (head["repo"].get("id") == REPOSITORY_ID and
                      head["repo"].get("full_name") == REPOSITORY and
                      head.get("ref") == BRANCH and base.get("ref") == "main")
        if not registered:
            continue
        if role == "pull_request":
            # Closed prior PRs for exactly the same C also make its association
            # nonunique; reopening a fresh PR is not a fresh science allowance.
            if head.get("sha") == event_sha:
                candidates.append(item)
        else:
            require(role == "push", "EVENT_NOT_REGISTERED")
            if item.get("merge_commit_sha") == event_sha and item.get("state") == "closed" and item.get("merged_at") is not None:
                candidates.append(item)
    require(len(candidates) == 1, "ASSOCIATED_PR_NOT_UNIQUE")
    if role == "pull_request":
        require(candidates[0]["number"] == event_pr_number, "ASSOCIATED_PR_NOT_UNIQUE")
    return candidates[0]


def graph_node(graph: dict[str, Any], commit: str, reason: str) -> dict[str, Any]:
    value = graph.get(commit)
    require(isinstance(value, dict) and isinstance(value.get("tree"), str) and
            SHA1.fullmatch(value["tree"]) is not None and isinstance(value.get("parents"), list) and
            all(isinstance(parent, str) and SHA1.fullmatch(parent) is not None for parent in value["parents"]), reason)
    return value


def graph_has_ancestor(graph: dict[str, Any], ancestor: str, descendant: str) -> bool:
    pending, seen = [descendant], set()
    while pending:
        current = pending.pop()
        if current == ancestor:
            return True
        if current in seen:
            continue
        seen.add(current)
        value = graph.get(current)
        if not isinstance(value, dict) or not isinstance(value.get("parents"), list):
            # A bounded actual-object witness needs one complete path to B;
            # an unexpanded other merge parent does not negate that path.
            continue
        pending.extend(value["parents"])
    return False


SCIENCE_FIELDS = ("data_role", "hypothesis", "success_decision", "failure_decision",
                  "dependencies", "source_config", "profiles", "process_model", "new_root",
                  "transaction", "io_faults", "execution_matrix", "controls", "acceptance")
ORIGINAL_COMPARISON = "5187c5e59526d4047b3965b44c770ab21edbde9f"
SOURCE_ROW_FIELDS = ("path", "bytes", "sha256", "git_blob_sha1")


def source_row(path: str, raw: bytes, mode: str = "100644") -> dict[str, Any]:
    return {"path": safe_path(path), "mode": mode, "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}


def validate_frozen_rows(rows: Any, actual: dict[str, dict[str, Any]], paths: set[str], reason: str) -> None:
    require(isinstance(rows, list) and len(rows) == len(paths) and
            all(isinstance(row, dict) and isinstance(row.get("path"), str) for row in rows), reason)
    require({row["path"] for row in rows} == paths and set(actual) == paths, reason)
    for row in rows:
        path = safe_path(row["path"])
        observed = actual[path]
        require(isinstance(observed, dict) and observed.get("mode") == "100644" and
                strict_int(row.get("bytes"), 1) and
                isinstance(row.get("sha256"), str) and SHA256.fullmatch(row["sha256"]) is not None and
                isinstance(row.get("git_blob_sha1"), str) and SHA1.fullmatch(row["git_blob_sha1"]) is not None and
                all(type(row.get(key)) is type(observed.get(key)) and row.get(key) == observed.get(key)
                    for key in SOURCE_ROW_FIELDS), reason, path)


def validate_source_documents(documents: dict[str, bytes], protected_documents: dict[str, bytes],
                              candidate: str, original: dict[str, dict[str, Any]],
                              implementation: dict[str, dict[str, Any]],
                              protected_guard: dict[str, Any], actual_guard: bytes,
                              locked_programs: dict[str, bytes]) -> dict[str, Any]:
    """Pure validation of actual original blobs and completed C documents.

    The runtime supplies Git observations from actual B/C and both immutable
    original commits. Offline tests supply explicitly labelled model rows.
    Neither a candidate CLI pin nor these documents grant execution alone.
    """
    names = {"README.md", "source-lock.json", "test-contract.json", "EXECUTION_BASELINE.json",
             "ADMISSION_NEGATIVE_CONTROLS.json"}
    require(set(documents) == names and set(protected_documents) == names and
            all(isinstance(value, bytes) for value in documents.values()),
            "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    lock = strict_json(documents["source-lock.json"])
    baseline = strict_json(documents["EXECUTION_BASELINE.json"])
    contract = strict_json(documents["test-contract.json"])
    base_lock = strict_json(protected_documents["source-lock.json"])
    base_contract = strict_json(protected_documents["test-contract.json"])
    base_baseline = strict_json(protected_documents["EXECUTION_BASELINE.json"])
    require(all(isinstance(value, dict) for value in (lock, baseline, contract, base_lock, base_contract, base_baseline)),
            "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    require(set(lock) == set(base_lock), "SOURCE_FREEZE_SELF_REFERENCE")
    require(set(baseline) == set(base_baseline) and
            all(baseline[key] == base_baseline[key] for key in base_baseline if key not in ("status", "integration_base")),
            "SOURCE_FREEZE_SELF_REFERENCE")
    require(lock.get("id") == baseline.get("id") == contract.get("id") == IDENTITY and
            lock.get("original_baseline") == SCIENTIFIC_BASE and baseline.get("source_baseline") == SCIENTIFIC_BASE and
            lock.get("original_comparison_commit") == ORIGINAL_COMPARISON,
            "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT")
    require(lock.get("source_self_reference_policy") == base_lock.get("source_self_reference_policy") and
            lock.get("execution_admitted_by_this_file") is False and
            baseline.get("candidate_source_identity") == {
                "location": "external issue847 freeze and runtime provider/Git observations only",
                "C_or_tree_embedded_in_this_file": False,
                "future_comment_ID_or_body_hash_embedded": False,
                "document_alone_authorizes_execution": False}, "SOURCE_FREEZE_SELF_REFERENCE")
    lock_digest = hashlib.sha256(documents["source-lock.json"]).hexdigest().encode()
    require(candidate.encode() not in documents["source-lock.json"] and
            candidate.encode() not in documents["EXECUTION_BASELINE.json"] and
            lock_digest not in documents["source-lock.json"] and
            all(lock_digest not in value for value in locked_programs.values()), "SOURCE_FREEZE_SELF_REFERENCE")
    require(all(field in contract and field in base_contract and contract[field] == base_contract[field]
                for field in SCIENCE_FIELDS), "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT")
    require(documents["ADMISSION_NEGATIVE_CONTROLS.json"] == protected_documents["ADMISSION_NEGATIVE_CONTROLS.json"],
            "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT")
    trusted_rows = base_lock.get("known_immutable_files")
    require(isinstance(trusted_rows, list) and len(trusted_rows) == 88 and
            all(isinstance(row, dict) and isinstance(row.get("path"), str) for row in trusted_rows),
            "IMMUTABLE_SCIENTIFIC_SOURCE_CLOSURE_INVALID")
    original_paths = {safe_path(row["path"]) for row in trusted_rows}
    require(len(original_paths) == 88 and lock.get("known_immutable_file_count") == 88 and
            type(lock["known_immutable_file_count"]) is int and lock.get("known_immutable_files") == trusted_rows,
            "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT")
    validate_frozen_rows(trusted_rows, original, original_paths, "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT")
    expected = {"tests/validation/frontend_evolution/" + name for name in SOURCE_FILES} | set(HOOKS)
    require(source_ready(lock, baseline), "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    rows = lock["pending_implementation_files"] + lock["pending_hookup_files"]
    validate_frozen_rows(rows, implementation, expected, "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    require(set(locked_programs) == {"tests/validation/frontend_evolution/" + name for name in SOURCE_FILES},
            "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    base = baseline["integration_base"]
    require(set(base) == {"status", "commit", "tree", "verify_run_id", "verify_attempt", "required_summary_job_id",
                         "release_run_id", "release_attempt", "release_job_id", "convergence_job_id",
                         "protected_guard_path", "protected_guard_mode", "protected_guard_blob", "protected_guard_bytes",
                         "protected_guard_sha256", "root_independent_main_closure_report_sha256",
                         "all_fields_complete_before_final_C_required"}, "INTEGRATION_BASE_NOT_QUALIFIED")
    require(base.get("protected_guard_path") == GUARD and base.get("protected_guard_mode") == "100644" and
            protected_guard.get("mode") == "100644", "PROTECTED_POLICY_MODE_DRIFT")
    for key in ("verify_run_id", "required_summary_job_id", "release_run_id", "release_job_id", "convergence_job_id"):
        positive_id(base.get(key), "INTEGRATION_BASE_NOT_QUALIFIED")
    require(type(base.get("verify_attempt")) is int and base["verify_attempt"] == 1 and
            type(base.get("release_attempt")) is int and base["release_attempt"] == 1 and
            base.get("all_fields_complete_before_final_C_required") is True and
            isinstance(base.get("root_independent_main_closure_report_sha256"), str) and
            SHA256.fullmatch(base["root_independent_main_closure_report_sha256"]) is not None,
            "INTEGRATION_BASE_NOT_QUALIFIED")
    require(base["protected_guard_blob"] == protected_guard.get("git_blob_sha1") and
            type(base["protected_guard_bytes"]) is int and base["protected_guard_bytes"] == protected_guard.get("bytes") and
            base["protected_guard_sha256"] == protected_guard.get("sha256") and
            actual_guard == locked_programs[GUARD] and source_row(GUARD, actual_guard) == protected_guard,
            "PROTECTED_POLICY_SOURCE_DRIFT")
    require(lock.get("original_direct_translation_units") == base_lock.get("original_direct_translation_units") and
            lock.get("original_included_translation_unit") == base_lock.get("original_included_translation_unit") and
            lock.get("generated_header_requirement") == base_lock.get("generated_header_requirement"),
            "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    return {"qualified_base": base,
            "document_hashes": {field: hashlib.sha256(documents[name]).hexdigest()
                                for field, name in FREEZE_DOC_FIELDS.items()},
            "original88": [original[path] for path in sorted(original)],
            "implementation_and_hooks9": [implementation[path] for path in sorted(implementation)],
            "scientific_execution_admitted": False, "source_closed_before_freeze": True}


def derive_actual_source(run: dict[str, Any], actual: dict[str, Any], pr: Any,
                         association: dict[str, Any], main_ref: Any,
                         graph: dict[str, Any], qualified_base: dict[str, Any],
                         previous: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_run(run, actual)
    require(isinstance(pr, dict), "PR_SOURCE_IDENTITY_DRIFT")
    require(positive_id(pr.get("id"), "PR_SOURCE_IDENTITY_DRIFT") == association["id"] and
            positive_id(pr.get("number"), "PR_SOURCE_IDENTITY_DRIFT") == association["number"],
            "PR_SOURCE_IDENTITY_DRIFT")
    provider_owner(pr.get("user"), "PR_SOURCE_IDENTITY_DRIFT")
    require(pr.get("draft") is False, "PR_SOURCE_IDENTITY_DRIFT")
    head, base = pr.get("head", {}), pr.get("base", {})
    require(isinstance(head, dict) and isinstance(base, dict), "PR_SOURCE_IDENTITY_DRIFT")
    for value in (head, base):
        provider_repository(value.get("repo"), "PR_SOURCE_IDENTITY_DRIFT")
    require(head.get("ref") == BRANCH and base.get("ref") == "main", "PR_SOURCE_IDENTITY_DRIFT")
    c, b = oid(head.get("sha")), oid(base.get("sha"))
    if previous is not None:
        require((b, c, pr["id"], pr["number"]) ==
                (previous["B"], previous["C"], previous["PR_id"], previous["PR_number"]),
                "SOURCE_IDENTITY_CHANGED_AFTER_PRE")
    require(isinstance(qualified_base, dict) and qualified_base.get("commit") == b and
            qualified_base.get("status") == "QUALIFIED_PROTECTED_BASE_WITH_GUARD",
            "INTEGRATION_BASE_NOT_QUALIFIED")
    base_node = graph_node(graph, b, "C_BASE_ANCESTRY_DRIFT")
    candidate_node = graph_node(graph, c, "C_BASE_ANCESTRY_DRIFT")
    require(base_node["tree"] == qualified_base.get("tree"), "INTEGRATION_BASE_NOT_QUALIFIED")
    require(graph_has_ancestor(graph, b, c), "C_BASE_ANCESTRY_DRIFT")
    require(isinstance(main_ref, dict) and main_ref.get("ref") == "refs/heads/main" and
            isinstance(main_ref.get("object"), dict) and main_ref["object"].get("type") == "commit",
            "PROTECTED_MAIN_REF_DRIFT")
    checkout = actual["checkout"]
    node = graph_node(graph, checkout, "EXECUTION_TREE_NOT_REVIEWED_C")
    if actual["event"] == "pull_request":
        require(pr.get("state") == "open" and pr.get("merged") is False and
                actual["event_head"] == c and actual.get("event_pr_number") == pr["number"],
                "PR_SOURCE_IDENTITY_DRIFT")
        require(main_ref["object"].get("sha") == b, "PROTECTED_MAIN_REF_DRIFT")
        require(pr.get("merge_commit_sha") == checkout and node["parents"] == [b, c],
                "PR_TEST_MERGE_RELATION_DRIFT")
    else:
        require(actual["event"] == "push" and actual["event_head"] == checkout,
                "MAIN_C_DERIVATION_NOT_PROVIDER_BOUND")
        require(pr.get("state") == "closed" and pr.get("merged") is True and
                pr.get("merge_commit_sha") == checkout, "MAIN_C_DERIVATION_NOT_PROVIDER_BOUND")
        require(main_ref["object"].get("sha") == checkout, "PROTECTED_MAIN_REF_DRIFT")
        require(node["parents"] == [b], "MAIN_SQUASH_PARENT_DRIFT")
        require(utc_ns(pr.get("merged_at")) <= utc_ns(run["created_at"]), "MERGE_RUN_ORDER_INVALID")
    require(node["tree"] == candidate_node["tree"], "EXECUTION_TREE_NOT_REVIEWED_C")
    return {"event": actual["event"], "run_id": actual["run_id"], "attempt": 1,
            "run_created_at": run["created_at"], "B": b, "B_tree": base_node["tree"],
            "C": c, "C_tree": candidate_node["tree"], "checkout": checkout,
            "PR_id": pr["id"], "PR_number": pr["number"]}


def validate_registration_issue(issue: Any) -> int:
    reason = "REGISTRATION_ISSUE_IDENTITY_DRIFT"
    require(isinstance(issue, dict) and type(issue.get("number")) is int and issue["number"] == ISSUE_NUMBER and
            type(issue.get("id")) is int and issue["id"] == ISSUE_ID and issue.get("node_id") == ISSUE_NODE and
            issue.get("created_at") == ISSUE_CREATED and issue.get("url") == ISSUE_URL and
            issue.get("repository_url") == API_PREFIX.rstrip("/"), reason)
    provider_owner(issue.get("user"), reason)
    require(issue.get("state") == "open" and "pull_request" not in issue, "REGISTRATION_ISSUE_NOT_OPEN")
    require(type(issue.get("comments")) is int and 0 <= issue["comments"] <= 100,
            "STRICT_METADATA_SCHEMA_DRIFT")
    return issue["comments"]


def freeze_body(comment: dict[str, Any]) -> dict[str, Any] | None:
    body = comment.get("body")
    require(isinstance(body, str), "FREEZE_COMMENT_LIST_INVALID")
    if FREEZE_KIND not in body or not body.lstrip().startswith(("{", "```")):
        return None
    try:
        value = strict_json(body.encode("utf-8"), 131072)
    except (AdmissionError, UnicodeError) as exc:
        raise AdmissionError("FREEZE_JSON_NOT_STRICT") from exc
    require(isinstance(value, dict), "FREEZE_JSON_NOT_STRICT")
    if value.get("kind") == FREEZE_KIND and value.get("experiment_id") == IDENTITY:
        require(isinstance(value.get("candidate_sha"), str) and SHA1.fullmatch(value["candidate_sha"]) is not None,
                "FREEZE_SCHEMA_DRIFT")
    return value if value.get("kind") == FREEZE_KIND else None


def validate_freeze_payload(value: dict[str, Any], source: dict[str, Any],
                            documents: dict[str, str]) -> None:
    require(set(value) == FREEZE_KEYS, "FREEZE_SCHEMA_DRIFT")
    for key, expected in FREEZE_CONSTANTS.items():
        actual = value[key]
        require(type(actual) is type(expected) and actual == expected, "FREEZE_SCHEMA_DRIFT")
        if isinstance(expected, list):
            require(len(actual) == len(expected) and all(type(a) is type(b) for a, b in zip(actual, expected)),
                    "FREEZE_SCHEMA_DRIFT")
    for key in FREEZE_GIT_FIELDS:
        require(isinstance(value[key], str) and SHA1.fullmatch(value[key]) is not None,
                "FREEZE_SCHEMA_DRIFT")
    for key in (*FREEZE_DOC_FIELDS, "independent_review_report_sha256"):
        require(isinstance(value[key], str) and SHA256.fullmatch(value[key]) is not None,
                "FREEZE_SCHEMA_DRIFT")
    expected_source = {"integration_base_sha": source["B"], "integration_base_tree": source["B_tree"],
                       "candidate_sha": source["C"], "candidate_tree": source["C_tree"]}
    require(all(value[k] == v for k, v in expected_source.items()), "FREEZE_SOURCE_IDENTITY_DRIFT")
    require(set(documents) == set(FREEZE_DOC_FIELDS), "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    require(all(value[key] == digest for key, digest in documents.items()), "FREEZE_SOURCE_IDENTITY_DRIFT")


def select_freeze(comments: Any, headers: dict[str, str], issue_before: Any,
                  source: dict[str, Any], documents: dict[str, str]) -> dict[str, Any]:
    count = validate_registration_issue(issue_before)
    require(isinstance(comments, list) and len(comments) == count <= 100,
            "FREEZE_COMMENT_LIST_INCOMPLETE")
    no_next_link(headers, "FREEZE_COMMENT_LIST_INCOMPLETE")
    seen: set[int] = set()
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for comment in comments:
        require(isinstance(comment, dict), "FREEZE_COMMENT_LIST_INVALID")
        number = positive_id(comment.get("id"), "FREEZE_COMMENT_LIST_INVALID")
        require(number not in seen, "FREEZE_COMMENT_LIST_INVALID")
        seen.add(number)
        require(comment.get("issue_url") == ISSUE_URL, "FREEZE_COMMENT_ISSUE_DRIFT")
        value = freeze_body(comment)
        if value is not None and value.get("experiment_id") == IDENTITY and value.get("candidate_sha") == source["C"]:
            matches.append((comment, value))
    require(len(matches) == 1, "FREEZE_FOR_ACTUAL_C_NOT_UNIQUE")
    comment, value = matches[0]
    validate_freeze_payload(value, source, documents)
    provider_owner(comment.get("user"), "FREEZE_AUTHOR_IDENTITY_DRIFT")
    require(comment.get("created_at") == comment.get("updated_at"), "FREEZE_COMMENT_EDITED")
    require(utc_ns(comment.get("created_at")) < utc_ns(source["run_created_at"]), "FREEZE_NOT_BEFORE_RUN")
    return {"comment": comment, "payload": value,
            "body_sha256": hashlib.sha256(comment["body"].encode("utf-8")).hexdigest()}


def finish_freeze_checkpoint(selected: dict[str, Any], direct: Any, issue_before: Any,
                             issue_after: Any, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    before = validate_registration_issue(issue_before)
    after = validate_registration_issue(issue_after)
    require(before == after, "FREEZE_COMMENT_CHECKPOINT_RACE")
    require(isinstance(direct, dict), "FREEZE_DIRECT_LIST_MISMATCH")
    comment = selected["comment"]
    keys = ("id", "body", "created_at", "updated_at", "issue_url")
    require(all(key in direct and direct[key] == comment.get(key) for key in keys),
            "FREEZE_DIRECT_LIST_MISMATCH")
    require(isinstance(direct.get("user"), dict) and
            all(direct["user"].get(key) == comment["user"][key] for key in ("id", "login", "type")),
            "FREEZE_DIRECT_LIST_MISMATCH")
    result = {"comment_id": comment["id"], "body_sha256": selected["body_sha256"],
              "author": {key: comment["user"][key] for key in ("id", "login", "type")},
              "created_at": comment["created_at"], "updated_at": comment["updated_at"],
              "payload": selected["payload"], "complete_checkpoint": True}
    if previous is not None:
        require(result == previous, "FREEZE_CHANGED_AFTER_PRE")
    return result


@dataclasses.dataclass
class AcquisitionLedger:
    next_route: int = 1
    active_ns: int = 0
    raw_bytes: int = 0
    helper_starts: int = 0
    helper_reaped: bool = False
    accounted_routes: set[int] = dataclasses.field(default_factory=set)
    request_records: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    validation_ns: int = 0

    def consistent(self) -> None:
        require(self.active_ns == self.validation_ns + sum(row["whole_operation_elapsed_ns"] for row in self.request_records) and
                self.raw_bytes == sum(row["body_bytes"] + row["exchange_bytes"] for row in self.request_records),
                "API_BUDGET_ACCOUNTING_DRIFT")

    def admit_start(self, route: int) -> None:
        self.consistent()
        require(self.next_route == len(self.accounted_routes) + 1, "API_BUDGET_ACCOUNTING_DRIFT")
        require(type(route) is int and route == self.next_route and 1 <= route <= 17,
                "API_REQUEST_BUDGET_EXCEEDED")
        require(self.active_ns < API_ACTIVE_NS, "API_AGGREGATE_BUDGET_EXCEEDED")
        self.next_route += 1

    def account(self, route: int, body_bytes: int, exchange_bytes: int, duration_ns: int) -> None:
        self.consistent()
        require(type(route) is int and route == self.next_route - 1 == len(self.accounted_routes) + 1 and
                route not in self.accounted_routes and 1 <= route <= 17, "API_BUDGET_ACCOUNTING_DRIFT")
        require(strict_int(body_bytes) and body_bytes <= API_BODY_CAPS[route - 1], "API_BODY_BOUND_EXCEEDED")
        require(strict_int(exchange_bytes) and exchange_bytes <= 16384, "API_EXCHANGE_BOUND_EXCEEDED")
        require(strict_int(duration_ns) and duration_ns <= COMMAND_NS, "API_WHOLE_OPERATION_TIMEOUT")
        require(self.active_ns + duration_ns <= API_ACTIVE_NS, "API_AGGREGATE_BUDGET_EXCEEDED")
        validate_control_bytes(self.raw_bytes + body_bytes + exchange_bytes)
        self.active_ns += duration_ns
        self.raw_bytes += body_bytes + exchange_bytes
        self.accounted_routes.add(route)
        self.request_records.append({"route": route, "body_bytes": body_bytes,
                                     "exchange_bytes": exchange_bytes, "whole_operation_elapsed_ns": duration_ns})

    def account_validation(self, duration_ns: int) -> None:
        self.consistent()
        require(strict_int(duration_ns) and self.active_ns + duration_ns <= API_ACTIVE_NS,
                "API_AGGREGATE_BUDGET_EXCEEDED")
        self.active_ns += duration_ns
        self.validation_ns += duration_ns

    def start_helper(self) -> None:
        require(type(self.helper_starts) is int and self.helper_starts == 0, "METADATA_HELPER_RETRY_NOT_ALLOWED")
        self.helper_starts += 1

    def finish(self) -> None:
        self.consistent()
        require(self.next_route == 18 and self.accounted_routes == set(range(1, 18)), "FREEZE_POST_CHECKPOINT_INCOMPLETE")
        require(type(self.helper_starts) is int and self.helper_starts == 1 and self.helper_reaped is True,
                "METADATA_HELPER_LIFECYCLE_INCOMPLETE")


def validate_api_exchange(route: int, body: bytes, exchange: dict[str, Any], expected_url: str) -> Any:
    require(type(route) is int and 1 <= route <= 17 and isinstance(body, bytes), "API_ROUTE_NOT_REGISTERED")
    require(expected_url.startswith(API_PREFIX) and exchange.get("url") == expected_url and
            exchange.get("method") == "GET", "API_ROUTE_NOT_REGISTERED")
    require(type(exchange.get("status")) is int and exchange["status"] == 200 and
            exchange.get("complete") is True, "API_RESPONSE_NOT_ADMITTED")
    headers = exchange.get("headers", {})
    require(isinstance(headers, dict) and all(isinstance(key, str) and isinstance(value, str)
            and "\r" not in key and "\n" not in key and "\r" not in value and "\n" not in value
            for key, value in headers.items()), "API_RESPONSE_NOT_ADMITTED")
    encoding = [v for k, v in headers.items() if k.lower() == "content-encoding"]
    require(len(encoding) <= 1 and (not encoding or encoding[0].lower() == "identity"),
            "API_RESPONSE_NOT_ADMITTED")
    require(len(body) <= API_BODY_CAPS[route - 1], "API_BODY_BOUND_EXCEEDED")
    require(exchange.get("body_sha256") == hashlib.sha256(body).hexdigest() and
            type(exchange.get("body_bytes")) is int and exchange["body_bytes"] == len(body),
            "CONTROL_ORIGINAL_EVIDENCE_INCOMPLETE")
    return strict_json(body, API_BODY_CAPS[route - 1])


def validate_control_bytes(total_bytes: int) -> None:
    require(strict_int(total_bytes) and total_bytes <= CONTROL_BYTES, "CONTROL_EVIDENCE_BOUND_EXCEEDED")


def validate_operation_observation(record: dict[str, Any]) -> None:
    """Validate the parent's complete operation, including capture and cleanup.

    The raw exchange records its pre-capture measurement cut. This record is
    emitted later in the original receipt, so it can include the capture that
    created that exchange without claiming a self-observed future timestamp.
    """
    require(isinstance(record, dict), "API_BUDGET_ACCOUNTING_DRIFT")
    admitted = record.get("admitted_duration_ns")
    elapsed = record.get("whole_operation_elapsed_ns")
    require(strict_int(admitted, 1) and admitted <= COMMAND_NS and strict_int(elapsed)
            and elapsed <= admitted, "API_WHOLE_OPERATION_TIMEOUT")
    require(strict_int(record.get("start_monotonic_ns")), "API_BUDGET_ACCOUNTING_DRIFT")


def capture_control_member(output: Path, name: str, raw: bytes) -> None:
    """Create a fixed original member through owned no-follow directory FDs."""
    require(re.fullmatch(r"r(?:0[1-9]|1[0-7])-[a-z-]+\.(?:body|exchange)\.json", name) is not None,
            "ARCHIVE_MEMBER_SET_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(output, flags)
    descriptors = [directory]
    try:
        for part in ("control", "api"):
            info = os.fstat(directory)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(),
                    "CONTROL_EVIDENCE_DIRECTORY_INVALID")
            try:
                os.mkdir(part, 0o700, dir_fd=directory)
            except FileExistsError:
                pass
            directory = os.open(part, flags, dir_fd=directory)
            descriptors.append(directory)
        info = os.fstat(directory)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(),
                "CONTROL_EVIDENCE_DIRECTORY_INVALID")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                     0o600, dir_fd=directory)
        try:
            offset = 0
            while offset < len(raw):
                try:
                    wrote = os.write(fd, raw[offset:])
                except InterruptedError:
                    continue
                require(wrote > 0, "CONTROL_EVIDENCE_WRITE_INCOMPLETE")
                offset += wrote
        finally:
            os.close(fd)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def api_route_url(request: dict[str, Any]) -> str:
    require(isinstance(request, dict) and set(request) == {"route", "role", "run_id", "pr_number", "C", "S", "comment_id"},
            "API_ROUTE_NOT_REGISTERED")
    route, role = request["route"], request["role"]
    require(type(route) is int and 1 <= route <= 17 and role in ("pull_request", "push"),
            "API_ROUTE_NOT_REGISTERED")
    run_id = positive_id(request["run_id"], "API_ROUTE_NOT_REGISTERED")
    if route in (1, 10):
        path = f"actions/runs/{run_id}/attempts/1"
    elif route == 2:
        path = f"actions/runs/{run_id}/attempts/1/jobs?per_page=100&page=1"
    elif route in (3, 11):
        path = "git/ref/heads/main"
    elif route in (4, 12):
        path = (f"pulls/{positive_id(request['pr_number'], 'API_ROUTE_NOT_REGISTERED')}" if role == "pull_request"
                else f"commits/{oid(request['S'])}/pulls?per_page=100&page=1")
    elif route in (5, 13):
        path = (f"commits/{oid(request['C'])}/pulls?per_page=100&page=1" if role == "pull_request"
                else f"pulls/{positive_id(request['pr_number'], 'API_ROUTE_NOT_REGISTERED')}")
    elif route in (6, 9, 14, 17):
        path = "issues/847"
    elif route in (7, 15):
        path = "issues/847/comments?per_page=100&page=1"
    else:
        require(route in (8, 16), "API_ROUTE_NOT_REGISTERED")
        path = f"issues/comments/{positive_id(request['comment_id'], 'API_ROUTE_NOT_REGISTERED')}"
    return API_PREFIX + path


def _worker_read_exact(stream: Any, count: int) -> bytes | None:
    output = bytearray()
    while len(output) < count:
        part = stream.read(count - len(output))
        if not part:
            return None if not output else bytes(output)
        output.extend(part)
    return bytes(output)


def _worker_frame(kind: bytes, payload: bytes) -> None:
    import struct
    require(kind in (b"H", b"B", b"D") and len(payload) <= (65536 if kind == b"B" else 16384),
            "METADATA_WORKER_FRAME_BOUND_EXCEEDED")
    for raw in (struct.pack("!cI", kind, len(payload)), payload):
        offset = 0
        while offset < len(raw):
            try:
                written = os.write(sys.stdout.fileno(), raw[offset:])
            except InterruptedError:
                continue
            require(written > 0, "METADATA_WORKER_RESPONSE_TRUNCATED")
            offset += written


def metadata_http_worker() -> int:
    """The sole owned HTTP child: fixed GET routes, streaming bounded originals.

    This entry is never used by offline tests. The parent owns the complete
    operation deadline, process group and wait; socket timeout alone is not it.
    """
    import struct
    import http.client
    import urllib.error
    import urllib.request
    require(sys.flags.isolated == 1, "ISOLATED_STANDARD_LIBRARY_RUNTIME_REQUIRED")
    require(os.environ.get("FE_A3_OWNED_HTTP_WORKER") == "1", "METADATA_WORKER_PARENT_REQUIRED")
    require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", "RUN_ATTEMPT_NOT_REGISTERED")
    token = os.environ.get("GH_TOKEN", "")
    require(bool(token) and len(token) <= 8192 and "\r" not in token and "\n" not in token,
            "READ_ONLY_PROVIDER_TOKEN_REQUIRED")

    class RefuseRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RefuseRedirect())
    expected_route, role, run_id = 1, None, None
    for _ in range(17):
        raw_size = _worker_read_exact(sys.stdin.buffer, 4)
        if raw_size is None:
            return 0
        require(len(raw_size) == 4, "METADATA_WORKER_REQUEST_TRUNCATED")
        size = struct.unpack("!I", raw_size)[0]
        require(0 < size <= 4096, "METADATA_WORKER_REQUEST_BOUND_EXCEEDED")
        raw = _worker_read_exact(sys.stdin.buffer, size)
        require(raw is not None and len(raw) == size, "METADATA_WORKER_REQUEST_TRUNCATED")
        request = strict_json(raw, 4096)
        url = api_route_url(request)
        require(request["route"] == expected_route, "API_REQUEST_BUDGET_EXCEEDED")
        if role is None:
            role, run_id = request["role"], request["run_id"]
            require(os.environ.get("GITHUB_EVENT_NAME") == role and
                    os.environ.get("GITHUB_RUN_ID") == str(run_id) and
                    os.environ.get("GITHUB_REPOSITORY") == REPOSITORY,
                    "ACTUAL_RUN_BINDING_REQUIRED")
        require((role, run_id) == (request["role"], request["run_id"]), "API_ROUTE_NOT_REGISTERED")
        cap = API_BODY_CAPS[expected_route - 1]
        digest, body_bytes, response_started = hashlib.sha256(), 0, False
        failure, complete = "", False
        response = None
        try:
            req = urllib.request.Request(url, method="GET", headers={
                "Accept": "application/vnd.github+json", "Accept-Encoding": "identity",
                "Authorization": "Bearer " + token, "User-Agent": "FE09-A3-R1-owned-source-admission",
                "X-GitHub-Api-Version": "2022-11-28"})
            try:
                response = opener.open(req, timeout=4.5)
            except urllib.error.HTTPError as exc:
                # Preserve this actual response; never follow its Location.
                response = exc
            observed: dict[str, str] = {}
            for header in ("Link", "Content-Type", "Content-Encoding", "Content-Length", "X-GitHub-Request-Id"):
                values = response.headers.get_all(header, [])
                if values:
                    require(all(isinstance(value, str) for value in values), "API_RESPONSE_NOT_ADMITTED")
                    observed[header.lower()] = ", ".join(values)
            metadata = {"route": expected_route, "status": response.status, "headers": observed}
            encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            require(len(encoded) <= 8192, "API_EXCHANGE_BOUND_EXCEEDED")
            _worker_frame(b"H", encoded)
            response_started = True
            while True:
                incomplete = False
                try:
                    chunk = response.read(min(65536, cap - body_bytes + 1))
                except http.client.IncompleteRead as exc:
                    chunk = exc.partial
                    incomplete = True
                if not chunk:
                    complete = not incomplete
                    failure = "API_RESPONSE_TRUNCATED" if incomplete else ""
                    break
                permitted = min(len(chunk), cap - body_bytes)
                if permitted:
                    prefix = chunk[:permitted]
                    _worker_frame(b"B", prefix)
                    digest.update(prefix)
                    body_bytes += permitted
                if permitted != len(chunk):
                    failure = "API_BODY_BOUND_EXCEEDED"
                    break
                if incomplete:
                    failure = "API_RESPONSE_TRUNCATED"
                    break
        except AdmissionError as exc:
            failure = exc.reason
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
            failure = "API_NETWORK_FAILED"
        finally:
            if response is not None:
                response.close()
        done = {"route": expected_route, "complete": complete and not failure,
                "response_started": response_started, "failure_reason": failure,
                "body_bytes": body_bytes, "body_sha256": digest.hexdigest()}
        _worker_frame(b"D", json.dumps(done, sort_keys=True, separators=(",", ":")).encode())
        if failure:
            return 2
        expected_route += 1
    return 0


class OwnedHTTPWorker:
    """One helper for all17 reads; no restart and no live test entry point."""
    def __init__(self, source_scope: dict[str, Any], collector_budget: DurationBudget,
                 ledger: AcquisitionLedger, output: Path):
        require(source_scope.get("disposition") == REQUIRED and
                source_scope.get("scientific_execution_admitted") is False,
                "PROVIDER_ACQUISITION_SCOPE_REQUIRED")
        self.collector_budget = collector_budget
        self.ledger = ledger
        self.output = output
        self.process: subprocess.Popen[bytes] | None = None
        self.stderr = bytearray()
        self.failed_budget: DurationBudget | None = None
        self.failed_operation: dict[str, Any] | None = None
        self.lifecycle: dict[str, Any] = {"source_path": str(Path(__file__).resolve()),
                                          "source_sha256": hashlib.sha256(read_regular(Path(__file__), FILE_CAP)).hexdigest(),
                                          "start_attempts": 0, "actual_pid": None, "wait_returncode": None,
                                          "owned_process_reaped": False, "scientific_C_target": False}

    def _budget(self) -> DurationBudget:
        remaining = min(COMMAND_NS, API_ACTIVE_NS - self.ledger.active_ns,
                        self.collector_budget.remaining_ns())
        require(remaining > CLEANUP_RESERVE_NS, "API_AGGREGATE_BUDGET_EXCEEDED")
        return DurationBudget.start(remaining)

    def _start(self) -> None:
        require(self.process is None and self.lifecycle["start_attempts"] == 0,
                "METADATA_HELPER_RETRY_NOT_ALLOWED")
        self.lifecycle["start_attempts"] = 1
        self.ledger.start_helper()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("PYTHON") and key not in ("GITHUB_TOKEN",)}
        env["FE_A3_OWNED_HTTP_WORKER"] = "1"
        argv = [sys.executable, "-I", "-u", str(Path(__file__).resolve()), "--http-worker"]
        self.lifecycle["argv"] = argv
        self.lifecycle["start_monotonic_ns"] = time.monotonic_ns()
        self.process = subprocess.Popen(argv, cwd=Path.cwd(), env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        start_new_session=True, close_fds=True)
        self.lifecycle["actual_pid"] = self.process.pid
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)

    def _kill_wait(self, budget: DurationBudget) -> None:
        if self.process is None or self.lifecycle["owned_process_reaped"]:
            return
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            code = self.process.wait(timeout=budget.remaining_ns() / 1e9)
        except subprocess.TimeoutExpired as exc:
            raise AdmissionError("METADATA_HELPER_LIFECYCLE_INCOMPLETE") from exc
        self.lifecycle["wait_returncode"] = code
        self.lifecycle["owned_process_reaped"] = True
        self.lifecycle["wait_monotonic_ns"] = time.monotonic_ns()
        self.ledger.helper_reaped = True
        require(budget.remaining_ns() > 0, "API_WHOLE_OPERATION_TIMEOUT")

    def _write_request(self, payload: bytes, budget: DurationBudget) -> None:
        assert self.process is not None and self.process.stdin is not None
        selector = selectors.DefaultSelector()
        try:
            selector.register(self.process.stdin.fileno(), selectors.EVENT_WRITE)
            done = 0
            while done < len(payload):
                left = budget.remaining_ns()
                require(left > CLEANUP_RESERVE_NS, "API_WHOLE_OPERATION_TIMEOUT")
                ready = selector.select(min(0.05, (left - CLEANUP_RESERVE_NS) / 1e9))
                if not ready:
                    continue
                try:
                    count = os.write(self.process.stdin.fileno(), payload[done:])
                except BlockingIOError:
                    continue
                require(count > 0, "METADATA_WORKER_REQUEST_TRUNCATED")
                done += count
        finally:
            selector.close()

    def request(self, request: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        import struct
        route = request.get("route")
        url = api_route_url(request)
        self.ledger.admit_start(route)
        budget = self._budget()
        # Install the original deadline before any operation can raise. Even
        # an unexpected decoder/capture exception cannot mint a cleanup cap.
        self.failed_budget = budget
        self.failed_operation = {"route": route, "failure_reason": "OPERATION_NOT_COMPLETED",
                                 "start_monotonic_ns": budget.start_ns,
                                 "admitted_duration_ns": budget.duration_ns}
        body, wire = bytearray(), bytearray()
        observed: dict[str, Any] | None = None
        done: dict[str, Any] | None = None
        failure = ""
        selector = selectors.DefaultSelector()
        value: Any = None
        try:
            if self.process is None:
                self._start()
            assert self.process is not None and self.process.stdout is not None and self.process.stderr is not None
            raw = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
            require(len(raw) <= 4096, "METADATA_WORKER_REQUEST_BOUND_EXCEEDED")
            self._write_request(struct.pack("!I", len(raw)) + raw, budget)
            selector.register(self.process.stdout.fileno(), selectors.EVENT_READ, "stdout")
            selector.register(self.process.stderr.fileno(), selectors.EVENT_READ, "stderr")
            while done is None:
                left = budget.remaining_ns()
                require(left > CLEANUP_RESERVE_NS, "API_WHOLE_OPERATION_TIMEOUT")
                for key, _ in selector.select(min(0.05, (left - CLEANUP_RESERVE_NS) / 1e9)):
                    try:
                        part = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not part:
                        selector.unregister(key.fd)
                        require(key.data != "stdout" or done is not None, "METADATA_WORKER_RESPONSE_TRUNCATED")
                        continue
                    if key.data == "stderr":
                        require(len(self.stderr) + len(part) <= STDERR_CAP, "METADATA_HELPER_DIAGNOSTIC_BOUND_EXCEEDED")
                        self.stderr.extend(part)
                        continue
                    require(len(wire) + len(part) <= 131072, "METADATA_WORKER_FRAME_BOUND_EXCEEDED")
                    wire.extend(part)
                    while len(wire) >= 5:
                        kind, count = struct.unpack("!cI", wire[:5])
                        require(kind in (b"H", b"B", b"D") and count <= (65536 if kind == b"B" else 16384),
                                "METADATA_WORKER_FRAME_BOUND_EXCEEDED")
                        if len(wire) < count + 5:
                            break
                        payload = bytes(wire[5:5 + count]); del wire[:5 + count]
                        if kind == b"H":
                            require(observed is None and not body and done is None, "METADATA_WORKER_FRAME_ORDER_INVALID")
                            observed = strict_json(payload, 16384)
                            require(isinstance(observed, dict) and set(observed) == {"route", "status", "headers"} and
                                    type(observed["route"]) is int and observed["route"] == route,
                                    "METADATA_WORKER_FRAME_ORDER_INVALID")
                        elif kind == b"B":
                            require(observed is not None and done is None and
                                    len(body) + len(payload) <= API_BODY_CAPS[route - 1], "API_BODY_BOUND_EXCEEDED")
                            body.extend(payload)
                        else:
                            require(done is None, "METADATA_WORKER_FRAME_ORDER_INVALID")
                            done = strict_json(payload, 16384)
                            require(isinstance(done, dict) and set(done) == {"route", "complete", "response_started", "failure_reason", "body_bytes", "body_sha256"} and
                                    type(done["route"]) is int and done["route"] == route and
                                    type(done["complete"]) is bool and type(done["response_started"]) is bool and
                                    type(done["body_bytes"]) is int and done["body_bytes"] == len(body) and
                                    done["body_sha256"] == hashlib.sha256(body).hexdigest(),
                                    "CONTROL_ORIGINAL_EVIDENCE_INCOMPLETE")
                            require(not wire, "METADATA_WORKER_FRAME_ORDER_INVALID")
            require(done["response_started"] == (observed is not None), "CONTROL_ORIGINAL_EVIDENCE_INCOMPLETE")
            if done["failure_reason"]:
                require(done["failure_reason"] in {"API_BODY_BOUND_EXCEEDED", "API_EXCHANGE_BOUND_EXCEEDED", "API_RESPONSE_NOT_ADMITTED", "API_NETWORK_FAILED", "API_RESPONSE_TRUNCATED"},
                        "METADATA_WORKER_FRAME_ORDER_INVALID")
                raise AdmissionError(done["failure_reason"])
            preview = {"url": url, "method": "GET", "status": observed["status"] if observed else None,
                       "headers": observed["headers"] if observed else {}, "complete": done["complete"],
                       "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest()}
            value = validate_api_exchange(route, bytes(body), preview, url)
            if route == 17:
                left = budget.remaining_ns()
                require(left > CLEANUP_RESERVE_NS, "API_WHOLE_OPERATION_TIMEOUT")
                try:
                    code = self.process.wait(timeout=(left - CLEANUP_RESERVE_NS) / 1e9)
                except subprocess.TimeoutExpired as exc:
                    raise AdmissionError("METADATA_HELPER_LIFECYCLE_INCOMPLETE") from exc
                self.lifecycle["owned_process_reaped"] = True
                self.lifecycle["wait_returncode"] = code
                self.lifecycle["wait_monotonic_ns"] = time.monotonic_ns()
                self.ledger.helper_reaped = True
                require(code == 0, "METADATA_HELPER_LIFECYCLE_INCOMPLETE")
                # A completed helper must not leave another response or child
                # holding its pipes. No request is consumed speculatively.
                for stream, channel in ((self.process.stdout, "stdout"), (self.process.stderr, "stderr")):
                    assert stream is not None
                    while True:
                        try:
                            trailing = os.read(stream.fileno(), 65536)
                        except BlockingIOError as exc:
                            raise AdmissionError("METADATA_HELPER_LIFECYCLE_INCOMPLETE") from exc
                        if not trailing:
                            break
                        require(channel == "stderr", "METADATA_WORKER_FRAME_ORDER_INVALID")
                        require(len(self.stderr) + len(trailing) <= STDERR_CAP,
                                "METADATA_HELPER_DIAGNOSTIC_BOUND_EXCEEDED")
                        self.stderr.extend(trailing)
        except AdmissionError as exc:
            failure = exc.reason
        except (OSError, UnicodeError, ValueError):
            failure = "API_ACQUISITION_FAILED"
        except BaseException:
            # Deep malformed JSON or interruption must retain this same
            # operation budget; it may not escape to a fresh cleanup window.
            failure = "API_ACQUISITION_FAILED"
        finally:
            selector.close()
            if failure:
                try:
                    self._kill_wait(budget)
                except AdmissionError as exc:
                    failure = failure + ";" + exc.reason
        elapsed = time.monotonic_ns() - budget.start_ns
        if elapsed > budget.duration_ns:
            failure = failure or "API_WHOLE_OPERATION_TIMEOUT"
        if not failure and budget.remaining_ns() <= CLEANUP_RESERVE_NS:
            failure = "API_WHOLE_OPERATION_TIMEOUT"
            try:
                self._kill_wait(budget)
            except AdmissionError as exc:
                failure += ";" + exc.reason
        exchange = {"schema_version": 1, "route": route, "url": url, "method": "GET",
                    "status": observed.get("status") if observed else None,
                    "headers": observed.get("headers", {}) if observed else {},
                    "response_started": observed is not None,
                    "response_body_complete": done is not None and done.get("complete") is True,
                    "complete": not failure and done is not None and done.get("complete") is True,
                    "failure_reason": failure, "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(),
                    "started_monotonic_ns": budget.start_ns, "admitted_duration_ns": budget.duration_ns,
                    "acquisition_decode_cleanup_elapsed_ns": elapsed,
                    "measurement_cut": "BEFORE_ORIGINAL_CONTROL_FILE_CAPTURE",
                    "whole_operation_observation_location": "receipt.control_plane.request_records",
                    "helper_pid": self.lifecycle["actual_pid"],
                    "failure_body_role": "PARENT_RECEIVED_BOUNDED_PREFIX_ONLY" if failure else "COMPLETE_ORIGINAL_RESPONSE_BODY"}
        exchange_raw = json.dumps(exchange, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
        stem = f"r{route:02d}-" + API_LABELS[route - 1]
        captured: list[str] = []
        try:
            require(len(exchange_raw) <= 16384, "API_EXCHANGE_BOUND_EXCEEDED")
            validate_control_bytes(self.ledger.raw_bytes + len(body) + len(exchange_raw))
            for suffix, raw in ((".body.json", bytes(body)), (".exchange.json", exchange_raw)):
                capture_control_member(self.output, stem + suffix, raw)
                captured.append("control/api/" + stem + suffix)
            # Capture/serialization belongs to this request. The later receipt
            # records this complete duration; the exchange explains its cut.
            final_elapsed = time.monotonic_ns() - budget.start_ns
            record = {"start_monotonic_ns": budget.start_ns,
                      "admitted_duration_ns": budget.duration_ns,
                      "whole_operation_elapsed_ns": final_elapsed}
            validate_operation_observation(record)
            if not failure:
                self.ledger.account(route, len(body), len(exchange_raw), final_elapsed)
                self.ledger.request_records[-1].update(record | {
                    "response_body_sha256": exchange["body_sha256"],
                    "exchange_sha256": hashlib.sha256(exchange_raw).hexdigest()})
        except AdmissionError as exc:
            failure = failure or exc.reason
        except (OSError, UnicodeError, ValueError):
            failure = failure or "CONTROL_EVIDENCE_WRITE_INCOMPLETE"
        if failure:
            self.failed_budget = budget
            try:
                self._kill_wait(budget)
            except AdmissionError as exc:
                failure += ";" + exc.reason
            self.failed_operation = {"route": route, "failure_reason": failure,
                                     "start_monotonic_ns": budget.start_ns,
                                     "admitted_duration_ns": budget.duration_ns,
                                     "actual_elapsed_ns": time.monotonic_ns() - budget.start_ns,
                                     "body_bytes_received": len(body), "exchange_bytes_prepared": len(exchange_raw),
                                     "original_members_captured": captured}
            raise AdmissionError(failure)
        self.failed_budget = None
        self.failed_operation = None
        return value, exchange

    def close(self) -> None:
        try:
            if self.process is not None and not self.lifecycle["owned_process_reaped"]:
                # An expired request receives no second cleanup allowance.
                # With an exhausted aggregate allowance, still send SIGKILL
                # and attempt an immediate reap; never report qualification.
                remaining = max(0, min(COMMAND_NS, API_ACTIVE_NS - self.ledger.active_ns,
                                       self.collector_budget.remaining_ns()))
                budget = self.failed_budget or DurationBudget(time.monotonic_ns(), remaining)
                try:
                    self._kill_wait(budget)
                finally:
                    if self.failed_budget is None:
                        self.ledger.account_validation(time.monotonic_ns() - budget.start_ns)
        finally:
            if self.process is not None:
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                    if stream is not None:
                        stream.close()
            self.lifecycle["stderr_bytes"] = len(self.stderr)
            self.lifecycle["stderr_sha256"] = hashlib.sha256(self.stderr).hexdigest()
            self.lifecycle["stderr_hex"] = bytes(self.stderr).hex()
            if self.failed_budget is not None and self.failed_operation is not None:
                self.failed_operation["actual_elapsed_through_finalization_ns"] = time.monotonic_ns() - self.failed_budget.start_ns


class AdmissionActivity:
    """One cumulative PRE/POST active clock; the scientific gap is excluded."""
    def __init__(self, ledger: AcquisitionLedger, collector_budget: DurationBudget):
        self.ledger = ledger
        self.collector_budget = collector_budget
        self.phase: dict[str, Any] | None = None
        self.phases: list[dict[str, Any]] = []

    def begin(self, name: str, start_ns: int | None = None) -> None:
        require(self.phase is None, "API_BUDGET_ACCOUNTING_DRIFT")
        now = time.monotonic_ns() if start_ns is None else start_ns
        require(strict_int(now) and now <= time.monotonic_ns(), "MONOTONIC_CLOCK_INVALID")
        self.phase = {"phase": name, "start_monotonic_ns": now,
                      "previous_active_ns": self.ledger.active_ns}

    def sync(self, now_ns: int | None = None) -> int:
        require(self.phase is not None, "API_BUDGET_ACCOUNTING_DRIFT")
        now = time.monotonic_ns() if now_ns is None else now_ns
        elapsed = now - self.phase["start_monotonic_ns"]
        already = self.ledger.active_ns - self.phase["previous_active_ns"]
        # Request records already include their measured DNS/body/capture and
        # cleanup interval. Account the remaining elapsed phase exactly once.
        require(strict_int(elapsed) and elapsed >= already, "API_BUDGET_ACCOUNTING_DRIFT")
        self.ledger.account_validation(elapsed - already)
        require(self.collector_budget.remaining_ns(now) > 0, "A3_ENCLOSING_BUDGET_EXHAUSTED")
        return now

    def end(self) -> None:
        try:
            now = self.sync()
        except AdmissionError as exc:
            assert self.phase is not None
            self.phases.append(dict(self.phase, actual_end_monotonic_ns=time.monotonic_ns(),
                                    complete=False, failure_reason=exc.reason))
            self.phase = None
            raise
        assert self.phase is not None
        self.phases.append(dict(self.phase, actual_end_monotonic_ns=now, complete=True,
                                actual_elapsed_ns=now - self.phase["start_monotonic_ns"],
                                cumulative_active_ns=self.ledger.active_ns))
        self.phase = None


class AdmissionGit(GitObjects):
    def __init__(self, root: Path, activity: AdmissionActivity):
        super().__init__(root)
        self.activity = activity

    def run(self, *args: str, cap: int = FILE_CAP) -> bytes:
        self.activity.sync()
        # Each existing Git reader owns a complete five-second operation.
        # Admit it only when that entire allowance fits both enclosing clocks.
        require(API_ACTIVE_NS - self.activity.ledger.active_ns >= COMMAND_NS and
                self.activity.collector_budget.remaining_ns() >= COMMAND_NS,
                "API_AGGREGATE_BUDGET_EXCEEDED")
        try:
            return super().run(*args, cap=cap)
        finally:
            self.activity.sync()


def actual_source_graph(git: GitObjects, b: str, c: str, checkout: str) -> dict[str, Any]:
    graph: dict[str, Any] = {}
    def add(commit: str) -> tuple[str, ...]:
        if commit not in graph:
            require(len(graph) < 256, "C_BASE_ANCESTRY_DRIFT")
            tree, parents = git.commit(commit)
            graph[commit] = {"tree": tree, "parents": list(parents)}
        return tuple(graph[commit]["parents"])
    for value in (b, c, checkout):
        add(oid(value))
    pending, expanded = [c], set()
    while pending:
        current = pending.pop()
        if current == b:
            break
        if current in expanded:
            continue
        expanded.add(current)
        parents = add(current)
        if b in parents:
            break
        pending.extend(parents)
    require(graph_has_ancestor(graph, b, c), "C_BASE_ANCESTRY_DRIFT")
    return graph


def actual_source_closure(git: GitObjects, root: Path, source: dict[str, Any]) -> dict[str, Any]:
    documents: dict[str, bytes] = {}
    protected: dict[str, bytes] = {}
    for name in (*FREEZE_DOC_FIELDS.values(),):
        path = DOC_ROOT + "/" + name
        documents[name] = git.blob(source["C"], path) or b""
        protected[name] = git.blob(source["B"], path) or b""
    lock = strict_json(documents["source-lock.json"])
    base_lock = strict_json(protected["source-lock.json"])
    require(isinstance(base_lock, dict) and isinstance(base_lock.get("known_immutable_files"), list) and
            len(base_lock["known_immutable_files"]) == 88, "IMMUTABLE_SCIENTIFIC_SOURCE_CLOSURE_INVALID")
    original: dict[str, dict[str, Any]] = {}
    implementation: dict[str, dict[str, Any]] = {}
    programs: dict[str, bytes] = {}
    def observed(path: str) -> tuple[bytes, dict[str, Any]]:
        path = safe_path(path)
        entry = git.entry(source["C"], path)
        require(entry is not None and entry.mode == "100644", "EXECUTION_SOURCE_CLOSURE_INCOMPLETE", path)
        raw = git.blob(source["C"], path) or b""
        actual_path = root / path
        require(actual_path.resolve(strict=True) == actual_path and
                read_regular(actual_path, FILE_CAP) == raw, "EXECUTION_WORKTREE_SOURCE_DRIFT", path)
        row = source_row(path, raw, entry.mode)
        require(row["git_blob_sha1"] == entry.blob, "GIT_BLOB_IDENTITY_MISMATCH")
        return raw, row
    for item in base_lock["known_immutable_files"]:
        require(isinstance(item, dict), "IMMUTABLE_SCIENTIFIC_SOURCE_CLOSURE_INVALID")
        path = safe_path(item.get("path"))
        _, row = observed(path)
        for original_commit in (SCIENTIFIC_BASE, ORIGINAL_COMPARISON):
            entry = git.entry(original_commit, path)
            require(entry is not None and entry.mode == "100644" and entry.blob == row["git_blob_sha1"],
                    "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT", path)
        original[path] = row
    for path in sorted({"tests/validation/frontend_evolution/" + name for name in SOURCE_FILES} | set(HOOKS)):
        raw, row = observed(path)
        implementation[path] = row
        if path not in HOOKS:
            programs[path] = raw
    for name, raw in documents.items():
        path = root / DOC_ROOT / name
        require(path.resolve(strict=True) == path and read_regular(path, FILE_CAP) == raw,
                "EXECUTION_WORKTREE_SOURCE_DRIFT", DOC_ROOT + "/" + name)
    guard_entry = git.entry(source["B"], GUARD)
    require(guard_entry is not None and guard_entry.mode == "100644", "PROTECTED_POLICY_MODE_DRIFT")
    guard = git.blob(source["B"], GUARD) or b""
    result = validate_source_documents(documents, protected, source["C"], original, implementation,
                                       source_row(GUARD, guard), read_regular(Path(__file__), FILE_CAP), programs)
    require(result["qualified_base"]["commit"] == source["B"] and
            result["qualified_base"]["tree"] == source["B_tree"], "INTEGRATION_BASE_NOT_QUALIFIED")
    require(lock["original_direct_translation_units"] and len(lock["original_direct_translation_units"]) == 20,
            "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
    result["actual_checkout"] = source["checkout"]
    result["actual_candidate"] = source["C"]
    result["actual_candidate_tree"] = source["C_tree"]
    return result


class ProviderAdmission:
    """Live coordinator, callable only by the frozen collector after scope.

    Merely importing this class does not read the network. Offline controls
    never instantiate it; source-only scope never creates the HTTP child.
    The collector supplies its real entry clocks, never a CLI deadline or C.
    """
    def __init__(self, root: Path, event_path: Path, env: dict[str, str], output: Path,
                 stage_monotonic_ns: int, stage_epoch_ns: int):
        require(sys.flags.isolated == 1, "ISOLATED_STANDARD_LIBRARY_RUNTIME_REQUIRED")
        self.root = root.resolve(strict=True)
        self.output = output
        self.stage_monotonic_ns, self.stage_epoch_ns = stage_monotonic_ns, stage_epoch_ns
        require(strict_int(stage_monotonic_ns) and strict_int(stage_epoch_ns) and
                stage_monotonic_ns <= time.monotonic_ns() and stage_epoch_ns <= time.time_ns(), "TIME_BUDGET_INVALID")
        self.ledger = AcquisitionLedger()
        self.activity = AdmissionActivity(self.ledger, DurationBudget(stage_monotonic_ns, 600_000_000_000))
        self.activity.begin("PRE", stage_monotonic_ns)
        self.git = AdmissionGit(self.root, self.activity)
        self.worker: OwnedHTTPWorker | None = None
        self.pre_receipt: dict[str, Any] | None = None
        self.post_receipt: dict[str, Any] | None = None
        self.post_validated = False
        self.failure: dict[str, Any] | None = None
        self.source: dict[str, Any] | None = None
        self.freeze: dict[str, Any] | None = None
        self.closure: dict[str, Any] | None = None
        self.graph: dict[str, Any] = {}
        self.job: dict[str, Any] | None = None
        self.scope = local_scope(self.root, event_path, env, self.git)
        require(self.scope.get("disposition") == REQUIRED and self.scope.get("api_requests") == 0 and
                self.scope.get("HTTP_helper_starts") == 0 and self.scope.get("scientific_execution_admitted") is False,
                "PROVIDER_ACQUISITION_SCOPE_REQUIRED")
        local = self.scope["actual_local_source"]
        event = strict_json(read_regular(event_path, FILE_CAP))
        run_raw = env.get("GITHUB_RUN_ID", "")
        require(re.fullmatch(r"[1-9][0-9]{0,18}", run_raw) is not None, "ACTUAL_RUN_BINDING_REQUIRED")
        pr_number = None
        if local["event"] == "pull_request":
            pr_number = positive_id(event.get("number"), "PR_SOURCE_IDENTITY_DRIFT")
            require(event["pull_request"].get("number") == pr_number and
                    env.get("GITHUB_REF") == f"refs/pull/{pr_number}/merge", "PR_SOURCE_IDENTITY_DRIFT")
        self.actual = {"run_id": positive_id(int(run_raw), "ACTUAL_RUN_BINDING_REQUIRED"), "attempt": 1,
                       "event": local["event"], "event_head": local["C"] if pr_number else local["checkout"],
                       "checkout": local["checkout"], "event_pr_number": pr_number}
        baseline = strict_json(self.git.blob(local["checkout"], DOC_ROOT + "/EXECUTION_BASELINE.json") or b"")
        require(isinstance(baseline, dict) and isinstance(baseline.get("integration_base"), dict),
                "INTEGRATION_BASE_NOT_QUALIFIED")
        self.qualified_base = baseline["integration_base"]
        require(self.qualified_base.get("commit") == local["B"], "INTEGRATION_BASE_NOT_QUALIFIED")
        self.request_identity = {"route": 0, "role": local["event"], "run_id": self.actual["run_id"],
                                 "pr_number": pr_number, "C": local["C"] or None,
                                 "S": local["checkout"] if local["event"] == "push" else None,
                                 "comment_id": None}
        self.worker = OwnedHTTPWorker(self.scope, self.activity.collector_budget, self.ledger, output)
        self.activity.sync()

    @property
    def collector_budget(self) -> DurationBudget:
        return self.activity.collector_budget

    def _read(self, route: int) -> tuple[Any, dict[str, Any]]:
        require(self.worker is not None, "METADATA_WORKER_PARENT_REQUIRED")
        self.activity.sync()
        value, exchange = self.worker.request(self.request_identity | {"route": route})
        self.activity.sync()
        return value, exchange

    def _source_phase(self, post: bool) -> tuple[dict[str, Any], dict[str, Any]]:
        if self.actual["event"] == "push" and not post:
            require(self.request_identity["C"] is None and self.request_identity["pr_number"] is None,
                    "MAIN_C_DERIVATION_NOT_PROVIDER_BOUND")
        run, _ = self._read(10 if post else 1)
        validate_run(run, self.actual)
        if not post:
            jobs, exchange = self._read(2)
            self.job = validate_jobs(jobs, exchange["headers"], self.actual["run_id"])
            try:
                budget = bind_collector_budget(self.job, self.stage_monotonic_ns, self.stage_epoch_ns)
            except AdmissionError:
                self.activity.collector_budget = DurationBudget(self.stage_monotonic_ns, 0)
                assert self.worker is not None
                self.worker.collector_budget = self.activity.collector_budget
                raise
            self.activity.collector_budget = budget
            assert self.worker is not None
            self.worker.collector_budget = budget
            self.activity.sync()
        main_ref, _ = self._read(11 if post else 3)
        first, first_exchange = self._read(12 if post else 4)
        if self.actual["event"] == "push":
            association = validate_associations(first, first_exchange["headers"], role="push",
                                                 event_sha=self.actual["checkout"], event_pr_number=None)
            self.request_identity["pr_number"] = association["number"]
            pr, _ = self._read(13 if post else 5)
        else:
            pr = first
            # C comes from the actual event and is checked against the actual
            # PR; no freeze or CLI supplied C is read to select this route.
            second, second_exchange = self._read(13 if post else 5)
            association = validate_associations(second, second_exchange["headers"], role="pull_request",
                                                 event_sha=self.actual["event_head"],
                                                 event_pr_number=self.actual["event_pr_number"])
        require(isinstance(pr, dict) and isinstance(pr.get("base"), dict) and isinstance(pr.get("head"), dict),
                "PR_SOURCE_IDENTITY_DRIFT")
        b, c = oid(pr["base"].get("sha")), oid(pr["head"].get("sha"))
        graph = actual_source_graph(self.git, b, c, self.actual["checkout"])
        source = derive_actual_source(run, self.actual, pr, association, main_ref, graph,
                                      self.qualified_base, self.source if post else None)
        require(b == self.scope["actual_local_source"]["B"], "PROTECTED_POLICY_SOURCE_DRIFT")
        self.request_identity["C"] = source["C"]
        self.graph.update(graph)
        return run, source

    def _freeze_phase(self, source: dict[str, Any], post: bool) -> dict[str, Any]:
        require(self.closure is not None and self.closure.get("source_closed_before_freeze") is True,
                "EXECUTION_SOURCE_CLOSURE_INCOMPLETE")
        issue_before, _ = self._read(14 if post else 6)
        comments, exchange = self._read(15 if post else 7)
        selected = select_freeze(comments, exchange["headers"], issue_before, source,
                                  self.closure["document_hashes"])
        self.request_identity["comment_id"] = selected["comment"]["id"]
        direct, _ = self._read(16 if post else 8)
        issue_after, _ = self._read(17 if post else 9)
        return finish_freeze_checkpoint(selected, direct, issue_before, issue_after, self.freeze if post else None)

    def pre(self) -> dict[str, Any]:
        require(self.pre_receipt is None and self.ledger.next_route == 1, "API_REQUEST_BUDGET_EXCEEDED")
        try:
            _, self.source = self._source_phase(False)
            self.closure = actual_source_closure(self.git, self.root, self.source)
            self.freeze = self._freeze_phase(self.source, False)
            require(self.ledger.accounted_routes == set(range(1, 10)), "FREEZE_PRE_CHECKPOINT_INCOMPLETE")
            self.activity.end()
            self.pre_receipt = {"state": "PRE_ADMITTED_FOR_REGISTERED_FIXED_MATRIX_ONLY",
                                "source": self.source, "freeze": self.freeze, "source_closure": self.closure,
                                "actual_job": self.job, "scientific_result_complete": False,
                                "collector_budget": self.collector_budget.receipt()}
            return self.pre_receipt
        except BaseException as exc:
            self._deny(exc, "PRE")
            raise

    def post(self) -> dict[str, Any]:
        require(self.pre_receipt is not None and self.post_receipt is None and self.ledger.next_route == 10,
                "FREEZE_POST_CHECKPOINT_INCOMPLETE")
        self.activity.begin("POST")
        try:
            _, source = self._source_phase(True)
            require(source == self.source, "SOURCE_IDENTITY_CHANGED_AFTER_PRE")
            # Recheck all actual source payloads as well as provider lineage.
            closure = actual_source_closure(self.git, self.root, source)
            require(closure == self.closure, "SOURCE_IDENTITY_CHANGED_AFTER_PRE")
            freeze = self._freeze_phase(source, True)
            require(freeze == self.freeze, "FREEZE_CHANGED_AFTER_PRE")
            assert self.worker is not None
            self.worker.close()
            self.ledger.finish()
            # close() includes FD closure and diagnostic hash/hex capture.
            # The final phase cut is after that work, not before finalization.
            self.activity.end()
            self.post_validated = True
            self.post_receipt = {"state": "COMPLETE_PROVIDER_SOURCE_AND_FREEZE_CHECKPOINTS",
                                 "same_source": True, "same_freeze": True,
                                 "scientific_result_complete": False,
                                 "control_plane": self.control_receipt(),
                                 "collector_budget": self.collector_budget.receipt()}
            return self.post_receipt
        except BaseException as exc:
            self._deny(exc, "POST")
            raise

    def _deny(self, exc: BaseException, phase: str) -> None:
        self.post_validated = False
        self.failure = {"phase": phase, "reason": getattr(exc, "reason", type(exc).__name__),
                        "provider_freeze_admitted": False}
        try:
            self.abort()
        except BaseException as cleanup:
            self.failure["cleanup_denial"] = getattr(cleanup, "reason", type(cleanup).__name__)

    def abort(self) -> None:
        if self.activity.phase is None:
            self.activity.begin("DENIAL_CLEANUP")
        try:
            if self.worker is not None:
                self.worker.close()
        finally:
            self.activity.end()

    def control_receipt(self) -> dict[str, Any]:
        return {"request_count": self.ledger.next_route - 1,
                "request_count_role": "PARENT_ADMITTED_FIXED_GET_ATTEMPTS_NO_RETRY",
                "successful_operation_count": len(self.ledger.accounted_routes),
                "active_acquisition_ns": self.ledger.active_ns,
                "validation_and_finalization_ns": self.ledger.validation_ns,
                "raw_control_bytes": self.ledger.raw_bytes,
                "request_records": copy.deepcopy(self.ledger.request_records),
                "active_phases": copy.deepcopy(self.activity.phases),
                "helper": copy.deepcopy(self.worker.lifecycle) if self.worker is not None else None,
                "failed_operation": copy.deepcopy(self.worker.failed_operation) if self.worker is not None else None,
                "failure": copy.deepcopy(self.failure),
                "full_PRE_and_POST": self.post_validated and self.failure is None and
                                     self.ledger.accounted_routes == set(range(1, 18)) and self.ledger.helper_reaped}


def coordinator_metadata_self_test() -> dict[str, Any]:
    """Exercise real phase logic with typed in-memory provider/Git readers.

    __init__, OwnedHTTPWorker, Git process readers and source/DSP are never
    invoked. This observes parser/route order, not real transport lifecycle.
    """
    traces: list[dict[str, Any]] = []
    negatives: list[dict[str, str]] = []
    for role in ("pull_request", "push"):
        seed = provider_metadata_fixture(role)
        coordinator = ProviderAdmission.__new__(ProviderAdmission)
        coordinator.actual = copy.deepcopy(seed["actual"])
        coordinator.source = None
        coordinator.freeze = None
        coordinator.qualified_base = copy.deepcopy(seed["qualified_base"])
        coordinator.scope = {"actual_local_source": {"B": "1" * 40}}
        coordinator.graph = {}
        coordinator.stage_monotonic_ns = time.monotonic_ns()
        coordinator.stage_epoch_ns = utc_ns(seed["run"]["created_at"])
        coordinator.ledger = AcquisitionLedger()
        coordinator.activity = AdmissionActivity(coordinator.ledger, DurationBudget(coordinator.stage_monotonic_ns, 600_000_000_000))
        coordinator.activity.begin("OFFLINE_METADATA_PHASE_MODEL")
        coordinator.request_identity = {"route": 0, "role": role, "run_id": 42,
                                        "pr_number": 123 if role == "pull_request" else None,
                                        "C": "2" * 40 if role == "pull_request" else None,
                                        "S": "4" * 40 if role == "push" else None, "comment_id": None}
        class TypedGitModel:
            def commit(self, commit: str) -> tuple[str, tuple[str, ...]]:
                value = seed["graph"][commit]
                return value["tree"], tuple(value["parents"])
        class UnstartedWorkerModel:
            collector_budget = coordinator.activity.collector_budget
        coordinator.git = TypedGitModel()
        coordinator.worker = UnstartedWorkerModel()
        requested: list[dict[str, Any]] = []
        mapping = {1: "run", 2: "jobs", 3: "main_ref", 6: "issue_before", 7: "comments", 8: "direct", 9: "issue_after",
                   10: "run", 11: "main_ref", 14: "issue_before", 15: "comments", 16: "direct", 17: "issue_after"}
        mapping.update({4: "pr" if role == "pull_request" else "associations", 5: "associations" if role == "pull_request" else "pr",
                        12: "pr" if role == "pull_request" else "associations", 13: "associations" if role == "pull_request" else "pr"})
        def read_model(route: int) -> tuple[Any, dict[str, Any]]:
            request = coordinator.request_identity | {"route": route}
            requested.append({"route": route, "url": api_route_url(request), "C_before_read": request["C"]})
            if route in (6, 7, 8, 9, 14, 15, 16, 17):
                require(coordinator.source == seed["source"], "SELF_TEST_SOURCE_BEFORE_FREEZE")
            return copy.deepcopy(seed[mapping[route]]), {"headers": {}}
        coordinator._read = read_model
        if role == "push":
            coordinator.request_identity["C"] = "2" * 40
            try:
                coordinator._source_phase(False)
            except AdmissionError as exc:
                require(exc.reason == "MAIN_C_DERIVATION_NOT_PROVIDER_BOUND" and not requested,
                        "SELF_TEST_WRONG_DENIAL")
            else:
                raise AdmissionError("SELF_TEST_DID_NOT_REJECT", "push_self_declared_C")
            negatives.append({"name": "push_self_declared_C", "actual_reason": "MAIN_C_DERIVATION_NOT_PROVIDER_BOUND"})
            coordinator.request_identity["C"] = None
        _, coordinator.source = coordinator._source_phase(False)
        coordinator.closure = {"source_closed_before_freeze": True, "document_hashes": seed["documents"]}
        coordinator.freeze = coordinator._freeze_phase(coordinator.source, False)
        _, post_source = coordinator._source_phase(True)
        post_freeze = coordinator._freeze_phase(post_source, True)
        require(post_source == coordinator.source and post_freeze == coordinator.freeze and
                [row["route"] for row in requested] == list(range(1, 18)), "SELF_TEST_COORDINATOR_ROUTE_ORDER")
        coordinator.activity.end()
        traces.append({"role": role, "modeled_routes": requested,
                       "actual_HTTP_requests": 0, "actual_subprocess_starts": 0,
                       "source_derived_before_first_comment_read": True})
    return {"fixture_role": "OFFLINE_COORDINATOR_METHOD_MODEL_ONLY", "traces": traces,
            "negative_cases": negatives, "real_transport_or_kill_wait_tested": False}


def source_closure_metadata_fixture() -> dict[str, Any]:
    """Typed, nonempty metadata model; these bytes are never compiled/imported."""
    original = {f"offline_original/input_{index:02d}.c": source_row(
        f"offline_original/input_{index:02d}.c", f"ORIGINAL_MODEL_{index}\n".encode()) for index in range(88)}
    programs = {"tests/validation/frontend_evolution/" + name: ("OFFLINE_MODEL_" + name + "\n").encode()
                for name in SOURCE_FILES}
    implementation = {path: source_row(path, raw) for path, raw in programs.items()}
    implementation.update({path: source_row(path, ("OFFLINE_HOOK_MODEL_" + path).encode()) for path in HOOKS})
    lock = {"id": IDENTITY, "original_baseline": SCIENTIFIC_BASE, "original_comparison_commit": ORIGINAL_COMPARISON,
            "known_immutable_file_count": 88, "known_immutable_files": list(original.values()),
            "pending_implementation_files": [implementation[path] for path in programs],
            "pending_hookup_files": [implementation[path] for path in HOOKS],
            "source_self_reference_policy": {"own_member_digest_omitted": True,
                                             "containing_execution_commit_not_embedded": True,
                                             "future_comment_identity_not_embedded": True},
            "execution_admitted_by_this_file": False,
            "original_direct_translation_units": list(original)[:20],
            "original_included_translation_unit": list(original)[20],
            "generated_header_requirement": {"bytes": "OFFLINE_MODEL_ONLY"}}
    guard = implementation[GUARD]
    base = {"status": "QUALIFIED_PROTECTED_BASE_WITH_GUARD", "commit": "1" * 40, "tree": "a" * 40,
            "verify_run_id": 1, "verify_attempt": 1, "required_summary_job_id": 2,
            "release_run_id": 3, "release_attempt": 1, "release_job_id": 4, "convergence_job_id": 5,
            "protected_guard_path": GUARD, "protected_guard_mode": "100644", "protected_guard_blob": guard["git_blob_sha1"],
            "protected_guard_bytes": guard["bytes"], "protected_guard_sha256": guard["sha256"],
            "root_independent_main_closure_report_sha256": "c" * 64,
            "all_fields_complete_before_final_C_required": True}
    baseline = {"id": IDENTITY, "source_baseline": SCIENTIFIC_BASE, "status": "OFFLINE_SOURCE_CLOSURE_MODEL",
                "integration_base": base, "candidate_source_identity": {
                    "location": "external issue847 freeze and runtime provider/Git observations only",
                    "C_or_tree_embedded_in_this_file": False, "future_comment_ID_or_body_hash_embedded": False,
                    "document_alone_authorizes_execution": False}}
    contract = {"id": IDENTITY, **{field: {"offline_scientific_field": field} for field in SCIENCE_FIELDS}}
    def encoded(value: Any) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    documents = {"README.md": b"OFFLINE_SOURCE_METADATA_MODEL_ONLY\n", "source-lock.json": encoded(lock),
                 "EXECUTION_BASELINE.json": encoded(baseline), "test-contract.json": encoded(contract),
                 "ADMISSION_NEGATIVE_CONTROLS.json": b'{"role":"OFFLINE_MODEL_ONLY"}'}
    return {"OFFLINE_METADATA_FIXTURE_ONLY": True, "documents": documents, "protected_documents": copy.deepcopy(documents),
            "candidate": "e" * 40, "original": original, "implementation": implementation,
            "protected_guard": copy.deepcopy(guard), "actual_guard": programs[GUARD], "locked_programs": programs}


def validate_source_fixture(seed: dict[str, Any]) -> dict[str, Any]:
    require(seed.get("OFFLINE_METADATA_FIXTURE_ONLY") is True, "SELF_TEST_FIXTURE_ROLE")
    return validate_source_documents(*(seed[key] for key in (
        "documents", "protected_documents", "candidate", "original", "implementation", "protected_guard",
        "actual_guard", "locked_programs")))


def source_closure_metadata_self_test() -> dict[str, Any]:
    seed = source_closure_metadata_fixture()
    valid = validate_source_fixture(seed)
    require(valid["source_closed_before_freeze"] is True and valid["scientific_execution_admitted"] is False,
            "SELF_TEST_SOURCE_CLOSURE_SEED")
    completed: list[dict[str, str]] = []
    def reject(name: str, reason: str, changed: dict[str, Any]) -> None:
        try:
            validate_source_fixture(changed)
        except AdmissionError as exc:
            require(exc.reason == reason, "SELF_TEST_WRONG_DENIAL", name + ":" + exc.reason)
        else:
            raise AdmissionError("SELF_TEST_DID_NOT_REJECT", name)
        completed.append({"name": name, "actual_reason": reason})
    def document_change(changed: dict[str, Any], name: str, action: Any) -> None:
        value = strict_json(changed["documents"][name])
        action(value)
        changed["documents"][name] = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    for name, key, value, reason in (
        ("candidate_guard_used_as_authority", "actual_guard", b"CANDIDATE_DIFFERENT_GUARD", "PROTECTED_POLICY_SOURCE_DRIFT"),
        ("guard_mode_symlink", "mode", "120000", "PROTECTED_POLICY_MODE_DRIFT"),
        ("guard_blob_changed", "git_blob_sha1", "f" * 40, "PROTECTED_POLICY_SOURCE_DRIFT"),
    ):
        changed = copy.deepcopy(seed)
        if key == "actual_guard":
            changed[key] = value
        else:
            changed["protected_guard"][key] = value
        reject(name, reason, changed)
    changed = copy.deepcopy(seed)
    changed["locked_programs"][GUARD] += b"C_BYTE_CHANGED\n"
    changed["implementation"][GUARD] = source_row(GUARD, changed["locked_programs"][GUARD])
    document_change(changed, "source-lock.json", lambda lock: lock.update(
        pending_implementation_files=[changed["implementation"][row["path"]] for row in lock["pending_implementation_files"]]))
    reject("C_guard_differs_B", "PROTECTED_POLICY_SOURCE_DRIFT", changed)
    changed = copy.deepcopy(seed)
    path = next(iter(changed["original"]))
    changed["original"][path] = source_row(path, b"ALTERED_ORIGINAL_BYTE_AND_RESEALED_C")
    document_change(changed, "source-lock.json", lambda lock: lock.update(known_immutable_files=list(changed["original"].values())))
    reject("original_source_byte_changed", "IMMUTABLE_SCIENTIFIC_SOURCE_DRIFT", changed)
    changed = copy.deepcopy(seed)
    changed["implementation"]["unregistered_extra_TU.c"] = source_row("unregistered_extra_TU.c", b"EXTRA_SOURCE")
    reject("unlocked_new_source", "EXECUTION_SOURCE_CLOSURE_INCOMPLETE", changed)
    changed = copy.deepcopy(seed)
    document_change(changed, "source-lock.json", lambda lock: lock["pending_implementation_files"][0].update(bytes=None))
    reject("pending_lock_row", "EXECUTION_SOURCE_CLOSURE_INCOMPLETE", changed)
    changed = copy.deepcopy(seed)
    document_change(changed, "source-lock.json", lambda lock: lock.update(source_lock_sha256="f" * 64))
    reject("source_lock_self_hash", "SOURCE_FREEZE_SELF_REFERENCE", changed)
    changed = copy.deepcopy(seed)
    changed["locked_programs"][GUARD] += hashlib.sha256(changed["documents"]["source-lock.json"]).hexdigest().encode()
    reject("verifier_embeds_lock_hash", "SOURCE_FREEZE_SELF_REFERENCE", changed)
    changed = copy.deepcopy(seed)
    document_change(changed, "EXECUTION_BASELINE.json", lambda baseline: baseline.update(future_comment_id=123456))
    reject("future_comment_embedded", "SOURCE_FREEZE_SELF_REFERENCE", changed)
    return {"negative_cases": completed, "fixture_role": "OFFLINE_SOURCE_CLOSURE_METADATA_MODEL_ONLY",
            "actual_source_compilations": 0, "network_requests": 0, "subprocess_starts": 0}


def transport_metadata_self_test() -> dict[str, Any]:
    """Pure nonempty metadata traces, never real DNS, HTTP, timeout or kill."""
    completed: list[dict[str, str]] = []
    def reject(name: str, reason: str, action: Any) -> None:
        try:
            action()
        except AdmissionError as exc:
            require(exc.reason == reason, "SELF_TEST_WRONG_DENIAL", name + ":" + exc.reason)
        else:
            raise AdmissionError("SELF_TEST_DID_NOT_REJECT", name)
        completed.append({"name": name, "actual_reason": reason})

    request = {"route": 1, "role": "pull_request", "run_id": 42, "pr_number": 123,
               "C": "2" * 40, "S": "3" * 40, "comment_id": 789}
    url = api_route_url(request)
    body = b'{"nonempty_offline_trace":true}'
    exchange = {"url": url, "method": "GET", "status": 200, "headers": {}, "complete": True,
                "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest()}
    require(validate_api_exchange(1, body, exchange, url) == {"nonempty_offline_trace": True},
            "SELF_TEST_TRANSPORT_SEED")
    for name, reason, changes in (
        ("wrong_HTTP_host", "API_ROUTE_NOT_REGISTERED", {"url": "https://invalid.example/run"}),
        ("wrong_HTTP_method", "API_ROUTE_NOT_REGISTERED", {"method": "POST"}),
        ("redirect_response", "API_RESPONSE_NOT_ADMITTED", {"status": 302}),
        ("non200_response", "API_RESPONSE_NOT_ADMITTED", {"status": 403}),
        ("unexpected_encoding", "API_RESPONSE_NOT_ADMITTED", {"headers": {"content-encoding": "gzip"}}),
    ):
        reject(name, reason, lambda changes=changes: validate_api_exchange(1, body, exchange | changes, url))
    reject("body_cap_plus_one", "API_BODY_BOUND_EXCEEDED", lambda:
           validate_api_exchange(1, b"x" * (API_BODY_CAPS[0] + 1), exchange, url))
    pending = AcquisitionLedger()
    pending.admit_start(1)
    reject("exchange_cap_plus_one", "API_EXCHANGE_BOUND_EXCEEDED", lambda:
           pending.account(1, len(body), 16385, 1_000_000))
    reject("metadata_total_plus_one", "CONTROL_EVIDENCE_BOUND_EXCEEDED", lambda:
           validate_control_bytes(CONTROL_BYTES + 1))
    timing = {"start_monotonic_ns": 10**18 + 123, "admitted_duration_ns": COMMAND_NS,
              "whole_operation_elapsed_ns": COMMAND_NS}
    validate_operation_observation(timing)
    for name in ("DNS_whole_operation_timeout", "slow_body_whole_operation_timeout"):
        reject(name, "API_WHOLE_OPERATION_TIMEOUT", lambda:
               validate_operation_observation(timing | {"whole_operation_elapsed_ns": COMMAND_NS + 1}))

    def ledger_through(count: int, duration: int = 1_000_000) -> AcquisitionLedger:
        result = AcquisitionLedger()
        result.start_helper()
        for route in range(1, count + 1):
            result.admit_start(route)
            result.account(route, len(body), 512, duration)
        return result
    exhausted = ledger_through(12, COMMAND_NS)
    reject("aggregate_sixty_plus", "API_AGGREGATE_BUDGET_EXCEEDED", lambda: exhausted.admit_start(13))
    reset = ledger_through(9)
    reset.active_ns = 0
    reject("phase_budget_reset", "API_BUDGET_ACCOUNTING_DRIFT", lambda: reset.admit_start(10))
    complete = ledger_through(17)
    reject("eighteenth_request", "API_REQUEST_BUDGET_EXCEEDED", lambda: complete.admit_start(18))
    reject("helper_restart", "METADATA_HELPER_RETRY_NOT_ALLOWED", complete.start_helper)
    reject("helper_unreaped", "METADATA_HELPER_LIFECYCLE_INCOMPLETE", complete.finish)
    complete.helper_reaped = True
    complete.finish()
    incomplete = ledger_through(9)
    reject("POST_old_ID_only", "FREEZE_POST_CHECKPOINT_INCOMPLETE", incomplete.finish)
    for role in ("pull_request", "push"):
        urls = [api_route_url(request | {"role": role, "route": route}) for route in range(1, 18)]
        require(len(urls) == 17 and all(item.startswith(API_PREFIX) for item in urls),
                "SELF_TEST_REGISTERED_ROUTES")
        require("actions/runs/42/attempts/1/jobs?per_page=100&page=1" in urls[1] and
                urls[5] == urls[8] == urls[13] == urls[16] == ISSUE_URL and
                urls[6] == urls[14] and urls[7] == urls[15], "SELF_TEST_REGISTERED_ROUTES")
    return {"negative_cases": completed, "fixture_role": "OFFLINE_PARENT_TRACE_MODEL_ONLY",
            "actual_HTTP_requests": 0, "actual_helper_starts": 0,
            "real_transport_or_kill_wait_tested": False}


def provider_metadata_fixture(role: str = "pull_request") -> dict[str, Any]:
    """Nonempty typed offline fixture; none of these objects are live evidence."""
    repository = {"id": REPOSITORY_ID, "full_name": REPOSITORY}
    user = {"id": AUTHOR_ID, "login": "jiying2007", "type": "User"}
    b, c, m, s = (letter * 40 for letter in "1234")
    checkout = m if role == "pull_request" else s
    actual = {"run_id": 42, "attempt": 1, "event": role,
              "event_head": c if role == "pull_request" else s,
              "checkout": checkout, "event_pr_number": 123 if role == "pull_request" else None}
    run = {"id": 42, "run_attempt": 1, "event": role, "head_sha": actual["event_head"],
           "head_branch": BRANCH if role == "pull_request" else "main",
           "repository": copy.deepcopy(repository), "head_repository": copy.deepcopy(repository),
           "path": ".github/workflows/verify.yml", "name": "Verify", "status": "in_progress",
           "conclusion": None, "created_at": "2026-10-25T00:00:01Z"}
    pr = {"id": 456, "number": 123, "draft": False, "state": "open" if role == "pull_request" else "closed",
          "merged": role == "push", "merged_at": None if role == "pull_request" else "2026-10-25T00:00:00Z",
          "merge_commit_sha": checkout, "user": copy.deepcopy(user),
          "head": {"ref": BRANCH, "sha": c, "repo": copy.deepcopy(repository)},
          "base": {"ref": "main", "sha": b, "repo": copy.deepcopy(repository)}}
    graph = {b: {"tree": "a" * 40, "parents": []}, c: {"tree": "b" * 40, "parents": [b]},
             m: {"tree": "b" * 40, "parents": [b, c]}, s: {"tree": "b" * 40, "parents": [b]}}
    qualified = {"status": "QUALIFIED_PROTECTED_BASE_WITH_GUARD", "commit": b, "tree": "a" * 40}
    main_ref = {"ref": "refs/heads/main", "object": {"type": "commit", "sha": b if role == "pull_request" else s}}
    association = copy.deepcopy(pr)
    source = derive_actual_source(run, actual, pr, association, main_ref, graph, qualified)
    documents = {key: hashlib.sha256(("OFFLINE METADATA FIXTURE / " + name).encode()).hexdigest()
                 for key, name in FREEZE_DOC_FIELDS.items()}
    payload = copy.deepcopy(FREEZE_CONSTANTS)
    payload.update({"integration_base_sha": b, "integration_base_tree": "a" * 40,
                    "candidate_sha": c, "candidate_tree": "b" * 40,
                    "independent_review_report_sha256": hashlib.sha256(b"OFFLINE REVIEW FIXTURE").hexdigest(),
                    **documents})
    comment = {"id": 789, "issue_url": ISSUE_URL, "user": copy.deepcopy(user),
               "created_at": "2026-10-24T23:59:50Z", "updated_at": "2026-10-24T23:59:50Z",
               "body": json.dumps(payload, sort_keys=True)}
    issue = {"number": ISSUE_NUMBER, "id": ISSUE_ID, "node_id": ISSUE_NODE, "url": ISSUE_URL,
             "repository_url": API_PREFIX.rstrip("/"), "created_at": ISSUE_CREATED,
             "user": copy.deepcopy(user), "state": "open", "comments": 1}
    jobs = {"total_count": 2, "jobs": [
        {"id": 101, "run_id": 42, "name": "quality / frontend-s3-t3s2b1ba3",
         "steps": [{"number": 1, "name": "Set up job", "started_at": "2026-10-25T00:00:02Z"},
                   {"number": 2, "name": "Checkout", "started_at": "2026-10-25T00:00:03Z"}]},
        {"id": 102, "run_id": 42, "name": "unrelated-metadata-fixture", "steps": []}]}
    return {"OFFLINE_METADATA_FIXTURE_ONLY": True, "actual": actual, "run": run, "pr": pr,
            "associations": [association], "main_ref": main_ref, "graph": graph,
            "qualified_base": qualified, "source": source, "documents": documents,
            "payload": payload, "comments": [comment], "direct": copy.deepcopy(comment),
            "issue_before": issue, "issue_after": copy.deepcopy(issue), "headers": {}, "jobs": jobs}


def fixture_source(seed: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    association = validate_associations(seed["associations"], seed["headers"], role=seed["actual"]["event"],
                                         event_sha=seed["actual"]["event_head"],
                                         event_pr_number=seed["actual"].get("event_pr_number"))
    return derive_actual_source(seed["run"], seed["actual"], seed["pr"], association,
                                seed["main_ref"], seed["graph"], seed["qualified_base"], previous)


def fixture_freeze(seed: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = select_freeze(seed["comments"], seed["headers"], seed["issue_before"],
                             seed["source"], seed["documents"])
    return finish_freeze_checkpoint(selected, seed["direct"], seed["issue_before"],
                                     seed["issue_after"], previous)


def provider_metadata_self_test() -> dict[str, Any]:
    """Finite original-byte/typed-object controls; no process, HTTP or DSP."""
    seed = provider_metadata_fixture()
    completed: list[dict[str, str]] = []
    positives: list[str] = []
    first = fixture_freeze(seed)
    require(fixture_source(seed) == seed["source"], "SELF_TEST_PROVIDER_POSITIVE")
    require(fixture_freeze(seed, first) == first, "SELF_TEST_PROVIDER_POSITIVE")
    positives.append("ADMP01")
    main = provider_metadata_fixture("push")
    require(fixture_source(main) == main["source"] and fixture_freeze(main)["complete_checkpoint"],
            "SELF_TEST_PROVIDER_POSITIVE")
    positives.append("ADMP02")
    ordinary = copy.deepcopy(seed)
    ordinary["comments"].append({"id": 790, "issue_url": ISSUE_URL, "body": "Ordinary offline discussion fixture."})
    ordinary["issue_before"]["comments"] = ordinary["issue_after"]["comments"] = 2
    require(fixture_freeze(ordinary, first) == first, "SELF_TEST_PROVIDER_POSITIVE")
    positives.append("ADMP06")

    def reject(name: str, reason: str, subject: dict[str, Any], check: Any) -> None:
        require(subject.get("OFFLINE_METADATA_FIXTURE_ONLY") is True, "SELF_TEST_FIXTURE_LABEL_REQUIRED")
        try:
            check(subject)
        except AdmissionError as exc:
            require(exc.reason == reason, "SELF_TEST_WRONG_DENIAL", name + ":" + exc.reason)
        else:
            raise AdmissionError("SELF_TEST_DID_NOT_REJECT", name)
        completed.append({"name": name, "expected_reason": reason, "actual_reason": reason})

    def mutate(path: tuple[Any, ...], value: Any, original: dict[str, Any] = seed) -> dict[str, Any]:
        result = copy.deepcopy(original)
        target: Any = result
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return result

    source_cases = [
        ("wrong_event", "EVENT_NOT_REGISTERED", ("run", "event"), "workflow_dispatch"),
        ("attempt2", "RUN_ATTEMPT_NOT_REGISTERED", ("run", "run_attempt"), 2),
        ("run_head_mismatch", "RUN_HEAD_BINDING_DRIFT", ("run", "head_sha"), "9" * 40),
        ("wrong_run_repo", "REPOSITORY_IDENTITY_DRIFT", ("run", "repository", "id"), REPOSITORY_ID + 1),
        ("wrong_main_pre", "PROTECTED_MAIN_REF_DRIFT", ("main_ref", "object", "sha"), "9" * 40),
        ("PR_is_draft", "PR_SOURCE_IDENTITY_DRIFT", ("pr", "draft"), True),
        ("PR_is_fork", "PR_SOURCE_IDENTITY_DRIFT", ("pr", "head", "repo", "id"), REPOSITORY_ID + 1),
        ("PR_base_not_main", "PR_SOURCE_IDENTITY_DRIFT", ("pr", "base", "ref"), "other"),
        ("PR_base_not_closed_B", "INTEGRATION_BASE_NOT_QUALIFIED", ("qualified_base", "commit"), "9" * 40),
        ("M_wrong_parents", "PR_TEST_MERGE_RELATION_DRIFT", ("graph", "3" * 40, "parents"), ["2" * 40, "1" * 40]),
        ("M_tree_not_C", "EXECUTION_TREE_NOT_REVIEWED_C", ("graph", "3" * 40, "tree"), "e" * 40),
        ("C_not_descendant_B", "C_BASE_ANCESTRY_DRIFT", ("graph", "2" * 40, "parents"), []),
    ]
    for name, reason, path, value in source_cases:
        reject(name, reason, mutate(path, value), fixture_source)
    for name, reason, path, value in (
        ("S_wrong_parent", "MAIN_SQUASH_PARENT_DRIFT", ("graph", "4" * 40, "parents"), ["1" * 40, "2" * 40]),
        ("S_tree_not_C", "EXECUTION_TREE_NOT_REVIEWED_C", ("graph", "4" * 40, "tree"), "e" * 40),
        ("merged_after_run", "MERGE_RUN_ORDER_INVALID", ("pr", "merged_at"), "2026-10-25T00:00:02Z"),
        ("wrong_merge_commit", "MAIN_C_DERIVATION_NOT_PROVIDER_BOUND", ("pr", "merge_commit_sha"), "9" * 40),
    ):
        reject(name, reason, mutate(path, value, main), fixture_source)
    reject("associated_PR_missing", "ASSOCIATED_PR_NOT_UNIQUE", mutate(("associations",), [], main), fixture_source)
    duplicate = copy.deepcopy(main); duplicate["associations"].append(copy.deepcopy(duplicate["associations"][0])); duplicate["associations"][1]["id"] += 1
    reject("associated_PR_duplicate", "ASSOCIATED_PR_NOT_UNIQUE", duplicate, fixture_source)
    full = copy.deepcopy(main); full["associations"] *= 100
    reject("associated_page_full", "ASSOCIATED_PR_LIST_INCOMPLETE", full, fixture_source)
    reject("wrong_main_post", "PROTECTED_MAIN_REF_DRIFT", mutate(("main_ref", "object", "sha"), "9" * 40),
           lambda x: fixture_source(x, seed["source"]))
    reject("PR_head_changed", "SOURCE_IDENTITY_CHANGED_AFTER_PRE", mutate(("pr", "head", "sha"), "9" * 40),
           lambda x: fixture_source(x, seed["source"]))

    for name, reason, path, value in (
        ("wrong_issue_number", "REGISTRATION_ISSUE_IDENTITY_DRIFT", ("issue_before", "number"), 848),
        ("wrong_issue_id", "REGISTRATION_ISSUE_IDENTITY_DRIFT", ("issue_before", "id"), ISSUE_ID + 1),
        ("wrong_issue_node", "REGISTRATION_ISSUE_IDENTITY_DRIFT", ("issue_before", "node_id"), "other"),
        ("wrong_issue_owner", "REGISTRATION_ISSUE_IDENTITY_DRIFT", ("issue_before", "user", "id"), AUTHOR_ID + 1),
        ("closed_issue", "REGISTRATION_ISSUE_NOT_OPEN", ("issue_before", "state"), "closed"),
        ("comment_list_paginated", "FREEZE_COMMENT_LIST_INCOMPLETE", ("headers", "Link"), '<https://api.github.com/repos/jiying2007/audio-pipeline/issues/847/comments?page=2>; rel="next"'),
        ("comment_count_mismatch", "FREEZE_COMMENT_LIST_INCOMPLETE", ("issue_before", "comments"), 2),
        ("comment_count_changed_within_checkpoint", "FREEZE_COMMENT_CHECKPOINT_RACE", ("issue_after", "comments"), 2),
        ("comment_count_bool", "STRICT_METADATA_SCHEMA_DRIFT", ("issue_before", "comments"), True),
        ("wrong_freeze_author_login", "FREEZE_AUTHOR_IDENTITY_DRIFT", ("comments", 0, "user", "login"), "other"),
        ("wrong_freeze_author_ID", "FREEZE_AUTHOR_IDENTITY_DRIFT", ("comments", 0, "user", "id"), AUTHOR_ID + 1),
        ("wrong_freeze_author_type", "FREEZE_AUTHOR_IDENTITY_DRIFT", ("comments", 0, "user", "type"), "Bot"),
        ("freeze_edited", "FREEZE_COMMENT_EDITED", ("comments", 0, "updated_at"), "2026-10-24T23:59:51Z"),
        ("freeze_wrong_issue_URL", "FREEZE_COMMENT_ISSUE_DRIFT", ("comments", 0, "issue_url"), API_PREFIX + 'issues/848'),
        ("direct_list_body_mismatch", "FREEZE_DIRECT_LIST_MISMATCH", ("direct", "body"), '{}'),
    ):
        reject(name, reason, mutate(path, value), fixture_freeze)
    for name, when in (("freeze_created_at_run_second", "2026-10-25T00:00:01Z"),
                       ("freeze_created_after_run", "2026-10-25T00:00:02Z")):
        test = mutate(("comments", 0, "created_at"), when); test["comments"][0]["updated_at"] = when
        reject(name, "FREEZE_NOT_BEFORE_RUN", test, fixture_freeze)
    dup = copy.deepcopy(seed); dup["comments"] *= 2; dup["issue_before"]["comments"] = dup["issue_after"]["comments"] = 2
    reject("comment_duplicate_ID", "FREEZE_COMMENT_LIST_INVALID", dup, fixture_freeze)
    dup["comments"] = [copy.deepcopy(seed["comments"][0]), copy.deepcopy(seed["comments"][0])]; dup["comments"][1]["id"] = 790
    reject("two_matching_C_freezes", "FREEZE_FOR_ACTUAL_C_NOT_UNIQUE", dup, fixture_freeze)
    reject("POST_new_duplicate", "FREEZE_FOR_ACTUAL_C_NOT_UNIQUE", dup, lambda x: fixture_freeze(x, first))
    for name, reason, change in (
        ("no_matching_C_freeze", "FREEZE_FOR_ACTUAL_C_NOT_UNIQUE", {"candidate_sha": "9" * 40}),
        ("freeze_unknown_field", "FREEZE_SCHEMA_DRIFT", {"extra": "unknown"}),
        ("freeze_bool_integer", "FREEZE_SCHEMA_DRIFT", {"repository_id": True}),
        ("freeze_short_or_upper_hash", "FREEZE_SCHEMA_DRIFT", {"candidate_sha": "A" * 40}),
        ("freeze_wrong_tree", "FREEZE_SOURCE_IDENTITY_DRIFT", {"candidate_tree": "e" * 40}),
        ("freeze_wrong_lock", "FREEZE_SOURCE_IDENTITY_DRIFT", {"source_lock_sha256": "e" * 64}),
        ("freeze_wrong_contract", "FREEZE_SOURCE_IDENTITY_DRIFT", {"test_contract_sha256": "e" * 64}),
    ):
        test = copy.deepcopy(seed); body = dict(test["payload"], **change); test["comments"][0]["body"] = json.dumps(body)
        reject(name, reason, test, fixture_freeze)
    original_body = seed["comments"][0]["body"]
    for name, body in (
        ("freeze_markdown_fence", "```json\n" + original_body + "\n```"),
        ("freeze_duplicate_key", original_body[:-1] + ', "candidate_sha":"' + seed["source"]["C"] + '"}'),
        ("freeze_nonfinite", original_body[:-1] + ', "nonfinite": NaN}'),
    ):
        reject(name, "FREEZE_JSON_NOT_STRICT", mutate(("comments", 0, "body"), body), fixture_freeze)
    missing = copy.deepcopy(seed); missing["comments"] = []; missing["issue_before"]["comments"] = missing["issue_after"]["comments"] = 0
    reject("POST_missing_freeze", "FREEZE_FOR_ACTUAL_C_NOT_UNIQUE", missing, lambda x: fixture_freeze(x, first))
    recreated = copy.deepcopy(seed); recreated["comments"][0]["id"] = recreated["direct"]["id"] = 790
    reject("POST_recreated_comment", "FREEZE_CHANGED_AFTER_PRE", recreated, lambda x: fixture_freeze(x, first))
    changed = copy.deepcopy(seed); changed["comments"][0]["body"] += "\n"; changed["direct"]["body"] += "\n"
    reject("POST_body_changed", "FREEZE_CHANGED_AFTER_PRE", changed, lambda x: fixture_freeze(x, first))

    job = validate_jobs(seed["jobs"], {}, seed["actual"]["run_id"])
    require(job["earliest_step_epoch_ns"] == utc_ns("2026-10-25T00:00:02Z"), "SELF_TEST_JOB_DEADLINE")
    for name, reason, path, value in (
        ("jobs_incomplete", "ACTUAL_JOBS_PAGE_INCOMPLETE", ("jobs", "total_count"), 3),
        ("wrong_job_selector", "ACTUAL_A3_JOB_NOT_UNIQUE", ("jobs", "jobs", 0, "name"), "quality / frontend-rss-f1"),
        ("duplicate_A3_job", "ACTUAL_A3_JOB_NOT_UNIQUE", ("jobs", "jobs", 1, "name"), "frontend-s3-t3s2b1ba3"),
        ("missing_earliest_step", "ORIGINAL_JOB_DEADLINE_UNPROVEN", ("jobs", "jobs", 0, "steps"), []),
    ):
        reject(name, reason, mutate(path, value), lambda x: validate_jobs(x["jobs"], {}, x["actual"]["run_id"]))
    reject("nonpositive_enclosing_budget", "A3_ENCLOSING_BUDGET_EXHAUSTED", seed,
           lambda unused: bind_collector_budget(job, 10**18, job["original_job_deadline_epoch_ns"] - 300_000_000_000))
    return {"negative_cases": completed, "positive_cases": positives,
            "fixture_role": "OFFLINE_TYPED_METADATA_ONLY_NOT_PROVIDER_EVIDENCE",
            "network_requests": 0, "subprocess_starts": 0, "scientific_C_target_starts": 0,
            "DSP_frames": 0, "registered117_controls_complete": False}


def self_test() -> dict[str, Any]:
    """Pure metadata cases: no Git process, HTTP, filesystem fixture or C code."""
    count = 0
    def rejects(reason: str, action: Any) -> None:
        nonlocal count
        try:
            action()
        except AdmissionError as exc:
            require(exc.reason == reason, "SELF_TEST_WRONG_DENIAL", exc.reason)
        else:
            raise AdmissionError("SELF_TEST_DID_NOT_REJECT", reason)
        count += 1
    for raw, reason in ((b'{"a":1,"a":2}', "JSON_DUPLICATE_KEY"),
                        (b'{"a":NaN}', "JSON_NONFINITE_NUMBER"),
                        (b'{"a":Infinity}', "JSON_NONFINITE_NUMBER"),
                        (b'\xff', "JSON_INVALID")):
        rejects(reason, lambda raw=raw: strict_json(raw))
    for bad in ("../x", "/x", "a//b", "a/./b", "a\\b", "a\nx"):
        rejects("SOURCE_PATH_INVALID", lambda bad=bad: safe_path(bad))
    for bad in ("A" * 40, "a" * 39, True, None):
        rejects("GIT_OBJECT_ID_INVALID", lambda bad=bad: oid(bad))
    source = {"event": "pull_request", "head_ref": BRANCH, "B": "1" * 40,
              "C": "2" * 40, "checkout": "3" * 40}
    changed = (DOC_ROOT + "/test-contract.json",)
    require(classify_scope(source, None, b"candidate", changed, False, False) == BOOTSTRAP,
            "SELF_TEST_BOOTSTRAP")
    pushed = dict(source, event="push", C="", head_ref="")
    require(classify_scope(pushed, None, b"candidate", changed, False, False) == BOOTSTRAP,
            "SELF_TEST_BOOTSTRAP")
    count += 2
    for candidate in (None, b"changed"):
        rejects("PROTECTED_POLICY_SOURCE_DRIFT", lambda candidate=candidate:
                classify_scope(source, b"base", candidate, changed, True, True))
    rejects("A3_OWNED_CI_FRAGMENT_DRIFT", lambda:
            classify_scope(source, b"base", b"base", changed, False, True))
    rejects("A3_SCOPE_OUTSIDE_REGISTERED_BRANCH", lambda:
            classify_scope(dict(source, head_ref="other"), b"base", b"base", changed, True, True))
    for role in (source, pushed):
        rejects("A3_SOURCE_NOT_READY", lambda role=role:
                classify_scope(role, b"base", b"base", changed, True, False))
        require(classify_scope(role, b"base", b"base", changed, True, True) == REQUIRED,
                "SELF_TEST_REQUIRED")
        require(classify_scope(role, b"base", b"base", ("README.md",), True, False) == UNRELATED,
                "SELF_TEST_UNRELATED")
        count += 2
    budget = DurationBudget(10**18 + 123, 600_000_000_000)
    require(budget.remaining_ns(10**18 + 124) == 599_999_999_999 and
            budget.receipt(10**18 + 124)["admitted_duration_ns"] == 600_000_000_000,
            "SELF_TEST_INTEGER_BUDGET")
    count += 1
    require(not source_ready({}, {}), "SELF_TEST_PENDING_SOURCE")
    count += 1
    provider_controls = provider_metadata_self_test()
    transport_controls = transport_metadata_self_test()
    closure_controls = source_closure_metadata_self_test()
    coordinator_controls = coordinator_metadata_self_test()
    return {"experiment_id": IDENTITY, "status": "BOOTSTRAP_PURE_METADATA_CONTROLS_PASS",
            "actual_cases": count + len(provider_controls["negative_cases"]) + len(provider_controls["positive_cases"]) + len(transport_controls["negative_cases"]) + len(closure_controls["negative_cases"]) + len(coordinator_controls["negative_cases"]),
            "local_source_control_cases": count, "provider_metadata_controls": provider_controls,
            "transport_metadata_controls": transport_controls,
            "source_closure_metadata_controls": closure_controls,
            "coordinator_metadata_controls": coordinator_controls,
            "registered117_controls_complete": False,
            "network_requests": 0, "subprocess_starts": 0, "scientific_C_target_starts": 0,
            "DSP_frames": 0, "real_transport_or_kill_wait_tested": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--source-scope", action="store_true")
    modes.add_argument("--http-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--event", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if args.http_worker:
            return metadata_http_worker()
        if args.self_test:
            receipt = self_test()
        else:
            require(sys.flags.isolated == 1, "ISOLATED_STANDARD_LIBRARY_RUNTIME_REQUIRED")
            event_path = args.event or Path(os.environ.get("GITHUB_EVENT_PATH", ""))
            require(str(event_path) not in ("", "."), "ACTUAL_EVENT_PATH_REQUIRED")
            receipt = local_scope(args.root, event_path, dict(os.environ))
            write_github_outputs(args.github_output, receipt)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (AdmissionError, OSError, UnicodeError) as exc:
        print(json.dumps({"experiment_id": IDENTITY, "disposition": DENIED,
                          "reason": getattr(exc, "reason", "SOURCE_OPERATION_FAILED"),
                          "detail": str(exc), "scientific_execution_admitted": False,
                          "scientific_C_target_starts": 0, "DSP_frames": 0}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
