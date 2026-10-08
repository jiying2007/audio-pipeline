# FE05 NS → controlled AGC → VAD downstream diagnostic

This tranche consumes the sealed FE05-NS-FREQUENCY-RES-V1 evidence instead of regenerating AEC/NS.
The only upstream difference is therefore the already-qualified NS frequency-domain residual-echo
path.

For each case, the sealed NS-only and NS+frequency-RES Float32 streams are copied bit-for-bit into
an offline downstream runner. Both arms receive:

- the same measured far/double-talk trajectory;
- the same NS speech probability (the predecessor requires bit identity across NS arms);
- the production controlled-AGC rule `allow_gain_increase = !(far && !double_talk)`;
- Assistant defaults target=-18 dBFS and limiter=-2 dBFS;
- separate AGC and VAD states, with VAD using upstream NS probability exactly as production does.

The runner retains per-frame AGC state gain, pre/post RMS and peak, limiter activity, VAD internal
noise/hangover, VAD probability/active and arm-difference counts. If a pre-AGC frame and AGC state
are identical, post-AGC must remain identical. If post-AGC audio and VAD state are identical, VAD
results must remain identical.

The original renderer near-present schedule is used only as an audit label for confusion/onset/
offset accounting. It is not passed into AGC or VAD and is not tuning authority.

This is disclosed English speech with synthetic echo and exact synthetic timestamp transport.
The fixed decision is NS_AGC_VAD_DOWNSTREAM_DIAGNOSTIC_NO_PROMOTION. Any AGC/VAD policy change or
KWS/ASR claim requires separate preregistration and fresh independent evidence.
