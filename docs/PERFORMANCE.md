# Performance and Release Gates

## Automated benchmarks

`ap_bench` drives the complete 16 kHz two-mic CALL DSP graph and reports average/p50/p95/p99/max per-frame time, 10 ms deadline misses, RTF, state bytes, AEC backend/block/partitions/taps, ERLE, delay error, drift ppm, sample slips, route jumps, AEC resets and RES state.

```bash
./build/ap_bench <seconds> <max_rtf> <max_p99_us>
./build/ap_bench 120 0.40 9000
```

`ap_runtime_bench` paces submissions at a real 10 ms cadence through the dual-core worker and reports/gates input-full, output-drop, DSP overrun and FULL/LITE/SAFE residence.

```bash
./build/ap_runtime_bench <seconds> <max_overruns> <min_full_ratio> <dsp_cpu>
./build/ap_runtime_bench 120 0 0.999 1
```

Target wrappers record CPU/kernel/frequency context and `/usr/bin/time -v` when available:

```bash
./scripts/run-target-benchmark.sh ./build/ap_bench 120 0.40 9000 1
./scripts/run-target-soak.sh ./build/ap_runtime_bench 28800 0 0.999 1
```

The second command defaults to an 8 h nominal soak.

## Initial Cortex-A32 product gates

| Metric | Initial gate |
|---|---:|
| DSP p99 | <9 ms preferred, <10 ms hard |
| DSP p95 | <7 ms |
| 10 ms deadline misses | 0 nominal |
| Two-core average CPU | target <=35-40%, lower preferred |
| Pipeline/runtime steady-state heap growth | 0 in data plane |
| Pipeline state | <=128 KiB API ceiling |
| Runtime state | <=64 KiB API ceiling |
| Input-full/output-drop | 0 nominal |
| DSP overruns | 0 nominal |
| FULL residence | >=99.9% nominal |
| 8 h soak | no XRUN/queue/deadline regression |

CPU/RSS/thermal/power are not measured claims until the same binaries run on the shipping board/kernel/compiler/DVFS/audio route.

## CI matrix

The release gate is:

- GCC and Clang native build/tests with assertions retained in Release;
- SDK install smoke for core/runtime static libraries and public headers;
- strict Clang warnings;
- ASan/UBSan including the Linux runtime integration test;
- MDF default and NLMS fallback;
- 8/16/24/32/48 kHz contracts;
- AEC convergence/geometry/double-talk;
- slow drift + sample-slip and abrupt route-jump reset;
- frequency RES and SAFE/double-talk fallback;
- runtime start/backpressure/output-drop/semaphore wakeup/deinit lifecycle;
- libFuzzer smoke;
- optional ALSA example compilation with `libasound2-dev` only in that job;
- paced runtime benchmark smoke;
- Cortex-A32 cross-build of both portable core and Linux runtime libraries.

## Acoustic release corpus

At minimum include far-end-only at multiple playback levels, near-end-only at multiple distances/angles, true double-talk, enclosure/path changes, injected 0/20/40/80/120/180 ms delays, ppm-level clock mismatch, stationary and non-stationary noise, quiet-room speech and CPU/DDR contention soak.

Measure ERLE/residual echo, SI-SDR or segmental SNR, STOI, PESQ/POLQA when licensing permits, plus VAD precision/recall. Do not trade double-talk naturalness for a single far-end-only score.

## Optimization order

1. Correct DAC reference and synchronization first.
2. Reduce measured AEC tail/active partitions.
3. Increase adaptation stride only after path-change tests.
4. Use hardware timestamps to narrow delay tracking where possible.
5. Profile MDF complex MAC/FFT and NS/RES FFT hot spots before adding NEON assembly.
6. Use SAFE/broadband RES when headroom is tight.
7. Consider neural NS or a heavier AEC backend only after target measurements demonstrate headroom.

## Target profiling

Use RelWithDebInfo and the shipping governor:

```bash
perf stat -e cycles,instructions,cache-misses,context-switches ./build/ap_bench 120 0.40 9000
perf record -g ./build/ap_bench 120
```

Also capture `top -H`, `/proc/<pid>/status`, IRQ affinity, ALSA XRUN counters, thermal zones and product power measurements.
