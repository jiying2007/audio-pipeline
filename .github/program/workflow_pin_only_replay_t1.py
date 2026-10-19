#!/usr/bin/env python3
"""T1 preflight: reproduce the exact #714 GitHub Actions pin proposal offline.

This is deliberately ONLY a nonshipping/fail-closed test of the already
merged T0 classifier. NO scientific workflow calls this script and it never
authorizes bypassing research measurements, PR admission, releases or HIL.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PROPOSAL = HERE / "workflow_pin_only_bot714_exact_t1.json"
CLASSIFIER = HERE / "workflow_pin_only_scope.py"
SOURCE_HEAD = "3e29c6cc81000741844ecc47962ba43e18e7e502"
SOURCE_PR = 714
FILES = 55
REPLACEMENTS = 108
SHA = re.compile(r"[0-9a-f]{40}")
PIN_PATH = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.yml")
READ_CAP = 100_000


class PreflightFailure(ValueError):
    pass


def demand(condition: bool, reason: str) -> None:
    if not condition:
        raise PreflightFailure(reason)


def strict_json(pairs: list[tuple[str, object]]) -> dict:
    obj: dict = {}
    for key, value in pairs:
        demand(key not in obj, "DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def read_manifest() -> tuple[dict, str]:
    demand(PROPOSAL.is_file() and not PROPOSAL.is_symlink() and
           0 < PROPOSAL.stat().st_size < 100_000, "MANIFEST_MISSING_OR_OVERSIZED")
    raw = PROPOSAL.read_bytes()
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_json)
    demand(type(data) is dict and set(data) == {
        "schema_version", "source_pr", "source_pr_url", "source_bot_head_sha",
        "source_observed_main_sha", "decision", "files", "workflow_count",
        "pin_replacements"
    }, "MANIFEST_SCHEMA_DRIFT")
    demand(type(data["schema_version"]) is int and data["schema_version"] == 1 and
           type(data["source_pr"]) is int and data["source_pr"] == SOURCE_PR and
           data["source_pr_url"] == "https://github.com/jiying2007/audio-pipeline/pull/714" and
           data["source_bot_head_sha"] == SOURCE_HEAD and
           SHA.fullmatch(data["source_observed_main_sha"]) is not None and
           data["decision"] == "EXACT_BOT_PROPOSAL_REPLAY_RESEARCH_ONLY_NOT_ADMITTED" and
           data["workflow_count"] == FILES and
           data["pin_replacements"] == REPLACEMENTS, "SOURCE_AUTHORITY_DRIFT")
    return data, hashlib.sha256(raw).hexdigest()


def load_t0() -> object:
    demand(CLASSIFIER.is_file() and not CLASSIFIER.is_symlink() and
           0 < CLASSIFIER.stat().st_size < READ_CAP, "T0_CLASSIFIER_UNAVAILABLE")
    spec = importlib.util.spec_from_file_location("t0_classifier_replay", CLASSIFIER)
    demand(spec is not None and spec.loader is not None,
           "T0_CLASSIFIER_IMPORT_NOT_AVAILABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_proposal(data: dict, t0: object) -> None:
    rows = data["files"]
    demand(type(rows) is list and len(rows) == FILES, "PROPOSAL_55_FILES_REQUIRED")
    seen: set[str] = set()
    total = 0
    actions = {"actions/upload-artifact": 0,
               "github/codeql-action/init": 0,
               "github/codeql-action/analyze": 0}
    for entry in rows:
        demand(type(entry) is dict and set(entry) == {"path", "pairs"},
               "PROPOSAL_ENTRY_INVALID")
        path, pairs = entry["path"], entry["pairs"]
        demand(type(path) is str and PIN_PATH.fullmatch(path) is not None
               and path not in seen, "PATH_RENAME_OR_DUPLICATE")
        seen.add(path)
        demand(type(pairs) is list and 0 < len(pairs) <= 70,
               "PROPOSAL_PER_FILE_COUNT")
        for pair in pairs:
            demand(type(pair) is list and len(pair) == 2 and
                   all(type(s) is str and 0 < len(s) <= 300 for s in pair),
                   "NONLINEAR_PATCH")
            admission = t0.authorized_line(pair[0] + "\n", pair[1] + "\n")
            demand(admission is not None and admission[0] in actions,
                   "UNTRUSTED_OR_MIXED_PATCH")
            actions[admission[0]] += 1
        total += len(pairs)
    demand(total == REPLACEMENTS and
           actions == {"actions/upload-artifact": 106,
                       "github/codeql-action/init": 1,
                       "github/codeql-action/analyze": 1},
           "CANDIDATE_COUNTS_CHANGED")


def git(where: Path, *arguments: str) -> str:
    argv = ["git", *arguments]
    demand(len(argv) <= 12, "GIT_ARG_BOUND")
    try:
        proc = subprocess.run(argv, cwd=where, capture_output=True, timeout=35,
                              check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise PreflightFailure("OFFLINE_GIT_FAILURE") from None
    demand(proc.returncode == 0 and len(proc.stdout) < READ_CAP and
           len(proc.stderr) < READ_CAP,
           "OFFLINE_GIT_FAILED_" + arguments[0])
    return proc.stdout.decode("utf-8").strip()



def historical_fixture_baseline(raw: bytes, pairs: list[list[str]]) -> bytes:
    """Create ONLY a synthetic historical base for the frozen M0 replay.

    The *actual* bot PR Git tree must still be separately qualified by M1.
    Exact already-approved new pins may be reversed in this temporary
    fixture; mixed/partial/unknown pin states are intentionally denied.
    """
    demand(type(raw) is bytes and 0 < len(raw) < 300_000 and b"\r" not in raw,
           "WORKFLOW_NEWLINE_DRIFT")
    lines = raw.splitlines(keepends=True)
    groups: dict[tuple[bytes, bytes], int] = {}
    for old, new in pairs:
        prior, updated = (old + "\n").encode(), (new + "\n").encode()
        demand(prior != updated and prior.endswith(b"\n") and
               updated.endswith(b"\n"), "FIXTURE_UNTRUSTED_PIN_PAIR")
        key = (prior, updated)
        groups[key] = groups.get(key, 0) + 1
    demand(groups, "FIXTURE_EMPTY_PIN_PROPOSAL")
    for (prior, updated), required in groups.items():
        n_prior, n_updated = lines.count(prior), lines.count(updated)
        # The frozen witness is a subset: modern main has additional, still
        # unmodified identical Action pins (e.g. 40 vs 24 in quality.yml).
        # Reject mixed old/new state, but do not reject extra unchanged lines.
        demand((n_prior >= required and n_updated == 0) or
               (n_updated >= required and n_prior == 0),
               "BOT_PROPOSAL_PIN_STATE_MISSING_OR_MIXED")
        if n_updated:
            remaining = required
            for index, line in enumerate(lines):
                if line == updated and remaining:
                    lines[index] = prior
                    remaining -= 1
            demand(remaining == 0, "HISTORICAL_FIXTURE_REVERSAL_INCOMPLETE")
    return b"".join(lines)


def fixture_state_self_test(manifest: dict) -> None:
    """Regression: historical M0 replay is valid before/after trusted pins."""
    pair = manifest["files"][0]["pairs"][0]
    prior, updated = (pair[0] + "\n").encode(), (pair[1] + "\n").encode()
    header = b"name: offline synthetic fixture\n"
    demand(historical_fixture_baseline(header + prior, [pair]) ==
           header + prior, "OLD_PIN_FIXTURE_REJECTED")
    demand(historical_fixture_baseline(header + updated, [pair]) ==
           header + prior, "APPROVED_NEW_PIN_FIXTURE_REJECTED")
    demand(historical_fixture_baseline(header + prior * 2, [pair, pair]) ==
           header + prior * 2, "REPEATED_OLD_PINS_REJECTED")
    demand(historical_fixture_baseline(header + updated * 2, [pair, pair]) ==
           header + prior * 2, "REPEATED_NEW_PINS_REJECTED")
    # Unchanged extra identical pins are allowed only in this offline fixture;
    # an actual PR/head change is always judged by the separate strict T0/M1.
    demand(historical_fixture_baseline(header + prior * 2, [pair]) ==
           header + prior * 2, "EXTRA_OLD_PIN_FIXTURE_REJECTED")
    demand(historical_fixture_baseline(header + updated * 2, [pair]) ==
           header + prior + updated, "EXTRA_NEW_PIN_FIXTURE_REJECTED")
    for name, source, pairs in (
        ("missing", header, [pair]),
        ("mixed", header + prior + updated, [pair, pair]),
        ("duplicate_conflict", header + prior + updated, [pair]),
        ("unknown_pin", header + prior.replace(b"0", b"f", 1), [pair]),
        ("crlf", header + prior.replace(b"\n", b"\r\n"), [pair]),
        ("truncated", header + prior.rstrip(b"\n"), [pair]),
    ):
        try:
            historical_fixture_baseline(source, pairs)
        except PreflightFailure:
            pass
        else:
            raise PreflightFailure("FALSE_OFFLINE_PIN_STATE_ADMISSION_" + name)


def replay(t0: object, manifest: dict, receipt_sha: str) -> dict:
    cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="fe-t1-exact-pin-proposal-") as d:
        sandbox = Path(d)
        git(sandbox, "init", "-q")
        git(sandbox, "config", "user.email", "qualification@example.invalid")
        git(sandbox, "config", "user.name", "Qualification Only")
        for entry in manifest["files"]:
            path = entry["path"]
            source = ROOT / path
            demand(source.is_file() and not source.is_symlink() and
                   0 < source.stat().st_size < 300_000,
                   "PROPOSAL_BASE_FILE_UNAVAILABLE")
            target = sandbox / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(historical_fixture_baseline(
                source.read_bytes(), entry["pairs"]))
        git(sandbox, "add", ".github/workflows")
        git(sandbox, "commit", "-qm", "Fixture base: main unchanged workflows")
        base = git(sandbox, "rev-parse", "HEAD")
        touched = []
        for entry in manifest["files"]:
            path = sandbox / entry["path"]
            current = path.read_bytes()
            demand(b"\r" not in current, "WORKFLOW_NEWLINE_DRIFT")
            for old, new in entry["pairs"]:
                before, after = (old + "\n").encode(), (new + "\n").encode()
                demand(before != after and before in current,
                       "BOT_PROPOSAL_BASE_LINE_MISSING")
                current = current.replace(before, after, 1)
            path.write_bytes(current)
            touched.append(entry["path"])
        git(sandbox, "add", ".github/workflows")
        git(sandbox, "commit", "-qm", "Exact 714 55-workflow 108-pin replay")
        good_head = git(sandbox, "rev-parse", "HEAD")
        os.chdir(sandbox)
        try:
            verdict = t0.classify_repo(base, good_head)
            demand(verdict.get("pin_only") is True and
                   verdict.get("decision") ==
                   "SCIENCE_NOT_EXECUTED_NON_MEASUREMENT_MAINTENANCE" and
                   verdict.get("files_checked") == FILES and
                   verdict.get("replacements") == REPLACEMENTS and
                   SHA.fullmatch(verdict.get("base", "")) is not None and
                   SHA.fullmatch(verdict.get("head", "")) is not None and
                   re.fullmatch(r"[0-9a-f]{64}", verdict.get("pin_diff_sha256", ""))
                   is not None, "EXACT_BOT_PIN_DIFF_NOT_CLASSIFIED")

            path = sandbox / touched[0]
            text = path.read_text(encoding="utf-8")
            approved = manifest["files"][0]["pairs"][0][1]
            demand(approved in text, "BAD_APPROVED_TEST_LINE")
            rejected = 0

            def reject(reason: str, mutate) -> None:
                nonlocal rejected
                git(sandbox, "reset", "--hard", good_head)
                git(sandbox, "clean", "-fd")
                mutate()
                git(sandbox, "add", "-A")
                git(sandbox, "commit", "-qm", "Negative: " + reason)
                commit = git(sandbox, "rev-parse", "HEAD")
                try:
                    actual = t0.classify_repo(base, commit)
                except (t0.ScopeError, ValueError):
                    rejected += 1
                    return
                demand(actual.get("pin_only") is False,
                       "FALSE_MAINTENANCE_ADMISSION_" + reason)
                rejected += 1

            def replace_line(needle: str, replacement: str) -> None:
                content = path.read_text(encoding="utf-8")
                demand(needle in content, "MUTATION_ANCHOR_MISSING")
                path.write_text(content.replace(needle, replacement, 1),
                                encoding="utf-8")

            def add_extra(name: str, contents: str) -> None:
                target = sandbox / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents, encoding="utf-8")

            reject("shipping_source", lambda:
                   add_extra("src/injected.c", "int unsafe = 1;\n"))
            reject("unknown_action", lambda:
                   replace_line(approved,
                                approved.replace("actions/upload-artifact",
                                                 "thirdparty/unknown")))
            reject("floating_tag", lambda:
                   replace_line(approved,
                                re.sub(r"@[0-9a-f]{40}", "@v7.0.2", approved)))
            reject("untrusted_sha", lambda:
                   replace_line(approved,
                                re.sub(r"@[0-9a-f]{40}", "@" + "f" * 40,
                                       approved)))
            reject("workflow_step", lambda:
                   add_extra(".github/workflows/extra.yml",
                             "name: extra\njobs:\n  x:\n    runs-on: ubuntu-latest\n"))
            reject("permissions_change", lambda:
                   path.write_text(path.read_text(encoding="utf-8") +
                                   "\npermissions: write-all\n", encoding="utf-8"))
            reject("env_fake_uses", lambda:
                   path.write_text(path.read_text(encoding="utf-8") +
                                   "\nenv:\n  NOTE: uses: actions/upload-artifact@v7\n",
                                   encoding="utf-8"))
            reject("script_fake_uses", lambda:
                   path.write_text(path.read_text(encoding="utf-8") +
                                   "\n# run: |\n#   uses: malicious/action@main\n",
                                   encoding="utf-8"))
            reject("executable_mode", lambda:
                   path.chmod(0o755))
            reject("workflow_deleted", lambda:
                   path.unlink())
            reject("workflow_renamed", lambda:
                   path.rename(path.with_name("renamed-" + path.name)))
            reject("classifier_modified", lambda:
                   add_extra(".github/program/workflow_pin_only_scope.py",
                             "# malicious candidate-supplied classifier\n"))
            git(sandbox, "reset", "--hard", good_head)
            git(sandbox, "clean", "-fd")
            try:
                t0.classify_repo(base, base)
            except (t0.ScopeError, ValueError):
                rejected += 1
            else:
                raise PreflightFailure("EMPTY_COMMIT_RANGE_ACCEPTED")
            try:
                t0.classify_repo("0" * 40, good_head)
            except (t0.ScopeError, ValueError):
                rejected += 1
            else:
                raise PreflightFailure("FAKE_BASE_ACCEPTED")

            demand(rejected == 14, "NEGATIVE_SUITE_INCOMPLETE")
            return {
                "schema_version": 1,
                "decision": "T1_EXACT_BOT_DIFF_OFFLINE_REPLAY_ONLY_NOT_ADMITTED",
                "source_pr": 714,
                "source_bot_head_sha": SOURCE_HEAD,
                "replayed_workflows": verdict["files_checked"],
                "replayed_pin_replacements": verdict["replacements"],
                "replayed_pin_diff_sha256": verdict["pin_diff_sha256"],
                "bot_patch_fixture_sha256": receipt_sha,
                "adversarial_negative_cases": rejected,
                "source_role": "offline-replay-of-exact-GitHub-PR-patch",
                "actual_bot_git_tree_checked": False,
                "actual_scientific_experiment_executed": False,
                "automated_bypass_enabled": False,
                "ssc305_or_acoustic_gain_qualified": False,
            }
        finally:
            os.chdir(cwd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", required=True)
    args = parser.parse_args()
    try:
        demand(args.self_test, "SELF_TEST_MODE_REQUIRED")
        proposal, sha = read_manifest()
        t0 = load_t0()
        validate_proposal(proposal, t0)
        fixture_state_self_test(proposal)
        result = replay(t0, proposal, sha)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         allow_nan=False))
    except (PreflightFailure, ValueError, OSError, UnicodeError,
            subprocess.CalledProcessError, KeyError, TypeError) as exc:
        print("T1_EXACT_BOT_DIFF_REPLAY_NOT_ADMITTED: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
