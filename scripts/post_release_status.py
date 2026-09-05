#!/usr/bin/env python3
"""Classify and bind post-release laboratory qualification evidence."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TERMINAL_STATUSES = {"completed"}
FAIL_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required"}


def classify(enabled: str, conclusion: str, blocked_status: str) -> str:
    if enabled.strip().lower() != "true":
        return blocked_status
    conclusion = conclusion.strip().lower()
    if conclusion == "success":
        return "PASS"
    if conclusion in FAIL_CONCLUSIONS:
        return "FAIL"
    if conclusion in {"queued", "in_progress", "waiting", "pending", ""}:
        return "PENDING"
    return "UNKNOWN"


def build(source_sha: str, tag: str, hil_enabled: str, hil_conclusion: str,
          extended_enabled: str, extended_conclusion: str) -> dict:
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be exact 40-hex commit")
    if not tag.startswith("v"):
        raise ValueError("tag must begin with v")
    return {
        "schema_version": 1,
        "source_sha": source_sha,
        "tag": tag,
        "software_release": "PASS",
        "lab_qualification": {
            "hil": classify(hil_enabled, hil_conclusion, "BLOCKED_RUNNER"),
            "extended_real": classify(extended_enabled, extended_conclusion, "BLOCKED_CONFIG"),
        },
    }


def _run_list(payload: dict) -> list[dict]:
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("workflow run payload must contain workflow_runs list")
    return runs


def _compact(run: dict | None, authority: str) -> dict:
    if run is None:
        return {
            "authority": authority,
            "run_id": None,
            "url": None,
            "event": None,
            "display_title": None,
            "head_sha": None,
            "status": "pending",
            "conclusion": None,
        }
    return {
        "authority": authority,
        "run_id": run.get("id"),
        "url": run.get("html_url"),
        "event": run.get("event"),
        "display_title": run.get("display_title"),
        "head_sha": run.get("head_sha"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
    }


def _select(payload: dict, exact_title: str, legacy_title: str | None,
            source_sha: str, exact_requires_source: bool = False) -> dict | None:
    runs = _run_list(payload)
    for run in runs:
        if run.get("display_title") != exact_title:
            continue
        if exact_requires_source and run.get("head_sha") != source_sha:
            continue
        return run
    if legacy_title:
        for run in runs:
            if run.get("display_title") == legacy_title and run.get("head_sha") == source_sha:
                return run
    return None


def _terminal(run: dict | None) -> bool:
    return bool(run and run.get("status") in TERMINAL_STATUSES and run.get("conclusion"))


def resolve_runs(source_sha: str, tag: str, hil_enabled: str,
                 extended_enabled: str, hil_payload: dict,
                 extended_automation_payload: dict,
                 extended_validation_payload: dict) -> dict:
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be exact 40-hex commit")
    if not tag.startswith("v"):
        raise ValueError("tag must begin with v")

    hil = _select(
        hil_payload,
        f"hil-post-release {tag}",
        "hil-post-release",
        source_sha,
        exact_requires_source=True,
    )
    ext_auto = _select(
        extended_automation_payload,
        f"extended-real-post-release {tag}",
        "extended-real-post-release",
        source_sha,
        exact_requires_source=True,
    )
    ext_validation = _select(
        extended_validation_payload,
        f"extended-real-validation {source_sha}",
        None,
        source_sha,
    )

    hil_is_enabled = hil_enabled.strip().lower() == "true"
    ext_is_enabled = extended_enabled.strip().lower() == "true"
    ready = _terminal(hil)
    hil_conclusion = str(hil.get("conclusion") or "") if hil else ""

    if ready and not hil_is_enabled and hil_conclusion == "success":
        raise ValueError("disabled HIL post-release gate unexpectedly succeeded")

    ext_authority = "extended-real-automation-disabled-gate"
    ext_run = ext_auto
    if ext_is_enabled:
        if _terminal(ext_validation):
            ext_authority = "extended-real-validation"
            ext_run = ext_validation
        elif _terminal(ext_auto) and str(ext_auto.get("conclusion") or "") in FAIL_CONCLUSIONS:
            ext_authority = "extended-real-automation-control-plane"
            ext_run = ext_auto
        else:
            ready = False
            ext_authority = "extended-real-validation-pending"
            ext_run = ext_validation or ext_auto
    else:
        if not _terminal(ext_auto):
            ready = False
        elif str(ext_auto.get("conclusion") or "") == "success":
            raise ValueError("disabled Extended Real post-release gate unexpectedly succeeded")

    ext_conclusion = str(ext_run.get("conclusion") or "") if ext_run else ""
    return {
        "schema_version": 1,
        "source_sha": source_sha,
        "tag": tag,
        "ready": ready,
        "hil": _compact(hil, "hil-tiered-soak"),
        "extended_real": _compact(ext_run, ext_authority),
        "hil_conclusion": hil_conclusion,
        "extended_real_conclusion": ext_conclusion,
    }


def _fake_run(run_id: int, title: str, source_sha: str, status: str,
              conclusion: str | None, event: str) -> dict:
    return {
        "id": run_id,
        "html_url": f"https://example.invalid/runs/{run_id}",
        "event": event,
        "display_title": title,
        "head_sha": source_sha,
        "status": status,
        "conclusion": conclusion,
    }


def self_test() -> None:
    assert classify("", "failure", "BLOCKED_RUNNER") == "BLOCKED_RUNNER"
    assert classify("true", "success", "BLOCKED_RUNNER") == "PASS"
    assert classify("true", "failure", "BLOCKED_RUNNER") == "FAIL"
    assert classify("true", "", "BLOCKED_RUNNER") == "PENDING"
    result = build("a" * 40, "v2.3.6", "", "failure", "true", "success")
    assert result["lab_qualification"] == {"hil": "BLOCKED_RUNNER", "extended_real": "PASS"}

    sha = "b" * 40
    tag = "v2.3.11"
    legacy_hil = {"workflow_runs": [_fake_run(1, "hil-post-release", sha, "completed", "failure", "repository_dispatch")]}
    legacy_ext = {"workflow_runs": [_fake_run(2, "extended-real-post-release", sha, "completed", "failure", "repository_dispatch")]}
    empty = {"workflow_runs": []}
    resolved = resolve_runs(sha, tag, "", "", legacy_hil, legacy_ext, empty)
    assert resolved["ready"] is True
    assert resolved["hil"]["run_id"] == 1
    assert resolved["extended_real"]["authority"] == "extended-real-automation-disabled-gate"

    current_hil = {"workflow_runs": [_fake_run(3, f"hil-post-release {tag}", sha, "completed", "success", "repository_dispatch")]}
    current_auto = {"workflow_runs": [_fake_run(4, f"extended-real-post-release {tag}", sha, "completed", "success", "repository_dispatch")]}
    current_validation = {"workflow_runs": [_fake_run(5, f"extended-real-validation {sha}", "d" * 40, "completed", "success", "workflow_dispatch")]}
    resolved = resolve_runs(sha, tag, "true", "true", current_hil, current_auto, current_validation)
    assert resolved["ready"] is True
    assert resolved["extended_real"]["run_id"] == 5
    assert resolved["extended_real"]["authority"] == "extended-real-validation"

    pending_validation = {"workflow_runs": [_fake_run(6, f"extended-real-validation {sha}", "d" * 40, "in_progress", None, "workflow_dispatch")]}
    resolved = resolve_runs(sha, tag, "true", "true", current_hil, current_auto, pending_validation)
    assert resolved["ready"] is False
    assert resolved["extended_real"]["authority"] == "extended-real-validation-pending"

    failed_auto = {"workflow_runs": [_fake_run(7, f"extended-real-post-release {tag}", sha, "completed", "failure", "repository_dispatch")]}
    resolved = resolve_runs(sha, tag, "true", "true", current_hil, failed_auto, empty)
    assert resolved["ready"] is True
    assert resolved["extended_real"]["authority"] == "extended-real-automation-control-plane"
    assert resolved["extended_real_conclusion"] == "failure"

    wrong_source_control = {
        "workflow_runs": [_fake_run(8, f"extended-real-post-release {tag}", "c" * 40, "completed", "failure", "repository_dispatch")]
    }
    resolved = resolve_runs(sha, tag, "true", "true", current_hil, wrong_source_control, empty)
    assert resolved["ready"] is False
    assert resolved["extended_real"]["authority"] == "extended-real-validation-pending"
    assert resolved["extended_real"]["run_id"] is None

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "status.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        assert json.loads(path.read_text())["software_release"] == "PASS"
    print("post release status self-test: OK")


def _load_json(path: Path | None, name: str) -> dict:
    if path is None:
        raise ValueError(f"{name} is required")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha")
    parser.add_argument("--tag")
    parser.add_argument("--hil-enabled", default="")
    parser.add_argument("--hil-conclusion", default="")
    parser.add_argument("--extended-real-enabled", default="")
    parser.add_argument("--extended-real-conclusion", default="")
    parser.add_argument("--hil-runs", type=Path)
    parser.add_argument("--extended-automation-runs", type=Path)
    parser.add_argument("--extended-validation-runs", type=Path)
    parser.add_argument("--resolve-runs", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.source_sha or not args.tag:
        parser.error("--source-sha and --tag are required")

    if args.resolve_runs:
        result = resolve_runs(
            args.source_sha,
            args.tag,
            args.hil_enabled,
            args.extended_real_enabled,
            _load_json(args.hil_runs, "--hil-runs"),
            _load_json(args.extended_automation_runs, "--extended-automation-runs"),
            _load_json(args.extended_validation_runs, "--extended-validation-runs"),
        )
    else:
        result = build(
            args.source_sha, args.tag, args.hil_enabled, args.hil_conclusion,
            args.extended_real_enabled, args.extended_real_conclusion,
        )

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
