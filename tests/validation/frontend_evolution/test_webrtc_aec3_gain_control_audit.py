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
        changed = "cng_.Compute(a, b, comfort_noise, high_band_comfort_noise);\n" + changed
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


if __name__ == "__main__":
    unittest.main()
