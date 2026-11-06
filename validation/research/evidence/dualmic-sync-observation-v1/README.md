# SYNC observation-time original local logs

These are unchanged text/JSON files from the original local execution directory.
The manifest seals every copied member; build trees, ELF files and exported
baseline source trees are not included. The baseline is public Git history;
final candidate source is recoverable at `fdcea684300f4f6846fbe130cd567ab7f412158b`
using the adjacent `dualmic-local-source-v1` bundle.

Intermediate fixture and environment failures are retained alongside final logs.
In particular, `baseline-continuous-v1.log` and the initial configure log must not
be relabeled as final candidate runs. The low-resource legacy drift/RES failure
also occurs on the baseline because its 100 ms request exceeds the compiled
60 ms envelope. No thresholds were changed.

See the [result and exact source hashes](../../../../docs/research/frontend-evolution-v1/SYNC_OBSERVATION_TIME_V1_RESULT.zh-CN.md)
for case roles, before/after comparisons and reproducible commands. These logs
are host engineering evidence, not independent speech-quality or target evidence.
