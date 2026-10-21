"""Known answers for the D17 HDI sample-coordinate model, not DSP quality."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_alignment import buffered_reference, mismatch, s16_bytes, shifted


class AlignmentTests(unittest.TestCase):
    def test_native_queue_known_answers(self):
        for count in (256, 384, 768, 4096):
            raw = [(j * 97 % 65536) - 32768 for j in range(count)]
            for delay in (0, 20, 1600):
                with self.subTest(count=count, delay=delay):
                    actual, pending = buffered_reference(raw, delay)
                    expected = [0 if j < delay else raw[j - delay] for j in range(count // 256 * 256)]
                    self.assertEqual(actual, expected)
                    self.assertEqual(pending, count % 256)

    def test_boundary_direction(self):
        actual, pending = buffered_reference(list(range(512)), 20)
        self.assertEqual(actual[:20], [0] * 20)
        self.assertEqual(actual[20:24], [0, 1, 2, 3])
        self.assertEqual(actual[256], 236)
        self.assertEqual(actual[-1], 491)
        self.assertEqual(pending, 0)

    def test_negative_coordinates_and_double_delay(self):
        raw = list(range(512))
        used = shifted(raw, 20)
        for delay in (19, 21, 16, 640):
            self.assertGreater(mismatch(shifted(raw, delay), used), 0)
        self.assertEqual(shifted(used, 20), shifted(raw, 40))
        self.assertEqual(mismatch(shifted([0] * 512, 640), [0] * 512), 0)

    def test_s16le(self):
        self.assertEqual(s16_bytes([-32768, -1, 0, 32767]), b'\x00\x80\xff\xff\x00\x00\xff\x7f')

    def test_fail_closed(self):
        for delay in (-1, 1601, True, 1.25):
            with self.assertRaises(ValueError):
                buffered_reference([0] * 256, delay)
        with self.assertRaises(ValueError):
            buffered_reference([0] * 127, 20)
        with self.assertRaises(ValueError):
            mismatch([0], [])


if __name__ == '__main__':
    unittest.main()
