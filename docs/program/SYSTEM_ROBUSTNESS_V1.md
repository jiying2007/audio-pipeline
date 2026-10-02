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

## S003 mic-mismatch measurement-domain checkpoint

For `FR-S003-MIC-GAIN-DELAY-MISMATCH-V1` → `severe-near-reference-degradation`, the independent SLR31 source-domain oracle passed 8/8 fixed utterances on fresh seeds 9507 and 9607 without invoking the audio pipeline or consuming `near_si_sdr_improvement_db`. The measurement-domain/reference-construction artifact blocker is therefore closed for this narrow sub-signature.

S004 remains closed. The next authorized work is candidate-zero downstream-transfer artifact exclusion; bounded candidate resource fit remains after that. No DSP tuning, validation-grade/blind feedback, or root-cause claim is authorized by this checkpoint.

## S003 downstream-transfer checkpoint

For the mic-gain/delay-mismatch `severe-near-reference-degradation` sub-signature, two independent public families reproduce the symptom at the test-only `prefix-capture` observation. That prefix is source-bound to `AP_STAGE_HPF` only; BF, NS, AGC, VAD and final/full-pipeline processing have not yet occurred. Therefore those downstream stages are not necessary for the symptom to become observable. This does **not** prove HPF is causal.

The scoped S004 prerequisites now have only one unresolved item: `bounded_candidate_resource_fit`. S004 remains closed until a candidate-independent conservative resource envelope is qualified. No parameter search or candidate design is authorized by this checkpoint alone.

## S003 HPF-aware metric-reference checkpoint

A final candidate-zero oracle invalidated the mic-gain/delay-mismatch `severe-near-reference-degradation` line for S004 admission. On the frozen SLR31 8-speaker microset and fresh seeds 9707/9807, the existing raw-clean SI-SDR watch remained severe in 8/8 cases, but the same output scored against an HPF-processed clean reference was severe in 0/8 cases. Replacing the right mismatch channel with the left channel produced bitwise-identical HPF-only output in 8/8 cases on both seeds.

Therefore the first-observable severe symptom is an evaluation reference/metric-target artifact, not evidence that right-channel gain/delay mismatch needs a DSP candidate. This does not mean HPF is defective and does not claim anything about later BF/full-pipeline sensitivity to real microphone mismatch. The candidate line is terminally rejected; resource-fit admission is not applicable and S004 remains closed.

The next authorized work is S003 AEC metric-safe evidence expansion using stage-appropriate AEC metrics (ERLE, render correlation/reduction, transition recovery) and HPF-aware near-end quality where needed. Candidate budget remains zero.

## S003 AEC metric-safe checkpoint

The first AEC metric-safe pass is terminal and candidate-zero. Fresh seeds 10307/10407 both completed all eight S002 transition cases with a consistent stage-appropriate metric map. Near-end-only raw-clean SI-SDR improvement is explicitly rejected as a primary metric; HPF-aware near-end quality is used instead. Far-end/nonlinear cases use ERLE and render-correlation evidence, while transition cases add fixed pre / early-post / late-post residual-to-echo trajectories.

The transition trajectories show a repeatable early residual spike after echo-path, acoustic-gain and render-level changes followed by late recovery. This is evidence, not an algorithm performance verdict, and no new AEC performance threshold or parameter search has been authorized.

The next authorized work is `S003_AEC_TRANSITION_RECOVERY_LATENCY_V1`: measure time-to-recovery relative to each case's own pre-transition residual baseline. Use 100 ms windows; define recovered as residual power no more than 2x pre baseline (+3.01029995664 dB) for 300 ms continuously; search 0..2500 ms and record censored when recovery is not observed. Candidate budget remains zero.
