# Platform Support and Certification

## Support levels

- **Build-supported**: continuously compiled for the stated ABI/SIMD profile.
- **Emulation-executed**: selected executable contracts run under QEMU for that architecture class.
- **Board-validated**: benchmark + functional/acoustic corpus pass on a named real board/kernel/compiler/audio route.
- **Product-certified**: exact shipping build/deploy/execute identity plus approved SKU policy, real acoustic/thermal/power evidence, required route soak, attested evidence and lifecycle archive all pass.

Cross-build/QEMU are never reported as target-board performance.

## Current platform matrix

| Platform class | ABI | SIMD | Repository signal | Product certification |
|---|---|---|---|---|
| generic ARMv7-A | armhf | scalar/VFP | build-supported | pending per SKU |
| Cortex-A7 | armhf | scalar/VFPv4 | build-supported | pending per SKU |
| Cortex-A7 | armhf | NEON/VFPv4 | build + QEMU executed contracts | pending per SKU |
| Cortex-A32 | armhf | NEON/FP-Armv8 | build-supported | pending per SKU |
| generic AArch64 | LP64 | NEON/ASIMD | build + QEMU executed contracts | pending per SKU |
| Arm without hardware floating point | varies | none | unsupported by this profile | separate fixed-point profile required |

Portable DSP code is CPU-model agnostic. CPU names appear only in presets, emulation/certification records and product build configuration.

## Compile-time SKU envelope

Products can reduce physical memory/ROM with:

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

These settings are part of the product artifact fingerprint and must be captured in certification. A smaller envelope is a product capability decision, not a runtime overload response.

Hosted proof-of-pruning measurements have one source of truth: [`ci/resource-baseline.json`](../ci/resource-baseline.json), rendered for humans in [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md). Resource-gate CI regenerates both views from the current hosted GCC Release measurement and fails if either checked-in view is stale.

Those hosted values are build-contract/regression evidence only. They are not ABI constants, target-board RAM claims or product-certification evidence.

## Runtime resource classes

Resource class is independent of CPU model:

| Class | Default internal rate | CALL AEC tail | BF tracking | Intended envelope |
|---|---:|---:|---|---|
| `TINY` | 8 kHz | 48 ms | off | very constrained SKU / reserve headroom |
| `LOW` | 16 kHz | 64 ms | on | constrained voice product |
| `STANDARD` | 16 kHz | 96 ms | on | highest built-in classical quality |

Compile-time build caps may further restrict these defaults. `ap_config_for_resource()` clamps to the binary envelope rather than promising unsupported geometry.

## Required certification record

For each shipping SoC/SKU capture at least:

- product/SKU/board identifier and date;
- exact source revision and approved shipping policy hash;
- CPU model/revision/core count and online cpuset;
- exact shipping compiler executable hash/version, sysroot hash, toolchain-root hash and C flags;
- `ap_build_info_v2_get()` build identity/config digest and certification binary SHA-256 values;
- builder runner and distinct DUT runner identity;
- build, deployed and executed binary SHA-256 equality;
- kernel, governor/DVFS, cpuset and IRQ affinity;
- codec/ALSA period/buffer geometry;
- capture/playback hardware timestamp clock domains and timestamp integration mode;
- selected use case/resource class/stage subset;
- AEC/NS/resampler backend selection;
- active/idle CPU, p95/p99 frame time, RSS, cache misses and context switches;
- XRUN, input-full, output-drop and DSP overrun counters;
- ERLE/convergence, double-talk, path-change and noise corpus results;
- thermal and product power measurements;
- policy-required real route soak; the checked-in Cortex-A32 LOW shipping policy requires 72 hours;
- attested certification bundle and an immutable `product-lifecycle` archive receipt.

Use `certification/record.schema.json` as the machine-readable record contract. The current shipping record format is v4; older v2/v3 records remain historical evidence and do not satisfy the v4 shipping provenance contract.

## Acoustic certification

Use the repository `eval/` schema/runner for public interchange and product-specific thresholding. Real/private WAV corpora remain outside the public repository. A release is not considered acoustically certified just because the eval self-test passes.

Advanced BF/SYNC/wind/microphone-health complexity is evidence-triggered rather than roadmap-triggered: if the real shipping corpus meets the approved SKU policy, retain the lower-cost implementation; if it fails, the failed acoustic gates become the evidence for a scoped algorithm upgrade.

## Unsupported assumptions

Do not assume:

- Cortex-A7 always requires TINY;
- Cortex-A32 always supports STANDARD;
- dual-core means DSP belongs on CPU1;
- NEON/FIFO scheduling is available on every BSP;
- QEMU timings represent silicon timings;
- hardware timestamps are comparable unless they share a defined monotonic clock domain;
- a new software release preserves a previous board certification without rerunning required gates;
- existence of a shipping policy means the SKU has passed certification.
