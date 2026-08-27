# Platform Support and Certification

## Support levels

- **Build-supported**: continuously cross-compiled in CI with the stated ABI/SIMD profile.
- **Board-validated**: target benchmark and functional audio corpus pass on a named board/kernel/compiler/audio route.
- **Product-certified**: board validation plus thermal/power/contention and 8 h soak gates pass for the shipping SKU.

A cross-build is never reported as a Cortex CPU performance claim.

## Current platform matrix

| Platform class | ABI | SIMD profile | CI | Board certification |
|---|---|---|---|---|
| generic ARMv7-A | armhf | scalar/VFP | build-supported | pending per SKU |
| Cortex-A7 | armhf | scalar/VFPv4 | build-supported | pending per SKU |
| Cortex-A7 | armhf | NEON/VFPv4 | build-supported | pending per SKU |
| Cortex-A32 | armhf | NEON/FP-Armv8 | build-supported | pending per SKU |
| generic AArch64 | LP64 | NEON/ASIMD | build-supported | pending per SKU |
| Arm without hardware floating point | varies | none | unsupported | requires separate fixed-point profile |

The portable DSP source is CPU-model agnostic. CPU names appear only in build presets, CI and certification records.

## Product resource classes

Resource class is a product envelope, not an architecture label:

| Class | Default internal rate | CALL AEC tail | Beamformer tracking | Intended use |
|---|---:|---:|---|---|
| `TINY` | 8 kHz | 48 ms | off | very constrained SKU / reserve headroom |
| `LOW` | 16 kHz | 64 ms | on | constrained voice product |
| `STANDARD` | 16 kHz | 96 ms | on | highest built-in classical quality |

Assistant tails are slightly shorter. Products may override individual fields after constructing the resource profile, but every override must be re-certified.

## Certification record requirements

For every shipping SoC/SKU record at least:

- CPU model/revision/core count and online cpuset;
- compiler version, ABI, `-mcpu/-mfpu`/SIMD selection and fast-math state;
- kernel version, governor/DVFS policy and IRQ affinity;
- codec/ALSA period/buffer geometry and capture/playback clock domains;
- selected use case/resource class and AEC backend;
- active/idle CPU, p95/p99 frame time, RSS, cache misses and context switches;
- XRUN/input-full/output-drop/overrun counters;
- ERLE/double-talk/path-change/noise corpus results;
- thermal and product power measurements;
- 8 h runtime soak result.

## Unsupported assumptions

Do not assume that Cortex-A7 always uses `TINY`, that Cortex-A32 always uses `STANDARD`, that a dual-core SoC always assigns DSP to CPU1, or that NEON/FIFO scheduling is always available. Those are product integration decisions proven by the target certification record.
