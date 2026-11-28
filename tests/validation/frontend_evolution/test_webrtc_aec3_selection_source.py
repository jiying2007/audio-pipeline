#!/usr/bin/env python3
"""Pure selector derivation and malformed evidence tests; no compiler or DSP."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import webrtc_aec3_selection_source as module
from contracts import ROOT


def rows(mode="observe"):
    result = []
    for index in range(2):
        source = bool(index)
        result.append({"kind": module.TRACE_KIND, "block_index": index, "source_linear": source,
                       "applied_linear": source or mode == "force-linear",
                       "forced": mode == "force-linear" and not source, "capture_output_used": True,
                       "gain_bits": [1065353216] * 65, "high_bands_gain_bits": 1065353216,
                       "dominant_nearend_after_gain": False})
    return result


def encode(value):
    return ("\n".join(json.dumps(row) for row in value) + "\n").encode()


class SourceTests(unittest.TestCase):
    def test_runner_derivation_and_original_preserved(self):
        path = ROOT / module.RUNNER
        original = path.read_bytes()
        changed = module.transform(module.RUNNER, original)
        self.assertEqual(path.read_bytes(), original)
        for clause in (b"--aec3-synthesis-selection", b"frames > 1600", b"no reset",
                       b"research_synthesis_selection.force_linear",
                       b'"factory-on"', b"std::fflush(stderr)"):
            self.assertIn(clause, changed)

    def test_unknown_and_mutated_original_rejected(self):
        original = (ROOT / module.RUNNER).read_bytes()
        for name, data in (("other", original), (module.RUNNER, original + b"\n"),
                           (module.CONFIG, b"  struct Buffering {\n")):
            with self.assertRaises(ValueError):
                module.transform(name, data)

    def test_ambiguous_anchor_rejected(self):
        for value in ("absent", "x x"):
            with self.assertRaises(ValueError):
                module.replace_once(value, "x", "replacement")

    def test_observe_and_force_trace_actual_intervention(self):
        for mode in ("observe", "force-linear"):
            self.assertEqual(module.parse_trace(b"unrelated upstream log\n" + encode(rows(mode)), 160, mode),
                             rows(mode))

    def test_missing_extra_reordered_reset_trace_rejected(self):
        valid = rows()
        for changed in (valid[:1], valid + valid[:1], valid[::-1], [valid[0], valid[0]]):
            with self.assertRaises(ValueError):
                module.parse_trace(encode(changed), 160, "observe")

    def test_wrong_field_types_or_semantics_rejected(self):
        for key, value in (("block_index", False), ("forced", 1), ("capture_output_used", False),
                           ("source_linear", "false"), ("applied_linear", True),
                           ("dominant_nearend_after_gain", 0), ("kind", "other"),
                           ("gain_bits", [1065353216] * 64), ("high_bands_gain_bits", True)):
            changed = rows()
            changed[0][key] = value
            with self.assertRaises(ValueError):
                module.parse_trace(encode(changed), 160, "observe")

    def test_nan_infinite_negative_and_amplification_gain_rejected(self):
        for bits in (0x7fc00000, 0x7f800000, 0xbf800000, 0x40000000, -1, 2**32, True):
            changed = rows()
            changed[0]["gain_bits"][3] = bits
            with self.assertRaises(ValueError):
                module.parse_trace(encode(changed), 160, "observe")

    def test_missing_or_extra_fields_rejected(self):
        for missing in (True, False):
            changed = rows()
            if missing:
                del changed[0]["gain_bits"]
            else:
                changed[0]["new"] = 1
            with self.assertRaises(ValueError):
                module.parse_trace(encode(changed), 160, "observe")

    def test_bad_or_duplicate_json_not_silently_ignored(self):
        good = encode(rows())
        for bad in (b"broken aec3_synthesis_selection\n", good.replace(b'"block_index": 0',
                               b'"block_index": 0, "block_index": 0', 1)):
            with self.assertRaises((ValueError, json.JSONDecodeError)):
                module.parse_trace(bad, 160, "observe")

    def test_input_and_trace_bounds_rejected(self):
        for count in (0, 64, 256160, True):
            with self.assertRaises(ValueError):
                module.parse_trace(encode(rows()), count, "observe")
        with self.assertRaises(ValueError):
            module.parse_trace(b"x" * (16 * 1024 * 1024 + 1), 160, "observe")

    def test_force_mode_requires_actual_change_semantics(self):
        changed = rows("force-linear")
        changed[1]["forced"] = True
        with self.assertRaises(ValueError):
            module.parse_trace(encode(changed), 160, "force-linear")

    def test_symlink_source_tree_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "original").write_bytes(b"source")
            (root / "alias").symlink_to(root / "original")
            with self.assertRaises(ValueError):
                module.manifest(root)


if __name__ == "__main__":
    unittest.main()
