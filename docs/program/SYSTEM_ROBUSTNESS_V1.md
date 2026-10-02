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


## S003 AEC transition recovery-latency checkpoint

Using the metric-safe AEC evidence map, the three transition cases were measured on fresh seeds 10507/10607 with a fixed recovery definition: 100 ms residual-to-echo windows, pre-transition median baseline from -1000..-200 ms, recovered when residual stays within +3.0103 dB (2x power) of baseline for 300 ms continuously.

Observed recovery:
- echo-path change: 200 ms / 200 ms;
- speaker acoustic gain step: 300 ms / 300 ms;
- render-level step: 400 ms / 300 ms;
- censored cases: 0.

These are measurements, not a product requirement or algorithm pass/fail threshold. The next authorized step is candidate-zero stage-prefix recovery decomposition across AEC/RES/NS/AGC/full to locate where the 200-400 ms recovery trajectory is formed or extended. Parameter search remains forbidden.


## S003 AEC stage-recovery decomposition checkpoint

Fresh seeds 10707/10807 decomposed the same transition recovery measurement across AEC, RES, NS, AGC and full-pipeline diagnostic prefixes. The only repeatable stage-boundary recovery extension was the speaker acoustic gain step: AEC 200/200 ms, RES 200/200 ms, NS 300/300 ms, with AGC/full retaining 300/300 ms. The NS boundary also increased the first-1000-ms peak excess and positive excess area on both seeds.

Echo-path and render-level transitions did not show a repeatable single stage-boundary recovery-time extension across both seeds.

This is an observational stage boundary, not an NS root-cause claim. The next authorized work is one focused fresh-seed confirmation using only RES, NS and full for the speaker acoustic gain step. Candidate budget remains zero and NS internal parameter search remains forbidden until that boundary is independently confirmed.


## S003 speaker-gain NS recovery confirmation checkpoint

The focused fresh-seed confirmation rejected the earlier RES→NS recovery-extension hypothesis. On seed 10907, speaker acoustic gain recovery was RES=300 ms, NS=300 ms, full=300 ms (Δ=0). On seed 11007 it was RES=200 ms, NS=300 ms, full=300 ms (Δ=+100 ms). The preregistered rule required NS−RES >=100 ms on every fresh confirmation seed, so the outcome is **REJECTED**.

The prior 10707/10807 observation of +100/+100 ms remains historical evidence, but it does not override the independent confirmation. This closes the NS-boundary hypothesis: there is no authority to claim NS root cause, open NS temporal-state attribution, search NS parameters, or create an NS candidate from this line.

The next authorized work returns to broad candidate-zero AEC recovery variability/source decomposition using stage-appropriate telemetry and residual trajectories. The goal is to explain why recovery varies across seeds without assuming any stage is causal. S004 remains closed.


## S003 AEC recovery variability checkpoint

After the speaker-gain RES→NS +100 ms hypothesis was rejected on independent confirmation seeds, a broader candidate-zero matrix measured four new seeds across three transition cases and AEC/RES/NS/AGC/full profiles. All 60 observations completed with no censoring.

The remaining cross-seed recovery spread is bounded to 100 ms. AEC-stage recovery is stable for all three transition families; variability appears at selected downstream boundaries. In every observation at the slower end of a 100 ms range, the immediately preceding 100 ms recovery window misses the preregistered limit by only 0.058–0.585 dB. The reviewed AEC boolean telemetry does not show a common state change aligned with those slower observations.

This is not yet proof of a measurement-resolution artifact and does not identify a causal stage. The next authorized step is a paired temporal-resolution measurement on fresh seeds: retain the original 100 ms definition and compare it with a 50 ms post-transition grid while keeping the same pre-transition baseline, +3.01029995664 dB recovery limit, and 300 ms continuous hold. Candidate budget remains zero and no DSP parameter search is authorized.

## S003 AEC recovery measurement-resolution checkpoint

Paired measurements on fresh seeds 11507–11807 show that recovery latency is materially sensitive to post-transition measurement geometry. Moving from 100 ms windows/100 ms stride to 50 ms windows/50 ms stride changed 46/60 paired recovery times. Cross-seed range shrank for 5 case/profile pairs, grew for 3, and was unchanged for 7. Therefore the simple explanation “100 ms quantization alone causes recovery variability” is rejected; the evidence does not establish a measurement artifact.

The next authorized work is candidate-zero window-geometry decomposition on exactly three preregistered geometries: `100w-100s`, `100w-50s`, and `50w-50s`. This isolates stride/sampling-grid sensitivity at fixed 100 ms integration length, then integration-window sensitivity at fixed 50 ms stride. No additional geometry sweep, DSP parameter search, performance threshold, causal claim, or S004 admission is authorized.

## S003 AEC recovery window-geometry checkpoint

On fresh seeds 11907–12207, recovery was measured on the same output under exactly three preregistered geometries. At fixed 100 ms integration length, changing stride from 100 to 50 ms reduced cross-seed recovery range in 9/15 case/profile pairs, increased it in 1/15, and left 5/15 unchanged; total range fell from 1000 ms to 600 ms. At fixed 50 ms stride, shortening integration from 100 to 50 ms reduced range in only 1/15 pairs, increased it in 3/15, left 11/15 unchanged, and introduced one censored observation.

This does not change the research measurement default yet. It authorizes a single independent confirmation of `100w-50s` versus `100w-100s` on fresh seeds 12307–12607. Confirmation requires at least 13/15 case/profile ranges to be non-worse, strictly lower summed cross-seed range, and zero censoring under both geometries. Confirmation grants research-measurement-method authority only; it does not authorize DSP tuning, a product recovery requirement, or S004 admission.


## S003 confirmed AEC recovery research geometry

Independent fresh confirmation on seeds 12307–12607 establishes `100w-50s`—100 ms integration with 50 ms stride—as the preferred **research** recovery measurement geometry for future S003 AEC diagnostics. It was non-worse than `100w-100s` in 14/15 case/profile pairs, reduced summed cross-seed recovery range from 1000 ms to 600 ms, and introduced no censoring.

This is a measurement-method authority only. It does not define a product recovery requirement, does not select or modify a DSP candidate, does not alter shipping source/API, and does not open S004. The next authorized phase is to rebaseline retained recovery/variability evidence under `100w-50s`, preserving rejected hypotheses as rejected and admitting only phenomena that survive the confirmed measurement-method change.
