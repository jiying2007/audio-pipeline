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

## Resource delivery

Two declared delivery profiles are tracked:
- **conservative**: current SSC305 Cortex-A32 LOW product preset; stability/low-resource default.
- **effect-first**: Cortex-A32 full graph research envelope; may consume more resources but has no shipping authority.

Hosted/QEMU evidence may gate deterministic build identity, ROM/static state and relative regressions. Silicon CPU/thermal/power budgets remain calibration-required and cannot be fabricated from hosted timing.

## Runner baseline

New system-robustness qualification jobs pin `ubuntu-24.04`. Existing workflows are migrated independently; the immutable I025-I040 evidence surfaces are not edited merely to change runner labels.
