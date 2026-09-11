# Diagnostic reasoning schema

`apdiagnose.py` emits schema version 1.

The stable top-level fields are:

- `authority`: always `repository-internal-heuristic-diagnostic-only`;
- `causal_proof`: always `false`;
- `first_fault`: first non-trigger anomaly after deterministic frame/kind ordering, or `null`;
- `intervals`: nearby non-trigger anomalies clustered only by frame distance;
- `anomaly_counts`: counts by anomaly kind;
- `root_cause_hypotheses`: ranked evidence families with deterministic heuristic scores;
- `candidate_chains`: recognized ordered event patterns marked `temporal-association-only`;
- `top_hypothesis`: first ranked hypothesis, or `null`;
- `notes`: evidence-boundary reminders.

Reference comparison emits schema version 1 with anomaly-count deltas, new/resolved anomaly kinds, selected numeric summary deltas and the top hypothesis from each side.

The schema intentionally does not contain a probability or claim causal certainty. A future promotion into the released SDK/tool surface requires the normal release-bearing review and SemVer process.
