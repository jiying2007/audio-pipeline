#!/usr/bin/env python3
"""Negative coverage for the source-derived sequential selection decision."""
import json
import unittest

import webrtc_aec3_selection as subject


def row(index, selected=True, force=False):
    return {"kind": "aec3_synthesis_selection", "block_index": index,
            "source_linear": selected, "applied_linear": selected or force,
            "forced": force and not selected, "capture_output_used": True,
            "gain_bits": [1065353216] * 65, "high_bands_gain_bits": 1065353216,
            "dominant_nearend_after_gain": False}


def encoded(rows):
    return ("upstream informational message\n" + "\n".join(json.dumps(r) for r in rows) + "\n").encode()


class SelectionMethodTests(unittest.TestCase):
    def test_exact_ola_dependency(self):
        self.assertEqual(subject.synthesis_support(97600, 126400), (1525, 1976))
        self.assertEqual(subject.synthesis_support(97601, 126399), (1525, 1976))

    def test_one_sample_crossing_end_adds_dependency(self):
        self.assertEqual(subject.synthesis_support(97600, 126401), (1525, 1977))

    def test_reject_noninteger_and_outside_target(self):
        for interval in [(True, 1), (1.0, 2), (2, 2), (-1, 2), (0, 256000)]:
            with self.subTest(interval=interval), self.assertRaises((ValueError, AssertionError)):
                subject.synthesis_support(*interval)

    def test_observe_and_force_branches(self):
        self.assertEqual(len(subject.parse_trace(encoded([row(0, False), row(1)]), "observe", 2)), 2)
        forced = [row(0, False, True), row(1, True, True)]
        self.assertEqual(subject.parse_trace(encoded(forced), "force-linear", 2), forced)

    def test_omitted_repeated_reordered_reset_and_extra(self):
        for records in ([row(1)], [row(0), row(0)], [row(1), row(0)],
                        [row(0), row(1), row(0)], [row(0), row(1), row(2)]):
            with self.subTest(records=records), self.assertRaises((ValueError, AssertionError)):
                subject.parse_trace(encoded(records), "observe", 2)

    def test_bool_is_not_index_and_number_is_not_flag(self):
        for key, value in [("block_index", False), ("forced", 0), ("source_linear", 1),
                           ("applied_linear", "true"), ("capture_output_used", False)]:
            bad = row(0); bad[key] = value
            with self.subTest(key=key), self.assertRaises((ValueError, AssertionError)):
                subject.parse_trace(encoded([bad]), "observe", 1)

    def test_malformed_informative_trace_is_not_ignored(self):
        with self.assertRaises((ValueError, AssertionError)):
            subject.parse_trace(b'aec3_synthesis_selection: broken\n' + encoded([row(0)]), "observe", 1)

    def test_duplicate_key_and_nonfinite_constant_rejected(self):
        duplicate = json.dumps(row(0)).replace('"block_index": 0', '"block_index": 2, "block_index": 0')
        invalid = json.dumps(row(0)).replace('"block_index": 0', '"block_index": NaN')
        for raw in (duplicate, invalid):
            with self.assertRaises((ValueError, AssertionError)):
                subject.parse_trace(raw.encode(), "observe", 1)

    def test_extra_field_and_hidden_branch_are_rejected(self):
        for bad in (dict(row(0), extra=1), dict(row(0, False), applied_linear=True)):
            with self.assertRaises((ValueError, AssertionError)):
                subject.parse_trace(encoded([bad]), "observe", 1)

    def test_nonfinite_invalid_gain_words_are_rejected(self):
        for words in ([0] * 64, [2139095040] * 65, [-1] * 65, [True] * 65, [1065353217] * 65):
            with self.subTest(first=words[0]), self.assertRaises((ValueError, AssertionError)):
                subject.parse_trace(encoded([dict(row(0), gain_bits=words)]), "observe", 1)

    def test_all_E_stops_without_intervention(self):
        result = subject.selection_summary([row(i) for i in range(4000)])
        self.assertFalse(result["force_linear_permitted"])
        self.assertEqual(result["counts"]["primary_with_ola"]["blocks"], 451)

    def test_each_ola_boundary_Y_requires_intervention(self):
        for index in (1525, 1526, 1974, 1975):
            records = [row(i, i != index) for i in range(4000)]
            with self.subTest(index=index):
                self.assertTrue(subject.selection_summary(records)["force_linear_permitted"])

    def test_Y_outside_support_does_not_reopen_primary(self):
        records = [row(i, i not in (0, 1524, 1976, 3999)) for i in range(4000)]
        self.assertFalse(subject.selection_summary(records)["force_linear_permitted"])

    def test_both_metrics_must_support_and_degeneracy_is_retained(self):
        base = {"si_sdr_db": -4., "normalized_mse": .7, "projection_identifiable": True}
        cases = [({"si_sdr_db": 1., "normalized_mse": .2, "projection_identifiable": True},
                  "SUPPORTED_IN_DISCLOSED_WINDOW"),
                 ({"si_sdr_db": 1., "normalized_mse": .8, "projection_identifiable": True},
                  "INCONCLUSIVE_MIXED_INDICATORS"),
                 ({"si_sdr_db": -5., "normalized_mse": .8, "projection_identifiable": True},
                  "NOT_SUPPORTED_IN_DISCLOSED_WINDOW"),
                 ({"si_sdr_db": 100., "normalized_mse": .0, "projection_identifiable": False},
                  "NOT_IDENTIFIABLE")]
        for candidate, expected in cases:
            self.assertEqual(subject.intervention_decision(base, candidate), expected)

    def test_runner_cannot_receive_scoring_targets_or_activity_labels(self):
        from pathlib import Path
        command = subject.run_command(Path('/binary'), Path('/input'), Path('/output'), 'observe')
        self.assertIn('/input/mic.pcm', command)
        self.assertIn('/input/render.pcm', command)
        self.assertFalse(any('target.s16' in x or 'echo.s16' in x or '97600' in x for x in command))


if __name__ == "__main__":
    unittest.main()
