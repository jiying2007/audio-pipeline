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
            return False
        pending.extend(value["parents"])
    return False


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

    def admit_start(self, route: int) -> None:
        require(self.next_route == len(self.accounted_routes) + 1, "API_BUDGET_ACCOUNTING_DRIFT")
        require(type(route) is int and route == self.next_route and 1 <= route <= 17,
                "API_REQUEST_BUDGET_EXCEEDED")
        require(self.active_ns < API_ACTIVE_NS, "API_AGGREGATE_BUDGET_EXCEEDED")
        self.next_route += 1

    def account(self, route: int, body_bytes: int, exchange_bytes: int, duration_ns: int) -> None:
        require(type(route) is int and route == self.next_route - 1 == len(self.accounted_routes) + 1 and
                route not in self.accounted_routes and 1 <= route <= 17, "API_BUDGET_ACCOUNTING_DRIFT")
        require(strict_int(body_bytes) and body_bytes <= API_BODY_CAPS[route - 1], "API_BODY_BOUND_EXCEEDED")
        require(strict_int(exchange_bytes) and exchange_bytes <= 16384, "API_EXCHANGE_BOUND_EXCEEDED")
        require(strict_int(duration_ns) and duration_ns <= COMMAND_NS, "API_WHOLE_OPERATION_TIMEOUT")
        require(self.active_ns + duration_ns <= API_ACTIVE_NS, "API_AGGREGATE_BUDGET_EXCEEDED")
        require(self.raw_bytes + body_bytes + exchange_bytes <= CONTROL_BYTES, "CONTROL_EVIDENCE_BOUND_EXCEEDED")
        self.active_ns += duration_ns
        self.raw_bytes += body_bytes + exchange_bytes
        self.accounted_routes.add(route)

    def start_helper(self) -> None:
        require(type(self.helper_starts) is int and self.helper_starts == 0, "METADATA_HELPER_RETRY_NOT_ALLOWED")
        self.helper_starts += 1

    def finish(self) -> None:
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
    require(isinstance(headers, dict), "API_RESPONSE_NOT_ADMITTED")
    encoding = [v for k, v in headers.items() if k.lower() == "content-encoding"]
    require(len(encoding) <= 1 and (not encoding or encoding[0].lower() == "identity"),
            "API_RESPONSE_NOT_ADMITTED")
    require(len(body) <= API_BODY_CAPS[route - 1], "API_BODY_BOUND_EXCEEDED")
    require(exchange.get("body_sha256") == hashlib.sha256(body).hexdigest() and
            type(exchange.get("body_bytes")) is int and exchange["body_bytes"] == len(body),
            "CONTROL_ORIGINAL_EVIDENCE_INCOMPLETE")
    return strict_json(body, API_BODY_CAPS[route - 1])


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
    return {"experiment_id": IDENTITY, "status": "BOOTSTRAP_PURE_METADATA_CONTROLS_PASS",
            "actual_cases": count + len(provider_controls["negative_cases"]) + len(provider_controls["positive_cases"]),
            "local_source_control_cases": count, "provider_metadata_controls": provider_controls,
            "registered117_controls_complete": False,
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
