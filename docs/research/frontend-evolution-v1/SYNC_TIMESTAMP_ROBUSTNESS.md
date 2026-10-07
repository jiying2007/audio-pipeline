# FE04 timestamp robustness diagnostic

This tranche does not tune synchronization. It stress-tests the already-qualified public timestamp
path with three frozen synthetic authority profiles:

- jitter: observe every 10 ms frame with deterministic sample error [0,+1,0,-1];
- dropout: exact timestamp observations except every positive frame divisible by 20 is skipped;
- combined: the same jitter plus the same dropout schedule.

The exact timestamp + AEC-reset result from FE04-SYNC-TIMESTAMP-AUTHORITY-V1 is an immutable
same-run predecessor, not regenerated here. The six speech/fault inputs and physical render
schedule are also unchanged.

The true application transport lead drives render-buffer availability. Only the timestamp
observation is stressed. A route transition therefore remains a transport timeline event:
jitter must report it at frame 800; dropout and combined deliberately skip frame 800 and must
report exactly one event at frame 801. Static and drift must never emit a discrete route event.

Evidence includes the true lead, timestamp lead, observation/dropout flag, effective public-SYNC
delay, route/reset event, reference error against the retained physical render, far-only residual,
speech metrics, exact-predecessor deltas and raw output/trace hashes.

These are deterministic engineering stresses, not measured PCR02/SSC305 timestamp statistics.
A passing result would define a candidate tolerance target only. DUT timestamp accuracy, jitter,
dropout and driver-clock behavior still require real measurement before shipping authority.
The fixed decision is SYNC_TIMESTAMP_ROBUSTNESS_DIAGNOSTIC_NO_PROMOTION.
