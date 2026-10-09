# FE06 hard microphone-fault suggestion / 四麦硬故障建议 D0

## Scope, frozen hypothesis and evidence boundary

Preregistered **before implementation or scoring** in [#657 comment 6064106017](https://github.com/jiying2007/audio-pipeline/issues/657#issuecomment-6064106017).
The frozen contract is
[`mic-fault-control-d0.json`](../../../.github/research/frontend-evolution-v1/mic-fault-control-d0.json).
This is a **research-only, deterministic synthetic engineering test**. It neither
qualifies real microphone diagnosis nor changes the shipping 2.x C API,
default BF/NS/AEC graph, presets, release, vendor BSP or E001 identity.

The detector resides only in `tests/validation/frontend_evolution/mic_fault_control.[ch]`.
It is caller-owned and serialized; it does not import or copy AISpeech, Athena,
WebRTC or other vendor algorithms. It accepts interleaved **physical** 4-channel
normalized Float32 at exactly 16 kHz × 160 samples per call, with the channel map
handled *explicitly by its caller*. Render reference is not one of the microphones.

It emits a proposed **nonempty** active mask, never mutates capture, BF state or
the product profile, and never calls the BF mask setter. A separate research-only
caller explicitly decides whether to call the existing
`fe_array_set_active_mask`; that array API continues to reject unsupported
joint fixed spatial33 mask changes atomically.

## Hard signatures and negatives

The only two hard-signature heuristics are intentionally conservative:

- All 160 floats of one physical channel are exactly zero, for three consecutive
  complete frames, while at least two other channels have RMS ≥ 0.01 **and**
  nonzero within-frame variance.
- All 160 floats of one physical channel are exactly +1 or exactly -1 for three
  consecutive complete frames, while at least two other channels are not
  simultaneously stuck at an exact signed rail.

These are construction-specific signals, **not** generally reliable indicators
of noisy/weak/disconnected mics. No energy, coherence, wind, motor tone, clipping,
DOA or speech estimate can independently auto-disable a channel. Bad numeric
input fails atomically without advancing the state or touching the observation.

The fixed 16 kHz / 1600-frame scene matrix is ULA4 and UCA4 × eleven scenes:
six negative controls (all quiet, coherent speech-like, weak-side, diffuse,
correlated motor tone, intermittent all-channel clipping), plus single exact-zero
fault, +rail, -rail, sequential two-channel faults and explicit recovery.
Faults start at zero-based frames 400/800; exact three-frame decisions must occur
at frames 402/802. Manual reductions are 0xF→0xE→0xA. The recovery scenario
restores the first channel at frame 1000 but re-enables it only by *caller action*
at frame 1020, exposing cold-history warmup. A single active channel is allowed
by the existing delay-sum API; an empty mask and a changed spatial33 mask are
rejected. The test compares two independent, identically controlled arrays
running whole-frame versus 17+143-sample processing, and records BF changes
relative to the healthy reference without hiding discontinuities.

## Execution and non-shipping authority

The existing extended Quality/frontend-reference job runs the same research
executable natively, with ASan/UBSan and under real AArch32/QEMU. It records
exact source/config and toolchain commands, compiled ELF hashes, each complete
1600-frame case's input/output/mask rolling fingerprints, per-case output RMS
difference and maximum sample-to-sample discontinuity. Two independent native
executions must be identical. The tool seals the evidence file set with SHA-256
and reruns eight deliberately resealed negative evidence variants through the
semantic verifier. A small rolling fingerprint in a report is **not** equivalent
to retaining and independently rehashing all source PCM/waveform samples.

```sh
python3 tests/validation/frontend_evolution/mic_fault_control.py --self-test
python3 tests/validation/frontend_evolution/mic_fault_control.py \
  --output /tmp/fe06-mic-fault --execution-source "$(git rev-parse HEAD)" --require-arm
python3 tests/validation/frontend_evolution/mic_fault_control.py \
  --output /tmp/fe06-mic-fault --execution-source "$(git rev-parse HEAD)" \
  --verify --require-arm
```

The `--require-arm` mode fails closed when the cross compiler or QEMU is absent;
native-only local runs cannot claim Arm coverage. Only successful exact-head
Quality/Verify and independently preserved artifacts are execution evidence.
The fixed disposition is **`MIC_FAULT_HARD_SIGNATURE_D0_NO_PROMOTION`** regardless
of whether these synthetic tests pass.

No reported result from this tranche is a measured false-positive rate in a real
quiet room or a real microphone disconnected/shorted under motion. Subsequent FE06
qualification requires consent/right-checked real mic, enclosure, wheel/motor,
wind and ground-noise recordings, independent splits, recovery/click audibility
and SSC305 resource and latency measurements. No automatic production mute is
authorized by this synthetic D0.
