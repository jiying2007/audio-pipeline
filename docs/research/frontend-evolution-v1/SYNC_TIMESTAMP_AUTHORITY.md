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

The first exact-head execution rejected the original whole-interleaved-file byte-identity guard.
The public reference accessor evaluates current + frac*(previous-current), and exact timestamp
observation drives frac to zero; IEEE signed-zero representation can therefore differ from a direct
oracle copy without changing numerical audio. That failure is retained rather than rewritten.

The amended causal guard separates lanes: the AEC output lane must remain bitwise identical to the
predecessor oracle; the reference lane must be numerically identical sample-by-sample, and every
reference bit mismatch must be signed-zero-only. Any nonzero numerical difference or any AEC output
bit difference fails. Raw evidence is not normalized. Static/drift still have no timestamp route
event, so reset/no-reset packed outputs must remain byte-identical.

Exact synthetic timestamps are not a DUT timing qualification. No shipping API, preset, version,
E001 authority, RES/NS/AGC behavior or product default is changed. The fixed decision is
SYNC_TIMESTAMP_AUTHORITY_DIAGNOSTIC_NO_PROMOTION.
