# Public API Contract

## Frame and PCM contract

High-level pipeline:

- fixed frame duration: 10 ms;
- capture: 1 or 2 channel interleaved S16;
- render reference: mono S16, post-mix/post-gain signal actually sent toward the DAC;
- output: mono S16;
- I/O rates: 8/16/24/32/48 kHz;
- internal DSP rates: 8 or 16 kHz.

Standalone DSP modules consume normalized float frames unless their API explicitly names S16. Wrong frame sizes or unsupported geometry return `AP_EINVAL`.

## Build capability contract

A binary is composed at CMake time with:

```text
AP_BUILD_PIPELINE=ON|OFF
AP_MODULES=RESAMPLER,HPF,BF,SYNC,AEC,RES,NS,AGC,VAD
```

The installed generated `audio_pipeline_build.h` is the capability source of truth:

```text
AP_HAVE_PIPELINE
AP_HAVE_MODULE_RESAMPLER
AP_HAVE_MODULE_HPF
AP_HAVE_MODULE_BF
AP_HAVE_MODULE_SYNC
AP_HAVE_MODULE_AEC
AP_HAVE_MODULE_RES
AP_HAVE_MODULE_NS
AP_HAVE_MODULE_AGC
AP_HAVE_MODULE_VAD
```

A module omitted from the build has no public standalone declaration in `audio_modules.h`, no implementation TU and no embedded pipeline state. Module-only SDK builds do not install the high-level `audio_pipeline.h`; runtime headers are installed only when the runtime target exists.

## Runtime pipeline composition

`ap_config_t.stages` selects a runtime subset of the DSP stages compiled into the binary. The high-level graph has a fixed safe order; stage bits select/bypass nodes but do not reorder them and do not define an arbitrary DAG.

Validation rules:

- unknown/uncompiled stage requested -> `AP_ESTATE`;
- BF with anything other than two microphones -> `AP_EINVAL`;
- AEC without SYNC -> `AP_EINVAL`;
- RES without AEC -> `AP_EINVAL`;
- delay or clock-drift sub-policy without SYNC -> `AP_EINVAL`.

RESAMPLER is a boundary module and intentionally has no `AP_STAGE_*` bit. Therefore a valid RAW pipeline can have `stages == 0` while still performing I/O/internal-rate adaptation. `ap_pipeline_compiled_stages()` reports build-time DSP stage capability; `ap_pipeline_stages()` reports the initialized instance selection.

## Caller-owned state

The library does not allocate synchronous DSP state.

High-level pipeline:

```c
_Alignas(AP_PIPELINE_STATE_ALIGNMENT)
static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
```

Contract:

- `AP_PIPELINE_STATE_ALIGNMENT` is 16 bytes;
- `AP_PIPELINE_STATE_MAX_BYTES` is the high-level hard static ceiling;
- `ap_pipeline_state_size()` is the exact requirement for that compiled graph;
- omitted build modules physically disappear from this exact size.

Standalone modules use the separate `AP_MODULE_STATE_ALIGNMENT` / `AP_MODULE_STATE_MAX_BYTES` contract and expose exact per-module `ap_module_*_state_size()` functions. Callers should allocate to the exact function whenever the SDK/build is known instead of assuming the hard ceiling.

Current GCC CI demonstrates physical pipeline pruning with full=78,456 B, voice-front-end=9,936 B and RAW=3,392 B. These are verification values for that build, not an ABI promise across compilers or architectures.

The Linux runtime has equivalent `AP_RUNTIME_STATE_ALIGNMENT`, `AP_RUNTIME_STATE_MAX_BYTES`, `ap_runtime_state_size()` and `ap_runtime_state_alignment()` contracts.

## Standalone module lifecycle

`audio_pipeline/audio_modules.h` exposes only modules compiled into the SDK. Stateful modules follow the same model:

```text
state_size -> caller-aligned storage -> init -> bounded process/reset/status
```

They do not allocate memory, create threads or use locks. Standalone adapters call the same private implementations as the high-level pipeline; behavioral fixes must not be duplicated into a second algorithm implementation.

AEC standalone input requires already aligned mono microphone/reference float frames and explicit far-end/double-talk activity. SYNC is independently available when the application wants this repository to produce the aligned reference/activity inputs. NS may run independently; frequency RES is only available in builds containing RES and requires predicted echo.

## Status semantics

| Status | Meaning |
|---|---|
| `AP_OK` | operation completed |
| `AP_EINVAL` | NULL pointer, bad alignment, unsupported enum/rate/geometry, dependency violation or wrong frame size |
| `AP_ENOMEM` | caller-owned state buffer is too small |
| `AP_ESTATE` | requested feature is not compiled, invalid lifecycle or OS control-plane failure |
| `AP_EFULL` | bounded producer queue is full |
| `AP_EEMPTY` | bounded consumer queue is empty |

Do not use `AP_ENOMEM` as a generic invalid-argument status.

## Configuration dimensions

`ap_config_default(profile)` returns the `STANDARD` envelope filtered to the modules physically compiled into the SDK. `ap_config_for_resource(profile, resource_class)` separates product resource policy from runtime overload state.

- use case: CALL / ASSISTANT;
- resource class: TINY / LOW / STANDARD;
- compiled module set: CMake product/SKU choice;
- runtime stage subset: `ap_config_t.stages`;
- runtime quality: FULL / LITE / SAFE.

These dimensions are independent of CPU model.

## Compile-time backend contract

Hard-cut selectors:

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_ENABLE_LINUX_RUNTIME=ON|OFF
AP_ENABLE_FAST_MATH=ON|OFF
```

Backend selectors are meaningful only when the corresponding module is compiled. There are no compatibility aliases for removed build or public stage-enable booleans.

## Threading and runtime

The synchronous pipeline/module APIs are caller-serialized and create no threads. The Linux runtime owns one bounded SPSC worker. It supports both duplex graphs and capture-only graphs; it pushes render into the pipeline only when the instance contains `AP_STAGE_SYNC`.

The runtime deliberately uses lock-free-width 32-bit atomics for realtime counters on ARMv7-A and widens public snapshots to 64 bits. Counters are reset at runtime initialization.
