#!/usr/bin/env python3
"""Shared fail-closed checks for live-or-retired one-shot research workflows."""

from __future__ import annotations

import json
import re
from pathlib import Path

RETIREMENT_MANIFEST = Path("docs/program/terminal-workflow-retirement.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _retired_record(root: Path, relative: str) -> dict:
    data = json.loads((root / RETIREMENT_MANIFEST).read_text(encoding="utf-8"))
    matches = []
    for value in data.values():
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and item.get("path") == relative:
                matches.append(item)
    assert len(matches) == 1, (
        f"expected exactly one retirement record for {relative}, got {len(matches)}"
    )
    record = matches[0]
    blob_sha = str(record.get("blob_sha", ""))
    assert SHA_RE.fullmatch(blob_sha), f"invalid retirement blob SHA for {relative}"
    return record


def assert_contract_or_retired(root: Path, live: Path, self_name: str | None = None) -> dict | None:
    """Validate the active contract shell or its terminal retirement record."""
    relative = live.relative_to(root).as_posix()
    if not live.exists():
        return _retired_record(root, relative)

    text = live.read_text(encoding="utf-8")
    assert "\n  pull_request:\n" in text, relative
    for forbidden in ("workflow_dispatch", "push", "schedule", "workflow_call", "workflow_run"):
        assert f"\n  {forbidden}:\n" not in text, f"{relative}: {forbidden}"

    jobs_index = text.find("\njobs:")
    assert jobs_index >= 0, f"{relative}: missing jobs"
    jobs = re.findall(
        r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
        text[jobs_index + 1 :],
    )
    assert jobs == ["contract"], f"{relative}: jobs={jobs}"
    if self_name:
        assert self_name in text, f"{relative}: missing retirement test {self_name}"
    return None
