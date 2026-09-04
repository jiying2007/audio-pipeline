# Fixed-Geometry Reference Alignment

## Purpose

Fixed-geometry reference alignment is a named product configuration policy for systems whose speaker-to-microphone and I/O geometry is stable enough that acoustic correlation must not chase moving room reflections.

It is **not** a third CALL/ASSISTANT use-case profile, adds no v2 API/ABI surface, and does **not** change the default configuration. `ap_config_default()` and `ap_config_for_resource()` continue to use adaptive acoustic delay tracking and clock-drift compensation.

Apply the policy with the existing v2 configuration fields before `ap_pipeline_init()`:

```c
ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);

cfg.initial_delay_ms = 40u;
cfg.enable_delay_tracking = 0u;
cfg.enable_clock_drift_compensation = 0u;

if (ap_pipeline_validate_config(&cfg) != AP_OK) {
    /* reject unsupported geometry */
}
```

This uses a 40 ms causal startup/fallback reference anchor and disables correlation-based delay chasing and correlation-derived drift compensation. Products must calibrate the anchor for their actual direct I/O/acoustic geometry; 40 ms is not a universal hardware constant.

## Hardware timestamps remain authoritative

Disabling `enable_delay_tracking` and `enable_clock_drift_compensation` does **not** disable hardware timestamp observation. `ap_pipeline_observe_io_timestamps()` remains available and authoritative because capture/playback hardware positions describe I/O alignment directly rather than inferring it from room-acoustic correlation peaks.

A valid timestamp observation may update the active reference delay while the fixed-geometry policy is in use. Subsequent acoustic correlation cannot move that calibrated delay because acoustic tracking remains disabled. The configured anchor is therefore the stable startup/fallback alignment; it is not a prohibition on trusted hardware calibration.

A stream discontinuity or clock reset deterministically resets SYNC to `initial_delay_ms`; a later trusted timestamp observation may calibrate it again.

This separation is intentional:

```text
hardware timestamps + stable initial anchor -> I/O/reference alignment
MDF adaptation                             -> moving room reflections
acoustic correlation tracker               -> disabled for fixed geometry
```

## Evidence boundary

The policy was derived from non-shipping research and is not justified by tuning the existing correlation heuristics.

Frozen-candidate replay run `33821302690` used exact v2.3.5 main (`fca59240c8a10ca4fe19b9daf1bf664cd01976ba`) as baseline and kept Hosted Real AEC outside the feedback loop.

Fresh generic-call replay remained 27/27 PASS on validation and shadow. Median ERLE improved by approximately +19.73 dB and +12.03 dB respectively.

Fresh canonical motion replay also remained policy-PASS, but the aligned tail gate rejected a global replacement of adaptive tracking:

- validation worst ERLE delta: about -0.90 dB;
- shadow worst ERLE delta: about -4.65 dB;
- both validation and shadow violated the correlation tail limits.

Therefore fixed geometry is an **opt-in product policy only**. The default adaptive policy must remain unchanged.

## Product eligibility

Use fixed geometry only when all of the following are true:

- the direct speaker/DAC-to-microphone/ADC timing path is stable by product design;
- hardware timestamp observations are available when the platform can provide them, or the startup anchor is otherwise calibrated and bounded;
- robot/device motion primarily changes later room reflections rather than the direct I/O path;
- route changes, codec reopen, XRUNs and other topology/timeline changes still use the explicit discontinuity/path-change APIs;
- validation for the target product confirms no unacceptable tail regression.

Do not use this policy as a generic cure for weak delay tracking, unknown hardware latency, Bluetooth/USB routes with changing buffering, or products whose direct acoustic path itself changes materially.

## Promotion gates

The policy must not become a default merely because median ERLE improves. Promotion for a concrete product SKU requires all of the following:

1. canonical motion validation and shadow pass for that deployment scope;
2. generic call validation and shadow pass;
3. timestamp-observation behavior pass with acoustic tracking disabled;
4. bounded drift/timeline-discontinuity validation;
5. resource and performance regression gates on the target SKU envelope;
6. only after those gates, one-way Hosted Real AEC qualification outside the tuning feedback loop.

The repository contract test locks the key separation: wideband acoustic content cannot move the configured anchor, hardware timestamps may calibrate the active delay, later acoustic content cannot chase the calibrated result, and a clock-reset discontinuity returns SYNC to `initial_delay_ms`.

A failure in canonical tail behavior means the product must remain on adaptive alignment or use a narrower fixed-geometry deployment scope.
