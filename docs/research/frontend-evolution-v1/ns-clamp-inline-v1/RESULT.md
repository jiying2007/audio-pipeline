# FE-NS-CLAMP-INLINE-V1 local result: REVIEW_ONLY

Exact base: 6bc79aeae22b104312fee3bc02017f9e89a43ca1. Independent scratch directory; no shared working-tree edits and no main mutation. Open PRs checked before execution were #949, #925 and #714. GitHub searches `inline noise` and `clamp performance`, plus local research text search, found no identical experiment; this is bounded duplicate screening, not proof over all history.

D5-D8 and D30-D49 leave acoustic attribution and Chinese clean-near identifiability limits. This experiment deliberately avoids another gate/AGC/DTD intervention. It changes only cross-translation-unit scalar clamp calls in the existing noise estimator to an exact local inline copy of the canonical ternary expression. No state, arithmetic sequence, parameters, noise model or global API is changed. EMA and MCRA are both tested. Baseline and candidate retain the original public tracker functions under isolated symbol names; production sources are untouched.

PLAN.json and freeze.sha256 were written before any compile or measurement. First strict compilation failed on harness misleading indentation (-Werror); attempt-compile-failure preserves the initial source and logs. Only a line break was changed; no scientific invocation completed before this correction. The corrected execution-source.sha256 identifies the only measured implementation.

Both modes passed 872,000 result plus complete-state byte comparisons, including frame resets, zero/signed zero/tiny/large/NaN/infinity stress and all 17/33/129/257-bin configurations. Nine alternating timing pairs per mode/bin produced 72 raw observations. Eight paired-ratio medians have geometric mean 0.7489864476684026, corresponding to 25.101355% lower process CPU in this host microbenchmark. Every median is <=1.05 and the geometric mean <=0.95. The fixed local screen therefore passes as REVIEW_ONLY, never production promotion. No timing rerun, second candidate, parameter sweep, confidence interval or hardware claim was performed.

Timing uses the same caller and deterministic finite powers for both arms, includes tracker-update calls and next_frame, and excludes reset, equivalence checks, compilation and IO. No LTO, fast-math or core affinity. Very short host timing groups and no held-out environment limit confidence. This is not full NS, pipeline, or SSC305 speedup and not an acoustic improvement claim. State sizes remain 1032B EMA / 2060B MCRA.

Supplementary engineering checks, not new performance decisions:
- ASan/UBSan with ASAN_OPTIONS=detect_leaks=0: both modes exit0, stderr empty, equivalence-only. No LSan claim.
- Deliberate bad clamp return: both modes exit1 / MISMATCH 17 0 20 4. Not a second scientific candidate.
- Existing repository noise/window tests: baseline and candidate both pass for EMA and MCRA. First attempt lacked ap_window.h and failed compilation; the ensuing launch returned127. attempt-unit-missing-window preserves those launch receipts. Adding original ap_window.c/h from the exact base and linking them fixes only test dependencies; no benchmark rerun.

Independent review and full pipeline PCM/state equivalence remain prerequisites before a production PR, followed by exact-head protected CI and fresh-main validation. No Codex/Work task, paid resource, scheduler, hardware execution or source audio collection was used.

## Subsequent integration applicability result

See integration/RESULT.md. Full NS output/state equivalence passed, but default-style unity object code is identical in both modes: baseline was already inlined by the compiler. Consequently NO_PRODUCTION_CHANGE is the final applicability decision for default pipeline; the initial non-unity component timing screen stays intact as a limited observation. Do not promote based on that 25.1% number.
