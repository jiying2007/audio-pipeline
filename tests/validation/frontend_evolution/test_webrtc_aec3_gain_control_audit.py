#!/usr/bin/env python3
"""Pure fail-closed tests for the pinned AEC3 source-mechanism audit."""
import unittest

from webrtc_aec3_gain_control_audit import inspect_structure


ECHO = """
cng_.Compute(a, b, comfort_noise, high_band_comfort_noise);
suppression_gain_.GetGain(a, b, c, d, e, f, g, h, &high_bands_gain, &G);
suppression_filter_.ApplyGain(comfort_noise, high_band_comfort_noise, G,
                              high_bands_gain, Y_fft, y);
"""
FILTER = """
noise_gain[i] = 1.f - suppression_gain[i] * suppression_gain[i];
const float high_bands_noise_scaling =
      0.4f * std::sqrt(1.f - high_bands_gain * high_bands_gain);
std::vector<std::array<float, kFftLengthBy2>> e_output_old_;
std::copy(e_extended.begin() + kFftLengthBy2,
          e_extended.begin() + kFftLength, std::begin(e_output_old_[0][ch]));
"""


class GainControlAuditTests(unittest.TestCase):
    def test_pinned_mechanism_contract(self):
        result = inspect_structure(ECHO, FILTER)
        self.assertEqual(result["status"], "PASS_SOURCE_MECHANISM_AUDIT_ONLY")
        self.assertEqual(result["call_order"], ["CNG_COMPUTE", "GET_GAIN", "APPLY_GAIN"])
        self.assertTrue(result["low_band_cng_mix_depends_on_gain"])
        self.assertTrue(result["high_band_cng_mix_depends_on_gain"])
        self.assertTrue(result["overlap_add_history_is_mutated"])
        self.assertFalse(result["speech_execution_authorized"])

    def test_duplicate_call_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_structure(ECHO + "\n" + ECHO, FILTER)

    def test_reordered_cng_and_gain_is_rejected(self):
        changed = ECHO.replace("cng_.Compute(a, b, comfort_noise, high_band_comfort_noise);",
                               "/* moved */")
        changed += "\ncng_.Compute(a, b, comfort_noise, high_band_comfort_noise);\n"
        with self.assertRaises(ValueError):
            inspect_structure(changed, FILTER)

    def test_cng_inputs_cannot_be_touched_before_apply(self):
        changed = ECHO.replace(
            "suppression_gain_.GetGain",
            "comfort_noise[0].re[0] = 0.f;\nsuppression_gain_.GetGain")
        with self.assertRaises(ValueError):
            inspect_structure(changed, FILTER)

    def test_changed_apply_arguments_are_rejected(self):
        changed = ECHO.replace("high_band_comfort_noise, G,",
                               "different_noise, G,")
        with self.assertRaises(ValueError):
            inspect_structure(changed, FILTER)

    def test_missing_low_band_cng_coupling_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_structure(ECHO, FILTER.replace(
                "noise_gain[i] = 1.f - suppression_gain[i] * suppression_gain[i];",
                "noise_gain[i] = 0.f;"))

    def test_missing_high_band_cng_coupling_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_structure(ECHO, FILTER.replace(
                "0.4f * std::sqrt(1.f - high_bands_gain * high_bands_gain)",
                "0.4f"))

    def test_missing_ola_history_is_rejected(self):
        with self.assertRaises(ValueError):
            inspect_structure(ECHO, FILTER.replace("e_output_old_", "old_state"))



class GainControlTraceTests(unittest.TestCase):
    def row(self, index, mode):
        import webrtc_aec3_gain_control_trace as t
        import webrtc_aec3_gain_control_source as s
        support = s.SUPPORT[0] <= index < s.SUPPORT[1]
        forced = mode == "gain-unity" and support
        result = {key: [0] * (63 if key in t.CNG_IMAGINARY else 65)
                  for key in t.CNG_FIELDS + t.UPSTREAM_FIELDS}
        result.update({"kind": s.TRACE_KIND, "block_index": index, "support": support,
                       "cng_imaginary_endpoint_policy": s.CNG_ENDPOINT_POLICY,
                       "forced": forced, "estimated_low_bits": [0x3f000000] * 65,
                       "estimated_high_bits": 0x3f000000,
                       "applied_low_bits": [t.UNITY if forced else 0x3f000000] * 65,
                       "applied_high_bits": t.UNITY if forced else 0x3f000000})
        return result

    def test_frozen_boundaries_and_neutral_mode(self):
        import webrtc_aec3_gain_control_trace as t
        for index, expected in ((1524, False), (1525, True), (1975, True), (1976, False)):
            for mode in ("gain-observe", "gain-unity"):
                row = self.row(index, mode)
                self.assertEqual(t.validate_row(row, index, mode)["forced"],
                                 expected and mode == "gain-unity")

    def test_partial_unity_or_out_of_support_unity_rejected(self):
        import webrtc_aec3_gain_control_trace as t
        for index in (1524, 1525, 1975, 1976):
            row = self.row(index, "gain-unity")
            row["applied_low_bits"][0] ^= 1
            with self.assertRaises(ValueError):
                t.validate_row(row, index, "gain-unity")

    def test_bad_words_and_malformed_block_rejected(self):
        import webrtc_aec3_gain_control_trace as t
        for field, value in (("block_index", True), ("support", 1),
                             ("cng_high_im", [0x7f800000] * 65),
                             ("estimated_high_bits", 0x40000000),
                             ("cng_low_re", [0] * 64)):
            row = self.row(1525, "gain-unity")
            row[field] = value
            with self.assertRaises(ValueError):
                t.validate_row(row, 1525, "gain-unity")

    def test_unregistered_source_preimage_rejected(self):
        import webrtc_aec3_gain_control_source as s
        for path in s.TARGETS + ("unregistered",):
            with self.assertRaises(ValueError):
                s.transform(path, b"not the pinned complete selector source")

    def test_cng_and_estimator_fields_are_compared_as_raw_words(self):
        import webrtc_aec3_gain_control_trace as t
        selector = [{"block_index": i} for i in range(2000)]
        neutral = {"selector": selector, "gain": [self.row(i, "gain-observe") for i in range(2000)]}
        unity = {"selector": list(selector), "gain": [self.row(i, "gain-unity") for i in range(2000)]}
        self.assertEqual(t.compare_arms(neutral, unity)["nonunity_support_blocks"], 451)
        for field in ("cng_low_im", "cng_high_re", "residual_power", "selected_input_im"):
            unity["gain"][1525][field][0] = 0x80000000
            with self.assertRaises(ValueError):
                t.compare_arms(neutral, unity)
            unity["gain"][1525][field][0] = 0

    def test_unwritten_endpoint_slots_cannot_enter_trace(self):
        import webrtc_aec3_gain_control_trace as t
        for key in t.CNG_IMAGINARY:
            row = self.row(1525, "gain-unity")
            row[key] = [0] + row[key] + [0]
            with self.assertRaises(ValueError):
                t.validate_row(row, 1525, "gain-unity")
        row = self.row(1525, "gain-unity")
        row["cng_imaginary_endpoint_policy"] = "ZERO_FILLED"
        with self.assertRaises(ValueError):
            t.validate_row(row, 1525, "gain-unity")

    def test_duplicate_json_field_rejected(self):
        import webrtc_aec3_gain_control_trace as t
        with self.assertRaises(ValueError):
            t.distinct([("block_index", 1), ("block_index", 2)])



class GainControlScienceContractTests(unittest.TestCase):
    def test_scientific_admission_is_source_bound_and_not_engineering_authority(self):
        import hashlib
        import json
        from contracts import ROOT
        import webrtc_aec3_gain_control_science as s
        p = ROOT / ".github/research/frontend-evolution-v1/aec3-joint-gain-controlled-synthesis-science-v1.json"
        plan = json.loads(p.read_text())
        self.assertEqual(plan["executor_sha256"], hashlib.sha256((ROOT / plan["executor_path"]).read_bytes()).hexdigest())
        self.assertEqual(plan["engineering_revision"], s.HEAD)
        self.assertEqual(plan["support_blocks"], list(s.SUPPORT))
        self.assertEqual(plan["primary_samples"], [97600, 126400])
        self.assertEqual((plan["max_calls"], plan["max_capture_seconds"], plan["retries"]), (2, 32, 0))
        self.assertTrue(plan["speech_execution_authorized"])
        self.assertFalse(plan["promotion_allowed"])
        engineering = json.loads((ROOT / ".github/research/frontend-evolution-v1/aec3-joint-gain-controlled-synthesis-v1.json").read_text())
        self.assertFalse(engineering["speech_execution_authorized"])

    def test_frozen_decision_directions(self):
        import webrtc_aec3_gain_control_science as s
        def score(si_sdr, nmse, far=5, peak=0.1):
            return {"final": {"near": {"double-before": {"projection_identifiable": True,
                    "si_sdr_db": si_sdr, "normalized_mse": nmse}},
                    "far": {"aggregate_ratio_db": far, "blocks": [{"echo_to_output_ratio_db": far} for _ in range(19)]},
                    "raw_amplitude": {"peak": peak, "rms": 0.01, "negative_endpoint_count": 0, "positive_endpoint_count": 0}}}
        before = score(1, 0.5)
        def outcome(after):
            return s.decide(dict(zip(s.MODES, (before, after))))["decision"]
        self.assertEqual(outcome(score(1, 0.5)), "JOINT_GAIN_CONTROLLED_SYNTHESIS_HYPOTHESIS_NOT_SUPPORTED")
        self.assertEqual(outcome(score(2, 0.4)), "JOINT_GAIN_CONTROLLED_SYNTHESIS_EFFECT_SUPPORTED_IN_ONE_DISCLOSED_WINDOW")
        self.assertEqual(outcome(score(2, 0.4, 4)), "NEAR_END_GAIN_TRADEOFF_OBSERVED_NO_PROMOTION")
        self.assertEqual(outcome(score(2, 0.4, peak=0.2)), "NEAR_END_GAIN_TRADEOFF_OBSERVED_NO_PROMOTION")
        self.assertEqual(outcome(score(2, 0.6)), "INCONCLUSIVE_MIXED_INDICATORS")
        self.assertEqual(outcome(score(None, 0.4)), "NOT_IDENTIFIABLE")

if __name__ == "__main__":
    unittest.main()
