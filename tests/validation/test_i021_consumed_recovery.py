#!/usr/bin/env python3
"""Offline contracts for the one-time I021 consumed diagnostic recovery."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/program/i021_consumed_recovery.py"
MANIFEST = ROOT / (
    ".github/research/continuous-optimization/development-v4/"
    "i021-consumed-diagnostic-tail-frame-recovery-v1.json"
)
WORKFLOW = ROOT / ".github/workflows/i021-consumed-diagnostic-recovery.yml"
PROBE = ROOT / "tests/validation/i021_vad_public_development_transfer_gap_probe.c"

SPEC = importlib.util.spec_from_file_location("i021_consumed_recovery", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class I021ConsumedRecoveryTests(unittest.TestCase):
    def test_frozen_recovery_contract_is_valid_and_non_authoritative(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        contract = module.validate_contract(manifest)
        self.assertEqual(
            contract["fresh_diagnostic_authority"]["seeds"],
            [501307, 511307, 521307],
        )
        self.assertEqual(manifest["failed_execution"]["run_id"], 36417062971)
        self.assertEqual(manifest["failed_execution"]["artifact_count"], 0)
        self.assertEqual(
            manifest["repair"]["class"], "MECHANICAL_INPUT_FRAMING_ONLY"
        )
        self.assertTrue(
            manifest["recovery_execution"]["rebuild_same_consumed_inputs_only"]
        )
        self.assertTrue(
            all(value is False for value in manifest["authority_boundary"].values())
        )

    def test_probe_ignores_trailing_partial_frame_but_keeps_empty_invalid(self):
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn("if (got != FRAME) break;", text)
        self.assertNotIn("return 5;", text)
        self.assertIn("return frame_index ? 0 : 7;", text)

    def test_recovery_surface_has_no_manual_or_scheduled_replay(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("\n  pull_request:\n", text)
        self.assertIn("\n  push:\n", text)
        self.assertNotIn("\n  workflow_dispatch:\n", text)
        self.assertNotIn("\n  schedule:\n", text)
        self.assertIn(
            "if: github.event_name == 'push' && github.ref == 'refs/heads/main'",
            text,
        )
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pull-requests: write", text)

    def test_failed_execution_shape_is_machine_checked(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        failed = manifest["failed_execution"]
        steps = [
            {"name": name, "conclusion": conclusion}
            for name, conclusion in failed["required_step_state"].items()
        ]

        def fake(endpoint: str):
            if endpoint.endswith(f"/actions/runs/{failed['run_id']}"):
                return {
                    "id": failed["run_id"],
                    "run_attempt": failed["run_attempt"],
                    "head_sha": failed["head_sha"],
                    "event": failed["event"],
                    "status": "completed",
                    "conclusion": "failure",
                }
            if endpoint.endswith(f"/actions/runs/{failed['run_id']}/jobs?per_page=100"):
                return {
                    "jobs": [{
                        "id": failed["diagnose_job_id"],
                        "conclusion": "failure",
                        "steps": steps,
                    }]
                }
            if endpoint.endswith(f"/actions/runs/{failed['run_id']}/artifacts?per_page=100"):
                return {"total_count": 0, "artifacts": []}
            raise AssertionError(endpoint)

        with (
            patch.dict(
                os.environ,
                {"GITHUB_REPOSITORY": "jiying2007/audio-pipeline"},
                clear=True,
            ),
            patch.object(module, "gh_json", side_effect=fake),
        ):
            module.validate_failed_execution(manifest)

        def bad(endpoint: str):
            value = fake(endpoint)
            if endpoint.endswith("/artifacts?per_page=100"):
                value = {"total_count": 1, "artifacts": [{"id": 1}]}
            return value

        with (
            patch.dict(
                os.environ,
                {"GITHUB_REPOSITORY": "jiying2007/audio-pipeline"},
                clear=True,
            ),
            patch.object(module, "gh_json", side_effect=bad),
            self.assertRaisesRegex(ValueError, "artifact count drift"),
        ):
            module.validate_failed_execution(manifest)

    def test_recovery_run_is_first_attempt_and_exact_parent_only(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            'require(os.environ.get("GITHUB_RUN_ATTEMPT") == "1", '
            '"recovery rerun is forbidden")',
            text,
        )
        self.assertIn(
            '"main moved before deterministic recovery"',
            text,
        )
        self.assertIn(
            '"authority": "RECOVERY_OF_CONSUMED_DIAGNOSTIC_ONLY"',
            text,
        )


if __name__ == "__main__":
    unittest.main()
