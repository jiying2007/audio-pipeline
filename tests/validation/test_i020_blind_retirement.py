#!/usr/bin/env python3
"""Retire consumed I020 blind execution while preserving non-terminal review state."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]

BLIND_WORKFLOW = Path(
    ".github/workflows/research-i020-vad-weak-start-requires-blend-blind.yml"
)
RESUME_WORKFLOW = Path(
    ".github/workflows/research-i020-vad-weak-start-requires-blend-blind-resume.yml"
)
BLIND_HISTORY = Path("tests/validation/data/i020-consumed-blind-workflow.yml")
RESUME_HISTORY = Path(
    "tests/validation/data/i020-consumed-blind-resume-workflow.yml"
)
BLIND_HISTORY_BLOB = "0b64f84986298943ef930977541e9f3614c25cea"
RESUME_HISTORY_BLOB = "5f7fdbe156c5f4251be1fefda5908efbed2f2ce5"

MANIFEST = Path(
    ".github/research/continuous-optimization/code-candidates/"
    "i020-vad-weak-start-requires-blend-v1.json"
)
QUALIFICATION_RESULT = Path(
    ".github/research/continuous-optimization/qualifications/"
    "i020-vad-weak-start-requires-blend-blind-v1-result.json"
)
FUTURE_EVIDENCE = "validation/research/evidence/i020-blind-resume-36324803945/**"
SELF = "tests/validation/test_i020_blind_retirement.py"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def yaml_data(path: Path) -> dict:
    command = (
        'require "json"; require "yaml"; '
        'print JSON.generate(YAML.safe_load(STDIN.read, aliases: false))'
    )
    payload = json.loads(
        subprocess.check_output(
            ["ruby", "-e", command], input=(ROOT / path).read_bytes()
        )
    )
    if not isinstance(payload, dict):
        raise ValueError(f"workflow mapping required: {path}")
    if "true" in payload:
        if "on" in payload:
            raise ValueError("ambiguous workflow trigger mapping")
        payload["on"] = payload.pop("true")
    return payload


def assert_contract_only(path: Path, forbidden_job: str) -> None:
    data = yaml_data(path)
    triggers = data.get("on", {})
    if set(triggers) != {"pull_request"}:
        raise ValueError(f"{path} must remain pull_request-only")
    if data.get("permissions") != {"contents": "read"}:
        raise ValueError(f"{path} must remain contents-read-only")
    jobs = data.get("jobs", {})
    if list(jobs) != ["contract"]:
        raise ValueError(f"{path} must retain exactly one contract job")
    if forbidden_job in jobs:
        raise ValueError(f"{path} restored consumed job: {forbidden_job}")
    contract = jobs["contract"]
    steps = contract.get("steps", [])
    text = json.dumps(steps, sort_keys=True)
    if "actions/checkout@" not in text:
        raise ValueError(f"{path} contract lost checkout")
    if "--self-test" not in text:
        raise ValueError(f"{path} contract lost offline self-test")
    if SELF not in text:
        raise ValueError(f"{path} contract lost retirement test")
    pull_paths = triggers["pull_request"].get("paths", [])
    for required in (
        str(MANIFEST), str(QUALIFICATION_RESULT),
        str(BLIND_HISTORY), str(RESUME_HISTORY), SELF, FUTURE_EVIDENCE,
    ):
        if required not in pull_paths:
            raise ValueError(f"{path} lost retirement path coverage: {required}")


class RetirementTests(unittest.TestCase):
    def test_consumed_workflow_fixtures_are_immutable(self):
        pairs = (
            (BLIND_HISTORY, BLIND_HISTORY_BLOB),
            (RESUME_HISTORY, RESUME_HISTORY_BLOB),
        )
        for path, expected in pairs:
            with self.subTest(path=str(path)):
                self.assertEqual(
                    git_blob_sha((ROOT / path).read_bytes()),
                    expected,
                )

    def test_historical_surfaces_are_actually_consumed(self):
        blind = yaml_data(BLIND_HISTORY)
        resume = yaml_data(RESUME_HISTORY)
        self.assertIn("workflow_dispatch", blind["on"])
        self.assertIn("workflow_dispatch", resume["on"])
        self.assertIn("qualify-blind", blind["jobs"])
        self.assertIn("resume", resume["jobs"])

    def test_active_blind_workflow_is_contract_only(self):
        assert_contract_only(BLIND_WORKFLOW, "qualify-blind")

    def test_active_resume_workflow_is_contract_only(self):
        assert_contract_only(RESUME_WORKFLOW, "resume")

    def test_candidate_is_review_required_not_terminal(self):
        manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
        result = json.loads(
            (ROOT / QUALIFICATION_RESULT).read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["status"], "BLIND_BASELINE_INVALID_REVIEW_REQUIRED"
        )
        self.assertEqual(manifest["next_gate"], "baseline-policy-review")
        self.assertEqual(
            result["decision"], "BLIND_BASELINE_INVALID_REVIEW_REQUIRED"
        )
        self.assertFalse(result["terminal_candidate"])
        self.assertEqual(result["next_gate"], "baseline-policy-review")
        self.assertFalse(
            result["authority_boundary"]["new_blind_partition_authorized"]
        )
        self.assertFalse(
            result["authority_boundary"]["blind_rerun_authorized"]
        )
        self.assertFalse(
            result["authority_boundary"]["posthoc_policy_relaxation_authorized"]
        )
        self.assertFalse(
            result["authority_boundary"]["source_merge_authority"]
        )

        self.assertEqual(
            manifest["research_candidate_id"], result["research_candidate_id"]
        )
        self.assertEqual(
            manifest["patch"]["sha256"], result["patch_sha256"]
        )
        patch_path = ROOT / manifest["patch"]["path"]
        self.assertEqual(
            hashlib.sha256(patch_path.read_bytes()).hexdigest(),
            result["patch_sha256"],
        )

    def test_consumed_partition_identity_is_frozen(self):
        result = json.loads(
            (ROOT / QUALIFICATION_RESULT).read_text(encoding="utf-8")
        )
        partition = result["consumed_blind_partition"]
        self.assertEqual(partition["source_run_id"], 36304120808)
        self.assertEqual(partition["source_artifact_id"], 10927016997)
        self.assertEqual(
            partition["holdout_key_fingerprint"], "ebeec484da932ee7"
        )
        self.assertEqual(partition["visible_case_count"], 130)
        self.assertEqual(partition["blind_case_count"], 30)
        self.assertTrue(partition["partition_consumed"])
        self.assertFalse(partition["new_partition_allowed"])
        self.assertFalse(partition["rerun_allowed"])
        resume = result["same_partition_resume"]
        self.assertEqual(resume["run_id"], 36324803945)
        self.assertEqual(resume["artifact_id"], 10934232488)
        self.assertFalse(resume["partition_changed"])
        self.assertFalse(resume["new_holdout_key_generated"])
        self.assertFalse(resume["candidate_or_policy_changed"])

    def test_relative_observation_does_not_override_baseline_invalidity(self):
        result = json.loads(
            (ROOT / QUALIFICATION_RESULT).read_text(encoding="utf-8")
        )
        relative = result["paired_relative_observation"]
        self.assertTrue(relative["visible"]["preregistered_bounds_pass"])
        self.assertTrue(relative["blind"]["preregistered_bounds_pass"])
        self.assertEqual(
            relative["authority"],
            "review-context-only-because-baseline-absolute-pass-required",
        )
        absolute = result["absolute_policy_results"]
        self.assertEqual(
            absolute["visible"]["baseline"]["validation_result"], "FAIL"
        )
        self.assertEqual(
            absolute["blind"]["baseline"]["validation_result"], "FAIL"
        )

    def test_central_registry_marks_both_consumed_surfaces_contract_only(self):
        path = ROOT / ".github/program/maintenance_workflow_contract.py"
        spec = importlib.util.spec_from_file_location("maintenance", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for workflow in (BLIND_WORKFLOW, RESUME_WORKFLOW):
            with self.subTest(workflow=str(workflow)):
                self.assertIn(
                    workflow, module.CONTRACT_ONLY_RESEARCH_WORKFLOWS
                )
                evidence = module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow]
                self.assertIn(MANIFEST, evidence)
                self.assertIn(QUALIFICATION_RESULT, evidence)
        module.validate_program_archive_trigger_boundaries(ROOT)

    def test_no_active_workflow_matches_consumed_fixture_blob(self):
        consumed = {BLIND_HISTORY_BLOB, RESUME_HISTORY_BLOB}
        for path in (ROOT / ".github/workflows").glob("*.y*ml"):
            self.assertNotIn(
                git_blob_sha(path.read_bytes()),
                consumed,
                f"consumed workflow restored under active workflows: {path}",
            )


def self_test() -> None:
    # Keep an explicit --self-test entry for central maintenance governance.
    assert BLIND_HISTORY_BLOB != RESUME_HISTORY_BLOB
    assert FUTURE_EVIDENCE.endswith("/**")
    print("I020 blind retirement self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RetirementTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
