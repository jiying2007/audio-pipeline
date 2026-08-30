# Performance and Release Gates

## Principle

Hosted x86 CI, QEMU and Arm cross-builds are regression/correctness signals only. Product performance is certified on the shipping SoC, kernel, compiler, DVFS policy, memory system and audio route.

Optimization is evidence-driven. Additional SIMD or algorithmic complexity is accepted only when target-board/acoustic evidence demonstrates a policy failure or material benefit and the relevant contracts remain valid.

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
sh scripts/compare-perf.sh <base> 7 20
sh scripts/compare-ns-perf.sh <base> 7 50000
sh scripts/compare-resampler-perf.sh <base> 7 100000
sh scripts/compare-runtime-perf.sh <base> 7 100000 10000
```

PR verification uses `origin/main` as the paired base. Main push verification uses the exact pre-push commit. Full-graph/NS/full-runtime comparators use the paired relative regression gate; very small hosted microbenchmarks additionally require their documented absolute noise floor before failing.

## Current low-compute behavior

- stable far-end-only AEC automatically increases adaptation stride after sustained valid observations;
- double talk/reference loss restores the configured fast AEC cadence;
- SYNC delay search compares squared normalized correlation and avoids per-candidate `sqrtf`;
- fractional drift residue is consumed by linear reference interpolation while integer delay crossings remain explicit;
- output backpressure does not create a DSP state discontinuity.

These behaviors still require target-board measurement; hosted timing does not prove Cortex-A7/A32 savings.

## SKU memory/ROM gates

Quality CI verifies physical pruning, not only runtime bypass. Hosted state-size values have one machine source of truth: [`ci/resource-baseline.json`](../ci/resource-baseline.json), with [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md) generated from it.

Resource-gate CI remeasures representative FULL/LOW/TINY/RAW pipeline envelopes and FULL/TINY runtime envelopes, regenerates both views and fails on drift. Diagnostics PCM history is separately caller-owned Flight Recorder memory.

CI also links final consumer executables with section GC and verifies pruning relationships. Exact hosted values are not ABI or target-ROM promises.

## Resampler quality gate

`BANDLIMITED` is default. Supported downsampling ratios have automated tone contracts for passband preservation and stopband attenuation. `FAST` is a separate explicit lightweight implementation and is independently measured; it is not a compatibility alias.

## Product resource/build classes

Runtime resource classes remain tuning envelopes:

- TINY: 8 kHz internal default, shortest built-in tail, no BF tracking;
- LOW: 16 kHz internal, shorter AEC tail;
- STANDARD: 16 kHz internal, highest built-in classical geometry.

Compile-time SKU envelopes can additionally cap max I/O/internal rate, mic count, delay, AEC tail and runtime queue depth. Runtime class and compile-time cap are separate dimensions.

## Initial target-board gates

| Metric | Initial board-validation gate |
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
| Route soak | policy-defined; no XRUN/queue/deadline regression |

Board validation may use shorter engineering soaks; formal shipping certification follows the approved SKU policy. The checked-in Cortex-A32 LOW shipping policy requires 72 hours.

## Target certification collectors

```bash
python3 tools/target_evidence.py benchmark \
  --binary /deployed/exact/ap_bench \
  --output benchmark.json --seconds 120 --idle-seconds 30 --dsp-cpu 1 \
  --sample-rate 16000 --mic-channels 2 --ambient-c 25 \
  --power-input /path/to/live_power --power-scale 1000000 --require-sensors

python3 tools/target_evidence.py route-soak \
  --binary /deployed/exact/ap_alsa_runtime_duplex \
  --output soak.json --capture-device hw:0,0 --playback-device hw:0,0 \
  --farend /path/to/farend.pcm --seconds 259200 --dsp-cpu 1 \
  --sample-rate 16000 --mic-channels 2 --max-xruns 0 --max-overruns 0 \
  --power-input /path/to/live_power --power-scale 1000000
```

`ap_runtime_bench` is a synthetic runtime regression tool and is not accepted as product-route soak evidence. Product Certification builds on `audio-builder`, deploys the exact artifact to `audio-target`, and requires build/deployed/executed SHA-256 equality.

## Realtime correctness gates

Performance acceptance also requires:

- TSan-clean runtime/control/Flight Recorder ownership;
- ASan/UBSan-clean data/control paths;
- output backpressure preserves DSP timeline continuity;
- bounded control/event queues remain observable on overflow;
- recorder triggering remains independent of event-ring capacity;
- ERLE is valid only during proper far-end-only AEC observations;
- double talk restores fast AEC cadence;
- path/timestamp/discontinuity changes reset stale convergence/alignment state;
- no degradation in delay convergence or double-talk behavior.

The v2 runtime exposes these operational signals through one `ap_runtime_metrics_t` structure and `ap_runtime_read_metrics()`: successful/failed DSP frames, queue/overrun counters, render/capture failures, last pipeline error, critical events, sampled CPU changes, queue high-water marks and DSP p50/p95/p99.

## Diagnostics/replay gate

Audio Quality CI exercises:

```text
deterministic input
 -> Flight Recorder .apd
 -> apdump info/extract
 -> apreplay through matching processor
 -> bit-exact output comparison
```

This proves tooling/format interoperability, not acoustic quality.

## CI quality matrix

Required repository signals include architecture boundary lint; GCC/Clang strict builds; MDF/NLMS, EMA/MCRA, precise/fast-math and BANDLIMITED/FAST variants; ASan/UBSan, TSan and fuzz smoke; hosted source coverage; static analysis; SKU composition/RAM/ELF pruning; ARM cross-build/QEMU execution; installed SDK consumers; acoustic evaluation contracts; dump/replay; certification semantic/provenance validation; and Nightly longer fuzz/history tracking.

## Acoustic/product corpus

A real certification corpus should include far-end-only at several playback levels, near-end speech at multiple distances/angles, true double-talk, music/content echo, enclosure/path and gain changes, injected delay and independent clock mismatch, stationary/non-stationary robot noise, quiet speech and CPU/DDR/IRQ contention.

Record ERLE/residual echo, convergence time, SI-SDR or segmental SNR, STOI/PESQ/POLQA where licensing permits, VAD precision/recall, CPU/RSS/cache/context switches, thermal zones, power and XRUN/backpressure counters.

Algorithm escalation is corpus-driven. A passing shipping corpus is evidence to retain the lower-cost baseline.

## Certification semantics

`certification/record.schema.json` and `certification/validate_record.py` accept schema v4 only. A `product-certified` record requires an approved shipping SKU policy, exact shipping toolchain identity, build/deployed/executed binary SHA-256 equality, target performance evidence, real corpus results, thermal/power evidence, a policy-duration passing route soak, artifacts/checksums and deployment provenance.

The certification bundle is attested and final acceptance requires an immutable `product-lifecycle` archive receipt. A hosted CI release can never manufacture these target-board measurements.
