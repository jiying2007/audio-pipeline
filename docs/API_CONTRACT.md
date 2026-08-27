# Public API Contract

## Frame and PCM contract

- fixed frame duration: 10 ms;
- capture: 1 or 2 channel interleaved S16;
- render reference: mono S16, post-mix/post-gain signal actually sent toward the DAC;
- output: mono S16;
- I/O rates: 8/16/24/32/48 kHz;
- internal DSP rates: 8 or 16 kHz.

Wrong frame sizes or unsupported geometry return `AP_EINVAL`.

## Caller-owned state

The library does not allocate synchronous DSP state.

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
```

Contract:

- `AP_PIPELINE_STATE_ALIGNMENT` is 16 bytes;
- `AP_PIPELINE_STATE_MAX_BYTES` is the hard static ceiling;
- `ap_pipeline_state_size()` is the exact requirement for the selected build;
- `ap_pipeline_state_alignment()` returns the required alignment;
- `ap_pipeline_init()` rejects misaligned storage with `AP_EINVAL`;
- storage smaller than the exact requirement returns `AP_ENOMEM`.

The Linux runtime has equivalent `AP_RUNTIME_STATE_ALIGNMENT`, `AP_RUNTIME_STATE_MAX_BYTES`, `ap_runtime_state_size()` and `ap_runtime_state_alignment()` contracts.

## Status semantics

| Status | Meaning |
|---|---|
| `AP_OK` | operation completed |
| `AP_EINVAL` | NULL pointer, bad alignment, unsupported enum/rate/geometry or wrong frame size |
| `AP_ENOMEM` | caller-owned state buffer is too small |
| `AP_ESTATE` | invalid lifecycle or OS control-plane failure |
| `AP_EFULL` | bounded producer queue is full |
| `AP_EEMPTY` | bounded consumer queue is empty |

Do not use `AP_ENOMEM` as a generic invalid-argument status.

## Configuration dimensions

`ap_config_default(profile)` returns the `STANDARD` envelope. `ap_config_for_resource(profile, resource_class)` separates product resource policy from runtime overload state.

- use case: CALL / ASSISTANT;
- resource class: TINY / LOW / STANDARD;
- runtime quality: FULL / LITE / SAFE.

Callers may tune config fields after construction. An invalid `resource_class` stored in `ap_config_t` is rejected by init.

## Compile-time backend contract

The supported hard-cut build selectors are:

```text
AP_AEC_BACKEND=MDF|NLMS
AP_SIMD_BACKEND=SCALAR|NEON
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
```

There are no compatibility aliases for the removed boolean backend/runtime/SIMD switches.

## Runtime counters on 32-bit Arm

The Linux runtime deliberately uses lock-free-width 32-bit atomics for data-plane counters and widens values to the public 64-bit metrics structure when read. Counters are reset at runtime initialization. At 100 frames/s, a continuously incrementing frame counter reaches 2^32 after roughly 497 days; products requiring longer uninterrupted counter epochs should periodically re-create the runtime or persist higher-level totals outside the realtime object.

## Threading

The synchronous `ap_pipeline_*` API is single-stream/caller-serialized. It does not create threads or locks. The Linux runtime owns one worker and uses bounded SPSC queues; one producer and one consumer are assumed for the queue APIs.
