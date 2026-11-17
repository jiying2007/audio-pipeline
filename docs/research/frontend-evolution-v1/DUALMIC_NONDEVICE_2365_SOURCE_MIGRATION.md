# Dual-mic host source identity: 2.3.65

This current-tree adapter extension consumes the exact R10 registration already
protected and merged in #958, main 379d6f88bcfc467b88ad31c2a924221d8349a806.
It does not create a new scientific registration or inherit any prior result.
The R7/R9 registrations and the historical 2.3.64 migration document are unchanged.

PR #957 Verify validation-smoke job 133477860541 rejected the previously unknown
2.3.65 in source-identity test setup. The original failure remains a failure;
the source adapter had not reached the downstream audio experiment.

The adapter now pins the R10 plan SHA256 and its exact thirteen reviewed source
identities over the same 56-member public build snapshot. Current committed and
working-tree bytes, revision, version, membership, length and hashes remain
mandatory. Tests migrate real Git fixtures through 2.3.63, 2.3.64 and 2.3.65,
reject every cross-version pairing and continue rejecting unknown versions,
old R8 bytes, dirty/mixed sources and untracked public files.

No codec, DSP parameters, audio/model inputs, acoustic thresholds, measurement
budgets or promotion rules change. The original host integrations must run on
the new exact revision; these metadata tests confer no quality, performance,
physical-device or shipping qualification. This document is bound into each
new adapter execution, alongside the adapter, tests and original registrations.
