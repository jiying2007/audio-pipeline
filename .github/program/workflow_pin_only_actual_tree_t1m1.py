#!/usr/bin/env python3
"""T1-M1: fail-closed, read-only *actual GitHub bot tree* inspection.

Research CI policy only; never executes code from the bot PR, bypasses
measurement gates, or attests security of replacement third-party Actions.
--self-test is offline. --probe-real may return a NOT_ADMITTED *data verdict*
with exit 0 so bot rebase timing cannot make unrelated science CI fail; only a
CLASSIFIED result could be independently examined by a later preregistered
consumer, and this tool NEVER grants that consumer permission.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
REPO = "jiying2007/audio-pipeline"
BOT_PR = 714
BOT_ACTOR = "dependabot[bot]"
BOT_ACTOR_ID = 49699333
BOT_REF = "dependabot/github_actions/actions-non-major-5b90254856"
GIT_REMOTE = "https://github.com/jiying2007/audio-pipeline.git"
PR_API = "https://api.github.com/repos/jiying2007/audio-pipeline/pulls/714"
CLASSIFIER_PATH = ".github/program/workflow_pin_only_scope.py"
WITNESS_PATH = ".github/program/workflow_pin_only_bot714_exact_t1.json"
QUALIFIER_PATH = ".github/program/workflow_pin_only_actual_tree_t1m1.py"
HISTORICAL_REVIEW = "historical-t0"
PREVIOUS_REVIEW = "2026-10-20"
CURRENT_REVIEW = "2026-10-24"
WITNESSES = {
    HISTORICAL_REVIEW: WITNESS_PATH,
    PREVIOUS_REVIEW: ".github/program/workflow_pin_only_bot714_20261020.json",
    CURRENT_REVIEW: ".github/program/workflow_pin_only_bot714_20261024.json",
}
SHA = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
MAX_BYTES = 150_000
ADMITTED = "T1_ACTUAL_BOT_TREE_CLASSIFIED_NON_MEASUREMENT_ONLY_NO_WORKFLOW_SKIP"
REJECTED = "T1_ACTUAL_BOT_TREE_NOT_ADMITTED"


class AdmissionDenied(ValueError):
    """A valid negative (safe outcome), or a source/provenance uncertainty."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise AdmissionDenied(code)


def strict_pairs(pairs: list[tuple[str, object]]) -> dict:
    output: dict = {}
    for name, value in pairs:
        need(name not in output, "DUPLICATE_JSON_KEY")
        output[name] = value
    return output


def git(args: list[str], *, cwd: Path = ROOT, cap: int = MAX_BYTES) -> bytes:
    need(0 < len(args) <= 16 and all(type(v) is str for v in args),
         "GIT_ARGUMENT_BOUND")
    try:
        done = subprocess.run(
            ["git", "-c", "safe.directory=" + str(cwd), *args], cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=45)
    except (OSError, subprocess.TimeoutExpired):
        raise AdmissionDenied("GIT_IO_OR_TIMEOUT") from None
    need(done.returncode == 0 and len(done.stdout) < cap and
         len(done.stderr) < cap, "GIT_COMMAND_DENIED_" + args[0])
    return done.stdout


def git_sha(args: list[str], *, cwd: Path = ROOT) -> str:
    value = git(args, cwd=cwd, cap=2048).decode("ascii").strip()
    need(SHA.fullmatch(value) is not None, "MALFORMED_GIT_OID")
    return value


def remote_heads() -> tuple[str, str]:
    """Pin both branch refs through the canonical URL, never a PR-controlled remote."""
    data = git(["ls-remote", GIT_REMOTE,
                "refs/heads/main", "refs/heads/" + BOT_REF], cap=4096)
    records = {}
    for line in data.decode("ascii").splitlines():
        parts = line.split("\t")
        need(len(parts) == 2 and SHA.fullmatch(parts[0]) is not None,
             "MALFORMED_REMOTE_REF")
        need(parts[1] not in records and
             parts[1] in {"refs/heads/main", "refs/heads/" + BOT_REF},
             "UNEXPECTED_REMOTE_REF")
        records[parts[1]] = parts[0]
    need(set(records) == {"refs/heads/main", "refs/heads/" + BOT_REF},
         "MISSING_REMOTE_REF")
    return records["refs/heads/main"], records["refs/heads/" + BOT_REF]


def fetch_public_bot_pr() -> dict:
    req = urllib.request.Request(
        PR_API, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "audio-pipeline-t1-m1-source-only/1",
            "X-GitHub-Api-Version": "2022-11-28",
        })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            need(resp.status == 200, "GITHUB_METADATA_STATUS")
            body = resp.read(MAX_BYTES + 1)
    except (OSError, urllib.error.URLError, TimeoutError):
        raise AdmissionDenied("BOT_PR_READ_UNAVAILABLE") from None
    need(0 < len(body) <= MAX_BYTES, "BOT_PR_METADATA_OVERSIZE")
    result = json.loads(body.decode("utf-8"), object_pairs_hook=strict_pairs)
    need(type(result) is dict, "BOT_PR_METADATA_NOT_OBJECT")
    return result


def snapshot_metadata(data: dict, main_sha: str, bot_sha: str) -> tuple[str, str]:
    """Reject stale main, fork, untrusted actor, wrong PR/ref and changed OIDs."""
    need(type(data) is dict and
         type(data.get("number")) is int and data["number"] == BOT_PR and
         data.get("state") == "open" and data.get("draft") is False and
         type(data.get("user")) is dict and
         data["user"].get("login") == BOT_ACTOR and
         type(data["user"].get("id")) is int and
         data["user"]["id"] == BOT_ACTOR_ID and
         data["user"].get("type") == "Bot",
         "WRONG_BOT_PR_IDENTITY")
    base, head = data.get("base"), data.get("head")
    need(type(base) is dict and type(head) is dict, "MISSING_BOT_REF")
    need(type(base.get("repo")) is dict and
         type(head.get("repo")) is dict and
         base["repo"].get("full_name") == REPO and
         head["repo"].get("full_name") == REPO and
         base.get("ref") == "main" and head.get("ref") == BOT_REF,
         "BOT_REF_OR_REPOSITORY_DRIFT")
    b, h = base.get("sha"), head.get("sha")
    need(type(b) is str and SHA.fullmatch(b) is not None and
         type(h) is str and SHA.fullmatch(h) is not None and
         SHA.fullmatch(main_sha) is not None and
         SHA.fullmatch(bot_sha) is not None, "PR_SHA_MALFORMED")
    need(b == main_sha, "BOT_BASE_NOT_CURRENT_MAIN")
    need(h == bot_sha, "BOT_HEAD_NOT_REMOTE_REF")
    need(h != b, "BOT_EMPTY_RANGE")
    return b, h


def own_checkout_base_ok(current_main: str) -> None:
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return
    # GH pull_request checkout executes synthetic merge tree. Parent 1 is the
    # actual protected-base object, not user-controlled PR code.
    values = git(["rev-list", "--parents", "-n", "1", "HEAD"], cap=1024)
    parents = values.decode("ascii").strip().split()
    need(bool(parents) and (parents[0] == current_main or
         (len(parents) == 3 and parents[1] == current_main)),
         "OWN_PR_MERGE_BASE_STALE")


def trusted_files(current_main: str, *,
                  review: str = HISTORICAL_REVIEW) -> tuple[object, dict, dict]:
    need(SHA.fullmatch(current_main) is not None, "MAIN_SHA_MALFORMED")
    need(review in WITNESSES, "UNKNOWN_PIN_REVIEW")
    classifier = ROOT / CLASSIFIER_PATH
    qualifier = ROOT / QUALIFIER_PATH
    witness = ROOT / WITNESSES[review]
    for path in (classifier, qualifier, witness):
        need(path.is_file() and not path.is_symlink() and
             0 < path.stat().st_size < MAX_BYTES, "TRUSTED_FILE_MISSING")
        name = path.relative_to(ROOT).as_posix()
        protected_bytes = git(["show", current_main + ":" + name])
        need(path.read_bytes() == protected_bytes,
             "PR_SUPPLIED_TRUSTED_POLICY_DRIFT")
    raw = witness.read_bytes()
    expected = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs)
    need(type(expected) is dict and
         expected.get("schema_version") == (1 if review == HISTORICAL_REVIEW else 2) and
         expected.get("source_pr") == BOT_PR and
         (review == HISTORICAL_REVIEW or expected.get("review_id") == review) and
         type(expected.get("source_observed_main_sha")) is str and
         SHA.fullmatch(expected["source_observed_main_sha"]) is not None and
         type(expected.get("source_bot_head_sha")) is str and
         SHA.fullmatch(expected["source_bot_head_sha"]) is not None,
         "FROZEN_WITNESS_INVALID")
    spec = importlib.util.spec_from_file_location("trusted_m1_t0", classifier)
    need(spec is not None and spec.loader is not None,
         "TRUSTED_CLASSIFIER_LOADER_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hashes = {
        "trusted_classifier_sha256": hashlib.sha256(classifier.read_bytes()).hexdigest(),
        "trusted_qualifier_sha256": hashlib.sha256(qualifier.read_bytes()).hexdigest(),
        "bot_patch_witness_sha256": hashlib.sha256(raw).hexdigest(),
        "trusted_classifier_git_blob": git_sha(
            ["rev-parse", current_main + ":" + CLASSIFIER_PATH]),
    }
    return module, expected, hashes


def canonical_witness_digest(t0: object, witness: dict, *,
                             review: str = HISTORICAL_REVIEW) -> str:
    """Freeze approved workflow+pin content, independent of bot Git ref rebases.

    Every pair must be a previously reviewed first-party T0 action update.
    No PR HEAD code or unbounded ref revision is accepted as authority.
    """
    files = witness.get("files")
    need(review in WITNESSES, "UNKNOWN_PIN_REVIEW")
    count_files, count_pins = witness.get("workflow_count"), witness.get("pin_replacements")
    need(type(count_files) is int and 0 < count_files <= t0.MAX_FILES and
         type(count_pins) is int and 0 < count_pins <= t0.MAX_FILES * t0.MAX_EDITS_PER_FILE,
         "WITNESS_COUNT_BOUND")
    if review == HISTORICAL_REVIEW:
        need(count_files == 55 and count_pins == 108, "HISTORICAL_WITNESS_COUNT_DRIFT")
    need(type(files) is list and len(files) == count_files, "WITNESS_FILE_COUNT_DRIFT")
    records: list[dict] = []
    seen: set[str] = set()
    count = 0
    for entry in files:
        need(type(entry) is dict and set(entry) == {"path", "pairs"},
             "WITNESS_ENTRY_SCHEMA_DRIFT")
        path = entry["path"]
        need(type(path) is str and
             re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.yml", path)
             is not None and path not in seen, "WITNESS_PATH_OR_DUPLICATE")
        seen.add(path)
        pairs = entry["pairs"]
        need(type(pairs) is list and 0 < len(pairs) <= 70,
             "WITNESS_PAIR_COUNT_DRIFT")
        edits = []
        for pair in pairs:
            need(type(pair) is list and len(pair) == 2 and
                 all(type(line) is str and 0 < len(line) < 300
                     for line in pair), "WITNESS_UNTRUSTED_LINE_PAIR")
            pin = t0.authorized_line(pair[0] + "\n", pair[1] + "\n", review=review)
            need(pin is not None, "WITNESS_UNAPPROVED_ACTION_PIN")
            action, old_pin, new_pin = pin
            edits.append({"action": action, "old": old_pin, "new": new_pin})
            count += 1
        records.append({"path": path, "edits": edits})
    need(count == count_pins, "WITNESS_PIN_REPLACEMENT_COUNT_DRIFT")
    records.sort(key=lambda r: r["path"])
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def receipt(decision: str, reason: str, *, current_main: str = "",
            bot_base: str = "", bot_head: str = "",
            actual_tree_checked: bool = False, extra: dict | None = None) -> dict:
    result = {
        "schema_version": 1, "decision": decision, "reason": reason,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protected_main_sha": current_main, "bot_base_sha": bot_base,
        "bot_head_sha": bot_head,
        "actual_bot_git_tree_checked": actual_tree_checked,
        "automated_bypass_enabled": False,
        "scientific_experiment_executed": False,
        "action_supply_chain_attested": False,
        "ssc305_or_physical_hil_qualified": False,
        "public_sdk_3x_admitted": False,
    }
    if extra:
        result.update(extra)
    return result


@contextlib.contextmanager
def t0_exact_checkout_trust():
    """Limit subprocess Git safe.directory to THIS checkout, never globally."""
    names = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0")
    need(all(not os.environ.get(x) for x in names),
         "EXTERNAL_GIT_CONFIG_ENV_NOT_TRUSTED")
    try:
        os.environ["GIT_CONFIG_COUNT"] = "1"
        os.environ["GIT_CONFIG_KEY_0"] = "safe.directory"
        os.environ["GIT_CONFIG_VALUE_0"] = str(ROOT)
        yield
    finally:
        for x in names:
            os.environ.pop(x, None)


def actual_matches_expected(actual: dict, expected: dict) -> None:
    need(actual.get("pin_only") is True and
         actual.get("decision") == "SCIENCE_NOT_EXECUTED_NON_MEASUREMENT_MAINTENANCE" and
         type(actual.get("files_checked")) is int and
         type(actual.get("replacements")) is int and
         HEX64.fullmatch(actual.get("pin_diff_sha256", "")) is not None,
         "BOT_ACTUAL_GIT_DIFF_NOT_PIN_ONLY")
    need(all(actual.get(key) == expected.get(key) for key in
             ("files_checked", "replacements", "pin_diff_sha256")),
         "BOT_PIN_DIFF_NOT_COMPLETE_REVIEWED_BASE_TRANSITION")


def live_probe(*, review: str = HISTORICAL_REVIEW) -> dict:
    """Do not trust, check out or run the bot's code; its Git objects are DATA."""
    current_main = bot_base = bot_head = ""
    try:
        current_main, bot_head = remote_heads()
        own_checkout_base_ok(current_main)
        before = fetch_public_bot_pr()
        base, head = snapshot_metadata(before, current_main, bot_head)
        bot_base = base
        t0, witness, hashes = trusted_files(current_main, review=review)
        frozen_digest = canonical_witness_digest(t0, witness, review=review)
        # Fetch *only* exact sha objects from a hardcoded same-repo URL.
        # No remote executable is sourced, imported, checked out or run.
        git(["fetch", "--no-tags", "--no-write-fetch-head",
             "--recurse-submodules=no", GIT_REMOTE, base, head],
            cap=8192)
        actual_base = git_sha(["rev-parse", base + "^{commit}"])
        actual_head = git_sha(["rev-parse", head + "^{commit}"])
        need(actual_base == base and actual_head == head,
             "FETCHED_BOT_GIT_OBJECT_MISMATCH")
        base_tree = git_sha(["rev-parse", base + "^{tree}"])
        head_tree = git_sha(["rev-parse", head + "^{tree}"])
        with temporary_current_directory(ROOT), t0_exact_checkout_trust():
            result = t0.classify_repo(base, head, review=review)
            if review == HISTORICAL_REVIEW:
                expected = {"files_checked": witness["workflow_count"],
                            "replacements": witness["pin_replacements"],
                            "pin_diff_sha256": frozen_digest}
            else:
                # The newly reviewed contract binds every use site in this
                # exact protected tree, not a historical 55/125 size constant.
                expected = t0.expected_repo(base, review=review)
        actual_matches_expected(result, expected)
        # Read both PR metadata and canonical public branch refs again after
        # parsing the bot OIDs. An in-flight rebase *must* invalidate result.
        after = fetch_public_bot_pr()
        newer_main, newer_head = remote_heads()
        need((newer_main, newer_head) == (current_main, bot_head) and
             snapshot_metadata(after, newer_main, newer_head) == (base, head),
             "BOT_REF_RACE_OR_REBASE")
        return receipt(
            ADMITTED, "ACTUAL_TRUSTED_GIT_PIN_SCOPE_ONLY",
            current_main=current_main, bot_base=base, bot_head=head,
            actual_tree_checked=True,
            extra={
                "actual_base_tree": base_tree, "actual_bot_tree": head_tree,
                "actual_merge_base": result["merge_base"],
                "review_id": review,
                "file_count": result["files_checked"],
                "pin_replacements": result["replacements"],
                "pin_diff_sha256": result["pin_diff_sha256"],
                "frozen_witness_content_diff_sha256": frozen_digest,
                "expected_current_base_pin_diff_sha256": expected["pin_diff_sha256"],
                "historical_witness_matches_current_diff": frozen_digest == result["pin_diff_sha256"],
                "bot_patch_witness_sha256": hashes["bot_patch_witness_sha256"],
                "trusted_classifier_sha256": hashes["trusted_classifier_sha256"],
                "trusted_qualifier_sha256": hashes["trusted_qualifier_sha256"],
                "trusted_classifier_git_blob": hashes["trusted_classifier_git_blob"],
            })
    except (AdmissionDenied, ValueError, OSError, UnicodeError,
            subprocess.SubprocessError, KeyError, TypeError) as exc:
        # Safe negative is a meaningful, auditable result, not a scientific
        # PASS or a request to bypass a failed upstream scope check.
        code = str(exc)[:100]
        if not re.fullmatch(r"[A-Za-z0-9_]+", code):
            code = "MALFORMED_OR_INACCESSIBLE_SOURCE"
        return receipt(
            REJECTED, code, current_main=current_main,
            bot_base=bot_base, bot_head=bot_head, extra={"review_id": review})


@contextlib.contextmanager
def temporary_current_directory(where: Path):
    """Python 3.10-compatible, exception-safe Git fixture isolation."""
    previous = Path.cwd()
    try:
        os.chdir(where)
        yield
    finally:
        os.chdir(previous)


def fake_bot(base: str, head: str) -> dict:
    return {
        "number": BOT_PR, "state": "open", "draft": False,
        "user": {"login": BOT_ACTOR, "id": BOT_ACTOR_ID, "type": "Bot"},
        "base": {"ref": "main", "sha": base, "repo": {"full_name": REPO}},
        "head": {"ref": BOT_REF, "sha": head, "repo": {"full_name": REPO}},
    }


def current_base_transition_self_test(t0: object) -> None:
    """Actual Git proofs of growing base sites, complete updates and denials."""
    old_upload, new_upload, _ = t0.REVIEWED[CURRENT_REVIEW]["actions/upload-artifact"]
    old_codeql, new_codeql, _ = t0.REVIEWED[CURRENT_REVIEW]["github/codeql-action/init"]
    row = "      - uses: actions/upload-artifact@" + old_upload + " # v7.0.1\n"
    before = ("jobs:\n  example:\n    steps:\n" + row +
              "      - uses: github/codeql-action/init@" + old_codeql + " # v4\n")

    def update(source: str) -> str:
        return source.replace(old_upload, new_upload).replace(
            "# v7.0.1", "# v7.0.2").replace(old_codeql, new_codeql)

    with tempfile.TemporaryDirectory(prefix="t1-m1-current-base-") as temp:
        area = Path(temp)
        git(["init", "-q"], cwd=area)
        git(["config", "user.email", "offline@example.invalid"], cwd=area)
        git(["config", "user.name", "Offline Probe"], cwd=area)
        target = area / ".github/workflows/probe.yml"
        target.parent.mkdir(parents=True)

        def commit(source: str, message: str) -> str:
            target.write_text(source, encoding="utf-8")
            git(["add", "."], cwd=area)
            git(["commit", "-qm", message], cwd=area)
            return git_sha(["rev-parse", "HEAD"], cwd=area)

        start = commit(before, "reviewed base with two sites")
        end = commit(update(before), "complete reviewed update")
        with temporary_current_directory(area):
            expected = t0.expected_repo(start, review=CURRENT_REVIEW)
            actual_matches_expected(t0.classify_repo(start, end, review=CURRENT_REVIEW), expected)
            need(expected["replacements"] == 2, "CURRENT_TWO_SITE_BASE_INVALID")

            git(["reset", "--hard", start], cwd=area)
            additional = ("      - name: Newly reviewed base upload site\n"
                          "        uses: actions/upload-artifact@" + old_upload + " # v7.0.1\n")
            larger = before + additional
            larger_base = commit(larger, "protected base adds an upload site")
            larger_expected = t0.expected_repo(larger_base, review=CURRENT_REVIEW)
            need(larger_expected["replacements"] == 3 and
                 larger_expected["pin_diff_sha256"] != expected["pin_diff_sha256"],
                 "CURRENT_EXPECTATION_DID_NOT_FOLLOW_EXACT_BASE")
            partial = commit(update(before) + additional, "incomplete bot proposal")
            pure_but_partial = t0.classify_repo(larger_base, partial, review=CURRENT_REVIEW)
            need(pure_but_partial["pin_only"] is True, "PARTIAL_FIXTURE_NOT_PIN_ONLY")
            try:
                actual_matches_expected(pure_but_partial, larger_expected)
            except AdmissionDenied:
                pass
            else:
                raise AdmissionDenied("PARTIAL_CURRENT_UPDATE_ADMITTED")
            complete = commit(update(larger), "complete three site proposal")
            actual_matches_expected(t0.classify_repo(larger_base, complete, review=CURRENT_REVIEW),
                                    larger_expected)
            for name, source in (
                ("mixed_permissions", "permissions: write-all\n" + update(larger)),
                ("unknown_target", update(larger).replace(new_codeql, "f" * 40)),
                ("historical_target", update(larger).replace(new_codeql, t0.TRUSTED["github/codeql-action/init"][1])),
                ("previous_target", update(larger).replace(new_codeql, t0.REVIEWED[PREVIOUS_REVIEW]["github/codeql-action/init"][1])),
            ):
                bad = commit(source, name)
                try:
                    actual_matches_expected(t0.classify_repo(larger_base, bad, review=CURRENT_REVIEW),
                                            larger_expected)
                except AdmissionDenied:
                    pass
                else:
                    raise AdmissionDenied("CURRENT_REVIEW_FALSE_ADMISSION_" + name)


def self_test() -> None:
    """No web access; test exact metadata authority and actual local Git modes."""
    base, head = "a" * 40, "b" * 40
    model = fake_bot(base, head)
    need(snapshot_metadata(model, base, head) == (base, head),
         "VALID_METADATA_REJECTED")
    mutants: list[tuple[str, dict, str, str]] = []

    def mutated(name: str, f, cur: str = base, bot: str = head) -> None:
        altered = copy.deepcopy(model)
        f(altered)
        mutants.append((name, altered, cur, bot))

    mutated("wrong_pr", lambda p: p.__setitem__("number", 713))
    mutated("wrong_actor", lambda p: p["user"].__setitem__("login", "attacker"))
    mutated("forged_bot_login", lambda p: p["user"].__setitem__("id", 1))
    mutated("wrong_actor_type", lambda p: p["user"].__setitem__("type", "User"))
    mutated("draft", lambda p: p.__setitem__("draft", True))
    mutated("closed", lambda p: p.__setitem__("state", "closed"))
    mutated("wrong_base_ref", lambda p: p["base"].__setitem__("ref", "dev"))
    mutated("wrong_head_ref", lambda p: p["head"].__setitem__("ref", "danger"))
    mutated("fork", lambda p: p["head"]["repo"].__setitem__("full_name", "bad/repo"))
    mutated("wrong_base_repo", lambda p: p["base"]["repo"].__setitem__("full_name", "bad/repo"))
    mutated("stale_base", lambda p: None, cur="c" * 40)
    mutated("stale_head", lambda p: None, bot="d" * 40)
    mutated("empty", lambda p: p["head"].__setitem__("sha", base), bot=base)
    mutated("floating_tag", lambda p: p["head"].__setitem__("sha", "v7.0.2"))
    mutated("short_sha", lambda p: p["base"].__setitem__("sha", "abc123"))
    mutated("upper_sha", lambda p: p["head"].__setitem__("sha", head.upper()))
    mutated("missing_head_repo", lambda p: p["head"].pop("repo"))
    mutated("missing_base", lambda p: p.pop("base"))
    mutated("invalid_number", lambda p: p.__setitem__("number", True))
    mutated("null_head", lambda p: p.__setitem__("head", None))
    mutated("missing_user", lambda p: p.pop("user"))
    mutated("wrong_pr_repo", lambda p: p["base"]["repo"].__setitem__("full_name", "openai/other"))
    for name, cand, cur, bot in mutants:
        try:
            snapshot_metadata(cand, cur, bot)
        except AdmissionDenied:
            continue
        raise AdmissionDenied("FALSE_BOT_METADATA_ADMISSION_" + name)

    try:
        json.loads('{"a":1,"a":2}', object_pairs_hook=strict_pairs)
    except AdmissionDenied:
        pass
    else:
        raise AdmissionDenied("DUPLICATE_JSON_ADMITTED")

    # Positive and negative tests of the frozen, old-ref-independent digest.
    # It must be exactly the unchanged reviewed 55-workflow/108-pin content.
    raw = (HERE / "workflow_pin_only_bot714_exact_t1.json").read_bytes()
    frozen = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_pairs)
    cls_spec = importlib.util.spec_from_file_location(
        "frozen_m1_witness_t0", HERE / "workflow_pin_only_scope.py")
    need(cls_spec is not None and cls_spec.loader is not None,
         "T0_WITNESS_CLASSIFIER_LOADER_UNAVAILABLE")
    orig = importlib.util.module_from_spec(cls_spec)
    cls_spec.loader.exec_module(orig)
    digest = canonical_witness_digest(orig, frozen)
    need(HEX64.fullmatch(digest) is not None,
         "FROZEN_DIFF_DIGEST_INVALID")
    current_witness = json.loads((ROOT / WITNESSES[CURRENT_REVIEW]).read_text(
        encoding="utf-8"), object_pairs_hook=strict_pairs)
    current_digest = canonical_witness_digest(orig, current_witness, review=CURRENT_REVIEW)
    need(HEX64.fullmatch(current_digest) is not None and current_digest != digest,
         "CURRENT_WITNESS_CONFUSED_WITH_HISTORICAL")
    previous_witness = json.loads((ROOT / WITNESSES[PREVIOUS_REVIEW]).read_text(
        encoding="utf-8"), object_pairs_hook=strict_pairs)
    previous_digest = canonical_witness_digest(orig, previous_witness, review=PREVIOUS_REVIEW)
    need(HEX64.fullmatch(previous_digest) is not None and
         len({digest, previous_digest, current_digest}) == 3,
         "PREVIOUS_WITNESS_REVIEW_NOT_INDEPENDENT")
    for selected, other_witness in ((PREVIOUS_REVIEW, current_witness),
                                    (CURRENT_REVIEW, previous_witness)):
        try:
            canonical_witness_digest(orig, other_witness, review=selected)
        except AdmissionDenied:
            pass
        else:
            raise AdmissionDenied("CROSS_REVIEW_WITNESS_ADMITTED_" + selected)
    for key, payload in (
        ("unknown_action", "uses: attacker/not-a-trusted-action@" + "f" * 40),
        ("floating_tag", "uses: actions/upload-artifact@v7.0.2"),
        ("fake_pin", "uses: actions/upload-artifact@" + "f" * 40),
    ):
        altered = copy.deepcopy(frozen)
        altered["files"][0]["pairs"][0][1] = payload
        try:
            canonical_witness_digest(orig, altered)
        except AdmissionDenied:
            pass
        else:
            raise AdmissionDenied("FALSE_WITNESS_CONTENT_ADMISSION_" + key)
    for kind in ("duplicate_path", "wrong_path", "wrong_pair_count"):
        altered = copy.deepcopy(frozen)
        if kind == "duplicate_path":
            altered["files"][1]["path"] = altered["files"][0]["path"]
        elif kind == "wrong_path":
            altered["files"][0]["path"] = "src/shipping.c"
        else:
            altered["files"][0]["pairs"] = []
        try:
            canonical_witness_digest(orig, altered)
        except AdmissionDenied:
            pass
        else:
            raise AdmissionDenied("FALSE_WITNESS_SHAPE_ADMISSION_" + kind)

    # Execute the *original* first-party T0 against actual Git objects in an
    # isolated tiny local repository; never need to fetch untrusted bot code.
    classifier = HERE / "workflow_pin_only_scope.py"
    spec = importlib.util.spec_from_file_location("actual_tree_test_t0", classifier)
    need(spec is not None and spec.loader is not None, "T0_MISSING_IN_TEST")
    t0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t0)
    current_base_transition_self_test(t0)
    old, new, _ = t0.TRUSTED["actions/upload-artifact"]
    with tempfile.TemporaryDirectory(prefix="t1-m1-offline-") as tmp:
        area = Path(tmp)
        git(["init", "-q"], cwd=area)
        git(["config", "user.email", "offline@example.invalid"], cwd=area)
        git(["config", "user.name", "Offline Probe"], cwd=area)
        target = area / ".github/workflows/probe.yml"
        target.parent.mkdir(parents=True)
        before = ("jobs:\n  example:\n    steps:\n"
                  "      - uses: actions/upload-artifact@" + old + " # v7.0.1\n")
        target.write_text(before, encoding="utf-8")
        git(["add", "."], cwd=area)
        git(["commit", "-qm", "base"], cwd=area)
        start = git_sha(["rev-parse", "HEAD"], cwd=area)
        target.write_text(before.replace(old, new).replace(
            "# v7.0.1", "# v7.0.2"), encoding="utf-8")
        git(["add", "."], cwd=area)
        git(["commit", "-qm", "pin only"], cwd=area)
        end = git_sha(["rev-parse", "HEAD"], cwd=area)
        with temporary_current_directory(area):
            good = t0.classify_repo(start, end)
            need(good.get("pin_only") is True and good.get("files_checked") == 1
                 and good.get("replacements") == 1, "REAL_GIT_VALID_PIN_REJECTED")
            target.chmod(0o755)
            git(["add", "."], cwd=area)
            git(["commit", "-qm", "executable drift"], cwd=area)
            mode_sha = git_sha(["rev-parse", "HEAD"], cwd=area)
            bad = t0.classify_repo(start, mode_sha)
            need(bad.get("pin_only") is False, "REAL_GIT_MODE_DRIFT_ADMITTED")
    negative = receipt(REJECTED, "BOT_BASE_NOT_CURRENT_MAIN", current_main=base)
    need(negative["automated_bypass_enabled"] is False and
         negative["scientific_experiment_executed"] is False and
         negative["actual_bot_git_tree_checked"] is False,
         "NEGATIVE_RECEIPT_PROMOTED")
    print("T1_M1_ACTUAL_GIT_TREE_SELF_TEST_PASS metadata_negatives=" +
          str(len(mutants) + 1) + " real_git_mode_negatives=1 " +
          "witness_diff_negatives=6 previous_review_cross_negatives=2 "
          "current_base_transition_negatives=5")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--self-test", action="store_true")
    modes.add_argument("--probe-real", action="store_true")
    parser.add_argument("--review", choices=tuple(WITNESSES), default=HISTORICAL_REVIEW)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            result = live_probe(review=args.review)
            print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                             allow_nan=False))
    except (AdmissionDenied, ValueError, TypeError, OSError, UnicodeError) as exc:
        print("T1_M1_ACTUAL_BOT_TREE_QUALIFIER_NOT_ADMITTED: " + str(exc)[:160],
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
