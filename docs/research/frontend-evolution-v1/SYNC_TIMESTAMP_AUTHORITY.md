# FE04 exact timestamp authority diagnostic

This tranche compares the existing public timestamp observation API with the acoustic-correlation
SYNC path on the already frozen transport-only faults.

The timestamps are an exact synthetic transport oracle: at 16 kHz each sample is exactly 62500 ns.
For every capture frame the render timestamp is the capture frame-end timestamp minus the known
transport lead. No future audio samples are read to construct timestamps.

The physical playback sequence and synthetic acoustic echo path do not change when the application
transport lead changes. Therefore the timestamp route event in the 320 -> 800 sample case is a
transport timeline event, not evidence that the acoustic impulse response changed.

Two new arms are run:
- timestamp-no-reset: timestamp observation every frame, no acoustic tracking and no AEC reset;
- timestamp-reset: the same timestamp path plus the existing AEC reset on timestamp route_jump.

The strongest causal guard is byte identity: timestamp-no-reset must be byte-identical to the
predecessor oracle arm because both use the same physical render reference. Timestamp references
must also exactly match the retained physical-render input column. Static/drift have no timestamp
route event, so reset/no-reset outputs must remain byte-identical.

Exact synthetic timestamps are not a DUT timing qualification. No shipping API, preset, version,
E001 authority, RES/NS/AGC behavior or product default is changed. The fixed decision is
SYNC_TIMESTAMP_AUTHORITY_DIAGNOSTIC_NO_PROMOTION.
