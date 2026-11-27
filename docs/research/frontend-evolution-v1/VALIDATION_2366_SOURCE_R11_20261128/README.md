# Validation 2.3.66 R11 exact source registration

Issue [#968](https://github.com/jiying2007/audio-pipeline/issues/968) authorizes the
F01 authority binding and F02 canonical reproducer repairs. The registration freezes
remotely retained proposal commit `f7d3f825415c2ca9175c8fc3b4a1c3a36ebafdef`, tree `360db548e6d8f51e6113723b012adb9cb440d462`, after local engineering tests
and before protected source merge.
It does not claim that review, merge or a fresh scientific run already passed.

Relative to R10, the thirteen-member cumulative public source delta changes only
the exact CMake version from 2.3.65 to 2.3.66. All public DSP C/H bytes remain the
same. The additional validation-tool identities bind the authority loader, report
writer, baseline reader, independent negative tests, active v2 authority, reproducer
and its two canonical implementation dependencies.

The original R10 source/derivation/route tests, locks and source receipts remain
byte-exact. New B3/F0, F1-R8 and A3-R7 identity derivatives preserve scientific
function/class source and AST. Only the enumerated receipt/source identities and
two initial build-rejection status literals change. Thresholds, inputs, repetition
counts, budgets and failure preservation do not change.

The outer R11 selectors dispatch only the registered 2.3.66 bytes; the inner R10
selectors retain their rejection of that version. Each new execution must collect
new exact-head evidence. This registration performs no DSP or physical-target run
and inherits no historical acoustic, resource, product or HIL result.
