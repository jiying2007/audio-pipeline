# Local source-preparation validation

Base upstream: 7c82ecf101ad9660398c387caebae7932998c1ab (2.3.63).
Candidate implementation: 33b7651afe5e3df8bf99de43a5efae2bb635b107.
The candidate is not merged and not qualified by this document.

## Actual results

The commands and stdout/stderr in source-tests.log ran on the local prepared
source subset. R7/R8 source tests each rejected 31 negative cases. R8 derivation
rejected 24 cases and verified the five exact derivations, including 102
unchanged scientific functions and two receipt-literal exceptions.
The literal method test rejected 12 cases. Maintenance rebind passed all eight
registered versions. Two route tests passed. B3 and F0 metadata self-tests
passed without DSP execution. Shell syntax and workflow YAML parsing passed.

A committed local partial source snapshot also passed R8 --check-current,
delegating to the unchanged R7 gate for production version 2.3.63. Its local
commit identity is not upstream main, not a full checkout, and not merge evidence.
Frozen Git commit/tree/blob objects used by source tests were retrieved from
public GitHub and reconstructed with every Git object hash verified. No fake
git executable, substituted source reader, or simulated scientific result was used.

## Preserved negative findings and limits

During preparation an overbroad identity substitution altered the F0 image
digest. The derivative checker rejected R8_NONIDENTITY_CONSTANT_CHANGED.
The transformation was narrowed; the original image digest is unchanged and
all derivation checks were rerun successfully. An initial current-source check
on uncommitted changes rejected R7_DIRTY_TRACKED_WORKTREE as intended; after
committing the local snapshot it passed. A route-generation regex initially
rejected an unexpected upload block before writing that workflow; the narrower
pattern produced the reviewed diff.

The environment has Python and GCC, but no CMake or Clang. The full repository
aggregate, ARM builds, F1/A3 builds, and candidate B3/F0 execution have NOT run
here. No hardware or listening claim is made. Exact remote PR CI, independent
review and branch protection remain prerequisites; after merge, fresh-main
verification must run independently.

## Reproduction

On a full checkout, run each command printed in source-tests.log, then
python3 tests/validation/frontend_evolution/fe09_b3_f0_r8_source_admission.py --check-current
and the normal repository Verify gates. Keep production at 2.3.63 for this
source-preparation PR. Execute the candidate only after this admission is
independently reviewed and protected-merged.
