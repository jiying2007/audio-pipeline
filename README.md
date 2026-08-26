# audio-pipeline

English | [简体中文](README.zh-CN.md)

A dependency-light real-time speech front end for low-power embedded Linux, targeting dual-core Cortex-A32-class SoCs and similar low-end Arm Linux CPUs for hands-free calls and voice assistants.

Default path:

`S16 capture -> rate adapter -> HPF -> 2-mic TDOA/delay-and-sum -> delay+drift tracker -> MDF/AUMDF-lite AEC -> subband residual echo suppression -> STFT Wiener NS -> VAD -> AGC/limiter -> mono S16`

The synchronous DSP path is caller-owned, bounded and allocation-free. No third-party DSP source is vendored.

## Low-compute design

- Public contract: fixed 10 ms frames.
- I/O: 8/16/24/32/48 kHz; heavy DSP stays at 8 or 16 kHz.
- Default AEC: clean-room partitioned MDF/AUMDF-lite, five 2 ms blocks per 10 ms frame.
- 16 kHz MDF geometry: 32-sample block, 64-point FFT, at most 60 partitions for the 120 ms hard tail ceiling.
- `AP_ENABLE_MDF_AEC=OFF` selects the independently tested NLMS fallback.
- FULL/LITE/SAFE reduces active AEC partitions/update rate and array work before removing essential AEC/NS/AGC/VAD.
- Cortex-A32 NEON complex MAC is optional; scalar C remains available.

The architecture was informed by aispeech-earbuds, athena-signal, SpeexDSP MDF/AUMDF literature/practices, WebRTC Audio Processing, RNNoise and DeepFilterNet. See [THIRD_PARTY.md](THIRD_PARTY.md) for the clean-room policy.

## Echo synchronization and clock drift

The render reference must be the signal actually sent to the DAC after software mixing/gain. The bounded render ring is searched every ~100 ms with a low-cost coarse correlation plus one-sample fine search.

- A >20 ms change is treated as a route/buffer-path jump: snap delay and reset learned AEC state.
- Small movement is treated as jitter/clock mismatch.
- A ppm estimator integrates persistent drift and performs slow single-sample reference insert/drop correction only after fractional error reaches a whole sample.
- Metrics expose `estimated_drift_ppm`, `delay_error_samples`, `reference_sample_slips`, `delay_jumps` and `aec_resets`.

Hardware playback/capture timestamps are still preferred when available because they narrow the search and distinguish clock domains more directly.

## Residual echo suppression

FULL/LITE reuse the NS STFT to apply frequency-dependent residual suppression from the AEC-predicted echo spectrum, avoiding another model or large dependency. Double-talk disables subband RES so near-end speech is not aggressively removed. SAFE or NS-off falls back to the cheaper broadband RES path.

## Dual-core Linux runtime

Recommended split:

- Core 0: ALSA/audio I/O, render-reference acquisition, codec/application work.
- Core 1: one serial DSP worker.

The cores use bounded SPSC queues. The worker blocks on a POSIX semaphore when idle rather than polling. Affinity and `SCHED_FIFO` are best-effort optimizations. Runtime telemetry exposes submitted/processed frames, input-full/output-drop events, DSP overruns, last/max DSP time and current quality state.

This avoids a cross-core barrier between AEC/NS every 10 ms, which is often a net loss on a small dual-core CPU because of wakeup/cache/synchronization overhead.

## Profiles

| Profile | AEC | NS/RES | Beamforming | AGC | Use |
|---|---:|---:|---:|---:|---|
| `AP_PROFILE_CALL` | 96 ms default tail | stronger | 2-mic | conservative | full-duplex call |
| `AP_PROFILE_ASSISTANT` | 80 ms default tail | gentler | 2-mic | slightly hotter | wake/ASR/assistant |

## Build

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/ap_bench 30
```

Install the SDK to a staging prefix:

```bash
cmake --install build --prefix ./stage
```

The default Linux build installs `libaudio_pipeline.a`, `libaudio_pipeline_runtime.a` and the public headers under `include/audio_pipeline/`. When `AP_ENABLE_RUNTIME=OFF`, only the portable core library and headers are installed.

Cortex-A32 cross-build:

```bash
cmake -S . -B build-arm \
  -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/arm-cortex-a32.cmake \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build-arm --parallel
```

NLMS fallback:

```bash
cmake -S . -B build-nlms -DAP_ENABLE_MDF_AEC=OFF
cmake --build build-nlms --parallel
ctest --test-dir build-nlms --output-on-failure
```

Optional ALSA examples do not affect the minimum dependency set:

```bash
cmake -S . -B build-alsa -DAP_BUILD_ALSA_EXAMPLE=ON
cmake --build build-alsa --target ap_alsa_duplex ap_alsa_runtime_duplex
```

`ap_alsa_runtime_duplex` demonstrates the intended two-core product wiring, XRUN recovery, silent/NULL render reference handling and runtime telemetry.

## Performance and target-board gates

`ap_bench` reports average/p50/p95/p99/max frame time, 10 ms deadline misses, RTF, state size, AEC geometry, ERLE, delay/drift/sample-slip, RES and reset metrics.

```bash
./build/ap_bench 120 0.40 9000
./scripts/run-target-benchmark.sh ./build/ap_bench 120 0.40 9000 1
```

`ap_runtime_bench` paces real 10 ms submissions through the worker and gates queue drops, DSP overruns and FULL/LITE/SAFE residence. The target soak wrapper defaults to eight hours:

```bash
./scripts/run-target-soak.sh ./build/ap_runtime_bench 28800 0 0.999 1
```

GitHub x86 numbers are regression signals only; they are not Cortex-A32 CPU/RSS/power claims. Final acceptance must run on the shipping board/kernel/compiler/DVFS/audio route.

## Verification

CI is designed to cover GCC/Clang, strict warnings, ASan/UBSan, MDF and NLMS fallback, 8/16/24/32/48 kHz contracts, double-talk, drift/path-jump/RES contracts, bounded runtime/backpressure/wakeup, libFuzzer smoke, optional ALSA example compilation, runtime benchmark smoke and Cortex-A32 cross-build.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [DSP design](docs/DSP_DESIGN.md)
- [Performance and release gates](docs/PERFORMANCE.md)
- [Porting](docs/PORTING.md)
- [Tuning](docs/TUNING.md)

## License

Apache-2.0. The minimum implementation contains no vendored third-party DSP source.
