# Supplemental public-wrapper regression

This supplements the original frozen proposal; it does not change any of its registered source identities. The public wrapper uses the unchanged baseline module source, candidate BF source, and the explicit minimal BF build header in this directory. That header is not a CMake-generated SDK artifact.

Run from the repository root, with `d=docs/research/frontend-evolution-v1/evidence/dualmic-bf-alias-v1/public-wrapper`:

```
cc -std=c11 -O2 -Wall -Wextra -Werror -I "$d" -I include -I src \
  "$d/test.c" src/modules/ap_beamformer_module.c src/frontend/ap_beamformer.c \
  -lm -o /tmp/bf-wrapper
/tmp/bf-wrapper
```

Repeat with `-DAP_BUILD_BF_DIRECTION_TRACKING=0`. For the baseline, replace only the BF source with `git show 7c82ecf101ad9660398c387caebae7932998c1ab:src/frontend/ap_beamformer.c` saved to a temporary .c file. For the sanitized candidate use `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` and `ASAN_OPTIONS=detect_leaks=0`; leak detection was unavailable under the original test environment's ptrace restrictions.

The tests use 8/16k, exact mic0/mic1/both aliases, fixed/tracking requests, 120 consecutive frames, and reset before zero-based frame index 61 (the 62nd call). Each configuration has 1,440 calls. Tracking-enabled baseline has 960 mismatches; candidate has zero. Tracking-disabled candidate has 720 successful fixed-direction calls and 720 AP_ESTATE rejection checks with state/input/output unchanged. The sanitized enabled configuration also has zero failures. Public-wrapper state is 188 bytes in this build.

These are output/state equivalence checks, not exhaustive route coverage, acoustic gains, or hardware evidence. The original internal regression's 17 lag values and five routes are initial state seeds; tracking can change them and fixed direction can clear a soft fallback. They are not 17 fixed-lag or five persistent-route trajectories.

`host-resource.log` records GCC 14.2 x86_64 O2 compiler stack estimates (384 bytes both versions) and standalone object text (5391 to 5551 bytes). These are not target-board stack, linked firmware size, or measured processing-time claims.
