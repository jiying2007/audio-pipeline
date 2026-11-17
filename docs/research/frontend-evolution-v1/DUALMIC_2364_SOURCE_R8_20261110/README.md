# Beamformer alias 2.3.64 source admission R8

This is source-only preparation for implementation proposal
`33b7651afe5e3df8bf99de43a5efae2bb635b107`.
Production remains version 2.3.63. This change neither runs candidate DSP nor
inherits historical qualification results. Independent protected source review
must precede candidate B3/F0 execution.

## Scope

Preserve all historical gates, original 77/66/88 source member sets, scientific
contracts, negative findings, and resource budgets. The 13 existing exception
paths remain the full scope. Only CMakeLists.txt, audio_modules.h, and
ap_beamformer.c differ from R7 in the preregistered candidate.

R8 derives five runners with executable scientific functions unchanged, except
for two individually checked initial receipt-status literals. Runtime rebind
adds an exact six-path 2.3.64 identity mapping. CI retains all older version
routes and gives R8 artifacts separate names. The old R7 route test remains
unchanged as historical evidence; the live aggregate invokes its R8 successor.

## Validation and limitations

See VALIDATION.md and source-tests.log for actual local commands and outcomes.
These are source and metadata checks, not B3/F0, hardware, or shipping approval.
The implementation proposal independently contains focused compiler tests and
baseline/candidate evidence; its results do not qualify this source-prep commit.
