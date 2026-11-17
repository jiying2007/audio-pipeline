# Composition baseline environment and unresolved GCC 15 finding

## Observed failure, not an R9 production-source change

On the unchanged production 2.3.63 source, fresh-main Verify 42827397960 job 129870269014 (sku-memory-rom) passed on ubuntu-24.04 image 20261101.360.1 with GNU 13.3.0. Source-only R9 Verify 42840850003 instead received ubuntu-26.04 image 20261101.186.1 through the moving ubuntu-latest label, with GNU 15.2.0.

Three jobs failed in that new environment:
- 129917901921: quality / sku-memory-rom.
- 129917903533: ci / composition-size-contract.
- 129917904248: ci / composition-contract (composition-tiny).

All report src/aec/ap_aec_mdf.c:170, error[k] may be used uninitialized, promoted to an error by the unchanged -Werror policy, while compiling the CMake Unity translation unit. The source blob is unchanged (6ee3d3c08f9b38522de3bdc1d81f6cbf06431605). Complete decoded logs, including the original commands, preset settings, compiler identity and diagnostics, are retained in the three gcc15-job-*.json files. No source algorithm changed in this preparation PR.

## Limited environment stabilization

A separate CI commit fixes only these three job definitions to ubuntu-24.04 with explicit CC=gcc-13 and records gcc-13, the actual cc path/version, CMake and architecture. CMake receives CC=gcc-13; the two explicit cc invocations in sku-memory-rom retain the runner default cc and are not represented as explicitly selecting gcc-13. The composition matrix uses one consistent baseline environment. All build/test/install commands, presets, flags, -Werror, resource comparisons and quality thresholds remain unchanged. The ordinary native GCC/Clang matrix and other toolchain gates are unchanged.

This restores the previously verified composition/resource baseline. It does NOT repair the GNU 15 warning, prove that warning false, or claim the ordinary non-Unity native build substitutes for this Unity/SKU configuration. The new head must pass complete CI and fresh-main checks independently. The failed run is retained; it is not silently rerun or represented as a transient success.

## Unresolved compatibility work

GCC 15.2 / Ubuntu 26.04 strict Unity composition compatibility remains open. Reproduce the exact presets and flags from the archived logs, investigate the adaptation/error-buffer control-flow warning, and test a source-level remedy under the required source-admission process before claiming support. Static review sees the error buffer filled before adaptation when do_adapt is true, but this is not sufficient to declare a compiler false positive. Do not suppress the warning or weaken the strict compiler policy.
