#!/usr/bin/env python3
"""End-to-end runtime fault -> APD -> triage -> diagnosis contract.

This stays repository-internal. It validates diagnostic behavior using real runtime
metadata faults and the production Flight Recorder path without changing APD v1,
shipping DSP, public APIs, or product qualification authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


CASES = {
    "capture-gap": {
        "flag": "capture_discontinuity",
        "family": "capture-io",
        "hypothesis": "capture-io",
    },
    "render-gap": {
        "flag": "render_discontinuity",
        "family": "sync-reference",
        "hypothesis": "sync-reference-path",
    },
    "clock-reset": {
        "flag": "clock_reset",
        "family": "sync-reference",
        "hypothesis": "sync-reference-path",
    },
    "xrun": {
        "flag": "xrun",
        "family": "runtime-continuity",
        "hypothesis": "runtime-continuity",
    },
    "codec-reopen": {
        "flag": "codec_reopen",
        "family": "capture-io",
        "hypothesis": "capture-io",
    },
}


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--processor", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    triage_tool = root / "tests/diagnostics/aptriage.py"
    diagnose_tool = root / "tests/diagnostics/apdiagnose.py"
    args.work_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "schema_version": 1,
        "authority": "repository-internal-diagnostic-contract-only",
        "causal_proof": False,
        "cases": [],
    }

    for case, expected in CASES.items():
        case_dir = args.work_dir / case
        triage_dir = case_dir / "triage"
        diagnosis_dir = case_dir / "diagnosis"
        dump = case_dir / "fault.apd"
        case_dir.mkdir(parents=True, exist_ok=True)

        run([str(args.generator), case, str(dump)])
        run([
            sys.executable,
            str(triage_tool),
            str(dump),
            "--processor",
            str(args.processor),
            "--output-dir",
            str(triage_dir),
        ])
        run([
            sys.executable,
            str(diagnose_tool),
            str(triage_dir / "triage.json"),
            "--output-dir",
            str(diagnosis_dir),
        ])

        triage = load_json(triage_dir / "triage.json")
        diagnosis = load_json(diagnosis_dir / "diagnosis.json")
        first = diagnosis.get("first_fault") or {}
        top = diagnosis.get("top_hypothesis") or {}
        flags = set(first.get("flags") or [])
        header_trigger = int((triage.get("header") or {}).get("trigger_event") or 0)

        assert triage["status"] == "PASS", case
        assert triage["authority"] == "repository-internal-diagnostic-only", case
        assert header_trigger > 0, (case, "runtime event did not trigger Flight Recorder")
        assert triage["analysis"]["summary"]["frames"] >= 1, case
        assert triage["analysis"]["summary"]["metrics_frames"] >= 1, case
        assert first.get("kind") == "metadata", (case, first)
        assert expected["flag"] in flags, (case, flags)
        assert first.get("family") == expected["family"], (case, first)
        assert top.get("hypothesis") == expected["hypothesis"], (case, top)
        assert top.get("causal_proof") is False, case
        assert diagnosis["causal_proof"] is False, case

        replay = triage.get("replay") or {}
        comparison = replay.get("comparison") if isinstance(replay, dict) else None
        summary["cases"].append(
            {
                "case": case,
                "metadata_flag": expected["flag"],
                "trigger_event": header_trigger,
                "first_fault_family": first.get("family"),
                "top_hypothesis": top.get("hypothesis"),
                "heuristic_score": top.get("heuristic_score"),
                "replay_bit_exact": (
                    comparison.get("bit_exact")
                    if isinstance(comparison, dict)
                    else None
                ),
                "causal_proof": False,
            }
        )

    assert len(summary["cases"]) == len(CASES)
    summary_path = args.work_dir / "fault-injection-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "cases": len(CASES), "summary": str(summary_path)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
