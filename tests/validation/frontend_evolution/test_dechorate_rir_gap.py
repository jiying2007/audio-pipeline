#!/usr/bin/env python3
"""Tiny synthetic mathematical/transport negatives; no measured RIR is read."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

import dechorate_rir_gap as gap


class SupportGapTests(unittest.TestCase):
    def setUp(self):
        self.plan = gap.contract()

    def test_real_contract_is_source_only(self):
        self.assertEqual(len(self.plan["source"]["objects"]), 12)
        self.assertEqual(sum(x["size_bytes"] for x in self.plan["source"]["objects"]), 19403164)
        self.assertEqual(gap.support_length(self.plan)["native_window_samples"], 1677)

    def test_unit_geometry_endpoint_and_kernel_units(self):
        p = copy.deepcopy(self.plan)
        p["metadata"]["room_dimensions_m"] = [1.0, 1.0, 1.0]
        p["metadata"]["sample_rate_hz"] = 10
        p["model"].update(speed_of_sound_m_s=1.0, source_rate_hz=4,
                          kernel_support_source_samples=2)
        # Two seconds of excess path, half second interpolation support,
        # ten native samples/second and one endpoint bin.
        self.assertEqual(gap.support_length(p)["native_window_samples"], 26)

    def test_actual_canonical_fractional_delay_support(self):
        path = gap.ROOT / "validation/tools/build_aec_motion_corpus.py"
        spec = importlib.util.spec_from_file_location("_gap_motion_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.RATE, 16000)
        self.assertEqual(module.MODEL["speed_of_sound_m_s"], 343.0)
        impulse = [1, 0, 0, 0]
        actual = [module.sample(impulse, n - 2.25) for n in range(8)]
        self.assertEqual(actual, [0.0, 0.0, 0.75, 0.25, 0.0, 0.0, 0.0, 0.0])

    def test_compact_support_and_separated_mass(self):
        compact = gap.energy_coverage([0, 2, 1, 0, 0, 0, 0, 0], 3, 8, [[0, 1]])
        self.assertEqual(compact["uncovered_energy_fraction_lower_bound"], 0.0)
        split = gap.energy_coverage([1, 0, 0, 0, 0, 0, 0, 1], 3, 8, [[0, 1]])
        self.assertEqual(split["oracle_covered_energy_fraction"], 0.5)
        self.assertEqual(split["oracle_window_start_sample"], 0)

    def test_last_window_is_included(self):
        r = gap.energy_coverage([0, 0, 0, 0, 0, 0, 1, 2], 2, 8, [[0, 1]])
        self.assertEqual(r["oracle_window_start_sample"], 6)
        self.assertEqual(r["oracle_window_end_sample_exclusive"], 8)
        self.assertEqual(r["oracle_covered_energy_fraction"], 1.0)

    def test_shift_is_only_an_oracle_statistic(self):
        a = gap.energy_coverage([0, 1, 2, 0, 0, 0, 0, 0], 2, 8, [[0, 1]])
        b = gap.energy_coverage([0, 0, 0, 0, 1, 2, 0, 0], 2, 8, [[0, 1]])
        self.assertEqual(a["oracle_covered_energy_fraction"], b["oracle_covered_energy_fraction"])
        self.assertEqual(b["oracle_window_start_sample"] - a["oracle_window_start_sample"], 3)
        self.assertIsNone(a["absolute_arrival_error_samples"])
        self.assertIsNone(b["absolute_arrival_error_samples"])

    def test_sliding_sum_against_independent_brute_force(self):
        rng = random.Random(71)
        x = [rng.randrange(-8, 9) / 8.0 for _ in range(97)]
        for length in (1, 7, 48, 97):
            with self.subTest(length=length):
                sums = [math.fsum(v * v for v in x[i:i + length])
                        for i in range(len(x) - length + 1)]
                r = gap.energy_coverage(x, length, 97, [[0, 1]])
                self.assertEqual(r["oracle_max_window_energy"], max(sums))
                self.assertEqual(r["oracle_window_start_sample"], sums.index(max(sums)))

    def test_zero_short_nonfinite_and_overflow_rejected(self):
        for x, length in (([0, 0], 1), ([1], 2), ([1, float("nan")], 1),
                          ([float("inf"), 1], 1), ([1e308, 1], 1)):
            with self.subTest(x=x), self.assertRaises(ValueError):
                gap.energy_coverage(x, length, 2, [[0, 1]])

    def test_fixed_windows_partition_original_record(self):
        r = gap.energy_coverage([1.0] * 1000, 80, 1000, gap.FIXED_WINDOWS)
        parts = r["fixed_record_windows"]
        self.assertEqual([p["energy"] for p in parts], [5.0, 15.0, 30.0, 50.0, 100.0, 800.0])
        self.assertAlmostEqual(sum(p["fraction"] for p in parts), 1.0)

    def test_data_role_model_budget_and_promotion_negatives(self):
        for path, value in ((["data_role"], "independent-validation"),
                            (["promotion_allowed"], True), (["candidate_budget"], 1),
                            (["model", "speed_of_sound_m_s"], 346.98),
                            (["budget", "analysis_wall_seconds"], 91),
                            (["dependencies", "physical_room_count"], 11),
                            (["dependencies", "scored_microphone_indices_zero_based"], [1, 0])):
            p = copy.deepcopy(self.plan)
            target = p
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                gap.validate_plan(p)

    def test_shape_rate_delay_contract(self):
        gap.validate_header([1, 5, 48000], "float64", 48000.0, [0.0] * 5)
        for args in (([1, 2, 48000], "float64", 48000.0, [0.0] * 5),
                     ([1, 5, 48000], "float32", 48000.0, [0.0] * 5),
                     ([1, 5, 48000], "float64", 16000.0, [0.0] * 5),
                     ([1, 5, 48000], "float64", 48000.0, [1.0] * 5)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                gap.validate_header(*args)

    def test_wrong_input_bytes_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            # Explicit tiny transport fixture; it never impersonates real audio.
            for obj in self.plan["source"]["objects"]:
                (root / obj["name"]).write_bytes(b"synthetic transport negative")
            with self.assertRaises(ValueError):
                gap.verify_inputs(root, self.plan)
            path = root / self.plan["source"]["objects"][0]["name"]
            path.unlink()
            path.symlink_to(root / self.plan["source"]["objects"][1]["name"])
            with self.assertRaises(ValueError):
                gap.verify_inputs(root, self.plan)

    def test_recomputed_score_role_count_and_promotion_negatives(self):
        # Pure semantic fixture, not an execution or a measured-corpus receipt.
        expected = {"cases": [{"room_state": "synthetic", "mic_index_zero_based": 0,
                               "uncovered_energy_fraction_lower_bound": 0.5}],
                    "scored_ir_count": 1, "promotion_allowed": False}
        result = {"status": gap.STATUS, "experiment_id": gap.EXPERIMENT,
                  "analysis_attempts": 1, "automatic_retries": 0, "elapsed_seconds": 0.1,
                  "measurement": copy.deepcopy(expected)}
        gap.validate_result(result, expected, self.plan)
        changes = [dict(expected, cases=[]), dict(expected, scored_ir_count=22),
                   dict(expected, promotion_allowed=True)]
        score = copy.deepcopy(expected)
        score["cases"][0]["uncovered_energy_fraction_lower_bound"] = 0.0
        changes.append(score)
        role = copy.deepcopy(expected)
        role["cases"][0]["mic_index_zero_based"] = 1
        changes.append(role)
        for measurement in changes:
            bad = dict(result, measurement=measurement)
            with self.assertRaises(ValueError):
                gap.validate_result(bad, expected, self.plan)
        with self.assertRaises(ValueError):
            gap.validate_result(dict(result, elapsed_seconds=90.1), expected, self.plan)

    def test_failed_evidence_and_hidden_nested_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "nested").mkdir()
            (root / "nested/manifest.json").write_text("{}")
            self.assertIn("nested/manifest.json", gap.exact_manifest(root)["files"])
            (root / "failure.json").write_text('{"status":"FAIL"}')
            gap.write_json(root / "manifest.json", gap.exact_manifest(root))
            with self.assertRaises(ValueError):
                gap.reject_failed_output(root)

    def test_duplicate_or_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tiny.json"
            for text in ('{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    gap.read_json(path)


if __name__ == "__main__":
    unittest.main()
