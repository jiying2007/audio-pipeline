# Performance and Release Gates

## Principle

Hosted x86 CI, QEMU and Arm cross-builds are regression/correctness signals only. Product performance is certified on the shipping SoC, kernel, compiler, DVFS policy, memory system and audio route.

Optimization policy is profile-driven. The repository keeps compile-time SCALAR/NEON infrastructure, but additional FFT/NS SIMD surface is accepted only when target-board profiling demonstrates material benefit and the acoustic/bit-level contracts appropriate to that path remain valid.

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

Full-graph/NS/full-runtime comparators use the existing >10% paired regression gate. Very small hosted microbenchmarks additionally require an absolute regression above a documented noise floor: the FAST resampler must regress by both >10% and >0.05 us per 10 ms frame, while the minimal runtime thread/queue round-trip must regress by both >10% and >1.0 us per 10 ms frame. The minimal runtime path is only a few microseconds and includes hosted scheduler/wakeup noise; the 1 us floor is 0.01% of the 10 ms realtime deadline. Shipping target-board p95/p99/deadline gates are unchanged and do not use these hosted noise floors.

## Current low-compute reductions

The v1.1 line adds several low-risk steady-state reductions without converting the graph into a dynamic scheduler:

- stable far-end-only AEC automatically increases adaptation stride to at least 4 after 50 valid frames;
- double talk/reference loss immediately restores the configured fast AEC cadence;
- SYNC delay search compares squared normalized correlation and removes a `sqrtf` from every candidate delay;
- fractional drift residue is consumed by linear reference interpolation while integer delay crossings remain explicit;
- output backpressure no longer causes DSP state discontinuity or later expensive reacquisition.

These are algorithmic/runtime policy changes and still require target-board measurement; hosted timing does not prove Cortex-A7/A32 CPU savings.

## SKU memory/ROM gates

Quality CI verifies physical pruning, not only runtime bypass.

Current hosted GCC reference:

| Product | Pipeline state |
|---|---:|
| full | 78,096 B |
| LOW build envelope | 46,928 B |
| TINY build envelope | 25,408 B |
| RAW/resampler-only | 1,064 B |

Current Linux runtime reference:

| Envelope | Runtime state |
|---|---:|
| full 48 kHz / 2 mic / depth 8 | 32,632 B |
| constrained 16 kHz / 1 mic / depth 4 | 5,080 B |

The diagnostics event/control plane remains inside the 32 KiB hosted full-runtime resource gate. Audio pre/post-roll storage is separately caller-owned Flight Recorder memory and is not included unless a product chooses to provision it.

CI additionally links final consumer executables with section GC and verifies `RAW < voice < full` ELF size. Exact hosted values are not ABI or target-ROM promises.

## Resampler quality gate

`BANDLIMITED` is default. Supported downsampling ratios have automated tone contracts requiring preserved 1 kHz passband energy and representative stopband attenuation. Frame history/reset behavior is also tested.

`FAST` retains the lightweight path and is independently A/B measured. Shipping products may select FAST only as an explicit quality/performance decision.

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
| Runtime state | <=64 KiB public hard ceiling; hosted full gate <=32 KiB |
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

- TSan-clean runtime/control/Flight Recorder ownership;
- ASan/UBSan-clean data/control paths;
- output backpressure preserves DSP timeline continuity;
- bounded control/event queues remain observable on overflow;
- recorder triggering remains independent of event-ring capacity;
- ERLE is valid only during proper far-end-only AEC observations;
- double talk restores the configured fast AEC cadence;
- path/timestamp/discontinuity changes reset stale convergence/alignment state;
- no degradation in delay convergence or double-talk behavior.

## Diagnostics/replay gate

Audio Quality CI exercises the full field-debug contract:

```text
deterministic input
 -> Flight Recorder .apd
 -> apdump info/extract
 -> apreplay through matching processor
 -> bit-exact output comparison
```

This proves tooling/format interoperability. It is not an acoustic-quality claim.

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
- CMake/pkg-config installed SDK consumer tests including runtime diagnostics headers;
- acoustic eval harness threshold/self-test;
- dump parse/extract/replay test;
- strict certification semantic validator;
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

`eval/run_eval.py` accepts 1/2-mic and capture-only/full-duplex cases and can enforce per-case SI-SDR/RMS/render-correlation thresholds. Private product audio remains external.

## Certification semantics

`record.schema.json` defines the interchange structure. `validate_record.py` adds product semantic enforcement. A `product-certified` record requires target performance evidence, corpus revision/cases, artifacts/checksums and a passing >=8 h soak. Current semantic hard gates include p95 <7 ms, p99 <10 ms and nominal zero XRUN/overrun/output-drop/deadline-miss evidence.

A hosted CI release can never manufacture these target-board measurements.

## Target profiling

```bash
perf stat -e cycles,instructions,cache-misses,context-switches ./build/ap_bench 120 0.40 9000 active
perf record -g ./build/ap_bench 120 0.40 9000 active
```

Also capture `top -H`, `/proc/<pid>/status`, CPU online/cpuset state, IRQ affinity, governor/frequency, ALSA XRUNs and product power measurements. Compare FULL/LITE/SAFE, steady-state AEC cadence and SYNC tracking separately so optimization decisions are based on the real hotspot distribution.

Store the final result using `certification/record.schema.json` and validate it with `certification/validate_record.py`. A successful hosted release is not a product certification record.

## v1.2 runtime health telemetry

Runtime metrics v3 distinguishes successful and failed DSP frames, render-push/capture-process failures, the last pipeline error, critical ERROR/FATAL events, and sampled CPU migration. CPU identity is sampled every 64 frames when the worker runs, keeping scheduler diagnostics low-overhead; the counter therefore represents observed CPU changes rather than an exact scheduler migration trace.
