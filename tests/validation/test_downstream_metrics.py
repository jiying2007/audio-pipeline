#!/usr/bin/env python3
"""Independent metric oracles and negative contracts; no model inference."""
import copy
import importlib.util
import itertools
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("downstream_metrics", ROOT / "validation/tools/downstream_metrics.py")
metrics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metrics)


def distance_oracle(a, b):
    # Independent full matrix scalar distance; no count tuple or production
    # tie-breaking logic is reused here.
    grid = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        grid[i][0] = i
    for j in range(len(b) + 1):
        grid[0][j] = j
    for i, x in enumerate(a, 1):
        for j, y in enumerate(b, 1):
            grid[i][j] = min(grid[i - 1][j] + 1, grid[i][j - 1] + 1,
                             grid[i - 1][j - 1] + int(x != y))
    return grid[-1][-1]


def event(key, when, keyword="hello"):
    return {"event_id": key, "keyword": keyword, "emitted_at_sample": when}


def annotation():
    return {"positive_events": [{"event_id": "target", "keyword": "hello", "start_sample": 100, "end_sample": 200}],
            "max_latency_samples": 50, "negative_intervals": [[0, 100], [251, 1000]]}


def inputs():
    manifest = {"schema_version": 1, "normalization": metrics.NORMALIZATION,
                "model_bindings": {"asr": "a" * 64, "kws": "b" * 64},
                "cases": [{"case_id": "raw", "pcm_sha256": "c" * 64, "sample_rate_hz": 16000,
                           "samples": 1600, "reference_text": "你好世界", "reference_words": None,
                           "kws_annotation": None}]}
    predictions = {"schema_version": 1, "model_bindings": copy.deepcopy(manifest["model_bindings"]),
                   "manifest_digest": metrics.manifest_digest(manifest),
                   "cases": [{"case_id": "raw", "pcm_sha256": "c" * 64,
                              "asr": {"status": "ok", "text": "你好 世界"},
                              "kws": {"status": "ok", "events": []}}]}
    return manifest, predictions


class TextMetrics(unittest.TestCase):
    def test_exhaustive_distance_independent_oracle(self):
        strings = ["".join(p) for n in range(5) for p in itertools.product("ab", repeat=n)]
        for a in strings:
            for b in strings:
                with self.subTest(a=a, b=b):
                    row = metrics.edit_counts(a, b)
                    self.assertEqual(row["distance"], distance_oracle(a, b))
                    self.assertEqual(row["distance"], row["substitutions"] + row["deletions"] + row["insertions"])
                    self.assertEqual(len(b) - len(a), row["insertions"] - row["deletions"])

    def test_known_error_types_and_tie(self):
        for ref, hyp, expected in [("你好", "你号", (1, 0, 0)), ("你好", "你", (0, 1, 0)),
                                   ("你好", "你好吗", (0, 0, 1)), ("ab", "ba", (2, 0, 0))]:
            row = metrics.edit_counts(ref, hyp)
            self.assertEqual(tuple(row[k] for k in ("substitutions", "deletions", "insertions")), expected)

    def test_empty_reference_preserves_insertions_and_null(self):
        row = metrics.score_transcript("", "你好", [])
        self.assertEqual(row["cer"]["insertions"], 2)
        self.assertIsNone(row["cer"]["error_rate"])
        self.assertEqual(row["wer"]["insertions"], 1)
        self.assertIsNone(row["wer"]["error_rate"])

    def test_empty_hypothesis_is_total_deletion(self):
        row = metrics.score_transcript("你好", "")
        self.assertEqual(row["cer"]["error_rate"], 1.0)
        self.assertEqual(row["cer"]["deletions"], 2)

    def test_unicode_whitespace_and_punctuation_contract(self):
        self.assertEqual(metrics.normalize_text(" e\u0301\t你\u3000好\n"), "é你好")
        self.assertEqual(metrics.normalize_text("A，臺灣1!"), "A，臺灣1!")
        self.assertEqual(metrics.score_transcript("你好！", "你好")["cer"]["deletions"], 1)

    def test_chinese_words_not_invented(self):
        self.assertIsNone(metrics.score_transcript("广州市房地产中介协会分析", "广州 市 房地产 中介 协会 分析")["wer"])

    def test_fixed_word_boundaries(self):
        row = metrics.score_transcript("we like tea", "we like coffee", ["we", "like", "tea"])
        self.assertEqual(row["wer"]["substitutions"], 1)
        self.assertAlmostEqual(row["wer"]["error_rate"], 1 / 3)
        with self.assertRaises(ValueError):
            metrics.score_transcript("we like tea", "we like tea", ["we", "tea"])
        with self.assertRaises(ValueError):
            metrics.score_transcript("hi", "hi", ["h i"])

    def test_invalid_text_and_bound(self):
        for value in (None, False, 123, []):
            with self.assertRaises(ValueError):
                metrics.score_transcript("x", value)
        with self.assertRaises(ValueError):
            metrics.edit_counts("x" * 4097, "y")

    def test_unequal_reference_lengths_pool_counts_not_rates(self):
        rows = [metrics.edit_counts("a", "b"), metrics.edit_counts("aaaaaaaaa", "aaaaaaaaa")]
        pooled = metrics.pool_edit_counts(rows)
        self.assertEqual(pooled["reference_units"], 10)
        self.assertEqual(pooled["distance"], 1)
        self.assertAlmostEqual(pooled["error_rate"], 0.1)
        self.assertNotEqual(pooled["error_rate"], sum(row["error_rate"] for row in rows) / 2)
        rows.append(metrics.edit_counts("", "x"))
        self.assertAlmostEqual(metrics.pool_edit_counts(rows)["error_rate"], 0.2)


class EventMetrics(unittest.TestCase):
    def test_unavailable_labels_are_null_even_with_events(self):
        row = metrics.score_events([event("hit", 300)], 1000, 1000)
        self.assertEqual(row["emitted_events"], 1)
        for name in ("positive_events", "matched_events", "frr", "far_per_hour", "latency_ms"):
            self.assertIsNone(row[name])

    def test_exact_target_and_actual_emission_latency(self):
        row = metrics.score_events([event("hit", 230)], 1000, 1000, annotation())
        self.assertEqual(row["matched_events"], 1)
        self.assertEqual(row["latency_ms"], [30.0])
        self.assertEqual(row["frr"], 0)

    def test_missed_duplicate_wrong_word_and_negative_trigger(self):
        row = metrics.score_events([event("wrong", 150, "other"), event("hit", 200),
                                    event("twice", 210), event("false", 500)], 1000, 1000, annotation())
        self.assertEqual(row["matched_events"], 1)
        self.assertEqual(row["unmatched_events"], 3)
        self.assertEqual(row["duplicate_target_triggers"], 1)
        self.assertEqual(row["negative_false_alarms"], 1)
        self.assertEqual(row["negative_exposure_samples"], 849)
        self.assertAlmostEqual(row["far_per_hour"], 3600000 / 849)
        miss = metrics.score_events([event("wrong", 150, "other")], 1000, 1000, annotation())
        self.assertEqual(miss["missed_events"], 1)
        self.assertEqual(miss["frr"], 1)

    def test_inclusive_positive_deadline_halfopen_negative(self):
        inside = metrics.score_events([event("on", 250)], 1000, 1000, annotation())
        outside = metrics.score_events([event("late", 251)], 1000, 1000, annotation())
        end = metrics.score_events([event("end", 1000)], 1000, 1000, annotation())
        self.assertEqual(inside["matched_events"], 1)
        self.assertEqual(outside["negative_false_alarms"], 1)
        self.assertEqual(outside["frr"], 1)
        self.assertEqual(end["negative_false_alarms"], 0)
        self.assertEqual(end["unscored_event_ids"], ["end"])

    def test_zero_exposure_and_positive_counts(self):
        row = metrics.score_events([], 1000, 1000, {"positive_events": [], "negative_intervals": [], "max_latency_samples": 0})
        self.assertIsNone(row["far_per_hour"])
        self.assertIsNone(row["frr"])

    def test_zero_events_has_nonzero_poisson_upper(self):
        row = metrics.score_events([], 1000, 3600000,
                                   {"positive_events": [], "negative_intervals": [[0, 3600000]], "max_latency_samples": 0})
        self.assertEqual(row["far_per_hour"], 0)
        self.assertAlmostEqual(row["far_zero_event_one_sided_95_upper_per_hour"], 2.995732273553991)

    def test_nonfinite_boolean_unsorted_or_outside_events_rejected(self):
        for bad in (True, -1, 1001, 1.0, math.nan, math.inf):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                metrics.score_events([event("a", bad)], 1000, 1000)
        for bad in (True, math.nan, math.inf, -0.1, 1.1):
            with self.subTest(score=bad), self.assertRaises(ValueError):
                metrics.score_events([{**event("a", 100), "confidence": bad}], 1000, 1000)
        with self.assertRaises(ValueError):
            metrics.score_events([event("a", 101), event("b", 100)], 1000, 1000)
        with self.assertRaises(ValueError):
            metrics.score_events([event("a", 100), event("a", 100)], 1000, 1000)

    def test_frame_counts_are_not_booleans(self):
        for rate, count, maximum in ((True, 1000, None), (1000, True, None), (1000, 1000, True)):
            with self.assertRaises(ValueError):
                metrics.score_events([], rate, count, max_emitted_samples=maximum)

    def test_ambiguous_ground_truth_or_exposure_rejected(self):
        cases = []
        a = annotation(); a["positive_events"].append({"event_id": "two", "keyword": "hello", "start_sample": 250, "end_sample": 300}); cases.append(a)
        a = annotation(); a["negative_intervals"] = [[0, 150]]; cases.append(a)
        a = annotation(); a["negative_intervals"] = [[300, 600], [500, 700]]; cases.append(a)
        a = annotation(); a["max_latency_samples"] = True; cases.append(a)
        a = annotation(); a["positive_events"][0]["start_sample"] = True; cases.append(a)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                metrics.score_events([], 1000, 1000, value)

    def test_one_event_does_not_match_multiple_nonoverlapping_targets(self):
        a = annotation()
        a["positive_events"].append({"event_id": "two", "keyword": "hello", "start_sample": 300, "end_sample": 400})
        a["negative_intervals"] = []
        row = metrics.score_events([event("only", 350)], 1000, 1000, a)
        self.assertEqual(row["matched_events"], 1)
        self.assertEqual(row["missed_events"], 1)
        self.assertEqual(row["matches"][0]["reference_event_id"], "two")


class SourceBinding(unittest.TestCase):
    def test_complete_observation(self):
        manifest, predictions = inputs()
        result = metrics.evaluate(manifest, predictions)
        self.assertEqual(result["cases"][0]["asr"]["cer"]["error_rate"], 0)
        self.assertIsNone(result["cases"][0]["kws"]["far_per_hour"])
        self.assertFalse(result["promotion_allowed"])

    def test_identity_mismatch(self):
        for kind in ("manifest", "model", "pcm"):
            manifest, predictions = inputs()
            if kind == "manifest": predictions["manifest_digest"] = "d" * 64
            elif kind == "model": predictions["model_bindings"]["kws"] = "d" * 64
            else: predictions["cases"][0]["pcm_sha256"] = "d" * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                metrics.evaluate(manifest, predictions)

    def test_missing_extra_duplicate_case_rejected(self):
        for kind in ("missing", "duplicate", "extra", "duplicate-label"):
            manifest, predictions = inputs()
            if kind == "missing": predictions["cases"] = []
            elif kind == "duplicate": predictions["cases"] *= 2
            elif kind == "extra": predictions["cases"].append({**predictions["cases"][0], "case_id": "extra"})
            else:
                manifest["cases"] *= 2
                predictions["manifest_digest"] = metrics.manifest_digest(manifest)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                metrics.evaluate(manifest, predictions)

    def test_model_failure_is_not_empty_success(self):
        for kind in ("asr", "kws"):
            manifest, predictions = inputs()
            predictions["cases"][0][kind]["status"] = "failed"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                metrics.evaluate(manifest, predictions)
        manifest, predictions = inputs()
        predictions["cases"][0]["asr"]["text"] = ""
        self.assertEqual(metrics.evaluate(manifest, predictions)["cases"][0]["asr"]["cer"]["error_rate"], 1)

    def test_method_drift_and_bool_schema_rejected(self):
        for kind in ("normalization", "schema"):
            manifest, predictions = inputs()
            if kind == "normalization": manifest["normalization"] = "drop-punctuation"
            else: manifest["schema_version"] = True
            predictions["manifest_digest"] = metrics.manifest_digest(manifest)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                metrics.evaluate(manifest, predictions)


if __name__ == "__main__":
    unittest.main()
