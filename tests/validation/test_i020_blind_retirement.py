#!/usr/bin/env python3
"""Retire consumed I020 blind surfaces after baseline-invalid review."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
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
REVIEW = Path(
    ".github/research/continuous-optimization/development-v4/"
    "i020-vad-weak-start-requires-blend-v1-blind-review.json"
)
MANIFEST = Path(
    ".github/research/continuous-optimization/code-candidates/"
    "i020-vad-weak-start-requires-blend-v1.json"
)
PATCH = Path(
    ".github/research/continuous-optimization/code-candidates/"
    "i020-vad-weak-start-requires-blend-v1.patch"
)
DEVELOPMENT_RESULT = Path(
    ".github/research/continuous-optimization/development-v4/"
    "i020-vad-weak-start-requires-blend-v1-result.json"
)
DURABLE_MANIFEST = Path(
    ".github/research/continuous-optimization/development-v4/"
    "i020-blind-baseline-invalid-durable-evidence-v1.json"
)
SELF = Path("tests/validation/test_i020_blind_retirement.py")
ONE_SHOT = Path("tests/validation/test_i020_code_candidate_blind_one_shot.py")
EVIDENCE_ROOT = Path(
    "validation/research/evidence/"
    "i020-blind-baseline-invalid-36304120808-36324803945"
)
EVIDENCE_GLOB = str(EVIDENCE_ROOT) + "/**"
POLICY_BLOBS = {
    Path("validation/policies/validation-full-partition.json"):
        "ae1d57fbb5672aa3c00c280e1d0d666587d63a8b",
    Path("validation/policies/validation-full-blind.json"):
        "d425362542cc622b64951b8dde53fe8aae080112",
    Path("validation/authority.json"):
        "24de4a38bfa235be15b5cdad8d5a99552b4ea9fa",
    Path("validation/datasets.lock.json"):
        "65d1e9bef12563e1742bc43c93e3f5870459ed50",
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def yaml_data(path: Path) -> dict:
    command = (
        'require "json"; require "yaml"; '
        'print JSON.generate(YAML.safe_load(STDIN.read, aliases: false))'
    )
    value = json.loads(
        subprocess.check_output(
            ["ruby", "-e", command], input=(ROOT / path).read_bytes()
        )
    )
    if not isinstance(value, dict):
        raise ValueError(f"workflow mapping required: {path}")
    if "true" in value:
        if "on" in value:
            raise ValueError(f"ambiguous trigger mapping: {path}")
        value["on"] = value.pop("true")
    return value


def job_names(workflow: dict) -> list[str]:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError("jobs mapping required")
    return list(jobs)


class I020BlindRetirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        blind_bytes = (ROOT / BLIND_HISTORY).read_bytes()
        resume_bytes = (ROOT / RESUME_HISTORY).read_bytes()
        if git_blob(blind_bytes) != BLIND_HISTORY_BLOB:
            raise ValueError("consumed I020 blind fixture drift")
        if git_blob(resume_bytes) != RESUME_HISTORY_BLOB:
            raise ValueError("consumed I020 blind-resume fixture drift")
        cls.blind_history = yaml_data(BLIND_HISTORY)
        cls.resume_history = yaml_data(RESUME_HISTORY)
        cls.blind_live = yaml_data(BLIND_WORKFLOW)
        cls.resume_live = yaml_data(RESUME_WORKFLOW)

    def test_historical_execution_surfaces_are_preserved_only_as_data(self):
        self.assertIn("workflow_dispatch", self.blind_history["on"])
        self.assertIn("qualify-blind", self.blind_history["jobs"])
        self.assertIn("workflow_dispatch", self.resume_history["on"])
        self.assertIn("resume", self.resume_history["jobs"])
        for path, expected in (
            (BLIND_HISTORY, BLIND_HISTORY_BLOB),
            (RESUME_HISTORY, RESUME_HISTORY_BLOB),
        ):
            self.assertFalse((ROOT / path).resolve().is_relative_to(
                ROOT / ".github/workflows"
            ))
            self.assertEqual(git_blob((ROOT / path).read_bytes()), expected)

    def test_live_blind_surfaces_are_contract_only_and_read_only(self):
        for name, workflow in (
            ("blind", self.blind_live),
            ("resume", self.resume_live),
        ):
            with self.subTest(name=name):
                self.assertEqual(set(workflow["on"]), {"pull_request"})
                self.assertEqual(job_names(workflow), ["contract"])
                self.assertEqual(workflow.get("permissions"), {"contents": "read"})
                self.assertNotIn("workflow_dispatch", workflow["on"])

    def test_live_contracts_bind_retirement_review(self):
        for workflow in (self.blind_live, self.resume_live):
            paths = workflow["on"]["pull_request"]["paths"]
            for required in (
                str(REVIEW), str(DURABLE_MANIFEST), str(SELF),
                str(BLIND_HISTORY), str(RESUME_HISTORY), EVIDENCE_GLOB,
            ):
                self.assertIn(required, paths)
            contract = workflow["jobs"]["contract"]
            scripts = "\n".join(
                step.get("run", "") for step in contract.get("steps", [])
            )
            self.assertIn("test_i020_blind_retirement.py", scripts)
            self.assertIn("--self-test", scripts)

    def test_review_state_is_baseline_invalid_not_candidate_verdict(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        self.assertEqual(
            review["status"], "BLIND_BASELINE_INVALID_REVIEW_REQUIRED"
        )
        self.assertEqual(
            review["decision"], "BLIND_BASELINE_INVALID_REVIEW_REQUIRED"
        )
        self.assertFalse(review["terminal_candidate"])
        self.assertEqual(
            review["next_gate"], "shipping-baseline-authority-review"
        )
        boundary = review["authority_boundary"]
        self.assertFalse(boundary["candidate_terminalized"])
        self.assertFalse(boundary["candidate_qualified"])
        self.assertFalse(boundary["candidate_rejected"])
        self.assertFalse(boundary["candidate_advancement_authorized"])
        self.assertFalse(boundary["requalification_authorized"])
        self.assertFalse(boundary["rerun_authorized"])
        self.assertFalse(boundary["repartition_authorized"])
        self.assertFalse(boundary["policy_relaxation_authorized"])
        self.assertFalse(boundary["source_merge_authorized"])

    def test_consumed_partition_and_resume_are_exact(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        blind = review["blind_partition_authority"]
        self.assertEqual(blind["source_run_id"], 36304120808)
        self.assertEqual(blind["source_artifact_id"], 10927016997)
        self.assertEqual(blind["blind_key_fingerprint"], "ebeec484da932ee7")
        self.assertEqual(blind["visible_case_count"], 130)
        self.assertEqual(blind["blind_case_count"], 30)
        self.assertFalse(blind["repartition_allowed"])
        self.assertFalse(blind["rerun_allowed"])
        resume = review["same_partition_resume"]
        self.assertEqual(resume["run_id"], 36324803945)
        self.assertEqual(resume["artifact_id"], 10934232488)
        self.assertTrue(resume["all_sha256s_verified"])
        self.assertFalse(resume["partition_changed"])
        self.assertFalse(resume["new_holdout_key_generated"])
        self.assertFalse(resume["candidate_or_policy_changed"])

    def test_shipping_baseline_failure_is_real_and_version_matched(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        identity = review["baseline_contract_identity"]
        self.assertTrue(identity["source_and_current_same_blobs"])
        for path, expected_blob in POLICY_BLOBS.items():
            self.assertEqual(
                git_blob((ROOT / path).read_bytes()),
                expected_blob,
                f"policy/authority blob drift: {path}",
            )
        visible = review["shipping_baseline_absolute_results"]["visible"]
        blind = review["shipping_baseline_absolute_results"]["blind"]
        self.assertEqual(visible["validation_result"], "FAIL")
        self.assertEqual(blind["validation_result"], "FAIL")
        self.assertEqual(
            {item["gate"] for item in visible["violations"]},
            {
                "min_median_near_si_sdr_improvement_db",
                "min_median_output_render_corr_reduction",
                "min_vad_f1",
            },
        )
        self.assertEqual(
            {item["gate"] for item in blind["violations"]},
            {
                "min_median_output_render_corr_reduction",
                "min_vad_f1",
            },
        )

    def test_relative_candidate_observation_cannot_promote(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        relative = review["paired_relative_observation"]
        self.assertEqual(
            relative["authority"],
            "NON_PROMOTING_OBSERVATION_ONLY_BECAUSE_BASELINE_INVALID",
        )
        self.assertEqual(relative["relative_vad_violations"], [])
        self.assertTrue(relative["visible"]["relative_gates_pass"])
        self.assertTrue(relative["blind"]["relative_gates_pass"])
        self.assertGreaterEqual(relative["blind"]["recall_delta"], -0.03)
        self.assertGreaterEqual(relative["blind"]["f1_delta"], -0.03)
        self.assertLessEqual(relative["blind"]["false_positive_rate_delta"], 0.0)
        self.assertFalse(
            review["authority_boundary"]["candidate_advancement_authorized"]
        )

    def test_durable_archive_manifest_is_frozen_and_review_bound(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        manifest = json.loads(
            (ROOT / DURABLE_MANIFEST).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "FROZEN_ARCHIVE_MANIFEST")
        self.assertEqual(manifest["review_path"], str(REVIEW))
        self.assertEqual(
            manifest["required_review_status"], review["status"]
        )
        self.assertEqual(
            manifest["archive_root"],
            review["durable_evidence_plan"]["root"],
        )
        source = manifest["source_partition_artifact"]
        resume = manifest["same_partition_resume_artifact"]
        self.assertEqual(
            source["run_id"], review["blind_partition_authority"]["source_run_id"]
        )
        self.assertEqual(
            source["artifact_id"],
            review["blind_partition_authority"]["source_artifact_id"],
        )
        self.assertEqual(
            source["artifact_digest"],
            review["blind_partition_authority"]["source_artifact_digest"],
        )
        self.assertEqual(
            resume["run_id"], review["same_partition_resume"]["run_id"]
        )
        self.assertEqual(
            resume["artifact_id"], review["same_partition_resume"]["artifact_id"]
        )
        self.assertEqual(
            resume["artifact_digest"],
            review["same_partition_resume"]["artifact_digest"],
        )
        self.assertEqual(
            manifest["invariants"]["decision"], review["decision"]
        )
        self.assertFalse(manifest["invariants"]["terminal_candidate"])
        self.assertTrue(
            manifest["authority_boundary"]["archive_copy_only"]
        )
        for key, value in manifest["authority_boundary"].items():
            if key != "archive_copy_only":
                self.assertFalse(value, key)

    def test_durable_archive_bytes_match_trusted_manifest_and_review(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        manifest = json.loads(
            (ROOT / DURABLE_MANIFEST).read_text(encoding="utf-8")
        )
        root = ROOT / EVIDENCE_ROOT
        self.assertTrue(root.is_dir())

        members = (
            manifest["source_partition_artifact"]["members"]
            + manifest["same_partition_resume_artifact"]["members"]
        )
        expected_names = sorted(item["archive_name"] for item in members)
        actual_names = sorted(
            path.name for path in root.iterdir() if path.is_file()
        )
        self.assertEqual(actual_names, expected_names)
        self.assertEqual(len(expected_names), 11)

        for item in members:
            path = root / item["archive_name"]
            self.assertEqual(path.stat().st_size, item["bytes"], path.name)
            self.assertEqual(sha256_file(path), item["sha256"], path.name)

        origin = json.loads(
            (root / "holdout-key-origin.json").read_text(encoding="utf-8")
        )
        self.assertFalse(origin["key_persisted"])
        self.assertEqual(
            origin["key_fingerprint"],
            review["blind_partition_authority"]["blind_key_fingerprint"],
        )
        self.assertEqual(
            str(origin["github_run_id"]),
            str(review["blind_partition_authority"]["source_run_id"]),
        )

        visible_corpus = json.loads(
            (root / "corpus-validation.json").read_text(encoding="utf-8")
        )
        blind_corpus = json.loads(
            (root / "corpus-blind.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            len(visible_corpus["cases"]),
            review["blind_partition_authority"]["visible_case_count"],
        )
        self.assertEqual(
            len(blind_corpus["cases"]),
            review["blind_partition_authority"]["blind_case_count"],
        )
        self.assertEqual(
            visible_corpus["blind_key_fingerprint"],
            review["blind_partition_authority"]["blind_key_fingerprint"],
        )
        self.assertEqual(
            blind_corpus["blind_key_fingerprint"],
            review["blind_partition_authority"]["blind_key_fingerprint"],
        )

        source_summary = json.loads(
            (root / "source-qualification-summary.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            source_summary["decision"],
            review["blind_partition_authority"]["source_decision"],
        )
        self.assertEqual(
            source_summary["failed_stage"],
            review["blind_partition_authority"]["source_failed_stage"],
        )

        receipt = json.loads(
            (root / "resume-partition-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(receipt["partition_changed"])
        self.assertFalse(receipt["new_holdout_key_generated"])
        self.assertFalse(receipt["candidate_or_policy_changed"])
        self.assertEqual(
            receipt["blind_key_fingerprint"],
            review["blind_partition_authority"]["blind_key_fingerprint"],
        )

        qualification = json.loads(
            (root / "qualification-summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(qualification["decision"], review["decision"])
        self.assertFalse(qualification["terminal_candidate"])
        self.assertEqual(
            qualification["failed_stage"],
            review["same_partition_resume"]["failed_stage"],
        )

        reports = {
            "baseline-visible-report.json":
                review["shipping_baseline_absolute_results"]["visible"],
            "baseline-blind-report.json":
                review["shipping_baseline_absolute_results"]["blind"],
            "candidate-visible-report.json":
                review["candidate_absolute_results"]["visible"],
            "candidate-blind-report.json":
                review["candidate_absolute_results"]["blind"],
        }
        for name, expected in reports.items():
            report = json.loads((root / name).read_text(encoding="utf-8"))
            self.assertEqual(
                report["validation_result"], expected["validation_result"]
            )
            for key in (
                "min_vad_recall",
                "min_vad_f1",
                "max_vad_false_positive_rate",
            ):
                self.assertAlmostEqual(
                    float(report["summary"][key]), float(expected[key]),
                    places=12,
                )

        sums = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        by_basename = {}
        for line in sums:
            digest, relative = line.split("  ", 1)
            by_basename[Path(relative).name] = digest
        for name in (
            "baseline-visible-report.json",
            "candidate-visible-report.json",
            "baseline-blind-report.json",
            "candidate-blind-report.json",
            "resume-partition-receipt.json",
            "qualification-summary.json",
        ):
            self.assertEqual(by_basename[name], sha256_file(root / name))

    def test_frozen_candidate_identity_is_unchanged(self):
        review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
        development = json.loads(
            (ROOT / DEVELOPMENT_RESULT).read_text(encoding="utf-8")
        )
        self.assertEqual(
            review["research_candidate_id"], manifest["research_candidate_id"]
        )
        self.assertEqual(
            review["candidate_patch"]["sha256"], manifest["patch"]["sha256"]
        )
        self.assertEqual(
            review["candidate_patch"]["sha256"],
            development["candidate_patch"]["sha256"],
        )
        self.assertEqual(
            review["source_base_sha"], manifest["source_base_sha"]
        )
        self.assertEqual(
            review["source_base_sha"], development["source_base_sha"]
        )

    def test_central_registry_marks_both_blind_surfaces_contract_only(self):
        spec = importlib.util.spec_from_file_location(
            "i020_blind_registry",
            ROOT / ".github/program/maintenance_workflow_contract.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for workflow in (BLIND_WORKFLOW, RESUME_WORKFLOW):
            self.assertIn(
                workflow, module.CONTRACT_ONLY_RESEARCH_WORKFLOWS
            )
            evidence = set(
                module.CONTRACT_ONLY_RESEARCH_EVIDENCE[workflow]
            )
            self.assertIn(REVIEW, evidence)
            self.assertIn(DURABLE_MANIFEST, evidence)
            self.assertIn(MANIFEST, evidence)
            self.assertIn(PATCH, evidence)
        module.validate_program_archive_trigger_boundaries(ROOT)

    def test_consumed_workflows_cannot_reappear_under_active_workflow_dir(self):
        forbidden = {BLIND_HISTORY_BLOB, RESUME_HISTORY_BLOB}
        for path in (ROOT / ".github/workflows").glob("*.y*ml"):
            self.assertNotIn(
                git_blob(path.read_bytes()), forbidden, str(path)
            )


if __name__ == "__main__":
    unittest.main()
