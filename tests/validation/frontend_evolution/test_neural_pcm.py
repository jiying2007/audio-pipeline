#!/usr/bin/env python3
"""Independent transport/OLA tests; optional admitted real-model qualification."""
import argparse
from pathlib import Path
import unittest
import numpy as np
from contracts import require
from neural_pcm import PCMStream, ONNXModel, MODELS, run_pcm, quantize_s16


class PCMTests(unittest.TestCase):
    def test_identity_tails_and_chunk_boundaries(self):
        rng = np.random.default_rng(1709)
        for window in ('hann', 'sqrt-hann'):
            for count in (1, 159, 160, 161, 319, 320, 64001):
                signal = rng.uniform(-0.3, 0.3, count).astype(np.float32)
                actual, trace = run_pcm(lambda x: x, window, signal)
                other, _ = run_pcm(lambda x: x, window, signal, chunk=37)
                self.assertEqual(actual.tobytes(), other.tobytes())
                self.assertLess(float(np.max(np.abs(actual - signal))), 2e-6)
                self.assertEqual(len(actual), count)
                self.assertLessEqual(trace['high_water_samples'], 415)

    def test_first_output_and_no_future_consumption(self):
        stream = PCMStream(lambda x: x, 'sqrt-hann')
        lengths = [len(stream.push(np.ones(160, np.float32) * .1)) for _ in range(4)]
        self.assertEqual(lengths, [0, 0, 0, 256])
        self.assertEqual(stream.input_samples, 640)
        self.assertEqual(stream.output_samples, 256)

    def test_invalid_input_is_atomic_and_lifecycle_is_explicit(self):
        stream = PCMStream(lambda x: x, 'hann')
        for data in ([], [np.nan], [np.inf], [2.0], [0.1+0.1j], np.array([-2**63], dtype=np.int64),
                     np.zeros(161), np.zeros((1, 160))):
            with self.assertRaises(ValueError):
                stream.push(data)
            self.assertEqual(stream.input_samples, 0)
        with self.assertRaises(ValueError):
            stream.flush()
        stream.push([0.1])
        stream.flush()
        for call in (stream.flush, lambda: stream.push([0.1])):
            with self.assertRaises(ValueError):
                call()
        for rate in (8000, 48000):
            with self.assertRaises(ValueError):
                PCMStream(lambda x: x, 'hann', sample_rate=rate)

    def test_quantization_boundary(self):
        out, clips = quantize_s16(np.array([-2, -1, -0.5/32768, 0.5/32768, 1, 2]))
        self.assertEqual(out.tolist(), [-32768, -32768, -1, 1, 32767, 32767])
        self.assertEqual(clips, 3)


def model_checks(source):
    # No speech scoring or model choice in this deterministic engineering test.
    signal = np.random.default_rng(1709).uniform(-.15, .15, 32161).astype(np.float32)
    records = {}
    for name, spec in MODELS.items():
        model = ONNXModel(source, name)
        a, trace = run_pcm(model, spec['window'], signal)
        b, _ = run_pcm(model, spec['window'], signal, chunk=37)
        require(a.tobytes() == b.tobytes(), 'model engineering partition/reset mismatch')
        changed = signal.copy()
        changed[16000:] *= -1
        future, _ = run_pcm(model, spec['window'], changed)
        # Only blocks finalized before the first differing input.
        cut = (16000 // 256 - 1) * 256
        require(a[:cut].tobytes() == future[:cut].tobytes(), 'model engineering prefix mismatch')
        require(a[16000:].tobytes() != future[16000:].tobytes(), 'model engineering future unchanged')
        silence, _ = run_pcm(model, spec['window'], np.zeros(321, np.float32))
        require(np.max(np.abs(silence)) <= 2e-6, 'model engineering silence output')
        records[name] = {'partition_and_reset_equal': True, 'causal_prefix_samples': cut,
                         'future_changed': True, 'silence_pass': True,
                         'model_cache_bytes': model.cache_bytes,
                         'high_water_samples': trace['high_water_samples']}
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    args, remaining = parser.parse_known_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PCMTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.source:
        import json
        print(json.dumps(model_checks(args.source), sort_keys=True))
