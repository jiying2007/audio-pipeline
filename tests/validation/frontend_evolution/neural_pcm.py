#!/usr/bin/env python3
"""Research-only bounded PCM wrapper around two pristine streaming ONNX graphs.

This deliberately differs from the upstream whole-file centered/reflected STFT
demo: 256 zero samples precede the stream, and zero extension is allowed only
after explicit end-of-stream. No shipping API, weights or defaults are changed.
"""
from __future__ import annotations

from pathlib import Path
import time
import numpy as np

from contracts import require
import external_source

NFFT, HOP, RATE, MAX_PUSH = 512, 256, 16000, 160
MODELS = {
    'gtcrn': {'path': 'stream/onnx_models/gtcrn_simple.onnx', 'window': 'sqrt-hann',
              'caches': {'conv_cache': [2, 1, 16, 16, 33], 'tra_cache': [2, 3, 1, 1, 16],
                         'inter_cache': [2, 1, 33, 16]}},
    'ul-unas': {'path': 'ulunas_onnx/onnx_models/ulunas_stream_simple.onnx', 'window': 'hann',
                'caches': {'conv_cache': [1, 5358], 'tfa_cache': [1, 402], 'inter_cache': [1, 1056]}},
}


class ONNXModel:
    def __init__(self, source: Path, name: str):
        require(name in MODELS, 'unregistered neural model')
        receipt = external_source.admitted(source, name)
        self.name, self.spec = name, MODELS[name]
        self.model_sha256 = receipt['files_sha256'][self.spec['path']]
        # Verify bytes/admission BEFORE loading executable graph.
        import onnxruntime as ort
        require(ort.__version__ == '1.23.2', 'unregistered ONNX Runtime version')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(str(source / name / self.spec['path']),
                                            options, providers=['CPUExecutionProvider'])
        wanted = {'mix': [1, 257, 1, 2], **self.spec['caches']}
        got = {v.name: v.shape for v in self.session.get_inputs()}
        require(got == wanted and all(v.type == 'tensor(float)' for v in self.session.get_inputs()),
                'ONNX input contract drift')
        wanted_out = {'enh': [1, 257, 1, 2],
                      **{k + '_out': v for k, v in self.spec['caches'].items()}}
        require({v.name: v.shape for v in self.session.get_outputs()} == wanted_out,
                'ONNX output contract drift')
        self.output_names = list(wanted_out)
        self.reset()

    def reset(self):
        self.caches = {k: np.zeros(v, np.float32) for k, v in self.spec['caches'].items()}

    @property
    def cache_bytes(self):
        return sum(v.nbytes for v in self.caches.values())

    def __call__(self, spec):
        values = self.session.run(self.output_names, {'mix': spec, **self.caches})
        require(all(np.isfinite(v).all() for v in values), 'non-finite neural output/cache')
        self.caches = {k: values[i + 1] for i, k in enumerate(self.spec['caches'])}
        return values[0]


class PCMStream:
    """Bounded DSP working state; caller owns output and timing history.

With real samples [0, (k+2)*256), output block [k*256, (k+1)*256)
is final. No end padding occurs before flush. Push accepts at most 10 ms.
"""
    def __init__(self, transform, window: str, sample_rate: int = RATE):
        require(sample_rate == RATE, 'native model requires 16000 Hz; explicit SRC is separate')
        require(window in ('hann', 'sqrt-hann'), 'unregistered analysis window')
        self.transform = transform
        if hasattr(transform, 'reset'):
            transform.reset()
        self.window = np.hanning(NFFT + 1)[:-1]
        if window == 'sqrt-hann':
            self.window = np.sqrt(self.window)
        self.window_squared = self.window * self.window
        self.history = np.zeros(HOP, np.float32)
        self.pending = np.empty(0, np.float32)
        self.overlap = np.zeros(NFFT, np.float64)
        self.normalizer = np.zeros(NFFT, np.float64)
        self.input_samples = self.output_samples = self.frames = 0
        self.high_water_samples = 0
        self.closed = False

    def _hop(self, new):
        frame = np.concatenate((self.history, new))
        frequency = np.fft.rfft(frame * self.window)
        tensor = np.stack((frequency.real, frequency.imag), axis=-1).astype(np.float32)[None, :, None, :]
        enhanced = self.transform(tensor)
        require(enhanced.shape == (1, 257, 1, 2) and np.isfinite(enhanced).all(),
                'invalid enhanced spectrum')
        spectrum = enhanced[0, :, 0, 0].astype(np.float64) + 1j * enhanced[0, :, 0, 1]
        self.overlap += np.fft.irfft(spectrum, n=NFFT) * self.window
        self.normalizer += self.window_squared
        result = None
        if self.frames > 0:
            require(np.all(self.normalizer[:HOP] > 1e-12), 'invalid OLA normalization')
            result = (self.overlap[:HOP] / self.normalizer[:HOP]).astype(np.float32)
            require(np.isfinite(result).all(), 'non-finite PCM output')
        self.overlap[:HOP] = self.overlap[HOP:]
        self.overlap[HOP:] = 0
        self.normalizer[:HOP] = self.normalizer[HOP:]
        self.normalizer[HOP:] = 0
        self.history = new.copy()
        self.frames += 1
        return result

    def push(self, samples):
        require(not self.closed, 'push after flush')
        samples = np.asarray(samples)
        require(samples.ndim == 1 and 0 < samples.size <= MAX_PUSH,
                'push must contain 1..160 mono samples')
        require(np.isrealobj(samples) and np.isfinite(samples).all()
                and np.all(samples >= -1) and np.all(samples <= 1),
                'non-finite or unnormalized PCM input')
        # Validate all input before changing any state.
        samples = samples.astype(np.float32)
        self.input_samples += samples.size
        self.pending = np.concatenate((self.pending, samples))
        self.high_water_samples = max(self.high_water_samples, self.pending.size)
        require(self.high_water_samples <= HOP - 1 + MAX_PUSH, 'unbounded PCM FIFO')
        result = []
        while self.pending.size >= HOP:
            chunk = self._hop(self.pending[:HOP])
            self.pending = self.pending[HOP:].copy()
            if chunk is not None:
                result.append(chunk)
                self.output_samples += len(chunk)
        return np.concatenate(result) if result else np.empty(0, np.float32)

    def flush(self):
        require(not self.closed and self.input_samples > 0, 'empty/double flush')
        result = []
        if self.pending.size:
            chunk = self._hop(np.pad(self.pending, (0, HOP - self.pending.size)))
            if chunk is not None:
                result.append(chunk)
        chunk = self._hop(np.zeros(HOP, np.float32))
        if chunk is not None:
            result.append(chunk)
        pending_output = np.concatenate(result)
        remaining = self.input_samples - self.output_samples
        require(0 < remaining <= len(pending_output), 'flush accounting drift')
        output = pending_output[:remaining].copy()
        self.output_samples += len(output)
        self.pending = np.empty(0, np.float32)
        self.closed = True
        require(self.output_samples == self.input_samples, 'lost/extra output samples')
        return output

    @property
    def explicit_working_array_bytes(self):
        # Arrays owned here + NN recurrent caches; excludes runtime arena,
        # Python objects, transient FFT arrays, caller PCM and process RSS.
        arrays = (self.window, self.window_squared, self.history, self.pending,
                  self.overlap, self.normalizer)
        return sum(v.nbytes for v in arrays) + getattr(self.transform, 'cache_bytes', 0)


def run_pcm(model, window, samples, chunk=MAX_PUSH):
    require(1 <= chunk <= MAX_PUSH, 'unregistered caller chunk')
    stream = PCMStream(model, window)
    output, timings, available = [], [], []
    for start in range(0, len(samples), chunk):
        tick = time.perf_counter_ns()
        value = stream.push(samples[start:start + chunk])
        timings.append(time.perf_counter_ns() - tick)
        if value.size:
            output.append(value)
            available.append({'input_samples': stream.input_samples,
                              'output_samples': stream.output_samples})
    tick = time.perf_counter_ns()
    output.append(stream.flush())
    flush_ns = time.perf_counter_ns() - tick
    return np.concatenate(output), {'push_ns': timings, 'flush_ns': flush_ns,
                                   'availability': available, 'high_water_samples': stream.high_water_samples,
                                   'network_frames_including_flush': stream.frames,
                                   'explicit_working_array_bytes_after_flush': stream.explicit_working_array_bytes}


def quantize_s16(samples):
    scaled = np.asarray(samples, np.float64) * 32768
    require(np.isfinite(scaled).all(), 'non-finite output quantization')
    clips = int(np.count_nonzero((scaled > 32767) | (scaled < -32768)))
    rounded = np.where(scaled >= 0, np.floor(scaled + 0.5), np.ceil(scaled - 0.5))
    return np.clip(rounded, -32768, 32767).astype('<i2'), clips
