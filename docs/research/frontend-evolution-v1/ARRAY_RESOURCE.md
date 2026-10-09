# FE08 1/2/4-mic array resource characterization (component-only)

This is the first bounded FE08 **research component** measurement. The hypothesis,
cases, flags and claim boundary were registered before execution in
[issue #657 comment 6074892584](https://github.com/jiying2007/audio-pipeline/issues/657#issuecomment-6074892584).
The machine contract is
[`array-resource-profile-v1.json`](../../../.github/research/frontend-evolution-v1/array-resource-profile-v1.json).
It neither changes nor promotes the production 2.x two-microphone API, SKU
profile, defaults, release, E001 identity or physical certification.

## Fixed measurement / 固定测量

Use **the existing first-party** `array_native.[ch]`; no alternative BF,
external source, new FFT or implementation change. Exactly five profiles are
measured: C1 linear, C2 linear, C2 FIR33, C4 FIR33 and C4 explicit equal-weight
SPATIAL33. Geometry is fixed ULA broadside with 35 mm adjacent positions;
the spatial bank uses existing explicit center taps, not an MVDR design.
All cases process 2,000 deterministic 160-sample frames at 16 kHz,
with 1/2/4 physical microphone channels separated from render references.

The same hosted Linux run records 3 Native runs under
`CLOCK_THREAD_CPUTIME_ID`, reporting CPU-ms/audio-second plus frame
p50/p95/p99/max for **`fe_array_process` only**. Input generation,
output hashing, stdout, Python verification and runtime/system work are not
inside the timed boundary. Times are **descriptive**, with no hosted absolute
time PASS threshold, because shared-host scheduling can drift. Compute format
and effects are not evaluated here.

Additionally, the harness retains native/sanitizer/AArch32 ELF/source
identities, build/toolchain commands, code/rodata sizes, compiler-generated
static data-plane stack reports, actual array-state bytes, complete-input and
output rolling fingerprints, and functional sanitizer + Arm/QEMU executions.
All profile/control data and associated evidence are SHA-256 sealed.
The seven resealed semantic negatives reject false promotion, changed result
identity, missing profile, breached state ceiling, malformed time ordering,
missing Arm and modified ELF evidence.

The first exact-head execution FAILED its stack parser, preserving unaltered
GCC -fstack-usage receipts. On native/sanitizer, fe_array_init and
fe_array_init_spatial33 are 32-byte dynamic,bounded initialization wrappers,
while on Arm they are static. The per-audio-frame fe_array_process is static
on Native (144 bytes), Sanitizer (288 bytes), and Arm (88 bytes). A separate
post-failure adjudication explicitly accepts only these two named init wrappers
as dynamic,bounded (each <=64 bytes); every other function must remain static,
and any unbounded/nonstatic data-plane annotation still fails closed. This
does not retroactively approve the original failed run; a new exact-head
required summary and fresh-main proof remain mandatory.

The component **state arena safety bound of 16 KiB** checks only this array
object; it explicitly excludes BF adaptation, capture/rate adapter, AEC, RES,
NS, AGC, VAD, Linux runtime queues/threads/stacks, ALSA buffers, allocator,
model weights, CPU cache/RSS and Flight Recorder. It is **not** the planned
192 KiB full C4 profile budget. QEMU timing is never converted to Cortex-A32
performance; native CPU measurements cannot establish SSC305 10 ms deadlines
or real-device p99, thermal, battery/power or throughput under contention.

The decision remains `FE08_ARRAY_RESOURCE_CHARACTERIZATION_NO_PROMOTION`,
even if its engineering checks pass. This is a resource-baseline input for
future FE08 selection, not a proof of four-mic shipping readiness.

## Reproduce / 复验

On a clean exact-source checkout equipped with native GCC, Arm GNU
cross-compiler and QEMU:

```sh
python3 tests/validation/frontend_evolution/array_resource_qualification.py --self-test
python3 tests/validation/frontend_evolution/array_resource_qualification.py \
  --output /tmp/fe08-resource --execution-source "$(git rev-parse HEAD)"
python3 tests/validation/frontend_evolution/array_resource_qualification.py \
  --verify --output /tmp/fe08-resource --execution-source "$(git rev-parse HEAD)"
```

The existing Quality/frontend-reference gate runs the qualification once
and retains the exact-run artifact. Missing compiler, input, Arm execution,
section/stack receipt or file digest fails closed. Passing does not close FE08
or replace true SDK + SSC305 board measurements.

Subsequent work requires independently reviewed stable candidates, numerical
equivalence and full C2/C4 SDK integration before real target budget comparisons.
