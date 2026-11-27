#!/usr/bin/env python3
"""Independent byte-identity checks; synthetic metadata only, Python 3.8+."""
from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation/tools"))
import authority
import run_validation as validation
import tuning_iteration_engine as tuning


def digest(raw):
    # Test oracle intentionally does not use a producer/consumer hash helper.
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class AuthorityBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ap-authority-binding-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = (ROOT / "validation/research-authority.json").read_bytes()
        self.legacy_raw = (ROOT / "validation/authority.json").read_bytes()
        self.assertNotEqual(digest(self.raw), digest(self.legacy_raw))
        self.authority_path = self.root / "custom-authority.json"
        self.authority_path.write_bytes(self.raw)
        self.corpus = self.root / "corpus.json"
        self.policy = self.root / "policy.json"
        self.dataset_lock = self.root / "datasets.lock.json"
        self.processor = self.root / "not-an-executable"
        self.processor.write_bytes(b"metadata fixture: never executed\n")
        self.corpus.write_text(json.dumps({
            "schema_version": 1, "corpus_id": "synthetic-authority-only",
            "tier": "regression", "cases": [{
                "case_id": "fixture", "sample_rate_hz": 16000,
                "mic_channels": 1, "mic_audio": "not-executed.pcm",
            }],
        }), encoding="utf-8")
        self.policy.write_text(json.dumps({
            "allowed_tiers": ["regression"], "policy_id": "synthetic-authority-only",
        }), encoding="utf-8")
        self.dataset_lock.write_text("{}\n", encoding="utf-8")

    def test_default_snapshot_identifies_active_v2_bytes(self):
        loaded, bound = authority.load_authority_snapshot()
        self.assertEqual(loaded, json.loads(self.raw))
        self.assertEqual(loaded["schema_version"], 2)
        self.assertEqual(bound, digest(self.raw))
        self.assertNotEqual(bound, digest(self.legacy_raw))

    def test_custom_path_hashes_original_bytes_not_json_or_default_path(self):
        custom = json.dumps(json.loads(self.raw), ensure_ascii=False, indent=4)
        custom_raw = (custom + "\n ").replace("\n", "\r\n").encode("utf-8")
        self.authority_path.write_bytes(custom_raw)
        loaded, bound = authority.load_authority_snapshot(self.authority_path)
        self.assertEqual(loaded, json.loads(self.raw))
        self.assertEqual(authority.load_authority(self.authority_path), loaded)
        self.assertEqual(bound, digest(custom_raw))
        self.assertNotEqual(bound, digest(self.raw))

    def test_snapshot_reads_once_and_rejects_legacy_policy(self):
        with patch.object(Path, "read_bytes", return_value=self.raw) as reader:
            loaded, bound = authority.load_authority_snapshot(self.authority_path)
        reader.assert_called_once_with()
        self.assertEqual(loaded, json.loads(self.raw))
        self.assertEqual(bound, digest(self.raw))
        self.authority_path.write_bytes(self.legacy_raw)
        with self.assertRaisesRegex(ValueError, "schema_version must be 2"):
            authority.load_authority_snapshot(self.authority_path)

    def report(self, on_evaluate=None):
        output = self.root / "report.json"

        def evaluate(processor, corpus_path, case, semantics):
            if on_evaluate is not None:
                on_evaluate()
            # Exercise report assembly without invoking DSP or quality metrics.
            return {"case_id": case["case_id"], "passed": False,
                    "violations": [{"gate": "synthetic-metadata-fixture"}]}

        semantics = validation.ValidationSemantics(
            evaluation=validation.canonical_evaluation_semantics(),
            evaluate_case=evaluate,
            engine_policy_violations=lambda *args: ({"synthetic_fixture": True}, []),
        )
        argv = ["run_validation.py", "--corpus", str(self.corpus),
                "--policy", str(self.policy), "--dataset-lock", str(self.dataset_lock),
                "--processor", str(self.processor), "--output", str(output),
                "--source-revision", "synthetic-metadata-fixture"]
        with patch.object(sys, "argv", argv), \
                patch.object(validation.render_corr_exact, "report_bindings", return_value={}), \
                redirect_stdout(io.StringIO()), working_directory(self.root):
            self.assertEqual(validation.main(semantics), 0)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_report_uses_active_authority_from_an_unrelated_working_directory(self):
        report = self.report()
        self.assertEqual(report["bindings"]["authority_sha256"], digest(self.raw))
        self.assertNotEqual(report["bindings"]["authority_sha256"], digest(self.legacy_raw))

    def test_report_keeps_loaded_snapshot_when_path_changes_during_evaluation(self):
        original = b"\n" + self.raw
        changed = self.raw + b"\n\n"
        self.authority_path.write_bytes(original)

        def load_custom_snapshot():
            return authority.load_authority_snapshot(self.authority_path)

        with patch.object(validation, "load_authority_snapshot", side_effect=load_custom_snapshot) as loader:
            report = self.report(lambda: self.authority_path.write_bytes(changed))
        loader.assert_called_once_with()
        self.assertEqual(report["bindings"]["authority_sha256"], digest(original))
        self.assertNotEqual(report["bindings"]["authority_sha256"], digest(changed))
        self.assertNotEqual(report["bindings"]["authority_sha256"], digest(self.raw))

    def reusable_report(self):
        validation_dir = self.root / "validation"
        validation_dir.mkdir()
        active = validation_dir / "research-authority.json"
        active.write_bytes(self.raw + b"\n")
        (validation_dir / "authority.json").write_bytes(self.legacy_raw)
        report = {
            "schema_version": 1, "validation_result": "PASS",
            "corpus_id": "synthetic-authority-only", "tier": "regression",
            "source_revision": "synthetic-metadata-fixture",
            "bindings": {
                "authority_sha256": digest(active.read_bytes()),
                "corpus_sha256": digest(self.corpus.read_bytes()),
                "policy_sha256": digest(self.policy.read_bytes()),
                "dataset_lock_sha256": digest(self.dataset_lock.read_bytes()),
                "processor_sha256": digest(self.processor.read_bytes()),
            },
        }
        return active, report

    def reuse(self, report):
        path = self.root / "baseline-report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        with patch.object(tuning, "current_source_revision", return_value="synthetic-metadata-fixture"):
            return tuning.load_reusable_baseline_report(
                self.root, path, self.corpus, self.policy, self.dataset_lock, self.processor,
            )

    def test_reuse_accepts_explicit_repository_bytes_and_rejects_legacy_or_other_source(self):
        active, report = self.reusable_report()
        self.assertEqual(self.reuse(report), report)
        for wrong in (digest(self.legacy_raw), digest(self.raw), "0" * 64):
            changed = copy.deepcopy(report)
            changed["bindings"]["authority_sha256"] = wrong
            with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "authority_sha256"):
                self.reuse(changed)

    def test_reuse_rejects_a_byte_changed_authority_even_if_json_semantics_match(self):
        active, report = self.reusable_report()
        before = json.loads(active.read_bytes())
        active.write_bytes(b"\n" + active.read_bytes())
        self.assertEqual(json.loads(active.read_bytes()), before)
        with self.assertRaisesRegex(ValueError, "authority_sha256"):
            self.reuse(report)


if __name__ == "__main__":
    unittest.main()
