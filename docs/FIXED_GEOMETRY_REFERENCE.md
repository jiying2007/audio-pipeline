# Fixed-Geometry Reference Alignment

## Purpose

Fixed-geometry reference alignment is an explicit product policy for systems whose speaker-to-microphone and I/O geometry is stable enough that acoustic correlation must not chase moving room reflections.

It is **not** a third CALL/ASSISTANT use-case profile and it does **not** change the default configuration. `ap_config_default()` and `ap_config_for_resource()` continue to use adaptive acoustic delay tracking and clock-drift compensation.

Apply the policy explicitly:

```c
ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);

if (ap_config_apply_reference_alignment_policy(
        &cfg,
        AP_REFERENCE_ALIGNMENT_FIXED_GEOMETRY,
        40u) != AP_OK) {
    /* reject unsupported geometry */
}
```

This sets the initial causal reference anchor to 40 ms and disables correlation-based delay chasing and correlation-based drift compensation.

## Hardware timestamps remain authoritative

`AP_REFERENCE_ALIGNMENT_FIXED_GEOMETRY` does **not** disable hardware timestamp observation. `ap_pipeline_observe_io_timestamps()` remains available and authoritative because capture/playback hardware positions describe I/O alignment directly rather than inferring it from room-acoustic correlation peaks.

A valid timestamp observation may update the active reference delay even when fixed-geometry policy is selected. The fixed anchor is therefore the stable startup/fallback alignment; it is not a prohibition on trusted hardware calibration.

This separation is intentional:

```text
hardware timestamps + stable initial anchor -> I/O/reference alignment
MDF adaptation                         -> moving room reflections
acoustic correlation tracker           -> disabled for fixed geometry
```

## Evidence boundary

The policy was derived from non-shipping research and is not justified by tuning the existing correlation heuristics.

Frozen-candidate replay run `33821302690` used exact v2.3.5 main (`fca59240c8a10ca4fe19b9daf1bf664cd01976ba`) as baseline and kept Hosted Real AEC outside the feedback loop.

Fresh generic-call replay remained 27/27 PASS on validation and shadow. Median ERLE improved by approximately +19.73 dB and +12.03 dB respectively.

Fresh canonical motion replay also remained policy-PASS, but the aligned tail gate rejected a global replacement of adaptive tracking:

- validation worst ERLE delta: about -0.90 dB;
- shadow worst ERLE delta: about -4.65 dB;
- both validation and shadow violated the correlation tail limits.

Therefore fixed geometry is an **opt-in policy only**. The default adaptive policy must remain unchanged.

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

1. canonical motion validation and shadow pass;
2. generic call validation and shadow pass;
3. timestamp-observation contract pass with acoustic tracking disabled;
4. bounded drift/timeline-discontinuity validation;
5. resource and performance regression gates on the target SKU envelope;
6. only after those gates, one-way Hosted Real AEC qualification outside the tuning feedback loop.

A failure in canonical tail behavior means the product must remain on adaptive alignment or use a narrower fixed-geometry deployment scope.
