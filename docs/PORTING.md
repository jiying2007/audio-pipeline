# Porting Guide

## Minimum platform

The portable core needs C11, `libm`, fixed-width integers and caller-owned memory. The Linux runtime adds pthreads, C11 atomics and POSIX semaphores. ALSA is optional and disabled by default.

The supplied Cortex-A32 toolchain uses `-mcpu=cortex-a32 -mfpu=neon-fp-armv8 -mfloat-abi=hard`. Verify the actual SoC FPU/NEON configuration. A CPU without hardware floating point needs a separate fixed-point port/profile and target re-benchmark; this repository does not claim a completed Q15/Q31 backend.

## PCM contract

Prefer 10 ms periods. Capture is 1/2-channel S16; render reference is mono S16 representing the post-mix/post-gain speaker signal. If capture/playback callbacks are independent, align them with PCM timestamps before forming matched runtime items.

## Two-core Linux wiring

Typical policy:

- audio I/O thread on CPU0;
- DSP worker on CPU1;
- optional `SCHED_FIFO` around priority 20 after validating IRQ priorities;
- no logging/file I/O/malloc/control RPC in the hot PCM path.

The runtime uses bounded SPSC queues. `AP_EFULL` is an explicit producer-overrun signal. Output drops are counted rather than hidden. The DSP worker sleeps on a semaphore when idle.

Runtime lifetime is explicit: initialize once with `ap_runtime_init()`, start/stop the worker as required, then call `ap_runtime_deinit()` before reusing or releasing the caller-owned runtime memory. `ap_runtime_deinit()` stops a running worker and destroys the POSIX semaphore, so route/service re-creation does not leak control-plane synchronization resources.

## ALSA examples

ALSA integration is opt-in:

```bash
cmake -S . -B build-alsa -DAP_BUILD_ALSA_EXAMPLE=ON
cmake --build build-alsa --target ap_alsa_duplex ap_alsa_runtime_duplex
```

`ap_alsa_duplex` shows the simplest synchronous path. `ap_alsa_runtime_duplex` shows the recommended worker path, XRUN recovery, a `-` far-end argument for a NULL/silent render reference, output draining and runtime telemetry.

In a real VoIP application, feed the exact decoded/mixed samples written to the playback device into the AEC reference. On route/codec restart, preserve explicit XRUN/route diagnostics; the DSP delay tracker will treat a large alignment change as a path jump and reset AEC.

## Clock domains

The core has a low-cost reference-domain drift controller: one-sample fine delay estimates feed a ppm IIR and slow sample slips. It is meant to keep AEC alignment stable for small clock mismatch, not to act as a high-fidelity full-band ASRC.

If ALSA/driver timestamps expose capture and playback clocks, use them to establish the base delay and clock ratio; let the DSP correlation correct only residual acoustic/buffering uncertainty.

## 24/32/48 kHz hardware

Best: configure codec/hardware/ALSA to deliver synchronized 16 kHz voice-band streams. The built-in adapter is a low-CPU bring-up fallback and does not provide a production full-band anti-aliasing guarantee.

## VoIP and assistant integration

Calls: send cleaned mono output to the uplink codec; use `vad_active` for DTX only if codec policy expects it.

Assistants: feed the same cleaned mono stream to wake/ASR. Do not run a second independent AEC in the assistant stack. Use VAD probability for wake/endpointing policy.

## Target certification

Run both target wrappers under the shipping kernel/DVFS/audio route. Do not certify from x86 CI or an ARM cross-build alone.
