# BF terminal-LF correction: source admission R9

## Why this registration exists

Candidate PR #927 at ea4831c72cbad6f18cdcb3222b6144a67c674493 failed Verify 42837750099 in the protected-base strict whitespace check: src/frontend/ap_beamformer.c had a new blank line at EOF. The redundant terminal LF was accidentally included in proposal 33b7651afe5e3df8bf99de43a5efae2bb635b107 and therefore in R8's exact identity. That omission is an implementation/preflight error, not grounds to relax whitespace or scientific gates.

The decoded failed impact-job log is retained in failed-verify-42837750099.json. Original proposal, failed implementation commit and every R8 file remain unchanged. R9 was created after this failure; it was not preregistered before the failed run.

## Exact scope

Corrected proposal: 1e633c01404767a71b398ec2b44ddef8ee5b2383.
It differs from the original proposal by exactly one removed terminal LF in src/frontend/ap_beamformer.c. The version stays 2.3.64. R9's source proof independently requires all other registered files to match R8, and requires original BF bytes == corrected BF bytes + one LF. The source-preparation PR itself retains production at 2.3.63 and does not alter production CMake/header/BF bytes.

The original 77/66/88 source sets and 13 exception paths remain. All R1–R8 source evidence and scientific budgets/thresholds are retained. R8 continues to reject corrected bytes; R9 rejects the original double-LF bytes and other mutations.

Four exact identity-only derivatives are necessary: B3, F0, F1 source and F1 build. They preserve 95 scientific functions and the bounded process classes; one F1 initial receipt literal is explicitly checked. A3 r5 remains byte-identical because its version/header contract is unchanged. Old R8 derivative and method negatives remain in the aggregate; R9 adds 18 derivative and six method negatives for its four pairs and one literal exception.

Runtime registration retains all eight original mappings and adds an explicitly distinct 2.3.64-r9 source revision. The original runtime checker is archived byte-for-byte, hash-pinned, and its registry is parsed as data to verify all eight mappings remain unchanged. Receipt fields distinguish semantic version 2.3.64 from exact source revision 2.3.64-r9. There is no generic whitespace normalization.

## Actual validation and limitations

source-tests.log records the local commands. R8 source/derivation/method negatives remain 31/24/12; R9 source/derivation/method negatives are 32/18/6. Both same-version runtime revisions and all previous versions reconstruct the original frozen source; the nine registrations pass all prior negative cases plus 14 for R9. Two version-routing tests and B3/F0 metadata self-tests pass without DSP execution.

These checks use a documented partial local checkout with exact fetched public Git objects, not a full remote main. No candidate DSP, full CMake/ARM build, or fresh-main qualification is claimed by local source tests. A first development self-test correctly rejected an outdated negative-count assertion after adding the extra R8-rejection case; the asserted count was corrected to the actual 32 and the suite rerun. This does not reduce any inherited test or scientific threshold.

Run every command in source-tests.log and the normal full repository gates. Source-only preparation requires independent review, protected merge and its own fresh-main verification before corrected implementation execution. The failed candidate may not inherit either R8/R9 preparation results or earlier acoustic results.

Independent read-only review reran the R9 source/derivation/method/runtime/route checks and found no blocking defect. A separate committed corrected-candidate local snapshot passes strict git diff --check and R9 --check; the unchanged R8 --check rejects it with R8_CURRENT_DELTA_MISMATCH. No candidate DSP was executed for these contrast checks. The preparation checkout's R9 --check-current delegates to the original R7/2.3.63 result, as required while production is unchanged.
