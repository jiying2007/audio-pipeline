# Tuning Guide

## Separate product decisions

Do not tune by CPU name. Treat these independently:

1. build module set;
2. build geometry envelope;
3. CALL/ASSISTANT use case;
4. runtime TINY/LOW/STANDARD resource class;
5. FULL/LITE/SAFE overload quality;
6. acoustic/device tuning.

A Cortex-A7 may ship STANDARD if the real board meets product gates; an AArch64 product may intentionally use LOW for power.

## Start from measured artifact identity

Always record `ap_build_info()` before acoustic work. A result is not comparable if module set, AEC/NS/SIMD/resampler backend, fast-math or max geometry changed silently.

## AEC

Tune in this order:

1. render reference correctness;
2. route/timestamp correctness;
3. delay convergence;
4. AEC tail length;
5. adaptation rate/stride;
6. RES aggressiveness.

Do not increase `aec_mu` to compensate for a wrong render reference or delay.

ERLE is considered valid only when `erle_valid=1`; double-talk samples must not be used as convergence evidence. Use `aec_convergence_frames/aec_converged` to separate startup/path-change epochs.

If the application knows an echo path changed, call the explicit path-change API instead of waiting for the tracker.

## SYNC and timestamps

Correlation remains the robust fallback. Hardware timestamp observations are useful only when capture and playback positions share a documented monotonic timebase and describe corresponding positions.

Verify route changes, codec reopen and playback gain/mixer behavior. Treat sudden >~20 ms equivalent delay changes as path-change events requiring new AEC convergence.

## Activity / double-talk

The built-in Activity module currently uses a simple energy relationship with hangover. It is intentionally classical and low-cost. Do not tune its far threshold/double-talk ratio from one room or one playback level.

Use a corpus containing near-only, far-only, double-talk, music/content echo and robot motion noise before changing these defaults. If a future coherence/correlation DTD replaces the current method, keep the same standalone/core contract.

## Boundary resampler

Default `BANDLIMITED` uses small fixed FIR filters for current downsampling ratios. Prefer it for production unless target profiling and acoustic tests justify `FAST`.

When comparing modes record:

- passband speech quality;
- stopband alias rejection with motor/PWM/high-frequency noise;
- algorithmic latency/filter delay;
- CPU and state on the shipping SoC.

Do not compare FAST and BANDLIMITED by expecting sample-for-sample equality.

## Noise suppression

EMA remains the default noise estimator. MCRA is an opt-in backend that must be certified on the target corpus. Tune `ns_floor` against quiet speech preservation and stationary/non-stationary noise, not synthetic noise alone.

Frequency RES requires AEC predicted echo and should not be evaluated as a standalone denoiser quality gain.

## AGC / limiter

Tune target and limiter jointly. Input values must be finite and `target_dbfs < limiter_dbfs`.

Assess:

- quiet speech audibility;
- pump/breathing after NS;
- transient clipping;
- background-noise uplift;
- far-end leakage during double-talk.

AGC process cadence is a 10 ms contract; do not feed arbitrary frame durations to standalone AGC.

## VAD

The built-in VAD is intentionally lightweight. When NS is present it may consume upstream speech probability; without NS it uses its own noise/rms history.

For product thresholds use labeled speech/non-speech data and report precision/recall/F1 by noise condition. Do not treat VAD probability as a calibrated neural posterior.

## Beamformer

BF requires two microphones and trustworthy geometry. Tune/validate microphone spacing, polarity, channel order and sample synchronization before changing tracking thresholds.

TINY disables BF tracking by policy; a build with max microphone channels=1 physically removes the valid two-mic configuration.

## Resource/build envelope

Compile-time caps can save substantial RAM, but capability removed at build time cannot be restored by runtime configuration. Choose max delay/AEC tail from real route/path measurements with margin.

Current hosted proof points show full > LOW > TINY state reduction, but shipping caps must be chosen from actual product acoustics, not the hosted byte counts.

## Acceptance corpus

At minimum include:

- far-end speech/music at multiple volumes;
- near speech at multiple distances/angles;
- double-talk;
- path/route changes;
- delay/clock mismatch;
- stationary + non-stationary environment noise;
- robot motors/gears/PWM/structure vibration;
- quiet speech;
- CPU/DDR contention.

Use the canonical `validation/` corpus/report contract for repeatable result exchange and store shipping results in a `certification/` record. Hosted synthetic tests protect contracts; they do not replace listening/product corpus evaluation.

## Automated dataset-driven iteration

The repository has one bounded automatic tuning loop under `validation/tuning/` and `validation/tools/tuning_iteration.py`. It uses the public `ap_tuning_t` control boundary rather than private source pokes, so offline replay and product runtime use the same four supported controls.

Evidence and optimizer permissions are defined in the machine-readable `validation/authority.json`; `validation/tools/authority.py --self-test` keeps that source synchronized with `corpus.schema.json`.

The default hosted loop deliberately separates data roles:

- seed 1307 is development/search data;
- seed 2307 is independent validation data;
- seed 3307 is independent shadow data;
- development input is restricted to `regression` or `research-validation`;
- `validation-grade` is independent evidence, not search input;
- `validation-grade-blind` is reserved for post-candidate promotion and is never a tuning-search dataset;
- product certification is a separate terminal authority under `certification/`, not a validation corpus tier.

Candidate selection is baseline-relative and multi-metric. Pass rate, p10 speech/noise tails, ERLE, VAD and clipping participate in the objective, while validation/shadow tolerances reject a development winner that trades one metric for an unacceptable regression elsewhere.

Pull requests execute the bounded `call-pr-smoke-v1` neighborhood inside the required `Audio Quality Gates -> validation-smoke` path. The standalone `.github/workflows/acoustic-tuning-iteration.yml` is scheduled/manual only and runs the wider `call-v1` search. This avoids executing the same PR optimization twice while retaining a larger recurring discovery search.

A hosted result may only become `ACOUSTIC_CANDIDATE`. It must not mutate `main`, update shipping defaults, or be described as a shipping improvement. Promotion requires the exact candidate revision to pass blind validation, target CPU/RSS/latency evidence, target HIL/soak and Product Certification. This preserves the repository's existing authority hierarchy while allowing GitHub Actions to do useful iterative search automatically.
