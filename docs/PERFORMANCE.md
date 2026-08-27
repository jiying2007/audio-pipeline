# Performance and Release Gates

## Automated benchmarks

`ap_bench` drives the complete 16 kHz two-mic CALL DSP graph and reports average/p50/p95/p99/max per-frame time, 10 ms deadline misses, RTF, state bytes, AEC backend/block/partitions/taps, ERLE, delay error, drift ppm, sample slips, route jumps, AEC resets and RES state.

The optional fourth argument selects the workload:

```bash
./build/ap_bench <seconds> <max_rtf> <max_p99_us> [active|idle]
./build/ap_bench 120 0.40 9000 active
./build/ap_bench 120 0.40 9000 idle
```

`active` is the full-duplex synthetic call workload. `idle` keeps near-end speech/noise but sends a silent render reference, representing assistant/listening periods after the AEC reference tail has drained. CI runs both modes so an optimization cannot silently make the low-duty-cycle path expensive again.

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

## Current low-compute hot-path policy

The default MDF/FFT implementation deliberately trades a small, bounded amount of state/ROM for predictable CPU savings:

- supported 32/64/256/512-point FFTs use a 512-root read-only twiddle table, removing per-butterfly twiddle recurrence and all steady-state trigonometric calls; the raw table is 2 KiB of read-only data;
- MDF maintains a rolling per-bin `sum(|X|^2)` over active partitions, so adaptation normalization no longer rescans the full render history;
- MDF coefficient updates are partition-major for contiguous `X/W` access and use a four-bin Arm NEON complex update where available;
- active-partition traversal and adaptation cadence avoid variable modulo operations in the 2 ms hot loop;
- scratch clearing is limited to the half spectrum that is actually consumed;
- when the complete active render-reference tail has drained to zero, MDF keeps advancing history/cadence but bypasses echo MAC/IFFT until far-end data returns.

The rolling MDF power state increases the current pipeline state by roughly a hundred bytes, while remaining well below the 128 KiB public ceiling. The FFT table affects code/rodata, not caller-owned pipeline state.

GitHub-hosted x86 benchmark changes are useful **directional regression signals only**. Hosted runners are not pinned to identical CPUs, regions or load, so do not publish their percentage delta as Cortex-A32 performance. The same active/idle commands must be rerun on the real target to decide whether the 2 KiB twiddle-table ROM trade is worthwhile for a particular SKU.

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
- active and assistant-idle benchmark smoke;
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
2. Measure active and idle separately; do not optimize a synthetic average workload.
3. Reduce measured AEC tail/active partitions.
4. Increase adaptation stride only after path-change tests.
5. Use hardware timestamps to narrow delay tracking where possible.
6. Profile MDF complex MAC/FFT and NS/RES FFT hot spots before adding more assembly or tables.
7. Use SAFE/broadband RES when headroom is tight.
8. Consider neural NS or a heavier AEC backend only after target measurements demonstrate headroom.

## Target profiling

Use RelWithDebInfo and the shipping governor:

```bash
perf stat -e cycles,instructions,cache-misses,context-switches ./build/ap_bench 120 0.40 9000 active
perf record -g ./build/ap_bench 120 0.40 9000 active
./build/ap_bench 120 0.40 9000 idle
```

Also capture `top -H`, `/proc/<pid>/status`, IRQ affinity, ALSA XRUN counters, thermal zones and product power measurements.
