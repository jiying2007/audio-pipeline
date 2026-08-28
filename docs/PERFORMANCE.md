# Performance and Release Gates

## Principle

Hosted x86 CI, QEMU and Arm cross-builds are regression/correctness signals only. Product performance is certified on the shipping SoC, kernel, compiler, DVFS policy, memory system and audio route.

## Automated hosted regression

High-level graph:

```bash
./build/ap_bench <seconds> <max_rtf> <max_p99_us> [active|idle]
```

Runtime:

```bash
./build/ap_runtime_bench <seconds> <max_overruns> <min_full_ratio> <dsp_cpu>
```

Paired same-runner comparators:

```bash
sh scripts/compare-perf.sh origin/main 7 20
sh scripts/compare-ns-perf.sh origin/main 7 50000
sh scripts/compare-resampler-perf.sh origin/main 7 100000
sh scripts/compare-runtime-perf.sh origin/main 7 100000 10000
```

Full-graph/NS/runtime comparators use the existing >10% paired regression gate. The FAST resampler microbenchmark is sub-microsecond, so it fails only when the paired regression is **both >10% and >0.05 us per 10 ms frame**; this prevents timer/wrapper overhead from dominating a tiny denominator while still blocking a material kernel regression. Smaller deltas are diagnostic until board profiling confirms significance.

The current v0.5 candidate hosted same-runner signal is essentially flat for the full graph: approximately +0.40% active / -0.10% idle; runtime minimal/full were approximately -5.56% / -1.87%. These are x86 runner signals only.

## SKU memory/ROM gates

Quality CI verifies physical pruning, not only runtime bypass.

Current hosted GCC reference:

| Product | Pipeline state |
|---|---:|
| full | 78,072 B |
| LOW build envelope | 46,904 B |
| TINY build envelope | 25,384 B |
| RAW/resampler-only | 1,064 B |

Current Linux runtime reference:

| Envelope | Runtime state |
|---|---:|
| full 48 kHz / 2 mic / depth 8 | 31,824 B |
| constrained 16 kHz / 1 mic / depth 4 | 4,464 B |

CI additionally links final consumer executables with section GC and verifies `RAW < voice < full` ELF size. These exact hosted values are not ABI or target-ROM promises.

## Resampler quality gate

`BANDLIMITED` is default. Supported downsampling ratios have automated tone contracts requiring preserved 1 kHz passband energy and at least approximately 14 dB attenuation for representative tones well into the stopband. Frame history/reset behavior is also tested.

`FAST` retains the legacy lightweight path and is independently A/B measured. Shipping products may select FAST only as an explicit quality/performance decision.

## Product resource/build classes

Runtime resource classes remain product tuning envelopes:

- TINY: 8 kHz internal default, shortest built-in tail, no BF tracking;
- LOW: 16 kHz internal, shorter AEC tail;
- STANDARD: 16 kHz internal, full built-in classical geometry.

Compile-time SKU envelopes can additionally cap max I/O/internal rate, mic count, delay, AEC tail and runtime queue depth. Runtime class and compile-time cap are separate concepts.

## Initial target-board gates

| Metric | Initial gate |
|---|---:|
| DSP p99 | <9 ms preferred, <10 ms hard |
| DSP p95 | <7 ms |
| 10 ms deadline misses | 0 nominal |
| Average CPU | product target <=35-40%, lower preferred |
| Data-plane heap growth | 0 |
| Pipeline state | <=80,000 B public hard ceiling |
| Runtime state | <=64 KiB public hard ceiling |
| Input-full/output-drop | 0 nominal |
| DSP overruns | 0 nominal |
| FULL residence | >=99.9% nominal |
| 8 h soak | no XRUN/queue/deadline regression |

The CPU target is a starting product gate, not an architecture rating.

## Target wrappers

```bash
./scripts/run-target-benchmark.sh ./build/ap_bench 120 0.40 9000 1
./scripts/run-target-soak.sh ./build/ap_runtime_bench 28800 0 0.999 1
```

The soak defaults to 8 h.

## Realtime correctness gates

Performance acceptance also requires:

- TSan clean runtime ownership;
- ASan/UBSan clean data/control paths;
- no queue/backpressure/lifecycle contract regressions;
- ERLE only valid during proper far-end-only AEC observations;
- path/timestamp jumps reset stale convergence state;
- no degradation in delay convergence or double-talk behavior.

## CI quality matrix

Required repository signals include:

- architecture boundary lint;
- native GCC/Clang, strict warnings;
- MDF/NLMS, EMA/MCRA and precise/fast-math;
- BANDLIMITED default plus FAST composition/perf fallback;
- ASan/UBSan, ThreadSanitizer and libFuzzer smoke;
- >=90% hosted source line coverage;
- clang static analyzer;
- LOW/TINY/RAW/voice/module-only composition tests;
- pipeline/runtime state and final consumer ELF pruning;
- generic ARMv7-A, Cortex-A7 scalar/NEON, Cortex-A32 NEON and AArch64 cross-builds;
- Cortex-A7 NEON and AArch64 executable tests under QEMU;
- CMake/pkg-config installed SDK consumer tests;
- acoustic eval harness self-test;
- nightly longer fuzz.

## Acoustic/product corpus

A real certification corpus should include:

- far-end-only at several playback levels;
- near-end speech at multiple distances/angles;
- true double-talk;
- music/content echo;
- enclosure/path and speaker gain changes;
- injected delay and independent clock mismatch;
- stationary and non-stationary robot/environment noise;
- quiet speech;
- CPU/DDR/IRQ contention.

Record ERLE/residual echo, convergence time, SI-SDR or segmental SNR, STOI, PESQ/POLQA when licensing permits, VAD precision/recall, CPU/RSS/cache/context switches, thermal zones, power and XRUN/backpressure counters.

The repository `eval/` harness defines the interchange/threshold mechanism; private product audio remains external.

## Target profiling

```bash
perf stat -e cycles,instructions,cache-misses,context-switches ./build/ap_bench 120 0.40 9000 active
perf record -g ./build/ap_bench 120 0.40 9000 active
```

Also capture `top -H`, `/proc/<pid>/status`, CPU online/cpuset state, IRQ affinity, governor/frequency, ALSA XRUNs and product power measurements.

Store the result using `certification/record.schema.json`. A successful hosted release is not a product certification record.
