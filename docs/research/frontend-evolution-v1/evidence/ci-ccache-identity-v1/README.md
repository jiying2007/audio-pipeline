# CI ccache identity regression evidence V1

Result: five actual CMake configurations satisfy the frozen expectations.
See [result](../../CI_CCACHE_IDENTITY_V1_RESULT.zh-CN.md) and
[pre-change freeze](../../CI_CCACHE_IDENTITY_V1_FREEZE.zh-CN.md).

- `run_identity_probe.py`: exact script executed in external scratch; configurable source/build/output paths.
- `summary.json`: measured source identities, cumulative elapsed time, explicit NOT_RUN boundaries.
- Five case directories: original configure stdout/stderr, full command, generated build header,
  source status before/after, cache check-ignore, tracked diff and observation metadata.
- `cmake-version.txt`: actual CMake version output.
- `final-git-status.txt`: empty after probe cleanup, before adding result artifacts.
- `manifest.json`: SHA-256 and byte size of every other file in this directory.

The artificial cache file only demonstrates a reachable filesystem condition. No ccache
executable, remote Actions run, DSP build/test or physical target was executed. The before
case is expected to produce `HEAD-dirty`; a case expectation PASS does not mean that the
strict profile revision equality accepted that identity.
