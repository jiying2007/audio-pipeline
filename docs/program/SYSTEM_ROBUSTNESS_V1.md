# System Robustness v1

This phase starts after the terminal I025-I040 NS response-mismatch lineage. I025-I040 remain immutable research evidence: they may be regression-checked, but they must not be reopened for floor/gain/tracker/domain/window/OLA search.

## Authority model

S001-S003 are candidate-zero diagnostics. They may create deterministic/public-development evidence, failure heatmaps, first-observable-stage attribution and replay entries. They may not change shipping DSP parameters or authorize a product release.

S004 is only an entry gate. A bounded candidate is allowed only after the same failure:
1. repeats on multiple fresh seeds;
2. repeats across more than one independent development/public source family;
3. first appears at the same stage;
4. is not a measurement-domain artifact;
5. is not a downstream transfer artifact; and
6. fits the declared resource profile.

Validation-grade/blind data remain independent validation and are never optimizer feedback.

## Milestones

- **S001** — end-to-end perturbation map: fixed shipping pipeline, candidate=0, deterministic failure heatmap and replay index.
- **S002** — AEC double-talk / echo-path transition decomposition: reuse the canonical motion/AEC generators and reports, candidate=0.
- **S003** — stage-interaction attribution: combine full-pipeline and isolated-stage evidence into first-observable-stage taxonomy, candidate=0.
- **S004** — bounded candidate authority, closed by default.

## S001 perturbation dimensions

The first deterministic map covers speech/noise SNR, tapped-room proxy, echo-path transition, double-talk balance, two-mic gain/delay mismatch, clipping, DC offset, sample-slip clock-drift proxy, dropped/duplicated frames and robot-like harmonic/start-stop transient noise.

Real measured RIR, Microsoft AEC/DNS development partitions and Pyroomacoustics expansion may be added later as separate source families. They must preserve source identity and authority separation.

## Failure replay

Every failed diagnostic case must be representable by the v1 failure replay schema with input/source identity, seed, perturbation configuration, report/telemetry references, expected signature, shipping output identity, first-observable stage and regression assertion.

Release-policy PASS and diagnostic degradation are separate facts. The initial 5107/5207 exploratory run showed that the permissive smoke policy can remain PASS while severe stress signatures are visible in raw metrics. S001 therefore pre-registers a replay-only diagnostic watch and confirms it on fresh seeds 5307/5407. These watch rules create replay evidence only; they do not authorize a release failure, candidate, parameter change or promotion.

## Resource delivery

Two declared delivery profiles are tracked:
- **conservative**: current SSC305 Cortex-A32 LOW product preset; stability/low-resource default.
- **effect-first**: Cortex-A32 full graph research envelope; may consume more resources but has no shipping authority.

Hosted/QEMU evidence gates deterministic AArch32 build identity, pipeline/runtime state, linked text/rodata and ELF size, direct allocator-symbol absence, algorithmic latency, and repeated QEMU execution identity for both profiles. Silicon CPU ms/audio-second, frame p50/p95/p99, RSS, whole-thread stack, adaptive warm-up, transition worst-case timing, thermal and power remain calibration-required and cannot be fabricated from hosted or QEMU timing.

## Runner baseline

New system-robustness qualification jobs pin `ubuntu-24.04`. Existing workflows are migrated independently; the immutable I025-I040 evidence surfaces are not edited merely to change runner labels.


## S003 public cross-source checkpoint

The first public measured-RIR review is terminal and diagnostic-only. Frozen dEchorate evidence on fresh seeds 8307/8407 showed that both durable S003 failures transfer only partially:

- `severe-near-reference-degradation` reproduced in all 11 fixed rooms for both seeds;
- the original `noise-amplification` component reproduced in 0/11 rooms;
- therefore the original composite durable signatures did not reproduce exactly cross-source;
- raw-prefix watch-clear is retained only as a sanity observation because the watched metrics are input-to-output deltas and raw bypass is structurally near-neutral.

That first review did not open S004. A second public-development review is now also terminal: on the frozen 8-speaker SLR31 Mini LibriSpeech microset, capture clipping reproduced the severe sub-signature in 0/8 utterances on both seeds, while mic gain/delay mismatch reproduced `severe-near-reference-degradation` in 8/8 utterances on both seeds with first observable stage `capture`.

Therefore the multiple-independent-public-dataset repetition prerequisite is closed only for the mic-gain/delay-mismatch severe sub-signature (dEchorate 11/11 on both seeds + SLR31 8/8 on both seeds). It is not closed for capture clipping and it is not a root-cause claim.

S004 remains closed. The mic-mismatch line still requires independently sufficient measurement-domain artifact exclusion, downstream-transfer artifact exclusion, and a later bounded candidate resource-fit qualification. The next authorized work is candidate-zero measurement-domain artifact exclusion using source-domain/oracle metrics independent of output-vs-input delta metrics; no DSP tuning or validation-grade/blind feedback is authorized.
