#!/usr/bin/env python3
"""Lock I021 consumed-authority recovery to the original failed run."""

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
RECOVERY=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i021-vad-public-development-transfer-gap-v1-recovery.json")
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i021-vad-public-development-transfer-gap-v1.json")
WORKFLOW=ROOT/".github/workflows/i021-consumed-diagnostic-recovery.yml"
PROBE=ROOT/"tests/validation/i021_vad_public_development_transfer_gap_probe.c"


class I021RecoveryContractTests(unittest.TestCase):
    def test_recovery_is_same_consumed_authority_only(self):
        r=json.loads(RECOVERY.read_text())
        c=json.loads(CONTRACT.read_text())
        self.assertEqual(r["status"],"FROZEN_RECOVERY_ONLY")
        self.assertEqual(r["source_run"]["run_id"],36417062971)
        self.assertEqual(r["source_run"]["run_attempt"],1)
        self.assertEqual(
            r["source_run"]["head_sha"],
            "d6e8c145d66aef119c0e9d166e52de9af1f54202")
        self.assertEqual(r["fixed_seeds"],[501307,511307,521307])
        self.assertEqual(
            r["fixed_seeds"],c["fresh_diagnostic_authority"]["seeds"])
        inv=r["invariants"]
        self.assertFalse(inv["new_diagnostic_authority"])
        self.assertFalse(inv["seeds_may_change"])
        self.assertFalse(inv["dataset_may_change"])
        self.assertFalse(inv["source_base_may_change"])
        self.assertEqual(inv["candidate_budget"],0)
        self.assertEqual(inv["confirmation_budget"],0)
        self.assertFalse(inv["selection_authority"])
        self.assertFalse(inv["shipping_authority"])

    def test_recovery_has_no_manual_or_recurring_execution_surface(self):
        text=WORKFLOW.read_text()
        self.assertIn("\n  pull_request:\n",text)
        self.assertIn("\n  push:\n",text)
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        self.assertIn(
            "test \"$(git rev-parse HEAD^1)\" = \"$SOURCE_RUN_SHA\"",
            text)
        self.assertIn("SOURCE_RUN_ID: '36417062971'",text)
        self.assertIn("SOURCE_JOB_ID: '108910684840'",text)
        self.assertIn("Upload recovery evidence even on failure",text)

    def test_probe_tail_semantics_match_complete_frame_labels(self):
        text=PROBE.read_text()
        self.assertIn("if (got != FRAME) break;",text)
        self.assertNotIn("if (got != FRAME) {\n            fclose(input_file);\n            return 5;",text)
        builder=(ROOT/"validation/tools/build_public_corpus.py").read_text()
        self.assertRegex(
            builder,
            re.compile(
                r"def frame_labels\(signal: list\[int\], rate: int\).*?"
                r"range\(0, len\(signal\) - frame \+ 1, frame\)",
                re.S,
            ),
        )

    def test_recovery_cannot_change_evaluator_or_dataset_builder(self):
        text=WORKFLOW.read_text()
        self.assertIn(
            "git diff --exit-code \"$SOURCE_RUN_SHA\"...HEAD --",
            text)
        for path in (
            ".github/research/continuous-optimization/development-data-v3",
            "tests/validation/i021_vad_public_development_transfer_gap.py",
            "src/enhance/ap_vad.c",
            "src/modules/ap_vad_module.c",
        ):
            self.assertIn(path,text)


if __name__=="__main__":
    unittest.main()
