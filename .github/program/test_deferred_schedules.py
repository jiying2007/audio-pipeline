#!/usr/bin/env python3
"""Live YAML/Bash policy regression: unavailable HIL/Extended Real must not look green.

Execute ONLY the hosted availability/dispatch-guard shell snippets with synthetic
environment and temporary GITHUB_OUTPUT. Never start a runner, use gh or fetch
data. This does not certify a real hardware lab or dataset.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / ".github/workflows/hil-soak.yml"
EXTENDED = ROOT / ".github/workflows/extended-real-automation.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bash_step(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    heading = f"      - name: {name}\n"
    require(source.count(heading) == 1, "missing/duplicate action step: " + name)
    block = source.split(heading, 1)[1]
    marker = "\n        run: |\n"
    require(block.count(marker) >= 1 and marker in block.split("\n      - name:", 1)[0],
            "step run block missing: " + name)
    body = block.split(marker, 1)[1]
    selected = []
    for line in body.splitlines():
        if line and not line.startswith("          "):
            break  # next workflow step or job; none of it is executed
        selected.append(line)
    script = textwrap.dedent("\n".join(selected) + "\n")
    require(script.startswith("set -euo pipefail\n"), "policy must remain Bash fail-closed")
    return script


def evaluate(script: str, *, event: str, hil_enabled: str = "",
             extended_enabled: str = "", manual_sha: str = "",
             release_ref: str = "", release_tag: str = "", event_type: str = "",
             expected_success: bool, expected_marker: str,
             expected_output: Optional[str] = None) -> None:
    with tempfile.TemporaryDirectory(prefix="audio-availability-") as home:
        output = Path(home) / "github-output"
        output.touch()
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": home,
            "LC_ALL": "C",
            "GITHUB_OUTPUT": str(output),
            "EVENT_NAME": event,
            "EVENT_TYPE": event_type,
            "RELEASE_REF": release_ref,
            "RELEASE_TAG": release_tag,
            "HIL_ENABLED": hil_enabled,
            "EXTENDED_REAL_ENABLED": extended_enabled,
            "EXTENDED_REAL_DATA_ROOT": "",
            "MANUAL_SHA": manual_sha,
        }
        result = subprocess.run(["bash", "-c", script], cwd=ROOT, env=env,
                                capture_output=True, text=True, timeout=5)
        require((result.returncode == 0) == expected_success,
                f"policy false-green/false-red: {event}, exit={result.returncode}, stderr={result.stderr}")
        output_text = output.read_text(encoding="utf-8")
        combined = result.stdout + "\n" + result.stderr
        require(expected_marker in combined if expected_marker else True,
                f"missing expected availability diagnosis: {expected_marker}")
        if expected_output is not None:
            require(output_text == expected_output,
                    f"wrong branch allocation authority: {output_text!r}")


def self_test() -> None:
    hil = bash_step(HIL, "Enforce HIL availability policy")
    ext = bash_step(EXTENDED, "Resolve exact source and automation profile")
    for message, text in (
        ("HIL_SCHEDULE_SKIPPED_DISABLED", HIL.read_text(encoding="utf-8")),
        ("EXTENDED_REAL_SCHEDULE_SKIPPED_DISABLED", EXTENDED.read_text(encoding="utf-8")),
    ):
        require(message not in text, "disabled scheduled green skip reintroduced: " + message)
    require("if: needs.availability.outputs.run == 'true'" in HIL.read_text(encoding="utf-8"),
            "HIL runner guard lost")
    require("if: steps.request.outputs.run == 'true'" in EXTENDED.read_text(encoding="utf-8"),
            "Extended Real dispatch guard lost")
    exact_sha = "1" * 40
    # HIL accepts no implicit release, scheduled event, or unreviewed source.
    for event in ("schedule", "repository_dispatch", "push", "pull_request"):
        evaluate(hil, event=event, hil_enabled="true", manual_sha=exact_sha,
                 expected_success=False, expected_marker="HIL_RESEARCH_MANUAL_ONLY",
                 expected_output="")
    # Explicit manual requests must fail when physical HIL is unavailable.
    for enabled in ("", "false"):
        evaluate(hil, event="workflow_dispatch", hil_enabled=enabled,
                 manual_sha=exact_sha, expected_success=False,
                 expected_marker="HIL_REQUIRED_BUT_DISABLED",
                 expected_output="run=false\n")
    evaluate(hil, event="workflow_dispatch", hil_enabled="true",
             manual_sha=exact_sha, expected_success=True,
             expected_marker="", expected_output="run=true\n")
    evaluate(hil, event="workflow_dispatch", hil_enabled="true",
             manual_sha="bad", expected_success=False,
             expected_marker="source_sha must be a 40-character commit SHA",
             expected_output="")

    # Extended Real retains an independently source/rights-bounded
    # availability contract, never becoming HIL hardware evidence.
    for event in ("schedule", "workflow_dispatch", "repository_dispatch"):
        evaluate(ext, event=event, extended_enabled="false", expected_success=False,
                 expected_marker="EXTENDED_REAL_REQUIRED_BUT_DISABLED",
                 expected_output="")

    # Counterexample: a disabled HIL runner may not be reclassified as
    # success even when the original failure diagnosis is echoed.
    old = (
        'echo "HIL_REQUIRED_BUT_DISABLED: manual scientific experiment requires '
        'an actual isolated audio-target runner and HIL_ENABLED=true." >&2\n'
        '  exit 1'
    )
    require(old in hil, "cannot construct research HIL false-green negative")
    mutated = hil.replace(old, old.replace("exit 1", "exit 0"), 1)
    try:
        evaluate(mutated, event="workflow_dispatch", hil_enabled="false",
                 manual_sha=exact_sha, expected_success=False,
                 expected_marker="HIL_REQUIRED_BUT_DISABLED",
                 expected_output="run=false\n")
    except AssertionError:
        pass
    else:
        raise AssertionError("known false-green manual HIL policy unexpectedly qualified")
    print("manual HIL and scheduled Extended Real availability: fail-visible PASS")


if __name__ == "__main__":
    self_test()
