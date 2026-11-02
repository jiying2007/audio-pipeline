#!/usr/bin/env python3
"""A3-R2-T2-S0 offline metadata decoder tests; no archived A3 import or I/O."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

MODULE = Path(__file__).with_name("fe09_a3_r2_metadata_json.py")
SPEC = importlib.util.spec_from_file_location("a3_r2_t2_s0_metadata", MODULE)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class StrictMetadataTests(unittest.TestCase):
    def denied(self, raw, reason, **options):
        with self.assertRaises(M.MetadataRejected) as caught:
            M.parse_metadata_json(raw, **options)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(str(caught.exception), reason)

    def test_nested_finite_round_trip(self):
        value = {"a": [True, False, None, {"v": 12.5, "int": -42}],
                 "tag": "中文", "rate": 1.5e-3}
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.assertEqual(M.parse_metadata_json(raw), value)

    def test_top_level_array_and_scalars(self):
        for raw, expected in ((b'[]', []), (b'null', None),
                              (b'true', True), (b'123', 123),
                              (b'"ok"', "ok")):
            self.assertEqual(M.parse_metadata_json(raw), expected)

    def test_numeric_upper_finite_range(self):
        value = M.parse_metadata_json(b'{"a":1e308,"b":-1e308}')
        self.assertEqual(value["a"], 1e308)
        self.assertEqual(value["b"], -1e308)

    def test_normal_finite_exponents(self):
        value = M.parse_metadata_json(b'{"a":1E-3,"b":0e-9999,"c":-0.0}')
        self.assertEqual(value, {"a": 0.001, "b": 0.0, "c": -0.0})

    def test_literal_nan_and_infinity(self):
        for item in (b'NaN', b'Infinity', b'-Infinity'):
            self.denied(b'{"a":[' + item + b']}',
                        "A3_METADATA_NONFINITE_NUMBER")

    def test_json_exponent_overflow(self):
        for item in (b'1e999', b'-1e999', b'9E+999', b'1e309'):
            self.denied(b'{"v":' + item + b'}',
                        "A3_METADATA_NONFINITE_NUMBER")

    def test_nested_overflow(self):
        self.denied(b'[{"a":{"b":[0,1e999]}}]',
                    "A3_METADATA_NONFINITE_NUMBER")

    def test_nonzero_numeric_underflow(self):
        for item in (b'1e-999', b'-5E-9999', b'0.001e-999'):
            self.denied(b'[' + item + b']',
                        "A3_METADATA_FLOAT_UNDERFLOW")

    def test_duplicate_object_key(self):
        self.denied(b'{"k":1,"k":2}', "A3_METADATA_DUPLICATE_KEY")

    def test_escaped_duplicate_object_key(self):
        self.denied(b'{"k":1,"\\u006b":2}', "A3_METADATA_DUPLICATE_KEY")

    def test_duplicate_nested_key(self):
        self.denied(b'{"ok":{"x":1,"x":2}}', "A3_METADATA_DUPLICATE_KEY")

    def test_duplicate_in_array_object(self):
        self.denied(b'[0, {"v":1,"v":2}]', "A3_METADATA_DUPLICATE_KEY")

    def test_reject_oversize_and_empty(self):
        raw = b'{"v":1}'
        self.assertEqual(M.parse_metadata_json(raw, cap=len(raw)), {"v": 1})
        self.denied(raw, "A3_METADATA_BODY_BOUND", cap=len(raw) - 1)
        self.denied(b'', "A3_METADATA_BODY_BOUND")

    def test_invalid_cap_and_type(self):
        for cap in (0, -1, M.MAX_CAP + 1, 1.5, True, None):
            self.denied(b'{}', "A3_METADATA_INVALID_CAP", cap=cap)
        for item in (bytearray(b'{}'), '{}', None, memoryview(b'{}')):
            self.denied(item, "A3_METADATA_BYTES_REQUIRED")

    def test_integer_token_limit(self):
        self.denied(b'[' + b'1' * (M.NUMBER_TOKEN_CAP + 1) + b']',
                    "A3_METADATA_NUMBER_TOKEN_BOUND")
        self.assertEqual(M.parse_metadata_json(b'[' + b'1' * 128 + b']')[0],
                         int("1" * 128))

    def test_float_token_limit(self):
        self.denied(b'[0.' + b'0' * (M.NUMBER_TOKEN_CAP + 1) + b'1]',
                    "A3_METADATA_NUMBER_TOKEN_BOUND")

    def test_malformed_json(self):
        for item in (b'{', b'{"a":}', b'[1,]', b'{"a":01}',
                     b'{"a":+1}', b'garbage'):
            self.denied(item, "A3_METADATA_INVALID_JSON")

    def test_bom_and_invalid_utf8(self):
        self.denied(b'\xef\xbb\xbf{}', "A3_METADATA_UTF8_BOM")
        self.denied(b'{"x":"\xff"}', "A3_METADATA_INVALID_JSON")

    def test_reject_surrogate_in_key_and_value(self):
        for item in (b'{"\\ud800":1}', b'{"v":"\\udfff"}',
                     b'{"v":["\\ud800"]}'):
            self.denied(item, "A3_METADATA_UNPAIRED_SURROGATE")

    def test_valid_surrogate_pair(self):
        self.assertEqual(M.parse_metadata_json(b'{"emoji":"\\ud83d\\ude00"}'),
                         {"emoji": "😀"})

    def test_nesting_depth_exact_boundary(self):
        for n in (1, M.MAX_NESTING):
            raw = b'[' * n + b'0' + b']' * n
            self.assertIsInstance(M.parse_metadata_json(raw), list)
        self.denied(b'[' * (M.MAX_NESTING + 1) + b'0' +
                    b']' * (M.MAX_NESTING + 1), "A3_METADATA_NESTING_BOUND")

    def test_excessive_nesting_fails_boundedly(self):
        raw = b'[' * 1400 + b'0' + b']' * 1400
        try:
            M.parse_metadata_json(raw)
        except M.MetadataRejected as exc:
            self.assertIn(exc.reason, ("A3_METADATA_NESTING_BOUND",
                                       "A3_METADATA_INVALID_JSON"))
        else:
            self.fail("deep JSON must never be accepted")

    def test_authority_descriptor_is_defensive(self):
        report = M.authority_boundary()
        self.assertEqual(report["status"], M.STATUS)
        self.assertTrue(report["syntax_only"])
        self.assertEqual(set(report) - {"schema_version", "status", "syntax_only"},
                         set(M.DENIALS))
        self.assertTrue(all(report[key] is False for key in M.DENIALS))
        report["shipping_authority"] = True
        self.assertFalse(M.authority_boundary()["shipping_authority"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
