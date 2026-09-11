# Diagnostic reasoning schema

`apdiagnose.py` emits schema version 1.

The stable diagnosis fields are:

- `authority`: always `repository-internal-heuristic-diagnostic-only`;
- `causal_proof`: always `false`;
- `first_fault`: first non-trigger anomaly after deterministic frame/kind ordering, or `null`;
- `intervals`: nearby non-trigger anomalies clustered only by frame distance;
- `anomaly_counts`: counts by anomaly kind;
- `root_cause_hypotheses`: ranked evidence families with deterministic heuristic scores;
- `candidate_chains`: recognized ordered event patterns marked `temporal-association-only`;
- `top_hypothesis`: first ranked hypothesis, or `null`;
- `notes`: evidence-boundary reminders.

Reference comparison also emits schema version 1. Existing raw fields remain additive/backward-compatible:

- `anomaly_count_delta_by_kind`;
- `new_anomaly_kinds` / `resolved_anomaly_kinds`;
- `summary_delta`;
- reference/candidate top hypotheses.

To prevent unequal capture lengths from creating a false apparent improvement or regression, comparison additionally reports:

- `comparison_geometry`: reference/candidate `frames`, `metrics_frames` and `duration_ms`, plus equality flags;
- `raw_count_comparability`: per count metric, the exposure denominator and whether the raw delta is directly comparable;
- `normalized_metrics`: anomaly rate per 1000 frames, quality/VAD transition rates per 1000 metrics frames, and far-end/double-talk/AEC-converged ratios;
- `warnings`: explicit notices when frame count, decoded-metrics exposure or capture duration differs.

`summary_delta` is retained for compatibility. A raw count delta must not be interpreted as an improvement/regression when its `raw_count_comparability.*.directly_comparable` value is false; use the corresponding normalized rate/ratio instead. Max delay-error and drift extrema are not normalized because longer captures inherently have more opportunity to observe an extreme value; unequal durations are therefore warned explicitly.

The schema intentionally does not contain a probability or claim causal certainty. None of these fields participate in HIL, Product Qualification, Product Certification or shipping gates. A future promotion into the released SDK/tool surface requires the normal release-bearing review and SemVer process.
