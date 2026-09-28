#!/usr/bin/env python3
"""Retire consumed I021 execution and preserve only deterministic recovery."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIVE=ROOT/".github/workflows/research-i021-vad-public-development-transfer-gap-v1.yml"
HISTORY=ROOT/"tests/validation/data/i021-consumed-workflow.yml"
RECOVERY_LIVE=ROOT/".github/workflows/i021-consumed-diagnostic-recovery.yml"
RECOVERY_HISTORY=ROOT/"tests/validation/data/i021-consumed-recovery-workflow.yml"
RECOVERY_HISTORY_BLOB="da45fd7cf01bd35faabdf2a82dc8c520d81fbb06"
RESULT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i021-vad-public-development-transfer-gap-v1-result.json")
EVIDENCE_ROOT=Path("validation/research/evidence/i021-recovery-36419466840")
CONTRACT=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i021-vad-public-development-transfer-gap-v1.json")
RECOVERY=ROOT/(
    ".github/research/continuous-optimization/development-v4/"
    "i021-vad-public-development-transfer-gap-v1-recovery.json")
HISTORY_BLOB="bff679a710d6a3b6634363258c1762d5e6e1267c"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob "+str(len(data)).encode()+b"\0"+data
    ).hexdigest()


class I021RetirementTests(unittest.TestCase):
    def test_consumed_workflow_is_immutable_data(self):
        self.assertEqual(git_blob(HISTORY.read_bytes()),HISTORY_BLOB)
        text=HISTORY.read_text()
        self.assertIn("  workflow_dispatch:\n",text)
        self.assertIn("  diagnose:\n",text)
        self.assertIn("Enforce one-shot I021 diagnostic execution",text)

    def test_live_surface_is_contract_only(self):
        text=LIVE.read_text()
        self.assertIn("\n  pull_request:\n",text)
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  push:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        jobs=re.findall(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$",
                        text[text.index("\njobs:")+1:])
        self.assertEqual(jobs,["contract"])
        self.assertIn("--self-test",text)

    def test_reviewed_closure_is_non_shipping_and_archive_bound(self):
        result=json.loads(RESULT.read_text())
        self.assertEqual(result["status"],"CLOSED_DIAGNOSTIC_ONLY")
        self.assertEqual(
            result["reviewed_decision"],
            "PUBLIC_DEVELOPMENT_TRANSFER_GAP_CONFIRMED_LOW_LOCAL_EVIDENCE_DOMINANT_NO_CANDIDATE",
        )
        self.assertFalse(result["fresh_authority"]["rerun_allowed"])
        self.assertEqual(
            result["authoritative_execution"]["run_id"],36419466840)
        self.assertEqual(
            result["authoritative_execution"]["artifact_id"],10968739971)
        self.assertEqual(
            result["original_result_path"],
            str(EVIDENCE_ROOT/"result.json"),
        )
        self.assertGreater(
            result["summary"]["false_negative_mechanisms"]["low_local_evidence"]["fraction"],
            0.90,
        )
        self.assertEqual(result["summary"]["below_reference_slices"],18)
        self.assertEqual(result["summary"]["eligible_speech_slices"],18)
        self.assertTrue(all(
            value is False
            for value in result["authority_boundary"].values()
        ))

    def test_recovery_is_retired_as_immutable_history(self):
        self.assertFalse(RECOVERY_LIVE.exists())
        self.assertEqual(git_blob(RECOVERY_HISTORY.read_bytes()),RECOVERY_HISTORY_BLOB)
        text=RECOVERY_HISTORY.read_text()
        self.assertIn("\n  pull_request:\n",text)
        self.assertIn("\n  push:\n",text)
        self.assertNotIn("\n  workflow_dispatch:\n",text)
        self.assertNotIn("\n  schedule:\n",text)
        r=json.loads(RECOVERY.read_text())
        c=json.loads(CONTRACT.read_text())
        self.assertEqual(r["source_run"]["run_id"],36417062971)
        self.assertEqual(r["fixed_seeds"],c["fresh_diagnostic_authority"]["seeds"])
        self.assertFalse(r["invariants"]["new_diagnostic_authority"])
        self.assertEqual(r["invariants"]["candidate_budget"],0)
        self.assertEqual(r["invariants"]["confirmation_budget"],0)


if __name__=="__main__":
    unittest.main()
