#!/usr/bin/env python3
"""Fail-closed GitHub Actions pin-only PR classifier (NOT scientific admission).

A legitimate pin-only workflow update can be recognized as NON_MEASUREMENT,
never reported as a BF/AEC/DOA science experiment or as an action-security pass.
All other PRs return pin_only=false so existing scientific guards stay in force.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

TRUSTED = {
    "actions/upload-artifact": (
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "cf430e030ddbb5b0abf93d22962f4752f3646cd9",
        "",  # no suffix or old/new exact v7 labels
    ),
    "github/codeql-action/init": (
        "2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2",
        "24c54180a607b1449ed407dd24f251e4e9147c8d",
        "# v4",
    ),
    "github/codeql-action/analyze": (
        "2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2",
        "24c54180a607b1449ed407dd24f251e4e9147c8d",
        "# v4",
    ),
}
# Historical T0/M0 evidence is immutable. A later source review must select its
# own exact transitions; neither a version tag nor an arbitrary target is policy.
HISTORICAL_REVIEW = "historical-t0"
CURRENT_REVIEW = "2026-10-20"
REVIEWED = {
    HISTORICAL_REVIEW: TRUSTED,
    CURRENT_REVIEW: {
        "actions/upload-artifact": TRUSTED["actions/upload-artifact"],
        "github/codeql-action/init": (
            "2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2",
            "6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee", "# v4"),
        "github/codeql-action/analyze": (
            "2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2",
            "6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee", "# v4"),
    },
}
SHA = re.compile(r"[0-9a-f]{40}")
PATH = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.yml")
USES = re.compile(
    r"(?P<prefix>[ \t]*(?:-[ \t]+)?uses:[ \t]+)"
    r"(?P<action>[A-Za-z0-9_./-]+)@(?P<sha>[0-9a-f]{40})"
    r"(?P<suffix>[ \t]*(?:#[ \t]*[^\r\n]*)?)"
)
MAX_FILES = 80
MAX_BYTES_PER_FILE = 300_000
MAX_EDITS_PER_FILE = 70


class ScopeError(ValueError):
    """Untrusted revision, path, diff, permission or source checkout."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ScopeError(code)


def reviewed_pins(review: str) -> dict:
    require(type(review) is str and review in REVIEWED, "UNKNOWN_PIN_REVIEW")
    return REVIEWED[review]


def authorized_line(old: str, new: str, *,
                    review: str = HISTORICAL_REVIEW) -> tuple[str, str, str] | None:
    policy = reviewed_pins(review)
    if old == new:
        return None
    # No mixed CRLF/LF or trailing whitespace ambiguity in a policy-critical diff.
    old_eol = "\r\n" if old.endswith("\r\n") else "\n" if old.endswith("\n") else ""
    new_eol = "\r\n" if new.endswith("\r\n") else "\n" if new.endswith("\n") else ""
    if not old_eol or old_eol != new_eol:
        return None
    a = USES.fullmatch(old[:-len(old_eol)])
    b = USES.fullmatch(new[:-len(new_eol)])
    if a is None or b is None or a["prefix"] != b["prefix"] or a["action"] != b["action"]:
        return None
    entry = policy.get(a["action"])
    if entry is None or a["sha"] != entry[0] or b["sha"] != entry[1]:
        return None
    old_suffix = a["suffix"].strip()
    new_suffix = b["suffix"].strip()
    if a["action"] == "actions/upload-artifact":
        if (old_suffix, new_suffix) not in (
            ("", ""), ("# v7.0.1", "# v7.0.2")
        ):
            return None
    elif old_suffix != new_suffix or old_suffix not in ("", "# v4"):
        return None
    return a["action"], a["sha"], b["sha"]


def _yaml_literal_line_numbers(lines: list[str]) -> set[int]:
    """Reject pin-looking text nested inside run:/env: block scalar payloads.

    This is intentionally conservative lexical screening. Not a complete YAML
    parser and never permits promoting science without independent guards.
    """
    blocked: set[int] = set()
    scalar_indent: int | None = None
    for index, line in enumerate(lines):
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if scalar_indent is not None:
            if not stripped or indent > scalar_indent:
                blocked.add(index)
                continue
            scalar_indent = None
        if re.fullmatch(r".*?:[ \\t]*[|>][+-]?[ \\t]*(?:#.*)?", line.rstrip("\r\n")):
            scalar_indent = indent
    return blocked


def _actual_step_uses_line_numbers(lines: list[str]) -> set[int]:
    """Allow only real step-level uses keys in conventional Actions jobs.

    Deliberately fail closed for nonstandard YAML indentation, env/with maps,
    inline snippets and synthetic string payloads. This is not a YAML parser.
    The reviewed workflow set uses two-space job/step nesting.
    """
    allowed: set[int] = set()
    seen_jobs = False
    inside_steps = False
    inside_step = False
    for index, raw in enumerate(lines):
        line = raw.rstrip("\r\n")
        if re.fullmatch(r"jobs:[ ]*(?:#.*)?", line):
            seen_jobs = True
            inside_steps = False
            inside_step = False
            continue
        if not seen_jobs or not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if inside_steps and indent <= 4:
            inside_steps = False
            inside_step = False
        if re.fullmatch(r" {4}steps:[ ]*(?:#.*)?", line):
            inside_steps = True
            inside_step = False
            continue
        if not inside_steps:
            continue
        if re.match(r" {6}-[ ]+", line):
            inside_step = True
            if re.match(r" {6}-[ ]+uses:", line):
                allowed.add(index)
        elif inside_step and re.match(r" {8}uses:", line):
            allowed.add(index)
    return allowed


def classify_text(before: str, after: str, *,
                  review: str = HISTORICAL_REVIEW) -> list[dict] | None:
    reviewed_pins(review)
    if before == after or not before or not after:
        return None
    old_lines = before.splitlines(keepends=True)
    new_lines = after.splitlines(keepends=True)
    old_block = _yaml_literal_line_numbers(old_lines)
    new_block = _yaml_literal_line_numbers(new_lines)
    old_steps = _actual_step_uses_line_numbers(old_lines)
    new_steps = _actual_step_uses_line_numbers(new_lines)
    edits: list[dict] = []
    for op, i, i2, j, j2 in difflib.SequenceMatcher(
        None, old_lines, new_lines, autojunk=False
    ).get_opcodes():
        if op == "equal":
            continue
        if op != "replace" or i2 - i != j2 - j or i2 == i:
            return None
        for old_index, new_index in zip(range(i, i2), range(j, j2)):
            if (old_index in old_block or new_index in new_block or
                    old_index not in old_steps or new_index not in new_steps):
                return None  # A changed script/string payload is not a step uses.
            line_before = old_lines[old_index]
            line_after = new_lines[new_index]
            pin = authorized_line(line_before, line_after, review=review)
            if pin is None:
                return None
            action, old_sha, new_sha = pin
            edits.append({"action": action, "old": old_sha, "new": new_sha})
            if len(edits) > MAX_EDITS_PER_FILE:
                return None
    return edits or None


def command(args: list[str], *, max_bytes: int = 1024 * 1024) -> bytes:
    require(0 < len(args) <= 9 and all(isinstance(x, str) for x in args),
            "COMMAND_ARGUMENT_INVALID")
    try:
        result = subprocess.run(args, capture_output=True, check=False,
                                timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScopeError("GIT_IO_FAILED_" + type(exc).__name__) from None
    require(result.returncode == 0 and len(result.stdout) < max_bytes and
            len(result.stderr) < max_bytes, "GIT_COMMAND_FAILED")
    return result.stdout


def commit_sha(revision: str) -> str:
    require(isinstance(revision, str) and
            (revision == "HEAD" or SHA.fullmatch(revision) is not None),
            "BAD_REVISION")
    sha = command(["git", "rev-parse", "--verify", revision + "^{commit}"],
                  max_bytes=1024).decode("ascii").strip()
    require(SHA.fullmatch(sha) is not None, "MALFORMED_COMMIT")
    return sha


def plain_workflow_tree_entry_ok(line: str, path: str) -> bool:
    # A content-only classifier must not admit a mixed executable-bit change.
    return re.fullmatch(r"100644 blob [0-9a-f]{40}\t" +
                        re.escape(path) + r"\n", line) is not None


def plain_workflow_blob(revision: str, path: str) -> bool:
    tree = command(["git", "ls-tree", revision, "--", path],
                   max_bytes=1024).decode("utf-8")
    return plain_workflow_tree_entry_ok(tree, path)


def classify_repo(base: str, head: str, *,
                  review: str = HISTORICAL_REVIEW) -> dict:
    reviewed_pins(review)
    before = commit_sha(base)
    after = commit_sha(head)
    require(before != after, "EMPTY_REVISION_RANGE")
    common = command(["git", "merge-base", before, after],
                     max_bytes=1024).decode("ascii").strip()
    require(SHA.fullmatch(common) is not None, "INVALID_MERGE_BASE")
    require(common == before, "BASE_NOT_HEAD_ANCESTOR")
    range_spec = before + "..." + after
    names = command(["git", "diff", "--no-renames", "--name-status",
                     "-z", range_spec], max_bytes=100_000).decode("utf-8")
    parts = names.split("\0")
    require(parts[-1:] == [""] and len(parts) % 2 == 1,
            "AMBIGUOUS_DIFF_STATUS")
    records = list(zip(parts[::2], parts[1::2]))
    # zip above includes an incomplete terminal pair only if bad framing;
    # fail closed instead of ever dropping a path.
    require(0 < len(records) <= MAX_FILES and
            len(parts) == 2 * len(records) + 1,
            "EMPTY_OR_OVERSIZED_DIFF")
    files: list[dict] = []
    for status, path in records:
        if status != "M" or PATH.fullmatch(path) is None:
            # Not pure dependency maintenance: existing science/source guards
            # MUST execute, not be short-circuited by this classifier.
            return {
                "schema_version": 1,
                "base": before, "head": after, "merge_base": common,
                "pin_only": False,
                "decision": "NOT_PIN_ONLY_SCIENCE_GUARDS_REMAIN_ACTIVE",
                "reason": "NON_WORKFLOW_OR_NONMODIFICATION_DIFF",
                "files_checked": len(records), "replacements": 0,
            }
        if not (plain_workflow_blob(before, path) and
                plain_workflow_blob(after, path)):
            return {
                "schema_version": 1,
                "base": before, "head": after, "merge_base": common,
                "pin_only": False,
                "decision": "NOT_PIN_ONLY_SCIENCE_GUARDS_REMAIN_ACTIVE",
                "reason": "WORKFLOW_BLOB_TYPE_OR_MODE_DRIFT",
                "files_checked": len(records), "replacements": 0,
            }
        old = command(["git", "show", before + ":" + path],
                      max_bytes=MAX_BYTES_PER_FILE).decode("utf-8")
        new = command(["git", "show", after + ":" + path],
                      max_bytes=MAX_BYTES_PER_FILE).decode("utf-8")
        edits = classify_text(old, new, review=review)
        if edits is None:
            return {
                "schema_version": 1,
                "base": before, "head": after, "merge_base": common,
                "pin_only": False,
                "decision": "NOT_PIN_ONLY_SCIENCE_GUARDS_REMAIN_ACTIVE",
                "reason": "WORKFLOW_LOGIC_OR_UNAPPROVED_PIN_DIFF",
                "files_checked": len(records), "replacements": 0,
            }
        files.append({"path": path, "edits": edits})
    return {
        "schema_version": 1, "base": before, "head": after,
        "merge_base": common, "pin_only": True,
        "decision": "SCIENCE_NOT_EXECUTED_NON_MEASUREMENT_MAINTENANCE",
        "files_checked": len(files),
        "replacements": sum(len(f["edits"]) for f in files),
        "pin_diff_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def expected_repo(base: str, *, review: str) -> dict:
    """Derive the entire reviewed update from the protected base's actual tree.

    This is independent of the bot's diff and historical fixture counts. New
    approved upload sites on protected main participate automatically, while
    omissions, partial updates and any extra bot edit fail the later equality
    check. This function cannot establish that ``base`` is protected main;
    the M1 caller must establish that provenance before using its result.
    """
    policy = reviewed_pins(review)
    before = commit_sha(base)
    tree = command(["git", "ls-tree", "-r", "-z", before, "--",
                    ".github/workflows"], max_bytes=100_000).decode("utf-8")
    records: list[dict] = []
    for entry in tree.split("\0"):
        if not entry:
            continue
        fields = entry.split("\t")
        require(len(fields) == 2, "BASE_WORKFLOW_TREE_FRAMING")
        mode, path = fields
        if PATH.fullmatch(path) is None:
            continue
        require(re.fullmatch(r"100644 blob [0-9a-f]{40}", mode) is not None,
                "BASE_WORKFLOW_TYPE_OR_MODE_DRIFT")
        raw = command(["git", "show", before + ":" + path],
                      max_bytes=MAX_BYTES_PER_FILE).decode("utf-8")
        lines = raw.splitlines(keepends=True)
        steps = _actual_step_uses_line_numbers(lines)
        blocked = _yaml_literal_line_numbers(lines)
        edits = []
        for index, line in enumerate(lines):
            if index not in steps or index in blocked:
                continue
            match = USES.fullmatch(line.rstrip("\r\n"))
            if match is None or match["action"] not in policy:
                continue
            old, new, _ = policy[match["action"]]
            if match["sha"] != old:
                continue
            candidate = line[:match.start("sha")] + new + line[match.end("sha"):]
            if match["action"] == "actions/upload-artifact":
                candidate = candidate.replace("# v7.0.1", "# v7.0.2")
            pin = authorized_line(line, candidate, review=review)
            require(pin is not None, "PROTECTED_BASE_REVIEWED_PIN_SYNTAX_DRIFT")
            action, old_pin, new_pin = pin
            edits.append({"action": action, "old": old_pin, "new": new_pin})
        require(len(edits) <= MAX_EDITS_PER_FILE, "EXPECTED_PIN_EDIT_BUDGET")
        if edits:
            records.append({"path": path, "edits": edits})
    require(0 < len(records) <= MAX_FILES, "EXPECTED_PIN_FILE_BUDGET")
    records.sort(key=lambda entry: entry["path"])
    return {
        "base": before, "review_id": review,
        "files_checked": len(records),
        "replacements": sum(len(row["edits"]) for row in records),
        "pin_diff_sha256": hashlib.sha256(json.dumps(
            records, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "source": "complete-reviewed-pin-transition-from-protected-base-tree",
    }


def self_test() -> None:
    old_pin, new_pin, _ = TRUSTED["actions/upload-artifact"]
    old_codeql, new_codeql, _ = TRUSTED["github/codeql-action/init"]
    before = (
        "name: Example\n"
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - uses: actions/upload-artifact@" + old_pin + " # v7.0.1\n"
        "      - name: Plain\n"
        "        uses: github/codeql-action/init@" + old_codeql + " # v4\n"
        "        run: echo harmless\n"
    )
    after = before.replace(old_pin, new_pin).replace(
        "# v7.0.1", "# v7.0.2").replace(old_codeql, new_codeql)
    edits = classify_text(before, after)
    require(edits is not None and len(edits) == 2, "VALID_PIN_DIFF_REJECTED")
    plain_old = ("jobs:\n  unit:\n    steps:\n"
                 "      - name: Upload\n"
                 "        uses: actions/upload-artifact@" + old_pin + "\n")
    plain_new = plain_old.replace(old_pin, new_pin)
    require(classify_text(plain_old, plain_new) is not None,
            "MISSING_COMMENT_VARIANT_REJECTED")

    mutations = [
        after + "      - run: curl attacker\n",
        after.replace("run: echo harmless", "run: curl attacker"),
        after.replace("jobs:", "permissions:\n  contents: write\njobs:"),
        after.replace("uses: github/codeql-action/init@", "uses: external/action@"),
        after.replace(new_codeql, "1" * 40),
        after.replace("# v7.0.2", "# v100"),
        after.replace(new_pin, "v7"),
        before,  # no modifications is not a classified update
        before + "     ",
        after.replace("      - name: Plain\n", ""),
    ]
    for i, bad in enumerate(mutations):
        require(classify_text(before, bad) is None,
                "FALSE_PIN_ONLY_ACCEPT_MUTATION_" + str(i))
    # An approved pin update PLUS executable/permissions changes is never pure.
    require(classify_text(before, after.replace(
        "run: echo harmless", "run: rm -rf /")) is None,
            "MIXED_EXECUTABLE_DIFF_ACCEPTED")
    in_script_old = ("jobs:\n  a:\n    steps:\n"
                     "      - run: |\n          uses: actions/upload-artifact@" + old_pin + "\n")
    in_script_new = in_script_old.replace(old_pin, new_pin)
    require(classify_text(in_script_old, in_script_new) is None,
            "RUN_BLOCK_USES_NOT_ACTUAL_ACTION_ACCEPTED")
    in_env_old = ("jobs:\n  a:\n    env:\n      NOTE: >\n"
                  "        uses: actions/upload-artifact@" + old_pin + "\n")
    require(classify_text(in_env_old, in_env_old.replace(old_pin, new_pin)) is None,
            "YAML_LITERAL_USES_AS_ACTION_ACCEPTED")
    # A pin-looking env/with/root uses is NOT a GitHub Actions executable step.
    # A future T1 science skip must not trust non-step YAML strings.
    nonstep_sources = (
        ("jobs:\n  x:\n    env:\n"
         "      uses: actions/upload-artifact@" + old_pin + "\n"),
        ("jobs:\n  x:\n    steps:\n"
         "      - name: Task\n"
         "        with:\n"
         "          uses: actions/upload-artifact@" + old_pin + "\n"),
        ("uses: actions/upload-artifact@" + old_pin + "\n"),
        ("jobs:\n  x:\n    steps:\n"
         "      - run: echo safe\n"
         "        env:\n"
         "          uses: actions/upload-artifact@" + old_pin + "\n"),
    )
    for i, source in enumerate(nonstep_sources):
        require(classify_text(source, source.replace(old_pin, new_pin)) is None,
                "NONSTEP_YAML_FALSE_ADMISSION_" + str(i))
    require(PATH.fullmatch(".github/workflows/x.yml") is not None and
            PATH.fullmatch("src/audio.c") is None and
            PATH.fullmatch(".github/workflows/x.yml/../../bad") is None,
            "PATH_ALLOWLIST_FAILED")
    require(SHA.fullmatch(old_pin) is not None and
            SHA.fullmatch("v7.0.2") is None,
            "PIN_MUST_BE_FULL_SHA")
    sample_path = ".github/workflows/example.yml"
    valid_entry = "100644 blob " + old_pin + "\t" + sample_path + "\n"
    require(plain_workflow_tree_entry_ok(valid_entry, sample_path) and
            not plain_workflow_tree_entry_ok(
                valid_entry.replace("100644", "100755"), sample_path) and
            not plain_workflow_tree_entry_ok(
                valid_entry.replace("100644", "120000"), sample_path) and
            not plain_workflow_tree_entry_ok(
                valid_entry.replace(" blob ", " tree "), sample_path),
            "WORKFLOW_GIT_OBJECT_MODE_NOT_ENFORCED")
    current_codeql = REVIEWED[CURRENT_REVIEW]["github/codeql-action/init"][1]
    current_after = after.replace(new_codeql, current_codeql)
    require(classify_text(before, current_after) is None and
            classify_text(before, current_after, review=CURRENT_REVIEW) is not None,
            "REVIEW_GENERATIONS_CONFUSED")
    require(classify_text(before, after, review=CURRENT_REVIEW) is None and
            classify_text(before, current_after.replace(current_codeql, "e" * 40),
                          review=CURRENT_REVIEW) is None,
            "UNREVIEWED_CURRENT_PIN_ADMITTED")
    try:
        classify_text(before, current_after, review="future-unreviewed")
    except ScopeError:
        pass
    else:
        raise ScopeError("UNKNOWN_REVIEW_ADMITTED")
    print("WORKFLOW_PIN_ONLY_CLASSIFIER_SELF_TEST_PASS negatives=" +
          str(len(mutations) + 12 + len(nonstep_sources)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--review", choices=tuple(REVIEWED),
                        default=HISTORICAL_REVIEW)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        if args.self_test:
            require(not args.base and not args.head and not args.github_output,
                    "SELF_TEST_OPTIONS_INVALID")
            self_test()
            return
        require(args.base and args.head, "BASE_HEAD_REQUIRED")
        result = classify_repo(args.base, args.head, review=args.review)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
        if args.github_output:
            require(args.github_output.is_file() and
                    not args.github_output.is_symlink(),
                    "INVALID_GITHUB_OUTPUT")
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write("pin_only=" +
                             ("true" if result["pin_only"] else "false") +
                             "\n")
                output.write("pin_decision=" + result["decision"] + "\n")
    except (ScopeError, OSError, UnicodeError, ValueError,
            subprocess.CalledProcessError) as exc:
        print("WORKFLOW_PIN_ONLY_SCOPE_NOT_ADMITTED: " + str(exc),
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
