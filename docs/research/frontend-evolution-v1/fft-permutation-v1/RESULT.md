# FE-FFT-PERMUTATION-V1: bounded local result

Base: `8f282f0b8b55cf71285bf77b76598e101f9ba3c0`.
Plan SHA256: `d5d39695041688c8375db39dead10e8b47d63df1d6563f190c2cc1ef3b0a4c13`.

One candidate replaced the existing runtime bit-reversal recurrence with a 512-entry uint16 table, shifted for powers of two up to 512. The generic fallback and all butterfly floating-point operations remain unchanged. No production checkout was changed. Data were deterministic synthetic engineering inputs, including signed zeros, tiny/large finite values and nonfinite stress; not speech recordings or acoustic evidence.

GCC strict O2/ffp-contract=off build completed. 22,000 transforms (11 lengths 1..1024, two directions, 1,000 inputs each) matched baseline bytes exactly. Seven alternating pairs for eight hot size/direction combinations completed, 10,000 transforms per invocation. Process CPU includes identical memcpy overhead. Raw observations are retained in result.txt. Median candidate/baseline ratios:

| length | forward | inverse |
|---|---:|---:|
|32|0.933067125|0.923038478|
|64|0.967770057|0.966445884|
|256|0.956140028|0.973286734|
|512|0.938924540|0.945350093|

Geometric mean 0.9503498490056138 misses the frozen <=0.95 threshold. It must not be rounded to pass. All individual medians meet <=1.10. Candidate rodata grows exactly 1,024 bytes, text grows 101 bytes, bss/data unchanged. No caller-owned state was added.

**NO_ADVANCE under the fixed performance screen.** Do not promote the candidate or rerun to seek a favorable timing sample. These short hosted measurements are preliminary resource evidence, not confidence bounds, full-pipeline throughput or SSC305 performance.

Additional attempted verification preserved separately:
- ASan/UBSan build succeeded; execution exit 1 because LeakSanitizer reports it cannot operate under ptrace. No sanitizer PASS claimed. stdout was buffered and no completed equivalence receipt was retained for this invocation; do not infer completed tests from the runtime duration.
- Full CMake configure was attempted but `cmake: command not found` (exit 127); no build/test/pipeline PCM equivalence claim. The performance-screen rejection already prevents advancing this candidate, so no packages were installed or measurement gates weakened.

No PR or production edit was made by this worker. A research-only archive may preserve this negative result; full-repository exact-head CI and independent review would still be separate.

## Supplementary checks (no new performance decision)

A separately labelled rerun of the same sanitizer binary with `ASAN_OPTIONS=detect_leaks=0` completed exit 0: all 22,000 byte comparisons passed, stderr empty. This is ASan/UBSan coverage only, not LeakSanitizer coverage. Its incidental instrumented timings are retained but are not interpreted or combined with the original performance screen. The original ptrace/LSan failure remains unchanged.

The repository's existing `tests/test_fft.c` compiled and ran successfully against both original and candidate source. One deliberately corrupted table (swapped the first nonzero reversal entries) was rejected by the equivalence harness, exit 1 / `MISMATCH 4 0 8`. This is a measurement negative control, not a second candidate or parameter search.

No CPU affinity pinning, confidence interval or independent holdout timing was used. The fixed single-run screen is only a preliminary resource filter; its NO_ADVANCE remains unchanged.
