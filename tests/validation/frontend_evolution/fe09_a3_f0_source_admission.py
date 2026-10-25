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
                part = os.read(key.fd, min(65536, limit + 1 - len(output)))
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
    "5f56f9465c0cab5320cb70544ac3cc8d5edaeb71c928bcdd61c700f50de20bbb",
})
F1_METADATA_COMMAND = "python3 tests/validation/frontend_evolution/test_fe09_t3s3_f1_rss_qualification.py\n"
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
        top["owned_jobs"] = {"frontend-s3-t3s2b1ba3": jobs["frontend-s3-t3s2b1ba3"]}
    else:
        require(workflow == "verify", "A3_OWNED_CI_FRAGMENT_UNCLASSIFIED")
        selected = ("impact", "fast-docs", "fast-code", "fast-gate", "quality", "summary")
        require(set(selected) <= set(jobs), "A3_REQUIRED_DISPATCH_MISSING")
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


def local_scope(root: Path, event_path: Path, env: dict[str, str]) -> dict[str, Any]:
    git = GitObjects(root)
    head = git.head()
    _, parents = git.commit(head)
    event = strict_json(read_regular(event_path, FILE_CAP))
    source = local_source(event, env, head, parents)
    base_guard = git.blob(source["B"], GUARD, required=False)
    changed = git.changed_paths(source["B"], head)
    if base_guard is None:
        return scope_receipt(source, BOOTSTRAP, changed)
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
    return scope_receipt(source, decision, changed)


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
    return {"experiment_id": IDENTITY, "status": "BOOTSTRAP_PURE_METADATA_CONTROLS_PASS",
            "actual_cases": count, "registered117_controls_complete": False,
            "network_requests": 0, "subprocess_starts": 0, "scientific_C_target_starts": 0,
            "DSP_frames": 0, "real_transport_or_kill_wait_tested": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--source-scope", action="store_true")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--event", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if args.self_test:
            receipt = self_test()
        else:
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
