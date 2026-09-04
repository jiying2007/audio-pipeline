# Render-Correlation Validation

## Scope

Since v2.3.6, canonical offline AEC render-correlation metrics evaluate every integer lag in the existing +/-100 ms window. This fixes sparse-grid misses on narrow broadband peaks without changing the metric definition, dataset locks, policy thresholds, product DSP, public API/ABI, or Product Certification authority.

The exact search window is `max_lag = sample_rate // 10`; both input-render and output-render maximum correlation use the same backend and the same complete integer-lag set.

The validation-only helper in `validation/tools/render_corr_exact.c` is compiled by `run_validation.py` on the host and is never installed, exported by CMake, or linked into the product SDK/runtime. The helper only selects the globally strongest integer lag using the same stride-4 normalization terms as the canonical evaluator. `run_validation.py` then recomputes the reported value with `run_validation_engine.normalized_corr(..., stride=4)` and fails closed if the native and canonical scores differ.

## Trust and evidence

Validation fails rather than falling back to the historical sparse scan if the host C11 helper cannot be compiled or loaded. Each report binds the evaluator engine, loader source, helper source, compiled helper binary, correlation-search identifier, and compiler identity. Evidence manifests also include the evaluator/loader/helper source files.

The acceptance policy remains unchanged. In particular, `max_output_render_corr_ratio` remains 1.20 where that policy applies. A larger discovered input or output maximum is treated symmetrically because both are evaluated over the complete integer-lag window.

## Admission evidence

Non-shipping research run `33843998920` compared identical processor/corpus bytes before and after exact search. Known colored geometry and a separate fresh colored seed set each improved from 28/36 to 36/36 by removing ratio-only sparse-grid false failures; fresh tonal stayed 36/36. Canonical motion validation/shadow and generic call validation/shadow for exact-main and fixed-geometry processors retained full pass rates with no new failures. The measured evaluation wall time changed from 300.537 s to 118.364 s (0.394x).

Hosted Real AEC is intentionally excluded from search design and tuning. It remains a one-way final admission gate for the release candidate. A failure there rejects the candidate; it must not be used to tune lag-search parameters or relax thresholds.

## Host requirement

Canonical validation now requires a POSIX host with a C11 compiler available through `CC` or `cc`. Repository CI and trusted validation runners provision this compiler. Missing compiler support is an infrastructure failure, not permission to use the old sparse evaluator.
