# Performance and Release Gates

## Principle

Hosted x86 CI and Arm cross-builds are regression/build signals only. Product performance is certified on the shipping SoC, kernel, compiler, DVFS policy and audio route. This applies equally to Cortex-A7, Cortex-A32 and other Arm profiles.

## Automated benchmarks

Full graph:

```bash
./build/ap_bench <seconds> <max_rtf> <max_p99_us> [active|idle]
./build/ap_bench 120 0.40 9000 active
./build/ap_bench 120 0.40 9000 idle
```

Runtime:

```bash
./build/ap_runtime_bench <seconds> <max_overruns> <min_full_ratio> <dsp_cpu>
./build/ap_runtime_bench 120 0 0.999 -1
```

Target wrappers:

```bash
./scripts/run-target-benchmark.sh ./build/ap_bench 120 0.40 9000 1
./scripts/run-target-soak.sh ./build/ap_runtime_bench 28800 0 0.999 1
```

The soak defaults to 8 h.

Optimization branches compare base/head on the same hosted runner:

```bash
sh scripts/compare-perf.sh origin/main 7 20
sh scripts/compare-ns-perf.sh origin/main 7 50000
sh scripts/compare-resampler-perf.sh origin/main 7 100000
sh scripts/compare-runtime-perf.sh origin/main 7 100000 10000
```

A >10% same-runner regression fails the comparator; smaller deltas remain diagnostic until board profiling confirms them.

## Product resource classes

Measure each SKU at the resource class it intends to ship:

- `TINY`: 8 kHz internal default, shortest built-in tail, BF tracking off;
- `LOW`: 16 kHz internal, shorter AEC tail;
- `STANDARD`: 16 kHz internal, full built-in classical geometry.

Resource class is not inferred from CPU model. If a Cortex-A7 meets STANDARD thermal/power/latency gates, it may ship STANDARD. If an AArch64 SKU needs LOW for product power, that is equally valid.

## Initial low-compute Arm gates

| Metric | Initial gate |
|---|---:|
| DSP p99 | <9 ms preferred, <10 ms hard |
| DSP p95 | <7 ms |
| 10 ms deadline misses | 0 nominal |
| Average CPU | product target <=35-40%, lower preferred |
| Data-plane heap growth | 0 |
| Pipeline state | <=80,000 B hard public ceiling |
| Runtime state | <=64 KiB hard public ceiling |
| Input-full/output-drop | 0 nominal |
| DSP overruns | 0 nominal |
| FULL residence | >=99.9% nominal |
| 8 h soak | no XRUN/queue/deadline regression |

The CPU percentage target is a starting point, not a universal architecture rating. TINY/LOW may use a lower product power target.

## Current low-compute policies

- FFT uses a fixed read-only root table for current 32/64/256/512 geometries;
- MDF keeps rolling reference-spectrum power and partition-major updates;
- complete render-tail silence bypasses MDF echo synthesis work;
- fixed dB/geometry controls are precomputed at init;
- render ring uses a power-of-two mask;
- frequency RES retains echo power bins and reuses one complex FFT scratch;
- frame scratch buffers with non-overlapping lifetimes share storage;
- fixed 10 ms boundary ratios avoid generic per-sample position math;
- scalar/NEON kernels are compile-time selected;
- fast math is separately opt-in and never hidden in a platform toolchain.

## CI release matrix

Required automated gates:

- architecture/module boundary lint;
- GCC and Clang native build/tests;
- strict Clang warnings;
- MDF and NLMS backends;
- explicit fast-math build/test;
- ASan/UBSan including Linux runtime;
- libFuzzer smoke;
- optional ALSA example compilation;
- full 8/16/24/32/48 kHz contracts and all IO/internal-rate smoke;
- AEC convergence, double-talk, drift/path-jump and RES contracts;
- runtime queue/backpressure/wakeup/lifecycle and paired performance smoke;
- generic ARMv7-A scalar cross-build;
- Cortex-A7 scalar and NEON cross-builds;
- Cortex-A32 NEON cross-build;
- generic AArch64 NEON cross-build.

## Acoustic/product certification corpus

Include far-end-only at several playback levels, near-end at multiple distances/angles, true double-talk, enclosure/path changes, injected delays, clock mismatch, stationary/non-stationary noise, quiet speech and CPU/DDR contention.

Record ERLE/residual echo, SI-SDR or segmental SNR, STOI, PESQ/POLQA when licensing permits, VAD precision/recall, CPU/RSS/cache/context-switches, thermal zones, power and XRUN counters.

Do not accept a CPU optimization that regresses delay convergence or double-talk naturalness.

## Target profiling

```bash
perf stat -e cycles,instructions,cache-misses,context-switches ./build/ap_bench 120 0.40 9000 active
perf record -g ./build/ap_bench 120 0.40 9000 active
./build/ap_bench 120 0.40 9000 idle
```

Also capture `top -H`, `/proc/<pid>/status`, CPU online/cpuset state, IRQ affinity, governor/frequency, ALSA XRUNs and product power measurements. Store them with the SKU certification record defined in `PLATFORM_SUPPORT.md`.
