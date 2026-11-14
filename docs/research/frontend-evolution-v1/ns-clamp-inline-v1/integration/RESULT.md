# NS unity applicability: do not promote default pipeline candidate

This is a separate supplementary engineering check. The initial component screen and its 72 measurements are immutable; no performance rerun was performed.

CMakeLists.txt lines 308–313 enables UNITY_BUILD for AP_BUILD_PIPELINE and excludes only module wrappers. NS, noise tracker, window and FFT implementations share a translation unit in the default build. The apparent cross-TU clamp-call overhead of the component benchmark therefore may not exist in production.

CMake was absent. Attempting to obtain its PyPI distribution was explicitly rejected by the environment approval mechanism; no installation succeeded and no alternate download was attempted. Full CMake pipeline build/CTest remains BLOCKED. These manual isolated NS builds are not a substitute for that gate.

Frozen integration/PLAN.md fixes the original algorithm candidate and checks 80/160-frame NS, SAFE/LITE/FULL, far/DT/echo-enable changes, null echo, and reset. Both EMA/MCRA actual runs process 3600 frames each per arm. Complete Float32 output, entire NS state, and result bytes are identical:

- EMA: 34,603,200 bytes, SHA256 34ce8c8c44f030f05d701bf9554eaf83563f871f357ad728cd0f1373a2ec4552.
- MCRA: 38,304,000 bytes, SHA256 096033318503de18d7d51bd4c6a36a15513bef0896d13ff15e33f87cf064be86.

For both modes, complete object disassembly is identical after removing only the differing object-filename header (first two lines). The compiler already inlines the baseline clamp in this unity layout. This is stronger than another noisy host timing comparison: no separate runtime speedup is attributable to this source change in the tested unity build. It does not prove all toolchains produce identical objects.

Decision: NO_PRODUCTION_CHANGE for the default pipeline. Preserve the initial synthetic non-unity REVIEW_ONLY result as a limited measurement, not a claim of 25.1% default pipeline improvement. The candidate adds no justified production benefit in the tested normal compilation structure. No pipeline/SSC305 acoustic/resource promotion, threshold relaxation, repeated timing selection, or production edit is made. A future actual non-unity deployment with measured cost could be a different requirement; do not create one merely to revive this experiment.
