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

## S003 AEC recovery rebaseline on 100w-50s

Fresh seeds 12707–13007 rebaseline the AEC transition stage-recovery evidence on the confirmed `100w-50s` research geometry. The only 4/4-seed repeatable non-zero adjacent-stage delta is **echo-path-change RES→NS**, at +50/+100/+100/+100 ms. Full-pipeline cross-seed range is 50 ms for echo-path change, 0 ms for speaker-gain step, and 50 ms for render-level step. The previously rejected speaker-gain RES→NS hypothesis remains rejected.

This observation is not a causal NS claim and does not authorize parameter search. The only next authorized step is an independent candidate-zero confirmation of the echo-path-change RES→NS recovery extension; full pipeline remains context-only and S004 stays closed.


## S003 confirmed echo-path RES-to-NS recovery extension

After rebaselining AEC recovery on the confirmed `100w-50s` research measurement geometry, the only retained non-zero stage-extension phenomenon was independently confirmed for `echo-path-change`: RES recovered at 150 ms on all fresh seeds 13107–13407, while NS recovered at 200–250 ms, yielding a repeatable **+50 to +100 ms** RES→NS extension.

This is a stage-boundary timing observation only. It does **not** prove an NS root cause and authorizes no NS/AEC/RES parameter search, no shipping change, and no S004 admission.

The next authorized phase is `S003_AEC_ECHO_PATH_NS_STATE_DECOMPOSITION_V1`: observe existing NS state/telemetry around the echo-path transition and determine which state trajectories align with the confirmed 50–100 ms extension. The work remains candidate-zero and observation-only.


## S003 echo-path NS-state applicability checkpoint

The test-only NS internal-state probe was bitwise output-equivalent to the standard `prefix-ns` processor on fresh seeds 13507–13807. However, the prerequisite RES→NS recovery extension did **not** remain invariant on this next fresh set: the measured extensions were `+100, +50, -50, +100 ms`. Seed 13707 therefore invalidated all-seed applicability of the NS-state attribution experiment.

The earlier 4/4 confirmation on seeds 13107–13407 remains a truthful result for that seed set, but it is no longer treated as an invariant across subsequent fresh seeds. State trajectories on the three applicable seeds remain descriptive evidence only; no state family is ranked and no NS root cause or parameter-search authority is granted.

The next authorized phase is `S003_AEC_ECHO_PATH_RECOVERY_SIGN_VARIABILITY_V1`: explain why NS-minus-RES recovery changes sign and magnitude across fresh seeds under the confirmed `100w-50s` research geometry. Reuse test-only traces and pipeline telemetry; do not tune NS/AEC/RES parameters or define a performance threshold.


## S003 echo-path recovery sign-variability checkpoint

On fresh seeds 13907–14607 under the confirmed `100w-50s` research geometry, RES→NS recovery was `+50/+100 ms` on 7/8 seeds and neutral on seed 14107; no contraction occurred in this fresh set. The test-only NS-state probe remained bitwise-equivalent on all seeds.

The neutral seed is mechanically a **RES-side delay**: RES recovery moved from the common 150 ms to 250 ms while NS remained at 250 ms. Its immediately preceding RES recovery window missed the fixed recovery limit by only `+0.049 dB`. The earlier contraction seed 13707 showed the same direction of variation—RES at 300 ms versus NS at 250 ms—with a preceding RES margin of `+0.196 dB`.

This localizes the remaining sign variability to RES/AEC-side recovery timing, but does not prove an RES root cause or a recovery-threshold artifact. No NS/RES/AEC parameter search, state-family ranking, threshold fitting, shipping change, or S004 admission is authorized.

The next phase is `S003_AEC_ECHO_PATH_RES_SIDE_RECOVERY_VARIABILITY_V1`: observe AEC→RES→NS recovery together with test-only standalone RES gain state and existing AEC telemetry on fresh seeds.


## S003 echo-path RES-side recovery checkpoint

Fresh seeds 14707–15407 were observed on AEC / RES / NS / full under the confirmed `100w-50s` research geometry with a bitwise-equivalent test-only standalone RES-state probe. The non-positive RES→NS signs were seeds 14807, 14907, and 15107.

The two contraction seeds are mechanically `AEC 250 ms → RES 300 ms → NS 250 ms`; the neutral seed is `AEC/RES/NS/full = 300 ms`. Thus every non-positive sign on this fresh set already has late AEC-side recovery, while the contraction seeds add a further +50 ms AEC→RES delay. This is **not** evidence that AEC or RES is a root cause.

The standalone RES gain trajectory is not a sufficient single-state explanation. By 200 ms all eight seeds have converged tightly to approximately 0.100–0.101 gain even though their measured recovery branches differ. No gain threshold, RES alpha, AEC parameter, or recovery-threshold search is authorized.

The next authorized phase is `S003_AEC_ECHO_PATH_RES_GAIN_CONTRIBUTION_DECOMPOSITION_V1`: analysis-only decomposition of the RES recovery curve into the AEC residual trajectory plus exact scalar RES-gain contribution, including a counterfactual recovery calculation with the gain contribution removed/frozen to its preregistered pre-transition reference. Candidate budget remains zero and shipping execution is unchanged.


## S003 RES gain contribution checkpoint

The shipping scalar RES formula was reconstructed exactly on fresh seeds 15507–16207 with test-only probe PCM bitwise-equivalent to standard `prefix-res`. Freezing the pre-transition gain reproduced the standard AEC recovery time on all eight seeds, proving that post-transition RES gain action mechanically accounts for the AEC→RES recovery difference.

However, smoothing/history is not the delay source: the actual-smoothed path and instantaneous-target path recover at the same time on six seeds, while on 15807 and 16207 the smoothed path recovers **100–150 ms earlier** than the instantaneous target. Therefore release-alpha/history tuning is not authorized by this evidence.

The only retained bounded question is the instantaneous target trajectory itself, driven by existing `residual_energy` and `echo_energy`. The next authorized phase is `S003_AEC_RES_TARGET_DRIVER_DECOMPOSITION_V1`, candidate-zero counterfactual analysis only. No gain/alpha search, formula change, root-cause claim, shipping change, or S004 admission is authorized.


## S003 RES instantaneous-target driver checkpoint

Fresh-main counterfactual analysis on seeds 16307–17007 isolated the two existing inputs to the RES instantaneous target. Positive target-induced recovery delay occurred on five seeds. Freezing post-transition `residual_energy` variation removed the positive delay on **5/5** applicable seeds, while freezing `echo_energy` variation removed it on **0/5** and sometimes increased the measured delay. Freezing both drivers removed all target delay.

This establishes `residual_energy` variation as a necessary **mechanical driver** of the retained target delay under the preregistered counterfactual; it does not establish an AEC root cause and authorizes no RES target/formula or AEC parameter change.

The next authorized phase is `S003_AEC_RESIDUAL_ENERGY_TRAJECTORY_DECOMPOSITION_V1`: observe the far-end-only AEC residual before RES using the exact identity between AEC input, echo estimate, their cross term, and residual energy. Start with normalized estimate/input power ratio and similarity; do not inspect/tune filter taps unless this bounded decomposition fails to explain the trajectory.


## S003 AEC residual-geometry checkpoint

Fresh-main evidence on seeds 17107–17807 validates the frame identity and normalized residual geometry after correcting a test-only observation bug caused by the pipeline's intentional `mono/processed` buffer alias. The AEC subtraction input is reconstructed as `m = aec_out + echo_estimate`; probe PCM remains bitwise-equivalent and no shipping/public API surface changes.

Under the confirmed `100w-50s` research geometry, freezing both normalized coordinates `q=E/M` and `rho=C/sqrt(ME)` to their preregistered pre-transition medians yields **50 ms recovery on all eight fresh seeds**. Freezing q or rho individually has seed-dependent effects and is not directionally invariant.

Therefore the retained observation is **joint q/rho residual-geometry variation**, not a q-only or rho-only root cause. No q/rho scaling, filter-weight/tap inspection, AEC parameter search, recovery-threshold change, candidate selection, shipping change, or S004 admission is authorized. The next phase is an independent fresh-seed confirmation of the joint-geometry observation.


## S003 confirmed joint q-rho residual geometry

Independent fresh confirmation on seeds 17907–18607 reproduced the joint residual-geometry counterfactual on **8/8** seeds. Freezing both normalized coordinates `q=E/M` and `rho=C/sqrt(ME)` to their preregistered pre-transition geometry yielded **50 ms** recovery on every seed, while standard AEC recovery was 100–150 ms.

Single-factor freezes did not provide a stable explanation: freezing `rho` alone changed recovery on 0/8 seeds; freezing `q` alone changed only 2/8 seeds and the shifts were in opposite directions (+50 ms and -50 ms). The retained result is therefore **joint geometry change as a repeatable mechanical contributor**, not a q-only, rho-only, or interaction root-cause claim.

The next authorized phase is `S003_AEC_RESIDUAL_GEOMETRY_RAW_COORDINATE_DECOMPOSITION_V1`: stay above filter weights/taps and decompose the joint q/rho change into observed subtraction-input energy `M`, predicted-echo energy `E`, and cross term `C`. Counterfactuals remain analysis-only and use preregistered pre-transition references; no scale sweep, AEC/RES parameter search, filter coefficient inspection, recovery-threshold change, shipping change, or S004 admission is authorized.


## S003 raw residual-coordinate admissibility checkpoint

Fresh seeds 18707–19407 were used to test whether the observed second-order coordinates `M` (AEC subtraction-input energy), `E` (predicted-echo energy), and `C` (cross term) can be independently frozen to preregistered pre-transition medians while the other two remain actual.

They cannot. `freeze_M`, `freeze_E`, and `freeze_C` were each physically inadmissible on **8/8 seeds** because the resulting coordinate triples violated the Cauchy constraint `C² <= M*E`. No invalid value was clamped and no reference was adjusted after observing the result, so no fabricated recovery values exist for these modes.

This closes independent raw-coordinate manipulation as an attribution method. It does not invalidate the confirmed joint q/rho geometry result; instead it demonstrates that the raw coordinates are coupled.

The next authorized phase is `S003_AEC_RESIDUAL_SCALE_GEOMETRY_DECOMPOSITION_V1`, using the exact physically valid factorization `R=M*G`, `G=R/M=1+q-2*rho*sqrt(q)`. Only two analysis-only counterfactuals are authorized: actual M with preregistered pre-transition G, and preregistered pre-transition M with actual G. No return to independent M/E/C freezes, pairwise/scale sweeps, filter inspection, DSP parameter tuning, shipping change, or S004 admission is authorized.


## S003 residual scale-versus-geometry checkpoint

Fresh-main analysis on seeds 19507–20207 used the exact physically valid factorization `R=M*G`, with `G=R/M=1+q-2*rho*sqrt(q)`. Both authorized counterfactuals were physically admissible on 8/8 seeds.

Holding normalized geometry `G` at its preregistered pre-transition median while preserving actual subtraction-input scale `M` made recovery **0 ms on all eight seeds**. Holding `M` fixed while preserving actual `G` improved recovery on only 5/8 seeds and was unchanged on 3/8.

This retains post-transition normalized geometry variation as the stronger repeatable mechanical contributor and scale variation as secondary/seed-dependent. It does **not** establish `G`, `q`, or `rho` as a tunable root-cause parameter and authorizes no factor scaling, filter inspection, AEC/RES tuning, recovery-threshold change, shipping change, or S004 admission.

The next authorized phase is `S003_AEC_GEOMETRY_FREEZE_CONFIRMATION_V1`: one independent fresh-seed confirmation of the single hypothesis that the physically valid `freeze_geometry` counterfactual yields 0 ms recovery on every seed. `freeze_scale` remains descriptive only.


## S003 AEC residual-geometry mechanism closeout

The echo-path transition mechanism line is now terminal at a repeatable, physically valid diagnostic coordinate. On independent fresh seeds 20307–21007, holding normalized residual geometry `G=R/M` at the preregistered pre-transition reference while preserving actual subtraction-input scale `M` produced **0 ms** measured recovery on **8/8** seeds. Standard AEC recovery remained 100–150 ms. Holding scale `M` fixed was not cross-seed invariant.

This confirms post-transition normalized residual geometry change as a repeatable mechanical contributor to the measured recovery trajectory. It does **not** make `G`, `q`, `rho`, filter coefficients, or taps tunable root-cause parameters.

The internal mechanism line therefore stops here. Further filter-weight/tap inspection, q/rho/G scale sweeps, AEC/RES parameter search, or recovery-threshold optimization are outside current authority.

The next authorized phase returns to the system-robustness objective: `S003_AEC_GEOMETRY_SIGNATURE_REPLAY_V1`. The validated geometry trajectory is to be captured as candidate-zero diagnostic telemetry/replay evidence for existing S002/S003 echo-path transition failures, with source identity, measurement geometry, first-observable stage, and regression assertions. No shipping DSP change or S004 admission is implied.


## System Robustness v1 phase closeout

The candidate-zero foundation is now **closed for research progression and active for regression qualification**.

Authoritative checkpoint: main `41614296a4b2541ca7cd81d38e4995038ef2f592`. On that exact main:
- System Robustness v1 passed;
- the core Failure Replay Bank passed;
- AEC Geometry Signature Replay v1 passed;
- Hosted Real Audio and Hosted Real AEC passed;
- canonical Verify completed all 50 jobs with summary success;
- Release and I015 finalization passed.

S001, S002, and S003 intentionally remain active diagnostic/regression workflows with candidate budget zero. Their purpose is now to detect drift, replay known failures, and attribute new failures—not to continue automatic micro-mechanism research.

The NS I025–I040 lineage remains terminal/immutable. The AEC echo-path internal mechanism line is also terminal at the validated diagnostic coordinate `G=R/M`; its result has been converted into durable supplemental replay `SR-S003-AEC-ECHO-PATH-GEOMETRY-V1`. Neither line may be reopened by routine optimization.

**S004 remains closed.** No active candidate has a complete, separately reviewed S004 admission. The mic gain/delay candidate line was rejected as a metric/reference artifact; the AEC geometry line is diagnostic/replay evidence, not a candidate.

The next work is event-driven rather than automatic:
- replay drift → explicit lifecycle review;
- new independent public-development, HIL, or silicon failure not covered by the taxonomy → new candidate-zero diagnosis;
- SSC305 silicon data → calibrate CPU/latency/RSS/stack/warmup/transition/thermal/power against the existing conservative/effect-first build profiles;
- only a separately reviewed bounded candidate that satisfies all S004 preconditions may open S004.

The active regression workflows, replay bank, resource qualification, and Ubuntu 24.04 qualification baseline are retained as long-lived system assets.
