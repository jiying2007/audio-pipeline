#!/usr/bin/env python3
"""Live YAML/Bash policy regression: unavailable HIL/Extended Real must not look green.

Execute ONLY the hosted availability/dispatch-guard shell snippets with synthetic
environment and temporary GITHUB_OUTPUT. Never start a runner, use gh or fetch
data. This does not certify a real hardware lab or dataset.
"""
from __future__ import annotations

import os
from pathlib import Path
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
             expected_output: str | None = None) -> None:
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
    # The unavailable scheduled controllers are expected FAILURES, not
    # successfully skipped runners or a synthetic PASS.
    evaluate(hil, event="schedule", hil_enabled="false", expected_success=False,
             expected_marker="HIL_REQUIRED_BUT_DISABLED", expected_output="run=false\n")
    evaluate(hil, event="schedule", hil_enabled="", expected_success=False,
             expected_marker="HIL_REQUIRED_BUT_DISABLED", expected_output="run=false\n")
    evaluate(hil, event="schedule", hil_enabled="true", expected_success=True,
             expected_marker="", expected_output="run=true\n")
    evaluate(hil, event="repository_dispatch", event_type="hil-post-release",
             release_ref=exact_sha, release_tag="v1.0.0", hil_enabled="false",
             expected_success=False, expected_marker="HIL_REQUIRED_BUT_DISABLED",
             expected_output="run=false\n")
    # Reviewed exact-SHA manual HIL bring-up is intentionally an exception to
    # HIL_ENABLED, but its later real target job still requires a runner.
    evaluate(hil, event="workflow_dispatch", hil_enabled="false",
             manual_sha=exact_sha, expected_success=True, expected_marker="",
             expected_output="run=true\n")
    evaluate(hil, event="workflow_dispatch", hil_enabled="false",
             manual_sha="bad", expected_success=False,
             expected_marker="source_sha must be a 40-character commit SHA",
             expected_output="")
    for event in ("schedule", "workflow_dispatch", "repository_dispatch"):
        evaluate(ext, event=event, extended_enabled="false", expected_success=False,
                 expected_marker="EXTENDED_REAL_REQUIRED_BUT_DISABLED",
                 expected_output="")
    # Negative control: a rewritten policy that exits zero when HIL is absent
    # must be distinguishable from the exact-source fail-visible contract.
    old = 'echo "HIL_REQUIRED_BUT_DISABLED: event=$EVENT_NAME; set HIL_ENABLED=true only after an isolated audio-target runner is online." >&2\n  exit 1'
    require(old in hil, "cannot construct controller false-green negative")
    mutated = hil.replace(old, old.replace("exit 1", "exit 0"), 1)
    try:
        evaluate(mutated, event="schedule", hil_enabled="false",
                 expected_success=False, expected_marker="HIL_REQUIRED_BUT_DISABLED",
                 expected_output="run=false\n")
    except AssertionError:
        pass
    else:
        raise AssertionError("known false-green controller unexpectedly qualified")
    print("scheduled HIL/Extended Real availability: fail-visible self-test PASS")


if __name__ == "__main__":
    self_test()
