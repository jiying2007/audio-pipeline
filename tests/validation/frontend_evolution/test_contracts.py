#!/usr/bin/env python3
"""Offline positive/negative tests for the FE00/FE01 foundation."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from contracts import (ARCHIVE, B0, FrameContract, Reblocker, admit_execution,
                       check_archive, check_catalog, check_outputs,
                       check_prefix_causality, load_json, sha256)


class ArchiveTests(unittest.TestCase):
    def test_actual_approved_bytes_and_dependency_graph(self):
        self.assertEqual(len(check_archive()["tasks"]), 10)

    def test_archive_mutation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("PLAN.zh-CN.md", "TASKS.json", "SHA256SUMS"):
                (root / name).write_bytes((ARCHIVE / name).read_bytes())
            with (root / "PLAN.zh-CN.md").open("ab") as stream:
                stream.write(b"not approved")
            with self.assertRaisesRegex(ValueError, "archive drift"):
                check_archive(root)

    def test_duplicate_json_and_nonfinite_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '[]'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(ValueError):
                    load_json(path)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"schema_version": 1, "stage": "frontend-evolution-v1", "baseline_source": B0,
                        "sources": [{"id": "test-fixture", "url": "https://example.org/test-fixture",
                                     "commit": "a" * 40, "status": "PINNED_PENDING_REVIEW",
                                     "rights": {k: "PENDING" for k in
                                                ("code", "dependencies", "weights", "data", "redistribution")}}]}

    def test_pending_is_valid_inventory_but_not_execution(self):
        check_catalog(self.catalog)
        with self.assertRaises(ValueError):
            admit_execution(self.catalog, "test-fixture")

    def test_approved_fixture_needs_bytes_and_review(self):
        source = self.catalog["sources"][0]
        source.update(status="EXECUTION_ADMITTED", admission_receipt_sha256="b" * 64,
                      materialized_source_sha256="c" * 64)
        source["rights"] = {k: "ALLOWED" for k in source["rights"]}
        self.assertEqual(admit_execution(self.catalog, "test-fixture"), source)
        del source["materialized_source_sha256"]
        with self.assertRaises(ValueError):
            admit_execution(self.catalog, "test-fixture")

    def test_review_only_and_blanket_claim_cannot_run(self):
        source = self.catalog["sources"][0]
        for state in ("REFERENCE_REVIEW_ONLY", "EXECUTION_ADMITTED"):
            source["status"] = state
            with self.subTest(state=state), self.assertRaises(ValueError):
                admit_execution(self.catalog, "test-fixture")

    def test_invalid_commit_duplicate_and_embedded_credentials(self):
        for key, value in (("commit", "master"), ("url", "https://user:pass@example.org/src")):
            broken = copy.deepcopy(self.catalog)
            broken["sources"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_catalog(broken)
        self.catalog["sources"] *= 2
        with self.assertRaises(ValueError):
            check_catalog(self.catalog)

    def test_live_catalog_has_no_implicit_admissions(self):
        catalog = load_json(ARCHIVE.parents[2] / ".github/research/frontend-evolution-v1/sources.json")
        check_catalog(catalog)
        for source in catalog["sources"]:
            if source["status"] != "EXECUTION_ADMITTED":
                with self.assertRaises(ValueError):
                    admit_execution(catalog, source["id"])


class ReblockTests(unittest.TestCase):
    def test_10ms_to_128_does_not_wait_for_lcm(self):
        c = FrameContract(16000, 2, 1, 128, (0, 1))
        r = Reblocker(c)
        frame = struct.pack("<480h", *range(480))
        out = r.push(frame)
        self.assertEqual(len(out), 1)
        self.assertEqual(len(r.pending), 32 * 3 * 2)
        for _ in range(3):
            out.extend(r.push(frame))
        r.finish()
        self.assertEqual(b"".join(out), frame * 4)
        self.assertLessEqual(r.high_water_sample_frames, 287)

    def test_384_hop_is_still_24ms_and_bounded(self):
        r = Reblocker(FrameContract(16000, 4, 1, 384, (0, 1, 2, 3)))
        frame = bytes(160 * 5 * 2)
        self.assertEqual(r.push(frame), [])
        self.assertEqual(r.push(frame), [])
        self.assertEqual(len(r.push(frame)), 1)
        for _ in range(9):
            r.push(frame)
        r.finish()
        self.assertLessEqual(r.high_water_sample_frames, 543)

    def test_incomplete_native_tail_fails_without_padding(self):
        r = Reblocker(FrameContract(16000, 1, 0, 128, (0,)))
        r.push(bytes(320))
        with self.assertRaisesRegex(ValueError, "tail policy"):
            r.finish()
        self.assertEqual(r.output_sample_frames, 128)

    def test_bad_frame_does_not_mutate_state(self):
        r = Reblocker(FrameContract(16000, 2, 0, 160, (0, 1)))
        with self.assertRaises(ValueError):
            r.push(bytes(320))
        self.assertEqual(r.input_sample_frames, 0)
        self.assertEqual(r.pending, bytearray())

    def test_geometry_references_and_mapping_are_separate(self):
        self.assertEqual(FrameContract(16000, 4, 1, 160, (0, 1, 2, 3)).channels, 5)
        for args in ((16000, 3, 1, 160, (0, 1, 2)), (16000, 2, 0, 160, (0, 0)),
                     (16000, 2, 0, 160, (1, 2)), (16000, 2, 0, 0, (0, 1)),
                     (16000, True, 0, 160, (0,))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                FrameContract(*args)

    def test_float_normalization_and_nan(self):
        c = FrameContract(16000, 1, 0, 160, (0,), encoding="f32le")
        for value in (float("nan"), float("inf"), -float("inf"), 32767.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Reblocker(c).push(struct.pack("<160f", *([value] * 160)))
        self.assertEqual(len(Reblocker(c).push(struct.pack("<160f", *([0.5] * 160)))), 1)


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.c = FrameContract(16000, 1, 0, 160, (0,))
        self.data = struct.pack("<160h", *range(160))
        (self.root / "out.pcm").write_bytes(self.data)
        self.identity = {"source_sha": B0, "config_sha256": "a" * 64,
                         "processor_sha256": "b" * 64, "evaluator_sha256": "c" * 64}
        self.expected = {"case": {"output_samples": 160, "require_nonzero": True, "input_sha256": "d" * 64}}
        self.results = [{"case_id": "case", "exit_code": 0, "status": "SUCCESS", "identity": self.identity.copy(),
                         "input_sha256": "d" * 64, "output_path": "out.pcm", "output_sha256": sha256(self.data)}]

    def check(self):
        return check_outputs(self.expected, self.results, self.root, self.c, self.identity)

    def test_valid_result_does_not_claim_quality(self):
        self.assertEqual(self.check(), {"status": "OUTPUT_CONTRACT_PASS", "cases": 1, "acoustic_authority": False})

    def test_zero_exit_with_failed_case_rejected(self):
        self.results[0]["status"] = "FAILED"
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_duplicate_unknown_cases(self):
        for results in ([], self.results * 2, [dict(self.results[0], case_id="other")]):
            with self.subTest(results=results), self.assertRaises(ValueError):
                check_outputs(self.expected, results, self.root, self.c, self.identity)

    def test_each_stale_identity_component_rejected(self):
        for key in self.identity:
            old = self.results[0]["identity"][key]
            self.results[0]["identity"][key] = "e" * len(old)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            self.results[0]["identity"][key] = old

    def test_missing_input_digest_and_output_tamper(self):
        for key in ("input_sha256", "output_sha256"):
            old = self.results[0][key]
            self.results[0][key] = "e" * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            self.results[0][key] = old

    def test_extra_lost_and_silent_samples(self):
        for data in (self.data[:-2], self.data + b"\0\0", bytes(len(self.data))):
            (self.root / "out.pcm").write_bytes(data)
            self.results[0]["output_sha256"] = sha256(data)
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                self.check()

    def test_expected_silence_allowed_without_quality_claim(self):
        (self.root / "out.pcm").write_bytes(bytes(320))
        self.results[0]["output_sha256"] = sha256(bytes(320))
        self.expected["case"]["require_nonzero"] = False
        self.assertFalse(self.check()["acoustic_authority"])

    def test_traversal_missing_symlink_rejected(self):
        for path in ("../out.pcm", "/tmp/out.pcm", "absent.pcm"):
            self.results[0]["output_path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.check()
        (self.root / "alias").symlink_to(self.root / "out.pcm")
        self.results[0]["output_path"] = "alias"
        with self.assertRaises(ValueError):
            self.check()


class CausalityTests(unittest.TestCase):
    def setUp(self):
        self.a = [1.] * 80 + [2.] * 80
        self.b = [1.] * 80 + [5.] * 80

    def test_causal_identity_and_delayed_identity(self):
        self.assertEqual(check_prefix_causality(self.a, self.b, self.a, self.b, 80), 80)
        ya, yb = [0.] * 10 + self.a[:-10], [0.] * 10 + self.b[:-10]
        self.assertEqual(check_prefix_causality(self.a, self.b, ya, yb, 80, 10), 90)

    def test_global_normalization_and_hidden_future_fail(self):
        ya, yb = [x / max(self.a) for x in self.a], [x / max(self.b) for x in self.b]
        with self.assertRaises(ValueError):
            check_prefix_causality(self.a, self.b, ya, yb, 80)
        ya, yb = self.a[1:] + [0.], self.b[1:] + [0.]
        with self.assertRaises(ValueError):
            check_prefix_causality(self.a, self.b, ya, yb, 80)
        self.assertEqual(check_prefix_causality(self.a, self.b, ya, yb, 80, 0, 1), 79)

    def test_different_past_and_vacuous_coverage_fail(self):
        with self.assertRaises(ValueError):
            check_prefix_causality(self.a, self.b, self.a, self.b, 81)
        with self.assertRaises(ValueError):
            check_prefix_causality(self.a, self.b, self.a, self.b, 80, 0, 80)


if __name__ == "__main__":
    unittest.main(verbosity=2)
