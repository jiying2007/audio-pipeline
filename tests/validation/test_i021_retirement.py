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
RECOVERY_WF=ROOT/".github/workflows/i021-consumed-diagnostic-recovery.yml"
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

    def test_recovery_is_only_post_consumption_execution(self):
        text=RECOVERY_WF.read_text()
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
