# Porting Guide

## Minimum platform

Portable core requirements:

- C11 compiler;
- `libm`;
- fixed-width integer types;
- hardware floating point for the supported profile;
- caller-owned aligned storage.

The Linux runtime additionally needs pthreads, C11 lock-free 32-bit atomics and POSIX semaphores. ALSA remains optional.

A CPU without hardware floating point requires a separate fixed-point backend/profile; this repository does not claim Q15/Q31 support.

## Toolchain versus CPU profile

Generic toolchains describe ABI/compiler only:

```text
cmake/toolchains/arm-linux-gnueabihf.cmake
cmake/toolchains/aarch64-linux-gnu.cmake
```

CPU/FPU/SIMD tuning lives in `CMakePresets.json` or the product build:

```bash
cmake --preset armv7a-scalar
cmake --preset cortex-a7-scalar
cmake --preset cortex-a7-neon
cmake --preset cortex-a32-neon
cmake --preset aarch64-neon
```

Do not copy `-mcpu`, `-mfpu` or fast-math policy into a generic toolchain. `AP_ENABLE_FAST_MATH` is a separate, default-OFF product decision.

For vendor BSPs, replace only the compiler/sysroot portion and retain the same backend/build contract where possible.

## SIMD selection

Use:

```text
-DAP_SIMD_BACKEND=SCALAR
-DAP_SIMD_BACKEND=NEON
```

NEON is never required for correctness. The scalar build is a first-class CI target and is the portability baseline.

## AEC selection

Use one compile-time backend:

```text
-DAP_AEC_BACKEND=MDF
-DAP_AEC_BACKEND=NLMS
```

MDF is the default product backend. NLMS is independently tested for constrained/bring-up comparison; there are no legacy boolean compatibility switches.

## State storage

Respect the public alignment contract:

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
```

Use `ap_pipeline_state_size()` for the exact selected build. Misaligned storage is rejected rather than relying on undefined behavior.

## PCM contract

Prefer 10 ms periods. Capture is 1/2-channel S16; render reference is mono S16 representing the post-mix/post-gain speaker signal. If capture/playback callbacks are independent, align them using driver/PCM timestamps before forming matched items.

## Linux runtime integration

`AP_ENABLE_LINUX_RUNTIME=ON` is supported only for Linux. The default runtime does not pin or request realtime scheduling. After validating IRQ affinity, cpusets and privileges, products may explicitly configure a worker CPU and FIFO priority.

Do not place logging, file/network I/O, allocation or control RPC in the PCM/DSP hot path.

## 24/32/48 kHz devices

Best: configure codec/hardware/ALSA to provide a synchronized voice-band stream. The built-in fixed-ratio linear adapter is deterministic and low cost, but it is not a full-band anti-aliasing resampler guarantee.

## Target certification

Cross compilation establishes build support only. Each shipping SoC/SKU must create a record following `PLATFORM_SUPPORT.md` and pass target benchmark, acoustic corpus, contention/thermal/power checks and the 8 h soak.
