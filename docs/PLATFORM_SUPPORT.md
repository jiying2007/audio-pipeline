# Platform Support and Research Evidence

> **Current research scope:** This is a technical-research guide. [RESEARCH_ONLY_EXECUTION.md](RESEARCH_ONLY_EXECUTION.md) owns current execution policy. GitHub Releases, shipping SKU approval and product certification are not research prerequisites. Missing device evidence limits only device claims, not independent software/acoustic experiments. Source rights, measurement integrity and blind-data isolation remain required.

## Support levels

- **Build-supported**: continuously compiled for the stated ABI/SIMD profile.
- **Emulation-executed**: selected executable contracts run under QEMU for that architecture class.
- **Board-validated**: benchmark + functional/acoustic corpus pass on a named real board/kernel/compiler/audio route.
- **Independent device evidence**: the named study retains exact build/deploy/execute identity, real acoustic/resource/thermal/power observations and its preregistered endurance interval. No commercial certificate is issued.

Cross-build/QEMU are never reported as target-board performance.

## Current platform matrix

| Platform class | ABI | SIMD | Repository signal | Independent physical evidence |
|---|---|---|---|---|
| generic ARMv7-A | armhf | scalar/VFP | build-supported | NOT_RUN for a specific target |
| Cortex-A7 | armhf | scalar/VFPv4 | build-supported | NOT_RUN for a specific target |
| Cortex-A7 | armhf | NEON/VFPv4 | build + QEMU executed contracts | NOT_RUN for a specific target |
| Cortex-A32 | armhf | NEON/FP-Armv8 | build-supported | NOT_RUN for a specific target |
| SigmaStar SSC305 `ssc305-cortex-a32-low` | armhf | NEON/FP-Armv8 | exact preset build/install identity + QEMU consumer contract | SSC305 physical measurements NOT_RUN |
| generic AArch64 | LP64 | NEON/ASIMD | build + QEMU executed contracts | NOT_RUN for a specific target |
| Arm without hardware floating point | varies | none | unsupported by this profile | separate fixed-point profile required |

Portable DSP code is CPU-model agnostic. CPU names appear only in presets, emulation/measurement records and build configuration. The SSC305 repository signal proves the exact software build envelope and SDK consumption path only; it does not claim silicon timing, acoustic performance, power, thermal or route qualification.

## Compile-time research envelope

Research builds can reduce physical memory/ROM with:

```text
AP_MODULES
AP_BUILD_MAX_IO_RATE_HZ
AP_BUILD_MAX_INTERNAL_RATE_HZ
AP_BUILD_MAX_MIC_CHANNELS
AP_BUILD_MAX_DELAY_MS
AP_BUILD_MAX_AEC_TAIL_MS
AP_RUNTIME_QUEUE_DEPTH
```

These settings are part of the artifact fingerprint and must be captured in the research report. A smaller envelope is an explicit capability decision, not a runtime overload response.

Hosted pruning measurements have one source of truth: [`ci/resource-baseline.json`](../ci/resource-baseline.json), rendered in [`docs/generated/RESOURCE_BASELINE.md`](generated/RESOURCE_BASELINE.md). Resource-gate CI regenerates both views and fails on drift. Hosted values are regression/build evidence only, not target RAM or product-certification claims.

## Runtime resource classes

Resource class is independent of CPU model:

| Class | Default internal rate | CALL AEC tail | BF tracking | Intended envelope |
|---|---:|---:|---|---|
| `TINY` | 8 kHz | 48 ms | off | very constrained target / reserve headroom |
| `LOW` | 16 kHz | 64 ms | on | constrained voice target |
| `STANDARD` | 16 kHz | 96 ms | on | highest built-in classical quality |

Compile-time caps may further restrict these defaults. `ap_config_for_resource()` clamps to the binary envelope rather than promising unsupported geometry.

## Independent target research record

For each measured target, retain the actual board/SoC identity; exact source revision; compiler, sysroot, flags and `ap_build_info()`; build/deployed/executed binary hashes; kernel/DVFS/cpuset/IRQ configuration; PCM/ALSA geometry and timestamp domain; module and backend configuration; CPU/frame latency/RSS/XRUN/queue metrics; acoustic corpus identity; thermal/power readings; and the actual bounded endurance interval. Keep raw evidence and failure classifications.

Neither an approved SKU policy, a GitHub Release, a product-lifecycle receipt nor an arbitrary 72-hour duration is a research prerequisite. Original certification schemas remain historical records; they do not admit current experiments. Unmeasured fields stay NOT_RUN or unknown, and QEMU is never relabeled as silicon timing.

## Independent acoustic validation

Use the canonical repository [`validation/`](../validation/) framework and its machine-readable `validation/research-authority.json` for public/approved acoustic validation. Real/private WAV corpora remain outside the public repository. The retired `eval/` path is not an authority source. A release is not acoustically certified just because a hosted/public validation or evaluator self-test passes.

Advanced BF/SYNC/wind/microphone-health complexity remains evidence-triggered: compare independent target-corpus results against preregistered research criteria. Retain a lower-cost implementation when measured results support it; report failures as evidence for a scoped algorithm experiment.

## Unsupported assumptions

Do not assume Cortex-A7 always requires TINY, Cortex-A32 always supports STANDARD, dual-core implies CPU1, NEON/FIFO exists on every BSP, QEMU timing represents silicon, hardware timestamps are comparable without a shared monotonic domain, a new software release inherits previous board certification, or a checked-in shipping policy means the SKU has passed certification.
